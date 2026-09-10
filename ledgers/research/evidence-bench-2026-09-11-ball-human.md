Human gate: no candidate passes. Proxy verdicts retire for this human-labelled sample.

tinyball-r1 held out: recall 46.09%, precision 67.60%, no-ball false/frame 0.201, 51.51 FPS.
Its two held-out on-ball clips: recall 54.10%, precision 78.57%, no-ball false/frame 0.130 (122 visible / 46 no-ball labels).
tinyball-r1-960 held out: recall 49.39%, precision 73.01%, no-ball false/frame 0.132, 37.90 FPS.
Its two held-out on-ball clips: recall 59.02%, precision 83.72%, no-ball false/frame 0.174 (122 visible / 46 no-ball labels).

| Candidate | On recall | On precision | No-ball false/10s | Median error px (all) | FPS | Real sample gate |
|---|---:|---:|---:|---:|---:|---|
| rf_full | 57.58% | 10.49% | 72.747 | 1.647 | 26.88 | FAIL |
| rf_2x2 | 83.18% | 9.13% | 118.352 | 1.233 | 8.33 | FAIL |
| rf_3x3 | 87.20% | 6.73% | 192.418 | 1.060 | 1.57 | FAIL |
| wasb | 3.55% | 10.56% | 5.385 | 3.437 | 37.90 | FAIL |
| wasb_2x2 | 18.25% | 11.41% | 22.857 | 2.150 | 12.90 | FAIL |
| tinyball-r1 | 75.36% | 86.89% | 3.736 | 1.802 | 51.51 | FAIL |
| tinyball-r1-960 | 77.73% | 90.36% | 2.418 | 1.921 | 37.90 | FAIL |

| Candidate / group | Labels / visible / no-ball | Recall | Precision | False/frame (no-ball) | Median error px | Box short side median / p95 px (n) |
|---|---:|---:|---:|---:|---:|---:|
| rf_full / all | 1057 / 875 / 182 | 62.51% | 10.55% | 3.637 | 1.647 | 13.086 / 46.339 (547) |
| rf_full / off_pitch | 213 / 160 / 53 | 80.00% | 15.63% | 1.981 | 1.172 | 27.516 / 47.983 (128) |
| rf_full / on_ball | 506 / 422 / 84 | 57.58% | 10.49% | 3.821 | 1.861 | 11.161 / 31.084 (243) |
| rf_full / other | 338 / 293 / 45 | 60.07% | 8.59% | 5.244 | 1.688 | 13.694 / 46.546 (176) |
| rf_2x2 / all | 1057 / 875 / 182 | 86.51% | 9.19% | 5.918 | 1.233 | 10.414 / 43.877 (757) |
| rf_2x2 / off_pitch | 213 / 160 / 53 | 96.25% | 13.65% | 1.887 | 0.601 | 19.156 / 47.177 (154) |
| rf_2x2 / on_ball | 506 / 422 / 84 | 83.18% | 9.13% | 6.619 | 1.430 | 9.623 / 27.235 (351) |
| rf_2x2 / other | 338 / 293 / 45 | 86.01% | 7.72% | 9.356 | 1.416 | 10.463 / 43.946 (252) |
| rf_3x3 / all | 1057 / 875 / 182 | 89.37% | 6.80% | 9.621 | 1.060 | 10.293 / 42.170 (782) |
| rf_3x3 / off_pitch | 213 / 160 / 53 | 93.75% | 8.68% | 6.472 | 0.000 | 18.214 / 46.931 (150) |
| rf_3x3 / on_ball | 506 / 422 / 84 | 87.20% | 6.73% | 10.833 | 1.492 | 9.489 / 26.012 (368) |
| rf_3x3 / other | 338 / 293 / 45 | 90.10% | 6.14% | 11.067 | 1.208 | 10.299 / 41.600 (264) |
| wasb / all | 1057 / 875 / 182 | 4.69% | 10.17% | 0.269 | 3.437 | — / — (0) |
| wasb / off_pitch | 213 / 160 / 53 | 3.75% | 6.59% | 0.264 | 10.261 | — / — (0) |
| wasb / on_ball | 506 / 422 / 84 | 3.55% | 10.56% | 0.262 | 3.437 | — / — (0) |
| wasb / other | 338 / 293 / 45 | 6.83% | 11.76% | 0.289 | 3.054 | — / — (0) |
| wasb_2x2 / all | 1057 / 875 / 182 | 15.77% | 11.38% | 1.143 | 2.150 | — / — (0) |
| wasb_2x2 / off_pitch | 213 / 160 / 53 | 6.25% | 6.54% | 0.717 | 5.800 | — / — (0) |
| wasb_2x2 / on_ball | 506 / 422 / 84 | 18.25% | 11.41% | 1.357 | 2.082 | — / — (0) |
| wasb_2x2 / other | 338 / 293 / 45 | 17.41% | 13.25% | 1.244 | 2.206 | — / — (0) |
| tinyball-r1 / all | 1057 / 875 / 182 | 59.09% | 76.71% | 0.187 | 1.802 | 17.358 / 18.760 (517) |
| tinyball-r1 / off_pitch | 213 / 160 / 53 | 36.25% | 61.70% | 0.208 | 1.904 | 17.675 / 19.270 (58) |
| tinyball-r1 / on_ball | 506 / 422 / 84 | 75.36% | 86.89% | 0.131 | 1.792 | 17.243 / 18.461 (318) |
| tinyball-r1 / other | 338 / 293 / 45 | 48.12% | 65.89% | 0.267 | 1.802 | 17.484 / 19.136 (141) |
| tinyball-r1-960 / all | 1057 / 875 / 182 | 61.71% | 81.08% | 0.121 | 1.921 | 17.765 / 19.010 (540) |
| tinyball-r1-960 / off_pitch | 213 / 160 / 53 | 42.50% | 67.33% | 0.094 | 1.917 | 17.944 / 19.424 (68) |
| tinyball-r1-960 / on_ball | 506 / 422 / 84 | 77.73% | 90.36% | 0.131 | 1.817 | 17.658 / 18.803 (328) |
| tinyball-r1-960 / other | 338 / 293 / 45 | 49.15% | 71.29% | 0.133 | 1.977 | 17.819 / 19.129 (144) |

