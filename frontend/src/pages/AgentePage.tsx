import { useEffect, useRef, useState } from "react";
import { Bot, ChevronDown, MessageSquare, Send, Sparkles, TrendingDown, BarChart3 } from "lucide-react";

import { PageHeader } from "@/components/SharedUI";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/collapsible";
import { type AgentEvidence, queryAgent, toCurrency } from "@/lib/observatorio-api";

type BrandTab = "Samsung" | "Apple" | "all";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  evidence?: AgentEvidence[];
  intent?: string;
  isError?: boolean;
}

const SUGGESTIONS = [
  { icon: TrendingDown, text: "¿Cuál es el más barato Galaxy S25 Ultra 256GB?" },
  { icon: BarChart3, text: "¿Qué cobertura tenemos de Samsung?" },
  { icon: Sparkles, text: "Resumen de precios del Galaxy S25" },
];

export default function AgentePage() {
  const [brand, setBrand] = useState<BrandTab>("Samsung");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  async function handleSend(text?: string) {
    const question = (text ?? input).trim();
    if (!question || isLoading) return;

    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: "user", text: question };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await queryAgent(question, brand);
      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        text: response.answer,
        evidence: response.evidence,
        intent: response.intent,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      const errorMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        text: "Error al procesar la consulta. Comprueba que el backend está activo e inténtalo de nuevo.",
        isError: true,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <>
      <PageHeader
        title="Agente IA"
        subtitle="Consultas en lenguaje natural sobre cobertura, gaps y tendencias del observatorio"
        actions={
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Marca:</span>
            <Select value={brand} onValueChange={(v) => setBrand(v as BrandTab)}>
              <SelectTrigger className="w-36 h-9 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Samsung">Samsung</SelectItem>
                <SelectItem value="Apple">Apple</SelectItem>
                <SelectItem value="all">Todas</SelectItem>
              </SelectContent>
            </Select>
          </div>
        }
      />

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_280px] gap-6">
        {/* Chat area */}
        <div className="glass-card rounded-xl flex flex-col" style={{ minHeight: 520 }}>
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {/* Welcome */}
            <div className="flex items-start gap-3">
              <div className="h-8 w-8 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                <Bot className="h-4 w-4 text-primary" />
              </div>
              <div className="glass-card rounded-xl rounded-tl-none px-4 py-3 max-w-xl">
                <p className="text-sm text-foreground">
                  Hola. Soy el agente del Observatorio. Puedo responder preguntas sobre
                  precios, cobertura por modelo, alertas y tendencias del mercado. ¿En qué te ayudo?
                </p>
              </div>
            </div>

            {/* Real messages */}
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex items-start gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}
              >
                <div
                  className={`h-8 w-8 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-primary/10 border border-primary/20"
                  }`}
                >
                  {msg.role === "user" ? (
                    <MessageSquare className="h-4 w-4" />
                  ) : (
                    <Bot className="h-4 w-4 text-primary" />
                  )}
                </div>
                <div
                  className={`rounded-xl px-4 py-3 max-w-xl text-sm ${
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground rounded-tr-none"
                      : msg.isError
                        ? "glass-card rounded-tl-none border-destructive/30"
                        : "glass-card rounded-tl-none"
                  }`}
                >
                  {/* Render text with bold markdown */}
                  {msg.text.split("\n").map((line, j) => {
                    const formatted = line.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
                    return (
                      <p
                        key={j}
                        className={line === "" ? "mt-2" : ""}
                        dangerouslySetInnerHTML={{ __html: formatted }}
                      />
                    );
                  })}

                  {/* Intent badge */}
                  {msg.intent && (
                    <span className="badge-neutral text-[10px] mt-2 inline-block">{msg.intent}</span>
                  )}

                  {/* Evidence */}
                  {msg.evidence && msg.evidence.length > 0 && (
                    <Collapsible className="mt-3">
                      <CollapsibleTrigger className="flex items-center gap-1 text-xs text-primary hover:underline cursor-pointer">
                        <ChevronDown className="h-3 w-3" />
                        {msg.evidence.length} registro{msg.evidence.length !== 1 ? "s" : ""} de evidencia
                      </CollapsibleTrigger>
                      <CollapsibleContent className="mt-2 space-y-1.5">
                        {msg.evidence.map((ev, idx) => (
                          <div key={idx} className="rounded-lg border border-border/60 bg-muted/20 px-3 py-2 text-xs">
                            <div className="flex justify-between">
                              <span className="font-medium text-foreground">{ev.competidor ?? ev.modelo ?? "—"}</span>
                              {ev.precio_valor != null && (
                                <span className="font-semibold text-foreground">{toCurrency(ev.precio_valor)}</span>
                              )}
                            </div>
                            {ev.modelo && (
                              <p className="text-muted-foreground">
                                {ev.modelo} {ev.capacidad ? `${ev.capacidad}GB` : ""}
                                {ev.modalidad ? ` · ${ev.modalidad}` : ""}
                              </p>
                            )}
                            {ev.coverage_pct != null && (
                              <p className="text-muted-foreground">{ev.coverage_pct.toFixed(1)}% cobertura</p>
                            )}
                          </div>
                        ))}
                      </CollapsibleContent>
                    </Collapsible>
                  )}
                </div>
              </div>
            ))}

            {/* Typing indicator */}
            {isLoading && (
              <div className="flex items-start gap-3">
                <div className="h-8 w-8 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Bot className="h-4 w-4 text-primary" />
                </div>
                <div className="glass-card rounded-xl rounded-tl-none px-4 py-3">
                  <div className="flex gap-1">
                    <span className="h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "0ms" }} />
                    <span className="h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "150ms" }} />
                    <span className="h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="border-t border-border/60 p-4">
            <div className="flex gap-2">
              <input
                className="flex-1 rounded-lg border border-border/60 bg-background px-4 py-2.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/40"
                placeholder="Escribe tu consulta..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isLoading}
              />
              <Button size="icon" onClick={() => handleSend()} disabled={isLoading || !input.trim()}>
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          <div className="glass-card rounded-xl p-5">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
              Consultas sugeridas
            </p>
            <div className="space-y-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s.text}
                  onClick={() => setInput(s.text)}
                  className="w-full flex items-start gap-3 rounded-lg border border-border/60 bg-background/60 px-3 py-2.5 text-left text-sm text-foreground/80 hover:bg-muted/40 hover:text-foreground transition-colors"
                >
                  <s.icon className="h-4 w-4 text-primary mt-0.5 flex-shrink-0" />
                  {s.text}
                </button>
              ))}
            </div>
          </div>

          <div className="glass-card rounded-xl p-5">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
              Cómo usar
            </p>
            <ul className="space-y-2 text-xs text-muted-foreground">
              {[
                "Pregunta por el precio más barato de un modelo",
                "Consulta la cobertura por marca o competidor",
                "Pide un resumen de precios de cualquier producto",
                "Puedes cambiar la marca arriba para filtrar contexto",
              ].map((item) => (
                <li key={item} className="flex items-start gap-2">
                  <span className="mt-1.5 h-1 w-1 rounded-full bg-primary/50 flex-shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </>
  );
}
