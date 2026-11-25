import { usePolled, type Polled } from "../../lib/usePolled";

// Mirrors api/app/modules/dashboard/models.py.
export type DeviceStatus = "online" | "warning" | "critical" | "suspected_offline" | "offline";
export type DeviceType = "router" | "switch" | "firewall" | "server" | "access_point" | "unknown";
export type SeverityGroup = "critical" | "warning" | "info" | "neutral";
export type Source = "demo" | "live";

export interface Device {
  id: string;
  name: string | null;
  ip: string;
  vendor: string | null;
  model: string | null;
  type: DeviceType;
  status: DeviceStatus;
  os_version: string | null;
  serial: string | null;
  site: string | null;
  last_poll_at: string | null;
}
export interface NetInterface {
  if_index: string;
  name: string;
  alias: string | null;
  admin_status: "up" | "down";
  oper_status: "up" | "down";
  speed_mbps: number | null;
  in_util_pct: number | null;
  out_util_pct: number | null;
  in_errors: number | null;
  out_errors: number | null;
}
export interface DeviceDetails extends Device {
  interfaces: NetInterface[];
  metrics: {
    cpu_pct: number | null;
    memory_pct: number | null;
    temperature_c: number | null;
    uptime_seconds: number | null;
  };
}
export interface NetworkEvent {
  id: string;
  kind: "syslog" | "trap";
  severity: string | null;
  severity_group: SeverityGroup;
  device_id: string | null;
  device_name: string | null;
  source_ip: string;
  received_at: string;
  message: string;
}
export interface Alert {
  id: string;
  severity: "info" | "warning" | "critical";
  code: "device_unreachable" | "interface_down" | "high_temperature" | "high_utilization";
  device_id: string;
  device_name: string | null;
  opened_at: string;
}
export interface Summary {
  source: Source;
  devices: { total: number; by_status: Record<DeviceStatus, number> };
  open_alerts: Alert[];
  recent_events: NetworkEvent[];
}
export interface DeviceList {
  source: Source;
  total: number;
  vendors: string[];
  items: Device[];
}
export interface DeviceView {
  source: Source;
  device: DeviceDetails;
  events: NetworkEvent[];
}
export interface EventList {
  source: Source;
  total: number;
  items: NetworkEvent[];
}

export type Loaded<T> = Polled<T>;

/** Loads a Dashboard API path and keeps it fresh (see lib/usePolled). */
export const useApi = <T>(path: string): Loaded<T> => usePolled<T>(`/api/v1/dashboard${path}`);

export function query(params: Record<string, string>): string {
  const search = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  return search ? `?${search}` : "";
}
