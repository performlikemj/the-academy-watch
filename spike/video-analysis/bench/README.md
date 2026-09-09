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
uv pip install --python ~/Projects/loanarmy/.loan/bin/python -r spike/video-analysis/bench/requirements.txt
BENCH_REQUIRE_CV2=1 ~/Projects/loanarmy/.loan/bin/python -m pytest \
  spike/video-analysis/bench -v
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
`malformed_claim_text_count`. These review fields do not change geometry metrics. Round 3 also aggregates
identity checks in the legacy scorer, excluding disputed truth labels.

Test blind spots: `prepare_anchor` is monkeypatched in MLX adapter tests;
the worker test fakes the `mlx_vlm` API, so signature drift is caught only by a
live smoke. The production single-still test exercises actual anchor drawing,
frame sizing and boxed-frame tagging, with media extraction and inference faked.

## Lane A: annotated meaning-only reads (`qwen3vl_annotated`)

The tracker owns geometry; the VLM owns meaning. Every future lane-A model frame has a
magenta rectangle and `#N` label, drawn from `truth["box_track"]` through
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

`semantic_score.py` alone scores this adapter; geometry scoring stays unchanged.
The original runs had no human notes. Round 3 applies MJ's 20 notes and reports
deterministic activity checks, with the limits described below. Other metrics
cover format, empty answers, presence-only prose, invented numbers (the exact
r2 jersey regex), explicit kit-colour matches/abstentions/mismatches, and event
times within the window ±0.5s. Schema-invalid JSON is failed. Clip time validity
requires all event times to pass (vacuously true with no events); the separate
event-time rate has no denominator when no events exist.

Honesty rates and events/clip use scored clips. `valid_attempt_rate` exposes
schema/transport failures across every attempt; `valid_rate` among scored clips
is necessarily 100%. Wall/clip includes every attempt. `unclear` colour is an
abstention, never wrong; report match/abstain/wrong rates use all scored clips,
with a separate match rate among asserted colours. `presence_only_read` preserves the original rule: no
substantive event class and the narrow presence regex, so it is not an independent
assessment of descriptive usefulness. Names/goals and sentence kit assertions
are not independently verified by these metrics.

Fill `notes_template.md` with one plain sentence per marked clip (about 30
minutes for 20 clips). Prefer a local ignored copy for completed notes:

```sh
cp spike/video-analysis/bench/notes_template.md ledgers/lane-a-notes.md
# Paste the page output into ledgers/lane-a-notes.md, then:
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/apply_notes.py \
  --manifest ~/Projects/loanarmy-bench-frozen/manifest.json \
  --notes ledgers/lane-a-notes.md
```

The intake validates the complete form, clip IDs, windows, jersey and kit before
writing `human_note` into local `truth/*.json` (and dispute metadata when requested).
Human prose may contain multiple sentences and is preserved without rewriting. It refuses tracked or
nonignored truth inside a Git worktree. Blank notes preserve existing values.
`--generate --notes <new-path>` creates a form for another manifest and refuses
to overwrite an existing form. Never commit populated truth or raw reports.

When notes exist, re-score via the comparison command below with no new inference
or code change. The existing conservative keyword mismatch rule examines the
sentence plus explicit event classes (underscores replaced by spaces); it is
available only for noted scored clips with classifiable activity and does not
grade every action class. Simple no/without clause negation is handled.
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


## Lane A honesty review, round 2 (saved-output rescoring only)

The `e1c-annotated-dense` and `e1c-annotated-prod30` measurements used **red**
rectangles. No model runs or review-video renders were repeated for this repair.
Future `qwen3vl_annotated` inputs use magenta (RGB 255, 0, 255), recorded in their
run settings; `grounding.draw_anchor_box` retains its original default for other
callers. At round 2 all kit truth fields were red; round 4 adds MJ's black override and
two kit uncertainties, so the evaluated set remains heavily red-dominated.

The original `presence_only_rate` becomes `presence_only_read_rate`, with its
exact event-gated calculation preserved. `presence_only_sentence_rate` inspects
the sentence regardless of events: `visible`, `can be seen`, or `on the field`,
without a hit on the requested action-verb stems (carry/carries/carrying, pass,
duel, shot/shoot, run/running, dribbl, tackl, cross, header, clear). This literal
rule still counts moving/interacting/holding descriptions. It yields 7/20 dense
and 12/20 prod30 presence sentences; it is not the manual strict/loose tally.
`sentence_event_consistency_rate` originally required every substantive event
type in the narrow keyword vocabulary. Round 4 separates unmapped types and
recognises the requested inflections; details follow below.

