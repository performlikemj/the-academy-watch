# PC2: one set of Scout numbers

Reported headlines import `merge_match_lines` and `season_totals` from the player page. Paired club figures win, unique self lines remain, ambiguous double headers retain every line. Raw club/user cells are evidence panels, never additive headlines. Mixed totals have `primary_source=matches`; pure club/user and provider source names remain. Provider sources win whole and are never added to reports. No schema change.

`reported_match_totals.scout_totals_projection` corrects old reported totals in a request-owned SQL relation **before** filters, ranking, counts and pagination. All Scout readers share it. Missing provider rollups on positive reported identities use the same provider feeders in batches. Reads never refresh/write rows or call providers. New match writes already invoke the corrected `refresh_player` writer. Deployment is safe before and after the rebuild.

The desk/watchlist receive only these card additions: `approved_photo_url` (approved primary photo), `bio_line` (plain, one line, at most 160 characters), `club_confirmed` (confirmed affiliation). Enrichment follows existing adult/public eligibility and runs four batch queries. The measured PostgreSQL 50-row page used 11 queries before and 17 after; both 1-row and 50-row pages use 17. The extra provider guard is batched; missing provider cells need at most four extra queries for the entire request.

## Off-container rebuild — renewal only, on MJ's go

Do not run inside the production web container. The script is outside `src`, so the Docker image does not include it. Use an off-container checkout and the **pooler's** psycopg URL, obtained through the existing secrets workflow; no production operation was performed by the builder.

```sh
cd ~/Projects/loanarmy/.worktrees/pc2
# Set PC2_DATABASE_URL via the approved secrets workflow:
# postgresql+psycopg://USER:PASSWORD@HOST.pooler.supabase.com:6543/postgres
python3 academy-watch-backend/scripts/rebuild_reported_match_totals.py --dry-run --limit 100 --delay 0.25
python3 academy-watch-backend/scripts/rebuild_reported_match_totals.py --limit 100 --delay 0.25 --checkpoint ./pc2-cursor.json --undo ./pc2-undo.jsonl
```

Repeat the write command until `players_scanned=0`. The durable cursor resumes after the last committed signed player ID. `--after` is also available for explicit signed cursors. A fresh dry-run ignores the checkpoint and scans from the start; re-running a write from the start skips identical derived cells. Keep one rebuild process running. Each player takes the rollup advisory lock, writes its undo record with fsync **before** commit, then atomically advances the cursor; no transaction spans the throttle sleep. Dry-run issues only SELECTs. The script accepts localhost for a rehearsal and the IPv4 pooler for hosted operation, requires explicit `PC2_DATABASE_URL`, and rejects container execution. It never loads app startup integrations or a default database URL.

Rollback, from the same checkout/target and with the saved journal:

```sh
python3 academy-watch-backend/scripts/rebuild_reported_match_totals.py --rollback ./pc2-undo.jsonl
```

Rollback restores the earliest recorded cells/totals per player under the same lock and refuses to overwrite later changed derived facts. If refused, rebuild from the current source facts instead. Source match/provider facts are never modified. If reverting application code as well, restore compatible derived rows before reverting. Retain the cursor/undo together until the release is accepted; use a fresh pair for a new operation.

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

Dry-run: **6 scanned / 5 changed players / 5 changed seasons**, 0.487 s. First batch: 2/2/2, 0.248 s; resumed batch: 4/3/3, 0.439 s. Full repeat: 6/0/0, 0.526 s. Rollback restored all 5 changed players, and a new dry-run again reported 6/5/5. Emeka's figures stay the same; his provenance gains the canonical match-line breakdown. Provider 1 app/90 min remains unchanged. At the default 0.25 s delay, six players add at least 1.5 s of throttle plus database/network time; do not infer production runtime from local latency. `aw_pc2` is dropped after the proof.

Raw receipts: `~/codex-runs/aw-redesign/logs/PC2-rebuild-{dry,first,resume,repeat,rollback,restored}.json`. The cross-surface test checks old and rebuilt cells, frozen/unfrozen, flags ON/OFF, existing/missing provider rollup, all eight stats. It also proves dry-run has no writes, resume, idempotence and numeric-rating rollback.

## iOS

No binary change is needed to receive corrected numbers: Scout desk/boards, watchlist, compare and player season-stats already use these endpoints and decode the existing integer fields and provenance. The desk revalidates after loading its disk cache, so cached old figures can briefly remain until the network answer; refresh/reload for the staging check. Saved-list resolve now includes totals/provenance, but its current iOS DTO/view would need optional fields to display those new figures. Optional DTO fields `approvedPhotoUrl`, `bioLine`, `clubConfirmed` are needed if iOS adopts the new card data. This lane does not redesign iOS or change its raw match-log UI.

The pre-existing club-colour fallback needs a separate UI/data decision: `clubColorStyle` accepts a palette, but current page callers do not pass one; provider `Team` has no colour palette, so Bayern gets the CSS green/gold default. ClubProgram does have stored branding colours. No club-name guess/map or extra list payload field was added in PC2's three-field contract.
