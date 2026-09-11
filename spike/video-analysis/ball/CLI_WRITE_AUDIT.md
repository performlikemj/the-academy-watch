# Ball CLI write-path audit — follow-up to PR #1085

Baseline: main 6a2ae331. No kit rebuild, training, inference, or committed fixture
changes in this task. Tests use synthetic inputs and temporary copies.

`output_guard.guard_outputs()` resolves symlinks and `..`, rejects existing
files/directories (including dangling symlinks), fixture descendants, input
aliases, protected `~/codex-runs/ball-human-truth*.jsonl` names, and overlapping
input directories. Multi-file outputs are checked together before capture; a
fresh run directory owns its generated descendants and can update its own history.
CLI callers pass label/JSONL inputs. Report/capture library writers require destinations too; low-level dump/write
helpers still support repeated writes within a newly owned run. This is
CLI preflight, not a filesystem sandbox or a lock against concurrent writers.

The migration CLI retains its existing no-overwrite checks and now requires all
three output destinations explicitly. Its intentional creation
of a new migrated `ball-human-truth*.jsonl` file remains available; it refuses an
existing migrated output/input alias and previously built kit/sync destinations.

Four historical entry points have fixture-pinned source hashes. Their shared
`common.py` import runs the same preflight through `guard_frozen_entrypoint()` on
direct execution, before any training or capture. It is narrowly scoped to those
four filenames in this ball directory and does not change library imports. Their
source bytes and all fixture hashes remain unchanged.

`review_round5 --freeze` rejects every `--extra`; chooses all four canonical
`FINAL_PASSES`; compares the exact name set, each detection hash, and the actual
label-file hash with the committed scored fixture **before capture**. It checks
identities again afterward. Freeze now writes gzip only to a fresh `--out`;
ordinary output is JSON. The committed fixture is always an input. This avoids a
fixture-overwrite exception to the shared guard. The n21 sensitivity CLI now requires a fresh --out JSON. Historical round-2/3/4
capture and round-5 freeze now require fresh output directories; inputs and
trainer metrics remain read-only. Report regeneration
must use a new output prefix, then compare bytes with the committed ledgers.

All CLI entry points are enumerated below. “Yes” covers their run-owned file
writes; browser temporary downloads and third-party caches are not user-selected
output targets. A library-only writer is covered by its calling CLI's preflight.

