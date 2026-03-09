"""
Scraper para Movistar Swap / Movistar Conecta (movistar.es).
Servicio de renting/financiación de dispositivos de Telefónica.
Usa DynamicFetcher — el sitio es JS-heavy (React/Angular).

NOTA: La URL exacta del servicio Swap se verifica en ejecución.
Los candidatos conocidos son:
  - https://tiendaonline.movistar.es/moviles
  - https://www.movistar.es/particulares/moviles/catalogo/
"""
from __future__ import annotations
import asyncio
import json
import re
from typing import Optional

from loguru import logger
from scrapling.fetchers import StealthyFetcher

from models.product import Product, PricePoint
from scrapers.base import BaseScraper

BASE_URL = "https://tiendaonline.movistar.es"
FALLBACK_URL = "https://www.movistar.es"

# URLs candidatas (se prueban en orden hasta encontrar productos)
CATEGORY_URLS = {
    "apple": [
        f"{BASE_URL}/moviles?brand=apple",
        f"{BASE_URL}/moviles/iphone",
        f"{FALLBACK_URL}/particulares/moviles/catalogo/?fabricante=Apple",
    ],
    "samsung": [
        f"{BASE_URL}/moviles?brand=samsung",
        f"{BASE_URL}/moviles/samsung",
        f"{FALLBACK_URL}/particulares/moviles/catalogo/?fabricante=Samsung",
    ],
}

DELAY = 3.0


