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

## Planned Phase B
- Club player page and club-uploaded player photos.
- Photo precedence: claimed player's approved photo > club photo > API photo.
- Minors' club photos never public.

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
