"""
Scraper para Santander Boutique España.
Usa la API pública SAP Commerce Cloud (Hybris) — sin autenticación necesaria.

Estrategia:
1. Search endpoint → lista de productos base (uno por variante en catálogo)
2. Para cada producto, detail endpoint → baseOptions → variantes únicas por almacenamiento
3. Para cada variante de almacenamiento, detail endpoint → priceGroups con todos los offer_type
4. Genera filas planas compatibles con master_prices.csv
"""
from __future__ import annotations
import asyncio
import re
from typing import Optional
from urllib.parse import quote

from loguru import logger
from scrapling.fetchers import Fetcher

from models.price_row import PriceRow

BASE_API = "https://api-boutique.bancosantander.es/rest/v2/mktBoutique"
BASE_WEB = "https://boutique.bancosantander.es"
COMMON_PARAMS = "lang=es&curr=EUR&region=es-pn&channel=Web"
PAGE_SIZE = 50
SEARCH_PAGE_SIZE_FALLBACKS = (50, 30, 10, 80, 100)
DELAY = 0.3  # segundos entre llamadas API

# Palabras clave que identifican accesorios (se excluyen del CSV)
ACCESSORY_KEYWORDS = [
    "keyboard", "teclado", "folio", "funda", "case", "cover", "magic keyboard",
    "airpods", "airdpods", "watch", "apple watch", "correa", "altavoz",
    "sound tower", "proyector", "music frame", "hub", "adaptador",
]

# Mapeo de palabras clave en nombre → device_type
DEVICE_TYPE_RULES = [
    (["iphone", "galaxy s", "galaxy z", "galaxy a", "galaxy m", "galaxy s25", "galaxy s26"], "mobile"),
    (["ipad mini", "ipad air", "ipad pro", "ipad 1", "galaxy tab", "tab s", "tab a"], "tablet"),
    (["ipad"], "tablet"),  # genérico (después de las variantes específicas)
    (["macbook", "galaxy book", "portátil", "laptop", "book5", "book4"], "laptop"),
    (["mac mini", "mac studio", "imac", "mac pro"], "desktop"),
    (["tv ", "televisor", "qled", "oled tv"], "tv"),
    (["lavadora", "lavavajillas", "combi", "frigorífico", "horno", "aspirador"], "appliance"),
]

# Marcas objetivo (ignorar el resto)
TARGET_BRANDS = {"apple", "samsung"}

# Categorías de device_type que se incluyen en la exportación CSV principal
RELEVANT_DEVICE_TYPES = {"mobile", "tablet", "laptop", "desktop"}

# Patrón para eliminar especificaciones de almacenamiento/RAM del nombre del modelo
# Elimina patrones como: "256GB", "/ 512GB", "- 256gb", "/ 16GB / 512GB" al final
_STORAGE_IN_NAME_RE = re.compile(
    r"(\s*[/,\-]\s*)?\d+\s*(GB|TB)\s*$",
    re.IGNORECASE,
)


