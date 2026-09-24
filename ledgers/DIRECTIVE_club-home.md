# Club Home

## Phase A — built and verified (2026-09-24)
- Branch: `feat/club-home-a`, based on `origin/main` = `c95f11874aa87374bc6c08248844572e587f1ab1`.
- Scope: private manager console with squads, reporting-line staff, roster assignment, shirt numbers, branding and pitch map.
- This is the task ledger; the user fence excludes changes to CONTINUITY.md.

## Data model and boundaries
- `ch01` → down_revision `s4d1` (confirmed with Flask). Guarded PostgreSQL DDL; RLS enabled on `club_squads` and `club_staff`.
- Squad: program, case-insensitive unique name, kind, age limit, order and timestamps.
- Staff: program, display name/title, reporting parent, lead squad, optional existing manager account and order/timestamps. Roles never grant login access. One lead per squad through the serialized API.
- Roster: nullable squad and shirt number; database uniqueness on `(squad_id, shirt_number)`, range 1–99. Squad deletion leaves members unassigned; staff deletion detaches direct reports.
- Program: private primary/accent colour and banner fields. `manager_dict`/roster and map carry branding; `public_dict` is unchanged. Crest moderation remains on profile revisions.
- Program row locks serialize squad/template/staff/assignment mutations. Parent and squad references must belong to the same program; reporting cycles return 422.
- All Club Home routes require the existing verified manager gate. No new public staff, squad, player identity or branding payloads.
- Roster film evidence aggregates only finalized, human-confirmed reports still linked to the current member. No invented appearances/minutes. Year-only birth data is displayed as an age range; minors' precise dates retain the existing minimization policy.

## API
All following paths are under `/api/club/<program_id>`:
- `GET/POST /squads`; `PATCH/DELETE /squads/<id>`; `POST /squads/reorder`; `POST /squads/template` (zero squads only).
- `GET/POST /staff`; `PATCH/DELETE /staff/<id>`.
- `PATCH /roster/<member_id>`; existing roster POST accepts squad/shirt; GET accepts `squad_id=<id>` or `none`.
- `GET /map`: manager program, staff, squad counts/lead ids, unassigned count; no player arrays.
- `PATCH /branding`: strict hex and WCAG 4.5:1 against white/`#16201B` respectively.
- `POST /branding/banner`, `POST /branding/banner/complete`: existing showcase storage target, `club-banners/<program_id>/` prefix, expiring signed manager/program grant, bounded JPEG/PNG/WebP decode and metadata-free JPEG publication. Changes log actor and program. No admin publication queue for banners.
- Existing `POST /api/local-players` gains verified-manager `club_program_id` mode: atomic private identity + roster assignment, without a public ownership claim. Existing duplicate checks remain. Fix round 1 separates club creation safeguards from normal self-submission quotas (see below).

## UI map
- `MyClubConsole` retains existing data/workflow panels; `club-console/ClubHome` supplies the new shell.
- Club: searchable squad sidebar, pitch tree, focus pills, up to four player chips and a private dock with available film evidence.
- Squads: positional groups, initials cards, shirt/move controls, minor privacy notice and tracked/new-player dialog.
- Matches: existing match upload, roster, processing request, results, report and reel workflows.
- Scouts: existing feature-gated introductions and consent/thread panel.
- Settings: Branding, Squads & age groups, Staff & roles, Roster & briefs (including invitations/feedback), Club profile, Affiliations & vouches.
- Barlow Condensed + Archivo are scoped to Club Home. Club variables also theme retained panels. Banner tint includes darkening to preserve white text contrast.
- Mobile: bottom rail and expandable navigation expose squad search/program switching; pitch scroll is internal. Nodes are keyboard buttons.
- Player onboarding prompt is suppressed throughout `/my-club`, including the manager eligibility-loading interval.
- Screenshot review refinements: compact player chips, dark dock, readable labels, banner contrast, explicit selector name, and intentional cancellation excluded from API error logging.

