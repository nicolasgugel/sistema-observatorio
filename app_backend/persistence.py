from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app_backend.config import CURRENT_DATA_DIR, HISTORY_DATA_DIR, LOGS_DATA_DIR, STATE_DB_PATH

_DB_LOCK = threading.Lock()


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def init_storage() -> None:
    CURRENT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS refresh_runs (
                id TEXT PRIMARY KEY,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                origin TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                return_code INTEGER,
                brand_scope TEXT NOT NULL,
                competitors_json TEXT,
                products_json TEXT,
                record_count INTEGER,
                error TEXT,
                snapshot_id TEXT,
                triggered_by TEXT,
                command_json TEXT,
                request_json TEXT,
                logs_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                run_id TEXT,
                mode TEXT NOT NULL,
                is_current INTEGER NOT NULL DEFAULT 0,
                csv_path TEXT NOT NULL,
                json_path TEXT NOT NULL,
                html_path TEXT NOT NULL,
                metadata_path TEXT NOT NULL,
                record_count INTEGER NOT NULL DEFAULT 0,
                brand_scope TEXT NOT NULL,
                competitors_json TEXT
            )
            """
        )
        conn.commit()


def mark_stale_runs_failed(reason: str = "Worker restarted before completion.") -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE refresh_runs
            SET status = 'failed',
                finished_at = COALESCE(finished_at, ?),
                error = COALESCE(error, ?)
            WHERE status IN ('queued', 'running')
            """,
            (now_iso(), reason),
        )
        conn.commit()


@contextmanager
def _connect() -> Any:
    with _DB_LOCK:
        conn = sqlite3.connect(STATE_DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _run_log_path(run_id: str) -> Path:
    return LOGS_DATA_DIR / f"{run_id}.log"


def create_run(
    *,
    run_id: str,
    mode: str,
    status: str,
    origin: str,
    brand_scope: str,
    competitors: list[str] | None,
    products: list[dict] | None,
    triggered_by: str | None,
    request_payload: dict,
) -> None:
    init_storage()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO refresh_runs (
                id, mode, status, origin, created_at, brand_scope,
                competitors_json, products_json, triggered_by, request_json, logs_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                run_id,
                mode,
                status,
                origin,
                now_iso(),
                brand_scope,
                _json_dumps(competitors or []),
                _json_dumps(products or []),
                triggered_by or "",
                _json_dumps(request_payload),
            ),
        )
        conn.commit()


def update_run(
    run_id: str,
    *,
    status: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    return_code: int | None = None,
    error: str | None = None,
    snapshot_id: str | None = None,
    record_count: int | None = None,
    command: list[str] | None = None,
) -> None:
    assignments: list[str] = []
    values: list[Any] = []
    if status is not None:
        assignments.append("status = ?")
        values.append(status)
    if started_at is not None:
        assignments.append("started_at = ?")
        values.append(started_at)
    if finished_at is not None:
        assignments.append("finished_at = ?")
        values.append(finished_at)
    if return_code is not None:
        assignments.append("return_code = ?")
        values.append(return_code)
    if error is not None:
        assignments.append("error = ?")
        values.append(error)
    if snapshot_id is not None:
        assignments.append("snapshot_id = ?")
        values.append(snapshot_id)
    if record_count is not None:
        assignments.append("record_count = ?")
        values.append(record_count)
    if command is not None:
        assignments.append("command_json = ?")
        values.append(_json_dumps(command))
    if not assignments:
        return

    values.append(run_id)
    with _connect() as conn:
        conn.execute(f"UPDATE refresh_runs SET {', '.join(assignments)} WHERE id = ?", values)
        conn.commit()


