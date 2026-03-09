"""
Scraper para Grover España (getgrover.com/es-es).
Grover es una plataforma de renting de tecnología — competidor directo en renting.

Estrategia:
- Scraping por categorías (brand pages) → un fetch por categoría
- Extracción de __NEXT_DATA__ JSON embebido en Next.js
- Fuzzy match contra targets de Santander
- Output: renting_no_insurance (precio mensual mínimo)

Las páginas de Grover son SSR (Next.js) — Fetcher HTTP es suficiente y mucho más rápido.
"""
from __future__ import annotations
import asyncio
import json
import re
from typing import Optional

from loguru import logger
from scrapling.fetchers import Fetcher

from models.price_row import PriceRow
from scrapers.competitor_base import CompetitorBase

BASE_URL = "https://www.getgrover.com"

# Páginas de categoría filtradas por marca — el SSR embebe ~4 productos por página
CATEGORY_URLS = [
    # Apple
    f"{BASE_URL}/es-es/phones-and-tablets/smartphones?brand=apple",
    f"{BASE_URL}/es-es/phones-and-tablets/tablets?brand=apple",
    f"{BASE_URL}/es-es/computers/laptops?brand=apple",
    # Samsung
    f"{BASE_URL}/es-es/phones-and-tablets/smartphones?brand=samsung",
    f"{BASE_URL}/es-es/phones-and-tablets/tablets?brand=samsung",
    f"{BASE_URL}/es-es/computers/laptops?brand=samsung",
]

DELAY = 1.0
MAX_PAGES = 20       # límite de páginas por categoría (24 productos × 20 = 480 por cat)
RENTING_TERM = 1     # Grover = renting flexible desde 1 mes