`zero_duration_event_rate` counts events with equal endpoints;
`window_filling_event_rate` counts events whose endpoints are each within 0.5s of
the full window. Both denominators are events across scored clips.
`events_per_sent_frame` divides their total event count by their total sent-frame
count. `high_confidence_completed_from_one_frame_count` counts high-confidence,
completed events from scored attempts with exactly one sent frame. The r2 jersey
review also supplies `supplied_number_asserted_as_kit_detail_rate`, independently
of invented-number detection.

Both scorers expose `from_thinking_rate`: recorded true flags divided by all
attempts, including pre-inference failures (missing flags count false). All 40
lane-A replies came through the thinking-field fallback despite `think=false`;
Pydantic validity therefore does not verify the effect of Ollama's `format`
grammar on that field. The transport is unchanged.

Every new runner launch records `truth_set_sha256_after_notes` and
`human_notes_sha256` in both `run.json` and the report. The snapshot covers all
manifest truth files, including clips not selected for inference. The first hash
is SHA-256 of a sorted JSON clip-ID → SHA-256(file bytes) mapping; the second is
SHA-256 of a sorted JSON clip-ID → human-note mapping (Python JSON defaults).
The same single-read snapshot supplies scoring truth throughout the run. These
hashes join the inference fingerprint, so changed truth/notes refuse a stale
explicit resume; this intentionally changes new launch fingerprints. The
manifest's `frozen_set_id` semantics remain unchanged. `apply_notes.py` prints
both current hashes after intake. Use the comparison scripts to re-score saved
outputs without inference: their report hashes describe the current scoring
snapshot, while historical launch metadata remains intact. Missing historical
inference-time hashes cannot be retroactively established.

## Lane A round 3: MJ notes and activity checks

MJ reviewed all 20 boxed clips. Apply his local notes verbatim, without inference:

```sh
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/apply_notes.py \
  --manifest ~/Projects/loanarmy-bench-frozen/manifest.json \
  --notes ~/codex-runs/lane-a-notes.md \
  --dispute m04-n24-t3013-679939-681217
```

`--dispute CLIP_ID` is repeatable, requires a nonblank note, and writes
`truth_label_disputed: true` and `truth_label_dispute_note` alongside `human_note`.
The supplied label stays unchanged for audit; it is not silently replaced with
another number. Both scorers list `disputed_clips` in overall and exclude them
from jersey denominators, retaining their raw assertions and activity checks.
A kit override restores kit evaluation; uncertain kit truth counts as abstention. Semantic per-clip jersey metrics are null for disputed clips; legacy
`jersey_review` keeps colour/number mentions. Disputed kits without an override
or uncertainty flag remain unavailable.
The manifest's `frozen_set_id` is unchanged. Intake prints the updated truth-byte
and note hashes; the regenerated ledger records the same snapshot hashes.
Truth JSON is never committed; the notes text is published in the ledgers and
test fixtures. The local intake file remains outside Git.

MJ disputes #24: “wrong number. this is number 12 from the shorts”. The earlier
fps2 video lane called this player's kit **black**, as did annotated prod30.
MJ's appended clarification confirms black warm-up kit and black shorts: those
colour readings were correct and frozen `kit_color: red` is wrong. The existing
dispute excludes jersey metrics; a black kit override now restores colour
evaluation while the original frozen fields stay for audit. MJ also reports “some misses as
far as boxes are concerned”: visible truth-track misses belong to the tracker
input, and may affect model readings. Kit metrics remain dominated by red labels with historical red annotations.

The explicit rules live in `semantic_activity.py`. Case-insensitive phrase/stem
matches classify the note, with no clip-ID overrides. Multiple classes are kept:

| Truth activity | Positive note evidence | Current clips |
|---|---|---:|
| off_pitch | sideline(s), warm-up/warmup/warm up, warming up, stretching, walking off, coming off, hamstring | 7 |
| idle_on_pitch | just walks/walking around, wait(s)/waiting, ball doesn't come | 3 |
| defensive_track_back | track/tracks/tracked/tracking back, walking back on defense | 3 |
| on_ball_action | Any action from the next table, excluding a missed header | 6 |
| positional_only | center/centre back, touchline, stays wide, only when no other activity matched | 1 |

The idle/on-ball overlap is n04-243433. The disputed n24 note is unclassified:
it says nothing about activity. n22's “misses header” is not a positive header.

| Note/sentence action class | Explicit keyword family |
|---|---|
| pass | pass, passes, passed, passing |
| carry | carry, carries, carried, carrying, dribbl…, running with (the) ball |
| duel | duel(s), challeng…, tackl… |
| shot | shot(s), shoot… |
| defensive_action | intercept… |
| header | head(s) the ball, header(s); exclude “miss(es/ed/ing) [a/the] header” |
| receive | receiv… |
| turn | half turn, half-turn |
| loss | lose/loses/losing/lost the ball |
| cross | cross, crosses, crossed, crossing |
| goalkeeping | save, saves, saved, saving |

