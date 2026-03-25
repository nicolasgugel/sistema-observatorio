from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import traceback
import uuid
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app_backend.config import (
    DEFAULT_COMPETITORS,
    OUTPUT_DIR,
    ROOT_DIR,
    SCRAPER_RUNTIME_ENTRYPOINT,
    SCRAPER_RUNTIME_NAME,
)
from app_backend.data_access import (
    load_rows_from_path,
    load_table_rows,
    write_all_outputs,
)
from app_backend.published_runtime import (
    apply_validated_retailer_merge,
    find_validation_report,
    load_validation_report,
)
from app_backend.persistence import (
    append_run_log,
    create_run,
    get_active_run,
    get_logs_after as list_run_logs_after,
    get_run,
    now_iso,
    update_run,
)
from app_backend.runtime_state import RUN_CREATION_LOCK
from observatorio.text_utils import normalize_text


JobState = Literal["queued", "running", "completed", "failed"]
SANTANDER_NAME = "Santander Boutique"


class ProductSelector(BaseModel):
    model: str = Field(min_length=1)
    capacity_gb: int | None = None


class ScrapingJobRequest(BaseModel):
    brand: Literal["Samsung", "Apple"] = "Samsung"
    competitor: str = Field(min_length=1)
    products: list[ProductSelector] = Field(min_length=1)
    max_products: int = 500
    headed: bool = False
    scope: str = "full_catalog"


def _selected_product_keys(products: list[ProductSelector]) -> set[tuple[str, int | None]]:
    return {
        (normalize_text(product.model), product.capacity_gb)
        for product in products
    }


def _discover_targets_from_canonical(brand: str) -> list[dict]:
    rows, _ = load_table_rows()
    brand_n = normalize_text(brand)
    targets_by_key: dict[tuple[str, int | None], dict] = {}

    for row in rows:
        if normalize_text(str(row.get("brand") or "")) != brand_n:
            continue
        if normalize_text(str(row.get("retailer") or "")) != normalize_text(SANTANDER_NAME):
            continue

        key = (
            normalize_text(str(row.get("model") or "")),
            row.get("capacity_gb"),
        )
        if key in targets_by_key:
            continue
        targets_by_key[key] = {
            "model": str(row.get("model") or ""),
            "capacity_gb": row.get("capacity_gb"),
            "product_code": str(row.get("product_code") or ""),
            "brand": str(row.get("brand") or brand),
            "device_type": str(row.get("device_type") or "mobile"),
            "product_family": str(row.get("product_family") or row.get("brand") or brand),
            "source_url": str(row.get("source_url") or ""),
        }

    return sorted(
        targets_by_key.values(),
        key=lambda item: (normalize_text(item["model"]), item["capacity_gb"] or -1),
    )


