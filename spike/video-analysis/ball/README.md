# Local ball detection bench

This bench samples all 20 frozen match-4 windows at **2 fps**, using the verified
native 1080p source where available. It is a detector comparison and an independent
human ball-label intake, not touch attribution or a production ball tracker.

All code is local. Model weights, the MIT WASB checkout, generated media and raw
reports are excluded from git. The committed measurement fixture contains recorded
numeric outputs and player truth context; it contains no ball human labels.

```sh
# From the worktree root. Existing required pytest environment is in main checkout.
uv venv spike/video-analysis/ball/.venv-bench --python 3.11
uv pip install --python spike/video-analysis/ball/.venv-bench/bin/python \
  -r spike/video-analysis/ball/requirements.txt

git clone https://github.com/nttcom/WASB-SBDT.git \
  spike/video-analysis/ball/third_party/WASB-SBDT
git -C spike/video-analysis/ball/third_party/WASB-SBDT checkout \
  923462cacdeb3353b84ddebdedb3f4b7a8553b0f
mkdir -p ~/models/wasb
spike/video-analysis/ball/.venv-bench/bin/gdown \
  'https://drive.google.com/uc?id=1pg0MpMtKZ6ziYEr4oyfKYPOO3hjLw94l' \
  -O ~/models/wasb/wasb_soccer_best.pth.tar

# Only run one model lane at a time. Check that matched processes belong to you.
pgrep -f 'run_bench|qwen_match_analysis'
spike/video-analysis/ball/.venv-bench/bin/python spike/video-analysis/ball/ball_truth_kit.py
for candidate in rf_full rf_2x2 rf_3x3 wasb; do
  spike/video-analysis/ball/.venv-bench/bin/python \
    spike/video-analysis/ball/run_ball.py --candidate "$candidate" || break
done

# Capture a new set of raw reports only deliberately; ordinary regeneration uses fixtures.
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/compare_ball.py --capture
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/annotate_examples.py
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/compare_ball.py

# Human follow-up; produces separate human metrics, leaving proxy unchanged.
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/compare_ball.py \
  --human-jsonl ~/Downloads/ball-human-truth.jsonl \
  --out-prefix ~/Projects/loanarmy-bench-reports/ball-detect-2026-09-10/human-followup

BENCH_REQUIRE_CV2=1 ~/Projects/loanarmy/.loan/bin/python -m pytest \
  spike/video-analysis/bench spike/video-analysis/ball -q
ruff check spike/video-analysis/bench spike/video-analysis/ball
ruff format --check spike/video-analysis/bench spike/video-analysis/ball
```

Open `~/ball-truth-review/index.html` in a browser. Click the match ball centre,
mark **No ball visible**, or leave uncertain frames unlabelled. Arrow keys navigate.
Clip selector jumps to each window. Export JSONL as a backup; import restores or
merges validated labels. Browser localStorage under `file://` depends on browser
settings, so the page reports storage errors and still supports export. All code
and images are local; there is no CDN or detector cue on the human review page.
The tested JSONL contract is exactly `{clip,t,x,y,visible}` with absolute source
seconds and source-pixel coordinates; invisible coordinates are null.

## Measurement definitions

- Fixed **proxy** voters: RF full at 0.1, RF 2x2 at 0.1, WASB at heatmap 0.5.
  At least two distinct voters must agree within 40 source pixels. All qualifying
  pair midpoints are retained; candidate recall requires a centre within 40 pixels
  of at least one midpoint. This endogenous proxy favours its voters and shares
  RF weights. The 3x3 variant has no additional vote. Sweeps never move the denominator.
- RF-DETR medium uses the production loader, prediction and class filter (sports
  ball, sparse COCO ID 37), default 576 input. Supervision InferenceSlicer uses
  exactly 2x2 or 3x3 overlapping tiles with 100 px overlap, sequential callbacks
  and 0.5 IoU NMS. The emitted coordinates are restored to source pixels.
- WASB directly loads the pinned upstream HRNet and soccer state dict on MPS.
  The upstream CUDA-only wrapper is bypassed. Inputs are three consecutive native
  RGB frames, affine resized to 512x288 and ImageNet normalized. The last channel's
  sigmoid heatmap is thresholded at 0.5; weighted connected components and maximum
  heatmap mass select one ball. No physical ball diameter can be derived from this
  heatmap, so size stays null. This is single last-frame output, not upstream
  overlapping-window ensemble evaluation. Repeat left boundary frames explicitly.
- **False/10 s proxy** = every raw ball observation on the seven off-pitch clips
  divided by their full duration, times ten, at the stated 2 fps cadence. These
  notes concern the player, so a real ball elsewhere can count against this proxy.
  This is neither precision nor a count of distinct false tracks. Human false rate
  uses explicitly invisible labelled samples on off-pitch clips, at 0.5 s exposure
  per sample. Unlabelled samples contribute to neither human numerator nor denominator.
- **Gate proxy** pools the six on-ball visible-frame denominators and seven
  off-pitch durations: recall at least 80%, false rate at most 1 per 10 s. Zero
  visible denominator is UNMEASURABLE. The gate is not human validation.
- FPS includes sequential decoding of all intervening native frames, RGB conversion,
  inference and coordinate extraction, with MPS synchronization before/after each
  clip. Model load/warmup is separate. JSON serialization, tracking and annotations
  are excluded. Threshold sweep filters a shared 0.1 inference output and therefore
  shares measured inference FPS. Timings are recorded observations, not deterministic
  claims about rerunning inference.
- The constant-velocity Kalman filter has a 1.0 s maximum observation gap and an
  uncalibrated **20 px/metre** jump convention: 3 metres per sampled-frame = 60 px.
  Jump allowance scales with missing sample intervals. No homography or physically
  measured metres. Continuity is longest fragment duration (bridging accepted short
  gaps, plus one sample interval), clipped to clip duration; no trailing extrapolation.
  Overall continuity is weighted by clip duration; fragment counts are summed.
- **Touch proximity preview** counts raw detected ball centres within 1.5 player
  box heights of bottom-centre. Player boxes use shared gap-aware interpolation.
  Missing player boxes are excluded and counts exposed. Preview is not touch truth.

`compare_ball.py` uses committed measurement and execution fixtures, with sorted
JSON and stable formatting. No clock, inference, network, or media is needed for
ordinary regeneration. The evidence includes every candidate/threshold/clip, the
separate human section, raw model versions and the execution decisions.

Recorded Python typecheck (mypy 2.3.1; third-party imports are skipped):

```sh
uvx mypy --follow-imports=skip --ignore-missing-imports --check-untyped-defs \
  --cache-dir spike/video-analysis/ball/.mypy_cache \
  spike/video-analysis/ball/{common,ball_track,ball_truth_kit,metrics,detectors,run_ball,compare_ball,annotate_examples}.py
```

The numeric measurement fixture is `fixtures/measurements.json.gz` (deterministic
gzip of sorted JSON); `gzip -dc` exposes the raw per-frame detections, timings,
source provenance and player box tracks for review. It is never a human ball-label
fixture. The 3x3 integer tile grid has 100–101 px overlaps at the final edges.
