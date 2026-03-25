from __future__ import annotations

import json
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app_backend.agent_traces import (
    append_agent_trace_event,
    create_agent_trace,
    finish_agent_trace,
)
from app_backend.config import (
    OBSERVATORIO_AGENT_MODEL,
    OPENAI_API_KEY,
)
from app_backend.data_access import build_table_meta, load_table_rows, read_publish_manifest
from app_backend.intelligence import (
    _record_to_public,
    answer_agent_question,
    apply_filters,
    build_dashboard_payload,
    sort_rows,
)
from app_backend.live_agent import LiveAgentOffer
from observatorio.text_utils import normalize_text

_INTERNAL_DATASET_HINTS = (
    "observatorio",
    "current",
    "dataset",
    "cobertura",
    "santander",
    "competidor",
    "competidores",
    "gap",
    "gaps",
    "posicionamiento",
    "pricing",
    "estrategia",
    "renting",
    "financiacion",
    "financiación",
    "cash",
    "modalidad",
    "modalidades",
    "bundle",
    "bundles",
    "lanzamiento",
    "lanzamientos",
    "juego",
    "juegos",
    "videojuego",
    "videojuegos",
    "snapshot",
    "nuestros datos",
)
_PRODUCT_REQUEST_HINTS = (
    "precio",
    "precios",
    "cuesta",
    "coste",
    "costar",
    "busca",
    "buscar",
    "compare",
    "comparar",
    "vs",
)
_GENERIC_PRODUCT_HINTS = (
    "samsung",
    "galaxy",
    "iphone",
    "apple",
    "movil",
    "moviles",
    "telefono",
    "smartphone",
    "tablet",
    "watch",
    "reloj",
)
_MEMORY_FOLLOW_UP_HINTS = (
    "y para",
    "y si",
    "con eso",
    "sobre eso",
    "de ese",
    "de esa",
    "de este",
    "de esta",
    "ese producto",
    "esta consola",
    "lo posicionarias",
    "lo pondrias",
    "que harias",
    "qué harías",
    "haria santander",
    "haria banco santander",
)
_MEMORY_STRATEGY_HINTS = (
    "estrategia",
    "pricing",
    "renting",
    "financiacion",
    "financiación",
    "cuota",
    "cuotas",
    "bundle",
    "bundles",
    "lanzamiento",
    "lanzamientos",
    "juego",
    "juegos",
    "promo",
    "promocion",
    "promoción",
    "cash",
)
_MAX_MEMORY_THREADS = 200
_MAX_MEMORY_MESSAGES = 10


class AgentChatError(RuntimeError):
    pass


class AgentChatConfigurationError(AgentChatError):
    pass


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)


class AgentToolOutcome(BaseModel):
    status: Literal["completed", "needs_clarification", "failed"] = "completed"
    answer: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    offers: list[LiveAgentOffer] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class AgentChatResponse(BaseModel):
    trace_id: str
    thread_id: str
    status: Literal["completed", "needs_clarification", "failed"] = "completed"
    answer: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    offers: list[LiveAgentOffer] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class CurrentSnapshotMeta(BaseModel):
    snapshot_id: str
    source_path: str
    record_count: int
    latest_timestamp: str = ""
    competitors: list[str] = Field(default_factory=list)
    brands: list[str] = Field(default_factory=list)
    offer_types: list[str] = Field(default_factory=list)
    manifest: dict[str, Any] = Field(default_factory=dict)


class CurrentOfferRecord(BaseModel):
    competidor: str
    marca: str = ""
    modelo: str
    capacidad: int | None = None
    modalidad: str = ""
    modalidad_label: str = ""
    precio_valor: float | None = None
    moneda: str = "EUR"
    disponibilidad: bool | None = None
    timestamp_extraccion: str = ""
    url_producto: str = ""


class FindCurrentOffersResult(BaseModel):
    count: int
    applied_filters: dict[str, Any] = Field(default_factory=dict)
    offers: list[CurrentOfferRecord] = Field(default_factory=list)


