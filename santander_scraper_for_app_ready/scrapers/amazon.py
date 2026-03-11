"""
Scraper para Amazon.es.

Estrategia:
- Busqueda por producto: una query por cada target (model + capacity)
- Fetcher (curl/TLS fingerprint)
- Extrae el mejor resultado relevante de la pagina de busqueda
- Output: cash (precio de compra)
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional
from urllib.parse import quote_plus

from loguru import logger
from scrapling.fetchers import Fetcher

from models.price_row import PriceRow
from scrapers.competitor_base import CompetitorBase

BASE_URL = "https://www.amazon.es"
ELECTRONICS_NODE = "3944681031"
DELAY = 2.0
RETRY_DELAY = 1.0
CONCURRENCY = 5
MAX_RESULTS = 3
MAX_TARGET_ATTEMPTS = 2

_NON_NEW_KEYWORDS = (
    "reacondicionado",
    "renewed",
    "refurbished",
    "usado",
)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}


class AmazonScraper(CompetitorBase):
    SOURCE_NAME = "amazon"
    RETAILER = "Amazon"
    DATA_QUALITY_TIER = "amazon_adapter_live"

    async def scrape(self) -> list[PriceRow]:
        rows: list[PriceRow] = []
        fetcher = Fetcher

        seen = set()
        unique_targets = []
        for target in self.targets:
            key = (target["model"], target.get("capacity_gb"))
            if key in seen:
                continue
            seen.add(key)
            unique_targets.append(target)

        logger.info(f"[Amazon] {len(unique_targets)} productos a buscar")

        sem = asyncio.Semaphore(CONCURRENCY)

        async def fetch_one(target: dict):
            async with sem:
                queries = self._build_queries(target)
                logger.debug(f"[Amazon] Buscando: {queries!r}")
                result = None
                for attempt in range(1, MAX_TARGET_ATTEMPTS + 1):
                    result = await self._search_product(fetcher, queries, target)
                    if result:
                        break
                    if attempt < MAX_TARGET_ATTEMPTS:
                        logger.debug(
                            f"[Amazon] Reintento {attempt + 1}/{MAX_TARGET_ATTEMPTS} para "
                            f"{target['model']} {target.get('capacity_gb') or ''}".strip()
                        )
                        await asyncio.sleep(RETRY_DELAY)
                await asyncio.sleep(DELAY)
                return result

        results = await asyncio.gather(*[fetch_one(t) for t in unique_targets])
        rows = [row for row in results if row]

        logger.info(f"[Amazon] Total: {len(rows)} filas")
        return rows

    @staticmethod
    def _build_query(target: dict) -> str:
        model = target["model"]
        cap = target.get("capacity_gb")
        if cap:
            return f"{model} {cap}GB"
        return model

    @classmethod
    def _build_queries(cls, target: dict) -> list[str]:
        model = target["model"]
        variants: list[str] = [model]

        if " 5G" in model:
            variants.append(model.replace(" 5G", ""))

        current_variants = list(variants)
        for variant in current_variants:
            if "+" in variant:
                variants.append(variant.replace("+", " Plus"))
            if "Wi Fi" in variant:
                variants.append(variant.replace("Wi Fi", "WiFi"))
                variants.append(variant.replace("Wi Fi", "Wi-Fi"))
            if "+ Cell" in variant:
                variants.append(variant.replace("+ Cell", "Cellular"))
                variants.append(variant.replace("+ Cell", "Celular"))
                variants.append(variant.replace("+ Cell", "5G"))
            if "Galaxy Book" in variant:
                variants.append(variant.replace("Galaxy Book", "Book"))
            if "15,6 / i5" in variant:
                variants.append(variant.replace("15,6 / i5", "15.6 i5"))
                variants.append(variant.replace("15,6 / i5", "i5 15.6"))

        queries: list[str] = []
        seen: set[str] = set()
        for variant in variants:
            query = cls._build_query({**target, "model": variant})
            if query not in seen:
                seen.add(query)
                queries.append(query)

        product_code = str(target.get("product_code", "") or "").strip()
        if product_code:
            code_variants = [product_code]
            if "_" in product_code:
                code_variants.append(product_code.replace("_", "/"))
                code_variants.append(product_code.split("_", 1)[0])
            for code_query in code_variants:
                if code_query and code_query not in seen:
                    seen.add(code_query)
                    queries.append(code_query)
        return queries

    async def _search_product(
        self,
        fetcher: Fetcher,
        queries: list[str],
        target: dict,
    ) -> Optional[PriceRow]:
        for query in queries:
            is_code_query = self._is_code_query(query)
            if is_code_query:
                search_url = f"{BASE_URL}/s?k={quote_plus(query)}"
            else:
                search_url = f"{BASE_URL}/s?k={quote_plus(query)}&rh=n:{ELECTRONICS_NODE}"

            try:
                response = await asyncio.to_thread(fetcher.get, search_url, headers=_HEADERS)
            except Exception as e:
                logger.warning(f"[Amazon] Error buscando {query!r}: {e}")
                continue

            row = self._try_json_data(response, target, search_url)
            if row:
                return row

            row = self._parse_result_cards(
                response=response,
                target=target,
                query=query,
                source_url=search_url,
                threshold=50 if is_code_query else 72,
                code_query=is_code_query,
            )
            if row:
                return row

        return None

    def _try_json_data(self, response, target: dict, source_url: str) -> Optional[PriceRow]:
        try:
            scripts = response.find_all("script")
            for script in scripts:
                text = script.text or ""
                if "amznUncompressedData" in text or '"price"' in text:
                    pass
        except Exception:
            pass
        return None

    def _parse_result_cards(
        self,
        response,
        target: dict,
        query: str,
        source_url: str,
        threshold: int,
        code_query: bool,
    ) -> Optional[PriceRow]:
        try:
            cards = response.css("[data-component-type='s-search-result']")
            if not cards:
                cards = response.css("[data-asin]:not([data-asin=''])")

            best_row: Optional[PriceRow] = None
            best_score = 0
            matched = 0

            for card in cards:
                if matched >= MAX_RESULTS:
                    break

                result = self._parse_card(
                    card=card,
                    target=target,
                    query=query,
                    source_url=source_url,
                    threshold=threshold,
                    code_query=code_query,
                )
                if not result:
                    continue

                row, score = result
                if score > best_score:
                    best_score = score
                    best_row = row
                matched += 1

            if best_row:
                logger.debug(f"[Amazon] Match encontrado para {query!r} (score={best_score})")
            else:
                logger.debug(f"[Amazon] Sin match para {query!r}")

            return best_row

        except Exception as e:
            logger.debug(f"[Amazon] Error parseando resultados: {e}")
            return None

    def _parse_card(
        self,
        card,
        target: dict,
        query: str,
        source_url: str,
        threshold: int,
        code_query: bool,
    ) -> Optional[tuple[PriceRow, int]]:
        try:
            asin = card.attrib.get("data-asin", "")
            if not asin:
                return None

            name = ""
            for span in card.css("h2 span"):
                text = span.text.strip()
                if len(text) > 10:
                    name = text
                    break
            if not name:
                return None

            if self._is_accessory(name):
                return None
            if self._is_non_new(name):
                return None
            if code_query:
                brand = str(target.get("brand", "") or "").lower()
                if brand and brand not in name.lower():
                    return None

            price = self._extract_amazon_price(card)
            if not price:
                return None

            capacity = self._parse_capacity(name)
            score = self._score_name_against_target(name, target, capacity)
            if code_query and self._title_contains_code(name, query):
                score = max(score, 100)
            if score < threshold:
                return None

            product_url = f"{BASE_URL}/dp/{asin}"
            oos_el = self._css_first(card, "[class*='unavailable'], [class*='out-of-stock']")
            in_stock = oos_el is None

            row = self._make_row(
                target=target,
                offer_type="cash",
                price_value=price,
                term_months=None,
                source_url=product_url,
                source_title=name,
                in_stock=in_stock,
            )
            return row, score

        except Exception as e:
            logger.debug(f"[Amazon] Error parseando card: {e}")
            return None

    def _extract_amazon_price(self, card) -> Optional[float]:
        whole_el = self._css_first(card, ".a-price-whole")
        fraction_el = self._css_first(card, ".a-price-fraction")
        if whole_el:
            whole = re.sub(r"[^\d]", "", whole_el.text)
            fraction = re.sub(r"[^\d]", "", fraction_el.text) if fraction_el else "00"
            if whole:
                try:
                    return float(f"{whole}.{fraction[:2]}")
                except ValueError:
                    pass

        offscreen_el = self._css_first(card, ".a-offscreen")
        if offscreen_el:
            text = offscreen_el.text.strip()
            text = re.sub(r"[€$£\s]", "", text)
            if re.search(r"\d\.\d{3},\d", text):
                text = text.replace(".", "").replace(",", ".")
            elif "," in text:
                text = text.replace(",", ".")
            try:
                return float(re.sub(r"[^\d.]", "", text))
            except ValueError:
                pass

        return None

    @staticmethod
    def _is_code_query(query: str) -> bool:
        q = str(query or "").strip()
        if not q or " " in q:
            return False
        return bool(re.search(r"[a-z]", q, flags=re.I) and re.search(r"\d", q))

    @staticmethod
    def _is_non_new(name: str) -> bool:
        lowered = name.lower()
        return any(keyword in lowered for keyword in _NON_NEW_KEYWORDS)

    @staticmethod
    def _title_contains_code(title: str, query: str) -> bool:
        title_key = re.sub(r"[^a-z0-9]", "", title.lower())
        query_key = re.sub(r"[^a-z0-9]", "", str(query or "").lower())
        return bool(query_key and query_key in title_key)
