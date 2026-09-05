# Money-safety stage (MS) — common brief header

Context: The Academy Watch (loanarmy monorepo). An independent review (`ledgers/research/astra-review-2026-09-05.md`, read it — Part 2 "Defects" and the
Appendix) found three P1 defects and three launch blockers that must be fixed BEFORE billing (`BILLING_ENABLED`) is switched on in prod. This stage fixes them.
Read first: `CLAUDE.md`, `docs/agents/backend.md`, `docs/agents/invariants.md` (migrations guard every DDL; RLS on every new public table; naive-UTC timestamps;
dialect-neutral SQLAlchemy; SQLite in-memory tests where `with_for_update` is a no-op), and for web `docs/agents/frontend.md`.
Python: `/Users/michaeljones/Projects/loanarmy/.loan/bin/python` (3.11). Gates (CI): `ruff check academy-watch-backend && ruff format --check academy-watch-backend`;
web: `cd academy-watch-frontend && pnpm lint && pnpm build` and `pnpm test`. Backend pytest is NOT a CI gate — run it yourself and report real counts.

Standing rules: you work alone in the worktree named in your package; stage files by path (never `git add -A`/`.`), never `--no-verify`, never merge, never push to
main, ONE commit unless told otherwise, no ledger/CONTINUITY/docs edits, no secrets printed, no changes outside your package's file list. Do not weaken tests.
Prod: Stripe LIVE keys — never call Stripe for real; tests use fakes/mocks only. Migrations: new revision id given in the package; `down_revision` = current head
(`flask db heads` → expect `s3d1`); guard DDL with existence checks; `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` on every new table (no policies).
Final report contract: diff stat; what you changed and why per item; the exact test/gate output lines; anything odd or unfinished; commit sha; PR URL.
Money-path lifecycle attacks the checker WILL run (design for them): duplicate/out-of-order/concurrent webhook events, partial refunds, config changes between
checkout and fulfilment, payment completing after account deletion, client replay of the same request, process death mid-stream.
# MS-M2 — club-confirmed statistics need a proven club–player relationship (P1)

Worktree: `/Users/michaeljones/Projects/loanarmy/.worktrees/ms-m2` (branch `fix/ms-m2-club-attribution`, from origin/main).
Files you may touch: `academy-watch-backend/src/routes/club.py`, `src/services/season_rollup_service.py` (only if the rollup must learn a new status),
`src/services/club_registry.py` (helper only), a new service module if cleaner, tests (`tests/test_club_results*.py` or a new `tests/test_club_result_affiliation.py`).
No migration unless truly unavoidable (say so in the report if you think one is; do not write one).

## The defect
`club.py:~821-850` deliberately lets an approved manager attach ANY tracked (positive `player_api_id`) player to the roster ("private video/report scope only").
But `club.py:~1030-1070` result entry then writes `PlayerMatchEntry(source="club", status="club_confirmed", club_program_id=program_id)` for those players, and
`season_rollup_service.py:~822` ranks club above user, so an unrelated approved club can PUBLISH misleading "club-confirmed" statistics for a player it has no
relationship with and displace the player's self-reported totals. Local players are safe today (a manager may only attach locals they created).

## Build (smallest correct mechanism — reuse what exists)
1. Define one helper `club_has_authority_over_player(program, player_api_id) -> bool` (put it near the roster code or in `club_registry.py`) that is TRUE when any of:
   a. `program.team_api_id` is set and equals the player's current club or parent/academy club api id (read `TrackedPlayer` fields: `current_club_api_id`,
      the parent club id column — find the real names in `src/models/`), or
   b. an approved affiliation/claim record already links this club program and this player — grep the models for the existing affiliation/claim tables
      (`club_program_claims`, player affiliations, `ClubRosterMember` flags) and use the one that expresses "the player or the club's verified identity authorised
      this link"; if none expresses player authorisation for tracked players, say so and rely on (a) only.
   Local players (negative ids) keep today's creator rule.
