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

## qwen3vl_mlx native video

```sh
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/run_bench.py \
  --adapter qwen3vl_mlx --fps 2.0 --clips all \
  --manifest ~/Projects/loanarmy-bench-frozen/manifest.json \
  --report-root ~/Projects/loanarmy-bench-reports --run-id e1b-mlx-video-fps2 \
  --anchor-mode first --box-space normalized_1000 \
  --num-predict 400 --repeat-penalty 1.15 --timeout 120 --wall-cap 120
```

Install the worker's pinned template dependencies into its own venv:

```sh
uv pip install --python ~/mlx-vlm-venv/bin/python -r spike/video-analysis/bench/requirements-worker.txt
```

The worker no longer inherits `PYTHONPATH`. The optional, fingerprinted
`BENCH_MLX_PYTHONPATH` escape hatch defaults to empty; normal runs need none.
Set `HF_HUB_OFFLINE=1` to use the cached model without network access.
No dependencies, frozen media, or raw reports should be staged.

The bench stays on Python 3.11 and launches `adapters/mlx_worker.py` with
`BENCH_MLX_PYTHON` (default `~/mlx-vlm-venv/bin/python`, Python 3.12).
Each clip uses one JSON stdin/stdout transaction and includes model startup in
wall time. Optional `--wall-cap 120` stops a slow lane after at least five
attempts (immediately if the breach occurs later), writes the partial report,
and records `stopped_early.unrun_clips` in `report.json`. The cap is fingerprinted. Failures and unparseable responses are `failed`; there is no fallback.
`--model` / `BENCH_MLX_MODEL` defaults to
`mlx-community/Qwen3-VL-8B-Instruct-4bit`. `--fps` overrides `BENCH_MLX_FPS`
(default 2.0); FPS, resolved model and worker interpreter are fingerprinted.
`--num-predict` maps to `max_tokens`, `--repeat-penalty` to
`repetition_penalty` (64-token repetition context, temperature 0).

“Native video” here means mlx-vlm's dense `fps`-sampled frames with Qwen3-VL's
video encoding, versus the production 3-still multi-image lane. The frozen E1
Ollama control actually samples every 5 seconds, up to six stills per clip.
The MLX loader uniformly samples an even frame count (maximum 768); effective
FPS can differ from the request. Decoder-read indices supply actual source
timestamps. The installed mlx-vlm Qwen processor does no second sampling;
native video tensors and temporal patch grids are passed to `generate`. This
processor omits HF per-pair timestamp tokens: exact times are supplied in the
text prompt, while the model uses its native video grid for temporal positions.

One separate first-sample image gets the shared red `#N` anchor; the raw video
is unlabelled. The image uses the same truth-aware first time as Ollama
(usually 0.05s), while native video begins at 0s. Model claims must already use
absolute source seconds; only frame provenance is converted from clip-local
seconds with the shared helper. No heuristic claim-time correction is applied.
`sent_frames` records every native frame's absolute time and processor-grid
pixel dimensions. Anchor dimensions/boxes also reflect processor resizing.
The existing ±0.5s boxed-frame tolerance remains, so nearby unlabelled video
frames can still count as boxed controls. Normalized-1000 and anchor-first are
required; all-frame anchors and image-pixel boxes are rejected.

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

## Production sampling control and reproducible comparison

`qwen3vl_ollama` accepts `--sample-interval` (seconds, default 5.0) and
`--sample-limit` (default 6). Nondefault sampling settings enter the fingerprint;
the legacy defaults omit these fields to preserve existing v5 fingerprints exactly.
Production's policy is one still every 30 seconds, at most three per call.
For a short 0.5–7 second window this is one still: only the identity anchor.

```sh
BENCH_NUM_CTX=65536 ~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/run_bench.py \
  --adapter qwen3vl_ollama --anchor-mode first --box-space normalized_1000 \
  --model qwen3-vl:8b --num-predict 400 --repeat-penalty 1.15 \
  --sample-interval 30 --sample-limit 3 --clips all \
  --manifest ~/Projects/loanarmy-bench-frozen/manifest.json \
  --report-root ~/Projects/loanarmy-bench-reports --run-id e1b-ollama-frames-prod30

~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/compare_runs.py \
  --reports-root ~/Projects/loanarmy-bench-reports \
  --runs frames=e1b-ollama-frames frames_prod30=e1b-ollama-frames-prod30 \
         video_fps2=e1b-mlx-video-fps2 video_fps4=e1b-mlx-video-fps4 \
  --manifest ~/Projects/loanarmy-bench-frozen/manifest.json \
  --out-json ledgers/research/evidence-bench-2026-09-09-video-lane.json \
  --out-md ledgers/research/evidence-bench-2026-09-09-video-lane.md
```

The comparison reads existing run metadata, full report metrics, raw claims and
(optional) truth identity/kit colour. Outputs are deterministic for those inputs;
no model calls or frozen-data writes occur. Jersey/kit review records textual
assertions, not whether a supplied jersey number was independently legible.

