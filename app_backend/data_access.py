from __future__ import annotations

import csv
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from observatorio.html_builder import build_html
from observatorio.io_utils import write_records_csv, write_records_json
from observatorio.models import PriceRecord
from observatorio.text_utils import normalize_text

from app_backend.config import (
    CURRENT_CSV_PATH,
    CURRENT_DATA_DIR,
    CURRENT_HTML_PATH,
    CURRENT_JSON_PATH,
    PUBLISH_MANIFEST_PATH,
    CURRENT_TABLE_PATH,
    CURRENT_UNIFIED_CSV_PATH,
    HISTORY_DATA_DIR,
    LATEST_CSV_PATH,
    LATEST_JSON_PATH,
    LIVE_HTML_PATH,
    SCRAPER_CLEAN_INITIAL_SNAPSHOT_PATH,
    SCRAPER_CLEAN_RAW_RETAILER_ALIASES,
    SCRAPER_CLEAN_RAW_SLUG_ALIASES,
    TABLE_COPY_PATH,
    TABLE_OUTPUT_MASTER_PATH,
    TEMPLATE_PATH,
    UNIFIED_CSV_PATH,
)
from app_backend.persistence import create_snapshot, get_snapshot, init_storage, list_snapshots, sync_snapshots_with_filesystem

CANONICAL_TABLE_COLUMNS = [
    "country",
    "retailer",
    "retailer_slug",
    "product_family",
    "brand",
    "device_type",
    "model",
    "capacity_gb",
    "product_code",
    "offer_type",
    "price_value",
    "price_text",
    "price_unit",
    "term_months",
    "in_stock",
    "data_quality_tier",
    "extracted_at",
    "source_url",
    "source_title",
    "source_snapshot",
    "source_snapshots",
]

REQUIRED_TABLE_COLUMNS = {
    "country",
    "retailer",
    "retailer_slug",
    "product_family",
    "brand",
    "device_type",
    "model",
    "capacity_gb",
    "offer_type",
    "price_value",
    "price_text",
    "price_unit",
    "term_months",
    "in_stock",
    "data_quality_tier",
    "extracted_at",
    "source_url",
    "source_title",
    "source_snapshot",
    "source_snapshots",
}


def _parse_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _parse_optional_int(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _parse_optional_float(value: object) -> float | None:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_retailer(value: object) -> str:
    retailer = str(value or "").strip()
    return SCRAPER_CLEAN_RAW_RETAILER_ALIASES.get(retailer, retailer)


def _normalize_retailer_slug(value: object) -> str:
    slug = str(value or "").strip()
    return SCRAPER_CLEAN_RAW_SLUG_ALIASES.get(slug, slug)


def _record_key(row: dict) -> tuple:
    return (
        normalize_text(str(row.get("brand") or "")),
        normalize_text(str(row.get("retailer") or "")),
        normalize_text(str(row.get("device_type") or "mobile")),
        normalize_text(str(row.get("model") or "")),
        _parse_optional_int(row.get("capacity_gb")),
        normalize_text(str(row.get("offer_type") or "")),
        _parse_optional_int(row.get("term_months")),
    )


def _canonicalize_row(raw: dict) -> dict:
    row = {column: raw.get(column, "") for column in CANONICAL_TABLE_COLUMNS}
    row["retailer"] = _normalize_retailer(row.get("retailer"))
    row["retailer_slug"] = _normalize_retailer_slug(row.get("retailer_slug"))
    row["capacity_gb"] = _parse_optional_int(row.get("capacity_gb"))
    row["price_value"] = _parse_optional_float(row.get("price_value"))
    row["term_months"] = _parse_optional_int(row.get("term_months"))
    row["in_stock"] = _parse_bool(row.get("in_stock"))
    row["product_code"] = str(row.get("product_code") or "")
    row["country"] = str(row.get("country") or "ES")
    row["device_type"] = str(row.get("device_type") or "mobile")
    row["retailer"] = str(row.get("retailer") or "")
    row["retailer_slug"] = str(row.get("retailer_slug") or "")
    row["product_family"] = str(row.get("product_family") or row.get("brand") or "")
    row["brand"] = str(row.get("brand") or "")
    row["model"] = str(row.get("model") or "")
    row["offer_type"] = str(row.get("offer_type") or "")
    row["price_text"] = str(row.get("price_text") or "")
    row["price_unit"] = str(row.get("price_unit") or "")
    row["data_quality_tier"] = str(row.get("data_quality_tier") or "")
    row["extracted_at"] = str(row.get("extracted_at") or "")
    row["source_url"] = str(row.get("source_url") or "")
    row["source_title"] = str(row.get("source_title") or "")
    row["source_snapshot"] = str(row.get("source_snapshot") or "")
    row["source_snapshots"] = str(row.get("source_snapshots") or "")
    return row


def _validate_csv_header(fieldnames: list[str] | None, path: Path) -> None:
    columns = set(fieldnames or [])
    missing = sorted(REQUIRED_TABLE_COLUMNS - columns)
    if missing:
        raise ValueError(f"El CSV {path} no contiene las columnas requeridas: {', '.join(missing)}")


def _load_rows_from_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        _validate_csv_header(reader.fieldnames, path)
        return [_canonicalize_row(dict(raw)) for raw in reader]


def load_rows_from_path(path: Path) -> list[dict]:
    return _load_rows_from_csv(path)


def _csv_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    return str(value)


def _resolved_fieldnames(rows: list[dict]) -> list[str]:
    extras: list[str] = []
    seen = set(CANONICAL_TABLE_COLUMNS)
    for row in rows:
        for key in row.keys():
            if key not in seen:
                extras.append(key)
                seen.add(key)
    return [*CANONICAL_TABLE_COLUMNS, *extras]


def _write_canonical_csv(rows: list[dict], path: Path) -> Path:
    normalized_rows = [_canonicalize_row(row) for row in dedupe_records(rows)]
    fieldnames = _resolved_fieldnames(normalized_rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in normalized_rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})
    return path


