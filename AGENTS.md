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

- The web loader's logo is the real app-icon artwork, never a trace or redraw: `academy-watch-frontend/scripts/build-loader-logo.py` builds the WebP layers in `src/lib/academy-watch-logo.js` from the brand master `public/assets/loan_army_assets/favicon-512x512.png` (the source of iOS AppIcon-1024/LaunchBoot; no vector master exists). Only the boot is recoloured, along the icon's own shading (lace slots and seams stay ink in every phase, highlights stay light; black-gold puts gold only on the outer keyline); the wing keeps its original white pixels and never moves. Dark surfaces (night, `.dark`, or any dark painted ancestor, e.g. a navy club console) get a light rim. Judge changes side by side with AppIcon-1024, not by shape alone.

- Web loader primitives: runtime markup/palette/surface detection in `academy-watch-frontend/src/lib/cleat-loader.js`; the CSS carrying the inline artwork in `src/lib/cleat-splash.js`, which app code must never import — it ships once, in index.html's splash `<style>` (outside `#root`, so it serves every React loader). After edits run `node academy-watch-frontend/scripts/sync-cleat-splash.mjs`. The Node test protects the parity and the no-import rule.

> Agents: Add patterns here when you discover reusable conventions.

- Result opponent/competition storage and fixture keys use `sanitize_plain_text` as on main. Decode only at JSON/display boundaries with `utils.sanitize.display_plain_text` (one pass over Bleach amp/lt/gt escapes; preserve literal user entities). Never decode stored keys or rollup grouping labels.
- Club console, billing, verification and admin dates use frontend `src/lib/display-date.js`: en-GB display, date-only values keep their calendar day, naive Flask ISO timestamps are UTC. Use `withTime` when the view needs a timestamp.
- Coach's brief writes require `players.manage` OR `feedback` with member scope; other management stays `players.manage`. Whole-club writes use the complete stored alias closure (both roster keys, local/provider/shadow bridges, merge survivors and match sheets). Scoped saves refuse only readable own-squad roster/match-sheet names; never branch on hidden names. `_brief_context` withholds whole named lines against the full stored inventory using neutral placeholders; retain stored brief hashes and expectation positions. Fold complete names before tokenizing NFD storage. Scoped sheet aliases require currently readable members; scoped analysis JSON removes private brief checks/hashes/counters/limits/check-only notes. Neutral 422 for every role; shared 20/hour account budget is enforced on name refusals only; exhausted accounts can still save clean briefs. Route-owned JSON 429 survives the global handler with Retry-After/no-store.

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
- C1 public guards add no SQL while dark and only check negative/local IDs when enabled; positive provider surfaces retain main behavior. Admin can remove a legacy club/provider mapping without transferring content or permissions. Moderation exposes masked identity evidence and blocks self-invitations; rejection permanently closes threads. C1 privacy retention purges invited emails while dark and erasure covers withheld club-first requests.
- C1 recovery retires prior claims with `club_vouch_retired` (partial local/account uniqueness), snapshots permission evidence in append-only audit, and requires fresh invite/claim/consent/review. Old introduction claim bindings stay closed; consenting withdrawal alone never permits reassignment. Club follow names are live-derived; new stored labels are null and migration/dark retention/export repair historical labels.
- C1 club-origin publication preserves provenance and uses `club_player_publication` plus canonical `public_adult_ids`; invitation/self-claim, adult consent and moderation are independent keys. Introductions pin the publication claim, conceal the player inbox until club grant and permanently close old threads on either publication permission withdrawal. Consent cannot transfer through a merge/provider bridge.

---

- Web feature consumers share `APIService.getFeatures()` through `src/lib/features.js`: cache successful bootstrap responses per page session, keep dark opportunity/application keys absent, and distinguish failed/pending flags from OFF. New dark entry points must make zero opportunity/application requests.

- Web current-season reads share `lib/seasonDirectory.js` / `useSeasonDirectory`; use the server directory `display_season` for default desk labels and player label fallbacks; player totals prefer the response season, including frozen shadow history. Use `current_season` only as a last resort. Omit `season` from unpicked desk/player requests so the server retains latest-data fallbacks; carry every explicit URL/store pick into reads and player links. Retain historical URL/store overrides and frozen-mode logic; community pages have no picker, ignore stored season and keep games unfiltered; positive provider games retain the resolved totals season scope. Unpicked local/provider-linked totals also omit season, and game mutations reload the server default totals. The directory must not gate independent data reads. Short positions use `lib/positions.js::positionAbbreviation`; keep free text on player profiles.

