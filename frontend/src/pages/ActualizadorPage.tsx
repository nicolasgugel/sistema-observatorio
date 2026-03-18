import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarClock, Database, History, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";

import { EmptyState, PageHeader, SkeletonCard } from "@/components/SharedUI";
import { fetchPublishInfo, fetchSnapshots, type PublishInfoResponse, type SnapshotSummary } from "@/lib/observatorio-api";

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "Sin datos";
  return new Date(value).toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getRelativeBadge(value: string | null | undefined): "HOY" | "AYER" | null {
  if (!value) return null;
  const now = new Date();
  const date = new Date(value);
  const diffDays = Math.floor((Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) - Date.UTC(date.getFullYear(), date.getMonth(), date.getDate())) / 86400000);
  if (diffDays === 0) return "HOY";
  if (diffDays === 1) return "AYER";
  return null;
}

function formatSchedule(schedule: PublishInfoResponse["schedule"] | undefined): string {
  if (!schedule) return "Sin programacion";
  const cron = schedule.cron ?? "manual";
  const timezone = schedule.timezone || "UTC";
  return `${cron} · ${timezone}`;
}

function SnapshotCard({ snapshot }: { snapshot: SnapshotSummary }) {
  const badge = snapshot.is_current ? "ACTUAL" : getRelativeBadge(snapshot.created_at);

  return (
    <article
      className={`rounded-2xl border p-4 transition-colors ${
        snapshot.is_current ? "border-primary/25 bg-primary/5" : "border-border/70 bg-background/40"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-foreground">{formatDateTime(snapshot.created_at)}</p>
            {badge ? <span className="badge-neutral text-[10px]">{badge}</span> : null}
            <span className="badge-neutral text-[10px] uppercase">{snapshot.mode}</span>
          </div>
          <p className="mt-1 truncate text-xs text-muted-foreground">{snapshot.id}</p>
        </div>

        <div className="text-right text-xs text-muted-foreground">
          <p className="font-medium text-foreground">{snapshot.record_count} registros</p>
          <p>{snapshot.competitors.length} competidores</p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-border/70 px-2.5 py-1 text-[11px] text-muted-foreground">
          Scope: {snapshot.brand_scope}
        </span>
        <Link
          to={snapshot.is_current ? "/visualizador" : `/visualizador?snapshot=${encodeURIComponent(snapshot.id)}`}
          className="rounded-full border border-border/70 px-2.5 py-1 text-[11px] font-medium text-foreground transition-colors hover:bg-muted"
        >
          Abrir en tabla
        </Link>
      </div>
    </article>
  );
}

export default function ActualizadorPage() {
  const publishInfoQuery = useQuery({
    queryKey: ["table-publish-info"],
    queryFn: fetchPublishInfo,
  });

  const snapshotsQuery = useQuery({
    queryKey: ["table-snapshots"],
    queryFn: fetchSnapshots,
  });

  const snapshots = snapshotsQuery.data?.snapshots ?? [];
  const currentSnapshot = useMemo(() => snapshots.find((snapshot) => snapshot.is_current) ?? null, [snapshots]);
  const visibleHistory = useMemo(() => snapshots.slice(0, 12), [snapshots]);

  const publishedAt = publishInfoQuery.data?.published_at ?? currentSnapshot?.created_at ?? null;
  const publishedSnapshotId = publishInfoQuery.data?.current_snapshot_id ?? currentSnapshot?.id ?? null;
  const recordCount = publishInfoQuery.data?.record_count ?? currentSnapshot?.record_count ?? 0;
  const competitorsCount = publishInfoQuery.data?.competitors.length ?? currentSnapshot?.competitors.length ?? 0;

  return (
    <>
      <PageHeader
        title="Actualizacion diaria"
        subtitle="Vista publica de snapshots publicados en Vercel. En produccion se muestra el historico publicado, no los jobs live del updater."
      />

      {publishInfoQuery.isLoading || snapshotsQuery.isLoading ? (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4 mb-8">
          {[0, 1, 2, 3].map((index) => (
            <SkeletonCard key={index} />
          ))}
        </div>
      ) : null}

      {publishInfoQuery.error || snapshotsQuery.error ? (
        <p className="mb-4 text-sm text-destructive">No se pudo cargar la publicacion actual.</p>
      ) : null}

      {publishInfoQuery.data || currentSnapshot ? (
        <div className="mb-8 grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
          <section className="glass-card p-5 animate-fade-in">
            <div className="flex items-center gap-2">
              <CalendarClock className="h-4 w-4 text-primary" />
              <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Publicado</p>
            </div>
            <p className="mt-3 text-xl font-semibold text-foreground">{formatDateTime(publishedAt)}</p>
            <p className="mt-1 text-xs text-muted-foreground">{getRelativeBadge(publishedAt) ?? "Historico"}</p>
          </section>

          <section className="glass-card p-5 animate-fade-in">
            <div className="flex items-center gap-2">
              <RefreshCw className="h-4 w-4 text-info" />
              <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Snapshot actual</p>
            </div>
            <p className="mt-3 break-all text-sm font-semibold text-foreground">{publishedSnapshotId ?? "Sin snapshot"}</p>
            <p className="mt-1 text-xs text-muted-foreground">{publishInfoQuery.data?.mode ?? currentSnapshot?.mode ?? "Sin modo"}</p>
          </section>

          <section className="glass-card p-5 animate-fade-in">
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-success" />
              <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Dataset</p>
            </div>
            <p className="mt-3 text-xl font-semibold text-foreground">{recordCount}</p>
            <p className="mt-1 text-xs text-muted-foreground">{competitorsCount} competidores en la publicacion vigente</p>
          </section>

          <section className="glass-card p-5 animate-fade-in">
            <div className="flex items-center gap-2">
              <History className="h-4 w-4 text-chart-neutral" />
              <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Programacion</p>
            </div>
            <p className="mt-3 text-sm font-semibold text-foreground">{formatSchedule(publishInfoQuery.data?.schedule)}</p>
            <p className="mt-1 text-xs text-muted-foreground">{snapshots.length} snapshots visibles en historico</p>
          </section>
        </div>
      ) : null}

      <section className="glass-card p-6 animate-fade-in">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-foreground">Historial publicado</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              La app publica de Vercel ensena snapshots publicados. Los jobs del updater siguen deshabilitados en este despliegue.
            </p>
          </div>
          <Link
            to="/visualizador"
            className="rounded-full border border-border/70 px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted"
          >
            Abrir version actual
          </Link>
        </div>

        {visibleHistory.length === 0 ? (
          <EmptyState
            icon={History}
            title="No hay snapshots publicados"
            description="Cuando Vercel publique un snapshot nuevo, aparecera aqui automaticamente."
          />
        ) : (
          <div className="space-y-3">
            {visibleHistory.map((snapshot) => (
              <SnapshotCard key={snapshot.id} snapshot={snapshot} />
            ))}
          </div>
        )}
      </section>
    </>
  );
}
