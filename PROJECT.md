# Monicomm: Project Spec and Team Sync

> **This file is the single source of truth for the team.**
> If you change a decision, change it here in the same pull request.
> Anything marked **PROPOSED** is not final until the team agrees and marks it **DECIDED**.

Repository: https://github.com/amit0604/monicomm

---

## 1. What we are building

Monicomm is an AI-assisted **network communication monitoring** platform for technicians.
It collects data from the network (SNMP, syslog, logs, flows, packet captures), stores it,
and gives technicians six AI-based tools to understand, map and investigate the network.

### Hard constraints (non-negotiable)

| # | Constraint | What it means for us |
|---|---|---|
| C1 | **Air-gapped.** No internet access, ever. | No cloud APIs (no OpenAI/Anthropic/etc.), no CDN links in the UI, no runtime `pip install` / `npm install`, no telemetry, no license checks that call home. Every model, image, font and package ships inside the delivery. |
| C2 | **Runs on Docker.** | Every component is a container. One `docker compose up -d` per deployment brings it up: the Monicomm stack, the syslog server and the SNMP server (see §3). |
| C3 | **Everything local, on the closed network.** | The LLM runs on our own hardware. All data stays on our servers. |

If a library, model or tool can't satisfy C1–C3, we don't use it.

---

## 2. The six features

Each feature is a module with its own folder, API routes and UI page. All six share the
same data store and the same local LLM service.

### 2.1 Chat AI: technician assistant
- **Goal:** A chat assistant that answers questions about *our* network ("Which switch is
  host 10.1.4.22 on?", "What changed on core-sw-01 since yesterday?", "Why is VLAN 30 slow?").
- **How:** The LLM doesn't guess. It calls **tools** (read-only queries against our database,
  the mapper graph, the analyzer results) and answers from what they return. It can also search
  our own documents (runbooks, vendor manuals uploaded by us) through local RAG.
- **Must have:** cites the source of each answer (device, log line, time range); never
  runs write or config actions on network devices; keeps per-user conversation history.
- **Changes (ChatIAF, DECIDED):** the AI is read-only. It can *propose* a change, which shows in the chat as
  an impact card (commands/OIDs, IMPACT analysis, warnings, rollback plan). Only the technician's
  **Approve** button sends it to the configurator (docs/plans/syslog-snmp-deployment.md §7). High-risk
  changes need an explicit acknowledgement; routers, firewalls and core switches need a second approver.
  Every tool call the AI makes is visible in the conversation. UI: `web/src/features/chat/`.
- **Scope (DECIDED):** networking, computer communications, IT infrastructure, OSI, TCP/IP, routing and switching,
  DNS/DHCP, monitoring, servers, logs and alerts, defensive security, troubleshooting, root cause, impact, MoniComm usage.
  Off-topic requests are declined; mixed requests get only the in-scope part; attempts to override the rules are refused.
- **Prototype status:** no model is connected yet. Replies come from a rule-based intent classifier, demo scenarios on
  mock data and a small local knowledge base, and the UI labels them as such (Prototype mode, Mock data, Simulated AI, Read-only).
  The system prompt template for the future model is `api/app/ai/prompts/chat_system.md`; the code-enforced rules are in
  `web/src/features/chat/policy.ts`.
- **Later:** suggested next steps, hand-off to Incident Investigator ("open an investigation from this chat").

### 2.2 Dashboard: network overview
- **Goal:** One screen that shows the health of the network at a glance.
- **Shows:** device up/down status, interface utilization and errors, top talkers, alert
  counts by severity, recent incidents, syslog volume over time.
