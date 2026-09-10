# Rule A implementation — 2026-09-11

- Scope: ball code and regenerated human ledger only; original labels immutable; no inference, training or push; one commit.
- Decision: every visible ball counts for detection; match_ball is a separate tracker flag.
- Done: schema v2 migration, persistent review state and ranked saved-box queue; build 9; scoring switches/provisional tables; all three review notes and throughput guard.
- Done: final worktree and staged-tree git-archive gates passed; implementation ready for the single local commit.
- Next: MJ confirms 188 frames; re-score after review. No new rule-A headline published.
- Master CONTINUITY.md left unchanged because it is outside the explicit write fence.

- Migrated 1,057 rows to `~/codex-runs/ball-human-truth-v2.jsonl`; original untouched.
- Original SHA256: `a0f51b42cb95e5327bf45fd353fd46f50495f99c096709b8836c7309ed2373ff`.
- V2 SHA256: `e535d84d27bc77c0c4d0c24abc8a1cc8653e4e1a005e5e6d494f9e6956e2debf`.
- Queue: 182 old no-ball + n21 s0–s5 = 188; 126 saved-box suggestions, 62 without; 0 confirmed. WASB point outputs cannot supply boxes.
- Kit: 1,105 cached frames, 688 normal suggestions retained; HTML/metadata/queue/migration audit copied to `~/codex-runs/ball-truth-review-build9/` (no JPEGs).
- Browser: isolated Chromium validates seed/no auto-save, Enter/click/N/M/arrows/J/K, normal defaults, v2 export/import with provenance, and legacy storage.
- Scorers: private saved-only smoke reports show `PROVISIONAL: 0 of 188 review frames confirmed` in all four table headers across the human and round-5 reports; no committed scores changed.
- Notes: TRAIN-2 qualifier plus TRAIN-1 tie values; capitalized integrity result; historical trainer same-run observed-hash caveat.
- Guard: checks YOLO, old RF and new RF checkpoints before any model/runtime import or wait; timing fixture unchanged.

- Final gates (worktree AND git archive): `.loan` 472 passed / 1 skipped (Playwright absent); `.venv-mj` 473 passed, including Chromium. Six existing Pillow deprecation warnings in each environment.
- Ruff check and format check: all 110 ball/bench Python files pass in worktree/archive; Python compile and JavaScript syntax checks pass.
- Ledger regeneration from the staged/committed aggregate fixtures is byte-for-byte in both environments (pytest), plus an explicit archive regeneration/cmp. No label, weight, detection, frame or crop added to git.
- Gate logs: `~/codex-runs/ball-any-ball-{worktree,archive}-{loan,rf}.log`; isolated real-kit screenshot: `~/codex-runs/ball-truth-review-build9-check.png`.
- Not done: MJ's review (0/188), laptop sync by orchestrator, final rule-A headline re-score, tracker use of match_ball. No push, training, model inference or throughput rerun performed.
