# Task Ledger: Grounded caption enum prompt

Parent: `CONTINUITY.md`
Root: `CONTINUITY.md`
Related: `ledgers/CONTINUITY_grounded-caption-lenient-enums.md`
Owner: `/root`

## Goal

- Stop grounded caption and player-read prompts from presenting pipe-joined enum alternatives as example values.
- Recover an invalid pipe-joined action label only when exactly one token is a valid action type.
- Preserve legacy prompts and validators exactly.

## Constraints / Assumptions

- Work only in this worktree on `fix/grounded-caption-enum-prompt`.
- Change only the two requested spike files plus this ledger and at most three lines in `CONTINUITY.md`.
- Use mocked tests only; make no basecamp or Ollama calls.
- Commit, push, and open an unmerged PR to `main` with the exact requested subject.

## Key decisions

- Derive all grounded enum instruction lists from module constants so prompt text and validators share one vocabulary.
- Count every invalid action coercion and separately count only deterministic single-choice recoveries.

## State

- Done: Replaced grounded enum example values with placeholders, retained constant-derived vocabulary sentences, made single-choice recovery set-based, excluded `unclear` from the recovery counter, and added regressions; all required checks pass.
- Now: PR #970 open; review fix round applied; awaiting merge.
- Next: next regen: compare label distributions (share of unclear/carry/central/medium/clear) against regen 11 to catch any example/echo bias.

## Links

- Upstream: `CONTINUITY.md`
- Downstream: PR to `main`
- Related: `ledgers/CONTINUITY_grounded-caption-lenient-enums.md`

## Open questions (UNCONFIRMED)

- None blocking.

## Working set

- `spike/video-analysis/qwen_match_analysis.py`
- `spike/video-analysis/test_qwen_match_analysis.py`

## Notes

- 2026-09-02: Regen 11 reported 7/56 grounded window action labels coerced; all raw labels were pipe-joined prompt alternatives or multi-choice subsets.
- 2026-09-02: Focused regression selection → 10 passed.
- 2026-09-02: `/Users/michaeljones/Projects/loanarmy/.loan/bin/python -m pytest spike/video-analysis -q` → 136 passed.
- 2026-09-02: Bare `ruff check` → all checks passed; bare `ruff format --check` → both files already formatted; `git diff --check` clean.
- 2026-09-02 review fix: Focused prompt/recovery/snapshot selection → 9 passed.
- 2026-09-02 review fix: `/Users/michaeljones/Projects/loanarmy/.loan/bin/python -m pytest spike/video-analysis -q` → 138 passed.
- 2026-09-02 review fix: Bare `ruff check` → all checks passed; bare `ruff format --check` → both files already formatted; `git diff --check` clean.
