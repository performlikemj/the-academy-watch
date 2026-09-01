# Film Room Evidence Bench

This bench freezes 20 uploader-side reel windows from local match 4 and scores
model claims only against deterministic time and tracked-box evidence. The
frozen footage is evaluation data, never training data. Player names are not
copied into the bench.

## Build the frozen set

Use the project Python 3.11 interpreter from the repository root. The builder
loads the local backend environment, opens Postgres read-only, calls the
existing reel and dev-artifact helpers, follows the footage symlink, and writes
local-only data below `frozen/`.

```sh
/Users/michaeljones/Projects/loanarmy/.loan/bin/python \
  spike/video-analysis/bench/build_manifest.py
```

The deterministic selection seed is `20260901`. The builder requires 20
windows of at least three seconds across at least eight uploader-side roster
entries. It includes human-corrected chain 1411, the two smallest-box
far-side/panning windows, and two tracked windows below the identity pipeline's
two-read jersey evidence gate. A timestamped stored `phase_of_play=set-piece`
observation is included when available; otherwise the manifest records the
constraint as skipped. The manifest also registers the local SoccerTrack v2
117093 video, homography, and keypoints paths.

Generated data:

```text
frozen/
  manifest.json
  clips/<clip_id>.mp4
  truth/<clip_id>.json
```

`frozen/` is ignored. Force-add only `frozen/README.md` and
`frozen/manifest.example.json`; never commit the generated manifest, truth, or
clips.

## Run an adapter

Runs are sequential. Do not run model adapters on the laptop; run them on
basecamp after the model is installed.

```sh
/Users/michaeljones/Projects/loanarmy/.loan/bin/python \
  spike/video-analysis/bench/run_bench.py \
  --adapter baseline --clips all \
  --ollama-url http://127.0.0.1:11434 \
  --model qwen3.8:27b-obliterated-q8

/Users/michaeljones/Projects/loanarmy/.loan/bin/python \
  spike/video-analysis/bench/run_bench.py \
  --adapter qwen3vl_ollama --clips all \
  --anchor-mode first \
  --box-space normalized_1000 \
  --ollama-url http://127.0.0.1:11434 \
  --model qwen3-vl:8b \
  --num-predict 400 --repeat-penalty 1.15
```

The Qwen3-VL adapter supports `--anchor-mode first|all` and defaults to
`first`. In `first` mode, only the first sampled image carries the red `#N`
identity rectangle. The remaining images are unlabelled, and the model must
find the same player and return its own evidence box. This prevents a model
from inflating E1 grounding by simply copying a truth rectangle drawn on every
frame. `all` preserves the original all-frames-boxed behavior as an explicitly
echo-prone control run.

`BENCH_NUM_CTX` controls Ollama context for both adapters, falling back to `QWEN_NUM_CTX` and then `65536`; set it to `0` or empty to omit `num_ctx`.

`--box-space normalized_1000|image_pixels` declares the model's box convention
and can also be set with `BENCH_BOX_SPACE`. Qwen3-VL defaults to
`normalized_1000`, where each axis is an integer on a 0-1000 grid relative to
the image. `image_pixels` requests coordinates in the exact sent-image pixel
dimensions.

`--clips` accepts `all` or comma-separated clip IDs. Each result is written
immediately to `report/<timestamp>/claims/<clip_id>.json`. An interrupted run
automatically resumes the newest matching incomplete directory, or use
`--run-id <id>` explicitly. Existing claim files are skipped unless `--force`
is passed. `run.json` records a fingerprint over the adapter, resolved model
(including environment fallback), Ollama URL, timeout, anchor mode,
box space, `num_predict`, repeat penalty, frozen-set ID, and selected clips. A
run resumes only when that complete fingerprint matches; an explicit
mismatched run ID is refused unless `--force` is used.

Each claims file records `sent_frames` entries with the extracted image path,
absolute timestamp, and exact `sent_w`/`sent_h` dimensions observed after
extraction. Each claim requires `box_t`, the timestamp of the sampled frame in
which its box was observed; `t0..t1` may cover the whole action. For transition
compatibility, a missing `box_t` falls back to `t0` and records
`box_t_source=fallback_t0`. Each claim also records its declared `box_space`,
preserves the response as `box_model_space`, and stores the bench's axis-by-axis
conversion into source-video pixels as `box` for scoring. Normalized boxes
convert with `x * source_w / 1000` and `y * source_h / 1000`; image-pixel boxes
use the sent-to-source axis scales.

After conversion, a wholly out-of-frame box, a box larger than the source
frame, or an `image_pixels` box whose coordinates all remain at or below 1000
despite a larger sent image is explicitly malformed. The claim records a
`box_sanity_reason`, and reports count these under `box_sanity_guard_count`.

`qwen3vl_mlx` is intentionally a fail-fast E0 stub. It documents the native
video model/path but never substitutes another backend.

## Read the report

Each run writes `report.json` and `report.md`.

### What supported means

A supported claim must be well-formed, have its whole `[t0,t1]` inside the
truth window ±0.5 seconds, and ground its returned source-pixel box against the
truth box interpolated at `box_t`, with either IoU ≥ 0.5 or at least 80% of the
claim box inside the truth box. A provided `box_t` outside `[t0,t1]` ±0.5
seconds is malformed. `box_grounded_at_midpoint` and its rates retain the old
midpoint calculation for comparison only; they do not determine support.

`box_t` exists because a box locates evidence in one observed frame while
`t0..t1` describes the claim's full action. In the measured E1 v4 run, midpoint
scoring grounded 0/29 claims, while scoring those same boxes at `t0` grounded
14/29 (48%). Old claims therefore remain auditable through the explicit
`fallback_t0` source rather than silently changing provenance.

Claims also carry `boxed_frame`, computed by whether `box_t` is within ±0.5
seconds of an anchored image.

Truth boxes are interpolated only between adjacent samples no more than twice
the track's median sampling cadence apart, with a minimum 0.25-second
tolerance. A `box_t` inside a larger disjoint tracking gap is marked
`no_truth_at_time`, cannot be supported, and increments the per-clip and
overall `untracked_gap` metric.

`supported_rate_unboxed` is the headline E1 number. It measures supported
claims citing unlabelled frames where the model had to locate the player
itself. `supported_rate_boxed` is the echo-prone control. `echo_suspect_count`
counts boxed-frame claims whose declared-space box matches the exact
sent-image-space drawn rectangle within two pixels on all four sides. A
normalized box is converted to sent-image pixels for this comparison. The
report also splits raw box-grounding rates at `box_t` and at the midpoint into
boxed and unboxed claims.

`time_only_rate` counts claims whose time is grounded but box is not. `hollow`
means the claim lacks a valid time interval or box. Adapter errors mechanically
produce `failed`; missing truth produces `observed` and is excluded from
grounding aggregates. When `human_note` is non-null, `fabricated` is a
deliberately conservative explicit keyword-class mismatch, not a semantic
model judgment.

E1 acceptance thresholds from the directive:

- unsupported ≤ 10%
- supported ≥ 2× the baseline supported rate
- hollow < 5%
- wall time ≤ 2 minutes per clip on basecamp

Kill the E1 lane if unsupported exceeds 25% or the model invents jersey numbers
on the number-not-reliably-readable clips.

## Verify

```sh
/Users/michaeljones/Projects/loanarmy/.loan/bin/python -m pytest \
  spike/video-analysis/bench -q
ruff check spike/video-analysis/bench
ruff format --check spike/video-analysis/bench
```