## Verification
Final backend runs use `DB_NAME=aw_clubhome_a DB_HOST=127.0.0.1 DB_PORT=5432`, CI flags `SKIP_API_HANDSHAKE=1 API_USE_STUB_DATA=true TEST_ONLY_MANU=false OPENAI_API_KEY=test-not-a-real-key`, and disabled Azure configuration.
- `flask --app src.main db heads`: `s4d1 (background_jobs) (head)` before the change.
- `../.loan/bin/python -m pytest -q tests/test_club_console.py tests/test_club_home.py`: **107 passed in 9.84s**.
- Focused run including `tests/test_showcase.py`: **168 passed in 13.12s**.
- Full CI command `../.loan/bin/python -m pytest -q`: **3 failed, 2854 passed, 35 skipped, 114 warnings in 177.14s**; no deselections.
- All three full-suite failures reproduce on an extracted `origin/main` backend against the clone: `tests/test_radar_stats_e2e.py` → **3 failed, 2 passed, 1 skipped in 0.53s**. Failures: `test_full_radar_chart_data` (`peers_count`), `test_percentile_pool_stats` (removed `compute_position_percentiles` import), `test_old_vs_new_comparison` (`player_percentile`). No radar code changed.
- `ruff check academy-watch-backend`: **All checks passed!**
- `ruff format --check academy-watch-backend`: **507 files already formatted**.
- `./scripts/setup_frontend.sh`: initially blocked because OSV-Scanner was absent; rerun with a temporary scanner succeeded: **547 packages; No issues found**. Frozen dependency restore; no lockfile changes/new dependencies.
- `pnpm lint`: **0 errors, 178 warnings** (repository warning-level rules remain enabled).
- `pnpm build`: **3924 modules transformed; build passed**.
- `pnpm test` (CI frontend unit command): **186 passed, 0 failed**.
- Throwaway clone created via PostgreSQL `CREATE DATABASE aw_clubhome_a TEMPLATE soccer_newsletter` using psycopg (client binaries were not on PATH).
- `flask --app src.main db upgrade` → `ch01`; `db downgrade s4d1`; `db upgrade` → `ch01`: all passed. PostgreSQL reports RLS `true` on both new tables. Stamping the clone back to `s4d1` and upgrading over the existing schema also passed; final version was `ch01`.
- Live backend 5091/frontend 5192: Playwright bundled Chromium; Chrome channel is not installed. Main walk and extended walk passed; document width equals 390px at mobile width.
- Walk exercised template, three fictional staff, all 18 existing roster assignments, player focus/dock, squad page, new-player dialog, branding save/422, banner upload, finalized match/report/reel, introductions, atomic minor creation, move/shirt edit, briefs/invitations and mobile program switching.
- `/tmp/club-home-a/walk.log`: no unexpected console/page/API errors; one intended contrast-validation 422 and its three associated console messages.
- Iteration failures resolved: exact roster/head assertions, legacy tab source assertions, club-local create relationship support, walkthrough selector/readiness issues. Final gates above supersede intermediate runs.

## Evidence and deviations
- Screenshots retained in `/tmp/club-home-a/shots`: 01 empty map; 02 standard squads + three staff; 03 focused squad + dock; 04 squad page; 05 New player dialog; 06 saved claret + rejected white primary; 07 uploaded banner; 08 finalized match with report/reel loaded; 09 390px map; 10 introductions.
- Environment identifies as `mjs-macbook-pro.lan`, not basecamp. The available local fixture is Sample Club/program 2 with 18 existing players and finalized match 4 (“Visiting XI”); AFC Wyke is also present, but no AFC Yorkies-labelled fixture was found. Existing fixture identity/age/position data was preserved; Sample Club supplied the requested walkthrough instead.
- An initial full-suite run lacked the DB-name override and its existing radar checks read the shared local fixture statistics. Those checks are read-only; subsequent full-suite/baseline/live/migration verification explicitly targeted the throwaway. No migrations or application writes were performed on the shared database.
- Public player pages/photos and public highlight publication remain outside Phase A. Introduction evidence shows the real empty inbox; no scout requests or messages were fabricated.
- Cleanup complete: backend/frontend servers stopped; throwaway database dropped and absence verified; token, generated media, baseline checkout, scanner and other task temporary files deleted. Ten final screenshots and walk.log retained, along with pre-existing design/brief/run artifacts. Delivery is one local commit on `feat/club-home-a`; no push, PR or merge.

