from __future__ import annotations

import re
import unicodedata


EURO_PRICE_RE = re.compile(r"(\d{1,5}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s*€")
GB_RE = re.compile(r"(\d{2,4})\s*(gb|tb)\b", flags=re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"\s+", " ", value)
    return value.strip().lower()


def parse_euro_to_float(raw: str) -> float | None:
    s = raw.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def find_first_price(text: str) -> tuple[str, float] | None:
    match = EURO_PRICE_RE.search(text)
    if not match:
        return None
    value = parse_euro_to_float(match.group(1))
    if value is None:
        return None
    return match.group(0), value


def find_price_after_keywords(text: str, keywords: tuple[str, ...], window: int = 500) -> tuple[str, float] | None:
    text_n = normalize_text(text)
    for keyword in keywords:
        idx = text_n.find(normalize_text(keyword))
        if idx < 0:
            continue
        segment = text[idx : idx + window]
        price = find_first_price(segment)
        if price:
            return price
    return None


def detect_capacity_gb(text: str) -> int | None:
    matches = GB_RE.findall(text)
    if not matches:
        return None
    parsed: list[int] = []
    for amount, unit in matches:
        cap = int(amount)
        if unit.lower() == "tb":
            cap *= 1024
        parsed.append(cap)
    if not parsed:
        return None
    return min(parsed)


def detect_stock_state(text: str) -> bool | None:
    text_n = normalize_text(text)
    if any(token in text_n for token in ("agotado", "sin stock", "no disponible", "sale proximamente", "proximamente")):
        return False
    if any(token in text_n for token in ("en stock", "disponible", "anadir al carrito", "agregar al carrito")):
        return True
    return None


def strip_html_tags(value: str) -> str:
    return HTML_TAG_RE.sub("", value or "").strip()