def _to_price_record(row: dict) -> PriceRecord:
    price_value = _parse_optional_float(row.get("price_value"))
    if price_value is None:
        price_value = 0.0
    return PriceRecord(
        country=str(row.get("country") or "ES"),
        retailer=str(row.get("retailer") or ""),
        retailer_slug=str(row.get("retailer_slug") or ""),
        product_family=str(row.get("product_family") or row.get("brand") or ""),
        brand=str(row.get("brand") or ""),
        device_type=str(row.get("device_type") or "mobile"),
        model=str(row.get("model") or ""),
        capacity_gb=_parse_optional_int(row.get("capacity_gb")),
        offer_type=str(row.get("offer_type") or ""),
        price_value=price_value,
        price_text=str(row.get("price_text") or f"{price_value:.2f} EUR"),
        price_unit=str(row.get("price_unit") or "EUR"),
        term_months=_parse_optional_int(row.get("term_months")),
        in_stock=_parse_bool(row.get("in_stock")),
        data_quality_tier=str(row.get("data_quality_tier") or "frontend_job_refresh"),
        extracted_at=str(row.get("extracted_at") or PriceRecord.now_iso()),
        source_url=str(row.get("source_url") or ""),
        source_title=(str(row.get("source_title")) if row.get("source_title") is not None else None),
    )


