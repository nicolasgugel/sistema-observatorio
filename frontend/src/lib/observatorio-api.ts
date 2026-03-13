export type Brand = "Samsung" | "Apple" | "all";
export type RunMode = "bootstrap" | "manual" | "targeted" | "full";
export type RunStatus = "queued" | "running" | "completed" | "failed";

const ENV_API_BASE = import.meta.env.VITE_API_BASE_URL as string | undefined;
const LOCAL_API_BASE = "http://127.0.0.1:8000/api";
const EDITOR_TOKEN_STORAGE_KEY = "observatorio_editor_token.v1";

function isLocalRuntime(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  const host = window.location.hostname;
  return host === "127.0.0.1" || host === "localhost";
}

const DEFAULT_API_BASE = import.meta.env.PROD
  ? (isLocalRuntime() ? LOCAL_API_BASE : "/api")
  : LOCAL_API_BASE;

export const API_BASE = (ENV_API_BASE && ENV_API_BASE.trim().length > 0 ? ENV_API_BASE : DEFAULT_API_BASE).replace(
  /\/$/,
  "",
);

export function buildApiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${normalizedPath}`;
}

function resolveEditorToken(token?: string): string {
  if (token && token.trim()) {
    return token.trim();
  }
  if (typeof window === "undefined") {
    return "";
  }
  return window.sessionStorage.getItem(EDITOR_TOKEN_STORAGE_KEY)?.trim() ?? "";
}

function withEditorToken(headers: HeadersInit | undefined, token?: string): HeadersInit {
  const editorToken = resolveEditorToken(token);
  if (!editorToken) {
    return headers ?? {};
  }
  return {
    ...(headers ?? {}),
    "X-Observatorio-Editor-Token": editorToken,
  };
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed (${response.status})`);
  }

  return (await response.json()) as T;
}

export function getEditorToken(): string {
  return resolveEditorToken();
}

export function setEditorToken(token: string): void {
  if (typeof window === "undefined") {
    return;
  }
  const normalized = token.trim();
  if (!normalized) {
    window.sessionStorage.removeItem(EDITOR_TOKEN_STORAGE_KEY);
    return;
  }
  window.sessionStorage.setItem(EDITOR_TOKEN_STORAGE_KEY, normalized);
}

export function clearEditorToken(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.sessionStorage.removeItem(EDITOR_TOKEN_STORAGE_KEY);
}

export interface FiltersMetaResponse {
  competitors: string[];
  models: string[];
  capacities: number[];
  modalities: Array<{ value: string; label: string }>;
  availability: boolean[];
  price_min: number | null;
  price_max: number | null;
  latest_timestamp: string;
  total_records: number;
}

export interface ComparatorOffer {
  timestamp_extraccion: string;
  competidor: string;
  url_producto: string;
  marca: string;
  modelo: string;
  capacidad: number | null;
  modalidad: string;
  modalidad_label: string;
  precio_texto: string;
  precio_valor: number | null;
  moneda: string;
  disponibilidad: boolean | null;
  term_months: number | null;
  diferencial_vs_santander: number | null;
  diferencial_pct_vs_santander: number | null;
}

export interface ComparatorGroup {
  modelo: string;
  capacidad: number | null;
  modalidad: string;
  modalidad_label: string;
  mejor_competidor: string | null;
  mejor_precio: number | null;
  precio_santander: number | null;
  ahorro_vs_santander: number | null;
  ofertas: ComparatorOffer[];
}

export interface ComparatorResponse {
  groups: ComparatorGroup[];
  bars: Array<{
    producto: string;
    modalidad: string;
    modalidad_label: string;
    mejor_precio: number;
    santander: number | null;
    gap_vs_santander: number | null;
  }>;
  total_groups: number;
}

export interface DashboardResponse {
  kpis: {
    registros: number;
    productos_unicos: number;
    competidores_activos: number;
    timestamp_ultima_extraccion: string;
  };
  coverage_by_competitor: Array<{
    competidor: string;
    matched_models: number;
    total_base_models: number;
    coverage_pct: number;
  }>;
  avg_price_by_modality: Array<{
    modalidad: string;
    modalidad_label: string;
    precio_medio: number;
    muestras: number;
  }>;
  gap_vs_santander: Array<{
    competidor: string;
    gap_medio: number;
    muestras: number;
  }>;
  price_by_competitor: Array<{
    competidor: string;
    precio_medio: number;
    precio_min: number;
    precio_max: number;
    muestras: number;
  }>;
  price_by_model: Array<{
    modelo: string;
    precio_medio: number;
    muestras: number;
  }>;
  temporal_evolution: Array<{
    timestamp: string;
    competidor: string;
    precio_medio: number;
  }>;
}

export interface ComparatorFilters {
  brand: Brand;
  competitors?: string[];
  models?: string[];
  capacities?: number[];
  modalities?: string[];
  minPrice?: number | null;
  maxPrice?: number | null;
  availability?: boolean | null;
  search?: string;
}

