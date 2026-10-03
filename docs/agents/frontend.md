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

## Viewer change = fresh screen (keyed boundary)

Anything that belongs to the person looking — unsaved drafts, open dialogs, watchlist marks, claim/owner
state, pending saves and their timers — must live **under a boundary keyed on player + viewer**, so React
remounts it on logout, login or an account switch. The boundaries are the thin exported wrappers
`PlayerPage` → `PlayerPageBody`, `ScoutPage` → `ScoutDeskBody`, `WatchlistPage` → `WatchlistBody`, `ShowcaseSection` → `ShowcaseSectionBody`
and `LocalPlayerPage` → `LocalPlayerProfile`; the key comes from `viewerKey(token)` /
`showcaseScope()` in `src/lib/player-card.js`. Never add state to a wrapper, and never key viewer-bound
state by player id alone: a signed-in view can carry fields the server withholds from the next viewer.
For state that a late request might write (watch marks, an open dialog) use
`useViewerState` (`src/hooks/useViewerState.js`): a setter made for one viewer does nothing once another
is on screen. `tests/viewer-boundary.test.mjs` pins the wrappers; the lane spec
(`e2e/player-card.spec.mjs`) drives logout / login / switch with held responses.

Remounting drops component state; it does **not** stop a handler that is already running. Two more rules
close that:

- **The shared request layer is not viewer-bound.** `APIService.request` delivers answers to their
  caller even if the credential changed meanwhile — pages outside the keyed boundaries (club pages,
  pricing, …) do not re-read on a sign-in change and must still render. Its one rule: a **401 for a
  credential that is no longer current** comes back as a plain failure (no `status`,
  `staleCredential: true`), so no caller signs the current session out, opens the sign-in prompt or clears
  anything because of it (e.g. an expired saved sign-in, or an account switch, while a page loads).
- **Viewer-bound components talk through their lifetime.** `const life = useViewerLifetime()`,
  `const api = life.api` instead of `APIService`, and `useGuarded(life, fn)` around `navigate`, logout,
  the sign-in prompt and anything else global. Requests made through `life.api` ARE bound to the viewer:
  once it has changed, `api.x()` returns a rejected `StaleViewerError` without sending (a multi-step
  handler cannot issue its follow-up as the next viewer), and an answer that lands after the change is a
  `StaleViewerError` — never data, never an ordinary failure; swallow it silently. Guarded effects do
  nothing once the component is unmounted or the viewer has changed. Side effects that are not React
  state — a file download, clipboard after an await, `window.open`, a kept object URL — happen only
  through a guard, AFTER the whole body has been read through `life.api`: never call an API helper that
  downloads by itself (`api.download*`); fetch the Blob (`fetchScoutCsv`) and save it with
  `useGuarded(life, save)`. A viewer-bound component that is also mounted outside the keyed pages keys
  itself on `useViewerKey()` (as `CommentSection` does), so a stale answer never lands in a live
  instance. Sign-out plus
  prompt is one guarded step (`expireSession`), not two calls. Put `api` in hook dependency arrays.
  `tests/viewer-boundary.test.mjs` fails if a file in its list references `APIService`, calls `fetch`,
  takes `navigate` / `logout` / `openLoginModal` unguarded, or downloads outside a guard — add new viewer-bound components to that
  list. Rules and unit tests: `src/lib/viewer-lifetime.js`, `tests/stale-viewer-requests.test.mjs`.

## Deploy

Push touching only `academy-watch-frontend/**` triggers the fast `Deploy Frontend (fast)`
workflow (~1–2 min, no backend rebuild). The `Deploy Frontend` job can intermittently 403 on
the MCR base image — just `gh run rerun <id> --failed` (debugging.md), not a code bug.

## Verify a UI change

Don't iterate blind. Run `pnpm dev`, drive the affected page (Playwright for anything
interactive: `pnpm exec playwright test tests/<file>.mjs`), and confirm the change renders —
especially data-heavy pages, where a slow/oversized payload can block render even when the data
is correct (debugging.md).