class CurrentDatasetSummary(BaseModel):
    intent: str = "summary"
    summary_text: str
    latest_timestamp: str = ""
    coverage_by_competitor: list[dict[str, Any]] = Field(default_factory=list)
    avg_price_by_modality: list[dict[str, Any]] = Field(default_factory=list)
    gap_vs_santander: list[dict[str, Any]] = Field(default_factory=list)
    price_positioning: list[dict[str, Any]] = Field(default_factory=list)
    best_offers: list[CurrentOfferRecord] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)


@dataclass(slots=True)
class ThreadMemoryState:
    messages: list[dict[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class CurrentDatasetView:
    snapshot_id: str
    source_path: Path
    table_rows: list[dict[str, Any]]
    public_rows: list[dict[str, Any]]
    table_meta: dict[str, Any]
    manifest: dict[str, Any]


@dataclass(slots=True)
class AgentRunContext:
    service: "ObservatorioAgentService"
    trace_id: str
    thread_id: str
    allow_dataset_tools: bool = False
    dataset_cache: CurrentDatasetView | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)


def _import_agents_sdk() -> tuple[Any, Any, Any, Any, Any, Any, Any, Any]:
    try:
        from agents import (
            Agent,
            AgentOutputSchema,
            ModelSettings,
            RunConfig,
            RunContextWrapper,
            Runner,
            WebSearchTool,
            function_tool,
        )
    except ImportError as exc:
        raise AgentChatConfigurationError(
            "openai-agents no esta instalado. Ejecuta `python -m pip install openai-agents`."
        ) from exc
    return Agent, AgentOutputSchema, ModelSettings, RunConfig, RunContextWrapper, Runner, WebSearchTool, function_tool


def _normalize_status(value: Any) -> Literal["completed", "needs_clarification", "failed"]:
    status = normalize_text(str(value or "completed"))
    if status == "needs_clarification":
        return "needs_clarification"
    if status == "failed":
        return "failed"
    return "completed"


def _dedupe_jsonable(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        cleaned = item.strip()
        if not cleaned:
            continue
        key = normalize_text(cleaned)
        if key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)
    return unique


def _coerce_live_offer(value: Any) -> LiveAgentOffer | None:
    if isinstance(value, LiveAgentOffer):
        return value
    if isinstance(value, dict):
        try:
            return LiveAgentOffer.model_validate(value)
        except Exception:  # noqa: BLE001
            return None
    return None


def _coerce_tool_outcome(value: Any) -> AgentToolOutcome | None:
    if isinstance(value, AgentToolOutcome):
        return value
    if isinstance(value, dict):
        try:
            return AgentToolOutcome.model_validate(value)
        except Exception:  # noqa: BLE001
            return None
    return None


def _offer_record_from_public_row(row: dict[str, Any]) -> CurrentOfferRecord:
    capacity = row.get("capacidad")
    return CurrentOfferRecord(
        competidor=str(row.get("competidor") or ""),
        marca=str(row.get("marca") or ""),
        modelo=str(row.get("modelo") or ""),
        capacidad=int(capacity) if isinstance(capacity, int) else None,
        modalidad=str(row.get("modalidad") or ""),
        modalidad_label=str(row.get("modalidad_label") or row.get("modalidad") or ""),
        precio_valor=float(row["precio_valor"]) if isinstance(row.get("precio_valor"), (int, float)) else None,
        moneda=str(row.get("moneda") or "EUR"),
        disponibilidad=row.get("disponibilidad") if isinstance(row.get("disponibilidad"), bool) else None,
        timestamp_extraccion=str(row.get("timestamp_extraccion") or ""),
        url_producto=str(row.get("url_producto") or ""),
    )


def _best_offer_records(rows: list[dict[str, Any]], *, limit: int = 5) -> list[CurrentOfferRecord]:
    priced_rows = [row for row in rows if isinstance(row.get("precio_valor"), (int, float))]
    sorted_rows = sort_rows(priced_rows, sort_by="precio_valor", sort_dir="asc")
    return [_offer_record_from_public_row(row) for row in sorted_rows[: max(limit, 1)]]


def _synthesize_offer_answer(offers: list[LiveAgentOffer]) -> str:
    priced = [offer for offer in offers if isinstance(offer.price_value, (int, float))]
    if not priced:
        return "He completado la busqueda web, pero no he podido verificar un precio visible."
    sorted_offers = sorted(priced, key=lambda item: float(item.price_value or 0))
    best = sorted_offers[0]
    answer = (
        f"El mejor precio web visible es {best.price_value} {best.currency} en {best.retailer} "
        f"para {best.matched_title}."
    )
    if len(sorted_offers) > 1:
        answer += f" Tengo {len(sorted_offers)} referencias verificadas para comparar."
    return answer


def _system_prompt() -> str:
    return (
        "Eres el agente conversacional del Observatorio de precios. "
        "Respondes en espanol, con tono ejecutivo y sin relleno. "
        "Tu salida final debe cumplir exactamente el esquema AgentToolOutcome. "
        "Usa `get_current_snapshot_meta`, `find_current_offers` y `summarize_current_dataset` "
        "para preguntas sobre nuestro observatorio, current, cobertura, Santander Boutique, gaps, "
        "posicionamiento o estrategia interna. "
        "Usa `WebSearchTool` para precios de mercado abierto, precios actuales fuera del dataset o "
        "comparativas externas. "
        "Si la pregunta es hibrida, primero recupera el dato web y luego contrastalo con el dataset current. "
        "Para propuestas de pricing Santander, apoyate en modalidades del current como renting, financiacion y cash, "
        "y combina eso con senales de mercado abierto, bundles y futuros lanzamientos cuando sean relevantes. "
        "No inventes precios, URLs ni cobertura. "
        "Si falta modelo, capacidad o modalidad para responder con precision, devuelve "
        "`status=needs_clarification`, una pregunta de seguimiento corta y sugerencias concretas. "
        "En `evidence` incluye solo grounding del dataset local. "
        "En `offers` incluye solo ofertas de mercado abierto verificadas desde web search. "
        "Si usas ambos mundos, la respuesta debe dejar clara la diferencia entre dato web y dato current. "
        "Cuando respondas con precios de mercado abierto, incluye en `suggestions` al menos una opcion de follow-up "
        "para estrategia de pricing Santander si el contexto lo permite."
    )


class ObservatorioAgentService:
    def __init__(
        self,
        *,
        session_db_path: str | Path | None = None,
        web_search_tool: Any | None = None,
    ) -> None:
        _ = session_db_path
        self._web_search_tool_override = web_search_tool
        self._agent: Any | None = None
        self._thread_memory: OrderedDict[str, ThreadMemoryState] = OrderedDict()

    async def initialize(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    def _resolved_agent_model_name(self) -> str:
        candidate = normalize_text(OBSERVATORIO_AGENT_MODEL)
        if candidate:
            return candidate
        return "gpt-5-mini"

    def _trace(self, trace_id: str | None, kind: str, **data: Any) -> None:
        if not trace_id:
            return
        append_agent_trace_event(trace_id=trace_id, kind=kind, data=data)

    def _ensure_runtime_ready(self) -> None:
        if not OPENAI_API_KEY:
            raise AgentChatConfigurationError("OPENAI_API_KEY no esta configurada en el backend.")

    def _load_dataset_view(
        self,
        *,
        snapshot_id: str = "current",
        context: AgentRunContext | None = None,
    ) -> CurrentDatasetView:
        clean_snapshot_id = snapshot_id.strip() or "current"
        if clean_snapshot_id == "current" and context is not None and context.dataset_cache is not None:
            return context.dataset_cache

        table_rows, source_path = load_table_rows(snapshot_id=clean_snapshot_id)
        public_rows = [_record_to_public(row) for row in table_rows]
        manifest = read_publish_manifest() if clean_snapshot_id == "current" else {}
        view = CurrentDatasetView(
            snapshot_id=clean_snapshot_id,
            source_path=source_path,
            table_rows=table_rows,
            public_rows=public_rows,
            table_meta=build_table_meta(table_rows),
            manifest=manifest,
        )
        if clean_snapshot_id == "current" and context is not None:
            context.dataset_cache = view
        return view

    def _append_evidence(self, context: AgentRunContext, rows: list[dict[str, Any]]) -> None:
        context.evidence = _dedupe_jsonable(context.evidence + rows)

    def _top_model_suggestions(self, *, limit: int = 4) -> list[str]:
        dataset = self._load_dataset_view(snapshot_id="current")
        models = sorted({str(row.get("modelo") or "") for row in dataset.public_rows if row.get("modelo")})
        return models[: max(limit, 1)]

    def _memory_for_thread(self, thread_id: str) -> ThreadMemoryState:
        state = self._thread_memory.get(thread_id)
        if state is None:
            state = ThreadMemoryState()
            self._thread_memory[thread_id] = state
        else:
            self._thread_memory.move_to_end(thread_id)
        while len(self._thread_memory) > _MAX_MEMORY_THREADS:
            self._thread_memory.popitem(last=False)
        return state

    def _build_run_input(self, *, message: str, memory: ThreadMemoryState | None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if memory is not None:
            for item in memory.messages[-_MAX_MEMORY_MESSAGES:]:
                role = item.get("role", "user")
                text = item.get("text", "").strip()
                if not text:
                    continue
                content_type = "input_text" if role == "user" else "output_text"
                items.append({"role": role, "content": [{"type": content_type, "text": text}]})
        items.append({"role": "user", "content": [{"type": "input_text", "text": message}]})
        return items

    def _memory_suggests_dataset_follow_up(self, *, message: str, memory: ThreadMemoryState) -> bool:
        normalized = normalize_text(message)
        if not memory.messages:
            return False
        has_follow_up_shape = any(hint in normalized for hint in _MEMORY_FOLLOW_UP_HINTS)
        has_strategy_shape = any(hint in normalized for hint in _MEMORY_STRATEGY_HINTS)
        return has_follow_up_shape or has_strategy_shape

    def _append_thread_message(self, *, thread_id: str, role: Literal["user", "assistant"], text: str) -> None:
        clean_text = text.strip()
        if not clean_text:
            return
        memory = self._memory_for_thread(thread_id)
        memory.messages.append({"role": role, "text": clean_text})
        memory.messages = memory.messages[-_MAX_MEMORY_MESSAGES:]

    def _remember_thread_turn(
        self,
        *,
        thread_id: str,
        message: str,
        answer: str,
    ) -> None:
        self._append_thread_message(thread_id=thread_id, role="user", text=message)
        self._append_thread_message(thread_id=thread_id, role="assistant", text=answer)

    def _message_targets_internal_dataset(self, message: str) -> bool:
        normalized = normalize_text(message)
        return any(hint in normalized for hint in _INTERNAL_DATASET_HINTS)

    def _needs_clarification(self, message: str, *, memory: ThreadMemoryState | None = None) -> bool:
        normalized = normalize_text(message)
        if self._message_targets_internal_dataset(message):
            return False
        if memory is not None and memory.messages and self._memory_suggests_dataset_follow_up(message=message, memory=memory):
            return False
        if not any(hint in normalized for hint in _PRODUCT_REQUEST_HINTS):
            return False

        dataset = self._load_dataset_view(snapshot_id="current")
        models = [normalize_text(str(row.get("modelo") or "")) for row in dataset.public_rows if row.get("modelo")]
        if any(model and model in normalized for model in models):
            return False
        if any(token in normalized for token in _GENERIC_PRODUCT_HINTS) and not any(char.isdigit() for char in normalized):
            return True
        return len(normalized.split()) <= 2 and any(token in normalized for token in _GENERIC_PRODUCT_HINTS)

    def _clarification_response(self, *, message: str, thread_id: str, trace_id: str) -> AgentChatResponse:
        suggestions = self._top_model_suggestions()
        answer = (
            "Necesito al menos el modelo exacto y, si aplica, capacidad o modalidad para responder sin inventar."
        )
        if suggestions:
            answer += " Puedes pedirme, por ejemplo, uno de estos modelos del current."
        return AgentChatResponse(
            trace_id=trace_id,
            thread_id=thread_id,
            status="needs_clarification",
            answer=answer,
            evidence=[],
            offers=[],
            suggestions=suggestions,
        )

    def _default_suggestions(self, *, message: str, offers: list[LiveAgentOffer], evidence: list[dict[str, Any]]) -> list[str]:
        if offers:
            return [
                "Si quieres, te planteo la estrategia de pricing Santander para renting, financiacion y cash con este producto.",
                "Puedo cruzar estos precios con el current y decirte como posicionaria a Santander.",
                "Tambien puedo incorporar bundles y futuros lanzamientos para proponer timing comercial.",
            ]
        if evidence or self._message_targets_internal_dataset(message):
            return [
                "Bajalo a modelo, capacidad o modalidad concreta.",
                "Contrasta el current contra precio web actual.",
                "Si quieres, te propongo la estrategia de pricing Santander para renting, financiacion y cash.",
            ]
        return []

    def _build_agent(self) -> Any:
        Agent, AgentOutputSchema, ModelSettings, _, RunContextWrapper, _, WebSearchTool, function_tool = _import_agents_sdk()
        globals()["RunContextWrapper"] = RunContextWrapper

        def _dataset_tools_enabled(ctx: RunContextWrapper[AgentRunContext], _agent: Any) -> bool:
            return bool(ctx.context.allow_dataset_tools)

        @function_tool(is_enabled=_dataset_tools_enabled)
        async def get_current_snapshot_meta(
            ctx: RunContextWrapper[AgentRunContext],
            snapshot_id: str = "current",
        ) -> CurrentSnapshotMeta:
            """Return metadata for the requested observatorio snapshot.

            Args:
                snapshot_id: Snapshot id to inspect. Use `current` by default.
            """

            dataset = self._load_dataset_view(snapshot_id=snapshot_id, context=ctx.context)
            payload = CurrentSnapshotMeta(
                snapshot_id=dataset.snapshot_id,
                source_path=str(dataset.source_path),
                record_count=len(dataset.public_rows),
                latest_timestamp=str(dataset.table_meta.get("latest_extracted_at") or ""),
                competitors=list(dataset.table_meta.get("retailers") or []),
                brands=list(dataset.table_meta.get("brands") or []),
                offer_types=list(dataset.table_meta.get("offer_types") or []),
                manifest=dataset.manifest,
            )
            self._append_evidence(
                ctx.context,
                [
                    {
                        "snapshot_id": payload.snapshot_id,
                        "source_path": payload.source_path,
                        "record_count": payload.record_count,
                        "latest_timestamp": payload.latest_timestamp,
                    }
                ],
            )
            self._trace(
                ctx.context.trace_id,
                "tool_call",
                tool="get_current_snapshot_meta",
                snapshot_id=snapshot_id,
                record_count=payload.record_count,
            )
            return payload

        @function_tool(is_enabled=_dataset_tools_enabled)
        async def find_current_offers(
            ctx: RunContextWrapper[AgentRunContext],
            brand: str = "all",
            retailer: str | None = None,
            model: str | None = None,
            capacity_gb: int | None = None,
            modality: str | None = None,
            limit: int = 10,
            snapshot_id: str = "current",
            search: str | None = None,
        ) -> FindCurrentOffersResult:
            """Find current offers in the local observatorio dataset.

            Args:
                brand: Brand filter. Use `all` to avoid filtering.
                retailer: Competitor filter.
                model: Exact model filter as it appears in the dataset.
                capacity_gb: Capacity filter in GB.
                modality: Modality filter such as `cash` or `renting_with_insurance`.
                limit: Maximum number of rows to return.
                snapshot_id: Snapshot id to inspect. Use `current` by default.
                search: Optional free-text filter when the user phrase is fuzzy.
            """

            dataset = self._load_dataset_view(snapshot_id=snapshot_id, context=ctx.context)
            rows = dataset.public_rows
            if normalize_text(brand) not in {"", "all"}:
                brand_n = normalize_text(brand)
                rows = [row for row in rows if normalize_text(str(row.get("marca") or "")) == brand_n]

            filtered = apply_filters(
                rows,
                competitors=[retailer] if retailer else None,
                models=[model] if model else None,
                capacities=[capacity_gb] if capacity_gb is not None else None,
                modalities=[modality] if modality else None,
                search=search,
            )
            filtered = sort_rows(filtered, sort_by="precio_valor", sort_dir="asc")
            selected = filtered[: max(min(limit, 25), 1)]
            offers = [_offer_record_from_public_row(row) for row in selected]
            evidence = [offer.model_dump() for offer in offers[:5]]
            self._append_evidence(ctx.context, evidence)
            self._trace(
                ctx.context.trace_id,
                "tool_call",
                tool="find_current_offers",
                snapshot_id=snapshot_id,
                brand=brand,
                retailer=retailer,
                model=model,
                capacity_gb=capacity_gb,
                modality=modality,
                result_count=len(offers),
            )
            return FindCurrentOffersResult(
                count=len(offers),
                applied_filters={
                    "brand": brand,
                    "retailer": retailer,
                    "model": model,
                    "capacity_gb": capacity_gb,
                    "modality": modality,
                    "snapshot_id": snapshot_id,
                    "search": search,
                    "limit": max(min(limit, 25), 1),
                },
                offers=offers,
            )

        @function_tool(is_enabled=_dataset_tools_enabled)
        async def summarize_current_dataset(
            ctx: RunContextWrapper[AgentRunContext],
            question: str,
            brand: str = "Samsung",
            snapshot_id: str = "current",
        ) -> CurrentDatasetSummary:
            """Summarize coverage, gaps and positioning from the local observatorio dataset.

            Args:
                question: User question to summarize, for example coverage or Santander positioning.
                brand: Brand scope. Use `all` to summarize every brand.
                snapshot_id: Snapshot id to inspect. Use `current` by default.
            """

            dataset = self._load_dataset_view(snapshot_id=snapshot_id, context=ctx.context)
            rows = dataset.public_rows
            if normalize_text(brand) not in {"", "all"}:
                brand_n = normalize_text(brand)
                rows = [row for row in rows if normalize_text(str(row.get("marca") or "")) == brand_n]

            answer_bundle = answer_agent_question(question, rows)
            dashboard = build_dashboard_payload(rows, brand=brand if normalize_text(brand) else "all")
            summary = CurrentDatasetSummary(
                intent=str(answer_bundle.get("intent") or "summary"),
                summary_text=str(answer_bundle.get("answer") or ""),
                latest_timestamp=str(dashboard.get("kpis", {}).get("timestamp_ultima_extraccion") or ""),
                coverage_by_competitor=list(dashboard.get("coverage_by_competitor") or [])[:5],
                avg_price_by_modality=list(dashboard.get("avg_price_by_modality") or [])[:4],
                gap_vs_santander=list(dashboard.get("gap_vs_santander") or [])[:5],
                price_positioning=list(dashboard.get("price_by_competitor") or [])[:5],
                best_offers=_best_offer_records(rows, limit=5),
                evidence=list(answer_bundle.get("evidence") or [])[:5],
            )
            self._append_evidence(ctx.context, summary.evidence)
            self._trace(
                ctx.context.trace_id,
                "tool_call",
                tool="summarize_current_dataset",
                snapshot_id=snapshot_id,
                brand=brand,
                intent=summary.intent,
                evidence_count=len(summary.evidence),
            )
            return summary

        web_search_tool = self._web_search_tool_override or WebSearchTool(
            search_context_size="medium",
            user_location={"country": "ES", "type": "approximate"},
        )
        return Agent(
            name="Observatorio pricing chat",
            model=self._resolved_agent_model_name(),
            instructions=_system_prompt(),
            output_type=AgentOutputSchema(AgentToolOutcome, strict_json_schema=False),
            tools=[web_search_tool, get_current_snapshot_meta, find_current_offers, summarize_current_dataset],
            model_settings=ModelSettings(
                reasoning={"effort": "medium", "summary": "auto"},
                parallel_tool_calls=False,
                store=True,
            ),
        )

    def _get_agent(self) -> Any:
        if self._agent is None:
            self._agent = self._build_agent()
        return self._agent

    async def _run_agent(
        self,
        *,
        message: str | list[dict[str, Any]],
        context: AgentRunContext,
        trace_id: str,
        thread_id: str,
    ) -> Any:
        _, _, _, RunConfig, _, Runner, _, _ = _import_agents_sdk()
        sdk_trace_id = trace_id if trace_id.startswith("trace_") else f"trace_{trace_id}"
        return await Runner.run(
            self._get_agent(),
            message,
            context=context,
            max_turns=8,
            run_config=RunConfig(
                workflow_name="Observatorio Agent Chat",
                trace_id=sdk_trace_id,
                group_id=thread_id,
                trace_metadata={
                    "__trace_source__": "observatorio-agent-chat",
                    "thread_id": thread_id,
                },
            ),
        )

    async def chat(self, *, message: str, thread_id: str) -> AgentChatResponse:
        clean_message = message.strip()
        clean_thread_id = thread_id.strip() or uuid.uuid4().hex
        memory = self._memory_for_thread(clean_thread_id)
        trace_id = uuid.uuid4().hex
        create_agent_trace(
            trace_id=trace_id,
            thread_id=clean_thread_id,
            message=clean_message,
            model=self._resolved_agent_model_name(),
        )
        self._trace(trace_id, "chat_start", thread_id=clean_thread_id, message=clean_message)

        if self._needs_clarification(clean_message, memory=memory):
            response = self._clarification_response(message=clean_message, thread_id=clean_thread_id, trace_id=trace_id)
            self._remember_thread_turn(thread_id=clean_thread_id, message=clean_message, answer=response.answer)
            self._trace(trace_id, "chat_end", status=response.status, route="clarification_preflight")
            finish_agent_trace(trace_id=trace_id, status=response.status, answer=response.answer)
            return response

        try:
            self._ensure_runtime_ready()
            allow_dataset_tools = self._message_targets_internal_dataset(clean_message) or self._memory_suggests_dataset_follow_up(
                message=clean_message,
                memory=memory,
            )
            context = AgentRunContext(
                service=self,
                trace_id=trace_id,
                thread_id=clean_thread_id,
                allow_dataset_tools=allow_dataset_tools,
            )
            self._trace(
                trace_id,
                "agent_run_start",
                thread_id=clean_thread_id,
                history_messages=len(memory.messages),
                allow_dataset_tools=context.allow_dataset_tools,
            )
            result = await self._run_agent(
                message=self._build_run_input(message=clean_message, memory=memory),
                context=context,
                trace_id=trace_id,
                thread_id=clean_thread_id,
            )
            outcome = _coerce_tool_outcome(getattr(result, "final_output", None))
            if outcome is None:
                raise AgentChatError("No he podido estructurar la salida del agente.")

            evidence = _dedupe_jsonable(context.evidence + list(outcome.evidence or []))
            offers = [offer for offer in (_coerce_live_offer(item) for item in outcome.offers) if offer is not None]
            suggestions = _dedupe_strings(list(outcome.suggestions or []))
            if not suggestions:
                suggestions = self._default_suggestions(message=clean_message, offers=offers, evidence=evidence)

            answer = outcome.answer.strip() if outcome.answer else ""
            if not answer and offers:
                answer = _synthesize_offer_answer(offers)
            if not answer:
                answer = "No tengo una respuesta util para esa consulta."

            status = _normalize_status(outcome.status)
            if status != "failed":
                self._remember_thread_turn(
                    thread_id=clean_thread_id,
                    message=clean_message,
                    answer=answer,
                )
            response = AgentChatResponse(
                trace_id=trace_id,
                thread_id=clean_thread_id,
                status=status,
                answer=answer,
                evidence=evidence,
                offers=offers,
                suggestions=suggestions,
            )
            self._trace(
                trace_id,
                "chat_end",
                status=response.status,
                evidence_count=len(response.evidence),
                offer_count=len(response.offers),
                suggestion_count=len(response.suggestions),
            )
            finish_agent_trace(
                trace_id=trace_id,
                status=response.status,
                answer=response.answer,
                error=response.answer if response.status == "failed" else None,
            )
            return response
        except Exception as exc:  # noqa: BLE001
            error_text = str(exc) or "Error interno del agente."
            self._trace(trace_id, "chat_error", error=error_text, error_type=type(exc).__name__)
            finish_agent_trace(trace_id=trace_id, status="failed", answer=error_text, error=error_text)
            return AgentChatResponse(
                trace_id=trace_id,
                thread_id=clean_thread_id,
                status="failed",
                answer=error_text,
                evidence=[],
                offers=[],
                suggestions=[],
            )
