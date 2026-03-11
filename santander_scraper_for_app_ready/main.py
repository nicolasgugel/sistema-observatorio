"""
Orquestador principal del sistema comparador de precios.

Flujo:
1. Scraper Boutique → lista de PriceRow (fuente de verdad)
2. Derivar targets únicos (model + capacity_gb) del catálogo Boutique
3. Pasar targets a cada scraper de competidor
4. Combinar todos los PriceRow en un único CSV

Uso:
    python main.py                                    # Boutique solo → CSV
    python main.py --scrapers boutique grover         # Boutique + Grover → CSV
    python main.py --scrapers boutique amazon mediamarkt rentik apple_store samsung_store
    python main.py --brands apple                     # Solo targets Apple
    python main.py --scrapers boutique --test         # Modo prueba (pocos productos)
    python main.py --output precios_semana1           # Prefijo de archivo
    python main.py --targets-file targets.json        # Omite Boutique, carga targets de JSON
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

from exporters.csv_exporter import export_to_csv
from models.price_row import PriceRow
from scrapers.santander_boutique import SantanderBoutiqueScraper
from scrapers.grover import GroverScraper
from scrapers.rentik import RentikScraper
from scrapers.amazon import AmazonScraper
from scrapers.mediamarkt import MediaMarktScraper
from scrapers.apple_store import AppleStoreScraper
from scrapers.samsung_store import SamsungStoreScraper
from scrapers.movistar import MovistarScraper


# Scrapers de competidores disponibles (todos extienden CompetitorBase)
COMPETITOR_SCRAPERS: dict[str, type] = {
    "grover": GroverScraper,
    "rentik": RentikScraper,
    "amazon": AmazonScraper,
    "mediamarkt": MediaMarktScraper,
    "apple_store": AppleStoreScraper,
    "samsung_store": SamsungStoreScraper,
    "movistar": MovistarScraper,
}

ALL_SCRAPERS = ["boutique"] + list(COMPETITOR_SCRAPERS.keys())
DEFAULT_OUTPUT_PREFIX = "master_prices"


def setup_logging(verbose: bool = False) -> None:
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        colorize=True,
    )
    log_file = f"scraping_{datetime.now().strftime('%Y%m%d_%H%M')}.log"
    logger.add(log_file, level="DEBUG", rotation="10 MB", retention="7 days")


def derive_targets(rows: list[PriceRow], brands: list[str]) -> list[dict]:
    """
    Deriva la lista de targets únicos a partir de las filas de Boutique.
    Un target = un producto único (model + capacity_gb) con product_code de Santander,
    sin duplicar por offer_type.
    """
    seen: set[tuple] = set()
    targets: list[dict] = []

    for row in rows:
        # Filtrar por marca si se especificó
        if brands and row.brand.lower() not in [b.lower() for b in brands]:
            continue

        key = (row.model, row.capacity_gb)
        if key in seen:
            continue
        seen.add(key)

        targets.append({
            "model": row.model,
            "capacity_gb": row.capacity_gb,
            "product_code": row.product_code,
            "brand": row.brand,
            "device_type": row.device_type,
            "product_family": row.product_family,
        })

    logger.info(f"Targets derivados del catálogo Boutique: {len(targets)}")
    return targets


def load_targets_from_file(path: str, brands: list[str]) -> list[dict]:
    """Carga targets desde un JSON pre-generado (para re-usar sin scraping Boutique)."""
    with open(path, "r", encoding="utf-8") as f:
        targets = json.load(f)
    if brands:
        targets = [t for t in targets if t.get("brand", "").lower() in [b.lower() for b in brands]]
    logger.info(f"Targets cargados de {path}: {len(targets)}")
    return targets


def save_targets(targets: list[dict], prefix: str) -> None:
    """Guarda los targets en JSON para reutilización futura."""
    path = f"{prefix}_targets.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(targets, f, ensure_ascii=False, indent=2)
    logger.info(f"Targets guardados en: {path}")


async def run_boutique(brands: list[str], test_mode: bool) -> list[PriceRow]:
    logger.info("▶ Santander Boutique (API)")
    scraper = SantanderBoutiqueScraper(brands=brands, test_mode=test_mode)
    rows = await scraper.scrape()
    logger.success(f"✓ Santander Boutique: {len(rows)} filas")
    return rows


async def run_competitor(
    name: str,
    cls: type,
    targets: list[dict],
    test_mode: bool,
) -> list[PriceRow]:
    logger.info(f"▶ {cls.RETAILER} ({name})")
    scraper = cls(targets=targets)
    try:
        rows = await scraper.scrape()
    except Exception as e:
        logger.error(f"[{name}] Error inesperado: {e}")
        rows = []
    if test_mode and rows:
        rows = rows[:10]
    logger.success(f"✓ {cls.RETAILER}: {len(rows)} filas")
    return rows


async def main_async(args: argparse.Namespace) -> None:
    brands = [b.lower() for b in args.brands] if args.brands else []
    scrapers_to_run = args.scrapers or ["boutique"]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_prefix = args.output or DEFAULT_OUTPUT_PREFIX

    logger.info("=" * 60)
    logger.info("SISTEMA COMPARADOR DE PRECIOS — SANTANDER BOUTIQUE")
    logger.info("=" * 60)
    logger.info(f"Scrapers: {', '.join(scrapers_to_run)}")
    logger.info(f"Marcas:   {', '.join(brands) or 'todas'}")
    logger.info("=" * 60)

    all_rows: list[PriceRow] = []
    targets: list[dict] = []

    # ── 1. Obtener targets ──────────────────────────────────────────────
    if args.targets_file:
        # Cargar targets de fichero JSON (saltarse Boutique)
        targets = load_targets_from_file(args.targets_file, brands)
    elif "boutique" in scrapers_to_run:
        boutique_rows = await run_boutique(brands, test_mode=args.test)
        all_rows.extend(boutique_rows)
        targets = derive_targets(boutique_rows, brands)
        if args.save_targets:
            save_targets(targets, output_prefix)
    else:
        logger.warning(
            "Sin scraper 'boutique' ni --targets-file. "
            "Los competidores no tendrán targets contra los que comparar."
        )

    # ── 2. Ejecutar scrapers de competidores ────────────────────────────
    competitor_names = [s for s in scrapers_to_run if s in COMPETITOR_SCRAPERS]

    if competitor_names and not targets:
        logger.warning("No hay targets disponibles — omitiendo scrapers de competidores.")
        competitor_names = []

    for name in competitor_names:
        cls = COMPETITOR_SCRAPERS[name]
        rows = await run_competitor(name, cls, targets, args.test)
        all_rows.extend(rows)

    # ── 3. Exportar CSV combinado ───────────────────────────────────────
    if all_rows:
        csv_path = f"{output_prefix}_{timestamp}.csv"
        export_to_csv(all_rows, csv_path)

        logger.success(f"\n{'='*60}")
        logger.success(f"CSV generado: {csv_path}")
        logger.success(f"  • {len(all_rows)} filas de precio en total")

        # Resumen por fuente y offer_type
        from collections import Counter
        by_retailer: Counter = Counter(r.retailer for r in all_rows)
        by_offer: Counter = Counter(r.offer_type for r in all_rows)
        logger.info("  Filas por retailer:")
        for retailer, cnt in by_retailer.most_common():
            logger.info(f"    {retailer}: {cnt}")
        logger.info("  Filas por offer_type:")
        for ot, cnt in by_offer.most_common():
            logger.info(f"    {ot}: {cnt}")
        logger.success(f"{'='*60}")
    else:
        logger.error("No se obtuvieron datos. Revisa la conexión y los scrapers.")
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Comparador de precios Santander Boutique vs Competidores",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python main.py                                # Boutique -> CSV
  python main.py --brands apple                 # Solo Apple
  python main.py --scrapers boutique grover rentik   # Boutique + renting
  python main.py --scrapers boutique amazon mediamarkt apple_store samsung_store
  python main.py --scrapers boutique --test     # Prueba rapida
  python main.py --targets-file targets.json --scrapers grover  # Sin Boutique
  python main.py --output precios_marzo         # Prefijo de archivo

Scrapers disponibles:
  boutique (fuente principal), grover, rentik, amazon, mediamarkt, apple_store, samsung_store, movistar
        """,
    )
    parser.add_argument(
        "--scrapers", nargs="+",
        choices=ALL_SCRAPERS,
        help="Scrapers a ejecutar (por defecto: boutique)",
    )
    parser.add_argument(
        "--brands", nargs="+",
        choices=["apple", "Apple", "samsung", "Samsung"],
        help="Marcas a filtrar (por defecto: todas)",
    )
    parser.add_argument(
        "--output", type=str,
        help=f"Prefijo del archivo de salida (por defecto: {DEFAULT_OUTPUT_PREFIX})",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Modo prueba: pocos productos por scraper",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Logging detallado (DEBUG)",
    )
    parser.add_argument(
        "--targets-file", type=str, metavar="FILE",
        help="JSON con targets pre-generados (omite scraping de Boutique)",
    )
    parser.add_argument(
        "--save-targets", action="store_true",
        help="Guarda los targets derivados de Boutique en JSON para reutilización",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    asyncio.run(main_async(args))
