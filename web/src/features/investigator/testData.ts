import type { Incident, IncidentSummary } from "./api";

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
