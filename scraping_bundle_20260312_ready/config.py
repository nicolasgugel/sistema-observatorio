"""
Configuración centralizada del sistema de scraping.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

# ── Marcas y categorías disponibles ─────────────────────────────────────────

ALL_BRANDS = ["apple", "samsung"]
ALL_CATEGORIES = ["iphone", "ipad", "mac", "galaxy", "tablet"]

# ── Scrapers disponibles ─────────────────────────────────────────────────────

ALL_SCRAPERS = [
    "boutique",
    "grover",
    "rentik",
    "amazon",
    "mediamarkt",
    "apple_store",
    "samsung_store",
    "movistar",
    "orange",
    "el_corte_ingles",
]

SCRAPER_DISPLAY_NAMES = {
    "boutique": "Santander Boutique",
    "grover": "Grover",
    "rentik": "Rentik",
    "amazon": "Amazon.es",
    "mediamarkt": "MediaMarkt",
    "apple_store": "Apple Store",
    "samsung_store": "Samsung Store",
    "movistar": "Movistar",
    "orange": "Orange",
    "el_corte_ingles": "El Corte Ingles",
}

# ── Delays por scraper (segundos) ────────────────────────────────────────────

SCRAPER_DELAYS = {
    "boutique": 0.5,
    "grover": 1.5,
    "rentik": 2.0,
    "amazon": 3.0,
    "mediamarkt": 2.5,
    "apple_store": 3.0,
    "samsung_store": 2.0,
    "movistar": 3.0,
    "orange": 1.5,
    "el_corte_ingles": 1.2,
}

# ── Configuración Scrapling ──────────────────────────────────────────────────

SCRAPLING_CONFIG = {
    "auto_match": False,
    "stealthy_headers": True,
}

# ── Output ───────────────────────────────────────────────────────────────────

DEFAULT_OUTPUT_DIR = "."
DEFAULT_OUTPUT_PREFIX = "precios_santander"
