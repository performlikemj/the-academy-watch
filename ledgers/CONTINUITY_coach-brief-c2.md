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
- Briefed players use two calls: the byte-identical ordinary grounded read gets no brief; a Pydantic-parsed checks-only call gets private text and emits no prose.
- The worker-owned payload supplies the 8-line maximum and roster `(kit_color, jersey_number)` identity; eligibility comes from `player_tracks` plus interpolated evidence, never caption windows.

## State

- Done: Implemented review round 3: no-kit roster briefs now reach the spike as structured skips, overlength limits use payload `max_lines`, and brief normalization has one source.
- Now: Await re-review of PR #985 after the single Round 3 fix commit; PR remains open and unmerged.
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

- Review round 3: blank-kit jobs write and pass `brief.json` with `no_kit_colour` skips; the spike emits the roster-specific limit without scheduling checks or adding the generic checks limit; overlength text is `max_lines`-driven; `_brief_payload` returns payload plus normalized line count.
- Verified review round 3: `pytest spike/video-analysis -q` -> 176 passed; requested backend suite -> 85 passed; backend Ruff check/format and bare spike Ruff check/format pass.
- No Ollama calls, no merge, and no frontend changes in review round 3.
- Review round 2: private checks failures now persist fixed text and log type-only metadata; missing-kit, empty-track, and overlength paths degrade honestly; spike 175, requested backend 121, backend Ruff 460 files and bare spike Ruff 2 files all pass.
- Verified review round: `pytest spike/video-analysis -q` -> 170 passed.
- Verified review round: backend requested suite -> 87 passed.
- Verified review round: backend `ruff check .` + `ruff format --check .` pass (459 files); bare spike Ruff check/format pass (2 files).
- Verified by direct pre-fix comparison: no-brief grounded prompt and response schema are byte-identical.
- Not verified (inherited baseline): exact backend `pytest -q` stops at the same 12 legacy collection errors documented upstream.
- Diagnostic only: with those 12 modules ignored, 1,975 passed / 42 unrelated failures / 3 skipped; no failure names touch C2 files.
- No Basecamp/Ollama calls and no frontend changes.
- PR: https://github.com/performlikemj/the-academy-watch/pull/985 (open; not merged).
- PR checks: Backend Lint, Frontend Dependency Security / osv-scan, and Frontend Build & Lint passed.
