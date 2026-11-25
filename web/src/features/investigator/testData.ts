import type { Hop, Incident, IncidentSummary, Reroute, RerouteFlow } from "./api";

export const SUMMARY: IncidentSummary = {
  id: "aaaaaaaaaaaa",
  status: "open",
  severity: "critical",
  title: "Link down: 10.0.0.1 Gi1/0/24 <-> 10.0.0.2 ge-0/0/1",
  started_at: "2026-11-25T10:00:00Z",
  updated_at: "2026-11-25T10:01:00Z",
  devices: ["10.0.0.1", "10.0.0.2"],
  root_cause: { summary: "Gi1/0/24 went down on 10.0.0.1", event_ids: ["e1"], confidence: "high" },
};

export const INCIDENT: Incident = {
  ...SUMMARY,
  possible_causes: [{ summary: "config change on 10.0.0.1 30 s before", event_ids: ["e0"] }],
  impact: [
    {
      device: "10.0.0.2",
      interface: "ge-0/0/1",
      peer: null,
      what: "OSPF adjacency to 10.0.0.1 down",
      recovered: false,
      event_ids: ["e2"],
    },
  ],
  timeline: [
    {
      id: "e1",
      ts: "2026-11-25T10:00:00Z",
      device: "10.0.0.1",
      hostname: null,
      type: "link",
      state: "down",
      interface: "Gi1/0/24",
      peer: null,
      severity: "err",
      code: "LINK-3-UPDOWN",
      raw: "%LINK-3-UPDOWN: Interface Gi1/0/24, changed state to down",
      abnormal: true,
    },
  ],
  notes: "",
  resolution: "",
  analysis: null,
};

const hop = (from: string, to: string, util: number | null, status: Hop["status"]): Hop => ({
  from,
  from_if: "Gi1/0/1",
  to,
  to_if: "Gi1/0/2",
  speed_mbps: util == null ? null : 1000,
  load_bps: util == null ? null : util * 1e9,
  util_after: util,
  status,
});

const FAILED = hop("10.0.0.1", "10.0.0.2", null, "critical");

export const REROUTE_FLOW: RerouteFlow = {
  from: "10.0.0.1",
  to: "10.0.0.2",
  load_bps: 420_000_000,
  reason: "Link 10.0.0.1 Gi1/0/24 <-> 10.0.0.2 ge-0/0/1 down",
  before: { hops: [FAILED] },
  predicted: {
    hops: [hop("10.0.0.1", "10.0.0.4", 0.42, "ok"), hop("10.0.0.4", "10.0.0.2", 0.55, "ok")],
    cost: 2,
    max_util: 0.55,
    status: "ok",
  },
  recommended: null,
};

export const REROUTE: Reroute = {
  computed_at: "2026-11-25T10:01:00Z",
  assumptions: ["Link costs estimated from interface speed (reference 100000 Mbps)"],
  flows: [REROUTE_FLOW],
  isolated: [],
};

export const REROUTE_WARNING: Reroute = {
  ...REROUTE,
  flows: [
    {
      ...REROUTE_FLOW,
      predicted: {
        hops: [
          hop("10.0.0.1", "10.0.0.4", 0.93, "warning"),
          hop("10.0.0.4", "10.0.0.2", 1.2, "critical"),
        ],
        cost: 2,
        max_util: 1.2,
        status: "critical",
      },
      recommended: {
        hops: [
          hop("10.0.0.1", "10.0.0.3", 0.5, "ok"),
          hop("10.0.0.3", "10.0.0.5", 0.61, "ok"),
          hop("10.0.0.5", "10.0.0.2", 0.4, "ok"),
        ],
        cost: 3,
        max_util: 0.61,
        status: "ok",
        why: "keeps every link under 80 %",
      },
    },
  ],
};

export const REROUTE_CUT_OFF: Reroute = {
  ...REROUTE,
  flows: [{ ...REROUTE_FLOW, predicted: null }],
  isolated: ["10.0.0.9"],
};

export const REROUTE_UNKNOWN: Reroute = {
  ...REROUTE,
  flows: [
    {
      ...REROUTE_FLOW,
      load_bps: null,
      predicted: {
        hops: [hop("10.0.0.1", "10.0.0.4", null, "unknown")],
        cost: 1,
        max_util: null,
        status: "unknown",
      },
    },
  ],
};

// Minimal fetch stub for tests: route on "METHOD path" -> [status, body].
export function stubFetch(routes: Record<string, () => [number, unknown]>) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const route = routes[`${init?.method ?? "GET"} ${url}`];
    if (!route) return new Response("not found", { status: 404 });
    const [status, body] = route();
    return new Response(JSON.stringify(body), { status });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