The schema's on-ball event classes are `ACTION_TYPES` minus
`off_ball`, `none`, and `unclear`: pass, carry, duel, shot, defensive_action,
set_piece, goalkeeping. The contract has **no header or receive event**.
Header/receive/turn/loss remain distinct note classes; a carry is not credited
as a match for them. This deliberate vocabulary limitation lowers recall.

`model_activity` is on_ball when events or sentence action keywords assert an
action; otherwise off_ball. It additionally records stoppage for any stoppage
phase and off_pitch for an explicit sentence context. An empty event list does
not hide an on-ball sentence assertion. Subset headline rates below use the
structured events alone, as requested.

| Metric | Rule and denominator |
|---|---|
| fabricated_rate | Conservative `score.fabricated_event_classes` with simple no/without negation on sentence plus event classes; any mismatch / 19 activity-classified notes. Excludes the identity-only note; it does not prove every mismatch is fabricated. |
| off_pitch_claimed_on_ball_rate | Any structured on-ball event / off-pitch notes (7); headline fabrication diagnostic |
| idle_claimed_on_ball_rate | Any structured on-ball event / idle notes (3); mixed n04 can legitimately have a later on-ball action |
| on_ball_recall | At least one exact structured event-class match to a note action / on-ball notes (6); not event-level recall and not outcome grading |
| activity_agreement_rate | Compatible coarse activity / classified notes (19). Off-pitch requires explicit off-pitch prose with no on-ball activity; on-ball notes require any on-ball activity; idle/defensive/positional notes require no on-ball or off-pitch activity. Mixed idle/on-ball follows the on-ball rule. |
| sentence_matches_note | agree/disagree/undetermined counts across all scored clips (20). Positive shared action/activity with no detected incompatible assertion = agree; an extra action class or incompatible off-pitch/on-pitch context = disagree; absent evidence or unclassified note = undetermined. |

These deterministic rules measure limited correctness against MJ's observations.
Coarse activity agreement can pass a generic carry while exact event recall
fails. Sentence overlap treats an unsupported holding-ball detail as undetermined. It
does not resolve arbitrary negation, attribute actions to actors, or establish
outcome or event timing. The conservative fabricated rule retains its narrow
vocabulary, including its original missing inflections. These limits are also
shown in the ledger, alongside every note, both sentences/events, and verdicts.
No model runs, GPU work, transport changes or adoption decision are involved.

## Lane A round 4: kit corrections and narrower diagnostics

The `.loan` bench interpreter uses `bench/requirements.txt` for CPU review
rendering (`opencv-python-headless==4.13.0.92`, the existing spike pin). Install
it with the Verify command above. The basecamp gate sets `BENCH_REQUIRE_CV2=1`:
missing OpenCV, ffmpeg or ffprobe fails the review-kit test rather than skipping.
Outside that required gate, optional media dependencies can still skip cleanly.
No alternate interpreter, dependency shim, model run or clip rebuild is needed.

All note-entry instructions target `ledgers/lane-a-notes.md`, including the
page and generated README.txt. `apply_notes --notes` defaults to that worktree
path when it exists; otherwise it uses `bench/report/mj-notes.md`. Both are
local intake paths; do not stage the local intake file. Notes text is published
in ledgers and test fixtures. Explicit `--notes` still works.
Future `build.json` files record the current Git HEAD in `commit` at build
start (null if Git metadata is unavailable). Existing rendered clips and their
build metadata remain untouched.

Apply MJ's verified kit override and the two uncertain warm-up-kit flags:

```sh
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/apply_notes.py \
  --manifest ~/Projects/loanarmy-bench-frozen/manifest.json \
  --notes ~/codex-runs/lane-a-notes.md \
  --kit-override m04-n24-t3013-679939-681217=black \
  --kit-uncertain m04-n22-t3012-070707-074371 \
  --kit-uncertain m04-n03-t1406-385962-387137
```

The override requires an existing dispute or accompanying `--dispute`. It
restores kit evaluation independently of the disputed jersey binding. Uncertain
kit truth takes precedence and abstains, neither matching nor wrong, even if
the model asserts a colour. The current jersey denominator is 19; kit
match/wrong/abstain rates use all 20 scored clips, including two abstentions.
The asserted-only kit-match rate excludes those abstentions.

`presence_only_strict_rate` adds exclusions for hold/holding, with (the) ball,
possession, moving and interacting to the unchanged
`presence_only_sentence_rate`. `presence_with_substantive_event_rate` uses that
original sentence-only presence flag AND at least one event other than
none/unclear; it remains independent of the strict rate.

