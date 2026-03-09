"""
Scraper para Amazon.es — plataforma de compra de referencia.

Estrategia:
- Búsqueda por producto: una query por cada target (model + capacity)
- Fetcher (curl/TLS fingerprint) — más rápido que Playwright para búsquedas
- Extrae el PRIMER resultado relevante de la página de búsqueda
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
ELECTRONICS_NODE = "3944681031"  # Electrónica Amazon.es
DELAY = 2.0
CONCURRENCY = 5   # peticiones paralelas simultáneas
MAX_RESULTS = 3  # primeros N resultados a considerar por búsqueda

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

        # Deduplicar targets (un target por model+capacity)
        seen = set()
        unique_targets = []
        for t in self.targets:
            key = (t["model"], t.get("capacity_gb"))
            if key not in seen:
                seen.add(key)
                unique_targets.append(t)

        logger.info(f"[Amazon] {len(unique_targets)} productos a buscar")

        sem = asyncio.Semaphore(CONCURRENCY)

        async def fetch_one(target: dict):
            async with sem:
                query = self._build_query(target)
                logger.debug(f"[Amazon] Buscando: {query!r}")
                result = await self._search_product(fetcher, query, target)
                await asyncio.sleep(DELAY)
                return result

        results = await asyncio.gather(*[fetch_one(t) for t in unique_targets])
        rows = [r for r in results if r]

        logger.info(f"[Amazon] Total: {len(rows)} filas")
        return rows

    # ------------------------------------------------------------------ #
    # Búsqueda                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_query(target: dict) -> str:
        """Construye query de búsqueda desde el target de Santander."""
        model = target["model"]  # e.g. "Apple iPhone 17 Pro"
        cap = target.get("capacity_gb")
        if cap:
            return f"{model} {cap}GB"
        return model

    async def _search_product(
        self,
        fetcher: StealthyFetcher,
        query: str,
        target: dict,
    ) -> Optional[PriceRow]:
        search_url = f"{BASE_URL}/s?k={quote_plus(query)}&rh=n:{ELECTRONICS_NODE}"

        try:
            response = await asyncio.to_thread(fetcher.get, search_url, headers=_HEADERS)
        except Exception as e:
            logger.warning(f"[Amazon] Error buscando {query!r}: {e}")
            return None

        # Intentar extraer datos del JSON embebido primero
        row = self._try_json_data(response, target, search_url)
        if row:
            return row

        # Fallback: parsear tarjetas HTML de resultados
        return self._parse_result_cards(response, target, query, search_url)

    def _try_json_data(self, response, target: dict, source_url: str) -> Optional[PriceRow]:
        """Intenta extraer del JSON embebido en la página de Amazon."""
        try:
            import json
            scripts = response.find_all("script")
            for script in scripts:
                text = script.text or ""
                if "amznUncompressedData" in text or '"price"' in text:
                    pass  # Amazon data is complex, fall through to HTML
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
        """Parsea las tarjetas de búsqueda de Amazon para encontrar la mejor coincidencia."""
        try:
            cards = response.css("[data-component-type='s-search-result']")
            if not cards:
                cards = response.css("[data-asin]:not([data-asin=''])")

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
        source_url: str,
    ) -> Optional[tuple[PriceRow, int]]:
        """
        Parsea una tarjeta de Amazon y devuelve (PriceRow, match_score) o None.
        """
        try:
            asin = card.attrib.get("data-asin", "")
            if not asin:
                return None

            # Nombre del producto — en Amazon el título está en h2 span directamente
            name = ""
            for span in card.css("h2 span"):
                t = span.text.strip()
                if len(t) > 10:
                    name = t
                    break
            if not name:
                return None

            # Precio
            price = self._extract_amazon_price(card)
            if not price:
                return None

            # Capacidad del nombre del resultado
            capacity = self._parse_capacity(name)

            # Fuzzy match — verificar que es el producto buscado
            from rapidfuzz import fuzz
            name_norm = self._normalize(name)
            target_norm = self._normalize(target["model"])
            score = fuzz.token_set_ratio(name_norm, target_norm)

            # Penalizar si la capacidad no coincide
            target_cap = target.get("capacity_gb")
            if target_cap and capacity and int(target_cap) != int(capacity):
                score = max(0, score - 30)

            if score < 65:
                return None

            # URL del producto
            link_el = self._css_first(card, "h2 a[href], a[href][class*='s-link']")
            href = self._el_attr(link_el, "href")
            # Limpiar URL de Amazon (quitar tracking params)
            product_url = f"{BASE_URL}{href.split('?')[0]}" if href else source_url
            if asin in product_url or "/dp/" in product_url:
                product_url = f"{BASE_URL}/dp/{asin}"

            # Stock
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
        """Extrae el precio de una tarjeta de Amazon."""
        # Precio en partes: entero + decimal
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

        # Precio en offscreen (accesibilidad)
        offscreen_el = self._css_first(card, ".a-offscreen")
        if offscreen_el:
            text = offscreen_el.text.strip()
            # Formato: "1.299,00€"
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
