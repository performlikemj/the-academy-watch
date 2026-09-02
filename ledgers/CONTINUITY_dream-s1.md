# CONTINUITY — Dream roadmap S1: "One player universe + a games grain"

Parent: `CONTINUITY.md` · Source: `ledgers/GRADING_dream-scorecard-2026-09-02.md` (after S0: 54.1%) · Design: `ledgers/DIRECTIVE_phase1-user-fed-data.md`
Owner: MJ · Orchestrator: Fable · Executor: codex CLI (gpt-5.6-sol, ultra) · Started 2026-09-02 (MJ: "go S1, show the stats with the chip")

## Decisions (ratified 2026-09-02)
- **D1 id space:** negative synthetic `player_api_id = -local_player_id` for approved local players not linked to API-Football; shadow row minted; admin `link-api` re-keys later. (Fable call, per directive recommendation.)
- **D2 scout desk:** self-reported and club-entered stats ARE shown on the scout desk with a provenance chip (`api` / `club` / `self`) and a `source` filter. (MJ.)
- **D3 minors:** stats entry allowed for minors but never public (existing minor bridges apply to negative ids too). (Standing D1 policy.)

## Target rows (scorecard) → 3
1.3 add my own games/stats · 1.4 be found in scout discovery (local players) · 2.3 track games without video (club result + lineup entry) · 4.7 grassroots attested data path (same grain, provenance) · (1.2 trust-tiered auto-approval → 3 if it fits). Projected overall after S1 ≈ 59%.

## Status
- 2026-09-02 — recon dispatched (codex read-only, worktree `.worktrees/s1-recon` @ origin/main after S0) to re-verify every anchor of the Aug-23 directive; packages + briefs follow from its JSON.

## Log
- 2026-09-02 — ledger created.

