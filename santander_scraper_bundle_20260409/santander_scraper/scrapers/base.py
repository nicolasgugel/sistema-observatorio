"""
Clase base abstracta para todos los scrapers.
Proporciona retry logic, logging, y normalización de nombres.
"""
from __future__ import annotations
import asyncio
import re
import unicodedata
from abc import ABC, abstractmethod
from typing import Optional

from loguru import logger

from models.product import Product, PricePoint


class BaseScraper(ABC):
    """Scraper base con retry automático y helpers comunes."""

    SOURCE_NAME: str = "base"
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 2.0  # segundos entre reintentos

    def __init__(self, brands: Optional[list[str]] = None, categories: Optional[list[str]] = None):
        self.brands = [b.lower() for b in brands] if brands else ["apple", "samsung"]
        self.categories = [c.lower() for c in categories] if categories else []
        self.products: list[Product] = []

    @abstractmethod
    async def scrape(self) -> list[Product]:
        """Método principal de scraping. Retorna lista de Products."""
        ...

    async def scrape_with_retry(self) -> list[Product]:
        """Ejecuta scrape() con reintentos automáticos en caso de error."""
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.info(f"[{self.SOURCE_NAME}] Intento {attempt}/{self.MAX_RETRIES}...")
                result = await self.scrape()
                logger.success(f"[{self.SOURCE_NAME}] {len(result)} productos extraídos.")
                return result
            except Exception as e:
                logger.warning(f"[{self.SOURCE_NAME}] Error en intento {attempt}: {e}")
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(self.RETRY_DELAY * attempt)
                else:
                    logger.error(f"[{self.SOURCE_NAME}] Fallaron todos los intentos. Saltando.")
                    return []
        return []

    # ── Helpers de normalización ────────────────────────────────────────────

    @staticmethod
    def normalize_name(name: str) -> str:
        """Normaliza un nombre de producto para matching: lowercase, sin acentos, sin símbolos."""
        # Quitar acentos
        nfkd = unicodedata.normalize("NFKD", name)
        ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
        # Lowercase y limpiar
        clean = ascii_str.lower().strip()
        # Quitar caracteres especiales, dejar alfanumérico y guiones
        clean = re.sub(r"[^a-z0-9\s\-/]", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    @staticmethod
    def extract_storage(text: str) -> str:
        """Extrae capacidad de almacenamiento del nombre del producto."""
        match = re.search(r"(\d+)\s*(GB|TB)", text, re.IGNORECASE)
        if match:
            val, unit = match.groups()
            return f"{val}{unit.upper()}"
        return ""

    @staticmethod
    def extract_color(text: str) -> str:
        """Extrae color del nombre del producto."""
        colors = [
            "negro", "blanco", "plata", "plateado", "oro", "dorado",
            "azul", "rojo", "verde", "amarillo", "morado", "rosa", "gris",
            "black", "white", "silver", "gold", "blue", "red", "green",
            "yellow", "purple", "pink", "gray", "grey", "titanium",
            "natural", "starlight", "midnight", "desert", "teal",
        ]
        text_lower = text.lower()
        for color in colors:
            if color in text_lower:
                return color.capitalize()
        return ""

    @staticmethod
    def build_model_id(brand: str, name: str, storage: str = "") -> str:
        """
        Construye un model_id normalizado para fuzzy matching.
        Ej: "Apple iPhone 17 Pro 256GB" → "iphone-17-pro-256gb"
        """
        name_norm = BaseScraper.normalize_name(name)
        # Quitar la marca del inicio si está presente
        brand_norm = BaseScraper.normalize_name(brand)
        if name_norm.startswith(brand_norm):
            name_norm = name_norm[len(brand_norm):].strip()
        # Si storage no viene en el nombre, añadirlo
        if storage and storage.lower() not in name_norm:
            name_norm = f"{name_norm} {storage.lower()}"
        # Convertir espacios a guiones
        model_id = re.sub(r"\s+", "-", name_norm.strip())
        model_id = re.sub(r"-+", "-", model_id)
        return model_id

    @staticmethod
    def detect_category(name: str, brand: str) -> str:
        """Detecta la categoría del producto a partir de su nombre."""
        name_lower = name.lower()
        brand_lower = brand.lower()

        if "iphone" in name_lower:
            return "iPhone"
        if "ipad" in name_lower:
            return "iPad"
        if "macbook" in name_lower or "mac mini" in name_lower or "imac" in name_lower or "mac pro" in name_lower:
            return "Mac"
        if "airpods" in name_lower:
            return "AirPods"
        if "apple watch" in name_lower:
            return "AppleWatch"
        if "galaxy" in name_lower and any(s in name_lower for s in ["s2", "s3", "z fold", "z flip", "a5", "a7"]):
            return "Galaxy"
        if "galaxy tab" in name_lower or "tab s" in name_lower:
            return "Tablet"
        if brand_lower == "samsung" and ("tab" in name_lower or "tablet" in name_lower):
            return "Tablet"
        if brand_lower == "samsung":
            return "Galaxy"
        if any(w in name_lower for w in ["portátil", "portatil", "laptop", "notebook"]):
            return "Portátil"
        if "tablet" in name_lower:
            return "Tablet"
        if "tv" in name_lower or "televisor" in name_lower:
            return "TV"
        return "Otros"

    @staticmethod
    def clean_price(price_str: str) -> Optional[float]:
        """Convierte string de precio a float. Ej: '1.199,00 €' → 1199.0"""
        if not price_str:
            return None
        cleaned = re.sub(r"[^\d,.]", "", price_str)
        # Formato europeo: 1.199,00
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _should_include_brand(self, brand: str) -> bool:
        return brand.lower() in self.brands

    def _should_include_category(self, category: str) -> bool:
        if not self.categories:
            return True
        category_map = {
            "iphone": "iphone",
            "galaxy": "samsung",
            "ipad": "ipad",
            "tablet": "ipad",
            "mac": "mac",
            "portátil": "mac",
        }
        cat_lower = category.lower()
        for key, val in category_map.items():
            if key in cat_lower:
                return val in self.categories or cat_lower in self.categories
        return cat_lower in self.categories
