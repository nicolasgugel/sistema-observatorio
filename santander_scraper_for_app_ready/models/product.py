"""
Modelos de datos para el sistema comparador de precios.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class PricePoint:
    source: str            # "santander_boutique" | "amazon" | "mediamarkt" | etc.
    price_type: str        # "renting" | "purchase" | "installment"
    price: float           # precio en EUR (mensual si renting, total si compra)
    currency: str = "EUR"
    installments: int = 0  # nº de cuotas (0 = compra directa)
    monthly_price: Optional[float] = None  # precio mensual si es a plazos
    url: str = ""
    scraped_at: datetime = field(default_factory=datetime.now)
    availability: str = "unknown"  # "inStock" | "outOfStock" | "unknown"
    extra: dict = field(default_factory=dict)  # seguro, condiciones, etc.

    def to_dict(self) -> dict:
        return {
            "Fuente": self.source,
            "Tipo_Precio": self.price_type,
            "Precio_EUR": round(self.price, 2),
            "Moneda": self.currency,
            "Cuotas": self.installments if self.installments > 0 else "",
            "Precio_Mensual": round(self.monthly_price, 2) if self.monthly_price else "",
            "Disponibilidad": self.availability,
            "URL": self.url,
            "Fecha_Scraping": self.scraped_at.strftime("%Y-%m-%d %H:%M"),
        }


@dataclass
class Product:
    name: str              # nombre normalizado para display
    brand: str             # "Apple" | "Samsung" | "HP" | etc.
    category: str          # "iPhone" | "Galaxy" | "iPad" | "Mac" | "Portátil" | "Tablet"
    model_id: str          # clave normalizada para matching: "iphone-17-pro-256gb-black"
    raw_name: str          # nombre original del scraper
    source_code: str       # código interno del vendedor (SKU, ASIN, etc.)
    prices: list[PricePoint] = field(default_factory=list)
    storage: str = ""      # "128GB" | "256GB" | etc.
    color: str = ""        # color del dispositivo
    image_url: str = ""

    def add_price(self, price_point: PricePoint) -> None:
        self.prices.append(price_point)

    def get_prices_by_source(self, source: str) -> list[PricePoint]:
        return [p for p in self.prices if p.source == source]

    def get_best_price(self, price_type: str = "purchase") -> Optional[PricePoint]:
        candidates = [p for p in self.prices if p.price_type == price_type and p.price > 0]
        return min(candidates, key=lambda p: p.price) if candidates else None

    def to_rows(self) -> list[dict]:
        """Expande el producto en una fila por cada PricePoint."""
        base = {
            "Producto": self.name,
            "Marca": self.brand,
            "Categoría": self.category,
            "Almacenamiento": self.storage,
            "Color": self.color,
            "model_id": self.model_id,
        }
        if not self.prices:
            return [{**base, **PricePoint(source="N/A", price_type="N/A", price=0).to_dict()}]
        return [{**base, **p.to_dict()} for p in self.prices]


@dataclass
class ComparisonRow:
    """Fila de la hoja Comparativa Renting — un producto vs todas las fuentes renting."""
    product_name: str
    brand: str
    category: str
    storage: str
    model_id: str
    boutique_renting: Optional[float] = None
    boutique_cuotas: Optional[int] = None
    boutique_url: str = ""
    rentik_renting: Optional[float] = None
    rentik_url: str = ""
    grover_renting: Optional[float] = None
    grover_url: str = ""
    movistar_renting: Optional[float] = None
    movistar_url: str = ""
    boutique_purchase: Optional[float] = None
    amazon_purchase: Optional[float] = None
    mediamarkt_purchase: Optional[float] = None
    apple_official: Optional[float] = None
    samsung_official: Optional[float] = None

    def delta_vs_boutique_renting(self, competitor_price: Optional[float]) -> Optional[float]:
        """% de diferencia del competidor vs Boutique (positivo = Boutique más barato)."""
        if self.boutique_renting and competitor_price:
            return round((competitor_price - self.boutique_renting) / self.boutique_renting * 100, 1)
        return None

    def to_dict(self) -> dict:
        return {
            "Producto": self.product_name,
            "Marca": self.brand,
            "Categoría": self.category,
            "Almacenamiento": self.storage,
            "Boutique_Renting_€/mes": self.boutique_renting,
            "Boutique_Cuotas": self.boutique_cuotas,
            "Rentik_€/mes": self.rentik_renting,
            "Δ_Rentik_%": self.delta_vs_boutique_renting(self.rentik_renting),
            "Grover_€/mes": self.grover_renting,
            "Δ_Grover_%": self.delta_vs_boutique_renting(self.grover_renting),
            "Movistar_€/mes": self.movistar_renting,
            "Δ_Movistar_%": self.delta_vs_boutique_renting(self.movistar_renting),
            "Boutique_Compra_€": self.boutique_purchase,
            "Amazon_€": self.amazon_purchase,
            "Δ_Amazon_%": self._delta_purchase(self.amazon_purchase),
            "MediaMarkt_€": self.mediamarkt_purchase,
            "Δ_MediaMarkt_%": self._delta_purchase(self.mediamarkt_purchase),
            "Apple_Oficial_€": self.apple_official,
            "Samsung_Oficial_€": self.samsung_official,
            "Boutique_URL": self.boutique_url,
            "Rentik_URL": self.rentik_url,
            "Grover_URL": self.grover_url,
            "Movistar_URL": self.movistar_url,
        }

    def _delta_purchase(self, competitor: Optional[float]) -> Optional[float]:
        if self.boutique_purchase and competitor:
            return round((competitor - self.boutique_purchase) / self.boutique_purchase * 100, 1)
        return None