## Original Phase B plan — fulfilled below
- Club player page and club-uploaded player photos.
- Photo precedence: claimed player's approved photo > club photo > API photo.
- Minors' club photos never public.
- Claiming a club-created row requires an explicit "convert to public identity" step: change provenance and apply normal moderation. Today a claim on a club row is inert.
- Decide the ownership model for same-manager cross-program attachment: a manager of programs A and B can currently attach A's club players into B.
- Provide an admin-only view of club-created identities for safeguarding takedowns.

## Planned Phase C
- Two-key public highlights: club selects clip windows; adult claimed player approves.
- Cut approved windows into their own public files so the full match never leaks.
- Minors never public.

## Fix round 1 — verified (2026-09-24)
- Club creation uses `provenance=club`, remains pending/private, receives a synthetic stats key without a public shadow; public moderation excludes/refuses these rows.
- Club requests use program-scoped 120/hour and 500-roster-member safeguards; ordinary self-submission 5/hour and 10-pending limits remain separate.
- Private club results retain manager-only entries without public season totals. Public subject, discovery, GOL/search bridge and sitemap gates explicitly exclude club provenance.
- Banner replacement deletes only the previous same-program banner after commit. Existing-player picker lists only the manager's own available identities absent from this roster.
- Mobile reserves bottom-rail space and lifts the assistant button; unled squads sit below a labelled No lead yet branch.
- Verification uses throwaway `aw_clubhome_fix1`; ch01 is unchanged (provenance is unconstrained varchar(20)).

### Fix round 1 verification
- Focused command: `../.loan/bin/python -m pytest -q tests/test_club_console.py tests/test_club_home.py tests/test_showcase.py tests/test_local_players.py tests/test_scout_blueprint.py tests/test_sitemap.py tests/test_club_results.py` → **355 passed in 26.13s**.
- Full CI command: `../.loan/bin/python -m pytest -q` → **3 failed, 2862 passed, 35 skipped, 114 warnings in 180.94s**. Only the same three radar failures listed above.
- Fresh extracted `origin/main` baseline, `python -m pytest -q tests/test_radar_stats_e2e.py` → **3 failed, 2 passed, 1 skipped in 0.55s**, matching the full-run failures; radar sources/tests unchanged.
- All database-aware commands use `DB_NAME=aw_clubhome_fix1 DB_HOST=127.0.0.1 DB_PORT=5432`, CI stub flags and disabled Azure configuration. No shared-database application writes.
- `ruff check academy-watch-backend` → **All checks passed!**; `ruff format --check academy-watch-backend` → **507 files already formatted**.
- `./scripts/setup_frontend.sh` → **547 packages; No issues found; frozen lockfile already matches**. Missing scanner resolved with a temporary official OSV binary. No dependency/lockfile changes.
- `pnpm lint` → **0 errors, 179 warnings**; `pnpm build` → **3924 modules transformed; built in 457ms**; `pnpm test` → **186 passed, 0 failed**.
- `flask --app src.main db upgrade` on the fresh clone → **ch01 passed**. Round-trip not repeated because ch01 is unchanged. Clone schema inspection confirms provenance is varchar(20), with no provenance CHECK/enum.
- Playwright bundled Chromium → **12 dialog creations**, own existing-player picker attachment, **two banner replacements with old-file absence assertions**, No lead yet branch, and **390px width without page overflow**. Body bottom padding 79px for a 63px rail; GOL button bottom 79px; development feedback toolbar hidden.
- `/tmp/club-home-a/walk-fix1.log` → **zero API errors, zero console errors** on the final walk. Seven screenshots in `/tmp/club-home-a/shots-fix1`, visually reviewed: 01 twelfth creation dialog; 02 twelve private players; 03 existing-player picker; 04 twice-replaced banner; 05 unled squads branch; 06 mobile map; 07 mobile bottom clearance.
- Private result regression coverage includes adult and minor creation, match roster, result create/read/correct/delete, no public totals; approval refusal and discovery exclusion remain enforced even with a deliberately stale approved status/public shadow fixture.
- GOL dataframes load tracked/provider tables, not these private local identities or result entries; public search/digest bridge predicates explicitly exclude club provenance.
- Iteration issues resolved: fixture rate-limiter initialization, request-local allowance caching, admin test authentication, dialog selector accessibility, and mobile transition timing. Final gates above supersede intermediate failures.
- Phase B must implement an explicit player-owned claim/publication transition; an admin status change alone never removes the club-private provenance boundary. No public profile is created in this round.
- No scope deviations. Cleanup complete: servers stopped, throwaway database dropped/absence verified, temporary token/media/scanner/baseline/scripts removed. Fix screenshots and walk log retained. Delivery is one new commit (not an amend), no push.

