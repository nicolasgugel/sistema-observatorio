from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from observatorio.html_builder import build_html
from observatorio.io_utils import write_records_csv, write_records_json
from observatorio.models import PriceRecord, ProductSeed
from observatorio.scraper import run_live_scrape_from_seeds, scrape_santander_base_products
from observatorio.text_utils import normalize_text

DEFAULT_FAST_COMPETITORS = [
    "Santander Boutique",
    "Amazon",
    "Media Markt",
    "Grover",
    "Movistar",
    "Rentik",
    "Samsung Oficial",
    "Apple Oficial",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Runner rapido para observatorio (scope fijo: iPhone 17* + Galaxy S25*). "
            "Mantiene salidas CSV/JSON/HTML del pipeline principal."
        )
    )
    parser.add_argument(
        "--brand",
        type=str,
        default="all",
        choices=["all", "Samsung", "Apple"],
        help="Marca a ejecutar. Usa 'all' para Samsung+Apple.",
    )
    parser.add_argument(
        "--max-products",
        type=int,
        default=500,
        help=(
            "Cap de descubrimiento de seeds en Santander. "
            "Para Samsung con 500 se ajusta automaticamente a 12."
        ),
    )
    parser.add_argument(
        "--competitors",
        type=str,
        default=",".join(DEFAULT_FAST_COMPETITORS),
        help="Lista separada por coma. Ejemplo: Santander Boutique,Amazon,Media Markt",
    )
    parser.add_argument("--headed", action="store_true", help="Ejecuta Playwright con navegador visible.")
    parser.add_argument("--template", type=Path, default=Path("assets/templates/price_comparison_v10_dual_brand.html"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--html-out", type=Path, default=Path("output/price_comparison_live.html"))
    return parser.parse_args()


def _resolve_brands(brand_arg: str) -> list[str]:
    if normalize_text(brand_arg) == "all":
        return ["Samsung", "Apple"]
    return [brand_arg]


def _resolve_max_products(brand: str, requested: int) -> int:
    if requested == 500 and brand == "Samsung":
        return 12
    return requested


def _is_focused_seed(seed: ProductSeed) -> bool:
    if normalize_text(seed.device_type) != "mobile":
        return False
    model_n = normalize_text(seed.model)
    brand_n = normalize_text(seed.brand)
    if brand_n == "apple":
        return bool(re.search(r"\biphone\s*17\b", model_n) or re.search(r"\biphone\s+air\b", model_n))
    if brand_n == "samsung":
        return bool(re.search(r"\bs\s*25\b", model_n) or re.search(r"\bs25\b", model_n))
    return False


def _compact_focused_seeds(seeds: list[ProductSeed]) -> list[ProductSeed]:
    def score(seed: ProductSeed) -> tuple[int, int, int]:
        code = str(seed.product_code or "").strip().upper()
        if not code:
            return (0, 0, 0)
        # Santander suele exponer varias variantes de SKU para la misma capacidad.
        # Priorizamos codigos primarios (alfabeticos) sobre aliases/campanas (p. ej. prefijos 2/3).
        starts_alpha = 1 if code[:1].isalpha() else 0
        non_alias_prefix = 1 if not code.startswith(("2", "3")) else 0
        return (1, starts_alpha + non_alias_prefix, len(code))

    compact: dict[tuple[str, str, int | None], ProductSeed] = {}
    for seed in seeds:
        if not _is_focused_seed(seed):
            continue
        key = (normalize_text(seed.device_type), normalize_text(seed.model), seed.capacity_gb)
        current = compact.get(key)
        if current is None:
            compact[key] = seed
            continue
        if score(seed) > score(current):
            compact[key] = seed

    ordered = sorted(compact.values(), key=lambda s: (normalize_text(s.model), s.capacity_gb or 0))
    return ordered


def _dedupe_price_records(records: list[PriceRecord]) -> list[PriceRecord]:
    by_key: dict[tuple, tuple[int, PriceRecord]] = {}
    for idx, record in enumerate(records):
        key = (
            record.brand,
            record.retailer,
            record.device_type,
            record.model,
            record.capacity_gb,
            record.offer_type,
            record.term_months,
        )
        current = by_key.get(key)
        if current is None:
            by_key[key] = (idx, record)
            continue
        current_idx, current_record = current
        if float(record.price_value) < float(current_record.price_value):
            by_key[key] = (current_idx, record)

    ordered = sorted(by_key.values(), key=lambda item: item[0])
    return [record for _, record in ordered]


def _write_unified_csv(records: list[PriceRecord], path: Path, source_snapshot: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        path.write_text("", encoding="utf-8")
        return

    rows = []
    for record in records:
        row = record.to_dict()
        row["source_snapshot"] = source_snapshot
        row["source_snapshots"] = source_snapshot
        rows.append(row)

    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


async def _discover_compact_santander_seeds(*, brand: str, max_products: int, headed: bool) -> list[ProductSeed]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed)
        request_context = await pw.request.new_context()
        try:
            raw_seeds = await scrape_santander_base_products(
                browser=browser,
                request_context=request_context,
                max_products=max_products,
                brand=brand,
            )
        finally:
            await request_context.dispose()
            await browser.close()

    compact = _compact_focused_seeds(raw_seeds)
    print(
        f"[FAST] {brand}: seeds discovery={len(raw_seeds)}, "
        f"focused+compact={len(compact)}"
    )
    return compact


async def _run() -> None:
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    competitors = [x.strip() for x in args.competitors.split(",") if x.strip()]
    brands = _resolve_brands(args.brand)

    all_seeds: list[ProductSeed] = []
    all_records: list[PriceRecord] = []

    for brand in brands:
        brand_max_products = _resolve_max_products(brand, args.max_products)
        seeds = await _discover_compact_santander_seeds(
            brand=brand,
            max_products=brand_max_products,
            headed=args.headed,
        )
        all_seeds.extend(seeds)
        if not seeds:
            print(f"[FAST] {brand}: sin semillas en scope, se omite scraping.")
            continue

        records = await run_live_scrape_from_seeds(
            seeds=seeds,
            brand=brand,
            competitors=competitors,
            base_covered_keys=None,
            seed_scope="full_catalog",
            headed=args.headed,
        )
        all_records.extend(records)
        print(
            f"[FAST] {brand}: competidores={len(competitors)} "
            f"seeds_compact={len(seeds)} records={len(records)}"
        )

    records = _dedupe_price_records(all_records)

    latest_json = args.output_dir / "latest_prices.json"
    latest_csv = args.output_dir / "latest_prices.csv"
    unified_csv = args.output_dir / "unified_last_scrapes_with_book.csv"
    hist_json = args.output_dir / f"prices_{timestamp}.json"
    hist_csv = args.output_dir / f"prices_{timestamp}.csv"
    hist_html = args.output_dir / f"price_comparison_live_{timestamp}.html"

    write_records_json(records, latest_json)
    write_records_json(records, hist_json)
    write_records_csv(records, latest_csv)
    _write_unified_csv(records, unified_csv, source_snapshot=hist_csv.name)
    write_records_csv(records, hist_csv)
    build_html(args.template, args.html_out, records)
    build_html(args.template, hist_html, records)

    print(f"[OK] Runner: run_observatorio_focus_fast.py")
    print(f"[OK] Scope fijo: iPhone 17* + Galaxy S25* (mobile)")
    print(f"[OK] Marcas ejecutadas: {', '.join(brands)}")
    print(f"[OK] Competidores: {', '.join(competitors)}")
    print(f"[OK] Productos base compactados (total): {len(all_seeds)}")
    print(f"[OK] Registros de precio: {len(records)}")
    print(f"[OK] JSON latest: {latest_json}")
    print(f"[OK] CSV latest: {latest_csv}")
    print(f"[OK] CSV unificado: {unified_csv}")
    print(f"[OK] JSON historico: {hist_json}")
    print(f"[OK] CSV historico: {hist_csv}")
    print(f"[OK] HTML historico: {hist_html}")
    print(f"[OK] HTML comparativa: {args.html_out}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(_run())
