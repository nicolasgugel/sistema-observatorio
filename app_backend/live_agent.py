from __future__ import annotations

import asyncio
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from app_backend.config import (
    LIVE_AGENT_MAX_PRODUCTS,
    LIVE_AGENT_MODEL,
    LIVE_AGENT_SUPPORTED_RETAILERS,
    OPENAI_API_KEY,
    SCRAPLING_MCP_ARGS,
    SCRAPLING_MCP_CLIENT_SESSION_TIMEOUT_SECONDS,
    SCRAPLING_MCP_COMMAND,
)
from app_backend.persistence import now_iso
from observatorio.text_utils import detect_capacity_gb, normalize_text, strip_html_tags

_BOUTIQUE_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0",
}
_BOUTIQUE_API_BASE = "https://api-boutique.bancosantander.es/rest/v2/mktBoutique"
_BOUTIQUE_WEB_BASE = "https://boutique.bancosantander.es"
_BOUTIQUE_COMMON_PARAMS = "lang=es&curr=EUR&region=es-pn&channel=Web"
_SUPPORTED_RETAILERS = tuple(LIVE_AGENT_SUPPORTED_RETAILERS)
_SCRAPLING_TOOL_TIMEOUT_MS = 30_000
_SCRAPLING_PREVIEW_MAX_CHARS = 12_000
_SCRAPLING_PREVIEW_MAX_LINES = 120


class LiveAgentError(RuntimeError):
    pass


class LiveAgentConfigurationError(LiveAgentError):
    pass


class LiveRetailerSuggestion(BaseModel):
    title: str
    source_url: str
    capacity_gb: int | None = None


class ExtractedProduct(BaseModel):
    query_text: str
    brand: str
    model: str
    capacity_gb: int | None = None
    quantity: int = 1


class QueryExtractionResult(BaseModel):
    products: list[ExtractedProduct] = Field(default_factory=list)


class LiveAgentOffer(BaseModel):
    product_key: str = ""
    retailer: str
    modality: str = "cash"
    price_value: float | None = None
    currency: str = "EUR"
    availability: bool | None = None
    matched_title: str
    capacity_gb: int | None = None
    source_url: str
    confidence: float = 0.0
    extracted_at: str = Field(default_factory=now_iso)
    brand: str = ""
    model: str = ""


class RetailerSearchResult(BaseModel):
    offers: list[LiveAgentOffer] = Field(default_factory=list)
    suggestions: list[LiveRetailerSuggestion] = Field(default_factory=list)
    notes: str = ""


class LiveAgentProduct(BaseModel):
    query_text: str
    brand: str
    model: str
    capacity_gb: int | None = None
    status: str
    suggestions: list[str] = Field(default_factory=list)


class LiveAgentResponse(BaseModel):
    status: str
    answer: str
    offers: list[LiveAgentOffer] = Field(default_factory=list)
    products: list[LiveAgentProduct] = Field(default_factory=list)
    partial: bool = False
    job_id: str | None = None
    error: str | None = None
    suggestions: list[str] = Field(default_factory=list)
    poll_url: str | None = None


class PreparedLiveQuery(BaseModel):
    question: str
    retailers: list[str]
    products: list[ExtractedProduct]
    requested_modalities: list[str] = Field(default_factory=list)
    clarification_response: LiveAgentResponse | None = None


class _RetailerProfile(BaseModel):
    retailer: str
    search_urls: list[str]
    guidance: str


class _ModalityInterpretation(BaseModel):
    modalities: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    options: list[str] = Field(default_factory=list)


def _import_agents_sdk() -> tuple[Any, Any, Any, Any, Any]:
    try:
        from agents import Agent, Runner, function_tool
        from agents.mcp import MCPServerStdio, create_static_tool_filter
    except ImportError as exc:
        raise LiveAgentConfigurationError(
            "openai-agents no esta instalado. Ejecuta `python -m pip install openai-agents`."
        ) from exc
    return Agent, Runner, MCPServerStdio, create_static_tool_filter, function_tool


def _ensure_live_runtime_ready() -> None:
    if not OPENAI_API_KEY:
        raise LiveAgentConfigurationError("OPENAI_API_KEY no esta configurada en el backend.")
    if shutil.which(SCRAPLING_MCP_COMMAND) is None:
        raise LiveAgentConfigurationError(
            f"No encuentro `{SCRAPLING_MCP_COMMAND}` en PATH para lanzar Scrapling MCP."
        )


def _tokenize(value: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9]+", " ", normalize_text(value))
    return {token for token in cleaned.split() if token}


def build_product_key(brand: str, model: str, capacity_gb: int | None) -> str:
    cap = str(capacity_gb) if capacity_gb is not None else "na"
    return f"{normalize_text(brand)}|{normalize_text(model)}|{cap}"


def _canonical_model_title(title: str, brand: str) -> str:
    cleaned = strip_html_tags(title or "")
    cleaned = re.sub(r"\b\d+\s*(gb|tb)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -/,")
    if brand and not normalize_text(cleaned).startswith(normalize_text(brand)):
        return f"{brand} {cleaned}".strip()
    return cleaned