class MovistarSwapScraper(BaseScraper):
    SOURCE_NAME = "movistar"

    async def scrape(self) -> list[Product]:
        products = []
        fetcher = StealthyFetcher

        for brand in self.brands:
            if brand not in CATEGORY_URLS:
                continue
            logger.info(f"[Movistar] Scraping marca: {brand.capitalize()}")
            for url in CATEGORY_URLS[brand]:
                cat_products = await self._try_url(fetcher, url, brand.capitalize())
                if cat_products:
                    products.extend(cat_products)
                    break  # Si esta URL funcionó, no probar las siguientes
                await asyncio.sleep(DELAY)

        return products

    async def _try_url(
        self, fetcher: StealthyFetcher, url: str, brand: str
    ) -> list[Product]:
        logger.debug(f"[Movistar] Probando URL: {url}")
        try:
            response = fetcher.get(url, stealthy_headers=True)
        except Exception as e:
            logger.debug(f"[Movistar] URL fallida {url}: {e}")
            return []

        # Verificar si la página devolvió un 404 o página vacía
        page_text = response.get_content() if hasattr(response, "get_content") else ""
        if "404" in (response.status or "") or not page_text:
            return []

        products = self._try_json_data(response, brand, url)
        if not products:
            products = self._parse_product_cards(response, brand, url)

        return products

    def _try_json_data(self, response, brand: str, source_url: str) -> list[Product]:
        """Intenta extraer datos de JSON embebido (window.__STATE__, __NEXT_DATA__, etc.)."""
        products = []
        try:
            scripts = response.find_all("script")
            for script in scripts:
                text = script.text or ""
                # Buscar patrones de estado de app
                for pattern in [
                    r"window\.__(?:STATE|INITIAL_STATE|DATA)__\s*=\s*(\{.+?\});",
                    r"__NEXT_DATA__",
                ]:
                    if "__NEXT_DATA__" in pattern:
                        el = response.find("script", {"id": "__NEXT_DATA__"})
                        if el:
                            try:
                                data = json.loads(el.text)
                                items = self._find_products_in_json(data)
                                for item in items:
                                    p = self._parse_item(item, brand, source_url)
                                    if p:
                                        products.append(p)
                                if products:
                                    return products
                            except Exception:
                                pass
                    else:
                        match = re.search(pattern, text, re.DOTALL)
                        if match:
                            try:
                                data = json.loads(match.group(1))
                                items = self._find_products_in_json(data)
                                for item in items:
                                    p = self._parse_item(item, brand, source_url)
                                    if p:
                                        products.append(p)
                                if products:
                                    return products
                            except Exception:
                                pass
        except Exception as e:
            logger.debug(f"[Movistar] JSON extraction failed: {e}")
        return products

    def _find_products_in_json(self, data, depth: int = 0) -> list[dict]:
        """Busca recursivamente listas de productos."""
        if depth > 6:
            return []
        if isinstance(data, list) and data and isinstance(data[0], dict):
            if any(k in data[0] for k in ("name", "title", "device", "phone")):
                return data
        if isinstance(data, dict):
            for key in ("products", "items", "devices", "phones", "terminals", "data"):
                if key in data and isinstance(data[key], list):
                    result = self._find_products_in_json(data[key], depth + 1)
                    if result:
                        return result
            for value in data.values():
                if isinstance(value, (dict, list)):
                    result = self._find_products_in_json(value, depth + 1)
                    if result:
                        return result
        return []

    def _parse_product_cards(self, response, brand: str, source_url: str) -> list[Product]:
        """Parsea tarjetas de producto de Movistar HTML."""
        products = []
        try:
            cards = (
                response.css("[class*='product-card']")
                or response.css("[class*='device-card']")
                or response.css("[class*='terminal']")
                or response.find_all("article")
                or response.css("[data-testid*='product']")
            )

            for card in cards:
                try:
                    name_el = card.css_first("h2, h3, h4, [class*='name'], [class*='title']")
                    if not name_el:
                        continue
                    name = name_el.text.strip()
                    if not name or len(name) < 3:
                        continue

                    # Movistar muestra precio mensual (cuota)
                    price_el = card.css_first(
                        "[class*='price'], [class*='mensual'], "
                        "[class*='cuota'], [class*='monthly']"
                    )
                    if not price_el:
                        continue
                    price = self.clean_price(price_el.text)
                    if not price:
                        continue

                    # Tipo de precio: detectar si es mensual/renting
                    card_text = card.text.lower()
                    is_monthly = any(w in card_text for w in ["mes", "mensual", "cuota", "monthly"])
                    price_type = "renting" if is_monthly else "purchase"

                    link = card.css_first("a[href]")
                    href = link.attrib.get("href", "") if link else ""
                    product_url = (
                        f"{BASE_URL}{href}" if href.startswith("/") else (href or source_url)
                    )

                    # Extraer plazo si es renting
                    installments = 0
                    if is_monthly:
                        months_match = re.search(r"(\d+)\s*mes", card_text)
                        installments = int(months_match.group(1)) if months_match else 24

                    storage = self.extract_storage(name)
                    color = self.extract_color(name)
                    category = self.detect_category(name, brand)
                    model_id = self.build_model_id(brand, name, storage)

                    if not self._should_include_category(category):
                        continue

                    product = Product(
                        name=name,
                        brand=brand,
                        category=category,
                        model_id=model_id,
                        raw_name=name,
                        source_code=model_id,
                        storage=storage,
                        color=color,
                    )
                    product.add_price(PricePoint(
                        source=self.SOURCE_NAME,
                        price_type=price_type,
                        price=price,
                        installments=installments,
                        monthly_price=price if is_monthly else None,
                        url=product_url,
                        extra={"operator": "Movistar"},
                    ))
                    products.append(product)
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[Movistar] HTML parse error: {e}")
        return products

    def _parse_item(self, item: dict, brand: str, source_url: str) -> Optional[Product]:
        name = (
            item.get("name") or item.get("title") or
            item.get("deviceName") or item.get("terminal", "")
        )
        if not name:
            return None

        price_value = (
            item.get("price") or item.get("monthlyPrice") or
            item.get("cuota") or item.get("amount")
        )
        if isinstance(price_value, str):
            price_value = self.clean_price(price_value)
        if not price_value:
            return None

        is_monthly = "month" in str(item).lower() or "mes" in str(item).lower()
        price_type = "renting" if is_monthly else "purchase"
        installments = item.get("months") or item.get("installments", 0)

        url = item.get("url") or source_url
        if url and not url.startswith("http"):
            url = f"{BASE_URL}{url}"

        storage = self.extract_storage(name)
        color = self.extract_color(name)
        category = self.detect_category(name, brand)
        model_id = self.build_model_id(brand, name, storage)

        if not self._should_include_category(category):
            return None

        product = Product(
            name=name,
            brand=brand,
            category=category,
            model_id=model_id,
            raw_name=name,
            source_code=str(item.get("id", model_id)),
            storage=storage,
            color=color,
        )
        product.add_price(PricePoint(
            source=self.SOURCE_NAME,
            price_type=price_type,
            price=float(price_value),
            installments=int(installments) if installments else 0,
            monthly_price=float(price_value) if is_monthly else None,
            url=url,
            extra={"operator": "Movistar"},
        ))
        return product
