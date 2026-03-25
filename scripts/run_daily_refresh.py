from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from observatorio.text_utils import normalize_text

from app_backend.config import DEFAULT_COMPETITORS, OUTPUT_DIR, ROOT_DIR
from app_backend.config import SCRAPER_RUNTIME_ENTRYPOINT, SCRAPER_RUNTIME_NAME
from app_backend.data_access import (
    load_table_rows,
    load_rows_from_path,
    prune_history_snapshots,
    write_all_outputs,
    write_publish_manifest,
)
from app_backend.published_runtime import (
    apply_validated_retailer_merge,
    find_validation_report,
    load_validation_report,
)


def _find_generated_csv(output_prefix: Path) -> Path:
    matches = sorted(
        output_prefix.parent.glob(f"{output_prefix.name}_*.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        raise RuntimeError(f"No se encontro el CSV generado para el prefijo {output_prefix}.")
    return matches[0]


def _resolve_brands() -> tuple[list[str], str]:
    raw = os.getenv("OBSERVATORIO_REFRESH_BRANDS", "").strip()
    if not raw:
        return [], "all"

    brands = [item.strip().lower() for item in raw.split(",") if item.strip()]
    allowed = {"apple", "samsung"}
    unknown = [brand for brand in brands if brand not in allowed]
    if unknown:
        raise RuntimeError(f"Marcas no soportadas para refresh diario: {', '.join(unknown)}")
    return brands, ",".join(sorted(set(brands)))


def _run_scraper() -> tuple[Path, Path, list[str], str]:
    brands, brand_scope = _resolve_brands()
    output_prefix = OUTPUT_DIR / f"daily_refresh_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    command = [
        sys.executable,
        str(SCRAPER_RUNTIME_ENTRYPOINT.relative_to(ROOT_DIR)),
        "--brand",
        brand_scope if brand_scope != "all" else "all",
        "--competitors",
        ",".join(DEFAULT_COMPETITORS),
        "--output",
        str(output_prefix),
        "--scope",
        "full_catalog",
        "--max-products",
        "500",
    ]

    process = subprocess.run(
        command,
        cwd=ROOT_DIR,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        text=True,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(f"{SCRAPER_RUNTIME_NAME} finalizo con codigo {process.returncode}.")

    return output_prefix, _find_generated_csv(output_prefix), DEFAULT_COMPETITORS, brand_scope


def main() -> None:
    output_prefix, generated_csv, competitors, brand_scope = _run_scraper()
    validation_report_path = find_validation_report(output_prefix)
    rows = load_rows_from_path(generated_csv)
    validation_report = load_validation_report(validation_report_path)
    if not rows:
        raise RuntimeError("El refresh diario no genero filas publicables.")
    raw_record_count = len(rows)
    selected_keys = {
        (
            normalize_text(str(row.get("brand") or brand_scope or "all")),
            normalize_text(str(row.get("device_type") or "mobile")),
            normalize_text(str(row.get("model") or "")),
            row.get("capacity_gb"),
        )
        for row in rows
        if normalize_text(str(row.get("retailer") or "")) == normalize_text("Santander Boutique")
    }
    if not selected_keys:
        selected_keys = {
            (
                normalize_text(str(row.get("brand") or brand_scope or "all")),
                normalize_text(str(row.get("device_type") or "mobile")),
                normalize_text(str(row.get("model") or "")),
                row.get("capacity_gb"),
            )
            for row in rows
        }

    existing_rows, _ = load_table_rows()
    merged_rows = apply_validated_retailer_merge(
        existing_rows=existing_rows,
        fresh_rows=rows,
        validation_report=validation_report,
        selected_keys=selected_keys,
    )
    outputs = write_all_outputs(
        merged_rows,
        mode="scheduled",
        brand_scope=brand_scope,
        competitors=competitors,
        raw_generated_csv=str(generated_csv),
        raw_record_count=raw_record_count,
        selected_key_count=len(selected_keys),
        runtime_name=SCRAPER_RUNTIME_NAME,
        validation_report_path=str(validation_report_path),
        retailers_blocked=[str(item) for item in validation_report.get("retailers_blocked", [])],
        retailer_runtime_map={
            str(key): str(value)
            for key, value in validation_report.get("retailer_runtime_map", {}).items()
        },
    )

    write_publish_manifest(
        snapshot_id=outputs["snapshot_id"],
        created_at=outputs["created_at"],
        mode="scheduled",
        brand_scope=brand_scope,
        competitors=competitors,
        record_count=outputs["records_total"],
        cron=os.getenv("OBSERVATORIO_REFRESH_CRON", "08:00 Europe/Madrid"),
        timezone_name=os.getenv("OBSERVATORIO_REFRESH_TIMEZONE", "Europe/Madrid"),
    )

    keep = int(os.getenv("OBSERVATORIO_HISTORY_RETENTION", "90"))
    removed = prune_history_snapshots(keep=keep)

    summary = {
        "snapshot_id": outputs["snapshot_id"],
        "created_at": outputs["created_at"],
        "records_total": outputs["records_total"],
        "published_record_count": outputs["published_record_count"],
        "runtime_name": outputs["runtime_name"],
        "generated_csv": str(generated_csv),
        "validation_report_path": str(validation_report_path),
        "retailers_blocked": validation_report.get("retailers_blocked", []),
        "removed_snapshots": removed,
        "retention": keep,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    github_summary = os.getenv("GITHUB_STEP_SUMMARY")
    if github_summary:
        Path(github_summary).write_text(
            "\n".join(
                [
                    "## Daily Refresh",
                    "",
                    f"- Snapshot: `{outputs['snapshot_id']}`",
                    f"- Publicado: `{outputs['created_at']}`",
                    f"- Registros: `{outputs['records_total']}`",
                    f"- Registros crudos: `{raw_record_count}`",
                    f"- CSV origen: `{generated_csv.name}`",
                    f"- Validation report: `{Path(validation_report_path).name}`",
                    f"- Runtime: `{SCRAPER_RUNTIME_NAME}`",
                    f"- Snapshots eliminados por retencion: `{len(removed)}`",
                ]
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
