import { ReactNode, useEffect, useRef, useState } from "react";
import { TrendingDown, TrendingUp, Minus } from "lucide-react";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string | ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex items-start justify-between mb-8 animate-fade-in">
      <div>
        <h1 className="text-2xl font-semibold text-foreground sm:text-[2rem]">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </div>
  );
}

function useCountUp(target: number, duration = 900): number {
  const [count, setCount] = useState(0);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    if (target === 0) {
      setCount(0);
      return;
    }
    const startTime = performance.now();
    const tick = (now: number) => {
      const progress = Math.min((now - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setCount(Math.round(eased * target));
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(tick);
      }
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration]);

  return count;
}

export function KPICard({
  label,
  value,
  change,
  trend,
  accentColor,
  sublabel,
}: {
  label: string;
  value: string;
  change: number;
  trend: "up" | "down" | "neutral";
  accentColor?: string;
  sublabel?: string;
}) {
  const badgeClass = trend === "up" ? "badge-up" : trend === "down" ? "badge-down" : "badge-neutral";
  const sign = change > 0 ? "+" : "";
  const TrendIcon = trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : Minus;

  // Animate integer parts of the value string (e.g. "247", "8", "87.3%")
  const intMatch = value.match(/^(\d+)(.*)$/);
  const intTarget = intMatch ? parseInt(intMatch[1]) : null;
  const intSuffix = intMatch ? intMatch[2] : "";
  const animatedInt = useCountUp(intTarget ?? 0);
  const displayValue = intTarget !== null ? `${animatedInt}${intSuffix}` : value;

  const content = (
    <>
      <div className="flex items-center gap-2">
        <span
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ backgroundColor: accentColor ?? "hsl(var(--chart-neutral))" }}
        />
        <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
      </div>
      <p className="tabular-premium mt-3 break-words text-[2rem] font-semibold leading-none tracking-[-0.04em] text-foreground">
        {displayValue}
      </p>
      {sublabel && <p className="mt-1.5 text-xs text-muted-foreground">{sublabel}</p>}
      {change !== 0 && (
        <span className={`mt-2 inline-flex items-center gap-1 ${badgeClass}`}>
          <TrendIcon className="h-3 w-3" />
          {sign}{change}%
        </span>
      )}
    </>
  );

  return <div className="kpi-card animate-fade-in text-left">{content}</div>;
}

export function SkeletonCard({ className = "" }: { className?: string }) {
  return (
    <div className={`kpi-card animate-pulse ${className}`}>
      <div className="h-3 w-24 rounded-full bg-muted" />
      <div className="h-9 w-20 rounded bg-muted mt-3" />
      <div className="h-3 w-14 rounded-full bg-muted mt-2" />
    </div>
  );
}

export function SkeletonChart({ className = "" }: { className?: string }) {
  return (
    <div className={`glass-card rounded-xl p-6 animate-pulse ${className}`}>
      <div className="h-4 w-48 rounded-full bg-muted mb-6" />
      <div className="h-64 w-full rounded-xl bg-muted/50" />
      <div className="mt-3 flex gap-2">
        <div className="h-6 w-24 rounded-full bg-muted" />
        <div className="h-6 w-20 rounded-full bg-muted" />
        <div className="h-6 w-16 rounded-full bg-muted" />
      </div>
    </div>
  );
}

export function SkeletonTable({ rows = 8 }: { rows?: number }) {
  return (
    <div className="glass-card rounded-xl overflow-hidden animate-pulse">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border bg-muted/30">
            {[180, 200, 140, 80, 100, 90, 80, 90, 110].map((w, i) => (
              <th key={i} className="px-5 py-3">
                <div className="h-3 rounded-full bg-muted" style={{ width: w * 0.5 }} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, i) => (
            <tr key={i} className="border-b border-border/50">
              {[140, 180, 120, 60, 80, 70, 60, 80, 90].map((w, j) => (
                <td key={j} className="px-5 py-3.5">
                  <div
                    className="h-3 rounded-full bg-muted/70"
                    style={{ width: w * (0.5 + Math.random() * 0.4) }}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ElementType;
  title: string;
  description?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="h-12 w-12 rounded-full bg-muted/60 flex items-center justify-center mb-4">
        <Icon className="h-5 w-5 text-muted-foreground" />
      </div>
      <p className="text-sm font-medium text-foreground">{title}</p>
      {description && <p className="mt-1 text-xs text-muted-foreground max-w-xs">{description}</p>}
    </div>
  );
}