function buildComparatorParams(filters: ComparatorFilters): URLSearchParams {
  const params = new URLSearchParams();
  params.set("brand", filters.brand);

  filters.competitors?.forEach((value) => params.append("competitors", value));
  filters.models?.forEach((value) => params.append("models", value));
  filters.capacities?.forEach((value) => params.append("capacities", String(value)));
  filters.modalities?.forEach((value) => params.append("modalities", value));

  if (typeof filters.minPrice === "number") {
    params.set("min_price", String(filters.minPrice));
  }

  if (typeof filters.maxPrice === "number") {
    params.set("max_price", String(filters.maxPrice));
  }

  if (typeof filters.availability === "boolean") {
    params.set("availability", String(filters.availability));
  }

  if (filters.search && filters.search.trim()) {
    params.set("search", filters.search.trim());
  }

  return params;
}

export function toCurrency(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "-";
  }
  return `${value.toFixed(2)} EUR`;
}

export function toPct(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "-";
  }
  return `${value.toFixed(2)}%`;
}

export async function fetchHealth(): Promise<{ status: string }> {
  return fetchJson("/health");
}

export async function fetchFiltersMeta(brand: Brand): Promise<FiltersMetaResponse> {
  return fetchJson(`/intelligence/filters?brand=${encodeURIComponent(brand)}`);
}

export async function fetchComparator(filters: ComparatorFilters): Promise<ComparatorResponse> {
  const params = buildComparatorParams(filters);
  return fetchJson(`/intelligence/comparator?${params.toString()}`);
}

export async function fetchDashboard(filters: ComparatorFilters): Promise<DashboardResponse> {
  const params = buildComparatorParams(filters);
  return fetchJson(`/intelligence/dashboard?${params.toString()}`);
}

export interface RecordsResponse {
  count: number;
  total: number;
  page: number;
  page_size: number;
  rows: ComparatorOffer[];
}

export async function fetchRecords(
  filters: ComparatorFilters,
  page = 1,
  pageSize = 200,
  sortBy = "precio_valor",
  sortDir: "asc" | "desc" = "asc",
): Promise<RecordsResponse> {
  const params = buildComparatorParams(filters);
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  params.set("sort_by", sortBy);
  params.set("sort_dir", sortDir);
  return fetchJson(`/intelligence/records?${params.toString()}`);
}

export async function fetchAllRecords(
  filters: ComparatorFilters,
  pageSize = 500,
  sortBy = "precio_valor",
  sortDir: "asc" | "desc" = "asc",
): Promise<ComparatorOffer[]> {
  const allRows: ComparatorOffer[] = [];
  let page = 1;
  let total = Number.POSITIVE_INFINITY;

  while (allRows.length < total && page <= 100) {
    const response = await fetchRecords(filters, page, pageSize, sortBy, sortDir);
    allRows.push(...response.rows);
    total = response.total;

    if (response.rows.length === 0) {
      break;
    }
    page += 1;
  }

  return allRows;
}

export interface ScrapingSeed {
  brand: string;
  model: string;
  capacity_gb: number | null;
  device_type: string;
}

export interface ScrapingSeedsResponse {
  count: number;
  seeds: ScrapingSeed[];
}

export async function fetchScrapingSeeds(brand: "Samsung" | "Apple"): Promise<ScrapingSeedsResponse> {
  return fetchJson(`/scraping/seeds?brand=${encodeURIComponent(brand)}`);
}

export async function fetchScrapingCompetitors(): Promise<{ competitors: string[] }> {
  return fetchJson("/scraping/competitors");
}

export interface ScrapingJobPayload {
  brand: "Samsung" | "Apple";
  competitor: string;
  products: Array<{ model: string; capacity_gb: number | null }>;
  max_products: number;
  headed: boolean;
  scope: "full_catalog" | "focused_iphone17_s25";
}

export interface PersistedRunResponse {
  id: string;
  mode: RunMode | string;
  origin: string;
  status: RunStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  return_code: number | null;
  error: string | null;
  snapshot_id: string | null;
  record_count: number | null;
  brand_scope: string;
  competitors: string[];
  products: Array<{ model: string; capacity_gb: number | null }>;
  triggered_by: string;
  command: string[];
  request: Record<string, unknown>;
  logs_count: number;
}

export interface RunLogEvent {
  type: "log";
  index: number;
  ts: string;
  level: string;
  message: string;
}

export interface RunLogsResponse {
  events: RunLogEvent[];
  done: boolean;
  next_after: number;
}

export async function createScrapingJob(payload: ScrapingJobPayload, token?: string): Promise<PersistedRunResponse> {
  return fetchJson("/scraping/jobs", {
    method: "POST",
    headers: withEditorToken(undefined, token),
    body: JSON.stringify(payload),
  });
}

export async function fetchScrapingJob(jobId: string, token?: string): Promise<PersistedRunResponse> {
  return fetchJson(`/scraping/jobs/${encodeURIComponent(jobId)}`, {
    headers: withEditorToken(undefined, token),
  });
}

