from __future__ import annotations

from dataclasses import dataclass


SANTANDER_CATALOG_URLS = [
    "https://boutique.bancosantander.es/es/smartphones",
    "https://boutique.bancosantander.es/es/tablets",
    "https://boutique.bancosantander.es/es",
]

SANTANDER_API_BASE = "https://api-boutique.bancosantander.es/rest/v2/mktBoutique"
SANTANDER_API_PARAMS = "lang=es&curr=EUR&region=es-pn&channel=Web"
SANTANDER_SEARCH_PAGE_SIZE = 20
SANTANDER_PHONE_QUERIES = [
    "galaxy",
    "samsung s",
    "samsung a",
    "samsung z flip",
    "samsung z fold",
    "samsung fe",
]

SANTANDER_TABLET_QUERIES = [
    "samsung tab",
    "galaxy tab",
    "tab s",
    "tab a",
    "tab active",
]

SANTANDER_LAPTOP_QUERIES = [
    "samsung galaxy book",
    "galaxy book5",
    "galaxy book5 pro",
    "book5 pro 14 ultra5 16gb 512gb",
]

APPLE_PHONE_QUERIES = [
    "iphone",
    "iphone pro",
    "iphone plus",
    "iphone se",
]

APPLE_TABLET_QUERIES = [
    "ipad",
    "ipad air",
    "ipad pro",
    "ipad mini",
]

APPLE_LAPTOP_QUERIES = [
    "macbook",
    "macbook air",
    "macbook pro",
    "imac",
    "mac mini",
    "mac studio",
    "mac",
]

SUPPORTED_BRANDS = ("Samsung", "Apple")


TARGET_COMPETITORS = [
    "Apple Oficial",
    "Amazon",
    "El Corte InglÃ©s",
    "Grover",
    "Media Markt",
    "Movistar",
    "Qonexa",
    "Rentik",
    "Samsung Oficial",
    "Santander Boutique",
    "Vodafone",
]


RETAILER_SLUGS = {
    "Apple Oficial": "apple_oficial",
    "Amazon": "amazon",
    "El Corte InglÃ©s": "el_corte_ingles",
    "Fnac": "fnac",
    "Grover": "grover",
    "Media Markt": "media_markt",
    "Movistar": "movistar",
    "Orange": "orange",
    "PcComponentes": "pccomponentes",
    "Qonexa": "qonexa",
    "Rentik": "rentik",
    "Samsung Oficial": "samsung_oficial",
    "Santander Boutique": "santander_boutique",
    "Vodafone": "vodafone",
}


SEARCH_URL_TEMPLATES = {
    "Apple Oficial": "https://www.apple.com/es/shop/search/{query}",
    "Amazon": "https://www.amazon.es/s?k={query}",
    "El Corte InglÃ©s": "https://www.elcorteingles.es/electronica/?s={query}",
    "Fnac": "https://www.fnac.es/SearchResult/ResultList.aspx?Search={query}",
    "Grover": "https://www.grover.com/es-es/search?query={query}",
    "Media Markt": "https://www.mediamarkt.es/es/search.html?query={query}",
    "Movistar": "https://www.movistar.es/buscador/?q={query}",
    "Orange": "https://www.orange.es/buscar?query={query}",
    "PcComponentes": "https://www.pccomponentes.com/buscar/?query={query}",
    "Qonexa": "https://qonexa.com/?s={query}",
    "Rentik": "https://rentik.com/?s={query}",
    "Samsung Oficial": "https://www.samsung.com/es/search/?searchvalue={query}",
    "Santander Boutique": "https://boutique.bancosantander.es/es/search?query={query}",
    "Vodafone": "https://www.vodafone.es/c/tienda-online/particulares/?q={query}",
}


@dataclass(frozen=True)
class OfferType:
    code: str
    human_name: str
    keywords: tuple[str, ...]
    price_unit: str
    term_months_default: int | None = None


OFFER_TYPES = [
    OfferType(
        code="renting_no_insurance",
        human_name="Renting SIN Seguro",
        keywords=("renting sin seguro", "sin seguro"),
        price_unit="EUR/month",
    ),
    OfferType(
        code="renting_with_insurance",
        human_name="Renting CON Seguro",
        keywords=("renting con seguro", "con seguro"),
        price_unit="EUR/month",
    ),
    OfferType(
        code="financing_max_term",
        human_name="FinanciaciÃ³n",
        keywords=("financiaciÃ³n", "financiacion", "financiar", "cuotas"),
        price_unit="EUR/month",
        term_months_default=36,
    ),
    OfferType(
        code="cash",
        human_name="Al contado",
        keywords=("al contado", "contado", "pago Ãºnico", "pago unico"),
        price_unit="EUR",
    ),
]


TEXT_TIMEOUT_MS = 20_000

