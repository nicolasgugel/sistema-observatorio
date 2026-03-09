from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app_backend.config import DEFAULT_COMPETITORS
from app_backend.data_access import build_table_meta, ensure_current_dataset, list_available_snapshots, load_table_rows, read_publish_manifest
from app_backend.intelligence import (
    answer_agent_question,
    apply_filters,
    build_comparator_payload,
    build_dashboard_payload,
    build_filters_meta,
    export_rows,
    load_public_rows,
    paginate_rows,
    sort_rows,
)
from app_backend.persistence import get_snapshot
from observatorio.text_utils import normalize_text


app = FastAPI(
    title="Santander Price Intelligence API (Vercel)",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AgentQueryRequest(BaseModel):
    question: str = Field(min_length=3)
    brand: Literal["Samsung", "Apple", "all"] = "Samsung"


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_INDEX_FILE = FRONTEND_DIST_DIR / "index.html"


def _frontend_file(path: str) -> Path | None:
    if not path:
        return None

    candidate = (FRONTEND_DIST_DIR / path).resolve()
    dist_root = FRONTEND_DIST_DIR.resolve()

    if dist_root not in candidate.parents and candidate != dist_root:
        return None

    if candidate.is_file():
        return candidate
    return None


def _is_static_asset_request(path: str) -> bool:
    normalized = path.lstrip("/")
    if not normalized:
        return False
    if normalized.startswith("assets/"):
        return True
    return "." in Path(normalized).name


def _frontend_headers(path: str) -> dict[str, str]:
    normalized = path.lstrip("/")
    if normalized.startswith("assets/"):
        return {"Cache-Control": "public, max-age=31536000, immutable"}
    if normalized:
        return {"Cache-Control": "public, max-age=3600"}
    return {"Cache-Control": "no-store, max-age=0"}


def _serve_frontend_index() -> Response:
    if FRONTEND_INDEX_FILE.is_file():
        return FileResponse(FRONTEND_INDEX_FILE, headers=_frontend_headers(""))
    return Response(status_code=503, content="Frontend build not found in deployment.")


def _parse_sort_dir(value: str) -> str:
    return "desc" if normalize_text(value) == "desc" else "asc"


def _filtered_rows(
    *,
    brand: str,
    snapshot_id: str = "current",
    competitors: list[str] | None = None,
    models: list[str] | None = None,
    capacities: list[int] | None = None,
    modalities: list[str] | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    availability: bool | None = None,
    search: str | None = None,
) -> list[dict]:
    rows = load_public_rows(brand=brand, snapshot_id=snapshot_id)
    return apply_filters(
        rows,
        competitors=competitors,
        models=models,
        capacities=capacities,
        modalities=modalities,
        min_price=min_price,
        max_price=max_price,
        availability=availability,
        search=search,
    )


@app.get("/api/health")
async def health() -> dict:
    ensure_current_dataset()
    return {"status": "ok"}


@app.get("/api/observatorio/records")
async def observatorio_records(
    brand: Literal["Samsung", "Apple", "all"] = Query(default="all"),
) -> dict:
    records, source = load_table_rows()
    if brand != "all":
        bn = normalize_text(brand)
        records = [row for row in records if normalize_text(str(row.get("brand") or "")) == bn]

    extracted_at = max((str(row.get("extracted_at") or "") for row in records), default="")
    return {
        "count": len(records),
        "extracted_at": extracted_at,
        "source": str(source),
        "records": records,
    }


@app.get("/api/table/rows")
async def table_rows(snapshot_id: str = Query(default="current")) -> dict:
    rows, source = load_table_rows(snapshot_id=snapshot_id)
    return {
        "count": len(rows),
        "source": str(source),
        "snapshot_id": snapshot_id,
        "rows": rows,
    }


@app.get("/api/table/meta")
async def table_meta(snapshot_id: str = Query(default="current")) -> dict:
    rows, source = load_table_rows(snapshot_id=snapshot_id)
    meta = build_table_meta(rows)
    meta["source"] = str(source)
    meta["snapshot_id"] = snapshot_id
    return meta


@app.get("/api/table/snapshots")
async def table_snapshots() -> dict:
    snapshots = list_available_snapshots(limit=200)
    return {
        "count": len(snapshots),
        "snapshots": snapshots,
    }


@app.get("/api/table/snapshots/{snapshot_id}")
async def table_snapshot_detail(snapshot_id: str) -> dict:
    snapshot = get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Snapshot no encontrado: {snapshot_id}")
    return snapshot


@app.get("/api/table/publish-info")
async def table_publish_info() -> dict:
    info = read_publish_manifest()
    if info:
        return info
    snapshots = list_available_snapshots(limit=1)
    latest = snapshots[0] if snapshots else None
    return {
        "current_snapshot_id": latest.get("id") if latest else None,
        "published_at": latest.get("created_at") if latest else None,
        "mode": latest.get("mode") if latest else None,
        "brand_scope": latest.get("brand_scope") if latest else "all",
        "competitors": latest.get("competitors") if latest else [],
        "record_count": latest.get("record_count") if latest else 0,
        "schedule": {
            "kind": "manual",
            "cron": None,
            "timezone": "UTC",
        },
    }


@app.get("/api/scraping/seeds")
async def scraping_seeds(brand: Literal["Samsung", "Apple"] = Query(default="Samsung")) -> dict:
    records, _ = load_table_rows()
    bn = normalize_text(brand)

    seeds_by_key: dict[tuple[str, int | None, str], dict] = {}
    for row in records:
        if normalize_text(str(row.get("brand") or "")) != bn:
            continue
        if normalize_text(str(row.get("retailer") or "")) != normalize_text("Santander Boutique"):
            continue

        key = (
            str(row.get("model") or ""),
            row.get("capacity_gb"),
            str(row.get("device_type") or "mobile"),
        )
        if key not in seeds_by_key:
            seeds_by_key[key] = {
                "brand": brand,
                "model": key[0],
                "capacity_gb": key[1],
                "device_type": key[2],
            }

    seeds = sorted(
        seeds_by_key.values(),
        key=lambda item: (normalize_text(item["model"]), item["capacity_gb"] or -1),
    )
    return {"count": len(seeds), "seeds": seeds}


@app.get("/api/scraping/competitors")
async def scraping_competitors() -> dict:
    return {"competitors": DEFAULT_COMPETITORS}


@app.post("/api/scraping/jobs")
async def create_scraping_job() -> dict:
    raise HTTPException(
        status_code=501,
        detail="Scraping en vivo no disponible en despliegue Vercel. Usa la instancia local para lanzar jobs.",
    )


@app.get("/api/scraping/jobs/{job_id}")
async def scraping_job(job_id: str) -> dict:
    raise HTTPException(status_code=404, detail=f"Job no encontrado en Vercel: {job_id}")


@app.get("/api/scraping/jobs/{job_id}/events")
async def scraping_job_events(job_id: str) -> Response:
    payload = {
        "type": "status",
        "job": {
            "id": job_id,
            "status": "failed",
            "error": "Scraping en vivo no disponible en despliegue Vercel.",
        },
    }
    return Response(
        content=f"data: {json.dumps(payload, ensure_ascii=False)}\n\n",
        media_type="text/event-stream",
    )


@app.get("/api/intelligence/filters")
async def intelligence_filters(
    brand: Literal["Samsung", "Apple", "all"] = Query(default="Samsung"),
) -> dict:
    rows = load_public_rows(brand=brand)
    return build_filters_meta(rows)


@app.get("/api/intelligence/records")
async def intelligence_records(
    brand: Literal["Samsung", "Apple", "all"] = Query(default="Samsung"),
    competitors: list[str] | None = Query(default=None),
    models: list[str] | None = Query(default=None),
    capacities: list[int] | None = Query(default=None),
    modalities: list[str] | None = Query(default=None),
    min_price: float | None = Query(default=None),
    max_price: float | None = Query(default=None),
    availability: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    sort_by: str = Query(default="precio_valor"),
    sort_dir: str = Query(default="asc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=500),
) -> dict:
    rows = _filtered_rows(
        brand=brand,
        competitors=competitors,
        models=models,
        capacities=capacities,
        modalities=modalities,
        min_price=min_price,
        max_price=max_price,
        availability=availability,
        search=search,
    )
    sorted_rows = sort_rows(rows, sort_by=sort_by, sort_dir=_parse_sort_dir(sort_dir))
    page_rows, total = paginate_rows(sorted_rows, page=page, page_size=page_size)

    return {
        "count": len(page_rows),
        "total": total,
        "page": page,
        "page_size": page_size,
        "rows": page_rows,
    }


@app.get("/api/intelligence/comparator")
async def intelligence_comparator(
    brand: Literal["Samsung", "Apple", "all"] = Query(default="Samsung"),
    competitors: list[str] | None = Query(default=None),
    models: list[str] | None = Query(default=None),
    capacities: list[int] | None = Query(default=None),
    modalities: list[str] | None = Query(default=None),
    min_price: float | None = Query(default=None),
    max_price: float | None = Query(default=None),
    availability: bool | None = Query(default=None),
    search: str | None = Query(default=None),
) -> dict:
    rows = _filtered_rows(
        brand=brand,
        competitors=competitors,
        models=models,
        capacities=capacities,
        modalities=modalities,
        min_price=min_price,
        max_price=max_price,
        availability=availability,
        search=search,
    )
    return build_comparator_payload(rows)


@app.get("/api/intelligence/dashboard")
async def intelligence_dashboard(
    brand: Literal["Samsung", "Apple", "all"] = Query(default="Samsung"),
    competitors: list[str] | None = Query(default=None),
    models: list[str] | None = Query(default=None),
    capacities: list[int] | None = Query(default=None),
    modalities: list[str] | None = Query(default=None),
    min_price: float | None = Query(default=None),
    max_price: float | None = Query(default=None),
    availability: bool | None = Query(default=None),
    search: str | None = Query(default=None),
) -> dict:
    rows = _filtered_rows(
        brand=brand,
        competitors=competitors,
        models=models,
        capacities=capacities,
        modalities=modalities,
        min_price=min_price,
        max_price=max_price,
        availability=availability,
        search=search,
    )
    return build_dashboard_payload(rows, brand=brand)


@app.get("/api/intelligence/export")
async def intelligence_export(
    fmt: Literal["csv", "json"] = Query(default="csv"),
    brand: Literal["Samsung", "Apple", "all"] = Query(default="Samsung"),
    snapshot_id: str = Query(default="current"),
    competitors: list[str] | None = Query(default=None),
    models: list[str] | None = Query(default=None),
    capacities: list[int] | None = Query(default=None),
    modalities: list[str] | None = Query(default=None),
    min_price: float | None = Query(default=None),
    max_price: float | None = Query(default=None),
    availability: bool | None = Query(default=None),
    search: str | None = Query(default=None),
) -> Response:
    rows = _filtered_rows(
        brand=brand,
        snapshot_id=snapshot_id,
        competitors=competitors,
        models=models,
        capacities=capacities,
        modalities=modalities,
        min_price=min_price,
        max_price=max_price,
        availability=availability,
        search=search,
    )

    has_filters = any(
        value not in (None, "", [])
        for value in [competitors, models, capacities, modalities, min_price, max_price, availability, search]
    )
    if fmt == "csv" and not has_filters:
        _, source = load_table_rows(snapshot_id=snapshot_id)
        if not source.exists():
            raise HTTPException(status_code=404, detail=f"Snapshot no encontrado: {snapshot_id}")
        return Response(
            content=source.read_bytes(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename=\"{source.name}\"'},
        )

    body, media_type, filename = export_rows(rows, fmt)
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/intelligence/agent/query")
async def intelligence_agent_query(payload: AgentQueryRequest) -> dict:
    rows = load_public_rows(brand=payload.brand)
    answer = answer_agent_question(payload.question, rows)
    return {
        "brand": payload.brand,
        "question": payload.question,
        **answer,
    }


@app.post("/api/intelligence/updater/run")
async def updater_run() -> dict:
    raise HTTPException(
        status_code=501,
        detail="Updater automatico no disponible en despliegue Vercel. Usa la instancia local.",
    )


@app.get("/api/intelligence/updater/status")
async def updater_status() -> dict:
    return {
        "active_run": None,
        "schedule": {
            "enabled": False,
            "interval_minutes": 30,
            "next_run_at": None,
            "run_request": {
                "brand": "Samsung",
                "max_products": 12,
                "competitors": None,
                "scope": "full_catalog",
                "headed": False,
            },
        },
        "recent_runs": [],
    }


@app.get("/api/intelligence/updater/runs/{run_id}")
async def updater_run_detail(run_id: str) -> dict:
    raise HTTPException(status_code=404, detail=f"Run no encontrado en Vercel: {run_id}")


@app.get("/api/intelligence/updater/runs/{run_id}/logs")
async def updater_run_logs(run_id: str, after: int = Query(default=0, ge=0)) -> dict:
    return {
        "events": [],
        "done": True,
        "next_after": after,
        "run_id": run_id,
    }


@app.get("/api/intelligence/updater/schedule")
async def updater_schedule_state() -> dict:
    return {
        "enabled": False,
        "interval_minutes": 30,
        "next_run_at": None,
        "run_request": {
            "brand": "Samsung",
            "max_products": 12,
            "competitors": None,
            "scope": "full_catalog",
            "headed": False,
        },
    }


@app.put("/api/intelligence/updater/schedule")
async def updater_schedule() -> dict:
    raise HTTPException(
        status_code=501,
        detail="Programacion de updater no disponible en despliegue Vercel.",
    )


@app.get("/", include_in_schema=False)
async def spa_root() -> Response:
    return _serve_frontend_index()


@app.get("/{path:path}", include_in_schema=False)
async def spa_fallback(path: str) -> Response:
    if path == "api" or path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")

    static_file = _frontend_file(path)
    if static_file is not None:
        return FileResponse(static_file, headers=_frontend_headers(path))

    if _is_static_asset_request(path):
        raise HTTPException(status_code=404, detail=f"Static asset not found: {path}")

    return _serve_frontend_index()
