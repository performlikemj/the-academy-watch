# AGENTS.md

> This file defines how AI agents operate in this codebase.
> Read this first. Follow it always.

## Quick Start

1. Read `CONTINUITY.md` (or create it if missing)
2. Determine if this is trivial (<15 min, no dependencies) or needs a ledger
3. Do the work
4. Update ledgers before finishing

---

## Project Overview

**What:** The Academy Watch — Football academy tracking platform with AI newsletters
**Stack:** Flask 3.1 + SQLAlchemy (backend), React 19 + Vite 6 + Tailwind (frontend), PostgreSQL
**Test command:** `cd academy-watch-frontend && pnpm lint && pnpm test:e2e`
**Dev server:** Backend: `cd academy-watch-backend && python src/main.py` | Frontend: `cd academy-watch-frontend && pnpm dev`
**Frontend setup:** `./scripts/setup_frontend.sh` (OSV scan first; installs only when missing/stale)

---

## Operating Principles

1. **Ledger-first:** Read CONTINUITY.md before working. Update it when state changes.
2. **Single source of truth:** Ledgers and repo are authoritative; chat may be incomplete.
3. **Small updates:** Bullets over paragraphs. Facts only.
4. **No guessing:** Mark uncertainty as UNCONFIRMED. Ask 1-3 targeted questions.
5. **Right-size ceremony:** Trivial tasks get one-liners; complex work gets ledgers.

---

## File Locations

| File | Purpose |
|------|---------|
| `CONTINUITY.md` | Master ledger — current project state |
| `ledgers/` | Epic, planning, and task ledgers |
| `ledgers/archive/` | Completed ledgers |
| `scripts/ralph/` | Autonomous execution loop |
| `*/AGENTS.md` | Subdirectory-specific conventions |

---

## Bootstrap (First Run)

If `CONTINUITY.md` doesn't exist, create it with:
- Goal: inferred from user request or UNCONFIRMED
- State: Now = current task, Next = TBD

---

## Interactive → Ralph Handoff

Tasks flow from interactive sessions to autonomous execution:

**Planning ledger is the single source of truth** — both modes use it.

### Task Status Flow

| Status | Meaning | Ralph Action |
|--------|---------|--------------|
| `pending` | Has unmet dependencies | Skip |
| `ready` | Unblocked, can be worked | **Pick this** |
| `in-progress` | Currently being worked | Skip |
| `blocked` | Needs decision/input | Skip |
| `complete` | Done | Skip |

### To Hand Off to Ralph

1. Set any `in-progress` tasks to `ready` (if stopping mid-work)
2. Ensure acceptance criteria are explicit
3. Commit current state
4. Run: `./scripts/ralph/ralph.sh 25`

### After Ralph Completes

1. Review commits and `scripts/ralph/progress.txt`
2. Resolve any `blocked` or `failed` tasks
3. Continue interactively or run Ralph again

---

## Ledger Protocol

### Start of Turn
1. Read `CONTINUITY.md`
2. Attach to existing ledger OR create new one OR use trivial protocol
3. Update stale state before new work

### During Work
Update ledgers when:
- Goals/constraints change
- Decisions made
- Milestones reached (Done/Now/Next)
- Tests run (record result)
- Blockers identified

### Trivial Tasks
Skip ledger creation when ALL true:
- < 15 minutes
- Single file change
- No cross-task dependencies

Log one-liner in CONTINUITY.md's "Trivial Log" section.

---

## Codebase Patterns

> Agents: Add patterns here when you discover reusable conventions.

- Frozen legacy public pages use `src/lib/legacyRoutes.js` in the frontend; keep imports gated by `LEGACY_PUBLIC_PAGES`. Backend legacy URLs use `src/utils/legacy_pages.py` (`LEGACY_PUBLIC_PAGES` + `legacy_public_url`); sitemap enumeration/cache filtering, email contexts and public emitters share it. Keep frontend/backend gates aligned. Admin/writer/curator routes remain separate.
- Azure SWA legacy 301 rules live in `academy-watch-frontend/public/staticwebapp.config.json`; `tests/legacy-routes.test.mjs` checks agreement with the client route list and protects active paths. Restoring public routes requires removing the corresponding server redirects as well as enabling the gates. Legacy noindex depends only on the current legacy pathname; never carry it to the redirect destination.