class GroverScraper(CompetitorBase):
    SOURCE_NAME = "grover"
    RETAILER = "Grover"
    DATA_QUALITY_TIER = "grover_adapter_live"

    async def scrape(self) -> list[PriceRow]:
        rows: list[PriceRow] = []
        fetcher = Fetcher(auto_match=False)

        for url in CATEGORY_URLS:
            logger.info(f"[Grover] Fetching: {url}")
            page_rows = await self._scrape_category(fetcher, url)
            rows.extend(page_rows)
            logger.info(f"[Grover] {url}: {len(page_rows)} filas")
            await asyncio.sleep(DELAY)

        deduped = self._dedupe_rows(rows)
        logger.info(f"[Grover] Total: {len(rows)} filas ({len(deduped)} tras dedupe)")
        return deduped

    async def _scrape_category(self, fetcher: Fetcher, url: str) -> list[PriceRow]:
        rows: list[PriceRow] = []
        page = 1

        while page <= MAX_PAGES:
            page_url = f"{url}&page={page}" if page > 1 else url
            try:
                response = await asyncio.to_thread(fetcher.get, page_url, stealthy_headers=True)
            except Exception as e:
                logger.error(f"[Grover] Error en {page_url}: {e}")
                break

            page_rows, has_next = self._parse_next_data(response, page_url)
            if not page_rows:
                page_rows = self._parse_html(response, page_url)
                has_next = False

            if not page_rows:
                logger.debug(f"[Grover] Sin productos en página {page}")
                break

            rows.extend(page_rows)
            logger.debug(f"[Grover] Página {page}: {len(page_rows)} productos (has_next={has_next})")

            if not has_next:
                break
            page += 1
            await asyncio.sleep(DELAY)

        return rows

    # ------------------------------------------------------------------ #
    # Parsers                                                              #
    # ------------------------------------------------------------------ #

    def _parse_next_data(self, response, source_url: str) -> tuple[list[PriceRow], bool]:
        """
        Extrae productos del __NEXT_DATA__ de Next.js (React Query / TanStack Query).
        Grover embebe los datos en dehydratedState.queries, con queryKey[0]='searchProductsFull'.
        Retorna (rows, has_next_page).
        """
        rows: list[PriceRow] = []
        has_next = False
        try:
            script_el = response.find("script", {"id": "__NEXT_DATA__"})
            if not script_el:
                return [], False
            data = json.loads(script_el.text)

            # Navegar a dehydratedState.queries
            queries = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("dehydratedState", {})
                    .get("queries", [])
            )

            for q in queries:
                qkey = q.get("queryKey", [])
                # Solo queries de tipo searchProductsFull
                if not (isinstance(qkey, list) and qkey and qkey[0] == "searchProductsFull"):
                    continue

                state_data = q.get("state", {}).get("data") or {}
                if not isinstance(state_data, dict):
                    continue

                # Formato 1 (brand pages): state_data.products + state_data.pagination
                # Formato 2 (category pages, useInfiniteQuery): state_data.pages[0].products
                products = state_data.get("products") or []
                pagination = state_data.get("pagination") or {}

                if not products and "pages" in state_data:
                    # Formato useInfiniteQuery
                    for page_data in state_data.get("pages", []):
                        if isinstance(page_data, dict):
                            products.extend(page_data.get("products") or [])
                            pagination = page_data.get("pagination") or pagination

                for item in products:
                    row = self._parse_item(item, source_url)
                    if row:
                        rows.append(row)

                # Paginación desde el JSON
                if pagination.get("nextPage") is not None:
                    has_next = True

                # Con el primer query de productos es suficiente
                if products:
                    break

        except Exception as e:
            logger.debug(f"[Grover] No se pudo parsear __NEXT_DATA__: {e}")
        return rows, has_next

    def _parse_html(self, response, source_url: str) -> list[PriceRow]:
        """Fallback: parsea tarjetas de producto del HTML."""
        rows: list[PriceRow] = []
        try:
            cards = (
                response.css("[data-testid*='product-card']")
                or response.css("[class*='ProductCard']")
                or response.css("[class*='product-card']")
            )
            for card in cards:
                try:
                    name_el = self._css_first(card, "h3, h2, [class*='name'], [class*='title']")
                    price_el = self._css_first(card, "[class*='price'], [class*='Price']")
                    if not name_el or not price_el:
                        continue

                    name = name_el.text.strip()
                    price = self._clean_price(price_el.text)
                    if not name or not price:
                        continue

                    link_el = self._css_first(card, "a[href]")
                    href = self._el_attr(link_el, "href")
                    product_url = f"{BASE_URL}{href}" if href.startswith("/") else (href or source_url)
                    match_text = f"{name} {href.replace('-', ' ')}"
                    capacity = self._parse_capacity(match_text)

                    target = self._match_target(
                        match_text,
                        capacity,
                        strict_variant=True,
                    )
                    if target:
                        rows.append(self._make_row(
                            target=target,
                            offer_type="renting_no_insurance",
                            price_value=price,
                            term_months=RENTING_TERM,
                            source_url=product_url,
                            source_title=name,
                        ))
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[Grover] Error parseando HTML: {e}")
        return rows

    def _parse_item(self, item: dict, source_url: str) -> Optional[PriceRow]:
        """
        Parsea un producto del JSON de Grover.
        Estructura real: {name, cheapestRentalPlan: {price: {inCents}, length: {value}}, slug, ...}
        """
        name = item.get("name") or item.get("title", "")
        if not name:
            return None

        # Precio mensual desde cheapestRentalPlan (estructura real de Grover)
        price_value = 0.0
        min_months = RENTING_TERM

        cheapest = item.get("cheapestRentalPlan") or {}
        if cheapest:
            price_info = cheapest.get("price") or {}
            in_cents = price_info.get("inCents", 0)
            price_value = in_cents / 100 if in_cents else 0.0
            length = cheapest.get("length") or {}
            min_months = length.get("value", RENTING_TERM)

        # Fallback: otros campos de precio
        if not price_value:
            for field in ("minimumRentalPrice", "rentalPrice", "price"):
                pd = item.get(field)
                if isinstance(pd, dict):
                    price_value = (pd.get("inCents", 0) / 100) or pd.get("amount", 0)
                elif isinstance(pd, (int, float)):
                    price_value = float(pd)
                if price_value:
                    break

        if not price_value:
            return None

        # Ignorar productos no disponibles
        if not item.get("available", True):
            return None

        # URL del producto
        slug = item.get("slug") or ""
        product_url = f"{BASE_URL}/es-es/products/{slug}" if slug else source_url

        # Construir match_text desde el slug (más limpio que el nombre verboso):
        # - quitar conteos de CPU/GPU ("10cpu","8gpu") y años ("2025")
        # - separar tier+número pegados ("fold7"→"fold 7", "flip7"→"flip 7")
        slug_words = slug.replace("-", " ")
        slug_words = re.sub(r"\d+(cpu|gpu|core)s?\b", "", slug_words, flags=re.I)
        slug_words = re.sub(r"\b\d{4}\b", "", slug_words)
        slug_words = re.sub(
            r"\b(fold|flip|plus|mini|air|pro|max|ultra|lite|fe|se)(\d)",
            r"\1 \2", slug_words, flags=re.I,
        )
        match_text = slug_words
        capacity = self._parse_capacity(match_text)

        # Matching con chip M\d ignorado en comparación de números
        target = self._match_target_grover(match_text, capacity)
        if not target:
            return None

        return self._make_row(
            target=target,
            offer_type="renting_no_insurance",
            price_value=round(float(price_value), 2),
            term_months=int(min_months),
            source_url=product_url,
            source_title=name,
        )

    def _match_target_grover(
        self,
        name: str,
        capacity_gb: Optional[int],
        threshold: int = 72,
    ) -> Optional[dict]:
        """
        Variante de _match_target para Grover (strict_variant=True) que ignora
        el número de generación del chip Apple M-series (M3/M4/M5) en ambos lados,
        ya que Grover a veces omite la generación en el nombre del producto.
        """
        from rapidfuzz import fuzz
        _CHIP = re.compile(r"\bm\d\b", re.I)
        _TIER_KW = frozenset({
            "pro", "max", "plus", "air", "ultra", "mini", "lite",
            "fe", "fold", "flip", "e",
        })

        name_norm = self._normalize(name)
        name_nochip = re.sub(r"\s+", " ", _CHIP.sub("", name_norm)).strip()
        name_numbers = self._extract_model_numbers(name_nochip)
        name_tiers = frozenset(t for t in name_norm.split() if t in _TIER_KW)
        name_series = self._extract_galaxy_series(name_norm)

        best_score, best_target = 0, None

        for target in self.targets:
            t_cap = target.get("capacity_gb")
            if capacity_gb and t_cap:
                if int(capacity_gb) != int(t_cap):
                    continue

            t_norm = self._normalize(target["model"])
            t_nochip = re.sub(r"\s+", " ", _CHIP.sub("", t_norm)).strip()
            score = fuzz.token_set_ratio(name_norm, t_norm)

            t_numbers = self._extract_model_numbers(t_nochip)
            t_tiers = frozenset(t for t in t_norm.split() if t in _TIER_KW)
            t_series = self._extract_galaxy_series(t_norm)

            if name_numbers and t_numbers and name_numbers != t_numbers:
                continue
            if name_tiers != t_tiers:
                continue
            if name_series and t_series and name_series != t_series:
                continue

            if score > best_score:
                best_score = score
                best_target = target

        return best_target if best_score >= threshold else None

    @staticmethod
    def _dedupe_rows(rows: list[PriceRow]) -> list[PriceRow]:
        """
        Deduplica filas repetidas por paginaciÃ³n/categorÃ­as.
        Mantiene, para la misma clave, la de menor precio.
        """
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

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _drill_products(data, depth: int = 0) -> list[dict]:
        """Busca recursivamente listas de productos en el JSON de Next.js."""
        if depth > 6:
            return []
        if isinstance(data, list) and data and isinstance(data[0], dict):
            if any(k in data[0] for k in ("name", "title", "slug", "minimumRentalPrice")):
                return data
        if isinstance(data, dict):
            for key in ("products", "items", "edges", "nodes", "results", "data"):
                value = data.get(key)
                if value:
                    result = GroverScraper._drill_products(value, depth + 1)
                    if result:
                        return result
            # Búsqueda genérica en valores dict/list
            for value in data.values():
                if isinstance(value, (dict, list)):
                    result = GroverScraper._drill_products(value, depth + 1)
                    if result:
                        return result
        return []

    def _has_next_page(self, response) -> bool:
        try:
            next_btn = self._css_first(response,
                "[aria-label='Next page'], [data-testid='next-page'], "
                "a[rel='next'], button[class*='next']:not([disabled])"
            )
            return next_btn is not None
        except Exception:
            return False
