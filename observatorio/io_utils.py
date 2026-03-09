from __future__ import annotations

import csv
import json
from pathlib import Path

from observatorio.models import PriceRecord


def write_records_json(records: list[PriceRecord], path: Path) -> None:
    payload = {"records": [record.to_dict() for record in records]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_records_csv(records: list[PriceRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = list(records[0].to_dict().keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_dict())

