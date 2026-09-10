# Local ball bench: MJ human truth

The current click kit is **build 11**, in its own versioned directory. See the
[build-11 fixes](#build-11--confirmed-decisions-and-merge-conflicts) before labelling;
builds 9 and 10 are preserved, with their historical instructions below.

MJ's September 11 product decision: **RF-DETR (Apache-2.0)** is the product model.
**ultralytics is bench-only and must not enter the serving path; the product model
is RF-DETR (Apache-2.0).** The YOLO trainer and saved results remain comparison
evidence for this round. The generated ledger leads with the corrected round-5
fair comparison: thresholds selected on TRAIN at 1 and 2 false boxes/10s.
A shared confidence 0.1 is not comparable across model families. See the
[round-5 workflow](#round-5-fair-calibration-augmentation-and-replay) below.
Rounds 1–4 retain historical results and their superseded selection statements.

## Historical round 4: trainer swap

Round 4 uses `train_tiny_ball_rfdetr.py`, with no Ultralytics import or dependency.
`requirements-rfdetr.txt` pins the executed RF environment; install it into a
separate external venv rather than installing the bench-only YOLO requirements
into a serving environment. The documented `.venv-bench` was absent on resumption,
so execution restored `rfdetr[train]==1.7.1` in the existing external training venv.

Both RF-DETR Nano fits are frozen in `fixtures/round4_execution.json`: 640 px from
COCO, then a 960 px continuation from a's **final** checkpoint, fresh optimizer.
The floor is 18.6804351807 native px in both; no floor sweep. Every target uses
`clamp(TRAIN-only affine(image_y), floor, 48)`, superseding the direct matched-size
override from round 3. Four native 960×540 crops are padded below to 960×960,
then resized uniformly. No source aspect distortion and no held-out training data.

The RF model/criterion and official layer-wise AdamW groups run in an explicit
PyTorch loop: TRAIN-loss patience only, no validation loader or EMA, final-step
export including a time-ended partial epoch. This avoids RF-DETR 1.7.1's obsolete
callback dict (discarded by its Lightning facade) and its validation-best export.
Each fit has a 29-minute training budget, leaving export margin under 30 minutes.
All fits finish before either held-out saved pass; neither thresholds nor recipes
are changed using the new held-out scores. Model selection then intentionally
uses held-out top-1 recall under the ≤2 false/10s ceiling and is optimistic.
An improvement must beat r2-b's 68.03% held-out top-1 without exceeding its
1.67 false/10s. Only such an RF win permits a kit refresh.

```sh
# New output directories required; at most these two fits.
~/models/tinyball/.venv-mj/bin/python spike/video-analysis/ball/run_round4.py
~/models/tinyball/.venv-mj/bin/python spike/video-analysis/ball/evaluate_round4.py
# Saved scoring, independent size buckets, null controls and unchanged Kalman:
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/review_round4.py
# Byte-for-byte ledgers from aggregate fixtures, no labels/models/source needed:
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/build_human_report.py
```

`fixtures/round4_scored_output.json.gz` contains scored aggregates, not click
coordinates. It retains All / held-out metrics and manual-only recall. Manual
frames were the harder cases MJ clicked where no suggestion existed; lower
manual-only recall does not by itself establish model bias. Fresh labelled club
footage is required for a clean test. Better footage is helpful but has not been
demonstrated to solve the detection and false-rate gate.

## Historical rounds 1–3

The September 11 human report supersedes proxy verdicts for the labelled sample:
`ledgers/research/evidence-bench-2026-09-11-ball-human.{json,md}`. All five saved
baselines and all trained models fail the **top-1** real gate at confidence 0.1.
Nearest-of-N recall is an oracle over multiple guesses, not pipeline recall.
Current best is round-2 b under the explicitly evaluation-based selection rule;
the two scale-aware repeats improve large-ball hits but lose small-ball recall.

MJ's 1,057 validated labels cover 506/540 on-ball targets and 99/100 off-pitch
targets, plus 452 extra frames. There are 48 unlabelled frames. Missing frames
remain unknown; a sample PASS/FAIL is not certification of missing labels.
The source JSONL and all training outputs remain outside git.

`score_from_saved.py` uses **20 source pixels** and the highest-confidence box
for top-1 recall. Nearest-of-N is separately labelled oracle recall, with duplicate
predictions penalising oracle precision. The real gate requires top-1 on-ball
visible-frame recall >=80% and <=1 prediction per
10 seconds on **all explicitly no-ball frames** (0.5 seconds exposure per sample).
Trained headline metrics use held-out clips only, with all-clip (including training)
metrics explicitly separate. It reports on-ball/off-pitch/other groups,
pooled/manual-only recall, accepted-source bias, matched
box short-side distributions, and re-tracked Kalman points versus human centres.
Human clicks confirm association, not detector box boundaries; matched sizes are
not independently measured ball diameters. Trained point-box sizes are especially
unsuitable as independent ball-size evidence.

Round 2 uses the committed deterministic **14 train / 6 evaluation** split:
631 visible training labels / 244 evaluation labels, including two on-ball and
two off-pitch clips in evaluation. Every evaluation estimate is labelled
**held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate)**.
The user explicitly accepted that exposure. These 20 clips cannot be a clean test
set again; new labelled club footage is the real test. All-clip and six-clip
numbers are paired throughout the generated ledger, including rescored round-1
models. The original four-train/16-evaluation round-1 records remain in JSON.

`fixtures/round2_execution.json` freezes the split and four-fit protocol. Fits a/b
use 2×2@960 (COCO / round-1 weights), c uses 2×2@1280 for 33% more effective ball
pixels within a 23-minute fit budget, and d continues the minimum-TRAIN-loss a–c
checkpoint. Historically, early stopping, checkpoint selection and the round-2
kit model used **TRAIN loss only**. Round 3 supersedes model selection with the
user-authorized held-out top-1/false-rate rule; checkpoint selection remains TRAIN-only. Held-out images never enter fitting or box-size estimation;
a custom validator reads training loss without evaluating images. All four fits
finish and selection is frozen before any round-2 saved inference pass. AdamW
settings are pinned to the optimizer used in round 1. Batch, fit budgets, actual
epochs/minutes, hashes and MPS nondeterminism caveats are recorded in the ledger.

Build version **7**, with 636 saved suggestions from current-best `mj-r2-b`, accepts `--human-jsonl` to seed MJ's validated export while
preserving the existing localStorage key and giving newer browser labels priority.
The new **Next unlabelled frame** button visits optional as well as target frames.
Suggestions remain unconfirmed and cannot overwrite labels.

```sh
PY=~/Projects/loanarmy/.loan/bin/python
$PY spike/video-analysis/ball/score_from_saved.py \
  --human-jsonl ~/codex-runs/ball-human-truth.jsonl \
  --extra-detections tinyball-r1=$HOME/models/tinyball/mj-r1/detections.json
# The four prescribed fits (outputs/logs must be new; preserves existing runs):
~/models/tinyball/.venv-mj/bin/python spike/video-analysis/ball/run_round2.py
# Only after all four fits and TRAIN-only selection are frozen:
~/models/tinyball/.venv-mj/bin/python spike/video-analysis/ball/evaluate_round2.py
~/models/tinyball/.venv-mj/bin/python spike/video-analysis/ball/round2_people.py
# Aggregate saved detections, tracks and predeclared error buckets (no inference):
$PY spike/video-analysis/ball/round2_analysis.py
# Reproduce committed human ledgers without labels, videos or models:
$PY spike/video-analysis/ball/build_human_report.py
```

The aggregate human measurement fixture contains metrics and target coverage keys,
not click coordinates or label rows. For archive tests, use Python 3.11 and
NumPy 2.4.6 to match the original strict floating-point retracking fixture;
Python 3.12 produces small differences in the historical aggregate fixture. `fixtures/human_execution.json` records the
round-1 training, refresh and verification evidence. Round-2 execution and aggregate
measurement fixtures add paired scoring, error buckets and the conditional doubled-ball-pixel
projection without embedding label coordinates. `build_human_report.py --capture`
freezes a completed score JSON. Tests regenerate both ledgers byte-for-byte.

## Historical proxy bench and recipe background

**Historical proxy verdicts are `UNMEASURABLE (proxy)`.** The numbers measure detector
self-agreement, candidate box/point counts, throughput and unverified trajectories.
They do not measure recall against the real match ball. The RF full/2x2 voters
share weights; 387/408 on-ball and 143/155 off-pitch agreement-positive frames are
RF-pair-only. The ledger decomposes pairs per clip and class.

The marked player is off pitch in seven clips; **the match ball is usually still
in frame**. `boxes_per_10s_offpitch` is a count of candidate outputs per ten seconds,
not a false-ball rate. WASB emits points rather than boxes. RF near-player rates
at 0.5 overlap (on-ball 6.8–12.9%, off-pitch 11.7–12.6%): **no separation**.

## Human loop

**Click → train → pre-fill → confirm → re-score.** Each export preserves manual
versus suggestion-accepted provenance. Nothing becomes truth until MJ acts.

1. Open `~/ball-truth-review/index.html`. Six on-ball clips appear first. A hollow
   cyan ring and source name show an optional suggestion. **Enter/Space accepts**,
   a click overrides, **N** marks no ball, **←/→** change frames, **J/K** change clips.
   Use **Next unlabelled target** to skip optional frames. Suggestions never auto-save.
2. Label all **540 on-ball frames plus 100 off-pitch samples**. The off-pitch plan
   reserves at least **10 per clip**, then distributes the remaining slots equally
   with clip-length caps and samples evenly through each window. It retains the
   **640 target**. Exact lists and the seven clip
   IDs are in `build.json` and `human_label_plan` in the measurement fixture.
   Progress counts labelled target frames, excluding optional frames. The old
   localStorage key stays compatible. Export JSONL regularly as your backup.
3. Train from the export, then load the model's suggestions into the same kit.
   Existing confirmed labels survive rebuilding; suggestions do not replace them.
   Confirm or correct new suggestions and export again before re-scoring.

First-pass planning estimate: **32–64 minutes** at 3–6 seconds per target frame,
plus breaks/uncertainty. This is an estimate, not measured annotation speed.
Accepting a correct suggestion takes one keypress; finding a tiny ball may take
longer. Leave uncertain frames unlabelled; do not mark them invisible.

```sh
# Setup (already installed on basecamp). Ultralytics stays bench-only.
uv pip install --python spike/video-analysis/ball/.venv-bench/bin/python \
  -r spike/video-analysis/ball/requirements-train.txt

# After MJ exports the kit to ~/Downloads/ball-human-truth.jsonl:
spike/video-analysis/ball/.venv-bench/bin/python spike/video-analysis/ball/train_tiny_ball.py \
  --human-jsonl ~/Downloads/ball-human-truth.jsonl --out ~/models/tinyball/mj-r1

# Pre-fill again, retaining existing localStorage labels and image files:
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/ball_truth_kit.py \
  --suggestions ~/models/tinyball/mj-r1/suggestions.jsonl

# MJ confirms/corrects and exports again, then score all saved candidates:
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/score_from_saved.py \
  --human-jsonl ~/Downloads/ball-human-truth.jsonl \
  --extra-detections tinyball-r1=$HOME/models/tinyball/mj-r1/detections.json

# A subsequent training run can start from the earlier weights:
spike/video-analysis/ball/.venv-bench/bin/python spike/video-analysis/ball/train_tiny_ball.py \
  --human-jsonl ~/Downloads/ball-human-truth.jsonl --out ~/models/tinyball/mj-r2 \
  --init ~/models/tinyball/mj-r1/weights.pt
```

Use a fresh output directory per run. Weights, datasets and labels stay outside
git. `score_from_saved.py` needs no torch, cv2, video, model or inference.
`--extra-detections name=path` can repeat; it validates source hash, frozen set,
all 20 clips, all 1,105 timestamps/frame indices, geometry and timings.
Extras declaring `synthetic_smoke: true` are refused unless `--allow-synthetic`
is explicitly supplied. That diagnostic override badges every synthetic table
row **SYNTHETIC**, including per-clip rows; JSON rows retain the synthetic flag.
Synthetic smoke scores remain plumbing diagnostics, never ball accuracy results.
`compare_ball.py --human-jsonl` remains available for the original candidates.

The first 1,041 suggestions come solely from saved detections: **683 rf_3x3,
242 rf_2x2, 116 wasb_2x2**. Choose the highest confidence observation on one of
those candidates' longest re-tracked fragments at that timestamp; otherwise use
the top rf_3x3 box at >=0.3, or no suggestion. WASB supplies a point.
**Ranking is unchanged and unnormalised:** it compares RF detection confidence
with WASB's maximum sigmoid heatmap value within its selected component, on
different scales. Equal raw scores
break by source name, so WASB wins ties over RF; that preference has no meaning
on a calibrated common scale and might reverse after calibration. This is a
suggestion-display heuristic only, not evidence of accuracy or ball identity.

Regenerate and make an auditable copy beside the synced build metadata:

```sh
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/human_loop.py \
  --copy-to ~/codex-runs/suggestions.jsonl
```

The copy is byte-identical to `~/ball-truth-review/suggestions.jsonl`; source
counts can be checked without opening the kit. `--copy-to` takes a file path.
Then rebuild with
`ball_truth_kit.py --suggestions ~/ball-truth-review/suggestions.jsonl`.
Build version 4 is synced to `~/codex-runs/ball-truth-review-build.json`.

The original JSONL fields remain `{clip,t,x,y,visible}`: source pixels, absolute
seconds and null coordinates when invisible. New labels add `source_accepted`;
accepted suggestions also keep `accepted_source` and `accepted_score`. Old
five-field exports still import. Suggestion files use `{clip,t,x,y,score,source}`
and cannot be imported as truth. Re-scoring reports accepted-source counts.

**Training recipe:** YOLO11-nano via Ultralytics 8.4.146, **AGPL-3.0**, used only
in this local bench. [Upstream licence](https://github.com/ultralytics/ultralytics/blob/main/LICENSE)
and [MPS training documentation](https://docs.ultralytics.com/modes/train/).
No production integration or deployment is part of this work.

Each native 1920x1080 frame becomes four non-overlapping 960x540 crops. YOLO
letterboxes each to 640x640 (640x360 image content). A click belongs to exactly
one tile; its point-box is clipped at the tile boundary. Box side at model scale
is `max(12, 2 * median matched RF size * 640/960)`, using only saved RF 2x2 boxes
within 20 source pixels of **training** clicks. No size matches → 12 model pixels
(18 source pixels). Sizes remain detector estimates. Non-click tiles and explicit
no-ball frames supply negatives; unlabelled frames never do. `--pseudo` alone
adds saved RF 0.1 boxes within 20 source pixels of a training click, with NMS.
There is no pseudo-label propagation to held-out clips or unclicked frames.

The fixed training split is by complete clip, **never by frame**; all additional
labelled clips are held out for evaluation:

| Role | On-ball clips |
|---|---|
| Train | n03-157170, n04-243433, n12-237107, n15 |
| Held out | n17-253073, n17-416826 |

All seven off-pitch clips are reserved for scoring. The run records full IDs.
Normal runs use the last checkpoint; held-out labels do not select weights.
Per-epoch validation is disabled; Ultralytics may validate once at the end.
Default training requests five epochs with MPS and a 15-minute trainer budget;
Ultralytics' time budget may adjust epoch count and finishes at epoch boundaries.
Completed round-1/2/3 training times are recorded in the human ledger. Use `--epochs`
to set the requested count. `--init` lets later clicks improve the preceding model.

Outputs: `weights.pt`, `dataset.json`, `dataset/`, `metrics.json`,
`detections.json`, `suggestions.jsonl`, and Ultralytics `fit/` checkpoints.
Metrics report held-out **20-source-pixel** recall/precision, unmatched predictions
per labelled off-pitch frame and FPS including decode. At most one prediction
matches each visible label; duplicates count as unmatched. A single model pass
covers all 1,105 scheduled frames. Suggestions contain at most one point per
frame with an output >=0.1; missing predictions produce no suggestion, never an
invented point. The saved detection file includes those empty frames.

Historical `compare_ball.py` retains its **40-pixel** diagnostic matching rule.
The human `score_from_saved.py` uses **20 pixels** for every candidate. Scores that include training clips are in-sample; consult the separate
20-pixel held-out metrics for generalisation. Model-assisted confirmation also
needs careful review; acceptance provenance is available for audits.

The following gate is retired; the current top-1 human-sample gate is defined above.
The historical human gate required all 540 on-ball labels and >=100 off-pitch
labels: visible-ball recall >=80%, unmatched predictions <=1/10 s. A visible ball
on off-pitch frames permits one match; every other prediction is unmatched.
Exposure is 0.5 s per labelled frame. Partial labels give metrics with the gate
withheld. **Every proxy verdict stays UNMEASURABLE (proxy).**

Smoke command (already completed; do not rerun for scoring):

```sh
spike/video-analysis/ball/.venv-bench/bin/python spike/video-analysis/ball/smoke_tiny_ball.py \
  --out ~/models/tinyball/a-new-SYNTHETIC-smoke
```

The actual `~/models/tinyball/round3-synthetic-smoke` used 36 synthetic proxy labels
from one on-ball clip (144 tiles), two epochs on MPS: **27.21 s training, 50.59 s
total**. Its trainer health check reuses that clip without splitting frames; no
independent held-out labels exist, and those scores are null. Weights, metrics
and all-frame saved detections were produced. **Zero predictions reached 0.1**,
so its `suggestions.jsonl` is valid but empty. This proves pipeline execution,
not detection quality or a useful trained pre-fill. Synthetic labels and model
outputs are not committed or loaded into MJ's kit. No smoke accuracy numbers are
reported as ball results.

## Runner device and parity preflight

`run_ball.py --device cpu` now forwards CPU to every RF candidate, including
tiled variants; `--device mps` forwards MPS. A loader/device mismatch is rejected
with the requested and actual devices.

`--parity-frames 5` plans five distinct samples before model loading. It spaces
selected clips across the available `--clips` list, balances the sample counts,
and spaces frames within each clip. Three clips work (2/2/1 samples); fewer than
five available frames fail preflight. MPS must be available for the comparison.
The parity check restores the originally selected device, including on errors.
Round 4 tested these paths with stub models only; no inference was rerun.

## Recorded inference and resolution

All 20 windows use the hash-verified 1920x1080 native source at 2 fps, 1,105 samples.
Every intervening native frame is decoded inside clip timing. WASB stacks the
three consecutive native frames ending at each sampled frame; the first window
frame is replicated at the boundary. Model load/warmup, parity, serialization,
tracking and rendering are excluded from reported inference FPS.

RF-DETR medium **anisotropically squashes** every frame/tile to 576x576. For a
hypothetical 24x24 source-pixel ball (not measured ball truth):

| Candidate | Source input/tile | Model input | Effective reference ball px |
|---|---|---|---|
| RF full | 1920x1080 | 576x576 | 7.2x12.8 |
| RF 2x2 | 1010x590 | 576x576 | 13.7x23.4 |
| RF 3x3 | 707x427 | 576x576 | 19.6x32.4 |
| WASB full | 1920x1080 | 512x288 | 6.4x6.4 |
| WASB 2x2 | 960x540 | 512x288 | 12.8x12.8 |

RF uses production `load_detector`/`detect_batch`/sports-ball filtering (COCO 37)
and Supervision InferenceSlicer with 100–101 px overlaps and 0.5 IoU NMS.
`run_ball.py --resolution <side>` now supports a different RF input resolution;
**no RF inference or resolution-override inference was run in fix round 2**.

Round 2 added the full pass for `wasb_2x2`, on MPS, with four non-overlapping 960x540
crops mapped to 512x288. Each tile gets its own consecutive native-frame stack,
ImageNet normalization, last-channel sigmoid, weighted components and peak-mass
selection. Points within 40 source pixels merge by descending heatmap mass.
No bounding box or ball diameter is fabricated from a heatmap. Tiling can split
a ball at a seam. Original full-frame WASB outputs are retained, not rerun.
Five additional parity samples compare MPS/CPU FP32 heatmaps for all four tiles
and all three channels; raw per-tile differences and tolerance are in run metadata.
Parity establishes numerical agreement only, not detection accuracy.

## Re-tracking the saved RF 0.1 boxes

The Kalman association cap is **30 m/s x elapsed seconds x 20 px/metre**: 300 px
in 0.5 seconds, 600 px across a one-second gap. The old 60 px per sampled frame
was only 6 m/s. A synthetic kicked-ball segment plus gap demonstrates the repair.
Pixels/metre is still an **uncalibrated convention**, not actual pitch geometry.

Max observation gap remains 1.0 s. Continuity is the longest fragment duration
(including a 0.5 s sample bin, bridging accepted short gaps, excluding trailing
predictions) divided by clip length. Overall continuity is weighted by duration;
fragment counts sum; longest track is the maximum across clips.

The ledger reports every on-ball clip plus grouped results. “Single speed-bounded
hypothesis” requires exactly one fragment covering >=80% of the clip. No RF
candidate achieves that on these six clips. Even a passing trajectory heuristic
would not identify the ball: false boxes, camera movement and identity switches
can satisfy the cap. Three track-overlay contact sheets show first/middle/last
points of each RF candidate's longest n12 fragment, with raw and Kalman positions.

## Reproduce and verify

The original detector environment is `ball/.venv-bench` (pinned requirements in
`requirements.txt`); upstream MIT WASB is ignored under `third_party/WASB-SBDT`,
revision `923462cacdeb3353b84ddebdedb3f4b7a8553b0f`. Its soccer weights stay at
`~/models/wasb/wasb_soccer_best.pth.tar`; URL and SHA256 are in the execution fixture.
Do not rerun inference just to regenerate or label-score reports.

```sh
# Ordinary regeneration: saved numeric fixtures only.
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/compare_ball.py

# Append the already-recorded WASB tiled run and recompute saved RF tracks.
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/compare_ball.py --update-saved
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/track_overlays.py

# Worktree gate with cv2 required for existing bench rendering checks.
BENCH_REQUIRE_CV2=1 ~/Projects/loanarmy/.loan/bin/python -m pytest \
  spike/video-analysis/bench spike/video-analysis/ball -q
ruff check spike/video-analysis/bench spike/video-analysis/ball
ruff format --check spike/video-analysis/bench spike/video-analysis/ball
```

The WASB tiled inference command used in round 2 (already completed) was:

```sh
spike/video-analysis/ball/.venv-bench/bin/python spike/video-analysis/ball/run_ball.py \
  --candidate wasb_2x2 --parity-frames 5
```

`fixtures/measurements.json.gz` is deterministic gzip of sorted JSON. `gzip -dc`
exposes the original unchanged four candidate outputs, the new WASB tiled outputs,
re-tracked RF points, human-label plan, provenance and timings. Execution decisions
come from a committed fixture. Ordinary regeneration is byte-for-byte and checks
that saved re-tracks agree with the current tracker. No ball human labels exist
in these fixtures.

Archive-export gates also run with a minimal Python environment **without cv2**,
torch or supervision, with `BENCH_REQUIRE_CV2` unset. CV2-dependent tests use
`pytest.importorskip`; all saved-score, tracking, schema and proxy tests still run.
The export has no `.git`, model weights, local media, or third-party checkout.

## Round-3 human review and scale-aware fits

The human gate now uses **highest-confidence top-1 recall**, not nearest-of-N.
`recall` is retained in JSON only as a historical alias of `oracle_recall`;
`top1_recall` governs PASS/FAIL. Trained headline rows use held-out-only metrics,
with explicit training-inclusive columns. Headline boxes/frame divides by visible
on-ball frames (the reviewer’s denominator); `boxes_per_frame` in JSON instead
divides by all labelled frames and `boxes_per_visible_frame` records the former.
Manual-only recall and visible-labelled track-point precision/rates are reported.

`fixtures/human_measurements.json.gz` and `round2_measurements.json.gz` are
historical filenames for **scored aggregate output**, not raw measurements or
human labels. `round3_scored_output.json.gz` contains the revised paired scores,
100-repeat seeded matching controls, path-credit sensitivity and error buckets.
All three exclude human centres and per-label outcome records. The execution
fixtures preserve historical decisions; round3 explicitly supersedes model
selection. The original 4/16 split and common 14/6 split are kept separate.

```sh
# Regenerate both committed ledgers, without private files or inference.
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/build_human_report.py

# Re-score existing local saved passes, including the two completed scale runs.
# No inference; requires MJ's local JSONL and saved local artifacts.
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/review_round3.py
```

The two authorized scale fits are scripted in `run_round3.py`, followed once by
`evaluate_round3.py`. Both refuse to overwrite previous training/prediction
artifacts. Do not rerun them to regenerate reports. The recipes repeat round2 a/b
at 2×2@960, with exactly the same budgets, initial checkpoints, optimizer and
augmentation. `--scale-targets --train-loss-only` replaces the fixed square side
with each click's nearest matched TRAIN RF 2×2 box short side; an affine size-vs-y
fit supplies missing sizes, clipped to [6,48] native px. Fit coefficients, R²,
matching population and fallback count are recorded. No held-out sizes enter
fitting. Detector extents remain estimates, not human-drawn diameters.

Round3 selects the highest H on-ball top-1 recall among round2 a–d and round3 a–b
with H no-ball false/10s ≤2. The real gate still requires ≤1. This intentionally
uses held-out data and produces an optimistic selected estimate; the earlier
640-vs-960 aggregate choice already exposed these clips. Fresh labelled club
footage is the true holdout. A 4K/follow-cam export can improve ball pixels but is
not, by itself, a demonstrated solution to the remaining errors.

Accepted labels already require `accepted_source` and `accepted_score` in Python
and browser validators. Accept preserves the model source; a hand click clears
acceptance provenance. Keep those fields in future JSONL exports so model-seeded
labels can be separated from manual labels during evaluation.

### Round 5: fair calibration, augmentation and replay

The corrected round-5 protocol is `fixtures/round5_execution.json`. The two new
fits are RF-DETR Nano@960 from COCO, first with native-content zoom/translation
and step LR decay, then with identical settings plus TRAIN-only hard-negative
replay. `train_round5.py` uses the existing verified round-4 TRAIN tile cache;
no validation clips enter training, mining or stopping. `round5_data.py` clips
transformed targets to actual image content and preserves positive annotations
on replayed tiles. Every original tile appears once per complete epoch; each
mined tile appears once more. The final checkpoint is the product candidate.

`round5_inference.py` saves fresh detections to confidence 0.01. The YOLO adapter
is bench-only. Before runtime/model loading or output creation, the selected
weights must match the independent fit summary's final SHA256. Diagnostics require
`--checkpoint-epoch N` and match that declared checkpoint hash instead; the final
declaration is never overwritten. `run_round5.py` supplies this flag for diagnostics.
`checkpoint_provenance.py` also binds every capture/finish envelope (historical
baselines included) to a registered candidate's fit summary. Finish preflights all
finals and declared diagnostics before writing any artifact. To repeat the private
six-pass disk audit, call `audit_saved_passes(Path.home() / "models/tinyball")`
from that module; the aggregate audit is in the ledger execution block.
`fair_protocol.py` chooses thresholds using TRAIN no-ball frames
only, at nominal 1 and 2 false boxes/10s, with tied scores handled atomically.
Held-out curves and exact frame-level McNemar comparisons are diagnostic only.
The six evaluation clips are **recipe-selected on these clips**, not a clean
test set: all clips share a match, and held-out on-ball clips share a player with
training. A new match from a different venue/day is required for a product claim.

`run_round5.py` finishes the second fit only after the first fit completes, then
runs final and saved-checkpoint inference. `finish_round5.py` captures metrics,
uses final-checkpoint H metrics at TRAIN-chosen thresholds to choose an RF-only kit source (optimistic selection), and prepares suggestions.
`throughput_round5.py` benchmarks three interleaved repeats on the same TRAIN
clips, including decode and batched four-tile inference, after training stops.
RF throughput uses `optimize_for_inference`; accuracy is scored separately from
eager FP32 passes, with this distinction explicit in the report.

Private labels, crops, datasets, predictions and weights remain outside git.
The execution and scored-output fixtures contain aggregate results only. The
legacy `human_measurements.json.gz` filename also holds **scored aggregates**,
not raw measurements or clicks. `build_human_report.py` regenerates both ledgers
without private files; historical hashed protocol snapshots retain their original
wording while current presentation corrects the evaluation-exposure label.

The round-4 `train_tiny_ball_rfdetr.py` stays frozen for its recorded source-hash
checks. Use `train_round5.py` for the lifted time budget, decay and replay;
its protocol replaces the old 29-minute limit. Final and intermediate new-model
inference refuses to start until both final checkpoint hashes validate, and
writes an immutable evaluation-start marker. Cross-model selection uses final H
metrics at TRAIN-chosen thresholds and is explicitly optimistic; intermediate
learning curves never select a checkpoint. Controlled throughput now measures
both 2fps sampling and native-rate bursts, so each match projection uses its own
measured pipeline rate.

`benchmark_activity.py` records macOS media-analysis CPU and AGX GPU utilization
for every repeat. mediaanalysisd and PhotosReliveWidget are steady background,
not blockers. The shared quiet-wait budget is 900 seconds across the whole
session; remaining contention is reported rather than waited on indefinitely.
The benchmark checks active generators, ComfyUI queues and bench jobs without
pausing unrelated work. Per-repeat observations accompany the median, including
any `contended (steady background load)` classification.

The final selection audit recounts raw saved detections independently of the
scorer: RF a has 76/122 held-out on-ball hits and 6 false boxes on 60 no-ball
frames (2.00/10s); RF b has 75/122 and 4 (1.33/10s). Both qualify at the declared
<=2 ceiling, so RF a is selected by one hit. This remains optimistic selection
on recipe-selected clips, not proof of product superiority.

### Round-5 framing review: no winner at a strict budget

The matched-false-rate table is diagnostic, not a deployed threshold selector.
The two r5 fits exchange any apparent advantage with only a few false boxes;
A's selected kit source sits exactly at the ceiling and wins by one hit. The
formerly disputed 2.17/1.30 rates use the 46-frame **on-ball** no-ball subset;
strict selection uses all 60 held-out no-ball frames. `round5_framing.py` derives
matched-rate budgets, n21 visible-ball sensitivity and timing ranges from saved
aggregates. It retains strict labels and selection. Process IDs, resident model
memory and per-second process samples remain private; committed timing evidence
contains per-repeat summaries, with mean mediaanalysisd CPU >=30% flagged as
contended. This retrospective flag does not change the nonblocking wait policy.

`inspect_n21_adjudication.py` decodes five source frames and draws saved boxes for
all four models at both TRAIN budgets; it imports no detector. Its private sheet
is `~/codex-runs/ball-r5-n21/adjudicate-s6-s10.png`. The later decision must cover s0–s10 and
choose match-ball versus any-ball semantics before labels change.

Canonical historical tracker aggregates were generated under CPython 3.11.16,
NumPy 2.4.6, with no SciPy installed (`~/Projects/loanarmy/.loan`). The RF runtime
uses CPython 3.12.14, NumPy 2.3.5 and SciPy 1.18.1. We chose a narrow comparison
tolerance rather than changing either environment: only duration-weighted group
continuity permits absolute/relative drift <=1e-12. Per-clip tracks, counts and
other fields remain exact; validated reports retain canonical saved values.
The reproduced three differences were about 1e-16; no SciPy function is used on
this path, so a SciPy-specific cause is unconfirmed. The RF full suite is now
included in verification.

No further m04 training. Calibrate on TRAIN-disjoint clips; budget future fits by
optimizer steps; publish matched-rate curves and per-clip counts beside TRAIN
operating points. Fresh labels from a different venue/day are the next evidence.

N21 follow-up: `inspect_n21_adjudication.py --all-frames` renders all eleven frames,
current MJ labels (including accepted-source/manual provenance), background zoom
and saved boxes from every candidate at both TRAIN budgets. The output is
`~/codex-runs/ball-r5-n21/adjudicate-s0-s10.png`. s8–s10 show a football, s6 none,
and s7 is ambiguous. YOLO has no boxes on these five no-ball frames, but does
box the background ball among the six visible frames. The click-distance sequence
86,142,164,158,118,77px (reviewer's flagged spot) moves away, then back.

`n21_rule_sensitivity.py` verifies saved-pass/label hashes and captures aggregate
counterfactuals without editing labels. Match-ball-only removes six visible
background-ball labels and expands the held-out no-ball denominator to66. The
any-visible-ball false column retains the prior fixed60-frame credit convention;
its overall recall adds three provisional references from inspected old RF box
centres, not MJ-confirmed clicks. The20px tolerance can include nearby footwear;
this limitation is explicit. On-ball recall is unchanged because n21 is off_pitch.
One MJ decision must cover s0–s10: any visible ball or match ball only; current
labels follow neither rule consistently. The pending decision is not applied to
the real labels, gate, thresholds or kit selection.

### Historical Rule A — build 9 (2026-09-11)

MJ adopted **every visible ball counts**: match, spare and kick-about balls are
all detector positives. `visible:false` means no visible ball of any kind.
`match_ball` is a separate tracker flag, unused by detector metrics.
The committed headline remains as labelled; re-scoring awaits MJ's 188-frame review.
The preceding n21 decision requests and build descriptions are historical.

Label schema v2 retains `clip,t,x,y,visible` and optional `source_accepted`,
`accepted_source`, `accepted_score`, adding `schema_version:2` and
`match_ball:true|false|null` (null for no-ball or unknown match identity).
Import accepts five-field v1, provenance v1 and v2. Visible v1 rows default to
`match_ball:true`; v1 no-ball rows gain `needs_any_ball_review:true`.
N21 s0–s5 retain their original coordinates/provenance and default to
`match_ball:false,needs_confirmation:true`; these are not final adjudications.
`review_frame` persists queue membership; `review_confirmed` records an explicit
review action. Pending flags are cleared only by Enter/click/N in review mode.
M changes identity without confirming visibility. Clearing a label resets progress.
Normal-mode edits to queued frames require review again.

`any_ball_review.py` writes a **new** `~/codex-runs/ball-human-truth-v2.jsonl`,
refuses existing output, hashes both files and leaves the original unchanged.
It ranks all 182 old no-ball frames plus six n21 confirmations by the highest
saved box confidence ≥0.3 from five baselines and r5-a/r5-b final low passes.
Source-name ties are deterministic; queue ties use clip/time; remaining frames
come last. WASB points are inspected but cannot provide a box suggestion.
Raw scores are uncalibrated suggestion priorities, never evidence of accuracy.
No model inference, training or new frame extraction is needed.

Build 9 embeds the v2 seed and queue in `index.html`. The unchanged localStorage
key remains importable; browser labels take priority and keep provenance. New
exports are v2. **Review: any visible ball?** shows `reviewed X / 188`:

- Enter/Space accepts the displayed saved suggestion as visible, NOT match ball.
- Click places a visible ball, NOT match ball; it clears acceptance provenance.
- N confirms no ball at all; M toggles the current visible label's match-ball flag.
- Arrows move through ranked queue entries; J/K move between clips in the queue.
- Normal mode retains frame/clip navigation; new clicks/accepts default match ball.

Nothing auto-saves a suggestion. The private queue has 126 suggestions, 62 frames
without one, and 0 confirmations at delivery. Full ranking/source scores and
hashes are in `~/ball-truth-review/migration.json` and `any-ball-review.json`.
Sync **only** the contents of `~/codex-runs/ball-truth-review-build9/` over the
existing laptop kit: `index.html`, `build.json`, `any-ball-review.json`,
`migration.json`. Existing JPEGs are reused; none are included in the sync folder.

`human_score.py`, `score_from_saved.py`, `review_round5.py` and `round5_report.py`
accept `--label-rule {as_labelled,any_ball}` (default `as_labelled`). Both use
supplied visibility: the switch does not hallucinate additional balls or use
`match_ball` to exclude positives. Rule A declares the adopted semantics and
badges **every table header** `PROVISIONAL: N of 188 review frames confirmed`
until all 188 are explicitly confirmed. Round-5 saved scoring recomputes TRAIN
thresholds and current denominators; it never reuses old framing/denominators as
new rule-A results. Its CLI writes separate local files and never updates the
headline or kit selection. No new headline scores are published in this change.

```sh
# One-time migration/build (refuses to overwrite an existing v2 output):
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/any_ball_review.py
# Refresh HTML after code edits, reusing the private seed and queue:
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/ball_truth_kit.py \
  --human-jsonl ~/codex-runs/ball-human-truth-v2.jsonl \
  --suggestions ~/ball-truth-review/suggestions.jsonl \
  --review ~/ball-truth-review/any-ball-review.json
# Isolated real-browser verification; never uses MJ's browser profile:
~/models/tinyball/.venv-mj/bin/python spike/video-analysis/ball/check_any_ball_kit.py
# Machinery for after MJ exports reviewed v2 labels (saved detections only):
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/round5_report.py \
  --human-jsonl ~/codex-runs/ball-human-truth-v2.jsonl --label-rule any_ball \
  --out-prefix ~/codex-runs/ball-rule-a-provisional
```

`throughput_round5.py` now validates every selected checkpoint against its fit
summary **before any model/runtime load or quiet wait**, outside timing. Recorded
throughput results are unchanged. Historical `train_tiny_ball.py:585` stamps the
observed weights hash in the same run that trained those weights; it is historical
and unused here, not an independent post-training integrity declaration.

### Historical build 10 — storage and review safety fixes

Build 10 used `~/ball-truth-review-build10/index.html`. Use build 11 for new
labelling; it preserves the same v2 storage key and schema. Build 10 uses
`ball-human-v2:{frozen_set_id}:{source}:fps2` and reads
the old v1 key only during first-open bootstrap when no v2 value exists. It
never writes the v1 key. Seed/migrated rows have `updated_at:0`; edits and imports
stamp integer milliseconds. Existing labels, including accepted-source provenance,
remain intact across migration.

V2 storage is one validated envelope containing labels and timestamped deletion
records. Every save re-reads storage and merges the newest timestamp per label;
Web Locks serializes tab writes in Chromium. Storage events merge updates and
show “labels changed in another tab”. Clear records stop stale tabs resurrecting
removed labels. Exported JSONL contains the surviving label rows, with timestamps.

Invalid stored labels or clear history force **READ-ONLY** mode. Enter, click,
N, M, C and Clear cannot save. Export creates a recovery backup including the raw
stored value. Re-import repaired JSONL, inspect the import counts and explicitly
confirm replacement to recover; unreadable storage is never silently overwritten.
An ordinary import reports new, changed, unchanged and would-downgrade-confirmed
counts (ignoring timestamp-only differences). Replacing confirmed reviews with
unconfirmed or v1 rows requires explicit confirmation; cancellation changes nothing.

**C** in review mode confirms the current visible label as-is, NOT the match ball.
It keeps x/y and accepted-source/manual provenance, clears pending flags and
records confirmation. Enter still accepts the displayed suggestion and its source.

The `fixtures/any_ball_review_keys.json` registry freezes 188 clip|time identities.
Of these, 182 are exactly MJ's original no-ball frames; the remaining six are n21
s0–s5 confirmations. It has no explicit visibility fields, boxes or pixel
coordinates, but it does reveal which frames were marked no-ball. The file remains
committed to keep the review queue deterministic. The queue is
those keys plus every label with `needs_any_ball_review` or `needs_confirmation`.
The kit updates membership after import/storage changes and has saved suggestions
for the entire frame catalog. A non-queue row's `review_confirmed` flag cannot
increase progress. Scoring remains PROVISIONAL while any pending row exists or
any queue key is absent/unconfirmed; its denominator expands with pending rows.
Historical scores and the committed headline are unchanged. F5 (multiple balls
per frame) remains explicitly deferred pending MJ's decision.

Before syncing a fresh laptop export, compare its values against the immutable
original. The command reports added/removed/changed identities and changed fields,
ignoring file order, JSON key order and whitespace:

```sh
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/compare_label_exports.py \
  ~/codex-runs/ball-human-truth.jsonl /path/to/fresh-mj-export.jsonl
# If different, use the NEW export as input and NEW names for all outputs:
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/any_ball_review.py \
  --input /path/to/fresh-mj-export.jsonl \
  --output /new/revision/ball-human-truth-v2-build10.jsonl \
  --kit /new/revision/ball-truth-review-build10 \
  --sync /new/sync/ball-truth-review-build10
```

`any_ball_review.py` also includes the value diff against the immutable baseline
in its migration audit. This build used the existing original export; no fresh
laptop export was available. Its new seed is
`~/codex-runs/ball-human-truth-v2-build10.jsonl`; both prior JSONLs remain immutable.
The initial queue is still exactly 188 entries in the same order, 126 suggestions,
0 confirmations, and all 688 normal suggestions are retained.

Builders require a **new versioned directory** ending `-build10`, refuse existing
builds and shared frame directories, and never extract or copy frames. The page
points at `../ball-truth-review/` on basecamp. Sync the five files in
`~/codex-runs/ball-truth-review-build10/` to the sibling laptop directory
`~/ball-truth-review-build10/`, preserving that relative frame path:
`index.html`, `build.json`, `any-ball-review.json`, `review-suggestions.json`,
`migration.json`. Do not overlay an old kit. The verified build-8 copy remains at
`~/codex-runs/ball-truth-review-build8/`; its page/build hashes are in WORK_LOG.md.

```sh
# Synthetic browser regressions run within pytest in the existing RF environment:
~/models/tinyball/.venv-mj/bin/python -m pytest spike/video-analysis/ball/test_kit_safety.py -q
# Real kit and exact preserved build-8 page, always isolated browser storage:
~/models/tinyball/.venv-mj/bin/python spike/video-analysis/ball/check_any_ball_kit.py
~/models/tinyball/.venv-mj/bin/python spike/video-analysis/ball/check_build10_private.py
```

### Build 11 — confirmed decisions and merge conflicts

Use `~/ball-truth-review-build11/index.html`. The v2 storage key, label fields and
storage envelope are **identical to build 10**. No migration or restamping occurs
when existing v2 storage is opened. Builds 8/9/10 remain untouched.

Import now protects **every changed confirmed row**, even if the incoming row is
also confirmed. The preview includes “would replace N confirmed decisions (M of
them newer locally)”. Older changed rows are labelled STALE. Stored decisions are
kept unless MJ explicitly approves replacement; Cancel leaves storage byte-for-byte
unchanged. Approved changes receive new timestamps. Timestamp-only differences
are counted as unchanged. This protects visibility, point, match identity and
manual/accepted-source provenance against stale backups.

Timestamp ties rank **confirmed > explicit clear > unconfirmed**. Ties between
differing confirmed rows retain the row already in storage and increment a visible,
page-local conflict counter; repeat observations of the same conflict count once.
Two different unconfirmed rows at equal time also retain storage. Later timestamps
still win, including explicit clears. These rules change merge behavior, not the
schema. No conflict metadata is added to rows or the v2 envelope.

A separate `:legacy-sha256` metadata key records the v1 value's hash at bootstrap.
Later opens and legacy storage events compare it and show:
“The old click page was used after this page started. Export from it and import
here to include those labels.” Legacy rows are never automatically merged again.
**Build 10 stored no such hash:** an existing build-10 browser establishes its
baseline on its first build-11 visit; earlier legacy edits cannot be detected
retroactively. The warning persists while v1 differs from the recorded baseline.

**Mandatory before laptop sync:** export the current browser labels and run
`compare_label_exports.py` against the immutable original export. Do both before
replacing or distributing a kit. If the export differs, regenerate using that
fresh export and new output names. **Once v2 browser storage exists, the embedded
seed is ignored.** A kit rebuilt from a fresh export must have that export imported
explicitly into any browser that already opened build 10 or 11; merely opening the
new page does not update existing stored labels. This requirement is also in the
page help.

```sh
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/compare_label_exports.py \
  ~/codex-runs/ball-human-truth.jsonl /path/to/fresh-browser-export.jsonl
# New outputs only; never overwrite a previous kit or label file:
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/any_ball_review.py \
  --input /path/to/fresh-browser-export.jsonl \
  --output /new/revision/ball-human-truth-v2-build11.jsonl \
  --kit /new/revision/ball-truth-review-build11 \
  --sync /new/sync/ball-truth-review-build11
```

This local build stages the existing immutable source because no fresh laptop
export was supplied. It is at `~/ball-truth-review-build11/`, with five identical
sync files under `~/codex-runs/ball-truth-review-build11/`: `index.html`, `build.json`,
`any-ball-review.json`, `review-suggestions.json`, `migration.json`. The page reuses
`../ball-truth-review/` frames. The mandatory export/compare step still precedes
laptop sync. The new seed is `~/codex-runs/ball-human-truth-v2-build11.jsonl`.

`test_storage_ties.py` covers all equal/newer-time pairings of confirmed,
unconfirmed and clear records. Chromium tests cover same-confirmed stale imports,
conflict counts, legacy warnings and seed isolation. `check_build11_private.py`
opens the preserved real build-10 page, makes representative browser-only decisions
and a clear, then verifies build 11 preserves every row and the exact v2 stored
value. All browser checks use isolated contexts, never MJ's profile.
