import { useEffect, useRef, type KeyboardEvent } from "react";
import { Bot, ChevronDown, ExternalLink, LoaderCircle, MessageSquare, RefreshCw, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Textarea } from "@/components/ui/textarea";
import { buildApiUrl, toCurrency } from "@/lib/observatorio-api";

import { useAgentConsole, type ChatMessage } from "./AgentConsoleContext";

function formatModality(modality: string): string {
  const labels: Record<string, string> = {
    cash: "cash",
    financing: "financiacion",
    renting_no_insurance: "renting sin seguro",
    renting_with_insurance: "renting con seguro",
  };
  return labels[modality] ?? modality.replaceAll("_", " ");
}

function formatOfferPrice(value: number | null, currency: string): string {
  if (value === null) {
    return "sin precio";
  }
  return `${value.toFixed(2)} ${currency || "EUR"}`;
}

function statusLabel(status?: string): string | null {
  if (!status || status === "completed") {
    return null;
  }
  if (status === "needs_clarification") {
    return "necesita aclaracion";
  }
  if (status === "failed") {
    return "error";
  }
  return status;
}

function isNearBottom(element: HTMLDivElement | null): boolean {
  if (!element) return true;
  return element.scrollHeight - element.scrollTop - element.clientHeight < 96;
}

function renderMessageParagraphs(message: ChatMessage) {
  return message.text.split("\n").map((line, index) => {
    const pieces = line.split(/(\*\*.*?\*\*)/g);
    return (
      <p key={`${message.id}-${index}`} className={line === "" ? "mt-2" : ""}>
        {pieces.map((piece, pieceIndex) => {
          const isStrong = piece.startsWith("**") && piece.endsWith("**") && piece.length >= 4;
          if (isStrong) {
            return <strong key={`${message.id}-${index}-${pieceIndex}`}>{piece.slice(2, -2)}</strong>;
          }
          return <span key={`${message.id}-${index}-${pieceIndex}`}>{piece}</span>;
        })}
      </p>
    );
  });
}

function renderEvidenceSummary(evidence: Record<string, unknown>): string[] {
  const lines: string[] = [];
  if (typeof evidence.competidor === "string" && evidence.competidor) {
    lines.push(`Retailer: ${evidence.competidor}`);
  }
  if (typeof evidence.modelo === "string" && evidence.modelo) {
    const capacity =
      typeof evidence.capacidad === "number" && Number.isFinite(evidence.capacidad)
        ? ` ${evidence.capacidad}GB`
        : "";
    lines.push(`Producto: ${evidence.modelo}${capacity}`);
  }
  if (typeof evidence.modalidad === "string" && evidence.modalidad) {
    lines.push(`Modalidad: ${formatModality(evidence.modalidad)}`);
  }
  if (typeof evidence.precio_valor === "number") {
    lines.push(`Precio: ${toCurrency(evidence.precio_valor)}`);
  }
  if (typeof evidence.timestamp_extraccion === "string" && evidence.timestamp_extraccion) {
    lines.push(`Capturado: ${evidence.timestamp_extraccion}`);
  }
  return lines;
}

interface AgentConsoleProps {
  variant?: "page" | "panel";
  contextLabel?: string;
}