Even optimistically filling all missing labels cannot rescue the frozen-schedule gate for: rf_full, rf_2x2, rf_3x3, wasb, wasb_2x2, tinyball-r1, tinyball-r1-960. Per-candidate bounds are recorded in JSON.

Human-associated RF 2x2 ball box short side: median 10.414 px / p95 43.877 px over 757 matched frames. On independently hand-clicked frames: 9.334 / 20.800 px over 420 matches. These are detector extents around confirmed ball centres, not human-measured boundaries.

Labels: 1057 validated; 875 visible / 182 no-ball; 352 accepted / 705 manual; 0 rejected. Accepted sources: {'rf_2x2': 87, 'rf_3x3': 258, 'wasb_2x2': 7}.
Target coverage: 506/540 on-ball + 99/100 off-pitch; 452 extra; 48 unlabelled. Exact covered/missing target keys are in the JSON ledger.

| Clip | Class | Labels | Visible | No-ball | Accepted | Manual | Missing |
|---|---|---:|---:|---:|---:|---:|---:|
| m04-n02-t3005-474114-478131 | other | 76 | 70 | 6 | 36 | 40 | 5 |
| m04-n03-t1406-157170-158922 | on_ball | 36 | 30 | 6 | 0 | 36 | 0 |
| m04-n03-t1406-385962-387137 | off_pitch | 24 | 0 | 24 | 0 | 24 | 0 |
| m04-n04-t3006-243433-247994 | on_ball | 90 | 86 | 4 | 0 | 90 | 2 |
| m04-n04-t3006-307417-310307 | other | 56 | 44 | 12 | 9 | 47 | 2 |
| m04-n05-t3007-284945-287898 | other | 59 | 50 | 9 | 27 | 32 | 1 |
| m04-n09-t1409-143096-143834 | off_pitch | 15 | 14 | 1 | 9 | 6 | 0 |
| m04-n09-t1409-297601-298865 | other | 26 | 23 | 3 | 7 | 19 | 0 |
| m04-n09-t1409-385922-386603 | off_pitch | 13 | 0 | 13 | 0 | 13 | 1 |
| m04-n10-t711-186553-188161 | other | 33 | 33 | 0 | 3 | 30 | 0 |
| m04-n12-t1411-237107-242145 | on_ball | 95 | 77 | 18 | 18 | 77 | 6 |
| m04-n12-t1411-679986-681985 | off_pitch | 40 | 40 | 0 | 40 | 0 | 0 |
| m04-n15-t3010-164698-170777 | on_ball | 117 | 107 | 10 | 36 | 81 | 5 |
| m04-n17-t717-253073-260377 | on_ball | 131 | 102 | 29 | 68 | 63 | 16 |
| m04-n17-t717-304624-307834 | other | 62 | 47 | 15 | 15 | 47 | 3 |
| m04-n17-t717-416826-418915 | on_ball | 37 | 20 | 17 | 4 | 33 | 5 |
| m04-n21-t3011-390297-390800 | off_pitch | 11 | 6 | 5 | 5 | 6 | 0 |
| m04-n22-t3012-070707-074371 | off_pitch | 72 | 71 | 1 | 38 | 34 | 2 |
| m04-n24-t3013-679939-681217 | other | 26 | 26 | 0 | 23 | 3 | 0 |
| m04-n25-t3014-530600-532465 | off_pitch | 38 | 29 | 9 | 14 | 24 | 0 |

