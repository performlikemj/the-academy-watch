# Task Ledger: Grounded num_predict handling

Parent: `CONTINUITY.md`
Root: `CONTINUITY.md`
Related: `spike/video-analysis/qwen_match_analysis.py`, `spike/video-analysis/test_qwen_match_analysis.py`
Owner: `/root`

## Goal

- Prevent grounded caption and player-read JSON from being cut off by legacy pre-grounding token caps.
- Surface Ollama length truncation explicitly and retry it once with a larger bounded cap.
- Preserve legacy/ungrounded behavior.

## Constraints / Assumptions

- Work only in the `caption-cap` worktree on `fix/grounded-num-predict`.
- Do not call basecamp, Ollama, or any live service; tests use mocks only.
- Do not touch backend, worker, bench adapters, or `grounding.py`.
- Commit, push, and open a PR without merging or enabling auto-merge.

## Key decisions

- Grounded captions and player reads both use 900 tokens initially: `3 × ~220 + 150 = 810`, rounded up below 1000.
- Only grounded truncation retries double the cap (900 → 1800, hard ceiling 2000); legacy caps and ordinary invalid-output retries stay unchanged.

## State

- Done: Implemented explicit length truncation, 900-token grounded caps, bounded grounded prompts, and one 1800-token truncation retry; added mock-only regressions; local pytest and scoped lint pass.
- Now: Deliver the single scoped commit and PR; do not merge.
- Next: Review/merge the PR, then validate separately in a post-merge regen.

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
- 2026-09-02: Focused test: `...python -m pytest spike/video-analysis/test_qwen_match_analysis.py -q` → 66 passed.
- 2026-09-02: Requested full test: `...python -m pytest spike/video-analysis -q` → 124 passed.
- 2026-09-02: `ruff check --config academy-watch-backend/pyproject.toml` on the two scoped files passes.
- 2026-09-02: Full-directory Ruff checks are baseline-red outside scope: bare check reports one unused variable in `anchor_identity.py`; configured check reports 13 pre-existing issues across other spike files; format check wants 16 files bare / 25 configured. No out-of-scope files changed.
