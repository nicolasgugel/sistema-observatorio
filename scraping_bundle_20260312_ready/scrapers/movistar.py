"""
Scraper para Movistar España (movistar.es/moviles/).

Estrategia:
- Listing page /moviles/ → URLs de producto (una por modelo, deduplicadas)
- Página de producto → JSON embebido (props.pageProps.initialState):
    detailedProduct.offers[capacity][color].cards
      - cardFree.currentPrice        → precio cash (compra libre)
      - cardR2R.pvp_fusion_mv        → cuota mensual Swap (Movistar Fusion, 24 meses)
- Fuzzy match de nombre+capacidad contra targets del catálogo Boutique
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

BASE_URL = "https://www.movistar.es"
LISTING_URL = f"{BASE_URL}/moviles/"
DELAY = 2.0

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}

class MovistarScraper(CompetitorBase):
    SOURCE_NAME = "movistar"
    RETAILER = "Movistar"
    DATA_QUALITY_TIER = "movistar_adapter_live"

    async def scrape(self) -> list[PriceRow]:
        rows: list[PriceRow] = []
        fetcher = Fetcher(auto_match=False)

        logger.info("[Movistar] Fetching listing page...")
        try:
            listing_resp = await asyncio.to_thread(
                fetcher.get, LISTING_URL, headers=_HEADERS
            )
        except Exception as e:
            logger.warning(f"[Movistar] Error en listing: {e}")
            return []

        model_urls = self._extract_model_urls(listing_resp)
        logger.info(f"[Movistar] {len(model_urls)} modelos únicos encontrados")

        for url in model_urls:
            await asyncio.sleep(DELAY)
            try:
                resp = await asyncio.to_thread(fetcher.get, url, headers=_HEADERS)
                page_rows = self._parse_product_page(resp, url)
                rows.extend(page_rows)
                logger.debug(
                    f"[Movistar] {url.split('/')[-2]}: {len(page_rows)} filas"
                )
            except Exception as e:
                logger.debug(f"[Movistar] Error en {url}: {e}")

        logger.info(f"[Movistar] Total: {len(rows)} filas")
        return rows

    # ------------------------------------------------------------------ #
    # Extracción de URLs del listing                                       #
    # ------------------------------------------------------------------ #

    def _extract_model_urls(self, response) -> list[str]:
        """Extrae URLs únicas (una por modelo) del listing de movistar.es/moviles/."""
        seen_models: set[str] = set()
        urls: list[str] = []

        for link in response.css("a[href*='/moviles/']") or []:
            href = link.attrib.get("href", "")
            if not href:
                continue
            # Solo slugs de producto (al menos 3 guiones en el segmento final)
            slug = href.strip("/").split("/")[-1]
            if slug.count("-") < 3:
                continue
            model_key = self._slug_to_model(slug)
            if model_key and model_key not in seen_models:
                seen_models.add(model_key)
                full_url = (
                    f"{BASE_URL}{href}" if href.startswith("/") else href
                )
                urls.append(full_url)

        return urls

    @staticmethod
    def _slug_to_model(slug: str) -> Optional[str]:
        """
        Extrae la clave de modelo sin capacidad ni color.
        'apple-iphone-17-pro-256gb-azuloscuro' → 'apple-iphone-17-pro'
        'samsung-galaxy-s25-256gb-azulmarino'  → 'samsung-galaxy-s25'
        """
        m = re.match(r"^((?:[a-z0-9]+-)+?)(\d+(?:gb|tb))-", slug + "-")
        if m:
            return m.group(1).rstrip("-")
        return slug

    # ------------------------------------------------------------------ #
    # Parseo de página de producto                                         #
    # ------------------------------------------------------------------ #

    def _parse_product_page(self, response, source_url: str) -> list[PriceRow]:
        """Extrae precios de todas las capacidades de una página de producto."""
        rows: list[PriceRow] = []
        try:
            data = self._extract_page_json(response)
            if not data:
                logger.debug(f"[Movistar] Sin JSON en {source_url}")
                return []

            dp = (
                data.get("props", {})
                .get("pageProps", {})
                .get("initialState", {})
                .get("device", {})
                .get("detailedProduct", {})
            )
            offers = dp.get("offers", {})
            if not offers:
                logger.debug(f"[Movistar] Sin offers en {source_url}")
                return []

            for cap_str, color_dict in offers.items():
                cap_gb = self._parse_capacity_str(cap_str)
                if not cap_gb or not isinstance(color_dict, dict):
                    continue

                # Tomar el primer color con datos de cards
                first_offer = self._first_valid_offer(color_dict)
                if not first_offer:
                    continue

                cards = first_offer.get("cards", {})
                prod_name = first_offer.get("name", "")

                # ── Cash (cardFree) ────────────────────────────────────
                free_cards = cards.get("cardFree", [])
                if free_cards:
                    free = free_cards[0]
                    cash_price = free.get("currentPrice", 0)
                    if cash_price and float(cash_price) > 0:
                        name = free.get("name") or prod_name
                        target = self._match_target(name, cap_gb)
                        if target:
                            rows.append(
                                self._make_row(
                                    target=target,
                                    offer_type="cash",
                                    price_value=float(cash_price),
                                    term_months=None,
                                    source_url=source_url,
                                    source_title=name,
                                    in_stock=bool(free.get("stock", 1)),
                                )
                            )

                # ── Swap / Movistar Fusion (cardR2R) ───────────────────
                r2r_cards = cards.get("cardR2R", [])
                if r2r_cards:
                    r2r = r2r_cards[0]
                    monthly = self._best_monthly_price(r2r)
                    swap_term = self._best_swap_term(cards)
                    if monthly and monthly > 0:
                        name = r2r.get("name") or prod_name
                        target = self._match_target(name, cap_gb)
                        if target:
                            rows.append(
                                self._make_row(
                                    target=target,
                                    offer_type="renting_no_insurance",
                                    price_value=float(monthly),
                                    term_months=swap_term,
                                    source_url=source_url,
                                    source_title=name,
                                    in_stock=bool(r2r.get("stock", 1)),
                                )
                            )

        except Exception as e:
            logger.debug(f"[Movistar] Error parseando {source_url}: {e}")
        return rows

    @staticmethod
    def _first_valid_offer(color_dict: dict) -> Optional[dict]:
        """Devuelve el primer color que tenga datos de cards."""
        for offer in color_dict.values():
            if isinstance(offer, dict) and offer.get("cards"):
                return offer
        return None

    @staticmethod
    def _best_monthly_price(card: dict) -> Optional[float]:
        """
        Extrae el precio mensual más representativo del Swap.
        Orden de preferencia: pvp_fusion_mv → pvp_fusion_av → pvp_fusion_bv
        Solo devuelve si es > 0.
        """
        for key in ("pvp_fusion_mv", "pvp_fusion_av", "pvp_fusion_bv"):
            val = card.get(key)
            try:
                v = float(val)
                if v > 0:
                    return v
            except (TypeError, ValueError):
                pass
        return None

    @staticmethod
    def _best_swap_term(cards: dict) -> Optional[int]:
        """
        Detecta el plazo visible del plan Swap a partir de los campos de
        mensualidad por plazo presentes en la ficha.
        """
        if not isinstance(cards, dict):
            return None

        candidate_cards = []
        for key in ("cardAditionalR2R", "cardR2R"):
            values = cards.get(key, [])
            if values:
                candidate_cards.extend(v for v in values if isinstance(v, dict))

        for card in candidate_cards:
            for term in (48, 36, 24):
                try:
                    monthly = float(card.get(f"monthlyPayment{term}", -1))
                except (TypeError, ValueError):
                    monthly = -1
                if monthly > 0:
                    return term

            for key in ("swapRenewalPeriod", "quotaMonths"):
                raw = card.get(key)
                try:
                    value = int(float(raw))
                except (TypeError, ValueError):
                    value = 0
                if value > 0:
                    return value

        return None

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_page_json(response) -> Optional[dict]:
        """Extrae el JSON principal del script más grande de la página."""
        scripts = response.find_all("script")
        if not scripts:
            return None
        big = max(scripts, key=lambda s: len(s.text or ""), default=None)
        if big and big.text:
            try:
                data = json.loads(big.text)
                if "props" in data:
                    return data
            except Exception:
                pass
        return None

    @staticmethod
    def _parse_capacity_str(cap_str: str) -> Optional[int]:
        """
        '256 GB' → 256, '512 GB' → 512, '1 TB' → 1024, '2 TB' → 2048
        """
        m = re.match(r"(\d+)\s*(GB|TB)", str(cap_str).strip(), re.IGNORECASE)
        if not m:
            return None
        val, unit = int(m.group(1)), m.group(2).upper()
        return val * 1024 if unit == "TB" else val

    def _match_target(self, name: str, cap_gb: int) -> Optional[dict]:
        """Fuzzy match nombre (sin capacidad) + capacidad contra targets Boutique."""
        # Quitar capacidad del nombre para el match fuzzy
        name_clean = re.sub(
            r"\d+\s*(?:gb|tb)\b", "", name, flags=re.IGNORECASE
        ).strip()
        return super()._match_target(name_clean, cap_gb, threshold=72)
