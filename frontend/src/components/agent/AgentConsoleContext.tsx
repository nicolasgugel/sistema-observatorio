/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useState,
} from "react";
import { type LucideIcon, Search, Sparkles } from "lucide-react";

import {
  type AgentChatResponse,
  type AgentChatStatus,
  type AgentEvidence,
  type LiveAgentOffer,
  chatWithAgent,
} from "@/lib/observatorio-api";

const THREAD_STORAGE_KEY = "observatorio_agent_thread_id.v1";
const MESSAGES_STORAGE_KEY = "observatorio_agent_messages.v1";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  traceId?: string;
  evidence?: AgentEvidence[];
  offers?: LiveAgentOffer[];
  suggestions?: string[];
  isError?: boolean;
  status?: AgentChatStatus;
}

export interface AgentSuggestion {
  icon: LucideIcon;
  text: string;
}

export interface AgentActivityStep {
  label: string;
  detail: string;
}

export interface AgentActivityState {
  summary: string;
  steps: AgentActivityStep[];
  activeStep: number;
  startedAt: number;
}

interface AgentConsoleContextValue {
  messages: ChatMessage[];
  input: string;
  setInput: (value: string) => void;
  isLoading: boolean;
  activity: AgentActivityState | null;
  conversationCount: number;
  suggestions: AgentSuggestion[];
  handleSend: (text?: string) => Promise<void>;
  startNewConversation: () => void;
}

const AgentConsoleContext = createContext<AgentConsoleContextValue | null>(null);

const UNIFIED_SUGGESTIONS: AgentSuggestion[] = [
  { icon: Search, text: "Busca el precio del Galaxy S25 Ultra 256GB en Amazon y Media Markt" },
  { icon: Search, text: "Que precio web visible tienen ahora unos AirPods Max?" },
  { icon: Sparkles, text: "Que implicaciones tiene para Santander Boutique el precio actual del iPhone 16 Pro 256GB?" },
  { icon: Sparkles, text: "Que estrategia de pricing deberia seguir Santander Boutique para Galaxy Buds3 Pro?" },
];

const DATASET_HINTS = [
  "observatorio",
  "current",
  "dataset",
  "cobertura",
  "gap",
  "gaps",
  "santander",
  "competidor",
  "competidores",
  "snapshot",
];

const STRATEGY_HINTS = [
  "estrategia",
  "pricing",
  "renting",
  "financiacion",
  "financiación",
  "cuota",
  "bundle",
  "bundles",
  "lanzamiento",
  "lanzamientos",
  "promo",
  "promocion",
  "promoción",
];

const WEB_HINTS = [
  "busca",
  "precio",
  "precios",
  "compare",
  "comparar",
  "mercado",
  "amazon",
  "fnac",
  "mediamarkt",
  "media markt",
  "web",
  "tienda",
];