def _normalize_brand(value: str) -> str:
    return normalize_text(value)


def _dedupe_brand_prefix(brand: str, model: str) -> str:
    brand_n = normalize_text(brand)
    model_n = normalize_text(model)
    if brand_n and model_n.startswith(brand_n + " "):
        return model[len(brand) :].strip() or model.strip()
    return model.strip()


def _score_offer_match(product: ExtractedProduct, offer: LiveAgentOffer, *, require_capacity: bool) -> int:
    product_brand = _normalize_brand(product.brand)
    offer_brand = _normalize_brand(offer.brand or offer.matched_title)
    product_tokens = _tokenize(product.model)
    offer_tokens = _tokenize(" ".join(filter(None, [offer.model, offer.matched_title])))

    if not product_tokens or not offer_tokens:
        return 0

    overlap = len(product_tokens.intersection(offer_tokens))
    score = int((overlap / max(len(product_tokens), 1)) * 70)

    if product_brand and product_brand == offer_brand:
        score += 20
    elif product_brand and product_brand not in offer_brand:
        score -= 25

    if product.capacity_gb is not None:
        if offer.capacity_gb == product.capacity_gb:
            score += 20
        elif require_capacity:
            score -= 35

    if isinstance(offer.price_value, (int, float)) and offer.price_value > 0:
        score += 5

    return max(min(score, 100), 0)


def is_exact_offer_match(product: ExtractedProduct, offer: LiveAgentOffer) -> bool:
    if product.capacity_gb is not None and offer.capacity_gb != product.capacity_gb:
        return False
    return _score_offer_match(product, offer, require_capacity=True) >= 85


def rank_offer_suggestions(product: ExtractedProduct, offers: Iterable[LiveAgentOffer]) -> list[LiveAgentOffer]:
    unique: dict[tuple[str, int | None, str], LiveAgentOffer] = {}
    for offer in offers:
        key = (offer.matched_title, offer.capacity_gb, offer.retailer)
        existing = unique.get(key)
        if existing is None or (offer.confidence > existing.confidence):
            unique[key] = offer

    ranked = sorted(
        unique.values(),
        key=lambda offer: (
            _score_offer_match(product, offer, require_capacity=False),
            offer.confidence,
            -(offer.price_value or 0.0),
        ),
        reverse=True,
    )
    return ranked[:3]


def build_product_outcome(
    product: ExtractedProduct,
    offers: list[LiveAgentOffer],
    suggestions: list[str],
) -> tuple[LiveAgentProduct, list[LiveAgentOffer]]:
    product_key = build_product_key(product.brand, product.model, product.capacity_gb)
    normalized_offers = _dedupe_offers([offer.model_copy(update={"product_key": product_key}) for offer in offers])

    if product.capacity_gb is not None:
        exact_offers = [offer for offer in normalized_offers if is_exact_offer_match(product, offer)]
        if exact_offers:
            return (
                LiveAgentProduct(
                    query_text=product.query_text,
                    brand=product.brand,
                    model=product.model,
                    capacity_gb=product.capacity_gb,
                    status="completed",
                    suggestions=[],
                ),
                sorted(exact_offers, key=lambda offer: (offer.price_value is None, offer.price_value or 0.0)),
            )

        ranked = rank_offer_suggestions(product, normalized_offers)
        return (
            LiveAgentProduct(
                query_text=product.query_text,
                brand=product.brand,
                model=product.model,
                capacity_gb=product.capacity_gb,
                status="needs_clarification" if ranked or suggestions else "not_found",
                suggestions=[*suggestions, *[_offer_label(offer) for offer in ranked]][:3],
            ),
            [],
        )

    candidate_offers = [offer for offer in normalized_offers if _score_offer_match(product, offer, require_capacity=False) >= 85]
    capacities = sorted({offer.capacity_gb for offer in candidate_offers if offer.capacity_gb is not None})
    if len(capacities) > 1:
        return (
            LiveAgentProduct(
                query_text=product.query_text,
                brand=product.brand,
                model=product.model,
                capacity_gb=None,
                status="needs_clarification",
                suggestions=[
                    f"{product.brand} {product.model} {capacity}GB".strip()
                    for capacity in capacities[:3]
                ],
            ),
            [],
        )

    if candidate_offers:
        return (
            LiveAgentProduct(
                query_text=product.query_text,
                brand=product.brand,
                model=product.model,
                capacity_gb=candidate_offers[0].capacity_gb,
                status="completed",
                suggestions=[],
            ),
            sorted(candidate_offers, key=lambda offer: (offer.price_value is None, offer.price_value or 0.0)),
        )

    ranked = rank_offer_suggestions(product, normalized_offers)
    return (
        LiveAgentProduct(
            query_text=product.query_text,
            brand=product.brand,
            model=product.model,
            capacity_gb=None,
            status="needs_clarification" if ranked or suggestions else "not_found",
            suggestions=[*suggestions, *[_offer_label(offer) for offer in ranked]][:3],
        ),
        [],
    )


