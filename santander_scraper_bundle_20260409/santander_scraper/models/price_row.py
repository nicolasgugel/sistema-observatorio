"""
Modelo de fila plana de precio, compatible con master_prices.csv.
Cada fila representa un (producto, variante_almacenamiento, offer_type).
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class PriceRow:
    # Identificación del retailer
    country: str = "ES"
    retailer: str = ""
    retailer_slug: str = ""

    # Identificación del producto
    product_family: str = ""
    brand: str = ""
    device_type: str = ""       # mobile | tablet | laptop | desktop | other
    model: str = ""             # "Apple iPhone 17 Pro" (sin almacenamiento/color)
    capacity_gb: Optional[int] = None  # 256, 512, 1024 (1TB), None si no aplica
    product_code: str = ""      # codigo de referencia de Santander (ej. "SM-40991")

    # Precio
    offer_type: str = ""        # renting_no_insurance | renting_with_insurance | financing_max_term | cash
    price_value: float = 0.0
    price_text: str = ""        # "25.99 EUR"
    price_unit: str = ""        # "EUR/month" | "EUR"
    term_months: Optional[int] = None  # 36 para renting, 30/24/18... para financiación, None para cash

    # Disponibilidad y calidad
    in_stock: bool = True
    data_quality_tier: str = ""

    # Metadatos
    extracted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_url: str = ""
    source_title: str = ""
    source_snapshot: str = ""
    source_snapshots: str = ""

    @property
    def total_cost(self) -> float:
        """Coste total = cuota mensual × plazo. Para cash, es el precio directo."""
        if self.term_months:
            return round(self.price_value * self.term_months, 2)
        return self.price_value

    def to_dict(self) -> dict:
        d = asdict(self)
        # Formato numérico compatible con CSV
        d["capacity_gb"] = str(self.capacity_gb) if self.capacity_gb is not None else ""
        d["product_code"] = str(self.product_code or "")
        d["term_months"] = str(self.term_months) if self.term_months is not None else ""
        d["price_value"] = str(self.price_value)
        d["total_cost"] = str(self.total_cost)
        d["in_stock"] = str(self.in_stock)
        return d

    @classmethod
    def csv_columns(cls) -> list[str]:
        return [
            "country", "retailer", "retailer_slug",
            "product_family", "brand", "device_type", "model", "capacity_gb", "product_code",
            "offer_type", "price_value", "total_cost", "price_text", "price_unit", "term_months",
            "in_stock", "data_quality_tier", "extracted_at",
            "source_url", "source_title", "source_snapshot", "source_snapshots",
        ]
