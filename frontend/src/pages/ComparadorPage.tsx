import { Dispatch, SetStateAction, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { X, SlidersHorizontal } from "lucide-react";

import { KPICard, PageHeader, SkeletonCard, SkeletonChart } from "@/components/SharedUI";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ComparatorOffer, fetchAllRecords, toCurrency } from "@/lib/observatorio-api";
import RetailerLogo from "@/components/RetailerLogo";
import BrandSegmentedControl from "@/components/BrandSegmentedControl";

type BrandTab = "Samsung" | "Apple";

const OFFER_LABELS: Record<string, string> = {
  renting_no_insurance: "Renting SIN seguro",
  renting_with_insurance: "Renting CON seguro",
  financing_max_term: "Financiacion",
  cash: "Compra al contado",
};

const OFFER_BADGES: Record<string, string> = {
  renting_no_insurance: "badge-neutral",
  renting_with_insurance: "badge-neutral",
  financing_max_term: "badge-up",
  cash: "badge-up",
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
  "El Corte InglÃ©s",
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

interface TotalCostRow {
  competidor: string;
  total_cost: number;
}

const CHART_MARGIN = { top: 34, right: 12, left: 0, bottom: 12 };
const CHART_Y_AXIS_WIDTH = 56;
const CHART_AXIS_LABEL_PADDING_LEFT = CHART_MARGIN.left + CHART_Y_AXIS_WIDTH;
const CHART_AXIS_LABEL_PADDING_RIGHT = CHART_MARGIN.right;

export default function ComparadorPage() {
  const [brand, setBrand] = useState<BrandTab>("Samsung");
  const [selectedModality, setSelectedModality] = useState("renting_with_insurance");
  const [selectedModel, setSelectedModel] = useState("all");
  const [selectedCapacity, setSelectedCapacity] = useState("all");
  const [selectedTerm, setSelectedTerm] = useState("all");
  const [selectedRetailers, setSelectedRetailers] = useState<Set<string>>(new Set());
  const [generated, setGenerated] = useState(false);

  const recordsQuery = useQuery({
    queryKey: ["comparador-v10-records", brand],
    queryFn: () => fetchAllRecords({ brand }),
  });

  const allRows = recordsQuery.data ?? [];

  const retailers = useMemo(() => {
    const unique = Array.from(new Set(allRows.map((row) => row.competidor).filter(Boolean)));
    return unique.sort(retailerSort);
  }, [allRows]);
  const retailerKey = retailers.join("|");

  const models = useMemo(() => {
    const unique = Array.from(new Set(allRows.map((row) => row.modelo).filter(Boolean)));
    return unique.sort((a, b) => a.localeCompare(b, "es"));
  }, [allRows]);

  const capacities = useMemo(() => {
    const values = allRows
      .filter((row) => (selectedModel === "all" ? true : row.modelo === selectedModel))
      .filter((row) => row.modalidad === selectedModality)
      .map((row) => row.capacidad)
      .filter((value): value is number => typeof value === "number");
    return Array.from(new Set(values)).sort((a, b) => a - b);
  }, [allRows, selectedModel, selectedModality]);

  const terms = useMemo(() => {
    if (!HAS_TERMS.has(selectedModality)) {
      return [] as number[];
    }

    const values = allRows
      .filter((row) => row.modalidad === selectedModality)
      .filter((row) => (selectedModel === "all" ? true : row.modelo === selectedModel))
      .filter((row) => (selectedCapacity === "all" ? true : String(row.capacidad) === selectedCapacity))
      .map((row) => row.term_months)
      .filter((value): value is number => typeof value === "number");

    return Array.from(new Set(values)).sort((a, b) => a - b);
  }, [allRows, selectedModality, selectedModel, selectedCapacity]);

  useEffect(() => {
    setSelectedRetailers(new Set(retailers));
    setGenerated(false);
    setSelectedModel("all");
    setSelectedCapacity("all");
    setSelectedTerm("all");
    setSelectedModality("renting_with_insurance");
  }, [brand, retailerKey]);

  useEffect(() => {
    if (selectedModel !== "all" && !models.includes(selectedModel)) {
      setSelectedModel("all");
    }
  }, [models, selectedModel]);

  useEffect(() => {
    if (selectedCapacity !== "all" && !capacities.some((value) => String(value) === selectedCapacity)) {
      setSelectedCapacity("all");
    }
  }, [capacities, selectedCapacity]);

  useEffect(() => {
    if (!HAS_TERMS.has(selectedModality)) {
      if (selectedTerm !== "all") {
        setSelectedTerm("all");
      }
      return;
    }

    if (selectedTerm !== "all" && !terms.some((value) => String(value) === selectedTerm)) {
      setSelectedTerm("all");
    }
  }, [selectedModality, selectedTerm, terms]);

  const kpiRows = useMemo(() => {
    return allRows.filter((row) => {
      if (!selectedRetailers.has(row.competidor)) {
        return false;
      }
      if (selectedModel !== "all" && row.modelo !== selectedModel) {
        return false;
      }
      return typeof row.precio_valor === "number" && Number.isFinite(row.precio_valor) && row.precio_valor >= 0;
    });
  }, [allRows, selectedModel, selectedRetailers]);

  const filteredRows = useMemo(() => {
    return allRows.filter((row) => {
      if (!selectedRetailers.has(row.competidor)) {
        return false;
      }
      if (row.modalidad !== selectedModality) {
        return false;
      }
      if (selectedModel !== "all" && row.modelo !== selectedModel) {
        return false;
      }
      if (selectedCapacity !== "all" && String(row.capacidad) !== selectedCapacity) {
        return false;
      }
      if (HAS_TERMS.has(selectedModality) && selectedTerm !== "all" && String(row.term_months) !== selectedTerm) {
        return false;
      }
      return typeof row.precio_valor === "number" && Number.isFinite(row.precio_valor) && row.precio_valor >= 0;
    });
  }, [allRows, selectedRetailers, selectedModality, selectedModel, selectedCapacity, selectedTerm]);

  const chartRows = useMemo(() => {
    const bestByRetailer = new Map<string, number>();

    for (const row of filteredRows) {
      if (typeof row.precio_valor !== "number") {
        continue;
      }
      const current = bestByRetailer.get(row.competidor);
      if (current === undefined || row.precio_valor < current) {
        bestByRetailer.set(row.competidor, row.precio_valor);
      }
    }

    const labels = Array.from(bestByRetailer.keys()).sort(retailerSort);
    return labels.map((retailer) => ({
      competidor: retailer,
      precio: bestByRetailer.get(retailer) ?? 0,
      fill: CHART_COLORS[retailer] ?? "#7a8193",
    }));
  }, [filteredRows]);

  const tableRows = useMemo(() => {
    return [...filteredRows].sort((a, b) => {
      const left = typeof a.precio_valor === "number" ? a.precio_valor : Number.POSITIVE_INFINITY;
      const right = typeof b.precio_valor === "number" ? b.precio_valor : Number.POSITIVE_INFINITY;
      return left - right;
    });
  }, [filteredRows]);

  const isRentingMode =
    generated &&
    HAS_TERMS.has(selectedModality) &&
    selectedModality !== "financing_max_term";

  const showTotalCostChart =
    isRentingMode &&
    selectedModel !== "all" &&
    selectedTerm !== "all";

  const totalCostRows = useMemo(() => {
    if (!showTotalCostChart) {
      return [] as TotalCostRow[];
    }

    const minTotalCost = new Map<string, number>();
    for (const row of filteredRows) {
      if (row.modalidad === "financing_max_term") {
        continue;
      }
      if (typeof row.precio_valor !== "number" || typeof row.term_months !== "number") {
        continue;
      }
      const totalCost = row.precio_valor * row.term_months;
      const current = minTotalCost.get(row.competidor);
      if (current === undefined || totalCost < current) {
        minTotalCost.set(row.competidor, totalCost);
      }
    }

    return Array.from(minTotalCost.entries())
      .sort((a, b) => retailerSort(a[0], b[0]))
      .map(([competidor, total_cost]) => ({ competidor, total_cost }));
  }, [filteredRows, showTotalCostChart]);

  const santanderPvp = useMemo(() => {
    if (!showTotalCostChart) {
      return null;
    }

    const row = allRows.find((item) => {
      if (item.competidor !== "Santander Boutique") {
        return false;
      }
      if (item.modalidad !== "cash") {
        return false;
      }
      if (item.modelo !== selectedModel) {
        return false;
      }
      if (selectedCapacity !== "all" && String(item.capacidad) !== selectedCapacity) {
        return false;
      }
      return typeof item.precio_valor === "number";
    });

    return row?.precio_valor ?? null;
  }, [allRows, showTotalCostChart, selectedModel, selectedCapacity]);

  const mainChartCeiling = useMemo(() => {
    const maxValue = chartRows.reduce((max, row) => Math.max(max, row.precio), 0);
    return computeChartCeiling(maxValue);
  }, [chartRows]);

  const totalCostChartCeiling = useMemo(() => {
    const maxValue = totalCostRows.reduce((max, row) => Math.max(max, row.total_cost), 0);
    return computeChartCeiling(maxValue);
  }, [totalCostRows]);

  const comparadorSummary = useMemo(() => {
    const prices = filteredRows
      .map((r) => r.precio_valor)
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
    if (!prices.length) return null;
    const avg = prices.reduce((s, v) => s + v, 0) / prices.length;
    const cheapestRow = filteredRows.reduce<ComparatorOffer | null>((best, row) => {
      if (typeof row.precio_valor !== "number") return best;
      if (!best || row.precio_valor < (best.precio_valor ?? Infinity)) return row;
      return best;
    }, null);
    return {
      count: filteredRows.length,
      avg,
      min: Math.min(...prices),
      max: Math.max(...prices),
      cheapestRetailer: cheapestRow?.competidor ?? null,
    };
  }, [filteredRows]);

  const selectedModelCount = useMemo(() => {
    return new Set(kpiRows.map((row) => row.modelo)).size;
  }, [kpiRows]);

  const bestRentingRow = useMemo(() => {
    const rentingRows = kpiRows.filter((row) => row.modalidad === "renting_no_insurance" || row.modalidad === "renting_with_insurance");
    return pickBestPrice(rentingRows);
  }, [kpiRows]);

  const bestCashRow = useMemo(() => {
    const cashRows = kpiRows.filter((row) => row.modalidad === "cash");
    return pickBestPrice(cashRows);
  }, [kpiRows]);

  const kpiCards = [
    {
      label: "Modelo seleccionado",
      value: selectedModel === "all" ? "Todos los modelos" : selectedModel,
      meta: `${selectedModelCount} modelo(s) visibles`,
    },
    {
      label: "Mejor precio renting",
      value: bestRentingRow ? toCurrency(bestRentingRow.precio_valor) : "-",
      meta: bestRentingRow
        ? `${bestRentingRow.competidor} - ${formatCapacity(bestRentingRow.capacidad)}${bestRentingRow.term_months ? ` - ${bestRentingRow.term_months}m` : ""}`
        : "Sin oferta de renting",
    },
    {
      label: "Mejor precio contado",
      value: bestCashRow ? toCurrency(bestCashRow.precio_valor) : "-",
      meta: bestCashRow ? `${bestCashRow.competidor} - ${formatCapacity(bestCashRow.capacidad)}` : "Sin oferta al contado",
    },
    {
      label: "Retailers activos",
      value: String(new Set(kpiRows.map((row) => row.competidor)).size),
      meta: `${kpiRows.length} oferta(s) detectadas`,
    },
  ];

  const retailerLabel =
    selectedRetailers.size === 0
      ? "Sin retailers"
      : selectedRetailers.size === retailers.length
        ? "Todos los retailers"
        : `${selectedRetailers.size} de ${retailers.length} retailers`;

  return (
    <>
      <PageHeader
        title="Observatorio"
        subtitle="Comparativa de precios por modelo, capacidad y modalidad de pago"
      />

      <div className="mb-5">
        <BrandSegmentedControl value={brand} onChange={(b) => setBrand(b as BrandTab)} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
        {kpiCards.map((kpi) => (
          <div key={kpi.label} className="glass-card rounded-xl p-4 animate-fade-in">
            <KPICard label={kpi.label} value={kpi.value} change={0} trend="neutral" />
            <p className="text-xs text-muted-foreground mt-2">{kpi.meta}</p>
          </div>
        ))}
      </div>

      <div className="glass-card rounded-xl p-5 mb-3 animate-fade-in">
        {/* Fila 1: Modalidad / Modelo / Capacidad */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Modalidad</p>
            <Select value={selectedModality} onValueChange={setSelectedModality}>
              <SelectTrigger>
                <SelectValue placeholder="Modalidad" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="renting_no_insurance">Renting SIN seguro</SelectItem>
                <SelectItem value="renting_with_insurance">Renting CON seguro</SelectItem>
                <SelectItem value="financing_max_term">Financiacion</SelectItem>
                <SelectItem value="cash">Compra al contado</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Modelo</p>
            <Select value={selectedModel} onValueChange={setSelectedModel}>
              <SelectTrigger>
                <SelectValue placeholder="Modelo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos los modelos</SelectItem>
                {models.map((model) => (
                  <SelectItem key={model} value={model}>{model}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Capacidad</p>
            <Select value={selectedCapacity} onValueChange={setSelectedCapacity}>
              <SelectTrigger>
                <SelectValue placeholder="Capacidad" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas las capacidades</SelectItem>
                {capacities.map((capacity) => (
                  <SelectItem key={capacity} value={String(capacity)}>{formatCapacity(capacity)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Fila 2: Plazo / Retailers / Botón */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Plazo</p>
            <Select value={selectedTerm} onValueChange={setSelectedTerm} disabled={!HAS_TERMS.has(selectedModality)}>
              <SelectTrigger>
                <SelectValue placeholder="Plazo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos los plazos</SelectItem>
                {terms.map((term) => (
                  <SelectItem key={term} value={String(term)}>{term} meses</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Retailers</p>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="w-full justify-start font-normal">
                  {retailerLabel}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-72 max-h-[360px] overflow-auto">
                <DropdownMenuLabel>Seleccion de retailers</DropdownMenuLabel>
                <DropdownMenuItem onSelect={(e) => { e.preventDefault(); setSelectedRetailers(new Set(retailers)); }}>
                  Seleccionar todos
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={(e) => { e.preventDefault(); setSelectedRetailers(new Set()); }}>
                  Limpiar
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                {retailers.map((retailer) => (
                  <DropdownMenuCheckboxItem
                    key={retailer}
                    checked={selectedRetailers.has(retailer)}
                    onCheckedChange={(value) => toggleRetailer(retailer, Boolean(value), setSelectedRetailers)}
                    onSelect={(e) => e.preventDefault()}
                  >
                    {retailer}
                  </DropdownMenuCheckboxItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          <div className="flex items-end">
            <Button className="w-full" onClick={() => setGenerated(true)}>
              Generar comparativa
            </Button>
          </div>
        </div>
      </div>

      {/* Chips de filtros activos */}
      {(selectedModality !== "renting_with_insurance" || selectedModel !== "all" || selectedCapacity !== "all" || (HAS_TERMS.has(selectedModality) && selectedTerm !== "all") || selectedRetailers.size < retailers.length) && (
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <span className="text-xs text-muted-foreground flex items-center gap-1"><SlidersHorizontal className="h-3 w-3" />Filtros:</span>
          {selectedModality !== "renting_with_insurance" && (
            <button onClick={() => setSelectedModality("renting_with_insurance")} className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/8 px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/15 transition-colors">
              {OFFER_LABELS[selectedModality] ?? selectedModality}<X className="h-3 w-3" />
            </button>
          )}
          {selectedModel !== "all" && (
            <button onClick={() => setSelectedModel("all")} className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/8 px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/15 transition-colors">
              {selectedModel}<X className="h-3 w-3" />
            </button>
          )}
          {selectedCapacity !== "all" && (
            <button onClick={() => setSelectedCapacity("all")} className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/8 px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/15 transition-colors">
              {formatCapacity(Number(selectedCapacity))}<X className="h-3 w-3" />
            </button>
          )}
          {HAS_TERMS.has(selectedModality) && selectedTerm !== "all" && (
            <button onClick={() => setSelectedTerm("all")} className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/8 px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/15 transition-colors">
              {selectedTerm} meses<X className="h-3 w-3" />
            </button>
          )}
          {selectedRetailers.size < retailers.length && (
            <button onClick={() => setSelectedRetailers(new Set(retailers))} className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/8 px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/15 transition-colors">
              {selectedRetailers.size}/{retailers.length} retailers<X className="h-3 w-3" />
            </button>
          )}
        </div>
      )}

      {!generated ? (
        <div className="glass-card rounded-xl p-12 flex flex-col items-center justify-center text-center animate-fade-in">
          <div className="h-14 w-14 rounded-full bg-muted/60 flex items-center justify-center mb-4">
            <SlidersHorizontal className="h-6 w-6 text-muted-foreground" />
          </div>
          <p className="text-base font-semibold text-foreground mb-1">Configura tu comparativa</p>
          <p className="text-sm text-muted-foreground max-w-sm">
            Selecciona la modalidad, modelo y capacidad que quieres analizar y pulsa <strong>Generar comparativa</strong>.
          </p>
        </div>
      ) : null}

      {recordsQuery.isLoading ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
            {[0, 1, 2, 3].map((i) => <SkeletonCard key={i} />)}
          </div>
          <SkeletonChart />
        </>
      ) : null}
      {recordsQuery.error ? <p className="text-sm text-destructive mb-4">Error cargando datos del comparador.</p> : null}

      {generated ? (
        <>
          <div className="glass-card rounded-xl p-6 mb-6 animate-fade-in">
            <h3 className="text-sm font-semibold text-foreground mb-4">Comparativa de precios por retailer</h3>
            {chartRows.length === 0 ? (
              <p className="text-sm text-muted-foreground">No hay ofertas para los filtros seleccionados.</p>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={340}>
                  <BarChart data={chartRows} margin={CHART_MARGIN}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="competidor" tick={false} axisLine={false} tickLine={false} height={8} />
                    <YAxis tick={{ fontSize: 11 }} width={CHART_Y_AXIS_WIDTH} domain={[0, mainChartCeiling]} />
                    <Tooltip formatter={(value) => toCurrency(typeof value === "number" ? value : null)} />
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
                  <div
                    className="min-w-[760px]"
                    style={{
                      paddingLeft: `${CHART_AXIS_LABEL_PADDING_LEFT}px`,
                      paddingRight: `${CHART_AXIS_LABEL_PADDING_RIGHT}px`,
                    }}
                  >
                    <div
                      className="grid items-start gap-3"
                      style={{ gridTemplateColumns: `repeat(${Math.max(chartRows.length, 1)}, minmax(0, 1fr))` }}
                    >
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

          {isRentingMode ? (
            <div className="glass-card rounded-xl p-6 mb-6 animate-fade-in">
              <h3 className="text-sm font-semibold text-foreground mb-4">Coste total renting vs PVP contado Santander</h3>
              {!showTotalCostChart ? (
                <p className="text-sm text-muted-foreground">Selecciona un modelo y un plazo concreto para generar esta comparativa.</p>
              ) : totalCostRows.length === 0 ? (
                <p className="text-sm text-muted-foreground">No hay datos de renting para el filtro actual.</p>
              ) : (
                <>
                  <ResponsiveContainer width="100%" height={340}>
                    <BarChart data={totalCostRows} margin={CHART_MARGIN}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="competidor" tick={false} axisLine={false} tickLine={false} height={8} />
                      <YAxis tick={{ fontSize: 11 }} width={CHART_Y_AXIS_WIDTH} domain={[0, totalCostChartCeiling]} />
                      <Tooltip formatter={(value) => toCurrency(typeof value === "number" ? value : null)} />
                      {typeof santanderPvp === "number" ? (
                        <ReferenceLine
                          y={santanderPvp}
                          stroke="hsl(var(--destructive))"
                          strokeDasharray="6 4"
                          label={{
                            value: `PVP ${toCurrency(santanderPvp)}`,
                            position: "insideTopRight",
                            fill: "hsl(var(--destructive))",
                            fontSize: 11,
                            fontWeight: 700,
                          }}
                        />
                      ) : null}
                      <Bar dataKey="total_cost" fill="hsl(var(--primary))" radius={[12, 12, 0, 0]}>
                        <LabelList
                          dataKey="total_cost"
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
                    <div
                      className="min-w-[760px]"
                      style={{
                        paddingLeft: `${CHART_AXIS_LABEL_PADDING_LEFT}px`,
                        paddingRight: `${CHART_AXIS_LABEL_PADDING_RIGHT}px`,
                      }}
                    >
                      <div
                        className="grid items-start gap-3"
                        style={{ gridTemplateColumns: `repeat(${Math.max(totalCostRows.length, 1)}, minmax(0, 1fr))` }}
                      >
                        {totalCostRows.map((entry) => (
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
          ) : null}

          <div className="glass-card rounded-xl overflow-hidden animate-fade-in">
            <h3 className="text-sm font-semibold text-foreground px-5 pt-5 pb-3">Ofertas filtradas (ordenadas por precio)</h3>
            {tableRows.length === 0 ? (
              <div className="px-5 pb-5 text-sm text-muted-foreground">No hay ofertas para los filtros seleccionados.</div>
            ) : (
              <div className="overflow-auto max-h-[70vh]">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-card sticky top-0 z-10">
                      <th className="table-header text-left px-4 py-3">Retailer</th>
                      <th className="table-header text-left px-4 py-3">Modelo</th>
                      <th className="table-header text-left px-4 py-3">Capacidad</th>
                      <th className="table-header text-left px-4 py-3">Modalidad</th>
                      <th className="table-header text-left px-4 py-3">Plazo</th>
                      <th className="table-header text-right px-4 py-3">Precio</th>
                      <th className="table-header text-right px-4 py-3">Coste Total</th>
                      <th className="table-header text-left px-4 py-3">Stock</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tableRows.map((row, index) => {
                      const isSantander = row.competidor === "Santander Boutique";
                      return (
                        <tr
                          key={`${row.competidor}-${row.modelo}-${row.capacidad}-${row.modalidad}-${row.term_months}-${index}`}
                          className={`border-b border-border/50 hover:bg-muted/20 transition-colors ${isSantander ? "bg-destructive/5" : ""}`}
                        >
                          <td className="px-4 py-3">
                            <div className="inline-flex items-center gap-2">
                              <RetailerLogo retailer={row.competidor} className="h-5 w-5" />
                              <span>{row.competidor}</span>
                            </div>
                          </td>
                          <td className="px-4 py-3">{row.modelo}</td>
                          <td className="px-4 py-3">{formatCapacity(row.capacidad)}</td>
                          <td className="px-4 py-3">
                            <span className={OFFER_BADGES[row.modalidad] ?? "badge-neutral"}>
                              {OFFER_LABELS[row.modalidad] ?? row.modalidad}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            {HAS_TERMS.has(row.modalidad) && typeof row.term_months === "number" ? `${row.term_months} meses` : "-"}
                          </td>
                          <td className="px-4 py-3 text-right font-semibold">{toCurrency(row.precio_valor)}</td>
                          <td className="px-4 py-3 text-right">{toCurrency(totalCostForRow(row))}</td>
                          <td className="px-4 py-3">{stockLabel(row.disponibilidad)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {comparadorSummary && (
            <div className="sticky bottom-4 mt-4 animate-fade-in">
              <div className="glass-card rounded-xl border border-border/70 px-5 py-3 flex flex-wrap items-center gap-x-6 gap-y-2 backdrop-blur-md shadow-lg">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Resumen</p>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-muted-foreground">Ofertas</span>
                  <span className="text-xs font-semibold text-foreground">{comparadorSummary.count.toLocaleString("es-ES")}</span>
                </div>
                <div className="h-3 w-px bg-border" />
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-muted-foreground">Más barato</span>
                  <span className="text-xs font-semibold text-success">
                    {toCurrency(comparadorSummary.min)}
                    {comparadorSummary.cheapestRetailer ? ` (${comparadorSummary.cheapestRetailer})` : ""}
                  </span>
                </div>
                <div className="h-3 w-px bg-border" />
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-muted-foreground">Precio medio</span>
                  <span className="text-xs font-semibold text-foreground">{toCurrency(comparadorSummary.avg)}</span>
                </div>
                <div className="h-3 w-px bg-border" />
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-muted-foreground">Rango</span>
                  <span className="text-xs font-semibold text-foreground">
                    {toCurrency(comparadorSummary.min)} – {toCurrency(comparadorSummary.max)}
                  </span>
                </div>
              </div>
            </div>
          )}
        </>
      ) : null}
    </>
  );
}

function toggleRetailer(
  retailer: string,
  checked: boolean,
  setSelectedRetailers: Dispatch<SetStateAction<Set<string>>>,
): void {
  setSelectedRetailers((current) => {
    const next = new Set(current);
    if (checked) {
      next.add(retailer);
    } else {
      next.delete(retailer);
    }
    return next;
  });
}

function retailerSort(a: string, b: string): number {
  const left = RETAILER_ORDER.indexOf(a);
  const right = RETAILER_ORDER.indexOf(b);
  const leftPos = left === -1 ? 999 : left;
  const rightPos = right === -1 ? 999 : right;
  return leftPos - rightPos || a.localeCompare(b, "es");
}

function formatCapacity(value: number | null): string {
  if (typeof value !== "number") {
    return "-";
  }
  if (value >= 1024) {
    const tb = value / 1024;
    return `${tb % 1 === 0 ? tb.toFixed(0) : tb.toFixed(1)} TB`;
  }
  return `${value} GB`;
}

function pickBestPrice(rows: ComparatorOffer[]): ComparatorOffer | null {
  const priced = rows.filter((row) => typeof row.precio_valor === "number");
  if (priced.length === 0) {
    return null;
  }

  return priced.reduce((best, row) => {
    if ((row.precio_valor ?? Number.POSITIVE_INFINITY) < (best.precio_valor ?? Number.POSITIVE_INFINITY)) {
      return row;
    }
    return best;
  });
}

function unitForRow(row: ComparatorOffer): string {
  if (row.modalidad === "cash") {
    return row.moneda || "EUR";
  }
  return `${row.moneda || "EUR"}/mes`;
}

function totalCostForRow(row: ComparatorOffer): number | null {
  if (row.precio_valor == null) return null;
  if (row.modalidad === "cash") return row.precio_valor;
  if (typeof row.term_months === "number" && row.term_months > 0) {
    return Math.round(row.precio_valor * row.term_months * 100) / 100;
  }
  return null;
}

function stockLabel(value: boolean | null): string {
  if (value === null) {
    return "-";
  }
  return value ? "Disponible" : "No disponible";
}

function formatBarPrice(value: number): string {
  if (!Number.isFinite(value)) {
    return "-";
  }
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: value >= 1000 ? 0 : 2,
  }).format(value);
}

function computeChartCeiling(maxValue: number): number {
  if (!Number.isFinite(maxValue) || maxValue <= 0) {
    return 1;
  }
  return Math.ceil(maxValue * 1.18);
}


