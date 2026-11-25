import type { MapNode, Topology } from "./api";

const node = (id: string, name: string, extra: Partial<MapNode> = {}): MapNode => ({
  id,
  name,
  ip: "192.0.2.1",
  type: "switch",
  status: "online",
  vendor: "Cisco",
  model: null,
  site: "Site A",
  ...extra,
});

/** A small synthetic topology for tests: one of each link status, and a device with no links. */
export const TOPOLOGY: Topology = {
  source: "demo",
  collected_at: "2026-11-25T12:00:00Z",
  nodes: [
    node("rtr", "rtr-1", { type: "router", vendor: "Juniper" }),
    node("sw", "sw-1"),
    node("srv", "srv-1", { type: "server", status: "offline", vendor: null }),
    node("ap", "ap-1", { type: "access_point" }),
    node("lonely", "lonely-1", { type: "unknown" }),
  ],
  links: [
    {
      id: "l1",
      a: { device_id: "sw", port: "GigabitEthernet1/0/1" },
      b: { device_id: "rtr", port: "ge-0/0/0" },
      medium: "fiber",
      speed_mbps: 10_000,
      status: "up",
      reason: null,
    },
    {
      id: "l2",
      a: { device_id: "sw", port: "GigabitEthernet1/0/2" },
      b: { device_id: "srv", port: "eth0" },
      medium: "copper",
      speed_mbps: 1000,
      status: "down",
      reason: "device_offline",
    },
    {
      id: "l3",
      a: { device_id: "rtr", port: "Dot11Radio1" },
      b: { device_id: "ap", port: "Dot11Radio1" },
      medium: "wireless",
      speed_mbps: 867,
      status: "degraded",
      reason: "reported",
    },
  ],
  unresolved_links: 0,
};
