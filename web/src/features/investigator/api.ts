// Typed client for the Investigator REST contract (plans/incident-analyzer/plan.md, "Contracts").
const BASE = "/api/v1/investigator";

export type IncidentStatus = "open" | "recovered" | "closed";
export type Severity = "critical" | "warning";

export interface RootCause {
  summary: string;
  event_ids: string[];
  confidence: "high" | "medium" | "low";
}

export interface IncidentSummary {
  id: string;
  status: IncidentStatus;
  severity: Severity;
  title: string;
  started_at: string;
  updated_at: string;
  devices: string[];
  root_cause: RootCause | null;
}

export interface TimelineEvent {
  id: string;
  ts: string;
  device: string;
  hostname: string | null;
  type: string;
  state: string | null;
  interface: string | null;
  peer: string | null;
  severity: string;
  code: string | null;
  raw: string;
  abnormal: boolean;
}

export interface ImpactItem {
  device: string;
  interface: string | null;
  peer: string | null;
  what: string;
  recovered: boolean;
  event_ids: string[];
}

export interface Analysis {
  summary: string;
  root_cause: string;
  impact: string;
  sources: string[];
  model: string;
  created_at: string;
}

// Rerouting (plans/incident-analyzer/reroute-plan.md, "reroute.py" contract).
export type HopStatus = "ok" | "warning" | "critical" | "unknown";

export interface Hop {
  from: string;
  from_if: string | null;
  to: string;
  to_if: string | null;
  speed_mbps: number | null;
  load_bps: number | null;
  util_after: number | null;
  status: HopStatus;
}

export interface RoutePath {
  hops: Hop[];
  cost: number;
  max_util: number | null;
  status: HopStatus;
}

export interface RerouteFlow {
  from: string;
  to: string;
  load_bps: number | null;
  reason: string;
  failed?: { device: string; interface: string | null } | null;
  before: { hops: Hop[] };
  predicted: RoutePath | null;
  recommended: (RoutePath & { why: string }) | null;
}

export interface Reroute {
  computed_at: string;
  assumptions: string[];
  flows: RerouteFlow[];
  isolated: string[];
}

export interface Incident extends IncidentSummary {
  reroute?: Reroute | null;
  possible_causes: { summary: string; event_ids: string[] }[];
  impact: ImpactItem[];
  timeline: TimelineEvent[];
  notes: string;
  resolution: string;
  analysis: Analysis | null;
}

export interface IncidentPatch {
  notes?: string;
  resolution?: string;
  status?: "closed" | "open";
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) throw new ApiError(res.status, `Request failed (${res.status})`);
  return (await res.json()) as T;
}

export const listIncidents = () => request<IncidentSummary[]>("/incidents");

export const getIncident = (id: string) =>
  request<Incident>(`/incidents/${encodeURIComponent(id)}`);

export const patchIncident = (id: string, body: IncidentPatch) =>
  request<Incident>(`/incidents/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });

export const analyzeIncident = (id: string) =>
  request<Analysis>(`/incidents/${encodeURIComponent(id)}/analysis`, { method: "POST" });
