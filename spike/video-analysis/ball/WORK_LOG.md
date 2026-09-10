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

## Build 10 safety fix round

- Now: F1–F4, F6, F7; one commit atop 5222f947; same fences; no push/training/inference. F5 explicitly deferred.
- Both immutable label hashes rechecked unchanged before work.
- Preserved build-8 copy: `~/codex-runs/ball-truth-review-build8/index.html` SHA256 `164ed33753991ef381f706d880936b9190056512add26c9e110e29a5c00e39a7`; build.json `19dc12428158a386ffb06fd4487e671e2bc634bff3a449c8945cea6a1b9fae00`.
- Decision: commit only the original 188 clip|time identities, without label values or pixel coordinates. Queue/provisional membership is independent of row-supplied review_frame flags.
- Decision: v2 storage has timestamped labels and deletion records in one atomic envelope; v1 is read once only. Corrupt storage disables editing until an exported recovery backup and validated, explicitly confirmed re-import.

- F1 browser evidence: exact preserved build-8 page + real original export opened beside build 10 in isolated Chromium. Migrated comparison: 0 missing, 0 extra, 0 changed rows; build-8 N rewrote only v1 and preserved both v2 confirmations. Legacy input unchanged by build 10.
- F1 read-only tests: malformed legacy/v2 storage, invalid v2 label, malformed legacy clear history; all edit keys/click/save blocked; raw recovery export retained the failed value; confirmed validated re-import recovered.
- F2 browser evidence: two pages, event notification, intentionally stale tab memory, distinct confirmations (2 retained), newer same-label update wins, and cross-tab clear remains cleared after another save.
- F3 browser evidence: v1 and v2-unconfirmed imports report counts; cancelling downgrade preserves row/timestamp; explicit confirmation permits replacement; unchanged import reports unchanged.
- F4: queue membership frozen as 188 keys plus pending rows; both non-queue-confirmation and extra-pending-row banner bypasses tested. Value diff CLI ignores formatting; any new input is compared with immutable baseline before regeneration. No fresh laptop export supplied this round.
- F6 browser evidence: C preserved actual n21 s1 point and rf_2x2 acceptance provenance while confirming NOT match; synthetic tests also verify timestamp and pending flags.
- F7: versioned builder rejects shared/existing directories; build 10 points to shared frame files. Preserved build-8 copy and current shared kit index/build hashes remained unchanged.
- Build: `~/ball-truth-review-build10/`; five sync files copied byte-identically to `~/codex-runs/ball-truth-review-build10/`; no JPEGs copied.
- New seed only: `~/codex-runs/ball-human-truth-v2-build10.jsonl`, SHA256 `d74900f6b25b86b7017399966514ae263422e47a3fc7d50d7862ef7a36cea491`. All 1,057 prior v2 rows identical except new `updated_at:0`; original two label hashes unchanged. Queue exactly unchanged: 188 entries / 126 suggestions / 0 confirmed; normal suggestions 688.
- Private execution evidence: `~/codex-runs/ball-build10-real-build8-check.json`, `ball-build10-protected-sha.json`, `ball-build10-generation.log`, `ball-build10-browser.png`. No local browser test uses MJ's profile or writes source labels.
- Done: F1–F4/F6/F7 implementation and private build 10; final worktree/archive gates passed.

- Worktree gates: `.loan` 475 passed / 10 skipped (Playwright unavailable); `.venv-mj` 485 passed including all 10 browser checks. Six pre-existing Pillow deprecation warnings per environment.
- Ledger regeneration remains byte-identical with no committed ledger changes.

- Archive gates: `.loan` 475 passed / 10 skipped (browser dependencies absent); `.venv-mj` 485 passed including every Chromium check. Ruff check/format: all 113 Python files pass. Python compile and all three JavaScript syntax checks pass.
- Real saved-label scoring of the new build-10 seed: 188 pending rows, `PROVISIONAL: 0 of 188 review frames confirmed` in all three human-score table headers. No headline or timing changes.
- Gate logs: `~/codex-runs/ball-build10-{worktree,archive}-{loan,rf}.log`; archive path recorded in `ball-build10-archive-path.txt`. Both ledgers regenerate byte-for-byte from committed fixtures.
- Not done: F5 multi-ball schema (explicitly pending MJ), fresh laptop export comparison when supplied, laptop sync, MJ review and final rule-A headline re-score. No push, training, model inference or throughput rerun.
