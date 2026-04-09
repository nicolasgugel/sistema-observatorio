from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app_backend.config import DEFAULT_COMPETITORS, OUTPUT_DIR
from app_backend.published_runtime import run_full_runtime_sync, run_targeted_runtime_sync


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Runtime publicado hibrido con validacion por retailer.")
    parser.add_argument("--brand", default="all", choices=["all", "Samsung", "Apple"])
    parser.add_argument("--competitors", default=",".join(DEFAULT_COMPETITORS))
    parser.add_argument("--targets-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scope", default="full_catalog")
    parser.add_argument("--max-products", type=int, default=500)
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def _resolve_competitors(raw: str) -> list[str]:
    competitors = [item.strip() for item in str(raw or "").split(",") if item.strip()]
    return competitors or list(DEFAULT_COMPETITORS)


def main() -> None:
    args = parse_args()
    if args.output.is_absolute():
        output_prefix = args.output
    elif args.output.parent == Path("."):
        output_prefix = OUTPUT_DIR / args.output
    else:
        output_prefix = args.output

    if args.targets_file:
        targets = json.loads(args.targets_file.read_text(encoding="utf-8"))
        competitors = _resolve_competitors(args.competitors)
        if len(competitors) != 1:
            raise RuntimeError("El scraping dirigido requiere exactamente un competidor.")
        result = run_targeted_runtime_sync(
            brand=args.brand,
            competitor=competitors[0],
            targets=targets,
            output_prefix=output_prefix,
            headed=args.headed,
        )
    else:
        result = run_full_runtime_sync(
            brand_scope=args.brand,
            competitors=_resolve_competitors(args.competitors),
            output_prefix=output_prefix,
            max_products=args.max_products,
            scope=args.scope,
            headed=args.headed,
        )

    print(
        json.dumps(
            {
                "runtime_name": "legacy_hybrid_validated_runtime",
                "raw_generated_csv": result["raw_generated_csv"],
                "validation_report_path": result["validation_report_path"],
                "raw_record_count": len(result["raw_rows"]),
                "selected_key_count": len(result["selected_keys"]),
                "retailers_blocked": result["retailers_blocked"],
                "retailer_runtime_map": result["retailer_runtime_map"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if result["should_fail"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