def sanitize_live_retailers(retailers: list[str] | None) -> list[str]:
    if not retailers:
        return list(_SUPPORTED_RETAILERS)

    supported_lookup = {normalize_text(retailer): retailer for retailer in _SUPPORTED_RETAILERS}
    resolved: list[str] = []
    for retailer in retailers:
        key = normalize_text(retailer)
        value = supported_lookup.get(key)
        if value and value not in resolved:
            resolved.append(value)
    return resolved or list(_SUPPORTED_RETAILERS)


def _offer_label(offer: LiveAgentOffer) -> str:
    title = offer.matched_title or offer.model
    capacity = f" {offer.capacity_gb}GB" if offer.capacity_gb else ""
    return f"{title}{capacity} en {offer.retailer}".strip()


def _modality_label(modality: str) -> str:
    labels = {
        "cash": "cash",
        "financing": "financiacion",
        "renting_no_insurance": "renting sin seguro",
        "renting_with_insurance": "renting con seguro",
    }
    return labels.get(modality, modality.replace("_", " "))


def _unique_preserving_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        key = normalize_text(cleaned)
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _question_mentions_any(question: str, phrases: Iterable[str]) -> bool:
    normalized_question = normalize_text(question)
    return any(normalize_text(phrase) in normalized_question for phrase in phrases)


def _question_allows_any_capacity(question: str) -> bool:
    return _question_mentions_any(
        question,
        [
            "cualquier capacidad",
            "sin importar capacidad",
            "me da igual la capacidad",
            "cualquier almacenamiento",
            "sin importar almacenamiento",
        ],
    )


def _question_allows_any_modality(question: str) -> bool:
    return _question_mentions_any(
        question,
        [
            "cualquier modalidad",
            "sin importar modalidad",
            "me da igual la modalidad",
            "todas las modalidades",
        ],
    )


def _product_likely_has_capacity_variants(product: ExtractedProduct) -> bool:
    normalized = normalize_text(f"{product.brand} {product.model}")
    negative_keywords = [
        "watch",
        "buds",
        "airpods",
        "earbuds",
        "funda",
        "cable",
        "charger",
        "cargador",
        "protector",
        "cover",
        "case",
    ]
    if any(keyword in normalized for keyword in negative_keywords):
        return False

    positive_keywords = [
        "iphone",
        "galaxy",
        "pixel",
        "ipad",
        "tablet",
        "xiaomi",
        "redmi",
        "honor",
        "oneplus",
        "oppo",
        "realme",
        "motorola",
        "poco",
    ]
    return any(keyword in normalized for keyword in positive_keywords)


def _capacity_suggestions_for_product(product: ExtractedProduct) -> list[str]:
    base = [128, 256, 512]
    if _question_mentions_any(product.model, ["ultra", "pro max"]):
        base.append(1024)
    return [f"{product.brand} {product.model} {capacity}GB".strip() for capacity in base]


def _interpret_requested_modalities(question: str, retailers: list[str]) -> _ModalityInterpretation:
    if "Santander Boutique" not in retailers or _question_allows_any_modality(question):
        return _ModalityInterpretation()

    normalized = normalize_text(question)
    modalities: list[str] = []

    if _question_mentions_any(question, ["cash", "contado", "pago unico", "precio total"]):
        modalities.append("cash")
    if _question_mentions_any(question, ["financiacion", "financiado", "financiar", "cuotas", "aplazado"]):
        modalities.append("financing")

    mentions_renting = _question_mentions_any(question, ["renting", "alquiler"])
    mentions_with_insurance = _question_mentions_any(question, ["con seguro", "incluye seguro"])
    mentions_without_insurance = _question_mentions_any(question, ["sin seguro"])

    if mentions_with_insurance:
        modalities.append("renting_with_insurance")
    if mentions_without_insurance:
        modalities.append("renting_no_insurance")

    unique_modalities = _unique_preserving_order(modalities)
    if mentions_renting and not mentions_with_insurance and not mentions_without_insurance:
        return _ModalityInterpretation(
            modalities=unique_modalities,
            needs_clarification=True,
            options=["renting sin seguro", "renting con seguro"],
        )

    if unique_modalities:
        return _ModalityInterpretation(modalities=unique_modalities)

    return _ModalityInterpretation(
        needs_clarification=True,
        options=["cash", "financiacion", "renting sin seguro", "renting con seguro"],
    )


def _filter_offers_by_requested_modalities(
    offers: list[LiveAgentOffer],
    requested_modalities: list[str],
) -> list[LiveAgentOffer]:
    if not requested_modalities:
        return offers
    allowed = set(requested_modalities)
    return [offer for offer in offers if offer.modality in allowed]


def _dedupe_offers(offers: list[LiveAgentOffer]) -> list[LiveAgentOffer]:
    unique: dict[tuple[str, str, str, int | None, float, str], LiveAgentOffer] = {}
    for offer in offers:
        key = (
            offer.retailer,
            offer.modality,
            normalize_text(offer.matched_title or offer.model),
            offer.capacity_gb,
            round(float(offer.price_value or 0.0), 2),
            offer.source_url,
        )
        existing = unique.get(key)
        if existing is None or offer.confidence > existing.confidence:
            unique[key] = offer
    return list(unique.values())