Consistency now requires only substantive classes with a shared keyword map.
It reports ignored off_ball/defensive_action/set_piece/goalkeeping classes in
`sentence_event_unmapped_classes` and unmatched mapped classes separately.
A local extension recognises carrying, dribbling and running with (the) ball as
carry, and passing as pass. The shared fabrication keyword vocabulary is unchanged; round 5 adds simple
no/without negation handling in the fabrication diagnostic.
No mapped events still passes consistency vacuously; the presence-plus-event
metric makes that limitation visible.

Lane A's `number_invented` is stricter than the shared jersey kill: any
unsupplied “#N / number N / jersey N” flags, while timestamps do not.

## Lane A round 5: strict versus lenient recall

`on_ball_recall` remains the strict, discriminating column. The new
`on_ball_recall_lenient` also credits carry for receive, half-turn or ball-loss
notes, using the same six on-ball clips as denominator. It does not substitute
carry for a header, duel/challenge or interception. A pass can still match a
pass under either rule. Dense matches 1/6 strictly and 3/6 leniently; prod30
matches 0/6 strictly and 2/6 leniently.

The saved outputs contain carry on **36/40 reads** (dense 19/20, prod30 17/20).
Lenient recall therefore rewards a frequent
carry prior; it must not replace strict recall or be read as evidence that the
model recovered the actual receive/turn/loss. No matching outcome is implied.

`fabricated_rate` now excludes unclassifiable notes: n24 is identity-only, leaving
19 eligible clips. Per-clip keyword lists are retained for audit. Activity subset
rates appear first in the top table; the keyword fabrication rate follows them.
Simple `no …` and `without …` scopes end at punctuation or but/then/however;
negated keywords in either model prose or notes do not count as positive events.
A semicolon separates prose from explicit event classes so a trailing negation
cannot suppress the structured events. This is not general negation parsing.
Prod30 n25's “no ball contact or goal scored” no longer contributes goal, while
its explicit carry event still contributes to fabrication.

“holding (the) ball” is an on-ball assertion but not an action class. When the
note does not mention holding, that extra detail blocks a sentence agree verdict
and gives undetermined unless another explicit contradiction already gives
disagree. Prod30 n09-143096 now has sentence verdict undetermined.

The requested headline's no-on-ball denominator needs correction: n04-243433
contains both idle behaviour and a receive/half-turn. Excluding it leaves 13
classified clips where MJ saw no on-ball action, with inventions on 12/13 dense
and 10/13 prod30. The idle subset still includes the mixed clip. The headline
uses the requested “12 frames” and “single-still” shorthand; actual sampling is
11.9 versus 1.45 frames/attempt, with single stills on 13/20 prod30 clips. This
single-pass comparison does not prove a general causal effect of frame density.

## Semantic comparison completeness and paired metrics

`compare_semantic.py` requires complete coverage of the selected clip IDs in
both saved `report.json` files and raw claim files. Failed attempts count as
covered; missing reports, missing claim files, missing/not-attempted report rows,
or `stopped_early` / `wall_cap_exceeded` markers in either run/report withhold
the headline as **INCOMPLETE COMPARISON — headline withheld**. Missing IDs and
stop markers are listed for both lanes. A configured wall cap alone is not a
stop marker; an empty recorded stop object still is.

Every comparison-table rate, recall, agreement and sentence count uses only the
shared IDs scored in both saved reports and current rescoring. The shared count
is printed above the table. Full per-run reports and the scored/failed columns
retain all attempts, so failures remain visible. JSON records coverage, exact
paired counts, shared IDs, paired aggregates and frame facts under
`comparison_metadata`; existing per-clip scores are not rewritten.

Run adapter, model and frozen-set identities must match, and the frozen set
must match the supplied manifest. `--allow-mixed` explicitly permits identity
mismatches and displays them; it does not relax the identical selection or
semantic-schema requirements. Mixed-set comparisons still use the supplied
manifest truth, as disclosed in the report. Both run.json model names must be
recorded. The headline uses those names, measured mean boxed-frame counts from
`anchored_frames`, and the count of raw attempts with exactly one `sent_frame`.
Frame facts include all recorded attempts, including failures, independently
of the shared scored metric denominator. Dense/sparse order follows measured
boxed-frame means, so custom run names or reversed input order do not substitute
hard-coded models or frame counts. The canonical pair has 20 shared scored
clips and means 11.9 vs 1.45 boxed frames; 13/20 sparse attempts have one frame.
The earlier round-5 headline shorthand is superseded by these measured facts.

## Lane B: yes/no checks (`qwen3vl_checks`)

MJ's 2026-09-10 decision narrows Qwen3-VL to six closed questions that can be
assessed for use by the existing honesty gate. Lane A invented on-ball play on
12/13 dense clips where MJ saw none. This experiment measures checks; adoption
and production integration remain MJ's decision.