| CLI | Guarded? | Write paths | G2 sweep disposition |
|---|---|---|---|
| `annotate_examples.py` | Yes — shared preflight | required fresh --out directory, examples/ child images | Explicit destination required (changed) |
| `any_ball_review.py` | Yes — existing safeguards (unchanged exception) | new migrated JSONL, kit and sync HTML/build/queue/suggestion/migration files | Explicit destination required (changed) |
| `ball_truth_kit.py` | Yes — shared preflight | fresh versioned output directory: index.html, build.json | Explicit destination required (changed) |
| `build_human_report.py` | Yes — shared preflight | prefix .json/.md; fresh --capture-out gzip; optional read-only --fixtures bundle | Explicit destination required (changed) |
| `check_any_ball_kit.py` | Yes — shared preflight | optional screenshot; browser downloads use isolated temporary files | Already explicit fresh output; optional screenshot writes nothing by default |
| `check_build10_private.py` | Yes — shared preflight | audit JSON; browser downloads and synthetic scratch kits use isolated temporary directories | Explicit destination required (changed) |
| `check_build11_private.py` | Yes — shared preflight | audit JSON; browser downloads and synthetic scratch kits use isolated temporary directories | Explicit destination required (changed) |
| `check_build12_private.py` | Yes — shared preflight | audit JSON; browser downloads and synthetic scratch kits use isolated temporary directories | Explicit destination required (changed) |
| `check_build13_private.py` | Yes — shared preflight | audit JSON; browser downloads and synthetic scratch kits use isolated temporary directories | Explicit destination required (changed) |
| `check_build14_private.py` | Yes — shared preflight | audit JSON; browser downloads and synthetic scratch kits use isolated temporary directories | Already explicit fresh output; optional screenshot writes nothing by default |
| `check_click_kit.py` | Yes — shared preflight | screenshot; browser downloads use isolated temporary files | Already explicit fresh output; optional screenshot writes nothing by default |
| `check_round2_kit.py` | Yes — shared preflight | screenshot | Already explicit fresh output; optional screenshot writes nothing by default |
| `compare_ball.py` | Yes — shared preflight | prefix .json/.md; --update-saved requires separate fresh --measurements-out | Explicit destination required (changed) |
| `compare_label_exports.py` | No — no file writes | stdout only | No file writes |
| `evaluate_round2.py` | Yes — shared preflight | evaluation marker; detections.json and suggestions.jsonl for all four fits | Per-fit outputs/markers; immutable single execution (unchanged) |
| `evaluate_round3.py` | Yes — shared preflight | evaluation marker; detections.json and suggestions.jsonl for both fits | Per-fit outputs/markers; immutable single execution (unchanged) |
| `evaluate_round4.py` | Yes — shared preflight | fit state, evaluation marker, fresh protocol snapshot, saved detections/suggestions | Per-fit outputs/markers; immutable single execution (unchanged) |
| `finish_round5.py` | Yes — shared preflight | both fit metrics-scored.json (trainer metrics.json preserved), round5-kit-suggestions.jsonl, round5-evidence.json | Per-fit outputs/markers; immutable single execution (unchanged) |
| `freeze_round5.py` | Yes — shared preflight | fresh --out bundle containing copied aggregate inputs, protocol/scored artifacts and generated ledger pair | Already explicit fresh output; optional screenshot writes nothing by default |
| `human_loop.py` | Yes — shared preflight | suggestion JSONL, .plan.json, optional --copy-to | Already explicit fresh output; optional screenshot writes nothing by default |
| `human_score.py` | Yes — guarded delegate | delegates to score_from_saved (prefix .json/.md) | Explicit destination required (changed) |
| `inspect_n21_adjudication.py` | Yes — shared preflight | required fresh --out directory: crops, contexts, sheets, audit JSON | Explicit destination required (changed) |
| `inspect_round5_distractor.py` | Yes — shared preflight | required fresh --out directory: crops, contexts, contact sheet, audit JSON | Explicit destination required (changed) |
| `n21_rule_sensitivity.py` | Yes — shared preflight | required fresh --out JSON; committed sensitivity stays read-only | Explicit destination required (changed) |
| `plot_round5.py` | Yes — shared preflight | PNG at --out | Already explicit fresh output; optional screenshot writes nothing by default |
| `review_round3.py` | Yes — shared preflight | fresh --out directory: historical/round2/round3 aggregates, scored metrics, evidence | Already explicit fresh output; optional screenshot writes nothing by default |
| `review_round4.py` | Yes — shared preflight | fresh --out directory: round4 aggregate, scored metrics, evidence | Already explicit fresh output; optional screenshot writes nothing by default |
| `review_round5.py` | Yes — shared preflight | fresh --out JSON; --freeze emits fresh gzip at --out, never the fixture | Already explicit fresh output; optional screenshot writes nothing by default |
| `round2_analysis.py` | Yes — shared preflight | fresh --out directory: scored metrics/evidence and round2 aggregate | Already explicit fresh output; optional screenshot writes nothing by default |
| `round2_people.py` | Yes — shared preflight | person-detection JSON | Explicit destination required (changed) |
| `round5_inference.py` | Yes — shared preflight | fresh pass directory with detections/suggestions; new evaluation marker preflight (existing marker is read/verified) | Already explicit fresh output; optional screenshot writes nothing by default |
| `round5_report.py` | Yes — shared preflight | prefix .json/.md | Already explicit fresh output; optional screenshot writes nothing by default |
| `run_ball.py` | Yes — shared preflight | fresh candidate directory: run.json, per-clip JSON, parity metadata | Explicit destination required (changed) |
| `run_round2.py` | Yes — shared preflight | four new fit directories, exclusive logs, fit-state and selection JSON | Per-fit outputs/markers; immutable single execution (unchanged) |
| `run_round3.py` | Yes — shared frozen-entry preflight | two new fit directories, exclusive logs, fit-state JSON | Per-fit outputs/markers; immutable single execution (unchanged) |
| `run_round4.py` | Yes — shared preflight | selected fresh fit directories and exclusive logs | Per-fit outputs/markers; immutable single execution (unchanged) |
| `run_round5.py` | Yes — shared preflight | protocol snapshot, fit-b directory/log, pass directories/logs (existing matching passes/logs rejected before orchestration) | Per-fit outputs/markers; immutable single execution (unchanged) |
| `score_from_saved.py` | Yes — shared preflight | prefix .json/.md | Explicit destination required (changed) |
| `smoke_tiny_ball.py` | Yes — shared preflight | fresh smoke directory, synthetic-label JSONL and provenance JSON | Already explicit fresh output; optional screenshot writes nothing by default |
| `throughput_round5.py` | Yes — shared preflight | timing JSON | Already explicit fresh output; optional screenshot writes nothing by default |
| `track_overlays.py` | Yes — shared preflight | required fresh --out directory, tracks/ child: images and provenance.json | Explicit destination required (changed) |
| `train_round5.py` | Yes — shared frozen-entry preflight | new fit directory: dataset, replay/history, checkpoints, weights, fit/metrics JSON | Already explicit fresh output; optional screenshot writes nothing by default |
| `train_tiny_ball.py` | Yes — shared frozen-entry preflight | new fit directory: dataset/crops/labels, training logs, weights, suggestions/detections, metrics; optional standard missing pretrained-weight download | Already explicit fresh output; optional screenshot writes nothing by default |
| `train_tiny_ball_rfdetr.py` | Yes — shared frozen-entry preflight | new fit directory: dataset/crops, history, checkpoints/weights, fit/metrics JSON | Already explicit fresh output; optional screenshot writes nothing by default |