export async function fetchScrapingJobLogs(jobId: string, after = 0, token?: string): Promise<RunLogsResponse> {
  return fetchJson(`/scraping/jobs/${encodeURIComponent(jobId)}/logs?after=${after}`, {
    headers: withEditorToken(undefined, token),
  });
}

export interface TableRowsResponse {
  count: number;
  source: string;
  snapshot_id: string;
  rows: Array<Record<string, unknown>>;
}

export async function fetchTableRows(snapshotId = "current"): Promise<TableRowsResponse> {
  return fetchJson(`/table/rows?snapshot_id=${encodeURIComponent(snapshotId)}`);
}

export interface TableMetaResponse {
  count: number;
  retailers: string[];
  brands: string[];
  offer_types: string[];
  latest_extracted_at: string;
  source: string;
  snapshot_id: string;
}

export async function fetchTableMeta(snapshotId = "current"): Promise<TableMetaResponse> {
  return fetchJson(`/table/meta?snapshot_id=${encodeURIComponent(snapshotId)}`);
}

export interface SnapshotSummary {
  id: string;
  label: string;
  created_at: string;
  run_id: string | null;
  mode: RunMode | string;
  is_current: boolean;
  csv_path: string;
  json_path: string;
  html_path: string;
  metadata_path: string;
  record_count: number;
  brand_scope: string;
  competitors: string[];
}

export interface SnapshotDetail extends SnapshotSummary {
  metadata: {
    id?: string;
    created_at?: string;
    run_id?: string | null;
    mode?: string;
    brand_scope?: string;
    competitors?: string[];
    record_count?: number;
    files?: Record<string, string>;
  };
  files: Record<string, string>;
  products: Array<{ model: string; capacity_gb: number | null }>;
}

export async function fetchSnapshots(): Promise<{ count: number; snapshots: SnapshotSummary[] }> {
  return fetchJson("/table/snapshots");
}

export async function fetchSnapshotDetail(snapshotId: string): Promise<SnapshotDetail> {
  return fetchJson(`/table/snapshots/${encodeURIComponent(snapshotId)}`);
}

export interface PublishInfoResponse {
  current_snapshot_id: string | null;
  published_at: string | null;
  mode: string | null;
  brand_scope: string;
  competitors: string[];
  record_count: number;
  schedule: {
    kind: string;
    cron: string | null;
    timezone: string;
  };
}

export async function fetchPublishInfo(): Promise<PublishInfoResponse> {
  return fetchJson("/table/publish-info");
}

export function buildExportUrl(options?: { fmt?: "csv" | "json"; snapshotId?: string; brand?: Brand }): string {
  const params = new URLSearchParams();
  params.set("fmt", options?.fmt ?? "csv");
  params.set("snapshot_id", options?.snapshotId ?? "current");
  params.set("brand", options?.brand ?? "all");
  return buildApiUrl(`/intelligence/export?${params.toString()}`);
}

export interface UpdateRunRequest {
  brand: Brand;
  max_products: number;
  competitors: string | null;
  scope: string;
  headed: boolean;
}

export interface UpdaterStatusResponse {
  active_run: PersistedRunResponse | null;
  schedule: {
    enabled: boolean;
    interval_minutes: number;
    next_run_at: string | null;
    run_request: UpdateRunRequest;
  };
  recent_runs: PersistedRunResponse[];
}

export async function runFullRefresh(payload: UpdateRunRequest, token?: string): Promise<PersistedRunResponse> {
  return fetchJson("/intelligence/updater/run", {
    method: "POST",
    headers: withEditorToken(undefined, token),
    body: JSON.stringify(payload),
  });
}

export async function fetchUpdaterStatus(token?: string): Promise<UpdaterStatusResponse> {
  return fetchJson("/intelligence/updater/status", {
    headers: withEditorToken(undefined, token),
  });
}

export async function fetchUpdaterRun(runId: string, token?: string): Promise<PersistedRunResponse> {
  return fetchJson(`/intelligence/updater/runs/${encodeURIComponent(runId)}`, {
    headers: withEditorToken(undefined, token),
  });
}

export async function fetchUpdaterRunLogs(runId: string, after = 0, token?: string): Promise<RunLogsResponse> {
  return fetchJson(`/intelligence/updater/runs/${encodeURIComponent(runId)}/logs?after=${after}`, {
    headers: withEditorToken(undefined, token),
  });
}

// ── Agent ──────────────────────────────────────────────────

export interface AgentEvidence {
  competidor?: string;
  modelo?: string;
  capacidad?: number | null;
  modalidad?: string;
  precio_valor?: number | null;
  timestamp_extraccion?: string;
  url_producto?: string;
  matched_models?: number;
  total_base_models?: number;
  coverage_pct?: number;
}

export interface AgentQueryResponse {
  brand: string;
  question: string;
  answer: string;
  evidence: AgentEvidence[];
  intent: "coverage" | "cheapest" | "summary" | "no_data";
}

export async function queryAgent(question: string, brand: Brand = "Samsung"): Promise<AgentQueryResponse> {
  return fetchJson("/intelligence/agent/query", {
    method: "POST",
    body: JSON.stringify({ question, brand }),
  });
}
