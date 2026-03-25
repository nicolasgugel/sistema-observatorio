from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app_backend.config import (
    DEFAULT_COMPETITORS,
    OUTPUT_DIR,
    ROOT_DIR,
    SCRAPER_BUNDLE_ENTRYPOINT,
    SCRAPER_BUNDLE_NAME,
    SCRAPER_CLEAN_RETAILER_LABEL_TO_ID,
    SCRAPER_RUNTIME_BY_RETAILER,
    SCRAPER_RUNTIME_NAME,
)
from app_backend.data_access import load_rows_from_path, merge_competitor_slice, write_runtime_raw_csv
from app_backend.retailer_validation import validate_retailer_rows
from observatorio.text_utils import normalize_text


SANTANDER_NAME = "Santander Boutique"
FULL_CATALOG_SCOPE = "full_catalog"


def _resolve_brand_list(brand_scope: str) -> list[str]:
    brand_n = normalize_text(brand_scope)
    if brand_n in {"", "all"}:
        return ["Samsung", "Apple"]
    if brand_n == "samsung":
        return ["Samsung"]
    if brand_n == "apple":
        return ["Apple"]
    raise RuntimeError(f"Marca no soportada por {SCRAPER_RUNTIME_NAME}: {brand_scope}")


def _selected_key_from_target(target: dict[str, Any], brand: str) -> tuple[str, str, str, int | None]:
    return (
        normalize_text(str(target.get("brand") or brand)),
        normalize_text(str(target.get("device_type") or "mobile")),
        normalize_text(str(target.get("model") or "")),
        target.get("capacity_gb"),
    )


def _group_rows_by_retailer(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("retailer") or "")].append(row)
    return dict(grouped)


def _validation_report_path(output_prefix: Path) -> Path:
    return output_prefix.parent / f"{output_prefix.name}_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}_validation.json"


