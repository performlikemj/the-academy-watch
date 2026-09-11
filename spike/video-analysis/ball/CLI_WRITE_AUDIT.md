# Ball CLI write-path audit — follow-up to PR #1085

Baseline: main 6a2ae331. No kit rebuild, training, inference, or committed fixture
changes in this task. Tests use synthetic inputs and temporary copies.

`output_guard.guard_outputs()` resolves symlinks and `..`, rejects existing
files/directories (including dangling symlinks), fixture descendants, input
aliases, protected `~/codex-runs/ball-human-truth*.jsonl` names, and overlapping
input directories. Multi-file outputs are checked together before capture; a
fresh run directory owns its generated descendants and can update its own history.
CLI callers pass label/JSONL inputs. Library generation/dump/write helpers retain
their API for controlled temporary regeneration and within-run updates. This is
CLI preflight, not a filesystem sandbox or a lock against concurrent writers.

The migration CLI is unchanged under the explicit instruction to leave existing
no-overwrite CLIs such as `any_ball_review.py` as they are. Its intentional creation
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
fixture-overwrite exception to the shared guard. The n21 sensitivity fixture CLI still fails closed. Historical round-2/3/4
capture and round-5 freeze now require fresh output directories; inputs and
trainer metrics remain read-only. Report regeneration
must use a new output prefix, then compare bytes with the committed ledgers.

All CLI entry points are enumerated below. “Yes” covers their run-owned file
writes; browser temporary downloads and third-party caches are not user-selected
output targets. A library-only writer is covered by its calling CLI's preflight.

