# Task Ledger: Dev club fixture bridge (B1)

Parent: `ledgers/CONTINUITY_coach-brief.md`
Root: `CONTINUITY.md`
Related: `ledgers/DIRECTIVE_coach-brief.md` §3 Acceptance and §8 B1
Owner: `/root`

## Goal

- Add a backend-only, dev-guarded, idempotent CLI that attaches an existing video match to a manager-owned club program and maps every match roster entry to a local club roster member.
- Cover guard refusals, complete bridge behavior, club authorization/reel visibility, and idempotency in SQLite tests.
- Deliver a scoped commit and open PR against `main`; do not merge or run the script against basecamp/prod.

## Constraints / Assumptions

- Worktree: `feat/dev-club-fixture-bridge`; backend only.
- Require `ALLOW_FIXTURE_BRIDGE=1`; reject production-like environments and database hosts containing `supabase` or `pooler` before database mutation.
- `ClubProgram.funding_league_id` and `ClubProgramManager.source_claim_id` are mandatory; roster subjects obey the API/local XOR constraint.
- Existing match association may be reused only when it points to the same resolved program.
- Stage files by explicit path; never use `git add -A`, `--no-verify`, basecamp execution, or production execution.

## Key decisions

- Program access must satisfy the existing registry contract: approved program, approved claim, active manager, non-hidden program.
- MyClub activation additionally relies on the approved program claim.
- Fixture-created programs use a deterministic `*-dev-fixture` slug and the approved/open `Dev fixture league`; exact-name ambiguity is refused rather than guessed.
- Each script-created roster membership carries a private match-entry marker so an unlinked fixture can be repaired without duplicating its local identity.
- Dry-run executes the same transaction and reports assigned IDs/counts, then rolls back before returning.

## State

- Done: guarded/idempotent CLI, dev README, and SQLite coverage implemented; full bridge exposes 18 authorised roster members and 18 reel players; rerun creates zero rows; dry-run rolls back.
- Done: `/Users/michaeljones/Projects/loanarmy/.loan/bin/pytest -q tests/test_dev_bridge_match_to_club.py tests/test_club_console.py` → 53 passed in 3.42s.
- Done: `ruff check academy-watch-backend && ruff format --check academy-watch-backend` → clean; 445 files already formatted.
- Done: scoped commit pushed and PR #975 opened against `main`: `https://github.com/performlikemj/the-academy-watch/pull/975`.
- Now: implementation work complete; PR remains open and unmerged.
- Next: reviewer/Fable runs the script on basecamp only after C1 merges; this workstream did not run it or merge the PR.

## Links

- Upstream: `ledgers/CONTINUITY_coach-brief.md`
- Downstream: none
- Related: `academy-watch-backend/src/services/club_registry.py`, `academy-watch-backend/src/routes/club.py`

## Open questions (UNCONFIRMED)

- None blocking.

## Working set

- `academy-watch-backend/scripts/dev/bridge_match_to_club.py`
- `academy-watch-backend/scripts/dev/README.md`
- `academy-watch-backend/tests/test_dev_bridge_match_to_club.py`
- `academy-watch-backend/tests/test_club_console.py`

## Notes

- 2026-09-02: no basecamp or production command will be run in this workstream.
- 2026-09-02: first focused run exposed a nested Flask-context identity-map issue in the test caller; `execute_bridge` now reuses the active app context and all requested checks pass.
- 2026-09-02: delivery complete in PR #975; basecamp execution and C1-dependent brief-key behavior remain intentionally unverified here.
