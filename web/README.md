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

## Adding your module

1. Create `src/features/<module>/` with a page component and its own CSS (tokens only).
2. Add a case for it in `src/App.tsx` (the nav entry already exists in `components/layout/modules.ts`).
3. Use strings from `src/i18n/en.ts` and logical CSS properties so RTL keeps working.