## Fix round 2 — verified (2026-09-24)
- Non-club duplicate queries exclude club provenance; club-mode duplicate queries only inspect identities created by the requesting manager. Existing duplicate error text is unchanged.
- Regression coverage: different managers can create the same name/year; ordinary submissions ignore club-private matches; same-manager club duplicates and ordinary public/pending duplicates still return 409.
- Only runtime change is in showcase.py; verification uses disposable SQLite test databases. Full backend suite is not required for this scope.
- `../.loan/bin/python -m pytest -q tests/test_showcase.py tests/test_club_home.py tests/test_club_console.py tests/test_local_players.py` → **264 passed in 18.07s** (includes six new regression cases covering minors, adults, normalized same-manager duplicates, and pending/approved ordinary identities).
- `ruff check academy-watch-backend` → **All checks passed!**; `ruff format --check academy-watch-backend` → **507 files already formatted**; `git diff --check` → passed.
- No migration, frontend, dependency or lockfile changes. Test databases discarded by fixture teardown; no servers or temporary files created. Delivery is one new commit, no amend or push.

## Phase B — execution record (2026-09-24)
- Worktree `feat/club-home-b`; private player profile, private photos, pathway, origin ownership and safeguarding list.
- User fence continues to exclude CONTINUITY.md; this directive is the active ledger.
- Plan: guarded ch02/pre-apply SQL → shared private backend read model/storage/history → Club Home/admin UI → focused/full gates, PostgreSQL parity and browser evidence → one commit.
- Results model has no starts field: omit starts rather than infer it from minutes. Existing match entries remain the source of recorded appearances/minutes/goals/assists.

## Phase B — as built (2026-09-24)
- `ch02`, down_revision `ch01`: guarded/idempotent history table + index + RLS; private roster photo path/timestamp; nullable local-player origin FK. Backfills create one open history interval for assigned members and select each club identity's earliest roster program.
- Squad assignments share `change_squad`: initial assigned creation, roster PATCH/move and squad deletion close/open intervals atomically. No-op assignments do not add intervals. Failed writes roll back history. Member removal and invitation revocation close history; the required member FK cascade then removes history with the member (there is no surviving "removed" interval).
- Club-mode creation stamps origin. Any manager of that origin can attach the club identity; another program cannot attach it even when the same user manages both. Non-club identities retain the creator-only attachment rule. Picker uses the same ownership scope; historical memberships are retained for safeguarding inventory.
- Private photos use the existing pending/direct PUT pattern and expiring actor/program/member grants. Completion bounds bytes/pixels, decodes and re-encodes metadata-free JPEG, then stores `club-player-photos/<program>/<member>/<uuid>.jpg` outside both showcase containers. Local private artifacts are outside the public/pending filesystem trees. Anonymous dev pending-photo GET is denied for this namespace.
- GET photo streams authorized bytes with `Cache-Control: private, no-store`; no public URL or read SAS is minted. Replacement/deletion removes only the prior matching program/member prefix after commit. Failed DB completion compensates by deleting the new private artifact.
- Photo precedence: adult approved primary photo uploaded by an approved player claimant (approved/public local identity required) → private club photo → tracked photo → initials. Minors never select showcase photos. Suppressed/unavailable subjects return neutral 404 for profile/photo.
- Profile aggregates identity/claim/squad/age, pathway, club-entered results, match roster/film, coach brief, current readable development feedback/actions, club-visible introductions and private note. Empty sections are omitted; minors get an explicit locked scout state. Starts are omitted because the results schema has no starts field; appearances count entries with positive minutes. Brief and feedback/progress writes use the existing APIs.
- Film uses the existing reel builder and shared club report serializer. Report links/minutes additionally require the current member's finalization snapshot, preventing attribution after entry rebinding. Existing reel/report UI is reused and scoped to the selected player; playback stacks inside the player-page column.
- Club contact listing and player aggregate share the existing club-included/block visibility query; development uses the existing relationship/closure serializer and feedback-development service. Existing feature flags remain effective.
- Club Home deep link: `/my-club?program=<program_id>&player=<member_id>`. Hero/tabs/desktop pathway column follow the approved mock without sample statistics. Dock, squad cards, sidebar search and roster rows open the page. Authenticated blob avatars appear on page/map/dock/cards; upload supports progress/preview/replace/remove. Busy photo/move/brief actions cannot race a pending save.
- Admin nav → `/admin/club-identities`: dual admin auth, paginated club-provenance inventory, origin/program/creator/date/minor/memberships and program filter. The form uses the EXISTING local takedown intake → suppression queue → activate lifecycle, including its existing audit behavior.
- No new public player, search, scout, sitemap or GOL surfaces; no public publication transition.

