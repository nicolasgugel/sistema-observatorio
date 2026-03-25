import { startTransition, useDeferredValue, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpDown, CalendarDays, Download, Search, SlidersHorizontal } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import BrandIdentity from "@/components/BrandIdentity";
import RetailerLogo from "@/components/RetailerLogo";
import { EmptyState, PageHeader, SkeletonTable } from "@/components/SharedUI";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  buildExportUrl,
  fetchSnapshots,
  fetchTableMeta,
  fetchTableRows,
} from "@/lib/observatorio-api";

type SortKey =
  | "retailer"
  | "model"
  | "offer_type"
  | "price_value"
  | "capacity_gb"
  | "brand"
  | "extracted_at";

interface TableRow {
  retailer: string;
  brand: string;
  model: string;
  capacity_gb: number | null;
  product_code: string;
  offer_type: string;
  term_months: number | null;
  price_value: number | null;
  price_text: string;
  in_stock: boolean | null;
  extracted_at: string;
}

const PAGE_SIZE = 80;
const HAS_TERM_MODALITIES = new Set(["renting_no_insurance", "renting_with_insurance", "financing_max_term"]);

export default function VisualizadorPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const snapshotId = searchParams.get("snapshot") || "current";

  const [search, setSearch] = useState("");
  const [retailerFilter, setRetailerFilter] = useState("all");
  const [brandFilter, setBrandFilter] = useState("all");
  const [modalityFilter, setModalityFilter] = useState("all");
  const [modelFilter, setModelFilter] = useState("all");
  const [termFilter, setTermFilter] = useState("all");
  const [sortKey, setSortKey] = useState<SortKey>("extracted_at");
  const [sortAsc, setSortAsc] = useState(false);
  const [page, setPage] = useState(1);

  const deferredSearch = useDeferredValue(search);

  const snapshotsQuery = useQuery({
    queryKey: ["table-snapshots"],
    queryFn: fetchSnapshots,
    refetchInterval: 60000,
  });

  const currentSnapshot = useMemo(() => {
    const snapshots = snapshotsQuery.data?.snapshots ?? [];
    return snapshots.find((snapshot) => snapshot.is_current) ?? null;
  }, [snapshotsQuery.data]);

  const resolvedSnapshotKey = snapshotId === "current" ? (currentSnapshot?.id ?? "current") : snapshotId;

  const rowsQuery = useQuery({
    queryKey: ["table-rows", snapshotId, resolvedSnapshotKey],
    queryFn: () => fetchTableRows(snapshotId),
    refetchOnMount: "always",
  });

  const metaQuery = useQuery({
    queryKey: ["table-meta", snapshotId, resolvedSnapshotKey],
    queryFn: () => fetchTableMeta(snapshotId),
    refetchOnMount: "always",
  });

  const rows = useMemo(() => normalizeTableRows(rowsQuery.data?.rows ?? []), [rowsQuery.data]);

  const historicalSnapshots = useMemo(() => {
    const snapshots = snapshotsQuery.data?.snapshots ?? [];
    return snapshots.filter((snapshot) => !snapshot.is_current).sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );
  }, [snapshotsQuery.data]);

  const activeSnapshotLabel = useMemo(() => {
    if (snapshotId === "current") return null;
    const match = historicalSnapshots.find((s) => s.id === snapshotId);
    return match ? formatSnapshotDate(match.created_at) : snapshotId;
  }, [snapshotId, historicalSnapshots]);

  const modelOptions = useMemo(() => {
    const models = rows
      .filter((row) => (brandFilter === "all" ? true : row.brand === brandFilter))
      .filter((row) => (retailerFilter === "all" ? true : row.retailer === retailerFilter))
      .filter((row) => (modalityFilter === "all" ? true : row.offer_type === modalityFilter))
      .map((row) => row.model)
      .filter((value) => value && value.trim().length > 0);
    return Array.from(new Set(models)).sort((a, b) => a.localeCompare(b, "es"));
  }, [rows, brandFilter, retailerFilter, modalityFilter]);

  const termOptions = useMemo(() => {
    if (!HAS_TERM_MODALITIES.has(modalityFilter)) {
      return [] as number[];
    }
    const terms = rows
      .filter((row) => (brandFilter === "all" ? true : row.brand === brandFilter))
      .filter((row) => (retailerFilter === "all" ? true : row.retailer === retailerFilter))
      .filter((row) => row.offer_type === modalityFilter)
      .filter((row) => (modelFilter === "all" ? true : row.model === modelFilter))
      .map((row) => row.term_months)
      .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
    return Array.from(new Set(terms)).sort((a, b) => a - b);
  }, [rows, brandFilter, retailerFilter, modalityFilter, modelFilter]);

  useEffect(() => {
    setPage(1);
  }, [snapshotId]);

  useEffect(() => {
    const retailers = metaQuery.data?.retailers ?? [];
    if (retailerFilter !== "all" && !retailers.includes(retailerFilter)) {
      setRetailerFilter("all");
    }
  }, [metaQuery.data?.retailers, retailerFilter]);

  useEffect(() => {
    const brands = metaQuery.data?.brands ?? [];
    if (brandFilter !== "all" && !brands.includes(brandFilter)) {
      setBrandFilter("all");
    }
  }, [brandFilter, metaQuery.data?.brands]);

  useEffect(() => {
    const offerTypes = metaQuery.data?.offer_types ?? [];
    if (modalityFilter !== "all" && !offerTypes.includes(modalityFilter)) {
      setModalityFilter("all");
    }
  }, [metaQuery.data?.offer_types, modalityFilter]);

  useEffect(() => {
    if (modelFilter !== "all" && !modelOptions.includes(modelFilter)) {
      setModelFilter("all");
      setPage(1);
    }
  }, [modelFilter, modelOptions]);

  useEffect(() => {
    if (!HAS_TERM_MODALITIES.has(modalityFilter) && termFilter !== "all") {
      setTermFilter("all");
      setPage(1);
      return;
    }
    if (termFilter !== "all" && !termOptions.some((value) => String(value) === termFilter)) {
      setTermFilter("all");
      setPage(1);
    }
  }, [modalityFilter, termFilter, termOptions]);

  const filteredRows = useMemo(() => {
    const needle = deferredSearch.toLowerCase().trim();

    return rows
      .filter((row) => (retailerFilter === "all" ? true : row.retailer === retailerFilter))
      .filter((row) => (brandFilter === "all" ? true : row.brand === brandFilter))
      .filter((row) => (modalityFilter === "all" ? true : row.offer_type === modalityFilter))
      .filter((row) => (modelFilter === "all" ? true : row.model === modelFilter))
      .filter((row) => (termFilter === "all" ? true : String(row.term_months) === termFilter))
      .filter((row) => {
        if (!needle) {
          return true;
        }
        const haystack = `${row.retailer} ${row.brand} ${row.model} ${row.product_code} ${row.offer_type} ${row.capacity_gb ?? ""} ${row.term_months ?? ""}`.toLowerCase();
        return haystack.includes(needle);
      })
      .sort((a, b) => compareRows(a, b, sortKey, sortAsc));
  }, [rows, retailerFilter, brandFilter, modalityFilter, modelFilter, termFilter, deferredSearch, sortKey, sortAsc]);

  const pageCount = Math.max(Math.ceil(filteredRows.length / PAGE_SIZE), 1);
  const pageRows = filteredRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const summaryStats = useMemo(() => {
    const prices = filteredRows
      .map((r) => r.price_value)
      .filter((v): v is number => v !== null);
    if (!prices.length) return null;
    const avg = prices.reduce((s, v) => s + v, 0) / prices.length;
    return {
      count: filteredRows.length,
      avg,
      min: Math.min(...prices),
      max: Math.max(...prices),
    };
  }, [filteredRows]);

  const setSort = (nextKey: SortKey) => {
    if (sortKey === nextKey) {
      setSortAsc(!sortAsc);
      return;
    }
    setSortKey(nextKey);
    setSortAsc(true);
  };

  const selectSnapshot = (value: string) => {
    startTransition(() => {
      if (value === "current") {
        setSearchParams({});
        return;
      }
      setSearchParams({ snapshot: value });
    });
  };

  return (
    <>
      <PageHeader
        title="Tabla de Precios"
        subtitle={
          activeSnapshotLabel
            ? `Versión del ${activeSnapshotLabel}`
            : "Precios vigentes de todos los competidores"
        }
        actions={
          <div className="flex items-center gap-2">
            <Select value={snapshotId} onValueChange={selectSnapshot}>
              <SelectTrigger className="w-[240px] h-9 text-sm">
                <CalendarDays className="h-3.5 w-3.5 mr-1.5 text-muted-foreground flex-shrink-0" />
                <SelectValue placeholder="Versión de la tabla" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="current">
                  <span className="flex items-center gap-2">
                    <span>Versión actual</span>
                    <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                      {getSnapshotRelativeBadge(currentSnapshot?.created_at) ?? "ACTUAL"}
                    </span>
                  </span>
                </SelectItem>
                {historicalSnapshots.map((snapshot) => (
                  <SelectItem key={snapshot.id} value={snapshot.id}>
                    <span className="flex items-center gap-2">
                      <span>{formatSnapshotDate(snapshot.created_at)}</span>
                      {getSnapshotRelativeBadge(snapshot.created_at) && (
                        <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                          {getSnapshotRelativeBadge(snapshot.created_at)}
                        </span>
                      )}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Button asChild size="sm">
              <a href={buildExportUrl({ fmt: "csv", snapshotId, brand: "all" })}>
                <Download className="h-4 w-4" />
                Descargar CSV
              </a>
            </Button>
          </div>
        }
      />

      <div className="flex flex-wrap gap-3 mb-6 animate-fade-in">
        <div className="relative flex-1 min-w-[260px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Buscar por modelo, competidor..."
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
            className="pl-9"
          />
        </div>

        <Select
          value={retailerFilter}
          onValueChange={(value) => {
            setRetailerFilter(value);
            setPage(1);
          }}
        >
          <SelectTrigger className="w-[220px]">
            <SelectValue placeholder="Competidor" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos los competidores</SelectItem>
            {metaQuery.data?.retailers.map((retailer) => (
              <SelectItem key={retailer} value={retailer}>
                <span className="inline-flex items-center gap-2">
                  <RetailerLogo retailer={retailer} className="h-5 w-7" />
                  <span>{retailer}</span>
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={brandFilter}
          onValueChange={(value) => {
            setBrandFilter(value);
            setPage(1);
          }}
        >
          <SelectTrigger className="w-[160px]">
            {brandFilter === "all" ? (
              <span className="text-sm">Todas las marcas</span>
            ) : brandFilter === "Samsung" || brandFilter === "Apple" ? (
              <BrandIdentity brand={brandFilter} />
            ) : (
              <span className="text-sm">{brandFilter}</span>
            )}
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas las marcas</SelectItem>
            {metaQuery.data?.brands.map((brand) => (
              <SelectItem key={brand} value={brand}>
                {brand === "Samsung" || brand === "Apple" ? <BrandIdentity brand={brand} /> : brand}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={modalityFilter}
          onValueChange={(value) => {
            setModalityFilter(value);
            setPage(1);
          }}
        >
          <SelectTrigger className="w-[220px]">
            <SelectValue placeholder="Modalidad" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas las modalidades</SelectItem>
            {metaQuery.data?.offer_types.map((offerType) => (
              <SelectItem key={offerType} value={offerType}>
                {offerType}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={termFilter}
          onValueChange={(value) => {
            setTermFilter(value);
            setPage(1);
          }}
          disabled={!HAS_TERM_MODALITIES.has(modalityFilter)}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Plazo" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos los plazos</SelectItem>
            {termOptions.map((term) => (
              <SelectItem key={term} value={String(term)}>
                {term} meses
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={modelFilter}
          onValueChange={(value) => {
            setModelFilter(value);
            setPage(1);
          }}
        >
          <SelectTrigger className="w-[280px]">
            <SelectValue placeholder="Modelo" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos los modelos</SelectItem>
            {modelOptions.map((model) => (
              <SelectItem key={model} value={model}>
                {model}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {rowsQuery.error ? <p className="text-sm text-destructive mb-4">No se pudieron cargar los datos.</p> : null}

      {rowsQuery.isLoading ? (
        <SkeletonTable rows={8} />
      ) : (
      <div className="glass-card rounded-xl overflow-auto max-h-[70vh] animate-fade-in">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border bg-card sticky top-0 z-10">
              <SortableHead label="Competidor" onClick={() => setSort("retailer")} />
              <SortableHead label="Modelo" onClick={() => setSort("model")} />
              <SortableHead label="Modalidad" onClick={() => setSort("offer_type")} />
              <th className="table-header text-left px-5 py-3">Plazo</th>
              <SortableHead label="Precio" onClick={() => setSort("price_value")} />
              <SortableHead label="Capacidad" onClick={() => setSort("capacity_gb")} />
              <SortableHead label="Marca" onClick={() => setSort("brand")} />
              <th className="table-header text-left px-5 py-3">Estado</th>
              <SortableHead label="Actualizado" onClick={() => setSort("extracted_at")} />
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, index) => {
              const stockBadge = row.in_stock === null ? null : row.in_stock ? "badge-up" : "badge-down";
              const stockLabel = row.in_stock === null ? "-" : row.in_stock ? "Disponible" : "No disponible";
              return (
                <tr key={`${row.retailer}-${row.model}-${index}`} className="border-b border-border/50 hover:bg-muted/20 transition-colors">
                  <td className="px-5 py-3.5 text-sm text-muted-foreground">
                    {row.retailer ? (
                      <span className="inline-flex items-center gap-2">
                        <RetailerLogo retailer={row.retailer} className="h-5 w-7" />
                        <span>{row.retailer}</span>
                      </span>
                    ) : (
                      "-"
                    )}
                  </td>
                  <td className="px-5 py-3.5 text-sm">
                    <p className="font-medium text-foreground">{row.model || "-"}</p>
                    {row.product_code ? <p className="text-[11px] font-mono text-muted-foreground">{row.product_code}</p> : null}
                  </td>
                  <td className="px-5 py-3.5 text-sm text-muted-foreground">{row.offer_type || "-"}</td>
                  <td className="px-5 py-3.5 text-sm text-muted-foreground">{formatTerm(row.term_months)}</td>
                  <td className="px-5 py-3.5 text-sm font-semibold text-foreground">
                    {typeof row.price_value === "number" ? `${row.price_value.toFixed(2)} EUR` : row.price_text || "-"}
                  </td>
                  <td className="px-5 py-3.5 text-sm text-muted-foreground">{row.capacity_gb ? `${row.capacity_gb}GB` : "-"}</td>
                  <td className="px-5 py-3.5 text-sm text-muted-foreground">{row.brand || "-"}</td>
                  <td className="px-5 py-3.5">{stockBadge ? <span className={stockBadge}>{stockLabel}</span> : <span>{stockLabel}</span>}</td>
                  <td className="px-5 py-3.5 text-xs text-muted-foreground">{formatIso(row.extracted_at)}</td>
                </tr>
              );
            })}
            {pageRows.length === 0 ? (
              <tr>
                <td colSpan={9}>
                  <EmptyState
                    icon={SlidersHorizontal}
                    title="Sin resultados"
                    description="No hay filas que coincidan con los filtros activos. Prueba a ampliar la búsqueda."
                  />
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      )}

      <div className="flex items-center justify-between mt-3">
        <p className="text-xs text-muted-foreground">
          {filteredRows.length} filas · página {page} de {pageCount}
        </p>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Anterior
          </Button>
          <Button size="sm" variant="outline" disabled={page >= pageCount} onClick={() => setPage(page + 1)}>
            Siguiente
          </Button>
        </div>
      </div>

      {summaryStats && (
        <div className="sticky bottom-4 mt-4 animate-fade-in">
          <div className="glass-card rounded-xl border border-border/70 px-5 py-3 flex flex-wrap items-center gap-x-6 gap-y-2 backdrop-blur-md shadow-lg">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Resumen</p>
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-muted-foreground">Filas</span>
              <span className="text-xs font-semibold text-foreground">{summaryStats.count.toLocaleString("es-ES")}</span>
            </div>
            <div className="h-3 w-px bg-border" />
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-muted-foreground">Precio medio</span>
              <span className="text-xs font-semibold text-foreground">{summaryStats.avg.toFixed(2)} €</span>
            </div>
            <div className="h-3 w-px bg-border" />
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-muted-foreground">Mínimo</span>
              <span className="text-xs font-semibold text-success">{summaryStats.min.toFixed(2)} €</span>
            </div>
            <div className="h-3 w-px bg-border" />
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-muted-foreground">Máximo</span>
              <span className="text-xs font-semibold text-foreground">{summaryStats.max.toFixed(2)} €</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function normalizeTableRows(rows: Array<Record<string, unknown>>): TableRow[] {
  return rows.map((row) => ({
    retailer: String(row.retailer ?? ""),
    brand: String(row.brand ?? ""),
    model: String(row.model ?? ""),
    capacity_gb: parseMaybeNumber(row.capacity_gb),
    product_code: String(row.product_code ?? ""),
    offer_type: String(row.offer_type ?? ""),
    term_months: parseMaybeNumber(row.term_months),
    price_value: parseMaybeNumber(row.price_value),
    price_text: String(row.price_text ?? ""),
    in_stock: parseMaybeBool(row.in_stock),
    extracted_at: String(row.extracted_at ?? ""),
  }));
}

function parseMaybeNumber(value: unknown): number | null {
  if (typeof value === "number") {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
  }
  return null;
}

function parseMaybeBool(value: unknown): boolean | null {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "string") {
    const normalized = value.toLowerCase();
    if (["true", "1", "yes", "si"].includes(normalized)) {
      return true;
    }
    if (["false", "0", "no"].includes(normalized)) {
      return false;
    }
  }
  return null;
}

function compareRows(a: TableRow, b: TableRow, key: SortKey, asc: boolean): number {
  const dir = asc ? 1 : -1;
  const aValue = a[key];
  const bValue = b[key];

  if (typeof aValue === "number" || typeof bValue === "number") {
    const left = typeof aValue === "number" ? aValue : -Infinity;
    const right = typeof bValue === "number" ? bValue : -Infinity;
    return (left - right) * dir;
  }

  return String(aValue ?? "").localeCompare(String(bValue ?? "")) * dir;
}

function formatSnapshotDate(isoDate: string): string {
  if (!isoDate) return "-";
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return isoDate;
  return date.toLocaleDateString("es-ES", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function getSnapshotRelativeBadge(isoDate: string | null | undefined): "HOY" | "AYER" | null {
  if (!isoDate) {
    return null;
  }

  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  const targetDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const today = new Date();
  const todayDay = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const diffDays = Math.round((todayDay.getTime() - targetDay.getTime()) / 86400000);

  if (diffDays === 0) {
    return "HOY";
  }
  if (diffDays === 1) {
    return "AYER";
  }
  return null;
}

function formatIso(value: string): string {
  if (!value) {
    return "-";
  }
  return value.slice(0, 16).replace("T", " ");
}

function formatTerm(value: number | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }
  return `${Math.round(value)} meses`;
}

function SortableHead({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <th className="table-header text-left px-5 py-3 cursor-pointer hover:text-foreground transition-colors select-none" onClick={onClick}>
      <span className="inline-flex items-center gap-1">
        {label}
        <ArrowUpDown className="h-3 w-3" />
      </span>
    </th>
  );
}