| CLI | Guarded? | Write paths |
|---|---|---|
| `annotate_examples.py` | Yes — shared preflight | `DEFAULT_REPORT/examples/` images |
| `any_ball_review.py` | Yes — existing safeguards (unchanged exception) | new migrated JSONL, kit and sync HTML/build/queue/suggestion/migration files |
| `ball_truth_kit.py` | Yes — shared preflight | fresh versioned output directory: index.html, build.json |
| `build_human_report.py` | Yes — shared preflight | prefix .json/.md; fresh --capture-out gzip; optional read-only --fixtures bundle |
| `check_any_ball_kit.py` | Yes — shared preflight | optional screenshot; browser downloads use isolated temporary files |
| `check_build10_private.py` | Yes — shared preflight | audit JSON; browser downloads and synthetic scratch kits use isolated temporary directories |
| `check_build11_private.py` | Yes — shared preflight | audit JSON; browser downloads and synthetic scratch kits use isolated temporary directories |
| `check_build12_private.py` | Yes — shared preflight | audit JSON; browser downloads and synthetic scratch kits use isolated temporary directories |
| `check_build13_private.py` | Yes — shared preflight | audit JSON; browser downloads and synthetic scratch kits use isolated temporary directories |
| `check_build14_private.py` | Yes — shared preflight | audit JSON; browser downloads and synthetic scratch kits use isolated temporary directories |
| `check_click_kit.py` | Yes — shared preflight | screenshot; browser downloads use isolated temporary files |
| `check_round2_kit.py` | Yes — shared preflight | screenshot |
| `compare_ball.py` | Yes — shared preflight | prefix .json/.md; --update-saved requires separate fresh --measurements-out |
| `compare_label_exports.py` | No — no file writes | stdout only |
| `evaluate_round2.py` | Yes — shared preflight | evaluation marker; detections.json and suggestions.jsonl for all four fits |
| `evaluate_round3.py` | Yes — shared preflight | evaluation marker; detections.json and suggestions.jsonl for both fits |
| `evaluate_round4.py` | Yes — shared preflight | fit state, evaluation marker, fresh protocol snapshot, saved detections/suggestions |
| `finish_round5.py` | Yes — shared preflight | both fit metrics-scored.json (trainer metrics.json preserved), round5-kit-suggestions.jsonl, round5-evidence.json |
| `freeze_round5.py` | Yes — shared preflight | fresh --out bundle containing copied aggregate inputs, protocol/scored artifacts and generated ledger pair |
| `human_loop.py` | Yes — shared preflight | suggestion JSONL, .plan.json, optional --copy-to |
| `human_score.py` | Yes — guarded delegate | delegates to score_from_saved (prefix .json/.md) |
| `inspect_n21_adjudication.py` | Yes — shared preflight | fresh ball-r5-n21 directory: crops, contexts, sheets, audit JSON |
| `inspect_round5_distractor.py` | Yes — shared preflight | fresh ball-r5-n21 directory: crops, contexts, contact sheet, audit JSON |
| `n21_rule_sensitivity.py` | Yes — shared preflight | fixed sensitivity fixture; preflight blocks entry |
| `plot_round5.py` | Yes — shared preflight | PNG at --out |
| `review_round3.py` | Yes — shared preflight | fresh --out directory: historical/round2/round3 aggregates, scored metrics, evidence |
| `review_round4.py` | Yes — shared preflight | fresh --out directory: round4 aggregate, scored metrics, evidence |
| `review_round5.py` | Yes — shared preflight | fresh --out JSON; --freeze emits fresh gzip at --out, never the fixture |
| `round2_analysis.py` | Yes — shared preflight | fresh --out directory: scored metrics/evidence and round2 aggregate |
| `round2_people.py` | Yes — shared preflight | person-detection JSON |
| `round5_inference.py` | Yes — shared preflight | fresh pass directory with detections/suggestions; new evaluation marker preflight (existing marker is read/verified) |
| `round5_report.py` | Yes — shared preflight | prefix .json/.md |
| `run_ball.py` | Yes — shared preflight | fresh candidate directory: run.json, per-clip JSON, parity metadata |
| `run_round2.py` | Yes — shared preflight | four new fit directories, exclusive logs, fit-state and selection JSON |
| `run_round3.py` | Yes — shared frozen-entry preflight | two new fit directories, exclusive logs, fit-state JSON |
| `run_round4.py` | Yes — shared preflight | selected fresh fit directories and exclusive logs |
| `run_round5.py` | Yes — shared preflight | protocol snapshot, fit-b directory/log, pass directories/logs (existing matching passes/logs rejected before orchestration) |
| `score_from_saved.py` | Yes — shared preflight | prefix .json/.md |
| `smoke_tiny_ball.py` | Yes — shared preflight | fresh smoke directory, synthetic-label JSONL and provenance JSON |
| `throughput_round5.py` | Yes — shared preflight | timing JSON |
| `track_overlays.py` | Yes — shared preflight | fresh DEFAULT_REPORT/tracks directory: images and provenance.json |
| `train_round5.py` | Yes — shared frozen-entry preflight | new fit directory: dataset, replay/history, checkpoints, weights, fit/metrics JSON |
| `train_tiny_ball.py` | Yes — shared frozen-entry preflight | new fit directory: dataset/crops/labels, training logs, weights, suggestions/detections, metrics; optional standard missing pretrained-weight download |
| `train_tiny_ball_rfdetr.py` | Yes — shared frozen-entry preflight | new fit directory: dataset/crops, history, checkpoints/weights, fit/metrics JSON |

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
They are not training chains. `n21_rule_sensitivity` remains a retired fixed-fixture
capture: the shared guard refuses it, and committed sensitivity is read during
ledger regeneration. No guard exemption was added.

Consumer audit: no Python reader in ball/ loads round-5 `metrics.json`.
`review_round5`/`round5_report` use fit_summary + saved detections;
`finish_round5` emits aggregates directly to round5-evidence; `freeze_round5`
reads that evidence; `build_human_report`/plotting read aggregate fixtures.
For manual metrics inspection prefer metrics-scored.json, falling back to the
historical metrics.json if the new artifact is absent. No consumer needs the
trainer file rewritten. Round-4 review explicitly falls back to the committed
protocol when a fresh evaluation snapshot is absent. Committed fixtures and
hash-pinned trainers are unchanged.
