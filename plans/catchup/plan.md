# Catchup (PCAP investigation): build plan

- Date: 2026-11-25
- Branch: `catchup`
- Status: IN PROGRESS (phases 1-3 done, 4 blocked, 5 pending PR)

## Overview
Technician uploads a `.pcap`/`.pcapng`, the backend parses it in the background into protocols,
conversations, DNS/HTTP/TLS metadata and anomalies (retransmissions, resets, handshake latency),
and the local LLM summarizes it and answers questions scoped to that file, citing packet numbers.
Spec: PROJECT.md 2.6. We build **only** the `pcap` module; the foundation (app skeleton, DB,
worker, llm_client, UI shell, tokens) is built in parallel by the team.

## Problem in one line
Technicians need answers from a capture file without hand-reading it in Wireshark.

## Assumptions about parallel work (NOT validated; adjust when foundation lands)
| # | Assumption | If wrong |
|---|---|---|
| A1 | `app.ai.llm_client` exposes `async def chat(messages: list[dict]) -> str` | change one call site in `service.py` |
| A2 | Foundation mounts module routers from `app/modules/<name>/router.py` (`router = APIRouter()`) under `/api/v1/pcap` | one line in their `main.py` |
| A3 | No DB/worker yet: results stored as JSON on disk, background work via FastAPI `BackgroundTasks` | move to DB tables + arq job later |
| A4 | UI shell, `tokens.css` and `components/ui/` arrive later; UI phase waits for them | — |

## Decisions
- Parser: **dpkt** (pure Python, no system deps, testable without Docker). tshark/Zeek later if deeper dissection is needed.
- Tests build synthetic PCAPs in code (no binary fixtures, no real traffic in git).

## Phase 1: Parser (status: DONE)
- [x] `api/app/modules/pcap/parser.py`: `analyze(path) -> dict` (counts, duration, protocol breakdown, conversations, DNS/HTTP/TLS-SNI, anomalies with packet numbers)
- [x] `follow_stream(path, conv_id) -> list[segment]`
- [x] pcap + pcapng support
- [x] `api/tests/pcap/test_parser.py`

Verification
- [x] `pytest api/tests/pcap -q` passes
- [x] Synthetic capture with a retransmission + RST is flagged with correct packet numbers
- [x] Malformed/truncated file returns an error, not a crash

## Phase 2: API + background processing (status: DONE)
- [x] `router.py`: `POST /captures` (size limit, extension + magic-bytes check), `GET /captures`, `GET /captures/{id}`, `GET /captures/{id}/streams/{conv_id}`, `DELETE /captures/{id}`
- [x] `service.py`: storage under `PCAP_DATA_DIR`, status `queued/processing/done/failed`
- [x] `.env.example`: `PCAP_DATA_DIR`, `PCAP_MAX_UPLOAD_MB`
- [x] tests via FastAPI `TestClient`

Verification
- [x] Upload → status reaches `done` → breakdown returned
- [x] Oversized / non-pcap upload rejected with 413 / 400
- [x] Path traversal in id rejected

## Phase 3: AI summary + scoped chat (status: DONE)
- [x] `api/app/ai/prompts/pcap_summary.md`, `pcap_chat.md`
- [x] `POST /captures/{id}/summary`, `POST /captures/{id}/chat` (history kept per capture)
- [x] LLM gets the compact analysis JSON, never raw payloads; answers cite packet numbers
- [x] tests with `llm_client.chat` mocked

Verification
- [x] Prompt contains analysis, not payload bytes
- [x] Response includes `sources` (packet numbers / conversation ids)

## Phase 4a: Network views + temporary tab UI (status: DONE)
Decided with the user: workshop UI (graph + inspector + timeline/time window) now, as a tab inside the site.
- [x] Parser: per-conversation time bins (adaptive), direction counts, scan/beacon hosts
- [x] `network.py` + endpoints: graph, overview, timeline, hosts/{ip}
- [x] `web/src/features/pcap/legacy/`: `mountCatchup(el)`, scoped CSS on 6A tokens, Cytoscape 3.30.2 vendored
- [x] Findings + AI assistant in the inspector

Verification
- [x] `pytest api/tests/pcap` (45 pass), ruff + black clean
- [x] In a stand-in shell at 1440 px: graph, host details, time window 2:40–3:19 (665 packets), light + dark
- [ ] Not done: JS unit tests (no web toolchain yet; vitest arrives with the shell)

## Phase 4b: React port (status: BLOCKED on A4)
- [ ] Port `legacy/` to React + shared components; loading/empty/error states as Skeleton/EmptyState/ErrorState
- [ ] `vitest` passes; screenshots light + dark; delete `legacy/`

## Phase 5: Docs + PR (status: IN PROGRESS)
- [x] PROJECT.md: resolve open question 1 (Catchup = PCAP), record A1–A3 contract, decision log row for dpkt
- [ ] Adversarial review, then PR to `main`

## Out of scope (v1)
Link to Investigation (module not built yet), tshark/Zeek, retention job, auth/roles (foundation).

## Cross-cutting notes
- Product: v1 = upload → understand → ask. Next: Investigation link.
- Data: analysis JSON is the stored knowledge; evidence = packet numbers (AI rule 4).
- Security: captures are sensitive; delete endpoint now, per-user access once auth exists; no payloads sent to LLM beyond what a question needs.
- Adoption: one page, Wireshark vocabulary technicians already know.
- Agile: each phase ships testable on its own.

## Progress notes (2026-11-25)
- Ideas borrowed from pcap-lab-workshop: port-scan and beacon rules (re-implemented on conversation data);
  its synthetic `office-network.pcap/.pcapng` used for validation: 5,629 packets, scan + beacon detected.
- Adversarial review found 11 issues (DNS rdata crash, SNI never extracted, unbounded memory, anomaly cap hid
  scans, query-string secrets to LLM, prompt injection via system role, upload spooled before size check,
  delete-during-processing crash, keep-alive false positives, LLM errors as 500 / chat race, lint config).
  All fixed with a regression test each; 35 tests pass, ruff + black clean.
- Not verified: real `llm_client` (doesn't exist yet), `docker compose up` (no Docker locally), multi-GB upload.