def _write_unified_csv(records: list[PriceRecord], path: Path, source_snapshot: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        path.write_text("", encoding="utf-8")
        return
    rows = []
    for record in records:
        row = record.to_dict()
        row["source_snapshot"] = source_snapshot
        row["source_snapshots"] = source_snapshot
        rows.append(row)
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
        writer.writeheader()
        writer.writerows(rows)


def dedupe_records(records: list[dict]) -> list[dict]:
    by_key: dict[tuple, tuple[int, dict]] = {}
    for idx, row in enumerate(records):
        normalized_row = _canonicalize_row(row)
        key = _record_key(normalized_row)
        current = by_key.get(key)
        if current is None:
            by_key[key] = (idx, normalized_row)
            continue
        _, current_row = current
        current_price = _parse_optional_float(current_row.get("price_value"))
        incoming_price = _parse_optional_float(normalized_row.get("price_value"))
        if incoming_price is None:
            continue
        if current_price is None or incoming_price < current_price:
            by_key[key] = (idx, normalized_row)
    ordered = sorted(by_key.values(), key=lambda item: item[0])
    return [row for _, row in ordered]


def merge_competitor_slices(
    existing: list[dict],
    fresh: list[dict],
    competitors: list[str],
    selected_keys: set[tuple[str, str, str, int | None]],
) -> list[dict]:
    competitor_names = {normalize_text(name) for name in competitors}
    kept: list[dict] = []
    for row in existing:
        is_target_comp = normalize_text(str(row.get("retailer") or "")) in competitor_names
        row_key = (
            normalize_text(str(row.get("brand") or "")),
            normalize_text(str(row.get("device_type") or "mobile")),
            normalize_text(str(row.get("model") or "")),
            _parse_optional_int(row.get("capacity_gb")),
        )
        if is_target_comp and row_key in selected_keys:
            continue
        kept.append(row)
    return dedupe_records(kept + fresh)


def merge_competitor_slice(
    existing: list[dict],
    fresh: list[dict],
    competitor: str,
    selected_keys: set[tuple[str, str, str, int | None]],
) -> list[dict]:
    return merge_competitor_slices(existing, fresh, [competitor], selected_keys)


def _snapshot_dir(snapshot_id: str) -> Path:
    return HISTORY_DATA_DIR / snapshot_id


def _snapshot_file_paths(snapshot_id: str) -> dict[str, Path]:
    snapshot_dir = _snapshot_dir(snapshot_id)
    return {
        "dir": snapshot_dir,
        "table": snapshot_dir / "master_prices.csv",
        "csv": snapshot_dir / "latest_prices.csv",
        "json": snapshot_dir / "latest_prices.json",
        "html": snapshot_dir / "price_comparison_live.html",
        "metadata": snapshot_dir / "metadata.json",
    }


def _write_snapshot_metadata(
    *,
    snapshot_id: str,
    created_at: str,
    run_id: str | None,
    mode: str,
    brand_scope: str,
    competitors: list[str] | None,
    record_count: int,
    file_paths: dict[str, Path],
) -> dict:
    snapshot_dir = file_paths["dir"]
    payload = {
        "id": snapshot_id,
        "created_at": created_at,
        "run_id": run_id,
        "mode": mode,
        "brand_scope": brand_scope,
        "competitors": competitors or [],
        "record_count": record_count,
        "files": {
            "master_prices_csv": str(file_paths["table"].relative_to(snapshot_dir)),
            "latest_prices_csv": str(file_paths["csv"].relative_to(snapshot_dir)),
            "latest_prices_json": str(file_paths["json"].relative_to(snapshot_dir)),
            "price_comparison_live_html": str(file_paths["html"].relative_to(snapshot_dir)),
        },
    }
    file_paths["metadata"].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _publish_legacy_compatibility(
    *,
    table_path: Path,
    latest_csv_path: Path,
    latest_json_path: Path,
    html_path: Path,
    unified_csv_path: Path,
) -> None:
    TABLE_COPY_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(table_path, TABLE_COPY_PATH)
    shutil.copyfile(table_path, TABLE_OUTPUT_MASTER_PATH)
    shutil.copyfile(latest_csv_path, LATEST_CSV_PATH)
    shutil.copyfile(latest_json_path, LATEST_JSON_PATH)
    shutil.copyfile(html_path, LIVE_HTML_PATH)
    shutil.copyfile(unified_csv_path, UNIFIED_CSV_PATH)


def write_publish_manifest(
    *,
    snapshot_id: str,
    created_at: str,
    mode: str,
    brand_scope: str,
    competitors: list[str] | None,
    record_count: int,
    cron: str | None = None,
    timezone_name: str = "UTC",
) -> Path:
    payload = {
        "current_snapshot_id": snapshot_id,
        "published_at": created_at,
        "mode": mode,
        "brand_scope": brand_scope,
        "competitors": competitors or [],
        "record_count": record_count,
        "schedule": {
            "kind": "daily" if cron else "manual",
            "cron": cron,
            "timezone": timezone_name,
        },
    }
    PUBLISH_MANIFEST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return PUBLISH_MANIFEST_PATH


def read_publish_manifest() -> dict:
    if not PUBLISH_MANIFEST_PATH.exists():
        return {}
    try:
        payload = json.loads(PUBLISH_MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def prune_history_snapshots(keep: int = 90) -> list[str]:
    sync_snapshots_with_filesystem()
    snapshots = list_snapshots(limit=max(keep + 200, 500))
    removed: list[str] = []
    for snapshot in snapshots[keep:]:
        snapshot_dir = _snapshot_dir(str(snapshot["id"]))
        if snapshot_dir.exists():
            shutil.rmtree(snapshot_dir, ignore_errors=True)
            removed.append(str(snapshot["id"]))
    if removed:
        sync_snapshots_with_filesystem()
    return removed


def write_all_outputs(
    records: list[dict],
    *,
    run_id: str | None = None,
    mode: str = "manual",
    brand_scope: str = "all",
    competitors: list[str] | None = None,
    snapshot_id: str | None = None,
) -> dict:
    init_storage()
    canonical_rows = dedupe_records(records)
    price_records = [_to_price_record(row) for row in canonical_rows]
    created_at = datetime.now(tz=timezone.utc).isoformat()
    snapshot_name = snapshot_id or f"{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    snapshot_paths = _snapshot_file_paths(snapshot_name)
    snapshot_paths["dir"].mkdir(parents=True, exist_ok=True)

    _write_canonical_csv(canonical_rows, CURRENT_TABLE_PATH)
    write_records_csv(price_records, CURRENT_CSV_PATH)
    write_records_json(price_records, CURRENT_JSON_PATH)
    build_html(TEMPLATE_PATH, CURRENT_HTML_PATH, price_records)
    _write_unified_csv(price_records, CURRENT_UNIFIED_CSV_PATH, source_snapshot=f"{snapshot_name}.csv")

    _write_canonical_csv(canonical_rows, snapshot_paths["table"])
    write_records_csv(price_records, snapshot_paths["csv"])
    write_records_json(price_records, snapshot_paths["json"])
    build_html(TEMPLATE_PATH, snapshot_paths["html"], price_records)
    metadata = _write_snapshot_metadata(
        snapshot_id=snapshot_name,
        created_at=created_at,
        run_id=run_id,
        mode=mode,
        brand_scope=brand_scope,
        competitors=competitors,
        record_count=len(price_records),
        file_paths=snapshot_paths,
    )

    _publish_legacy_compatibility(
        table_path=CURRENT_TABLE_PATH,
        latest_csv_path=CURRENT_CSV_PATH,
        latest_json_path=CURRENT_JSON_PATH,
        html_path=CURRENT_HTML_PATH,
        unified_csv_path=CURRENT_UNIFIED_CSV_PATH,
    )

    create_snapshot(
        snapshot_id=snapshot_name,
        run_id=run_id,
        mode=mode,
        created_at=created_at,
        csv_path=snapshot_paths["table"],
        json_path=snapshot_paths["json"],
        html_path=snapshot_paths["html"],
        metadata_path=snapshot_paths["metadata"],
        record_count=len(price_records),
        brand_scope=brand_scope,
        competitors=competitors,
        is_current=True,
    )

    return {
        "snapshot_id": snapshot_name,
        "created_at": created_at,
        "metadata": metadata,
        "current_table_csv": str(CURRENT_TABLE_PATH),
        "current_json": str(CURRENT_JSON_PATH),
        "current_csv": str(CURRENT_CSV_PATH),
        "current_html": str(CURRENT_HTML_PATH),
        "current_unified_csv": str(CURRENT_UNIFIED_CSV_PATH),
        "latest_json": str(LATEST_JSON_PATH),
        "latest_csv": str(LATEST_CSV_PATH),
        "latest_html": str(LIVE_HTML_PATH),
        "unified_csv": str(UNIFIED_CSV_PATH),
        "table_copy_csv": str(TABLE_COPY_PATH),
        "table_output_csv": str(TABLE_OUTPUT_MASTER_PATH),
        "snapshot_csv": str(snapshot_paths["table"]),
        "snapshot_json": str(snapshot_paths["json"]),
        "snapshot_html": str(snapshot_paths["html"]),
        "snapshot_metadata": str(snapshot_paths["metadata"]),
        "records_total": len(price_records),
    }


def seed_canonical_table_from_snapshot(snapshot_path: Path | None = None) -> Path:
    source = snapshot_path or SCRAPER_CLEAN_INITIAL_SNAPSHOT_PATH
    rows = _load_rows_from_csv(source)
    write_all_outputs(rows, mode="bootstrap", brand_scope="all", competitors=[])
    return CURRENT_TABLE_PATH


def ensure_current_dataset() -> None:
    if CURRENT_TABLE_PATH.exists():
        return

    init_storage()
    current_snapshot = get_snapshot("current")
    if current_snapshot:
        csv_path = Path(current_snapshot["csv_path"])
        if csv_path.exists():
            rows = _load_rows_from_csv(csv_path)
            _write_canonical_csv(rows, CURRENT_TABLE_PATH)
            return

    if SCRAPER_CLEAN_INITIAL_SNAPSHOT_PATH.exists():
        seed_canonical_table_from_snapshot(SCRAPER_CLEAN_INITIAL_SNAPSHOT_PATH)


def load_table_rows(snapshot_id: str = "current") -> tuple[list[dict], Path]:
    ensure_current_dataset()
    if snapshot_id in {"", "current", None}:  # type: ignore[arg-type]
        source = CURRENT_TABLE_PATH
        return (_load_rows_from_csv(source), source) if source.exists() else ([], source)

    snapshot = get_snapshot(str(snapshot_id))
    if not snapshot:
        source = _snapshot_dir(str(snapshot_id)) / "master_prices.csv"
        return [], source

    source = Path(snapshot["csv_path"])
    if not source.exists():
        return [], source
    return _load_rows_from_csv(source), source


def load_latest_records() -> list[dict]:
    rows, _ = load_table_rows("current")
    return rows


def list_available_snapshots(limit: int = 100) -> list[dict]:
    ensure_current_dataset()
    return list_snapshots(limit=limit)


def build_table_meta(rows: list[dict]) -> dict:
    retailers = sorted({str(row.get("retailer") or "") for row in rows if row.get("retailer")})
    brands = sorted({str(row.get("brand") or "") for row in rows if row.get("brand")})
    offer_types = sorted({str(row.get("offer_type") or "") for row in rows if row.get("offer_type")})
    latest_extracted_at = max((str(row.get("extracted_at") or "") for row in rows), default="")
    return {
        "count": len(rows),
        "retailers": retailers,
        "brands": brands,
        "offer_types": offer_types,
        "latest_extracted_at": latest_extracted_at,
    }
