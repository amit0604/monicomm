// Pure helpers between the API topology and what the page draws. No React, no graph engine.
import type { Status } from "../../components/ui";
import type { DeviceStatus, LinkStatus, MapLink, MapNode, Medium, Topology } from "./api";

export const DEVICE_TONE: Record<DeviceStatus, Status> = {
  online: "ok",
  warning: "warning",
  critical: "critical",
  suspected_offline: "accent",
  offline: "neutral",
};

export const LINK_TONE: Record<LinkStatus, Status> = {
  up: "ok",
  degraded: "warning",
  down: "critical",
  unknown: "neutral",
};

/** Each medium has its own color token (tokens.css), so the legend and the graph always match. */
export const MEDIUM_TOKEN: Record<Medium, string> = {
  fiber: "--link-fiber",
  copper: "--link-copper",
  wireless: "--link-wireless",
  wan: "--link-wan",
};

/** Line style carries the status on the map, next to a text marker: never color alone (6A). */
export const LINK_LINE: Record<LinkStatus, "solid" | "dashed" | "dotted"> = {
  up: "solid",
  degraded: "dashed",
  down: "dotted",
  unknown: "dashed",
};

const PORT_PREFIXES: [RegExp, string][] = [
  [/^HundredGigE/i, "Hu"],
  [/^FortyGigabitEthernet/i, "Fo"],
  [/^TwentyFiveGigE/i, "Twe"],
  [/^TenGigabitEthernet/i, "Te"],
  [/^GigabitEthernet/i, "Gi"],
  [/^FastEthernet/i, "Fa"],
  [/^Ethernet/i, "Eth"],
  [/^Dot11Radio/i, "Radio"],
  [/^Port-channel/i, "Po"],
];

/** "GigabitEthernet1/0/1" → "Gi1/0/1", the way the CLI shows it. Other names stay as they are. */
export function shortPort(name: string): string {
  for (const [pattern, short] of PORT_PREFIXES)
    if (pattern.test(name)) return name.replace(pattern, short);
  return name;
}

export interface Filters {
  mediums: Set<Medium>;
  status: LinkStatus | "";
}

export function visibleLinks(topology: Topology, filters: Filters): MapLink[] {
  return topology.links.filter(
    (l) => filters.mediums.has(l.medium) && (!filters.status || l.status === filters.status),
  );
}

export interface Neighbor {
  link: MapLink;
  port: string;
  other: MapNode | undefined;
  otherPort: string;
}

/** A device's links, seen from its side: my port, the neighbor, the neighbor's port. */
export function neighbors(topology: Topology, nodeId: string): Neighbor[] {
  const byId = new Map(topology.nodes.map((n) => [n.id, n]));
  return topology.links.flatMap((link) => {
    if (link.a.device_id === nodeId)
      return [
        { link, port: link.a.port, other: byId.get(link.b.device_id), otherPort: link.b.port },
      ];
    if (link.b.device_id === nodeId)
      return [
        { link, port: link.b.port, other: byId.get(link.a.device_id), otherPort: link.a.port },
      ];
    return [];
  });
}

export function countBy<T extends string>(items: T[]): Partial<Record<T, number>> {
  const out: Partial<Record<T, number>> = {};
  for (const item of items) out[item] = (out[item] ?? 0) + 1;
  return out;
}

/** Routers are the roots of the drawing, so the map reads top-down: WAN, edge, core, access. */
export function roots(topology: Topology): string[] {
  return topology.nodes.filter((n) => n.type === "router").map((n) => n.id);
}
