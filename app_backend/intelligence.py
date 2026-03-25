from __future__ import annotations

import csv
import io
import json
import re
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from app_backend.data_access import list_available_snapshots, load_table_rows
from observatorio.text_utils import normalize_text

SANTANDER_NAME = "Santander Boutique"

MODALITY_LABELS = {
    "renting_no_insurance": "Renting SIN Seguro",
    "renting_with_insurance": "Renting CON Seguro",
    "financing_max_term": "Financiacion",
    "cash": "Al contado",
}

MODALITY_ORDER = {
    "renting_no_insurance": 0,
    "renting_with_insurance": 1,
    "financing_max_term": 2,
    "cash": 3,
}

COMPETITOR_ALIASES = {
    "santander": SANTANDER_NAME,
    "boutique": SANTANDER_NAME,
    "santander boutique": SANTANDER_NAME,
    "amazon": "Amazon",
    "apple oficial": "Apple Oficial",
    "apple store": "Apple Oficial",
    "el corte ingles": "El Corte Ingles",
    "corte ingles": "El Corte Ingles",
    "eci": "El Corte Ingles",
    "grover": "Grover",
    "media markt": "Media Markt",
    "mediamarkt": "Media Markt",
    "movistar": "Movistar",
    "orange": "Orange",
    "rentik": "Rentik",
    "samsung oficial": "Samsung Oficial",
    "samsung store": "Samsung Oficial",
}

POSITIONING_HINTS = (
    "posicionado",
    "posicionamiento",
    "estado",
    "situacion",
    "status",
    "pricing",
    "priceado",
    "como ve",
    "como esta",
    "donde esta",
)

STRATEGY_HINTS = (
    "estrategia",
    "recomendacion",
    "recomendaciones",
    "accion",
    "acciones",
    "deberia",
    "seguir",
    "bundle",
    "bundles",
)


