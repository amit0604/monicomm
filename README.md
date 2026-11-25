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

## Develop

| Part | Folder | Dev server | Tests |
|---|---|---|---|
| API (Python, FastAPI) | `api/` | `uv run uvicorn app.main:app --reload` | `uv run pytest` |
| Web (React, TypeScript) | `web/` | `npm run dev` (proxies `/api` to port 8000) | `npm test` |

First-time setup: install [uv](https://docs.astral.sh/uv/), Node 22 and Docker. Then:

```powershell
git config core.hooksPath .githooks
```
```powershell
cd api; uv sync; cd ..\web; npm ci; cd ..
```
The first command turns on the required pre-push hook: every `git push` runs the tests and is cancelled if they fail.

## Before you push

```powershell
.\scripts\check.ps1
```
This runs the same checks as CI. Details in PROJECT.md section 7.

## Branches

Work on your own branch named after your GitHub username (for example `amit0604` or
`amit0604/feat-mapper-lldp`) and open a pull request to `main`.
