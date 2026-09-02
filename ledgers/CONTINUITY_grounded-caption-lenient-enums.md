# Task Ledger: Grounded caption lenient enums

Parent: `CONTINUITY.md`
Root: `CONTINUITY.md`
Related: `ledgers/CONTINUITY_grounded-num-predict.md`
Owner: `/root`

## Goal

- Keep grounded caption windows when labels are outside the vocabulary or individual claims are malformed.
- Coerce unknown grounded labels, drop only malformed claims, and report fault counters in sampling.
- Preserve legacy caption validation behavior exactly.

## Constraints / Assumptions

- Work only in the `caption-enum` worktree on `fix/grounded-caption-lenient-enums`.
- Limit code changes to the two requested spike files; use mocked tests only and make no basecamp/Ollama calls.
- Commit, push, and open a PR to `main`; do not merge or enable auto-merge.

## Key decisions

- Normalize grounded captions in parsing before the pure schema validator: structural caption/claims failures still retry, while invalid labels and individual claims are repaired or removed.

## State

- Done: Implemented grounded-only label coercion, per-claim fault isolation, warnings/counters, sampling output, and regressions; all required tests and Ruff checks pass.
- Now: Deliver on the scoped branch and await PR review; do not merge.
- Next: Validate the counters separately in a post-merge regen.

## Links

- Upstream: `CONTINUITY.md`
- Downstream: PR to `main`
- Related: `ledgers/CONTINUITY_grounded-num-predict.md`

## Open questions (UNCONFIRMED)

- None blocking.

## Working set

- `spike/video-analysis/qwen_match_analysis.py`
- `spike/video-analysis/test_qwen_match_analysis.py`

## Notes

- 2026-09-02: Evidence supplied from basecamp regen 10: 8/56 grounded caption windows failed validation (7 invalid action labels, 1 malformed claim) after deterministic retries.
- 2026-09-02: Focused mocked test: `/Users/michaeljones/Projects/loanarmy/.loan/bin/python -m pytest spike/video-analysis/test_qwen_match_analysis.py -q` → 73 passed.
- 2026-09-02: Required full test: `/Users/michaeljones/Projects/loanarmy/.loan/bin/python -m pytest spike/video-analysis -q` → 131 passed.
- 2026-09-02: Bare `ruff check` → all checks passed; bare `ruff format --check` → both files already formatted.
