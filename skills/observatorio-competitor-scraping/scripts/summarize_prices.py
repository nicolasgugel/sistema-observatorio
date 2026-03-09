from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize observatorio output coverage and modalities.")
    parser.add_argument("--json", dest="json_path", type=Path, default=Path("output/latest_prices.json"))
    return parser.parse_args()


def load_records(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("records", [])


def model_capacity_set(records: list[dict], retailer: str) -> set[tuple[str, str, int | None]]:
    return {
        (str(r.get("device_type") or "mobile"), str(r.get("model")), r.get("capacity_gb"))
        for r in records
        if r.get("retailer") == retailer
    }


def coverage_by_device(models: set[tuple[str, str, int | None]]) -> dict[str, int]:
    return dict(Counter(device for device, _, _ in models))


def main() -> int:
    args = parse_args()
    if not args.json_path.exists():
        print(f"[ERROR] file not found: {args.json_path}")
        return 1

    records = load_records(args.json_path)
    if not records:
        print("[WARN] no records found")
        return 0

    retailers = sorted({r.get("retailer") for r in records})
    print(f"Records total: {len(records)}")
    print("By retailer:", dict(Counter(r.get("retailer") for r in records)))
    print("By tier:", dict(Counter(r.get("data_quality_tier") for r in records)))

    base_retailer = "Santander Boutique"
    base_models = model_capacity_set(records, base_retailer)
    print(f"\nBase retailer: {base_retailer}")
    print(f"Base coverage: {len(base_models)}")
    print("base coverage by device:", coverage_by_device(base_models))

    for retailer in retailers:
        subset = [r for r in records if r.get("retailer") == retailer]
        models = model_capacity_set(records, retailer)
        offer_counts = Counter(r.get("offer_type") for r in subset)
        print(f"\n[{retailer}]")
        print("records:", len(subset))
        print("coverage models:", len(models))
        print("coverage by device:", coverage_by_device(models))
        print("offers:", dict(offer_counts))
        if retailer != base_retailer and base_models:
            missing = sorted(base_models - models)
            print("missing vs base:", len(missing))
            if missing:
                print("missing list:", missing)

        if retailer == "Media Markt":
            terms = defaultdict(set)
            for row in subset:
                if row.get("offer_type") == "financing_max_term":
                    terms[(row.get("device_type") or "mobile", row.get("model"), row.get("capacity_gb"))].add(
                        row.get("term_months")
                    )
            print("financing term coverage:")
            for key in sorted(terms):
                values = sorted(v for v in terms[key] if v is not None)
                print(f"- {key}: {values}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