export default function AgentConsole({ variant = "page" }: AgentConsoleProps) {
  const {
    messages,
    input,
    setInput,
    isLoading,
    activity,
    handleSend,
    startNewConversation,
  } = useAgentConsole();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const shouldStickToBottomRef = useRef(true);
  const isPanel = variant === "panel";

  useEffect(() => {
    if (!shouldStickToBottomRef.current) {
      return;
    }
    window.requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: messages.length > 0 ? "smooth" : "auto" });
    });
  }, [messages, isLoading, activity]);

  function handleMessagesScroll() {
    shouldStickToBottomRef.current = isNearBottom(messagesContainerRef.current);
  }

  function onSubmit() {
    shouldStickToBottomRef.current = true;
    void handleSend();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  }

  const shellClass = isPanel
    ? "mx-auto flex h-[min(72vh,760px)] w-full max-w-4xl flex-col overflow-hidden rounded-[1.25rem] border border-border bg-white shadow-sm"
    : "mx-auto flex min-h-[calc(100vh-6rem)] w-full max-w-4xl flex-col overflow-hidden rounded-[1.25rem] border border-border bg-white shadow-sm";

  return (
    <section className={shellClass}>
      <div className="flex items-center justify-between border-b border-border px-4 py-3 sm:px-5">
        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
          <Bot className="h-4 w-4 text-muted-foreground" />
          Agente
        </div>

        <Button type="button" variant="ghost" onClick={startNewConversation} disabled={isLoading} className="h-8 px-3 text-xs text-muted-foreground">
          <RefreshCw className="h-3.5 w-3.5" />
          Nueva conversación
        </Button>
      </div>

      <div
        ref={messagesContainerRef}
        onScroll={handleMessagesScroll}
        className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6"
      >
        {messages.length === 0 ? (
          <div className="mx-auto flex max-w-2xl flex-1 items-center justify-center py-16">
            <div className="w-full max-w-xl text-center">
              <p className="text-base font-medium text-foreground">Pregunta por un producto, un benchmark o una estrategia de pricing.</p>
              <p className="mt-2 text-sm leading-7 text-muted-foreground">
                El agente puede buscar precios web, contrastarlos con el current y aterrizar una recomendación para Santander.
              </p>
            </div>
          </div>
        ) : null}

        <div className={`mx-auto max-w-3xl space-y-8 ${messages.length === 0 ? "mt-10" : ""}`}>
          {messages.map((message) => {
            const label = statusLabel(message.status);
            return (
              <div key={message.id} className={`flex gap-4 ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                {message.role === "assistant" ? (
                  <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-white text-muted-foreground">
                    <Bot className="h-4 w-4" />
                  </div>
                ) : null}

                <div
                  className={`max-w-[90%] text-sm leading-7 sm:max-w-2xl ${
                    message.role === "user"
                      ? "rounded-2xl bg-slate-100 px-4 py-3 text-foreground"
                      : "px-0 py-0 text-foreground"
                  }`}
                >
                  {renderMessageParagraphs(message)}

                  {label ? (
                    <span
                      className={`mt-3 inline-flex rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] ${
                        message.status === "needs_clarification"
                          ? "bg-amber-100 text-amber-800"
                          : "bg-red-100 text-red-700"
                      }`}
                    >
                      {label}
                    </span>
                  ) : null}

                  {message.traceId ? (
                    <a
                      href={buildApiUrl(`/intelligence/agent/traces/${message.traceId}`)}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-3 inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                    >
                      ver traza {message.traceId.slice(0, 8)}
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  ) : null}

                  {message.evidence && message.evidence.length > 0 ? (
                    <Collapsible className="mt-4 rounded-xl border border-border bg-white">
                      <CollapsibleTrigger asChild>
                        <button
                          type="button"
                          className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-medium text-muted-foreground"
                        >
                          Evidencia current
                          <ChevronDown className="h-4 w-4" />
                        </button>
                      </CollapsibleTrigger>
                      <CollapsibleContent className="space-y-2 border-t border-border px-3 py-3">
                        {message.evidence.map((item, index) => {
                          const summary = renderEvidenceSummary(item);
                          return (
                            <div key={`${message.id}-evidence-${index}`} className="rounded-lg bg-slate-50 px-3 py-2">
                              <div className="space-y-1 text-xs text-muted-foreground">
                                {summary.map((line) => (
                                  <p key={line}>{line}</p>
                                ))}
                                {typeof item.url_producto === "string" && item.url_producto ? (
                                  <a
                                    href={item.url_producto}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="inline-flex items-center gap-1 text-foreground underline-offset-4 hover:underline"
                                  >
                                    Abrir fuente
                                    <ExternalLink className="h-3.5 w-3.5" />
                                  </a>
                                ) : null}
                              </div>
                            </div>
                          );
                        })}
                      </CollapsibleContent>
                    </Collapsible>
                  ) : null}

                  {message.offers && message.offers.length > 0 ? (
                    <Collapsible className="mt-4 rounded-xl border border-border bg-white">
                      <CollapsibleTrigger asChild>
                        <button
                          type="button"
                          className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-medium text-muted-foreground"
                        >
                          Ofertas encontradas
                          <ChevronDown className="h-4 w-4" />
                        </button>
                      </CollapsibleTrigger>
                      <CollapsibleContent className="space-y-2 border-t border-border px-3 py-3">
                        {message.offers.map((offer) => (
                          <div key={`${message.id}-${offer.source_url}-${offer.modality}`} className="rounded-lg bg-slate-50 px-3 py-3">
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="text-sm font-medium text-foreground">{offer.retailer}</p>
                                <p className="mt-1 text-xs text-muted-foreground">{offer.matched_title}</p>
                              </div>
                              <p className="text-sm font-medium text-foreground">
                                {formatOfferPrice(offer.price_value, offer.currency)}
                              </p>
                            </div>

                            <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                              <span>{formatModality(offer.modality)}</span>
                              {offer.capacity_gb ? <span>{offer.capacity_gb}GB</span> : null}
                              <span>confianza {(offer.confidence * 100).toFixed(0)}%</span>
                            </div>

                            <a
                              href={offer.source_url}
                              target="_blank"
                              rel="noreferrer"
                              className="mt-3 inline-flex items-center gap-1 text-xs text-foreground underline-offset-4 hover:underline"
                            >
                              Abrir oferta
                              <ExternalLink className="h-3.5 w-3.5" />
                            </a>
                          </div>
                        ))}
                      </CollapsibleContent>
                    </Collapsible>
                  ) : null}
                </div>

                {message.role === "user" ? (
                  <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500">
                    <MessageSquare className="h-4 w-4" />
                  </div>
                ) : null}
              </div>
            );
          })}

          {isLoading ? (
            <div className="flex gap-4">
              <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-white text-muted-foreground">
                <Bot className="h-4 w-4" />
              </div>

              <div className="max-w-2xl">
                <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                  <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                  {activity?.steps[activity.activeStep]?.label ?? "Procesando"}
                </div>
                <p className="mt-2 text-sm leading-7 text-muted-foreground">
                  {activity?.steps[activity.activeStep]?.detail ?? "Preparando respuesta."}
                </p>
              </div>
            </div>
          ) : null}

          <div ref={messagesEndRef} />
        </div>
      </div>

      <div className="border-t border-border bg-white px-4 py-4 sm:px-6">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit();
          }}
          className="mx-auto max-w-3xl"
        >
          <div className="rounded-[1.5rem] border border-border bg-white px-4 py-3 shadow-sm">
            <Textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Escribe tu mensaje..."
              className="min-h-[96px] resize-none border-0 bg-transparent p-0 shadow-none focus-visible:ring-0"
              disabled={isLoading}
            />

            <div className="mt-3 flex items-center justify-between gap-3">
              <p className="text-xs text-muted-foreground">Enter envía. Shift + Enter añade una línea.</p>

              <Button type="submit" disabled={isLoading || !input.trim()} className="rounded-full px-4">
                <Send className="h-4 w-4" />
                Enviar
              </Button>
            </div>
          </div>
        </form>
      </div>
    </section>
  );
}
