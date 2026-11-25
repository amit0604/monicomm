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

import { ApiError, request as call } from "../../lib/api";

export { ApiError };
const request = <T>(path: string, init?: RequestInit) => call<T>(BASE + path, init);

export const getTopology = () => request<Topology>("/topology");

export const parseChange = (text: string) =>
  request<{ change: Change }>("/parse", { method: "POST", body: JSON.stringify({ text }) });

export const createReport = (change: Change) =>
  request<Report>("/reports", { method: "POST", body: JSON.stringify({ change }) });

export const listReports = () => request<ReportSummary[]>("/reports");

export const getReport = (id: string) => request<Report>(`/reports/${encodeURIComponent(id)}`);