def find_validation_report(output_prefix: Path) -> Path:
    matches = sorted(
        output_prefix.parent.glob(f"{output_prefix.name}_*_validation.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        raise RuntimeError(f"No se encontro el validation_report para el prefijo {output_prefix}.")
    return matches[0]


def load_validation_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def apply_validated_retailer_merge(
    *,
    existing_rows: list[dict[str, Any]],
    fresh_rows: list[dict[str, Any]],
    validation_report: dict[str, Any],
    selected_keys: set[tuple[str, str, str, int | None]],
) -> list[dict[str, Any]]:
    merged = list(existing_rows)
    fresh_by_retailer = _group_rows_by_retailer(fresh_rows)
    for item in validation_report.get("retailers", []):
        if item.get("blocked_publication"):
            continue
        retailer = str(item.get("retailer") or "")
        merged = merge_competitor_slice(
            existing=merged,
            fresh=fresh_by_retailer.get(retailer, []),
            competitor=retailer,
            selected_keys=selected_keys,
        )
    return merged


async def _stream_subprocess(process: asyncio.subprocess.Process) -> int:
    assert process.stdout is not None
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").rstrip()
        if text:
            stdout_encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
            safe_text = text.encode(stdout_encoding, errors="replace").decode(stdout_encoding, errors="replace")
            print(safe_text)
    return await process.wait()


async def _run_bundle_full(
    *,
    brand: str,
    competitors: list[str],
    output_prefix: Path,
) -> list[dict[str, Any]]:
    """Run the full bundle for one brand: scrapes Boutique then all competitors."""
    competitor_ids = [
        SCRAPER_CLEAN_RETAILER_LABEL_TO_ID[name]
        for name in competitors
        if name in SCRAPER_CLEAN_RETAILER_LABEL_TO_ID
    ]
    scraper_ids = ["boutique"] + competitor_ids

    command = [
        sys.executable,
        str(SCRAPER_BUNDLE_ENTRYPOINT.relative_to(ROOT_DIR)),
        "--scrapers",
        *scraper_ids,
        "--brands",
        normalize_text(brand),
        "--output",
        str(output_prefix),
    ]

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(ROOT_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    return_code = await _stream_subprocess(process)
    if return_code != 0:
        raise RuntimeError(f"{SCRAPER_BUNDLE_NAME} finalizo con codigo {return_code}.")
    generated_csv = _find_generated_csv(output_prefix)
    return load_rows_from_path(generated_csv)


async def _run_bundle_targets(
    *,
    targets: list[dict[str, Any]],
    competitors: list[str],
    brand: str,
    output_prefix: Path,
) -> list[dict[str, Any]]:
    if not targets or not competitors:
        return []

    scraper_ids = [SCRAPER_CLEAN_RETAILER_LABEL_TO_ID[name] for name in competitors]
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix=f"published_runtime_targets_{normalize_text(brand)}_",
        dir=str(OUTPUT_DIR),
        encoding="utf-8",
        delete=False,
    ) as temp_file:
        json.dump(targets, temp_file, ensure_ascii=False, indent=2)
        targets_path = Path(temp_file.name)

    command = [
        sys.executable,
        str(SCRAPER_BUNDLE_ENTRYPOINT.relative_to(ROOT_DIR)),
        "--targets-file",
        str(targets_path),
        "--scrapers",
        *scraper_ids,
        "--brands",
        normalize_text(brand),
        "--output",
        str(output_prefix),
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(ROOT_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        return_code = await _stream_subprocess(process)
        if return_code != 0:
            raise RuntimeError(f"{SCRAPER_BUNDLE_NAME} finalizo con codigo {return_code}.")
        generated_csv = _find_generated_csv(output_prefix)
        return load_rows_from_path(generated_csv)
    finally:
        try:
            targets_path.unlink(missing_ok=True)
        except OSError:
            pass


def _find_generated_csv(output_prefix: Path) -> Path:
    matches = sorted(
        output_prefix.parent.glob(f"{output_prefix.name}_*.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        raise RuntimeError(f"No se encontro el CSV generado para el prefijo {output_prefix}.")
    return matches[0]


async def _validate_runtime_rows(
    *,
    competitor_order: list[str],
    fresh_by_retailer: dict[str, list[dict[str, Any]]],
    mode: str,
    include_santander: bool = True,
) -> tuple[list[dict[str, Any]], bool]:
    validation_items: list[dict[str, Any]] = []
    santander_failed = False

    ordered = [name for name in competitor_order if name != SANTANDER_NAME]
    if include_santander:
        ordered = [SANTANDER_NAME, *ordered]
    seen: set[str] = set()
    for retailer in ordered:
        if retailer in seen:
            continue
        seen.add(retailer)
        result = await validate_retailer_rows(
            retailer,
            fresh_by_retailer.get(retailer, []),
            runtime_used=SCRAPER_RUNTIME_BY_RETAILER.get(retailer, "current_dedicated"),
            mode=mode,
        )
        validation_items.append(result)
        if retailer == SANTANDER_NAME and result.get("blocked_publication"):
            santander_failed = True

    return validation_items, santander_failed


def _write_validation_report(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


async def run_full_runtime(
    *,
    brand_scope: str,
    competitors: list[str] | None,
    output_prefix: Path,
    max_products: int = 500,
    scope: str = FULL_CATALOG_SCOPE,
    headed: bool = False,
) -> dict[str, Any]:
    requested_competitors = competitors or list(DEFAULT_COMPETITORS)
    all_rows: list[dict[str, Any]] = []
    selected_keys: set[tuple[str, str, str, int | None]] = set()

    for brand in _resolve_brand_list(brand_scope):
        brand_prefix = output_prefix.parent / f"{output_prefix.name}_{normalize_text(brand)}"
        brand_rows = await _run_bundle_full(
            brand=brand,
            competitors=requested_competitors,
            output_prefix=brand_prefix,
        )
        boutique_rows = [r for r in brand_rows if r.get("retailer") == SANTANDER_NAME]
        selected_keys.update(
            (
                normalize_text(str(r.get("brand") or "")),
                normalize_text(str(r.get("device_type") or "mobile")),
                normalize_text(str(r.get("model") or "")),
                r.get("capacity_gb"),
            )
            for r in boutique_rows
        )
        all_rows.extend(brand_rows)

    fresh_by_retailer = _group_rows_by_retailer(all_rows)
    validation_items, santander_failed = await _validate_runtime_rows(
        competitor_order=requested_competitors,
        fresh_by_retailer=fresh_by_retailer,
        mode="full",
        include_santander=True,
    )

    raw_csv_path = output_prefix.parent / f"{output_prefix.name}_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    write_runtime_raw_csv(all_rows, raw_csv_path)
    report_payload = {
        "runtime_name": SCRAPER_RUNTIME_NAME,
        "mode": "full",
        "brand_scope": brand_scope,
        "requested_competitors": requested_competitors,
        "retailer_runtime_map": {
            retailer: SCRAPER_RUNTIME_BY_RETAILER.get(retailer, "current_dedicated")
            for retailer in [SANTANDER_NAME, *requested_competitors]
        },
        "retailers_blocked": [item["retailer"] for item in validation_items if item.get("blocked_publication")],
        "selected_key_count": len(selected_keys),
        "raw_record_count": len(all_rows),
        "raw_generated_csv": str(raw_csv_path),
        "retailers": validation_items,
    }
    validation_path = _write_validation_report(_validation_report_path(output_prefix), report_payload)

    return {
        "raw_generated_csv": str(raw_csv_path),
        "validation_report_path": str(validation_path),
        "raw_rows": all_rows,
        "selected_keys": selected_keys,
        "retailers_blocked": report_payload["retailers_blocked"],
        "retailer_runtime_map": report_payload["retailer_runtime_map"],
        "should_fail": santander_failed,
    }


async def run_targeted_runtime(
    *,
    brand: str,
    competitor: str,
    targets: list[dict[str, Any]],
    output_prefix: Path,
    headed: bool = False,
) -> dict[str, Any]:
    if competitor not in DEFAULT_COMPETITORS:
        raise RuntimeError(f"Competidor no soportado: {competitor}")
    if not targets:
        raise RuntimeError("No hay targets para scraping dirigido.")

    selected_keys = {_selected_key_from_target(target, brand) for target in targets}

    fresh_rows = await _run_bundle_targets(
        targets=targets,
        competitors=[competitor],
        brand=brand,
        output_prefix=output_prefix,
    )

    fresh_by_retailer = _group_rows_by_retailer(fresh_rows)
    validation_items, _ = await _validate_runtime_rows(
        competitor_order=[competitor],
        fresh_by_retailer=fresh_by_retailer,
        mode="targeted",
        include_santander=False,
    )
    raw_csv_path = output_prefix.parent / f"{output_prefix.name}_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    write_runtime_raw_csv(fresh_rows, raw_csv_path)
    report_payload = {
        "runtime_name": SCRAPER_RUNTIME_NAME,
        "mode": "targeted",
        "brand_scope": brand,
        "requested_competitors": [competitor],
        "retailer_runtime_map": {competitor: "current_dedicated"},
        "retailers_blocked": [item["retailer"] for item in validation_items if item.get("blocked_publication")],
        "selected_key_count": len(selected_keys),
        "raw_record_count": len(fresh_rows),
        "raw_generated_csv": str(raw_csv_path),
        "retailers": validation_items,
    }
    validation_path = _write_validation_report(_validation_report_path(output_prefix), report_payload)

    return {
        "raw_generated_csv": str(raw_csv_path),
        "validation_report_path": str(validation_path),
        "raw_rows": fresh_rows,
        "selected_keys": selected_keys,
        "retailers_blocked": report_payload["retailers_blocked"],
        "retailer_runtime_map": report_payload["retailer_runtime_map"],
        "should_fail": False,
    }


def run_full_runtime_sync(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(run_full_runtime(**kwargs))


def run_targeted_runtime_sync(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(run_targeted_runtime(**kwargs))
