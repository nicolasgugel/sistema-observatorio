import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CalendarDays, Clock3, Download, History, RefreshCw, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/SharedUI";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  buildExportUrl,
  fetchPublishInfo,
  fetchSnapshotDetail,
  fetchSnapshots,
  SnapshotSummary,
} from "@/lib/observatorio-api";

const DAILY_CRON = "0 6 * * *";
const DAILY_TIMEZONE = "UTC";

export default function ActualizadorPage() {
  const [selectedSnapshotId, setSelectedSnapshotId] = useState("current");

  const publishInfoQuery = useQuery({
    queryKey: ["publish-info"],
    queryFn: fetchPublishInfo,
  });

  const snapshotsQuery = useQuery({
    queryKey: ["table-snapshots"],
    queryFn: fetchSnapshots,
  });

  const selectedSnapshotQuery = useQuery({
    queryKey: ["table-snapshot-detail", selectedSnapshotId],
    queryFn: () => fetchSnapshotDetail(selectedSnapshotId),
    enabled: selectedSnapshotId !== "current",
  });

  const snapshots = snapshotsQuery.data?.snapshots ?? [];
  const currentSnapshot = useMemo(
    () => snapshots.find((snapshot) => snapshot.is_current) ?? snapshots[0] ?? null,
    [snapshots],
  );
  const selectedSnapshot =
    selectedSnapshotId === "current"
      ? currentSnapshot
      : snapshots.find((snapshot) => snapshot.id === selectedSnapshotId) ?? null;
  const selectedSnapshotDetail = selectedSnapshotId === "current" ? currentSnapshot : selectedSnapshotQuery.data ?? selectedSnapshot;

  const scheduleLabel = publishInfoQuery.data?.schedule.cron ?? DAILY_CRON;
  const timezoneLabel = publishInfoQuery.data?.schedule.timezone ?? DAILY_TIMEZONE;
  const latestPublishedAt = publishInfoQuery.data?.published_at ?? currentSnapshot?.created_at ?? "";
  const latestSnapshotId = publishInfoQuery.data?.current_snapshot_id ?? currentSnapshot?.id ?? "";
  const latestRecordCount = publishInfoQuery.data?.record_count ?? currentSnapshot?.record_count ?? 0;
  const latestCompetitors = publishInfoQuery.data?.competitors ?? currentSnapshot?.competitors ?? [];

  return (
    <>
      <PageHeader
        title="Actualizacion Diaria"
        subtitle="El scraping se ejecuta automaticamente una vez al dia y publica snapshots historicos consultables"
        actions={
          <Button asChild>
            <a href={buildExportUrl({ fmt: "csv", snapshotId: "current", brand: "all" })}>
              <Download className="h-4 w-4" />
              Descargar vigente
            </a>
          </Button>
        }
      />

      <div className="grid grid-cols-1 xl:grid-cols-[1.08fr_0.92fr] gap-6">
        <section className="glass-card rounded-2xl border border-border/70 overflow-hidden animate-fade-in">
          <div className="px-6 py-5 bg-gradient-to-r from-emerald-50 via-background to-sky-50 border-b border-border/60">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Cadencia automatica</p>
                <h2 className="text-xl font-semibold text-foreground mt-1">Refresh diario programado</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  La app publica un nuevo snapshot cada dia y conserva historico para consulta en Visualizador.
                </p>
              </div>
              <Badge className="gap-2 px-3 py-1">
                <ShieldCheck className="h-3.5 w-3.5" />
                Modo automatico
              </Badge>
            </div>
          </div>

          <div className="p-6 space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <MetricCard
                icon={CalendarDays}
                label="Frecuencia"
                value="1 vez al dia"
                detail={`Cron ${scheduleLabel}`}
              />
              <MetricCard
                icon={Clock3}
                label="Zona horaria"
                value={timezoneLabel}
                detail="La ejecucion usa el branch principal"
              />
              <MetricCard
                icon={RefreshCw}
                label="Ultima publicacion"
                value={formatIso(latestPublishedAt)}
                detail={latestSnapshotId || "Sin snapshot publicado"}
              />
              <MetricCard
                icon={History}
                label="Dataset vigente"
                value={`${latestRecordCount} registros`}
                detail={latestCompetitors.join(", ") || "Competidores soportados"}
              />
            </div>

            <div className="rounded-2xl border border-border/70 bg-muted/20 px-5 py-4">
              <p className="text-sm font-medium text-foreground">Politica operativa</p>
              <p className="mt-2 text-sm text-muted-foreground">
                No hay refresco manual expuesto en la app publica. Si una corrida diaria falla, el snapshot vigente anterior se
                mantiene intacto y el historico publicado sigue accesible.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              {latestSnapshotId ? (
                <Button asChild>
                  <Link to={`/visualizador?snapshot=${latestSnapshotId}`}>
                    Abrir snapshot actual
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
              ) : null}
              <Button asChild variant="outline">
                <Link to="/visualizador">
                  Abrir historico
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
            </div>
          </div>
        </section>

        <section className="glass-card rounded-2xl border border-border/70 overflow-hidden animate-fade-in">
          <div className="px-6 py-5 border-b border-border/60">
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Snapshots publicados</p>
            <h2 className="text-xl font-semibold text-foreground mt-1">Ultimas versiones disponibles</h2>
          </div>

          <div className="p-6 space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">Seleccionar snapshot</label>
              <Select value={selectedSnapshotId} onValueChange={setSelectedSnapshotId}>
                <SelectTrigger>
                  <SelectValue placeholder="Selecciona snapshot" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="current">Actual publicado</SelectItem>
                  {snapshots.map((snapshot) => (
                    <SelectItem key={snapshot.id} value={snapshot.id}>
                      {snapshot.is_current ? `Actual | ${snapshot.label}` : snapshot.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <SnapshotPreview snapshot={selectedSnapshotDetail} />

            <div className="max-h-[320px] overflow-auto rounded-xl border border-border/70">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border bg-muted/20">
                    <th className="table-header text-left px-4 py-3">Fecha</th>
                    <th className="table-header text-left px-4 py-3">Modo</th>
                    <th className="table-header text-left px-4 py-3">Scope</th>
                    <th className="table-header text-left px-4 py-3">Registros</th>
                  </tr>
                </thead>
                <tbody>
                  {snapshots.map((snapshot) => (
                    <tr key={snapshot.id} className="border-b border-border/50 hover:bg-muted/20 transition-colors">
                      <td className="px-4 py-3 text-xs text-muted-foreground">{formatIso(snapshot.created_at)}</td>
                      <td className="px-4 py-3 text-sm text-foreground">{snapshot.mode}</td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{snapshot.brand_scope}</td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{snapshot.record_count}</td>
                    </tr>
                  ))}
                  {snapshots.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="px-4 py-5 text-sm text-muted-foreground">
                        Aun no hay snapshots historicos publicados.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: typeof CalendarDays;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <article className="rounded-2xl border border-border/70 bg-background/70 px-5 py-4">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/8 text-primary">
          <Icon className="h-4.5 w-4.5" />
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
          <p className="text-sm font-semibold text-foreground">{value}</p>
        </div>
      </div>
      <p className="mt-3 text-xs text-muted-foreground">{detail}</p>
    </article>
  );
}

function SnapshotPreview({ snapshot }: { snapshot: SnapshotSummary | null | undefined }) {
  if (!snapshot) {
    return (
      <div className="rounded-2xl border border-border/70 bg-muted/20 px-5 py-4 text-sm text-muted-foreground">
        No hay detalle disponible para el snapshot seleccionado.
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-border/70 bg-muted/20 px-5 py-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">Snapshot seleccionado</p>
          <p className="text-sm font-semibold text-foreground">{snapshot.id}</p>
        </div>
        <Badge variant={snapshot.is_current ? "default" : "outline"}>{snapshot.is_current ? "Actual" : "Historico"}</Badge>
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <MiniMetric label="Fecha" value={formatIso(snapshot.created_at)} />
        <MiniMetric label="Modo" value={snapshot.mode} />
        <MiniMetric label="Scope" value={snapshot.brand_scope} />
        <MiniMetric label="Registros" value={String(snapshot.record_count)} />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button asChild size="sm">
          <Link to={`/visualizador?snapshot=${snapshot.id}`}>
            Ver en visualizador
            <ArrowRight className="h-4 w-4" />
          </Link>
        </Button>
        <Button asChild size="sm" variant="outline">
          <a href={buildExportUrl({ fmt: "csv", snapshotId: snapshot.id, brand: "all" })}>
            <Download className="h-4 w-4" />
            Descargar CSV
          </a>
        </Button>
      </div>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border/60 bg-background/70 px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm font-medium text-foreground">{value || "-"}</p>
    </div>
  );
}

function formatIso(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return value.slice(0, 16).replace("T", " ");
}