### Phase B endpoints
- Manager-only: `GET /api/club/<pid>/roster/<mid>/profile`.
- Manager-only: `POST/GET/DELETE /api/club/<pid>/roster/<mid>/photo`; `POST /api/club/<pid>/roster/<mid>/photo/complete`.
- Admin-only: `GET /api/admin/club-identities?program_id=<pid>&limit=<1..200>&offset=<n>`.
- Existing roster PATCH, brief PUT, photo direct-upload PUT, feedback/progress, club film and takedown/suppression endpoints are reused.

### Phase B storage / deployment configuration
- New optional env var: `CLUB_PLAYER_PHOTOS_CONTAINER`, safe default **`club-player-photos-private`** (documented in backend env.template).
- Container must be private and distinct from `SHOWCASE_MEDIA_CONTAINER` and `SHOWCASE_MEDIA_PENDING_CONTAINER`. The Azure implementation can create it with `public_access=None` and refuses an existing public container. Orchestrator may provision this private container before deploy; existing connection string/pending-upload CORS are reused. No Azure/Supabase/prod access was performed for this work.
- Local dev uses `SHOWCASE_MEDIA_LOCAL_DIR/club-private/`; no new local env var is required.

### Phase B verification — final results
- Every database-aware command targeted the throwaway with `DB_NAME=aw_clubhome_b DB_HOST=127.0.0.1 DB_PORT=5432 DB_SSLMODE=disable`, CI flags `SKIP_API_HANDSHAKE=1 API_USE_STUB_DATA=true TEST_ONLY_MANU=false OPENAI_API_KEY=test-not-a-real-key`, disabled Azure/Key Vault and local-only media. Credentials were passed in process environment, never printed.
- Focused command from backend: `../.loan/bin/python -m pytest -q tests/test_club_players.py tests/test_club_home.py tests/test_club_console.py tests/test_player_feedback.py tests/test_club_invitations.py tests/test_contact.py tests/test_showcase.py tests/test_cb01_coach_briefs.py tests/test_pm01_player_match_entries.py tests/test_s2_foundation.py tests/test_season_data_sea01.py` → **508 passed, 11 skipped in 35.42s**.
- Full CI backend command: `../.loan/bin/python -m pytest -q` → **3 failed, 2893 passed, 35 skipped, 114 warnings in 156.86s**. No deselections. Only failures: radar `test_full_radar_chart_data`, `test_percentile_pool_stats`, `test_old_vs_new_comparison`.
- Fresh `git archive origin/main academy-watch-backend` extraction, same throwaway/CI env, `python -m pytest -q tests/test_radar_stats_e2e.py` → **3 failed, 2 passed, 1 skipped in 0.36s**, exactly the same three failures; no radar files changed.
- `ruff check academy-watch-backend` → **All checks passed**; `ruff format --check academy-watch-backend` → **511 files already formatted**; `git diff --check` → **passed**.
- `PATH=<temporary official OSV-Scanner v2.3.8>:$PATH ./scripts/setup_frontend.sh` → **547 packages scanned, no issues**, frozen dependency restore passed. No lockfile regeneration, lockfile modifications or new dependencies.
- Frontend `pnpm lint` → **0 errors, 182 warnings** (repository warning-level rules); `pnpm build` → **3927 modules, passed**; `pnpm test` → **186 passed, 0 failed**. This JSX frontend has no separate typecheck command; Vite build is the compilation gate.
- PostgreSQL clones `aw_clubhome_b` and `aw_clubhome_b_sql` created from `soccer_newsletter` using CREATE DATABASE ... TEMPLATE via psycopg. Shared database received no application writes/migrations.
- Alembic: clone `s4d1` → `ch01` → `ch02`; downgrade to `ch01`; upgrade to `ch02`; final repeat downgrade/upgrade → **passed**. RLS true on `club_roster_squad_history`; assigned-member/open-row and origin backfills verified; repeated SQL application leaves history counts unchanged.
- Pre-apply proof: fresh second clone upgraded only to `ch01`, identical backfill fixtures inserted in both clones, then `ch02_preapply.sql` applied as one BEGIN/COMMIT. `pg_dump --schema-only --no-owner --no-privileges -t public.club_roster_members -t public.club_roster_squad_history -t public.local_players` compared against the Alembic clone → **zero differences**. Only pg_dump's random `\restrict`/`\unrestrict` nonce lines were excluded. Both normalized dumps SHA-256: `89b3908513834b5599026337bc7ddc928afd1ec51dff72cfae7c157d06de912c`. A regression test also compares ch02's exact UPGRADE_SQL against the transaction-wrapped pre-apply file.
- Playwright bundled Chromium, backend 5093 / frontend 5193, throwaway only: **main walk + extended walk passed; zero API/console/page errors** in final `/tmp/club-home-b/walk.log`. Verified live reel frame readiness, report, all entry links, brief/note saves, photo preview/upload/replace/remove/reupload, origin-scoped private photo rendering, U16→U18, minor scout lock, admin filter and actual existing suppression activation. Mobile document width equals **390px**.
- Screenshot review against Player.dc.html completed; fixed narrow reel controls, squad-card action wrapping and pending-save action race. Eight final screenshots in `/tmp/club-home-b/shots/`: `01-player-adult.png`, `02-player-minor.png`, `03a-photo-map-and-dock.png`, `03b-photo-squad-card.png`, `04-pathway-u16-u18.png`, `05-film-finalized.png`, `06-admin-club-identities.png`, `07-mobile-player.png`.

