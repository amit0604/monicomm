# Monicomm web

React + TypeScript + Vite front end: the app shell, the shared design system (`PROJECT.md` §6A) and the module pages.

## Run it

```bash
cd web
npm ci
npm run dev
```

Open http://localhost:5173. The Chat AI page (ChatIAF) runs fully in the browser on mock network data, so no backend is needed yet.

## Checks

```bash
npm test          # vitest
npm run lint      # eslint + stylelint (blocks raw hex colors and px font sizes outside tokens.css)
npm run build     # type-check + production build into dist/
```

## Layout

| Path | What |
|---|---|
| `src/styles/tokens.css` | All design tokens. The only file allowed to hold raw colors or px font sizes. |
| `src/components/ui/` | Shared components (Button, StatusPill, Tag, Panel, EmptyState). Fix or extend here, never restyle locally. |
| `src/components/layout/` | App shell: side nav (six modules, fixed order), top bar (time range, RTL toggle, theme toggle). |
| `src/i18n/` | UI strings. Add a language by copying `en.ts` and registering it in `index.tsx`. |
| `src/features/chat/` | ChatIAF. `backend.ts` is the single seam to swap the mock for the real API. |
| `src/features/chat/mock/` | Mock network, read-only tools, impact analyzer, configurator. The assistant must never import the configurator (a test checks this). |

## ChatIAF in prototype mode: how replies are chosen

There is **no AI model** behind the chat yet. Each message goes through `src/features/chat/mock/intent.ts`, a **rule-based** classifier (English + Hebrew patterns), and is routed by intent:

| Intent | Reply |
|---|---|
| `TECHNICAL_KNOWLEDGE` | Local knowledge base (`mock/knowledge.ts`), labeled as such. A topic not in the knowledge base gets an explicit "not available yet". |
| `NETWORK_INFORMATION`, `CONFIG_HISTORY`, `ALERT_INFORMATION`, `INCIDENT_INFORMATION`, `IMPACT_INFORMATION` | Demo scenarios on mock data. They only run on an **anchored** match (a named device, port or IP, or phrases like "what changed" / "active alerts"), never on a loose keyword. |
| `SYSTEM_CAPABILITIES`, `DATA_PROVENANCE`, `PERMISSION_QUESTION`, `GREETING` | Fixed, honest replies (`mock/guardrails.ts`). |
| `FOLLOW_UP` | Resolved against the previous reply's topic; **New chat** clears it. No previous topic → asks what to explain. |
| `OUT_OF_SCOPE`, `MIXED`, `POLICY_VIOLATION`, `AMBIGUOUS` | Polite decline, answer only the in-scope part, refuse rule changes, or ask to clarify. |

Every assistant message shows how it was produced ("rule-based classifier · intent … · confidence"), so the rules are never presented as a model.

**Limits of the local classifier:** it matches patterns, not meaning. New phrasings can fall to `AMBIGUOUS`, follow-ups only look one reply back, and Hebrew answers exist for the knowledge base and guardrails while demo scenarios answer in English. The regression tests (`mock/intent.test.ts`) pin the known cases.

**Software policy vs model guidance:** `src/features/chat/policy.ts` holds the rules the code enforces (read-only, approval, second approver). `api/app/ai/prompts/chat_system.md` is the system prompt **template** for the future local model. It is not in use yet.

## Adding your module

1. Create `src/features/<module>/` with a page component and its own CSS (tokens only).
2. Add a case for it in `src/App.tsx` (the nav entry already exists in `components/layout/modules.ts`).
3. Use strings from `src/i18n/en.ts` and logical CSS properties so RTL keeps working.