`checks_contract.py` defines strict Pydantic v2 `ChecksRead`, with forbidden
extras at every level. Each of the six fields is an object containing `answer`,
`confidence` (`low|medium|high`), and an optional `reason` of at most 80 characters.
The first five answers are `yes|no|unclear`; `kit_color_seen.answer` is
`red|blue|white|black|yellow|green|other|unclear`. Example question value:
`{"answer":"unclear","confidence":"low","reason":"Ball obscured"}`.
There are no other free-text fields. Reasons are **never scored**; the prompt
requests brief reasons so the ledger can log verbatim audit examples. The exact
inlined schema is Ollama's `format`, and raw replies use `model_validate_json`.
A malformed reply fails the clip. Parsed caches cannot hide malformed raw JSON.

The prompt defines on-pitch as field of play (excluding bench/sideline/warm-up),
in-progress as active play (excluding warm-up/walking off/stoppages), nearby ball
as within roughly two body-lengths, a touch as clearly playing the ball at least
once, and running as running rather than walking/standing. `unclear` is correct
whenever frames do not clearly show an answer; never guess or infer unseen action.
The magenta box identifies the player; its `#N` label does not establish a visible
jersey number. Kit colour must come from the clothing, not the annotation.

The adapter imports `qwen3vl_annotated.prepare_frames` rather than duplicating
sampling or drawing: dense `0.5 / 12` and sparse `30 / 3`, magenta on every frame,
spread over the window with the same bounded gap adjustments. Runner fingerprints
include contract version, prompt version, resolved context, sampling and all
existing inference/truth provenance settings. Context must be 65536 or omitted.
The shared Ollama transport and thinking-field fallback are unchanged.

### Explicit truth rules

`checks_truth.py` applies `semantic_activity.truth_activity` to MJ's notes.
`fixtures/checks_notes.json` contains the 20 real note/kit fixtures and independently
transcribed expected cells. Missing evidence is ungraded, not a fabricated label.
Rules apply in the following precedence order; a missed header establishes
proximity even off-pitch. Otherwise off-pitch takes precedence, and
on-ball takes precedence over idle in the mixed receive clip:

| Question | Rule |
|---|---|
| player_on_pitch | off_pitch → no; every other classified clip → yes; identity-only n24 → ungraded |
| play_in_progress | off_pitch → no; on_ball_action / defensive_track_back / positional_only → yes; idle waiting for throw-in without running → no; mixed running/throw-in n04-307417 → ungraded; idle “just walking around” n10 → ungraded; mixed receive n04-243433 → yes |
| ball_near_player | misses/missed (a/the) header → yes, even off-pitch (n22); otherwise off_pitch → no; on_ball_action → yes; other idle → no; defensive / positional / unclassified → ungraded |
| player_touches_ball | off_pitch → no; on_ball_action → yes; other idle → no; defensive / positional / unclassified → ungraded |
| player_running | off_pitch or non-on-ball walking/standing/sideline/stretching → no; run / track back / goes or went forward → yes; challenges or receives alone → ungraded; mixed walking/receive n04-243433 and others → ungraded |
| kit_color_seen | Import lane A's `identity_truth.kit_truth`: uncertainty takes precedence and forces abstention; verified override restores colour independently of disputed jersey identity; disputed colour without override/uncertainty → ungraded |

On-ball touch positives: n03-157170, n12-237107, n15, n17-253073,
n17-416826, n04-243433. Running positives: n04-307417, n05, n09-297601,
n17-253073. Running negatives: n03-385962, n09-143096, n09-385922, n10,
n12-679986, n17-304624, n21, n22, n25. Other running cells are ungraded.
Round r2 removes the erroneous n17-416826 directive and challenge-as-running
rule; n03-157170, n15 and n17-416826 become ungraded for running. The mixed
running/throw-in note makes n04-307417 play-in-progress ungraded. A missed
header makes n22 ball-near yes. These are note rules, with no clip-ID overrides.
The two uncertain kits are n22 and n03-385962; disputed n24 uses black. The full
20 × 6 truth table with MJ's verbatim notes is printed in the comparison ledger
so MJ can correct any cell.

### Scoring and thresholds

`checks_score.py` uses only answer/confidence and derived truth, never reasons.
Per-question counts expose every denominator:

- Accuracy: correct / graded answered; `unclear` excluded.
- Abstain rate: unclear / eligible. Uncertain kit truth forces abstention even
  when a colour is asserted, exactly as lane A. Unavailable truth is ungraded.
- Coverage: graded answered / eligible. The kit denominator includes its two
  forced abstentions; binary eligibility requires yes/no truth.
