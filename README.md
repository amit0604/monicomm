# Monicomm

AI-assisted network communication monitoring for air-gapped networks.
Read **[PROJECT.md](PROJECT.md)** first: scope, architecture, UI rules and how we work.
For diagrams of how the app is built, open **[docs/architecture.html](docs/architecture.html)** in a browser.

## Run it

```powershell
copy .env.example .env
docker compose up -d --build
```
Open http://localhost:8080. Add the local LLM with `docker compose --profile llm up -d`.

## Modules

| Module | Status | Code |
|---|---|---|
| Dashboard | Built, on demo data | `api/app/modules/dashboard/`, `web/src/features/dashboard/` |
| Chat AI (ChatIAF) | Built: in-browser prototype, plus a live API backend | `api/app/modules/chat/`, `web/src/features/chat/` |
| Analyzer | Built: change impact ("what if") simulation, on demo topology | `api/app/modules/analyzer/`, `web/src/features/analyzer/` |
| Incident Investigator | Built: live incident analyzer, with predicted and recommended rerouting | `api/app/modules/investigator/`, `web/src/features/investigator/` |
| Mapper | Built, on demo data | `api/app/modules/mapper/`, `web/src/features/mapper/` |
| Catchup (PCAP) | Built | `api/app/modules/pcap/`, `web/src/features/pcap/` |
| Login and Admin (platform) | Built: local users, dev-only model settings page | `api/app/core/auth.py`, `api/app/modules/admin/`, `web/src/features/{auth,admin}/` |

The collectors (syslog and SNMP servers) are separate deployments in `collector/`, each with its own README.

- **Chat AI backend:** the page runs on the in-browser mock by default. Build the web with `VITE_CHAT_BACKEND=api`
  to use `POST /api/v1/chat` (the local LLM over current Monicomm data).
- **Incident Investigator input:** set `MONICOMM_INVESTIGATOR_INGEST_DIR` and mount the collectors' dev-ingest
  directory in `docker-compose.yml` (see the comment there). Empty = listener off.
- **Login:** off by default (`MONICOMM_AUTH_PROVIDER=none`). For local users set it to `local` and create the first
  admin with `docker compose exec api python -m app.create_user admin`. LDAP / Active Directory and SSO (OpenID Connect)
  are set on the Admin page (with Test connection) or in `.env`; start with
  `docker compose -f docker-compose.yml -f docker-compose.directory.yml up -d` so the api can reach them.
- **Shared code:** graph and link-load logic for the Analyzer and Investigator is in `api/app/core/graph.py`;
  web API calls go through `web/src/lib/api.ts`.
- **Language:** English by default; the top bar switches to Hebrew. All UI text lives in `web/src/i18n/`.

## Develop

| Part | Folder | Dev server | Tests |
|---|---|---|---|
| API (Python, FastAPI) | `api/` | `uv run uvicorn app.main:app --reload` | `uv run pytest` |
| Web (React, TypeScript) | `web/` | `npm run dev` (proxies `/api` to port 8000) | `npm test` |

First-time setup: install [uv](https://docs.astral.sh/uv/), Node 22 and Docker. Clone the repo **outside OneDrive**
(for example `C:\Users\<you>\108\Monicomm`): OneDrive locks files and breaks git and `uv`. If `uv sync` fails with
a hardlink error, run `setx UV_LINK_MODE copy` once and open a new terminal. Then:

```powershell
git config core.hooksPath .githooks
```
```powershell
cd api; uv sync; cd ..\web; npm ci; cd ..
```
The first command turns on the required pre-push hook: every `git push` runs the tests and is cancelled if they fail.

To see the Dashboard and the Mapper without a network, set `MONICOMM_ENV=dev` and `MONICOMM_DEMO_DATA=true` in `.env` and run the API with
`uv run --env-file ../.env uvicorn app.main:app --reload`. The data is fabricated and labelled DEMO.

## Before you push

```powershell
.\scripts\check.ps1
```
This runs the same checks as CI. Details in PROJECT.md section 7.

## Branches

Work on your own branch named after your GitHub username (for example `amit0604` or
`amit0604/feat-mapper-lldp`) and open a pull request to `main`.