2. In result entry (`club.py` `~1004-1070`, the lineup loop): for every tracked player without authority → do NOT write a `club_confirmed` entry. Reject the whole
   request with HTTP 422 `{"error":"player_not_affiliated","player_api_ids":[...]}` listing the offenders (no partial writes). Keep the roster attach itself
   allowed (private scope), but make the roster response include `public_stats_allowed: bool` per member so the console can show why.
3. Belt and braces in the rollup: `season_rollup_service` should only take `club`-source cells whose `club_program_id` has authority (compute via the same helper,
   or a set of authorised (program, player) pairs) — if that is more than ~30 lines, skip it and say so; the write-side block is the primary fix.
4. Existing rows: add a read-only admin report endpoint? NO — out of scope. Instead print, in your report, a SQL query the orchestrator can run read-only in prod to
   list existing club_confirmed entries for players the program has no authority over (prod has 0 club claims today, so the count is expected to be 0).
Tests: manager of program A (team X) attaches tracked player of team Y → roster 200 with `public_stats_allowed=false`; result entry including that player → 422 with the
id listed and NO PlayerMatchEntry rows written (also none for the other, valid players in the same request); same manager, player whose current club == X → entry
written `club_confirmed`; local player created by the manager → unchanged behaviour; rollup for the team-Y player shows no club cells from program A.
Run: the club result tests + rollup tests you touch, `ruff check` + `ruff format --check`.
Commit: `fix(club): club-confirmed results require the club's authority over the player; unrelated attachments stay private`.
Push `fix/ms-m2-club-attribution`; open the PR (base main). Do NOT merge.

## CRITIQUE FOLD-IN (overrides anything above that conflicts)
- Authority seam: reuse `PlayerClubAffiliation` (`src/models/showcase.py:~399`; created owner-gated at `routes/showcase.py:~2502`; moderated statuses are
  `self_reported` (admin-approved) and `club_confirmed` (official) — there is NO `approved` status). Accept only those two statuses; exclude pending/rejected.
  `ClubProgramClaim` links a manager to a program, not a player — never treat it as player authority.
- Parent academy identity: `TrackedPlayer.team_id → Team.id → Team.team_id` (provider id) compared with `ClubProgram.team_api_id`; evaluate ALL tracked rows for the
  player (`_tracked_player(...)` returns one — do not rely on it here). Current club: `TrackedPlayer.current_club_api_id`. Test with deliberately different DB
  ids vs provider ids, and an academy match present only on a second tracked row.
- Temporal rule (decision): authority is established AT ENTRY TIME for the result's season: (a) current club == program team at entry time, or (b) a parent/academy
  tracked row for the program team, or (c) an accepted affiliation for that season (or any season if the affiliation has none). Once written, a result keeps its
  authority — the rollup MUST NOT re-evaluate current-club on rebuild (that would erase legitimate old-club results after a transfer). Therefore: NO rollup-side
  filter in this package (the reviewer asked for one; the orchestrator decided against it because it cannot be made time-correct without persisting a marker, and
  prod has zero club claims today so there are no legacy rows). Instead provide the read-only audit SQL that mirrors the exact write-side predicate.
- Validate BEFORE any mutation, covering every player whose existing or new row the request would modify (including players omitted from the submitted lineup
  whose fixture rows would be touched at `club.py:~1041`); on rejection nothing changes (single transaction, rollback). Test an unauthorized player omitted from
  the lineup and assert rows + rollups unchanged.
- Helper lives in a request-independent service (takes the caller's session; no `g`, no commits, no route imports). Preserve today's creator rule for local roster
  attachment and today's same-program result access for a second manager (`club.py:~611`) — test both.
- Tests/fences: the real suite is `tests/test_club_console.py` (~:653 for results; its programs lack provider identity at ~:90 — add fixtures with `team_api_id`
  without weakening existing assertions). Roster POST returns 201 (`club.py:~870`), GET 200. Add `public_stats_allowed` via `_member_dict` (`club.py:~503`) with
  explicit values for unavailable/minor/local members. Public match list at `routes/player_matches.py:~306` is outside the fence and unaffected because no
  unauthorized rows can be written after this change (state that in the PR).
