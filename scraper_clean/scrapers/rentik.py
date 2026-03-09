"""
Scraper para Rentik España (rentik.com).
Plataforma de renting de tecnología — competidor directo en renting.

Estrategia (HTTP, sin Playwright):
1. Carga homepage con Fetcher (HTTP) para extraer URLs de productos del menú.
2. Para cada target, hace fuzzy match contra los slugs de URL.
3. Carga la página de producto individual con HTTP.
4. Parsea: título (h1), capacidad activa (.capacity_badge_active),
   precio mínimo (.item__smartphone-price--number).
5. Crea fila con offer_type=renting_no_insurance y term_months=1.

Nota: el HTTP Fetcher funciona perfectamente (sin timeouts) para este sitio.
      La selección de capacidad es JS-driven, por lo que solo se obtiene
      el precio de la capacidad por defecto (normalmente 128GB para iPhones).
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional

from loguru import logger
from rapidfuzz import fuzz
from scrapling.fetchers import Fetcher

from models.price_row import PriceRow
from scrapers.competitor_base import CompetitorBase

BASE_URL = "https://www.rentik.com"

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.google.com/",
}

DELAY = 1.5
FUZZY_MIN = 72

# Palabras que indican variante de modelo — penalizan si están en slug pero no en target
_VARIANT_WORDS = {
    "ultra", "plus", "edge", "pro", "max", "mini", "lite",
    "fe", "air", "se", "classic",
}


class RentikScraper(CompetitorBase):
    SOURCE_NAME = "rentik"
    RETAILER = "Rentik"
    DATA_QUALITY_TIER = "rentik_adapter_live"

    async def scrape(self) -> list[PriceRow]:
        fetcher = Fetcher(auto_match=False)
        rows: list[PriceRow] = []

        # 1. Obtener URLs de productos desde el nav de la homepage
        product_hrefs = await self._get_nav_hrefs(fetcher)
        logger.info(f"[Rentik] {len(product_hrefs)} URLs de producto del nav")

        if not product_hrefs:
            logger.warning("[Rentik] Homepage no devolvió links — abortando")
            return []

        # 2. Emparejar cada target con su mejor URL
        url_to_targets: dict[str, list[dict]] = {}
        for target in self.targets:
            href = self._match_href(target, product_hrefs)
            if href:
                url_to_targets.setdefault(href, []).append(target)

        logger.info(f"[Rentik] {len(url_to_targets)} páginas de producto a scraper")

        # 3. Scraping de cada página de producto
        for href, targets in url_to_targets.items():
            url = f"{BASE_URL}{href}"
            logger.info(f"[Rentik] Fetching: {url}")
            try:
                page_rows = await self._scrape_product(fetcher, href, targets)
                rows.extend(page_rows)
                slug = href.rstrip("/").split("/")[-1]
                logger.info(f"[Rentik] {slug}: {len(page_rows)} filas")
            except Exception as e:
                logger.error(f"[Rentik] Error en {url}: {e}")
            await asyncio.sleep(DELAY)

        logger.info(f"[Rentik] Total: {len(rows)} filas")
        return rows

    # ------------------------------------------------------------------ #
    # Homepage nav parsing                                                 #
    # ------------------------------------------------------------------ #

    async def _get_nav_hrefs(self, fetcher: Fetcher) -> list[str]:
        """Fetch homepage y extrae hrefs de productos del menú de navegación."""
        try:
            response = await asyncio.to_thread(
                fetcher.get, f"{BASE_URL}/es/", headers=HEADERS
            )
        except Exception as e:
            logger.error(f"[Rentik] Error cargando homepage: {e}")
            return []

        hrefs: list[str] = []
        seen: set[str] = set()

        for link in response.css("a[href]"):
            href = link.attrib.get("href", "") if hasattr(link, "attrib") else ""
            text = (link.text or "").strip()

            if not href or href in seen:
                continue
            seen.add(href)

            # Solo URLs de ofertas con al menos 4 segmentos de ruta
            # /es/ofertas-alquilar/{brand}/{product-slug}/ → 4 segmentos
            if not href.startswith("/es/ofertas-alquilar/"):
                continue
            if "/unpublish/" in href:
                continue
            # Excluir categorías (texto empieza con "->" o "Ver ")
            if text.startswith("->") or text.lower().startswith("ver "):
                continue

            parts = [p for p in href.strip("/").split("/") if p]
            if len(parts) < 4:
                continue  # Categoría, no producto

            hrefs.append(href)

        return hrefs

    # ------------------------------------------------------------------ #
    # URL matching                                                         #
    # ------------------------------------------------------------------ #

    def _match_href(self, target: dict, hrefs: list[str]) -> Optional[str]:
        """
        Fuzzy match del nombre de modelo del target contra los slugs de URL.
        Aplica penalización por palabras variante extra en el slug.
        """
        model = target.get("model", "")
        model_norm = re.sub(r"^(apple|samsung)\s+", "", model, flags=re.IGNORECASE).lower()
        model_norm = re.sub(r"\d+\s*(gb|tb)", "", model_norm, flags=re.I).strip()
        model_words = set(model_norm.split())

        best_href: Optional[str] = None
        best_score: float = 0.0

        for href in hrefs:
            slug = href.rstrip("/").split("/")[-1].lower()
            slug_clean = re.sub(r"[^a-z0-9 ]", " ", slug.replace("-", " "))
            slug_clean = re.sub(r"\b5g\d*\b", "5g", slug_clean).strip()
            slug_words = set(slug_clean.split())

            # Cobertura: palabras del modelo en el slug
            if not model_words:
                continue
            missing = model_words - slug_words
            coverage = 1.0 - len(missing) / len(model_words)

            # Penalización por variantes extra en slug
            extra_variants = (slug_words & _VARIANT_WORDS) - model_words
            variant_penalty = 0.4 * len(extra_variants)

            base = float(fuzz.token_set_ratio(model_norm, slug_clean))
            score = base * coverage * max(0.0, 1.0 - variant_penalty)

            if score > best_score:
                best_score = score
                best_href = href

        if best_score >= FUZZY_MIN:
            logger.debug(
                f"[Rentik] Match: {model!r} → {best_href!r} (score={best_score:.0f})"
            )
            return best_href
        else:
            logger.debug(
                f"[Rentik] Sin match para {model!r} "
                f"(mejor={best_score:.0f}, href={best_href!r})"
            )
            return None

    # ------------------------------------------------------------------ #
    # Product page scraping                                                #
    # ------------------------------------------------------------------ #

    async def _scrape_product(
        self,
        fetcher: Fetcher,
        href: str,
        targets: list[dict],
    ) -> list[PriceRow]:
        url = f"{BASE_URL}{href}"
        try:
            response = await asyncio.to_thread(fetcher.get, url, headers=HEADERS)
        except Exception as e:
            logger.warning(f"[Rentik] Error fetching {url}: {e}")
            return []

        # Título del producto
        name = ""
        for el in response.css("h1"):
            text = (el.text or "").strip()
            if text and 3 < len(text) < 80:
                name = text
                break

        if not name:
            logger.debug(f"[Rentik] Sin nombre en {url}")
            return []

        # Capacidad activa (la que se muestra por defecto — JS no ejecutado)
        cap_el = self._css_first(response, ".capacity_badge_active")
        cap_text = (cap_el.text or "").strip() if cap_el else ""
        cap_gb = self._parse_capacity(cap_text) if cap_text else None

        # Precios de todos los planes (para la capacidad activa)
        price_els = response.css(".item__smartphone-price--number")
        prices: list[float] = []
        seen_p: set[float] = set()
        for el in price_els:
            p = self._clean_price(el.text or "")
            if p and p not in seen_p:
                prices.append(p)
                seen_p.add(p)

        if not prices:
            logger.debug(f"[Rentik] Sin precios en {url}")
            return []

        min_price = min(prices)

        # Match target por nombre (sin filtro de capacidad — precio es para cap activa)
        # Intentar primero match exacto de capacidad, luego fallback al primer target de la URL
        # (targets ya están pre-filtrados por URL matching — no volver a buscar en self.targets)
        matching_target = None
        if cap_gb:
            matching_target = next(
                (t for t in targets if t.get("capacity_gb") == cap_gb), None
            )
        if not matching_target and targets:
            # Fallback: primer target asociado a esta URL (ya fue emparejado por slug matching)
            matching_target = targets[0]

        if not matching_target:
            logger.debug(f"[Rentik] Sin target para {name!r} cap={cap_gb}")
            return []

        # source_title incluye la capacidad real scrapeada
        cap_label = f" {cap_gb}GB" if cap_gb else ""
        source_title = f"{name}{cap_label}"

        return [
            self._make_row(
                target=matching_target,
                offer_type="renting_no_insurance",
                price_value=min_price,
                term_months=1,
                source_url=url,
                source_title=source_title,
            )
        ]
