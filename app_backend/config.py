from __future__ import annotations

import errno
import os
from pathlib import Path


def _ensure_dir(path: Path) -> Path:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        if exc.errno not in {errno.EROFS, errno.EACCES, errno.EPERM}:
            raise
    return path


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "output"
_ensure_dir(OUTPUT_DIR)

DATA_DIR = Path(os.getenv("OBSERVATORIO_DATA_DIR", ROOT_DIR / "data"))
_ensure_dir(DATA_DIR)
CURRENT_DATA_DIR = DATA_DIR / "current"
_ensure_dir(CURRENT_DATA_DIR)
HISTORY_DATA_DIR = DATA_DIR / "history"
_ensure_dir(HISTORY_DATA_DIR)
LOGS_DATA_DIR = DATA_DIR / "logs"
_ensure_dir(LOGS_DATA_DIR)
STATE_DB_PATH = DATA_DIR / "observatorio.sqlite3"

TEMPLATE_PATH = ROOT_DIR / "assets" / "templates" / "price_comparison_v10_dual_brand.html"
SCRAPER_RUNTIME_DIR = ROOT_DIR / "santander_scraper_for_app_ready"
SCRAPER_RUNTIME_ENTRYPOINT = SCRAPER_RUNTIME_DIR / "main.py"
SCRAPER_RUNTIME_NAME = SCRAPER_RUNTIME_DIR.name
SCRAPER_CLEAN_INITIAL_SNAPSHOT_PATH = ROOT_DIR / "master_prices_v3_20260309_0917.csv"
CURRENT_JSON_PATH = CURRENT_DATA_DIR / "latest_prices.json"
CURRENT_CSV_PATH = CURRENT_DATA_DIR / "latest_prices.csv"
CURRENT_HTML_PATH = CURRENT_DATA_DIR / "price_comparison_live.html"
CURRENT_UNIFIED_CSV_PATH = CURRENT_DATA_DIR / "unified_last_scrapes_with_book.csv"
CURRENT_TABLE_PATH = CURRENT_DATA_DIR / "master_prices.csv"
PUBLISH_MANIFEST_PATH = CURRENT_DATA_DIR / "publish_manifest.json"

LATEST_JSON_PATH = OUTPUT_DIR / "latest_prices.json"
LATEST_CSV_PATH = OUTPUT_DIR / "latest_prices.csv"
LIVE_HTML_PATH = OUTPUT_DIR / "price_comparison_live.html"
UNIFIED_CSV_PATH = OUTPUT_DIR / "unified_last_scrapes_with_book.csv"

TABLE_COPY_PATH = ROOT_DIR / "master_prices.csv"
TABLE_OUTPUT_MASTER_PATH = OUTPUT_DIR / "master_prices.csv"
TABLE_LEGACY_LATEST_PATH = LATEST_CSV_PATH
TABLE_FALLBACK_PATH = CURRENT_TABLE_PATH
TABLE_SOURCE_PATHS = [
    CURRENT_TABLE_PATH,
    TABLE_COPY_PATH,
    TABLE_OUTPUT_MASTER_PATH,
    TABLE_LEGACY_LATEST_PATH,
    TABLE_FALLBACK_PATH,
]

SCRAPER_CLEAN_RETAILER_LABEL_TO_ID = {
    "Santander Boutique": "boutique",
    "Amazon": "amazon",
    "Grover": "grover",
    "Media Markt": "mediamarkt",
    "Movistar": "movistar",
    "Rentik": "rentik",
    "Samsung Oficial": "samsung_store",
    "Apple Oficial": "apple_store",
}

SCRAPER_CLEAN_RAW_RETAILER_ALIASES = {
    "MediaMarkt": "Media Markt",
    "Samsung Store": "Samsung Oficial",
    "Apple Store": "Apple Oficial",
}

SCRAPER_CLEAN_RAW_SLUG_ALIASES = {
    "mediamarkt": "media_markt",
    "samsung_store": "samsung_oficial",
    "apple_store": "apple_oficial",
}

DEFAULT_COMPETITORS = [
    "Amazon",
    "Grover",
    "Media Markt",
    "Movistar",
    "Rentik",
    "Samsung Oficial",
    "Apple Oficial",
]

EDITOR_TOKEN = os.getenv("OBSERVATORIO_EDITOR_TOKEN", "").strip()
ALLOWED_ORIGINS = [
    item.strip()
    for item in os.getenv("OBSERVATORIO_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if item.strip()
]
ALLOWED_ORIGIN_REGEX = os.getenv("OBSERVATORIO_ALLOWED_ORIGIN_REGEX", r"https://.*\.vercel\.app")