- Community global search shares the dynamic `utils/scout_discovery.py::local_players_enabled` switch with the scout desk; OFF returns provider payload/order/query work directly. ON applies canonical public-adult eligibility to all constrained candidates before ranking/capping, retaining provider relative DB order and using NFKD/casefold for community insertion.

- Match-entry date-boundary tests use the parametrized `frozen_now` fixture in `tests/test_player_match_entries.py`; it patches route and subject-resolution UTC clocks. Derive relative date inputs inside the test from that fixture, never during parametrization.

- GOL model-written analyses use `services/gol_capabilities.py` facades and typed guards; never expose raw library modules or expand attributes without escape/compatibility corpus coverage. Pandas aggregation strings require reduction allowlists even inside pivots/named aggregations; transform strings use a separate reviewed list. Analysis helpers use stored frames only; validate plain results before coercion/JSON and keep formatting inside the timeout. Validate typed frames by dtype and inspect only object/category values; pandas 3 copy-on-write isolates table mutations, while nested object containers still need cloning. Keep public refusal cases generic and the per-type attribute classification inventory explicit.

- Player read views use `src/components/player-card/` with wording in `lib/player-card.js`. Match rows and their totals come merged from `GET /players/<id>/matches?view=lines` (`services/match_lines.py`): never pair self/club entries or sum match totals in a client, and never add provider totals to match-line totals. A club row and an own row pair only when they are the only two rows for that date and opponent; any other shape keeps every row as its own counted line (`shared_slot`) — no row is ever dropped. List surfaces print apps/minutes only for provider-sourced figures (`isProviderSourced`) until the rollup reads the same merged lines. `ShowcaseSection` loads the showcase once and hands it up via `onShowcaseChange`; it requests raw match rows only for the owner. Everything a player read view holds is scoped to player + viewer (`viewerKey(token)`, `scopedValue`, `useScopedShowcase`, `useSeasonTotalsRead`): a logout, login or account switch must withhold the previous viewer's data in the same render and ignore late answers — never key such state by player id alone. A failed read (lines or season totals) is an error with Retry and keeps the last good data of the same scope; it is never rendered as an empty season (`readProblem`). Viewer change = fresh screen: `PlayerPage`, `ScoutPage`, `ShowcaseSection` and `LocalPlayerPage` are thin wrappers that key their body on player + viewer, so drafts, dialogs and pending callbacks of the previous viewer are discarded by a remount; keep state out of the wrappers (`tests/viewer-boundary.test.mjs`, rule in `docs/agents/frontend.md`) and use `useViewerState` for state a late request may write. A remount does not stop running handlers: viewer-bound components use `useViewerLifetime()` — `life.api` instead of `APIService` (bound to the viewer: late answers are `StaleViewerError`), `useGuarded(life, …)` around navigate / logout / sign-in prompt / downloads (`lib/viewer-lifetime.js`). The shared `APIService.request` is NOT viewer-bound (pages outside the keyed boundaries must still get their answers); its only rule is that a 401 for a credential that is no longer current is a plain failure that signs nobody out. `ShowcaseSection` stays the owner's manage surface; pages pass `readSectionsElsewhere` when they render the read view themselves.

