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
| P1 | `feat/s1-match-entries-grain` / `.worktrees/s1-grain` | pm01 (player_match_entries, showcase_moderation_events, partial unique on local_players.api_player_id), model, owner match CRUD (`routes/player_matches.py`), rollup feeders user/club + source priorities | built `f4e2edc`; draft PR #963; CI green; basecamp sim 9/9 (db → pm01); check-P1 running | #963 |
| P2 | `feat/s1-local-player-universe` / `.worktrees/s1-identity` | is_external_player_id guard at every upstream boundary; approval mint (api_player_id=-id + no-network shadow); subject resolver; signed routes; suppression correlation; scout union behind SCOUT_INCLUDE_LOCAL_PLAYERS + `source` filter + provenance; contact/watch/follow negative acceptance; admin link-api re-key | built `d30b351` (20 files, 304 tests); draft PR #965; CI green; basecamp sim 9/9; check-P2 running | #965 |
| P4 | `feat/s1-user-fed-web` / `.worktrees/s1-web` | api helpers, ProvenanceChip, add-a-game CRUD on PlayerPage/LocalPlayerPage, scout source filter + chip, MyClub record-result dialog, mocked spec | built `ce817ac`+`b0e30cc`; PR #964; CI green; sim 9/9; check-P4 round 2 CLEAN — merge after backends | #964 |
| P3 | (after P1 merge) | club result/lineup adapter `POST /api/club/<program_id>/results` over PlayerMatchEntry (routes/club.py) | queued | — |
| P5 | (after P1+P2 merge) | trust-tiered auto-approval for low-risk profile edits using showcase_moderation_events + configured account-age threshold (fail closed) | queued | — |
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
