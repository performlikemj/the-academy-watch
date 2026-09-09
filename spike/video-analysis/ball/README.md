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

## MJ: score all five candidates without inference

Open `~/ball-truth-review/index.html`. Label the match ball centre, or explicitly
mark **No ball visible**. Leave uncertain frames unlabelled. Export JSONL.
Label all **540 frames in the six on-ball clips**, plus **approximately 100
representative off-pitch frames** spread across the seven off-pitch clips:

- `m04-n03-t1406-157170-158922`
- `m04-n04-t3006-243433-247994`
- `m04-n12-t1411-237107-242145`
- `m04-n15-t3010-164698-170777`
- `m04-n17-t717-253073-260377`
- `m04-n17-t717-416826-418915`

An exact, model-independent 100-frame off-pitch sample plan is in the ledger JSON
and compressed measurement fixture under `human_label_plan`. It spreads frames
through every off-pitch window; no detector output selects the sample. Other
representative samples of at least 100 frames also work. Labelling only obviously
ball-free frames would bias the result.

One command scores **all five candidates and all saved RF thresholds**:

```sh
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/score_from_saved.py \
  --human-jsonl ~/Downloads/ball-human-truth.jsonl
```

Output defaults to `~/Projects/loanarmy-bench-reports/ball-detect-2026-09-10/human-followup.{json,md}`;
use `--out-prefix` to change it. No model, torch, cv2, native video, network or new
inference is needed. `compare_ball.py --human-jsonl` also remains available.

The human section reports recall on visible on-ball labels. On **all labelled
off-pitch frames**, a visible match ball can match at most one prediction within
40 source pixels; all other predictions (including duplicates or other balls)
are unmatched for the single-match-ball target. If the match ball is invisible,
all predictions are unmatched. Exposure is 0.5 s per labelled sampled frame.

A **human sample** gate becomes available after all on-ball frames and >=100
off-pitch frames are labelled: recall >=80% and unmatched predictions <=1/10 s.
It is a sample estimate, not exhaustive full-match validation. Partial labels
still produce metrics and coverage, with the gate withheld. Unlabelled frames
never become negatives. Proxy verdicts remain UNMEASURABLE even after labels exist.
The JSONL contract stays `{clip,t,x,y,visible}`: source pixels, absolute seconds,
null x/y when invisible. Browser storage/export/import and native-size view remain.

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

The only new full pass was `wasb_2x2`, on MPS, with four non-overlapping 960x540
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

The one new inference command used in this round (already completed) was:

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