- iOS: `academy-watch-ios/project.yml` is the XcodeGen source of truth. Put generated Info.plist overrides (including `CFBundleShortVersionString = $(MARKETING_VERSION)`) in `info.properties` so regeneration preserves them.
- iOS owner showcase writes use `APIClient.ownerShowcasePath`: community identities call `local-players/<positive-local-id>`, while discovery and club-feedback APIs use signed player IDs.
- iOS player/coach UI checks use the offline `AcademyWatchExperience` scheme. `AcademyWatchUISmoke` is a separate live suite that sends login emails.
- Phase 2 public read decorators opt in with `hide_suppressed_player(..., public_read=True)`; discovery uses `public_player_visible_filter`. Public sitemap responses recheck current holds even when serving cached XML. `without_active_suppression` remains suppression-only for owner writes and maintenance/refresh sweeps.
- Phase 2 new public player paths use `services/public_adult.py` and derived `services/club_publication_hold.py` checks; existing public reads enforce holds while retaining their age rules.
- Phase 2 application subjects resolve local/provider bridges through `LocalPlayer.api_player_id`; identity merges re-point application claim/subject keys inside the merge transaction and reject colliding retained histories with 409. Opportunity dates use the shared formatter and creation +90-day horizon to preserve trial follow-up within the submission +180-day privacy cap.
- B2 opportunities canonicalize committed IANA legacy aliases before runtime availability checks/save/format/date entry; backend/frontend alias data stays byte-identical. Recruiting serializers use program → opportunity → application locks and build mutation responses before commit. Trusted outbox templates can defer publication-held intents without consuming delivery attempts; permanent/stale eligibility still cancels.
- Scout reads use `public_adult_ids` / `filter_public_adult_query` before pagination, counts and ranking; numeric age snapshots alone do not establish adulthood. Saved ineligible rows stay stored but are hidden. GOL rechecks cached frames and rebuilds answers from current eligible data; unstructured web discovery cannot establish adult eligibility.
- Paid GOL replay revisions hash both known signed IDs and excluded IDs because stored prose lacks a reliable referenced-ID inventory. Additions also invalidate; preserve the existing 409 without another debit and load narrow eligibility evidence as a set.
- Scout list/watchlist caps count currently visible rows using batched public-adult eligibility. Hidden saved rows stay stored; reactivation can exceed caps without truncating reads, and only further adds are blocked. List payload `follow_count` uses the same visibility filter as capacity.
- GOL alone uses `gol_public_adult_ids` / `allow_journeys=True` to admit stored journey identities with exact adult DOBs; shared conflicts, bridges, suppression and holds still veto them. Replay revisions include journey IDs. Scout discovery retains its tracked/shadow/approved-local universe.
- Scout eligibility loads narrow policy columns via a single evidence UNION and PostgreSQL array/SQLite VALUES hold candidates; constrain queries first, then filter before counts/LIMIT/ranking. Leaderboards share immutable query bases and one request cache; dynamic follows share an immutable base query and eligibility through the digest run cache. No cross-request/run eligibility cache.
- Scout digests share `cached_public_adult_ids` eligibility with follow resolution in the run-owned enrichment cache; eligible and ineligible IDs use a separate namespace from player states. Never reuse that cache across runs; ordinary list reads start fresh.
- Phase 2 email intents use transactional `notification_outbox.enqueue` plus a trusted template eligibility/renderer registered at app startup; never commit inside enqueue or persist credentials/child PII. Worker commits a sending lease, sends without DB locks, then finalizes after rechecking tombstones; delivery is at-least-once.
- Phase 2 case-created suppressions retain `suppression_id` after hold ownership clears; existing report/suppression decisions call `sync_source_case` in their transaction, and both suppression paths use `suppression_decision.decide_suppression`.
- B3 dark routes re-match a cached URL map without disabled B3 rules, preserving the real SPA fallback, wrong-method responses and OPTIONS Allow headers; retain Flask automatic-options attributes when cloning rules. Receipt projection/replay backfills only unmapped refunds sharing a payment intent and currency, preserving cash facts.
- B3 case notifications omit the mutable case version from both key and payload and isolate enqueue in a savepoint; Safety OFF gates enqueue and delivery. Case hide/restore sync sibling cases, retain/reuse original suppression evidence, and never own another requester's pending hold. Stripe 15 cash boundaries use recursive `to_dict()`, including provider list pages.
- Phase 2 account suspension uses `services/account_standing.py` plus persisted `account_status`/`auth_epoch`; central bearer, user-bound media and service grants recheck standing even after the admin page flag is OFF. Restore requires fresh login.

---

## Quality Bar

Before marking work complete:
- [ ] Dependency scan passes before any frontend dependency restore or lockfile change
- [ ] Typecheck passes
- [ ] Tests pass
- [ ] Ledger state updated
- [ ] Patterns added to AGENTS.md if discovered
- B3 moderation locks the canonical target with a PostgreSQL transaction advisory lock before case/source rows; public takedown intake and original report/suppression/club tools share it. Reconciliation takes multiple target locks in sorted order. Case hide intent comes from the latest hide/restore/source-lift event, survives close, and is independent of physical hold ownership.
- B3 case-generated suppression erasure uses the report's source link plus its first hide event before actor redaction; retain genuine requester evidence and active hold state. New generated contact/statement fields are fixed markers. B3 migration/preapply set a five-second transaction-local lock timeout; abort/rollback and retry the entire script after contention, before code deploy.