| Track / group | Coverage within 20px | Longest correct s | >50px frames / visible | Wrong episodes |
|---|---:|---:|---:|---:|
| rf_full / all | 23.20% | 8.0 | 591/875 (67.54%) | 193 |
| rf_full / off_pitch | 38.12% | 8.0 | 75/160 (46.88%) | 27 |
| rf_full / on_ball | 18.96% | 5.0 | 310/422 (73.46%) | 109 |
| rf_full / other | 21.16% | 3.5 | 206/293 (70.31%) | 57 |
| rf_2x2 / all | 32.91% | 12.5 | 491/875 (56.11%) | 132 |
| rf_2x2 / off_pitch | 58.13% | 8.0 | 33/160 (20.62%) | 14 |
| rf_2x2 / on_ball | 26.54% | 7.5 | 277/422 (65.64%) | 81 |
| rf_2x2 / other | 28.33% | 12.5 | 181/293 (61.77%) | 37 |
| rf_3x3 / all | 27.20% | 12.5 | 557/875 (63.66%) | 122 |
| rf_3x3 / off_pitch | 46.25% | 7.5 | 55/160 (34.38%) | 14 |
| rf_3x3 / on_ball | 17.77% | 5.5 | 323/422 (76.54%) | 75 |
| rf_3x3 / other | 30.38% | 12.5 | 179/293 (61.09%) | 33 |
| wasb / all | 4.69% | 3.5 | 311/875 (35.54%) | 151 |
| wasb / off_pitch | 3.75% | 1.0 | 71/160 (44.38%) | 31 |
| wasb / on_ball | 3.55% | 1.0 | 104/422 (24.64%) | 63 |
| wasb / other | 6.83% | 3.5 | 136/293 (46.42%) | 57 |
| wasb_2x2 / all | 8.57% | 2.0 | 531/875 (60.69%) | 266 |
| wasb_2x2 / off_pitch | 4.38% | 1.0 | 78/160 (48.75%) | 41 |
| wasb_2x2 / on_ball | 9.24% | 1.5 | 284/422 (67.30%) | 133 |
| wasb_2x2 / other | 9.90% | 2.0 | 169/293 (57.68%) | 92 |
| tinyball-r1 / all | 51.20% | 24.5 | 77/875 (8.80%) | 54 |
| tinyball-r1 / off_pitch | 32.50% | 4.5 | 21/160 (13.12%) | 13 |
| tinyball-r1 / on_ball | 65.17% | 24.5 | 26/422 (6.16%) | 24 |
| tinyball-r1 / other | 41.30% | 3.5 | 30/293 (10.24%) | 17 |
| tinyball-r1-960 / all | 52.00% | 24.5 | 58/875 (6.63%) | 43 |
| tinyball-r1-960 / off_pitch | 34.38% | 6.5 | 9/160 (5.62%) | 6 |
| tinyball-r1-960 / on_ball | 65.88% | 24.5 | 19/422 (4.50%) | 18 |
| tinyball-r1-960 / other | 41.64% | 4.5 | 30/293 (10.24%) | 19 |

| Candidate | Accepted recall / precision / median error | Manual recall / precision / median error |
|---|---:|---:|
| rf_full | 78.12% / 14.75% / 0.952 px | 52.01% / 8.20% / 2.672 px |
| rf_2x2 | 95.74% / 13.23% / 0.321 px | 80.31% / 7.38% / 2.500 px |
| rf_3x3 | 97.73% / 9.43% / 0.000 px | 83.75% / 5.58% / 2.542 px |
| wasb | 5.11% / 11.18% / 3.610 px | 4.40% / 9.50% / 3.268 px |
| wasb_2x2 | 18.75% / 17.55% / 1.974 px | 13.77% / 8.60% / 2.561 px |
| tinyball-r1 | 48.58% / 81.43% / 1.129 px | 66.16% / 74.57% / 2.406 px |
| tinyball-r1-960 | 54.83% / 81.43% / 1.276 px | 66.35% / 80.89% / 2.362 px |

Training and execution:

| Model | MPS minutes | Epochs completed / requested | Tile input px | Held-out recall | Held-out precision | No-ball false/frame | FPS |
|---|---:|---:|---:|---:|---:|---:|---:|
| tinyball-r1 | 15.71 | 33 / 5 | 640 | 46.09% | 67.60% | 0.201 | 51.51 |
| tinyball-r1-960 | 15.80 | 18 / 20 | 960 | 49.39% | 73.01% | 0.132 | 37.90 |

Exact frozen clip split:

| Role | Clip |
|---|---|
| train | m04-n03-t1406-157170-158922 |
| train | m04-n04-t3006-243433-247994 |
| train | m04-n12-t1411-237107-242145 |
| train | m04-n15-t3010-164698-170777 |
| held_out | m04-n02-t3005-474114-478131 |
| held_out | m04-n03-t1406-385962-387137 |
| held_out | m04-n04-t3006-307417-310307 |
| held_out | m04-n05-t3007-284945-287898 |
| held_out | m04-n09-t1409-143096-143834 |
| held_out | m04-n09-t1409-297601-298865 |
| held_out | m04-n09-t1409-385922-386603 |
| held_out | m04-n10-t711-186553-188161 |
| held_out | m04-n12-t1411-679986-681985 |
| held_out | m04-n17-t717-253073-260377 |
| held_out | m04-n17-t717-304624-307834 |
| held_out | m04-n17-t717-416826-418915 |
| held_out | m04-n21-t3011-390297-390800 |
| held_out | m04-n22-t3012-070707-074371 |
| held_out | m04-n24-t3013-679939-681217 |
| held_out | m04-n25-t3014-530600-532465 |

Tile counts: {"negative_tiles": 3353, "positive_tiles": 875, "train": 1352, "val": 2876}.

Recorded commands (training uses the external MPS environment):

```sh
~/models/tinyball/.venv-mj/bin/python spike/video-analysis/ball/train_tiny_ball.py --human-jsonl ~/codex-runs/ball-human-truth.jsonl --out ~/models/tinyball/mj-r1
~/models/tinyball/.venv-mj/bin/python spike/video-analysis/ball/train_tiny_ball.py --human-jsonl ~/codex-runs/ball-human-truth.jsonl --out ~/models/tinyball/mj-r1-960 --init ~/models/tinyball/mj-r1/weights.pt --imgsz 960 --epochs 20
```

Decisions:

- No baseline inference; strict committed JSONL validator accepts all 1057 rows.
- All six on-ball clips are represented but 34 on-ball targets remain unknown; sample gate uses only human-labelled frames, not invented complete coverage.
- Retain fixed first four on-ball clips for training; all remaining 16 labelled clips held out. No per-frame split, pseudo labels or threshold search.
- Create external /Users/mjjones/models/tinyball/.venv-mj because prior ignored bench environment was not present in this worktree; pinned training recipe restored successfully.
- Master CONTINUITY.md read but not edited because the explicit task fences limit ledgers to this report pair.
- First run held-out recall 46.09% (<80%): run exactly one continuation from mj-r1/weights.pt at imgsz=960 and requested epochs=20 under the same 15-minute budget, same frozen 4/16 clip split. No third experiment or confidence threshold tuning.
- Archive preflight reproduced with Python 3.11.16 and NumPy 2.4.6; Python 3.12 failed the older exact-float retracking fixture even with identical NumPy. Training remains Python 3.12/MPS; human score and reports use Python 3.11.
- Variant selected by held-out recall (49.39% >46.09%) with precision as tie-breaker; two final trained checkpoints evaluated, no additional hyperparameter or threshold tuning.
- Training minutes measure model.train wall time including trainer final validation; decoding/dataset preparation and the all-frame prediction pass are excluded. Ultralytics time=0.25 hours expanded five requested epochs to 33 in run 1; variant requested 20 and recorded 18.
- New round-2 kit seeds exactly 1057 validated labels without touching MJ browser storage. Browser labels override seed values; explicit clears persist in a companion localStorage key. Suggestions never label automatically.

Kit refresh:

