# Failure rerouting: predicted path + recommended path

- Date: 2026-11-25
- Branch: `chenpaz123/feat-investigator-reroute` (on `main`, which now includes PR #5)
- Status: IN PROGRESS (phases 1-3 built and verified; independent review cut off by the usage limit; PR not opened)

## Overview
When an incident has a failed link or device, show how traffic will be rerouted and whether the network can carry it:
the **predicted** new path (what the routing protocol will pick, by cost) and, when that path would run a link at
≥ 80 %, a **recommended** path that keeps every link lower, with the reason. Recommendation only: Monicomm never
changes device config (CLAUDE.md rule 3). Computed automatically, deterministically, no LLM.

## Problem in one line
After a failure the technician doesn't know where the traffic went or whether the backup path is about to choke.

## Facts (checked in the repo)
- Polled every 60 s (`collector/snmp-server/telegraf/templates/10-all.conf.tmpl`, `snmp_interface`): `ifHighSpeed`
  (Mbps), `ifHCInOctets`, `ifHCOutOctets`, tags `index`, `ifName`; rows carry `polled_at` (Unix ms).
- LLDP adjacency is already modeled in `api/app/modules/investigator/topology.py`.
- Not collected, by design: routing tables (`docs/plans/syslog-snmp-deployment.md` §4.4), OSPF interface costs, flows.

## Decisions (user, 2026-11-25)
| # | Decision |
|---|---|
| D1 | Show predicted path + a recommended path when the predicted one is overloaded |
| D2 | Load moved = the failed link's last measured rate (from interface counters). Device failure: connectivity and paths between its neighbors, load unknown (no flow data) |
| D3 | Link cost = `ref_bw / ifHighSpeed` (OSPF-style, min 1), `MONICOMM_INVESTIGATOR_REF_BW_MBPS` default 100000. Real configured costs are unknown, stated in every result |
| D4 | Warning at ≥ 80 % (`MONICOMM_INVESTIGATOR_UTIL_WARN=0.8`), critical at ≥ 100 % |
| D5 | Computed automatically on every incident update that has a link or device down |
| D6 | UI: "Rerouting" section in the incident detail: small before/after SVG path graph + hop list with utilization bars |
| D7 | Unknown speed or load → status "unknown", never "ok" (PROJECT.md 2.3 rule: what we can't see is unknown, not safe) |

## Assumptions (NOT validated)
- A1 Routing follows the lowest estimated cost; ECMP is ignored (one path shown).
- A2 The LLDP graph is the routed graph (no L2-only hops, no tunnels, no policy routing).
- A3 The failed link's last rate is the traffic that moves; it goes between the link's two ends.

## Contracts for parallel work
### Topology additions (`topology.py`)
- `update()` also keeps, per device + ifIndex from `snmp_interface`: `ifHighSpeed` and the last two octet samples
  (`polled_at`), giving `rate_bps = max(in, out)` from the delta (counter reset/wrap → no rate).
- `edges() -> list[dict]`: one per LLDP link, both directions merged:
  `{"a", "a_if", "b", "b_if", "speed_mbps": float | None, "load_bps": float | None}` (speed = min of known ends,
  load = max of known ends).

### `reroute.py` (pure)
`compute(topology, failed_links: list[tuple[str, str | None]], failed_devices: list[str], ref_bw_mbps: float,
util_warn: float, now: datetime) -> dict | None` (None when nothing failed or the failure isn't on a known link).

```json
{
  "computed_at": "ISO UTC",
  "assumptions": ["Link costs estimated from interface speed (reference 100000 Mbps); configured OSPF costs are not known", "..."],
  "flows": [{
    "from": "10.0.0.1", "to": "10.0.0.2", "load_bps": 420000000.0,
    "reason": "Link 10.0.0.1 Gi1/0/24 <-> 10.0.0.2 ge-0/0/1 down",
    "before": {"hops": [HOP]},
    "predicted": {"hops": [HOP], "cost": 3, "max_util": 0.93, "status": "ok|warning|critical|unknown"} ,
    "recommended": {"hops": [HOP], "cost": 4, "max_util": 0.61, "status": "ok", "why": "keeps every link under 80 %"}
  }],
  "isolated": ["10.0.0.9"]
}
```
`HOP = {"from", "from_if", "to", "to_if", "speed_mbps", "load_bps", "util_after", "status"}`.
`predicted` null = no path (the two ends are cut off). `recommended` null = predicted is fine or nothing better.
Recommended = path minimizing the max utilization after adding the load (bottleneck search), tie-break by cost.
Device failure: flows for pairs of its neighbors (≤ 10 pairs), `load_bps` null, before path through the device.

### Incident field
`incident["reroute"]` = the dict above or null. Set by the correlator when it rebuilds an incident.
Settings: `investigator_ref_bw_mbps: float = 100000`, `investigator_util_warn: float = 0.8`.

## Phase 1: Topology rates + reroute engine (status: DONE)
- [x] `topology.py`: speed, rates, `edges()`; tests (rate from two samples, counter wrap, missing speed)
- [x] `reroute.py` + `tests/investigator/test_reroute.py`
Verification
- [x] Square topology A-B-C-D-A with A-B down: predicted A-D-C-B by cost; when A-D-C-B overloads and a heavier-cost path is lighter, recommended differs, with why
- [x] No alternative path → predicted null, isolated listed
- [x] Missing speed/load → status "unknown", never "ok"

## Phase 2: Correlator + API wiring (status: DONE)
- [x] correlator sets `reroute` for incidents with link/device down (device down = coldStart, or all its LLDP links down)
- [x] settings + `.env.example`; export.md "Rerouting" section
Verification
- [x] Scenario test: link failure incident carries `reroute.flows[0]` with predicted path
- [x] Normal-only input still produces nothing

## Phase 3: UI (status: DONE)
- [x] `Rerouting` section in `IncidentDetail`: before/after SVG mini graph (tokens only), hop table with util bar + StatusPill, assumptions list, "Recommendation only — apply changes through the normal change process"
Verification
- [x] `npm run check` passes; vitest for predicted/recommended/no-path/unknown
- [x] Screenshot light + dark with sample data

## Phase 4: Docs, review, PR (status: IN PROGRESS)
- [x] PROJECT.md §2.4 rerouting + link to §2.3 change impact (shared engine later); plan status
- [ ] full `scripts/check.ps1`; independent review; PR stacked on #5