## Packages (wave 1 in parallel; wave 2 after P1 merges)
| Pkg | Branch / worktree | What | Status | PR |
|---|---|---|---|---|
| P1 | `feat/s1-match-entries-grain` / `.worktrees/s1-grain` | pm01 (player_match_entries, showcase_moderation_events, partial unique on local_players.api_player_id), model, owner match CRUD (`routes/player_matches.py`), rollup feeders user/club + source priorities | **MERGED 9a9c1c6** (3 rounds; 147 tests; prod pm01 pre-applied + stamped) | #963 |
| P2 | `feat/s1-local-player-universe` / `.worktrees/s1-identity` | is_external_player_id guard at every upstream boundary; approval mint (api_player_id=-id + no-network shadow); subject resolver; signed routes; suppression correlation; scout union behind SCOUT_INCLUDE_LOCAL_PLAYERS + `source` filter + provenance; contact/watch/follow negative acceptance; admin link-api re-key | **MERGED bd83b9c** (3 rounds; 317 tests; club _member_subject fallback deferred to P3) | #965 |
| P4 | `feat/s1-user-fed-web` / `.worktrees/s1-web` | api helpers, ProvenanceChip, add-a-game CRUD on PlayerPage/LocalPlayerPage, scout source filter + chip, MyClub record-result dialog, mocked spec | **MERGED 5c93178** (3 rounds; spec 7/7; live bundle verified: chips, Add a game, results dialog, withheld rows) | #964 |
| P3 | `feat/s1-club-results` / `.worktrees/s1-club-results` | club result/lineup adapter `POST /api/club/<program_id>/results` over PlayerMatchEntry (routes/club.py) + `_member_subject` shadow fallback + club_roster_member_id echo | **MERGED 19dd52f** (2 rounds; 43 console tests) | #968 |
| P5 | `feat/s1-trust-tiered-edits` / `.worktrees/s1-trust` | trust-tiered auto-approval (fail closed until configured) + graduation re-key of player_match_entries + rollup backfill for entry-only subjects + negative watchlist delete idempotency | **MERGED 8e0e0ae** (2 rounds; 293 tests) | #969 |
Policy decided today: browse shows all sources with a chip; default leaderboards exclude `self` unless `source=self`; server enforces source. Prod flag `SCOUT_INCLUDE_LOCAL_PLAYERS` flipped ON by the orchestrator after P1+P2 deploy.
- 2026-09-02 — recon JSON `scratchpad/s1-recon.json` (anchors/contracts extracted to s1-anchors.json / s1-contracts.json); P1+P2+P4 dispatched.
- 2026-09-02 — P2 stopped honestly (fence lacked services/player_suppression.py + transfer_heal_service.py) → fence extended, session resumed.
- 2026-09-02 — P1 handed back (f4e2edc: pm01 + models + owner CRUD + feeders; 119 tests) → draft PR opened; check-P1 + sim running; prod DDL staged (scratchpad/pm01_preapply.sql) pending CLEAN.
- 2026-09-02 — P4 handed back (ce817ac, 8 files, spec 5/5) → draft PR opened; check-P4 + sim running; merge after backend packages.
- 2026-09-02 — check-P1 FIX-FIRST (P2: minor enumeration via write routes; manager read gate ignores program approval; P3s: IntegrityError 500s, date bounds, club cell namespace, 0-minute appearances, 17/18 boundary tests, read/write relationship asymmetry) → fix round 1 dispatched.
- 2026-09-02 — check-P4 FIX-FIRST (P2: season totals vanish after add/edit because the real P1 write response is {cells,totals}; spec mocked an invented shape; P3s: 404 card, skeleton flash, per_page cap, 401 handler, roster keys) → fix round 1 dispatched.
- 2026-09-02 — P1 fix round 1 handed back (d73b1f2; 128 tests) → pushed to #963; check-P1 round 2 running. Follow-up routed to P2 (owns players.py): source_breakdown still exposes hashed competition_tier.
- 2026-09-02 — check-P1 round 2 CLEAN (P3 follow-ups: players.py source_breakdown label → P2; export is_manager_of_approved_program publicly; refresh_player cell re-insert race under real PG; auth bearer duplication). **PROD PRE-APPLIED pm01 DDL** (tables + RLS + indexes; stamp after merge).
- 2026-09-02 — P2 handed back (d30b351, 20 files, 304 tests) → draft PR opened; check-P2 + sim running. Outside-fence notes: club.py _member_subject should resolve PlayerShadow identities (→ P3), tests/test_season_rollup_reads.py has 6 stale exact-payload assertions (→ P2 fix round, ALLOWED extended).
- 2026-09-02 — Bot review on #963: (1) delete_account crashes on new FKs, (2) minor-entered cells leak into public rollup totals, (3) export omits entries → P1 fix round 2 dispatched (policy: self rows deleted + rollup refreshed; club rows + moderation events repointed to tombstone; feeders skip minors; export includes match_entries).
- 2026-09-02 — P4 fix round 1 handed back (b0e30cc; spec 7/7) → pushed to #964; check-P4 round 2 running.
- 2026-09-02 — check-P4 round 2 CLEAN (P3s: roster api_player_id branch inert vs real payload → P3 echoes club_roster_member_id; spec ordering/dedupe nits; whitespace). #964 merges after P1/P2/P3.
- 2026-09-02 — check-P2 FIX-FIRST (no P1; P2s: admin manual-add broken by the positive-id guard, digest lacks minor bridge, rollup breakdown labels, 6 stale rollup-read tests, prod has 3 orphan negative `players` rows (-10/-11/-12, placeholders from Nov 2025, zero references) → guard ignores orphans; deletion needs MJ's OK; deferred to integration: match-entry re-key + club _member_subject shadow fallback) → fix round 1 dispatched.
- 2026-09-02 — P1 fix round 2 handed back (e1f83ff; 147 tests) → pushed to #963; check-P1 round 3 running.
- 2026-09-02 — P2 fix round 1 handed back (ee7a0c1; 13 files; all gates) → pushed to #965; check-P2 round 2 running. check-P1 round 3 relaunched after a usage-limit failure. #966 (video-analysis docs) merged → main 6742508.
- 2026-09-02 — Docs PR #967 MERGED (main 458c303); primary checkout fast-forwarded (stale July index lines dropped with CONTINUITY.md reset; identical untracked copies removed; DIRECTIVE_evidence-bench.md local copy differed → moved aside for video-analysis).
- 2026-09-02 — check-P1 round 3 CLEAN (P3 follow-ups: backfill enumeration for match-entry subjects → P5; subject-existence rule duplication; carried notes). Bot threads answered + resolved; merging #963.
- 2026-09-02 — check-P2 round 2 FIX-FIRST (P1: public profile reads the orphan legacy Player row for negative ids — consequence of orphan tolerance; P3s) → fix round 2 dispatched.
- 2026-09-02 — **#963 MERGED → main 9a9c1c6**; Deploy 33599295646 watching; prod alembic_version stamped pm01; P3 (club results) dispatched from the new main.
- 2026-09-02 — prod alembic_version stamped pm01 (tables existed); s1-grain worktree removed; P3 running from main 9a9c1c6.
- 2026-09-02 — P2 fix round 2 handed back (c1e13b2; 317 tests) → pushed to #965; check-P2 round 3 running.
- 2026-09-02 — **P1 LIVE**: Deploy 33599295646 success, r413-1 healthy, /api/players/<id>/matches → 404 neutral (unknown), 401 unauth POST, negative id 404.
- 2026-09-02 — #965 CI green on c1e13b2, sim 9/9, no file overlap with merged P1 → marked ready (bot window); merge gated on check-P2 round 3.
- 2026-09-02 — check-P2 round 3: only open item is club.py _member_subject shadow fallback (outside P2's fence; P3 is implementing it now) → DEFERRED by the orchestrator, package otherwise clean; P3 for the negative-id watchlist double-click → P5. #965 merges after its bot review.
- 2026-09-02 — NOTE: the chatgpt-codex-connector PR bot has hit its code-review usage limit (its own comment on #963), which is why #961/#965 got no bot review; merges proceed on the Fable checkers + CI + sim. P3 monitor false-alarmed on that text (process alive, WIP in club.py + tests).
- 2026-09-02 — **#965 MERGED → main bd83b9c**; Deploy 33601196534 watching; P5 dispatched from the new main; flip SCOUT_INCLUDE_LOCAL_PLAYERS=1 in prod after the deploy settles.
- 2026-09-02 — **P2 LIVE**: Deploy 33601196534 success, r414-1 healthy; prod env SCOUT_INCLUDE_LOCAL_PLAYERS=1 set (new revision, verified above).
- 2026-09-02 — MJ approved: deleted the 3 orphan legacy players rows (-10/-11/-12) from prod (zero references re-verified in the same transaction).
- 2026-09-02 — MJ rotated the Mailgun key into the container; vault secret job-scout-digest-mailgun-api-key re-synced (new version) and the key verified against the Mailgun API (status only). Orphan negative players rows deleted.
- 2026-09-02 — P3 handed back (1550e9e; 39 console tests) → draft PR opened; check-P3 + sim running. Risks to attack: reporter-scoped uniqueness (two managers double-count), video_match_id not persisted.
- 2026-09-02 — check-P3 FIX-FIRST (P1 double-count proven: reporter-scoped identity; P2 history grouping; P3s: video_match_id echo-only, roster minor rule) → fix round 1 dispatched. Later migration: partial unique index on club rows per program.
- 2026-09-02 — P5 handed back (0dd4535; 233 tests) → draft PR opened; check-P5 + sim running. Outside-fence follow-ups: suppression route should append 'suppressed' events; rollup service year-only adult bridge after graduation.
- 2026-09-02 — check-P5 FIX-FIRST (P2s: graduation refresh before api_player_id set → minor cell window; staged attestation revert ignored; year-only adults lose totals on graduation; P3s: rebuild route negatives, eligibility lock, mutation tests, suppression event producer) → fix round 1 dispatched (ALLOWED + rollup service age rule + suppression route).
- 2026-09-02 — P3 fix round 1 handed back (0590028; 43 tests) → pushed to #968; check-P3 round 2 running. P4 micro-round 2 dispatched (withheld-minor rows, roster-member keys).
- 2026-09-02 — #968 CI green on 0590028, sim 9/9 → marked ready; merge gated on check-P3 round 2 (bot reviewer is out of quota today).
- 2026-09-02 — check-P3 round 2 CLEAN (P3s → s1-hygiene-items: cross-program FOR UPDATE deadlock→409, case-insensitive opponent identity, legacy duplicate 409). Merging #968.
- 2026-09-02 — **#968 MERGED → main 19dd52f**; Deploy 33607162453 watching. Next: P4 (#964) after its micro-round check; P5 (#969) after its fix round check.
- 2026-09-02 — **P3 LIVE**: Deploy 33607162453 success, r416-1, health 200, /api/club/<id>/results 401 unauth.
- 2026-09-02 — check-P4 round 3 CLEAN → **#964 MERGED** (see sha above); frontend fast deploy watching.
- 2026-09-02 — #969 CI green on 44b9082, sim 9/9 → marked ready; merge gated on check-P5 round 2 (after #964's frontend deploy).
- 2026-09-02 — #964 first merge attempt failed (still draft — my miss); video-analysis merged #970 (regen-11 prompt fix, b787de2) meanwhile; #964 marked ready and merged (see sha above).
- 2026-09-02 — check-P5 round 2 CLEAN (P3s → hygiene). Merging #969 after #964's deploy.
- 2026-09-02 — INCIDENT: #964 merge failed ('Head branch is out of date' after #970 landed) and my cleanup line, chained with ';', deleted the remote branch → GitHub auto-closed the PR. Recovered: re-pushed from the intact worktree, reopened #964, strict flag checked, branch updated with main, merging. Lesson: never chain branch deletion after a merge with ';' — gate it on MERGED with && only.
- 2026-09-02 — **#964 MERGED → main 5c93178; P4 LIVE** (Deploy Frontend fast 33609132372 success; bundle index-CtOKf01g.js carries all S1 web strings). Branch-protection strict flag confirmed OFF; the earlier 'out of date' error cleared via gh pr update-branch.
- 2026-09-02 — **#969 MERGED → main 8e0e0ae** (all five S1 packages merged); Deploy 33609308917 watching; then set SHOWCASE_TRUST_MIN_ACCOUNT_AGE_DAYS=14 in prod.
- 2026-09-02 — **P5 LIVE** (Deploy 33609308917 success); prod env `SHOWCASE_TRUST_MIN_ACCOUNT_AGE_DAYS=14` set (revision 0000015 healthy), `SCOUT_INCLUDE_LOCAL_PLAYERS=1` confirmed. **S1 COMPLETE AND LIVE.** Re-score: 1.2/1.3/1.4/2.3/4.7 → 3 → **59.8%** (after S0 54.1%, baseline 51.9%). Artifact republished (label 'after S1'). Hygiene sweep S1-E in flight (separate PR). Next stage: S2 (fans + reach).
- 2026-09-02 — S1-E hygiene handed back (4c5f873; 14 files; 313+38 tests, spec 7/7) → draft PR opened; check-E + sim running.
- 2026-09-02 — S1-E PR #974: CI green, basecamp sim 9/9; merge gated on check-S1E.
- 2026-09-02 — check-S1E FIX-FIRST (P2: graduation FOR UPDATE before the new advisory lock → deadlock cycle; P2: SQL vs Python case fold for non-ASCII opponents; P3s) → fix round 1 dispatched. Pre-existing failing tests noted on main: test_local_clubs TestAffiliationVisibility ×3, test_account ×1 (not from S1).
- 2026-09-02 — S1-E fix round 1 handed back (b47fa99; 391 tests) → pushed to #974; check-S1E round 2 running.
- 2026-09-02 — check-S1E round 2 CLEAN (P3: expose lock_player_refresh publicly → later). Merging #974.
- 2026-09-02 — **S1-E hygiene MERGED → main e217e85**, Deploy 33618632835 success, health 200. S1 fully closed (5 feature PRs + hygiene). Remaining S1 debts: partial unique index on club result rows + persisted video_match_id (migration), iOS add-a-game, lock_player_refresh public name, pre-existing failing tests (test_local_clubs ×3, test_account ×1).
