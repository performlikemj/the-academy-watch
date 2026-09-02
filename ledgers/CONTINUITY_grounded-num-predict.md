# Task Ledger: Grounded num_predict handling

Parent: `CONTINUITY.md`
Root: `CONTINUITY.md`
Related: `spike/video-analysis/qwen_match_analysis.py`, `spike/video-analysis/test_qwen_match_analysis.py`
Owner: `/root`

## Goal

- Prevent grounded caption and player-read JSON from being cut off by legacy pre-grounding token caps.
- Accept complete JSON at an Ollama length cap; surface invalid JSON as explicit truncation and retry it once with a larger bounded cap.
- Preserve legacy/ungrounded behavior.

## Constraints / Assumptions

- Work only in the `caption-cap` worktree on `fix/grounded-num-predict`.
- Do not call basecamp, Ollama, or any live service; tests use mocks only.
- Do not touch backend, worker, bench adapters, or `grounding.py`.
- Commit and push the PR #956 review round without merging or enabling auto-merge.

## Key decisions

- Grounded captions use 900 tokens initially: `3 × ~220 + 150 = 810`, rounded up below 1000.
- Grounded reads also use 900 tokens initially: `3 × ~100` plus generous headroom.
- Only grounded truncation retries double the cap (900 → 1800); the 2000 ceiling is a future guard and does not bind from 900. Legacy caps and ordinary invalid-output retries stay unchanged.

## State

- Done: Implemented parse-before-truncation, 900-token grounded caps, bounded grounded prompts, one 1800-token truncation retry, warning identities, and exact legacy/grounded cap-sequence regressions; the single review-round commit is pushed. Full mock-only spike suite and bare Ruff checks pass.
- Now: Await PR #956 review; do not merge.
- Next: Await PR review/merge, then validate separately in a post-merge regen.

## Links

- Upstream: `CONTINUITY.md`
- Downstream: PR to `main`
- Related: `ledgers/CONTINUITY_platform-review-qwen.md`

## Open questions (UNCONFIRMED)

- None blocking.

## Working set

- `spike/video-analysis/qwen_match_analysis.py`
- `spike/video-analysis/test_qwen_match_analysis.py`

## Notes

- 2026-09-02: Branch begins at `origin/main` with a clean worktree.
- 2026-09-02: Initial focused test before review round: `...python -m pytest spike/video-analysis/test_qwen_match_analysis.py -q` → 66 passed.
- 2026-09-02: Initial full test before review round: `...python -m pytest spike/video-analysis -q` → 124 passed.
- 2026-09-02: Review-round full test: `/Users/michaeljones/Projects/loanarmy/.loan/bin/python -m pytest spike/video-analysis -q` → 127 passed.
- 2026-09-02: Bare `ruff check spike/video-analysis/qwen_match_analysis.py spike/video-analysis/test_qwen_match_analysis.py` → all checks passed.
- 2026-09-02: Bare `ruff format --check spike/video-analysis/qwen_match_analysis.py spike/video-analysis/test_qwen_match_analysis.py` → both files already formatted.
