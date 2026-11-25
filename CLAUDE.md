# Monicomm: instructions for AI coding assistants

Read `PROJECT.md` first. It is the team's source of truth for scope, architecture and conventions.

Hard rules:
1. **Air-gapped target.** Never add code that calls the internet at runtime: no cloud AI APIs,
   no CDN links, no external fonts or map tiles, no telemetry. All AI goes through the local
   LLM via `api/app/ai/llm_client.py`.
2. **Everything runs in Docker.** New services go into `docker-compose.yml`; new config goes into `.env.example`.
   The syslog and SNMP servers are separate deployments: their services go into `collector/syslog-server/` and
   `collector/snmp-server/`, each with its own `docker-compose.yml` and `.env.example`.
3. **AI tools are read-only** toward network devices. Never write code that changes device config.
4. Pin every dependency version and commit lock files.
5. Follow the branch, commit and definition-of-done rules in `PROJECT.md` section 7.
6. **UI must follow `PROJECT.md` section 6A.** Use only the design tokens in `web/src/styles/tokens.css`
   (no raw hex colors or px font sizes in components), build from the shared components in
   `web/src/components/ui/`, use the Segoe UI font stack, show status as color + icon + text, and support light and dark themes.
7. If you change a decision, API contract or module boundary, update `PROJECT.md` in the same change.
