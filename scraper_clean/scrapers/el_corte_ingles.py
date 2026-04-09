"""
Scraper para El Corte Ingles (elcorteingles.es).

Estrategia:
- Busqueda por producto contra la API JSON usada por el frontend.
- Parseo de variantes internas por color/capacidad para no mezclar 128/256/512.
- Match fuzzy contra targets de Santander.
- Output: cash y financing_max_term cuando la promo indique "sin intereses".
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional
from urllib.parse import quote_plus, urlencode, urljoin

from loguru import logger
from scrapling.fetchers import Fetcher

from models.price_row import PriceRow
from scrapers.competitor_base import CompetitorBase

BASE_URL = "https://www.elcorteingles.es"
SEARCH_API_URL = f"{BASE_URL}/api/firefly/vuestore/new-search/1/"
DELAY = 1.2
RETRY_DELAY = 0.8
CONCURRENCY = 5
MAX_TARGET_ATTEMPTS = 1
MATCH_THRESHOLD = 72

_NON_NEW_KEYWORDS = (
    "reacondicionado",
    "refurbished",
    "renewed",
    "segunda mano",
)
_ECI_ACCESSORY_KEYWORDS = (
    "tarjeta interactiva",
)

_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


class ElCorteInglesScraper(CompetitorBase):
    SOURCE_NAME = "el_corte_ingles"
    RETAILER = "El Corte Ingles"
    DATA_QUALITY_TIER = "el_corte_ingles_adapter_live"

    async def scrape(self) -> list[PriceRow]:
        seen: set[tuple[str, Optional[int]]] = set()
        unique_targets: list[dict] = []
        for target in self.targets:
            key = (target["model"], target.get("capacity_gb"))
            if key in seen:
                continue
            seen.add(key)
            unique_targets.append(target)

        logger.info(f"[ECI] {len(unique_targets)} productos a buscar")
        sem = asyncio.Semaphore(CONCURRENCY)

        async def fetch_one(target: dict) -> list[PriceRow]:
            async with sem:
                result = await self._search_target(target)
                await asyncio.sleep(DELAY)
                return result

        results = await asyncio.gather(*[fetch_one(target) for target in unique_targets])
        rows = [row for batch in results for row in batch]
        rows = self._dedupe_rows(rows)

        logger.info(f"[ECI] Total: {len(rows)} filas")
        return rows

    async def _search_target(self, target: dict) -> list[PriceRow]:
        queries = self._build_queries(target)
        logger.debug(f"[ECI] Buscando {target['model']} -> {queries!r}")

        for attempt in range(1, MAX_TARGET_ATTEMPTS + 1):
            for query in queries:
                rows = await self._run_search_query(query, target)
                if rows:
                    return rows
            if attempt < MAX_TARGET_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY)

        logger.debug(
            f"[ECI] Sin match para {target['model']} "
            f"{target.get('capacity_gb') or ''}".strip()
        )
        return []

    async def _run_search_query(self, query: str, target: dict) -> list[PriceRow]:
        params = {
            "s": query,
            "stype": "text_box",
            "isBookSearch": "false",
            "isMultiSearchCategory": "false",
        }
        api_url = f"{SEARCH_API_URL}?{urlencode(params)}"
        referer = f"{BASE_URL}/search-nwx/?s={quote_plus(query)}&stype=text_box"

        try:
            response = await asyncio.to_thread(
                Fetcher.get,
                api_url,
                headers={**_HEADERS, "Referer": referer},
                stealthy_headers=True,
                timeout=30,
            )
            payload = response.json()
        except Exception as e:
            logger.debug(f"[ECI] Error buscando {query!r}: {e}")
            return []

        products = self._extract_products(payload)
        if not products:
            return []

        best_rows: list[PriceRow] = []
        best_key: Optional[tuple[int, int, float]] = None

        for product in products:
            candidate = self._pick_best_variant(product, target)
            if not candidate:
                continue

            score, cash_row, financing_row = candidate
            rank_key = (score, 1 if cash_row.in_stock else 0, -cash_row.price_value)
            if best_key is None or rank_key > best_key:
                best_key = rank_key
                best_rows = [cash_row]
                if financing_row:
                    best_rows.append(financing_row)

        return best_rows

    @classmethod
    def _extract_products(cls, payload: dict) -> list[dict]:
        raw_products = payload.get("data", {}).get("products", [])
        products: list[dict] = []
        for product in raw_products:
            if not isinstance(product, dict):
                continue
            if not product.get("title") or not product.get("_uri"):
                continue
            if cls._is_marketplace_product(product):
                continue
            products.append(product)
        return products

    def _pick_best_variant(
        self,
        product: dict,
        target: dict,
    ) -> Optional[tuple[int, PriceRow, Optional[PriceRow]]]:
        product_title = str(product.get("title") or "").strip()
        if (
            not product_title
            or self._is_non_new(product_title)
            or self._is_accessory(product_title)
            or self._is_eci_accessory(product_title)
        ):
            return None

        product_brand = str((product.get("brand") or {}).get("name") or "").strip().lower()
        target_brand = str(target.get("brand") or "").strip().lower()
        if target_brand and product_brand and product_brand != target_brand:
            return None

        source_url = urljoin(BASE_URL, str(product.get("_canonical") or product.get("_uri") or "").strip())
        color_groups = product.get("_my_colors") or [{}]

        best_candidate: Optional[tuple[int, PriceRow, Optional[PriceRow]]] = None
        best_key: Optional[tuple[int, int, float]] = None

        for color in color_groups:
            variants = color.get("variants") or [None]
            for variant in variants:
                candidate_name = self._build_candidate_name(product_title, variant)
                if (
                    self._is_non_new(candidate_name)
                    or self._is_accessory(candidate_name)
                    or self._is_eci_accessory(candidate_name)
                ):
                    continue
                if self._has_connectivity_mismatch(target, candidate_name):
                    continue

                capacity_gb = self._parse_capacity(candidate_name)
                price_value = self._extract_price(product, variant)
                if not price_value or price_value <= 0:
                    continue

                score = self._score_name_against_target(candidate_name, target, capacity_gb)
                if score < MATCH_THRESHOLD:
                    continue

                status = str(
                    (variant or {}).get("status")
                    or color.get("status")
                    or product.get("_status")
                    or ""
                ).strip()
                in_stock = self._status_is_available(status)

                cash_row = self._make_row(
                    target=target,
                    offer_type="cash",
                    price_value=price_value,
                    term_months=None,
                    source_url=source_url,
                    source_title=candidate_name,
                    in_stock=in_stock,
                )

                financing_row = None
                financing_term = self._extract_financing_term(variant)
                if financing_term and financing_term > 0:
                    financing_row = self._make_row(
                        target=target,
                        offer_type="financing_max_term",
                        price_value=round(price_value / financing_term, 2),
                        term_months=financing_term,
                        source_url=source_url,
                        source_title=candidate_name,
                        in_stock=in_stock,
                    )

                rank_key = (score, 1 if in_stock else 0, -price_value)
                if best_key is None or rank_key > best_key:
                    best_key = rank_key
                    best_candidate = (score, cash_row, financing_row)

        return best_candidate

    @classmethod
    def _build_queries(cls, target: dict) -> list[str]:
        model = str(target["model"]).strip()
        cap = target.get("capacity_gb")
        variants: list[str] = [model]

        if " 5G" in model:
            variants.append(model.replace(" 5G", ""))
        if "+" in model:
            variants.append(model.replace("+", " Plus"))
        if " Plus" in model:
            variants.append(model.replace(" Plus", "+"))
        if "Wi Fi" in model:
            variants.append(model.replace("Wi Fi", "WiFi"))
            variants.append(model.replace("Wi Fi", "Wi-Fi"))
        if "+ Cell" in model:
            variants.append(model.replace("+ Cell", "Wi-Fi + 5G"))
            variants.append(model.replace("+ Cell", "5G"))
            variants.append(model.replace("+ Cell", "Cellular"))
        if "Cellular" in model:
            variants.append(model.replace("Cellular", "5G"))
            variants.append(model.replace("Cellular", "Wi-Fi + 5G"))
        if "Galaxy Book" in model:
            variants.append(model.replace("Galaxy Book", "Book"))

        queries: list[str] = []
        seen: set[str] = set()

        for variant in variants:
            variant = variant.strip()
            if not variant:
                continue
            if cap:
                for suffix in (str(cap), f"{cap}GB", f"{cap} GB"):
                    query = f"{variant} {suffix}".strip()
                    if query not in seen:
                        seen.add(query)
                        queries.append(query)
            if variant not in seen:
                seen.add(variant)
                queries.append(variant)

        return queries

    @staticmethod
    def _build_candidate_name(product_title: str, variant: Optional[dict]) -> str:
        name = product_title.strip()
        if not variant:
            return name

        variant_meta = variant.get("variant") or {}
        variant_value = str(variant_meta.get("value") or "").strip()
        if not variant_value or variant_value.lower() == "variante unica":
            return name

        if ElCorteInglesScraper._parse_capacity(name):
            return name

        return f"{name} {variant_value}".strip()

    @staticmethod
    def _extract_price(product: dict, variant: Optional[dict]) -> Optional[float]:
        candidates = []
        if variant:
            candidates.extend([variant.get("sale_price"), variant.get("price")])

        single_sku = product.get("_single_sku") or {}
        candidates.extend([single_sku.get("sale_price"), single_sku.get("price")])

        for value in candidates:
            try:
                price = float(value)
            except (TypeError, ValueError):
                continue
            if price > 0:
                return price
        return None

    @staticmethod
    def _extract_financing_term(variant: Optional[dict]) -> Optional[int]:
        if not variant:
            return None

        promos = []
        promos.extend(variant.get("all_promos") or [])
        promos.extend(variant.get("sku_informativa_promos") or [])

        best_term = 0
        for promo in promos:
            if not isinstance(promo, dict):
                continue
            title = str(promo.get("title") or promo.get("make_up", {}).get("title") or "").strip()
            if "financi" not in title.lower() or "sin intereses" not in title.lower():
                continue
            match = re.search(r"(\d+)\s+mes(?:es)?", title, re.I)
            if match:
                best_term = max(best_term, int(match.group(1)))

        return best_term or None

    @staticmethod
    def _status_is_available(status: str) -> bool:
        normalized = str(status or "").strip().upper()
        return normalized in {"ADD", "RESERVE", "PREORDER"}

    @staticmethod
    def _is_marketplace_product(product: dict) -> bool:
        single_sku = product.get("_single_sku") or {}
        if bool(single_sku.get("marketplace")):
            return True

        providers = product.get("provider") or []
        for provider in providers:
            if not isinstance(provider, dict):
                continue
            if str(provider.get("type") or "").lower() == "mkp":
                return True
        return False

    @staticmethod
    def _is_non_new(name: str) -> bool:
        lowered = name.lower()
        return any(keyword in lowered for keyword in _NON_NEW_KEYWORDS)

    @staticmethod
    def _is_eci_accessory(name: str) -> bool:
        lowered = name.lower()
        return any(keyword in lowered for keyword in _ECI_ACCESSORY_KEYWORDS)

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
                row.retailer_slug,
            )
            dedup[key] = row
        return list(dedup.values())