- Scout desk (Discover) and watchlist: wording and "only from real data" rules live in `lib/scout-desk.js`; the desk card is `PlayerCard variant="desk"` and the watchlist tile is `PlayerTile` (same card family — never a second card component). Every filter chip is a server filter (`deskFilterParams`; "Open to an introduction" = `contactable=1`, the SQL form of the per-row `contactable` flag in `services/scout_desk_card.py`) — never filter a page of results in the browser. List figures print with their source word; club- or player-entered figures are withheld on rows that lack the merged-lines fields (`club_confirmed` key), so the desk cannot contradict the player page. Leaders render below the results and only boards with rows. Desk rows (signed-in caller) and watchlist entries carry `introduction` (the caller's own request state + `can_ask`, one `contact_requests` query, read-only: a due request is reported expired, never written). It mirrors `routes/contact.py` exactly — `target_claims` is the batched `_target_claim` (newest approved self-claim; club-created players via the live publication + operational program), a block counts only for THAT target's owner, a request is hidden only when its OWN claim is behind a block, and a blocked pair reads as the neutral `{state: none, can_ask: false}`; `tests/test_scout_desk_card.py` runs one case table against both the projection and the real POST route — extend the table when a contact rule changes. The UI offers only what that state allows (`deskIntroduction`, `introductionView`). `conversation_open` likewise mirrors the message route (a block with an active manager of the thread's operational club makes the thread `read_only`); extend `MESSAGE_CASES` with the rule. Compare withholds club- or player-entered season figures exactly as cards / table / leaders do (`compareFiguresWithheld`). Introductions, lists, the thread and the club introductions panel are viewer-keyed boundaries (`tests/viewer-boundary.test.mjs`). The Cards/Table choice is stored per ACCOUNT (`viewOwnerTag`: a one-way tag of the user id read from the token payload — never the credential or the email); table-only filters keep their tools on screen in the cards view (`hiddenFilterActive`); `WatchlistPage` → `WatchlistBody` is a viewer-keyed boundary like the desk.

## Quality Bar

Before marking work complete:
- [ ] Dependency scan passes before any frontend dependency restore or lockfile change
- [ ] Typecheck passes
- [ ] Tests pass
- [ ] Ledger state updated
- [ ] Patterns added to AGENTS.md if discovered

- Opportunity feature/retry and approved-player navigation state live in `OpportunityStateProvider`; hooks enable the lazy shared bootstrap. Private claims clear on every auth-token transition and ignore stale responses. Keep page and menu consumers on this shared state; flags-OFF must issue zero opportunity/application requests. Consumer route arrivals recover failed reads once per arrival (router key + pathname); player-home/owner-summary arrivals revalidate claims, retaining successful values during loading and sharing pending/completed reads within an arrival. Navigation reports every route arrival to the provider even when signed out, without enabling requests; reset arrival markers on transitions so reused Back/Forward keys still recover and revalidate.
- B3 moderation locks the canonical target with a PostgreSQL transaction advisory lock before case/source rows; public takedown intake and original report/suppression/club tools share it. Reconciliation takes multiple target locks in sorted order. Case hide intent comes from the latest hide/restore/source-lift event, survives close, and is independent of physical hold ownership.
- B3 case-generated suppression erasure uses the report's source link plus its first hide event before actor redaction; retain genuine requester evidence and active hold state. New generated contact/statement fields are fixed markers. B3 migration/preapply set a five-second transaction-local lock timeout; abort/rollback and retry the entire script after contention, before code deploy.

- B3X stored admin names use `services/admin_control_names.py` only inside dual-authenticated admin DTOs, constrained/batched per page; never use it for public/user/export reads. A player suppression lift retires report-case hold intent without deciding the report or sending a closed notice. B3 overview counts queue items per enabled page and shares linked-list filters (including community provenance and photo kind); a report and its case occupy two queues cleared by one decision. Paying subscription MRR uses active status only and keeps past due separate.

- C1 claim retirement quarantines showcase rows/approval snapshots and self-reported matches in private `retired_club_showcases` scoped to each actual author; rebuild affected season cells and preserve club facts; no fresh-owner reads use this evidence. Dark maintenance purges at 180 days and account erasure removes it. Publication approval only accepts pending rows and never corrects conflicting shadow DOBs. Scout club-first history exposes counterpart identity/content only with live eligibility and a club grant.

- C1 contact request serializers require an explicit viewer at every call site; API-key admin calls explicitly use None. Finish lazy expiry before acquiring the first program/publication lock; recheck current permissions after locking. Decline notes remain visible only for a plain club decline with a live eligible publication; other scout-unavailable states withhold club text. Account erasure deletes owned showcase media/affiliations; session-scoped media cleanup runs after the root commit and is discarded on root/savepoint rollback.

- C1 introduction creation finishes expiry before taking program → publication → claim locks; consent/link/revoke mutations use program → publication → request order and recheck permissions. Retryable PostgreSQL 40P01/40001/55P03 contention returns neutral 409/503 after rollback. Live scout titles use the batched, claim/program-pinned `public_profile` projection; participant account identity stays withheld until grant and unavailable/closed histories omit public titles. Club-first outcomes require available publication plus club grant and player acceptance. Club adults share community search insertion and final cap across community flag states.

- Contact scopes share `services/contact_locks.py::lock_contact_scope`: resolve unlocked IDs, lock all programs → publications → claims → requests (sorted within each table), and revalidate identity bindings. Resolve full batch scopes before merges/erasure; helper state is transaction/savepoint scoped. New direct four-table locks fail the static guard; contact contention uses neutral contact_conflict/contact_busy with rollback.

- Contact batches resolve all invitation recipient/source-owned claim IDs before locking; keep lock scope distinct from mutation selection. Feedback lists are plain reads; purge uses one upfront invitation/contact/account batch. Account erasure uses settlement → full contact scope → sorted accounts, with the entire prefix inside its purchase-retry savepoint. Helper held-row caches are transaction/savepoint scoped; dynamic earlier locks use PostgreSQL NOWAIT, never a synthetic rank-conflict retry.

- Account erasure revalidates every owned claim/contact/publication/invitation/program and purchase selection after sorted account locks; changed hints roll back the full acquisition savepoint before bounded canonical retry. Closure writes persist feedback deadlines; pure lists never start retention clocks.

- Phase 2 highlights use reviewed immutable adult-only match snapshots and server reel windows; public lists/bytes recheck both keys via `services/highlights.py`. Separate `highlight_worker` performs bounded cuts and delayed private cleanup; never mint raw-match SAS or run ffmpeg in Flask. Source guards revoke consent even while dark. C2 revocation authorizes program/match ownership without raw-storage checks; GET evidence is batched per request, never reused across requests or worker commits. Institutional club reviews survive staff anonymization; only verified staff exercise the club key. Standalone read redirects expire after 60s; no raw/container capability.
- C2 grants pin absolute expiry before eligibility/storage and rebuild batched evidence after I/O; web previews request authenticated URL JSON then use native video transport across origins. Sticky moderation holds contain only recording/window keys and survive clip audit purge/subject erasure; lifting requires fresh club and player consent.
- C2 context reviews pin finalized date/squad evidence; context edits invalidate them in ORM and SQL. Highlight takedowns hold all overlapping windows across subjects, including batched/post-storage reads. Retention resolves local/provider claim bridges independently of reversible standing. Source-change notices aggregate per recording/recipient/event and omit declined picks.
- C2 reviews bind classification results for match and member squads; cosmetic renames preserve retained cuts, unsafe evidence transitions invalidate permanently in ORM/SQL. Legacy context conversion verifies the exact old hash and squad bindings without changing the consent fingerprint. Approved claimant ambiguity ignores suspension; request-owned subject indexes are rebuilt after storage.
- C2 review idempotency requires a live `source_context` as well as matching retained context; change/revert re-confirmation renews review evidence but never old clip consent. Queued inbox polling re-arms after failed loads with a five-minute maximum delay and cancels while hidden or unmounted.
- C2 retention and worker storage deletion require `HIGHLIGHT_RETENTION_SWEEP_ENABLED` (default OFF), independently of publication. Explicit `--dry-run` selects/logs proposals without mutations or storage. Delete only exact recorded highlight attempt blobs, never raw-match paths/prefixes. Build/activation/scheduling require MJ's go as separate go-live operations; deployment does not schedule highlights.
- GOL loader compatibility checks use the real psycopg/PostgreSQL path with all selected frames; Numeric columns explicitly retain pandas float coercion, while exact finite Decimal values are accepted at the plain-data boundary. Keep builtin names in the reviewed classification inventory.

- GOL operational availability uses `services/gol_availability.py` at request time; unavailable selected-provider credentials share the maintenance response. Fresh and already-refunded/failed paused questions write nothing; only latest unreversed running/completed debits enter reservation/replay/lease recovery/refund. Paused reservations carry `recover_only` and revalidate eligibility under the account lock before compensation, balance checks or new attempts; the unlocked hint is never authoritative. Active provider chunks and resumed completion boundaries recheck availability without SQL; close the stream before a maintenance error and never accept its completion. Failed web questions retain Retry while paused unless that attempt already received maintenance. Web availability rechecks belong to `useGolChat` through the existing suggestions read; respect retry deadlines, reset on Clear, and preserve the shared feature bootstrap request count.

- C4 attendance decides until session start independently of player intake; accepted rescinds and trust/session revocations clear instructions atomically with audit/outbox. Today stays read-only, batches authoritative trust/advert/scope evidence, caps all queues and labels sampled application counts; expiry/trust sweeps run outside Today, and moderation/maintenance survive rollback.

- Phase 2 scout attendance stays separate from applications; C4 Today omits unauthorized queues and uses `match_bytes_in_scope` for analysis summaries. Distance searches use POST bodies and approved B1 pins; retention/account privacy adapters operate with the rollout flag OFF.

- C4 trust revocation locks scout account → attendance only, re-reading after the mutex; admission/decisions use program → opportunity → scout → attendance. Never acquire program locks from trust reconciliation. Before-flush retains trust-loss IDs and locks the account before UPDATE; before-commit rechecks/reconciles flushed changes; rollback clears transaction-local evidence.

- Today scopes match SQL with `filter_match_bytes_query` and introduction subjects with `filter_public_adult_query` before LIMIT/has-more. Accepted scout queues end at session end (fallback start+one day); retention history is separate.

- C4 private opportunity DTOs batch retained pending/accepted `live_attendance` evidence even after rollback. Session locks compare UTC instants/canonical timezone aliases and normalized venue/address; disabled editor dates carry exact stored timestamps, avoiding minute-input rounding. Same-program Today refresh retains stable row drafts, while program changes and failed reads discard private data.
