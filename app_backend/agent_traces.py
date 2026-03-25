from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app_backend.config import LOGS_DATA_DIR
from app_backend.persistence import init_storage, now_iso

_TRACE_DIR = LOGS_DATA_DIR / "agent_traces"
_TRACE_LOCK = threading.Lock()


class AgentTraceEvent(BaseModel):
    ts: str
    kind: str
    data: dict[str, Any] = Field(default_factory=dict)


class AgentTraceRecord(BaseModel):
    trace_id: str
    thread_id: str
    message: str
    model: str
    status: str = "running"
    started_at: str
    finished_at: str | None = None
    answer: str | None = None
    error: str | None = None
    events: list[AgentTraceEvent] = Field(default_factory=list)


def _sanitize(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _ensure_trace_dir() -> None:
    init_storage()
    _TRACE_DIR.mkdir(parents=True, exist_ok=True)


def _meta_path(trace_id: str) -> Path:
    return _TRACE_DIR / f"{trace_id}.meta.json"


def _events_path(trace_id: str) -> Path:
    return _TRACE_DIR / f"{trace_id}.events.jsonl"


def create_agent_trace(*, trace_id: str, thread_id: str, message: str, model: str) -> None:
    _ensure_trace_dir()
    payload = AgentTraceRecord(
        trace_id=trace_id,
        thread_id=thread_id,
        message=message,
        model=model,
        started_at=now_iso(),
    ).model_dump()
    with _TRACE_LOCK:
        _meta_path(trace_id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        _events_path(trace_id).touch(exist_ok=True)


def append_agent_trace_event(*, trace_id: str, kind: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    _ensure_trace_dir()
    event = AgentTraceEvent(ts=now_iso(), kind=kind, data=_sanitize(data or {})).model_dump()
    with _TRACE_LOCK:
        with _events_path(trace_id).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def finish_agent_trace(
    *,
    trace_id: str,
    status: str,
    answer: str | None = None,
    error: str | None = None,
) -> None:
    _ensure_trace_dir()
    record = get_agent_trace(trace_id)
    if record is None:
        return
    updated = record.model_copy(
        update={
            "status": status,
            "finished_at": now_iso(),
            "answer": answer,
            "error": error,
        }
    )
    with _TRACE_LOCK:
        _meta_path(trace_id).write_text(
            json.dumps(updated.model_dump(exclude={"events"}), ensure_ascii=False),
            encoding="utf-8",
        )


def get_agent_trace(trace_id: str) -> AgentTraceRecord | None:
    _ensure_trace_dir()
    meta_path = _meta_path(trace_id)
    if not meta_path.exists():
        return None

    try:
        meta_payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    events: list[AgentTraceEvent] = []
    events_path = _events_path(trace_id)
    if events_path.exists():
        with events_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(AgentTraceEvent.model_validate_json(line))
                except Exception:  # noqa: BLE001
                    continue

    meta_payload["events"] = [event.model_dump() for event in events]
    return AgentTraceRecord.model_validate(meta_payload)


def list_agent_traces(limit: int = 20) -> list[AgentTraceRecord]:
    _ensure_trace_dir()
    meta_files = sorted(
        _TRACE_DIR.glob("*.meta.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    traces: list[AgentTraceRecord] = []
    for path in meta_files[: max(limit, 1)]:
        trace = get_agent_trace(path.stem.replace(".meta", ""))
        if trace is not None:
            traces.append(trace)
    return traces
