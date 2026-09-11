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
fixture-overwrite exception to the shared guard. Legacy commands hard-coded to
rewrite fixtures now fail closed before their capture work. Report regeneration
must use a new output prefix, then compare bytes with the committed ledgers.

All CLI entry points are enumerated below. “Yes” covers their run-owned file
writes; browser temporary downloads and third-party caches are not user-selected
output targets. A library-only writer is covered by its calling CLI's preflight.

| CLI | Guarded? | Write paths |
|---|---|---|
| `annotate_examples.py` | Yes — shared preflight | `DEFAULT_REPORT/examples/` images |
| `any_ball_review.py` | Yes — existing safeguards (unchanged exception) | new migrated JSONL, kit and sync HTML/build/queue/suggestion/migration files |
| `ball_truth_kit.py` | Yes — shared preflight | fresh versioned output directory: index.html, build.json |
| `build_human_report.py` | Yes — shared preflight | prefix .json/.md; --capture fixture destination blocked |
| `check_any_ball_kit.py` | Yes — shared preflight | optional screenshot; browser downloads use isolated temporary files |
| `check_build10_private.py` | Yes — shared preflight | audit JSON; browser downloads and synthetic scratch kits use isolated temporary directories |
| `check_build11_private.py` | Yes — shared preflight | audit JSON; browser downloads and synthetic scratch kits use isolated temporary directories |
| `check_build12_private.py` | Yes — shared preflight | audit JSON; browser downloads and synthetic scratch kits use isolated temporary directories |
| `check_build13_private.py` | Yes — shared preflight | audit JSON; browser downloads and synthetic scratch kits use isolated temporary directories |
| `check_build14_private.py` | Yes — shared preflight | audit JSON; browser downloads and synthetic scratch kits use isolated temporary directories |
| `check_click_kit.py` | Yes — shared preflight | screenshot; browser downloads use isolated temporary files |
| `check_round2_kit.py` | Yes — shared preflight | screenshot |
| `compare_ball.py` | Yes — shared preflight | prefix .json/.md; --update-saved measurement write blocked |
| `compare_label_exports.py` | No — no file writes | stdout only |
| `evaluate_round2.py` | Yes — shared preflight | evaluation marker; detections.json and suggestions.jsonl for all four fits |
| `evaluate_round3.py` | Yes — shared preflight | evaluation marker; detections.json and suggestions.jsonl for both fits |
| `evaluate_round4.py` | Yes — shared preflight | fit state, evaluation marker, protocol fixture, saved detections/suggestions; fixture preflight blocks entry |
| `finish_round5.py` | Yes — shared preflight | both fit metrics.json, round5-kit-suggestions.jsonl, round5-evidence.json |
| `freeze_round5.py` | Yes — shared preflight | protocol/scored fixtures and generated ledger pair; fixture preflight blocks entry |
| `human_loop.py` | Yes — shared preflight | suggestion JSONL, .plan.json, optional --copy-to |
| `human_score.py` | Yes — guarded delegate | delegates to score_from_saved (prefix .json/.md) |
| `inspect_n21_adjudication.py` | Yes — shared preflight | fresh ball-r5-n21 directory: crops, contexts, sheets, audit JSON |
| `inspect_round5_distractor.py` | Yes — shared preflight | fresh ball-r5-n21 directory: crops, contexts, contact sheet, audit JSON |
| `n21_rule_sensitivity.py` | Yes — shared preflight | fixed sensitivity fixture; preflight blocks entry |
| `plot_round5.py` | Yes — shared preflight | PNG at --out |
| `review_round3.py` | Yes — shared preflight | historical/round2/round3 fixtures, fit metrics, evidence; fixture preflight blocks entry |
| `review_round4.py` | Yes — shared preflight | round4 fixture, fit metrics, evidence; fixture preflight blocks entry |
| `review_round5.py` | Yes — shared preflight | fresh --out JSON; --freeze emits fresh gzip at --out, never the fixture |
| `round2_analysis.py` | Yes — shared preflight | fit metrics/evidence and round2 measurement fixture; fixture preflight blocks entry |
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