function normalizeForActivity(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function buildActivityPlan(message: string): AgentActivityState {
  const normalized = normalizeForActivity(message);
  const asksStrategy = STRATEGY_HINTS.some((hint) => normalized.includes(hint));
  const asksDataset = DATASET_HINTS.some((hint) => normalized.includes(hint));
  const asksWeb = WEB_HINTS.some((hint) => normalized.includes(hint));

  if (asksStrategy) {
    return {
      summary: "Running pricing workflow",
      activeStep: 0,
      startedAt: Date.now(),
      steps: [
        {
          label: "Understanding request",
          detail: "Delimitando producto, modalidad y objetivo comercial antes de mover el benchmark.",
        },
        {
          label: "Searching the web",
          detail: "Localizando referencias visibles del mercado abierto para España.",
        },
        {
          label: "Fetching visible prices",
          detail: "Extrayendo precio, disponibilidad y posibles bundles relevantes.",
        },
        {
          label: "Comparing with current dataset",
          detail: "Contrastando el mercado con el current del observatorio y la posición de Santander.",
        },
        {
          label: "Developing pricing strategy",
          detail: "Traduciendo el benchmark en renting, financiación, cash y timing comercial.",
        },
        {
          label: "Drafting answer",
          detail: "Ordenando la recomendación final y los siguientes pasos sugeridos.",
        },
      ],
    };
  }

  if (asksDataset && !asksWeb) {
    return {
      summary: "Reading observatorio dataset",
      activeStep: 0,
      startedAt: Date.now(),
      steps: [
        {
          label: "Understanding request",
          detail: "Identificando si la consulta es de cobertura, gaps o posicionamiento Santander.",
        },
        {
          label: "Reading current snapshot",
          detail: "Cargando el current local y su metadata operativa.",
        },
        {
          label: "Comparing Santander position",
          detail: "Midiendo gaps de precio y cobertura frente a competidores.",
        },
        {
          label: "Drafting answer",
          detail: "Preparando una lectura accionable para negocio, sin inventar datos.",
        },
      ],
    };
  }

  return {
    summary: "Running market benchmark",
    activeStep: 0,
    startedAt: Date.now(),
    steps: [
      {
        label: "Understanding request",
        detail: "Identificando producto, capacidad, retailer y nivel de precisión necesarios.",
      },
      {
        label: "Searching the web",
        detail: "Rastreando referencias abiertas y retailers con precio visible.",
      },
      {
        label: "Fetching visible prices",
        detail: "Recogiendo precio, stock y formato de oferta antes de comparar.",
      },
      {
        label: "Structuring benchmark",
        detail: "Ordenando retailers, señales de precio y follow-ups útiles para negocio.",
      },
    ],
  };
}

function loadStoredThreadId(): string {
  if (typeof window === "undefined") {
    return crypto.randomUUID();
  }
  const stored = window.sessionStorage.getItem(THREAD_STORAGE_KEY)?.trim();
  return stored || crypto.randomUUID();
}

function loadStoredMessages(): ChatMessage[] {
  if (typeof window === "undefined") {
    return [];
  }
  const raw = window.sessionStorage.getItem(MESSAGES_STORAGE_KEY);
  if (!raw) {
    return [];
  }
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function mapResponseToMessage(response: AgentChatResponse): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: "assistant",
    text: response.answer,
    traceId: response.trace_id,
    evidence: response.evidence,
    offers: response.offers,
    suggestions: response.suggestions,
    isError: response.status === "failed",
    status: response.status,
  };
}

export function AgentConsoleProvider({ children }: { children: ReactNode }) {
  const [threadId, setThreadId] = useState(loadStoredThreadId);
  const [messages, setMessages] = useState<ChatMessage[]>(loadStoredMessages);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [activity, setActivity] = useState<AgentActivityState | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.sessionStorage.setItem(THREAD_STORAGE_KEY, threadId);
  }, [threadId]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.sessionStorage.setItem(MESSAGES_STORAGE_KEY, JSON.stringify(messages));
  }, [messages]);

  useEffect(() => {
    if (!isLoading || !activity || typeof window === "undefined") {
      return;
    }
    const timer = window.setInterval(() => {
      setActivity((prev) => {
        if (!prev) {
          return prev;
        }
        const nextStep = Math.min(prev.activeStep + 1, prev.steps.length - 1);
        if (nextStep === prev.activeStep) {
          return prev;
        }
        return {
          ...prev,
          activeStep: nextStep,
        };
      });
    }, 2400);
    return () => window.clearInterval(timer);
  }, [activity?.steps.length, isLoading]);

  async function handleSend(text?: string) {
    const message = (text ?? input).trim();
    if (!message || isLoading) return;

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      text: message,
      status: "completed",
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);
    setActivity(buildActivityPlan(message));

    try {
      const response = await chatWithAgent({ message, thread_id: threadId });
      setThreadId(response.thread_id || threadId);
      setMessages((prev) => [...prev, mapResponseToMessage(response)]);
    } catch (error) {
      const messageText =
        error instanceof Error && error.message.trim()
          ? error.message
          : "Error al procesar la consulta. Comprueba que el backend y la configuracion del agente estan activos.";
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: messageText,
          isError: true,
          status: "failed",
        },
      ]);
    } finally {
      setIsLoading(false);
      setActivity(null);
    }
  }

  function startNewConversation() {
    const nextThreadId = crypto.randomUUID();
    setThreadId(nextThreadId);
    setMessages([]);
    setInput("");
    setActivity(null);
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(THREAD_STORAGE_KEY, nextThreadId);
      window.sessionStorage.removeItem(MESSAGES_STORAGE_KEY);
    }
  }

  const value: AgentConsoleContextValue = {
    messages,
    input,
    setInput,
    isLoading,
    activity,
    conversationCount: messages.filter((message) => message.role === "user").length,
    suggestions: UNIFIED_SUGGESTIONS,
    handleSend,
    startNewConversation,
  };

  return <AgentConsoleContext.Provider value={value}>{children}</AgentConsoleContext.Provider>;
}

export function useAgentConsole() {
  const context = useContext(AgentConsoleContext);
  if (!context) {
    throw new Error("useAgentConsole must be used within AgentConsoleProvider");
  }
  return context;
}
