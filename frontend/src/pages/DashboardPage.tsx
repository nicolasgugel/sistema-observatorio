import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, TooltipProps, XAxis, YAxis } from "recharts";
import { AlertTriangle, CalendarClock, ShieldCheck, Trophy } from "lucide-react";

import { PageHeader, KPICard, SkeletonCard, SkeletonChart } from "@/components/SharedUI";
import { Brand, ComparatorFilters, fetchComparator, fetchDashboard, toCurrency, toPct } from "@/lib/observatorio-api";
import RetailerLogo from "@/components/RetailerLogo";
import BrandSegmentedControl from "@/components/BrandSegmentedControl";
import { useAlertCount } from "@/context/AlertContext";

const COLORS = ["hsl(var(--primary))", "hsl(var(--info))", "hsl(var(--accent))", "hsl(var(--chart-neutral))"];

function ChartTooltip({
  active,
  payload,
  label,
  formatter,
}: TooltipProps<number, string> & { formatter?: (v: number) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass-card rounded-lg border border-border/70 px-3 py-2 text-xs shadow-lg backdrop-blur-sm">
      {label !== undefined && <p className="font-semibold text-foreground mb-1.5">{label}</p>}
      {payload.map((entry) => (
        <p key={entry.name} className="flex items-center gap-1.5 text-muted-foreground">
          <span className="h-2 w-2 rounded-full flex-shrink-0" style={{ backgroundColor: entry.color }} />
          <span>{entry.name}:</span>
          <span className="font-medium text-foreground">
            {formatter && typeof entry.value === "number" ? formatter(entry.value) : String(entry.value ?? "")}
          </span>
        </p>
      ))}
    </div>
  );
}
const COVERAGE_CHART_MARGIN = { top: 8, right: 12, left: 0, bottom: 12 };
const COVERAGE_CHART_Y_AXIS_WIDTH = 42;
const COVERAGE_LABEL_PADDING_LEFT = COVERAGE_CHART_MARGIN.left + COVERAGE_CHART_Y_AXIS_WIDTH;
const COVERAGE_LABEL_PADDING_RIGHT = COVERAGE_CHART_MARGIN.right;

interface AlertRow {
  model: string;
  capacity: number | null;
  modality: string;
  competitor: string;
  pct: number;
  competitorPrice: number | null;
  santanderPrice: number | null;
}

