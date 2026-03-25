"""
Scraper para MediaMarkt España (mediamarkt.es).

Estrategia:
- Búsqueda por producto: una query por cada target (model + capacity)
- Fetcher (HTTP) — MediaMarkt devuelve SSR tanto en búsqueda como en producto
- Extrae el primer resultado relevante de la búsqueda → cash price + URL producto
- Visita la página de producto → cuota de financiación (JSON embebido o texto HTML)
- Output: cash + financing_max_term (si disponible en la página de producto)

La financiación NO es al 0%; MediaMarkt usa crédito con TAE variable.
Se extrae el finalRate directamente de la página (no se calcula sobre el precio).
"""
from __future__ import annotations
import asyncio
import json
import re
from typing import Optional
from urllib.parse import quote_plus

from loguru import logger
from scrapling.fetchers import Fetcher

from models.price_row import PriceRow
from scrapers.competitor_base import CompetitorBase

BASE_URL = "https://www.mediamarkt.es"
DELAY = 2.5          # delay entre targets
PRODUCT_DELAY = 1.0  # delay entre search page y product page
CONCURRENCY = 5      # peticiones paralelas simultáneas
MAX_RESULTS = 3      # primeros N resultados a considerar por búsqueda

# Términos de financiación estándar de MediaMarkt (meses)
FINANCING_TERMS = [3, 6, 10, 12, 14, 18, 20, 24, 30]
# TIN (tipo de interés nominal anual) por defecto de MediaMarkt España
DEFAULT_TIN = 18.95

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


