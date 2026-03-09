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

from app_backend.config import DEFAULT_COMPETITORS, OUTPUT_DIR, ROOT_DIR, SCRAPER_CLEAN_RETAILER_LABEL_TO_ID
from app_backend.data_access import (
    load_rows_from_path,
    prune_history_snapshots,
    write_all_outputs,
    write_publish_manifest,
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


def _run_scraper() -> tuple[Path, list[str], str]:
    brands, brand_scope = _resolve_brands()
    scraper_ids = [SCRAPER_CLEAN_RETAILER_LABEL_TO_ID[label] for label in DEFAULT_COMPETITORS]
    output_prefix = OUTPUT_DIR / f"daily_refresh_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    command = [
        sys.executable,
        "scraper_clean/main.py",
        "--scrapers",
        "boutique",
        *scraper_ids,
        "--output",
        str(output_prefix),
    ]
    if brands:
        command.extend(["--brands", *brands])

    process = subprocess.run(
        command,
        cwd=ROOT_DIR,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        text=True,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(f"scraper_clean finalizo con codigo {process.returncode}.")

    return _find_generated_csv(output_prefix), DEFAULT_COMPETITORS, brand_scope


def main() -> None:
    generated_csv, competitors, brand_scope = _run_scraper()
    rows = load_rows_from_path(generated_csv)
    if not rows:
        raise RuntimeError("El refresh diario no genero filas publicables.")

    outputs = write_all_outputs(
        rows,
        mode="scheduled",
        brand_scope=brand_scope,
        competitors=competitors,
    )

    write_publish_manifest(
        snapshot_id=outputs["snapshot_id"],
        created_at=outputs["created_at"],
        mode="scheduled",
        brand_scope=brand_scope,
        competitors=competitors,
        record_count=outputs["records_total"],
        cron=os.getenv("OBSERVATORIO_REFRESH_CRON", "0 6 * * *"),
        timezone_name=os.getenv("OBSERVATORIO_REFRESH_TIMEZONE", "UTC"),
    )

    keep = int(os.getenv("OBSERVATORIO_HISTORY_RETENTION", "90"))
    removed = prune_history_snapshots(keep=keep)

    summary = {
        "snapshot_id": outputs["snapshot_id"],
        "created_at": outputs["created_at"],
        "records_total": outputs["records_total"],
        "generated_csv": str(generated_csv),
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
                    f"- CSV origen: `{generated_csv.name}`",
                    f"- Snapshots eliminados por retencion: `{len(removed)}`",
                ]
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
