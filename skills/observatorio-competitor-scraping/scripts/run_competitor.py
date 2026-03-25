from __future__ import annotations

import argparse
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app_backend.config import OUTPUT_DIR, ROOT_DIR, SCRAPER_CLEAN_RETAILER_LABEL_TO_ID, SCRAPER_RUNTIME_ENTRYPOINT


SANTANDER_NAME = "Santander Boutique"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the published scraping bundle for Boutique + selected competitors."
    )
    parser.add_argument("--competitor", required=True, help='Target competitor, e.g. "Media Markt"')
    parser.add_argument(
        "--brand",
        default="Samsung",
        choices=["Samsung", "Apple"],
        help="Base brand extracted from Santander Boutique.",
    )
    parser.add_argument("--max-products", type=int, default=8, help="Kept for compatibility; ignored by the bundle runtime.")
    parser.add_argument(
        "--scope",
        default="full_catalog",
        choices=["focused_iphone17_s25", "full_catalog"],
        help="Kept for compatibility; ignored by the bundle runtime.",
    )
    parser.add_argument("--headed", action="store_true", help="Kept for compatibility; ignored by the bundle runtime.")
    parser.add_argument(
        "--closed-base",
        default="",
        help='Closed competitors baseline, comma-separated (default: empty -> run only target competitor)',
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=ROOT_DIR,
        help="Repo root containing the published scraping bundle.",
    )
    return parser.parse_args()


def unique_competitors(base: str, target: str) -> list[str]:
    ordered: list[str] = []
    for part in [*base.split(","), target]:
        value = part.strip()
        if not value or value == SANTANDER_NAME:
            continue
        if value in ordered:
            continue
        ordered.append(value)
    return ordered


def resolve_scraper_ids(labels: list[str]) -> list[str]:
    unknown = [label for label in labels if label not in SCRAPER_CLEAN_RETAILER_LABEL_TO_ID]
    if unknown:
        raise RuntimeError(f"Competidores no soportados por el runtime publicado: {', '.join(unknown)}")
    return [SCRAPER_CLEAN_RETAILER_LABEL_TO_ID[label] for label in labels]


def main() -> int:
    args = parse_args()
    competitors = unique_competitors(args.closed_base, args.competitor)
    scraper_ids = resolve_scraper_ids(competitors)
    output_prefix = OUTPUT_DIR / (
        f"skill_run_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    )

    cmd = [
        sys.executable,
        str(SCRAPER_RUNTIME_ENTRYPOINT.relative_to(ROOT_DIR)),
        "--scrapers",
        "boutique",
        *scraper_ids,
        "--brands",
        args.brand.lower(),
        "--output",
        str(output_prefix),
    ]

    if args.headed:
        print("[run_competitor] headed=true se ignora en el runtime publicado.")
    if args.max_products != 8:
        print("[run_competitor] max-products se mantiene por compatibilidad y se ignora.")
    if args.scope != "full_catalog":
        print("[run_competitor] scope se mantiene por compatibilidad y se ignora.")

    print("[run_competitor] command:")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=str(args.workdir))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
