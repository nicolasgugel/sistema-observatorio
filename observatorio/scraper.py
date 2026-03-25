from __future__ import annotations

import asyncio
import json
import re
from typing import Iterable
from urllib.parse import quote_plus, urlparse

from playwright.async_api import APIRequestContext, Browser, Page, async_playwright

from observatorio.config import (
    APPLE_LAPTOP_QUERIES,
    APPLE_PHONE_QUERIES,
    APPLE_TABLET_QUERIES,
    OFFER_TYPES,
    RETAILER_SLUGS,
    SANTANDER_API_BASE,
    SANTANDER_LAPTOP_QUERIES,
    SANTANDER_API_PARAMS,
    SANTANDER_CATALOG_URLS,
    SANTANDER_PHONE_QUERIES,
    SANTANDER_TABLET_QUERIES,
    SANTANDER_SEARCH_PAGE_SIZE,
    SEARCH_URL_TEMPLATES,
    TARGET_COMPETITORS,
    TEXT_TIMEOUT_MS,
)
from observatorio.models import PriceRecord, ProductSeed
from observatorio.text_utils import (
    detect_capacity_gb,
    detect_stock_state,
    find_first_price,
    find_price_after_keywords,
    normalize_text,
    parse_euro_to_float,
    strip_html_tags,
)


SAMSUNG_MODEL_RE = re.compile(r"(Galaxy[\w\s+\-]{1,40})", flags=re.IGNORECASE)
APPLE_IPHONE_RE = re.compile(
    r"(iPhone\s*(?:SE(?:\s*\(\d{4}\))?|\d{1,2}[a-z]?)(?:\s*(?:Pro\s*Max|Pro|Plus|Mini|Air))?)",
    flags=re.IGNORECASE,
)
APPLE_IPAD_RE = re.compile(r"(iPad\s*(?:Pro|Air|Mini)?(?:\s*\d{1,2}(?:[.,]\d)?)?)", flags=re.IGNORECASE)
APPLE_MACBOOK_RE = re.compile(r"(MacBook\s*(?:Air|Pro)?(?:\s*\d{2})?)", flags=re.IGNORECASE)
APPLE_IMAC_RE = re.compile(r"(iMac\s*\d{2}(?:[.,]\d)?)", flags=re.IGNORECASE)
APPLE_MAC_MINI_RE = re.compile(r"(Mac\s*mini(?:\s*M\d(?:\s*Pro|\s*Max|\s*Ultra)?)?)", flags=re.IGNORECASE)
APPLE_MAC_STUDIO_RE = re.compile(r"(Mac\s*Studio(?:\s*M\d(?:\s*Pro|\s*Max|\s*Ultra)?)?)", flags=re.IGNORECASE)
APPLE_CHIP_RE = re.compile(r"\b(M\d)(?:\s*(Pro|Max|Ultra))?\b", flags=re.IGNORECASE)
SIN_SEGURO_RE = re.compile(r"sin seguro[^\d]{0,40}(\d{1,3}(?:[.,]\d{1,2})?)\s*(?:\u20ac|eur)", flags=re.IGNORECASE)
EURO_VALUE_RE = re.compile(r"(\d{1,5}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s*(?:\u20ac|eur)", flags=re.IGNORECASE)
MONTHLY_VALUE_RE = re.compile(r"(\d{1,5}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s*(?:\u20ac|eur)\s*/?\s*mes", flags=re.IGNORECASE)
TERM_RE = re.compile(r"(\d{1,2})\s*mes(?:es)?", flags=re.IGNORECASE)
AMAZON_ASIN_RE = re.compile(r"/dp/([A-Z0-9]{10})")
AMAZON_ASIN_ANY_RE = re.compile(r"(?:/dp/|/gp/product/)([A-Z0-9]{10})", flags=re.IGNORECASE)
MEDIAMARKT_FIN_RE = re.compile(
    r"en\s*(\d{1,2})\s*cuotas[^\d]{0,40}(\d{1,5}(?:[.,]\d{1,2})?)\s*(?:\u20ac|eur)\s*(?:mensual|mes)",
    flags=re.IGNORECASE,
)
MEDIAMARKT_SIM_BUTTON_RE = re.compile(r"simula tu financi", flags=re.IGNORECASE)
GROVER_CASH_RE = re.compile(
    r"(?:compr(?:a|alo|arlo)|quedatelo|al contado|precio de compra)[^\d]{0,120}"
    r"(\d{1,5}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s*(?:\u20ac|eur)",
    flags=re.IGNORECASE,
)
GROVER_FIN_RE = re.compile(
    r"(?:financi(?:a|acion)|cuotas?)[^\d]{0,80}(\d{1,2})\s*(?:cuotas?|mes(?:es)?)"
    r"[^\d]{0,40}(\d{1,5}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s*(?:\u20ac|eur)",
    flags=re.IGNORECASE,
)
MOVISTAR_MONTHLY_RE = re.compile(
    r"(\d{1,5}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s*(?:\u20ac|eur)\s*/\s*mes",
    flags=re.IGNORECASE,
)
MOVISTAR_TERM_X_RE = re.compile(r"x\s*(\d{1,2})\s*mes(?:es)?", flags=re.IGNORECASE)
FNAC_FIN_A_RE = re.compile(
    r"(?:financi(?:a|acion)|cuotas?|cetelem)[^\d]{0,80}(\d{1,2})\s*(?:mes(?:es)?|cuotas?)"
    r"[^\d]{0,60}(\d{1,5}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s*(?:\u20ac|eur)\s*/?\s*mes",
    flags=re.IGNORECASE,
)
FNAC_FIN_B_RE = re.compile(
    r"(\d{1,5}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s*(?:\u20ac|eur)\s*/?\s*mes"
    r"[^\d]{0,80}(?:x|durante|en)\s*(\d{1,2})\s*(?:mes(?:es)?|cuotas?)",
    flags=re.IGNORECASE,
)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

ACCESSORY_HINTS = (
    "watch",
    "buds",
    "airpods",
    "pencil",
    "keyboard",
    "teclado",
    "folio",
    "airtag",
    "homepod",
    "funda",
    "carcasa",
    "protector",
    "cargador",
    "auriculares",
    "bateria",
    "battery",
    "replacement",
    "reemplazo",
    "compatible",
    "case",
    "cover",
    "estuche",
    "magsafe",
    "tech21",
    "evopro",
    "evolite",
    "screen protector",
    "tempered",
    "lapiz",
    "stylus",
    "pluma",
    "s pen",
)

MOBILE_HINTS = (
    "/moviles/",
    "/movil/",
    "/mobile/",
    "/smartphone/",
    "/smartphones/",
    "movil",
    "moviles",
    "smartphone",
    "smartphones",
)

LAPTOP_HINTS = (
    "/portatil",
    "/portatiles",
    "/laptop",
    "/laptops",
    "/notebook",
    "/ordenadores-portatiles",
    "portatil",
    "portatiles",
    "laptop",
    "notebook",
    "galaxy book",
    "macbook",
    "imac",
    "mac mini",
    "mac studio",
)

APPLE_TABLET_HINTS = (
    "ipad",
    "tablet",
)

APPLE_MOBILE_HINTS = (
    "iphone",
)

SEED_SCOPE_FOCUSED_IPHONE17_S25 = "focused_iphone17_s25"
SEED_SCOPE_FULL_CATALOG = "full_catalog"


def _is_samsung_seed(seed: ProductSeed) -> bool:
    return normalize_text(seed.brand) == "samsung"


def _is_apple_seed(seed: ProductSeed) -> bool:
    return normalize_text(seed.brand) == "apple"


def _extract_samsung_model(text: str) -> str:
    cleaned = strip_html_tags(text)
    match = SAMSUNG_MODEL_RE.search(cleaned)
    if match:
        model = re.sub(r"\s+", " ", match.group(1)).strip()
        model = re.sub(r"\b\d{2,4}\s*GB\b", "", model, flags=re.IGNORECASE).strip()
        model = re.sub(r"[\s\-_/]+$", "", model).strip()
        return f"Samsung {model}".strip()
    return "Samsung Galaxy"


def _canonicalize_apple_model(model: str) -> str:
    words = re.split(r"\s+", model.strip())
    mapped: list[str] = []
    for word in words:
        low = word.lower()
        if low == "iphone":
            mapped.append("iPhone")
        elif low == "ipad":
            mapped.append("iPad")
        elif low == "macbook":
            mapped.append("MacBook")
        elif low == "pro":
            mapped.append("Pro")
        elif low == "max":
            mapped.append("Max")
        elif low == "mini":
            mapped.append("Mini")
        elif low == "air":
            mapped.append("Air")
        elif low == "se":
            mapped.append("SE")
        else:
            mapped.append(word)
    return " ".join(mapped)


def _extract_apple_chip(text: str) -> str | None:
    match = APPLE_CHIP_RE.search(text or "")
    if not match:
        return None
    base = match.group(1).upper()
    suffix_raw = (match.group(2) or "").strip().lower()
    if not suffix_raw:
        return base
    if suffix_raw == "pro":
        return f"{base} Pro"
    if suffix_raw == "max":
        return f"{base} Max"
    if suffix_raw == "ultra":
        return f"{base} Ultra"
    return base


def _extract_apple_connectivity(text: str) -> str | None:
    value = normalize_text(text or "")
    has_wifi = bool(re.search(r"\bwi[\s\-]?fi\b", value))
    has_cell = any(token in value for token in ("cell", "cellular", "lte", "5g", "4g"))
    if has_wifi and has_cell:
        return "WiFi+Cell"
    if has_wifi:
        return "WiFi"
    if has_cell:
        return "Cell"
    return None


def _seed_connectivity_conflicts(seed: ProductSeed, text: str) -> bool:
    if _is_apple_seed(seed):
        return False
    if _seed_device_type(seed) != "mobile":
        return False

    seed_n = normalize_text(seed.model)
    text_n = normalize_text(text)
    seed_has_5g = bool(re.search(r"\b5g\b", seed_n))
    seed_has_lte = bool(re.search(r"\blte\b", seed_n))
    text_has_5g = bool(re.search(r"\b5g\b", text_n))
    text_has_lte = bool(re.search(r"\blte\b", text_n))

    if seed_has_5g and text_has_lte and not text_has_5g:
        return True
    if seed_has_lte and text_has_5g and not text_has_lte:
        return True
    return False


def _extract_apple_model(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", strip_html_tags(text)).strip()
    cleaned = cleaned.replace('"', " ")
    cleaned_no_capacity = re.sub(r"\b\d{2,4}\s*(?:gb|tb)\b", "", cleaned, flags=re.IGNORECASE)
    normalized = normalize_text(cleaned_no_capacity)

    if "macbook" in normalized:
        family = "Air" if re.search(r"\bair\b", normalized) else ("Pro" if re.search(r"\bpro\b", normalized) else "")
        size_m = re.search(r"\b(13|14|15|16)\b", normalized)
        chip = _extract_apple_chip(cleaned_no_capacity)
        parts = ["Apple", "MacBook"]
        if family:
            parts.append(family)
        if size_m:
            parts.append(size_m.group(1))
        if chip:
            parts.append(chip)
        return " ".join(parts).strip()

    if "imac" in normalized:
        size_m = re.search(r"\b(24|27)\b", normalized)
        chip = _extract_apple_chip(cleaned_no_capacity)
        parts = ["Apple", "iMac"]
        if size_m:
            parts.append(size_m.group(1))
        if chip:
            parts.append(chip)
        return " ".join(parts).strip()

    if "mac studio" in normalized:
        chip = _extract_apple_chip(cleaned_no_capacity)
        parts = ["Apple", "Mac Studio"]
        if chip:
            parts.append(chip)
        return " ".join(parts).strip()

    if "mac mini" in normalized:
        chip = _extract_apple_chip(cleaned_no_capacity)
        parts = ["Apple", "Mac Mini"]
        if chip:
            parts.append(chip)
        return " ".join(parts).strip()

    if "ipad" in normalized:
        family = None
        if re.search(r"\bpro\b", normalized):
            family = "Pro"
        elif re.search(r"\bair\b", normalized):
            family = "Air"
        elif re.search(r"\bmini\b", normalized):
            family = "Mini"
        generation_m = re.search(r"\b(\d{1,2}(?:st|nd|rd|th))\b", normalized)
        chip = _extract_apple_chip(cleaned_no_capacity)
        size_m = re.search(r"\b(11|13)\b", normalized)
        connectivity = _extract_apple_connectivity(cleaned_no_capacity)

        parts = ["Apple", "iPad"]
        if family:
            parts.append(family)
        elif generation_m:
            parts.append(generation_m.group(1))
        if chip:
            parts.append(chip)
        if size_m:
            parts.append(size_m.group(1))
        if connectivity:
            parts.append(connectivity)
        return " ".join(parts).strip()

    for regex in (APPLE_IPHONE_RE, APPLE_IPAD_RE, APPLE_MACBOOK_RE, APPLE_IMAC_RE, APPLE_MAC_MINI_RE, APPLE_MAC_STUDIO_RE):
        match = regex.search(cleaned_no_capacity)
        if not match:
            continue
        model = re.sub(r"\s+", " ", match.group(1)).strip()
        model = re.sub(r"[\s\-_/]+$", "", model).strip()
        return f"Apple {_canonicalize_apple_model(model)}".strip()
    generic_iphone = re.search(r"(iPhone(?:\s+[A-Za-z0-9]+){0,3})", cleaned_no_capacity, flags=re.IGNORECASE)
    if generic_iphone:
        model = re.sub(r"\b\d{2,4}\s*GB\b", "", generic_iphone.group(1), flags=re.IGNORECASE)
        model = re.sub(r"\s+", " ", model).strip()
        model = re.sub(r"[\s\-_/]+$", "", model).strip()
        return f"Apple {_canonicalize_apple_model(model)}".strip()
    return "Apple"


def _normalize_apple_model_alias(model: str) -> str:
    model_n = normalize_text(model)
    if re.search(r"\biphone\s+(?:17\s+)?air\b", model_n):
        return "Apple iPhone Air"
    return model


def _extract_model_for_brand(text: str, brand: str) -> str:
    if normalize_text(brand) == "apple":
        return _normalize_apple_model_alias(_extract_apple_model(text))
    return _extract_samsung_model(text)


def _brand_presence_in_text(seed: ProductSeed, text: str) -> bool:
    value = normalize_text(text)
    if _is_apple_seed(seed):
        return any(token in value for token in ("apple", "iphone", "ipad", "macbook", "imac", "mac mini", "mac studio"))
    return "samsung" in value or "galaxy" in value


def _has_tablet_hint(text: str) -> bool:
    value = normalize_text(text)
    if any(token in value for token in APPLE_TABLET_HINTS):
        return True
    return bool(re.search(r"\btab(?:let|lets)?\b", value)) or "/tablet" in value or "/tablets" in value


def _has_laptop_hint(text: str) -> bool:
    value = normalize_text(text)
    if "macbook" in value:
        return True
    if "galaxy book" in value:
        return True
    if ("samsung" in value or "galaxy" in value) and re.search(r"\bbook\s*\d?\b", value):
        return True
    if any(token in value for token in LAPTOP_HINTS):
        return True
    return False


def _seed_device_type(seed: ProductSeed) -> str:
    value = normalize_text(seed.device_type)
    if value == "tablet":
        return "tablet"
    if value == "laptop":
        return "laptop"
    return "mobile"


def _seed_matches_focused_iphone17_s25_scope(seed: ProductSeed) -> bool:
    if _seed_device_type(seed) != "mobile":
        return False

    model_n = normalize_text(seed.model)
    if _is_apple_seed(seed):
        return bool(re.search(r"\biphone\s*17\b", model_n) or re.search(r"\biphone\s+air\b", model_n))
    if _is_samsung_seed(seed):
        return bool(re.search(r"\bs\s*25\b", model_n) or re.search(r"\bs25\b", model_n))
    return False


def _filter_seeds_by_scope(seeds: list[ProductSeed], seed_scope: str) -> list[ProductSeed]:
    scope = normalize_text(seed_scope)
    if scope == normalize_text(SEED_SCOPE_FOCUSED_IPHONE17_S25):
        return [seed for seed in seeds if _seed_matches_focused_iphone17_s25_scope(seed)]
    return seeds


def _classify_brand_device_candidate(code: str, name: str, brand: str) -> str | None:
    text = normalize_text(name)
    brand_n = normalize_text(brand)
    if any(token in text for token in ACCESSORY_HINTS):
        return None

    if brand_n == "apple":
        if not any(token in text for token in ("apple", "iphone", "ipad", "macbook", "imac", "mac mini", "mac studio")):
            return None
        if any(token in text for token in ("macbook", "imac", "mac mini", "mac studio")) or _has_laptop_hint(text):
            return "laptop"
        if "ipad" in text or _has_tablet_hint(text):
            return "tablet"
        if "iphone" in text or any(token in text for token in APPLE_MOBILE_HINTS):
            return "mobile"
        return None

    if "galaxy" not in text and "samsung" not in text:
        return None
    if _has_laptop_hint(text):
        code_up = str(code or "").upper()
        if code_up.startswith("NP-") or code_up.startswith("NT-") or code_up.startswith("BOOK"):
            return "laptop"
        # Be permissive for Santander product coding of Galaxy Book variants.
        if code_up:
            return "laptop"
        return None
    if not str(code or "").upper().startswith("SM-"):
        return None
    if _has_tablet_hint(text):
        return "tablet"
    return "mobile"


def _candidate_device_type(text: str, href: str = "") -> str | None:
    mix = normalize_text(f"{text} {href}")
    if any(token in mix for token in ACCESSORY_HINTS):
        return None
    if _has_laptop_hint(mix):
        return "laptop"
    if _has_tablet_hint(mix) or "ipad" in mix:
        return "tablet"
    if any(token in mix for token in MOBILE_HINTS) or any(token in mix for token in APPLE_MOBILE_HINTS):
        return "mobile"
    if any(token in mix for token in ("samsung", "galaxy", "apple", "iphone", "ipad", "macbook")):
        return "mobile"
    return None


def _seed_device_matches_candidate(seed: ProductSeed, text: str, href: str) -> bool:
    seed_type = _seed_device_type(seed)
    candidate_type = _candidate_device_type(text=text, href=href)
    if candidate_type and candidate_type != seed_type:
        return False
    mix = normalize_text(f"{text} {href}")
    if seed_type == "laptop":
        seed_norm = normalize_text(seed.model)
        mix_compact = re.sub(r"[^a-z0-9]", "", mix)
        seed_code_raw = str(seed.product_code or "").strip()
        if seed_code_raw:
            seed_code = re.sub(r"[^a-z0-9]", "", normalize_text(seed_code_raw))
            code_root_raw = re.split(r"[-_/]", seed_code_raw)[0]
            code_root = re.sub(r"[^a-z0-9]", "", normalize_text(code_root_raw))
            if seed_code and seed_code in mix_compact:
                return _has_laptop_hint(mix)
            if code_root and len(code_root) >= 6 and code_root in mix_compact:
                return _has_laptop_hint(mix)
        if _is_samsung_seed(seed):
            book_match = re.search(r"\bbook\s*(\d{1,2})\b", seed_norm)
            if book_match:
                book_gen = book_match.group(1)
                if f"book{book_gen}" not in mix_compact:
                    return False
                cand_gens = set(re.findall(r"\bbook\s*(\d{1,2})\b", mix))
                if cand_gens and book_gen not in cand_gens:
                    return False
        if _is_apple_seed(seed) and "macbook" in seed_norm and "macbook" not in mix:
            return False
        seed_tokens = set(_alnum_tokens(seed_norm))
        cand_tokens = set(_alnum_tokens(mix))
        if _is_samsung_seed(seed):
            for marker in ("pro", "ultra", "360"):
                if marker in seed_tokens and marker not in cand_tokens:
                    return False
        if _is_apple_seed(seed):
            for marker in ("pro", "air", "mini", "max", "studio"):
                if marker in seed_tokens and marker not in cand_tokens:
                    return False
            if "macbook" in seed_norm and "macbook" not in mix:
                return False
            if "imac" in seed_norm and "imac" not in mix:
                return False
            if "mac mini" in seed_norm and "mac mini" not in mix:
                return False
            if "mac studio" in seed_norm and "mac studio" not in mix:
                return False
        return _has_laptop_hint(mix)
    if seed_type == "tablet":
        if _is_apple_seed(seed):
            return ("ipad" in mix or _has_tablet_hint(mix)) and not _has_laptop_hint(mix)
        return _has_tablet_hint(mix) and not _has_laptop_hint(mix)
    if _is_apple_seed(seed):
        return ("iphone" in mix or "apple" in mix) and not _has_tablet_hint(mix) and not _has_laptop_hint(mix)
    return not _has_tablet_hint(mix) and not _has_laptop_hint(mix)


def _normalize_capacity(capacity: int | None) -> int | None:
    if capacity is None:
        return None
    if capacity < 64:
        return None
    return capacity


def _normalize_phone_capacity(capacity: int | None) -> int | None:
    # Backward-compatible alias while rolling out mobile+tablet seeds.
    return _normalize_capacity(capacity)


def _extract_capacity_values(text: str) -> set[int]:
    normalized = normalize_text(text or "")
    gb_vals = {int(v) for v in re.findall(r"\b(64|128|256|512|1024|2048)\s*gb\b", normalized)}
    tb_vals = {int(v) * 1024 for v in re.findall(r"\b(1|2|4)\s*tb\b", normalized)}
    return gb_vals | tb_vals


def _detect_capacity_for_device(text: str, device_type: str) -> int | None:
    if normalize_text(device_type) == "laptop":
        values = _extract_capacity_values(text)
        return max(values) if values else None
    return _normalize_capacity(detect_capacity_gb(text or ""))


def _seed_search_queries(seed: ProductSeed) -> list[str]:
    seed_type = _seed_device_type(seed)
    model_text = re.sub(rf"^{re.escape(seed.brand)}\s+", "", seed.model, flags=re.IGNORECASE).strip() or seed.model
    base = " ".join([seed.brand, model_text]).strip()
    normalized_model = normalize_text(seed.model)
    core_model = re.sub(r"\b(wifi|wi fi|5g|lte)\b", " ", normalized_model)
    core_model = re.sub(rf"\b{re.escape(normalize_text(seed.brand))}\b", " ", core_model)
    core_model = re.sub(r"\s+", " ", core_model).strip()
    core = f"{seed.brand} {core_model}".strip()
    if _is_apple_seed(seed):
        if seed_type == "tablet":
            kind = "ipad"
        elif seed_type == "laptop":
            kind = "mac"
        else:
            kind = "iphone"
    else:
        if seed_type == "tablet":
            kind = "tablet"
        elif seed_type == "laptop":
            kind = "portatil"
        else:
            kind = "movil"

    candidates: list[str] = [seed.search_query, base, core]
    if seed.capacity_gb:
        candidates.append(f"{base} {seed.capacity_gb}GB")
        candidates.append(f"{core} {seed.capacity_gb}GB")
    candidates.append(f"{base} {kind}")
    candidates.append(f"{core} {kind}")
    if seed.capacity_gb:
        candidates.append(f"{base} {seed.capacity_gb}GB {kind}")
        candidates.append(f"{core} {seed.capacity_gb}GB {kind}")
    if seed_type == "laptop" and seed.product_code:
        code = re.sub(r"\s+", "", str(seed.product_code or "")).strip()
        if code:
            candidates.append(code)
            candidates.append(f"{seed.brand} {code}")
            candidates.append(f"{base} {code}")
            code_root = re.split(r"[-_/]", code)[0]
            if code_root and code_root != code:
                candidates.append(code_root)
                candidates.append(f"{seed.brand} {code_root}")
                candidates.append(f"{base} {code_root}")

    out: list[str] = []
    seen: set[str] = set()
    for query in candidates:
        cleaned = re.sub(r"\s+", " ", query).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def _alnum_tokens(text: str) -> list[str]:
    normalized = normalize_text(text)
    normalized = re.sub(r"([a-z])(\d)", r"\1 \2", normalized)
    normalized = re.sub(r"(\d)([a-z])", r"\1 \2", normalized)
    return [tok for tok in re.split(r"[^a-z0-9+]+", normalized) if tok]


def _collect_model_markers(text: str, raw_text: str = "") -> set[str]:
    markers = {"ultra", "plus", "fe", "flip", "fold", "edge", "lite"}
    tokens = set(_alnum_tokens(text))
    found = {marker for marker in markers if marker in tokens}
    raw = f"{raw_text} {text}".lower()
    if re.search(r"\b(?:s|a|z)\d{1,3}\+", raw):
        found.add("plus")
    return found


def _santander_search_url(query: str, page: int = 0) -> str:
    q = quote_plus(query)
    return (
        f"{SANTANDER_API_BASE}/products/search?"
        f"query={q}&fields=FULL&{SANTANDER_API_PARAMS}"
        f"&pageSize={SANTANDER_SEARCH_PAGE_SIZE}&currentPage={page}"
    )


async def _fetch_all_santander_search_products(request_context: APIRequestContext, query: str, max_pages: int = 20) -> list[dict]:
    products: list[dict] = []
    seen_codes: set[str] = set()
    total_pages = 1
    page = 0
    while page < total_pages and page < max_pages:
        data = await _fetch_json(request_context, _santander_search_url(query=query, page=page))
        if not data:
            break
        rows = data.get("products") or []
        if not rows and page > 0:
            break
        for row in rows:
            code = str(row.get("code") or "").strip()
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            products.append(row)
        pagination = data.get("pagination") or {}
        maybe_total = pagination.get("totalPages")
        if isinstance(maybe_total, int) and maybe_total > 0:
            total_pages = maybe_total
        else:
            total_pages = page + 1 if not rows else page + 2
        page += 1
    return products


def _santander_product_detail_url(code: str) -> str:
    return (
        f"{SANTANDER_API_BASE}/products/{code}?"
        "fields=brand,code,name,summary,url,price(FULL),priceGroups(FULL),"
        "baseOptions(FULL),stock(FULL),baseProductName&"
        f"{SANTANDER_API_PARAMS}"
    )


def _build_boutique_product_url(raw_url: str | None, code: str) -> str:
    def with_price_mode(url: str) -> str:
        if "previousPriceSelected=" in url:
            return url
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}previousPriceSelected=renting"

    def normalize_with_code(url: str, product_code: str) -> str:
        if product_code:
            url = re.sub(r"/p/[^/?#]+", f"/p/{product_code}", url, flags=re.IGNORECASE)
            url = re.sub(r"/product/[^/?#]+", f"/product/{product_code}", url, flags=re.IGNORECASE)
        return with_price_mode(url)

    if raw_url:
        if raw_url.startswith("http"):
            return normalize_with_code(raw_url, code)
        if raw_url.startswith("/es/"):
            return normalize_with_code(f"https://boutique.bancosantander.es{raw_url}", code)
        if raw_url.startswith("/"):
            return normalize_with_code(f"https://boutique.bancosantander.es/es{raw_url}", code)
    return normalize_with_code(f"https://boutique.bancosantander.es/es/product/{code}", code)


