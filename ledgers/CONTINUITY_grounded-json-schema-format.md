# Task Ledger: Grounded JSON Schema Format

Parent: CONTINUITY.md
Root: CONTINUITY.md
Related: ledgers/CONTINUITY_grounded-caption-enum-prompt.md; ledgers/research/evidence-bench-2026-09-01.json
Owner: /root

## Goal

- Constrain grounded Qwen3-VL caption/read output with Ollama JSON Schema objects derived from the validator constants.
- Preserve legacy `format: "json"` requests byte-for-byte and retain all existing validation/coercion/recovery safety nets.
- Prove server support with one basecamp live check and accept schema mode only after the frozen 20-clip A/B gates pass.

## Constraints / Assumptions

- Work only in the `schema-format` worktree on `fix/grounded-json-schema-format`.
- Touch the requested implementation/tests, benchmark adapter/evidence, this ledger, and at most three lines in `CONTINUITY.md`.
- Pydantic imports must be lazy; legacy paths must not touch Pydantic.
- Do not load another Ollama model; stop if the server rejects or ignores the schema.

## Key decisions

- Use lazy, builder-local Pydantic v2 models so legacy calls do not import Pydantic.
- Accept schema mode: frozen A/B passed all three gates with identical grounding and zero malformed output.
- Preserve the documented Ollama 0.33.2 `message.thinking` fallback; the live response used it.

## State

- Done: Implemented grounded-only production schemas and bench `format_mode`; live check returned HTTP 200/stop; frozen A/B passed; full spike suite passed (150 tests); six touched spike files pass bare Ruff check/format; JSON evidence and diff checks pass; commit pushed and PR #972 opened without merge/auto-merge.
- Now: Complete.
- Next: Human review of PR #972.

## Links

- Upstream: `CONTINUITY.md`
- Downstream: `ledgers/research/evidence-bench-2026-09-02-schema-ab.json`
- Related: `ledgers/CONTINUITY_grounded-caption-enum-prompt.md`

## Open questions (UNCONFIRMED)

- None.

## Working set

- `spike/video-analysis/qwen_match_analysis.py`
- `spike/video-analysis/test_qwen_match_analysis.py`
- `spike/video-analysis/bench/adapters/qwen3vl_ollama.py`
- `spike/video-analysis/bench/test_bench.py`
- `ledgers/research/evidence-bench-2026-09-02-schema-ab.json`

## Notes

- No active continuity locks found at task start.
- Live: HTTP 200, `done_reason=stop`, content empty/unparseable, answer in thinking, eval_count 248, wall 5.38s.
- JSON report `~/Projects/loanarmy-bench-reports/schema-ab-json/report.json`: grounded 14/19, malformed 0, hollow 0, failed 1, 20.276s/clip.
- Schema report `~/Projects/loanarmy-bench-reports/schema-ab-schema/report.json`: grounded 14/19, malformed 0, hollow 0, failed 1, 20.179s/clip.
- Both modes failed only `m04-n02-t3005-474114-478131` before inference because its truth box was unavailable at the sampled timestamp.
- Verification: `/Users/michaeljones/Projects/loanarmy/.loan/bin/python -m pytest spike/video-analysis -q` (150 passed); bare Ruff check/format on six touched spike files passed; evidence JSON and `git diff --check` passed.
- Delivery: PR `https://github.com/performlikemj/the-academy-watch/pull/972`; no merge or auto-merge requested.
