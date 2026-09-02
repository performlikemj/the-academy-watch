# CONTINUITY — Coach's brief C2

Parent: `ledgers/CONTINUITY_coach-brief.md`
Root: `CONTINUITY.md`
Related: `ledgers/DIRECTIVE_coach-brief.md`, `ledgers/CONTINUITY_grounded-json-schema-format.md`
Owner: /root

## Goal

- Implement directive C2: separate private brief context in the worker and grounded, hash-only expectation checks in the analysis spike.
- Deliver mocked tests, full requested verification, one scoped commit, pushed branch, and an open PR to `main`.

## Constraints / Assumptions

- Backend/spike only; no frontend.
- No Basecamp or Ollama calls.
- `brief_context` must never enter `_analysis_context` or the team pass.
- Persist hashes and expectation indexes only; never brief text, names, or position.
- Admin/no-program behavior stays byte-identical.
- C1 prerequisite confirmed: `ClubRosterMember.coach_brief_body` exists on merged-main commit `34f003e`.
- Stage by explicit path; no `git add -A`; no `--no-verify`; do not merge the PR.

## Key decisions

- Use the existing grounded schema models and Ollama schema-format path because C1's base includes merged PR #972.
- Use the shared grounding rule in `spike/video-analysis/grounding.py` for brief-check downgrades.

## State

- Done: Implemented and delivered separate worker `brief.json`; optional spike input; independent eligible brief scheduling; numbered grounded prompt; strict Pydantic/Ollama schema; hash-only checks; shared grounding downgrade gate; counters; honest limits; zero-observation support; privacy and legacy regressions. PR #985 is open and unmerged.
- Now: Await review of PR #985.
- Next: Fable acceptance regeneration after merge (outside this task and explicitly not run here).

## Links

- Upstream: `ledgers/CONTINUITY_coach-brief.md`
- Downstream: C3 club UI/display (not in scope)
- Related: grounded schema/gate work in `spike/video-analysis/`

## Open questions (UNCONFIRMED)

- None.

## Working set

- `academy-watch-backend/src/workers/vision_worker.py`
- `academy-watch-backend/tests/`
- `spike/video-analysis/qwen_match_analysis.py`
- `spike/video-analysis/grounding.py`
- `spike/video-analysis/test_*.py`

## Notes

- Verified: `pytest spike/video-analysis -q` -> 167 passed.
- Verified: `pytest tests/test_vision_worker.py -q` -> 25 passed.
- Verified: combined changed tests -> 129 passed.
- Verified: backend-config Ruff check/format on worker + test; bare Ruff check/format on spike + test.
- Verified: no-brief grounded player prompt SHA-256 matches `origin/main` exactly (`d0351d...f45e`).
- Not verified (inherited baseline): exact backend `pytest -q` stops at the same 12 legacy collection errors documented upstream.
- Diagnostic only: with those 12 modules ignored, 1,975 passed / 42 unrelated failures / 3 skipped; no failure names touch C2 files.
- No Basecamp/Ollama calls and no frontend changes.
- PR: https://github.com/performlikemj/the-academy-watch/pull/985 (open; not merged).
- PR checks: Backend Lint, Frontend Dependency Security / osv-scan, and Frontend Build & Lint passed.