async def _fetch_json(request_context: APIRequestContext, url: str) -> dict | None:
    try:
        response = await request_context.fetch(url, timeout=TEXT_TIMEOUT_MS)
        if response.status != 200:
            return None
        return await response.json()
    except Exception:
        return None


async def _safe_goto(page: Page, url: str) -> bool:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=TEXT_TIMEOUT_MS)
        await page.wait_for_timeout(1200)
        return True
    except Exception:
        return False


async def _safe_page_title(page: Page, retries: int = 2) -> str:
    for attempt in range(retries + 1):
        try:
            return await page.title()
        except Exception:
            if attempt >= retries:
                return ""
            await page.wait_for_timeout(300)
    return ""


async def _new_context(browser: Browser):
    return await browser.new_context(
        locale="es-ES",
        user_agent=DEFAULT_USER_AGENT,
        viewport={"width": 1366, "height": 900},
    )


def _page_looks_blocked(title: str, text: str) -> bool:
    t = normalize_text(title)
    body = normalize_text(text[:2500])
    if "just a moment" in t:
        return True
    if t.startswith("un momento"):
        return True
    if "access denied" in t:
        return True
    if any(
        token in body
        for token in (
            "cf-browser-verification",
            "verify you are human",
            "captcha",
            "captcha-delivery",
            "datadome",
            "slide right to secure your access",
            "we want to make sure it is actually you",
        )
    ):
        return True
    return False


def _seed_match_score(seed: ProductSeed, text: str) -> int:
    txt = normalize_text(text)
    score = 0
    if _is_apple_seed(seed):
        if "apple" in txt:
            score += 1
        if any(token in txt for token in ("iphone", "ipad", "macbook")):
            score += 1
    else:
        if "samsung" in txt:
            score += 1
        if "galaxy" in txt:
            score += 1

    base = normalize_text(seed.model)
    for token in ("samsung", "galaxy", "apple"):
        base = re.sub(rf"\b{token}\b", " ", base)
    tokens = [tok for tok in re.split(r"[^a-z0-9]+", base) if tok and tok not in {"5g", "gb"}]
    for token in tokens:
        if token in txt:
            score += 2

    if seed.capacity_gb:
        cap_token = str(seed.capacity_gb)
        if cap_token in txt:
            score += 3
        caps_found = _extract_capacity_values(txt)
        if caps_found:
            if seed.capacity_gb in caps_found:
                score += 2
            else:
                score -= 3
    return score


def _extract_first_euro_value(text: str) -> tuple[str, float] | None:
    match = EURO_VALUE_RE.search(text.replace("\xa0", " "))
    if not match:
        return None
    raw = match.group(1)
    value = parse_euro_to_float(raw)
    if value is None:
        return None
    return f"{raw} â‚¬", value


def _extract_monthly_offer(text: str) -> dict | None:
    for match in MONTHLY_VALUE_RE.finditer(text.replace("\xa0", " ")):
        raw = match.group(1)
        value = parse_euro_to_float(raw)
        if value is None:
            continue
        start = max(0, match.start() - 80)
        end = min(len(text), match.end() + 80)
        window = text[start:end]
        term_match = TERM_RE.search(window)
        term = int(term_match.group(1)) if term_match else None
        return {
            "offer_type": "financing_max_term",
            "price_text": f"{raw} \u20ac/mes",
            "price_value": value,
            "price_unit": "EUR/month",
            "term_months": term,
        }
    return None


def _canonical_amazon_url(url: str) -> str:
    match = AMAZON_ASIN_ANY_RE.search(url)
    if not match:
        return url
    return f"https://www.amazon.es/dp/{match.group(1).upper()}"


def _url_without_fragment(url: str) -> str:
    if "#" not in url:
        return url
    return url.split("#", 1)[0]


def _looks_like_listing_url(url: str) -> bool:
    parsed = urlparse(url or "")
    path = normalize_text(parsed.path or "")
    query = normalize_text(parsed.query or "")
    if any(token in path for token in ("/search", "/buscar", "/buscador", "/result", "/resultados")):
        return True
    if query and any(token in query for token in ("q=", "query=", "search=", "s=", "k=")):
        # Most retailers expose listing/search pages with these query params.
        return True
    segments = [segment for segment in path.split("/") if segment]
    if segments and segments[-1] in {
        "apple",
        "samsung",
        "movil",
        "moviles",
        "mobile",
        "smartphone",
        "smartphones",
        "tablet",
        "tablets",
        "laptop",
        "laptops",
    }:
        return True
    if len(segments) <= 3 and any(token in path for token in ("/movil", "/moviles", "/mobile", "/smartphone", "/tablet", "/tablets")):
        if not any(ch.isdigit() for ch in path):
            return True
    return False


