from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run observatorio pipeline for Santander + closed competitors + one target competitor."
    )
    parser.add_argument("--competitor", required=True, help='Target competitor, e.g. "Media Markt"')
    parser.add_argument(
        "--brand",
        default="Samsung",
        choices=["Samsung", "Apple"],
        help="Base brand extracted from Santander Boutique.",
    )
    parser.add_argument("--max-products", type=int, default=8)
    parser.add_argument(
        "--scope",
        default="focused_iphone17_s25",
        choices=["focused_iphone17_s25", "full_catalog"],
        help="Seed scope forwarded to run_observatorio.py.",
    )
    parser.add_argument("--headed", action="store_true", help="Run Playwright in headed mode")
    parser.add_argument(
        "--closed-base",
        default="",
        help='Closed competitors baseline, comma-separated (default: empty -> run only target competitor)',
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path.cwd(),
        help="Repo root containing run_observatorio.py",
    )
    return parser.parse_args()


def unique_competitors(base: str, target: str) -> str:
    ordered: list[str] = []
    for part in (base.split(",") + [target]):
        value = part.strip()
        if not value:
            continue
        if value in ordered:
            continue
        ordered.append(value)
    return ",".join(ordered)


def main() -> int:
    args = parse_args()
    competitors = unique_competitors(args.closed_base, args.competitor)
    cmd = [
        sys.executable,
        "run_observatorio.py",
        "--brand",
        args.brand,
        "--max-products",
        str(args.max_products),
        "--competitors",
        competitors,
        "--scope",
        args.scope,
    ]
    if args.headed:
        cmd.append("--headed")

    print("[run_competitor] command:")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=str(args.workdir))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
