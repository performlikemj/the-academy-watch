# Local ball bench: self-agreement now, human scoring next

**All proxy verdicts are `UNMEASURABLE (proxy)`.** The numbers measure detector
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
`compare_ball.py --human-jsonl` remains available for the original candidates.

The first 1,041 suggestions come solely from saved detections: **683 rf_3x3,
242 rf_2x2, 116 wasb_2x2**. Choose the highest confidence observation on one of
those candidates' longest re-tracked fragments at that timestamp; otherwise use
the top rf_3x3 box at >=0.3, or no suggestion. WASB supplies a point. These scores
are not calibrated across models. Track membership does not prove ball identity.
Regenerate using `python spike/video-analysis/ball/human_loop.py`; then rebuild
with `ball_truth_kit.py --suggestions ~/ball-truth-review/suggestions.jsonl`.
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

The fixed split is by complete clip, **never by frame**:

| Role | On-ball clips |
|---|---|
| Train | n03-157170, n04-243433, n12-237107, n15 |
| Held out | n17-253073, n17-416826 |

All seven off-pitch clips are reserved for scoring. The run records full IDs.
Normal runs use the last checkpoint; held-out labels do not select weights.
Per-epoch validation is disabled; Ultralytics may validate once at the end.
Default training requests five epochs with MPS and a 15-minute trainer budget;
Ultralytics' time budget may adjust epoch count and finishes at epoch boundaries.
Full human-labelled training time is not yet measured. Use `--epochs` to set the
requested count. `--init` lets later clicks improve the preceding model.

Outputs: `weights.pt`, `dataset.json`, `dataset/`, `metrics.json`,
`detections.json`, `suggestions.jsonl`, and Ultralytics `fit/` checkpoints.
Metrics report held-out **20-source-pixel** recall/precision, unmatched predictions
per labelled off-pitch frame and FPS including decode. At most one prediction
matches each visible label; duplicates count as unmatched. A single model pass
covers all 1,105 scheduled frames. Suggestions contain at most one point per
frame with an output >=0.1; missing predictions produce no suggestion, never an
invented point. The saved detection file includes those empty frames.

The six-candidate bench uses its existing **40-pixel** matching rule for fair
comparison. Scores that include training clips are in-sample; consult the separate
20-pixel held-out metrics for generalisation. Model-assisted confirmation also
needs careful review; acceptance provenance is available for audits.

The separate human sample gate requires all 540 on-ball labels and >=100 off-pitch
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