### Phase B evidence notes / deviations
- Host reports **mjs-macbook-pro.lan**, despite the brief naming basecamp. Work and all gates ran on the supplied machine/worktree.
- Existing Sample Club/program 2, match 4 (Visiting XI, finalized, 18 roster entries/reports) supplied real local film evidence. Existing fixture numbers were retained; no mock season numbers, starts, scout interest or development actions were invented. New identities/staff and the illustrated upload fixture are fictional.
- Original local suppression fixtures had encrypted fields incompatible with the isolated server's key. Unrelated requested suppression rows were reset **only on the throwaway** before testing the actual takedown form. Admin token was reissued after creating its local account, consistent with account-generation binding. Initial walkthrough selector/readiness issues and old migration-head assertions were corrected; final gate/log results above supersede intermediate failures.
- No separate removed-member pathway interval survives the explicitly required cascade; removing a squad preserves intervals with a nullable squad reference. Timeline truth is limited to recorded/backfilled assignments (no historical seasons invented).
- Full-suite radar failures are pre-existing; live Azure reads/writes were intentionally not exercised. Azure private-container behavior is covered with a mocked SDK; local filesystem upload/read lifecycle is exercised through HTTP and in SQLite tests.
- Supplied `_prodenv.sh`, `ch01_preapply.sql`, `prod_check_ch01.sh`, `prod_preapply_ch01.sh`, and `prod_stamp_ch01.sh` are included unchanged. No prod script was executed.

## Planned Phase B2
- A player claims a club-created profile through a club invitation.
- Require an explicit **convert-to-public** step: provenance flip, normal moderation, and the adult gate. Claim approval alone does not publish a club identity.
- A club photo may become the public photo only with that adult player's explicit approval; private club storage must never itself become public.
- Minors remain private; normal suppression and relationship safeguards continue to apply.

### Phase B cleanup / delivery
- Backend/frontend servers stopped. Both throwaway databases dropped and absence verified. Task temporary credentials, local media, baseline extraction, scanner, scripts and intermediate logs removed; only `/tmp/club-home-b/shots/` and `walk.log` retained.
- Delivery: one local commit on `feat/club-home-b`, no push/PR/merge. Pre-existing untracked `.loan` symlink is left untouched.

