"""
Exportador CSV compatible con el esquema de master_prices.csv.
"""
from __future__ import annotations
import csv
from pathlib import Path

from loguru import logger

from models.price_row import PriceRow


def export_to_csv(rows: list[PriceRow], output_path: str | Path) -> Path:
    """
    Exporta filas de precio a CSV con el mismo esquema que master_prices.csv.
    Devuelve la ruta del archivo generado.
    """
    output_path = Path(output_path)
    columns = PriceRow.csv_columns()

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_dict())

    logger.success(f"CSV exportado: {output_path} ({len(rows)} filas)")
    return output_path