function formatRefreshDate(ts: string | undefined): string {
  if (!ts) return "Sin datos";
  const d = new Date(ts);
  return d.toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export default function DashboardPage() {
  const [brand, setBrand] = useState<Brand>("Samsung");
  const { setAlertCount } = useAlertCount();

  const filters: ComparatorFilters = { brand };

  const dashboardQuery = useQuery({
    queryKey: ["dashboard", filters],
    queryFn: () => fetchDashboard(filters),
  });

  const comparatorQuery = useQuery({
    queryKey: ["dashboard-alerts", filters],
    queryFn: () => fetchComparator(filters),
  });

  const timeline = useMemo(() => {
    if (!dashboardQuery.data?.temporal_evolution?.length) {
      return { rows: [] as Array<Record<string, string | number>>, competitors: [] as string[] };
    }
    const groupedByDate = new Map<string, Record<string, string | number>>();
    const competitors = Array.from(new Set(dashboardQuery.data.temporal_evolution.map((item) => item.competidor)));
    for (const point of dashboardQuery.data.temporal_evolution) {
      const dateKey = (point.timestamp || "").slice(0, 10);
      if (!groupedByDate.has(dateKey)) groupedByDate.set(dateKey, { date: dateKey });
      groupedByDate.get(dateKey)![point.competidor] = point.precio_medio;
    }
    const rows = Array.from(groupedByDate.values()).sort((a, b) =>
      String(a.date ?? "").localeCompare(String(b.date ?? "")),
    );
    return { rows, competitors };
  }, [dashboardQuery.data]);

  const alertRows = useMemo(() => {
    if (!comparatorQuery.data) return [] as AlertRow[];
    const alerts: AlertRow[] = [];
    for (const group of comparatorQuery.data.groups) {
      for (const offer of group.ofertas) {
        if (offer.competidor === "Santander Boutique") continue;
        if (typeof offer.diferencial_pct_vs_santander !== "number") continue;
        if (offer.diferencial_pct_vs_santander <= -5) {
          alerts.push({
            model: group.modelo,
            capacity: group.capacidad,
            modality: group.modalidad_label,
            competitor: offer.competidor,
            pct: offer.diferencial_pct_vs_santander,
            competitorPrice: offer.precio_valor,
            santanderPrice: group.precio_santander,
          });
        }
      }
    }
    return alerts.slice(0, 20);
  }, [comparatorQuery.data]);

  useEffect(() => {
    setAlertCount(alertRows.length);
  }, [alertRows.length, setAlertCount]);

  // Block 1: top 5 most exposed products
  const topRiskProducts = useMemo(
    () => [...alertRows].sort((a, b) => a.pct - b.pct).slice(0, 5),
    [alertRows],
  );

  // Block 1: alerts grouped by modality
  const alertsByModality = useMemo(() => {
    const map = new Map<string, number>();
    for (const row of alertRows) map.set(row.modality, (map.get(row.modality) ?? 0) + 1);
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1]);
  }, [alertRows]);

  // Block 3: catalog coverage stats
  const coverageStats = useMemo(() => {
    const items = dashboardQuery.data?.coverage_by_competitor ?? [];
    if (!items.length) return null;
    const avg = items.reduce((s, r) => s + r.coverage_pct, 0) / items.length;
    const sorted = [...items].sort((a, b) => b.coverage_pct - a.coverage_pct);
    return { avg, best: sorted[0], worst: sorted[sorted.length - 1] };
  }, [dashboardQuery.data]);

  // Block 4: most aggressive retailers (by alert count)
  const aggressiveRetailers = useMemo(() => {
    const map = new Map<string, number>();
    for (const row of alertRows) map.set(row.competitor, (map.get(row.competitor) ?? 0) + 1);
    return Array.from(map.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6);
  }, [alertRows]);

  // Block 4: gap medio vs Santander (from dashboard endpoint)
  const gapRetailers = useMemo(() => {
    return (dashboardQuery.data?.gap_vs_santander ?? [])
      .filter((r) => r.competidor !== "Santander Boutique" && typeof r.gap_medio === "number")
      .sort((a, b) => a.gap_medio - b.gap_medio)
      .slice(0, 8);
  }, [dashboardQuery.data]);

  const lastRefresh = formatRefreshDate(dashboardQuery.data?.kpis?.timestamp_ultima_extraccion);

  const kpis = dashboardQuery.data
    ? [
        {
          label: "Cobertura media",
          value: coverageStats ? `${coverageStats.avg.toFixed(1)}%` : "—",
          change: 0,
          trend: "neutral" as const,
          accentColor: "hsl(var(--primary))",
          sublabel: "% modelos con datos de competidor",
        },
        {
          label: "Modelos únicos",
          value: String(dashboardQuery.data.kpis.productos_unicos),
          change: 0,
          trend: "neutral" as const,
          accentColor: "hsl(var(--info))",
        },
        {
          label: "Competidores activos",
          value: String(dashboardQuery.data.kpis.competidores_activos),
          change: 0,
          trend: "neutral" as const,
          accentColor: "hsl(var(--success))",
          sublabel: `Últ. refresh: ${lastRefresh}`,
        },
        {
          label: "Alertas precio",
          value: String(alertRows.length),
          change: 0,
          trend: (alertRows.length > 0 ? "down" : "neutral") as const,
          accentColor: alertRows.length > 0 ? "hsl(var(--destructive))" : "hsl(var(--chart-neutral))",
          sublabel: alertRows.length > 0 ? ">5% por debajo de Santander" : "Sin alertas activas",
        },
      ]
    : [];

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle="Resumen ejecutivo de cobertura, precios y alertas"
        actions={<BrandSegmentedControl value={brand} onChange={setBrand} />}
      />

      {dashboardQuery.error ? <p className="text-sm text-destructive mb-4">No se pudieron cargar los datos.</p> : null}

      {dashboardQuery.isLoading ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5 mb-8">
            {[0, 1, 2, 3].map((i) => <SkeletonCard key={i} />)}
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mb-8">
            <SkeletonChart />
            <SkeletonChart />
          </div>
        </>
      ) : null}

      {dashboardQuery.data ? (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5 mb-8">
            {kpis.map((kpi) => (
              <KPICard key={kpi.label} {...kpi} />
            ))}
          </div>

          {/* BLOQUE 1+3: Top productos en riesgo + Estado del catálogo */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 mb-6">
            {/* Top 5 productos en riesgo (Block 1) */}
            <div className="xl:col-span-2 glass-card p-6 animate-fade-in">
              <div className="flex items-center gap-2 mb-4">
                <AlertTriangle className="h-4 w-4 text-destructive" />
                <div>
                  <h3 className="text-sm font-semibold text-foreground">Top 5 productos en riesgo</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">Mayor gap negativo vs Santander Boutique</p>
                </div>
              </div>
              {topRiskProducts.length === 0 ? (
                <p className="text-sm text-muted-foreground">No hay productos con alerta activa.</p>
              ) : (
                <div className="space-y-2">
                  {topRiskProducts.map((row, i) => {
                    const barWidth = Math.min(100, Math.abs(row.pct) * 3);
                    return (
                      <div key={`${row.model}-${row.capacity}-${row.modality}-${row.competitor}-${i}`} className="flex items-center gap-3">
                        <span className="text-xs font-bold text-muted-foreground w-4 flex-shrink-0">#{i + 1}</span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between mb-0.5">
                            <span className="text-xs font-medium text-foreground truncate">
                              {row.model} {row.capacity ? `${row.capacity}GB` : ""} — {row.modality}
                            </span>
                            <span className="badge-down tabular-premium ml-2 flex-shrink-0 text-[10px]">{toPct(row.pct)}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full bg-gradient-to-r from-red-500 to-red-400"
                                style={{ width: `${barWidth}%` }}
                              />
                            </div>
                            <div className="flex items-center gap-1 flex-shrink-0">
                              <RetailerLogo retailer={row.competitor} className="h-3.5 w-5" />
                              <span className="text-[10px] text-muted-foreground">{row.competitor}</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Estado del catálogo (Block 3) */}
            <div className="glass-card p-6 animate-fade-in flex flex-col gap-4">
              <div className="flex items-center gap-2 mb-0">
                <ShieldCheck className="h-4 w-4 text-success" />
                <h3 className="text-sm font-semibold text-foreground">Estado del catálogo</h3>
              </div>

              {/* Cobertura media */}
              <div>
                <p className="text-xs text-muted-foreground mb-1">Cobertura media del catálogo</p>
                <div className="flex items-end gap-2">
                  <span className="tabular-premium text-2xl font-semibold text-foreground">
                    {coverageStats ? `${coverageStats.avg.toFixed(1)}%` : "—"}
                  </span>
                </div>
                <div className="mt-1.5 h-1.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-primary to-red-500 transition-all"
                    style={{ width: `${coverageStats?.avg ?? 0}%` }}
                  />
                </div>
              </div>

              {/* Mejor / peor cobertura */}
              {coverageStats && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between rounded-lg bg-success/5 border border-success/15 px-3 py-2">
                    <div className="flex items-center gap-2">
                      <Trophy className="h-3.5 w-3.5 text-success flex-shrink-0" />
                      <div>
                        <p className="text-[10px] text-muted-foreground">Mejor cobertura</p>
                        <p className="text-xs font-medium text-foreground">{coverageStats.best.competidor}</p>
                      </div>
                    </div>
                    <span className="tabular-premium text-xs font-bold text-success">{coverageStats.best.coverage_pct.toFixed(0)}%</span>
                  </div>
                  <div className="flex items-center justify-between rounded-lg bg-muted/30 border border-border/60 px-3 py-2">
                    <div>
                      <p className="text-[10px] text-muted-foreground">Menor cobertura</p>
                      <p className="text-xs font-medium text-foreground">{coverageStats.worst.competidor}</p>
                    </div>
                    <span className="tabular-premium text-xs font-medium text-muted-foreground">{coverageStats.worst.coverage_pct.toFixed(0)}%</span>
                  </div>
                </div>
              )}

              {/* Último refresh */}
              <div className="flex items-center gap-2 pt-1 border-t border-border/40">
                <CalendarClock className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                <div>
                  <p className="text-[10px] text-muted-foreground">Última extracción</p>
                  <p className="text-xs font-medium text-foreground">{lastRefresh}</p>
                </div>
              </div>
            </div>
          </div>

          {/* BLOQUE 1+4: Alertas por modalidad + Retailers más agresivos */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mb-6">
            {/* Alertas por modalidad (Block 1) */}
            <div className="glass-card p-6 animate-fade-in">
              <h3 className="text-sm font-semibold text-foreground mb-1">Alertas por modalidad</h3>
              <p className="text-xs text-muted-foreground mb-4">Distribución de las alertas activas por tipo de oferta</p>
              {alertsByModality.length === 0 ? (
                <p className="text-sm text-muted-foreground">No hay alertas activas.</p>
              ) : (
                <div className="space-y-3">
                  {alertsByModality.map(([modality, count]) => {
                    const maxCount = alertsByModality[0][1];
                    const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;
                    return (
                      <div key={modality}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs font-medium text-foreground">{modality}</span>
                          <span className="badge-down tabular-premium text-[10px]">{count} alerta{count !== 1 ? "s" : ""}</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-red-500 to-red-400"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Retailers más agresivos (Block 4) */}
            <div className="glass-card p-6 animate-fade-in">
              <h3 className="text-sm font-semibold text-foreground mb-1">Retailers más agresivos</h3>
              <p className="text-xs text-muted-foreground mb-4">Competidores con más alertas activas y gap medio vs Santander</p>
              {aggressiveRetailers.length === 0 ? (
                <p className="text-sm text-muted-foreground">Sin datos de alertas por retailer.</p>
              ) : (
                <div className="space-y-2.5">
                  {aggressiveRetailers.map(([competitor, count], i) => {
                    const gapEntry = gapRetailers.find((r) => r.competidor === competitor);
                    const maxCount = aggressiveRetailers[0][1];
                    const barPct = (count / maxCount) * 100;
                    return (
                      <div key={competitor} className="flex items-center gap-3">
                        <span className="text-xs font-bold text-muted-foreground w-4 flex-shrink-0">#{i + 1}</span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between mb-0.5">
                            <div className="flex items-center gap-1.5">
                              <RetailerLogo retailer={competitor} className="h-4 w-6" />
                              <span className="text-xs font-medium text-foreground">{competitor}</span>
                            </div>
                            <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                              {gapEntry && (
                                <span className="text-[10px] text-muted-foreground">
                                  gap medio {toPct(gapEntry.gap_medio)}
                                </span>
                              )}
                              <span className="badge-down text-[10px]">{count}</span>
                            </div>
                          </div>
                          <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                            <div
                              className="h-full bg-destructive/60 rounded-full"
                              style={{ width: `${barPct}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Gap medio por retailer — gráfico de barras (Block 4) */}
          {gapRetailers.length > 0 && (
            <div className="glass-card p-6 animate-fade-in mb-6">
              <h3 className="text-sm font-semibold text-foreground mb-1">Gap medio vs Santander Boutique por retailer</h3>
              <p className="text-xs text-muted-foreground mb-4">
                Diferencia media de precio (€) — negativo significa que el competidor es más barato
              </p>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={gapRetailers} margin={{ top: 4, right: 12, left: 0, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="competidor" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                  <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                  <Tooltip content={<ChartTooltip formatter={(v) => toCurrency(v)} />} />
                  <Bar dataKey="gap_medio" radius={[4, 4, 0, 0]} name="Gap medio (€)">
                    {gapRetailers.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={entry.gap_medio < 0 ? "hsl(var(--destructive))" : "hsl(var(--success))"}
                        fillOpacity={0.75}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Evolución temporal + Cobertura por competidor */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mb-6">
            <div className="glass-card p-6 animate-fade-in">
              <h3 className="text-sm font-semibold text-foreground mb-4">Evolución de precio medio por competidor</h3>
              {timeline.rows.length === 0 ? (
                <p className="text-sm text-muted-foreground">No hay histórico suficiente para mostrar la gráfica.</p>
              ) : (
                <>
                  <ResponsiveContainer width="100%" height={280}>
                    <LineChart data={timeline.rows}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="hsl(var(--muted-foreground))" />
                      <YAxis tick={{ fontSize: 12 }} stroke="hsl(var(--muted-foreground))" />
                      <Tooltip content={<ChartTooltip formatter={(v) => toCurrency(v)} />} />
                      {timeline.competitors.slice(0, 4).map((competitor, index) => (
                        <Line
                          key={competitor}
                          type="monotone"
                          dataKey={competitor}
                          stroke={COLORS[index % COLORS.length]}
                          strokeWidth={2}
                          dot={false}
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {timeline.competitors.slice(0, 4).map((competitor, index) => (
                      <div key={competitor} className="inline-flex items-center gap-2 rounded-md border border-border/70 bg-muted/20 px-2 py-1">
                        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: COLORS[index % COLORS.length] }} />
                        <RetailerLogo retailer={competitor} className="h-4 w-6" />
                        <span className="text-xs text-foreground/85">{competitor}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>

            <div className="glass-card p-6 animate-fade-in">
              <h3 className="text-sm font-semibold text-foreground mb-4">Cobertura por competidor</h3>
              {dashboardQuery.data.coverage_by_competitor.length === 0 ? (
                <p className="text-sm text-muted-foreground">Sin cobertura comparable para el filtro actual.</p>
              ) : (
                <>
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={dashboardQuery.data.coverage_by_competitor} margin={COVERAGE_CHART_MARGIN}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="competidor" tick={false} axisLine={false} tickLine={false} height={8} />
                      <YAxis tick={{ fontSize: 12 }} width={COVERAGE_CHART_Y_AXIS_WIDTH} stroke="hsl(var(--muted-foreground))" />
                      <Tooltip content={<ChartTooltip formatter={(v) => toPct(v)} />} />
                      <Bar dataKey="coverage_pct" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} name="Cobertura %" />
                    </BarChart>
                  </ResponsiveContainer>
                  <div className="mt-3 overflow-x-auto">
                    <div
                      className="min-w-[620px]"
                      style={{ paddingLeft: `${COVERAGE_LABEL_PADDING_LEFT}px`, paddingRight: `${COVERAGE_LABEL_PADDING_RIGHT}px` }}
                    >
                      <div
                        className="grid items-start gap-2"
                        style={{ gridTemplateColumns: `repeat(${Math.max(dashboardQuery.data.coverage_by_competitor.length, 1)}, minmax(0, 1fr))` }}
                      >
                        {dashboardQuery.data.coverage_by_competitor.map((row) => (
                          <div key={row.competidor} className="flex flex-col items-center justify-start gap-1 px-1 text-center">
                            <RetailerLogo retailer={row.competidor} className="h-5 w-8" />
                            <span className="text-xs font-medium leading-tight text-foreground/85">{row.competidor}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Tabla de alertas detallada */}
          <div className="glass-card p-6 animate-fade-in">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-semibold text-foreground">Alertas de precio — detalle</h3>
                <p className="text-xs text-muted-foreground mt-0.5">Competidores con precio más de un 5% inferior a Santander</p>
              </div>
              {alertRows.length > 0 && (
                <span className="badge-down">{alertRows.length} alerta{alertRows.length !== 1 ? "s" : ""}</span>
              )}
            </div>
            {alertRows.length === 0 ? (
              <p className="text-sm text-muted-foreground">No hay alertas activas para la selección actual.</p>
            ) : (
              <div className="space-y-3">
                {alertRows.map((row) => (
                  <div
                    key={`${row.model}-${row.capacity}-${row.modality}-${row.competitor}`}
                    className="flex items-center justify-between rounded-lg bg-destructive/5 px-4 py-3 border border-destructive/10"
                  >
                    <div>
                      <p className="text-sm font-medium text-foreground">
                        {row.model} {row.capacity ? `${row.capacity}GB` : ""}
                      </p>
                      <p className="text-xs text-muted-foreground">{row.modality}</p>
                    </div>
                    <div className="text-right">
                      <p className="inline-flex items-center justify-end gap-2 text-sm font-medium text-foreground">
                        <RetailerLogo retailer={row.competitor} className="h-5 w-8" />
                        <span>{row.competitor}</span>
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {toCurrency(row.competitorPrice)} vs Santander {toCurrency(row.santanderPrice)}
                      </p>
                    </div>
                    <span className="badge-down text-xs">{toPct(row.pct)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      ) : null}
    </>
  );
}
