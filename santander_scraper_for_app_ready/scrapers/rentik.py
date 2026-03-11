"""
Scraper para Rentik Espana (rentik.com).

La pagina de detalle completa el precio/capacidad real mediante endpoints JSON,
asi que el scraper usa HTML para descubrir producto, colores y plazo, y luego
consulta `bin/detailproduct` para cada capacidad objetivo.
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
JSON_HEADERS = {
    **HEADERS,
    "Accept": "application/json, text/plain, */*",
}

DELAY = 1.5
FUZZY_MIN = 72

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

        product_hrefs = await self._get_nav_hrefs(fetcher)
        logger.info(f"[Rentik] {len(product_hrefs)} URLs de producto del nav")

        if not product_hrefs:
            logger.warning("[Rentik] Homepage no devolvio links - abortando")
            return []

        url_to_targets: dict[str, list[dict]] = {}
        for target in self.targets:
            href = self._match_href(target, product_hrefs)
            if href:
                url_to_targets.setdefault(href, []).append(target)

        logger.info(f"[Rentik] {len(url_to_targets)} paginas de producto a scraper")

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
    # Homepage nav parsing                                               #
    # ------------------------------------------------------------------ #

    async def _get_nav_hrefs(self, fetcher: Fetcher) -> list[str]:
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

            if not href.startswith("/es/ofertas-alquilar/"):
                continue
            if "/unpublish/" in href:
                continue
            if text.startswith("->") or text.lower().startswith("ver "):
                continue

            parts = [p for p in href.strip("/").split("/") if p]
            if len(parts) < 4:
                continue

            hrefs.append(href)

        return hrefs

    # ------------------------------------------------------------------ #
    # URL matching                                                       #
    # ------------------------------------------------------------------ #

    def _match_href(self, target: dict, hrefs: list[str]) -> Optional[str]:
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

            if not model_words:
                continue
            missing = model_words - slug_words
            coverage = 1.0 - len(missing) / len(model_words)

            extra_variants = (slug_words & _VARIANT_WORDS) - model_words
            variant_penalty = 0.4 * len(extra_variants)

            base = float(fuzz.token_set_ratio(model_norm, slug_clean))
            score = base * coverage * max(0.0, 1.0 - variant_penalty)

            if score > best_score:
                best_score = score
                best_href = href

        if best_score >= FUZZY_MIN:
            logger.debug(
                f"[Rentik] Match: {model!r} -> {best_href!r} (score={best_score:.0f})"
            )
            return best_href

        logger.debug(
            f"[Rentik] Sin match para {model!r} "
            f"(mejor={best_score:.0f}, href={best_href!r})"
        )
        return None

    # ------------------------------------------------------------------ #
    # Product page scraping                                              #
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

        name = self._extract_name(response)
        if not name:
            logger.debug(f"[Rentik] Sin nombre en {url}")
            return []

        current_path = self._current_path_from_href(href)
        term_months = self._parse_term_months(response)
        initial_detail = await self._fetch_detail_product(
            fetcher=fetcher,
            current_path=current_path,
            color="",
            capacity="",
            checkparams=False,
        )
        if not initial_detail:
            logger.debug(f"[Rentik] Sin detalle JSON en {url}")
            return []

        capacity_slug_map = self._build_capacity_slug_map(initial_detail)
        if not capacity_slug_map:
            logger.debug(f"[Rentik] Sin capacidades JSON en {url}")
            return []

        color_slugs = self._extract_color_slugs(response)
        selected_color = self._extract_selected_color(initial_detail)
        if selected_color and selected_color not in color_slugs:
            color_slugs.insert(0, selected_color)
        if not color_slugs and selected_color:
            color_slugs = [selected_color]

        rows: list[PriceRow] = []
        for target in targets:
            target_cap = target.get("capacity_gb")
            if not target_cap:
                continue

            capacity_slug = capacity_slug_map.get(int(target_cap))
            if not capacity_slug:
                logger.debug(f"[Rentik] Capacidad no disponible para {name!r}: {target_cap}GB")
                continue

            detail_data, resolved_color, resolved_capacity = await self._pick_detail_for_capacity(
                fetcher=fetcher,
                current_path=current_path,
                colors=color_slugs,
                capacity_slug=capacity_slug,
            )
            if not detail_data or resolved_capacity != capacity_slug:
                logger.debug(
                    f"[Rentik] Sin variante disponible para {name!r} "
                    f"{target_cap}GB (requested={capacity_slug}, resolved={resolved_capacity!r})"
                )
                continue

            terminal = self._extract_terminal(detail_data)
            if not terminal:
                logger.debug(f"[Rentik] Sin terminal JSON para {name!r} {target_cap}GB")
                continue

            price_value = self._clean_price(str(terminal.get("price", "")))
            if price_value is None:
                logger.debug(f"[Rentik] Sin precio JSON para {name!r} {target_cap}GB")
                continue

            stock_value = self._parse_stock(terminal.get("stock"))
            rows.append(
                self._make_row(
                    target=target,
                    offer_type="renting_no_insurance",
                    price_value=price_value,
                    term_months=term_months,
                    source_url=f"{url}?color={resolved_color}&capacity={resolved_capacity}",
                    source_title=f"{name} {int(target_cap)}GB",
                    in_stock=stock_value > 0,
                )
            )

        return rows

    def _extract_name(self, response) -> str:
        title = self._css_first(response, "h1")
        text = (title.text or "").strip() if title else ""
        return text if 3 < len(text) < 80 else ""

    async def _fetch_detail_product(
        self,
        fetcher: Fetcher,
        current_path: str,
        color: str,
        capacity: str,
        checkparams: bool,
    ) -> Optional[dict]:
        try:
            response = await asyncio.to_thread(
                fetcher.get,
                f"{BASE_URL}/bin/detailproduct",
                headers=JSON_HEADERS,
                params={
                    "color": color,
                    "capacity": capacity,
                    "currentPath": current_path,
                    "checkparams": str(checkparams).lower(),
                },
            )
            data = response.json()
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.debug(f"[Rentik] Error detailproduct ({color}, {capacity}): {e}")
            return None

    async def _pick_detail_for_capacity(
        self,
        fetcher: Fetcher,
        current_path: str,
        colors: list[str],
        capacity_slug: str,
    ) -> tuple[Optional[dict], str, str]:
        seen: set[str] = set()
        candidate_colors = [color for color in colors if color]
        candidate_colors.append("")

        fallback_data: Optional[dict] = None
        fallback_color = ""

        for color in candidate_colors:
            if color in seen:
                continue
            seen.add(color)

            detail_data = await self._fetch_detail_product(
                fetcher=fetcher,
                current_path=current_path,
                color=color,
                capacity=capacity_slug,
                checkparams=True,
            )
            terminal = self._extract_terminal(detail_data)
            if terminal and fallback_data is None:
                fallback_data = detail_data
                fallback_color = color

            available = await self._fetch_available_terminal(
                fetcher=fetcher,
                current_path=current_path,
                color=color,
                capacity=capacity_slug,
            )
            if not available:
                continue

            resolved_color = str(available.get("color", "") or color or "")
            resolved_capacity = str(available.get("capacity", "") or "")
            if resolved_capacity != capacity_slug:
                continue

            detail_data = await self._fetch_detail_product(
                fetcher=fetcher,
                current_path=current_path,
                color=resolved_color,
                capacity=resolved_capacity,
                checkparams=True,
            )
            terminal = self._extract_terminal(detail_data)
            if terminal and self._parse_stock(terminal.get("stock")) > 0:
                return detail_data, resolved_color, resolved_capacity

        return fallback_data, fallback_color, ""

    async def _fetch_available_terminal(
        self,
        fetcher: Fetcher,
        current_path: str,
        color: str,
        capacity: str,
    ) -> Optional[dict]:
        try:
            response = await asyncio.to_thread(
                fetcher.get,
                f"{BASE_URL}/bin/availableTerminal",
                headers=JSON_HEADERS,
                params={
                    "color": color,
                    "currentPath": current_path,
                    "capacity": capacity,
                    "minimalStock": "1.0",
                },
            )
            data = response.json()
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.debug(f"[Rentik] Error availableTerminal ({color}, {capacity}): {e}")
            return None

    @staticmethod
    def _extract_terminal(detail_data: Optional[dict]) -> Optional[dict]:
        if not detail_data:
            return None
        terminals = detail_data.get("terminal", [])
        if not terminals:
            return None
        terminal = terminals[0]
        return terminal if isinstance(terminal, dict) else None

    @staticmethod
    def _extract_selected_color(detail_data: dict) -> str:
        selectors = detail_data.get("selectors", [])
        if not selectors:
            return ""
        selector = selectors[0]
        if not isinstance(selector, dict):
            return ""
        return str(selector.get("color", "") or "")

    def _build_capacity_slug_map(self, detail_data: dict) -> dict[int, str]:
        terminal = self._extract_terminal(detail_data)
        if not terminal:
            return {}

        capacity_slug_map: dict[int, str] = {}
        for tag in terminal.get("tagsCapacities", []):
            if not isinstance(tag, str) or "@" not in tag:
                continue
            label, raw_slug = tag.split("@", 1)
            cap_gb = self._parse_capacity(label)
            slug = raw_slug.rsplit("/", 1)[-1].strip()
            if cap_gb and slug:
                capacity_slug_map[int(cap_gb)] = slug
        return capacity_slug_map

    def _extract_color_slugs(self, response) -> list[str]:
        section = self._css_first(response, "section.rentik-detail") or response
        colors: list[str] = []
        seen: set[str] = set()
        for el in section.css("span.color-point[valuetag], span[valuetag]"):
            raw_value = self._el_attr(el, "valuetag")
            color = raw_value.rsplit("/", 1)[-1].strip()
            if color and color not in seen:
                seen.add(color)
                colors.append(color)
        return colors

    @staticmethod
    def _current_path_from_href(href: str) -> str:
        return f"/content/rentik-project{href.rstrip('/')}"

    def _parse_term_months(self, response) -> int:
        section = self._css_first(response, "section.rentik-detail") or response
        term_el = self._css_first(section, ".detail-tag.detail-tag--active")
        term_text = (term_el.text or "").strip() if term_el else ""
        match = re.search(r"(\d+)\s*mes", term_text, re.I)
        return int(match.group(1)) if match else 24

    @staticmethod
    def _parse_stock(value) -> int:
        try:
            return int(float(str(value or "0")))
        except (TypeError, ValueError):
            return 0
