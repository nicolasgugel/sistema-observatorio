"""
Scraper para Samsung Store España (samsung.com/es).

Estrategia:
- Fetch de páginas de categoría (Galaxy S, A, Z, Book, Tab)
- Samsung embebe datos en scripts JSON (__NEXT_DATA__ o window._data)
- Fallback a JSON-LD y HTML de tarjetas
- Fuzzy match contra targets de Santander
- Output: cash (precio de compra oficial Samsung)

Usa StealthyFetcher (Camoufox) para manejar anti-bot de Samsung.
"""
from __future__ import annotations
import asyncio
import json
import re
from typing import Optional
from urllib.parse import urlparse, urlunparse

from loguru import logger
from scrapling.fetchers import StealthyFetcher

from models.price_row import PriceRow
from scrapers.competitor_base import CompetitorBase

BASE_URL = "https://www.samsung.com"

# Páginas de categoría Samsung España
CATEGORY_URLS = [
    f"{BASE_URL}/es/smartphones/galaxy-s/",
    f"{BASE_URL}/es/smartphones/galaxy-a/",
    f"{BASE_URL}/es/smartphones/galaxy-z/",
    f"{BASE_URL}/es/tablets/galaxy-tab-s/",
    f"{BASE_URL}/es/tablets/galaxy-tab-a/",
    f"{BASE_URL}/es/computers/galaxy-book/",
]

DELAY = 3.0
PRODUCT_DELAY = 1.2


