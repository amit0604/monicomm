import { useCallback, useEffect, useState } from "react";

// Mirrors api/app/modules/mapper/models.py.
export type DeviceStatus = "online" | "warning" | "critical" | "suspected_offline" | "offline";
export type DeviceType = "router" | "switch" | "firewall" | "server" | "access_point" | "unknown";
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
const REFRESH_MS = 30_000;

export interface LoadedTopology {
  data: Topology | null;
  /** HTTP status, or 0 when the server could not be reached. */
  error: number | null;
  reload: () => void;
}

/** Loads the topology, refreshes it every 30 seconds and keeps the last good map if a refresh fails. */
export function useTopology(): LoadedTopology {
  const [data, setData] = useState<Topology | null>(null);
  const [error, setError] = useState<number | null>(null);
  const [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    const abort = new AbortController();
    const load = async () => {
      let status = 0;
      try {
        const res = await fetch(URL, { signal: abort.signal });
        if (res.ok) {
          const body = (await res.json()) as Partial<Topology> | null;
          if (abort.signal.aborted) return;
          // Anything that isn't a topology (a proxy's error page, an old server) is a failure.
          if (Array.isArray(body?.nodes) && Array.isArray(body?.links)) {
            setData(body as Topology);
            setError(null);
            return;
          }
        } else {
          status = res.status;
        }
      } catch {
        // Unreachable, or aborted because the page closed.
      }
      if (!abort.signal.aborted) setError(status);
    };
    void load();
    const timer = setInterval(() => void load(), REFRESH_MS);
    return () => {
      abort.abort();
      clearInterval(timer);
    };
  }, [attempt]);

  return { data, error, reload };
}