Library write paths audited: `common.dump`, `human_loop.write_jsonl`,
`review_round3.freeze`, `compare_ball.update_saved`, `build_human_report.generate`,
`ball_truth_kit.build`, dataset/crop/checkpoint helpers in `rfdetr_data`,
`train_tiny_ball`, `train_tiny_ball_rfdetr`, `train_round5`, prediction helpers in
`evaluate_round4`/`round5_inference`, and image-generation helpers called by the
listed CLIs. Repeated writes to files newly created by the same run (run state,
training history, detections enriched with provenance) remain supported.

## Multi-step chain audit

Follow-up baseline: 7fddf297 (PR #1086). All chain tests are in
`test_pipeline_chains.py` and use fresh `tmp_path` directories. Numeric model and
capture computation is stubbed; orchestration, preflights, markers, serialization,
report formatting and downstream file reads execute. The trainer's final export
statements are taken from the frozen `train_round5.py` AST. Historical capture
export statements are also executed from their AST with synthetic numeric
results, rather than reimplementing their destination paths inside a mock.
These are pipeline I/O regressions, not model-training or inference validation.

| Documented chain | Test name | Stage-boundary proof |
|---|---|---|
| Round 5: training export → finish → review_round5 → round5_report | `test_train_finish_review_report_chain` | Trainer metrics exist before finish; both remain byte-identical, enriched metrics are fresh; saved provenance and evaluation marker validate; JSON/Markdown consumers complete; repeat finish refuses. RED on 7fddf297: metrics.json already exists. |
| run_round5 → train_round5 b → final passes (round5_inference) | `test_run_round5_marker_and_pass_chain` | Fit a completes first; b exports before either pass; shared marker is created once and verified on later passes; rerun refuses. |
| run_round2 → deferred trainer → evaluate_round2 → person proxy → round2_analysis | `test_historical_fit_evaluate_review_chain[round2]` | Four fits and TRAIN selection precede passes; marker/fit records survive; fresh scored artifacts cannot overwrite trainer metrics. |
| run_round3 → deferred trainer → evaluate_round3 → review_round3 | `test_historical_fit_evaluate_review_chain[round3]` | Both fits precede passes; marker survives; historical and current gzip captures plus scored metrics use fresh review directory. |
| run_round4 → RF trainer → evaluate_round4 → review_round4 | `test_historical_fit_evaluate_review_chain[round4]` | Continuation orchestration completes; evaluation snapshot is separate from input protocol; review outputs preserve trainer metrics. |
| Initial kit → human_loop saved suggestions/copy → new versioned kit | `test_suggestions_kit_refresh_chain` | CLI suggestion JSONL and plan can be generated after a kit exists; copy is byte-identical; refresh targets a separate kit and reuses shared frames. |
| Smoke proxy JSONL → trainer → saved scoring | `test_smoke_train_saved_score_chain` | Synthetic input/provenance precede fresh fit output; synthetic override is required at scoring; report outputs are fresh. The ordinary exported-label → train → score cycle uses the same trainer/suggestion boundaries; it is not executed on human data. |
| Saved runner output → update measurements → compare report → compare again | `test_saved_update_compare_chain` | Measurement input stays byte-identical; update writes new artifact; both reports agree. |
| score JSON → capture gzip/report; finish evidence + throughput + historical kit verification → freeze bundle → report regeneration | `test_capture_report_and_freeze_bundle_chain` | Fresh capture feeds report; fresh freeze bundle contains its own aggregate inputs; regeneration consumes that bundle and is byte-identical. Historical freeze still requires verified build-8 metadata. |
| Committed proxy fixtures → ledger | `test_proxy_ledger_regenerates_byte_identical` | Both JSON and Markdown match git bytes, including historical RF candidate order. |
| Repeated suggestions/private audit | `test_repeat_run_requires_explicit_destination` | No implicit existing path; parser requires --out before work. |

The README's standalone overlays/annotation/inspection commands consume saved
runs and emit a fresh image directory; they have no later stage writing into it.
Runner/device/parity, image rendering, saved-score validation, kit migration and
Chromium import/export have their existing focused tests in the full suite.
They are not training chains. `n21_rule_sensitivity` writes a fresh explicit JSON;
committed sensitivity is still read during ledger regeneration. No guard exemption
was added.

Consumer audit: no Python reader in ball/ loads round-5 `metrics.json`.
`review_round5`/`round5_report` use fit_summary + saved detections;
`finish_round5` emits aggregates directly to round5-evidence; `freeze_round5`
reads that evidence; `build_human_report`/plotting read aggregate fixtures.
For manual metrics inspection prefer metrics-scored.json, falling back to the
historical metrics.json if the new artifact is absent. No consumer needs the
trainer file rewritten. Round-4 review explicitly falls back to the committed
protocol when a fresh evaluation snapshot is absent. Committed fixtures and
hash-pinned trainers are unchanged.

## Fixed-destination sweep (G1–G3)

Baseline c159a78. The disposition column covers all 44 CLI entries.
Repeatable inspections, reports and audits require explicit destinations;
per-fit orchestrators deliberately bind immutable markers, logs and saved passes
to their declared fit identity. Their guards enumerate files/new fit directories,
not the shared root, so earlier-stage artifacts coexist without a bypass.

- G1: resolve all paths; reject equal/nested output pairs in either order, and
  outputs nested below existing or missing input files. Existing input directories
  can contain new outputs. Symlink aliases use the same ancestry rule.
- G2 inspections: inspect_n21_adjudication and inspect_round5_distractor require
  fresh --out directories. Normal and all-frames runs never claim ball-r5-n21.
  annotate_examples and track_overlays also require fresh --out directories.
- Sweep: check_build10/11/12/13_private and round2_people require --out;
  score_from_saved (including human_score delegate), compare_ball and
  build_human_report require --out-prefix; run_ball requires --report-dir;
  ball_truth_kit requires --out; any_ball_review requires --output/--kit/--sync.
  Existing label/kit protections are retained. Required parser paths are tested
  without opening real models, old kits or browsers.
- G3: review_round3.capture, review_round4.capture and round2_analysis.capture
  require keyword-only out, with all fallback writes removed. update_saved requires
  keyword-only out and guards it before loading input. Its save_measurements
  serializer also requires an explicit path and preflights it. build_human_report.generate
  requires out_prefix and guards both report files. Overlay generator destinations
  are required as well. n21_rule_sensitivity requires a fresh --out file.
- RED: 16 G1/G2/library cases and 16 sweep-parser cases fail on unchanged c159a78.
  GREEN adds fresh sensitivity output, symlinked input and positive input-directory
  cases. Real inspection rendering uses synthetic frames/labels in temporary HOME.
  The normal/all-frames/distractor runs each preserve a pre-existing evidence file,
  and each can run twice with separate destinations. No prior evidence is deleted.

## Non-directory ancestors (G4)

Every guarded output, including CLI-derived children, checks both supplied and
resolved ancestors before work. Existing non-directories (files, file symlinks,
dangling symlinks, FIFOs, etc.) refuse the run. Checking supplied ancestry retains
dangling links that realpath would otherwise erase. Real directories and symlinks
to real directories still permit fresh nested outputs. This remains preflight,
not protection against a filesystem change made after the check.

`test_guard_followup.py` adds seven G4 cases. On 2ca0fa75, five refusal tests
failed (the runner reached dataset and model stubs), while two legitimate nested
paths passed. With the guard fixed, all seven pass without model load or writes.
