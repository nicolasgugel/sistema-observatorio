from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

from observatorio.config import SUPPORTED_BRANDS, TARGET_COMPETITORS
from observatorio.html_builder import build_html
from observatorio.io_utils import write_records_csv, write_records_json
from observatorio.models import PriceRecord
from observatorio.scraper import run_live_scrape, run_live_scrape_from_seeds

SCOPE_FOCUSED_IPHONE17_S25 = "focused_iphone17_s25"
SCOPE_FULL_CATALOG = "full_catalog"
SCOPE_CHOICES = [SCOPE_FOCUSED_IPHONE17_S25, SCOPE_FULL_CATALOG]

DEFAULT_FULL_COMPETITORS = [
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
        description="Scrapping de productos de Santander Boutique + competidores y generacion de comparativa HTML."
    )
    parser.add_argument("--max-products", type=int, default=500, help="Numero maximo de productos base.")
    parser.add_argument(
        "--brand",
        type=str,
        default="all",
        choices=["all", *list(SUPPORTED_BRANDS)],
        help="Marca base a extraer desde Santander Boutique. Usa 'all' para Samsung+Apple en una sola corrida.",
    )
    parser.add_argument(
        "--competitors",
        type=str,
        default=",".join(DEFAULT_FULL_COMPETITORS),
        help="Lista separada por coma. Ejemplo: Amazon,Fnac,Vodafone",
    )
    parser.add_argument("--headed", action="store_true", help="Ejecuta Playwright con navegador visible.")
    parser.add_argument(
        "--scope",
        type=str,
        default=SCOPE_FOCUSED_IPHONE17_S25,
        choices=SCOPE_CHOICES,
        help=(
            "Scope de semillas base de Santander: "
            "'focused_iphone17_s25' (default, solo iPhone 17* y Galaxy S25*) "
            "o 'full_catalog' (catalogo completo)."
        ),
    )
    parser.add_argument("--template", type=Path, default=Path("assets/templates/price_comparison_v10_dual_brand.html"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--html-out", type=Path, default=Path("output/price_comparison_live.html"))
    return parser.parse_args()


def _resolve_brands(brand_arg: str) -> list[str]:
    if brand_arg.strip().lower() == "all":
        return list(SUPPORTED_BRANDS)
    return [brand_arg]


def _resolve_max_products(brand: str, requested: int) -> int:
    # Default full run: Samsung catalog is ~10-12 products, Apple requires large cap to cover full offer.
    if requested == 500 and brand == "Samsung":
        return 12
    return requested


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


async def _run() -> None:
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    competitors = [x.strip() for x in args.competitors.split(",") if x.strip()]
    brands = _resolve_brands(args.brand)

    all_seeds = []
    all_records: list[PriceRecord] = []
    seeds_by_brand: dict[str, list] = {}
    base_keys_by_brand: dict[str, set[tuple[str, str, int | None]]] = {}

    # Phase 1: build Santander base for each brand first.
    for brand in brands:
        brand_max_products = _resolve_max_products(brand, args.max_products)
        seeds, santander_records = await run_live_scrape(
            max_products=brand_max_products,
            brand=brand,
            competitors=["Santander Boutique"],
            seed_scope=args.scope,
            headed=args.headed,
        )
        seeds_by_brand[brand] = seeds
        base_keys_by_brand[brand] = {(r.device_type, r.model, r.capacity_gb) for r in santander_records}
        all_seeds.extend(seeds)
        all_records.extend(santander_records)
        print(
            f"[OK] {brand} (fase Santander): "
            f"max_products={brand_max_products}, productos base {len(seeds)}, "
            f"registros Santander {len(santander_records)}"
        )

    # Phase 2: scrape remaining competitors using exactly Santander-covered products.
    other_competitors = [c for c in competitors if c != "Santander Boutique"]
    for brand in brands:
        if not other_competitors:
            continue
        competitor_records = await run_live_scrape_from_seeds(
            seeds=seeds_by_brand.get(brand, []),
            brand=brand,
            competitors=other_competitors,
            base_covered_keys=base_keys_by_brand.get(brand),
            seed_scope=args.scope,
            headed=args.headed,
        )
        all_records.extend(competitor_records)
        print(
            f"[OK] {brand} (fase competidores): "
            f"competidores={len(other_competitors)}, registros={len(competitor_records)}"
        )

    records = _dedupe_price_records(all_records)

    latest_json = args.output_dir / "latest_prices.json"
    latest_csv = args.output_dir / "latest_prices.csv"
    unified_csv = args.output_dir / "unified_last_scrapes_with_book.csv"
    hist_json = args.output_dir / f"prices_{timestamp}.json"
    hist_csv = args.output_dir / f"prices_{timestamp}.csv"

    write_records_json(records, latest_json)
    write_records_json(records, hist_json)
    write_records_csv(records, latest_csv)
    _write_unified_csv(records, unified_csv, source_snapshot=hist_csv.name)
    write_records_csv(records, hist_csv)
    build_html(args.template, args.html_out, records)

    print(f"[OK] Marcas ejecutadas: {', '.join(brands)}")
    print(f"[OK] Scope: {args.scope}")
    print(f"[OK] Productos base detectados (total): {len(all_seeds)}")
    print(f"[OK] Registros de precio: {len(records)}")
    print(f"[OK] JSON latest: {latest_json}")
    print(f"[OK] CSV latest: {latest_csv}")
    print(f"[OK] CSV unificado: {unified_csv}")
    print(f"[OK] HTML comparativa: {args.html_out}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(_run())