def _amazon_asin_from_url(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    host = normalize_text(parsed.netloc)
    if "amazon." not in host:
        return None
    match = AMAZON_ASIN_ANY_RE.search(url)
    if not match:
        return None
    return match.group(1).upper()


async def _extract_amazon_result_candidates(page: Page) -> list[dict]:
    script = """
    () => {
      const out = [];
      const cards = Array.from(document.querySelectorAll('[data-asin]'));
      for (const card of cards) {
        const asin = (card.getAttribute('data-asin') || '').trim();
        if (!asin || asin.length !== 10) continue;
        const titleEl = card.querySelector('h2 a span') || card.querySelector('h2 span');
        const linkEl = card.querySelector('h2 a[href]');
        const title = (titleEl?.textContent || '').replace(/\\s+/g, ' ').trim();
        const href = linkEl?.href || `https://www.amazon.es/dp/${asin}`;
        const cardText = (card.textContent || '').replace(/\\s+/g, ' ').trim();
        out.push({ href, text: title, card_text: cardText, asin });
      }
      return out;
    }
    """
    try:
        raw = await page.evaluate(script)
    except Exception:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw or []:
        asin = str(item.get("asin") or "").strip().upper()
        if not asin or asin in seen:
            continue
        seen.add(asin)
        out.append(
            {
                "href": f"https://www.amazon.es/dp/{asin}",
                "text": str(item.get("text", "")),
                "card_text": str(item.get("card_text", "")),
                "asin": asin,
            }
        )
    return out


def _amazon_looks_refurbished(text: str) -> bool:
    t = normalize_text(text)
    return any(
        token in t
        for token in (
            "reacondicionado",
            "reacondic",
            "renewed",
            "refurbished",
            "renovado",
            "segunda mano",
            "usado",
            "seminuevo",
        )
    )


def _amazon_candidate_matches_seed(
    seed: ProductSeed,
    text: str,
    href: str,
    enforce_capacity: bool = True,
    title_text: str | None = None,
) -> bool:
    asin = _amazon_asin_from_url(href)
    if not asin:
        return False
    seed_type = _seed_device_type(seed)
    mix = normalize_text(f"{text} {href}")
    title_mix = normalize_text(title_text or text)
    if not _brand_presence_in_text(seed, mix):
        return False
    if _is_apple_seed(seed) and "apple" not in title_mix:
        return False
    if _amazon_looks_refurbished(mix):
        return False
    if any(token in mix for token in ACCESSORY_HINTS):
        return False
    if not _seed_device_matches_candidate(seed=seed, text=text, href=href):
        return False

    seed_norm = normalize_text(seed.model)
    model_n = seed_norm
    for token in ("samsung", "galaxy", "apple"):
        model_n = re.sub(rf"\b{token}\b", " ", model_n)
    model_n = re.sub(r"\s+", " ", model_n).strip()
    model_tokens = [tok for tok in _alnum_tokens(model_n) if tok and tok not in {"5g", "gb"}]
    if _is_apple_seed(seed):
        # Connectivity labels vary a lot across listings ("WiFi", "Wi-Fi", "Wi Fi", "Cellular"),
        # so they should not be mandatory for identity.
        model_tokens = [tok for tok in model_tokens if tok not in {"wifi", "cell", "cellular", "wificell", "wi", "fi"}]
    strong_tokens = [tok for tok in model_tokens if len(tok) >= 4 or any(ch.isdigit() for ch in tok)]
    mix_compact = re.sub(r"[^a-z0-9]", "", mix)
    code_match = False
    if seed_type == "laptop" and seed.product_code:
        seed_code = re.sub(r"[^a-z0-9]", "", normalize_text(str(seed.product_code)))
        seed_root = re.split(r"[-_/]", str(seed.product_code))[0]
        seed_root = re.sub(r"[^a-z0-9]", "", normalize_text(seed_root))
        code_match = bool(
            (seed_code and seed_code in mix_compact)
            or (seed_root and len(seed_root) >= 6 and seed_root in mix_compact)
        )
    if strong_tokens and not all(tok in mix for tok in strong_tokens):
        if not (seed_type == "laptop" and code_match):
            return False

    if _is_samsung_seed(seed):
        for family in ("s", "a"):
            numbers = set(re.findall(rf"\b{family}\s*(\d{{2,3}})\b", seed_norm))
            for num in numbers:
                if f"{family}{num}" not in mix_compact:
                    return False
        flip_num = re.search(r"\bflip\s*(\d{1,2})\b", seed_norm)
        if flip_num and f"flip{flip_num.group(1)}" not in mix_compact:
            return False
        fold_num = re.search(r"\bfold\s*(\d{1,2})\b", seed_norm)
        if fold_num and f"fold{fold_num.group(1)}" not in mix_compact:
            return False

        seed_markers = _collect_model_markers(model_n, seed.model)
        cand_markers = _collect_model_markers(mix, f"{text} {href}")
        if seed_type in {"mobile", "tablet"}:
            if "lite" in set(_alnum_tokens(model_n)):
                seed_markers.add("lite")
            if "lite" in set(_alnum_tokens(mix)):
                cand_markers.add("lite")
            if seed_markers and not seed_markers.issubset(cand_markers):
                return False
            if not seed_markers and cand_markers.intersection({"ultra", "plus", "fe", "lite", "edge"}):
                return False
    elif _is_apple_seed(seed):
        iphone_num = re.search(r"\biphone\s*(\d{1,2})\b", seed_norm)
        if iphone_num and not re.search(rf"\biphone\s*{iphone_num.group(1)}\b", mix):
            return False
        apple_markers = ("pro", "max", "plus", "mini", "air")
        seed_markers = {m for m in apple_markers if re.search(rf"\b{m}\b", seed_norm)}
        cand_markers = {m for m in apple_markers if re.search(rf"\b{m}\b", mix)}
        if seed_markers and not seed_markers.issubset(cand_markers):
            return False
        if not seed_markers and cand_markers.intersection({"pro", "max", "plus", "mini", "air"}):
            return False

    if seed.capacity_gb and enforce_capacity:
        caps = _extract_capacity_values(mix)
        if caps and seed.capacity_gb not in caps:
            return False
    return True


def _dedupe_offers(offers: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple] = set()
    for offer in offers:
        row = (offer["offer_type"], offer["price_value"], offer.get("term_months"))
        if row in seen:
            continue
        seen.add(row)
        out.append(offer)
    return out


async def _extract_visible_text(page: Page) -> str:
    try:
        return await page.locator("body").inner_text(timeout=TEXT_TIMEOUT_MS)
    except Exception:
        return ""


async def _extract_links(page: Page) -> list[dict]:
    script = """
    () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
      href: a.href || '',
      text: (a.textContent || '').trim()
    }))
    """
    try:
        result = await page.evaluate(script)
        return [item for item in result if item.get("href")]
    except Exception:
        return []


def _unique_by_key(seeds: Iterable[ProductSeed]) -> list[ProductSeed]:
    seen: set[str] = set()
    out: list[ProductSeed] = []
    for seed in seeds:
        if seed.product_code:
            code_key = _normalize_product_code_token(seed.product_code) or seed.product_code
            key = f"{_seed_device_type(seed)}::{code_key}"
        else:
            key = f"{_seed_device_type(seed)}::{seed.source_url}"
        if key in seen:
            continue
        seen.add(key)
        out.append(seed)
    return out


def _interleave_seeds_by_device(seeds: list[ProductSeed], max_products: int) -> list[ProductSeed]:
    if max_products <= 0:
        return []
    mobile = [seed for seed in seeds if _seed_device_type(seed) == "mobile"]
    tablet = [seed for seed in seeds if _seed_device_type(seed) == "tablet"]
    other = [seed for seed in seeds if _seed_device_type(seed) not in {"mobile", "tablet"}]

    out: list[ProductSeed] = []
    idx_mobile = 0
    idx_tablet = 0
    idx_other = 0
    while len(out) < max_products:
        advanced = False
        if idx_mobile < len(mobile):
            out.append(mobile[idx_mobile])
            idx_mobile += 1
            advanced = True
            if len(out) >= max_products:
                break
        if idx_tablet < len(tablet):
            out.append(tablet[idx_tablet])
            idx_tablet += 1
            advanced = True
            if len(out) >= max_products:
                break
        if idx_other < len(other):
            out.append(other[idx_other])
            idx_other += 1
            advanced = True
        if not advanced:
            break
    return out


def _unique_matching_seeds(seeds: list[ProductSeed]) -> list[ProductSeed]:
    out: list[ProductSeed] = []
    seen: set[tuple[str, str, str, int | None]] = set()
    for seed in seeds:
        key = (_seed_device_type(seed), normalize_text(seed.brand), normalize_text(seed.model), seed.capacity_gb)
        if key in seen:
            continue
        seen.add(key)
        out.append(seed)
    return out


def _capacity_from_option_qualifiers(option: dict) -> int | None:
    qualifiers = option.get("variantOptionQualifiers") or []
    preferred_labels = {
        "storage",
        "capacidad",
        "capacity",
        "memory",
        "memoria",
        "almacenamiento",
        "storage size",
    }

    fallback_caps: set[int] = set()
    for qualifier in qualifiers:
        qmeta = " ".join(
            [
                str(qualifier.get("qualifier", "")),
                str(qualifier.get("name", "")),
                str(qualifier.get("type", "")),
            ]
        )
        qname = normalize_text(qmeta)
        value = str(qualifier.get("value", ""))
        values = _extract_capacity_values(value)
        if values:
            fallback_caps.update(values)
        if not any(label in qname for label in preferred_labels):
            continue
        if values:
            return max(values)
        cap = _normalize_capacity(detect_capacity_gb(value))
        if cap is not None:
            return cap

    if fallback_caps:
        return max(fallback_caps)

    # Some payloads expose capacity directly at option level (outside qualifiers).
    for field in ("name", "value", "formattedValue", "displayValue", "code"):
        values = _extract_capacity_values(str(option.get(field, "")))
        if values:
            return max(values)
    return None


def _normalize_product_code_token(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _capacity_from_variant_options(detail: dict, product_code: str | None = None) -> int | None:
    base_options = detail.get("baseOptions") or []
    if not base_options:
        return None

    code_to_match = _normalize_product_code_token(product_code or detail.get("code") or "")
    if code_to_match:
        matched_code = False
        matched_caps: set[int] = set()
        for base_option in base_options:
            for opt in base_option.get("options") or []:
                opt_code = _normalize_product_code_token(opt.get("code") or "")
                if not opt_code or opt_code != code_to_match:
                    continue
                matched_code = True
                cap = _capacity_from_option_qualifiers(opt)
                if cap is not None:
                    matched_caps.add(cap)
        if matched_caps:
            return max(matched_caps)
        if matched_code:
            # We found the SKU, but no deterministic storage value.
            return None

    # Fallback only when SKU mapping is unavailable. If multiple capacities are
    # present, return None instead of picking one arbitrarily.
    fallback_caps: set[int] = set()
    for base_option in base_options:
        for opt in base_option.get("options") or []:
            cap = _capacity_from_option_qualifiers(opt)
            if cap is not None:
                fallback_caps.add(cap)
    if len(fallback_caps) == 1:
        return next(iter(fallback_caps))
    return None


def _variant_capacity_entries(detail: dict, device_type: str) -> list[tuple[str, str, int]]:
    base_options = detail.get("baseOptions") or []
    by_code: dict[str, tuple[str, int, int]] = {}
    for base_option in base_options:
        for opt in base_option.get("options") or []:
            raw_code = str(opt.get("code") or "").strip()
            norm_code = _normalize_product_code_token(raw_code)
            if not norm_code:
                continue

            capacity = _capacity_from_option_qualifiers(opt)
            if capacity is None:
                option_text = " ".join(
                    [
                        str(opt.get("name") or ""),
                        str(opt.get("value") or ""),
                        str(opt.get("formattedValue") or ""),
                        str(opt.get("displayValue") or ""),
                        str(opt.get("code") or ""),
                    ]
                )
                capacity = _detect_capacity_for_device(option_text, device_type)
            if capacity is None:
                continue

            # Prefer canonical SKU codes (usually non-campaign prefixed).
            preference = 0 if raw_code and raw_code[:1].isalpha() else 1
            current = by_code.get(norm_code)
            if current is None or preference < current[2]:
                by_code[norm_code] = (raw_code, capacity, preference)

    out: list[tuple[str, str, int]] = []
    for norm_code, (raw_code, capacity, _) in by_code.items():
        out.append((raw_code, norm_code, capacity))
    return out


async def _discover_santander_seeds_from_api(
    request_context: APIRequestContext,
    max_products: int,
    brand: str,
) -> list[ProductSeed]:
    brand_n = normalize_text(brand)
    seeds: list[ProductSeed] = []
    if brand_n == "apple":
        phone_queries = APPLE_PHONE_QUERIES
        tablet_queries = APPLE_TABLET_QUERIES
        laptop_queries = APPLE_LAPTOP_QUERIES
    else:
        phone_queries = SANTANDER_PHONE_QUERIES
        tablet_queries = SANTANDER_TABLET_QUERIES
        laptop_queries = SANTANDER_LAPTOP_QUERIES

    queries: list[tuple[str, str]] = []
    # Broad catch-all improves coverage for full-catalog runs.
    queries.extend([("mobile", brand), ("tablet", brand), ("laptop", brand)])
    queries.extend([("laptop", q) for q in laptop_queries])
    max_len = max(len(phone_queries), len(tablet_queries))
    for idx in range(max_len):
        if idx < len(phone_queries):
            queries.append(("mobile", phone_queries[idx]))
        if idx < len(tablet_queries):
            queries.append(("tablet", tablet_queries[idx]))
    seen_query_pairs: set[tuple[str, str]] = set()
    for expected_type, query in queries:
        key = (expected_type, normalize_text(query))
        if key in seen_query_pairs:
            continue
        seen_query_pairs.add(key)
        products = await _fetch_all_santander_search_products(request_context, query=query)
        for product in products:
            code = str(product.get("code") or "")
            name = strip_html_tags(str(product.get("name") or ""))
            if not code or not name:
                continue
            detected_type = _classify_brand_device_candidate(code=code, name=name, brand=brand)
            if not detected_type:
                continue
            if detected_type != expected_type:
                continue

            model = _extract_model_for_brand(name, brand=brand)
            capacity = _detect_capacity_for_device(name, detected_type)
            source_url = _build_boutique_product_url(product.get("url"), code)
            seeds.append(
                ProductSeed(
                    brand=brand,
                    model=model,
                    capacity_gb=capacity,
                    source_url=source_url,
                    device_type=detected_type,
                    product_code=code,
                )
            )

    deduped = _unique_by_key(seeds)
    return _interleave_seeds_by_device(deduped, max_products)


async def _enrich_seed_capacities_from_api(
    request_context: APIRequestContext,
    seeds: list[ProductSeed],
) -> list[ProductSeed]:
    enriched: list[ProductSeed] = []
    seen_codes: set[str] = set()
    for seed in seeds:
        detail: dict | None = None
        if seed.product_code:
            detail = await _fetch_json(request_context, _santander_product_detail_url(seed.product_code))

        if detail:
            seed_type = _seed_device_type(seed)
            cap = _capacity_from_variant_options(detail, product_code=seed.product_code)
            if cap is None:
                cap = _detect_capacity_for_device(
                    " ".join(
                        [
                            str(detail.get("name") or ""),
                            str(detail.get("summary") or ""),
                            str(detail.get("baseProductName") or ""),
                        ]
                    ),
                    seed_type,
                )
            if cap is not None:
                seed.capacity_gb = cap
            if _is_apple_seed(seed):
                title_for_model = " ".join(
                    [
                        str(detail.get("name") or ""),
                        str(detail.get("baseProductName") or ""),
                        str(detail.get("summary") or ""),
                    ]
                )
                normalized_model = _normalize_apple_model_alias(_extract_apple_model(title_for_model))
                if normalized_model and normalized_model != "Apple":
                    seed.model = normalized_model

        normalized_seed_code = _normalize_product_code_token(seed.product_code)
        if normalized_seed_code:
            seen_codes.add(normalized_seed_code)
        enriched.append(seed)

        if not detail:
            continue

        base_url = str(detail.get("url") or seed.source_url)
        for raw_code, normalized_code, variant_capacity in _variant_capacity_entries(detail, _seed_device_type(seed)):
            if normalized_code in seen_codes:
                continue
            seen_codes.add(normalized_code)
            enriched.append(
                ProductSeed(
                    brand=seed.brand,
                    model=seed.model,
                    capacity_gb=variant_capacity,
                    source_url=_build_boutique_product_url(base_url, raw_code),
                    device_type=seed.device_type,
                    product_code=raw_code,
                )
            )

    # Collapse color/SKU duplicates that map to the same device/model/capacity
    # so downstream competitor runs spend their budget on broader coverage.
    return _unique_matching_seeds(enriched)


async def _discover_santander_seeds_from_html(browser: Browser, max_products: int, brand: str) -> list[ProductSeed]:
    brand_n = normalize_text(brand)
    context = await _new_context(browser)
    page = await context.new_page()

    discovered_links: dict[str, str] = {}
    for url in SANTANDER_CATALOG_URLS:
        ok = await _safe_goto(page, url)
        if not ok:
            continue
        links = await _extract_links(page)
        for item in links:
            href = item["href"]
            text = item["text"]
            tokenized = normalize_text(f"{href} {text}")
            if brand_n == "apple":
                brand_hit = any(token in tokenized for token in ("apple", "iphone", "ipad", "macbook"))
            else:
                brand_hit = "galaxy" in tokenized or "samsung" in tokenized
            if "/product/" in href and brand_hit:
                discovered_links[href] = text
        if discovered_links:
            break

    seeds: list[ProductSeed] = []
    for href, hint_text in discovered_links.items():
        if len(seeds) >= max_products:
            break
        if not await _safe_goto(page, href):
            continue
        title = await page.title()
        body_text = await _extract_visible_text(page)
        mix = " ".join([hint_text, title, body_text[:3000]])
        device_type = _candidate_device_type(text=mix, href=href)
        if not device_type:
            continue
        seeds.append(
            ProductSeed(
                brand=brand,
                model=_extract_model_for_brand(mix, brand=brand),
                capacity_gb=_detect_capacity_for_device(mix, device_type),
                source_url=href,
                device_type=device_type,
            )
        )

    await context.close()
    deduped = _unique_by_key(seeds)
    return _interleave_seeds_by_device(deduped, max_products)


async def scrape_santander_base_products(
    browser: Browser,
    request_context: APIRequestContext,
    max_products: int,
    brand: str,
) -> list[ProductSeed]:
    seeds = await _discover_santander_seeds_from_api(
        request_context,
        max_products=max_products,
        brand=brand,
    )
    if seeds:
        return await _enrich_seed_capacities_from_api(request_context, seeds)
    return await _discover_santander_seeds_from_html(browser, max_products=max_products, brand=brand)


def _extract_offer_prices(page_text: str) -> list[dict]:
    offers: list[dict] = []
    for offer in OFFER_TYPES:
        matched = find_price_after_keywords(page_text, offer.keywords)
        if not matched:
            continue
        price_text, price_value = matched
        offers.append(
            {
                "offer_type": offer.code,
                "price_text": price_text,
                "price_value": price_value,
                "price_unit": offer.price_unit,
                "term_months": offer.term_months_default,
            }
        )

    if offers:
        return offers

    fallback = find_first_price(page_text)
    if fallback:
        price_text, price_value = fallback
        return [
            {
                "offer_type": "cash",
                "price_text": price_text,
                "price_value": price_value,
                "price_unit": "EUR",
                "term_months": None,
            }
        ]
    return []


def _extract_santander_api_offers(detail: dict) -> list[dict]:
    best_by_mode: dict[tuple[str, int | None], dict] = {}
    for group in detail.get("priceGroups") or []:
        for price in group.get("prices") or []:
            mode = normalize_text(str(price.get("paymentMode") or ""))
            installments = price.get("installments")
            value = price.get("value")
            if value is None:
                continue

            offer_type = "cash"
            price_unit = "EUR"
            term_months = None

            if "renting" in mode:
                insurance_title = normalize_text(str((price.get("insuranceTypeData") or {}).get("title") or ""))
                offer_type = "renting_with_insurance" if "con seguro" in insurance_title else "renting_no_insurance"
                price_unit = "EUR/month"
                term_months = installments if isinstance(installments, int) and installments > 0 else None
            elif "creditcard" in mode or "credit card" in mode:
                if isinstance(installments, int) and installments > 0:
                    offer_type = "financing_max_term"
                    price_unit = "EUR/month"
                    term_months = installments
                else:
                    offer_type = "cash"
                    price_unit = "EUR"

            candidate = {
                "offer_type": offer_type,
                "price_text": f"{float(value):.2f} EUR",
                "price_value": float(value),
                "price_unit": price_unit,
                "term_months": term_months,
            }
            key = (offer_type, term_months)
            current = best_by_mode.get(key)
            if current is None or float(candidate["price_value"]) < float(current["price_value"]):
                best_by_mode[key] = candidate
    return list(best_by_mode.values())


def _extract_sin_seguro_offer_from_text(page_text: str) -> dict | None:
    match = SIN_SEGURO_RE.search(page_text)
    if not match:
        return None
    value = parse_euro_to_float(match.group(1))
    if value is None:
        return None
    return {
        "offer_type": "renting_no_insurance",
        "price_text": f"{match.group(1)} â‚¬",
        "price_value": value,
        "price_unit": "EUR/month",
        "term_months": 36,
    }


def _allow_sin_seguro_fallback(seed_type: str, candidate: dict | None, offers: list[dict]) -> bool:
    if not candidate:
        return False
    # In laptops/tablets Santander often shows unrelated monthly snippets;
    # avoid inventing "sin seguro" when API does not provide it.
    if seed_type in {"laptop", "tablet"}:
        return False
    with_insurance = [float(o.get("price_value", 0.0)) for o in offers if o.get("offer_type") == "renting_with_insurance"]
    if not with_insurance:
        return True
    min_with = min(with_insurance)
    value = float(candidate.get("price_value", 0.0))
    if value <= 0:
        return False
    if value > min_with:
        return False
    return value >= (min_with * 0.6)


def _detail_stock_to_bool(detail: dict) -> bool | None:
    stock = detail.get("stock")
    if isinstance(stock, dict):
        status = normalize_text(str(stock.get("stockLevelStatus") or ""))
        if "outofstock" in status:
            return False
        if "instock" in status:
            return True
    return None


async def _scrape_page_offers(page: Page, url: str) -> tuple[str | None, str, list[dict], bool | None]:
    ok = await _safe_goto(page, url)
    if not ok:
        return None, "", [], None
    title = await page.title()
    text = await _extract_visible_text(page)
    offers = _extract_offer_prices(text)
    stock_state = detect_stock_state(text)
    return title, text, offers, stock_state


def _record_from_offer(
    competitor: str,
    seed: ProductSeed,
    source_url: str,
    source_title: str | None,
    in_stock: bool | None,
    capacity: int | None,
    offer: dict,
    quality_tier: str,
) -> PriceRecord:
    explicit_capture_kind = str(offer.get("price_capture_kind") or "").strip()
    quality_tier_n = normalize_text(quality_tier)
    competitor_n = normalize_text(competitor)
    offer_type_n = normalize_text(str(offer.get("offer_type") or ""))
    if explicit_capture_kind:
        capture_kind = explicit_capture_kind
    elif competitor_n == "santander boutique" or "api" in quality_tier_n:
        capture_kind = "api_exact"
    elif competitor_n == "movistar" or "json" in quality_tier_n:
        capture_kind = "embedded_json_exact"
    elif competitor_n == "media markt" and offer_type_n == "financing_max_term":
        capture_kind = "api_exact"
    else:
        capture_kind = "visible_dom"

    return PriceRecord(
        country="ES",
        retailer=competitor,
        retailer_slug=RETAILER_SLUGS[competitor],
        product_family=seed.brand,
        brand=seed.brand,
        device_type=_seed_device_type(seed),
        model=seed.model,
        capacity_gb=capacity,
        offer_type=offer["offer_type"],
        price_value=offer["price_value"],
        price_text=offer["price_text"],
        price_unit=offer["price_unit"],
        term_months=offer["term_months"],
        in_stock=in_stock,
        data_quality_tier=quality_tier,
        price_capture_kind=capture_kind,
        extracted_at=PriceRecord.now_iso(),
        source_url=source_url,
        source_title=source_title,
    )


async def _scrape_santander_prices(
    browser: Browser,
    request_context: APIRequestContext,
    seeds: list[ProductSeed],
) -> list[PriceRecord]:
    records: list[PriceRecord] = []
    context = await _new_context(browser)
    page = await context.new_page()

    for seed in seeds:
        if not seed.product_code:
            continue
        detail_url = _santander_product_detail_url(seed.product_code)
        detail = await _fetch_json(request_context, detail_url)
        if not detail:
            continue

        offers = _extract_santander_api_offers(detail)
        seed_type = _seed_device_type(seed)
        capacity = _capacity_from_variant_options(detail, product_code=seed.product_code)
        if capacity is None:
            capacity = _detect_capacity_for_device(
                " ".join(
                    [
                        str(detail.get("name") or ""),
                        str(detail.get("summary") or ""),
                        str(detail.get("baseProductName") or ""),
                    ]
                ),
                seed_type,
            )
        if capacity is None:
            capacity = seed.capacity_gb
        source_title = strip_html_tags(str(detail.get("name") or seed.model))
        in_stock = _detail_stock_to_bool(detail)

        if not any(o["offer_type"] == "renting_no_insurance" for o in offers):
            ok = await _safe_goto(page, seed.source_url)
            if ok:
                body_text = await _extract_visible_text(page)
                sin_seguro = _extract_sin_seguro_offer_from_text(body_text)
                if _allow_sin_seguro_fallback(seed_type, sin_seguro, offers):
                    offers.append(sin_seguro)
                if in_stock is None:
                    in_stock = detect_stock_state(body_text)

        for offer in offers:
            records.append(
                _record_from_offer(
                    competitor="Santander Boutique",
                    seed=seed,
                    source_url=seed.source_url,
                    source_title=source_title,
                    in_stock=in_stock,
                    capacity=capacity,
                    offer=offer,
                    quality_tier="santander_api_live",
                )
            )

    await context.close()
    return records


async def _extract_search_candidates(page: Page) -> list[dict]:
    script = """
    () => {
      const out = [];
      const anchors = Array.from(document.querySelectorAll('a[href]'));
      for (const a of anchors.slice(0, 2500)) {
        const href = a.href || '';
        const text = (a.textContent || '').replace(/\\s+/g, ' ').trim();
        if (!href) continue;
        const card = a.closest('article') || a.closest('li') || a.closest('[data-component-type=\"s-search-result\"]') || a.parentElement;
        const cardText = (card?.textContent || '').replace(/\\s+/g, ' ').trim();
        out.push({ href, text, card_text: cardText });
      }
      return out;
    }
    """
    try:
        result = await page.evaluate(script)
        return [item for item in result if item.get("href")]
    except Exception:
        return []


def _mediamarkt_candidate_text(item: dict) -> str:
    direct = re.sub(r"\s+", " ", strip_html_tags(str(item.get("text", "") or ""))).strip()
    card = re.sub(r"\s+", " ", strip_html_tags(str(item.get("card_text", "") or ""))).strip()
    if len(normalize_text(direct)) >= 12:
        return direct
    return card or direct


def _mediamarkt_candidate_priority(item: dict) -> tuple[int, int, int]:
    direct = re.sub(r"\s+", " ", strip_html_tags(str(item.get("text", "") or ""))).strip()
    card = re.sub(r"\s+", " ", strip_html_tags(str(item.get("card_text", "") or ""))).strip()
    return (1 if len(normalize_text(direct)) >= 12 else 0, len(direct), len(card))


def _pick_best_candidate(seed: ProductSeed, candidates: list[dict], excluded_urls: set[str] | None = None) -> dict | None:
    excluded = excluded_urls or set()
    scored: list[tuple[int, dict]] = []
    for item in candidates:
        href = str(item.get("href", ""))
        canonical = _canonical_amazon_url(href) if "amazon." in normalize_text(href) else href
        if canonical in excluded:
            continue
        mix = " ".join([str(item.get("text", "")), str(item.get("card_text", "")), str(item.get("href", ""))])
        score = _seed_match_score(seed, mix)
        if score <= 0:
            continue
        scored.append((score, item))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _apple_oficial_candidate_url(seed: ProductSeed, url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    host = normalize_text(parsed.netloc or "")
    path = normalize_text(parsed.path or "")
    query = normalize_text(parsed.query or "")
    if "apple.com" not in host:
        return None
    if not path.startswith("/es/"):
        return None
    if "/shop/buy-" not in path:
        return None
    if "/search/" in path or "/compare/" in path or "/specs/" in path or "/switch/" in path:
        return None
    if query and any(token in query for token in ("q=", "query=", "search=", "s=", "k=", "tab=", "page=")):
        return None
    if any(
        token in path
        for token in (
            "/shop/refurbished",
            "/shop/help",
            "/shop/browse",
            "/shop/iphone/accessories",
            "/shop/ipad/accessories",
            "/shop/mac/accessories",
            "/shop/accessories",
            "/shop/bag",
            "/shop/gift-cards",
            "/support/",
        )
    ):
        return None

    seed_type = _seed_device_type(seed)
    if seed_type == "mobile":
        allowed = ("/shop/buy-iphone/",)
    elif seed_type == "tablet":
        allowed = ("/shop/buy-ipad/",)
    else:
        allowed = ("/shop/buy-mac/",)
    if not any(token in path for token in allowed):
        return None

    clean = parsed._replace(query="", fragment="").geturl()
    return clean


def _apple_oficial_matches_seed(seed: ProductSeed, text: str, href: str) -> bool:
    if not _is_apple_seed(seed):
        return False
    mix = normalize_text(" ".join([text or "", href or ""]))
    if any(token in mix for token in ACCESSORY_HINTS):
        return False
    if not _brand_presence_in_text(seed, mix):
        return False
    if not _seed_device_matches_candidate(seed=seed, text=text, href=href):
        return False

    path = normalize_text(urlparse(href).path or "")
    seed_n = normalize_text(seed.model)
    seed_type = _seed_device_type(seed)

    if seed_type == "mobile":
        if "iphone air" in seed_n or "iphone 17 air" in seed_n:
            return "iphone-air" in path
        if "16e" in seed_n:
            return "iphone-16e" in path
        num_m = re.search(r"\biphone\s*(\d{1,2})\b", seed_n)
        if not num_m:
            return "/shop/buy-iphone/" in path
        num = num_m.group(1)
        if "pro max" in seed_n or re.search(r"\biphone\s*\d{1,2}\s*pro\b", seed_n):
            return f"iphone-{num}-pro" in path
        return (
            f"iphone-{num}" in path
            and f"iphone-{num}-pro" not in path
            and "iphone-air" not in path
        )

    if seed_type == "tablet":
        if "ipad pro" in seed_n:
            return "ipad-pro" in path
        if "ipad air" in seed_n:
            return "ipad-air" in path
        if "ipad mini" in seed_n:
            return "ipad-mini" in path
        return "/shop/buy-ipad/" in path and all(token not in path for token in ("ipad-pro", "ipad-air", "ipad-mini"))

    if "mac mini" in seed_n:
        return "mac-mini" in path
    if "mac studio" in seed_n:
        return "mac-studio" in path
    if "macbook air" in seed_n:
        return "macbook-air" in path
    if "macbook pro" in seed_n:
        return "macbook-pro" in path
    if "imac" in seed_n:
        return "imac" in path
    return "/shop/buy-mac/" in path


def _apple_oficial_manual_buy_urls(seed: ProductSeed) -> list[str]:
    seed_n = normalize_text(seed.model)
    seed_type = _seed_device_type(seed)
    urls: list[str] = []
    if seed_type == "mobile":
        if "iphone air" in seed_n or "iphone 17 air" in seed_n:
            urls.append("https://www.apple.com/es/shop/buy-iphone/iphone-air")
        if "iphone 16e" in seed_n:
            urls.append("https://www.apple.com/es/shop/buy-iphone/iphone-16e")
        if re.search(r"\biphone\s*17\b", seed_n) and "pro" not in seed_n and "max" not in seed_n and "air" not in seed_n:
            urls.append("https://www.apple.com/es/shop/buy-iphone/iphone-17")
        if "iphone 17 pro" in seed_n or "iphone 17 pro max" in seed_n:
            urls.append("https://www.apple.com/es/shop/buy-iphone/iphone-17-pro")
    elif seed_type == "tablet":
        if "ipad air" in seed_n:
            urls.append("https://www.apple.com/es/shop/buy-ipad/ipad-air")
        elif "ipad pro" in seed_n:
            urls.append("https://www.apple.com/es/shop/buy-ipad/ipad-pro")
        elif "ipad mini" in seed_n:
            urls.append("https://www.apple.com/es/shop/buy-ipad/ipad-mini")
        else:
            urls.append("https://www.apple.com/es/shop/buy-ipad/ipad")
    else:
        if "mac mini" in seed_n:
            urls.append("https://www.apple.com/es/shop/buy-mac/mac-mini")
        elif "mac studio" in seed_n:
            urls.append("https://www.apple.com/es/shop/buy-mac/mac-studio")
        elif "macbook air" in seed_n:
            urls.append("https://www.apple.com/es/shop/buy-mac/macbook-air")
        elif "macbook pro" in seed_n:
            urls.append("https://www.apple.com/es/shop/buy-mac/macbook-pro")
        elif "imac" in seed_n:
            urls.append("https://www.apple.com/es/shop/buy-mac/imac")
        else:
            urls.append("https://www.apple.com/es/shop/buy-mac")

    out: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


async def _select_apple_radio_value(page: Page, value_token: str, name_hint: str | None = None) -> bool:
    script = """
    ({ valueToken, nameHint }) => {
      const norm = (s) => (s || '').toLowerCase().replace(/\\s+/g, '');
      const want = norm(valueToken);
      const hint = norm(nameHint || '');
      const inputs = Array.from(document.querySelectorAll("input.form-selector-input[type='radio']"));
      const target = inputs.find((i) => {
        const name = norm(i.getAttribute('name') || '');
        const value = norm(i.getAttribute('value') || '');
        if (!value || value !== want) return false;
        if (hint && !name.includes(hint)) return false;
        return true;
      });
      if (!target) return false;
      const id = target.id || '';
      const label = id ? document.querySelector(`label[for='${id}']`) : null;
      if (label instanceof HTMLElement) label.click();
      if (target instanceof HTMLElement) target.click();
      target.dispatchEvent(new Event('input', { bubbles: true }));
      target.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    }
    """
    try:
        clicked = await page.evaluate(script, {"valueToken": value_token, "nameHint": name_hint or ""})
        if clicked:
            await page.wait_for_timeout(700)
        return bool(clicked)
    except Exception:
        return False


async def _select_apple_variant_for_seed(page: Page, seed: ProductSeed) -> None:
    if not _is_apple_seed(seed):
        return
    seed_n = normalize_text(seed.model)
    seed_type = _seed_device_type(seed)

    if seed_type == "tablet":
        if "ipad air" in seed_n:
            if re.search(r"\b13\b", seed_n):
                _ = await _select_apple_radio_value(page, "13inch", name_hint="dimensionscreensize")
            elif re.search(r"\b11\b", seed_n):
                _ = await _select_apple_radio_value(page, "11inch", name_hint="dimensionscreensize")
        if "wifi+cell" in seed_n or "wificell" in seed_n or "cell" in seed_n:
            _ = await _select_apple_radio_value(page, "wificell", name_hint="dimensionconnection")
        elif "wifi" in seed_n:
            _ = await _select_apple_radio_value(page, "wifi", name_hint="dimensionconnection")
        return

    if seed_type == "laptop" and "mac studio" in seed_n:
        if "m4 max" in seed_n:
            _ = await _select_apple_radio_value(page, "m4max", name_hint="dimensionchip")
        elif "m3 ultra" in seed_n:
            _ = await _select_apple_radio_value(page, "m3ultra", name_hint="dimensionchip")
        return


def _apple_offers_from_option_text(text: str) -> list[dict]:
    offers: list[dict] = []
    cash = _extract_first_euro_value(text)
    if cash:
        price_text, price_value = cash
        offers.append(
            {
                "offer_type": "cash",
                "price_text": price_text,
                "price_value": price_value,
                "price_unit": "EUR",
                "term_months": None,
            }
        )
    monthly = _extract_monthly_offer(text)
    if monthly:
        if monthly.get("term_months") is None:
            monthly["term_months"] = 24
        offers.append(monthly)
    return _dedupe_offers(offers)


async def _extract_apple_capacity_offer_map(page: Page) -> dict[int, list[dict]]:
    script = """
    () => {
      const out = [];
      const radios = Array.from(document.querySelectorAll(
        "input.form-selector-input[type='radio']"
      )).filter((input) => ((input.getAttribute('name') || '').toLowerCase().includes('dimensioncapacity')));
      const labels = Array.from(document.querySelectorAll("label[for]"));
      for (const input of radios) {
        const value = (input.value || "").toLowerCase();
        const autom = (input.getAttribute("data-autom") || "").toLowerCase();
        if (!/(gb|tb)/.test(`${value} ${autom}`)) continue;

        const inputId = input.id || "";
        let labelText = "";
        if (inputId) {
          const found = labels.find((lbl) => (lbl.getAttribute("for") || "") === inputId);
          if (found) labelText = found.textContent || "";
        }
        if (!labelText) {
          const host = input.closest("label, li, div, section, article") || input.parentElement;
          labelText = host ? host.textContent || "" : "";
        }
        labelText = labelText.replace(/\\s+/g, " ").trim();
        if (!labelText) continue;
        out.push({ value, autom, text: labelText, checked: !!input.checked });
      }
      return out;
    }
    """
    try:
        rows = await page.evaluate(script)
    except Exception:
        rows = []
    if not isinstance(rows, list):
        return {}

    by_capacity: dict[int, list[dict]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "")
        mix = " ".join([str(row.get("value") or ""), str(row.get("autom") or ""), text])
        capacities = _extract_capacity_values(mix)
        if not capacities:
            continue
        capacity = max(capacities)
        offers = _apple_offers_from_option_text(text)
        if not offers:
            continue
        current = by_capacity.get(capacity)
        if current is None:
            by_capacity[capacity] = offers
            continue
        # Keep the most complete set (cash + financing when available).
        current_types = {o.get("offer_type") for o in current}
        new_types = {o.get("offer_type") for o in offers}
        if len(new_types) > len(current_types):
            by_capacity[capacity] = offers
    return by_capacity


def _offers_from_snippet(text: str) -> list[dict]:
    offers: list[dict] = []
    cash = _extract_first_euro_value(text)
    if cash:
        price_text, price_value = cash
        offers.append(
            {
                "offer_type": "cash",
                "price_text": price_text,
                "price_value": price_value,
                "price_unit": "EUR",
                "term_months": None,
            }
        )
    monthly = _extract_monthly_offer(text)
    if monthly:
        offers.append(monthly)
    return _dedupe_offers(offers)


def _extract_mediamarkt_offers_from_text(text: str) -> list[dict]:
    offers: list[dict] = []
    plain = text.replace("\xa0", " ")
    lower = normalize_text(plain)

    # Try to anchor cash price around the main price section.
    cash_segment = plain
    anchor = lower.find(normalize_text("ficha tÃ©cnica"))
    if anchor >= 0:
        cash_segment = plain[anchor : anchor + 900]
    cash = _extract_first_euro_value(cash_segment) or _extract_first_euro_value(plain)
    if cash and cash[1] >= 100:
        price_text, price_value = cash
        offers.append(
            {
                "offer_type": "cash",
                "price_text": price_text,
                "price_value": price_value,
                "price_unit": "EUR",
                "term_months": None,
            }
        )

    fin_match = MEDIAMARKT_FIN_RE.search(plain)
    if fin_match:
        term = int(fin_match.group(1))
        value = parse_euro_to_float(fin_match.group(2))
        if value is not None:
            offers.append(
                {
                    "offer_type": "financing_max_term",
                    "price_text": f"{fin_match.group(2)} â‚¬/mes",
                    "price_value": value,
                    "price_unit": "EUR/month",
                    "term_months": term,
                }
            )

    return _dedupe_offers(offers)


def _normalize_mediamarkt_price_fragment(raw: str) -> str:
    cleaned = str(raw or "").strip().replace("\xa0", " ")
    cleaned = re.sub(r",\s*[–-]+", ",00", cleaned)
    cleaned = cleaned.replace("–", "00")
    return cleaned


def _extract_mediamarkt_teaser_offer_from_text(text: str) -> dict | None:
    plain = re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()
    if not plain:
        return None

    segment_match = re.search(
        r"Financiaci[oó]n(.*?)(?:Simula tu financiaci[oó]n|Puntos miMediaMarkt|Color \(por fabricante\)|Seleccione una oferta)",
        plain,
        flags=re.IGNORECASE,
    )
    segment = segment_match.group(1) if segment_match else plain
    term_match = re.search(r"En\s+(\d{1,2})\s+cuotas", segment, flags=re.IGNORECASE)
    price_match = re.search(
        r"(\d{1,5}(?:[.,][\d–-]{1,2})?)\s*(?:€|eur)\s*Mensual",
        segment,
        flags=re.IGNORECASE,
    )
    if not term_match or not price_match:
        return None

    value = parse_euro_to_float(_normalize_mediamarkt_price_fragment(price_match.group(1)))
    if value is None:
        return None
    return {
        "offer_type": "financing_max_term",
        "price_text": f"{price_match.group(1)} €",
        "price_value": value,
        "price_unit": "EUR/month",
        "term_months": int(term_match.group(1)),
        "price_capture_kind": "visible_dom",
    }


async def _extract_mediamarkt_cash_offer(page: Page) -> dict | None:
    main_price_script = """
    () => {
      const selectors = [
        "[data-test='mms-product-price']",
        "[data-test='cofr-price mms-branded-price']",
        "[data-test='mms-product-price'] [data-test='mms-price']",
      ];
      for (const selector of selectors) {
        const node = document.querySelector(selector);
        const text = String(node?.textContent || '').replace(/\\s+/g, ' ').trim();
        if (text) return text;
      }
      return '';
    }
    """
    try:
        main_price_text = await page.evaluate(main_price_script)
    except Exception:
        main_price_text = ""

    main_values: list[float] = []
    for match in re.finditer(r"(\d{1,5}(?:[.,]\d{2})?)\s*(?:€|eur)", str(main_price_text), flags=re.IGNORECASE):
        value = parse_euro_to_float(match.group(1))
        if value is not None and 100 <= value <= 10000:
            main_values.append(value)
    if main_values:
        value = min(main_values)
        return {
            "offer_type": "cash",
            "price_text": f"{value:.2f} €",
            "price_value": value,
            "price_unit": "EUR",
            "term_months": None,
            "price_capture_kind": "visible_dom",
        }

    script = """
    () => {
      const out = [];
      const push = (raw, source) => {
        if (!raw) return;
        const text = String(raw).replace(/\\s+/g, ' ').trim();
        if (text) out.push({ text, source });
      };

      push(document.querySelector("meta[itemprop='price']")?.getAttribute("content"), "meta");

      const walk = (node) => {
        if (!node || typeof node !== "object") return;
        if (Array.isArray(node)) {
          for (const item of node) walk(item);
          return;
        }
        const type = String(node["@type"] || "").toLowerCase();
        if (type.includes("product")) {
          const offers = node.offers;
          if (Array.isArray(offers)) {
            for (const offer of offers) {
              if (offer?.price != null) push(offer.price, "jsonld");
            }
          } else if (offers && offers.price != null) {
            push(offers.price, "jsonld");
          }
        }
        for (const value of Object.values(node)) {
          if (value && typeof value === "object") walk(value);
        }
      };

      for (const el of document.querySelectorAll('script[type="application/ld+json"]')) {
        try {
          walk(JSON.parse(el.textContent || "null"));
        } catch (_) {}
      }

      const selectors = [
        "[data-test='mms-price'] .mms-ui-sr_true",
        "[data-test='mms-price']",
        "[data-test*='price'] .mms-ui-sr_true",
        "[data-test*='price']",
      ];
      for (const selector of selectors) {
        const nodes = Array.from(document.querySelectorAll(selector)).slice(0, 12);
        for (const node of nodes) {
          push(node.getAttribute?.("content") || node.textContent || "", "dom");
        }
      }
      return out;
    }
    """
    try:
        raw_candidates = await page.evaluate(script)
    except Exception:
        raw_candidates = []

    by_source: dict[str, list[float]] = {"dom": [], "jsonld": [], "meta": []}
    for item in raw_candidates or []:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("text") or "").strip()
        value = parse_euro_to_float(raw)
        if value is None and raw.replace(".", "", 1).isdigit():
            try:
                value = float(raw)
            except ValueError:
                value = None
        if value is None or value < 100 or value > 10000:
            continue
        source = str(item.get("source") or "dom")
        if source not in by_source:
            source = "dom"
        by_source[source].append(value)

    source = ""
    value = None
    for candidate_source in ("dom", "jsonld", "meta"):
        values = by_source.get(candidate_source) or []
        if not values:
            continue
        source = candidate_source
        value = min(values)
        break
    if value is None:
        return None

    return {
        "offer_type": "cash",
        "price_text": f"{value:.2f} €",
        "price_value": value,
        "price_unit": "EUR",
        "term_months": None,
        "price_capture_kind": "embedded_json_exact" if source in {"meta", "jsonld"} else "visible_dom",
    }


async def _extract_mediamarkt_financing_offers(page: Page, page_text: str = "") -> list[dict]:
    teaser_offer = _extract_mediamarkt_teaser_offer_from_text(page_text)
    if not teaser_offer:
        try:
            await page.wait_for_timeout(1200)
        except Exception:
            pass
        refreshed_text = await _extract_visible_text(page)
        teaser_offer = _extract_mediamarkt_teaser_offer_from_text(refreshed_text)
    modal_offers = await _extract_mediamarkt_installment_offers(page)
    if teaser_offer:
        teaser_matches_modal = any(
            offer.get("offer_type") == teaser_offer["offer_type"]
            and offer.get("term_months") == teaser_offer["term_months"]
            and abs(float(offer.get("price_value") or 0) - float(teaser_offer["price_value"])) <= 1.0
            for offer in modal_offers
        )
        if not teaser_matches_modal:
            return [teaser_offer]
        return _dedupe_offers([teaser_offer, *modal_offers])
    return _dedupe_offers(modal_offers)


async def _extract_grover_product_payload(page: Page) -> dict | None:
    script = """
    () => {
      const queries = window.__NEXT_DATA__?.props?.pageProps?.dehydratedState?.queries || [];
      const productQuery = queries.find((item) => {
        const d = item?.state?.data;
        return d && Array.isArray(d.rentalPlans) && d.sku;
      });
      const data = productQuery?.state?.data;
      if (!data) return null;

      const normalizePlan = (plan) => ({
        durationMonths: plan?.length?.value ?? null,
        durationUnit: plan?.length?.unit ?? null,
        priceInCents: plan?.price?.inCents ?? null,
        oldPriceInCents: plan?.oldPrice?.inCents ?? null,
        groverCarePrices: Array.isArray(plan?.groverCarePrices) ? plan.groverCarePrices : [],
      });

      return {
        name: data.name || null,
        slug: data.slug || null,
        available: typeof data.available === "boolean" ? data.available : null,
        marketPriceInCents: data?.marketPrice?.inCents ?? null,
        rentalPlans: Array.isArray(data.rentalPlans) ? data.rentalPlans.map(normalizePlan) : [],
        cheapestRentalPlan: data.cheapestRentalPlan ? normalizePlan(data.cheapestRentalPlan) : null,
      };
    }
    """
    try:
        payload = await page.evaluate(script)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _grover_monthly_text(value: float) -> str:
    return f"{value:.2f}".replace(".", ",") + " Ã¢â€šÂ¬/mes"


def _grover_cash_text(value: float) -> str:
    return f"{value:.2f}".replace(".", ",") + " Ã¢â€šÂ¬"


def _grover_candidate_matches_seed(seed: ProductSeed, text: str, href: str) -> bool:
    href_n = normalize_text(href)
    if "grover.com" not in href_n:
        return False
    if "/products/" not in href_n:
        return False

    raw = f"{text} {href}".lower()
    mix = normalize_text(f"{text} {href}")
    if _is_apple_seed(seed):
        if not any(token in mix for token in ("apple", "iphone", "ipad", "macbook", "imac", "mac mini", "mac studio")):
            return False
    elif "samsung" not in mix and "galaxy" not in mix:
        return False
    if any(token in mix for token in ACCESSORY_HINTS):
        return False
    if not _seed_device_matches_candidate(seed=seed, text=text, href=href):
        return False

    model_n = normalize_text(seed.model)
    if _is_apple_seed(seed):
        model_n = re.sub(r"\bapple\b|\biphone\b|\bipad\b|\bmacbook\b|\bimac\b|\bmac\b", " ", model_n)
    else:
        model_n = re.sub(r"\bsamsung\b|\bgalaxy\b", " ", model_n)
    model_n = re.sub(r"\s+", " ", model_n).strip()

    model_tokens = [tok for tok in re.split(r"[^a-z0-9]+", model_n) if tok and tok not in {"5g", "gb"}]
    if _is_apple_seed(seed):
        # Grover product cards often omit chip/connectivity tokens in visible title.
        model_tokens = [
            tok
            for tok in model_tokens
            if tok not in {"wifi", "cell", "cellular", "wificell", "wi", "fi"} and not re.fullmatch(r"m\d+", tok)
        ]
    strong_tokens = [
        tok
        for tok in model_tokens
        if len(tok) >= 4 or (any(ch.isdigit() for ch in tok) and not tok.isdigit())
    ]
    if strong_tokens and not all(tok in mix for tok in strong_tokens):
        return False

    if _is_apple_seed(seed):
        seed_norm = normalize_text(seed.model)
        iphone_num = re.search(r"\biphone\s*(\d{1,2})\b", seed_norm)
        if iphone_num and not re.search(rf"\biphone\s*{iphone_num.group(1)}\b", mix):
            return False
        apple_markers = ("pro", "max", "plus", "mini", "air")
        seed_markers = {m for m in apple_markers if re.search(rf"\b{m}\b", seed_norm)}
        cand_markers = {m for m in apple_markers if re.search(rf"\b{m}\b", mix)}
        if seed_markers and not seed_markers.issubset(cand_markers):
            return False
        if not seed_markers and cand_markers.intersection({"pro", "max", "plus", "mini", "air"}):
            return False
    else:
        markers = {"ultra", "plus", "fe", "flip", "fold"}
        seed_markers = {m for m in markers if m in model_tokens}
        cand_markers = {m for m in markers if m in mix}
        if re.search(r"\b(?:s|a|z)\d{1,3}\+", raw):
            cand_markers.add("plus")
        if seed_markers and not seed_markers.issubset(cand_markers):
            return False
        if not seed_markers and cand_markers:
            # Example: seed is S25 base; skip S25 Ultra/S25+ mismatches.
            return False

    if seed.capacity_gb:
        found_caps = {int(v) for v in re.findall(r"\b(64|128|256|512|1024)\s*gb\b", mix)}
        if found_caps and seed.capacity_gb not in found_caps:
            return False

    return True


def _movistar_candidate_matches_seed(seed: ProductSeed, text: str, href: str) -> bool:
    href_n = normalize_text(href)
    seed_type = _seed_device_type(seed)
    if seed_type == "mobile" and "/moviles/" not in href_n:
        return False
    if seed_type == "tablet" and "/tablet" not in href_n:
        return False
    if seed_type == "laptop" and not any(token in href_n for token in ("/portatil", "/ordenador", "/laptop")):
        return False
    if any(token in href_n for token in ("pack-ahorro", "watch", "smart-tv", "reacondicionado")):
        return False

    mix = normalize_text(f"{text} {href}")
    if _is_apple_seed(seed):
        if not any(token in mix for token in ("apple", "iphone", "ipad", "macbook", "imac", "mac mini", "mac studio")):
            return False
    elif "samsung" not in mix and "galaxy" not in mix:
        return False
    if not _seed_device_matches_candidate(seed=seed, text=text, href=href):
        return False

    model_n = normalize_text(seed.model)
    if _is_apple_seed(seed):
        model_n = re.sub(r"\bapple\b|\biphone\b|\bipad\b|\bmacbook\b|\bimac\b|\bmac\b", " ", model_n)
    else:
        model_n = re.sub(r"\bsamsung\b|\bgalaxy\b", " ", model_n)
    model_n = re.sub(r"\s+", " ", model_n).strip()
    model_tokens = [tok for tok in _alnum_tokens(model_n) if tok and tok not in {"5g", "gb"}]

    strong_tokens = [tok for tok in model_tokens if len(tok) >= 4 or any(ch.isdigit() for ch in tok)]
    if strong_tokens and not all(tok in mix for tok in strong_tokens):
        return False

    if _is_apple_seed(seed):
        seed_norm = normalize_text(seed.model)
        iphone_num = re.search(r"\biphone\s*(\d{1,2})\b", seed_norm)
        if iphone_num and not re.search(rf"\biphone\s*{iphone_num.group(1)}\b", mix):
            return False
        apple_markers = ("pro", "max", "plus", "mini", "air")
        seed_markers = {m for m in apple_markers if re.search(rf"\b{m}\b", seed_norm)}
        cand_markers = {m for m in apple_markers if re.search(rf"\b{m}\b", mix)}
        if seed_markers and not seed_markers.issubset(cand_markers):
            return False
        if not seed_markers and cand_markers.intersection({"pro", "max", "plus", "mini", "air"}):
            return False
    else:
        seed_markers = _collect_model_markers(" ".join(model_tokens), seed.model)
        cand_markers = _collect_model_markers(mix, f"{text} {href}")
        if seed_markers and not seed_markers.issubset(cand_markers):
            return False
        if not seed_markers and cand_markers:
            return False

    # Movistar often exposes the same model with a different storage variant than Santander.
    # Keep the model match and resolve actual capacity from the detail page.
    return True


def _mediamarkt_candidate_matches_seed(seed: ProductSeed, text: str, href: str) -> bool:
    href_n = normalize_text(href)
    if "/product/" not in href_n or "mediamarkt" not in href_n:
        return False

    mix = normalize_text(f"{text} {href}")
    seed_type = _seed_device_type(seed)
    if _is_apple_seed(seed):
        if not any(token in mix for token in ("apple", "iphone", "ipad", "macbook", "imac", "mac mini", "mac studio")):
            return False
    elif "samsung" not in mix and "galaxy" not in mix:
        return False
    if any(token in mix for token in ("reacondicionado", "reacondic", "seminuevo", "renovado", "usado", "segunda mano")):
        return False
    accessory_hits = {token for token in ACCESSORY_HINTS if token in mix}
    if seed_type == "laptop":
        accessory_hits.difference_update({"teclado", "keyboard"})
    if accessory_hits:
        return False
    if not _seed_device_matches_candidate(seed=seed, text=text, href=href):
        return False

    model_n = normalize_text(seed.model)
    if _is_apple_seed(seed):
        model_n = re.sub(r"\bapple\b|\biphone\b|\bipad\b|\bmacbook\b|\bimac\b|\bmac\b", " ", model_n)
    else:
        model_n = re.sub(r"\bsamsung\b|\bgalaxy\b", " ", model_n)
    model_n = re.sub(r"\s+", " ", model_n).strip()
    model_tokens = [tok for tok in _alnum_tokens(model_n) if tok and tok not in {"5g", "gb"}]
    if not _is_apple_seed(seed):
        model_tokens = [tok for tok in model_tokens if tok not in {"wifi", "wi", "fi", "lte", "cell", "cellular"}]

    strong_tokens = [tok for tok in model_tokens if len(tok) >= 4 or any(ch.isdigit() for ch in tok)]
    if strong_tokens and not all(tok in mix for tok in strong_tokens):
        return False

    if _is_apple_seed(seed):
        seed_norm = normalize_text(seed.model)
        iphone_num = re.search(r"\biphone\s*(\d{1,2})\b", seed_norm)
        if iphone_num and not re.search(rf"\biphone\s*{iphone_num.group(1)}\b", mix):
            return False
        apple_markers = ("pro", "max", "plus", "mini", "air")
        seed_markers = {m for m in apple_markers if re.search(rf"\b{m}\b", seed_norm)}
        cand_markers = {m for m in apple_markers if re.search(rf"\b{m}\b", mix)}
        if seed_markers and not seed_markers.issubset(cand_markers):
            return False
        if not seed_markers and cand_markers.intersection({"pro", "max", "plus", "mini", "air"}):
            return False
    else:
        if seed_type == "laptop":
            size_match = re.search(r"\b(1[4-7])\b", model_n)
            if size_match and not re.search(rf"(?<!\d){re.escape(size_match.group(1))}(?!\d)", mix):
                return False

        if seed_type == "tablet":
            seed_norm = normalize_text(seed.model)
            seed_has_wifi = bool(re.search(r"\bwi[\s\-]?fi\b", seed_norm))
            seed_has_cell = any(token in seed_norm for token in ("5g", "lte", "cell", "cellular"))
            cand_has_wifi = bool(re.search(r"\bwi[\s\-]?fi\b", mix))
            cand_has_cell = any(token in mix for token in ("5g", "lte", "cell", "cellular"))
            if seed_has_wifi and cand_has_cell:
                return False
            if seed_has_cell and cand_has_wifi and not cand_has_cell:
                return False
        if _seed_connectivity_conflicts(seed, mix):
            return False

        # Enforce exact model family (avoid S25 <-> S24/S26 cross-matches).
        family_match = re.search(r"\b([sa])\s*(\d{1,3})\b", model_n)
        if family_match:
            family_letter, family_num = family_match.group(1), family_match.group(2)
            if not re.search(rf"\b{family_letter}\s*{family_num}\b", mix):
                return False

        # Enforce exact Z family generations when applicable.
        flip_match = re.search(r"\bflip\s*(\d{1,2})\b", model_n)
        if flip_match and not re.search(rf"\bflip\s*{flip_match.group(1)}\b", mix):
            return False
        fold_match = re.search(r"\bfold\s*(\d{1,2})\b", model_n)
        if fold_match and not re.search(rf"\bfold\s*{fold_match.group(1)}\b", mix):
            return False

        seed_markers = _collect_model_markers(" ".join(model_tokens), seed.model)
        cand_markers = _collect_model_markers(mix, f"{text} {href}")
        if seed_type == "laptop" and "core ultra" in mix:
            cand_markers.discard("ultra")
        if seed_markers and not seed_markers.issubset(cand_markers):
            return False
        if not seed_markers and cand_markers:
            # Example: seed "S25" must not match "S25 Edge/Ultra/Plus/FE".
            return False

    # Keep storage flexible for Media Markt: exact variant can be resolved from the detail page.
    return True


def _movistar_relaxed_match(seed: ProductSeed, text: str, href: str, body_text: str = "") -> bool:
    """Fallback matcher for Movistar detail pages with noisy titles/descriptors.

    Keeps strict model-family checks while ignoring commercial suffixes
    (for example "Enterprise Edition") and storage differences.
    """
    if _is_apple_seed(seed):
        return _movistar_candidate_matches_seed(seed=seed, text=" ".join([text, body_text]), href=href)

    mix = normalize_text(" ".join(part for part in (text, href, body_text) if part))
    href_n = normalize_text(href)
    seed_type = _seed_device_type(seed)
    if seed_type == "mobile" and "/moviles/" not in href_n:
        return False
    if seed_type == "tablet" and "/tablet" not in href_n:
        return False
    if seed_type == "laptop" and not any(token in href_n for token in ("/portatil", "/ordenador", "/laptop")):
        return False
    if "samsung" not in mix and "galaxy" not in mix:
        return False
    if not _seed_device_matches_candidate(seed=seed, text=text, href=href):
        return False

    model_n = normalize_text(seed.model)
    family_match = re.search(r"\b([saz]\d{1,3})\b", model_n)
    if not family_match:
        return False
    if family_match.group(1) not in mix:
        return False

    seed_markers = _collect_model_markers(model_n, seed.model)
    cand_markers = _collect_model_markers(mix, f"{text} {href}")
    if seed_markers and not seed_markers.issubset(cand_markers):
        return False
    if not seed_markers and cand_markers:
        return False
    return True


def _rentik_candidate_matches_seed(seed: ProductSeed, text: str, href: str) -> bool:
    href_n = normalize_text(href)
    if "rentik.com" not in href_n:
        return False
    brand_n = normalize_text(seed.brand)
    if brand_n == "apple":
        expected_paths = ("/ofertas-alquilar/iphone/", "/ofertas-alquilar/apple/")
    else:
        expected_paths = ("/ofertas-alquilar/samsung/",)
    if not any(path in href_n for path in expected_paths):
        return False
    if href_n.rstrip("/").endswith("/apple") or href_n.rstrip("/").endswith("/samsung"):
        return False
    if any(token in href_n for token in ("watch", "reacondicionados", "gaming")):
        return False

    mix = normalize_text(f"{text} {href}")
    if _is_apple_seed(seed):
        if not any(token in mix for token in ("apple", "iphone", "ipad", "macbook", "imac", "mac mini", "mac studio")):
            return False
    elif "samsung" not in mix and "galaxy" not in mix:
        return False
    if any(token in mix for token in ACCESSORY_HINTS):
        return False
    if not _seed_device_matches_candidate(seed=seed, text=text, href=href):
        return False

    model_n = normalize_text(seed.model)
    if _is_apple_seed(seed):
        model_n = re.sub(r"\bapple\b|\biphone\b|\bipad\b|\bmacbook\b|\bimac\b|\bmac\b", " ", model_n)
    else:
        model_n = re.sub(r"\bsamsung\b|\bgalaxy\b", " ", model_n)
    model_n = re.sub(r"\s+", " ", model_n).strip()
    model_tokens = [tok for tok in _alnum_tokens(model_n) if tok and tok not in {"5g", "gb"}]
    if _is_apple_seed(seed):
        model_tokens = [
            tok
            for tok in model_tokens
            if tok not in {"wifi", "cell", "cellular", "wificell", "wi", "fi"} and not re.fullmatch(r"m\d+", tok)
        ]
    strong_tokens = [tok for tok in model_tokens if len(tok) >= 4 or any(ch.isdigit() for ch in tok)]
    if strong_tokens and not all(tok in mix for tok in strong_tokens):
        return False

    if _is_apple_seed(seed):
        seed_norm = normalize_text(seed.model)
        iphone_num = re.search(r"\biphone\s*(\d{1,2})\b", seed_norm)
        if iphone_num and not re.search(rf"\biphone\s*{iphone_num.group(1)}\b", mix):
            return False
        apple_markers = ("pro", "max", "plus", "mini", "air")
        seed_markers = {m for m in apple_markers if re.search(rf"\b{m}\b", seed_norm)}
        cand_markers = {m for m in apple_markers if re.search(rf"\b{m}\b", mix)}
        if seed_markers and not seed_markers.issubset(cand_markers):
            return False
        if not seed_markers and cand_markers.intersection({"pro", "max", "plus", "mini", "air"}):
            return False
    else:
        seed_markers = _collect_model_markers(" ".join(model_tokens), seed.model)
        cand_markers = _collect_model_markers(mix, f"{text} {href}")
        if seed_markers and not seed_markers.issubset(cand_markers):
            return False
        if not seed_markers and cand_markers:
            return False
    return True


async def _dismiss_rentik_cookie_banner(page: Page) -> None:
    names = [
        re.compile("rechazarlas todas", flags=re.IGNORECASE),
        re.compile("aceptar cookies", flags=re.IGNORECASE),
        re.compile("aceptar", flags=re.IGNORECASE),
    ]
    for name in names:
        loc = page.get_by_role("button", name=name)
        if await loc.count() <= 0:
            continue
        try:
            await loc.first.click(timeout=3000)
            await page.wait_for_timeout(500)
            return
        except Exception:
            continue


def _capacity_from_rentik_url(url: str) -> int | None:
    match = re.search(r"[?&]capacity=(\d{2,4})-gb\b", normalize_text(url))
    if match:
        return _normalize_phone_capacity(int(match.group(1)))
    path_match = re.search(r"\b(\d{2,4})\s*gb\b", normalize_text(url))
    if path_match:
        return _normalize_phone_capacity(int(path_match.group(1)))
    return None


async def _extract_rentik_selected_capacity(page: Page) -> int | None:
    script = """
    () => {
      const active = document.querySelector('.detail-tag.detail-tag--active, .capacity_badge.capacity_badge_active, [aria-selected=\"true\"]');
      if (!active) return null;
      const txt = (active.textContent || '').replace(/\\s+/g, ' ').trim();
      const m = txt.match(/(64|128|256|512|1024)\\s*GB/i);
      return m ? Number(m[1]) : null;
    }
    """
    try:
        value = await page.evaluate(script)
    except Exception:
        return None
    if isinstance(value, int):
        return _normalize_phone_capacity(value)
    return None


async def _extract_rentik_available_capacities(page: Page) -> set[int]:
    script = """
    () => {
      const text = (document.body?.innerText || '').replace(/\\s+/g, ' ');
      const lower = text.toLowerCase();
      const idx = lower.indexOf('capacidades');
      if (idx < 0) return [];
      const segment = text.slice(idx, idx + 260);
      const matches = Array.from(segment.matchAll(/\\b(64|128|256|512|1024)\\s*GB\\b/gi));
      return [...new Set(matches.map((m) => Number(m[1])))]
        .filter((n) => Number.isFinite(n));
    }
    """
    try:
        values = await page.evaluate(script)
    except Exception:
        return set()
    caps: set[int] = set()
    if isinstance(values, list):
        for value in values:
            if isinstance(value, int):
                normalized = _normalize_phone_capacity(value)
                if normalized:
                    caps.add(normalized)
    return caps


async def _select_rentik_capacity(page: Page, capacity_gb: int) -> bool:
    try:
        capacity = int(capacity_gb)
    except Exception:
        return False
    if capacity <= 0:
        return False

    try:
        chip = page.locator(".detail-tag").filter(has_text=re.compile(rf"\b{capacity}\s*GB\b", flags=re.IGNORECASE))
        if await chip.count() > 0:
            await chip.first.click(timeout=5000)
            await page.wait_for_timeout(1200)
            return True
    except Exception:
        pass

    try:
        locator = page.get_by_text(re.compile(rf"\b{capacity}\s*GB\b", flags=re.IGNORECASE))
        if await locator.count() > 0:
            await locator.first.click(timeout=5000)
            await page.wait_for_timeout(1200)
            return True
    except Exception:
        pass

    js = """
    (capacity) => {
      const want = `${capacity} gb`;
      const root = document.body;
      if (!root) return false;

      const nodes = Array.from(root.querySelectorAll('button, [role="button"], a, label, span, div, li'));
      const candidates = [];
      for (const node of nodes) {
        const txt = (node.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
        if (!txt) continue;
        if (!new RegExp(`(^|\\\\b)${capacity}\\\\s*gb(\\\\b|$)`, 'i').test(txt)) continue;
        const parentTxt = (node.parentElement?.textContent || '').toLowerCase();
        const scope = (node.closest('section, article, main, form, div')?.textContent || '').toLowerCase();
        const score = (parentTxt.includes('capacidades') ? 2 : 0) + (scope.includes('capacidades') ? 1 : 0);
        candidates.push({ node, score });
      }

      if (!candidates.length) return false;
      candidates.sort((a, b) => b.score - a.score);
      const target = candidates[0].node;
      target.scrollIntoView({ block: 'center', inline: 'center' });
      target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, composed: true }));
      return true;
    }
    """
    try:
        clicked = await page.evaluate(js, capacity)
    except Exception:
        return False
    if not clicked:
        return False
    await page.wait_for_timeout(1200)
    return True


def _extract_rentik_primary_monthly_offer(text: str) -> dict | None:
    plain = text.replace("\xa0", " ")
    plain_n = normalize_text(plain)

    segment = plain
    idx = plain_n.find(normalize_text("tu rentik desde"))
    if idx >= 0:
        segment = plain[idx : idx + 260]
    monthly = MONTHLY_VALUE_RE.search(segment) if idx >= 0 else None
    if not monthly:
        monthly = MONTHLY_VALUE_RE.search(plain)
    if monthly:
        raw = monthly.group(1)
        value = parse_euro_to_float(raw)
        if value is not None and value > 0:
            term = None
            for kw in ("renting", "meses"):
                pos = plain_n.find(normalize_text(kw))
                if pos >= 0:
                    term_match = TERM_RE.search(plain[max(0, pos - 80) : pos + 180])
                    if term_match:
                        try:
                            term = int(term_match.group(1))
                        except Exception:
                            term = None
                        break
            return {
                "offer_type": "renting_with_insurance",
                "price_text": f"{raw} \u20ac/mes",
                "price_value": value,
                "price_unit": "EUR/month",
                "term_months": term,
            }
    return None


def _extract_rentik_offers_from_text(text: str) -> list[dict]:
    offers: list[dict] = []
    plain = text.replace("\xa0", " ")

    monthly_offer = _extract_rentik_primary_monthly_offer(plain)
    if monthly_offer:
        offers.append(monthly_offer)

    no_insurance = find_price_after_keywords(plain, ("sin seguro",))
    if no_insurance:
        price_text, price_value = no_insurance
        offers.append(
            {
                "offer_type": "renting_no_insurance",
                "price_text": price_text,
                "price_value": price_value,
                "price_unit": "EUR/month",
                "term_months": None,
            }
        )

    return _dedupe_offers(offers)


def _rentik_candidate_url(url: str, brand: str) -> str | None:
    href = str(url or "").strip()
    if not href:
        return None
    href_n = normalize_text(href)
    if "rentik.com" not in href_n:
        return None
    brand_n = normalize_text(brand)
    if brand_n == "apple":
        expected_paths = ("/ofertas-alquilar/iphone/", "/ofertas-alquilar/apple/")
    else:
        expected_paths = ("/ofertas-alquilar/samsung/",)
    if not any(path in href_n for path in expected_paths):
        return None
    if href_n.rstrip("/").endswith("/apple") or href_n.rstrip("/").endswith("/samsung"):
        return None
    return href


def _score_rentik_candidates(seed: ProductSeed, candidates: list[dict], used_urls: set[str]) -> list[tuple[int, dict]]:
    scored: list[tuple[int, dict]] = []
    for item in candidates:
        href = _rentik_candidate_url(str(item.get("href", "")), brand=seed.brand)
        if not href or href in used_urls:
            continue
        text = " ".join([str(item.get("text", "")), str(item.get("card_text", ""))])
        if not _rentik_candidate_matches_seed(seed, text=text, href=href):
            continue

        score = _seed_match_score(seed, f"{text} {href}")
        if seed.capacity_gb:
            cap_from_url = _capacity_from_rentik_url(href)
            if cap_from_url:
                if cap_from_url == seed.capacity_gb:
                    score += 3
                else:
                    continue
        if score < 1:
            continue
        scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def _fnac_candidate_matches_seed(seed: ProductSeed, text: str, href: str) -> bool:
    href_n = normalize_text(href)
    if "fnac.es" not in href_n:
        return False
    if not re.search(r"/a\d+", href_n):
        return False
    if any(token in href_n for token in ("watch", "tablet", "tab-", "smart-tv", "reacondicionado", "fundas", "carcasa", "protector")):
        return False

    mix = normalize_text(f"{text} {href}")
    if "samsung" not in mix and "galaxy" not in mix:
        return False

    model_n = normalize_text(seed.model)
    model_n = re.sub(r"\bsamsung\b|\bgalaxy\b", " ", model_n)
    model_n = re.sub(r"\s+", " ", model_n).strip()
    model_tokens = [tok for tok in _alnum_tokens(model_n) if tok and tok not in {"5g", "gb"}]
    strong_tokens = [tok for tok in model_tokens if len(tok) >= 4 or any(ch.isdigit() for ch in tok)]
    if strong_tokens and not all(tok in mix for tok in strong_tokens):
        return False

    seed_markers = _collect_model_markers(" ".join(model_tokens), seed.model)
    cand_markers = _collect_model_markers(mix, f"{text} {href}")
    if seed_markers and not seed_markers.issubset(cand_markers):
        return False
    if not seed_markers and cand_markers:
        return False
    return True


async def _dismiss_fnac_cookie_banner(page: Page) -> None:
    names = [
        re.compile("rechazar", flags=re.IGNORECASE),
        re.compile("aceptar", flags=re.IGNORECASE),
        re.compile("consentir", flags=re.IGNORECASE),
    ]
    for name in names:
        loc = page.get_by_role("button", name=name)
        if await loc.count() <= 0:
            continue
        try:
            await loc.first.click(timeout=3000)
            await page.wait_for_timeout(500)
            return
        except Exception:
            continue


async def _extract_fnac_cash_from_dom(page: Page) -> dict | None:
    selectors = [
        "[data-test='price']",
        "[data-testid*='price']",
        ".f-productHeader-price",
        ".userPrice",
        ".price",
    ]
    for selector in selectors:
        try:
            values = await page.locator(selector).all_text_contents()
        except Exception:
            values = []
        for raw in values:
            found = _extract_first_euro_value(raw)
            if not found:
                continue
            price_text, price_value = found
            return {
                "offer_type": "cash",
                "price_text": price_text,
                "price_value": price_value,
                "price_unit": "EUR",
                "term_months": None,
            }
    return None


def _extract_fnac_offers_from_text(text: str) -> list[dict]:
    offers: list[dict] = []
    plain = text.replace("\xa0", " ")

    for regex in (FNAC_FIN_A_RE, FNAC_FIN_B_RE):
        match = regex.search(plain)
        if not match:
            continue
        if regex is FNAC_FIN_A_RE:
            term_raw, value_raw = match.group(1), match.group(2)
        else:
            value_raw, term_raw = match.group(1), match.group(2)
        value = parse_euro_to_float(value_raw)
        if value is None:
            continue
        try:
            term = int(term_raw)
        except Exception:
            term = None
        if value <= 0:
            continue
        offers.append(
            {
                "offer_type": "financing_max_term",
                "price_text": f"{value_raw} ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬/mes",
                "price_value": value,
                "price_unit": "EUR/month",
                "term_months": term,
            }
        )
        break

    cash = _extract_first_euro_value(plain[:2200]) or _extract_first_euro_value(plain)
    if cash:
        price_text, price_value = cash
        if price_value > 0:
            offers.append(
                {
                    "offer_type": "cash",
                    "price_text": price_text,
                    "price_value": price_value,
                    "price_unit": "EUR",
                    "term_months": None,
                }
            )

    return _dedupe_offers(offers)


async def _wait_fnac_manual_unblock(page: Page, timeout_ms: int = 60_000) -> bool:
    """Allow a manual CAPTCHA solve in headed mode before giving up."""
    elapsed = 0
    while elapsed < timeout_ms:
        await page.wait_for_timeout(2000)
        elapsed += 2000
        title = await page.title()
        text = await _extract_visible_text(page)
        if not _page_looks_blocked(title, text):
            return True
    return False


async def _wait_pccomponentes_manual_unblock(page: Page, timeout_ms: int = 60_000) -> bool:
    """Allow manual Cloudflare/challenge solve in headed mode before aborting PcComponentes."""
    elapsed = 0
    while elapsed < timeout_ms:
        await page.wait_for_timeout(2000)
        elapsed += 2000
        title = await page.title()
        text = await _extract_visible_text(page)
        if not _page_looks_blocked(title, text):
            return True
    return False


def _extract_grover_offers(payload: dict | None, page_text: str) -> list[dict]:
    offers: list[dict] = []
    plans = []
    if payload:
        plans = payload.get("rentalPlans") or []
        if not plans and payload.get("cheapestRentalPlan"):
            plans = [payload.get("cheapestRentalPlan")]

    for plan in plans:
        cents = plan.get("priceInCents")
        if cents is None:
            continue
        try:
            value = round(float(cents) / 100.0, 2)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        term = plan.get("durationMonths")
        term_months = term if isinstance(term, int) and term > 0 else None
        offers.append(
            {
                "offer_type": "renting_with_insurance",
                "price_text": _grover_monthly_text(value),
                "price_value": value,
                "price_unit": "EUR/month",
                "term_months": term_months,
            }
        )

    # Fallback when dynamic payload is unavailable: capture visible monthly rent.
    if not offers:
        monthly = _extract_monthly_offer(page_text)
        if monthly:
            monthly["offer_type"] = "renting_with_insurance"
            offers.append(monthly)

    plain = page_text.replace("\xa0", " ")
    fin_match = GROVER_FIN_RE.search(plain)
    if fin_match:
        term = int(fin_match.group(1))
        value = parse_euro_to_float(fin_match.group(2))
        if value is not None:
            offers.append(
                {
                    "offer_type": "financing_max_term",
                    "price_text": _grover_monthly_text(value),
                    "price_value": value,
                    "price_unit": "EUR/month",
                    "term_months": term,
                }
            )

    cash_match = GROVER_CASH_RE.search(plain)
    if cash_match:
        value = parse_euro_to_float(cash_match.group(1))
        if value is not None:
            offers.append(
                {
                    "offer_type": "cash",
                    "price_text": _grover_cash_text(value),
                    "price_value": value,
                    "price_unit": "EUR",
                    "term_months": None,
                }
            )

    # If Grover surfaces a "no insurance" rental explicitly, keep it as separate modality.
    no_insurance = find_price_after_keywords(plain, ("sin grover care", "sin seguro"))
    if no_insurance:
        price_text, price_value = no_insurance
        offers.append(
            {
                "offer_type": "renting_no_insurance",
                "price_text": price_text,
                "price_value": price_value,
                "price_unit": "EUR/month",
                "term_months": None,
            }
        )

    return _dedupe_offers(offers)


async def _dismiss_movistar_cookie_banner(page: Page) -> None:
    names = [
        re.compile("rechazar cookies opcionales", flags=re.IGNORECASE),
        re.compile("aceptar todas las cookies", flags=re.IGNORECASE),
        re.compile("aceptar cookies", flags=re.IGNORECASE),
    ]
    for name in names:
        loc = page.get_by_role("button", name=name)
        if await loc.count() <= 0:
            continue
        try:
            await loc.first.click(timeout=3000)
            await page.wait_for_timeout(500)
            return
        except Exception:
            continue


async def _dismiss_pccomponentes_cookie_banner(page: Page) -> None:
    names = [
        re.compile("rechazar cookies", flags=re.IGNORECASE),
        re.compile("aceptar todas", flags=re.IGNORECASE),
        re.compile("rechazar", flags=re.IGNORECASE),
        re.compile("aceptar", flags=re.IGNORECASE),
    ]
    for name in names:
        loc = page.get_by_role("button", name=name)
        if await loc.count() <= 0:
            continue
        try:
            await loc.first.click(timeout=3000)
            await page.wait_for_timeout(500)
            return
        except Exception:
            continue


async def _dismiss_samsung_cookie_banner(page: Page) -> None:
    selectors = [
        "button#truste-consent-button",
        "button:has-text('Aceptar todo')",
        "button:has-text('Aceptar todas')",
        "button:has-text('Aceptar')",
        "button:has-text('Allow all')",
        "button:has-text('Accept all')",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count():
                await locator.click(timeout=2000)
                await page.wait_for_timeout(300)
                return
        except Exception:
            continue


async def _wait_pccomponentes_results(page: Page) -> None:
    for _ in range(10):
        try:
            h1 = await page.locator("h1").first.inner_text(timeout=1200)
        except Exception:
            h1 = ""
        if "resultados para" in normalize_text(h1):
            return
        try:
            count = await page.locator("a[href*='pccomponentes.com/']").count()
        except Exception:
            count = 0
        if count > 120:
            return
        await page.wait_for_timeout(900)


def _parse_euro_loose(raw: str) -> float | None:
    s = str(raw or "").strip().replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        if not re.fullmatch(r"\d+(?:\.\d{1,2})?", s):
            s = s.replace(".", "")
    try:
        return float(s)
    except Exception:
        return None


def _pccomponentes_candidate_matches_seed(seed: ProductSeed, text: str, href: str) -> bool:
    href_raw = str(href or "").strip()
    if not href_raw:
        return False
    href_n = normalize_text(href_raw)
    if "pccomponentes.com" not in href_n:
        return False

    parsed = urlparse(href_raw)
    path = normalize_text(parsed.path or "")
    if not path or path == "/":
        return False
    if parsed.query and "offer=" in normalize_text(parsed.query):
        return False
    if any(
        token in path
        for token in (
            "/search",
            "/buscar",
            "/smartphone-moviles",
            "/smartphone-y-tablets",
            "/tablets",
            "/televisores",
            "/smartwatch",
            "/pulseras",
            "/auriculares",
            "/galaxy-unpacked",
        )
    ):
        return False

    path_chunks = [chunk for chunk in path.split("/") if chunk]
    if len(path_chunks) != 1:
        return False

    mix = normalize_text(f"{text} {href_raw}")
    if "samsung" not in mix and "galaxy" not in mix:
        return False
    if any(token in mix for token in ("reacondicionado", "funda", "carcasa", "protector", "cargador", "auriculares")):
        return False

    model_n = normalize_text(seed.model)
    model_n = re.sub(r"\bsamsung\b|\bgalaxy\b", " ", model_n)
    model_n = re.sub(r"\s+", " ", model_n).strip()
    model_tokens = [tok for tok in _alnum_tokens(model_n) if tok and tok not in {"5g", "gb"}]
    strong_tokens = [tok for tok in model_tokens if len(tok) >= 4 or any(ch.isdigit() for ch in tok)]
    if strong_tokens and not all(tok in mix for tok in strong_tokens):
        return False
    return True


async def _extract_pccomponentes_cash_offer(page: Page, page_text: str) -> dict | None:
    selectors = [
        "#pdp-price-current-container",
        "#pdp-price-current-container-sticky",
        "[id^='pdp-price-current-container']",
    ]
    for selector in selectors:
        try:
            values = await page.locator(selector).all_text_contents()
        except Exception:
            values = []
        for raw in values:
            found = _extract_first_euro_value(raw)
            if not found:
                continue
            price_text, price_value = found
            return {
                "offer_type": "cash",
                "price_text": price_text,
                "price_value": price_value,
                "price_unit": "EUR",
                "term_months": None,
            }

    cash = _extract_first_euro_value(page_text)
    if not cash:
        return None
    price_text, price_value = cash
    return {
        "offer_type": "cash",
        "price_text": price_text,
        "price_value": price_value,
        "price_unit": "EUR",
        "term_months": None,
    }


def _extract_pccomponentes_financing_from_text(text: str) -> dict | None:
    plain = text.replace("\xa0", " ")
    patterns = [
        re.compile(
            r"(\d{1,4}(?:[.,]\d{1,2})?)\s*€\s*hoy\s*y\s*(\d{1,4}(?:[.,]\d{1,2})?)\s*€\s*/\s*mes\s*en\s*(\d{1,2})\s*plazos",
            flags=re.IGNORECASE,
        ),
        re.compile(
            r"(\d{1,4}(?:[.,]\d{1,2})?)\s*€\s*/\s*mes\s*en\s*(\d{1,2})\s*plazos",
            flags=re.IGNORECASE,
        ),
        re.compile(r"financiado\s+desde\s+(\d{1,4}(?:[.,]\d{1,2})?)\s*€\s*/\s*mes", flags=re.IGNORECASE),
    ]

    for idx, regex in enumerate(patterns):
        match = regex.search(plain)
        if not match:
            continue
        if idx == 0:
            raw_value, raw_term = match.group(2), match.group(3)
        elif idx == 1:
            raw_value, raw_term = match.group(1), match.group(2)
        else:
            raw_value, raw_term = match.group(1), None
        value = _parse_euro_loose(raw_value)
        if value is None:
            continue
        term = None
        if raw_term:
            try:
                term = int(raw_term)
            except Exception:
                term = None
        return {
            "offer_type": "financing_max_term",
            "price_text": f"{raw_value} €/mes",
            "price_value": value,
            "price_unit": "EUR/month",
            "term_months": term,
        }
    return None


async def _extract_pccomponentes_financing_offer(page: Page, page_text: str) -> dict | None:
    button = page.locator("#financing-item")
    button_text = ""
    try:
        if await button.count() > 0:
            button_text = (await button.first.inner_text(timeout=3000)) or ""
            if await button.first.is_enabled():
                try:
                    await button.first.click(timeout=5000)
                    await page.wait_for_timeout(800)
                except Exception:
                    pass
    except Exception:
        button_text = ""

    full_text = page_text
    try:
        full_text = await _extract_visible_text(page)
    except Exception:
        pass

    return _extract_pccomponentes_financing_from_text(" ".join([button_text, full_text]))


def _extract_movistar_offers_from_text(text: str) -> list[dict]:
    offers: list[dict] = []
    plain = text.replace("\xa0", " ")
    plain_n = normalize_text(plain)

    # Financing in Movistar pack format.
    for kw in ("anadelo a tu pack", "con tu pack desde"):
        idx = plain_n.find(normalize_text(kw))
        if idx < 0:
            continue
        segment = plain[idx : idx + 420]
        monthly = MOVISTAR_MONTHLY_RE.search(segment)
        if not monthly:
            continue
        value = parse_euro_to_float(monthly.group(1))
        if value is None:
            continue
        if value <= 0:
            continue
        term = None
        term_match = MOVISTAR_TERM_X_RE.search(segment) or TERM_RE.search(segment)
        if term_match:
            try:
                term = int(term_match.group(1))
            except Exception:
                term = None
        offers.append(
            {
                "offer_type": "financing_max_term",
                "price_text": f"{monthly.group(1)} Ã¢â€šÂ¬/mes",
                "price_value": value,
                "price_unit": "EUR/month",
                "term_months": term,
            }
        )
        break

    # Cash offer in "Compra libre" block: prefer the final (discounted) one-time price.
    # Some pages mix monthly amounts inside this block, so we explicitly discard "/mes" values.
    for kw in ("compralo libre", "compra libre", "libre"):
        idx = plain_n.find(normalize_text(kw))
        if idx < 0:
            continue
        segment = plain[idx : idx + 520]
        end = len(segment)
        for stopper in (
            re.compile(r"\bcomprar\b", flags=re.IGNORECASE),
            re.compile(r"\beres cliente\b", flags=re.IGNORECASE),
            re.compile(r"caracter[iÃ­]sticas principales", flags=re.IGNORECASE),
        ):
            m = stopper.search(segment)
            if m:
                end = min(end, m.start())
        clipped = segment[:end]

        matches = list(EURO_VALUE_RE.finditer(clipped))
        if not matches:
            continue
        non_monthly: list[re.Match] = []
        for match in matches:
            after = clipped[match.end() : match.end() + 18]
            before = clipped[max(0, match.start() - 16) : match.start()]
            context = normalize_text(" ".join([before, after]))
            if re.search(r"(?:/|por)?\s*mes(?:es)?\b|\bx\s*\d{1,2}\s*mes(?:es)?\b", context):
                continue
            non_monthly.append(match)
        if not non_monthly:
            continue

        chosen = non_monthly[-1]
        raw = chosen.group(1)
        value = parse_euro_to_float(raw)
        if value is None:
            continue

        # Guardrail: if last non-monthly token is still tiny (e.g. leaked installment),
        # prefer the latest realistic full-price candidate in the same block.
        if value < 100:
            realistic = []
            for match in non_monthly:
                v = parse_euro_to_float(match.group(1))
                if v is not None and v >= 100:
                    realistic.append((match, v))
            if realistic:
                chosen, value = realistic[-1]
                raw = chosen.group(1)
        offers.append(
            {
                "offer_type": "cash",
                "price_text": f"{raw} Ã¢â€šÂ¬",
                "price_value": value,
                "price_unit": "EUR",
                "term_months": None,
            }
        )
        break

    return _dedupe_offers(offers)


async def _extract_grover_collection_candidates(page: Page, brand: str) -> list[dict]:
    brand_n = normalize_text(brand)
    if brand_n == "apple":
        collection_url = "https://www.grover.com/es-es/collection/apple"
    else:
        collection_url = "https://www.grover.com/es-es/collection/samsung-galaxy"
    if not await _safe_goto(page, collection_url):
        return []

    load_more = page.get_by_role("button", name=re.compile(r"cargar siguiente", flags=re.IGNORECASE))
    for _ in range(3):
        if await load_more.count() <= 0:
            break
        try:
            await load_more.first.click(timeout=3000)
            await page.wait_for_timeout(1200)
        except Exception:
            break

    script = """
    () => {
      const out = [];
      const anchors = Array.from(document.querySelectorAll('main a[href*=\"/products/\"]'));
      for (const a of anchors) {
        const href = a.href || '';
        const text = (a.textContent || '').replace(/\\s+/g, ' ').trim();
        if (!href || !text) continue;
        out.push({ href, text, card_text: text });
      }
      return out;
    }
    """
    try:
        raw = await page.evaluate(script)
    except Exception:
        return []

    deduped: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        href = str(item.get("href", ""))
        if href in seen:
            continue
        seen.add(href)
        deduped.append(item)
    return deduped


async def _dismiss_mediamarkt_consent(page: Page) -> None:
    for selector in ('[data-test="pwa-consent-layer-accept-all"]', '[data-test="pwa-consent-layer-reject-all"]'):
        loc = page.locator(selector)
        if await loc.count() <= 0:
            continue
        try:
            await loc.first.click(timeout=3_000)
            await page.wait_for_timeout(700)
            return
        except Exception:
            continue

    names = [
        re.compile("aceptar", flags=re.IGNORECASE),
        re.compile("allow", flags=re.IGNORECASE),
        re.compile("permitir", flags=re.IGNORECASE),
        re.compile("guardar", flags=re.IGNORECASE),
        re.compile("rechazar", flags=re.IGNORECASE),
        re.compile("denegar", flags=re.IGNORECASE),
    ]
    for name in names:
        for loc in (
            page.locator("#mms-consent-portal-container").get_by_role("button", name=name),
            page.get_by_role("button", name=name),
        ):
            if await loc.count() <= 0:
                continue
            try:
                await loc.first.click(timeout=3_000)
                await page.wait_for_timeout(700)
                return
            except Exception:
                continue

    # Fallback non-destructive: hide overlay if still present.
    try:
        await page.evaluate(
            "() => { const n=document.querySelector('#mms-consent-portal-container'); if(n){ n.style.display='none'; } }"
        )
    except Exception:
        pass


def _offers_from_mediamarkt_installment_payload(payload: dict) -> list[dict]:
    offers: list[dict] = []
    data = payload.get("data") if isinstance(payload, dict) else None
    calculations = data.get("installmentCalculations") if isinstance(data, dict) else None
    installments = calculations.get("installments") if isinstance(calculations, dict) else None
    if not isinstance(installments, list):
        return offers

    for row in installments:
        if not isinstance(row, dict):
            continue
        duration = row.get("duration")
        monthly = row.get("monthlyRate")
        if not isinstance(duration, int) or duration <= 0:
            continue
        if monthly is None:
            continue
        try:
            value = float(monthly)
        except (TypeError, ValueError):
            continue
        offers.append(
            {
                "offer_type": "financing_max_term",
                "price_text": f"{value:.2f} â‚¬/mes",
                "price_value": value,
                "price_unit": "EUR/month",
                "term_months": duration,
                "price_capture_kind": "api_exact",
            }
        )
    return _dedupe_offers(offers)


async def _extract_mediamarkt_installment_offers(page: Page) -> list[dict]:
    await _dismiss_mediamarkt_consent(page)
    button = page.get_by_role("button", name=MEDIAMARKT_SIM_BUTTON_RE)
    if await button.count() <= 0:
        return []

    try:
        await button.first.click(force=True, timeout=8_000)
        await page.wait_for_timeout(500)
    except Exception:
        return []

    dialog = page.locator('[data-test="mms-financing-calculator"]')
    if await dialog.count() <= 0:
        dialog = page.get_by_role("dialog", name=re.compile("simula tu financi", flags=re.IGNORECASE))
    if await dialog.count() <= 0:
        return []

    async def _current_offer() -> dict | None:
        try:
            dialog_text = (await dialog.first.inner_text()).replace("\xa0", " ")
        except Exception:
            return None
        try:
            combo_text = (await dialog.get_by_role("combobox").first.inner_text()).replace("\xa0", " ")
        except Exception:
            combo_text = dialog_text
        term_match = re.search(r"\b(\d{1,2})\b", combo_text)
        monthly_match = re.search(
            r"cuotas?\s+de\s+(\d{1,5}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s*(?:€|eur)",
            dialog_text,
            flags=re.IGNORECASE,
        )
        monthly = _extract_first_euro_value(monthly_match.group(0)) if monthly_match else None
        if not term_match or not monthly:
            return None
        price_text, price_value = monthly
        return {
            "offer_type": "financing_max_term",
            "price_text": price_text,
            "price_value": price_value,
            "price_unit": "EUR/month",
            "term_months": int(term_match.group(1)),
            "price_capture_kind": "visible_dom",
        }

    offers: list[dict] = []
    current = await _current_offer()
    if current:
        offers.append(current)

    combobox = dialog.get_by_role("combobox")
    if await combobox.count() > 0:
        try:
            await combobox.first.click(timeout=3_000)
            await page.wait_for_timeout(250)
            options = dialog.get_by_role("option")
            option_labels: list[str] = []
            for idx in range(await options.count()):
                label = re.sub(r"\s+", " ", (await options.nth(idx).inner_text()) or "").strip()
                if label and label not in option_labels:
                    option_labels.append(label)
            for idx, label in enumerate(option_labels):
                opt = dialog.get_by_role("option", name=re.compile(rf"^{re.escape(label)}$", flags=re.IGNORECASE))
                if await opt.count() <= 0:
                    continue
                await opt.first.click(timeout=3_000)
                await page.wait_for_timeout(250)
                current = await _current_offer()
                if current:
                    offers.append(current)
                if idx < len(option_labels) - 1 and await combobox.count() > 0:
                    await combobox.first.click(timeout=3_000)
                    await page.wait_for_timeout(150)
        except Exception:
            pass

    close_button = dialog.get_by_role("button", name=re.compile("cerrar", flags=re.IGNORECASE))
    if await close_button.count() > 0:
        try:
            await close_button.first.click(timeout=2_000)
            await page.wait_for_timeout(150)
        except Exception:
            pass
    return _dedupe_offers(offers)


async def _extract_amazon_offers(page: Page, page_text: str) -> list[dict]:
    offers: list[dict] = []
    price_selectors = [
        "#corePrice_feature_div .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-offscreen",
        ".a-price .a-offscreen",
    ]
    for selector in price_selectors:
        try:
            values = await page.locator(selector).all_text_contents()
        except Exception:
            values = []
        for raw in values:
            found = _extract_first_euro_value(raw)
            if not found:
                continue
            price_text, price_value = found
            offers.append(
                {
                    "offer_type": "cash",
                    "price_text": price_text,
                    "price_value": price_value,
                    "price_unit": "EUR",
                    "term_months": None,
                }
            )
            break
        if offers:
            break

    if not offers:
        offers.extend(_offers_from_snippet(page_text))

    financing = _extract_monthly_offer(page_text)
    if financing:
        offers.append(financing)
    return _dedupe_offers(offers)


async def _scrape_amazon_prices(browser: Browser, seeds: list[ProductSeed]) -> list[PriceRecord]:
    records: list[PriceRecord] = []
    context = await _new_context(browser)
    page = await context.new_page()
    template = SEARCH_URL_TEMPLATES["Amazon"]
    used_urls_by_type: dict[str, set[str]] = {"mobile": set(), "tablet": set(), "laptop": set()}

    for seed in seeds:
        seed_type = _seed_device_type(seed)
        used_urls = used_urls_by_type.setdefault(seed_type, set())
        ranked_by_url: dict[str, tuple[int, dict, str | None]] = {}
        fallback_by_url: dict[str, tuple[int, dict, str | None]] = {}
        exploratory_by_url: dict[str, tuple[int, dict, str | None]] = {}
        for query in _seed_search_queries(seed):
            search_url = template.format(query=quote_plus(query))
            if not await _safe_goto(page, search_url):
                continue
            search_title = await page.title()
            search_text = await _extract_visible_text(page)
            if _page_looks_blocked(search_title, search_text):
                continue

            candidates = await _extract_amazon_result_candidates(page)
            if not candidates:
                raw_candidates = await _extract_search_candidates(page)
                candidates = []
                seen_asin: set[str] = set()
                for item in raw_candidates:
                    asin = _amazon_asin_from_url(str(item.get("href", "")))
                    if not asin or asin in seen_asin:
                        continue
                    seen_asin.add(asin)
                    candidates.append(
                        {
                            "href": f"https://www.amazon.es/dp/{asin}",
                            "text": str(item.get("text", "")),
                            "card_text": str(item.get("card_text", "")),
                        }
                    )
            candidates = [
                c
                for c in candidates
                if not _amazon_looks_refurbished(
                    " ".join(
                        [
                            str(c.get("text", "")),
                            str(c.get("card_text", "")),
                            str(c.get("href", "")),
                        ]
                    )
                )
            ]
            for item in candidates:
                href = str(item.get("href", ""))
                canonical = _canonical_amazon_url(href)
                if canonical in used_urls:
                    continue
                mix = " ".join([str(item.get("text", "")), str(item.get("card_text", "")), href])
                score = _seed_match_score(seed, mix)
                strict_match = _amazon_candidate_matches_seed(
                    seed,
                    text=" ".join([str(item.get("text", "")), str(item.get("card_text", ""))]),
                    href=href,
                    title_text=" ".join([str(item.get("text", "")), str(item.get("card_text", ""))]),
                )
                if strict_match:
                    if score <= 0:
                        continue
                    cur = fallback_by_url.get(canonical)
                    if not cur or score > cur[0]:
                        fallback_by_url[canonical] = (score, item, search_title)
                    cur2 = ranked_by_url.get(canonical)
                    if not cur2 or score > cur2[0]:
                        ranked_by_url[canonical] = (score, item, search_title)
                    continue

                if seed_type != "laptop":
                    continue
                mix_n = normalize_text(mix)
                if not _brand_presence_in_text(seed, mix_n) or not _has_laptop_hint(mix_n):
                    continue
                if any(token in mix_n for token in ACCESSORY_HINTS):
                    continue
                exploratory_score = max(score, 1)
                cur = exploratory_by_url.get(canonical)
                if not cur or exploratory_score > cur[0]:
                    exploratory_by_url[canonical] = (exploratory_score, item, search_title)

        ranked = sorted(ranked_by_url.values(), key=lambda x: x[0], reverse=True)
        if not ranked:
            ranked = sorted(fallback_by_url.values(), key=lambda x: x[0], reverse=True)
        if not ranked and seed_type == "laptop":
            ranked = sorted(exploratory_by_url.values(), key=lambda x: x[0], reverse=True)
        if not ranked:
            continue
        chosen: tuple[str, str | None, str, list[dict], int | None, bool | None, str] | None = None
        variant_fallback: tuple[str, str | None, str, list[dict], int | None, bool | None, str] | None = None
        candidate_limit = 20 if seed_type == "laptop" else 12
        for _, item, item_search_title in ranked[:candidate_limit]:
            product_url = _canonical_amazon_url(str(item.get("href", "")))
            if product_url in used_urls:
                continue
            snippet = " ".join([str(item.get("text", "")), str(item.get("card_text", ""))])
            snippet_is_strict_match = _amazon_candidate_matches_seed(
                seed,
                text=snippet,
                href=product_url,
                title_text=snippet,
            )
            snippet_is_loose_match = _amazon_candidate_matches_seed(
                seed,
                text=snippet,
                href=product_url,
                enforce_capacity=False,
                title_text=snippet,
            )

            title: str | None = None
            body_text = ""
            offers: list[dict] = []
            if await _safe_goto(page, product_url):
                title = await page.title()
                body_text = await _extract_visible_text(page)
                if (
                    not _page_looks_blocked(title, body_text)
                    and not _amazon_looks_refurbished(" ".join([title, body_text[:2500]]))
                    and _amazon_candidate_matches_seed(
                        seed,
                        text=" ".join([title, body_text[:2200]]),
                        href=product_url,
                        enforce_capacity=False,
                        title_text=title,
                    )
                ):
                    offers = await _extract_amazon_offers(page, body_text)
            if not offers:
                if snippet_is_strict_match:
                    offers = _offers_from_snippet(snippet)
                elif seed_type == "laptop" and snippet_is_loose_match:
                    offers = _offers_from_snippet(snippet)
            if not offers:
                continue

            if seed_type == "laptop":
                title_capacity = _detect_capacity_for_device(str(title or ""), seed_type)
                snippet_capacity = _detect_capacity_for_device(snippet, seed_type)
                body_capacity = _detect_capacity_for_device(body_text[:2500], seed_type)
                detected_capacity = title_capacity or snippet_capacity or body_capacity
                capacity = detected_capacity or seed.capacity_gb
            else:
                detected_capacity = _detect_capacity_for_device(
                    " ".join([str(title or ""), body_text[:2500], snippet]),
                    seed_type,
                )
                capacity = detected_capacity or seed.capacity_gb
                if seed.capacity_gb:
                    observed_caps = _extract_capacity_values(" ".join([str(title or ""), body_text[:2500], snippet]))
                    if _is_apple_seed(seed) and seed_type in {"mobile", "tablet"}:
                        # Apple phone/tablet variants should expose storage in listing/detail.
                        if seed.capacity_gb not in observed_caps:
                            continue
                        capacity = seed.capacity_gb
                    elif observed_caps and seed.capacity_gb not in observed_caps:
                        continue
                    elif observed_caps:
                        capacity = seed.capacity_gb
            in_stock = detect_stock_state(body_text)
            source_title = title or item_search_title
            if seed.capacity_gb and capacity and capacity != seed.capacity_gb:
                if seed_type == "laptop" and variant_fallback is None:
                    variant_fallback = (
                        product_url,
                        source_title,
                        body_text,
                        offers,
                        capacity,
                        in_stock,
                        "amazon_adapter_variant_live",
                    )
                continue

            chosen = (
                product_url,
                source_title,
                body_text,
                offers,
                capacity,
                in_stock,
                "amazon_adapter_live",
            )
            break

        if chosen is None and variant_fallback is not None:
            chosen = variant_fallback
        if chosen is None:
            continue

        product_url, source_title, body_text, offers, capacity, in_stock, tier = chosen
        used_urls.add(product_url)
        for offer in offers:
            records.append(
                _record_from_offer(
                    competitor="Amazon",
                    seed=seed,
                    source_url=product_url,
                    source_title=source_title,
                    in_stock=in_stock,
                    capacity=capacity,
                    offer=offer,
                    quality_tier=tier,
                )
            )
        await asyncio.sleep(0.6)

    await context.close()
    return records


async def _scrape_mediamarkt_prices(browser: Browser, seeds: list[ProductSeed]) -> list[PriceRecord]:
    records: list[PriceRecord] = []
    context = await _new_context(browser)
    page = await context.new_page()
    template = SEARCH_URL_TEMPLATES["Media Markt"]

    for seed in seeds:
        ranked: list[tuple[int, dict]] = []
        for query in _seed_search_queries(seed):
            search_url = template.format(query=quote_plus(query))
            if not await _safe_goto(page, search_url):
                continue
            title = await _safe_page_title(page)
            body_text = await _extract_visible_text(page)
            if _page_looks_blocked(title, body_text):
                continue

            candidates = await _extract_search_candidates(page)
            filtered_candidates = [
                c
                for c in candidates
                if _mediamarkt_candidate_matches_seed(
                    seed,
                    text=_mediamarkt_candidate_text(c),
                    href=str(c.get("href", "")),
                )
            ]
            if not filtered_candidates:
                filtered_candidates = []
                for c in candidates:
                    href = str(c.get("href", "")).strip()
                    candidate_text = _mediamarkt_candidate_text(c)
                    mix = normalize_text(f"{candidate_text} {href}")
                    if "/product/" not in normalize_text(href) or "mediamarkt" not in normalize_text(href):
                        continue
                    if any(token in mix for token in ("reacondicionado", "reacondic", "seminuevo", "renovado", "usado", "segunda mano")):
                        continue
                    if not _seed_device_matches_candidate(seed=seed, text=candidate_text, href=href):
                        continue
                    if _seed_connectivity_conflicts(seed, mix):
                        continue
                    if _seed_match_score(seed, f"{candidate_text} {href}") <= 0:
                        continue
                    filtered_candidates.append(c)
            # Deduplicate by URL because Media Markt search DOM often repeats anchors.
            deduped_by_href: dict[str, dict] = {}
            for c in filtered_candidates:
                href = str(c.get("href", "")).strip()
                if not href:
                    continue
                current = deduped_by_href.get(href)
                if current is None or _mediamarkt_candidate_priority(c) > _mediamarkt_candidate_priority(current):
                    deduped_by_href[href] = c
            for item in deduped_by_href.values():
                mix = " ".join([_mediamarkt_candidate_text(item), str(item.get("href", ""))])
                score = _seed_match_score(seed, mix)
                if score > 0:
                    ranked.append((score, item))
            if ranked:
                break
        ranked.sort(key=lambda x: x[0], reverse=True)
        if not ranked:
            continue

        tried_urls: set[str] = set()
        chosen_url: str | None = None
        chosen_title: str | None = None
        chosen_text = ""
        chosen_offers: list[dict] = []
        fallback_cash_only: tuple[str, str, str, list[dict]] | None = None

        # Try top candidates and prefer the one that yields financing plans.
        for _, candidate in ranked[:8]:
            detail_url = str(candidate.get("href", search_url))
            if not detail_url:
                continue
            if detail_url in tried_urls:
                continue
            tried_urls.add(detail_url)
            if not await _safe_goto(page, detail_url):
                continue

            detail_title = await _safe_page_title(page)
            detail_text = await _extract_visible_text(page)
            if _page_looks_blocked(detail_title, detail_text):
                continue
            if _amazon_looks_refurbished(" ".join([detail_title, detail_url])):
                continue
            if not _mediamarkt_candidate_matches_seed(
                seed,
                # Validate with title+URL (avoid noise from recommendation widgets).
                text=detail_title,
                href=detail_url,
            ):
                continue

            offers = []
            cash_offer = await _extract_mediamarkt_cash_offer(page)
            if cash_offer:
                offers.append(cash_offer)
            offers.extend(await _extract_mediamarkt_financing_offers(page, detail_text))
            if not offers:
                offers = _extract_mediamarkt_offers_from_text(detail_text)
            offers = _dedupe_offers(offers)
            if not offers:
                continue

            has_financing = any(o.get("offer_type") == "financing_max_term" for o in offers)
            if has_financing:
                chosen_url = detail_url
                chosen_title = detail_title
                chosen_text = detail_text
                chosen_offers = offers
                break

            if fallback_cash_only is None:
                fallback_cash_only = (detail_url, detail_title, detail_text, offers)

        if not chosen_offers and fallback_cash_only is not None:
            chosen_url, chosen_title, chosen_text, chosen_offers = fallback_cash_only
        if not chosen_offers or not chosen_url:
            continue
        if _seed_connectivity_conflicts(seed, " ".join([str(chosen_title or ""), chosen_url])):
            continue

        source_text = chosen_text
        seed_type = _seed_device_type(seed)
        detected_capacity = _detect_capacity_for_device(" ".join([str(chosen_title or ""), source_text[:3000], chosen_url]), seed_type)
        capacity = detected_capacity or seed.capacity_gb
        if seed.capacity_gb and _is_apple_seed(seed):
            # Use explicit title/URL capacity hints first; body often lists all variants.
            explicit_caps = _extract_capacity_values(" ".join([str(chosen_title or ""), chosen_url]))
            if explicit_caps and seed.capacity_gb not in explicit_caps:
                continue
            if explicit_caps:
                capacity = seed.capacity_gb
            elif detected_capacity and detected_capacity != seed.capacity_gb:
                continue
            else:
                capacity = seed.capacity_gb
        elif seed.capacity_gb:
            explicit_caps = _extract_capacity_values(" ".join([str(chosen_title or ""), chosen_url]))
            if explicit_caps and seed.capacity_gb not in explicit_caps:
                continue
            if explicit_caps:
                capacity = seed.capacity_gb
            elif detected_capacity and detected_capacity != seed.capacity_gb:
                continue
            else:
                capacity = seed.capacity_gb
        in_stock = detect_stock_state(source_text)
        records.extend(
            _record_from_offer(
                competitor="Media Markt",
                seed=seed,
                source_url=chosen_url,
                source_title=chosen_title,
                in_stock=in_stock,
                capacity=capacity,
                offer=offer,
                quality_tier="mediamarkt_adapter_live",
            )
            for offer in chosen_offers
        )
        await asyncio.sleep(0.5)

    await context.close()
    return records


async def _scrape_pccomponentes_prices(browser: Browser, seeds: list[ProductSeed]) -> list[PriceRecord]:
    records: list[PriceRecord] = []
    context = await _new_context(browser)
    page = await context.new_page()
    template = SEARCH_URL_TEMPLATES["PcComponentes"]
    used_urls: set[str] = set()
    unblock_attempted = False
    hard_blocked = False

    for seed in seeds:
        if hard_blocked:
            break
        search_url = template.format(query=quote_plus(seed.search_query))
        if not await _safe_goto(page, search_url):
            continue
        await _dismiss_pccomponentes_cookie_banner(page)
        await _wait_pccomponentes_results(page)
        title = await page.title()
        body_text = await _extract_visible_text(page)
        if _page_looks_blocked(title, body_text):
            if not unblock_attempted:
                unblock_attempted = True
                if await _wait_pccomponentes_manual_unblock(page):
                    title = await page.title()
                    body_text = await _extract_visible_text(page)
            if _page_looks_blocked(title, body_text):
                hard_blocked = True
            continue

        candidates = await _extract_search_candidates(page)
        candidates = [c for c in candidates if _pccomponentes_candidate_matches_seed(seed, str(c.get("text", "")), str(c.get("href", "")))]
        scored: list[tuple[int, dict]] = []
        for item in candidates:
            href = str(item.get("href", ""))
            if href in used_urls:
                continue
            text = " ".join([str(item.get("text", "")), str(item.get("card_text", ""))])
            score = _seed_match_score(seed, f"{text} {href}")
            if score < 4:
                continue
            scored.append((score, item))
        if not scored:
            continue
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]

        detail_url = str(best.get("href", ""))
        if not detail_url:
            continue
        if not await _safe_goto(page, detail_url):
            continue

        await _dismiss_pccomponentes_cookie_banner(page)
        await page.wait_for_timeout(1200)
        detail_title = await page.title()
        detail_text = await _extract_visible_text(page)
        if _page_looks_blocked(detail_title, detail_text):
            if not unblock_attempted:
                unblock_attempted = True
                if await _wait_pccomponentes_manual_unblock(page):
                    detail_title = await page.title()
                    detail_text = await _extract_visible_text(page)
            continue
        if _seed_match_score(seed, " ".join([detail_title, detail_text[:2200], detail_url])) < 4:
            continue

        offers: list[dict] = []
        cash_offer = await _extract_pccomponentes_cash_offer(page, detail_text)
        if cash_offer:
            offers.append(cash_offer)
        financing_offer = await _extract_pccomponentes_financing_offer(page, detail_text)
        if financing_offer:
            offers.append(financing_offer)
        if not offers:
            snippet = " ".join([str(best.get("text", "")), str(best.get("card_text", ""))])
            offers = _offers_from_snippet(snippet)
        offers = _dedupe_offers(offers)
        if not offers:
            continue

        used_urls.add(detail_url)
        capacity = seed.capacity_gb or _normalize_phone_capacity(detect_capacity_gb(" ".join([detail_title, detail_text[:2500]])))
        in_stock = detect_stock_state(detail_text)
        records.extend(
            _record_from_offer(
                competitor="PcComponentes",
                seed=seed,
                source_url=detail_url,
                source_title=detail_title,
                in_stock=in_stock,
                capacity=capacity,
                offer=offer,
                quality_tier="pccomponentes_adapter_live",
            )
            for offer in offers
        )
        await asyncio.sleep(0.5)

    await context.close()
    return records


async def _scrape_fnac_prices(browser: Browser, seeds: list[ProductSeed]) -> list[PriceRecord]:
    records: list[PriceRecord] = []
    context = await _new_context(browser)
    page = await context.new_page()
    template = SEARCH_URL_TEMPLATES["Fnac"]
    used_urls: set[str] = set()
    unblock_attempted = False
    hard_blocked = False

    for seed in seeds:
        if hard_blocked:
            break
        search_url = template.format(query=quote_plus(seed.search_query))
        if not await _safe_goto(page, search_url):
            continue
        await _dismiss_fnac_cookie_banner(page)

        title = await page.title()
        body_text = await _extract_visible_text(page)
        if _page_looks_blocked(title, body_text):
            if not unblock_attempted:
                unblock_attempted = True
                if await _wait_fnac_manual_unblock(page):
                    title = await page.title()
                    body_text = await _extract_visible_text(page)
            if _page_looks_blocked(title, body_text):
                hard_blocked = True
            continue

        candidates = await _extract_search_candidates(page)
        candidates = [c for c in candidates if _fnac_candidate_matches_seed(seed, str(c.get("text", "")), str(c.get("href", "")))]
        scored: list[tuple[int, dict]] = []
        for item in candidates:
            href = str(item.get("href", ""))
            if href in used_urls:
                continue
            text = " ".join([str(item.get("text", "")), str(item.get("card_text", ""))])
            score = _seed_match_score(seed, f"{text} {href}")
            if score < 1:
                continue
            scored.append((score, item))
        if not scored:
            continue
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        detail_url = str(best.get("href", ""))
        if not detail_url:
            continue

        if not await _safe_goto(page, detail_url):
            continue
        await _dismiss_fnac_cookie_banner(page)
        detail_title = await page.title()
        detail_text = await _extract_visible_text(page)
        if _page_looks_blocked(detail_title, detail_text):
            if not unblock_attempted:
                unblock_attempted = True
                if await _wait_fnac_manual_unblock(page):
                    detail_title = await page.title()
                    detail_text = await _extract_visible_text(page)
            continue

        detail_mix = " ".join([detail_title, detail_text[:2500], detail_url])
        if _seed_match_score(seed, detail_mix) < 4:
            continue
        if not _fnac_candidate_matches_seed(seed, detail_title, detail_url):
            continue

        offers = _extract_fnac_offers_from_text(detail_text)
        dom_cash = await _extract_fnac_cash_from_dom(page)
        if dom_cash:
            offers.append(dom_cash)
        if not offers:
            snippet = " ".join([str(best.get("text", "")), str(best.get("card_text", ""))])
            offers = _offers_from_snippet(snippet)
        offers = _dedupe_offers(offers)
        if not offers:
            continue

        used_urls.add(detail_url)
        capacity = seed.capacity_gb or _normalize_phone_capacity(detect_capacity_gb(" ".join([detail_title, detail_text[:2500]])))
        in_stock = detect_stock_state(detail_text)
        records.extend(
            _record_from_offer(
                competitor="Fnac",
                seed=seed,
                source_url=detail_url,
                source_title=detail_title,
                in_stock=in_stock,
                capacity=capacity,
                offer=offer,
                quality_tier="fnac_adapter_live",
            )
            for offer in offers
        )
        await asyncio.sleep(0.5)

    await context.close()
    return records


async def _scrape_grover_prices(browser: Browser, seeds: list[ProductSeed]) -> list[PriceRecord]:
    records: list[PriceRecord] = []
    context = await _new_context(browser)
    page = await context.new_page()
    used_urls: set[str] = set()
    brand = seeds[0].brand if seeds else "Samsung"
    catalog_candidates = await _extract_grover_collection_candidates(page, brand=brand)
    search_template = SEARCH_URL_TEMPLATES.get("Grover", "https://www.grover.com/es-es/search?query={query}")

    for seed in seeds:
        min_score = 4 if _is_apple_seed(seed) else 6
        scored_candidates: list[tuple[int, dict]] = []
        for item in catalog_candidates:
            href = str(item.get("href", ""))
            if href in used_urls:
                continue
            text = str(item.get("text", ""))
            if not _grover_candidate_matches_seed(seed, text=text, href=href):
                continue
            score = _seed_match_score(seed, f"{text} {href}")
            if score < min_score:
                continue
            scored_candidates.append((score, item))

        if not scored_candidates:
            search_url = search_template.format(query=quote_plus(seed.search_query))
            if await _safe_goto(page, search_url):
                search_title = await page.title()
                search_text = await _extract_visible_text(page)
                if not _page_looks_blocked(search_title, search_text):
                    dynamic_candidates = await _extract_search_candidates(page)
                    for item in dynamic_candidates:
                        href = str(item.get("href", ""))
                        href_n = normalize_text(href)
                        if "grover.com" not in href_n or "/products/" not in href_n:
                            continue
                        if href in used_urls:
                            continue
                        text = str(item.get("text", "")) or str(item.get("card_text", ""))
                        if not _grover_candidate_matches_seed(seed, text=text, href=href):
                            continue
                        score = _seed_match_score(seed, f"{text} {href}")
                        if score < min_score:
                            continue
                        scored_candidates.append((score, item))

        if not scored_candidates:
            continue
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        best = scored_candidates[0][1]

        detail_url = str(best.get("href", ""))
        if not await _safe_goto(page, detail_url):
            continue

        detail_title = await page.title()
        detail_text = await _extract_visible_text(page)
        if _page_looks_blocked(detail_title, detail_text):
            continue

        payload = await _extract_grover_product_payload(page)
        payload_name = str((payload or {}).get("name") or "")
        detail_mix = " ".join([detail_title, payload_name, detail_url])
        if _seed_match_score(seed, detail_mix) < min_score:
            continue
        if not _grover_candidate_matches_seed(seed, text=f"{detail_title} {payload_name}", href=detail_url):
            continue

        offers = _extract_grover_offers(payload=payload, page_text=detail_text)
        if not offers:
            continue
        used_urls.add(detail_url)

        in_stock: bool | None = None
        if isinstance(payload, dict):
            value = payload.get("available")
            if isinstance(value, bool):
                in_stock = value
        if in_stock is None:
            in_stock = detect_stock_state(detail_text)

        seed_type = _seed_device_type(seed)
        capacity = seed.capacity_gb or _detect_capacity_for_device(" ".join([detail_title, detail_text[:2500]]), seed_type)
        records.extend(
            _record_from_offer(
                competitor="Grover",
                seed=seed,
                source_url=detail_url,
                source_title=detail_title,
                in_stock=in_stock,
                capacity=capacity,
                offer=offer,
                quality_tier="grover_adapter_live",
            )
            for offer in offers
        )
        await asyncio.sleep(0.5)

    await context.close()
    return records


async def _scrape_movistar_prices(browser: Browser, seeds: list[ProductSeed]) -> list[PriceRecord]:
    records: list[PriceRecord] = []
    context = await _new_context(browser)
    page = await context.new_page()
    used_urls: set[str] = set()

    for seed in seeds:
        seed_type = _seed_device_type(seed)
        if seed_type == "tablet":
            base_path = "tablets"
            search_root = f"https://www.movistar.es/{base_path}/?sort=relevance&query="
        elif seed_type == "laptop":
            search_root = "https://www.movistar.es/buscador/?q="
        else:
            base_path = "moviles"
            search_root = f"https://www.movistar.es/{base_path}/?sort=relevance&query="
        ranked_by_url: dict[str, tuple[int, dict]] = {}
        for query in _seed_search_queries(seed):
            search_url = search_root + quote_plus(query)
            if not await _safe_goto(page, search_url):
                continue
            await _dismiss_movistar_cookie_banner(page)

            title = await page.title()
            body_text = await _extract_visible_text(page)
            if _page_looks_blocked(title, body_text):
                continue

            candidates = await _extract_search_candidates(page)
            candidates = [
                c
                for c in candidates
                if (
                    ("/tablet" in str(c.get("href", "")))
                    if seed_type == "tablet"
                    else (
                        ("/portatil" in str(c.get("href", "")) or "/ordenador" in str(c.get("href", "")).lower())
                        if seed_type == "laptop"
                        else "/moviles/" in str(c.get("href", ""))
                    )
                )
                and "movistar.es" in normalize_text(str(c.get("href", "")))
            ]
            for item in candidates:
                href = str(item.get("href", ""))
                if not href or href in used_urls:
                    continue
                text = " ".join([str(item.get("text", "")), str(item.get("card_text", ""))])
                if not _movistar_candidate_matches_seed(seed, text=text, href=href) and not _movistar_relaxed_match(
                    seed,
                    text=text,
                    href=href,
                ):
                    continue
                score = _seed_match_score(seed, f"{text} {href}")
                if score < 0:
                    continue
                cur = ranked_by_url.get(href)
                if not cur or score > cur[0]:
                    ranked_by_url[href] = (score, item)

        if not ranked_by_url:
            continue
        ranked = sorted(ranked_by_url.values(), key=lambda x: x[0], reverse=True)

        chosen: tuple[str, str, str, list[dict]] | None = None
        for _, item in ranked[:8]:
            detail_url = str(item.get("href", ""))
            if not detail_url:
                continue

            if not await _safe_goto(page, detail_url):
                continue
            await _dismiss_movistar_cookie_banner(page)
            detail_title = await page.title()
            detail_text = await _extract_visible_text(page)
            if _page_looks_blocked(detail_title, detail_text):
                continue
            if not _movistar_candidate_matches_seed(seed, text=detail_title, href=detail_url) and not _movistar_relaxed_match(
                seed,
                text=detail_title,
                href=detail_url,
                body_text=detail_text[:2200],
            ):
                continue

            offers = _extract_movistar_offers_from_text(detail_text)
            if not offers:
                continue
            chosen = (detail_url, detail_title, detail_text, offers)
            break

        if not chosen:
            continue
        detail_url, detail_title, detail_text, offers = chosen
        used_urls.add(detail_url)
        detected_capacity = _detect_capacity_for_device(" ".join([detail_title, detail_text[:2500], detail_url]), seed_type)
        capacity = detected_capacity if detected_capacity else seed.capacity_gb
        if seed.capacity_gb and seed_type in {"mobile", "tablet"}:
            # Prefer explicit title/URL capacity hints. Body text often lists all variants,
            # which can bias detection to a different GB than the selected SKU.
            explicit_caps = _extract_capacity_values(" ".join([detail_title, detail_url]))
            if explicit_caps and seed.capacity_gb not in explicit_caps:
                continue
            if explicit_caps:
                capacity = seed.capacity_gb
            elif detected_capacity and detected_capacity != seed.capacity_gb:
                continue
            else:
                capacity = seed.capacity_gb
        in_stock = detect_stock_state(detail_text)
        records.extend(
            _record_from_offer(
                competitor="Movistar",
                seed=seed,
                source_url=detail_url,
                source_title=detail_title,
                in_stock=in_stock,
                capacity=capacity,
                offer=offer,
                quality_tier="movistar_adapter_live",
            )
            for offer in offers
        )
        await asyncio.sleep(0.4)

    await context.close()
    return records


def _samsung_buy_url_matches_seed(seed: ProductSeed, text: str, href: str) -> bool:
    href_n = normalize_text(href)
    if "samsung.com/es" not in href_n:
        return False
    seed_type = _seed_device_type(seed)
    if seed_type == "tablet":
        expected_ok = "/tablets/" in href_n
    elif seed_type == "laptop":
        expected_ok = any(token in href_n for token in ("/computers/", "/laptops/", "/galaxy-book/"))
    else:
        expected_ok = "/smartphones/" in href_n
    if not expected_ok:
        return False
    if "/buy/" not in href_n:
        return False

    mix = " ".join([text, href])
    if not _seed_device_matches_candidate(seed=seed, text=text, href=href):
        return False
    score = _seed_match_score(seed, mix)
    if score < 2:
        return False

    seed_markers = _collect_model_markers(seed.model, raw_text=seed.model)
    cand_markers = _collect_model_markers(mix, raw_text=mix)
    href_markers = _collect_model_markers(href, raw_text=href)
    strict_markers = {"ultra", "plus", "fe", "flip", "fold", "lite"}
    for marker in strict_markers:
        if marker in seed_markers and marker not in cand_markers:
            return False
        if marker in href_markers and marker not in seed_markers:
            return False

    seed_norm = normalize_text(seed.model)
    mix_norm = normalize_text(mix)
    mix_compact = mix_norm.replace(" ", "")
    if "5g" in seed_norm:
        if "5g" not in mix_norm and "5g" not in href_n:
            return False
    else:
        if "5g" in href_n and "5g" not in seed_norm:
            return False
    for family in ("s", "a"):
        numbers = set(re.findall(rf"\b{family}\s*(\d{{2,3}})\b", seed_norm))
        for num in numbers:
            token = f"{family}{num}"
            if token not in mix_compact:
                return False
    if "flip" in seed_norm:
        flip_num = re.search(r"flip\s*(\d{1,2})", seed_norm)
        if flip_num and f"flip{flip_num.group(1)}" not in mix_compact:
            return False
    if "fold" in seed_norm:
        fold_num = re.search(r"fold\s*(\d{1,2})", seed_norm)
        if fold_num and f"fold{fold_num.group(1)}" not in mix_compact:
            return False
    return True


def _samsung_manual_buy_urls(seed: ProductSeed) -> list[str]:
    model_n = normalize_text(seed.model)
    urls: list[str] = []
    seed_type = _seed_device_type(seed)

    if seed_type == "mobile":
        if "s25 fe" in model_n:
            urls.append("https://www.samsung.com/es/smartphones/galaxy-s25/buy/")
        a_match = re.search(r"\ba\s*(\d{2,3})\b", model_n)
        if a_match:
            num = a_match.group(1)
            urls.append(f"https://www.samsung.com/es/smartphones/galaxy-a/galaxy-a{num}-5g/buy/")
            urls.append(f"https://www.samsung.com/es/smartphones/galaxy-a/galaxy-a{num}/buy/")
        s_match = re.search(r"\bs\s*(\d{2,3})\b", model_n)
        if s_match and "ultra" in model_n:
            urls.append(f"https://www.samsung.com/es/smartphones/galaxy-s{s_match.group(1)}-ultra/buy/")
        elif s_match:
            urls.append(f"https://www.samsung.com/es/smartphones/galaxy-s{s_match.group(1)}/buy/")
        flip_match = re.search(r"\bflip\s*(\d{1,2})\b", model_n)
        if flip_match:
            urls.append(f"https://www.samsung.com/es/smartphones/galaxy-z-flip{flip_match.group(1)}/buy/")
        fold_match = re.search(r"\bfold\s*(\d{1,2})\b", model_n)
        if fold_match:
            urls.append(f"https://www.samsung.com/es/smartphones/galaxy-z-fold{fold_match.group(1)}/buy/")
    else:
        if seed_type == "tablet":
            if "tab s10 fe" in model_n:
                urls.append("https://www.samsung.com/es/tablets/galaxy-tab-s10-fe/buy/")
            tab_s_match = re.search(r"\btab\s*s\s*(\d{1,2})\b", model_n)
            if tab_s_match:
                num = tab_s_match.group(1)
                urls.append(f"https://www.samsung.com/es/tablets/galaxy-tab-s{num}/buy/")
                urls.append(f"https://www.samsung.com/es/tablets/galaxy-tab-s{num}-fe/buy/")
                if "ultra" in model_n:
                    urls.append(f"https://www.samsung.com/es/tablets/galaxy-tab-s{num}-ultra/buy/")
                if "lite" in model_n:
                    urls.append(f"https://www.samsung.com/es/tablets/galaxy-tab-s{num}-lite/buy/")
            if "tab a11" in model_n:
                urls.append("https://www.samsung.com/es/tablets/galaxy-tab-a11-plus/buy/")
        else:
            if "book5 pro" in model_n:
                urls.append("https://www.samsung.com/es/computers/galaxy-book/galaxy-book5-pro/buy/")
            if "book5" in model_n:
                urls.append("https://www.samsung.com/es/computers/galaxy-book/galaxy-book5-360/buy/")
                urls.append("https://www.samsung.com/es/computers/galaxy-book/galaxy-book5-pro-360/buy/")

    out: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


async def _discover_samsung_buy_candidates(page: Page) -> list[dict]:
    sources = [
        "https://www.samsung.com/es/smartphones/all-smartphones/",
        "https://www.samsung.com/es/smartphones/",
        "https://www.samsung.com/es/smartphones/galaxy-s25/",
        "https://www.samsung.com/es/smartphones/galaxy-z/",
        "https://www.samsung.com/es/smartphones/galaxy-a/",
        "https://www.samsung.com/es/tablets/",
        "https://www.samsung.com/es/tablets/all-tablets/",
        "https://www.samsung.com/es/tablets/galaxy-tab-s/",
        "https://www.samsung.com/es/tablets/galaxy-tab-a/",
        "https://www.samsung.com/es/computers/galaxy-book/",
        "https://www.samsung.com/es/computers/laptops/",
    ]
    out: list[dict] = []
    seen: set[str] = set()

    for url in sources:
        if not await _safe_goto(page, url):
            continue
        await _dismiss_samsung_cookie_banner(page)
        links = await _extract_search_candidates(page)
        for item in links:
            href = str(item.get("href", "")).strip()
            if not href or href in seen:
                continue
            href_n = normalize_text(href)
            if "samsung.com/es" not in href_n or "/buy/" not in href_n:
                continue
            if "/smartphones/" not in href_n and "/tablets/" not in href_n and "/computers/" not in href_n:
                continue
            seen.add(href)
            out.append(item)
    return out


async def _discover_samsung_buy_candidates_from_aisearch(page: Page, query: str) -> list[dict]:
    search_url = "https://www.samsung.com/es/aisearch/?searchvalue=" + quote_plus(query)
    if not await _safe_goto(page, search_url):
        return []
    await _dismiss_samsung_cookie_banner(page)
    links = await _extract_search_candidates(page)
    return [
        item
        for item in links
        if "/buy/" in normalize_text(str(item.get("href", "")))
        and "samsung.com/es/" in normalize_text(str(item.get("href", "")))
    ]


def _samsung_variant_target(seed: ProductSeed) -> tuple[str | None, list[str]]:
    model_n = normalize_text(seed.model)
    if "s25 fe" in model_n:
        return "s25 fe", []
    return None, []


async def _select_samsung_model_variant(page: Page, seed: ProductSeed) -> bool:
    target, forbidden = _samsung_variant_target(seed)
    if not target:
        return False
    if target == "s25 fe":
        selectors = [
            "button:has-text('S25 FE')",
            "[role='tab']:has-text('S25 FE')",
            "[role='radio']:has-text('S25 FE')",
            "label:has-text('S25 FE')",
            "a:has-text('S25 FE')",
        ]
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if await loc.count() <= 0:
                    continue
                await loc.click(timeout=2500)
                await page.wait_for_timeout(700)
                check = normalize_text(await _extract_visible_text(page))
                if "s25 fe" in check:
                    return True
            except Exception:
                continue
    script = """
    ({ target, forbidden }) => {
      const nodes = Array.from(document.querySelectorAll('label, button, [role="tab"], [role="radio"], [role="button"], li, a'));
      for (const el of nodes) {
        const txt = (el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
        if (!txt || txt.length > 40) continue;
        if (!txt.includes(target)) continue;
        if (forbidden.some(f => txt.includes(f))) continue;
        if (!txt.includes('galaxy') && !txt.includes('s25 fe')) continue;
        el.click();
        return true;
      }
      return false;
    }
    """
    try:
        clicked = await page.evaluate(script, {"target": target, "forbidden": forbidden})
        if clicked:
            await page.wait_for_timeout(700)
            if target == "s25 fe":
                check = normalize_text(await _extract_visible_text(page))
                return "s25 fe" in check
        return bool(clicked)
    except Exception:
        return False


async def _select_samsung_capacity(page: Page, capacity_gb: int) -> bool:
    script = """
    (capacityGb) => {
      const want = `${capacityGb}gb`;
      const inputs = Array.from(document.querySelectorAll(
        "input[type='radio'][data-modelprice], input[type='radio'][data-promotionprice], input[type='radio'][data-discountprice], input.option-input[data-modelprice], input.option-input[data-discountprice]"
      ));
      for (const input of inputs) {
        const host = input.closest('label, li, div, section, article') || input.parentElement || input;
        const txt = (host.textContent || '').replace(/\\s+/g, ' ').toLowerCase();
        if (!txt.includes(want)) continue;
        if (txt.includes('agotado') || txt.includes('sin stock') || txt.includes('no disponible')) continue;
        if (host instanceof HTMLElement) host.click();
        if (input instanceof HTMLElement) input.click();
        return true;
      }
      const clickable = Array.from(document.querySelectorAll('label, button, [role="radio"], [role="button"], li, div'));
      for (const el of clickable) {
        const txt = (el.textContent || '').replace(/\\s+/g, ' ').toLowerCase();
        if (!txt.includes(want)) continue;
        if (!txt.includes('gb')) continue;
        if (txt.includes('agotado') || txt.includes('sin stock') || txt.includes('no disponible')) continue;
        if (el instanceof HTMLElement) el.click();
        return true;
      }
      return false;
    }
    """
    try:
        clicked = await page.evaluate(script, capacity_gb)
        if clicked:
            await page.wait_for_timeout(700)
            selected = await _extract_samsung_selected_capacity(page)
            if selected is not None:
                return selected == capacity_gb
            snippet = await _extract_samsung_selected_option_text(page, capacity_gb)
            return bool(snippet and f"{capacity_gb}" in snippet)
        return False
    except Exception:
        return False


async def _extract_samsung_selected_offer_from_dom(
    page: Page,
    target_capacity_gb: int | None,
) -> tuple[int | None, list[dict]]:
    script = """
    () => {
      const toNum = (raw) => {
        if (!raw) return null;
        const s = String(raw).replace(/\\s+/g, '').replace(',', '.');
        const n = Number(s);
        return Number.isFinite(n) ? n : null;
      };
      const capFromText = (txt) => {
        const m = txt.match(/\\b(64|128|256|512|1024)\\s*gb\\b/i);
        return m ? Number(m[1]) : null;
      };
      const monthFromText = (txt) => {
        const m = txt.match(/(\\d{1,5}(?:[.,]\\d{1,2})?)\\s*(?:€|eur|â‚¬)\\s*\\/?\\s*mes/i);
        return m ? toNum(m[1]) : null;
      };

      const inputs = Array.from(document.querySelectorAll(
        "input[data-modelprice], input[data-promotionprice], input[data-discountprice], input.option-input[data-modelprice], input.option-input[data-discountprice]"
      ));

      const items = [];
      for (const input of inputs) {
        const host = input.closest('label, li, div, section, article') || input.parentElement || input;
        const txt = (host.textContent || '').replace(/\\s+/g, ' ').trim();
        const low = txt.toLowerCase();
        const cap = capFromText(low);
        const monthly = monthFromText(low);
        const modelprice = toNum(input.getAttribute('data-modelprice'));
        const promotion = toNum(input.getAttribute('data-promotionprice'));
        const discount = toNum(input.getAttribute('data-discountprice'));
        const cash = discount ?? promotion ?? modelprice;
        const checked =
          !!input.checked ||
          input.getAttribute('aria-checked') === 'true' ||
          /\bchecked\b/.test((input.className || '').toLowerCase()) ||
          /\bactive\b/.test((host.className || '').toLowerCase());

        if (cash == null) continue;
        if (!cap) continue;
        if (low.includes('agotado') || low.includes('sin stock') || low.includes('no disponible')) continue;
        items.push({ cap, monthly, cash, checked, text: txt.slice(0, 260) });
      }
      return items;
    }
    """
    try:
        rows = await page.evaluate(script)
    except Exception:
        rows = []
    if not isinstance(rows, list) or not rows:
        return None, []

    candidates: list[dict] = [r for r in rows if isinstance(r, dict)]
    target = target_capacity_gb if isinstance(target_capacity_gb, int) else None
    picked: dict | None = None
    if target is not None:
        exact_checked = [r for r in candidates if r.get("cap") == target and bool(r.get("checked"))]
        exact_any = [r for r in candidates if r.get("cap") == target]
        pool = exact_checked or exact_any
        if pool:
            picked = min(pool, key=lambda r: float(r.get("cash") or 0.0))
    if picked is None:
        checked = [r for r in candidates if bool(r.get("checked"))]
        if checked:
            picked = min(checked, key=lambda r: float(r.get("cash") or 0.0))
    if picked is None:
        picked = min(candidates, key=lambda r: float(r.get("cash") or 0.0))

    cap = int(picked.get("cap")) if picked.get("cap") is not None else None
    cash_val = float(picked.get("cash"))
    monthly_val = picked.get("monthly")
    offers: list[dict] = [
        {
            "offer_type": "cash",
            "price_text": f"{cash_val:.2f} €",
            "price_value": cash_val,
            "price_unit": "EUR",
            "term_months": None,
        }
    ]
    if monthly_val is not None:
        offers.append(
            {
                "offer_type": "financing_max_term",
                "price_text": f"{float(monthly_val):.2f} €/mes",
                "price_value": float(monthly_val),
                "price_unit": "EUR/month",
                "term_months": 36,
            }
        )
    return cap, _dedupe_offers(offers)


async def _extract_samsung_selected_capacity(page: Page) -> int | None:
    script = """
    () => {
      const selected = Array.from(document.querySelectorAll('input[type="radio"]:checked, [aria-checked="true"], [aria-selected="true"]'));
      for (const node of selected) {
        const host = node.closest('label, li, div, section') || node;
        const txt = (host.textContent || '').replace(/\\s+/g, ' ').toLowerCase();
        const m = txt.match(/\\b(64|128|256|512|1024)\\s*gb\\b/);
        if (m) return parseInt(m[1], 10);
      }
      return null;
    }
    """
    try:
        value = await page.evaluate(script)
        if isinstance(value, int):
            return _normalize_phone_capacity(value)
    except Exception:
        pass
    return None


async def _extract_samsung_available_capacities(page: Page) -> list[int]:
    script = """
    () => {
      const out = new Set();
      const nodes = Array.from(document.querySelectorAll('label, button, [role="radio"], li, div'));
      for (const node of nodes) {
        const txt = (node.textContent || '').replace(/\\s+/g, ' ').toLowerCase();
        if (!(txt.includes('/mes') || txt.includes('€/mes') || txt.includes('eur/mes'))) continue;
        const m = txt.match(/\\b(64|128|256|512|1024)\\s*gb\\b/g) || [];
        for (const raw of m) {
          const val = parseInt(raw.replace(/[^0-9]/g, ''), 10);
          if (val) out.add(val);
        }
      }
      return Array.from(out).sort((a, b) => a - b);
    }
    """
    try:
        values = await page.evaluate(script)
        if isinstance(values, list):
            caps: list[int] = []
            for val in values:
                if isinstance(val, int):
                    cap = _normalize_phone_capacity(val)
                    if cap:
                        caps.append(cap)
            return sorted(set(caps))
    except Exception:
        pass
    return []


async def _extract_samsung_selected_option_text(page: Page, capacity_gb: int | None = None) -> str:
    script = """
    (capacityGb) => {
      const out = [];
      const want = capacityGb ? `${capacityGb}gb` : '';
      const nodes = Array.from(document.querySelectorAll('label, button, [role="radio"], li, div'));
      for (const node of nodes) {
        const txt = (node.textContent || '').replace(/\\s+/g, ' ').trim();
        if (!txt || txt.length > 260) continue;
        const low = txt.toLowerCase();
        if (!/\\b\\d{2,4}\\s*gb\\b/.test(low)) continue;
        if (!(low.includes('/mes') || low.includes('€/mes') || low.includes('eur/mes'))) continue;
        if (!(low.includes(' o ') || low.includes(', o ') || low.includes(' al contado'))) continue;
        if (want && !low.includes(want)) continue;
        out.push(txt);
      }
      if (out.length) return out.slice(0, 6).join(' | ');
      const checked = Array.from(document.querySelectorAll('input[type="radio"]:checked, [aria-checked="true"], [aria-selected="true"]'));
      const backup = [];
      for (const node of checked) {
        const host = node.closest('label, li, div, section') || node;
        const txt = (host.textContent || '').replace(/\\s+/g, ' ').trim();
        if (txt) backup.push(txt);
      }
      return backup.join(' | ');
    }
    """
    try:
        return str(await page.evaluate(script, capacity_gb))
    except Exception:
        return ""


def _extract_samsung_offers_from_text(text: str) -> list[dict]:
    offers: list[dict] = []
    pair_match = re.search(
        r"(\\d{1,5}(?:[.\\s]\\d{3})*(?:,\\d{1,2})?)\\s*(?:€|eur)\\s*/?\\s*mes[^\\d]{0,35}(?:,\\s*o|\\bo\\b)\\s*(\\d{1,5}(?:[.\\s]\\d{3})*(?:,\\d{1,2})?)\\s*(?:€|eur)",
        text,
        flags=re.IGNORECASE,
    )
    if pair_match:
        month_raw = pair_match.group(1)
        cash_raw = pair_match.group(2)
        month_value = parse_euro_to_float(month_raw)
        cash_value = parse_euro_to_float(cash_raw)
        if month_value is not None:
            offers.append(
                {
                    "offer_type": "financing_max_term",
                    "price_text": f"{month_raw} €/mes",
                    "price_value": month_value,
                    "price_unit": "EUR/month",
                    "term_months": 36,
                }
            )
        if cash_value is not None:
            offers.append(
                {
                    "offer_type": "cash",
                    "price_text": f"{cash_raw} €",
                    "price_value": cash_value,
                    "price_unit": "EUR",
                    "term_months": None,
                }
            )
        return _dedupe_offers(offers)

    monthly = _extract_monthly_offer(text)
    if monthly:
        monthly["offer_type"] = "financing_max_term"
        monthly["price_unit"] = "EUR/month"
        if monthly.get("term_months") is None:
            monthly["term_months"] = 36
        offers.append(monthly)

    cash_match = re.search(
        r"(?:\bo\b|\bcontado\b|\bal contado\b)[^\d]{0,20}(\d{1,5}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s*(?:€|eur)",
        text,
        flags=re.IGNORECASE,
    )
    cash_offer: dict | None = None
    if cash_match:
        raw = cash_match.group(1)
        value = parse_euro_to_float(raw)
        if value is not None:
            cash_offer = {
                "offer_type": "cash",
                "price_text": f"{raw} €",
                "price_value": value,
                "price_unit": "EUR",
                "term_months": None,
            }
    if not cash_offer:
        pvp_match = re.search(
            r"(?:\bpvp\b|\bpvpr\b|precio\s+(?:de\s+venta\s+al\s+publico\s+)?recomendado)[^\d]{0,35}"
            r"(\d{1,5}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s*(?:â‚¬|eur)",
            text,
            flags=re.IGNORECASE,
        )
        if pvp_match:
            raw = pvp_match.group(1)
            value = parse_euro_to_float(raw)
            if value is not None and value >= 100:
                cash_offer = {
                    "offer_type": "cash",
                    "price_text": f"{raw} â‚¬",
                    "price_value": value,
                    "price_unit": "EUR",
                    "term_months": None,
                }
    if not cash_offer:
        values: list[tuple[str, float]] = []
        for match in EURO_VALUE_RE.finditer(text.replace("\xa0", " ")):
            raw = match.group(1)
            value = parse_euro_to_float(raw)
            if value is None:
                continue
            values.append((raw, value))
        if values:
            raw, value = max(values, key=lambda x: x[1])
            if value >= 100:
                cash_offer = {
                    "offer_type": "cash",
                    "price_text": f"{raw} €",
                    "price_value": value,
                    "price_unit": "EUR",
                    "term_months": None,
                }
    if cash_offer:
        offers.append(cash_offer)
    return _dedupe_offers(offers)


def _extract_samsung_capacity_offer_map(text: str) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    cleaned = re.sub(r"\s+", " ", text)

    pair_re = re.compile(
        r"\b(64|128|256|512|1024)\s*gb\b.{0,180}?"
        r"(\d{1,5}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s*(?:€|eur|â‚¬)\s*/?\s*mes"
        r".{0,70}?(?:,\s*o|\bo\b)\s*"
        r"(\d{1,5}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s*(?:€|eur|â‚¬)",
        flags=re.IGNORECASE,
    )
    for match in pair_re.finditer(cleaned):
        cap = int(match.group(1))
        month_raw = match.group(2)
        cash_raw = match.group(3)
        month_val = parse_euro_to_float(month_raw)
        cash_val = parse_euro_to_float(cash_raw)
        offers: list[dict] = []
        if month_val is not None:
            offers.append(
                {
                    "offer_type": "financing_max_term",
                    "price_text": f"{month_raw} €/mes",
                    "price_value": month_val,
                    "price_unit": "EUR/month",
                    "term_months": 36,
                }
            )
        if cash_val is not None:
            offers.append(
                {
                    "offer_type": "cash",
                    "price_text": f"{cash_raw} €",
                    "price_value": cash_val,
                    "price_unit": "EUR",
                    "term_months": None,
                }
            )
        if offers:
            out[cap] = _dedupe_offers(offers)

    cash_only_re = re.compile(
        r"\b(64|128|256|512|1024)\s*gb\b.{0,140}?"
        r"(\d{1,5}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s*(?:€|eur|â‚¬)",
        flags=re.IGNORECASE,
    )
    for match in cash_only_re.finditer(cleaned):
        cap = int(match.group(1))
        if cap in out:
            continue
        cash_raw = match.group(2)
        cash_val = parse_euro_to_float(cash_raw)
        if cash_val is None:
            continue
        out[cap] = [
            {
                "offer_type": "cash",
                "price_text": f"{cash_raw} €",
                "price_value": cash_val,
                "price_unit": "EUR",
                "term_months": None,
            }
        ]

    return out


def _samsung_looks_upcoming(text: str) -> bool:
    n = normalize_text(text)
    if "proximamente" not in n and "coming soon" not in n:
        return False
    # Keep only explicit purchasable pages; otherwise treat as not on sale yet.
    if any(token in n for token in ("anadir al carrito", "agregar al carrito", "buy now", "comprar ahora")):
        return False
    return True


async def _scrape_rentik_prices(browser: Browser, seeds: list[ProductSeed]) -> list[PriceRecord]:
    records: list[PriceRecord] = []
    context = await _new_context(browser)
    page = await context.new_page()
    used_urls: set[str] = set()

    brand = seeds[0].brand if seeds else "Samsung"
    if normalize_text(brand) == "apple":
        catalog_url = "https://www.rentik.com/es/ofertas-alquilar/iphone/"
    else:
        catalog_url = "https://www.rentik.com/es/ofertas-alquilar/samsung/"
    if not await _safe_goto(page, catalog_url):
        await context.close()
        return records
    await _dismiss_rentik_cookie_banner(page)

    catalog_title = await page.title()
    catalog_text = await _extract_visible_text(page)
    if _page_looks_blocked(catalog_title, catalog_text):
        await context.close()
        return records

    catalog_candidates = await _extract_search_candidates(page)

    for seed in seeds:
        scored = _score_rentik_candidates(seed=seed, candidates=catalog_candidates, used_urls=used_urls)
        if not scored:
            # Secondary discovery for models not surfaced clearly in the catalog block.
            search_url = "https://rentik.com/?s=" + quote_plus(seed.search_query)
            if await _safe_goto(page, search_url):
                await _dismiss_rentik_cookie_banner(page)
                search_candidates = await _extract_search_candidates(page)
                scored = _score_rentik_candidates(seed=seed, candidates=search_candidates, used_urls=used_urls)
        if not scored:
            continue
        detail_url = _rentik_candidate_url(str(scored[0][1].get("href", "")), brand=seed.brand)
        if not detail_url:
            continue

        if not await _safe_goto(page, detail_url):
            continue
        await _dismiss_rentik_cookie_banner(page)
        detail_title = await page.title()
        detail_text = await _extract_visible_text(page)
        if _page_looks_blocked(detail_title, detail_text):
            continue
        if not _rentik_candidate_matches_seed(seed, text=detail_title, href=detail_url):
            continue

        # Force requested storage variant before reading monthly price.
        available_caps = await _extract_rentik_available_capacities(page)
        offers: list[dict] = []
        if seed.capacity_gb:
            if available_caps and seed.capacity_gb not in available_caps:
                continue
            if available_caps and len(available_caps) > 1:
                per_capacity_offer: dict[int, dict] = {}
                for cap in sorted(available_caps):
                    if not await _select_rentik_capacity(page, cap):
                        continue
                    cap_text = await _extract_visible_text(page)
                    offer = _extract_rentik_primary_monthly_offer(cap_text)
                    if offer:
                        per_capacity_offer[cap] = offer
                chosen = per_capacity_offer.get(seed.capacity_gb)
                if not chosen:
                    continue
                if not await _select_rentik_capacity(page, seed.capacity_gb):
                    continue
                detail_title = await page.title()
                detail_text = await _extract_visible_text(page)
                offers = [chosen]
            else:
                selected = await _select_rentik_capacity(page, seed.capacity_gb)
                if not selected and available_caps and len(available_caps) > 1:
                    # Multi-capacity page without deterministic selection: skip to avoid wrong price/capacity pairing.
                    continue
                detail_title = await page.title()
                detail_text = await _extract_visible_text(page)
                offers = _extract_rentik_offers_from_text(detail_text)
        else:
            offers = _extract_rentik_offers_from_text(detail_text)

        if not offers:
            continue

        used_urls.add(detail_url)
        detected_capacity = (
            _capacity_from_rentik_url(detail_url)
            or await _extract_rentik_selected_capacity(page)
            or _normalize_phone_capacity(detect_capacity_gb(" ".join([detail_title, detail_text[:2200]])))
        )
        capacity = seed.capacity_gb or detected_capacity
        in_stock = detect_stock_state(detail_text)
        records.extend(
            _record_from_offer(
                competitor="Rentik",
                seed=seed,
                source_url=detail_url,
                source_title=detail_title,
                in_stock=in_stock,
                capacity=capacity,
                offer=offer,
                quality_tier="rentik_adapter_live",
            )
            for offer in offers
        )
        await asyncio.sleep(0.4)

    await context.close()
    return records


async def _scrape_samsung_oficial_prices(browser: Browser, seeds: list[ProductSeed]) -> list[PriceRecord]:
    records: list[PriceRecord] = []
    context = await _new_context(browser)
    page = await context.new_page()

    catalog_candidates = await _discover_samsung_buy_candidates(page)

    for seed in seeds:
        seed_type = _seed_device_type(seed)
        scored: list[tuple[int, dict]] = []
        for item in catalog_candidates:
            href = str(item.get("href", ""))
            text = str(item.get("text", ""))
            if not _samsung_buy_url_matches_seed(seed, text=text, href=href):
                continue
            score = _seed_match_score(seed, f"{text} {str(item.get('card_text', ''))} {href}")
            scored.append((score, item))

        if not scored:
            ai_candidates = await _discover_samsung_buy_candidates_from_aisearch(page, seed.search_query)
            for item in ai_candidates:
                href = str(item.get("href", ""))
                text = str(item.get("text", ""))
                if not _samsung_buy_url_matches_seed(seed, text=text, href=href):
                    continue
                score = _seed_match_score(seed, f"{text} {str(item.get('card_text', ''))} {href}")
                scored.append((score, item))
        if not scored:
            for url in _samsung_manual_buy_urls(seed):
                if not _samsung_buy_url_matches_seed(seed, text=seed.model, href=url):
                    continue
                scored.append((4, {"href": url, "text": seed.model, "card_text": ""}))

        if not scored:
            continue
        scored.sort(key=lambda x: x[0], reverse=True)
        detail_url = str(scored[0][1].get("href", ""))
        if not detail_url:
            continue

        if not await _safe_goto(page, detail_url):
            continue
        await _dismiss_samsung_cookie_banner(page)
        await page.wait_for_timeout(900)
        detail_title = await page.title()
        detail_text = await _extract_visible_text(page)
        if _page_looks_blocked(detail_title, detail_text):
            continue

        variant_selected = await _select_samsung_model_variant(page, seed)
        if "s25 fe" in normalize_text(seed.model) and not variant_selected:
            continue
        if seed.capacity_gb:
            _ = await _select_samsung_capacity(page, seed.capacity_gb)
            detail_text = await _extract_visible_text(page)

        snippet_capacity = seed.capacity_gb if seed.capacity_gb else None
        selected_text = await _extract_samsung_selected_option_text(page, snippet_capacity)
        merged_text = " ".join([selected_text, detail_text[:7000]])
        if _samsung_looks_upcoming(" ".join([detail_title, merged_text])):
            continue
        capacity, offers = await _extract_samsung_selected_offer_from_dom(page, seed.capacity_gb)
        if seed.capacity_gb and seed_type in {"mobile", "tablet"}:
            if capacity != seed.capacity_gb:
                capacity_map = _extract_samsung_capacity_offer_map(merged_text)
                exact_offers = capacity_map.get(seed.capacity_gb) or []
                if exact_offers:
                    capacity = seed.capacity_gb
                    offers = exact_offers
                else:
                    continue
            capacity = seed.capacity_gb
        elif seed.capacity_gb and seed_type == "laptop":
            if capacity != seed.capacity_gb:
                capacity_map = _extract_samsung_capacity_offer_map(merged_text)
                exact_offers = capacity_map.get(seed.capacity_gb) or []
                if exact_offers:
                    capacity = seed.capacity_gb
                    offers = exact_offers
        if not offers:
            offers = _extract_samsung_offers_from_text(merged_text)
            if seed_type == "laptop":
                offers = [
                    offer
                    for offer in offers
                    if not (offer.get("offer_type") == "cash" and float(offer.get("price_value") or 0.0) < 800)
                ]
            if not offers:
                continue
            if seed.capacity_gb and seed_type in {"mobile", "tablet"}:
                # If we cannot prove exact capacity via DOM, skip to avoid mismatched GB/price.
                continue
            capacity = capacity or await _extract_samsung_selected_capacity(page) or _detect_capacity_for_device(
                merged_text,
                seed_type,
            )

        in_stock = detect_stock_state(" ".join([selected_text, detail_text]))
        if in_stock is False and offers:
            # Samsung PDPs can include "no disponible" snippets for other
            # capacities/colors while the selected variant is purchasable.
            in_stock = None

        records.extend(
            _record_from_offer(
                competitor="Samsung Oficial",
                seed=seed,
                source_url=detail_url,
                source_title=detail_title,
                in_stock=in_stock,
                capacity=capacity,
                offer=offer,
                quality_tier="samsung_oficial_adapter_live",
            )
            for offer in offers
        )
        await asyncio.sleep(0.4)

    await context.close()
    return records


async def _scrape_generic_competitor_prices(
    browser: Browser,
    competitor: str,
    seeds: list[ProductSeed],
) -> list[PriceRecord]:
    records: list[PriceRecord] = []
    context = await _new_context(browser)
    page = await context.new_page()
    used_urls: set[str] = set()

    for seed in seeds:
        template = SEARCH_URL_TEMPLATES.get(competitor)
        if not template:
            continue
        query = quote_plus(seed.search_query)
        search_url = template.format(query=query)
        if not await _safe_goto(page, search_url):
            continue
        search_title = await page.title()
        search_text = await _extract_visible_text(page)
        if _page_looks_blocked(search_title, search_text):
            continue

        candidates = await _extract_search_candidates(page)
        if competitor == "Apple Oficial":
            apple_candidates: list[dict] = []
            seen_apple_urls: set[str] = set()
            for item in candidates:
                raw_href = str(item.get("href", "")).strip()
                clean_href = _apple_oficial_candidate_url(seed=seed, url=raw_href)
                if not clean_href or clean_href in seen_apple_urls:
                    continue
                mix = " ".join([str(item.get("text", "")), str(item.get("card_text", "")), clean_href])
                if not _apple_oficial_matches_seed(seed=seed, text=mix, href=clean_href):
                    continue
                seen_apple_urls.add(clean_href)
                apple_candidates.append(
                    {
                        "href": clean_href,
                        "text": str(item.get("text", "")),
                        "card_text": str(item.get("card_text", "")),
                    }
                )
            for url in _apple_oficial_manual_buy_urls(seed):
                clean_href = _apple_oficial_candidate_url(seed=seed, url=url)
                if not clean_href or clean_href in seen_apple_urls:
                    continue
                if not _apple_oficial_matches_seed(seed=seed, text=seed.model, href=clean_href):
                    continue
                seen_apple_urls.add(clean_href)
                apple_candidates.append({"href": clean_href, "text": seed.model, "card_text": ""})
            candidates = apple_candidates
        best = _pick_best_candidate(seed, candidates, excluded_urls=used_urls)
        if not best:
            continue

        candidate_href = str(best.get("href", "")).strip()
        if not candidate_href:
            continue

        target_url = _canonical_amazon_url(candidate_href) if "amazon." in normalize_text(candidate_href) else candidate_href
        if _url_without_fragment(target_url) == _url_without_fragment(search_url):
            continue
        if _looks_like_listing_url(target_url):
            continue
        if competitor != "Apple Oficial" and target_url in used_urls:
            continue
        best_text = " ".join([str(best.get("text", "")), str(best.get("card_text", ""))])
        if not await _safe_goto(page, target_url):
            continue
        if competitor == "Apple Oficial":
            await _select_apple_variant_for_seed(page, seed)

        title = await page.title()
        text = await _extract_visible_text(page)
        if _page_looks_blocked(title, text):
            continue

        if competitor == "Apple Oficial":
            if not _apple_oficial_matches_seed(seed=seed, text=" ".join([title, best_text]), href=target_url):
                continue
        elif not _seed_device_matches_candidate(seed=seed, text=" ".join([title, best_text]), href=target_url):
            continue

        seed_type = _seed_device_type(seed)
        apple_exact_capacity = False
        offers: list[dict] = []
        capacity: int | None = None
        if competitor == "Apple Oficial" and _is_apple_seed(seed):
            capacity_offers = await _extract_apple_capacity_offer_map(page)
            if seed.capacity_gb:
                exact = capacity_offers.get(seed.capacity_gb) or []
                if exact:
                    offers = exact
                    capacity = seed.capacity_gb
                    apple_exact_capacity = True
                elif capacity_offers:
                    # Product exists, but requested GB variant is not available in official selector.
                    continue
            elif capacity_offers:
                chosen_capacity = min(capacity_offers.keys())
                offers = capacity_offers[chosen_capacity]
                capacity = chosen_capacity
                apple_exact_capacity = True

        if not offers:
            offers = _extract_offer_prices(text)
            if not offers and best_text:
                offers = _offers_from_snippet(best_text)
        if not offers:
            continue

        capacity_mix = " ".join([title or "", text[:2200], best_text])
        if capacity is None:
            capacity = _detect_capacity_for_device(capacity_mix, seed_type) or seed.capacity_gb
        if not apple_exact_capacity and competitor == "Apple Oficial" and _is_apple_seed(seed) and seed.capacity_gb:
            # Apple buy pages often render one selected capacity at a time.
            # Once model URL is validated, preserve seed capacity for comparability.
            capacity = seed.capacity_gb
        elif not apple_exact_capacity and seed.capacity_gb and seed_type in {"mobile", "tablet"}:
            observed_caps = _extract_capacity_values(capacity_mix)
            if observed_caps and seed.capacity_gb not in observed_caps:
                continue
            if observed_caps:
                capacity = seed.capacity_gb
        elif not apple_exact_capacity and seed.capacity_gb and capacity and capacity != seed.capacity_gb:
            continue

        in_stock = detect_stock_state(text)
        quality_tier = "apple_oficial_adapter_live" if competitor == "Apple Oficial" else "raw_first_visible_live"
        for offer in offers:
            records.append(
                _record_from_offer(
                    competitor=competitor,
                    seed=seed,
                    source_url=target_url,
                    source_title=title,
                    in_stock=in_stock,
                    capacity=capacity,
                    offer=offer,
                    quality_tier=quality_tier,
                )
            )
        if competitor != "Apple Oficial":
            used_urls.add(target_url)
        await asyncio.sleep(0.8)

    await context.close()
    return records


async def scrape_prices_for_competitor(
    browser: Browser,
    request_context: APIRequestContext,
    competitor: str,
    seeds: list[ProductSeed],
    brand: str,
) -> list[PriceRecord]:
    if competitor != "Santander Boutique":
        seeds = _unique_matching_seeds(seeds)

    brand_n = normalize_text(brand)
    if brand_n != "samsung":
        if competitor == "Santander Boutique":
            return await _scrape_santander_prices(browser=browser, request_context=request_context, seeds=seeds)
        if competitor == "Amazon":
            return await _scrape_amazon_prices(browser=browser, seeds=seeds)
        if competitor == "Media Markt":
            return await _scrape_mediamarkt_prices(browser=browser, seeds=seeds)
        if competitor == "Grover":
            return await _scrape_grover_prices(browser=browser, seeds=seeds)
        if competitor == "Movistar":
            return await _scrape_movistar_prices(browser=browser, seeds=seeds)
        if competitor == "Rentik":
            return await _scrape_rentik_prices(browser=browser, seeds=seeds)
        if competitor == "Samsung Oficial":
            return []
        if competitor == "Apple Oficial":
            return await _scrape_generic_competitor_prices(browser=browser, competitor=competitor, seeds=seeds)
        return await _scrape_generic_competitor_prices(browser=browser, competitor=competitor, seeds=seeds)

    if competitor == "Santander Boutique":
        return await _scrape_santander_prices(browser=browser, request_context=request_context, seeds=seeds)
    if competitor == "Amazon":
        records = await _scrape_amazon_prices(browser=browser, seeds=seeds)
        return records
    if competitor == "Media Markt":
        records = await _scrape_mediamarkt_prices(browser=browser, seeds=seeds)
        # Do not fallback to generic search-page scraping for Media Markt:
        # it can return unrelated "first visible" prices (wrong model/variant).
        return records
    if competitor == "Fnac":
        records = await _scrape_fnac_prices(browser=browser, seeds=seeds)
        return records if records else await _scrape_generic_competitor_prices(browser=browser, competitor=competitor, seeds=seeds)
    if competitor == "PcComponentes":
        records = await _scrape_pccomponentes_prices(browser=browser, seeds=seeds)
        return records if records else await _scrape_generic_competitor_prices(browser=browser, competitor=competitor, seeds=seeds)
    if competitor == "Grover":
        records = await _scrape_grover_prices(browser=browser, seeds=seeds)
        return records
    if competitor == "Movistar":
        records = await _scrape_movistar_prices(browser=browser, seeds=seeds)
        return records if records else await _scrape_generic_competitor_prices(browser=browser, competitor=competitor, seeds=seeds)
    if competitor == "Rentik":
        records = await _scrape_rentik_prices(browser=browser, seeds=seeds)
        return records
    if competitor == "Samsung Oficial":
        records = await _scrape_samsung_oficial_prices(browser=browser, seeds=seeds)
        return records
    if competitor == "Apple Oficial":
        return []
    return await _scrape_generic_competitor_prices(browser=browser, competitor=competitor, seeds=seeds)


def _coverage_by_model_capacity(records: list[PriceRecord]) -> int:
    return len({(r.device_type, r.model, r.capacity_gb) for r in records})


def _coverage_by_offer(records: list[PriceRecord], offer_type: str) -> int:
    return len({(r.device_type, r.model, r.capacity_gb) for r in records if r.offer_type == offer_type})


def _prioritize_santander_first(competitors: list[str]) -> list[str]:
    # Keep user order but ensure base extraction happens first when included.
    ordered: list[str] = []
    for name in competitors:
        if name not in ordered:
            ordered.append(name)
    if "Santander Boutique" not in ordered:
        return ordered
    return ["Santander Boutique"] + [name for name in ordered if name != "Santander Boutique"]


def _dedupe_price_records(records: list[PriceRecord]) -> list[PriceRecord]:
    by_key: dict[tuple, tuple[int, PriceRecord]] = {}
    for idx, r in enumerate(records):
        key = (
            r.retailer,
            r.device_type,
            r.model,
            r.capacity_gb,
            r.offer_type,
            r.term_months,
        )
        current = by_key.get(key)
        if current is None:
            by_key[key] = (idx, r)
            continue
        current_idx, current_record = current
        if float(r.price_value) < float(current_record.price_value):
            by_key[key] = (current_idx, r)

    ordered = sorted(by_key.values(), key=lambda item: item[0])
    return [record for _, record in ordered]


def _should_retry_headed(competitor: str, records: list[PriceRecord], seed_count: int) -> bool:
    model_cov = _coverage_by_model_capacity(records)
    financing_cov = _coverage_by_offer(records, "financing_max_term")
    if competitor == "Media Markt":
        # No penalizar corridas con cobertura ya alta; el retry headed se reserva
        # para bloqueos/parsing roto, no para perseguir el 100% de seeds.
        if model_cov == 0:
            return True
        if financing_cov == 0 and model_cov > 0:
            return True
        return model_cov < max(1, seed_count // 2)
    if competitor == "Fnac":
        # Fnac suele bloquear headless (DataDome), intentamos nuevamente en headed.
        return model_cov == 0 or model_cov < max(1, seed_count // 2)
    if competitor == "PcComponentes":
        # PcComponentes puede cargar shell parcial en headless; reintentar en headed cuando la cobertura sea nula o muy baja.
        return model_cov == 0 or model_cov < max(1, seed_count // 2)
    return False


def _competitor_timeout_seconds(competitor: str, seed_count: int, target_count: int) -> int:
    # Prioritize completeness for full runs; avoid truncating heavy competitors on Apple full catalog.
    if target_count <= 2:
        return 5400
    if competitor in {"Amazon", "Media Markt"}:
        if seed_count >= 30:
            return 7200
        if seed_count >= 15:
            return 3600
    return 1800


async def _run_targets_for_seeds(
    *,
    pw,
    browser: Browser,
    request_context: APIRequestContext,
    seeds: list[ProductSeed],
    brand: str,
    targets: list[str],
    headed: bool,
    base_covered_keys: set[tuple[str, str, int | None]] | None = None,
) -> tuple[list[PriceRecord], set[tuple[str, str, int | None]] | None]:
    records: list[PriceRecord] = []
    covered_keys = base_covered_keys

    for competitor in targets:
        competitor_seeds = seeds
        if competitor != "Santander Boutique" and covered_keys is not None:
            competitor_seeds = [
                seed
                for seed in seeds
                if (_seed_device_type(seed), seed.model, seed.capacity_gb) in covered_keys
            ]
        competitor_timeout_sec = _competitor_timeout_seconds(
            competitor=competitor,
            seed_count=len(competitor_seeds),
            target_count=len(targets),
        )
        timed_out = False
        try:
            competitor_records = await asyncio.wait_for(
                scrape_prices_for_competitor(
                    browser=browser,
                    request_context=request_context,
                    competitor=competitor,
                    seeds=competitor_seeds,
                    brand=brand,
                ),
                timeout=competitor_timeout_sec,
            )
        except asyncio.TimeoutError:
            timed_out = True
            competitor_records = []
            print(
                f"[SCRAPE] {brand} | {competitor}: TIMEOUT "
                f"after {competitor_timeout_sec}s (seeds={len(competitor_seeds)})"
            )

        if competitor == "Santander Boutique":
            covered_keys = {(r.device_type, r.model, r.capacity_gb) for r in competitor_records}

        # Media Markt y Fnac pueden bloquear headless; reintentamos en headed si la cobertura es parcial.
        if not headed and not timed_out and _should_retry_headed(competitor, competitor_records, len(competitor_seeds)):
            retry_browser = None
            try:
                retry_browser = await pw.chromium.launch(headless=False)
                retry_records = await asyncio.wait_for(
                    scrape_prices_for_competitor(
                        browser=retry_browser,
                        request_context=request_context,
                        competitor=competitor,
                        seeds=competitor_seeds,
                        brand=brand,
                    ),
                    timeout=competitor_timeout_sec,
                )
                competitor_records = _dedupe_price_records(competitor_records + retry_records)
            except Exception:
                pass
            finally:
                if retry_browser:
                    await retry_browser.close()

        records.extend(competitor_records)
        model_cov = _coverage_by_model_capacity(competitor_records)
        print(
            f"[SCRAPE] {brand} | {competitor}: "
            f"seeds={len(competitor_seeds)} records={len(competitor_records)} model_cov={model_cov}"
        )

    return _dedupe_price_records(records), covered_keys


async def run_live_scrape(
    max_products: int,
    brand: str = "Samsung",
    competitors: list[str] | None = None,
    seed_scope: str = SEED_SCOPE_FULL_CATALOG,
    headed: bool = False,
) -> tuple[list[ProductSeed], list[PriceRecord]]:
    targets = _prioritize_santander_first(competitors if competitors else TARGET_COMPETITORS)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed)
        request_context = await pw.request.new_context()

        seeds = await scrape_santander_base_products(
            browser=browser,
            request_context=request_context,
            max_products=max_products,
            brand=brand,
        )
        seeds = _filter_seeds_by_scope(seeds, seed_scope=seed_scope)

        records, _ = await _run_targets_for_seeds(
            pw=pw,
            browser=browser,
            request_context=request_context,
            seeds=seeds,
            brand=brand,
            targets=targets,
            headed=headed,
            base_covered_keys=None,
        )

        await request_context.dispose()
        await browser.close()
        return seeds, records


async def run_live_scrape_from_seeds(
    *,
    seeds: list[ProductSeed],
    brand: str,
    competitors: list[str],
    base_covered_keys: set[tuple[str, str, int | None]] | None = None,
    seed_scope: str = SEED_SCOPE_FULL_CATALOG,
    headed: bool = False,
) -> list[PriceRecord]:
    seeds = _filter_seeds_by_scope(seeds, seed_scope=seed_scope)
    targets = _prioritize_santander_first(competitors)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed)
        request_context = await pw.request.new_context()
        records, _ = await _run_targets_for_seeds(
            pw=pw,
            browser=browser,
            request_context=request_context,
            seeds=seeds,
            brand=brand,
            targets=targets,
            headed=headed,
            base_covered_keys=base_covered_keys,
        )
        await request_context.dispose()
        await browser.close()
        return records

