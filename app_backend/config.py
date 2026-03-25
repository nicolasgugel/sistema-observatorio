from __future__ import annotations

import errno
import os
import shlex
from pathlib import Path

from app_backend.env_loader import load_env_file


ROOT_DIR = Path(__file__).resolve().parents[1]
load_env_file(ROOT_DIR / ".env")


def _ensure_dir(path: Path) -> Path:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        if exc.errno not in {errno.EROFS, errno.EACCES, errno.EPERM}:
            raise
    return path


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
OBSERVATORIO_AGENT_SESSION_DB_PATH = Path(
    os.getenv("OBSERVATORIO_AGENT_SESSION_DB_PATH", DATA_DIR / "agent_sessions.sqlite3")
)
_ensure_dir(OBSERVATORIO_AGENT_SESSION_DB_PATH.parent)

TEMPLATE_PATH = ROOT_DIR / "assets" / "templates" / "price_comparison_v10_dual_brand.html"
SCRAPER_BUNDLE_DIR = ROOT_DIR / "santander_scraper_bundle_20260325" / "santander_scraper"
SCRAPER_BUNDLE_ENTRYPOINT = SCRAPER_BUNDLE_DIR / "main.py"
SCRAPER_BUNDLE_NAME = SCRAPER_BUNDLE_DIR.name
SCRAPER_RUNTIME_ENTRYPOINT = ROOT_DIR / "scripts" / "run_published_runtime.py"
SCRAPER_RUNTIME_NAME = "santander_20260325_bundle_runtime"
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
    "Orange": "orange",
    "El Corte Ingles": "el_corte_ingles",
}

SCRAPER_CLEAN_RAW_RETAILER_ALIASES = {
    "MediaMarkt": "Media Markt",
    "Samsung Store": "Samsung Oficial",
    "Apple Store": "Apple Oficial",
    "El Corte Inglés": "El Corte Ingles",
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
    "Orange",
    "El Corte Ingles",
]

SCRAPER_LEGACY_RETAILERS: list[str] = []

SCRAPER_CURRENT_DEDICATED_RETAILERS = [
    "Santander Boutique",
    "Amazon",
    "Media Markt",
    "Grover",
    "Movistar",
    "Rentik",
    "Samsung Oficial",
    "Apple Oficial",
    "Orange",
    "El Corte Ingles",
]

SCRAPER_RUNTIME_BY_RETAILER = {
    "Santander Boutique": "current_dedicated",
    "Amazon": "current_dedicated",
    "Media Markt": "current_dedicated",
    "Grover": "current_dedicated",
    "Movistar": "current_dedicated",
    "Rentik": "current_dedicated",
    "Samsung Oficial": "current_dedicated",
    "Apple Oficial": "current_dedicated",
    "Orange": "current_dedicated",
    "El Corte Ingles": "current_dedicated",
}

EDITOR_TOKEN = os.getenv("OBSERVATORIO_EDITOR_TOKEN", "").strip()
ALLOWED_ORIGINS = [
    item.strip()
    for item in os.getenv("OBSERVATORIO_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if item.strip()
]
ALLOWED_ORIGIN_REGEX = os.getenv("OBSERVATORIO_ALLOWED_ORIGIN_REGEX", r"https://.*\.vercel\.app")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
_SUPPORTED_OBSERVATORIO_AGENT_MODELS = {"gpt-5.4-mini", "gpt-5-mini", "gpt-5-nano"}


def _normalize_observatorio_agent_model(raw_value: str, *, default: str = "gpt-5-mini") -> str:
    candidate = (raw_value or "").strip().lower()
    if candidate in _SUPPORTED_OBSERVATORIO_AGENT_MODELS:
        return candidate
    if candidate.startswith("gpt-"):
        return candidate
    return default


LIVE_AGENT_MODEL = _normalize_observatorio_agent_model(
    os.getenv("OBSERVATORIO_LIVE_AGENT_MODEL", "gpt-5-mini"),
    default="gpt-5-mini",
)
OBSERVATORIO_AGENT_MODEL = _normalize_observatorio_agent_model(
    os.getenv("OBSERVATORIO_AGENT_MODEL", LIVE_AGENT_MODEL),
    default=LIVE_AGENT_MODEL,
)
LIVE_AGENT_CACHE_TTL_SECONDS = max(int(os.getenv("OBSERVATORIO_LIVE_AGENT_CACHE_TTL_SECONDS", "1800")), 60)
LIVE_AGENT_DEFAULT_SYNC_TIMEOUT_SECONDS = max(
    int(os.getenv("OBSERVATORIO_LIVE_AGENT_DEFAULT_SYNC_TIMEOUT_SECONDS", "20")),
    5,
)
LIVE_AGENT_MAX_PRODUCTS = max(int(os.getenv("OBSERVATORIO_LIVE_AGENT_MAX_PRODUCTS", "3")), 1)
LIVE_AGENT_SUPPORTED_RETAILERS = [
    "Santander Boutique",
    "Amazon",
    "Media Markt",
    "El Corte Ingles",
]
SCRAPLING_MCP_COMMAND = os.getenv("OBSERVATORIO_SCRAPLING_MCP_COMMAND", "scrapling").strip() or "scrapling"
SCRAPLING_MCP_ARGS = shlex.split(os.getenv("OBSERVATORIO_SCRAPLING_MCP_ARGS", "mcp").strip() or "mcp")
SCRAPLING_MCP_CLIENT_SESSION_TIMEOUT_SECONDS = max(
    float(os.getenv("OBSERVATORIO_SCRAPLING_MCP_CLIENT_SESSION_TIMEOUT_SECONDS", "45")),
    5.0,
)
SCRAPLING_MCP_ENABLED = os.getenv("OBSERVATORIO_SCRAPLING_MCP_ENABLED", "false").strip().lower() == "true"
