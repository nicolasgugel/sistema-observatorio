from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


@dataclass(slots=True)
class ProductSeed:
    brand: str
    model: str
    capacity_gb: int | None
    source_url: str
    device_type: str = "mobile"
    product_code: str | None = None

    @property
    def search_query(self) -> str:
        cap = f"{self.capacity_gb}GB" if self.capacity_gb else ""
        return " ".join([self.brand, self.model, cap]).strip()


@dataclass(slots=True)
class PriceRecord:
    country: str
    retailer: str
    retailer_slug: str
    product_family: str
    brand: str
    device_type: str
    model: str
    capacity_gb: int | None
    offer_type: str
    price_value: float
    price_text: str
    price_unit: str
    term_months: int | None
    in_stock: bool | None
    data_quality_tier: str
    price_capture_kind: str
    extracted_at: str
    source_url: str
    source_title: str | None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def now_iso() -> str:
        return datetime.now(tz=timezone.utc).isoformat()