- False-yes rate: yes answers / truth-no cells. False-no rate: no answers /
  truth-yes cells. Truth denominators include model abstentions. Neither rate
  applies to colour; colour accuracy grades exact matches.
- Modal answer/share: most frequent raw valid answer over all selected valid reads
  (20 here), including unclear, ungraded cells and uncertain kit assertions.
  Ties sort lexically. Failed reads have no answer and are counted separately.
- Majority baseline: largest truth-class count / all selected graded truth cells;
  independent of model abstention, excluding uncertain/unavailable kit truth.
  `accuracy_minus_baseline` subtracts that baseline from answered accuracy.
- `information` is true only if modal share < 0.9 AND accuracy > baseline + 0.05.
  This requested heuristic is not proof of visual grounding; selective abstention
  can raise answered accuracy even without any yes answers.
- Recall where binary truth is defined: true yes / all selected truth-positive
  clips; no, unclear and failures count as misses. Touch recall is subject to the
  temporal sampling screen below; its raw numerator, denominator and rate remain.
- Confident wrong: incorrect graded answers with high confidence. Confidence is
  uncalibrated and prompt-sensitive; two pilot clips changed no/low to no/high
  after the reason instruction changed. No prompt changes are made in r2.
- Macro accuracy: mean of available answered accuracies over all six questions.
  Macro false-yes: mean of available rates over the five binary questions.
  Overall abstain: pooled abstentions / eligible question cells.
- Gate 1: false-yes pooled across `player_on_pitch` and `play_in_progress` on
  off-pitch clips (14 truth-no cells on the complete set), also split by question
  (7 each).
- Gate 2: false-yes for `player_touches_ball` on off-pitch plus idle clips whose
  touch truth is **no** (9 clips). The mixed idle/receive clip n04-243433 is
  excluded because it has a real touch; an affirmative answer is correct there.

Thresholds are **Gate 1 false-yes ≤ 10%, Gate 2 touch false-yes ≤ 10% AND
measurable touch recall ≥ 50%, macro accuracy ≥ 80% on answered, overall
abstain ≤ 40%**. Gate 2 is WITHHELD when recall is not measurable; its
false-yes component passing alone is not a gate PASS. The ledger states each
PASS/FAIL/WITHHELD; it makes no adoption
call. Empty denominators withhold the corresponding threshold. Per-run reports
keep all attempts and failures; failed reads are excluded from correctness
metrics. `from_thinking_rate` and wall seconds/clip include all attempts.

`compare_checks.py` requires two runs selecting the same unique, nonempty clip
IDs in the same order. It validates adapter/model/frozen-set identities against
both runs and the supplied manifest, and checks the contract version in run,
report and raw files. `--allow-mixed` permits identity mismatches with a visible
caveat, but never relaxes selection or schema requirements. Missing raw files,
missing saved reports/rows, not-attempted rows and stop markers (including empty
objects) withhold the headline and thresholds. Failed attempts count as covered;
configured wall caps alone do not mark a run incomplete. Comparison accuracy/error metrics
use the intersection scored in both saved reports and current rescoring. Modal
distributions, baselines, touch counts and sampling use each full run. Full-run
reports retain every attempt. Frame facts come from run.json and recorded frame
lists, including failures; measured boxed-frame means determine dense/sparse
headline order. Five reasons are the first available question reason per scored
clip, in contract order, then the first five such clips in selected order.

### Sequential execution on basecamp

MJ authorizes lane B to start when ready: **no lane-A gate file applies**.
Before each run, `pgrep -f "run_bench|qwen_match_analysis"` must show only this
session's own processes. Never stop another session's processes. Smoke the
specified clip, inspect the raw JSON, then run the final lanes sequentially:

```sh
BENCH_NUM_CTX=65536 ~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/run_bench.py \
  --adapter qwen3vl_checks --model qwen3-vl:8b \
  --clips m04-n12-t1411-237107-242145 --sample-interval 0.5 --sample-limit 12 --timeout 120 \
  --manifest ~/Projects/loanarmy-bench-frozen/manifest.json \
  --report-root ~/Projects/loanarmy-bench-reports --run-id e1d-checks-smoke-reasons

BENCH_NUM_CTX=65536 ~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/run_bench.py \
  --adapter qwen3vl_checks --model qwen3-vl:8b --clips all \
  --sample-interval 0.5 --sample-limit 12 --timeout 120 \
  --manifest ~/Projects/loanarmy-bench-frozen/manifest.json \
  --report-root ~/Projects/loanarmy-bench-reports --run-id e1d-checks-dense

BENCH_NUM_CTX=65536 ~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/run_bench.py \
  --adapter qwen3vl_checks --model qwen3-vl:8b --clips all \
  --sample-interval 30 --sample-limit 3 --timeout 120 \
  --manifest ~/Projects/loanarmy-bench-frozen/manifest.json \
  --report-root ~/Projects/loanarmy-bench-reports --run-id e1d-checks-prod30

~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/diag_format_channel.py \
  --manifest ~/Projects/loanarmy-bench-frozen/manifest.json \
  --out-json ~/Projects/loanarmy-bench-reports/e1d-checks-format-diagnostic.json

~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/compare_checks.py \
  --reports-root ~/Projects/loanarmy-bench-reports \
  --manifest ~/Projects/loanarmy-bench-frozen/manifest.json \
  --diagnostic ~/Projects/loanarmy-bench-reports/e1d-checks-format-diagnostic.json \
  --out-json ledgers/research/evidence-bench-2026-09-10-lane-b.json \
  --out-md ledgers/research/evidence-bench-2026-09-10-lane-b.md
```

