from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, Page, async_playwright
from scrapling.fetchers import Fetcher

from app_backend.config import ROOT_DIR
from observatorio.models import ProductSeed
from observatorio.text_utils import normalize_text, parse_euro_to_float


BUNDLE_ROOT = ROOT_DIR / "santander_scraper_bundle_20260325" / "santander_scraper"
if str(BUNDLE_ROOT) not in sys.path:
    sys.path.insert(0, str(BUNDLE_ROOT))

from scrapers.movistar import MovistarScraper  # noqa: E402
from scrapers.orange import OrangeScraper  # noqa: E402

from observatorio.scraper import (  # noqa: E402
    _dedupe_offers,
    _dismiss_mediamarkt_consent,
    _dismiss_samsung_cookie_banner,
    _extract_mediamarkt_cash_offer,
    _extract_mediamarkt_financing_offers,
    _extract_mediamarkt_installment_offers,
    _extract_samsung_offers_from_text,
    _extract_samsung_selected_offer_from_dom,
    _extract_samsung_selected_option_text,
    _extract_visible_text,
    _safe_goto,
    _select_samsung_capacity,
    _select_samsung_model_variant,
)


_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}
_SAMPLE_LIMIT = 3
_MONTHLY_OFFER_TYPES = {
    "financing_max_term",
    "renting_no_insurance",
    "renting_with_insurance",
}


@dataclass(slots=True)
class ValidationResult:
    retailer: str
    runtime_used: str
    status: str
    validated_products: list[dict[str, Any]]
    mismatches: list[str]
    blocked_publication: bool
    evidence_urls: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "retailer": self.retailer,
            "runtime_used": self.runtime_used,
            "status": self.status,
            "validated_products": self.validated_products,
            "mismatches": self.mismatches,
            "blocked_publication": self.blocked_publication,
            "evidence_urls": self.evidence_urls,
        }


def _row_summary(row: dict) -> dict[str, Any]:
    return {
        "brand": str(row.get("brand") or ""),
        "model": str(row.get("model") or ""),
        "capacity_gb": row.get("capacity_gb"),
        "offer_type": str(row.get("offer_type") or ""),
        "price_value": row.get("price_value"),
        "term_months": row.get("term_months"),
        "source_url": str(row.get("source_url") or ""),
    }


def _target_from_row(row: dict) -> dict[str, Any]:
    return {
        "brand": str(row.get("brand") or ""),
        "model": str(row.get("model") or ""),
        "capacity_gb": row.get("capacity_gb"),
        "product_code": str(row.get("product_code") or ""),
        "device_type": str(row.get("device_type") or "mobile"),
        "product_family": str(row.get("product_family") or row.get("brand") or ""),
    }


def _seed_from_row(row: dict) -> ProductSeed:
    return ProductSeed(
        brand=str(row.get("brand") or ""),
        model=str(row.get("model") or ""),
        capacity_gb=row.get("capacity_gb"),
        source_url=str(row.get("source_url") or ""),
        device_type=str(row.get("device_type") or "mobile"),
        product_code=str(row.get("product_code") or "") or None,
    )