```json
{
  "best_model": "mj-r1-960",
  "browser_check": "PASS: all 1057 labels exact; no automatic saves; new browser labels and explicit clears survive reload; all-frame navigation reaches unlabelled frames. Isolated Chromium via Playwright 1.62.0.",
  "build_version": 5,
  "confirmed_seed_labels": 1057,
  "next_action": "Open ~/ball-truth-review/index.html, use Next unlabelled frame for the remaining 48; confirm/correct suggestions, use N only for no visible ball, leave uncertain frames unknown. Spot-check accepted suggestions for bias, then export a new JSONL.",
  "original_labels_sha256_unchanged": "a0f51b42cb95e5327bf45fd353fd46f50495f99c096709b8836c7309ed2373ff",
  "screenshot": "/Users/mjjones/codex-runs/ball-round2-kit-final.png",
  "storage_key_preserved": true,
  "suggestion_copies": [
    "/Users/mjjones/ball-truth-review/suggestions.jsonl",
    "/Users/mjjones/codex-runs/suggestions.jsonl",
    "/Users/mjjones/codex-runs/ball-human-round2-suggestions.jsonl"
  ],
  "suggestions": 606,
  "suggestions_sha256": "8012daaa298edb44f95d643d9a16ac85bd5c6b9c8b638080e710f48e0bccd045",
  "unlabelled": 48,
  "unlabelled_with_suggestion": 9,
  "unlabelled_without_suggestion": 39
}
```

Verification:

- Worktree: BENCH_REQUIRE_CV2=1 ~/Projects/loanarmy/.loan/bin/python -m pytest spike/video-analysis/bench spike/video-analysis/ball -q: 382 passed; six pre-existing Pillow deprecation warnings.
- Git archive export, no .git, media, labels, weights, cv2, torch or supervision: Python 3.11.16 / NumPy 2.4.6 pytest: 379 passed, three expected OpenCV skips; six pre-existing Pillow warnings.
- Ruff check and ruff format --check pass in worktree and archive for all 59 bench/ball Python files.
- Mypy 2.3.1 --check-untyped-defs --follow-imports=skip --ignore-missing-imports passes for all seven changed implementation/check modules.
- Human ledger JSON and Markdown regenerate byte-for-byte from committed aggregate and execution fixtures in worktree and archive.
- Isolated Chromium browser: exact 1057 seed labels preserved, zero auto-saves while browsing, newer labels and explicit clears survive reload, Next unlabelled frame works; final screenshot inspected.
- Best-model suggestion file and all three kit/codex-runs copies are byte-identical; original MJ JSONL SHA256 unchanged.
- Staged scope guard passes: only ball/** and the requested ledger pair; no JSONL labels or model weights staged. No baseline inference rerun. One local commit, no push.

Not done:

- No candidate passes the real gate; even optimistic completion of all 48 missing labels cannot rescue the frozen-schedule verdicts.
- MJ still has 48 unlabelled frames, including 34 on-ball targets and one off-pitch target; uncertain frames remain unknown.
- No third training experiment, no production integration, no push; labels, weights and datasets stay outside git.

Hashes, full execution provenance, per-clip scores and exact target coverage are retained in the JSON ledger and committed execution fixture.

Definitions and caveats:

- Human-sample PASS/FAIL is legitimate; proxy verdicts retire for these results. Gate: pooled visible-frame recall on six on-ball clips >=80%, and <=1 prediction per 10 seconds on ALL explicitly no-ball labels. Missing targets are excluded, never inferred; this is not certification of unlabelled frames or unseen matches.
- 20 source-pixel inclusive match radius; at most one nearest prediction matches each visible label, duplicates count against precision. Confidence 0.1 for all five saved baselines and trained models; no threshold search.
- Missing-label bounds are deliberately optimistic: assume every missing on-ball sample is visible and correctly detected for the recall upper bound; assume all 48 missing samples are no-ball with zero predictions for the false-rate lower bound. These separate best cases need not hold together. If either still fails, completing labels cannot rescue that candidate on the frozen schedule. Bounds never replace actual sample metrics.
- False-per-frame uses ONLY no-ball labels; false/10s = count *20 / no-ball frames at the frozen 2fps exposure. Sparse samples estimate an exposure-normalised rate, not continuous video event counts.
- Ball size is nearest matched detector box SHORT SIDE in native source pixels, median and nearest-rank p95. Human centres confirm association, not box boundaries or true physical diameter. Undetected balls have no size measurement, so this distribution is detection-conditioned. WASB points have no size. Trained point-box sizes are supervision-dependent and must not be treated as independent size measurements.
- Tracks rerun unchanged Kalman association without label guidance; score filtered points. Correct runs require successive scheduled samples within 20px in the same fragment; missing/no-ball/incorrect labels break runs. >50px wrong-object frames and contiguous wrong episodes are both counted; intervening unlabelled frames break episodes.
- Accepted/manual bias comparison is descriptive and confounded by frame difficulty and suggestion source, not an independent causal estimate. Manual includes explicit no-ball decisions.
- Baseline FPS reuses measured native decode+inference timings; model load, warmup, scoring and tracking excluded. Trained whole-corpus scores include training clips; held-out results are reported separately. All clips come from one match, limiting generalisation.
