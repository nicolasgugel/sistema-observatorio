"""
Scraper para Samsung Store España (samsung.com/es).

Estrategia:
- Fetch de páginas de categoría (Galaxy S, A, Z, Book, Tab)
- Samsung embebe datos en scripts JSON (__NEXT_DATA__ o window._data)
- Fallback a JSON-LD y HTML de tarjetas
- Fuzzy match contra targets de Santander
- Output: cash (precio de compra oficial Samsung)

Usa AsyncStealthySession (Camoufox) para reutilizar navegador y manejar anti-bot.
"""
from __future__ import annotations
import asyncio
import json
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse, urlunparse

from loguru import logger
from scrapling.fetchers import AsyncStealthySession

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

CATEGORY_CONCURRENCY = 2
PDP_CONCURRENCY = 2
SESSION_TIMEOUT_MS = 30_000


class SamsungStoreScraper(CompetitorBase):
    SOURCE_NAME = "samsung_store"
    RETAILER = "Samsung Store"
    DATA_QUALITY_TIER = "samsung_adapter_live"

    async def scrape(self) -> list[PriceRow]:
        rows: list[PriceRow] = []

        # Solo procesar si hay targets Samsung
        samsung_targets = [t for t in self.targets if t.get("brand", "").lower() == "samsung"]
        if not samsung_targets:
            logger.info("[Samsung Store] Sin targets Samsung — omitiendo")
            return []

        logger.info(f"[Samsung Store] {len(samsung_targets)} targets Samsung")

        sem = asyncio.Semaphore(CATEGORY_CONCURRENCY)

        async with AsyncStealthySession(
            timeout=SESSION_TIMEOUT_MS,
            retries=1,
            max_pages=max(CATEGORY_CONCURRENCY, PDP_CONCURRENCY),
            disable_resources=True,
        ) as session:
            async def fetch_category(url: str) -> list[PriceRow]:
                async with sem:
                    logger.info(f"[Samsung Store] Fetching: {url}")
                    try:
                        response = await session.fetch(url, google_search=True)
                        page_rows = self._parse_page(response, samsung_targets, url)
                        logger.info(f"[Samsung Store] {url.split('/')[-2]}: {len(page_rows)} filas")
                        return page_rows
                    except Exception as e:
                        logger.error(f"[Samsung Store] Error en {url}: {e}")
                        return []

            results = await asyncio.gather(*[fetch_category(url) for url in CATEGORY_URLS])
            for page_rows in results:
                rows.extend(page_rows)

            rows = await self._revalidate_cash_rows(session, rows)
            financing_rows = await self._build_financing_rows(rows)
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

    async def _build_financing_rows(self, rows: list[PriceRow]) -> list[PriceRow]:
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

    async def _revalidate_cash_rows(self, session, rows: list[PriceRow]) -> list[PriceRow]:
        """
        Revalida cada fila cash contra el PDP real.

        Samsung mezcla en cards y configuradores variantes distintas dentro del
        mismo producto. Antes de aceptar una fila, comprobamos:
        - capacidad real del SKU enlazado
        - disponibilidad del PDP
        - conectividad (Wi-Fi vs 5G) cuando viene explícita
        - precio/título reales del PDP cuando están disponibles
        """
        sem = asyncio.Semaphore(PDP_CONCURRENCY)
        trusted_rows: list[PriceRow] = []
        rows_to_fetch: list[PriceRow] = []
        pre_dropped = 0

        for row in rows:
            prechecked = self._precheck_cash_row(row)
            if prechecked is None:
                pre_dropped += 1
                continue
            if self._can_skip_pdp_validation(prechecked):
                trusted_rows.append(prechecked)
                continue
            rows_to_fetch.append(prechecked)

        async def validate(row: PriceRow) -> Optional[PriceRow]:
            async with sem:
                try:
                    return await self._revalidate_cash_row(session, row)
                except Exception as e:
                    logger.debug(f"[Samsung Store] PDP validate error {row.source_url}: {e}")
                    return row

        validated = await asyncio.gather(*[validate(row) for row in rows_to_fetch])
        fetched_kept = [row for row in validated if row is not None]
        kept = trusted_rows + fetched_kept
        dropped = pre_dropped + (len(validated) - len(fetched_kept))
        if trusted_rows:
            logger.info(f"[Samsung Store] Validacion PDP: {len(trusted_rows)} filas aceptadas por URL/SKU")
        if rows_to_fetch:
            logger.info(f"[Samsung Store] Validacion PDP: {len(rows_to_fetch)} PDPs abiertos")
        if dropped:
            logger.info(f"[Samsung Store] Validacion PDP: descartadas {dropped} filas incompatibles")
        return kept

    def _precheck_cash_row(self, row: PriceRow) -> Optional[PriceRow]:
        target_capacity = int(row.capacity_gb) if row.capacity_gb else None

        explicit_capacity = self._explicit_capacity_hint(row.source_url) or self._explicit_capacity_hint(row.source_title)
        if explicit_capacity and target_capacity and explicit_capacity != target_capacity:
            logger.info(
                f"[Samsung Store] Drop {row.model} {target_capacity}GB: "
                f"source apunta a {explicit_capacity}GB ({row.source_url})"
            )
            return None

        if self._has_connectivity_mismatch(row.model, f"{row.source_title} {row.source_url}"):
            logger.info(f"[Samsung Store] Drop {row.model}: Wi-Fi/5G mismatch ({row.source_url})")
            return None

        selected_model_code = self._extract_model_code_from_url(row.source_url)
        if selected_model_code and self._sku_root_mismatch(selected_model_code, row.product_code):
            logger.info(
                f"[Samsung Store] Drop {row.model}: SKU root mismatch "
                f"{selected_model_code} vs {row.product_code}"
            )
            return None

        return row

    def _can_skip_pdp_validation(self, row: PriceRow) -> bool:
        source_url = str(row.source_url or "")
        if "/buy/" in source_url:
            return False

        target_capacity = int(row.capacity_gb) if row.capacity_gb else None
        explicit_capacity = self._explicit_capacity_hint(source_url)
        if explicit_capacity and target_capacity and explicit_capacity == target_capacity:
            return source_url not in CATEGORY_URLS

        return False

    async def _revalidate_cash_row(self, session, row: PriceRow) -> Optional[PriceRow]:
        target_capacity = int(row.capacity_gb) if row.capacity_gb else None

        response = await session.fetch(row.source_url)
        validation = self._extract_pdp_validation(
            response,
            row.source_url,
            target_capacity=target_capacity,
            target_product_code=row.product_code,
        )
        if not validation:
            return row

        resolved_capacity = validation.get("capacity_gb")
        if resolved_capacity and target_capacity and resolved_capacity != target_capacity:
            logger.info(
                f"[Samsung Store] Drop {row.model} {target_capacity}GB: "
                f"PDP resuelve {resolved_capacity}GB ({row.source_url})"
            )
            return None

        resolved_sku = str(validation.get("sku") or "")
        if self._sku_root_mismatch(resolved_sku, row.product_code):
            logger.info(
                f"[Samsung Store] Drop {row.model}: SKU root mismatch "
                f"{resolved_sku} vs {row.product_code}"
            )
            return None

        resolved_title = validation.get("source_title") or row.source_title
        if self._has_connectivity_mismatch(row.model, resolved_title):
            logger.info(f"[Samsung Store] Drop {row.model}: PDP title mismatch ({resolved_title})")
            return None

        if validation.get("in_stock") is False:
            logger.info(f"[Samsung Store] Drop {row.model}: PDP not in stock ({row.source_url})")
            return None

        price_value = validation.get("price_value")
        if price_value:
            row.price_value = float(price_value)
            row.price_text = f"{float(price_value):.2f} EUR"
        if resolved_title:
            row.source_title = resolved_title
        if validation.get("source_url"):
            row.source_url = str(validation["source_url"])
        row.in_stock = bool(validation.get("in_stock", row.in_stock))
        return row

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

    def _extract_pdp_validation(
        self,
        response,
        source_url: str,
        target_capacity: Optional[int] = None,
        target_product_code: str = "",
    ) -> Optional[dict]:
        items = self._extract_json_ld_items(response)
        selected_model_code = self._extract_model_code_from_url(source_url)

        for item in items:
            if not self._json_ld_type_is(item, "ProductGroup"):
                continue
            variant = self._find_product_group_variant(
                item,
                selected_model_code=selected_model_code,
                target_capacity=target_capacity,
                target_product_code=target_product_code,
            )
            if not variant:
                continue
            offers = variant.get("offers") or {}
            title = str(variant.get("name") or "").strip()
            storage_text = self._extract_storage_text(variant)
            sku = str(variant.get("sku") or "")
            return {
                "sku": sku,
                "capacity_gb": self._parse_capacity(title) or self._parse_capacity(storage_text),
                "price_value": self._schema_offer_price(offers),
                "in_stock": self._schema_offer_in_stock(offers),
                "source_title": title,
                "source_url": self._with_model_code(source_url, sku),
            }

        product_item = next((item for item in items if self._json_ld_type_is(item, "Product")), None)
        webpage_item = next((item for item in items if self._json_ld_type_is(item, "WebPage")), None)
        if not product_item:
            return None

        offers = product_item.get("offers") or {}
        webpage_title = str(webpage_item.get("name") or "").strip() if webpage_item else ""
        product_title = str(product_item.get("name") or "").strip()
        resolved_title = webpage_title or product_title
        return {
            "sku": str(product_item.get("sku") or ""),
            "capacity_gb": (
                self._parse_capacity(product_title)
                or self._parse_capacity(webpage_title)
                or self._explicit_capacity_hint(source_url)
            ),
            "price_value": self._schema_offer_price(offers),
            "in_stock": self._schema_offer_in_stock(offers),
            "source_title": resolved_title,
            "source_url": self._schema_offer_url(offers) or source_url,
        }

    def _extract_json_ld_items(self, response) -> list[dict]:
        items: list[dict] = []
        try:
            scripts = response.find_all("script", {"type": "application/ld+json"})
        except Exception:
            return items

        for script in scripts:
            text = (script.text or "").strip()
            if not text:
                continue
            try:
                data = json.loads(text)
            except Exception:
                continue
            if isinstance(data, list):
                items.extend(x for x in data if isinstance(x, dict))
            elif isinstance(data, dict):
                items.append(data)
        return items

    @staticmethod
    def _json_ld_type_is(item: dict, expected: str) -> bool:
        item_type = item.get("@type")
        if isinstance(item_type, list):
            return expected in item_type
        return item_type == expected

    def _find_product_group_variant(
        self,
        item: dict,
        selected_model_code: Optional[str],
        target_capacity: Optional[int],
        target_product_code: str,
    ) -> Optional[dict]:
        variants = item.get("hasVariant") or []
        if not isinstance(variants, list):
            return None
        clean_variants = [variant for variant in variants if isinstance(variant, dict)]
        exact_sku = str(target_product_code or "").upper()

        if exact_sku:
            exact_variant = next(
                (v for v in clean_variants if str(v.get("sku") or "").upper() == exact_sku),
                None,
            )
            if exact_variant and self._variant_matches_target(exact_variant, target_capacity):
                return exact_variant

        if selected_model_code:
            selected_variant = next(
                (v for v in clean_variants if str(v.get("sku") or "").upper() == selected_model_code.upper()),
                None,
            )
            if selected_variant and self._variant_matches_target(selected_variant, target_capacity):
                return selected_variant

        candidates = [
            variant
            for variant in clean_variants
            if self._variant_matches_target(variant, target_capacity)
        ]
        in_stock = [variant for variant in candidates if self._variant_in_stock(variant) is not False]
        if in_stock:
            return in_stock[0]
        if candidates:
            return candidates[0]
        if len(variants) == 1 and isinstance(variants[0], dict):
            return variants[0]
        return None

    def _variant_matches_target(self, variant: dict, target_capacity: Optional[int]) -> bool:
        if not target_capacity:
            return True
        title = str(variant.get("name") or "")
        storage_text = self._extract_storage_text(variant)
        variant_capacity = self._parse_capacity(title) or self._parse_capacity(storage_text)
        return not variant_capacity or int(variant_capacity) == int(target_capacity)

    def _variant_in_stock(self, variant: dict) -> Optional[bool]:
        return self._schema_offer_in_stock(variant.get("offers") or {})

    @staticmethod
    def _extract_storage_text(item: dict) -> str:
        value = item.get("additionalProperty")
        if isinstance(value, dict):
            return str(value.get("value") or "")
        if isinstance(value, list):
            parts = [
                str(prop.get("value") or "")
                for prop in value
                if isinstance(prop, dict)
            ]
            return " ".join(p for p in parts if p)
        return ""

    def _schema_offer_price(self, offers) -> Optional[float]:
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if not isinstance(offers, dict):
            return None
        return self._clean_price(str(offers.get("price") or ""))

    @staticmethod
    def _schema_offer_url(offers) -> str:
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if not isinstance(offers, dict):
            return ""
        return str(offers.get("url") or "")

    @staticmethod
    def _schema_offer_in_stock(offers) -> Optional[bool]:
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if not isinstance(offers, dict):
            return None
        availability = str(offers.get("availability") or "").lower()
        if not availability:
            return None
        return "instock" in availability

    @staticmethod
    def _extract_model_code_from_url(url: str) -> Optional[str]:
        try:
            parsed = urlparse(url)
        except Exception:
            return None
        query = parse_qs(parsed.query)
        values = query.get("modelCode") or query.get("modelcode")
        if values:
            return str(values[0]).strip().upper()
        return None

    def _explicit_capacity_hint(self, text: str) -> Optional[int]:
        return self._parse_capacity(text)

    @staticmethod
    def _with_model_code(source_url: str, model_code: str) -> str:
        if not source_url or not model_code:
            return source_url
        parsed = urlparse(source_url)
        if "/buy/" not in parsed.path:
            return source_url
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", f"modelCode={model_code}", ""))

    def _has_connectivity_mismatch(self, target_model: str, source_text: str) -> bool:
        target_norm = self._normalize(target_model)
        source_norm = self._normalize(source_text)
        if "wi fi" in target_norm and ("5g" in source_norm or "cellular" in source_norm):
            return True
        return False

    @staticmethod
    def _sku_root(code: str) -> str:
        code = str(code or "").upper()
        m = re.search(r"(SM-[A-Z]\d{3,4})", code)
        if m:
            return m.group(1)
        return ""

    def _sku_root_mismatch(self, source_sku: str, target_product_code: str) -> bool:
        source_root = self._sku_root(source_sku)
        target_root = self._sku_root(target_product_code)
        if not source_root or not target_root:
            return False
        return source_root != target_root

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