### Phase B changed-file inventory
- Backend schema/models/config:
  - `academy-watch-backend/env.template`
  - `academy-watch-backend/migrations/versions/ch02_club_player_pages.py`
  - `academy-watch-backend/src/models/club_invitation.py`
  - `academy-watch-backend/src/models/funding.py`
  - `academy-watch-backend/src/models/showcase.py`
- Backend routes/services:
  - `academy-watch-backend/src/routes/club.py`
  - `academy-watch-backend/src/routes/club_home.py`
  - `academy-watch-backend/src/routes/club_players.py`
  - `academy-watch-backend/src/routes/contact.py`
  - `academy-watch-backend/src/routes/showcase.py`
  - `academy-watch-backend/src/services/club_player_profile.py`
  - `academy-watch-backend/src/services/feedback_development.py`
  - `academy-watch-backend/src/services/showcase_media_storage.py`
- Backend tests:
  - `academy-watch-backend/tests/test_cb01_coach_briefs.py`
  - `academy-watch-backend/tests/test_club_console.py`
  - `academy-watch-backend/tests/test_club_players.py`
  - `academy-watch-backend/tests/test_player_feedback.py`
  - `academy-watch-backend/tests/test_pm01_player_match_entries.py`
  - `academy-watch-backend/tests/test_s2_foundation.py`
  - `academy-watch-backend/tests/test_season_data_sea01.py`
- Frontend:
  - `academy-watch-frontend/src/App.jsx`
  - `academy-watch-frontend/src/components/admin/AdminSidebar.jsx`
  - `academy-watch-frontend/src/components/video/PlayerReel.jsx`
  - `academy-watch-frontend/src/lib/api.js`
  - `academy-watch-frontend/src/pages/MyClub.jsx`
  - `academy-watch-frontend/src/pages/MyClubConsole.jsx`
  - `academy-watch-frontend/src/pages/admin/AdminClubIdentities.jsx`
  - `academy-watch-frontend/src/pages/club-console/ClubHome.jsx`
  - `academy-watch-frontend/src/pages/club-console/PitchMap.jsx`
  - `academy-watch-frontend/src/pages/club-console/PlayerAvatar.jsx`
  - `academy-watch-frontend/src/pages/club-console/PlayerPage.jsx`
  - `academy-watch-frontend/src/pages/club-console/club-home.css`
- Ledger / deployment SQL and supplied tooling:
  - `ledgers/DIRECTIVE_club-home.md`
  - `ledgers/tooling/club-home/_prodenv.sh`
  - `ledgers/tooling/club-home/ch01_preapply.sql`
  - `ledgers/tooling/club-home/ch02_preapply.sql`
  - `ledgers/tooling/club-home/prod_check_ch01.sh`
  - `ledgers/tooling/club-home/prod_preapply_ch01.sh`
  - `ledgers/tooling/club-home/prod_stamp_ch01.sh`

## Phase B fix round 1 — complete
- Scope: batch photo reads and photo-free brief validation; origin fallback for unrostered identities with exactly one active managed program; durable squad-name snapshots; introduction expiry; ch02 production pre-apply/check scripts (not executed).
- Edit unapplied ch02 in place, mirror SQL exactly, verify focused/full suites and local PostgreSQL migration/schema equivalence, then one new commit (no amend/push).
- Evidence and scratch: `/tmp/club-home-b-fix1/`; preserve `run.log`. No shared/prod writes.