Comparison completeness is checked against the report's per-clip entries for every
selected ID; failed clips count as attempted, and leftover raw claim files cannot
fill a report gap. A missing entry or a `stopped_early`/`wall_cap_exceeded` marker
in run/report metadata produces `INCOMPLETE COMPARISON`, lists missing IDs per lane,
and withholds the historical headline and verdict. A configured `wall_cap_s`
alone is not a stop marker. Pair comparisons record absent entries as
`not_attempted`, without assigning a winner.

The jersey review retains all numeric candidates in the legacy `jersey_mentions`
and `unsupplied_numbers` audit fields. Only unsupplied numbers asserted as
jersey/shirt/kit detail trigger `invented_jersey_number_kill`; other numeric labels
(including frame/time/tracking references) appear in each clip's
`non_jersey_numbers`. Non-string claim text is replaced with an empty string,
flagged `malformed` with `malformed_fields: ["claim"]`, and counted in
`malformed_claim_text_count`. These review fields do not change scorer metrics.

Test blind spots: `prepare_anchor` is monkeypatched in MLX adapter tests;
the worker test fakes the `mlx_vlm` API, so signature drift is caught only by a
live smoke. The production single-still test exercises actual anchor drawing,
frame sizing and boxed-frame tagging, with media extraction and inference faked.

## Lane A: annotated meaning-only reads (`qwen3vl_annotated`)

The tracker owns geometry; the VLM owns meaning. Every sent frame has the shared
red rectangle and `#N` label, drawn from `truth["box_track"]` through
`grounding.interpolated_box`. **Bench truth stands in for the production
tracker's persisted box track.** This evaluates the semantic reader with supplied
geometry, not the tracker or unlabelled-player grounding. No box is requested
from the VLM, so copying a drawn box is not a failure mode in this lane.

`semantic_contract.py` defines the Pydantic v2 `SemanticRead` / `SemanticEvent`
contract: 0–3 events, visibility, observed kit colour, and one sentence of at
most 200 characters. The exact schema is sent as Ollama `format`; replies parse
with `model_validate_json`, forbidden extras and strict enums. Action and phase
vocabularies reuse `qwen_match_analysis`; all prompt vocabulary lists come from
the same constants. No names, unsupplied numbers, inferred actions or invisible
goals are permitted by the prompt. `none`, `unclear`, empty events and low
confidence provide honest exits. These prompt rules do not establish truth.

Sampling defaults to `--sample-interval 0.5 --sample-limit 12`. The cadence
sets the count (at least eight when the window accommodates eight samples),
then samples are evenly spread over the full window with 0.05s endpoint margins
and the shared truth-aware first timestamp. Thus long windows with the 12-frame
cap have an effective interval longer than 0.5s. The sparse annotated control
uses `30 / 3` with the same spread policy and contract.

The first smoke exposed a missing truth box inside a tracking gap. To keep every
image annotated without inventing geometry, a target lacking interpolation is
moved to the nearest *recorded* track timestamp within 0.5s (ties go earlier).
Samples must stay distinct and chronological; a larger gap fails the clip before
inference. `sent_frames` records actual absolute time, original `target_t`,
`sampling_shift_s`, path and dimensions. The text prompt lists actual times.
This bounded departure from uniform spacing is disclosed in the comparison;
no truth files or legacy interpolation rules change. Frame images are temporary.

Run on basecamp only. Wait for MJ's GPU gate before **any** Ollama call, polling
every 30s for at most 90 minutes. Keep `BENCH_NUM_CTX=65536` (or omit `num_ctx`);
this adapter refuses smaller context settings. Example gate:

```sh
python3 - <<'PY'
import time
from pathlib import Path
start = time.monotonic()
while not (Path.home() / "codex-runs/GPU_OK_A").exists():
    if time.monotonic() - start >= 5400:
        raise SystemExit("GPU_OK_A timed out; no model call made")
    time.sleep(30)
PY
```

After the gate, smoke `m04-n12-t1411-237107-242145` and inspect its
`semantic_raw`, then run these sequentially (repeat the gate check if removed):

```sh
BENCH_NUM_CTX=65536 ~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/run_bench.py \
  --adapter qwen3vl_annotated --model qwen3-vl:8b --clips all \
  --sample-interval 0.5 --sample-limit 12 --timeout 120 \
  --manifest ~/Projects/loanarmy-bench-frozen/manifest.json \
  --report-root ~/Projects/loanarmy-bench-reports --run-id e1c-annotated-dense

BENCH_NUM_CTX=65536 ~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/run_bench.py \
  --adapter qwen3vl_annotated --model qwen3-vl:8b --clips all \
  --sample-interval 30 --sample-limit 3 --timeout 120 \
  --manifest ~/Projects/loanarmy-bench-frozen/manifest.json \
  --report-root ~/Projects/loanarmy-bench-reports --run-id e1c-annotated-prod30

touch ~/codex-runs/GPU_DONE_A
```

