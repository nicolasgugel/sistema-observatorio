from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from app_backend.config import LIVE_AGENT_CACHE_TTL_SECONDS, LIVE_AGENT_DEFAULT_SYNC_TIMEOUT_SECONDS
from app_backend.live_agent import (
    LiveAgentConfigurationError,
    LiveAgentError,
    LiveAgentResponse,
    LiveAgentService,
    PreparedLiveQuery,
    build_cache_key,
)
from app_backend.persistence import now_iso


class LiveQueryRequest(BaseModel):
    question: str = Field(min_length=3)
    retailers: list[str] | None = None
    mode: Literal["auto", "sync", "async"] = "auto"
    max_wait_seconds: int | None = Field(default=None, ge=5, le=120)


@dataclass
class _LiveCacheEntry:
    response: LiveAgentResponse
    expires_at: float


@dataclass
class _LiveJobState:
    job_id: str
    cache_key: str
    prepared_query: PreparedLiveQuery
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    response: LiveAgentResponse = field(
        default_factory=lambda: LiveAgentResponse(
            status="running",
            answer="Scraping en curso.",
            partial=True,
        )
    )
    task: asyncio.Task[None] | None = None


class LiveQueryManager:
    def __init__(self, service: LiveAgentService | None = None):
        self._service = service or LiveAgentService()
        self._cache: dict[str, _LiveCacheEntry] = {}
        self._jobs: dict[str, _LiveJobState] = {}
        self._lock = asyncio.Lock()

    async def handle_query(self, payload: LiveQueryRequest) -> LiveAgentResponse:
        prepared = await self._service.prepare_query(question=payload.question, retailers=payload.retailers)
        if prepared.clarification_response is not None:
            return prepared.clarification_response.model_copy(deep=True)
        cache_key = build_cache_key(prepared)
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        job = await self._create_job(prepared=prepared, cache_key=cache_key)
        if payload.mode == "async":
            return self._snapshot(job)

        timeout = payload.max_wait_seconds or LIVE_AGENT_DEFAULT_SYNC_TIMEOUT_SECONDS
        try:
            await asyncio.wait_for(asyncio.shield(job.task), timeout=timeout)
        except asyncio.TimeoutError:
            return self._snapshot(job)

        return self._snapshot(job)

    def get_job(self, job_id: str) -> LiveAgentResponse:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return self._snapshot(job)

    def _get_cache(self, cache_key: str) -> LiveAgentResponse | None:
        cached = self._cache.get(cache_key)
        if cached is None:
            return None
        if cached.expires_at <= time.monotonic():
            self._cache.pop(cache_key, None)
            return None
        return cached.response.model_copy(deep=True)

    async def _create_job(self, *, prepared: PreparedLiveQuery, cache_key: str) -> _LiveJobState:
        async with self._lock:
            job_id = uuid.uuid4().hex
            job = _LiveJobState(job_id=job_id, cache_key=cache_key, prepared_query=prepared)
            job.response = LiveAgentResponse(
                status="running",
                answer="Scraping en curso.",
                partial=True,
                job_id=job_id,
                poll_url=f"/api/intelligence/agent/live-jobs/{job_id}",
            )
            job.task = asyncio.create_task(self._run_job(job))
            self._jobs[job_id] = job
            return job

    async def _run_job(self, job: _LiveJobState) -> None:
        try:
            result = await self._service.run_query(
                job.prepared_query,
                progress_callback=lambda response: self._update_partial(job.job_id, response),
            )
        except (LiveAgentConfigurationError, LiveAgentError) as exc:
            result = LiveAgentResponse(
                status="failed",
                answer=str(exc),
                partial=False,
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            result = LiveAgentResponse(
                status="failed",
                answer="El agente live ha fallado durante la extraccion.",
                partial=False,
                error=str(exc),
            )

        job.updated_at = now_iso()
        job.response = result.model_copy(
            update={
                "job_id": job.job_id,
                "poll_url": None,
                "partial": False,
            }
        )
        if job.response.status in {"completed", "needs_clarification"}:
            self._cache[job.cache_key] = _LiveCacheEntry(
                response=job.response.model_copy(deep=True),
                expires_at=time.monotonic() + LIVE_AGENT_CACHE_TTL_SECONDS,
            )

    def _update_partial(self, job_id: str, response: LiveAgentResponse) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.updated_at = now_iso()
        job.response = response.model_copy(
            update={
                "status": "running",
                "partial": True,
                "job_id": job_id,
                "poll_url": f"/api/intelligence/agent/live-jobs/{job_id}",
            }
        )

    def _snapshot(self, job: _LiveJobState) -> LiveAgentResponse:
        return job.response.model_copy(deep=True)
