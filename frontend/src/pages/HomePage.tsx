import { ArrowRight, BarChart3, Bell, GitCompareArrows, LayoutDashboard, MessageSquare, Table2, TrendingDown } from "lucide-react";
import { Link } from "react-router-dom";

import accentureWordmark from "@/assets/accenture-wordmark.png";
import santanderLogo from "@/assets/santander-logo.png";
import { Button } from "@/components/ui/button";

const features = [
  {
    icon: GitCompareArrows,
    title: "Observatorio",
    description:
      "Análisis cara a cara por modelo, capacidad y modalidad — renting con o sin seguro, financiación, contado — con gráfico de desviación vs. Santander Boutique.",
    accentColor: "hsl(var(--primary))",
  },
  {
    icon: Bell,
    title: "Alertas automáticas",
    description:
      "Detecta cuándo un competidor ofrece un precio significativamente inferior al de Santander Boutique y prioriza dónde actuar primero.",
    accentColor: "hsl(var(--destructive))",
  },
  {
    icon: TrendingDown,
    title: "Precios en tiempo real",
    description:
      "Consulta los precios actuales de Santander Boutique frente a los competidores del mercado, por modelo, capacidad y modalidad de pago.",
    accentColor: "hsl(var(--info))",
  },
  {
    icon: MessageSquare,
    title: "Agente IA",
    description:
      "Próximamente: consultas en lenguaje natural sobre cobertura, gaps de precio y tendencias del observatorio sin necesidad de filtros.",
    accentColor: "hsl(var(--muted-foreground))",
    soon: true,
  },
];

const modules = [
  {
    title: "Dashboard",
    description: "Resumen ejecutivo de cobertura, alertas y desviaciones.",
    to: "/dashboard",
    cta: "Abrir dashboard",
    icon: LayoutDashboard,
  },
  {
    title: "Observatorio",
    description: "Cara a cara por modelo, capacidad y modalidad.",
    to: "/observatorio",
    cta: "Abrir observatorio",
    icon: GitCompareArrows,
  },
  {
    title: "Tabla de Precios",
    description: "Consulta y filtra todos los precios actuales por competidor, modelo y modalidad.",
    to: "/visualizador",
    cta: "Ver tabla de precios",
    icon: Table2,
  },
  {
    title: "Agente IA",
    description: "Módulo conversacional en desarrollo.",
    to: "/agente",
    cta: "Ver módulo",
    icon: MessageSquare,
    soon: true,
  },
];

export default function HomePage() {
  return (
    <div className="space-y-10 animate-fade-in">

      {/* Hero */}
      <section className="home-hero">
        <div className="home-hero-glow" />
        <div className="relative z-10">
          {/* Brand lockup */}
          <div className="home-brand-lockup mb-8">
            <img src={santanderLogo} alt="Santander" className="home-brand-logo home-brand-logo-santander" />
            <span className="home-brand-divider" />
            <img src={accentureWordmark} alt="Accenture" className="home-brand-logo home-brand-logo-accenture" />
          </div>

          <div className="max-w-2xl space-y-4">
            <p className="home-eyebrow">Sistema Observatorio</p>
            <h1 className="text-3xl font-extrabold leading-tight tracking-tight text-foreground sm:text-4xl">
              Inteligencia de precios de Santander Boutique<br className="hidden sm:block" />
              frente al mercado, en un solo lugar.
            </h1>
            <p className="text-base text-muted-foreground max-w-xl">
              Monitorización continua de los precios de Santander Boutique comparados con los competidores del mercado,
              con alertas automáticas y análisis por modelo, capacidad y modalidad de pago.
            </p>
            <div className="flex flex-wrap gap-3 pt-2">
              <Button asChild size="lg" className="home-cta-primary">
                <Link to="/observatorio">
                  Ir al observatorio
                  <ArrowRight className="h-4 w-4 ml-2" />
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg" className="home-cta-secondary">
                <Link to="/dashboard">
                  <BarChart3 className="h-4 w-4 mr-2" />
                  Ver dashboard
                </Link>
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section>
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-4">Qué hace el observatorio</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {features.map((f, i) => (
            <article
              key={f.title}
              className="glass-card rounded-xl p-5 flex flex-col gap-3 animate-fade-in"
              style={{ animationDelay: `${i * 60}ms`, borderLeft: `3px solid ${f.accentColor}`, paddingLeft: "1.25rem" }}
            >
              <div
                className="h-9 w-9 rounded-lg flex items-center justify-center flex-shrink-0"
                style={{ background: `color-mix(in srgb, ${f.accentColor} 12%, transparent)` }}
              >
                <f.icon className="h-4.5 w-4.5" style={{ color: f.accentColor }} />
              </div>
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <h2 className="text-sm font-semibold text-foreground">{f.title}</h2>
                  {f.soon && (
                    <span className="badge-neutral text-[10px]">Próximamente</span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">{f.description}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* Module nav */}
      <section>
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-4">Módulos disponibles</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {modules.map((m, i) => (
            <article
              key={m.title}
              className="home-module-card animate-fade-in"
              style={{ animationDelay: `${120 + i * 50}ms` }}
            >
              <div className="flex items-start gap-3 mb-4">
                <div className="home-module-icon">
                  <m.icon className="h-4 w-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-foreground">{m.title}</h3>
                    {m.soon && <span className="home-module-status-soon">Próximamente</span>}
                    {!m.soon && <span className="home-module-status-on">Activo</span>}
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">{m.description}</p>
                </div>
              </div>
              <Button asChild variant="outline" className="w-full justify-between home-module-cta text-xs">
                <Link to={m.to}>
                  {m.cta}
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
            </article>
          ))}
        </div>
      </section>

    </div>
  );
}