`semantic_score.py` alone scores this adapter; the existing geometry scorer is
unchanged. Reports start with the honest limit: **the frozen clips have no human
notes, so event CORRECTNESS is not measured until MJ supplies them**. Metrics
cover format, empty answers, presence-only prose, invented numbers (the exact
r2 jersey regex), explicit kit-colour matches/abstentions/mismatches, and event
times within the window ±0.5s. Schema-invalid JSON is failed. Clip time validity
requires all event times to pass (vacuously true with no events); the separate
event-time rate has no denominator when no events exist.

Honesty rates and events/clip use scored clips. `valid_attempt_rate` exposes
schema/transport failures across every attempt; `valid_rate` among scored clips
is necessarily 100%. Wall/clip includes every attempt. `unclear` colour is an
abstention, never wrong; report match/abstain/wrong rates use all scored clips,
with a separate match rate among asserted colours. `presence_only` requires no
substantive event class and the narrow presence regex, so it is not an independent
assessment of descriptive usefulness. Names/goals and sentence kit assertions
are not independently verified by these metrics.

Fill `notes_template.md` with one plain sentence per marked clip (about 30
minutes for 20 clips). Prefer a local ignored copy for completed notes:

```sh
cp spike/video-analysis/bench/notes_template.md spike/video-analysis/bench/report/mj-notes.md
# Edit report/mj-notes.md, then:
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/apply_notes.py \
  --manifest ~/Projects/loanarmy-bench-frozen/manifest.json \
  --notes spike/video-analysis/bench/report/mj-notes.md
```

The intake validates the complete form, clip IDs, windows, jersey and kit before
writing only `human_note` into local `truth/*.json`. It refuses tracked or
nonignored truth inside a Git worktree. Blank notes preserve existing values.
`--generate --notes <new-path>` creates a form for another manifest and refuses
to overwrite an existing form. Never commit populated truth or raw reports.

When notes exist, re-score via the comparison command below with no new inference
or code change. The existing conservative keyword mismatch rule examines the
sentence plus explicit event classes (underscores replaced by spaces); it is
available only for noted scored clips and does not grade every action class.
The comparison fingerprints current human notes and includes five verbatim
sentences per run, chosen in manifest order, full clip metrics and provenance.

```sh
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/compare_semantic.py \
  --reports-root ~/Projects/loanarmy-bench-reports \
  --manifest ~/Projects/loanarmy-bench-frozen/manifest.json \
  --out-json ledgers/research/evidence-bench-2026-09-09-lane-a.json \
  --out-md ledgers/research/evidence-bench-2026-09-09-lane-a.md
```

No adoption call is made; that decision belongs to MJ.

## Offline human-note review kit

`review_kit.py` burns the tracked box into **every decoded frame** of a portable
review copy, with the same red three-pixel outline and the shared renderer's
white-on-red `#N` label. The OpenCV decoder, resizing, drawing and libx264 encoder
run on CPU; no model calls, GPU gate or GPU work is involved. Dependencies are
OpenCV (`cv2`), Pillow, ffmpeg and ffprobe; no frontend dependency restore is needed.
Basecamp also provides these Python dependencies in `~/mlx-vlm-venv/bin/python`,
which can be used as the builder interpreter.

```sh
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/review_kit.py \
  --frozen-dir ~/Projects/loanarmy-bench-frozen \
  --out-dir ~/lane-a-review --clips all --scale 1280
```

The output contains `clips/<clip_id>.mp4`, `index.html`, a five-line `README.txt`
and `build.json` with per-clip frame counts, tracking gaps and byte sizes. Copy
that folder to the laptop and open `index.html` directly. No server is required.
The videos use H.264/yuv420p with faststart and no audio for Safari/QuickTime.
If a clip exceeds 40 MB, rerun with `--scale 960`. Outputs replace only the
selected rendered clips; frozen inputs are never edited. `--clips` also accepts
comma-separated IDs; the page retains every manifest note line and clearly
marks videos omitted from a partial export.

Frame timestamps are `window.start_s + frame_index / source_fps` for these
constant-frame-rate frozen clips. Unlike sparse model sampling, review rendering
never moves a timestamp to obtain a box. It uses `grounding.interpolated_box`
with the existing gap rule: frames without a box receive a small **no track**
marker and no stale rectangle. Geometry is scaled from truth's source size to
the output size before drawing. The shared file renderer creates the small
identity-label stamp once per clip; OpenCV draws each frame's changing rectangle.

Notes autosave to localStorage as they are typed. The textarea always reflects
all template lines, and Copy notes falls back to selection/copy when the browser
blocks clipboard access from `file://`. Storage restrictions produce an explicit
message to copy notes before closing. Space plays/pauses the focused clip; J/K
move between clips, and shortcuts do not intercept note editing. Paste the
copied lines into `ledgers/lane-a-notes.md`, then use `apply_notes.py` with that
file when ready. The committed blank template remains unchanged.
