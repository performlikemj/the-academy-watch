# Frontend — React / Vite / Tailwind / Radix gotchas

Code-level notes for `academy-watch-frontend/`. Package manager is **pnpm** (not npm).

## Stack

React 19 + Vite 6 + Tailwind CSS 4 (`@tailwindcss/vite`) + Radix UI primitives, TipTap editor,
Stripe.js, framer-motion, `d3-force-3d` for journey maps. Pages in `src/pages/` (admin dashboard
= 14 pages under `admin/`, plus `writer/` and public Player/Team pages). Radix-based components in
`src/components/ui/`. All API calls go through `src/lib/api.js`.

## CI gates (mirror before pushing)

- `../scripts/security/check_frontend_dependencies.sh` from this directory (or
  `./scripts/security/check_frontend_dependencies.sh` from repo root) scans the
  frozen lockfile with OSV-Scanner before dependencies are restored. Use
  `./scripts/setup_frontend.sh` from repo root for setup; it skips installation
  when the installed virtual-store lock already matches.
- `pnpm lint` (ESLint flat config, `eslint.config.js`) **and** `pnpm build` (Vite) both run in
  CI — a build/type error reddens CI even with clean lint. Run the build too.
- The setup harness uses `pnpm install --frozen-lockfile` only when dependencies
  are missing/stale. A `package.json` change without a matching `pnpm-lock.yaml`
  fails install. The on-edit hook runs `eslint --fix` on `.js/.jsx/.ts/.tsx` saves.

## ESLint / lockfile traps

- `eslint-plugin-react-hooks` v7's new rules are pinned to **`warn`** in `eslint.config.js`
  pending a ~130-site migration (mostly `App.jsx`). Don't flip them to `error` casually.
- A broken **main** `pnpm-lock.yaml` (duplicate YAML key from stacked Dependabot merges) reddens
  every PR's install, not just the offending one. Fix the duplicate block **by hand** — never
  `pnpm install --lockfile-only` to regen (it silently jumps `^` versions). Full playbook in
  `debugging.md`.

## The API base URL — the #1 frontend prod bug

- **Dev**: Vite proxies `/api/*` → `http://localhost:5001` (`vite.config.js`). No env var needed.
- **Prod / manual deploy**: Azure Static Web Apps has **no proxy**, so the app needs the absolute
  backend URL baked in at build time via `VITE_API_BASE`. CI sets it from the backend FQDN; a
  local `pnpm build` without it falls back to `/api` → every call 404s, surfacing as
  "SyntaxError: The string did not match the expected pattern". Manual deploy:
  `VITE_API_BASE="https://ca-loan-army-backend.<fqdn>/api" pnpm build`.

## Deploy

Push touching only `academy-watch-frontend/**` triggers the fast `Deploy Frontend (fast)`
workflow (~1–2 min, no backend rebuild). The `Deploy Frontend` job can intermittently 403 on
the MCR base image — just `gh run rerun <id> --failed` (debugging.md), not a code bug.

## Verify a UI change

Don't iterate blind. Run `pnpm dev`, drive the affected page (Playwright for anything
interactive: `pnpm exec playwright test tests/<file>.mjs`), and confirm the change renders —
especially data-heavy pages, where a slow/oversized payload can block render even when the data
is correct (debugging.md).
