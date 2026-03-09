import { useState } from "react";
import { MessageSquare, Send, Sparkles, TrendingDown, BarChart3, Bot } from "lucide-react";
import { PageHeader } from "@/components/SharedUI";
import { Button } from "@/components/ui/button";

const DEMO_MESSAGES = [
  {
    role: "user",
    text: "¿Cuál es el gap de precio en Renting del Galaxy S25 Ultra 256GB vs Santander Boutique?",
  },
  {
    role: "assistant",
    text: "Para el **Galaxy S25 Ultra 256GB** en modalidad **Renting con seguro a 24 meses**, el análisis actual es:\n\n- **Santander Boutique:** 89,90 €/mes\n- **Competidor más barato:** Rentik a 74,90 €/mes (−16,7%)\n- **Media del mercado:** 82,40 €/mes\n\nEl gap con Rentik supera el umbral de alerta del 5%. Se recomienda revisar la estructura de coste del producto para los plazos de 24 meses.",
    chips: ["−16,7% vs Rentik", "Alerta activa", "24 meses"],
  },
  {
    role: "user",
    text: "¿Qué cobertura tenemos de Apple en el mercado?",
  },
  {
    role: "assistant",
    text: "La cobertura actual de **Apple** es del **68%** sobre el catálogo de referencia:\n\n- 8 de 12 modelos monitorizados tienen al menos una oferta de competidor\n- Mayor gap: iPhone 16 Pro Max 512GB — sin cobertura en renting\n- Mejor cobertura: iPhone 16 128GB — 9 retailers activos\n\nSe sugiere ampliar el tracking a MR.Apple y iGraal para mejorar la cobertura en los modelos Pro.",
    chips: ["68% cobertura", "4 modelos sin datos", "Apple"],
  },
];

const SUGGESTIONS = [
  { icon: TrendingDown, text: "Ver alertas de precio activas" },
  { icon: BarChart3, text: "Cobertura por modalidad esta semana" },
  { icon: Sparkles, text: "Resumen ejecutivo del último snapshot" },
];

export default function AgentePage() {
  const [input, setInput] = useState("");

  return (
    <>
      <PageHeader
        title="Agente IA"
        subtitle="Consultas en lenguaje natural sobre cobertura, gaps y tendencias del observatorio"
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
                  Hola. Soy el agente del Observatorio Samsung. Puedo responder preguntas sobre
                  precios, cobertura por modelo, alertas y tendencias del mercado. ¿En qué te ayudo?
                </p>
              </div>
            </div>

            {/* Demo messages */}
            {DEMO_MESSAGES.map((msg, i) => (
              <div
                key={i}
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
                      : "glass-card rounded-tl-none"
                  }`}
                >
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
                  {msg.chips && (
                    <div className="flex flex-wrap gap-1.5 mt-3">
                      {msg.chips.map((chip) => (
                        <span key={chip} className="badge-neutral text-[11px]">
                          {chip}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Placeholder disabled note */}
            <div className="flex justify-center">
              <span className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
                <Sparkles className="h-3 w-3" />
                Módulo en desarrollo — conversación de demostración
              </span>
            </div>
          </div>

          {/* Input */}
          <div className="border-t border-border/60 p-4">
            <div className="flex gap-2">
              <input
                className="flex-1 rounded-lg border border-border/60 bg-background px-4 py-2.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/40"
                placeholder="Escribe tu consulta… (demo, aún no conectado)"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled
              />
              <Button size="icon" disabled>
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        {/* Suggestions sidebar */}
        <div className="space-y-4">
          <div className="glass-card rounded-xl p-5">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
              Consultas sugeridas
            </p>
            <div className="space-y-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s.text}
                  className="w-full flex items-start gap-3 rounded-lg border border-border/60 bg-background/60 px-3 py-2.5 text-left text-sm text-foreground/80 hover:bg-muted/40 hover:text-foreground transition-colors cursor-default opacity-70"
                  disabled
                >
                  <s.icon className="h-4 w-4 text-primary mt-0.5 flex-shrink-0" />
                  {s.text}
                </button>
              ))}
            </div>
          </div>

          <div className="glass-card rounded-xl p-5">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
              Capacidades previstas
            </p>
            <ul className="space-y-2 text-xs text-muted-foreground">
              {[
                "Consulta de gaps por modelo y modalidad",
                "Resumen ejecutivo del snapshot",
                "Alertas interpretadas en lenguaje natural",
                "Sugerencias de acción comercial",
                "Comparativas históricas de precio",
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