def _find_generated_csv(output_prefix: Path) -> Path:
    parent = output_prefix.parent
    stem = output_prefix.name
    matches = sorted(parent.glob(f"{stem}_*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not matches:
        raise RuntimeError(f"No se encontro el CSV generado para el prefijo {output_prefix}.")
    return matches[0]


class JobManager:
    def _append_log(self, job_id: str, message: str, level: str = "info") -> None:
        append_run_log(job_id, level=level, message=message)

    async def create_job(self, request: ScrapingJobRequest) -> dict:
        async with RUN_CREATION_LOCK:
            active = get_active_run()
            if active:
                raise HTTPException(
                    status_code=409,
                    detail="Ya hay un scraping o refresh en ejecucion. Espera a que termine.",
                )

            competitor = request.competitor.strip()
            if not competitor:
                raise HTTPException(status_code=422, detail="Competidor invalido.")
            if competitor not in DEFAULT_COMPETITORS:
                raise HTTPException(status_code=422, detail=f"Competidor no soportado: {competitor}")
            request.competitor = competitor

            job_id = uuid.uuid4().hex
            create_run(
                run_id=job_id,
                mode="targeted",
                status="queued",
                origin="manual",
                brand_scope=request.brand,
                competitors=[request.competitor],
                products=[product.model_dump() for product in request.products],
                triggered_by="editor_token",
                request_payload=request.model_dump(),
            )
            self._append_log(job_id, "Job encolado.")
            asyncio.create_task(self._run_job(job_id, request.model_copy(deep=True)))
            return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict:
        job = get_run(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job no encontrado.")
        return job

    def get_logs_after(self, job_id: str, after: int) -> tuple[list[dict], bool]:
        job = self.get_job(job_id)
        events = list_run_logs_after(job_id, after=after)
        done = job["status"] in {"completed", "failed"}
        return events, done

    async def _run_job(self, job_id: str, request: ScrapingJobRequest) -> None:
        update_run(job_id, status="running", started_at=now_iso(), runtime_name=SCRAPER_RUNTIME_NAME)
        self._append_log(job_id, f"Inicializando scraping con {SCRAPER_RUNTIME_NAME}.")

        try:
            result = await self._execute_request(job_id, request)
            update_run(
                job_id,
                status="completed",
                finished_at=now_iso(),
                error="",
                snapshot_id=result["outputs"]["snapshot_id"],
                record_count=result["outputs"]["records_total"],
                raw_generated_csv=result["generated_csv"],
                raw_record_count=result["fresh_records"],
                published_record_count=result["outputs"]["published_record_count"],
                selected_key_count=result["targets_selected"],
                runtime_name=SCRAPER_RUNTIME_NAME,
                validation_report_path=result["validation_report_path"],
                retailers_blocked=result["outputs"]["retailers_blocked"],
                retailer_runtime_map=result["outputs"]["retailer_runtime_map"],
            )
            self._append_log(job_id, "Job completado correctamente.")
        except Exception as exc:  # noqa: BLE001
            update_run(
                job_id,
                status="failed",
                finished_at=now_iso(),
                error=str(exc),
            )
            self._append_log(job_id, f"Error: {exc}", level="error")
            stack = traceback.format_exc(limit=8)
            self._append_log(job_id, stack, level="error")

    async def _execute_request(self, job_id: str, req: ScrapingJobRequest) -> dict:
        available_targets = _discover_targets_from_canonical(req.brand)
        self._append_log(job_id, f"Targets Santander disponibles en dataset canonico: {len(available_targets)}.")

        selected_product_keys = _selected_product_keys(req.products)
        scoped_targets = [
            target
            for target in available_targets
            if (normalize_text(target["model"]), target["capacity_gb"]) in selected_product_keys
        ]
        if not scoped_targets:
            requested = ", ".join(f"{p.model} {p.capacity_gb or ''}GB".strip() for p in req.products)
            raise RuntimeError(f"No hay targets Santander para los productos solicitados: {requested}")

        selected_keys = {
            (
                normalize_text(str(target.get("brand") or req.brand)),
                normalize_text(str(target.get("device_type") or "mobile")),
                normalize_text(str(target.get("model") or "")),
                target.get("capacity_gb"),
            )
            for target in scoped_targets
        }
        self._append_log(job_id, f"Targets seleccionados por producto exacto: {len(scoped_targets)}.")

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix=f"scraper_targets_{job_id}_",
            dir=str(OUTPUT_DIR),
            encoding="utf-8",
            delete=False,
        ) as temp_file:
            json.dump(scoped_targets, temp_file, ensure_ascii=False, indent=2)
            targets_path = Path(temp_file.name)

        output_prefix = OUTPUT_DIR / f"scraper_runtime_job_{job_id}"
        command = [
            sys.executable,
            str(SCRAPER_RUNTIME_ENTRYPOINT.relative_to(ROOT_DIR)),
            "--brand",
            req.brand,
            "--competitors",
            req.competitor,
            "--targets-file",
            str(targets_path),
            "--output",
            str(output_prefix),
        ]
        if req.headed:
            command.append("--headed")
        update_run(job_id, command=command)
        update_run(job_id, runtime_name=SCRAPER_RUNTIME_NAME)

        self._append_log(job_id, "Comando lanzado: " + " ".join(command))
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(ROOT_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

        assert process.stdout is not None
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                self._append_log(job_id, text)

        return_code = await process.wait()
        update_run(job_id, return_code=return_code)

        try:
            targets_path.unlink(missing_ok=True)
        except OSError:
            self._append_log(job_id, f"No se pudo borrar el targets-file temporal: {targets_path}", level="warning")

        if return_code != 0:
            raise RuntimeError(f"{SCRAPER_RUNTIME_NAME} finalizo con codigo {return_code}.")

        generated_csv = _find_generated_csv(output_prefix)
        validation_report_path = find_validation_report(output_prefix)
        self._append_log(job_id, f"CSV generado por {SCRAPER_RUNTIME_NAME}: {generated_csv}")
        self._append_log(job_id, f"Validation report generado: {validation_report_path}")

        fresh_rows = load_rows_from_path(generated_csv)
        validation_report = load_validation_report(validation_report_path)
        self._append_log(job_id, f"Registros nuevos capturados: {len(fresh_rows)}.")

        existing_records, _ = load_table_rows()
        self._append_log(job_id, f"Registros existentes antes de merge: {len(existing_records)}.")

        merged = apply_validated_retailer_merge(
            existing_rows=existing_records,
            fresh_rows=fresh_rows,
            validation_report=validation_report,
            selected_keys=selected_keys,
        )
        blocked = [str(item) for item in validation_report.get("retailers_blocked", [])]
        if blocked:
            self._append_log(job_id, f"Retailers bloqueados por validacion: {', '.join(blocked)}.", level="warning")
        self._append_log(job_id, f"Registros tras merge: {len(merged)}.")

        paths = write_all_outputs(
            merged,
            run_id=job_id,
            mode="targeted",
            brand_scope=req.brand,
            competitors=[req.competitor],
            raw_generated_csv=str(generated_csv),
            raw_record_count=len(fresh_rows),
            selected_key_count=len(selected_keys),
            runtime_name=SCRAPER_RUNTIME_NAME,
            validation_report_path=str(validation_report_path),
            retailers_blocked=blocked,
            retailer_runtime_map={
                str(key): str(value)
                for key, value in validation_report.get("retailer_runtime_map", {}).items()
            },
        )
        self._append_log(job_id, "Artefactos actualizados: current/, latest_*, unified CSV y HTML.")
        self._append_log(job_id, f"Registros publicados tras merge validado: {paths['published_record_count']}.")

        return {
            "brand": req.brand,
            "competitor": req.competitor,
            "requested_products": [p.model_dump() for p in req.products],
            "targets_selected": len(scoped_targets),
            "fresh_records": len(fresh_rows),
            "records_total": paths["records_total"],
            "outputs": paths,
            "generated_csv": str(generated_csv),
            "validation_report_path": str(validation_report_path),
        }