def _build_preflight_clarification(
    *,
    question: str,
    retailers: list[str],
    products: list[ExtractedProduct],
    modality_interpretation: _ModalityInterpretation,
) -> LiveAgentResponse | None:
    product_lines: list[str] = []
    product_states: list[LiveAgentProduct] = []
    all_suggestions: list[str] = []

    for product in products:
        missing_parts: list[str] = []
        suggestions: list[str] = []

        if product.capacity_gb is None and _product_likely_has_capacity_variants(product) and not _question_allows_any_capacity(question):
            missing_parts.append("capacidad")
            suggestions.extend(_capacity_suggestions_for_product(product))

        if modality_interpretation.needs_clarification and "Santander Boutique" in retailers:
            missing_parts.append("modalidad en Santander Boutique")
            suggestions.extend(modality_interpretation.options)

        deduped_suggestions = _unique_preserving_order(suggestions)
        if not missing_parts:
            continue

        product_states.append(
            LiveAgentProduct(
                query_text=product.query_text,
                brand=product.brand,
                model=product.model,
                capacity_gb=product.capacity_gb,
                status="needs_clarification",
                suggestions=deduped_suggestions[:6],
            )
        )
        product_lines.append(
            f"- {product.brand} {product.model}: antes de buscar necesito confirmar "
            f"{' y '.join(missing_parts)}. Opciones: {', '.join(deduped_suggestions[:6])}."
        )
        all_suggestions.extend(deduped_suggestions[:6])

    if not product_lines:
        return None

    return LiveAgentResponse(
        status="needs_clarification",
        answer="Antes de lanzar el scraping necesito concretar la busqueda:\n" + "\n".join(product_lines),
        products=product_states,
        partial=False,
        suggestions=_unique_preserving_order(all_suggestions)[:10],
    )


def _scrapling_query_terms(product: ExtractedProduct) -> set[str]:
    terms = {token for token in _tokenize(f"{product.brand} {product.model}") if len(token) >= 2}
    if product.capacity_gb is not None:
        terms.add(str(product.capacity_gb))
        terms.add(f"{product.capacity_gb}gb")
    return terms


def _compact_scrapling_content(raw: str, product: ExtractedProduct) -> str:
    cleaned = raw.replace("\r\n", "\n").replace("\r", "\n")
    if len(cleaned) <= _SCRAPLING_PREVIEW_MAX_CHARS:
        return cleaned.strip()

    query_terms = _scrapling_query_terms(product)
    scored_lines: list[tuple[int, int, str]] = []
    for index, line in enumerate(cleaned.split("\n")):
        compact = re.sub(r"\s+", " ", line).strip()
        if not compact:
            continue

        normalized_line = normalize_text(compact)
        token_hits = sum(1 for term in query_terms if term in normalized_line)
        has_link = "http://" in compact or "https://" in compact or "](" in compact or "/dp/" in compact
        has_price = bool(
            re.search(r"(?:\d[\d.,]{1,10}\s?(?:€|eur))|(?:€\s?\d)", compact, flags=re.IGNORECASE)
        )
        has_capacity = bool(re.search(r"\b\d+\s?(?:gb|tb)\b", normalized_line, flags=re.IGNORECASE))

        score = (token_hits * 3) + (3 if has_price else 0) + (2 if has_link else 0) + (1 if has_capacity else 0)
        if score <= 0:
            continue

        scored_lines.append((score, index, compact))

    if not scored_lines:
        return cleaned[:_SCRAPLING_PREVIEW_MAX_CHARS].strip()

    selected = sorted(scored_lines, key=lambda item: (item[0], -item[1]), reverse=True)[:_SCRAPLING_PREVIEW_MAX_LINES]
    ordered_lines = [line for _, _, line in sorted(selected, key=lambda item: item[1])]

    compacted: list[str] = []
    remaining_chars = _SCRAPLING_PREVIEW_MAX_CHARS
    seen_lines: set[str] = set()
    for line in ordered_lines:
        normalized_key = normalize_text(line)[:240]
        if normalized_key in seen_lines:
            continue
        seen_lines.add(normalized_key)

        snippet = line[:remaining_chars].strip()
        if not snippet:
            continue
        compacted.append(snippet)
        remaining_chars -= len(snippet) + 1
        if remaining_chars <= 0:
            break

    return "\n".join(compacted).strip() or cleaned[:_SCRAPLING_PREVIEW_MAX_CHARS].strip()


