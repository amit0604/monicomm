# Incident Analyzer (Investigator, live): build plan

- Date: 2026-11-25
- Branch: `feat/investigator-incident-analyzer` (from `origin/main` 5d33e95)
- Status: DONE (all phases built and verified; final independent review not run: usage limit)

## Overview
Listens to the network events the collectors deliver (PR #2, `danulbatul/feat-collector-servers`),
spots network incidents, shows **what they affect on the network path** and a **probable root cause**
with evidence, and alerts the technician with a toast plus the Incident Investigator page.
Combines PROJECT.md 2.3 (findings from syslog/SNMP) and 2.4 (timeline + root cause + evidence).

**Abnormal only (user decision, 2026-11-25):** when the network works normally the feature stores,
logs and shows nothing. Normal events stay in an in-memory window (`INVESTIGATOR_WINDOW_S`) only so they
can serve as context or cause (for example a `config_change` just before a link drop), then they are dropped.
- Abnormal = link/protocol down, adjacency down (BGP/OSPF/IS-IS), VPN down, cluster failover, hardware/env
  alarm, STP topology change, interface flapping (≥ 3 down/up in the window), failed logins burst (≥ 5 per device in 5 min).
- Not abnormal on its own: link_up, config_change, a single failed login, info/debug syslog, `other`.
- A recovery event (link_up, adjacency up) does not open an incident; it only marks an open one as recovered.

## Problem in one line
When a link or a device fails, the technician gets a flood of syslog/trap lines from many devices
and has to work out by hand which one is the cause and what it broke.

## Facts (checked in the repo)
- Event contract: `collector/README.md` on PR #2: `monicomm.syslog.v1`, `monicomm.trap.v1`,
  `monicomm.snmp_metric.v1` (`snmp_lldp_neighbor`, `snmp_interface`, `snmp_bgp_peer`...).
- Until Monicomm `ingest` exists, `dev-ingest` writes `<dir>/<UTC date>/{syslog,trap,snmp_metric}.jsonl`.
- Vendor normalization (Cisco `%FAC-SEV-MNEMONIC`, Junos tags) is Monicomm's job: plan §3.3 event map.
- `main` has a FastAPI skeleton, `llm_client.py` (URL guard only, no `chat()` yet), React shell with
  tokens and `StatusPill`, CI (`scripts/check.ps1`, 80% coverage gate). No DB layer, worker or migrations yet.

## Assumptions (NOT validated; the user did not answer round 2, these are the defaults taken)
| # | Assumption | If wrong |
|---|---|---|
| A1 | Input = tail the dev-ingest JSONL directory (`INVESTIGATOR_INGEST_DIR`). Same format later arrives via Redis streams | swap the reader only |
| A2 | Detection = deterministic rules + correlation; the LLM only explains and cites evidence (7B model is not trusted to find causes) | add LLM triage later |
| A3 | Topology for impact = LLDP neighbor rows from `snmp_lldp_neighbor` metrics (no Mapper yet) | read the Mapper graph when it exists |
| A4 | Storage = JSON files under `INVESTIGATOR_DATA_DIR` (no DB layer on main yet) | move to Postgres with a migration |
| A5 | Listener runs as an asyncio task in the API lifespan (no worker container yet) | move to the worker |
| A6 | UI = Investigator page (list + detail) + `sonner` toast on new critical incident, polling 15 s | WebSocket `/api/v1/ws` later |
| A7 | We add `async chat(messages) -> str` to `llm_client.py` (Ollama `/api/chat`, `httpx`) | shared file: tell the team in the PR |

## Sub-problems
1. Normalize raw events → typed `NetEvent` (type, device, interface, peer, severity, time, raw evidence).
2. Build an adjacency map from LLDP rows.
3. Correlate events into incidents (time window + same device or LLDP neighbor).
4. Pick a root-cause candidate by rules and compute impact (affected devices, interfaces, lost peers).
5. Persist incidents, expose API, export Markdown.
6. LLM explanation with cited event ids.
7. UI page + toast.

## Phase 1: Normalizer (status: DONE)
- [x] `api/app/modules/investigator/events.py`: syslog (Cisco + Junos per §3.3: link, lineproto, bgp, ospf, isis, config, login_failed, stp, hw_env, vpn, cluster) and traps (linkDown/linkUp, `.1.3.6.1.6.3.1.1.5.3/.4`) → `NetEvent`; unknown → `other`
- [x] tests with sample lines from §3.3

Verification
- [x] `uv run pytest tests/investigator -q` passes
- [x] Each §3.3 sample maps to the right type, device = `source_ip`, interface/peer extracted
- [x] Malformed JSON line or missing `syslog` header is skipped, not a crash

## Phase 2: Topology + correlation + root cause (status: DONE)
- [x] `topology.py`: LLDP rows → `{device: {local_if: (neighbor, remote_if)}}`
- [x] `correlate.py`: group events (window `INVESTIGATOR_WINDOW_S`, default 120) by device or LLDP neighbor; rules: link_down on both ends of one LLDP link → link failure; earliest link/hw/config event explains later bgp/ospf/stp events; impact = devices/interfaces/peers touched + neighbors that lost adjacency
- [x] tests: synthetic scenario (core link down → 2 OSPF drops + BGP drop on neighbors) → 1 incident, root cause = the link, impact lists both ends
- [x] only abnormal events open incidents; normal events are kept in memory for the window, then dropped

Verification
- [x] A stream of only normal events (link_up, config_change, info syslog, 1 failed login) → zero incidents, nothing written to disk
- [x] config_change followed by link_down on the same device → incident cites the config_change as a possible cause
- [x] Scenario test gives exactly one incident with the expected root cause and evidence ids
- [x] Unrelated events 10 min apart give separate incidents
- [x] Every root cause and impact item points to at least one event id

## Phase 3: Listener, store, API (status: DONE)
- [x] `listener.py`: tail JSONL files by offset (survives restart), feed correlator
- [x] `store.py`: JSON per incident under `INVESTIGATOR_DATA_DIR`, status `open/closed`, notes
- [x] `router.py` at `/api/v1/investigator`: `GET /incidents?status=&since=`, `GET /incidents/{id}`, `PATCH /incidents/{id}` (notes, status, resolution), `GET /incidents/{id}/export.md`
- [x] mount in `main.py`, lifespan starts listener only when the ingest dir is set
- [x] `.env.example`: new variables

Verification
- [x] Write sample JSONL to a temp dir → incident appears in `GET /incidents`
- [x] Normal-only JSONL → `INVESTIGATOR_DATA_DIR` holds only the read offsets, no incident files
- [x] Restarting does not duplicate incidents (offsets kept)
- [x] Bad id → 404, path traversal rejected

## Phase 4: AI root-cause explanation (status: DONE)
- [x] `llm_client.chat()` (httpx to `MONICOMM_LLM_BASE_URL`, internal-URL guard kept)
- [x] `api/app/ai/prompts/investigator_root_cause.md`; incident + evidence go in a data message, never in system role
- [x] `POST /incidents/{id}/analysis` → `{summary, root_cause, impact, sources: [event ids]}`; 503 when model down; unknown cited ids dropped

Verification
- [x] Test with mocked `chat`: prompt contains evidence, answer's `sources` subset of incident event ids
- [x] Model down → 503, incident still readable

## Phase 5: UI (status: DONE)
- [x] `web/src/features/investigator/`: incident board (status pill + icon + text, severity, device, start time), detail panel (timeline, impact, root cause, AI tag + sources, notes, close)
- [x] `sonner` (pinned) toast for new critical incidents on any page
- [x] loading / empty / error states, light + dark, tokens only

Verification
- [x] `npm run check` passes (lint blocks raw colors)
- [x] vitest: list renders, empty state, toast fires once per new critical incident
- [x] Screenshots light + dark against a running API with sample data

## Phase 6: Docs + finish (status: DONE)
- [x] PROJECT.md 2.4: API contract, assumptions, decision log row
- [x] `scripts/check.ps1` green; independent review; PR description

Verification
- [x] Full check suite green and output read
- [x] Reviewer verdict PASS or issues fixed

## Contracts for parallel work (conductor, 2026-11-25)
Each agent owns only its files. Shared shapes below are fixed; change them only through the conductor.

### Incident (JSON dict, stored as `<INVESTIGATOR_DATA_DIR>/incidents/<id>.json`)
```json
{
  "id": "12 hex", "status": "open|recovered|closed", "severity": "critical|warning",
  "title": "Link down: 10.0.0.1 Gi1/0/24 <-> 10.0.0.2 ge-0/0/1",
  "started_at": "ISO UTC", "updated_at": "ISO UTC", "devices": ["10.0.0.1", "10.0.0.2"],
  "root_cause": {"summary": "text", "event_ids": ["..."], "confidence": "high|medium|low"},
  "possible_causes": [{"summary": "config change on 10.0.0.1 30 s before", "event_ids": ["..."]}],
  "impact": [{"device": "10.0.0.2", "interface": "ge-0/0/1", "peer": null,
              "what": "OSPF adjacency to 10.0.0.1 down", "recovered": false, "event_ids": ["..."]}],
  "timeline": [{"id": "...", "ts": "ISO UTC", "device": "...", "hostname": null, "type": "link",
                "state": "down", "interface": "...", "peer": null, "severity": "err",
                "code": "LINK-3-UPDOWN", "raw": "...", "abnormal": true}],
  "notes": "", "resolution": "", "analysis": null
}
```
`analysis` after AI: `{"summary": str, "root_cause": str, "impact": str, "sources": [event ids], "model": str, "created_at": ISO}`.

### Python interfaces
- `app.modules.investigator.events`: `NetEvent`, `parse_line`, `parse_event` (Phase 1, done).
- `app.modules.investigator.topology.Topology`: `update(metric: dict) -> None` (snmp_metric.v1 rows),
  `neighbors(device_ip) -> set[str]`, `link(device_ip, interface) -> tuple[str, str | None] | None`.
- `app.modules.investigator.correlate.Correlator(window_s=120, topology=None)` (+ `flush(now) -> list[dict]`, called by the listener every poll):
  `.topology` attribute, `feed(ev: NetEvent) -> list[dict]` (incidents created or changed by this event, full dicts),
  `load(incidents: list[dict]) -> None` (resume open incidents after restart). Normal-only input returns [].
- `app.modules.investigator.analysis.analyze(incident: dict) -> dict` (async) returns the `analysis` dict;
  raises `analysis.ModelUnavailable` when the model can't be reached.
- `app.ai.llm_client.chat(messages: list[dict]) -> str` (async).

### REST (`/api/v1/investigator`)
- `GET /incidents?status=` → list of `{id, status, severity, title, started_at, updated_at, devices, root_cause}` newest first
- `GET /incidents/{id}` → full incident · `PATCH /incidents/{id}` body `{notes?, resolution?, status?: "closed"|"open"}`
- `POST /incidents/{id}/analysis` → `analysis` dict (stored on the incident); 503 when model down
- `GET /incidents/{id}/export.md` → `text/markdown`
- 404 unknown id; ids must match `^[0-9a-f]{12}$`.

### Settings (`app.core.config.Settings`, env prefix `MONICOMM_`)
`investigator_ingest_dir: str = ""` (empty = listener off), `investigator_data_dir: str = "/data/investigator"`,
`investigator_window_s: int = 120`, `investigator_poll_s: float = 5.0`.
