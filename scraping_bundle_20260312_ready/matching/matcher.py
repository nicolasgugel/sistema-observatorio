"""
Motor de matching de productos entre distintas fuentes.
Normaliza nombres y usa fuzzy matching (RapidFuzz) para agrupar
el mismo producto de diferentes competidores.
"""
from __future__ import annotations
import re
import unicodedata
from collections import defaultdict
from typing import Optional

from rapidfuzz import fuzz, process

from models.product import Product, ComparisonRow

# Umbral mínimo de similitud para considerar dos productos iguales
MATCH_THRESHOLD = 80

# Stopwords que no aportan al matching de modelo
STOPWORDS = {
    "con", "de", "del", "la", "el", "los", "las", "para", "y", "en",
    "and", "with", "for", "the", "nuevo", "new", "edition", "edicion",
    "reacondicionado", "refurbished", "open", "box",
}


def normalize(text: str) -> str:
    """Normalización completa para matching."""
    # Quitar acentos
    nfkd = unicodedata.normalize("NFKD", text)
    clean = nfkd.encode("ascii", "ignore").decode("ascii").lower()
    # Mantener alfanumérico, espacios y guiones
    clean = re.sub(r"[^a-z0-9\s\-]", " ", clean)
    # Quitar stopwords
    tokens = [t for t in clean.split() if t not in STOPWORDS and len(t) > 1]
    return " ".join(tokens)


def extract_model_key(name: str) -> str:
    """
    Extrae la clave del modelo para matching directo.
    Ej: "Apple iPhone 17 Pro 256GB Titanium Black" → "iphone 17 pro 256gb"
    """
    clean = normalize(name)
    # Extraer serie/modelo conocido
    patterns = [
        r"(iphone\s+\d+(?:\s+(?:pro|air|plus|max|mini))*)",
        r"(ipad\s+(?:pro|air|mini)?\s*(?:m\d)?\s*\d*(?:\.?\d+)?)",
        r"(macbook\s+(?:air|pro)\s*(?:m\d)?)",
        r"(galaxy\s+(?:s|a|z|tab)\s*\d+(?:\+|ultra|plus|fe|fold|flip)?)",
        r"(galaxy\s+z\s+(?:fold|flip)\s*\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, clean, re.IGNORECASE)
        if match:
            base = match.group(1).strip()
            # Añadir almacenamiento si está presente
            storage_match = re.search(r"(\d+\s*(?:gb|tb))", clean)
            if storage_match:
                return f"{base} {storage_match.group(1)}"
            return base
    return clean


def group_products(all_products: list[Product]) -> dict[str, list[Product]]:
    """
    Agrupa productos de distintas fuentes que representan el mismo artículo.
    Retorna un dict: model_key → lista de Products de distintas fuentes.
    """
    groups: dict[str, list[Product]] = defaultdict(list)

    # Primero agrupar por model_id normalizado (matching exacto)
    for product in all_products:
        key = extract_model_key(product.name)
        groups[key].append(product)

    # Luego fusionar grupos que son muy similares (fuzzy)
    merged = _merge_similar_groups(dict(groups))
    return merged


def _merge_similar_groups(
    groups: dict[str, list[Product]]
) -> dict[str, list[Product]]:
    """Fusiona grupos cuyas claves son muy similares (fuzzy >= MATCH_THRESHOLD)."""
    keys = list(groups.keys())
    merged_into: dict[str, str] = {}  # key → canonical_key

    for i, key in enumerate(keys):
        if key in merged_into:
            continue
        for j, other_key in enumerate(keys[i + 1:], i + 1):
            if other_key in merged_into:
                continue
            score = fuzz.token_sort_ratio(key, other_key)
            if score >= MATCH_THRESHOLD:
                # Fusionar other_key en key
                merged_into[other_key] = key

    result: dict[str, list[Product]] = defaultdict(list)
    for key, products in groups.items():
        canonical = merged_into.get(key, key)
        result[canonical].extend(products)

    return dict(result)


def build_comparison_rows(
    grouped: dict[str, list[Product]]
) -> list[ComparisonRow]:
    """
    Construye ComparisonRow a partir de los grupos de productos matchados.
    Cada fila representa un modelo con precios de todas las fuentes disponibles.
    """
    rows = []

    for model_key, products in grouped.items():
        if not products:
            continue

        # Usar el producto de Boutique como referencia, si existe
        boutique_products = [p for p in products if any(
            pp.source == "santander_boutique" for pp in p.prices
        )]
        reference = boutique_products[0] if boutique_products else products[0]

        row = ComparisonRow(
            product_name=reference.name,
            brand=reference.brand,
            category=reference.category,
            storage=reference.storage,
            model_id=model_key,
        )

        # Rellenar precios por fuente
        source_map = {
            "santander_boutique": ("boutique_renting", "boutique_purchase", "boutique_url", "boutique_cuotas"),
            "rentik": ("rentik_renting", None, "rentik_url", None),
            "grover": ("grover_renting", None, "grover_url", None),
            "movistar": ("movistar_renting", None, "movistar_url", None),
            "amazon": (None, "amazon_purchase", None, None),
            "mediamarkt": (None, "mediamarkt_purchase", None, None),
            "apple_store": (None, "apple_official", None, None),
            "samsung_store": (None, "samsung_official", None, None),
        }

        for product in products:
            for price_point in product.prices:
                source = price_point.source
                if source not in source_map:
                    continue
                renting_field, purchase_field, url_field, cuotas_field = source_map[source]

                if price_point.price_type == "renting" and renting_field:
                    # Tomar el precio más bajo de renting para esta fuente
                    current = getattr(row, renting_field)
                    if current is None or price_point.price < current:
                        setattr(row, renting_field, price_point.price)
                        if url_field:
                            setattr(row, url_field, price_point.url)
                        if cuotas_field and price_point.installments:
                            setattr(row, cuotas_field, price_point.installments)

                elif price_point.price_type == "purchase" and purchase_field:
                    current = getattr(row, purchase_field)
                    if current is None or price_point.price < current:
                        setattr(row, purchase_field, price_point.price)
                        if url_field:
                            setattr(row, url_field, price_point.url)

        rows.append(row)

    # Ordenar por categoría y nombre
    rows.sort(key=lambda r: (r.category, r.product_name))
    return rows


def find_best_match(
    target: str, candidates: list[str], threshold: int = MATCH_THRESHOLD
) -> Optional[str]:
    """Encuentra el mejor match de `target` en `candidates`."""
    if not candidates:
        return None
    result = process.extractOne(
        normalize(target),
        [normalize(c) for c in candidates],
        scorer=fuzz.token_sort_ratio,
        score_cutoff=threshold,
    )
    if result:
        idx = result[2]
        return candidates[idx]
    return None