The diagnostic uses the smoke clip's dense frames for exactly three direct
`/api/chat` requests: schema format, `"json"` format, no format. It holds prompt,
frames, `think:false`, context 65536 and generation options constant. It records
both raw message fields, which contain JSON, content emptiness and strict
validation under the existing content-first/fallback selection. No response
repair or transport change is made. Exceptions are logged without blocking the
comparison. This small diagnostic cannot establish grammar enforcement generally.

Caveats: n=20, rule-derived note truth, single passes, mostly red kit truth,
magenta inputs versus lane A's historical red inputs, and MJ-reported tracker
misses. No frozen media, populated truth files or raw reports are staged. The
explicit note fixtures are committed for the required deterministic unit tests.
Run the Verify gates above with `BENCH_REQUIRE_CV2=1`; no frontend changes or
dependency restore are needed.

## Lane C: player-centred checks crops (`qwen3vl_checks_crop`)

Lane C imports lane B's six questions, strict contract, schema transport and
scorer. The only added prompt sentence is “Each image is a close crop centred
on the marked player.” With `--crop-context`, the sentence ends “, followed by
the full frame for context.” Prompt version is lane B's version plus `-crop`.
The context flag and `player-square-v1` crop version enter the run fingerprint;
existing lane-B fingerprints are unchanged.

Sampling and decoding reuse the annotated adapter's shared pre-annotation feed:
`0.5 / 12` dense or `30 / 3` sparse, including its existing spread and bounded gap
snapping. Geometry is in the **decoded lane-B frame's pixels** (1280×720 on this
set), after scaling the interpolated source truth box. Crop side is
`ceil(max(3 * box_height, 4 * box_width, 384))`, capped to the shorter frame
edge. Its centre starts at the box centre (integer rounding within half a pixel);
at edges the whole square shifts inside the frame. The crop is resized to
768×768 with Lanczos, then the shared magenta rectangle and `#N` are drawn.
Raw frame records include `crop_side_px`, `crop_scale` (=768/side), crop rectangle,
decoded dimensions, box transforms and timestamps. This enlarges decoded pixels;
it cannot restore detail lost in the original wide-frame decode.

Crop-only sends one image per sampled instant. `--crop-context` sends each crop
followed immediately by its 512-wide, aspect-preserving full frame with the same
magenta identity marker. Thus dense context sends up to 24 images for 12 sampled
instants. Prompt timestamps remain the same ordered sample instants, with the
added sentence defining the pair ordering. Comparison frame/anchor counts count
sent images, including context images; the crop ledger separately records sampled
instant counts. A second image at the same timestamp is not extra temporal evidence.

```sh
BENCH_NUM_CTX=65536 ~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/run_bench.py \
  --adapter qwen3vl_checks_crop --model qwen3-vl:8b --timeout 900 \
  --sample-interval 0.5 --sample-limit 12 --clips all \
  --manifest ~/Projects/loanarmy-bench-frozen/manifest.json \
  --report-root ~/Projects/loanarmy-bench-reports --run-id e1e-crop-8b-dense
```

Use `30 / 3` for `e1e-crop-8b-prod30`; add `--crop-context` to dense for
`e1e-cropctx-8b-dense`. Run the required n12 true-touch smoke first. Run
`e1e-crop-32b-dense` only when at least one completed 8B variant answers touch=yes
on at least **2 of the 6 truth-positive touch clips**. Recall counts yes/6;
unclear, no and failed reads are misses, independently of answered-only accuracy.
This was the original execution scheduling rule; r2 adds a measurable recall
requirement to gate 2 and marks these sparse-in-time raw counts unmeasurable.
Dense still spacing on the six touch clips is 1.58, 4.14, 4.57, 5.52, 6.62 and
1.88 seconds, derived from saved distinct timestamps. The review estimates a
perfect detector would score approximately 1/6 dense and 0/6 sparse, calling the
2/6 rule "unattainable by construction". That is a review assumption, not a
measured bound: spacing alone cannot establish touch visibility or mathematical
impossibility. Human touch times and frame-level visibility labels are missing.
Touch and running scores must be read with this temporal confound. The 32B
scheduling result is now recomputed from saved 8B crop answers, never hand-set.