class SantanderBoutiqueScraper:
    SOURCE_NAME = "santander_boutique"
    RETAILER = "Santander Boutique"

    def __init__(self, brands: list[str] | None = None, test_mode: bool = False):
        self.brands = [b.lower() for b in (brands or ["apple", "samsung"])]
        self.test_mode = test_mode
        self._fetcher = Fetcher()
        self._headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}

    # ------------------------------------------------------------------ #
    # Punto de entrada principal                                           #
    # ------------------------------------------------------------------ #

    async def scrape(self) -> list[PriceRow]:
        """Devuelve lista de PriceRow listas para exportar a CSV."""
        all_rows: list[PriceRow] = []

        for brand in self.brands:
            if brand not in TARGET_BRANDS:
                logger.warning(f"[Boutique] Marca no soportada: {brand}")
                continue
            brand_cap = brand.capitalize()
            logger.info(f"[Boutique] Scraping marca: {brand_cap}")
            rows = await self._scrape_brand(brand_cap)
            all_rows.extend(rows)
            logger.info(f"[Boutique] {brand_cap}: {len(rows)} filas generadas")
            if brand != self.brands[-1]:
                await asyncio.sleep(DELAY)

        return all_rows

    # ------------------------------------------------------------------ #
    # Búsqueda paginada                                                    #
    # ------------------------------------------------------------------ #

    async def _scrape_brand(self, brand: str) -> list[PriceRow]:
        rows: list[PriceRow] = []
        seen_base_product: set[str] = set()  # (nombre_base, storage)

        page = 0
        total_pages = 1
        page_size = PAGE_SIZE

        while page < total_pages:
            data, page_size = self._fetch_brand_search_page(brand, page, page_size)
            if not data:
                break

            pagination = data.get("pagination", {})
            total_pages = pagination.get("totalPages", 1)
            if page == 0:
                logger.info(
                    f"[Boutique] {brand}: "
                    f"{pagination.get('totalResults', 0)} productos en {total_pages} páginas"
                )

            for item in data.get("products", []):
                product_rows = await self._process_search_item(item, brand, seen_base_product)
                rows.extend(product_rows)
                if self.test_mode and len(rows) >= 5 * 9:  # ~5 productos × ~9 filas
                    return rows

            page += 1
            if page < total_pages:
                await asyncio.sleep(DELAY)

        return rows

    # ------------------------------------------------------------------ #
    # Procesamiento de un producto del search                              #
    # ------------------------------------------------------------------ #

    async def _process_search_item(
        self,
        item: dict,
        brand: str,
        seen: set[str],
    ) -> list[PriceRow]:
        name = item.get("name", "").strip()
        code = item.get("code", "")
        if not name or not code:
            return []

        device_type = self._detect_device_type(name)
        if device_type not in RELEVANT_DEVICE_TYPES:
            logger.debug(f"[Boutique] Omitiendo {name!r} (device_type={device_type})")
            return []

        rows: list[PriceRow] = []

        # Obtener detalle del producto base → baseOptions con todas las variantes
        detail = self._fetch_detail(code)
        if not detail:
            return []

        storage_variants = self._get_storage_variants(detail, code)

        for storage, variant_code in storage_variants.items():
            key = (name.lower(), storage)
            if key in seen:
                continue
            seen.add(key)

            await asyncio.sleep(DELAY)

            # Si el variant_code es el mismo que el code base, reutilizar detail
            if variant_code == code:
                variant_detail = detail
            else:
                variant_detail = self._fetch_detail(variant_code)
                if not variant_detail:
                    continue

            variant_rows = self._extract_price_rows(
                detail=variant_detail,
                brand=brand,
                base_name=name,
                storage=storage,
                device_type=device_type,
                product_code=variant_code,
            )
            rows.extend(variant_rows)

        return rows

    # ------------------------------------------------------------------ #
    # Extracción de variantes de almacenamiento                           #
    # ------------------------------------------------------------------ #

    def _get_storage_variants(self, detail: dict, fallback_code: str) -> dict[str, str]:
        """
        Devuelve {storage_string: first_code} agrupando por almacenamiento único.
        Si no hay baseOptions, intenta extraer almacenamiento de las categorías del producto.
        """
        seen: dict[str, str] = {}

        for bo in detail.get("baseOptions", []):
            for opt in bo.get("options", []):
                qualifiers = {
                    q["qualifier"]: q["value"]
                    for q in opt.get("variantOptionQualifiers", [])
                }
                storage = qualifiers.get("storage", "")
                if storage and storage not in seen:
                    seen[storage] = opt["code"]

        if not seen:
            # Producto sin variantes de almacenamiento (TV, electrodoméstico, etc.)
            # o variante única: extraer storage de categorías
            cats = [c.get("name", "") for c in detail.get("categories", [])]
            storage = next(
                (c for c in cats if re.match(r"\d+\s*(?:GB|TB)", c, re.I)),
                "",
            )
            seen[storage] = fallback_code

        return seen

    # ------------------------------------------------------------------ #
    # Extracción de filas de precio de un product detail                  #
    # ------------------------------------------------------------------ #

    def _extract_price_rows(
        self,
        detail: dict,
        brand: str,
        base_name: str,
        storage: str,
        device_type: str,
        product_code: str = "",
    ) -> list[PriceRow]:
        rows: list[PriceRow] = []

        code = detail.get("code", "") or product_code
        raw_url = detail.get("url", "")
        product_url = f"{BASE_WEB}/es{raw_url}" if raw_url else ""
        in_stock = detail.get("stock", {}).get("stockLevelStatus") == "inStock"
        cap_gb = self._parse_capacity_gb(storage)

        # Nombre de modelo limpio: "Brand CleanName" sin almacenamiento/color
        model = self._clean_model_name(base_name, brand)
        source_title = base_name

        for pg in detail.get("priceGroups", []):
            group_id = pg.get("groupId", "")
            prices = sorted(pg.get("prices", []), key=lambda p: p.get("value", 0))

            if group_id == "renting":
                for i, pr in enumerate(prices[:2]):
                    offer_type = (
                        "renting_no_insurance" if i == 0 else "renting_with_insurance"
                    )
                    term = pr.get("installments", 36)
                    val = pr.get("value", 0.0)
                    rows.append(PriceRow(
                        retailer=self.RETAILER,
                        retailer_slug=self.SOURCE_NAME,
                        product_family=brand,
                        brand=brand,
                        device_type=device_type,
                        model=model,
                        capacity_gb=cap_gb,
                        product_code=code,
                        offer_type=offer_type,
                        price_value=val,
                        price_text=f"{val:.2f} EUR",
                        price_unit="EUR/month",
                        term_months=term,
                        in_stock=in_stock,
                        data_quality_tier="santander_api_live",
                        source_url=product_url,
                        source_title=source_title,
                    ))

            elif group_id == "creditCard":
                for pr in prices:
                    installments = pr.get("installments", 0)
                    val = pr.get("value", 0.0)

                    if installments == 0:
                        # Precio de compra total (cash)
                        rows.append(PriceRow(
                            retailer=self.RETAILER,
                            retailer_slug=self.SOURCE_NAME,
                            product_family=brand,
                            brand=brand,
                            device_type=device_type,
                            model=model,
                            capacity_gb=cap_gb,
                            product_code=code,
                            offer_type="cash",
                            price_value=val,
                            price_text=f"{val:.2f} EUR",
                            price_unit="EUR",
                            term_months=None,
                            in_stock=in_stock,
                            data_quality_tier="santander_api_live",
                            source_url=product_url,
                            source_title=source_title,
                        ))
                    else:
                        # Financiación a N cuotas
                        rows.append(PriceRow(
                            retailer=self.RETAILER,
                            retailer_slug=self.SOURCE_NAME,
                            product_family=brand,
                            brand=brand,
                            device_type=device_type,
                            model=model,
                            capacity_gb=cap_gb,
                            product_code=code,
                            offer_type="financing_max_term",
                            price_value=val,
                            price_text=f"{val:.2f} EUR",
                            price_unit="EUR/month",
                            term_months=installments,
                            in_stock=in_stock,
                            data_quality_tier="santander_api_live",
                            source_url=product_url,
                            source_title=source_title,
                        ))

        return rows

    # ------------------------------------------------------------------ #
    # Helpers HTTP                                                         #
    # ------------------------------------------------------------------ #

    def _fetch_json(self, url: str) -> dict | None:
        try:
            response = self._fetcher.get(
                url,
                headers=self._headers,
                timeout=30,
                retries=2,
            )
            if getattr(response, "status", None) != 200:
                body = (getattr(response, "body", b"") or b"")[:300]
                snippet = body.decode("utf-8", "ignore").strip()
                logger.warning(
                    f"[Boutique] HTTP {response.status} en {url}"
                    + (f" | body={snippet}" if snippet else "")
                )
                return None
            return response.json()
        except Exception as e:
            logger.error(f"[Boutique] Error fetching {url}: {e}")
            return None

    def _fetch_brand_search_page(
        self,
        brand: str,
        page: int,
        preferred_page_size: int,
    ) -> tuple[dict | None, int]:
        tried: list[int] = []
        candidate_sizes = [preferred_page_size]
        candidate_sizes.extend(
            size for size in SEARCH_PAGE_SIZE_FALLBACKS if size not in candidate_sizes
        )

        for page_size in candidate_sizes:
            tried.append(page_size)
            url = (
                f"{BASE_API}/products/search"
                f"?query=:relevance:brand:{quote(brand)}"
                f"&{COMMON_PARAMS}&fields=FULL"
                f"&pageSize={page_size}&currentPage={page}"
            )
            data = self._fetch_json(url)
            if not data:
                continue
            if data.get("type") != "productCategorySearchPageWsDTO":
                logger.warning(
                    f"[Boutique] Respuesta inesperada para {brand} page={page} "
                    f"pageSize={page_size}"
                )
                continue
            return data, page_size

        logger.error(
            f"[Boutique] No se pudo obtener search de {brand} page={page} "
            f"con pageSize {tried}"
        )
        return None, preferred_page_size

    def _fetch_detail(self, code: str) -> dict | None:
        url = (
            f"{BASE_API}/products/{quote(code)}"
            f"?fields=FULL&{COMMON_PARAMS}"
        )
        return self._fetch_json(url)

    # ------------------------------------------------------------------ #
    # Helpers de normalización                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _detect_device_type(name: str) -> str:
        name_lower = name.lower()
        # Accesorios primero (tienen prioridad sobre tablets/móviles)
        if any(kw in name_lower for kw in ACCESSORY_KEYWORDS):
            return "accessory"
        for keywords, dtype in DEVICE_TYPE_RULES:
            if any(kw in name_lower for kw in keywords):
                return dtype
        return "other"

    @staticmethod
    def _parse_capacity_gb(storage: str) -> Optional[int]:
        """Convierte '256GB' → 256, '1TB' → 1024, '' → None."""
        if not storage:
            return None
        # Buscar el último número+unidad en la cadena (por si tiene RAM+storage)
        matches = re.findall(r"(\d+)\s*(GB|TB)", storage.strip(), re.I)
        if not matches:
            return None
        val = int(matches[-1][0])
        unit = matches[-1][1].upper()
        return val * 1024 if unit == "TB" else val

    @staticmethod
    def _clean_model_name(name: str, brand: str) -> str:
        """
        Limpia el nombre del modelo:
        - Elimina la marca si ya está incluida al inicio
        - Elimina especificaciones de almacenamiento y RAM del nombre (en bucle)
        - Elimina caracteres especiales
        """
        # Quitar comillas tipográficas de pulgadas y similares
        name = name.replace("\u2011", "-").replace('"', "").replace("″", "").replace("'", "")
        # Quitar almacenamiento/RAM embebido en bucle (p.ej. "16GB 512GB" → elimina ambos)
        for _ in range(5):
            cleaned = _STORAGE_IN_NAME_RE.sub("", name).strip()
            if cleaned == name:
                break
            name = cleaned
        # Limpiar separadores finales sobrantes ( "/", ",", "-" )
        name = re.sub(r"[\s/,\-]+$", "", name).strip()
        # Evitar doble prefijo de marca ("Samsung Samsung Galaxy...")
        if name.lower().startswith(brand.lower()):
            return name.strip()
        return f"{brand} {name}".strip()