### Fix round 1 — as built and verified
- Photo resolution now prefetches approved player claims and approved primary photos once per roster response, keyed by `(local, local_player_id)` / `(tracked, player_api_id)`. Claimant ownership stays scoped to each identity, with unchanged adult/approval/provenance/precedence gates. Empty prefetched maps do not trigger fallback queries.
- `_brief_name_tokens` resolves only the subject/name and no longer serializes photo/public-stats fields. SQLAlchemy cold-session regression: **2 photo-related SELECTs for both 3 and 30 roster members**, zero photo-related SELECTs in name validation. The counter deliberately covers the claims/media reads addressed by this fix, not unrelated existing subject-resolution queries. Cross-subject owner and local/tracked ID-collision regression passes.
- Edited unapplied **ch02 / down_revision ch01** in place: guarded nullable `squad_name VARCHAR(80)` on history, backfilled from extant squads without overwriting existing snapshots. Assignment opening snapshots the name; aggregate reads the snapshot, preserving names after squad deletion. Assignment/cascade tests cover closed and current intervals.
- Origin backfill still prefers earliest roster membership. Only unrostered club identities with NULL origin can fall back to the creator's **exactly one distinct active managed program**. Zero/multiple active programs, missing creator, or revoked-only management leave origin NULL for explicit safeguarding resolution; non-club and existing non-NULL origins are unchanged.
- Profile introductions call the inbox's `_expire_visible_rows` on the exact player/program-visible query before serialization. Pending and accepted-awaiting-club-consent expiry tests pass; another program's rows stay untouched.
- Added `prod_preapply_ch02.sh` and `prod_check_ch02.sh` following ch01 patterns. Check prints Alembic version, history RLS, all history columns including squad_name, origin/photo columns and club NULL-origin count. **Neither production script was executed**; shell syntax only checked. No new env vars/dependencies/lockfile changes; no frontend source changes.

### Fix round 1 — gates and evidence
- Focused backend: `../.loan/bin/python -m pytest -q tests/test_club_players.py tests/test_club_home.py tests/test_club_console.py tests/test_contact.py tests/test_player_feedback.py tests/test_showcase.py tests/test_club_invitations.py tests/test_cb01_coach_briefs.py tests/test_pm01_player_match_entries.py tests/test_s2_foundation.py tests/test_season_data_sea01.py --basetemp=/tmp/club-home-b-fix1/pytest-focused` → **512 passed, 11 skipped**, 36.30s.
- Full CI backend: `../.loan/bin/python -m pytest -q --basetemp=/tmp/club-home-b-fix1/pytest-full` → **2897 passed, 35 skipped, 3 failed**, 114 warnings, 160.36s. Only the previously baseline-proven radar failures remain: `test_full_radar_chart_data`, `test_percentile_pool_stats`, `test_old_vs_new_comparison`.
- `ruff check academy-watch-backend` → **passed**. `ruff format --check academy-watch-backend` → **511 files already formatted**. `git diff --check` → **passed**.
- Frontend: `pnpm lint` → **0 errors, 182 warnings**; `pnpm build` → **passed**; `pnpm test` → **186 passed, 0 failed**. Existing dependencies reused without restore; no separate JSX typecheck script.
- Cloned local shared database into **aw_clubhome_b_fix1** and **aw_clubhome_b_fix1_sql**; every DB-aware application/gate command used clone-only DB env plus offline API flags/local media. Shared DB received no application/migration writes.
- PostgreSQL: `flask --app src.main db upgrade ch01`, then **upgrade ch02 / downgrade ch01 / upgrade ch02 passed**. Identical fictional fixtures proved single/multiple/no/revoked manager origin fallback, earliest membership precedence, non-club exclusion, history/name backfill, RLS, missing-column drift recovery and repeat idempotency including non-NULL preservation.
- Fresh comparison rerun after returning both clones to ch01: Alembic upgrade on one, transaction-wrapped `ch02_preapply.sql` on the other. `pg_dump --schema-only --no-owner --no-privileges -t public.club_roster_members -t public.club_roster_squad_history -t public.local_players` → **zero differences**, excluding only dump-generated restriction nonce lines. Both normalized schema SHA-256: **d3dc377fc2bb3b7f70875ec958789aabe6730f122b68d83a11f2cfb990ed62ba**. Exact migration/pre-apply SQL regression passes.
- Playwright bundled Chromium, isolated backend5094/frontend5194: **passed, zero API/console/page errors**. Fictional player assigned U16 → U18; both squads deleted; API references NULL while rendered timeline retains U16 and U18 plus the open unassigned interval. Screenshot visually reviewed: `/tmp/club-home-b-fix1/pathway-after-delete.png`.
- Initial new fixture errors (required roster actor / unique contact pair) corrected before final gates. Initial browser server-lifetime/readiness issue corrected by holding server processes through the walk; final walk passed. Log retained at `/tmp/club-home-b-fix1/run.log`.
- Final cleanup: isolated servers stopped; both throwaway databases dropped; temporary credentials/scratch removed while preserving run.log and the requested screenshot. One new local commit, no amend/push.