- **AI part:** a short, auto-generated "network summary" (what's abnormal right now) and
  anomaly markers on charts.
- **Must have:** auto-refresh, time-range picker, drill-down from any widget into Analyzer / Investigator / Mapper.

### 2.3 Analyzer: SNMP, logs and syslog analysis
- **Goal:** Continuously process what flows in and turn raw data into findings.
- **Inputs:** SNMP polling (v2c/v3) and traps, syslog (UDP/TCP 514, RFC 3164/5424),
  application/device log files, and optionally NetFlow/sFlow/IPFIX.
- **AI part:** log parsing/clustering (group similar messages), anomaly detection on metrics
  (baseline vs current), severity classification and plain-language explanation of a log pattern.
- **Output:** "findings" records (what, where, when, severity, evidence) that the Dashboard,
  Chat and Investigator all read.

#### Change impact analysis ("what if")
- **Goal:** Before a technician makes a change, show **what that change would do** to the network.
- **Examples of changes:** shutting down an interface or port, rebooting or replacing a device,
  changing a VLAN, adding or removing a firewall/ACL rule, changing a route or link cost,
  moving a VM or host, taking a link down for maintenance.
- **Input:** the technician describes the change in plain language ("shut Gi1/0/24 on core-sw-01"),
  picks it in the UI (select a node or link on the Mapper and choose an action), or pastes a config diff.
- **How:** the AI turns the request into a structured change. The system then **simulates** it on a copy of
  the Mapper topology, using recent traffic and flow data from the Analyzer:
  - which hosts, VMs, containers and services lose connectivity, and which paths still work
  - where traffic would be rerouted, and whether the alternate links have the capacity (utilization after the change)
  - which flows or rules an ACL or firewall change would block or allow
  - new single points of failure the change creates
- **Output:** an impact report with a **risk level** (low / medium / high, shown with the section 6A status colors),
  an affected-items list, a before/after view on the map, a suggested maintenance window
  (lowest-traffic time from history) and a rollback note. Reports are saved and can be attached to an Investigation.
- **Rule:** this is **simulation only**. Monicomm never applies the change to a device (AI design rule 3).
- **Limits:** results are only as good as the discovered topology and traffic data. Every report states
  what data it used and how current it is. Anything it couldn't see is marked "unknown", never "safe".

### 2.4 Incident Investigator
- **Goal:** Investigate a specific incident or network event end to end.
- **Scope:** hosts, ports, services, bottlenecks, link saturation, flapping interfaces,
  unusual connections, failed logins, and so on.
- **Flow:** technician opens an investigation (from an alert, a finding, a chat, or manually) →
  the system collects related data in a time window (logs, metrics, flows, topology neighbors) →
  the AI builds a **timeline** and a **probable root cause** with evidence → technician adds
  notes and closes it with a resolution.
- **Must have:** every AI conclusion links to its evidence; investigations are saved and searchable; export to PDF/Markdown.

#### Live incident analyzer (built; plan: `plans/incident-analyzer/plan.md`)
- **What:** listens to collector events (`collector/README.md`: `monicomm.syslog.v1`, `monicomm.trap.v1`,
  `monicomm.snmp_metric.v1`), opens incidents **only for abnormal events**, shows what they affect on the
  network path and a probable root cause with evidence. **A normal network produces nothing:** no incident, no event content on disk or in logs
  (only the listener's read offsets). On first start it tails from now; it doesn't replay old files.
- **Abnormal:** link/adjacency (BGP/OSPF/IS-IS)/VPN down (not admin-down or admin BGP resets), cluster failover,
  hardware/env alarms, STP root/topology changes, interface flapping (≥ 3 downs in the window), failed-login bursts
  (≥ 5 per device in 5 min). Up events only mark an open incident as recovered. Normal events stay in memory for the
  window as possible causes (e.g. a config change just before a link drop), then are dropped.
- **How:** `api/app/modules/investigator/`: `events.py` (vendor normalization, Cisco + Junos, injection-safe),
  `topology.py` (LLDP neighbors from `snmp_lldp_neighbor`), `correlate.py` (group by time window + same device or
  LLDP neighbor; rule-based root cause; impact), `listener.py` (tails `<ingest_dir>/<date>/*.jsonl` by offset),
  `store.py`, `router.py`, `analysis.py` (the LLM only explains and cites event ids; it never finds the cause itself).
- **API (`/api/v1/investigator`):** `GET /incidents?status=` · `GET /incidents/{id}` · `PATCH /incidents/{id}`
  (`notes`, `resolution`, `status` open/closed) · `POST /incidents/{id}/analysis` (503 when the model is down) ·
  `GET /incidents/{id}/export.md`. Incident JSON shape: plan file, "Contracts".
- **Config:** `MONICOMM_INVESTIGATOR_INGEST_DIR` (empty = listener off), `_DATA_DIR`, `_WINDOW_S` (120), `_POLL_S` (5).
- **Interim, until the foundation lands:** reads dev-ingest JSONL files (later Redis streams, same format); incidents
  are JSON files under the data dir (later Postgres); the listener runs in the API lifespan (later the worker);
  the UI polls every 15 s (later `/api/v1/ws`). The UI is the Incident Investigator page plus a `sonner` toast on
  every page for each new critical incident.

### 2.5 Mapper: network topology and inventory
- **Goal:** A live map of what is on the network and how it connects.
- **Discovers:** network devices (switches, routers, firewalls), end devices, hosts,
  **VMs** and **containers**, and the links between them.
- **Sources:** SNMP (LLDP/CDP neighbors, ARP and MAC tables, interface tables), ICMP/ARP
  sweeps, optional nmap service scan, hypervisor APIs (VMware vCenter / Proxmox / Hyper-V,
  as applicable), Docker / Kubernetes APIs.
- **AI part:** device type/role classification, naming suggestions, "what changed in the topology since X".
- **Must have:** interactive graph (zoom, filter by VLAN/site/type, click a node for details),
  inventory table view, change history.

### 2.6 Chatchup: packet capture (PCAP) investigation
> **DECIDED:** Chatchup = **packet capture files (.pcap / .pcapng)**. Code lives in `api/app/modules/pcap/`.
- **Goal:** Upload a capture file and investigate what happened in it.
- **Flow:** upload a .pcap/.pcapng → the backend parses it (tshark / Zeek) into conversations,
  protocols, DNS/HTTP/TLS metadata, retransmissions, resets, latency → the AI summarizes the
  capture and answers questions about it in a chat scoped to that file.
- **Must have:** size limit and background processing for big files, protocol breakdown,
  conversation list, flagged anomalies, "follow stream" view, link findings into an Investigation.
- **Parser:** `dpkt` (pure Python; pcap + pcapng; Ethernet, raw IP, Linux SLL; IPv4 + IPv6). Flags port scans,
  beacons (regular internal→external check-ins), TCP retransmissions, resets, slow/unanswered handshakes.
  Every finding cites 1-based packet numbers (same as Wireshark).
- **API (`/api/v1/pcap`):** `POST /captures` (multipart `file`, 202, `PCAP_MAX_UPLOAD_MB`) · `GET /captures` ·
  `GET /captures/{id}` (meta + analysis, top 200 conversations by bytes) ·
  `GET /captures/{id}/conversations?offset=&limit=` · `GET /captures/{id}/streams/{conv_id}` · `DELETE /captures/{id}` ·
  `POST /captures/{id}/summary[?refresh=true]` · `GET|POST /captures/{id}/chat` (`{"question": "..."}`).
  AI answers return `sources` = cited packet numbers; 503 when the local model is down. The LLM gets
  metadata only (HTTP query strings are dropped, strings length-capped), in a data message, never in the
  system role and never payload bytes. Memory is bounded (20k tracked flows, per-type anomaly caps with true
  totals in `anomaly_counts`). Upload size is checked from `Content-Length` before parsing; nginx must enforce
  `client_max_body_size` too.
- **Wiring:** `app/main.py` mounts `app.modules.pcap.router.router` at `/api/v1/pcap`. AI calls go through
  `app.ai.llm_client.chat(messages) -> str` (async, Ollama `/api/chat`, URL checked by the air-gap guard,
  `LLMError` on failure; any module can use it). Settings: `MONICOMM_PCAP_DATA_DIR`, `MONICOMM_PCAP_MAX_UPLOAD_MB`,
  `MONICOMM_LLM_TIMEOUT_S`. Deps (`dpkt`, `python-multipart`, `httpx`) are in `api/pyproject.toml` / `uv.lock`.
- **Interim:** results stored as JSON under `MONICOMM_PCAP_DATA_DIR/<id>/` and analysis runs in FastAPI
  `BackgroundTasks`, until Chatchup moves to the DB and the shared worker. The api container needs that
  directory on a volume, and nginx must allow uploads of `MONICOMM_PCAP_MAX_UPLOAD_MB`.
- **Network views (graph tab):** `GET /captures/{id}/graph?protocol=&min_packets=&t_start=&t_end=` (hosts as
  nodes, host pairs as edges, hubs, scan/beacon hosts flagged) · `GET /captures/{id}/overview?t_start=&t_end=`
  (totals, protocol mix, top talkers/ports, findings) · `GET /captures/{id}/timeline` · `GET /captures/{id}/hosts/{ip}`.
  `t_start`/`t_end` are seconds from the first packet; windows use per-conversation time bins stored next to the
  analysis (1 s, coarsened automatically to stay under 200k bins), so no view re-reads the file.
- **UI (TEMPORARY):** `web/src/features/pcap/legacy/` is the Chatchup tab in plain JS, adapted from the PCAP Lab
  workshop UI (network graph + inspector + timeline with time window, plus findings and the AI assistant).
  `ChatchupTab.tsx` mounts it in the shell (`App.tsx`, module `pcap`) via `mountChatchup(el)`, re-reads tokens on
  a theme switch and calls `.destroy()` when you leave the tab. Styles are scoped under `.chatchup` and use only
  `tokens.css`. Graph: `cytoscape` 3.30.2 from npm (MIT), bundled by Vite, so nothing loads at runtime.
  **To do:** port to React + shared components (rule 6), then delete `legacy/`.
- **Later:** move storage to the DB and processing to the shared worker; link findings into an Investigation;
  per-user access once auth exists; packet list + hex view (the workshop has one).

---

## 3. Architecture (PROPOSED)

> **Diagrams:** open [`docs/architecture.html`](docs/architecture.html) in a browser (works offline). It shows the
> deployment and data flow, a Chat AI request end to end, the tech stack with build status, and the delivery
> pipeline. When the architecture or stack changes, update that page in the same PR.

```
  Network devices ──► syslog server VM  (own deployment)  ─┐  mTLS
  (mgmt network)  ◄─► SNMP server VM    (own deployment)  ─┤  (events, metrics; configurator API)
                     ┌──────────────── Monicomm VM (blocked from devices) ─────────────┐
                     │ ingest (Vector) ◄───────────────────────────────────────────────┘
                     │      │                                                          │
                     │      ▼                                                          │
                     │ queue (Redis) ──► workers (parsing, analysis, PCAP, mapping)    │
                     │                        │                                        │
                     │                        ▼                                        │
                     │                 database (Postgres + TimescaleDB + pgvector)    │
                     │                        ▲                                        │
                     │ llm (Ollama / vLLM) ◄─ api (FastAPI)  ◄──  web (React UI)       │
                     │                                              ▲                  │
                     │                        proxy (nginx, HTTPS) ─┘                  │
                     └─────────────────────────────────────────────────────────────────┘
```

**Collectors are separate deployments (PROPOSED).** The syslog server and the SNMP server each run as
their own Docker deployment on their own VM on the management network. They receive and poll device data,
buffer it to disk, and forward it to Monicomm over mutual TLS. The SNMP server holds all device credentials
and runs the `configurator`, the only component allowed to change device config, and only on a
human-approved request. Monicomm is blocked from network devices (host firewall on the shared
`192.168.108.0/24` subnet; a separate VLAN later). Full plan:
`docs/plans/syslog-snmp-deployment.md`. Setup: `docs/runbooks/collector-servers-setup.md`.
Event contract between the collectors and Monicomm `ingest`: `collector/README.md`.

### Containers in the Monicomm deployment (one service each in `docker-compose.yml`)

| Service | Role | Proposed tech |
|---|---|---|
| `proxy` | Single entry point, TLS, serves the UI | nginx |
| `web` | Front end, built static files | React + TypeScript + Vite |
| `api` | REST/WebSocket API, auth, AI orchestration (tool calling) | Python 3.12 + FastAPI |
| `worker` | Background jobs: log parsing, anomaly detection, PCAP processing, discovery | Python, same codebase as `api` (arq or Celery) |
| `ingest` | Receives events and metrics from the syslog and SNMP servers (mTLS) and puts them on the queue | Vector |
| `db` | Relational data, time series, vector embeddings | PostgreSQL 16 + TimescaleDB + pgvector |
| `queue` | Job queue and cache, pub/sub for live UI updates | Redis |
| `llm` | Local LLM and embedding model server | Ollama (simple) or vLLM (faster, with a GPU) |

**Why one database:** Postgres + TimescaleDB + pgvector covers relational, time-series and
vector search in one place. That means fewer containers to ship and back up air-gapped. We'll revisit
this (for example OpenSearch for logs) only if volume shows we need it.

### AI design rules
1. **One LLM gateway.** All model calls go through `api/app/ai/llm_client.py`. Nobody calls the model server directly. This lets us swap models without touching the features.
2. **Tools over raw dumps.** The model gets small, typed tools (`get_device`, `query_logs`, `get_neighbors`, `get_metric_series`...) instead of huge text dumps.
3. **Read-only by default.** No AI tool may change device config. Any future write action needs explicit human confirmation and its own design review.
4. **Evidence or it didn't happen.** Every AI answer or finding stores references to the rows/log lines/packets it was based on.
5. **Prompts live in files** (`api/app/ai/prompts/*.md`), versioned in git, not hard-coded in strings.

### Models (PROPOSED, decide after testing on our hardware)
| Purpose | Candidates (open weights, run offline) |
|---|---|
| Chat / reasoning / tool calling | Qwen 2.5/3 (7B–32B), Llama 3.x (8B/70B), Mistral Small |
| Embeddings (RAG, log clustering) | nomic-embed-text, bge-m3 |

Pick based on available GPU/RAM. Write the hardware spec in section 8 once we know it.

---

## 4. Repository layout (PROPOSED)

```
monicomm/
├── PROJECT.md                 ← this file
├── CLAUDE.md                  ← short instructions for AI coding assistants
├── README.md                  ← how to run it
├── docker-compose.yml
├── .env.example               ← every config variable, with safe defaults, no secrets
├── api/                       ← FastAPI app + workers (Python)
│   └── app/
│       ├── core/              ← config, db, auth, logging
│       ├── ai/                ← llm_client, tools, prompts/
│       ├── modules/
│       │   ├── chat/
│       │   ├── dashboard/
│       │   ├── analyzer/
│       │   ├── investigator/
│       │   ├── mapper/
│       │   └── pcap/          ← "Chatchup"
│       └── workers/
├── collector/                 ← separate deployments, each with its own docker-compose.yml
│   ├── syslog-server/         ← Vector: receive, archive, forward
│   └── snmp-server/           ← snmptrapd, Telegraf poller, configurator, Vector shipper
├── web/                       ← React front end
│   └── src/features/{chat,dashboard,analyzer,investigator,mapper,pcap}/
├── db/migrations/             ← Alembic migrations
├── deploy/
│   ├── offline/               ← scripts to build and load the air-gapped bundle
│   └── nginx/
└── docs/                      ← decisions (ADRs), diagrams, runbooks
```

**Rule:** a feature module talks to another module only through its service functions or the API, never by reading its tables directly.

---

## 5. Air-gapped delivery

Development can happen on machines with internet. **Deployment cannot.** So:

1. **Build on a connected build machine**: `docker compose build`, then pull the model weights.
2. **Bundle**: `deploy/offline/bundle.sh` runs `docker save` on all images into a `.tar`, copies model
   files, `docker-compose.yml` and `.env.example`, and writes a checksum file (SHA-256).
3. **Transfer** the bundle into the closed network (approved media/process).
4. **Install**: `deploy/offline/install.sh` runs `docker load`, places the models, then `docker compose up -d`.

Rules that keep this working:
- Pin **every** version: base images by tag *and* digest, Python deps in a lock file, npm `package-lock.json` committed.
- The UI must not load anything from the internet: no Google Fonts, no CDN scripts, no external map tiles. Bundle fonts and icons locally.
- No container may need internet at **startup or runtime**. Test this: run the stack with networking to the outside blocked (`internal: true` network in compose) before every release.
- The syslog server and SNMP server ship as their own bundles (`syslog-server`, `snmp-server`) next to the `monicomm` bundle. They use host networking on their own VMs, so the `internal: true` rule applies to the Monicomm stack only.
- Optional: a local Docker registry and Python/npm mirrors inside the closed network, for updates.

---

## 6. Front-end conventions

> The full visual rules (colors, font, layout, components) are in **section 6A, UI design system**. Every page must follow them so the six modules look like one product.

- It's a **web app** served by the `proxy` (nginx) container. Users open it in a browser inside the closed network. Nothing is installed on client machines.
- React + TypeScript, built with Vite.
- UI libraries, per the shared `108/CLAUDE.md` rules: **Base UI** (`@base-ui/react`) for
  primitives, `sonner` for toasts, `cmdk` for the command menu, `@number-flow/react` for live counters.
  Install only these exact package names.
- **PROPOSED:** Tailwind CSS + shadcn/ui. Needs team approval before adding.
- Charts: **PROPOSED** Apache ECharts (handles large time series). Topology graph: **PROPOSED** Cytoscape.js or React Flow.
- One page per feature, plus a shared layout (side nav with the six features, global search with ⌘K).
- **Language (DECIDED):** English first, with RTL supported from day one; Hebrew strings come later.
  All UI text goes through `web/src/i18n/` (`t('key')`), and CSS uses logical properties only
  (`margin-inline-start`, `inset-inline-end`, ...), never `left`/`right`. Commands, configs and IPs stay LTR.
- **Styling (for now):** plain CSS files per feature using the tokens, no Tailwind until the team decides (open question 8).
- **Shell (built):** module list `web/src/modules.ts`, layout `web/src/components/layout/` (side nav, top bar with
  time range, RTL and theme toggles), shared components `web/src/components/ui/`, tokens `web/src/styles/tokens.css`,
  global styles `web/src/styles/app.css`. Each module adds a page under `web/src/features/<module>/` and a case in `web/src/App.tsx`.

---

## 6A. UI design system (DECIDED: look and feel)

**The look:** modern, light and friendly, in **pastel colors**. Take **monday.com**'s colorful
status pills, rounded cards and board-style tables, and **Grafana**'s panel grid, time-range
picker and dense data views. Calm by default. Color is for meaning (status, severity, which module you're in), not decoration.

### The one rule
**All colors, fonts, sizes, spacing, radii and shadows come from design tokens** in
`web/src/styles/tokens.css` (CSS variables). No hex codes, pixel font sizes or ad-hoc shadows
inside components. Need a new value? Add a token in a PR, and update this section in the same PR.
All UI is built from shared components in `web/src/components/ui/`. Don't restyle a component locally. Fix it or add a variant there.

### Typography
```css
--font-sans: "Segoe UI", "Segoe UI Variable Text", system-ui, -apple-system, Roboto, "Helvetica Neue", Arial, sans-serif;
--font-mono: "Cascadia Mono", Consolas, "Liberation Mono", monospace;   /* IPs, MACs, ports, log lines, packets */
```
- **Segoe UI is a Microsoft system font.** We don't bundle the font file (its license doesn't allow it). It comes from the
  user's Windows machine. Non-Windows clients fall back to the next font in the stack. This also keeps us air-gap safe: no web-font downloads.
- Segoe UI also covers Hebrew, so it works if we add RTL later.
- Weights: **400** (regular) and **600** (semibold) only.
- Numbers in tables, counters and charts use `font-variant-numeric: tabular-nums` so they line up.

| Token | Size / line height | Use |
|---|---|---|
| `--text-xs` | 12 / 16 | badges, axis labels, timestamps |
| `--text-sm` | 13 / 18 | table cells, secondary text |
| `--text-base` | 14 / 20 | **default body text** |
| `--text-md` | 16 / 24 | panel titles |
| `--text-lg` | 20 / 28 | page titles |
| `--text-xl` | 24 / 32 | big stats on dashboard tiles |
| `--text-2xl` | 32 / 40 | hero numbers (KPI) only |

### Colors: light theme (default)
| Token | Value | Use |
|---|---|---|
| `--bg` | `#F6F7FB` | app background |
| `--surface` | `#FFFFFF` | cards, panels, tables |
| `--surface-2` | `#F0F2F8` | hover rows, inputs, inner sections |
| `--border` | `#E3E6EF` | card and table borders |
| `--text` | `#1F2433` | main text |
| `--text-muted` | `#6B7185` | secondary text |
| `--primary` | `#5B4FD6` | primary buttons, links, focus ring (lavender) |
| `--primary-soft` | `#ECEAFF` | selected nav item, primary tags |

### Colors: dark theme (Grafana-style, for NOC wall screens)
| Token | Value |
|---|---|
| `--bg` | `#14161F` |
| `--surface` | `#1C1F2B` |
| `--surface-2` | `#252938` |
| `--border` | `#2F3446` |
| `--text` | `#E8EAF2` |
| `--text-muted` | `#9AA0B4` |
| `--primary` | `#8E85F5` |

Both themes are required. The default follows the OS setting, and there's a toggle in the top bar.
In dark mode, the `-strong` status colors are lifted for contrast on dark surfaces (values in `tokens.css`),
and the `-soft` colors become their `-strong` color at 18% opacity.

### Status colors (monday-style pills; the same everywhere)
Each status has a **soft** background and a **strong** text/icon color. Every pair below is checked to pass WCAG AA (≥ 4.5:1).

| Status | Soft (bg) | Strong (text/icon) | Means |
|---|---|---|---|
| `ok` | `#D9F5E7` mint | `#1B7A50` | up, healthy, resolved |
| `warning` | `#FFF1C7` butter | `#8A5A00` | degraded, high utilization |
| `critical` | `#FFDDE0` coral | `#B42D41` | down, error, security event |
| `info` | `#DCEEFF` sky | `#2563A8` | informational, in progress |
| `neutral` | `#ECEDF2` grey | `#555B6E` | unknown, not polled, closed |
| `accent` | `#FFE6D6` peach | `#9C4517` | new, changed, needs review |

- Status is **never shown by color alone**: always color + icon + text (for example ● Down).
- Severity mapping for syslog: emerg/alert/crit → `critical`; err/warning → `warning`; notice/info → `info`; debug → `neutral`.

### Module accent colors
Each module has its own pastel accent (nav icon, page header stripe, chart default), like monday.com boards:

| Module | Accent |
|---|---|
| Chat AI | lavender `#C3B8FF` |
| Dashboard | periwinkle `#9DB4FF` |
| Analyzer | mint `#8FE0C4` |
| Incident Investigator | coral `#FFA3AE` |
| Mapper | sky `#8FD3F5` |
| Chatchup (PCAP) | peach `#FFC29E` |

### Chart palette (categorical, in this order)
`#8EA8FF` periwinkle · `#7FD8BE` mint · `#FFB38A` peach · `#C3A6FF` lavender · `#FF9AA8` pink · `#7CCCF2` sky · `#F5D36B` butter · `#A8D672` pistachio
- Lines are 2px, areas use 20% fill. Gridlines use `--border`. Axis text uses `--text-muted` at `--text-xs`.
- Status charts (up/down, severity) use the **status** colors, not the categorical palette.
- No more than 8 series per chart. Group the rest into "Other".
- One shared chart theme file (`web/src/charts/theme.ts`). Don't style charts one by one.

### Shape, spacing and depth
- **Spacing:** 4px grid. Tokens `--space-1`…`--space-8` = 4, 8, 12, 16, 20, 24, 32, 48.
- **Radius:** `--radius-sm` 6px (inputs, small buttons) · `--radius-md` 10px (buttons, menus) · `--radius-lg` 14px (cards, panels, dialogs) · `--radius-pill` 999px (status pills, tags).
- **Shadows:** soft and low. `--shadow-1: 0 1px 2px rgba(31,36,51,.06), 0 1px 3px rgba(31,36,51,.08)` for cards; `--shadow-2: 0 8px 24px rgba(31,36,51,.12)` for menus and dialogs. No hard or dark shadows.
- **Motion:** 150–200ms ease-out for hover and open/close. Respect `prefers-reduced-motion`. No decorative animation on data screens.

### Layout (the same app shell on every page)
```
┌──────────┬──────────────────────────────────────────────────────────────┐
│          │ Top bar: page title · global search (⌘K) · time range ·      │
│  Side    │          refresh · theme toggle · alerts bell · user         │
│  nav     ├──────────────────────────────────────────────────────────────┤
│ (6 mods  │                                                              │
│  + admin)│   Content: 12-column panel grid (Grafana-style)              │
│          │   ┌─────────┐ ┌─────────┐ ┌──────────────────────┐           │
│ 240px /  │   │ stat    │ │ stat    │ │ chart panel          │           │
│ 64px     │   └─────────┘ └─────────┘ └──────────────────────┘           │
│ collapsed│   ┌──────────────────────────────────────────────┐           │
│          │   │ board-style table (monday-style)             │           │
└──────────┴──────────────────────────────────────────────────────────────┘
```
- **Side nav:** collapsible (240px → 64px icons only). The six modules in a fixed order (Dashboard, Chat AI, Analyzer, Incident Investigator, Mapper, Chatchup), each with its accent color.
- **Top bar:** the **time-range picker** is global (Grafana-style: Last 15m / 1h / 6h / 24h / 7d / custom) and every module respects it.
- **Panels:** white card, `--radius-lg`, `--shadow-1`, 16px padding, header with title + "⋯" menu (view full screen, export CSV/PNG, open in Investigator).
- **Board tables (monday-style):** rows grouped under colored group headers, a 4px colored stripe on the left of each group, full-width status pills in status columns, inline row actions on hover, sticky header, column picker, density toggle (comfortable / compact).
- **Kiosk mode** for the Dashboard: full screen, dark theme, auto-rotating, no nav (for NOC wall screens).
- **Screen sizes:** desktop-first. Designed for 1440px, must work down to 1280px, usable at 1024px. Mobile is out of scope.

### Components (use these, don't reinvent)
Button (primary / secondary / ghost / danger) · Input · Select · Combobox · Checkbox · Switch · Tabs ·
Dialog · Drawer (side panel for details) · Menu · Tooltip · Toast (`sonner`) · Command menu (`cmdk`) ·
StatusPill · Tag · Panel · StatTile (with `@number-flow/react` for live counters) · DataTable/Board ·
EmptyState · Skeleton · ErrorState · ChatMessage · Timeline (Investigator) · TopologyNode (Mapper).

- **Icons:** `lucide-react` only, 16px in text and tables, 20px in nav. Icons are bundled at build time (no icon CDN).
- **Every data view has three states:** loading (skeleton, not a spinner), empty (friendly message + next action), error (what failed + retry).
- **AI content** (chat answers, summaries, root causes) has a small "AI" tag and a "Sources" list. It shows streaming text with a typing indicator.
- **Focus:** a visible 2px `--primary` focus ring on every interactive element. Everything works with the keyboard.

### Do / Don't
| Do | Don't |
|---|---|
| Use tokens and shared components | Hard-code hex colors or font sizes |
| Use soft pastel backgrounds with strong text | Put pastel text on white (unreadable) |
| Pair status color with icon + label | Use red/green alone to show state |
| Keep one primary button per view | Fill a screen with colored buttons |
| Use mono font for IPs, ports, MACs, logs | Use mono font for normal text |
| Bundle every asset locally | Load fonts, icons or scripts from the internet |

### Keeping it consistent
- **UI review:** any PR that adds or changes a page needs a screenshot (light + dark) in the PR description, reviewed by the front-end owner.
- **Lint:** stylelint/eslint rule that blocks raw hex colors and `px` font sizes outside `tokens.css`.
- **Gallery:** a `/dev/ui` route (dev builds only) shows every shared component and token so everyone can see and reuse them.

---

## 7. How we work together

### Git workflow
- `main` is always deployable. No direct pushes to `main`.
- **Every developer works on their own branch, named after their GitHub username.**
  - Your personal branch is your username, for example `amit0604`. Create it once from `main`:
    `git checkout main && git pull && git checkout -b <your-username> && git push -u origin <your-username>`
  - For separate tasks, branch under your username: `<your-username>/<type>-<module>-<short-desc>`,
    where type is `feat`, `fix`, `chore` or `docs` (for example `amit0604/feat-mapper-lldp-discovery`).
  - Never commit to someone else's branch unless they ask you to.
  - Keep your branch current: `git pull --rebase origin main` often, at least daily.
  - Code reaches `main` only through a pull request from your branch.
- Every change goes through a pull request with at least **one reviewer**.
- Commit messages: [Conventional Commits](https://www.conventionalcommits.org/) (`feat(analyzer): add syslog parser`).
- Squash-merge PRs.

### Definition of done (for any PR)
- [ ] Works with `docker compose up` from a clean checkout
- [ ] Doesn't need internet at runtime
- [ ] Tests added/updated and passing (`pytest` for api, `vitest` for web)
- [ ] Lint/format clean (`ruff` + `black` for Python, `eslint` + `prettier` for web)
- [ ] New config variables added to `.env.example`
- [ ] DB changes come with a migration
- [ ] This file updated if a decision, API contract or module boundary changed

### Tests and development pipeline (DECIDED)
Everyone runs the **same checks**, locally and in CI, so "works on my machine" means it works for everyone.

| Check | What it enforces | Tool |
|---|---|---|
| Air-gap check | No public URLs, CDNs, cloud AI or web-font hosts in app source | `scripts/check_airgap.py` |
| API format + lint | One Python style, common bugs, basic security rules | `ruff format`, `ruff check` |
| API tests | Unit + API tests, **coverage ≥ 80%** or the run fails | `pytest` + `pytest-cov` |
| Web format + lint | One TS/CSS style. **Blocks raw hex colors, `rgb()` and px font sizes outside `tokens.css`** (section 6A) | `prettier`, `eslint`, `stylelint` |
| Web typecheck + tests + build | Strict TypeScript, component tests, production build | `tsc`, `vitest` + Testing Library, `vite build` |
| Docker smoke test | Whole stack starts, UI and API answer through nginx, and **the api container can't reach the internet** | `scripts/smoke_test.sh` |

**Before you push:** run the full suite (needs Python + [uv](https://docs.astral.sh/uv/), Node 22, Docker):
```powershell
.\scripts\check.ps1            # Windows. Add -Docker for the full stack test
./scripts/check.sh             # Linux / macOS / Git Bash. Add --docker
```
**On every push (REQUIRED):** the repo's pre-push hook (`.githooks/pre-push`) runs the full check suite and **cancels the push if anything fails**. It also blocks direct pushes to `main`. Enable it once, right after cloning:
```powershell
git config core.hooksPath .githooks
```
Don't bypass it with `--no-verify`. CI runs the same checks anyway, and a red PR can't be merged.

**On every commit (optional but recommended):** `uv tool install pre-commit` then `pre-commit install`. It runs the fast checks (format, lint, air gap, secrets).
**On every push and PR:** GitHub Actions (`.github/workflows/ci.yml`) runs all of the above. **A PR can't be merged to `main` until CI is green and one reviewer approves.**

Rules:
- New code comes with tests. Bug fixes come with a test that fails without the fix.
- API tests live in `api/tests/`. Web tests sit next to the component (`Foo.tsx` → `Foo.test.tsx`).
- Don't disable a lint rule to make CI pass. If a rule is wrong, change it for everyone in its config file in its own PR.
- A line that must mention an external URL on purpose (for example a test that checks it's refused) gets the comment `airgap: allow`.
- Repo-wide editor settings: `.editorconfig`, LF line endings (`.gitattributes`), recommended VS Code extensions in `.vscode/extensions.json`.
- Every PR uses the template in `.github/pull_request_template.md` (the definition-of-done checklist).

### Decisions
Big technical choices get a short ADR in `docs/adr/NNNN-title.md` (context, decision, consequences)
and a one-line entry in the decision log below.

### API contract
- REST under `/api/v1/<module>/...`, JSON, snake_case fields.
- Live updates over WebSocket at `/api/v1/ws`.
- FastAPI generates the OpenAPI spec at `/api/docs`. The front end generates its API types from it, so the contract can't drift.

---

## 8. Team and ownership

| Area | Owner | Backup |
|---|---|---|
| Project lead / architecture | _TBD_ | |
| Chat AI (ChatIAF) | tomer775 | |
| Dashboard | _TBD_ | |
| Analyzer (SNMP / syslog / logs) | _TBD_ | |
| Incident Investigator | _TBD_ | |
| Mapper | _TBD_ | |
| Chatchup (PCAP) | _TBD_ | |
| Platform: Docker, DB, LLM, air-gap bundle | _TBD_ | |
| Front-end shell and design system | tomer775 | |

**Target hardware (fill in):** CPU ___, RAM ___, GPU ___ (VRAM ___), disk ___, OS ___

---

## 9. Roadmap (PROPOSED)

| Phase | Goal | Done when |
|---|---|---|
| **0. Foundation** | Repo skeleton, compose stack, DB, auth, LLM gateway, UI shell with 6 empty pages, offline bundle script | `docker compose up` shows the UI and can send a prompt to the local model, all with outside networking blocked |
| **1. Data in** | Collector: syslog + SNMP polling + traps; storage; basic inventory | Real devices show up and their logs/metrics land in the DB |
| **2. See it** | Dashboard v1, Mapper v1 (LLDP/CDP/ARP), Analyzer v1 (log parsing + findings) | A technician can see health, map and findings |
| **3. Ask it** | Chat AI with tools, Chatchup PCAP upload + summary | Chat answers network questions with sources; a PCAP gets parsed and summarized |
| **4. Investigate** | Incident Investigator with timeline + root cause, anomaly detection, Analyzer change impact analysis | An incident can be opened, investigated and closed with AI help. A proposed change gets an impact report before it's made |
| **5. Harden** | Security review, performance, backups, docs, VM/container discovery | Release candidate for the closed network |

---

## 10. Security baseline

- Login required for everything. Roles: `admin`, `technician`, `viewer`. **PROPOSED:** local users first, LDAP/AD later if the closed network has it.
- HTTPS inside the network (self-signed or internal CA certificate).
- SNMP v3 preferred. Credentials (SNMP communities, hypervisor/API passwords) stored encrypted, never in git, never in logs, never sent to the LLM.
- Device credentials live only on the SNMP server. Monicomm and the LLM run on a VM that is firewalled off from network devices.
- Uploaded PCAPs and logs can contain sensitive data: access control per user/role, retention policy, delete on request.
- Audit log of who viewed or ran what (including AI tool calls).

---

## 11. Open questions

1. ~~Confirm feature 6: is "pickup files" = **PCAP** files?~~ Resolved: yes, module `pcap`, product name Chatchup.
2. Target hardware: is there a GPU? That decides the model size and Ollama vs vLLM.
3. Expected scale: number of devices, syslog messages per second, PCAP sizes.
4. Which hypervisors / container platforms must the Mapper support?
5. ~~UI language~~ Answered: English first with RTL support, Hebrew later (§6).
6. Authentication: local users or LDAP/Active Directory?
7. Data retention period for logs, metrics and captures.
8. Tailwind + shadcn/ui for the front end: yes or no?
9. Syslog/SNMP servers: open questions in `docs/plans/syslog-snmp-deployment.md` §12 (device families and versions, management path, vSphere layout, write approval, NETCONF).
10. Change impact analysis: which device vendors/OS config formats must we read for pasted config diffs (Cisco IOS, Juniper, FortiGate...)?

---

## 12. Decision log

| Date | Decision | Status |
|---|---|---|
| 2026-11-25 | System is air-gapped, fully local, delivered as Docker containers | DECIDED |
| 2026-11-25 | Six modules: Chat AI, Dashboard, Analyzer, Incident Investigator, Mapper, Chatchup (PCAP) | DECIDED |
| 2026-11-25 | UI: pastel design system, Segoe UI font, Grafana + monday.com style, light and dark themes (section 6A) | DECIDED |
| 2026-11-25 | Analyzer includes change impact analysis ("what if"): simulation only, never applied to devices (section 2.3) | DECIDED |
| 2026-11-25 | Live incident analyzer reacts only to abnormal events; normal operation stores and shows nothing (section 2.4) | DECIDED |
| 2026-11-25 | Dev-only exception to C1: `MONICOMM_LLM_PROVIDER=gemini` (Google AI Studio) for local development without a GPU. Works only with `MONICOMM_ENV=dev` set explicitly (default is `prod`), key only in the local `.env`, the Docker api can't reach it (internal network); default stays `ollama` | PROPOSED (needs team approval) |
| 2026-11-25 | Shared test + CI pipeline: ruff/pytest, prettier/eslint/stylelint/vitest, air-gap check, Docker smoke test (section 7) | DECIDED |
| 2026-11-25 | `web` (nginx) serves the UI and proxies `/api`, so it also plays the `proxy` role for now. Backend containers sit on an `internal` Docker network with no way out | DECIDED |
| 2026-11-25 | Python/FastAPI backend, React/TS front end, Postgres+Timescale+pgvector, Redis, Ollama/vLLM | PROPOSED |
| 2026-11-25 | Syslog server and SNMP server are separate Docker deployments on their own vSphere VMs, forwarding to Monicomm over mTLS; device credentials and config writes live only on the SNMP server | PROPOSED |
| 2026-11-25 | Chatchup = PCAP module; parser is `dpkt` (pure Python), tshark/Zeek only if deeper dissection is needed | DECIDED |
| 2026-11-25 | Chat AI is read-only: it proposes changes, a human approves in the UI, the configurator applies (§2.1) | DECIDED |
| 2026-11-25 | UI in English first with RTL support built in; Hebrew later (§6) | DECIDED |
| 2026-11-25 | Front-end shell, tokens and shared components built in `web/` (React 19 + TS + Vite, plain CSS + tokens) | DECIDED |
| 2026-11-25 | Chat AI answers only networking/IT topics (§2.1 scope); prototype labels mock data and simulated AI explicitly | DECIDED |
| 2026-11-25 | Chat system prompt lives in `api/app/ai/prompts/chat_system.md`; enforcement stays in code, not in the prompt | PROPOSED |

---

## 13. Glossary

- **SNMP**: Simple Network Management Protocol. Polls device counters; devices send *traps* on events.
- **Syslog**: standard protocol for devices to send log messages (port 514).
- **LLDP / CDP**: protocols switches use to announce neighbors; the main source for topology.
- **NetFlow / sFlow / IPFIX**: flow records (who talked to whom, how much).
- **PCAP**: packet capture file (Wireshark/tcpdump format).
- **RAG**: retrieval-augmented generation. The LLM answers using documents we retrieve for it.
- **Air-gapped**: physically isolated from the internet.
