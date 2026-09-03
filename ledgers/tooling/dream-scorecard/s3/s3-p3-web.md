# S3-P3 — Web (React/Vite) for billing, Scout Pro, club program editing (frontend only; builds against the contracts with mocks)

Worktree: __WT__ (branch `feat/s3-p3-web`, base `origin/main`). Common brief: __COMMON__. Contracts: __CONTRACTS__ (every request/response you mock MUST match them byte-for-byte). Vite port for your spec: 5181.

The backend for these routes is being built in parallel; you never call it. `GET /api/billing/config` returning 404 means
"billing is dark" — every billing UI must degrade to today's behaviour on that 404 (no console errors, no broken layout).

## Requirements
1. `src/lib/api.js` (`APIService` static methods, same style as `getClubRoster`). First add a `nullOn404` request option to
   `APIService.request` (`api.js:308-339`) that returns `null` immediately after `fetch` when the status is 404 — BEFORE any error
   parsing or `console` logging (today every non-OK response logs twice). Methods: `getBillingConfig()`, `getBillingMe()`,
   `getAdminBillingSummary()`, `getScoutEntitlements()` (all `nullOn404`), `createBillingCheckout({ product_code, price_code, client_key })`,
   `createBillingPortal()`, `getClubProfile(programId)`, `putClubProfile(programId, payload)`,
   `listClubUpdates(programId)`, `createClubUpdate(programId, payload)`, `deleteClubUpdate(programId, updateId)`,
   `adminListProfileRevisions(status = 'pending')`, `adminReviewProfileRevision(programId, revisionId, payload)`,
   `adminListProgramUpdates(status = 'pending')`, `adminReviewProgramUpdate(programId, updateId, payload)`. The five admin methods
   MUST pass `{ admin: true }` as `request`'s third argument like the existing admin funding methods (`api.js:1889-1935`); the summary
   combines `admin: true` with `nullOn404`. `downloadScoutCsv` (`api.js:578-592`) reads errors as text today — make it parse JSON by
   content type and attach `err.body` exactly like `APIService.request` so the 403 body is reachable.