class MediaMarktScraper(CompetitorBase):
    SOURCE_NAME = "mediamarkt"
    RETAILER = "MediaMarkt"
    DATA_QUALITY_TIER = "mediamarkt_adapter_live"

    async def scrape(self) -> list[PriceRow]:
        rows: list[PriceRow] = []
        fetcher = Fetcher(auto_match=False)

        # Deduplicar targets (un target por model+capacity)
        seen = set()
        unique_targets = []
        for t in self.targets:
            key = (t["model"], t.get("capacity_gb"))
            if key not in seen:
                seen.add(key)
                unique_targets.append(t)

        logger.info(f"[MediaMarkt] {len(unique_targets)} productos a buscar")

        sem = asyncio.Semaphore(CONCURRENCY)

        async def fetch_one(target: dict):
            async with sem:
                query = self._build_query(target)
                logger.debug(f"[MediaMarkt] Buscando: {query!r}")
                product_rows = await self._search_product(fetcher, query, target)
                await asyncio.sleep(DELAY)
                return product_rows

        results = await asyncio.gather(*[fetch_one(t) for t in unique_targets])
        rows = [r for result in results for r in result]

        logger.info(f"[MediaMarkt] Total: {len(rows)} filas")
        return rows

    # ------------------------------------------------------------------ #
    # Búsqueda + financiación                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_query(target: dict) -> str:
        """Construye query de búsqueda desde el target de Santander."""
        model = target["model"]
        cap = target.get("capacity_gb")
        if cap:
            if cap >= 1000:
                tb = cap // 1024
                return f"{model} {tb} TB"
            return f"{model} {cap}GB"
        return model

    async def _search_product(
        self,
        fetcher: Fetcher,
        query: str,
        target: dict,
    ) -> list[PriceRow]:
        """
        1. Busca el producto en MediaMarkt → extrae cash price + URL producto.
        2. Visita la página de producto → extrae cuota de financiación.
        Devuelve lista de PriceRow (0-2 elementos por producto).
        """
        search_url = f"{BASE_URL}/es/search.html?query={quote_plus(query)}"
        try:
            response = await asyncio.to_thread(fetcher.get, search_url, headers=_HEADERS)
        except Exception as e:
            logger.warning(f"[MediaMarkt] Error buscando {query!r}: {e}")
            return []

        # Cash price desde búsqueda
        cash_row = (
            self._try_json_data(response, target, search_url)
            or self._parse_result_cards(response, target, query, search_url)
        )
        if not cash_row:
            logger.debug(f"[MediaMarkt] Sin match para {query!r}")
            return []

        rows: list[PriceRow] = [cash_row]

        # Visitar página de producto para financiación (todos los términos)
        product_url = cash_row.source_url
        if product_url and product_url != search_url and "/product/" in product_url:
            await asyncio.sleep(PRODUCT_DELAY)
            try:
                prod_resp = await asyncio.to_thread(
                    fetcher.get, product_url, headers=_HEADERS
                )
                financing_rows = self._extract_financing(
                    prod_resp, target, product_url, cash_row.price_value
                )
                rows.extend(financing_rows)
            except Exception as e:
                logger.debug(f"[MediaMarkt] Error en página producto {product_url}: {e}")

        return rows

    # ------------------------------------------------------------------ #
    # Financiación                                                         #
    # ------------------------------------------------------------------ #

    def _extract_financing(
        self,
        response,
        target: dict,
        product_url: str,
        cash_price: float,
    ) -> list[PriceRow]:
        """
        Extrae financiación de la página de producto MediaMarkt para TODOS los plazos.

        Estrategia:
        1. Busca el JSON de installment para obtener el TIN real del producto
           "installment": {"interestNominal": 18.95, ...}
        2. Con el TIN, calcula la cuota mensual para cada término estándar
           usando la fórmula de amortización francesa:
           monthly = P × r × (1+r)^n / ((1+r)^n - 1)
           donde r = TIN / 12

        El TIN de MediaMarkt España es fijo (~18.95%). Si no se encuentra,
        se usa el valor por defecto.
        """
        tin = DEFAULT_TIN  # % anual (nominal)
        found_installment = False

        # ── 1. Extraer TIN del JSON de installment ───────────────────────
        for script in response.find_all("script"):
            text = script.text or ""
            if '"installment"' not in text:
                continue
            m = re.search(r'"installment"\s*:\s*(\{[^}]+\})', text)
            if m:
                try:
                    inst = json.loads(m.group(1))
                    nominal = inst.get("interestNominal")
                    if nominal and float(nominal) > 0:
                        tin = float(nominal)
                    found_installment = True
                    break
                except Exception:
                    pass

        # Si no se encontró JSON de installment, verificar el HTML
        if not found_installment and not self._has_financing_html(response):
            return []

        # ── 2. Calcular cuotas para todos los términos estándar ──────────
        rows: list[PriceRow] = []
        r = tin / 12 / 100  # tasa mensual decimal

        for n in FINANCING_TERMS:
            try:
                factor = (1 + r) ** n
                monthly = round(cash_price * r * factor / (factor - 1), 2)
                rows.append(
                    self._make_row(
                        target=target,
                        offer_type="financing_max_term",
                        price_value=monthly,
                        term_months=n,
                        source_url=product_url,
                        source_title=None,
                        in_stock=True,
                    )
                )
            except Exception:
                pass

        return rows

    @staticmethod
    def _has_financing_html(response) -> bool:
        """Verifica si la página contiene texto de financiación (cuotas/mensual)."""
        for el in response.css("p, span"):
            text = (el.text or "").strip().replace("\xa0", " ")
            if re.search(r"cuota|mensual|installment", text, re.IGNORECASE):
                return True
        return False

    # ------------------------------------------------------------------ #
    # Cash price desde búsqueda                                            #
    # ------------------------------------------------------------------ #

    def _try_json_data(self, response, target: dict, source_url: str) -> Optional[PriceRow]:
        """Intenta extraer de __INITIAL_STATE__ o similar JSON embebido en MediaMarkt."""
        try:
            scripts = response.find_all("script")
            for script in scripts:
                text = script.text or ""
                for pattern in [
                    r"window\.__INITIAL_STATE__\s*=\s*(\{.+?\})(?:;|\s*</)",
                    r"window\.__REDUX_STATE__\s*=\s*(\{.+?\})(?:;|\s*</)",
                ]:
                    match = re.search(pattern, text, re.DOTALL)
                    if match:
                        try:
                            data = json.loads(match.group(1))
                            items = self._drill_products(data)
                            best_row, best_score = None, 0
                            for item in items[:MAX_RESULTS]:
                                result = self._parse_api_item(item, target, source_url)
                                if result:
                                    row, score = result
                                    if score > best_score:
                                        best_score, best_row = score, row
                            if best_row:
                                return best_row
                        except Exception:
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
    ) -> Optional[PriceRow]:
        """Parsea las tarjetas de búsqueda de MediaMarkt."""
        try:
            cards = (
                response.css("[data-test='mms-product-card']")
                or response.css("[class*='ProductCard']")
                or response.css("[class*='product-item']")
                or response.find_all("article")
            )

            best_row: Optional[PriceRow] = None
            best_score = 0
            count = 0

            for card in cards:
                if count >= MAX_RESULTS:
                    break
                result = self._parse_card(card, target, source_url)
                if result:
                    row, score = result
                    if score > best_score:
                        best_score = score
                        best_row = row
                    count += 1

            if best_row:
                logger.debug(
                    f"[MediaMarkt] Match para {query!r} (score={best_score})"
                )
            return best_row

        except Exception as e:
            logger.debug(f"[MediaMarkt] Error parseando resultados: {e}")
            return None

    def _parse_api_item(
        self,
        item: dict,
        target: dict,
        source_url: str,
    ) -> Optional[tuple[PriceRow, int]]:
        """Parsea un item del JSON embebido de MediaMarkt."""
        name = item.get("name") or item.get("title", "")
        if not name:
            return None

        price_data = item.get("price") or item.get("pricing", {})
        if isinstance(price_data, dict):
            price_value = (
                price_data.get("current")
                or price_data.get("value")
                or price_data.get("amount")
            )
        elif isinstance(price_data, (int, float)):
            price_value = float(price_data)
        else:
            return None
        if not price_value:
            return None

        url = item.get("url") or item.get("productUrl", source_url)
        if url and not url.startswith("http"):
            url = f"{BASE_URL}{url}"

        # Filtrar accesorios (fundas, hubs, cables…)
        if self._is_accessory(name):
            return None

        capacity = self._parse_capacity(name)

        # Scoring con penalizaciones completas (número, tier, serie, capacidad)
        score = self._score_name_against_target(name, target, capacity)
        if score < 72:
            return None

        row = self._make_row(
            target=target,
            offer_type="cash",
            price_value=float(price_value),
            term_months=None,
            source_url=url,
            source_title=name,
            in_stock=item.get("inStock", True),
        )
        return row, score

    def _parse_card(
        self,
        card,
        target: dict,
        source_url: str,
    ) -> Optional[tuple[PriceRow, int]]:
        """Parsea una tarjeta de MediaMarkt y devuelve (PriceRow, match_score) o None."""
        try:
            name_el = self._css_first(card, "[data-test='product-title']")
            if not name_el:
                return None
            name = name_el.text.strip()
            if not name or len(name) < 5:
                return None

            price_spans = card.css("[data-test='mms-price'] .mms-ui-mBgaT")
            if not price_spans:
                price_spans = card.css("[data-test*='price'] .mms-ui-mBgaT")
            if not price_spans:
                return None
            price = self._clean_price(price_spans[-1].text)
            if not price:
                return None

            link_el = self._css_first(
                card, "[data-test='mms-router-link-product-list-item-link']"
            )
            if not link_el:
                link_el = self._css_first(card, "a[href]")
            href = self._el_attr(link_el, "href")
            product_url = (
                f"{BASE_URL}{href}"
                if href.startswith("/")
                else (href or source_url)
            )

            # Filtrar accesorios (fundas, hubs, cables…)
            if self._is_accessory(name):
                return None

            capacity = self._parse_capacity(name)

            # Scoring con penalizaciones completas (número, tier, serie, capacidad)
            score = self._score_name_against_target(name, target, capacity)
            if score < 72:
                return None

            oos_el = self._css_first(
                card,
                "[class*='unavailable'], [class*='out-of-stock'], [class*='agotado']",
            )
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
            logger.debug(f"[MediaMarkt] Error parseando card: {e}")
            return None

    @staticmethod
    def _drill_products(data, depth: int = 0) -> list[dict]:
        """Busca recursivamente listas de productos en el JSON de estado."""
        if depth > 6:
            return []
        if isinstance(data, list) and data and isinstance(data[0], dict):
            if any(k in data[0] for k in ("name", "title", "price", "sku")):
                return data
        if isinstance(data, dict):
            for key in ("products", "items", "results", "hits", "data"):
                value = data.get(key)
                if value:
                    result = MediaMarktScraper._drill_products(value, depth + 1)
                    if result:
                        return result
            for value in data.values():
                if isinstance(value, (dict, list)):
                    result = MediaMarktScraper._drill_products(value, depth + 1)
                    if result:
                        return result
        return []