For all three crop variants, on-pitch numbers are also spatially confounded:
the sideline is largely cropped out in crops-only views, and crop+context adds
only a 512-wide frame. Crop runs are excluded from the gate-1 headline and their
gate-1 threshold is WITHHELD; raw counts remain visible. A ball outside the crop
confounds ball-near answers too. These crop results cannot isolate model failure
to recognize sideline context.

The crop ledger uses the shared `compare_checks.py --allow-mixed` alongside all
six lane-B runs. Existing complete/shared-coverage guards apply. It adds recall,
geometry, per-instant/image counts, the 32B execution decision and three local crop
PNG paths/hashes. Examples and raw reports stay outside the repository. Cropping
can remove the ball or sideline context; provided tracking may miss the player.
Round r2 corrects the five reviewed truth cells and rescores these saved outputs.
These are single passes on 20 clips; adoption remains MJ's decision.

## Round r2: temporal sampling and reproducible rescoring

Frame density is calculated from saved distinct timestamps: N / full truth-window
seconds, reporting the unweighted mean and minimum across clips. Crop/context
pairs count once. Mean spacing is window seconds / (N−1); a single-frame clip
uses the full window. Missing window/timestamp metadata withholds recall. If the
run's mean spacing exceeds 1.0 s, `touch_recall` and the touch question's `recall`
are null with reason "not measurable at this sampling"; raw touch counts and
`touch_recall_raw` remain. Passing the spacing screen alone does not verify that
a touch was visible.

The saved dense runs average about 2.49 s spacing, and prod30 about 23.99 s.
Zero affirmative touches across these nine runs cannot establish inability to
see a touch: the frames rarely contain the brief contact. Wide-frame on-pitch/sideline
failures retain context; crop on-pitch and ball-near results are spatially confounded. Follow-up **moment windows** require MJ to mark
touch times on the six clips: at least 8 frames at at least 4 fps in the 2 seconds
around each marked touch. No new model calls occur in r2.

`compare_checks.py --execution path.json` reads the committed execution record,
including archived run provenance, prompt diff, diagnostic results, notes hash,
previous metrics/truth for deltas, and crop artifact paths. It generates both
ledger formats without post-processing. The historical 32B-only ledger was
renamed to lane-b-models; this six-run ledger retains both 32B runs.
Regenerate all three current lane-B/C ledger pairs from the saved claims:

```sh
~/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/regenerate_checks_ledgers.py \
  --reports-root ~/Projects/loanarmy-bench-reports \
  --manifest ~/Projects/loanarmy-bench-frozen/manifest.json \
  --output-dir ledgers/research
```

The wrapper passes each committed `fixtures/lane-*-execution.json` to the
comparator and calls no inference code. With the same saved reports, truth and
execution inputs, JSON and Markdown regenerate byte-for-byte. Existing run.json,
claims, prompts, contracts, model fingerprints and frozen truth remain intact.

### Round r3 regeneration inputs and portable gates

R2's six ledger files already reproduced byte-for-byte; r3 retains that mechanism.
Each execution input now records its exact `compare_checks.py` command and cwd.
`--diagnostic NAME=PATH` is repeatable (the old bare-path form still works);
`--execution` can retain the already committed named diagnostic payloads and
historical model provenance. `--touch-clips` explicitly requests the automatically
truth-derived touch tables. `--example-crops DIR` reads `examples.json` and
verifies each local PNG's SHA-256. Crop geometry is derived from saved frames;
`decision_32b` is evaluated from complete 8B crop runs and the six truth positives.
`--baseline-run NAME` produces per-question percentage-point deltas versus that
selected run; these ledgers use 8B wide dense as the explicit baseline, including
for sparse runs. `--extra-caveat` or the execution input records additional context.

The requested nine-run review headline appears verbatim on the models and crops
ledgers, followed by its qualification: it is review wording, not a quantified
perfect-detector bound or a claim that all individual answers were identical.
Generated touch/running rows carry temporal caveats; crop on-pitch and ball-near
rows carry spatial caveats. Model inputs, questions, truth rules and numeric
scoring remain unchanged in r3.

Portable tests use Pillow `getdata()` and assert the review-kit commit only when
Git can resolve HEAD. Run `BENCH_REQUIRE_CV2=1 python -m pytest
spike/video-analysis/bench -q` both in the worktree and in a `git archive` export
using the same dependency environment. No `.git` directory is needed in the export.
