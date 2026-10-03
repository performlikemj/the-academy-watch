# PC2: one set of Scout numbers

Reported headlines import `merge_match_lines` and `season_totals` from the player page. Paired club figures win, unique self lines remain, ambiguous double headers retain every line. Raw club/user cells are evidence panels, never additive headlines. Mixed totals have `primary_source=matches`; pure club/user and provider source names remain. Provider sources win whole and are never added to reports. No schema change.

`reported_match_totals.scout_totals_projection` corrects old reported totals in a request-owned SQL relation **before** filters, ranking, counts and pagination. Scout readers, public team rosters and watchlist/list digest snapshots share the source selection. Missing provider rollups on positive reported identities use the same provider feeders in batches; a limited-coverage cache wins whole when detailed provider data is absent. Cache totals survive removal of the last own report. Orphan reported cells without source lines are withheld until the explicit rebuild clears them. Reads never refresh/write rows or call providers. Reported figures (raw or stored, including frozen evidence panels) require fresh conservative `public_adult_ids` evidence. Numeric age snapshots cannot establish a public adult. Private owner/manager match reads retain their existing authorization. Provider figures retain the legacy policy and win whole.

A canonical `source_breakdown.matches.revision=2` marks cells computed with the same one-pass boundary-decoded opponent/competition input as the player page. Only old or missing reported cells load and merge raw history. Canonical reads recheck policy and backing trusted lines but keep their figures in SQL. Corrected legacy rows use one JSON bind (`jsonb_to_recordset`) rather than a bound VALUES field per player, avoiding PostgreSQL’s 65,535-parameter cliff. Compare, watched/saved batches and explicit-ID CSV corrections are constrained to the selected identities before loading history.

`primary_source=matches` has its own `source_category=mixed`. The club filter means wholly club-confirmed totals; default boards exclude both self and mixed totals. `source=mixed` selects mixed totals. Provenance includes `club_confirmed` and `self_reported_only` line counts, so one confirmation cannot pass arbitrary self-only goals through the club filter.

New match writes already invoke the corrected `refresh_player` writer. Deployment is safe before and after the rebuild.

The desk/watchlist receive only these card additions: `approved_photo_url` (first approved photo ordered primary-first, sort order, then ID), `bio_line` (plain, one line, at most 160 characters), `club_confirmed` (confirmed affiliation). Enrichment follows existing adult/public eligibility and runs four batch queries. At reviewed head670b194b, the PostgreSQL 50-row page used11 queries before and17 after; both1-row and50-row pages used17. The fix-round50-row baseline is11 queries →22, with1-row and50-row pages both22; public report policy adds bounded set queries. Final PostgreSQL receipts are in `PC2F1.final.md`. The extra provider guard is batched; missing provider cells need at most five extra queries for the entire request (four existing feeders plus cache fallback).

## Off-container rebuild — renewal only, on MJ's go

Do not run inside the production web container. The script is outside `src`, so the Docker image does not include it. Use an off-container checkout and the **pooler's** psycopg URL, obtained through the existing secrets workflow; no production operation was performed by the builder.

```sh
cd ~/Projects/loanarmy/.worktrees/pc2
# Set PC2_DATABASE_URL via the approved secrets workflow:
# postgresql+psycopg://USER:PASSWORD@HOST.pooler.supabase.com:6543/postgres
python3 academy-watch-backend/scripts/rebuild_reported_match_totals.py --dry-run --limit 100 --delay 0.25
python3 academy-watch-backend/scripts/rebuild_reported_match_totals.py --limit 100 --delay 0.25 --checkpoint ./pc2-cursor.json --undo ./pc2-undo.jsonl
```

Read `players_figures_changed` / `seasons_figures_changed` for changed headline figures, separately from `players_changed` / `seasons_changed` (which also include metadata-only changes). `seasons_losing_totals` counts every previously present senior total that becomes absent or loses all nonzero figures. `losses` lists **every** affected player/season with before/after figures and source; it is independent of the five-item ordinary sample cap. Keep the JSON output as the operator’s complete preflight record.

Reported `club` / `user` / `matches` cells are derived from trusted `PlayerMatchEntry` rows. Repository writers/importers do not establish summary-only reported seasons. A report total without backing trusted rows is stale and is withheld; the rebuild removes it. This includes deleted/disputed rows and subjects the writer can no longer resolve as adults. Whole provider/cache/shadow totals remain. External historical imports or a production census are **UNCONFIRMED**: review every reported loss before any authorized production operation; this lane runs only local copies.

Repeat the write command until `players_scanned=0`. The durable cursor resumes after the last committed signed player ID. `--after` is also available for explicit signed cursors. A fresh dry-run ignores the checkpoint and scans from the start; re-running a write from the start skips identical derived cells. Keep one rebuild process running. Each player takes the rollup advisory lock, writes its undo record with fsync **before** commit, then atomically advances the cursor; no transaction spans the throttle sleep. Dry-run issues only SELECTs. The script accepts localhost for a rehearsal and the IPv4 pooler for hosted operation, requires explicit `PC2_DATABASE_URL`, and rejects container execution. It never loads app startup integrations or a default database URL.

