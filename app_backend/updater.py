from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app_backend.config import (
    DEFAULT_COMPETITORS,
    OUTPUT_DIR,
    ROOT_DIR,
    SCRAPER_CLEAN_RETAILER_LABEL_TO_ID,
    SCRAPER_RUNTIME_ENTRYPOINT,
    SCRAPER_RUNTIME_NAME,
)
from app_backend.data_access import (
    load_rows_from_path,
    load_table_rows,
    merge_competitor_slices,
    write_all_outputs,
)
from app_backend.persistence import (
    append_run_log,
    create_run,
    get_active_run,
    get_logs_after as list_run_logs_after,
    get_run,
    list_runs,
    now_iso,
    update_run,
)
from app_backend.runtime_state import RUN_CREATION_LOCK
from observatorio.text_utils import normalize_text


RunStatus = Literal["queued", "running", "completed", "failed"]
SANTANDER_NAME = "Santander Boutique"


class UpdateRunRequest(BaseModel):
    brand: Literal["all", "Samsung", "Apple"] = "all"
    max_products: int = Field(default=12, ge=1, le=500)
    competitors: str | None = None
    scope: str = "full_catalog"
    headed: bool = False


class UpdateScheduleRequest(BaseModel):
    enabled: bool
    interval_minutes: int = Field(default=30, ge=5, le=1440)
    run_request: UpdateRunRequest = Field(default_factory=UpdateRunRequest)


