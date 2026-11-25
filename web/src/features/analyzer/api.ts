// Typed client for change impact analysis (plans/change-impact/plan.md, "Contracts").
const BASE = "/api/v1/analyzer/impact";

export type Source = "demo" | "live";
export type ChangeKind = "interface_down" | "device_down";
export type Risk = "low" | "medium" | "high";
export type ItemStatus = "critical" | "warning" | "neutral";

export interface Node {
  id: string;
  type: string;
  role: string;
  vendor: string | null;
  site: string | null;
  interfaces: string[];
  endpoints: number;
  services: string[];
}

export interface Link {
  id: string;
  a: { device: string; interface: string | null };
  b: { device: string; interface: string | null };
  capacity_mbps: number | null;
  util_pct: number | null;
  hourly_util_pct?: number[] | null;
}

export interface Topology {
  source: Source;
  as_of: string;
  nodes: Node[];
  links: Link[];
}

export interface Change {
  kind: ChangeKind;
  device: string;
  interface: string | null;
}

export interface Affected {
  kind: "node" | "endpoints" | "service" | "link";
  id: string;
  label: string;
  detail: string;
  status: ItemStatus;
}

export interface LinkLoad {
  link: string;
  label: string;
  util_before: number | null;
  util_after: number | null;
}

export interface Reroute {
  link: string;
  via: string[];
  load_mbps: number | null;
  after: LinkLoad[];
}

export interface Spof {
  kind: "node" | "link";
  id: string;
  label: string;
}

export interface Window {
  start_hour: number;
  end_hour: number;
  avg_util_pct: number;
}

export interface ReportSummary {
  id: string;
  created_at: string;
  title: string;
  risk: Risk;
  source: Source;
}

export interface Report extends ReportSummary {
  data_as_of: string;
  change: Change;
  summary: string;
  affected: Affected[];
  reroutes: Reroute[];
  new_spofs: Spof[];
  maintenance_window: Window | null;
  rollback: string;
  warnings: string[];
  unknowns: string[];
  data_used: string[];
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    /** The server's reason, when it sent one (e.g. why a parse failed). */
    readonly detail?: string,
  ) {
    super(message);
  }
}

// FastAPI sends {"detail": "..."}; the plan also allows {"detail": {"detail": "..."}}.
function reason(body: unknown): string | undefined {
  const d = (body as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return d;
  const inner = (d as { detail?: unknown; message?: unknown } | null)?.detail;
  return typeof inner === "string" ? inner : undefined;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null);
    throw new ApiError(res.status, `Request failed (${res.status})`, reason(body));
  }
  return (await res.json()) as T;
}

export const getTopology = () => request<Topology>("/topology");

export const parseChange = (text: string) =>
  request<{ change: Change }>("/parse", { method: "POST", body: JSON.stringify({ text }) });

export const createReport = (change: Change) =>
  request<Report>("/reports", { method: "POST", body: JSON.stringify({ change }) });

export const listReports = () => request<ReportSummary[]>("/reports");

export const getReport = (id: string) => request<Report>(`/reports/${encodeURIComponent(id)}`);