2. `pages/PricingPage.jsx`: on mount fetch the config. `null` → the page is UNCHANGED from today. Enabled → the Scout Pro card
   shows the real price(s) (`Intl.NumberFormat(undefined, {style:'currency', currency})` on `unit_amount/100`; "See price at
   checkout" when `unit_amount` is absent), a monthly/yearly toggle only when both prices exist, and a "Subscribe" CTA:
   signed-out → the existing sign-in path that returns to `/pricing`; signed-in → `createBillingCheckout` with a `client_key`
   (UUID from `crypto.randomUUID()`, stored in `sessionStorage` per product+price and REUSED on retry) then
   `window.location.assign(checkout_url)`; emit the product event `checkout_started` (existing events helper) before navigating.
   Handle `409 already_subscribed` (link to `/account/billing`), other errors inline. `?checkout=canceled` → a dismissible
   notice "Checkout canceled — nothing was charged." Never show a donate/club-bundle CTA.
3. New `pages/AccountBillingPage.jsx` at route `/account/billing`. Do NOT wrap it in the existing `RequireAuth` (it redirects to `/`,
   `App.jsx:525-533`): when there is no token the page calls `openLoginModal` once and renders no billing data while the URL stays at
   `/account/billing`, so sign-in returns in place. Signed in: loads `getBillingConfig` + `getBillingMe` + `getScoutEntitlements`;
   any required one `null` → a single calm panel "Billing isn't available yet." Otherwise: each subscription as a card (product name
   from `config.products[].name` by `product_code`, fallback the code; status badge; "Renews on <date>" or "Ends on <date>" when
   `cancel_at_period_end`; price/interval), the entitlements summary (tier, source, what is unlocked), and "Manage billing" rendered
   ONLY when `has_billing_account` is true → `createBillingPortal` → `window.location.assign`; a racing 409 `no_billing_account` shows inline.
   `?checkout=success` → success banner, emit `checkout_completed` ONCE, then strip the query via `history.replaceState`. BEFORE
   building this flow add `session_id` to `SENSITIVE_PARAMS` in `src/lib/track.js:18-25` (analytics captures the current query in every
   event/pageview and would persist the Stripe checkout-session id; the separately generated analytics `session_id` field stays).
   Add a "Billing" entry to `Navigation.navItems` inside `src/App.jsx:560-597` next to Settings (one link, no redesign).
4. Scout gating UX: the CSV export controls are `src/pages/ScoutPage.jsx:675-677,846-849` and `src/pages/WatchlistPage.jsx:160-170,227-230`;
   the new-list controls are `src/pages/ListsPage.jsx:579-595,746-750,849-853` (all three currently only console-log failures). In all
   three, catch the exact 403 body `{error:"scout_pro_required", feature, upgrade_path}` and show an inline upgrade prompt
   ("Scout Pro unlocks <feature>" + link to `/pricing`). Pro badge: `AuthContext` (`src/context/AuthContext.jsx:4-15`) and
   `buildAuthSnapshot` (`src/context/buildAuthSnapshot.js:3-23`) drop unknown fields and `APIService.getProfile` (`api.js:222-239`)
   persists only role/display fields — retain the `/auth/me` `scout_pro` object as `scoutPro`, emit it after `getProfile`, clear it on
   logout, expose it as `auth.scoutPro`. When `auth.scoutPro?.enabled === true` and the feature is false, render a small "Pro" badge on
   the control — still clickable (the server is the truth). Never hide features client-side based on tier alone.
5. `pages/MyClubConsole.jsx` "Club profile" tab (`MyClubConsole.jsx:1762-1788,1918-1938`, read-only `ClubProfile` today; keep the
   tab name): replace the read-only view with an editor bound to `getClubProfile`/`putClubProfile`:
   fields per the contract (summary, age groups, activities, funding purpose, official URL, safeguarding URL, media URLs,
   external support provider select + URL), "Approved" vs "Pending review" status blocks, Save → PUT (replaces the pending
   revision), per-field errors from `validation_failed`. Below it an "Updates" section: list with status badges, a composer
   (title/body/impact), delete/withdraw, the `pending_limit_reached` message.
6. `pages/ProgramPage.jsx`: render `updates` as "Latest from the program" (title, body, impact, date) and `external_support` as
   an outbound button labelled "Support on <label>" with `target="_blank"` and `rel="noopener noreferrer"`. Keep the existing
   "Support is not live yet" copy ONLY when there is no external link. `is_fundable` false must never render a donate CTA.
7. `pages/admin/AdminDashboard.jsx`: a "Revenue" tile from `getAdminBillingSummary` (active subs, MRR formatted, past due,
   webhook failures 24h); `null` → tile not rendered. `pages/admin/AdminFunding.jsx`: two review queues (profile revisions,
   program updates) with approve/reject + required reason, showing the program name and the submitted content.
8. `pages/LegalPages.jsx`: fetch the config on mount. Enabled → Terms gains a section "Paid subscriptions" (auto-renews each
   period; cancel any time via the billing portal, effective at the end of the paid period; prices are shown before purchase;
   payments are processed by Stripe and we never store card numbers; no refunds for partial periods except where required by
   law) and Privacy replaces the "Stripe pays writers" sentence with "When you buy an optional paid feature, Stripe processes
   the payment and receives your payment details; we store only your Stripe customer id and subscription status." Dark →
   the writer-payment sentence is REMOVED (it is false today) and nothing about subscriptions appears. Draft wording only —
   the owner approves before launch; keep it short and plain.
9. `e2e/billing.spec.mjs` (new, mirrors `account-rails.spec.mjs`; mock every `**/api/**` explicitly — do NOT rely on its `{}`
   fallback). First make `playwright.config.js:42-63` skip BOTH webServers when `E2E_BASE_URL` is set
   (`webServer: process.env.E2E_BASE_URL ? undefined : <existing config>`), so your manually started Vite on 5181 is the only server.
   The `/api/auth/me` mock includes the P1 fields `scout_tier` and `scout_pro`. Scenarios: pricing dark (404 config → beta copy, no
   Subscribe button); pricing lit → formatted price, Subscribe posts exactly `{product_code, price_code, client_key}` and navigates to
   the mocked `checkout_url` (route it to a stub page); `/account/billing?checkout=success` → banner, exactly ONE event object named
   `checkout_completed` across all `/api/events` batch bodies (events are batched with pageviews — do not require a dedicated POST),
   and the Stripe `session_id` value absent from every event path/referrer/props; Manage billing posts to the portal; `/programs/<slug>`
   renders the Patreon button with both `rel` tokens and two updates; club console: mock `/api/me/club-claims` and `/api/me/club` as
   empty, `/api/funding/claims/me` with an approved claim on an approved program, `/api/club/<id>/roster` (members + system_brief),
   `/api/club/<id>/matches`, plus the new profile/update endpoints (`MyClub.jsx:371-433,770-788`, `MyClubConsole.jsx:1842-1869` gate
   the console) — the Club profile tab saves (assert the PUT body) and posts an update; CSV export 403 → upgrade prompt visible.
   Run only this spec on port 5181.

## ALLOWED (frontend only)
`academy-watch-frontend/src/lib/api.js`, `academy-watch-frontend/src/lib/track.js` (SENSITIVE_PARAMS only), `academy-watch-frontend/src/App.jsx`
(new route/import + the `Navigation.navItems` Billing link only), `academy-watch-frontend/src/context/AuthContext.jsx`,
`academy-watch-frontend/src/context/buildAuthSnapshot.js`, `academy-watch-frontend/playwright.config.js` (webServer guard only),
`academy-watch-frontend/src/pages/PricingPage.jsx`,
`academy-watch-frontend/src/pages/AccountBillingPage.jsx` (new), `academy-watch-frontend/src/pages/MyClubConsole.jsx`,
`academy-watch-frontend/src/pages/ProgramPage.jsx`, `academy-watch-frontend/src/pages/LegalPages.jsx`,
`academy-watch-frontend/src/pages/admin/AdminDashboard.jsx`, `academy-watch-frontend/src/pages/admin/AdminFunding.jsx`,
`academy-watch-frontend/src/pages/ScoutPage.jsx`, `academy-watch-frontend/src/pages/WatchlistPage.jsx`, `academy-watch-frontend/src/pages/ListsPage.jsx`,
new files under `academy-watch-frontend/src/components/billing/` and `.../components/club/` only,
`academy-watch-frontend/e2e/billing.spec.mjs` (new). No `package.json`/lockfile changes; do not touch `@stripe/stripe-js`.

## Commit (exactly one)
`feat(web): S3-P3 pricing checkout, account billing, club program editor + updates, program link-out, admin revenue tile (dark until billing config)`