def _parse_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(" ", "")
    if not text:
        return None
    text = text.replace("EUR", "").replace("eur", "")
    text = text.replace("€", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _parse_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = normalize_text(str(value or ""))
    if text in {"true", "1", "yes", "y", "si", "s"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _format_eur(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _format_signed_eur(value: float) -> str:
    prefix = "+" if value > 0 else ""
    return f"{prefix}{_format_eur(value)}"


def _extract_currency(row: dict) -> str:
    price_unit = str(row.get("price_unit") or "")
    if "EUR" in price_unit.upper() or "€" in price_unit:
        return "EUR"
    price_text = str(row.get("price_text") or "")
    if "EUR" in price_text.upper() or "€" in price_text:
        return "EUR"
    return "EUR"


def _record_to_public(raw: dict) -> dict:
    modality = str(raw.get("offer_type") or "")
    return {
        "timestamp_extraccion": str(raw.get("extracted_at") or ""),
        "competidor": str(raw.get("retailer") or ""),
        "url_producto": str(raw.get("source_url") or ""),
        "marca": str(raw.get("brand") or raw.get("product_family") or ""),
        "modelo": str(raw.get("model") or ""),
        "capacidad": _parse_int(raw.get("capacity_gb")),
        "modalidad": modality,
        "modalidad_label": MODALITY_LABELS.get(modality, modality),
        "precio_texto": str(raw.get("price_text") or ""),
        "precio_valor": _parse_float(raw.get("price_value")),
        "moneda": _extract_currency(raw),
        "disponibilidad": _parse_bool(raw.get("in_stock")),
        "device_type": str(raw.get("device_type") or "mobile"),
        "term_months": _parse_int(raw.get("term_months")),
        "quality_tier": str(raw.get("data_quality_tier") or ""),
        "source_title": str(raw.get("source_title") or ""),
        "retailer_slug": str(raw.get("retailer_slug") or ""),
    }


def _load_records_from_path(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("records", [])
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _demo_rows() -> list[dict]:
    now_iso = datetime.now().isoformat()
    return [
        {
            "timestamp_extraccion": now_iso,
            "competidor": "Santander Boutique",
            "url_producto": "https://example.local/samsung-s25-ultra",
            "marca": "Samsung",
            "modelo": "Samsung Galaxy S25 Ultra",
            "capacidad": 256,
            "modalidad": "cash",
            "modalidad_label": MODALITY_LABELS["cash"],
            "precio_texto": "1289.00 EUR",
            "precio_valor": 1289.0,
            "moneda": "EUR",
            "disponibilidad": True,
            "device_type": "mobile",
            "term_months": None,
            "quality_tier": "demo_dataset",
            "source_title": "Samsung Galaxy S25 Ultra",
            "retailer_slug": "santander_boutique",
        },
        {
            "timestamp_extraccion": now_iso,
            "competidor": "Amazon",
            "url_producto": "https://example.local/amazon-samsung-s25-ultra",
            "marca": "Samsung",
            "modelo": "Samsung Galaxy S25 Ultra",
            "capacidad": 256,
            "modalidad": "cash",
            "modalidad_label": MODALITY_LABELS["cash"],
            "precio_texto": "1249.00 EUR",
            "precio_valor": 1249.0,
            "moneda": "EUR",
            "disponibilidad": True,
            "device_type": "mobile",
            "term_months": None,
            "quality_tier": "demo_dataset",
            "source_title": "Samsung Galaxy S25 Ultra",
            "retailer_slug": "amazon",
        },
        {
            "timestamp_extraccion": now_iso,
            "competidor": "Media Markt",
            "url_producto": "https://example.local/mmarkt-samsung-s25-ultra",
            "marca": "Samsung",
            "modelo": "Samsung Galaxy S25 Ultra",
            "capacidad": 256,
            "modalidad": "financing_max_term",
            "modalidad_label": MODALITY_LABELS["financing_max_term"],
            "precio_texto": "52.90 EUR",
            "precio_valor": 52.9,
            "moneda": "EUR",
            "disponibilidad": True,
            "device_type": "mobile",
            "term_months": 24,
            "quality_tier": "demo_dataset",
            "source_title": "Samsung Galaxy S25 Ultra",
            "retailer_slug": "media_markt",
        },
        {
            "timestamp_extraccion": now_iso,
            "competidor": "Santander Boutique",
            "url_producto": "https://example.local/samsung-a56",
            "marca": "Samsung",
            "modelo": "Samsung Galaxy A56 5G",
            "capacidad": 128,
            "modalidad": "renting_with_insurance",
            "modalidad_label": MODALITY_LABELS["renting_with_insurance"],
            "precio_texto": "34.99 EUR",
            "precio_valor": 34.99,
            "moneda": "EUR",
            "disponibilidad": True,
            "device_type": "mobile",
            "term_months": 36,
            "quality_tier": "demo_dataset",
            "source_title": "Samsung Galaxy A56 5G",
            "retailer_slug": "santander_boutique",
        },
        {
            "timestamp_extraccion": now_iso,
            "competidor": "Rentik",
            "url_producto": "https://example.local/rentik-samsung-a56",
            "marca": "Samsung",
            "modelo": "Samsung Galaxy A56 5G",
            "capacidad": 128,
            "modalidad": "renting_with_insurance",
            "modalidad_label": MODALITY_LABELS["renting_with_insurance"],
            "precio_texto": "31.90 EUR",
            "precio_valor": 31.9,
            "moneda": "EUR",
            "disponibilidad": True,
            "device_type": "mobile",
            "term_months": 36,
            "quality_tier": "demo_dataset",
            "source_title": "Samsung Galaxy A56 5G",
            "retailer_slug": "rentik",
        },
    ]


def load_public_rows(brand: str = "Samsung", snapshot_id: str = "current") -> list[dict]:
    table_rows, _ = load_table_rows(snapshot_id=snapshot_id)
    rows: list[dict] = []
    has_real_data = bool(table_rows)

    if table_rows:
        rows = [_record_to_public(raw) for raw in table_rows]
    else:
        rows = _demo_rows()

    if normalize_text(brand) == "all":
        return rows

    brand_n = normalize_text(brand)
    filtered = [row for row in rows if normalize_text(str(row.get("marca") or "")) == brand_n]
    if filtered:
        return filtered

    if has_real_data:
        return []

    return [row for row in _demo_rows() if normalize_text(str(row.get("marca") or "")) == brand_n]


def build_filters_meta(rows: list[dict]) -> dict:
    competitors = sorted({str(r.get("competidor") or "") for r in rows if r.get("competidor")})
    models = sorted({str(r.get("modelo") or "") for r in rows if r.get("modelo")})
    capacities = sorted({int(r["capacidad"]) for r in rows if isinstance(r.get("capacidad"), int)})
    modalities = sorted(
        {str(r.get("modalidad") or "") for r in rows if r.get("modalidad")},
        key=lambda item: MODALITY_ORDER.get(item, 99),
    )
    availability = sorted({r.get("disponibilidad") for r in rows if r.get("disponibilidad") is not None})
    prices = [float(r["precio_valor"]) for r in rows if isinstance(r.get("precio_valor"), (int, float))]
    latest_ts = max((str(r.get("timestamp_extraccion") or "") for r in rows), default="")

    return {
        "competitors": competitors,
        "models": models,
        "capacities": capacities,
        "modalities": [
            {
                "value": modality,
                "label": MODALITY_LABELS.get(modality, modality),
            }
            for modality in modalities
        ],
        "availability": availability,
        "price_min": min(prices) if prices else None,
        "price_max": max(prices) if prices else None,
        "latest_timestamp": latest_ts,
        "total_records": len(rows),
    }


def _normalize_list(values: Iterable[str] | None) -> set[str]:
    if not values:
        return set()

    normalized: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        for part in text.split(","):
            pn = normalize_text(part)
            if pn:
                normalized.add(pn)
    return normalized


def apply_filters(
    rows: list[dict],
    *,
    competitors: Iterable[str] | None = None,
    models: Iterable[str] | None = None,
    capacities: Iterable[int] | None = None,
    modalities: Iterable[str] | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    availability: bool | None = None,
    search: str | None = None,
) -> list[dict]:
    comp_set = _normalize_list(competitors)
    model_set = _normalize_list(models)
    capacity_set = {int(c) for c in capacities} if capacities else set()
    modality_set = _normalize_list(modalities)
    search_n = normalize_text(search or "")

    filtered: list[dict] = []
    for row in rows:
        competitor_n = normalize_text(str(row.get("competidor") or ""))
        if comp_set and competitor_n not in comp_set:
            continue

        model_n = normalize_text(str(row.get("modelo") or ""))
        if model_set and model_n not in model_set:
            continue

        capacity = row.get("capacidad")
        if capacity_set and capacity not in capacity_set:
            continue

        modality_n = normalize_text(str(row.get("modalidad") or ""))
        if modality_set and modality_n not in modality_set:
            continue

        price_value = row.get("precio_valor")
        if min_price is not None and isinstance(price_value, (int, float)) and float(price_value) < min_price:
            continue
        if max_price is not None and isinstance(price_value, (int, float)) and float(price_value) > max_price:
            continue

        if availability is not None and row.get("disponibilidad") is not availability:
            continue

        if search_n:
            haystack = normalize_text(
                " ".join(
                    [
                        str(row.get("competidor") or ""),
                        str(row.get("modelo") or ""),
                        str(row.get("marca") or ""),
                        str(row.get("modalidad") or ""),
                        str(row.get("capacidad") or ""),
                    ]
                )
            )
            if search_n not in haystack:
                continue

        filtered.append(row)

    return filtered


def sort_rows(rows: list[dict], sort_by: str = "precio_valor", sort_dir: str = "asc") -> list[dict]:
    reverse = normalize_text(sort_dir) == "desc"

    def key(row: dict) -> tuple:
        value = row.get(sort_by)
        if isinstance(value, str):
            return (0, normalize_text(value))
        if value is None:
            return (1, 0)
        return (0, value)

    return sorted(rows, key=key, reverse=reverse)


def paginate_rows(rows: list[dict], page: int = 1, page_size: int = 30) -> tuple[list[dict], int]:
    safe_page = max(page, 1)
    safe_size = max(min(page_size, 500), 1)
    start = (safe_page - 1) * safe_size
    end = start + safe_size
    return rows[start:end], len(rows)


def _group_key(row: dict) -> tuple[str, int | None, str]:
    return (
        str(row.get("modelo") or ""),
        row.get("capacidad"),
        str(row.get("modalidad") or ""),
    )


def _price_sort_value(row: dict) -> float:
    price = row.get("precio_valor")
    if isinstance(price, (int, float)):
        return float(price)
    return float("inf")


def build_comparator_payload(rows: list[dict]) -> dict:
    grouped: dict[tuple[str, int | None, str], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[_group_key(row)].append(row)

    items: list[dict] = []
    bars: list[dict] = []
    for key, offers in grouped.items():
        model, capacity, modality = key
        sorted_offers = sorted(offers, key=_price_sort_value)
        santander = next(
            (row for row in sorted_offers if normalize_text(str(row.get("competidor") or "")) == normalize_text(SANTANDER_NAME)),
            None,
        )
        santander_price = santander.get("precio_valor") if santander else None

        enriched_offers = []
        for row in sorted_offers:
            offer = dict(row)
            current_price = offer.get("precio_valor")
            if isinstance(santander_price, (int, float)) and isinstance(current_price, (int, float)):
                diff = float(current_price) - float(santander_price)
                offer["diferencial_vs_santander"] = round(diff, 2)
                offer["diferencial_pct_vs_santander"] = round((diff / float(santander_price)) * 100, 2) if santander_price else None
            else:
                offer["diferencial_vs_santander"] = None
                offer["diferencial_pct_vs_santander"] = None
            enriched_offers.append(offer)

        best_offer = next((o for o in enriched_offers if isinstance(o.get("precio_valor"), (int, float))), None)
        best_price = best_offer.get("precio_valor") if best_offer else None

        santander_diff = None
        if isinstance(best_price, (int, float)) and isinstance(santander_price, (int, float)):
            santander_diff = round(float(santander_price) - float(best_price), 2)

        items.append(
            {
                "modelo": model,
                "capacidad": capacity,
                "modalidad": modality,
                "modalidad_label": MODALITY_LABELS.get(modality, modality),
                "mejor_competidor": best_offer.get("competidor") if best_offer else None,
                "mejor_precio": best_price,
                "precio_santander": santander_price,
                "ahorro_vs_santander": santander_diff,
                "ofertas": enriched_offers,
            }
        )

        if isinstance(best_price, (int, float)):
            bars.append(
                {
                    "producto": f"{model} {capacity or ''}GB".strip(),
                    "modalidad": modality,
                    "modalidad_label": MODALITY_LABELS.get(modality, modality),
                    "mejor_precio": round(float(best_price), 2),
                    "santander": round(float(santander_price), 2) if isinstance(santander_price, (int, float)) else None,
                    "gap_vs_santander": santander_diff,
                }
            )

    items.sort(key=lambda item: (normalize_text(item["modelo"]), item.get("capacidad") or 0, MODALITY_ORDER.get(item["modalidad"], 99)))
    bars.sort(key=lambda item: (normalize_text(item["producto"]), MODALITY_ORDER.get(item["modalidad"], 99)))

    return {
        "groups": items,
        "bars": bars,
        "total_groups": len(items),
    }


def _coverage_by_competitor(rows: list[dict]) -> list[dict]:
    santander_keys = {
        (str(r.get("modelo") or ""), r.get("capacidad"))
        for r in rows
        if normalize_text(str(r.get("competidor") or "")) == normalize_text(SANTANDER_NAME)
    }
    total_base = len(santander_keys)

    by_comp: dict[str, set[tuple[str, int | None]]] = defaultdict(set)
    for row in rows:
        competitor = str(row.get("competidor") or "")
        key = (str(row.get("modelo") or ""), row.get("capacidad"))
        by_comp[competitor].add(key)

    coverage = []
    for competitor, keys in by_comp.items():
        if normalize_text(competitor) == normalize_text(SANTANDER_NAME):
            continue
        matched = len(keys.intersection(santander_keys)) if total_base else 0
        coverage.append(
            {
                "competidor": competitor,
                "matched_models": matched,
                "total_base_models": total_base,
                "coverage_pct": round((matched / total_base) * 100, 2) if total_base else 0.0,
            }
        )

    coverage.sort(key=lambda item: item["coverage_pct"], reverse=True)
    return coverage


def _avg_price_by_modality(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        modality = str(row.get("modalidad") or "")
        price = row.get("precio_valor")
        if modality and isinstance(price, (int, float)):
            grouped[modality].append(float(price))

    result = []
    for modality, values in grouped.items():
        result.append(
            {
                "modalidad": modality,
                "modalidad_label": MODALITY_LABELS.get(modality, modality),
                "precio_medio": round(statistics.fmean(values), 2),
                "muestras": len(values),
            }
        )

    result.sort(key=lambda item: MODALITY_ORDER.get(item["modalidad"], 99))
    return result


def _gap_vs_santander(rows: list[dict]) -> list[dict]:
    santander_by_key: dict[tuple[str, int | None, str], float] = {}
    for row in rows:
        if normalize_text(str(row.get("competidor") or "")) != normalize_text(SANTANDER_NAME):
            continue
        price = row.get("precio_valor")
        if not isinstance(price, (int, float)):
            continue
        santander_by_key[_group_key(row)] = float(price)

    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        competitor = str(row.get("competidor") or "")
        if normalize_text(competitor) == normalize_text(SANTANDER_NAME):
            continue

        price = row.get("precio_valor")
        if not isinstance(price, (int, float)):
            continue

        key = _group_key(row)
        santander_price = santander_by_key.get(key)
        if santander_price is None:
            continue

        grouped[competitor].append(float(price) - santander_price)

    result = []
    for competitor, diffs in grouped.items():
        result.append(
            {
                "competidor": competitor,
                "gap_medio": round(statistics.fmean(diffs), 2),
                "muestras": len(diffs),
            }
        )

    result.sort(key=lambda item: item["gap_medio"])
    return result


def _price_by_competitor(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        competitor = str(row.get("competidor") or "")
        price = row.get("precio_valor")
        if competitor and isinstance(price, (int, float)):
            grouped[competitor].append(float(price))

    result = []
    for competitor, values in grouped.items():
        result.append(
            {
                "competidor": competitor,
                "precio_medio": round(statistics.fmean(values), 2),
                "precio_min": round(min(values), 2),
                "precio_max": round(max(values), 2),
                "muestras": len(values),
            }
        )

    result.sort(key=lambda item: item["precio_medio"])
    return result


def _price_by_model(rows: list[dict], *, top_n: int = 12) -> list[dict]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        model = str(row.get("modelo") or "")
        price = row.get("precio_valor")
        if model and isinstance(price, (int, float)):
            grouped[model].append(float(price))

    sorted_models = sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True)[:top_n]
    result = [
        {
            "modelo": model,
            "precio_medio": round(statistics.fmean(values), 2),
            "muestras": len(values),
        }
        for model, values in sorted_models
    ]
    result.sort(key=lambda item: item["precio_medio"])
    return result


def _temporal_evolution(*, brand: str, limit_snapshots: int = 24) -> list[dict]:
    snapshots = list_available_snapshots(limit=limit_snapshots)
    series: list[dict] = []

    for snapshot in reversed(snapshots):
        json_path = Path(snapshot.get("json_path") or "")
        raw_rows = _load_records_from_path(json_path)
        if not raw_rows:
            continue

        public_rows = [_record_to_public(row) for row in raw_rows]
        if normalize_text(brand) != "all":
            brand_n = normalize_text(brand)
            public_rows = [row for row in public_rows if normalize_text(str(row.get("marca") or "")) == brand_n]

        grouped: dict[str, list[float]] = defaultdict(list)
        for row in public_rows:
            competitor = str(row.get("competidor") or "")
            price = row.get("precio_valor")
            if competitor and isinstance(price, (int, float)):
                grouped[competitor].append(float(price))

        snapshot_ts = str(snapshot.get("created_at") or "")
        if not snapshot_ts:
            snapshot_ts = max((str(r.get("timestamp_extraccion") or "") for r in public_rows), default="")

        for competitor, values in grouped.items():
            series.append(
                {
                    "timestamp": snapshot_ts,
                    "competidor": competitor,
                    "precio_medio": round(statistics.fmean(values), 2),
                }
            )

    return series


def build_dashboard_payload(rows: list[dict], *, brand: str) -> dict:
    latest_ts = max((str(r.get("timestamp_extraccion") or "") for r in rows), default="")
    unique_models = {(str(r.get("modelo") or ""), r.get("capacidad")) for r in rows}
    competitors = {str(r.get("competidor") or "") for r in rows if r.get("competidor")}

    kpis = {
        "registros": len(rows),
        "productos_unicos": len(unique_models),
        "competidores_activos": len(competitors),
        "timestamp_ultima_extraccion": latest_ts,
    }

    return {
        "kpis": kpis,
        "coverage_by_competitor": _coverage_by_competitor(rows),
        "avg_price_by_modality": _avg_price_by_modality(rows),
        "gap_vs_santander": _gap_vs_santander(rows),
        "price_by_competitor": _price_by_competitor(rows),
        "price_by_model": _price_by_model(rows),
        "temporal_evolution": _temporal_evolution(brand=brand),
    }


def export_rows(rows: list[dict], fmt: str) -> tuple[bytes, str, str]:
    fmt_n = normalize_text(fmt)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if fmt_n == "json":
        payload = {
            "count": len(rows),
            "generated_at": datetime.now().isoformat(),
            "records": rows,
        }
        return (
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            "application/json",
            f"santander_price_intelligence_{timestamp}.json",
        )

    output = io.StringIO()
    fieldnames = [
        "timestamp_extraccion",
        "competidor",
        "url_producto",
        "marca",
        "modelo",
        "capacidad",
        "modalidad",
        "modalidad_label",
        "precio_texto",
        "precio_valor",
        "moneda",
        "disponibilidad",
        "device_type",
        "term_months",
        "quality_tier",
        "source_title",
        "retailer_slug",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return (
        output.getvalue().encode("utf-8"),
        "text/csv",
        f"santander_price_intelligence_{timestamp}.csv",
    )


def _extract_capacity(question_n: str) -> int | None:
    gb_match = re.search(r"(\d{2,4})\s*gb", question_n)
    if gb_match:
        return int(gb_match.group(1))

    tb_match = re.search(r"(\d)\s*tb", question_n)
    if tb_match:
        return int(tb_match.group(1)) * 1024

    return None


def _extract_competitor(question_n: str, rows: list[dict]) -> str | None:
    for alias, canonical in sorted(COMPETITOR_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in question_n:
            return canonical

    competitors = sorted(
        {str(row.get("competidor") or "") for row in rows if row.get("competidor")},
        key=len,
        reverse=True,
    )
    for competitor in competitors:
        competitor_n = normalize_text(competitor)
        if competitor_n and competitor_n in question_n:
            return competitor
    return None


def _is_positioning_question(question_n: str) -> bool:
    return any(token in question_n for token in POSITIONING_HINTS)


def _is_strategy_question(question_n: str) -> bool:
    return any(token in question_n for token in STRATEGY_HINTS)


def _product_key_without_modality(row: dict) -> tuple[str, int | None]:
    return (
        str(row.get("modelo") or ""),
        row.get("capacidad"),
    )


def _best_price_by_sku_and_competitor(rows: list[dict]) -> dict[tuple[str, int | None], dict[str, float]]:
    best_prices: dict[tuple[str, int | None], dict[str, float]] = defaultdict(dict)
    for row in rows:
        competitor = str(row.get("competidor") or "")
        model = str(row.get("modelo") or "")
        price = row.get("precio_valor")
        if not competitor or not model or not isinstance(price, (int, float)):
            continue
        key = _product_key_without_modality(row)
        current = best_prices[key].get(competitor)
        numeric_price = float(price)
        if current is None or numeric_price < current:
            best_prices[key][competitor] = numeric_price
    return best_prices


def _summarize_competitor_positioning(question_n: str, rows: list[dict], competitor: str) -> dict | None:
    competitor_rows = [
        row
        for row in rows
        if normalize_text(str(row.get("competidor") or "")) == normalize_text(competitor)
    ]
    if not competitor_rows:
        return None

    sku_count = len({_product_key_without_modality(row) for row in competitor_rows if row.get("modelo")})
    if sku_count == 0:
        return None

    best_by_sku = _best_price_by_sku_and_competitor(rows)
    sku_counts_by_competitor: dict[str, int] = defaultdict(int)
    prices_by_competitor: dict[str, list[float]] = defaultdict(list)
    for competitors in best_by_sku.values():
        for name, price in competitors.items():
            sku_counts_by_competitor[name] += 1
            prices_by_competitor[name].append(price)

    coverage_sorted = sorted(sku_counts_by_competitor.items(), key=lambda item: (-item[1], normalize_text(item[0])))
    coverage_rank = next((index + 1 for index, item in enumerate(coverage_sorted) if item[0] == competitor), None)

    relevant_threshold = max(5, round(sku_count * 0.3))
    relevant_avg_prices = {
        name: statistics.fmean(values)
        for name, values in prices_by_competitor.items()
        if values and (sku_counts_by_competitor.get(name, 0) >= relevant_threshold or name == competitor)
    }
    avg_price = relevant_avg_prices.get(competitor)
    price_sorted = sorted(relevant_avg_prices.items(), key=lambda item: (item[1], normalize_text(item[0])))
    price_leader = price_sorted[0] if price_sorted else None

    matched_products: list[dict] = []
    for key, competitors in best_by_sku.items():
        own_price = competitors.get(competitor)
        rivals = [(name, price) for name, price in competitors.items() if name != competitor]
        if own_price is None or not rivals:
            continue
        best_rival, best_rival_price = min(rivals, key=lambda item: item[1])
        matched_products.append(
            {
                "modelo": key[0],
                "capacidad": key[1],
                "precio_competidor": own_price,
                "mejor_rival": best_rival,
                "precio_mejor_rival": best_rival_price,
                "gap_vs_best": own_price - best_rival_price,
            }
        )

    matched_count = len(matched_products)
    wins = sum(1 for item in matched_products if item["gap_vs_best"] <= 0)
    losses = sum(1 for item in matched_products if item["gap_vs_best"] > 0)
    avg_gap = statistics.fmean(item["gap_vs_best"] for item in matched_products) if matched_products else None

    terms = sorted({int(row["term_months"]) for row in competitor_rows if isinstance(row.get("term_months"), int)})
    modality = str(competitor_rows[0].get("modalidad_label") or competitor_rows[0].get("modalidad") or "").strip()

    if coverage_rank == 1 and avg_gap is not None and avg_gap <= 5:
        positioning_label = "bien posicionado"
    elif avg_gap is not None and avg_gap <= 0:
        positioning_label = "competitivo"
    elif avg_gap is not None and avg_gap <= 15:
        positioning_label = "correcto, pero no lider"
    else:
        positioning_label = "por encima del mercado"

    evidence_rows = sorted(competitor_rows, key=_price_sort_value)

    if _is_strategy_question(question_n):
        focus_products = [
            item["modelo"]
            for item in sorted(matched_products, key=lambda item: item["gap_vs_best"], reverse=True)
            if item["gap_vs_best"] > 0
        ][:3]
        focus_text = ", ".join(focus_products) if focus_products else "los SKUs donde hoy pierde frente al mejor rival"
        parts = [
            (
                f"Yo iria a ajuste quirurgico, no a rebaja masiva: {competitor} tiene {sku_count} SKUs en {modality.lower()}"
                + (f" y lidera por cobertura en este corte." if coverage_rank == 1 else ".")
            )
        ]
        if matched_count and avg_gap is not None:
            parts.append(
                f"En comparables directos gana {wins}/{matched_count} y su gap medio frente al mejor rival es {_format_signed_eur(avg_gap)} EUR/mes."
            )
        if focus_text:
            parts.append(f"Accion clara: revisar {focus_text} y defender el resto con bundles o valor anadido.")
        return {
            "answer": " ".join(parts),
            "evidence": _build_evidence(evidence_rows),
            "intent": "competitor_strategy",
        }

    lines = [
        f"En {modality.lower()}, {competitor} esta {positioning_label}: {sku_count} SKUs"
        + (f", la mayor cobertura del current." if coverage_rank == 1 else ".")
    ]
    if matched_count and avg_gap is not None:
        lines.append(
            f"En comparables directos gana {wins}/{matched_count} y el gap medio frente al mejor rival es {_format_signed_eur(avg_gap)} EUR/mes."
        )
    elif avg_price is not None and price_leader is not None:
        lines.append(
            f"Referencia de precio: {competitor} marca { _format_eur(avg_price) } EUR de mejor cuota media por SKU frente a {price_leader[0]} ({ _format_eur(price_leader[1]) } EUR)."
        )
    if terms:
        if len(terms) == 1:
            lines.append(f"Plazo visible: {terms[0]} meses.")
        else:
            lines.append(f"Plazos visibles: {terms[0]}-{terms[-1]} meses.")
    return {
        "answer": " ".join(lines),
        "evidence": _build_evidence(evidence_rows),
        "intent": "competitor_positioning",
    }


def _extract_model(question_n: str, rows: list[dict]) -> str | None:
    models = sorted({str(row.get("modelo") or "") for row in rows if row.get("modelo")}, key=len, reverse=True)
    for model in models:
        model_n = normalize_text(model)
        if model_n and model_n in question_n:
            return model
    return None


def _extract_modalities(question_n: str) -> list[str]:
    if "al contado" in question_n or "contado" in question_n or "cash" in question_n:
        return ["cash"]
    if "financi" in question_n:
        return ["financing_max_term"]
    if "renting con seguro" in question_n:
        return ["renting_with_insurance"]
    if "renting sin seguro" in question_n:
        return ["renting_no_insurance"]
    if "renting" in question_n:
        return ["renting_no_insurance", "renting_with_insurance"]
    return []


def _build_evidence(rows: list[dict], *, limit: int = 5) -> list[dict]:
    evidence = []
    for row in rows[:limit]:
        evidence.append(
            {
                "competidor": row.get("competidor"),
                "modelo": row.get("modelo"),
                "capacidad": row.get("capacidad"),
                "modalidad": row.get("modalidad"),
                "precio_valor": row.get("precio_valor"),
                "timestamp_extraccion": row.get("timestamp_extraccion"),
                "url_producto": row.get("url_producto"),
            }
        )
    return evidence


def answer_agent_question(question: str, rows: list[dict]) -> dict:
    question_n = normalize_text(question)
    if not rows:
        return {
            "answer": "No hay datos cargados para responder. Ejecuta una actualizacion primero.",
            "evidence": [],
            "intent": "no_data",
        }

    model = _extract_model(question_n, rows)
    capacity = _extract_capacity(question_n)
    modalities = _extract_modalities(question_n)
    competitor = _extract_competitor(question_n, rows)

    scoped = rows
    if model:
        scoped = [row for row in scoped if str(row.get("modelo") or "") == model]
    if capacity is not None:
        scoped = [row for row in scoped if row.get("capacidad") == capacity]
    if modalities:
        modal_n = {normalize_text(mod) for mod in modalities}
        scoped = [row for row in scoped if normalize_text(str(row.get("modalidad") or "")) in modal_n]

    scope_sorted = sorted(scoped, key=_price_sort_value)

    if competitor and (_is_positioning_question(question_n) or _is_strategy_question(question_n)):
        outcome = _summarize_competitor_positioning(question_n, scope_sorted if scope_sorted else rows, competitor)
        if outcome is not None:
            return outcome

    if "cobertura" in question_n:
        coverage = _coverage_by_competitor(scoped if scoped else rows)
        if not coverage:
            return {
                "answer": "No hay comparativas suficientes para calcular cobertura frente a Santander Boutique.",
                "evidence": _build_evidence(scope_sorted),
                "intent": "coverage",
            }

        top = coverage[0]
        modality_text = ""
        if modalities:
            labels = [MODALITY_LABELS.get(mod, mod) for mod in modalities]
            modality_text = f" en {' + '.join(labels)}"

        return {
            "answer": (
                f"El competidor con mejor cobertura{modality_text} es {top['competidor']} "
                f"con {top['coverage_pct']}% ({top['matched_models']}/{top['total_base_models']} modelos base)."
            ),
            "evidence": coverage[:5],
            "intent": "coverage",
        }

    wants_cheapest = any(token in question_n for token in ["barato", "mejor precio", "mas economico", "economico"])
    if wants_cheapest:
        if not scope_sorted:
            return {
                "answer": "No encuentro registros que coincidan con esa consulta.",
                "evidence": [],
                "intent": "cheapest",
            }

        best = scope_sorted[0]
        answer = (
            f"El mejor precio es {best.get('precio_valor')} {best.get('moneda')} en {best.get('competidor')} "
            f"para {best.get('modelo')} {best.get('capacidad') or ''}GB ({MODALITY_LABELS.get(str(best.get('modalidad') or ''), best.get('modalidad'))})."
        )

        santander = next(
            (
                row
                for row in scope_sorted
                if normalize_text(str(row.get("competidor") or "")) == normalize_text(SANTANDER_NAME)
            ),
            None,
        )
        if santander and isinstance(best.get("precio_valor"), (int, float)) and isinstance(santander.get("precio_valor"), (int, float)):
            delta = round(float(santander["precio_valor"]) - float(best["precio_valor"]), 2)
            answer += f" Diferencia frente a Santander Boutique: {delta} EUR."

        return {
            "answer": answer,
            "evidence": _build_evidence(scope_sorted),
            "intent": "cheapest",
        }

    if not scope_sorted:
        scope_sorted = sorted(rows, key=_price_sort_value)

    prices = [float(row["precio_valor"]) for row in scope_sorted if isinstance(row.get("precio_valor"), (int, float))]
    if prices:
        avg = round(statistics.fmean(prices), 2)
        min_price = round(min(prices), 2)
        max_price = round(max(prices), 2)
        answer = f"{len(scope_sorted)} registros en el contexto actual. Media {_format_eur(avg)} EUR; rango {_format_eur(min_price)}-{_format_eur(max_price)} EUR."
    else:
        answer = f"{len(scope_sorted)} registros en el contexto actual, pero sin precio numerico parseado."

    return {
        "answer": answer,
        "evidence": _build_evidence(scope_sorted),
        "intent": "summary",
    }