class SamsungStoreScraper(CompetitorBase):
    SOURCE_NAME = "samsung_store"
    RETAILER = "Samsung Store"
    DATA_QUALITY_TIER = "samsung_adapter_live"

    async def scrape(self) -> list[PriceRow]:
        rows: list[PriceRow] = []
        fetcher = StealthyFetcher

        # Solo procesar si hay targets Samsung
        samsung_targets = [t for t in self.targets if t.get("brand", "").lower() == "samsung"]
        if not samsung_targets:
            logger.info("[Samsung Store] Sin targets Samsung — omitiendo")
            return []

        logger.info(f"[Samsung Store] {len(samsung_targets)} targets Samsung")

        sem = asyncio.Semaphore(2)  # max 2 browsers simultáneos (anti-bot Samsung)

        async def fetch_category(url: str) -> list[PriceRow]:
            async with sem:
                logger.info(f"[Samsung Store] Fetching: {url}")
                try:
                    response = await fetcher.async_fetch(url, google_search=True)
                    page_rows = self._parse_page(response, samsung_targets, url)
                    logger.info(f"[Samsung Store] {url.split('/')[-2]}: {len(page_rows)} filas")
                    return page_rows
                except Exception as e:
                    logger.error(f"[Samsung Store] Error en {url}: {e}")
                    return []

        results = await asyncio.gather(*[fetch_category(url) for url in CATEGORY_URLS])
        for page_rows in results:
            rows.extend(page_rows)

        financing_rows = await self._build_financing_rows(fetcher, rows)
        if financing_rows:
            rows.extend(financing_rows)
            logger.info(f"[Samsung Store] Financiacion: +{len(financing_rows)} filas")

        deduped = self._dedupe_rows(rows)
        logger.info(f"[Samsung Store] Total: {len(rows)} filas ({len(deduped)} tras dedupe)")
        return deduped

    # ------------------------------------------------------------------ #
    # Parseo                                                               #
    # ------------------------------------------------------------------ #

    def _parse_page(self, response, targets: list[dict], source_url: str) -> list[PriceRow]:
        """Intenta varias estrategias de extracción."""
        rows = self._try_next_data(response, targets, source_url)
        if not rows:
            rows = self._try_json_ld(response, targets, source_url)
        if not rows:
            rows = self._try_window_data(response, targets, source_url)
        if not rows:
            rows = self._parse_html(response, targets, source_url)
        return rows

    async def _build_financing_rows(self, fetcher, rows: list[PriceRow]) -> list[PriceRow]:
        """
        Genera filas financing_max_term a partir de filas cash.
        Samsung España ofrece financiación al 0% en 36 meses (cuota = precio / 36).
        """
        financing_rows: list[PriceRow] = []
        for row in rows:
            if row.offer_type != "cash" or not row.price_value:
                continue
            monthly = round(float(row.price_value) / 36, 2)
            target = {
                "product_family": row.product_family,
                "brand": row.brand,
                "device_type": row.device_type,
                "model": row.model,
                "capacity_gb": row.capacity_gb,
                "product_code": row.product_code,
            }
            financing_rows.append(
                self._make_row(
                    target=target,
                    offer_type="financing_max_term",
                    price_value=monthly,
                    term_months=36,
                    source_url=row.source_url,
                    source_title=row.source_title,
                )
            )
        return financing_rows

    def _try_next_data(self, response, targets: list[dict], source_url: str) -> list[PriceRow]:
        """Extrae de __NEXT_DATA__ Next.js."""
        rows: list[PriceRow] = []
        try:
            script = response.find("script", {"id": "__NEXT_DATA__"})
            if not script:
                return []
            data = json.loads(script.text)
            items = self._drill_products(data)
            for item in items:
                row = self._parse_item(item, targets, source_url)
                if row:
                    rows.append(row)
        except Exception as e:
            logger.debug(f"[Samsung Store] __NEXT_DATA__ error: {e}")
        return rows

    def _try_json_ld(self, response, targets: list[dict], source_url: str) -> list[PriceRow]:
        """Extrae de JSON-LD schema.org."""
        rows: list[PriceRow] = []
        try:
            scripts = response.find_all("script", {"type": "application/ld+json"})
            for script in scripts:
                try:
                    data = json.loads(script.text)
                    items = []
                    if isinstance(data, list):
                        items = data
                    elif data.get("@type") == "ItemList":
                        items = [el.get("item", el) for el in data.get("itemListElement", [])]
                    elif data.get("@type") == "Product":
                        items = [data]

                    for item in items:
                        row = self._parse_schema_item(item, targets, source_url)
                        if row:
                            rows.append(row)
                except Exception:
                    continue
        except Exception:
            pass
        return rows

    def _try_window_data(self, response, targets: list[dict], source_url: str) -> list[PriceRow]:
        """Busca datos de producto en scripts de window._data o dataLayer de Samsung."""
        rows: list[PriceRow] = []
        try:
            scripts = response.find_all("script")
            for script in scripts:
                text = script.text or ""
                # Samsung usa window._data o dataLayer con datos de producto
                if "modelName" not in text and "modelCode" not in text:
                    continue

                # Intentar extraer objetos de producto del script
                # Patrón: {"modelName":"...", ... "price":...}
                matches = re.finditer(
                    r'"modelName"\s*:\s*"([^"]+)"[^}]*?"price"\s*:\s*([\d.]+)',
                    text,
                    re.DOTALL,
                )
                for m in matches:
                    name = m.group(1)
                    try:
                        price = float(m.group(2))
                    except ValueError:
                        continue
                    if not name or not price:
                        continue
                    capacity = self._parse_capacity(name)
                    target = self._match_target(
                        name,
                        capacity,
                        strict_variant=True,
                    )
                    if target:
                        rows.append(self._make_row(
                            target=target,
                            offer_type="cash",
                            price_value=price,
                            term_months=None,
                            source_url=source_url,
                            source_title=name,
                        ))
        except Exception:
            pass
        return rows

    def _parse_html(self, response, targets: list[dict], source_url: str) -> list[PriceRow]:
        """Parseo HTML de tarjetas de la Samsung Store."""
        rows: list[PriceRow] = []
        try:
            selectors = [
                "[class*='product-card']",
                "[class*='ProductCard']",
                "[class*='ModelList'] li",
                "[data-modelcode]",
                "li[class*='list-item']",
            ]
            cards = []
            for sel in selectors:
                cards = response.css(sel)
                if cards:
                    break

            for card in cards:
                try:
                    name_el = self._css_first(card, 
                        "[class*='product-name'], [class*='model-name'], "
                        "[class*='card-title'], h3, h2, h4"
                    )
                    price_el = self._css_first(card, 
                        "[class*='price'], [class*='Price'], "
                        "[class*='from-price'], [aria-label*='€']"
                    )
                    if not name_el or not price_el:
                        continue

                    name = name_el.text.strip()
                    price = self._clean_price(price_el.text)
                    if not name or not price:
                        continue

                    link = self._css_first(card, "a[href]")
                    href = self._el_attr(link, "href")
                    product_url = f"{BASE_URL}{href}" if href.startswith("/") else (href or source_url)

                    capacity = self._parse_capacity(name)
                    target = self._match_target(
                        name,
                        capacity,
                        strict_variant=True,
                    )
                    if target:
                        rows.append(self._make_row(
                            target=target,
                            offer_type="cash",
                            price_value=price,
                            term_months=None,
                            source_url=product_url,
                            source_title=name,
                        ))
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[Samsung Store] HTML parse error: {e}")
        return rows

    # ------------------------------------------------------------------ #
    # Helpers de parseo de items JSON                                      #
    # ------------------------------------------------------------------ #

    def _parse_item(self, item: dict, targets: list[dict], source_url: str) -> Optional[PriceRow]:
        name = (
            item.get("modelName")
            or item.get("name")
            or item.get("title", "")
        )
        if not name:
            return None

        price_data = (
            item.get("price")
            or item.get("priceDisplay")
            or item.get("currentPrice")
            or {}
        )
        if isinstance(price_data, dict):
            price_value = price_data.get("currentPrice") or price_data.get("amount")
        elif isinstance(price_data, (int, float)):
            price_value = float(price_data)
        elif isinstance(price_data, str):
            price_value = self._clean_price(price_data)
        else:
            return None

        if not price_value:
            return None

        url = item.get("url") or item.get("pdpUrl") or source_url
        if url and not url.startswith("http"):
            url = f"{BASE_URL}{url}"

        capacity = self._parse_capacity(name)
        target = self._match_target(
            name,
            capacity,
            strict_variant=True,
        )
        if not target:
            return None

        return self._make_row(
            target=target,
            offer_type="cash",
            price_value=float(price_value),
            term_months=None,
            source_url=url,
            source_title=name,
        )

    def _parse_schema_item(self, item: dict, targets: list[dict], source_url: str) -> Optional[PriceRow]:
        name = item.get("name", "")
        if not name:
            return None
        offers = item.get("offers", {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        price_value = offers.get("price")
        if not price_value:
            return None
        try:
            price = float(price_value)
        except (ValueError, TypeError):
            return None

        url = item.get("url") or offers.get("url", source_url)
        capacity = self._parse_capacity(name)
        target = self._match_target(
            name,
            capacity,
            strict_variant=True,
        )
        if not target:
            return None

        return self._make_row(
            target=target,
            offer_type="cash",
            price_value=price,
            term_months=None,
            source_url=url,
            source_title=name,
        )

    @staticmethod
    def _drill_products(data, depth: int = 0) -> list[dict]:
        if depth > 6:
            return []
        if isinstance(data, list) and data and isinstance(data[0], dict):
            if any(k in data[0] for k in ("modelName", "name", "modelCode", "price")):
                return data
        if isinstance(data, dict):
            for key in ("products", "items", "models", "tiles", "results", "data"):
                value = data.get(key)
                if value:
                    result = SamsungStoreScraper._drill_products(value, depth + 1)
                    if result:
                        return result
            for value in data.values():
                if isinstance(value, (dict, list)):
                    result = SamsungStoreScraper._drill_products(value, depth + 1)
                    if result:
                        return result
        return []

    @staticmethod
    def _extract_financing_plan(response) -> Optional[tuple[int, float]]:
        """
        Extrae (term_months, annual_rate) desde campos eip* de Samsung.
        """
        try:
            body = (
                response.body.decode("utf-8", errors="replace")
                if isinstance(response.body, (bytes, bytearray))
                else str(response.body)
            )
        except Exception:
            return None

        # Si Samsung marca eipUse=N, no hay financiacion para ese SKU.
        use_match = re.search(r'"eipUse"\s*:\s*"([YN])"', body, flags=re.I)
        if use_match and use_match.group(1).upper() == "N":
            return None

        term_months: Optional[int] = None
        m = re.search(r'"eipMonth"\s*:\s*"?(?P<n>\d{1,3})"?', body, flags=re.I)
        if m:
            term_months = int(m.group("n"))
        if not term_months:
            m = re.search(r"hasta\s+en\s+(\d{1,3})\s+meses", body, flags=re.I)
            if m:
                term_months = int(m.group(1))
        if not term_months or term_months <= 0:
            return None

        annual_rate = 0.0
        m = re.search(
            r'"eipRate"\s*:\s*"?(?P<r>[0-9]+(?:[.,][0-9]+)?)"?',
            body,
            flags=re.I,
        )
        if m:
            try:
                annual_rate = float(m.group("r").replace(",", "."))
            except ValueError:
                annual_rate = 0.0

        return term_months, annual_rate

    @staticmethod
    def _compute_monthly_installment(
        cash_price: float,
        term_months: int,
        annual_rate: float,
    ) -> Optional[float]:
        if not cash_price or term_months <= 0:
            return None

        # Financiacion al 0%: cuota = precio / meses.
        if annual_rate <= 0:
            return round(cash_price / term_months, 2)

        monthly_rate = annual_rate / 12 / 100
        try:
            factor = (1 + monthly_rate) ** term_months
            if factor == 1:
                return round(cash_price / term_months, 2)
            return round(cash_price * monthly_rate * factor / (factor - 1), 2)
        except Exception:
            return None

    @staticmethod
    def _to_buy_url(url: str) -> str:
        if not url:
            return ""
        if not url.startswith("http"):
            url = f"{BASE_URL}{url}"

        parsed = urlparse(url)
        path = parsed.path.rstrip("/")

        if "/buy" not in path:
            path = f"{path}/buy"
        if not path.endswith("/"):
            path = f"{path}/"

        return urlunparse((parsed.scheme, parsed.netloc, path, "", parsed.query, ""))

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
            existing = dedup.get(key)
            if existing is None or row.price_value < existing.price_value:
                dedup[key] = row
        return list(dedup.values())
