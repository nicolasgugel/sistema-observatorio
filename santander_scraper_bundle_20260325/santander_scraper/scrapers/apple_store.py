"""
Scraper para Apple Store España (apple.com/es/shop).

Estrategia:
- iPhone: descubre URLs disponibles desde /es/shop/buy-iphone (evita 404s)
  Cada URL puede contener VARIOS modelos (ej. iphone-17-pro sirve Pro Y Pro Max).
  → usa productSelectionData (JSON embebido) con familyType por SKU para separar modelos.
- iPad: slugs fijos conocidos (/es/shop/buy-ipad/*), CSS selectors como fallback.
- Mac: omitidas (comparadores de línea, sin span.dimensionCapacity en SSR).
- Output: cash (precio de compra oficial Apple)
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

BASE_URL = "https://www.apple.com"

# URLs fijas para iPad (usan span.dimensionCapacity correctamente)
_IPAD_SLUGS = ["ipad-pro", "ipad-air", "ipad-mini", "ipad"]

# Slugs iPhone a excluir del descubrimiento (no son páginas de producto)
_IPHONE_SKIP_SLUGS = {"carrier-offers", "compare", "shop", "unlock", "iphone"}

# Tier keywords reutilizados del módulo base
_TIER_KW = frozenset({"pro", "max", "plus", "air", "ultra", "mini", "e"})

DELAY = 1.0


class AppleStoreScraper(CompetitorBase):
    SOURCE_NAME = "apple_store"
    RETAILER = "Apple Store"
    DATA_QUALITY_TIER = "apple_adapter_live"

    async def scrape(self) -> list[PriceRow]:
        rows: list[PriceRow] = []
        fetcher = Fetcher(auto_match=False)

        apple_targets = [t for t in self.targets if t.get("brand", "").lower() == "apple"]
        if not apple_targets:
            logger.info("[Apple Store] Sin targets Apple — omitiendo")
            return []

        logger.info(f"[Apple Store] {len(apple_targets)} targets Apple")

        # 1. Descubrir URLs iPhone reales desde listing page (evita 404s)
        iphone_urls = await self._discover_iphone_urls(fetcher)
        logger.info(f"[Apple Store] {len(iphone_urls)} URLs iPhone en tienda España")

        # 2. URLs fijas iPad
        ipad_urls = [f"{BASE_URL}/es/shop/buy-ipad/{s}" for s in _IPAD_SLUGS]

        for url in iphone_urls + ipad_urls:
            if "/buy-iphone/" in url:
                # iPhone: PSD extrae por familyType → pasar todos los targets Apple.
                # Una sola URL puede contener Pro y Pro Max (iphone-17-pro-max da 404
                # pero sus datos aparecen en iphone-17-pro via productSelectionData).
                url_targets = apple_targets
            else:
                # iPad: filtrar por slug (ipad-pro / ipad-air / ...)
                url_targets = self._targets_for_url(url, apple_targets)
                if not url_targets:
                    logger.debug(f"[Apple Store] Sin targets compatibles para {url} — skip")
                    continue

            logger.debug(f"[Apple Store] Fetching: {url}")
            try:
                response = await asyncio.to_thread(fetcher.get, url, stealthy_headers=True)
            except Exception as e:
                logger.warning(f"[Apple Store] Error en {url}: {e}")
                await asyncio.sleep(DELAY)
                continue

            page_rows = self._parse_model_page(response, url_targets, url)
            rows.extend(page_rows)
            logger.info(f"[Apple Store] {url.split('/')[-1]}: {len(page_rows)} filas")
            await asyncio.sleep(DELAY)

        # Deduplicar cross-page: misma (model, capacity_gb) puede aparecer
        # en varias páginas iPad (ej. ipad-mini y ipad genérico)
        seen: set[tuple] = set()
        deduped: list[PriceRow] = []
        for row in rows:
            key = (row.model, row.capacity_gb)
            if key not in seen:
                seen.add(key)
                deduped.append(row)

        logger.info(f"[Apple Store] Total: {len(deduped)} filas")
        return deduped

    # ------------------------------------------------------------------ #
    # Descubrimiento de URLs                                               #
    # ------------------------------------------------------------------ #

    async def _discover_iphone_urls(self, fetcher) -> list[str]:
        """Obtiene URLs iPhone reales desde la página de listado de Apple Store España."""
        try:
            resp = await asyncio.to_thread(
                fetcher.get, f"{BASE_URL}/es/shop/buy-iphone", stealthy_headers=True
            )
            body = resp.body.decode("utf-8", errors="replace")
            slugs = list(dict.fromkeys(
                re.findall(r'/es/shop/buy-iphone/([a-z0-9-]+)', body)
            ))
            slugs = [s for s in slugs if s not in _IPHONE_SKIP_SLUGS and len(s) > 4]
            logger.debug(f"[Apple Store] iPhones disponibles en España: {slugs}")
            return [f"{BASE_URL}/es/shop/buy-iphone/{s}" for s in slugs]
        except Exception as e:
            logger.warning(f"[Apple Store] Error descubriendo URLs iPhone: {e}")
            return []

    # ------------------------------------------------------------------ #
    # Filtrado de targets por URL (solo para iPad)                        #
    # ------------------------------------------------------------------ #

    def _targets_for_url(self, url: str, targets: list[dict]) -> list[dict]:
        """
        Devuelve los targets compatibles con una URL de Apple Store iPad.

        Para /buy-ipad/ipad-pro -> targets de iPad Pro.
        Fallback por familia (ipad-pro, ipad-air, ...).
        """
        slug = url.split("/")[-1]  # e.g. "ipad-pro"
        slug_norm = slug.replace("-", " ")
        is_ipad = "/buy-ipad/" in url

        if is_ipad:
            targets = [t for t in targets if "ipad" in self._normalize(t["model"])]

        slug_nums = frozenset(re.findall(r'\d+', slug_norm))
        slug_tiers = frozenset(w for w in slug_norm.split() if w in _TIER_KW)

        compatible = []
        for t in targets:
            t_norm = self._normalize(t["model"])
            t_nums = frozenset(re.findall(r'\d+', t_norm))
            t_tiers = frozenset(w for w in t_norm.split() if w in _TIER_KW)

            if slug_nums == t_nums and slug_tiers == t_tiers:
                compatible.append(t)

        if compatible:
            return compatible

        # Fallback iPad: priorizar match por tiers del slug.
        # "ipad-pro" (tiers={'pro'}) → solo iPad Pro targets
        # "ipad-mini" (tiers={'mini'}) → solo iPad mini targets
        # "ipad" (tiers={}) → todos los iPad targets (la página muestra iPad base)
        if slug_tiers:
            return [
                t for t in targets
                if slug_tiers <= frozenset(
                    w for w in self._normalize(t["model"]).split() if w in _TIER_KW
                )
            ]

        return targets

    # ------------------------------------------------------------------ #
    # Parseo de páginas de modelo                                          #
    # ------------------------------------------------------------------ #

    def _parse_model_page(
        self,
        response,
        targets: list[dict],
        source_url: str,
    ) -> list[PriceRow]:
        """
        Extrae pares (modelo, capacidad_GB, precio) de una página de Apple Store.

        Para iPhone: usa productSelectionData (JSON embebido) → familyType discrimina
        entre Pro y Pro Max en la misma página.
        Para iPad (fallback): CSS selectors span.dimensionCapacity + span.current_price.
        """
        if "/buy-iphone/" in source_url:
            # PSD conoce el familyType exacto por SKU → único método fiable para iPhone.
            # El CSS fallback es peligroso aquí porque la misma página puede tener
            # múltiples modelos (Pro + Pro Max) y se pasan todos los targets Apple.
            return self._parse_psd(response, targets, source_url)

        # Fallback CSS (solo iPad — PSD no siempre disponible en páginas de categoría)
        rows: list[PriceRow] = []
        try:
            cap_els = response.css("span.dimensionCapacity")
            price_els = response.css("span.current_price")

            if not cap_els or not price_els:
                logger.debug(f"[Apple Store] Sin capacity/price en {source_url}")
                return []

            seen_cap: set[int] = set()
            for cap_el, price_el in zip(cap_els, price_els):
                cap_text = (cap_el.text or "").strip()
                price_text = (price_el.text or "").strip()

                cap_gb = self._parse_apple_capacity(cap_text)
                price = self._clean_price(price_text)

                if not cap_gb or not price:
                    continue
                if cap_gb in seen_cap:
                    continue  # Duplicados por color
                seen_cap.add(cap_gb)

                matching_target = next(
                    (t for t in targets if t.get("capacity_gb") == cap_gb), None
                )
                if not matching_target and len(targets) == 1:
                    matching_target = targets[0]

                if not matching_target:
                    continue

                model_name = matching_target["model"].replace("Apple ", "")
                rows.append(self._make_row(
                    target=matching_target,
                    offer_type="cash",
                    price_value=price,
                    term_months=None,
                    source_url=source_url,
                    source_title=f"Apple {model_name} {cap_gb}GB",
                ))

        except Exception as e:
            logger.debug(f"[Apple Store] Error parseando pagina CSS: {e}")
        return rows

    def _parse_psd(
        self,
        response,
        targets: list[dict],
        source_url: str,
    ) -> list[PriceRow]:
        """
        Extrae precios de window.PRODUCT_SELECTION_BOOTSTRAP.productSelectionData.

        Cada producto tiene familyType (ej. 'iphone17pro', 'iphone17promax') y
        dimensionCapacity (ej. '256gb', '1tb'), lo que permite separar modelos que
        comparten URL (Pro y Pro Max en iphone-17-pro).
        """
        try:
            body = (
                response.body.decode("utf-8", errors="replace")
                if isinstance(response.body, (bytes, bytearray))
                else str(response.body)
            )

            # Extraer el objeto JSON de productSelectionData
            m = re.search(r'productSelectionData:\s*\{', body)
            if not m:
                return []

            start = m.end() - 1  # apunta al '{'
            depth = 0
            end = start
            for i, ch in enumerate(body[start:]):
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = start + i + 1
                        break
            else:
                return []

            psd = json.loads(body[start:end])
            products = psd.get("products", [])
            prices_dv = psd.get("displayValues", {}).get("prices", {})

            if not products or not prices_dv:
                return []

            # Construir mapa (familyType, cap_gb) → precio mínimo por color
            family_cap_price: dict[tuple, float] = {}
            for p in products:
                family = p.get("familyType", "")
                cap_text = p.get("dimensionCapacity", "")
                price_key = p.get("fullPrice", "")

                cap_gb = self._parse_apple_capacity_str(cap_text)
                if not cap_gb or not price_key or not family:
                    continue

                price_entry = prices_dv.get(price_key, {})
                raw = None
                cp = price_entry.get("currentPrice", {})
                if isinstance(cp, dict):
                    raw = cp.get("raw_amount")
                if raw is None:
                    raw = price_entry.get("amountBeforeTradeIn")
                if not raw:
                    continue

                try:
                    price = float(raw)
                except (ValueError, TypeError):
                    continue

                key = (family, cap_gb)
                if key not in family_cap_price or price < family_cap_price[key]:
                    family_cap_price[key] = price

            rows: list[PriceRow] = []
            for (family, cap_gb), price in family_cap_price.items():
                family_norm = self._familytype_to_norm(family)

                matching_target = next(
                    (
                        t for t in targets
                        if self._normalize(t["model"]) == family_norm
                        and t.get("capacity_gb") == cap_gb
                    ),
                    None,
                )
                if not matching_target:
                    continue

                model_name = matching_target["model"].replace("Apple ", "")
                rows.append(self._make_row(
                    target=matching_target,
                    offer_type="cash",
                    price_value=price,
                    term_months=None,
                    source_url=source_url,
                    source_title=f"Apple {model_name} {cap_gb}GB",
                ))

            logger.debug(
                f"[Apple Store] PSD: {len(rows)} filas desde {source_url.split('/')[-1]} "
                f"({len(family_cap_price)} combinaciones familia×capacidad)"
            )
            return rows

        except Exception as e:
            logger.debug(f"[Apple Store] PSD parse error: {e}")
            return []

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _familytype_to_norm(family: str) -> str:
        """
        Convierte familyType de Apple a nombre normalizado comparable con _normalize().
        'iphone17promax' → 'iphone 17 pro max'
        'iphone17pro'    → 'iphone 17 pro'
        'iphone17e'      → 'iphone 17 e'
        'iphone17'       → 'iphone 17'
        'iphoneair'      → 'iphone air'   (sin número de generación)
        'ipadmini'       → 'ipad mini'
        """
        s = re.sub(r"(\d+)", r" \1 ", family)
        s = s.replace("promax", "pro max")
        # Insertar espacio antes de tier-keywords pegados a letras (e.g. "iphoneair" → "iphone air")
        # Orden: más largas primero para evitar coincidencias parciales
        for kw in ("ultra", "plus", "mini", "air", "max", "pro", "se", "fe"):
            s = re.sub(rf"(?<=[a-z])({re.escape(kw)})(?=\s|$)", rf" \1", s)
        return re.sub(r"\s+", " ", s).strip()

    @staticmethod
    def _parse_apple_capacity_str(text: str) -> Optional[int]:
        """
        Parsea dimensionCapacity de productSelectionData.
        '256gb' → 256, '512gb' → 512, '1tb' → 1024, '2tb' → 2048
        """
        m = re.match(r"^(\d+)(gb|tb)$", text.lower().strip())
        if not m:
            return None
        val, unit = int(m.group(1)), m.group(2)
        return val * 1024 if unit == "tb" else val

    @staticmethod
    def _parse_apple_capacity(text: str) -> Optional[int]:
        """
        Convierte el texto de capacity de CSS selectors a GB.
        "256" → 256 GB, "512" → 512 GB, "1" → 1024 GB (1TB), "2" → 2048 GB (2TB)
        """
        text = text.strip()
        try:
            val = int(text)
        except ValueError:
            return None

        if val <= 4:
            return val * 1024
        return val
