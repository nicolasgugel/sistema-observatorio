import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ArrowDown, ArrowUp, Minus, Calculator } from "lucide-react";

import { EmptyState, KPICard, PageHeader, SkeletonCard, SkeletonChart } from "@/components/SharedUI";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import BrandSegmentedControl from "@/components/BrandSegmentedControl";
import RetailerLogo from "@/components/RetailerLogo";
import { type ComparatorOffer, fetchAllRecords, toCurrency } from "@/lib/observatorio-api";

type BrandTab = "Samsung" | "Apple";

const OFFER_LABELS: Record<string, string> = {
  renting_no_insurance: "Renting SIN seguro",
  renting_with_insurance: "Renting CON seguro",
  financing_max_term: "Financiación",
  cash: "Compra al contado",
};

const HAS_TERMS = new Set(["financing_max_term", "renting_with_insurance", "renting_no_insurance"]);

const RETAILER_ORDER = [
  "Santander Boutique",
  "Amazon",
  "Apple Oficial",
  "Movistar",
  "Rentik",
  "Samsung Oficial",
  "Media Markt",
  "El Corte Inglés",
  "El Corte Ingles",
  "Grover",
  "Orange",
  "Qonexa",
];

const CHART_COLORS: Record<string, string> = {
  "Santander Boutique": "#ec0000",
  Amazon: "#ff9900",
  "Apple Oficial": "#1d1d1f",
  Movistar: "#019df4",
  Rentik: "#e6007e",
  "Samsung Oficial": "#034ea2",
  "Media Markt": "#df0000",
  "El Corte Ingles": "#006739",
  Grover: "#ff245b",
  Orange: "#ff6600",
  Qonexa: "#333333",
};

function retailerSort(a: string, b: string): number {
  const left = RETAILER_ORDER.indexOf(a);
  const right = RETAILER_ORDER.indexOf(b);
  return (left === -1 ? 999 : left) - (right === -1 ? 999 : right) || a.localeCompare(b, "es");
}

function formatCapacity(value: number | null): string {
  if (typeof value !== "number") return "-";
  if (value >= 1024) {
    const tb = value / 1024;
    return `${tb % 1 === 0 ? tb.toFixed(0) : tb.toFixed(1)} TB`;
  }
  return `${value} GB`;
}

function formatBarPrice(value: number): string {
  if (!Number.isFinite(value)) return "-";
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: value >= 1000 ? 0 : 2,
  }).format(value);
}

function computeChartCeiling(maxValue: number): number {
  if (!Number.isFinite(maxValue) || maxValue <= 0) return 1;
  return Math.ceil(maxValue * 1.18);
}

const CHART_MARGIN = { top: 34, right: 12, left: 0, bottom: 12 };
const CHART_Y_AXIS_WIDTH = 56;
const CHART_LABEL_PL = CHART_MARGIN.left + CHART_Y_AXIS_WIDTH;
const CHART_LABEL_PR = CHART_MARGIN.right;