Rollback, from the same checkout/target and with the saved journal:

```sh
python3 academy-watch-backend/scripts/rebuild_reported_match_totals.py --rollback ./pc2-undo.jsonl
```

Rollback restores the earliest recorded cells/totals per player under the same lock and never overwrites later changed derived facts. It skips conflicting players, continues restoring the others, and prints `players_restored` plus the complete `players_skipped` ID list. A partial restore exits **2**; a complete restore exits **0**. Repeating it is safe and reports the same skipped IDs while those facts remain changed. Reconstruct skipped players from current source facts instead of forcing the journal over newer data. Source match/provider facts are never modified. If reverting application code as well, restore compatible derived rows before reverting. Retain the cursor/undo together until the release is accepted; use a fresh pair for a new operation.

## PostgreSQL rehearsal

The owned local `aw_pc2` database used the repository's full model schema and fictional staging-modelled personas. It contained 54 match-entry rows for 6 identities, 11 old source cells and 6 old totals. This is a production-shaped copy, **not a production snapshot or a verified production census**. Actual production counts are UNCONFIRMED; renewal's dry-run is authoritative.

Exact commands used (Python has Flask/SQLAlchemy/psycopg dependencies):

```sh
createdb aw_pc2
PC2_DATABASE_URL=postgresql+psycopg:///aw_pc2 /Users/mjjones/Projects/loanarmy/.loan/bin/python academy-watch-backend/tests/pc2_rebuild_proof.py
PC2_DATABASE_URL=postgresql+psycopg:///aw_pc2 /Users/mjjones/Projects/loanarmy/.loan/bin/python academy-watch-backend/scripts/rebuild_reported_match_totals.py --dry-run --limit 100 --delay 0.05
PC2_DATABASE_URL=postgresql+psycopg:///aw_pc2 /Users/mjjones/Projects/loanarmy/.loan/bin/python academy-watch-backend/scripts/rebuild_reported_match_totals.py --limit 2 --delay 0.05 --checkpoint /Users/mjjones/codex-runs/aw-redesign/logs/PC2-cursor.json --undo /Users/mjjones/codex-runs/aw-redesign/logs/PC2-undo.jsonl
PC2_DATABASE_URL=postgresql+psycopg:///aw_pc2 /Users/mjjones/Projects/loanarmy/.loan/bin/python academy-watch-backend/scripts/rebuild_reported_match_totals.py --limit 100 --delay 0.05 --checkpoint /Users/mjjones/codex-runs/aw-redesign/logs/PC2-cursor.json --undo /Users/mjjones/codex-runs/aw-redesign/logs/PC2-undo.jsonl
```

Dry-run: **6 scanned / 5 changed players / 5 changed seasons**, 0.499 s. First batch: 2/2/2, 0.285 s; resumed batch: 4/3/3, 0.415 s. Full repeat: 6/0/0, 0.497 s. Rollback restored all 5 changed players, and a new dry-run again reported 6/5/5. Emeka's figures stay the same; his provenance gains the canonical match-line breakdown. Provider 1 app/90 min remains unchanged. At the default 0.25 s delay, six players add at least 1.5 s of throttle plus database/network time; do not infer production runtime from local latency. `aw_pc2` is dropped after the proof.

Raw receipts: `~/codex-runs/aw-redesign/logs/PC2-rebuild-{dry,first,resume,repeat,rollback,restored}.json`. The cross-surface test checks old and rebuilt cells, frozen/unfrozen, flags ON/OFF, existing/missing fixture/cache provider rollup, all eight stats. Added controls cover orphan cells, last-report cache retention and worldwide shadow latest/historical seasons. Historical metadata includes raw report/shadow/cache seasons in one query when history reads are enabled; provider-only legacy validation stays gated. The player-card source classifier recognises `matches` as reported, never provider data. It also proves dry-run has no writes, resume, idempotence and numeric-rating rollback.

## Fix-round rehearsal and compatibility

The review rehearsal adds two late-sorting orphan player-seasons (92000/92001, each12 apps/1080 minutes) so both losses fall beyond the five ordinary samples. Dry-run: **8 scanned / 7 changed players / 7 changed seasons; 6 players / 6 seasons with changed headline figures; 2 seasons losing totals**, 0.644 s. Both loss IDs are listed although neither appears in the five ordinary samples. Limit2/resume6 changed2+5; repeat cursor scans0; a full dry-run after rebuild scans6 with0 changes/losses (0.505 s). Rollback twice restores7; restored dry-run reproduces8/7/7,6 figures,2 losses (0.624 s). This is a fictional full-schema local copy, not a verified production census. With ANALYZE statistics on the owned bulk fixture,4000 reporting players avoid the prior76,064-bind failure (maximum12,016 parameters). First-read desk/boards2.056/3.702s; canonical rebuilt projection0.202s and zero match merges. Unanalyzed fresh bulk data was much slower; these are local shared-machine timings, not a production SLA. Final-head endpoint and all-surface before/after receipts are in external `~/codex-runs/aw-redesign/logs/PC2F1.final.md`; earlier receipts above remain historical evidence.

