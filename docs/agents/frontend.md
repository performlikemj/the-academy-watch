# Frontend — React/Vite patterns & gotchas

- pnpm only (v9, Node 20). `pnpm dev` (port 5173, proxies `/api` → :5001 via
  `vite.config.js`), `pnpm lint`, `pnpm build`, `pnpm test:e2e`.
- All API calls go through `src/lib/api.js` — add endpoint methods there; no
  ad-hoc `fetch()` in components.
- `VITE_API_BASE` is baked at **build** time. Locally leave it unset (the dev
  proxy handles routing). Manual SWA deploys must set it (see workflow.md).
- ESLint flat config (`eslint.config.js`): unused vars are errors unless prefixed
  `A-Z`/`_` (vars/args) or `_` (caught errors). Node-context files (vite/playwright
  config, `e2e/**`) get Node globals; everything else gets browser globals. The
  edit hook runs `eslint --fix` for you.
- E2E: Playwright. One file: `pnpm exec playwright test tests/<file>.test.mjs`;
  interactive: `--ui`. Tests live in `tests/` and `e2e/`.
- UI is Radix primitives (`src/components/ui/`) + Tailwind 4 — reuse the existing
  `ui/` components before writing new ones.
- `pnpm-lock.yaml` conflicts/breakage: repair surgically, never regenerate the
  whole file (see `docs/agents/invariants.md` — Dependabot corruption incident).
- Verify UI work **visually** (Playwright: load the page, screenshot, check for
  console errors) — a green `pnpm build` proves nothing about rendering.