def _sample_rows(rows: list[dict]) -> list[dict]:
    priority = {
        "financing_max_term": 0,
        "renting_no_insurance": 1,
        "renting_with_insurance": 2,
        "cash": 3,
    }
    seen: set[tuple[str, int | None, str, int | None, str]] = set()
    ordered = sorted(
        rows,
        key=lambda row: (
            priority.get(str(row.get("offer_type") or ""), 9),
            str(row.get("model") or ""),
            int(row.get("capacity_gb") or 0),
        ),
    )
    sampled: list[dict] = []
    for row in ordered:
        key = (
            normalize_text(str(row.get("model") or "")),
            row.get("capacity_gb"),
            normalize_text(str(row.get("offer_type") or "")),
            row.get("term_months"),
            str(row.get("source_url") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        sampled.append(row)
        if len(sampled) >= _SAMPLE_LIMIT:
            break
    return sampled


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _offers_match_row(row: dict, offers: list[dict], *, tolerance: float = 1.0) -> bool:
    row_offer_type = normalize_text(str(row.get("offer_type") or ""))
    row_term = _coerce_int(row.get("term_months"))
    row_price = _coerce_float(row.get("price_value"))
    if row_price is None:
        return False
    for offer in offers:
        if normalize_text(str(offer.get("offer_type") or "")) != row_offer_type:
            continue
        offer_term = _coerce_int(offer.get("term_months"))
        if row_term is not None and offer_term not in {None, row_term}:
            continue
        offer_price = _coerce_float(offer.get("price_value"))
        if offer_price is None:
            continue
        if abs(offer_price - row_price) <= tolerance:
            return True
    return False


def _response_text(response: Any) -> str:
    body = getattr(response, "body", None)
    if isinstance(body, (bytes, bytearray)):
        return body.decode("utf-8", errors="replace")
    if isinstance(body, str) and body:
        return body
    text = getattr(response, "text", None)
    if callable(text):
        try:
            return str(text())
        except Exception:
            return ""
    return str(text or "")


async def _fetch_response(url: str) -> Any | None:
    if not url:
        return None
    try:
        return await asyncio.to_thread(
            Fetcher.get,
            url,
            headers=_FETCH_HEADERS,
            stealthy_headers=True,
            timeout=30,
        )
    except Exception:
        return None


def _price_present_in_text(row: dict, text: str) -> bool:
    if not text:
        return False
    normalized = normalize_text(text)
    if row.get("offer_type") in _MONTHLY_OFFER_TYPES:
        term = row.get("term_months")
        if term is not None and f"{term}" not in normalized:
            return False
        if "mes" not in normalized and "cuota" not in normalized and "plazo" not in normalized:
            return False

    row_price = _coerce_float(row.get("price_value"))
    if row_price is None:
        return False

    for raw in normalized.replace("eur", "€").split():
        value = parse_euro_to_float(raw)
        if value is not None and abs(value - row_price) <= 1.0:
            return True

    import re

    for match in re.finditer(r"(\d{1,5}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s*(?:€|eur)", normalized):
        value = parse_euro_to_float(match.group(1))
        if value is not None and abs(value - row_price) <= 1.0:
            return True
    return False


async def _validate_generic_rows(rows: list[dict]) -> list[str]:
    mismatches: list[str] = []
    for row in rows:
        response = await _fetch_response(str(row.get("source_url") or ""))
        text = _response_text(response) if response is not None else ""
        if not _price_present_in_text(row, text):
            mismatches.append(
                f"{row.get('retailer')}: precio no visible para {row.get('model')} {row.get('capacity_gb') or ''}GB"
            )
    return mismatches


async def _validate_santander_rows(rows: list[dict]) -> list[str]:
    return [] if rows else ["Santander Boutique no devolvio filas."]


async def _validate_movistar_rows(rows: list[dict]) -> list[str]:
    mismatches: list[str] = []
    for row in rows:
        response = await _fetch_response(str(row.get("source_url") or ""))
        if response is None:
            mismatches.append(f"Movistar: no se pudo abrir {row.get('source_url')}")
            continue
        scraper = MovistarScraper(targets=[_target_from_row(row)])
        parsed = scraper._parse_product_page(response, str(row.get("source_url") or ""))
        parsed_offers = [
            {
                "offer_type": item.offer_type,
                "price_value": item.price_value,
                "term_months": item.term_months,
            }
            for item in parsed
        ]
        if not _offers_match_row(row, parsed_offers):
            mismatches.append(f"Movistar: mismatch en {row.get('model')} {row.get('capacity_gb') or ''}GB")
    return mismatches


async def _validate_orange_rows(rows: list[dict]) -> list[str]:
    mismatches: list[str] = []
    for row in rows:
        response = await _fetch_response(str(row.get("source_url") or ""))
        if response is None:
            mismatches.append(f"Orange: no se pudo abrir {row.get('source_url')}")
            continue
        scraper = OrangeScraper(targets=[_target_from_row(row)])
        parsed = scraper._parse_product_page(response, str(row.get("source_url") or ""))
        parsed_offers = [
            {
                "offer_type": item.offer_type,
                "price_value": item.price_value,
                "term_months": item.term_months,
            }
            for item in parsed
        ]
        if not _offers_match_row(row, parsed_offers):
            mismatches.append(f"Orange: mismatch en {row.get('model')} {row.get('capacity_gb') or ''}GB")
    return mismatches


async def _validate_eci_rows(rows: list[dict]) -> list[str]:
    mismatches: list[str] = []
    for row in rows:
        if normalize_text(str(row.get("offer_type") or "")) != "cash":
            mismatches.append("El Corte Ingles: no se valida financiacion en PDP cash-only.")
            continue
        response = await _fetch_response(str(row.get("source_url") or ""))
        text = _response_text(response) if response is not None else ""
        if not _price_present_in_text(row, text):
            mismatches.append(f"El Corte Ingles: cash no visible en {row.get('model')} {row.get('capacity_gb') or ''}GB")
    return mismatches


async def _extract_mediamarkt_live_offers(page: Page, url: str) -> list[dict]:
    if not await _safe_goto(page, url):
        return []
    await _dismiss_mediamarkt_consent(page)
    page_text = await _extract_visible_text(page)
    offers: list[dict] = []
    cash_offer = await _extract_mediamarkt_cash_offer(page)
    if cash_offer:
        offers.append(cash_offer)
    offers.extend(await _extract_mediamarkt_financing_offers(page, page_text))
    return _dedupe_offers(offers)


async def _validate_mediamarkt_rows(rows: list[dict]) -> list[str]:
    mismatches: list[str] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            offers_by_url: dict[str, list[dict]] = {}
            for row in rows:
                url = str(row.get("source_url") or "")
                if url not in offers_by_url:
                    offers_by_url[url] = await _extract_mediamarkt_live_offers(page, url)
                if not _offers_match_row(row, offers_by_url[url]):
                    mismatches.append(f"Media Markt: mismatch en {row.get('model')} {row.get('capacity_gb') or ''}GB")
        finally:
            await browser.close()
    return mismatches


async def _extract_samsung_live_offers(page: Page, row: dict) -> list[dict]:
    seed = _seed_from_row(row)
    if not await _safe_goto(page, str(row.get("source_url") or "")):
        return []
    await _dismiss_samsung_cookie_banner(page)
    await page.wait_for_timeout(800)
    await _select_samsung_model_variant(page, seed)
    if row.get("capacity_gb"):
        await _select_samsung_capacity(page, int(row["capacity_gb"]))
    selected_text = await _extract_samsung_selected_option_text(page, row.get("capacity_gb"))
    page_text = await _extract_visible_text(page)
    _capacity, offers = await _extract_samsung_selected_offer_from_dom(page, row.get("capacity_gb"))
    if offers:
        return _dedupe_offers(offers)
    return _dedupe_offers(_extract_samsung_offers_from_text(" ".join([selected_text, page_text[:7000]])))


async def _validate_samsung_rows(rows: list[dict]) -> list[str]:
    mismatches: list[str] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            for row in rows:
                offers = await _extract_samsung_live_offers(page, row)
                if not _offers_match_row(row, offers):
                    mismatches.append(f"Samsung Oficial: mismatch en {row.get('model')} {row.get('capacity_gb') or ''}GB")
        finally:
            await browser.close()
    return mismatches


async def validate_retailer_rows(
    retailer: str,
    rows: list[dict],
    *,
    runtime_used: str,
    mode: str,
) -> dict[str, Any]:
    normalized_retailer = normalize_text(retailer)
    sampled_rows = _sample_rows(rows)
    evidence_urls = [str(row.get("source_url") or "") for row in sampled_rows if str(row.get("source_url") or "")]

    if not rows:
        blocked = mode != "targeted"
        result = ValidationResult(
            retailer=retailer,
            runtime_used=runtime_used,
            status="failed" if blocked else "passed",
            validated_products=[],
            mismatches=["No se capturaron filas nuevas."] if blocked else [],
            blocked_publication=blocked,
            evidence_urls=[],
        )
        return result.to_dict()

    if normalized_retailer == "santander boutique":
        mismatches = await _validate_santander_rows(sampled_rows)
    elif normalized_retailer == "media markt":
        mismatches = await _validate_mediamarkt_rows(sampled_rows)
    elif normalized_retailer == "samsung oficial":
        mismatches = await _validate_samsung_rows(sampled_rows)
    elif normalized_retailer == "movistar":
        mismatches = await _validate_movistar_rows(sampled_rows)
    elif normalized_retailer == "orange":
        mismatches = await _validate_orange_rows(sampled_rows)
    elif normalized_retailer == "el corte ingles":
        mismatches = await _validate_eci_rows(sampled_rows)
    else:
        mismatches = await _validate_generic_rows(sampled_rows)

    blocked = bool(mismatches)
    result = ValidationResult(
        retailer=retailer,
        runtime_used=runtime_used,
        status="failed" if blocked else "passed",
        validated_products=[_row_summary(row) for row in sampled_rows],
        mismatches=mismatches,
        blocked_publication=blocked,
        evidence_urls=evidence_urls,
    )
    return result.to_dict()
