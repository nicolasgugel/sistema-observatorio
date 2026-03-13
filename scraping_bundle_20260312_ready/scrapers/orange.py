"""
Scraper para Orange Espana.

Estrategia:
- Crawl ligero de categorias publicas de moviles, tablets y portatiles.
- Filtrado de PDPs por marca objetivo directamente desde la URL.
- PDP -> JSON-LD BuyAction para sacar PVP, disponibilidad y nombre normalizado.
- PDP -> bloque visible de financiacion para sacar cuota mensual y plazo maximo.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Iterable, Optional
from urllib.parse import urljoin

from loguru import logger
from scrapling.fetchers import Fetcher

from models.price_row import PriceRow
from scrapers.competitor_base import CompetitorBase

BASE_URL = "https://www.orange.es"
CATEGORY_URLS = (
    f"{BASE_URL}/dispositivos/moviles/financiados",
    f"{BASE_URL}/dispositivos/tablets",
    f"{BASE_URL}/dispositivos/portatiles",
)
DELAY = 1.5
CONCURRENCY = 6

_PRODUCT_PATH_RE = re.compile(
    r"^https://www\.orange\.es/dispositivos/(moviles|tablets|portatiles)/([^/]+)/.+\.html$",
    re.I,
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}


class OrangeScraper(CompetitorBase):
    SOURCE_NAME = "orange"
    RETAILER = "Orange"
    DATA_QUALITY_TIER = "orange_adapter_live"

    def __init__(self, targets: list[dict]):
        super().__init__(targets)
        self._target_brands = {
            str(t.get("brand", "")).strip().lower()
            for t in targets
            if t.get("brand")
        }

    async def scrape(self) -> list[PriceRow]:
        product_urls = await self._collect_product_urls()
        if not product_urls:
            logger.info("[Orange] Sin URLs de producto")
            return []

        logger.info(f"[Orange] {len(product_urls)} PDPs candidatas")
        sem = asyncio.Semaphore(CONCURRENCY)

        async def fetch_one(url: str) -> list[PriceRow]:
            async with sem:
                await asyncio.sleep(DELAY)
                try:
                    response = await asyncio.to_thread(
                        Fetcher.get,
                        url,
                        headers=_HEADERS,
                        stealthy_headers=True,
                        timeout=30,
                    )
                    return self._parse_product_page(response, url)
                except Exception as e:
                    logger.debug(f"[Orange] Error en PDP {url}: {e}")
                    return []

        results = await asyncio.gather(*[fetch_one(url) for url in product_urls])
        rows = [row for result in results for row in result]
        rows = self._dedupe_rows(rows)

        logger.info(f"[Orange] Total: {len(rows)} filas")
        return rows

    async def _collect_product_urls(self) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()

        async def fetch_listing(listing_url: str) -> list[str]:
            try:
                response = await asyncio.to_thread(
                    Fetcher.get,
                    listing_url,
                    headers=_HEADERS,
                    stealthy_headers=True,
                    timeout=30,
                )
                return self._extract_product_urls(response, listing_url)
            except Exception as e:
                logger.debug(f"[Orange] Error en listing {listing_url}: {e}")
                return []

        results = await asyncio.gather(*[fetch_listing(url) for url in CATEGORY_URLS])
        for batch in results:
            for url in batch:
                if url in seen:
                    continue
                seen.add(url)
                urls.append(url)
        return urls

    def _extract_product_urls(self, response, source_url: str) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()

        for href in response.css("a::attr(href)").getall():
            full_url = urljoin(source_url, str(href).strip())
            match = _PRODUCT_PATH_RE.match(full_url)
            if not match:
                continue
            brand_slug = match.group(2).lower()
            if self._target_brands and brand_slug not in self._target_brands:
                continue
            if full_url in seen:
                continue
            seen.add(full_url)
            urls.append(full_url)

        return urls

    def _parse_product_page(self, response, source_url: str) -> list[PriceRow]:
        payload = self._extract_buy_action_payload(response)
        if not payload:
            logger.debug(f"[Orange] Sin BuyAction JSON-LD en {source_url}")
            return []

        product = payload.get("object", {})
        offers = product.get("offers", {})
        schema_name = str(product.get("name") or "").strip()
        schema_desc = str(product.get("description") or "").strip()
        page_title = str(response.css("title::text").get() or "").strip()
        source_title = schema_desc or schema_name or page_title
        probe_name = " ".join(p for p in (schema_desc, schema_name) if p).strip() or page_title
        capacity_gb = self._parse_capacity(probe_name)

        target = self._match_target_orange(probe_name, capacity_gb)
        if not target:
            return []
        if self._has_connectivity_mismatch(target, probe_name):
            logger.debug(f"[Orange] Mismatch conectividad: {target['model']} <- {probe_name}")
            return []

        rows: list[PriceRow] = []
        price_value = self._coerce_float(offers.get("price"))
        availability = str(offers.get("availability") or "")
        in_stock = availability.endswith("InStock")

        if price_value and price_value > 0:
            rows.append(
                self._make_row(
                    target=target,
                    offer_type="cash",
                    price_value=price_value,
                    term_months=None,
                    source_url=source_url,
                    source_title=source_title,
                    in_stock=in_stock,
                )
            )

        financing_row = self._build_financing_row(
            response=response,
            target=target,
            source_url=source_url,
            source_title=source_title,
            in_stock=in_stock,
        )
        if financing_row:
            rows.append(financing_row)

        return rows

    def _match_target_orange(
        self,
        probe_name: str,
        capacity_gb: Optional[int],
        threshold: int = 60,
    ) -> Optional[dict]:
        best_target = None
        best_score = 0

        for target in self.targets:
            t_cap = target.get("capacity_gb")
            if capacity_gb and t_cap and int(capacity_gb) != int(t_cap):
                continue

            score = self._score_name_against_target(probe_name, target, capacity_gb)
            if score > best_score:
                best_score = score
                best_target = target

        if best_score >= threshold:
            return best_target
        return None

    @staticmethod
    def _extract_buy_action_payload(response) -> Optional[dict]:
        for raw_script in response.css('script[type="application/ld+json"]::text').getall():
            try:
                data = json.loads(str(raw_script))
            except Exception:
                continue

            for item in OrangeScraper._iter_json_ld_items(data):
                if not isinstance(item, dict):
                    continue
                if str(item.get("@type") or "").lower() != "buyaction":
                    continue
                product = item.get("object")
                if isinstance(product, dict):
                    return item

        return None

    @staticmethod
    def _iter_json_ld_items(data) -> Iterable[dict]:
        if isinstance(data, dict):
            yield data
            return
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item

    def _build_financing_row(
        self,
        response,
        target: dict,
        source_url: str,
        source_title: str,
        in_stock: bool,
    ) -> Optional[PriceRow]:
        term_months = self._extract_term_months(response)
        if not term_months:
            return None

        monthly = self._extract_monthly_price(response)
        total = self._extract_total_financed(response)
        if (not monthly or monthly <= 0) and total and total > 0:
            monthly = round(total / term_months, 2)

        if not monthly or monthly <= 0:
            return None

        return self._make_row(
            target=target,
            offer_type="financing_max_term",
            price_value=monthly,
            term_months=term_months,
            source_url=source_url,
            source_title=source_title,
            in_stock=in_stock,
        )

    @staticmethod
    def _extract_term_months(response) -> Optional[int]:
        for text in response.css(".js-product-payment-payments-text strong::text").getall():
            match = re.search(r"(\d+)\s+plazos", str(text), re.I)
            if match:
                return int(match.group(1))
        return None

    @staticmethod
    def _extract_monthly_price(response) -> Optional[float]:
        selectors = (
            ".js-product-price .js-product-payment-initial-plazo-payment hl-price-block",
            ".js-product-price hl-price-block",
        )
        for selector in selectors:
            for block in response.css(selector):
                monthly = OrangeScraper._price_from_block(block)
                if monthly and monthly > 0:
                    return monthly
        return None

    @staticmethod
    def _price_from_block(block) -> Optional[float]:
        unit = re.sub(r"[^\d]", "", str(block.attrib.get("unit", "")))
        dec = re.sub(r"[^\d]", "", str(block.attrib.get("dec", "")))
        if not unit:
            return None
        text = unit if not dec else f"{unit}.{dec}"
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _extract_total_financed(response) -> Optional[float]:
        for text in response.css(".js-product-price strong::text").getall():
            normalized = str(text).strip().replace("\xa0", " ")
            if "Total en" not in normalized:
                continue
            total = OrangeScraper._clean_price(normalized)
            if total and total > 0:
                return total
        return None

    @staticmethod
    def _coerce_float(value) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _has_connectivity_mismatch(self, target: dict, probe_name: str) -> bool:
        target_sig = self._connectivity_signature(target.get("model", ""))
        page_sig = self._connectivity_signature(probe_name)

        if target_sig == "wifi" and page_sig in {"cellular", "wifi_cellular"}:
            return True
        if target_sig in {"cellular", "wifi_cellular"} and page_sig == "wifi":
            return True
        return False

    @staticmethod
    def _connectivity_signature(text: str) -> Optional[str]:
        normalized = str(text or "").lower()
        has_wifi = bool(re.search(r"\bwi[\s-]?fi\b", normalized, re.I))
        has_cellular = any(token in normalized for token in ("cellular", "celular"))
        has_5g = bool(re.search(r"\b5g\b", normalized, re.I))

        if has_wifi and (has_cellular or has_5g):
            return "wifi_cellular"
        if has_cellular or has_5g:
            return "cellular"
        if has_wifi:
            return "wifi"
        return None

    @staticmethod
    def _dedupe_rows(rows: list[PriceRow]) -> list[PriceRow]:
        dedup: dict[tuple, PriceRow] = {}
        for row in rows:
            key = (
                row.model,
                row.capacity_gb,
                row.offer_type,
                row.term_months,
                row.source_url,
            )
            dedup[key] = row
        return list(dedup.values())