def build_live_answer(products: list[LiveAgentProduct], offers: list[LiveAgentOffer], retailers: list[str]) -> tuple[str, list[str], str]:
    product_lines: list[str] = []
    all_suggestions: list[str] = []
    overall_status = "completed"

    for product in products:
        expected_product_key = build_product_key(product.brand, product.model, product.capacity_gb)
        product_offers = [
            offer
            for offer in offers
            if offer.product_key == expected_product_key
        ]
        if product.status == "completed":
            cash_offers = [offer for offer in product_offers if offer.modality == "cash" and offer.price_value is not None]
            reference_offers = cash_offers or [offer for offer in product_offers if offer.price_value is not None]
            if reference_offers:
                best_offer = min(reference_offers, key=lambda offer: offer.price_value or float("inf"))
                product_lines.append(
                    f"- {product.brand} {product.model}"
                    f"{f' {product.capacity_gb}GB' if product.capacity_gb else ''}: "
                    f"mejor precio {best_offer.price_value:.2f} {best_offer.currency} en {best_offer.retailer}."
                )
        elif product.status == "needs_clarification":
            overall_status = "needs_clarification"
            all_suggestions.extend(product.suggestions)
            joined = ", ".join(product.suggestions[:3]) if product.suggestions else "sin sugerencias claras"
            product_lines.append(
                f"- {product.brand} {product.model}: necesito confirmar la variante exacta. Opciones: {joined}."
            )
        else:
            overall_status = "needs_clarification"
            product_lines.append(f"- {product.brand} {product.model}: no encontre un match fiable.")

    resolved_retailers = {offer.retailer for offer in offers}
    missing_retailers = [retailer for retailer in retailers if retailer not in resolved_retailers]
    if missing_retailers and offers:
        product_lines.append("Retailers sin match: " + ", ".join(missing_retailers) + ".")

    if not product_lines:
        return (
            "No he podido obtener precios fiables para esa consulta.",
            all_suggestions[:6],
            "needs_clarification",
        )

    return ("\n".join(product_lines), all_suggestions[:6], overall_status)


def build_cache_key(prepared_query: PreparedLiveQuery) -> str:
    product_parts = [
        build_product_key(product.brand, product.model, product.capacity_gb)
        for product in prepared_query.products
    ]
    retailers = ",".join(normalize_text(retailer) for retailer in prepared_query.retailers)
    modalities = ",".join(sorted(prepared_query.requested_modalities)) or "all_modalities"
    return "::".join([retailers, modalities, *product_parts])