```sh
PC2_REVIEW_LOSS_FIXTURE=1 PC2_DATABASE_URL=postgresql+psycopg:///aw_pc2 /Users/mjjones/Projects/loanarmy/.loan/bin/python academy-watch-backend/tests/pc2_rebuild_proof.py
PC2_DATABASE_URL=postgresql+psycopg:///aw_pc2 /Users/mjjones/Projects/loanarmy/.loan/bin/python academy-watch-backend/scripts/rebuild_reported_match_totals.py --dry-run --limit 100 --delay 0.05
```

Flags OFF/unfrozen is deliberately not byte-identical to pre-PC2 main: worldwide shadows use their latest stored season when no season is picked; unknown optional card/keeper counts are null (web and iOS tolerate them), and public report compatibility/policy adds bounded database work. No-season team players now use the displayed season rather than career totals; provider flag-OFF adapters remain live, with whole corrected cache/report compatibility. Numeric parity and privacy guards apply before and after rebuild with flags ON or OFF. Production already has all four rollup surfaces ON; there is no new deployment flag or schema change.

## iOS

No binary change is needed to receive corrected numbers: Scout desk/boards, watchlist, compare and player season-stats already use these endpoints and decode the existing integer fields and provenance. The desk revalidates after loading its disk cache, so cached old figures can briefly remain until the network answer; refresh/reload for the staging check. Saved-list resolve now includes totals/provenance, but its current iOS DTO/view would need optional fields to display those new figures. The new `mixed` source category is additive; clients that offer source filters should label it “Merged match entries” and keep club-confirmed filters separate. Existing `primary_source=matches` remains. Optional confirmed/self-only provenance counts allow an honest confirmation ratio. Optional DTO fields `approvedPhotoUrl`, `bioLine`, `clubConfirmed` are needed if iOS adopts the new card data. This lane does not redesign iOS or change its raw match-log UI.

The pre-existing club-colour fallback needs a separate UI/data decision: `clubColorStyle` accepts a palette, but current page callers do not pass one; provider `Team` has no colour palette, so Bayern gets the CSS green/gold default. ClubProgram does have stored branding colours. No club-name guess/map or extra list payload field was added in PC2's three-field contract.

## PC2F2 reader boundary and operator fixes

All public reported headlines, including an absent total, pass through `scout_totals_projection`; scalar/batch wrappers use that relation. Compare reads the same projected candidate as the desk and never queries a stored total again. Saved worldwide shadows obtain stored reported figures through the same projection; whole shadow provider fallback remains. The relation is constrained to the requested identities, senior scope and season. The static reader guard rejects raw total queries/stat columns in routes/services/utils outside the projection module, with explicit private merge-writer and authenticated own-club evidence exceptions. Metadata-only season/freshness queries remain permitted.

The equality matrix now includes positive-ID old/canonical orphan and disputed-only cells. In all flag/freeze combinations, both before and after rebuild, recorded reported figures are absent or zero on every surface; Compare per-90 figures are null and provenance says **No recorded totals**, without a fictitious source badge. The flag-OFF legacy `/stats` fixture-list adapter has no reported headline; orphan/disputed fixtures return an empty list. Provider rich Compare fields retain their fixture enrichment.

The web offers **Club + self-reported** as a source filter and badge, with the confirmed/self-only counts in its tooltip. Default leaderboards still exclude mixed totals; selecting mixed includes them. iOS receives corrected Compare figures through its existing endpoint. Any native source selector/badge should add the mixed label and optional confirmation counts; no backend DTO/schema migration is required.

Projection and desk eligibility now share one request-owned policy memo; digest projections can use their existing run-owned memo. Never share it across requests/runs. The request-freshness regression proves each identity is evaluated once per desk request and again on the next request. Before rebuild, legacy correction still loads constrained trusted match history and costs grow with reporting players/matches. Canonical reads skip merging, but policy and backing-row checks still grow with candidates. Local timings are not a 0.5-CPU production SLA; hosted rebuild remains a separately authorized operation.

URL validation checks authority and every query `host` (including repeated/comma-separated hosts) before initializing the database. Remote query overrides and `hostaddr` overrides are refused; socket-local rehearsals and explicit pooler hosts remain accepted.

The conservative age policy is intentional: a real adult represented only by `age=30` without an exact DOB cannot publish reported facts. Owning-club-only identities and unpublished club-created bridges are also excluded. Correct verified DOB/publication evidence is required to restore eligibility; numeric age does not override privacy. Provider headline policy remains as documented above.

PC2F2 local full-schema loss rehearsal: dry-run **8 scanned / 7 structural changes / 6 figure changes / 2 losses**, both loss IDs beyond the ordinary sample cap, **0.625s**. Limit2/resume6, empty cursor repeat, clean dry6/0 (0.478s), complete undo7 twice. After a simulated later change on Reuben, partial undo restored6, skipped only-2, exited2, and repeated identically. Exact receipts and final-head query/scale/browser evidence: `~/codex-runs/aw-redesign/logs/PC2F2.final.md` and `PC2F2-rebuild.json`. The scratch database is dropped after final validation. No production/staging access or schema change.