def _find_generated_csv(output_prefix: Path) -> Path:
    parent = output_prefix.parent
    stem = output_prefix.name
    matches = sorted(parent.glob(f"{stem}_*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not matches:
        raise RuntimeError(f"No se encontro el CSV generado para el prefijo {output_prefix}.")
    return matches[0]


class UpdaterManager:
    def __init__(self) -> None:
        self._schedule_enabled = False
        self._schedule_interval = 30
        self._schedule_request = UpdateRunRequest()
        self._schedule_task: asyncio.Task | None = None
        self._schedule_next_run_at: str | None = None

    def _append_log(self, run_id: str, message: str, *, level: str = "info") -> None:
        append_run_log(run_id, level=level, message=message)

    async def start_run(self, request: UpdateRunRequest, *, origin: str = "manual") -> dict:
        selected_competitors = self._resolve_competitors(request.competitors)
        self._resolve_brands(request.brand)

        async with RUN_CREATION_LOCK:
            active = get_active_run()
            if active:
                raise RuntimeError("Ya hay una actualizacion o scraping dirigido en ejecucion.")

            run_id = uuid.uuid4().hex
            create_run(
                run_id=run_id,
                mode="full",
                status="queued",
                origin=origin,
                brand_scope=request.brand,
                competitors=selected_competitors,
                products=None,
                triggered_by=origin,
                request_payload=request.model_dump(),
            )
            self._append_log(run_id, "Actualizacion encolada.")
            asyncio.create_task(self._execute(run_id, request.model_copy(deep=True), selected_competitors))
            return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict:
        run = get_run(run_id)
        if not run:
            raise KeyError("Run no encontrado")
        return run

    def get_logs_after(self, run_id: str, after: int = 0) -> tuple[list[dict], bool]:
        run = self.get_run(run_id)
        events = list_run_logs_after(run_id, after=after)
        done = run["status"] in {"completed", "failed"}
        return events, done

    def latest_runs(self, limit: int = 20) -> list[dict]:
        return list_runs(limit=limit)

    def active_run(self) -> dict | None:
        return get_active_run()

    def schedule_state(self) -> dict:
        return {
            "enabled": self._schedule_enabled,
            "interval_minutes": self._schedule_interval,
            "next_run_at": self._schedule_next_run_at,
            "run_request": self._schedule_request.model_dump(),
        }

    async def set_schedule(self, payload: UpdateScheduleRequest) -> dict:
        self._schedule_enabled = payload.enabled
        self._schedule_interval = payload.interval_minutes
        self._schedule_request = payload.run_request

        if self._schedule_enabled and self._schedule_task is None:
            self._schedule_task = asyncio.create_task(self._run_scheduler())

        if not self._schedule_enabled and self._schedule_task:
            self._schedule_task.cancel()
            self._schedule_task = None
            self._schedule_next_run_at = None

        return self.schedule_state()

    async def shutdown(self) -> None:
        if self._schedule_task:
            self._schedule_task.cancel()
            self._schedule_task = None
        self._schedule_next_run_at = None

    async def _run_scheduler(self) -> None:
        while self._schedule_enabled:
            next_dt = datetime.utcnow() + timedelta(minutes=self._schedule_interval)
            self._schedule_next_run_at = next_dt.isoformat() + "Z"
            sleep_seconds = max(self._schedule_interval * 60, 1)
            try:
                await asyncio.sleep(sleep_seconds)
            except asyncio.CancelledError:
                return

            if not self._schedule_enabled:
                break

            if self.active_run() is not None:
                continue

            try:
                await self.start_run(self._schedule_request, origin="scheduler")
            except RuntimeError:
                continue

    async def _execute(
        self,
        run_id: str,
        request: UpdateRunRequest,
        selected_competitors: list[str],
    ) -> None:
        update_run(run_id, status="running", started_at=now_iso())
        command, output_prefix = self._build_command(request, selected_competitors)
        update_run(run_id, command=command)

        if request.max_products != 12:
            self._append_log(
                run_id,
                f"max_products se mantiene por compatibilidad y no limita {SCRAPER_RUNTIME_NAME}.",
                level="warning",
            )
        if normalize_text(request.scope) != normalize_text("full_catalog"):
            self._append_log(
                run_id,
                f"scope se mantiene por compatibilidad y se ignora en {SCRAPER_RUNTIME_NAME}.",
                level="warning",
            )
        if request.headed:
            self._append_log(
                run_id,
                f"headed no esta soportado por {SCRAPER_RUNTIME_NAME} y se ignora.",
                level="warning",
            )

        self._append_log(run_id, "Comando lanzado: " + " ".join(command))

        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")

        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(ROOT_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )

        assert process.stdout is not None
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                self._append_log(run_id, text)

        return_code = await process.wait()
        update_run(run_id, return_code=return_code)

        if return_code != 0:
            error = f"{SCRAPER_RUNTIME_NAME} finalizo con codigo {return_code}."
            update_run(run_id, status="failed", finished_at=now_iso(), error=error)
            self._append_log(run_id, error, level="error")
            return

        try:
            generated_csv = _find_generated_csv(output_prefix)
            self._append_log(run_id, f"CSV generado por {SCRAPER_RUNTIME_NAME}: {generated_csv}")

            fresh_rows = load_rows_from_path(generated_csv)
            if not fresh_rows:
                raise RuntimeError(f"{SCRAPER_RUNTIME_NAME} no devolvio filas para el refresh solicitado.")
            existing_rows, _ = load_table_rows()

            selected_keys = {
                (
                    normalize_text(str(row.get("brand") or request.brand)),
                    normalize_text(str(row.get("device_type") or "mobile")),
                    normalize_text(str(row.get("model") or "")),
                    row.get("capacity_gb"),
                )
                for row in fresh_rows
                if normalize_text(str(row.get("retailer") or "")) == normalize_text(SANTANDER_NAME)
            }
            if not selected_keys:
                selected_keys = {
                    (
                        normalize_text(str(row.get("brand") or request.brand)),
                        normalize_text(str(row.get("device_type") or "mobile")),
                        normalize_text(str(row.get("model") or "")),
                        row.get("capacity_gb"),
                    )
                    for row in fresh_rows
                }

            merged = merge_competitor_slices(
                existing=existing_rows,
                fresh=fresh_rows,
                competitors=[SANTANDER_NAME, *selected_competitors],
                selected_keys=selected_keys,
            )
            paths = write_all_outputs(
                merged,
                run_id=run_id,
                mode="full",
                brand_scope=request.brand,
                competitors=selected_competitors,
            )
            update_run(
                run_id,
                status="completed",
                finished_at=now_iso(),
                error="",
                snapshot_id=paths["snapshot_id"],
                record_count=paths["records_total"],
            )
            self._append_log(run_id, "Artefactos actualizados: current/, latest_*, unified CSV y HTML.")
            self._append_log(run_id, f"Registros totales tras refresh: {paths['records_total']}.")
            self._append_log(run_id, "Actualizacion completada correctamente.")
        except Exception as exc:  # noqa: BLE001
            update_run(run_id, status="failed", finished_at=now_iso(), error=str(exc))
            self._append_log(run_id, f"Error post-proceso: {exc}", level="error")

    def _build_command(self, request: UpdateRunRequest, selected_labels: list[str]) -> tuple[list[str], Path]:
        scraper_ids = [SCRAPER_CLEAN_RETAILER_LABEL_TO_ID[label] for label in selected_labels]
        output_prefix = OUTPUT_DIR / f"scraper_runtime_updater_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        command = [
            sys.executable,
            str(SCRAPER_RUNTIME_ENTRYPOINT.relative_to(ROOT_DIR)),
            "--scrapers",
            "boutique",
            *scraper_ids,
        ]
        brands = self._resolve_brands(request.brand)
        if brands:
            command.extend(["--brands", *brands])
        command.extend(["--output", str(output_prefix)])
        return command, output_prefix

    def _resolve_competitors(self, value: str | None) -> list[str]:
        if not value or not value.strip():
            return list(DEFAULT_COMPETITORS)

        selected: list[str] = []
        unknown: list[str] = []
        for raw in value.split(","):
            label = raw.strip()
            if not label:
                continue
            if label == SANTANDER_NAME:
                continue
            if label not in DEFAULT_COMPETITORS:
                unknown.append(label)
                continue
            if label not in selected:
                selected.append(label)

        if unknown:
            unknown_text = ", ".join(unknown)
            raise RuntimeError(f"Competidores no soportados por {SCRAPER_RUNTIME_NAME}: {unknown_text}")
        if not selected:
            return list(DEFAULT_COMPETITORS)
        return selected

    def _resolve_brands(self, value: str) -> list[str]:
        brand = normalize_text(value)
        if brand == "all":
            return []
        if brand in {"samsung", "apple"}:
            return [brand]
        raise RuntimeError(f"Marca no soportada por {SCRAPER_RUNTIME_NAME}: {value}")
