import { Link, useLocation } from "react-router-dom";
import { Bot, ChevronRight, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

import AgentConsole from "./AgentConsole";
import { useAgentConsole } from "./AgentConsoleContext";

const ROUTE_LABELS: Record<string, string> = {
  "/": "Home",
  "/dashboard": "Dashboard",
  "/observatorio": "Observatorio",
  "/visualizador": "Tabla de precios",
  "/simulador": "Simulador",
  "/agente": "Agente IA",
};

export default function GlobalAgentLauncher() {
  const location = useLocation();
  const { conversationCount, isLoading } = useAgentConsole();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (location.pathname === "/agente") {
      setOpen(false);
    }
  }, [location.pathname]);

  if (location.pathname === "/agente") {
    return null;
  }

  const contextLabel = ROUTE_LABELS[location.pathname] ?? "esta pantalla";

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button
          type="button"
          className="fixed bottom-5 right-5 z-40 inline-flex items-center gap-3 rounded-full border border-primary/20 bg-[linear-gradient(135deg,rgba(255,255,255,0.96),rgba(255,246,244,0.95))] px-4 py-3 text-left shadow-[0_18px_45px_rgba(236,0,0,0.18),0_8px_18px_rgba(15,23,42,0.08)] ring-1 ring-white/40 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_22px_55px_rgba(236,0,0,0.22),0_12px_22px_rgba(15,23,42,0.1)] dark:bg-[linear-gradient(135deg,rgba(34,44,63,0.96),rgba(22,30,45,0.96))] sm:bottom-6 sm:right-6"
        >
          <span className="relative flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-[0_10px_24px_rgba(236,0,0,0.28)]">
            <Bot className="h-5 w-5" />
            {isLoading && <span className="absolute -right-0.5 -top-0.5 h-3 w-3 rounded-full bg-amber-400 ring-2 ring-background" />}
          </span>

          <span className="hidden min-w-0 sm:block">
            <span className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              <Sparkles className="h-3.5 w-3.5 text-primary" />
              IA disponible
            </span>
            <span className="mt-1 block text-sm font-semibold text-foreground">
              Abrir asistente
            </span>
            <span className="mt-0.5 block text-xs text-muted-foreground">
              {conversationCount > 0
                ? `${conversationCount} consulta${conversationCount !== 1 ? "s" : ""} en sesion`
                : "precio web + insights"}
            </span>
          </span>
        </button>
      </SheetTrigger>

      <SheetContent
        side="right"
        className="w-full border-l border-border/80 bg-[hsl(var(--background)/0.97)] p-0 backdrop-blur-xl sm:max-w-[36rem]"
      >
        <div className="flex h-full min-h-0 flex-col">
          <SheetHeader className="border-b border-border/70 px-6 py-5 text-left">
            <div className="flex items-start justify-between gap-3 pr-8">
              <div>
                <SheetTitle className="text-xl">Asistente IA</SheetTitle>
                <SheetDescription className="mt-1">
                  Disponible en {contextLabel}. Puedes seguir en esta pantalla y consultar desde aqui.
                </SheetDescription>
              </div>

              <Link
                to="/agente"
                onClick={() => setOpen(false)}
                className="inline-flex items-center gap-1 rounded-full border border-border/70 bg-background/80 px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted/50"
              >
                vista completa
                <ChevronRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </SheetHeader>

          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-5 sm:py-5">
            <AgentConsole variant="panel" contextLabel={contextLabel} />
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