export default function SimuladorPage() {
  const [brand, setBrand] = useState<BrandTab>("Samsung");
  const [selectedModality, setSelectedModality] = useState("renting_with_insurance");
  const [selectedModel, setSelectedModel] = useState("all");
  const [selectedCapacity, setSelectedCapacity] = useState("all");
  const [selectedTerm, setSelectedTerm] = useState("all");
  const [simulatedPrice, setSimulatedPrice] = useState<number | null>(null);
  const [priceInputText, setPriceInputText] = useState("");

  const recordsQuery = useQuery({
    queryKey: ["simulador-records", brand],
    queryFn: () => fetchAllRecords({ brand }),
  });

  const allRows = recordsQuery.data ?? [];

  // ── Derived filter options ──

  const models = useMemo(() => {
    const unique = Array.from(new Set(allRows.map((r) => r.modelo).filter(Boolean)));
    return unique.sort((a, b) => a.localeCompare(b, "es"));
  }, [allRows]);

  const capacities = useMemo(() => {
    const values = allRows
      .filter((r) => (selectedModel === "all" ? true : r.modelo === selectedModel))
      .filter((r) => r.modalidad === selectedModality)
      .map((r) => r.capacidad)
      .filter((v): v is number => typeof v === "number");
    return Array.from(new Set(values)).sort((a, b) => a - b);
  }, [allRows, selectedModel, selectedModality]);

  const terms = useMemo(() => {
    if (!HAS_TERMS.has(selectedModality)) return [] as number[];
    const values = allRows
      .filter((r) => r.modalidad === selectedModality)
      .filter((r) => (selectedModel === "all" ? true : r.modelo === selectedModel))
      .filter((r) => (selectedCapacity === "all" ? true : String(r.capacidad) === selectedCapacity))
      .map((r) => r.term_months)
      .filter((v): v is number => typeof v === "number");
    return Array.from(new Set(values)).sort((a, b) => a - b);
  }, [allRows, selectedModality, selectedModel, selectedCapacity]);

  // ── Resets ──

  useEffect(() => {
    setSelectedModel("all");
    setSelectedCapacity("all");
    setSelectedTerm("all");
    setSelectedModality("renting_with_insurance");
    setSimulatedPrice(null);
  }, [brand]);

  useEffect(() => {
    if (selectedModel !== "all" && !models.includes(selectedModel)) setSelectedModel("all");
  }, [models, selectedModel]);

  useEffect(() => {
    if (selectedCapacity !== "all" && !capacities.some((v) => String(v) === selectedCapacity)) setSelectedCapacity("all");
  }, [capacities, selectedCapacity]);

  useEffect(() => {
    if (!HAS_TERMS.has(selectedModality) && selectedTerm !== "all") {
      setSelectedTerm("all");
      return;
    }
    if (selectedTerm !== "all" && !terms.some((v) => String(v) === selectedTerm)) setSelectedTerm("all");
  }, [selectedModality, selectedTerm, terms]);

  useEffect(() => {
    setSimulatedPrice(null);
  }, [selectedModel, selectedCapacity, selectedModality, selectedTerm]);

  // ── Filtered data ──

  const filteredRows = useMemo(() => {
    return allRows.filter((r) => {
      if (r.modalidad !== selectedModality) return false;
      if (selectedModel !== "all" && r.modelo !== selectedModel) return false;
      if (selectedCapacity !== "all" && String(r.capacidad) !== selectedCapacity) return false;
      if (HAS_TERMS.has(selectedModality) && selectedTerm !== "all" && String(r.term_months) !== selectedTerm) return false;
      return typeof r.precio_valor === "number" && Number.isFinite(r.precio_valor) && r.precio_valor >= 0;
    });
  }, [allRows, selectedModality, selectedModel, selectedCapacity, selectedTerm]);

  const santanderPrice = useMemo(() => {
    const row = filteredRows.find((r) => r.competidor === "Santander Boutique");
    return row?.precio_valor ?? null;
  }, [filteredRows]);

  // Initialize simulated price when Santander price is available
  useEffect(() => {
    if (santanderPrice !== null && simulatedPrice === null) {
      setSimulatedPrice(santanderPrice);
      setPriceInputText(String(santanderPrice));
    }
  }, [santanderPrice, simulatedPrice]);

  const canSimulate = selectedModel !== "all" && selectedCapacity !== "all" && santanderPrice !== null;

  // ── Best price per retailer ──

  const bestByRetailer = useMemo(() => {
    const map = new Map<string, number>();
    for (const r of filteredRows) {
      if (typeof r.precio_valor !== "number") continue;
      const current = map.get(r.competidor);
      if (current === undefined || r.precio_valor < current) map.set(r.competidor, r.precio_valor);
    }
    return map;
  }, [filteredRows]);

  // ── Chart data with simulated Santander ──

  const chartRows = useMemo(() => {
    const labels = Array.from(bestByRetailer.keys()).sort(retailerSort);
    return labels.map((retailer) => {
      const realPrice = bestByRetailer.get(retailer) ?? 0;
      const price = retailer === "Santander Boutique" && simulatedPrice !== null ? simulatedPrice : realPrice;
      return { competidor: retailer, precio: price, fill: CHART_COLORS[retailer] ?? "#7a8193" };
    });
  }, [bestByRetailer, simulatedPrice]);

  const chartCeiling = useMemo(() => {
    const max = chartRows.reduce((m, r) => Math.max(m, r.precio), 0);
    const withOriginal = santanderPrice !== null ? Math.max(max, santanderPrice) : max;
    return computeChartCeiling(withOriginal);
  }, [chartRows, santanderPrice]);

  // ── Ranking ──

  const ranking = useMemo(() => {
    if (!canSimulate || simulatedPrice === null) return null;
    const sorted = [...chartRows].sort((a, b) => a.precio - b.precio);
    const simPos = sorted.findIndex((r) => r.competidor === "Santander Boutique") + 1;
    const total = sorted.length;

    // Original ranking
    const originalSorted = Array.from(bestByRetailer.entries())
      .sort((a, b) => a[1] - b[1]);
    const origPos = originalSorted.findIndex(([r]) => r === "Santander Boutique") + 1;

    return { currentPos: origPos, simulatedPos: simPos, total, delta: origPos - simPos };
  }, [canSimulate, simulatedPrice, chartRows, bestByRetailer]);

  // ── Differentials table ──

  const diffRows = useMemo(() => {
    if (!canSimulate || simulatedPrice === null || simulatedPrice === 0) return [];
    return chartRows
      .filter((r) => r.competidor !== "Santander Boutique")
      .map((r) => {
        const diff = r.precio - simulatedPrice;
        const diffPct = (diff / simulatedPrice) * 100;
        return { competidor: r.competidor, precio: r.precio, diff: Math.round(diff * 100) / 100, diffPct: Math.round(diffPct * 100) / 100 };
      })
      .sort((a, b) => a.precio - b.precio);
  }, [canSimulate, simulatedPrice, chartRows]);

  // ── Slider config ──

  const sliderStep = selectedModality === "cash" || selectedModality === "financing_max_term" ? 1 : 0.5;
  const sliderMin = santanderPrice !== null ? Math.round(santanderPrice * 0.5 * 100) / 100 : 0;
  const sliderMax = santanderPrice !== null ? Math.round(santanderPrice * 1.5 * 100) / 100 : 100;

  return (
    <>
      <PageHeader
        title="Simulador What-If"
        subtitle="Simula cambios de precio de Santander Boutique y observa el impacto competitivo en tiempo real"
      />

      <div className="mb-5">
        <BrandSegmentedControl value={brand} onChange={(b) => setBrand(b as BrandTab)} />
      </div>

      {/* Filters */}
      <div className="glass-card rounded-xl p-5 mb-6 animate-fade-in">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Modalidad</p>
            <Select value={selectedModality} onValueChange={setSelectedModality}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(OFFER_LABELS).map(([key, label]) => (
                  <SelectItem key={key} value={key}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Modelo</p>
            <Select value={selectedModel} onValueChange={setSelectedModel}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Selecciona un modelo</SelectItem>
                {models.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Capacidad</p>
            <Select value={selectedCapacity} onValueChange={setSelectedCapacity}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Selecciona capacidad</SelectItem>
                {capacities.map((c) => <SelectItem key={c} value={String(c)}>{formatCapacity(c)}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Plazo</p>
            <Select value={selectedTerm} onValueChange={setSelectedTerm} disabled={!HAS_TERMS.has(selectedModality)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos los plazos</SelectItem>
                {terms.map((t) => <SelectItem key={t} value={String(t)}>{t} meses</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {recordsQuery.isLoading && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
            {[0, 1, 2, 3].map((i) => <SkeletonCard key={i} />)}
          </div>
          <SkeletonChart />
        </>
      )}

      {recordsQuery.error && <p className="text-sm text-destructive mb-4">Error cargando datos.</p>}

      {!canSimulate && !recordsQuery.isLoading && (
        <EmptyState
          icon={Calculator}
          title="Selecciona un producto concreto"
          description="Elige un modelo, capacidad y modalidad para activar el simulador de precios."
        />
      )}

      {canSimulate && simulatedPrice !== null && (
        <>
          {/* Simulation control panel */}
          <div className="glass-card rounded-xl p-6 mb-6 animate-fade-in">
            <h3 className="text-sm font-semibold text-foreground mb-4">Panel de simulación</h3>
            <div className="grid grid-cols-1 xl:grid-cols-[1fr_1fr] gap-6">
              {/* Slider + input */}
              <div>
                <p className="text-xs text-muted-foreground mb-3">Ajusta el precio simulado de Santander Boutique</p>
                <Slider
                  value={[simulatedPrice]}
                  onValueChange={([v]) => {
                    setSimulatedPrice(v);
                    setPriceInputText(String(v));
                  }}
                  min={sliderMin}
                  max={sliderMax}
                  step={sliderStep}
                  className="mb-4"
                />
                <div className="flex items-center gap-3">
                  <Input
                    type="text"
                    inputMode="decimal"
                    value={priceInputText}
                    onChange={(e) => setPriceInputText(e.target.value)}
                    onBlur={() => {
                      const v = parseFloat(priceInputText);
                      if (Number.isFinite(v)) {
                        const clamped = Math.max(sliderMin, Math.min(sliderMax, v));
                        setSimulatedPrice(clamped);
                        setPriceInputText(String(clamped));
                      } else {
                        setPriceInputText(String(simulatedPrice));
                      }
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        (e.target as HTMLInputElement).blur();
                      }
                    }}
                    className="w-32 tabular-premium"
                  />
                  <span className="text-xs text-muted-foreground">
                    {selectedModality === "cash" ? "EUR" : "EUR/mes"} · Rango: {toCurrency(sliderMin)} – {toCurrency(sliderMax)}
                  </span>
                </div>
              </div>

              {/* KPI cards */}
              <div className="grid grid-cols-2 gap-3">
                <KPICard
                  label="Precio actual"
                  value={toCurrency(santanderPrice) ?? "—"}
                  change={0}
                  trend="neutral"
                  accentColor="hsl(var(--chart-neutral))"
                />
                <KPICard
                  label="Precio simulado"
                  value={toCurrency(simulatedPrice) ?? "—"}
                  change={0}
                  trend={simulatedPrice < santanderPrice ? "up" : simulatedPrice > santanderPrice ? "down" : "neutral"}
                  accentColor={simulatedPrice < santanderPrice ? "hsl(var(--success))" : simulatedPrice > santanderPrice ? "hsl(var(--destructive))" : "hsl(var(--chart-neutral))"}
                  sublabel={
                    santanderPrice !== simulatedPrice
                      ? `${simulatedPrice < santanderPrice ? "" : "+"}${toCurrency(simulatedPrice - santanderPrice)} (${((simulatedPrice - santanderPrice) / santanderPrice * 100).toFixed(1)}%)`
                      : "Sin cambio"
                  }
                />
                {ranking && (
                  <>
                    <div className="kpi-card animate-fade-in text-left">
                      <div className="flex items-center gap-2">
                        <span className="h-2 w-2 shrink-0 rounded-full bg-[hsl(var(--info))]" />
                        <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Posición actual</p>
                      </div>
                      <p className="tabular-premium mt-3 text-[2rem] font-semibold leading-none tracking-[-0.04em] text-foreground">
                        #{ranking.currentPos}
                      </p>
                      <p className="mt-1.5 text-xs text-muted-foreground">de {ranking.total} retailers</p>
                    </div>
                    <div className="kpi-card animate-fade-in text-left">
                      <div className="flex items-center gap-2">
                        <span
                          className="h-2 w-2 shrink-0 rounded-full"
                          style={{ backgroundColor: ranking.delta > 0 ? "hsl(var(--success))" : ranking.delta < 0 ? "hsl(var(--destructive))" : "hsl(var(--chart-neutral))" }}
                        />
                        <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Posición simulada</p>
                      </div>
                      <p className="tabular-premium mt-3 text-[2rem] font-semibold leading-none tracking-[-0.04em] text-foreground flex items-center gap-2">
                        #{ranking.simulatedPos}
                        {ranking.delta > 0 && <ArrowUp className="h-5 w-5 text-success" />}
                        {ranking.delta < 0 && <ArrowDown className="h-5 w-5 text-destructive" />}
                        {ranking.delta === 0 && <Minus className="h-5 w-5 text-muted-foreground" />}
                      </p>
                      <p className="mt-1.5 text-xs text-muted-foreground">
                        {ranking.delta > 0 ? `Sube ${ranking.delta} posición(es)` : ranking.delta < 0 ? `Baja ${Math.abs(ranking.delta)} posición(es)` : "Sin cambio"}
                      </p>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Bar chart */}
          <div className="glass-card rounded-xl p-6 mb-6 animate-fade-in">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-foreground">Comparativa de precios (simulada)</h3>
              {santanderPrice !== simulatedPrice && (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-destructive/30 bg-destructive/10 px-3 py-1 text-xs font-semibold text-destructive">
                  <span className="h-0.5 w-3 bg-destructive" style={{ borderTop: "2px dashed" }} />
                  Precio actual: {toCurrency(santanderPrice)}
                </span>
              )}
            </div>
            {chartRows.length === 0 ? (
              <p className="text-sm text-muted-foreground">No hay ofertas.</p>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={340}>
                  <BarChart data={chartRows} margin={CHART_MARGIN}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="competidor" tick={false} axisLine={false} tickLine={false} height={8} />
                    <YAxis tick={{ fontSize: 11 }} width={CHART_Y_AXIS_WIDTH} domain={[0, chartCeiling]} />
                    <Tooltip formatter={(value) => toCurrency(typeof value === "number" ? value : null)} />
                    {santanderPrice !== simulatedPrice && (
                      <ReferenceLine
                        y={santanderPrice}
                        stroke="hsl(var(--destructive))"
                        strokeWidth={2}
                        strokeDasharray="8 4"
                        label={{
                          value: `Precio actual: ${toCurrency(santanderPrice)}`,
                          position: "insideTopLeft",
                          fill: "hsl(var(--destructive))",
                          fontSize: 12,
                          fontWeight: 700,
                          offset: 8,
                        }}
                      />
                    )}
                    <Bar dataKey="precio" radius={[12, 12, 0, 0]}>
                      {chartRows.map((entry) => (
                        <Cell key={entry.competidor} fill={entry.fill} />
                      ))}
                      <LabelList
                        dataKey="precio"
                        position="top"
                        formatter={(value: number) => formatBarPrice(value)}
                        fill="hsl(var(--foreground))"
                        fontSize={11}
                        fontWeight={700}
                      />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <div className="mt-4 overflow-x-auto">
                  <div className="min-w-[760px]" style={{ paddingLeft: `${CHART_LABEL_PL}px`, paddingRight: `${CHART_LABEL_PR}px` }}>
                    <div className="grid items-start gap-3" style={{ gridTemplateColumns: `repeat(${Math.max(chartRows.length, 1)}, minmax(0, 1fr))` }}>
                      {chartRows.map((entry) => (
                        <div key={entry.competidor} className="flex flex-col items-center justify-start gap-1 px-1 text-center">
                          <RetailerLogo retailer={entry.competidor} className="h-6 w-10" />
                          <span className="text-sm font-medium leading-tight text-foreground/85">{entry.competidor}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Differentials table */}
          {diffRows.length > 0 && (
            <div className="glass-card rounded-xl overflow-auto max-h-[50vh] animate-fade-in">
              <h3 className="text-sm font-semibold text-foreground px-5 pt-5 pb-3">Diferenciales vs precio simulado</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-card sticky top-0 z-10">
                    <th className="table-header text-left px-4 py-3">Retailer</th>
                    <th className="table-header text-right px-4 py-3">Precio</th>
                    <th className="table-header text-right px-4 py-3">Diferencial (€)</th>
                    <th className="table-header text-right px-4 py-3">Diferencial (%)</th>
                  </tr>
                </thead>
                <tbody>
                  {diffRows.map((row) => {
                    const isMoreExpensive = row.diff > 0;
                    return (
                      <tr key={row.competidor} className="border-b border-border/50 hover:bg-muted/20 transition-colors">
                        <td className="px-4 py-3">
                          <span className="inline-flex items-center gap-2">
                            <RetailerLogo retailer={row.competidor} className="h-5 w-5" />
                            <span>{row.competidor}</span>
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-semibold tabular-premium">{toCurrency(row.precio)}</td>
                        <td className={`px-4 py-3 text-right tabular-premium font-medium ${isMoreExpensive ? "text-success" : "text-destructive"}`}>
                          {row.diff > 0 ? "+" : ""}{toCurrency(row.diff)}
                        </td>
                        <td className={`px-4 py-3 text-right tabular-premium font-medium ${isMoreExpensive ? "text-success" : "text-destructive"}`}>
                          {row.diffPct > 0 ? "+" : ""}{row.diffPct.toFixed(1)}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  );
}
