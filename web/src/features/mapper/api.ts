import { usePolled, type Polled } from "../../lib/usePolled";
import type { DeviceStatus, DeviceType } from "../dashboard/api";

// Mirrors api/app/modules/mapper/models.py. Device status and type are the Dashboard's.
export type { DeviceStatus, DeviceType };
export type Medium = "fiber" | "copper" | "wireless" | "wan";
export type LinkStatus = "up" | "degraded" | "down" | "unknown";
export type LinkReason =
  | "device_offline"
  | "port_down"
  | "not_polled"
  | "high_utilization"
  | "errors"
  | "no_port_data"
  | "reported";

export const MEDIUMS: Medium[] = ["fiber", "copper", "wireless", "wan"];
export const LINK_STATUSES: LinkStatus[] = ["up", "degraded", "down", "unknown"];

export interface MapNode {
  id: string;
  name: string;
  ip: string;
  type: DeviceType;
  status: DeviceStatus;
  vendor: string | null;
  model: string | null;
  site: string | null;
}
export interface Endpoint {
  device_id: string;
  port: string;
}
export interface MapLink {
  id: string;
  a: Endpoint;
  b: Endpoint;
  medium: Medium;
  speed_mbps: number | null;
  status: LinkStatus;
  reason: LinkReason | null;
}
export interface Topology {
  source: "demo" | "live";
  collected_at: string;
  nodes: MapNode[];
  links: MapLink[];
  unresolved_links: number;
}

const URL = "/api/v1/mapper/topology";

export type LoadedTopology = Polled<Topology>;

// Anything that isn't a topology (a proxy's error page, an old server) is a failure.
const isTopology = (body: unknown) => {
  const b = body as Partial<Topology> | null;
  return Array.isArray(b?.nodes) && Array.isArray(b?.links);
};

/** Loads the topology, refreshes it every 30 seconds and keeps the last good map if a refresh fails. */
export const useTopology = (): LoadedTopology => usePolled<Topology>(URL, isTopology);