class LiveAgentService:
    async def prepare_query(
        self,
        *,
        question: str,
        retailers: list[str] | None = None,
    ) -> PreparedLiveQuery:
        products = await self.extract_products(question)
        resolved_retailers = sanitize_live_retailers(retailers)
        modality_interpretation = _interpret_requested_modalities(question, resolved_retailers)
        clarification_response = _build_preflight_clarification(
            question=question,
            retailers=resolved_retailers,
            products=products,
            modality_interpretation=modality_interpretation,
        )
        return PreparedLiveQuery(
            question=question.strip(),
            retailers=resolved_retailers,
            products=products,
            requested_modalities=modality_interpretation.modalities,
            clarification_response=clarification_response,
        )

    async def extract_products(self, question: str) -> list[ExtractedProduct]:
        _ensure_live_runtime_ready()
        Agent, Runner, _, _, _ = _import_agents_sdk()

        extractor = Agent(
            name="Product extractor",
            model=LIVE_AGENT_MODEL,
            instructions=(
                "Extract up to three consumer tech products from the user request. "
                "Return only products that the user is explicitly asking to price-check. "
                "Infer the brand only when the model makes it obvious, for example Galaxy -> Samsung, iPhone -> Apple. "
                "Keep the model concise but commercially recognizable. "
                "If capacity is not explicitly present, leave capacity_gb null."
            ),
            output_type=QueryExtractionResult,
        )
        result = await Runner.run(extractor, question)
        payload = result.final_output
        if not isinstance(payload, QueryExtractionResult):
            raise LiveAgentError("No he podido estructurar la consulta del usuario.")

        normalized: list[ExtractedProduct] = []
        seen: set[tuple[str, str, int | None]] = set()
        for item in payload.products[:LIVE_AGENT_MAX_PRODUCTS]:
            brand = strip_html_tags(item.brand).strip()
            model = _dedupe_brand_prefix(brand, strip_html_tags(item.model).strip())
            if not brand or not model:
                continue
            key = (normalize_text(brand), normalize_text(model), item.capacity_gb)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                ExtractedProduct(
                    query_text=item.query_text or f"{brand} {model}".strip(),
                    brand=brand,
                    model=model,
                    capacity_gb=item.capacity_gb,
                    quantity=max(item.quantity, 1),
                )
            )
        if not normalized:
            raise LiveAgentError("No he detectado productos claros en la consulta.")
        return normalized

    async def run_query(
        self,
        prepared_query: PreparedLiveQuery,
        *,
        progress_callback: Callable[[LiveAgentResponse], Any] | None = None,
    ) -> LiveAgentResponse:
        offers: list[LiveAgentOffer] = []
        products_outcome: list[LiveAgentProduct] = []
        suggestions_by_product: dict[str, list[str]] = {}

        _, _, MCPServerStdio, create_static_tool_filter, _ = _import_agents_sdk()
        server_params = {
            "command": SCRAPLING_MCP_COMMAND,
            "args": SCRAPLING_MCP_ARGS,
        }

        async with MCPServerStdio(
            name="Scrapling MCP",
            params=server_params,
            cache_tools_list=True,
            client_session_timeout_seconds=SCRAPLING_MCP_CLIENT_SESSION_TIMEOUT_SECONDS,
            tool_filter=create_static_tool_filter(allowed_tool_names=["fetch", "stealthy_fetch"]),
            max_retry_attempts=1,
        ) as server:
            for product in prepared_query.products:
                raw_offers: list[LiveAgentOffer] = []
                raw_suggestions: list[str] = []
                for retailer in prepared_query.retailers:
                    if retailer == "Santander Boutique":
                        boutique_offers, boutique_suggestions = await self._search_boutique(product, server=server)
                        raw_offers.extend(boutique_offers)
                        raw_suggestions.extend(boutique_suggestions)
                    else:
                        result = await self._search_retailer_with_agent(product=product, retailer=retailer, server=server)
                        raw_offers.extend(result.offers)
                        raw_suggestions.extend([suggestion.title for suggestion in result.suggestions])

                    filtered_offers = _filter_offers_by_requested_modalities(
                        raw_offers,
                        prepared_query.requested_modalities,
                    )
                    partial_product, partial_offers = build_product_outcome(product, filtered_offers, raw_suggestions)
                    interim_products = [*products_outcome, partial_product]
                    interim_offers = [*offers, *partial_offers]
                    if progress_callback is not None:
                        maybe_result = progress_callback(
                            LiveAgentResponse(
                                status="running",
                                answer="Scraping en curso.",
                                offers=interim_offers,
                                products=interim_products,
                                partial=True,
                                suggestions=raw_suggestions[:6],
                            )
                        )
                        if asyncio.iscoroutine(maybe_result):
                            await maybe_result

                filtered_offers = _filter_offers_by_requested_modalities(
                    raw_offers,
                    prepared_query.requested_modalities,
                )
                product_outcome, accepted_offers = build_product_outcome(product, filtered_offers, raw_suggestions)
                offers.extend(accepted_offers)
                products_outcome.append(product_outcome)
                suggestions_by_product[product_outcome.query_text] = raw_suggestions

        answer, suggestions, status = build_live_answer(products_outcome, offers, prepared_query.retailers)
        return LiveAgentResponse(
            status=status,
            answer=answer,
            offers=offers,
            products=products_outcome,
            partial=False,
            suggestions=suggestions,
        )

    def _tool_result_text(self, result: Any) -> str:
        parts: list[str] = []

        for item in getattr(result, "content", []) or []:
            text = getattr(item, "text", None)
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
                continue
            if isinstance(item, dict):
                dict_text = item.get("text")
                if isinstance(dict_text, str) and dict_text.strip():
                    parts.append(dict_text.strip())

        structured_content = getattr(result, "structuredContent", None)
        if structured_content and not parts:
            if isinstance(structured_content, str):
                parts.append(structured_content)
            else:
                parts.append(json.dumps(structured_content, ensure_ascii=True))

        return "\n".join(parts).strip()

    async def _fetch_tool_preview(
        self,
        *,
        server: Any,
        product: ExtractedProduct,
        tool_name: str,
        url: str,
        css_selector: str | None = None,
    ) -> str:
        arguments: dict[str, Any] = {
            "url": url,
            "extraction_type": "markdown",
            "main_content_only": False,
            "disable_resources": True,
            "timeout": _SCRAPLING_TOOL_TIMEOUT_MS,
        }
        if css_selector:
            arguments["css_selector"] = css_selector

        result = await server.call_tool(tool_name, arguments)
        raw_text = self._tool_result_text(result)
        if not raw_text:
            return f"URL: {url}\nNo content returned by {tool_name}."

        if getattr(result, "isError", False):
            return f"URL: {url}\nFetch error via {tool_name}: {raw_text[:1200]}"

        compacted = _compact_scrapling_content(raw_text, product)
        return f"URL: {url}\n{compacted}".strip()

    async def _search_boutique(self, product: ExtractedProduct, *, server: Any) -> tuple[list[LiveAgentOffer], list[str]]:
        try:
            offers, suggestions = await asyncio.to_thread(self._search_boutique_api_sync, product)
        except Exception:
            offers, suggestions = [], []

        if offers or suggestions:
            return offers, suggestions

        fallback = await self._search_retailer_with_agent(product=product, retailer="Santander Boutique", server=server)
        return fallback.offers, [suggestion.title for suggestion in fallback.suggestions]

    def _search_boutique_api_sync(self, product: ExtractedProduct) -> tuple[list[LiveAgentOffer], list[str]]:
        suggestions: list[str] = []
        candidate_codes: list[str] = []
        seen_codes: set[str] = set()

        for query in self._candidate_queries(product):
            search_url = (
                f"{_BOUTIQUE_API_BASE}/products/search?"
                f"{_BOUTIQUE_COMMON_PARAMS}&fields=FULL&pageSize=6&currentPage=0&query={quote_plus(query)}"
            )
            payload = self._fetch_json(search_url)
            products = payload.get("products") if isinstance(payload, dict) else []
            if not isinstance(products, list):
                continue

            for item in products[:6]:
                title = strip_html_tags(str(item.get("name") or "")).strip()
                code = str(item.get("code") or "").strip()
                if title and title not in suggestions:
                    suggestions.append(title)
                if code and code not in seen_codes:
                    candidate_codes.append(code)
                    seen_codes.add(code)
            if candidate_codes:
                break

        offers: list[LiveAgentOffer] = []
        for code in candidate_codes[:3]:
            detail_url = f"{_BOUTIQUE_API_BASE}/products/{quote_plus(code)}?fields=FULL&{_BOUTIQUE_COMMON_PARAMS}"
            detail = self._fetch_json(detail_url)
            offers.extend(self._extract_boutique_offers(detail, product))

        return offers, suggestions[:3]

    def _fetch_json(self, url: str) -> dict[str, Any]:
        request = Request(url, headers=_BOUTIQUE_HEADERS)
        with urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))

    def _extract_boutique_offers(self, detail: dict[str, Any], product: ExtractedProduct) -> list[LiveAgentOffer]:
        if not isinstance(detail, dict):
            return []

        title = strip_html_tags(str(detail.get("name") or "")).strip()
        categories = " ".join(str(category.get("name") or "") for category in detail.get("categories", []))
        capacity_gb = detect_capacity_gb(title) or detect_capacity_gb(categories) or product.capacity_gb
        source_url = str(detail.get("url") or "")
        if source_url:
            source_url = f"{_BOUTIQUE_WEB_BASE}/es{source_url}"
        in_stock = str(detail.get("stock", {}).get("stockLevelStatus") or "") == "inStock"
        model = _canonical_model_title(title or product.model, product.brand)

        offers: list[LiveAgentOffer] = []
        for group in detail.get("priceGroups", []):
            group_id = str(group.get("groupId") or "").strip()
            prices = sorted(group.get("prices", []), key=lambda item: float(item.get("value") or 0.0))
            if group_id == "creditCard":
                cash_options = [item for item in prices if int(item.get("installments") or 0) == 0]
                if cash_options:
                    offers.append(
                        LiveAgentOffer(
                            retailer="Santander Boutique",
                            modality="cash",
                            price_value=float(cash_options[0].get("value") or 0.0),
                            currency="EUR",
                            availability=in_stock,
                            matched_title=title or product.model,
                            capacity_gb=capacity_gb,
                            source_url=source_url,
                            confidence=1.0,
                            brand=product.brand,
                            model=model,
                        )
                    )
                financing_options = [item for item in prices if int(item.get("installments") or 0) > 0]
                if financing_options:
                    financing = max(financing_options, key=lambda item: int(item.get("installments") or 0))
                    offers.append(
                        LiveAgentOffer(
                            retailer="Santander Boutique",
                            modality="financing",
                            price_value=float(financing.get("value") or 0.0),
                            currency="EUR",
                            availability=in_stock,
                            matched_title=title or product.model,
                            capacity_gb=capacity_gb,
                            source_url=source_url,
                            confidence=1.0,
                            brand=product.brand,
                            model=model,
                        )
                    )
            elif group_id == "renting":
                if prices:
                    offers.append(
                        LiveAgentOffer(
                            retailer="Santander Boutique",
                            modality="renting_no_insurance",
                            price_value=float(prices[0].get("value") or 0.0),
                            currency="EUR",
                            availability=in_stock,
                            matched_title=title or product.model,
                            capacity_gb=capacity_gb,
                            source_url=source_url,
                            confidence=1.0,
                            brand=product.brand,
                            model=model,
                        )
                    )
                if len(prices) > 1:
                    offers.append(
                        LiveAgentOffer(
                            retailer="Santander Boutique",
                            modality="renting_with_insurance",
                            price_value=float(prices[1].get("value") or 0.0),
                            currency="EUR",
                            availability=in_stock,
                            matched_title=title or product.model,
                            capacity_gb=capacity_gb,
                            source_url=source_url,
                            confidence=1.0,
                            brand=product.brand,
                            model=model,
                        )
                    )

        return [offer for offer in offers if isinstance(offer.price_value, (int, float)) and offer.price_value > 0]

    async def _search_retailer_with_agent(self, *, product: ExtractedProduct, retailer: str, server: Any) -> RetailerSearchResult:
        _ensure_live_runtime_ready()
        Agent, Runner, _, _, function_tool = _import_agents_sdk()
        profile = self._retailer_profile(product, retailer)

        @function_tool
        async def fetch_page(url: str, css_selector: str | None = None) -> str:
            """Fetch a retailer page and return a compact preview with relevant titles, prices, and links.

            Args:
                url: The page URL to fetch.
                css_selector: Optional CSS selector to restrict the extraction when the page is noisy.
            """

            return await self._fetch_tool_preview(
                server=server,
                product=product,
                tool_name="fetch",
                url=url,
                css_selector=css_selector,
            )

        @function_tool
        async def stealthy_fetch_page(url: str, css_selector: str | None = None) -> str:
            """Fetch a retailer page with the stealthy Scrapling tool when the normal fetch misses data.

            Args:
                url: The page URL to fetch.
                css_selector: Optional CSS selector to restrict the extraction when the page is noisy.
            """

            return await self._fetch_tool_preview(
                server=server,
                product=product,
                tool_name="stealthy_fetch",
                url=url,
                css_selector=css_selector,
            )

        agent = Agent(
            name=f"{retailer} live search",
            model=LIVE_AGENT_MODEL,
            instructions=(
                "You are a retail price extraction agent. "
                "Use the provided tools to fetch search results and product pages. "
                "Start with fetch_page. Use stealthy_fetch_page only when the normal fetch is blocked or lacks titles, prices or links. "
                "Never invent prices or URLs. "
                "If you cannot verify a product page and a visible price, return no offer. "
                "Return cash modality for competitors. "
                "For Santander Boutique, return financing or renting only when the page makes it explicit. "
                "Use the provided search URLs first and stop after one search page plus at most two product detail pages. "
                "Do not fetch the same URL twice unless you are changing the CSS selector or switching to stealthy mode. "
                "Prefer exact model and capacity matches. "
                "If exact match is not possible, return up to three suggestions."
            ),
            output_type=RetailerSearchResult,
            tools=[fetch_page, stealthy_fetch_page],
        )
        prompt = self._retailer_prompt(product, profile)
        result = await Runner.run(agent, prompt, max_turns=6)
        payload = result.final_output
        if not isinstance(payload, RetailerSearchResult):
            return RetailerSearchResult()

        normalized_offers: list[LiveAgentOffer] = []
        for offer in payload.offers:
            if offer.price_value is None or offer.price_value <= 0:
                continue
            normalized_offers.append(
                offer.model_copy(
                    update={
                        "retailer": retailer,
                        "brand": offer.brand or product.brand,
                        "model": offer.model or _canonical_model_title(offer.matched_title or product.model, product.brand),
                        "confidence": max(min(offer.confidence, 1.0), 0.0),
                        "modality": offer.modality or "cash",
                        "currency": offer.currency or "EUR",
                        "extracted_at": offer.extracted_at or now_iso(),
                    }
                )
            )
        normalized_suggestions = [
            suggestion
            for suggestion in payload.suggestions
            if suggestion.title and suggestion.source_url
        ]
        return RetailerSearchResult(
            offers=normalized_offers,
            suggestions=normalized_suggestions[:3],
            notes=payload.notes,
        )

    def _retailer_profile(self, product: ExtractedProduct, retailer: str) -> _RetailerProfile:
        queries = self._candidate_queries(product)
        if retailer == "Amazon":
            urls = [f"https://www.amazon.es/s?k={quote_plus(query)}" for query in queries[:2]]
            guidance = "Search page results usually include title, price and links to /dp/ pages."
        elif retailer == "Media Markt":
            urls = [f"https://www.mediamarkt.es/es/search.html?query={quote_plus(query)}" for query in queries[:2]]
            guidance = "Search results may be rendered client-side. Use stealthy_fetch if the normal fetch is too sparse."
        elif retailer == "El Corte Ingles":
            urls = [
                f"https://www.elcorteingles.es/search-nwx/?s={quote_plus(query)}&stype=text_box"
                for query in queries[:2]
            ]
            guidance = "El Corte Ingles may show multiple color or capacity variants on the same product page."
        else:
            urls = [
                f"https://boutique.bancosantander.es/es/search/?text={quote_plus(query)}"
                for query in queries[:2]
            ]
            guidance = "Use HTML fallback only if the direct API route was not enough."

        return _RetailerProfile(retailer=retailer, search_urls=urls, guidance=guidance)

    def _retailer_prompt(self, product: ExtractedProduct, profile: _RetailerProfile) -> str:
        capacity_text = f"{product.capacity_gb}GB" if product.capacity_gb is not None else "unspecified capacity"
        urls = "\n".join(f"- {url}" for url in profile.search_urls)
        return (
            f"Target retailer: {profile.retailer}\n"
            f"Target product brand: {product.brand}\n"
            f"Target product model: {product.model}\n"
            f"Target capacity: {capacity_text}\n"
            f"Search URLs:\n{urls}\n"
            f"Retailer notes: {profile.guidance}\n"
            "Return offers only when the product title and capacity are trustworthy. "
            "If capacity is unspecified in the user request, gather variants and suggest them instead of guessing."
        )

    def _candidate_queries(self, product: ExtractedProduct) -> list[str]:
        queries: list[str] = []
        raw_variants = [
            f"{product.brand} {product.model} {product.capacity_gb}GB" if product.capacity_gb else "",
            f"{product.brand} {product.model}",
            f"{product.model} {product.capacity_gb}GB" if product.capacity_gb else "",
            product.model,
        ]
        for candidate in raw_variants:
            cleaned = " ".join(candidate.split()).strip()
            if cleaned and cleaned not in queries:
                queries.append(cleaned)
        return queries