def append_run_log(run_id: str, *, level: str, message: str, ts: str | None = None) -> dict:
    event_ts = ts or now_iso()
    with _connect() as conn:
        row = conn.execute("SELECT logs_count FROM refresh_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"Run no encontrado: {run_id}")
        index = int(row["logs_count"] or 0)
        event = {
            "type": "log",
            "index": index,
            "ts": event_ts,
            "level": level,
            "message": message,
        }
        log_path = _run_log_path(run_id)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        conn.execute("UPDATE refresh_runs SET logs_count = logs_count + 1 WHERE id = ?", (run_id,))
        conn.commit()
        return event


def get_logs_after(run_id: str, after: int = 0) -> list[dict]:
    log_path = _run_log_path(run_id)
    if not log_path.exists():
        return []

    events: list[dict] = []
    with log_path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx < after:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _serialize_run_row(row: sqlite3.Row) -> dict:
    request_payload = _json_loads(row["request_json"], {})
    return {
        "id": row["id"],
        "mode": row["mode"],
        "origin": row["origin"],
        "status": row["status"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "return_code": row["return_code"],
        "error": row["error"],
        "snapshot_id": row["snapshot_id"],
        "record_count": row["record_count"],
        "brand_scope": row["brand_scope"],
        "competitors": _json_loads(row["competitors_json"], []),
        "products": _json_loads(row["products_json"], []),
        "triggered_by": row["triggered_by"] or "",
        "command": _json_loads(row["command_json"], []),
        "request": request_payload,
        "logs_count": row["logs_count"],
    }


def get_run(run_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM refresh_runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    return _serialize_run_row(row)


def list_runs(limit: int = 20) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM refresh_runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_serialize_run_row(row) for row in rows]


def get_active_run() -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM refresh_runs
            WHERE status IN ('queued', 'running')
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return _serialize_run_row(row)


def _relative_or_absolute(path: Path) -> str:
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def _snapshot_label_from_values(created_at: str, mode: str, brand_scope: str, record_count: int, snapshot_id: str) -> str:
    stamp = created_at.replace("T", " ")[:16] if created_at else snapshot_id
    return f"{stamp} | {mode} | {brand_scope} | {record_count} registros"


def _snapshot_row_payload(
    *,
    snapshot_id: str,
    created_at: str,
    run_id: str | None,
    mode: str,
    is_current: bool,
    csv_path: str,
    json_path: str,
    html_path: str,
    metadata_path: str,
    record_count: int,
    brand_scope: str,
    competitors: list[str],
) -> dict:
    return {
        "id": snapshot_id,
        "created_at": created_at,
        "run_id": run_id,
        "mode": mode,
        "is_current": is_current,
        "csv_path": csv_path,
        "json_path": json_path,
        "html_path": html_path,
        "metadata_path": metadata_path,
        "record_count": record_count,
        "brand_scope": brand_scope,
        "competitors": competitors,
        "label": _snapshot_label_from_values(created_at, mode, brand_scope, record_count, snapshot_id),
    }


def create_snapshot(
    *,
    snapshot_id: str,
    run_id: str | None,
    mode: str,
    created_at: str,
    csv_path: Path,
    json_path: Path,
    html_path: Path,
    metadata_path: Path,
    record_count: int,
    brand_scope: str,
    competitors: list[str] | None,
    is_current: bool = True,
) -> None:
    init_storage()
    with _connect() as conn:
        if is_current:
            conn.execute("UPDATE snapshots SET is_current = 0 WHERE is_current = 1")
        conn.execute(
            """
            INSERT OR REPLACE INTO snapshots (
                id, created_at, run_id, mode, is_current,
                csv_path, json_path, html_path, metadata_path,
                record_count, brand_scope, competitors_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                created_at,
                run_id,
                mode,
                1 if is_current else 0,
                _relative_or_absolute(csv_path),
                _relative_or_absolute(json_path),
                _relative_or_absolute(html_path),
                _relative_or_absolute(metadata_path),
                record_count,
                brand_scope,
                _json_dumps(competitors or []),
            ),
        )
        conn.commit()


def _load_snapshot_from_metadata(metadata_path: Path) -> dict | None:
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(metadata, dict):
        return None

    snapshot_id = str(metadata.get("id") or metadata_path.parent.name)
    created_at = str(metadata.get("created_at") or "")
    mode = str(metadata.get("mode") or "scheduled")
    brand_scope = str(metadata.get("brand_scope") or "all")
    competitors = metadata.get("competitors") if isinstance(metadata.get("competitors"), list) else []
    record_count = int(metadata.get("record_count") or 0)
    files = metadata.get("files") if isinstance(metadata.get("files"), dict) else {}

    def resolve_file(key: str, default_name: str) -> str:
        raw_value = str(files.get(key) or "").strip()
        if raw_value:
            candidate = Path(raw_value)
            if candidate.exists():
                return str(candidate)
            relative_candidate = metadata_path.parent / raw_value
            if relative_candidate.exists():
                return str(relative_candidate)
        return str(metadata_path.parent / default_name)

    return {
        "id": snapshot_id,
        "created_at": created_at,
        "run_id": metadata.get("run_id"),
        "mode": mode,
        "brand_scope": brand_scope,
        "competitors": [str(item) for item in competitors],
        "record_count": record_count,
        "csv_path": resolve_file("master_prices_csv", "master_prices.csv"),
        "json_path": resolve_file("latest_prices_json", "latest_prices.json"),
        "html_path": resolve_file("price_comparison_live_html", "price_comparison_live.html"),
        "metadata_path": str(metadata_path),
        "metadata": metadata,
        "files": {
            "master_prices_csv": resolve_file("master_prices_csv", "master_prices.csv"),
            "latest_prices_csv": resolve_file("latest_prices_csv", "latest_prices.csv"),
            "latest_prices_json": resolve_file("latest_prices_json", "latest_prices.json"),
            "price_comparison_live_html": resolve_file("price_comparison_live_html", "price_comparison_live.html"),
        },
        "products": metadata.get("products") if isinstance(metadata.get("products"), list) else [],
    }


def _discover_snapshots_from_filesystem() -> list[dict]:
    discovered: list[dict] = []
    for metadata_path in HISTORY_DATA_DIR.glob("*/metadata.json"):
        payload = _load_snapshot_from_metadata(metadata_path)
        if payload is not None:
            discovered.append(payload)

    discovered.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    current_id = discovered[0]["id"] if discovered else None

    snapshots: list[dict] = []
    for item in discovered:
        snapshots.append(
            _snapshot_row_payload(
                snapshot_id=item["id"],
                created_at=item["created_at"],
                run_id=item.get("run_id"),
                mode=item["mode"],
                is_current=item["id"] == current_id,
                csv_path=item["csv_path"],
                json_path=item["json_path"],
                html_path=item["html_path"],
                metadata_path=item["metadata_path"],
                record_count=item["record_count"],
                brand_scope=item["brand_scope"],
                competitors=item["competitors"],
            )
            | {
                "metadata": item.get("metadata", {}),
                "files": item.get("files", {}),
                "products": item.get("products", []),
            }
        )
    return snapshots


def sync_snapshots_with_filesystem() -> None:
    init_storage()
    discovered = _discover_snapshots_from_filesystem()

    try:
        with _connect() as conn:
            conn.execute("DELETE FROM snapshots")
            for item in discovered:
                conn.execute(
                    """
                    INSERT INTO snapshots (
                        id, created_at, run_id, mode, is_current,
                        csv_path, json_path, html_path, metadata_path,
                        record_count, brand_scope, competitors_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["id"],
                        item["created_at"],
                        item.get("run_id"),
                        item["mode"],
                        1 if item["is_current"] else 0,
                        item["csv_path"],
                        item["json_path"],
                        item["html_path"],
                        item["metadata_path"],
                        item["record_count"],
                        item["brand_scope"],
                        _json_dumps(item["competitors"]),
                    ),
                )
            conn.commit()
    except sqlite3.Error:
        # Vercel sirve el histórico desde archivos empaquetados; si SQLite no es
        # escribible, la lectura pública sigue funcionando con metadata.json.
        return


def _serialize_snapshot_row(row: sqlite3.Row) -> dict:
    return _snapshot_row_payload(
        snapshot_id=row["id"],
        created_at=row["created_at"],
        run_id=row["run_id"],
        mode=row["mode"],
        is_current=bool(row["is_current"]),
        csv_path=row["csv_path"],
        json_path=row["json_path"],
        html_path=row["html_path"],
        metadata_path=row["metadata_path"],
        record_count=row["record_count"],
        brand_scope=row["brand_scope"],
        competitors=_json_loads(row["competitors_json"], []),
    )


def list_snapshots(limit: int = 100) -> list[dict]:
    return _discover_snapshots_from_filesystem()[:limit]


def get_snapshot(snapshot_id: str = "current") -> dict | None:
    snapshots = _discover_snapshots_from_filesystem()
    if snapshot_id == "current":
        payload = snapshots[0] if snapshots else None
    else:
        payload = next((item for item in snapshots if item["id"] == snapshot_id), None)
    if payload is None:
        return None

    metadata_path = Path(payload["metadata_path"])
    if metadata_path.exists():
        try:
            payload["metadata"] = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload["metadata"] = {}
    else:
        payload["metadata"] = {}

    try:
        run_payload = get_run(str(payload.get("run_id") or "")) if payload.get("run_id") else None
    except sqlite3.Error:
        run_payload = None
    payload["products"] = run_payload.get("products", []) if run_payload else payload["metadata"].get("products", [])
    payload["files"] = payload["metadata"].get(
        "files",
        {
            "master_prices_csv": payload["csv_path"],
            "latest_prices_csv": payload["csv_path"],
            "latest_prices_json": payload["json_path"],
            "price_comparison_live_html": payload["html_path"],
        },
    )
    return payload
