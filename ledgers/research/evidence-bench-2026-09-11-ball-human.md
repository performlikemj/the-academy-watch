Trainer swap — held-out top-1 real gate: **no candidate passes**.

No RF-DETR model qualifies at ≤2 false/10s; diagnostic recall leader: **tinyball-r4-rf-b**, H on-ball top-1 **74.59%**, manual-only 64.00%, **4.67 false/10s**, 3.72 FPS. Versus YOLO r2-b: **+6.56 percentage points** H on-ball recall.

Improvement under the required recall-and-false-rate rule: **none**. The RF-DETR product direction does not depend on YOLO winning this benchmark.

ultralytics is bench-only and must not enter the serving path; the product model is RF-DETR (Apache-2.0).

RF-DETR Nano uses the Apache-2.0 implementation and official COCO weights; the installed package licence is recorded with its hash in the execution fixture. [Upstream package and model licensing](https://github.com/roboflow/rf-detr#license).

# Trainer swap: RF-DETR versus YOLO11-nano

All = all 20 clips (incl. training clips); H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate). All / H always uses the same fixed 14/6 split. H has 244 visible / 60 no-ball labels overall, including 122 visible on-ball labels. These clips have also informed subsequent error analysis and model selection; H is optimistic and is not a clean test set.

Selection intentionally uses the highest H on-ball top-1 recall among RF runs with H strict false/10s ≤2. Selected estimates are optimistic by construction. Improvement requires beating r2-b's 68.03% H top-1 **without increasing** its 1.67 false/10s. The separate real gate remains ≥80% top-1 and ≤1 false/10s. No confidence-threshold search: every run uses ≥0.1 and inclusive 20 native px matching.

## Held-out headline, with training-inclusive results separate

| Candidate | H top-1 | H manual-only | H oracle over N boxes | Incl. training: All top-1 / manual / oracle | Boxes/visible on frame All / H | Strict false/10s All / H | FPS All / H | Gate All / H | Training min |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|
| tinyball-r2-b | 68.03% | 44.00% | 68.03% | 76.30% / 72.97% / 76.54% | 0.80 / 0.70 | 1.32 / 1.67 | 11.55 / 11.51 | FAIL / FAIL | 20.14 |
| tinyball-r3-a | 65.57% | 44.00% | 65.57% | 62.56% / 55.41% / 62.80% | 0.74 / 0.68 | 1.43 / 2.33 | 51.49 / 51.01 | FAIL / FAIL | 20.17 |
| tinyball-r3-b | 62.30% | 34.00% | 62.30% | 70.85% / 64.86% / 70.85% | 0.89 / 0.66 | 1.54 / 3.00 | 51.12 / 50.85 | FAIL / FAIL | 20.20 |
| tinyball-r4-rf-a | 71.31% | 56.00% | 72.13% | 86.02% / 84.46% / 86.73% | 1.08 / 1.02 | 5.49 / 7.33 | 9.13 / 9.16 | FAIL / FAIL | 29.01 |
| tinyball-r4-rf-b | 74.59% | 64.00% | 75.41% | 89.10% / 88.85% / 89.34% | 0.99 / 0.85 | 2.42 / 4.67 | 3.81 / 3.72 | FAIL / FAIL | 29.01 |

## Precision, localisation and overall detection

All = all 20 clips (incl. training clips); H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate). All / H always uses the same fixed 14/6 split. H has 244 visible / 60 no-ball labels overall, including 122 visible on-ball labels. These clips have also informed subsequent error analysis and model selection; H is optimistic and is not a clean test set.

| Candidate / group | Top-1 recall All / H | Manual-only top-1 All / H | Top-1 precision All / H | Oracle over N recall All / H | Oracle precision All / H | Top-1 median error px All / H | Oracle median error px All / H | Boxes/labelled frame All / H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| tinyball-r2-b / on_ball | 76.30% / 68.03% | 72.97% / 44.00% | 96.99% / 94.32% | 76.54% / 68.03% | 93.62% / 93.26% | 1.77 / 1.33 | 1.77 / 1.33 | 0.68 / 0.53 |
| tinyball-r2-b / all | 67.77% / 45.49% | 69.02% / 42.86% | 94.28% / 90.24% | 69.26% / 45.49% | 86.70% / 88.80% | 1.71 / 1.45 | 1.72 / 1.45 | 0.66 / 0.41 |
| tinyball-r3-a / on_ball | 62.56% / 65.57% | 55.41% / 44.00% | 97.06% / 95.24% | 62.80% / 65.57% | 83.33% / 93.02% | 1.51 / 1.12 | 1.43 / 1.12 | 0.63 / 0.51 |
| tinyball-r3-a / all | 59.89% / 52.46% | 53.15% / 37.66% | 87.48% / 76.65% | 62.29% / 54.92% | 74.25% / 71.66% | 1.40 / 1.26 | 1.40 / 1.26 | 0.69 / 0.62 |
| tinyball-r3-b / on_ball | 70.85% / 62.30% | 64.86% / 34.00% | 98.36% / 93.83% | 70.85% / 62.30% | 78.89% / 89.41% | 1.46 / 0.97 | 1.38 / 0.97 | 0.75 / 0.51 |
| tinyball-r3-b / all | 67.43% / 53.28% | 62.33% / 35.06% | 92.62% / 81.76% | 68.57% / 54.51% | 74.53% / 72.68% | 1.50 / 1.28 | 1.47 / 1.29 | 0.76 / 0.60 |
| tinyball-r4-rf-a / on_ball | 86.02% / 71.31% | 84.46% / 56.00% | 90.75% / 82.08% | 86.73% / 72.13% | 75.93% / 63.77% | 2.00 / 1.71 | 2.03 / 1.75 | 0.95 / 0.82 |
| tinyball-r4-rf-a / all | 81.37% / 49.59% | 87.38% / 55.84% | 86.72% / 63.35% | 82.17% / 50.82% | 73.29% / 51.03% | 2.09 / 1.84 | 2.09 / 1.86 | 0.93 / 0.80 |
| tinyball-r4-rf-b / on_ball | 89.10% / 74.59% | 88.85% / 64.00% | 96.66% / 90.10% | 89.34% / 75.41% | 88.71% / 82.88% | 1.92 / 1.38 | 1.91 / 1.36 | 0.84 / 0.66 |
| tinyball-r4-rf-b / all | 83.66% / 53.28% | 89.87% / 62.34% | 92.42% / 73.45% | 84.11% / 54.10% | 84.21% / 67.01% | 1.81 / 1.43 | 1.81 / 1.43 | 0.83 / 0.65 |

Top-1 precision counts one highest-confidence prediction per labelled frame, including false predictions on no-ball frames in that group. Oracle precision counts all emitted guesses in its denominator. All and H precision each use their own labels; no whole-corpus precision is paired with H recall. FPS includes native decoding, padding, inference and NMS; excludes loading/warmup and scoring/tracking. Historical YOLO timings were not rerun; runtime differences prevent attributing the entire FPS gap to architecture.

On-ball H manual-only recall is lower because MJ hand-clicked frames where no suggestion existed: a harder subset. This is expected difficulty confounding, not by itself evidence of model bias. Overall cohort comparisons also change clip composition and can reverse that ordering, as the overall RF rows show. Accepted-source provenance remains available; suggestions are unconfirmed and must never become automatic labels.

## No-ball and near-path sensitivity

All = all 20 clips (incl. training clips); H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate). All / H always uses the same fixed 14/6 split. H has 244 visible / 60 no-ball labels overall, including 122 visible on-ball labels. These clips have also informed subsequent error analysis and model selection; H is optimistic and is not a clean test set.

No-ball = no ball visible to the labeller. Every emitted box counts false, even a potentially correct ball MJ could not see. Path credits are only a sensitivity analysis (≤50px from a linear path bracketed by visible labels ≤1.01s apart), not verified invisible-ball detections; the gate uses strict counts.

| Candidate | False count / no-ball frames All / H | False/frame All / H | Strict false/10s All / H | Near-path credits All / H | Path-credited false/10s All / H |
|---|---:|---:|---:|---:|---:|
| tinyball-r2-b | 12/182 / 5/60 | 0.0659 / 0.0833 | 1.32 / 1.67 | 2 / 0 | 1.10 / 1.67 |
| tinyball-r3-a | 13/182 / 7/60 | 0.0714 / 0.1167 | 1.43 / 2.33 | 0 / 0 | 1.43 / 2.33 |
| tinyball-r3-b | 14/182 / 9/60 | 0.0769 / 0.1500 | 1.54 / 3.00 | 1 / 0 | 1.43 / 3.00 |
| tinyball-r4-rf-a | 50/182 / 22/60 | 0.2747 / 0.3667 | 5.49 / 7.33 | 3 / 0 | 5.16 / 7.33 |
| tinyball-r4-rf-b | 22/182 / 14/60 | 0.1209 / 0.2333 | 2.42 / 4.67 | 3 / 1 | 2.09 / 4.33 |

## Exact fit configurations and training-only scale rule

Both fits were specified before evaluation. No alternative floor was tried. Affine(y) = -12.4205756808 + 0.04820986555 × native image y; TRAIN-only R²=0.4943506566, 545 matched observations from 631 visible training labels. Every target is clamp(affine(y), 18.6804351807, 48) px. This deliberately supersedes round 3's direct matched-size override. 592/631 targets sit at the floor, 23 are ≥24px; median 18.68px, maximum 32.85px. Box extents are teacher estimates associated with human clicks, not manually drawn ball boundaries.

Native 2×2 tiles are 960×540, padded below with 420px RGB114 to 960×960. At 640, content is 640×360 and minimum target 12.45px; at 960, content is 960×540 and minimum target 18.68px. No anisotropic squash. Each fit uses 3012 training tiles: 631 positive/2381 negative. No held-out or unlabelled frame is a training negative. Pseudo-labels were off and require --pseudo.

| Fit | Class / square resolution | Initialization | Batch / accumulation | Complete epochs + partial tiles | Final optimizer steps | MPS training minutes | LR / encoder LR | Seed |
|---|---|---|---:|---:|---:|---:|---|---:|
| a | RFDETRNano / 640 | COCO Nano | 8 / 1 | 2 + 3000/3012 | 1129 | 29.01 | 0.0001 / 0.00015 | 42 |
| b | RFDETRNano / 960 | a final checkpoint; fresh optimizer | 8 / 1 | 1 + 1016/3012 | 504 | 29.01 | 5e-05 / 7.5e-05 | 42 |

Run b adds 29.01 training minutes after a; cumulative a→b cost is 58.02 minutes. Model loading, dataset preparation and later inference are outside these training timers.

AdamW, weight decay 0.0001; RF-DETR official encoder layer decay 0.8 and decoder component decay 0.7; 100-step linear warmup, constant thereafter (epoch100 step decay is configured but not reached). Gradient norm clip 0.1, FP32, no EMA, horizontal flip 0.5 only. 100 epochs requested, 29-minute fit cap with six complete TRAIN-epoch patience. Final parameters at the last optimizer step are exported, including a budget-ended partial epoch; no minimum-loss checkpoint is restored. Final/partial epoch losses and full package/configuration provenance are retained in JSON. MPS deterministic algorithms warn where kernels cannot be deterministic.

### Train clip ids

- `m04-n02-t3005-474114-478131`
- `m04-n03-t1406-157170-158922`
- `m04-n03-t1406-385962-387137`
- `m04-n04-t3006-243433-247994`
- `m04-n04-t3006-307417-310307`
- `m04-n09-t1409-143096-143834`
- `m04-n09-t1409-297601-298865`
- `m04-n09-t1409-385922-386603`
- `m04-n10-t711-186553-188161`
- `m04-n12-t1411-237107-242145`
- `m04-n15-t3010-164698-170777`
- `m04-n17-t717-304624-307834`
- `m04-n22-t3012-070707-074371`
- `m04-n25-t3014-530600-532465`

### held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate): clip ids

- `m04-n05-t3007-284945-287898`
- `m04-n12-t1411-679986-681985`
- `m04-n17-t717-253073-260377`
- `m04-n17-t717-416826-418915`
- `m04-n21-t3011-390297-390800`
- `m04-n24-t3013-679939-681217`

## Size buckets: highest-confidence hits / visible labels

All = all 20 clips (incl. training clips); H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate). All / H always uses the same fixed 14/6 split. H has 244 visible / 60 no-ball labels overall, including 122 visible on-ball labels. These clips have also informed subsequent error analysis and model selection; H is optimistic and is not a clean test set.

Sizes are the same frozen independent RF full/2×2/3×3 matched-box short-side median used in round 3. RF-DETR's learned target sizes do not define these buckets. Missing teacher matches remain unknown; excluding them would flatter recall.

| Candidate | <6px All / H | 6–<10px All / H | 10–<16px All / H | 16–<24px All / H | ≥24px All / H | Unknown All / H |
|---|---:|---:|---:|---:|---:|---:|
| tinyball-r2-b | 9/11 / 0/1 | 162/210 / 27/39 | 97/122 / 34/46 | 22/22 / 3/3 | 19/23 / 18/22 | 13/34 / 1/11 |
| tinyball-r3-a | 6/11 / 0/1 | 142/210 / 24/39 | 79/122 / 34/46 | 17/22 / 3/3 | 20/23 / 19/22 | 0/34 / 0/11 |
| tinyball-r3-b | 8/11 / 0/1 | 149/210 / 20/39 | 91/122 / 34/46 | 22/22 / 3/3 | 20/23 / 19/22 | 9/34 / 0/11 |
| tinyball-r4-rf-a | 9/11 / 0/1 | 189/210 / 28/39 | 111/122 / 41/46 | 22/22 / 3/3 | 13/23 / 12/22 | 19/34 / 3/11 |
| tinyball-r4-rf-b | 9/11 / 0/1 | 196/210 / 33/39 | 117/122 / 42/46 | 21/22 / 3/3 | 12/23 / 11/22 | 21/34 / 2/11 |

## Matching-rule sanity floors

All = all 20 clips (incl. training clips); H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate). All / H always uses the same fixed 14/6 split. H has 244 visible / 60 no-ball labels overall, including 122 visible on-ball labels. These clips have also informed subsequent error analysis and model selection; H is optimistic and is not a clean test set.

Same permanent seed 20260911, 100 repetitions; corrupt label positions within each evaluation scope while keeping detections fixed. Means below are sanity floors, not alternate truth or a threshold-tuning set.

| RF candidate / control | On-ball top-1 mean All / H | On-ball oracle mean All / H |
|---|---:|---:|
| tinyball-r4-rf-a / shuffled_within_clip | 4.16% / 2.24% | 4.32% / 2.44% |
| tinyball-r4-rf-a / uniform_random | 0.06% / 0.02% | 0.07% / 0.02% |
| tinyball-r4-rf-b / shuffled_within_clip | 4.11% / 2.17% | 4.25% / 2.31% |
| tinyball-r4-rf-b / uniform_random | 0.06% / 0.03% | 0.07% / 0.05% |

## Track versus truth

All = all 20 clips (incl. training clips); H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate). All / H always uses the same fixed 14/6 split. H has 244 visible / 60 no-ball labels overall, including 122 visible on-ball labels. These clips have also informed subsequent error analysis and model selection; H is optimistic and is not a clean test set.

No eligible licence-clean model: show the RF recall leader diagnostically alongside YOLO r2-b.

| Candidate | Coverage All / H | Longest correct run seconds All / H | Wrong frames All / H | Track points on visible labels All / H | Wrong/track-point All / H | Track precision All / H | Wrong episodes All / H |
|---|---:|---:|---:|---:|---:|---:|---:|
| tinyball-r2-b | 58.29% / 36.89% | 24.00 / 2.50 | 39 / 14 | 618 / 118 | 6.31% / 11.86% | 82.52% / 76.27% | 28 / 9 |
| tinyball-r4-rf-b | 67.20% / 44.67% | 24.50 / 6.00 | 68 / 41 | 773 / 165 | 8.80% / 24.85% | 76.07% / 66.06% | 43 / 22 |

Unchanged Kalman parameters; correct≤20px, wrong>50px. Rates use emitted track points when a visible label exists; no-ball track points are outside this precision denominator. Coverage penalises silence, so a sparse track cannot claim quality from a small wrong count alone.

## Verdict, next experiment and footage

RF-DETR b exceeds YOLO r2-b on H top-1 recall: 74.59% versus 68.03% (+6.56pp), and manual-only 64% versus 44% (+20pp). It does not match the full operating point: strict H false/10s is 4.67 versus 1.67 (+3.00,2.8×), top-1 on-ball precision 90.10% versus 94.32%, and measured H FPS 3.72 versus 11.51 (historical YOLO timing). Path credit only reduces RF b to 4.33. Both RF runs FAIL the ≥80%/≤1 gate and exceed the ≤2 selection ceiling; no qualifying current best licence-clean model and no improvement under the specified rule. RF b is the diagnostic recall leader, not a selected product-ready checkpoint. The product path remains RF-DETR; YOLO remains bench-only.

Next RF experiment: retain Nano at 960 and train longer with TRAIN-only hard-negative replay and stronger large/near-ball supervision; freeze the protocol before evaluating fresh club footage. RF b still makes 8 false detections on 122 TRAIN no-ball frames (1.31/10s), so negative fitting is unfinished; H false rate is 4.67. Merely increasing input resolution did not fix the large-ball bucket (12/22→11/22) while small-ball hits improved 28/39→33/39. The training split contains only one independently estimated ≥24px on-ball label, and the affine-floor rule assigns it 18.68px; H has 22 such labels with observed median 31.07px versus rule median 23.11px. This supports collecting accurate large-ball boxes and hard negatives before choosing a bigger backbone. Longer training is a next experiment, not a claimed cure; the All/H gap means more epochs alone may overfit.

Better footage would multiply ball pixels, but it is not an established fix on its own. Historical r2-d's 2×-pixels extrapolation was 60.7→66.4% H oracle recall, not measured 4K performance. Size-bucket associations are confounded by distance, occlusion and teacher-matched selection. They neither predict false rates nor establish an 80%/1-false gate pass. Fresh labelled 4K/follow-cam club clips must be reserved as the true test.

## Kit and execution caveats

Unchanged: neither RF model satisfies the improvement rule. Build 7 retains 636 bench-only mj-r2-b suggestions and all 1057 seed labels; 48 frames remain unlabelled. MJ can finish those frames, but fresh labelled club clips must form the true holdout. No kit regeneration or suggestion copy was performed this round.

- Exactly two fits, both specified before any new held-out inference. No floor sweep: use the brief’s 18.68px starting floor and fit the affine relationship on TRAIN labels only.
- RFDETRNano at 640 first to obtain more updates within the MPS budget; then continue its final weights at 960 for 1.5× effective ball pixels. Native 960×540 crops are padded below to 960 square and resized uniformly, without anisotropic squash.
- Use the RF-DETR model/criterion and official layer-wise AdamW groups in an explicit PyTorch loop. No Lightning validation callback, EMA or held-out loader. Only complete TRAIN-epoch losses affect patience 6; the time budget stops at an optimizer-step boundary. Export final parameters.
- The documented .venv-bench environments were missing. Restored rfdetr[train]==1.7.1 in external ~/models/tinyball/.venv-mj; pinned RF requirements are separate from bench-only YOLO requirements.
- Name the RF run with highest H on-ball top-1 recall subject to H no-ball false/10s≤2 as current best licence-clean model. This selects on reused held-out data and is optimistic. If none qualifies, report no eligible model and label the recall leader diagnostic.
- An RF run only improves on r2-b when H on-ball top-1 recall exceeds 68.0327868852459% and H false/10s does not exceed 1.6666666666666667. The real gate is separately ≥80% and ≤1. Refresh the kit only for an RF improvement.
- Manual-labelled frames are harder: MJ hand-clicked where no suggestion existed. Lower manual-only recall is expected difficulty confounding, not by itself evidence of model bias. Preserve accepted-source provenance for future analysis.
- These 20 clips are no longer a clean test set; fresh labelled club footage is the true holdout. Better footage may help but has not been shown to solve the gate.
- RF versus historical YOLO also changes architecture, optimizer schedule, augmentation (horizontal flips only), and final versus minimum-TRAIN-loss checkpoint selection. This is a pipeline comparison, not an isolated target-floor ablation.
- Run b adds up to 29 minutes after run a. Report its additional and cumulative training cost; it is not an independent COCO fit.
- Run a completed 29.01min and 1129 optimizer steps: two complete epochs plus 3000/3012 tiles in the third. Epoch means 15.1164 and 3.8186; final partial 3.6290. Time-capped RF sees fewer passes than historical r2-b’s 10 epochs; this is not an architecture ceiling.
- Run b first complete epoch mean TRAIN loss 3.6718; final checkpoint remains budget-ended parameters, not a comparison of minima across the two resolutions.
- Measured RF inference uses eager FP32 MPS, batch of four padded tiles per frame, and NMS 0.5; optimize_for_inference was not called. FPS includes source decoding and padding, excludes loading/warmup, scoring and tracking. No own training overlaps these timed passes.
- Exactly two fits completed. No further training, threshold search or inference optimization after evaluation; saved scoring adds only a post-fit affine-scale diagnostic, without changing any target or checkpoint.

Verification: PASS: pytest409 worktree /409 git-archive export; minimal Python3.11 archive406 passed +3 expected OpenCV skips. Ruff check and ruff format --check passed in worktree and archive; mypy passed. JSON and Markdown regenerate byte-for-byte from committed aggregates with no labels, footage or weights. Both actual final checkpoints verified (a step1129, b step504; finite parameters and correct resolution/class metadata). Final staged-tree verification repeats after recording these results; commit/clean-status receipt stays outside git.

Not done:

- RF-DETR does not match the full YOLO operating point; no RF run qualifies at ≤2 false/10s and no model passes the real gate.
- No serving deployment, threshold tuning, inference optimization or third fit. Ultralytics remains bench-only.
- 48 frozen frames remain unlabelled; no fresh labelled club-footage holdout or measured 4K/follow-cam test.
- Large-ball supervision remains weak; more epochs, hard-negative replay and accurate large-ball boxes are proposed, not executed.

# Historical rounds 1–3 (retained verbatim)

The current product direction and round 4 verdict above supersede historical current-best and proposed-next-experiment statements below. Historical tables retain their original measurements and caveats.

Human top-1 gate: **no candidate passes**. Proxy verdicts retire for this labelled sample.

Current best under the authorized ≤2 false/10s selection rule: **tinyball-r2-b**. H on-ball top-1 **68.03%**, oracle over N boxes 68.03%, oracle precision 93.26%, **1.67 false/10s**, 11.51 FPS; real gate **FAIL**.

held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate). **Current-best selection now uses held-out results and is optimistic beyond that prior exposure.** Fresh labelled club footage is the true test; these 20 clips are no longer a clean test set.

# Ball human truth — round 3 review and scale targets

Gate = highest-confidence top-1 on-ball recall ≥80% AND ≤1 detection/10s on explicit no-ball frames. Model eligibility at ≤2 false/10s is a separate selection rule, not a PASS. Matching is inclusive 20 native px at confidence ≥0.1; ties use saved order. Oracle precision credits at most one nearest box per visible label and penalises all duplicate guesses. Top-1 precision is reported separately below. Boxes/frame in headlines uses visible on-ball frames, matching the reviewer; JSON also retains boxes per all labelled frames.

## Corrected round-1 headline (original 4/16 split)

H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate): original 16 evaluation clips for this table, 575 visible / 144 no-ball. On-ball H is the same two clips and 122 visible labels used below. Baselines are filtered to those same clips for comparability; none was fitted on this dataset. The All column preserves the reviewer’s six-on-ball-clip ranking.

| Candidate | H top-1 (manual-only) | H oracle over N boxes (manual-only) | H oracle precision | H boxes/visible on frame | H false/10s | H FPS | H gate | Incl. training clips: top-1 (manual) / oracle | All boxes / false/10s / FPS / gate |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| rf_full | 53.28% (24.00%) | 62.30% (36.00%) | 10.94% | 4.20 | 72.64 | 26.63 | FAIL | 43.36% (32.09%) / 57.58% (49.32%) | 4.73 / 72.75 / 26.88 / FAIL |
| rf_2x2 | 76.23% (50.00%) | 84.43% (64.00%) | 9.17% | 6.53 | 117.64 | 8.30 | FAIL | 67.77% (56.76%) / 83.18% (76.35%) | 7.80 / 118.35 / 8.33 / FAIL |
| rf_3x3 | 80.33% (56.00%) | 86.89% (70.00%) | 6.23% | 9.84 | 186.53 | 1.53 | FAIL | 74.17% (64.19%) / 87.20% (82.43%) | 10.81 / 192.42 / 1.57 / FAIL |
| wasb | 3.28% (2.00%) | 3.28% (2.00%) | 6.56% | 0.38 | 5.83 | 37.39 | FAIL | 3.55% (3.04%) / 3.55% (3.04%) | 0.28 / 5.38 / 37.90 / FAIL |
| wasb_2x2 | 10.66% (14.00%) | 22.13% (20.00%) | 9.96% | 1.64 | 22.92 | 12.83 | FAIL | 11.37% (10.81%) / 18.25% (15.88%) | 1.33 / 22.86 / 12.90 / FAIL |
| tinyball-r1 | 54.10% (50.00%) | 54.10% (50.00%) | 78.57% | 0.64 | 4.03 | 49.92 | FAIL | 75.36% (77.36%) / 75.36% (77.36%) | 0.84 / 3.74 / 51.51 / FAIL |
| tinyball-r1-960 | 58.20% (46.00%) | 59.02% (46.00%) | 83.72% | 0.64 | 2.64 | 37.35 | FAIL | 77.49% (78.04%) / 77.73% (78.04%) | 0.83 / 2.42 / 37.90 / FAIL |

Round-1 r1-960 was previously presented using 300 training on-ball labels plus 122 held-out labels. Its honest pipeline recall is **58.20% top-1 held-out**, versus 59.02% oracle; oracle precision on those same on-ball labels is 83.72%. All-clip 77.49% top-1 and 77.73% oracle are resubstitution-contaminated. Among round-1 candidates, r1-960 has the highest All on-ball top-1 recall; rf_3x3 falls from 87.20% oracle to 74.17% top-1 and fails the recall leg on all six on-ball clips.

## Corrected round-2 and new scale-run headline (common 14/6 split)

All = all 20 clips (incl. training clips); H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate), using the fixed six clips unless explicitly stated otherwise. Paired cells are All / H.

| Candidate | H top-1 (manual-only) | H oracle over N boxes (manual-only) | H oracle precision | H boxes/visible on frame | H false/10s | H FPS | H gate | Incl. training clips: top-1 (manual) / oracle | All boxes / false/10s / FPS / gate |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| rf_full | 53.28% (24.00%) | 62.30% (36.00%) | 10.94% | 4.20 | 87.67 | 26.86 | FAIL | 43.36% (32.09%) / 57.58% (49.32%) | 4.73 / 72.75 / 26.88 / FAIL |
| rf_2x2 | 76.23% (50.00%) | 84.43% (64.00%) | 9.17% | 6.53 | 153.33 | 8.28 | FAIL | 67.77% (56.76%) / 83.18% (76.35%) | 7.80 / 118.35 / 8.33 / FAIL |
| rf_3x3 | 80.33% (56.00%) | 86.89% (70.00%) | 6.23% | 9.84 | 233.67 | 1.33 | FAIL | 74.17% (64.19%) / 87.20% (82.43%) | 10.81 / 192.42 / 1.57 / FAIL |
| wasb | 3.28% (2.00%) | 3.28% (2.00%) | 6.56% | 0.38 | 8.33 | 37.71 | FAIL | 3.55% (3.04%) / 3.55% (3.04%) | 0.28 / 5.38 / 37.90 / FAIL |
| wasb_2x2 | 10.66% (14.00%) | 22.13% (20.00%) | 9.96% | 1.64 | 29.67 | 12.82 | FAIL | 11.37% (10.81%) / 18.25% (15.88%) | 1.33 / 22.86 / 12.90 / FAIL |
| tinyball-r1 | 54.10% (50.00%) | 54.10% (50.00%) | 78.57% | 0.64 | 2.33 | 49.90 | FAIL | 75.36% (77.36%) / 75.36% (77.36%) | 0.84 / 3.74 / 51.51 / FAIL |
| tinyball-r1-960 | 58.20% (46.00%) | 59.02% (46.00%) | 83.72% | 0.64 | 3.00 | 38.18 | FAIL | 77.49% (78.04%) / 77.73% (78.04%) | 0.83 / 2.42 / 37.90 / FAIL |
| tinyball-r2-a | 69.67% (56.00%) | 71.31% (56.00%) | 82.86% | 0.83 | 3.00 | 11.92 | FAIL | 74.64% (71.28%) / 75.12% (71.28%) | 0.86 / 2.97 / 11.85 / FAIL |
| tinyball-r2-b | 68.03% (44.00%) | 68.03% (44.00%) | 93.26% | 0.70 | 1.67 | 11.51 | FAIL | 76.30% (72.97%) / 76.54% (73.31%) | 0.80 / 1.32 / 11.55 / FAIL |
| tinyball-r2-c | 65.57% (56.00%) | 65.57% (56.00%) | 86.96% | 0.71 | 2.33 | 8.58 | FAIL | 80.57% (80.07%) / 80.57% (80.07%) | 0.86 / 2.09 / 8.53 / FAIL |
| tinyball-r2-d | 60.66% (46.00%) | 60.66% (46.00%) | 84.09% | 0.68 | 3.33 | 5.95 | FAIL | 75.83% (73.99%) / 76.30% (74.32%) | 0.83 / 1.98 / 4.65 / FAIL |
| tinyball-r3-a | 65.57% (44.00%) | 65.57% (44.00%) | 93.02% | 0.68 | 2.33 | 51.01 | FAIL | 62.56% (55.41%) / 62.80% (55.41%) | 0.74 / 1.43 / 51.49 / FAIL |
| tinyball-r3-b | 62.30% (34.00%) | 62.30% (34.00%) | 89.41% | 0.66 | 3.00 | 50.85 | FAIL | 70.85% (64.86%) / 70.85% (64.86%) | 0.89 / 1.54 / 51.12 / FAIL |

The all-clip columns are descriptive training-inclusive numbers. H false rates use 60 no-ball labels across all six H clips, while H recall/precision in the headline use the two on-ball clips. This is the predefined gate scope, not a mixture of training/test precision. FPS includes decode + inference and excludes loading, warmup, scoring and tracking. Baseline/R1/R2 timings are historical saved-pass measurements, not contemporaneous speed controls.

## Precision, localisation and no-ball exposure

All = all 20 clips (incl. training clips); H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate), using the fixed six clips unless explicitly stated otherwise. Paired cells are All / H.

| Candidate | On top-1 precision All / H | On oracle precision All / H | On top-1 median error px All / H | On oracle median error px All / H | No-ball false/frame All / H | No-ball counts All / H |
|---|---:|---:|---:|---:|---:|---:|
| rf_full | 37.42% / 40.37% | 10.49% / 10.94% | 1.59 / 1.07 | 1.86 / 1.25 | 3.6374 / 4.3833 | 662/182 / 263/60 |
| rf_2x2 | 56.97% / 56.02% | 9.13% / 9.17% | 1.20 / 0.46 | 1.43 / 0.52 | 5.9176 / 7.6667 | 1077/182 / 460/60 |
| rf_3x3 | 61.86% / 58.33% | 6.73% / 6.23% | 1.24 / 0.00 | 1.49 / 0.00 | 9.6209 / 11.6833 | 1751/182 / 701/60 |
| wasb | 10.56% / 6.56% | 10.56% / 6.56% | 3.44 / 5.38 | 3.44 / 5.38 | 0.2692 / 0.4167 | 49/182 / 25/60 |
| wasb_2x2 | 12.28% / 9.09% | 11.41% / 9.96% | 2.09 / 2.10 | 2.08 / 1.81 | 1.1429 / 1.4833 | 208/182 / 89/60 |
| tinyball-r1 | 93.53% / 84.62% | 86.89% / 78.57% | 1.79 / 1.30 | 1.79 / 1.30 | 0.1868 / 0.1167 | 34/182 / 7/60 |
| tinyball-r1-960 | 94.78% / 84.52% | 90.36% / 83.72% | 1.84 / 1.42 | 1.82 / 1.46 | 0.1209 / 0.1500 | 22/182 / 9/60 |
| tinyball-r2-a | 94.59% / 89.47% | 86.14% / 82.86% | 1.87 / 1.20 | 1.87 / 1.25 | 0.1484 / 0.1500 | 27/182 / 9/60 |
| tinyball-r2-b | 96.99% / 94.32% | 93.62% / 93.26% | 1.77 / 1.33 | 1.77 / 1.33 | 0.0659 / 0.0833 | 12/182 / 5/60 |
| tinyball-r2-c | 97.42% / 94.12% | 91.40% / 86.96% | 1.78 / 1.48 | 1.77 / 1.48 | 0.1044 / 0.1167 | 19/182 / 7/60 |
| tinyball-r2-d | 95.81% / 91.36% | 89.44% / 84.09% | 1.79 / 1.15 | 1.77 / 1.15 | 0.0989 / 0.1667 | 18/182 / 10/60 |
| tinyball-r3-a | 97.06% / 95.24% | 83.33% / 93.02% | 1.51 / 1.12 | 1.43 / 1.12 | 0.0714 / 0.1167 | 13/182 / 7/60 |
| tinyball-r3-b | 98.36% / 93.83% | 78.89% / 89.41% | 1.46 / 0.97 | 1.38 / 0.97 | 0.0769 / 0.1500 | 14/182 / 9/60 |

| Candidate / group | Pooled top-1 All / H | Manual-only top-1 All / H | Oracle over N boxes All / H | Manual-only oracle All / H | Oracle precision All / H | False/10s All / H |
|---|---:|---:|---:|---:|---:|---:|
| rf_full / all | 45.37% / 53.69% | 33.84% / 25.97% | 62.51% / 67.62% | 52.01% / 36.36% | 10.55% / 11.04% | 72.75 / 87.67 |
| rf_full / off_pitch | 63.75% / 82.61% | 42.59% / 0.00% | 80.00% / 93.48% | 66.67% / 0.00% | 15.63% / 19.82% | 39.62 / 24.00 |
| rf_2x2 / all | 65.71% / 71.31% | 54.68% / 50.65% | 86.51% / 86.89% | 80.31% / 70.13% | 9.19% / 9.87% | 118.35 / 153.33 |
| rf_2x2 / off_pitch | 77.50% / 91.30% | 51.85% / 100.00% | 96.25% / 100.00% | 90.74% / 100.00% | 13.65% / 22.22% | 37.74 / 32.00 |
| rf_3x3 / all | 71.09% / 78.28% | 59.85% / 57.14% | 89.37% / 90.57% | 83.75% / 75.32% | 6.80% / 7.04% | 192.42 / 233.67 |
| rf_3x3 / off_pitch | 80.00% / 100.00% | 46.30% / 100.00% | 93.75% / 100.00% | 81.48% / 100.00% | 8.68% / 14.56% | 129.43 / 188.00 |
| wasb / all | 4.69% / 2.46% | 4.40% / 2.60% | 4.69% / 2.46% | 4.40% / 2.60% | 10.17% / 4.29% | 5.38 / 8.33 |
| wasb / off_pitch | 3.75% / 2.17% | 1.85% / 0.00% | 3.75% / 2.17% | 1.85% / 0.00% | 6.59% / 3.33% | 5.28 / 16.00 |
| wasb_2x2 / all | 9.94% / 6.56% | 9.18% / 9.09% | 15.77% / 13.52% | 13.77% / 15.58% | 11.38% / 8.07% | 22.86 / 29.67 |
| wasb_2x2 / off_pitch | 4.38% / 0.00% | 3.70% / 0.00% | 6.25% / 0.00% | 7.41% / 0.00% | 6.54% / 0.00% | 14.34 / 32.00 |
| tinyball-r1 / all | 58.51% / 33.20% | 65.39% / 41.56% | 59.09% / 33.61% | 66.16% / 41.56% | 76.71% / 73.21% | 3.74 / 2.33 |
| tinyball-r1 / off_pitch | 35.00% / 6.52% | 35.19% / 100.00% | 36.25% / 6.52% | 38.89% / 100.00% | 61.70% / 42.86% | 4.15 / 0.00 |
| tinyball-r1-960 / all | 60.57% / 36.48% | 65.58% / 38.96% | 61.71% / 36.89% | 66.35% / 38.96% | 81.08% / 82.57% | 2.42 / 3.00 |
| tinyball-r1-960 / off_pitch | 38.75% / 8.70% | 44.44% / 100.00% | 42.50% / 8.70% | 51.85% / 100.00% | 67.33% / 80.00% | 1.89 / 4.00 |
| tinyball-r2-a / all | 71.66% / 52.87% | 71.70% / 49.35% | 73.60% / 54.92% | 73.23% / 50.65% | 72.20% / 67.68% | 2.97 / 3.00 |
| tinyball-r2-a / off_pitch | 73.75% / 47.83% | 81.48% / 100.00% | 78.75% / 52.17% | 87.04% / 100.00% | 64.95% / 58.54% | 1.89 / 12.00 |
| tinyball-r2-b / all | 67.77% / 45.49% | 69.02% / 42.86% | 69.26% / 45.49% | 70.55% / 42.86% | 86.70% / 88.80% | 1.32 / 1.67 |
| tinyball-r2-b / off_pitch | 63.75% / 15.22% | 79.63% / 100.00% | 66.25% / 15.22% | 85.19% / 100.00% | 84.80% / 77.78% | 0.00 / 0.00 |
| tinyball-r2-c / all | 69.49% / 43.03% | 75.53% / 53.25% | 70.40% / 43.44% | 76.48% / 53.25% | 86.15% / 80.92% | 2.09 / 2.33 |
| tinyball-r2-c / off_pitch | 53.12% / 8.70% | 68.52% / 100.00% | 55.62% / 8.70% | 75.93% / 100.00% | 81.65% / 44.44% | 0.75 / 8.00 |
| tinyball-r2-d / all | 68.00% / 40.98% | 72.08% / 46.75% | 69.83% / 41.80% | 73.80% / 46.75% | 80.71% / 72.86% | 1.98 / 3.33 |
| tinyball-r2-d / off_pitch | 58.75% / 10.87% | 75.93% / 100.00% | 64.38% / 13.04% | 87.04% / 100.00% | 67.32% / 46.15% | 1.51 / 8.00 |
| tinyball-r3-a / all | 59.89% / 52.46% | 53.15% / 37.66% | 62.29% / 54.92% | 55.83% / 40.26% | 74.25% / 71.66% | 1.43 / 2.33 |
| tinyball-r3-a / off_pitch | 73.12% / 58.70% | 64.81% / 100.00% | 78.75% / 67.39% | 74.07% / 100.00% | 74.12% / 72.09% | 0.38 / 0.00 |
| tinyball-r3-b / all | 67.43% / 53.28% | 62.33% / 35.06% | 68.57% / 54.51% | 63.48% / 36.36% | 74.53% / 72.68% | 1.54 / 3.00 |
| tinyball-r3-b / off_pitch | 74.38% / 60.87% | 64.81% / 0.00% | 77.50% / 65.22% | 70.37% / 0.00% | 73.37% / 65.22% | 1.13 / 4.00 |

## Permanent matching-rule controls

All = all 20 clips (incl. training clips); H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate), using the fixed six clips unless explicitly stated otherwise. Paired cells are All / H.

Corrupt visible human centres only; keep detections/confidences/timestamps/no-ball labels fixed. Ordinary within-clip permutation (fixed points allowed) or independent uniform native 1920x1080 centres. Same seeded draws for every candidate. Report mean/min/max across 100 repeats; oracle over N boxes and top-1 separately. No tracks or model inference. Reviewer gave ranges without a seed; these newly specified controls may differ.

Reviewer reference: shuffled-within-clip oracle recall about 4.0–5.5%, uniform random 0.2–1.2%, median hit error 1.4–1.9 px and <1.1% of hits beyond 10 px. The reviewer did not supply RNG seed/repetition/population details. The permanent controls below explicitly use seed 20260911, 100 ordinary permutations or random-centre replicates; differences are disclosed, not forced to those reference ranges. They are sanity floors, never gate candidates or training data. The reviewer’s hit-error range concerns the useful RF/YOLO matches, not every WASB result; exact hit counts below also expose RF2x2 on-ball 4/351 beyond 10px (1.14%), versus 7/757 overall (0.92%).

| Candidate / sanity floor | On-ball top-1 mean All / H | On-ball oracle over N boxes mean All / H |
|---|---:|---:|
| rf_full / shuffled_within_clip | 2.18% / 1.50% | 3.75% / 2.63% |
| rf_full / uniform_random | 0.06% / 0.06% | 0.28% / 0.20% |
| rf_2x2 / shuffled_within_clip | 3.11% / 2.30% | 5.52% / 3.86% |
| rf_2x2 / uniform_random | 0.07% / 0.01% | 0.35% / 0.25% |
| rf_3x3 / shuffled_within_clip | 3.56% / 2.47% | 6.02% / 4.07% |
| rf_3x3 / uniform_random | 0.06% / 0.02% | 0.55% / 0.52% |
| wasb / shuffled_within_clip | 0.11% / 0.11% | 0.11% / 0.11% |
| wasb / uniform_random | 0.00% / 0.02% | 0.00% / 0.02% |
| wasb_2x2 / shuffled_within_clip | 0.50% / 0.26% | 0.80% / 0.70% |
| wasb_2x2 / uniform_random | 0.05% / 0.10% | 0.08% / 0.15% |
| tinyball-r1 / shuffled_within_clip | 3.69% / 1.66% | 3.74% / 1.71% |
| tinyball-r1 / uniform_random | 0.05% / 0.02% | 0.05% / 0.02% |
| tinyball-r1-960 / shuffled_within_clip | 3.58% / 1.71% | 3.61% / 1.74% |
| tinyball-r1-960 / uniform_random | 0.05% / 0.01% | 0.05% / 0.01% |
| tinyball-r2-a / shuffled_within_clip | 3.56% / 2.17% | 3.58% / 2.18% |
| tinyball-r2-a / uniform_random | 0.05% / 0.02% | 0.05% / 0.02% |
| tinyball-r2-b / shuffled_within_clip | 3.49% / 1.88% | 3.52% / 1.88% |
| tinyball-r2-b / uniform_random | 0.05% / 0.01% | 0.05% / 0.01% |
| tinyball-r2-c / shuffled_within_clip | 3.74% / 1.95% | 3.76% / 1.97% |
| tinyball-r2-c / uniform_random | 0.05% / 0.02% | 0.06% / 0.02% |
| tinyball-r2-d / shuffled_within_clip | 3.61% / 1.95% | 3.64% / 1.97% |
| tinyball-r2-d / uniform_random | 0.05% / 0.02% | 0.05% / 0.02% |
| tinyball-r3-a / shuffled_within_clip | 3.10% / 1.84% | 3.15% / 1.84% |
| tinyball-r3-a / uniform_random | 0.04% / 0.02% | 0.04% / 0.02% |
| tinyball-r3-b / shuffled_within_clip | 3.28% / 1.78% | 3.33% / 1.78% |
| tinyball-r3-b / uniform_random | 0.05% / 0.02% | 0.05% / 0.02% |

| Candidate | Actual on-ball oracle median error px All / H | Hits beyond 10px / hits All / H |
|---|---:|---:|
| rf_full | 1.86 / 1.25 | 2/243 / 1/76 |
| rf_2x2 | 1.43 / 0.52 | 4/351 / 0/103 |
| rf_3x3 | 1.49 / 0.00 | 2/368 / 0/106 |
| wasb | 3.44 / 5.38 | 1/15 / 1/4 |
| wasb_2x2 | 2.08 / 1.81 | 0/77 / 0/27 |
| tinyball-r1 | 1.79 / 1.30 | 0/318 / 0/66 |
| tinyball-r1-960 | 1.82 / 1.46 | 0/328 / 0/72 |
| tinyball-r2-a | 1.87 / 1.25 | 0/317 / 0/87 |
| tinyball-r2-b | 1.77 / 1.33 | 0/323 / 0/83 |
| tinyball-r2-c | 1.77 / 1.48 | 0/340 / 0/80 |
| tinyball-r2-d | 1.77 / 1.15 | 0/322 / 0/74 |
| tinyball-r3-a | 1.43 / 1.12 | 0/265 / 0/80 |
| tinyball-r3-b | 1.38 / 0.97 | 0/299 / 0/76 |

## No-ball visibility sensitivity

**No-ball = no ball visible to the labeller.** Every detection on those frames counts false, even if it is a real ball MJ could not see. The reviewer classified 129 of 182 no-ball frames as mid-play; this is reviewer-supplied context, not a new occlusion annotation.

Sensitivity only, not verified invisible balls: credit detections within 50 native px of linear interpolation between visible clicks bracketing a no-ball frame, with total bracket gap <=1.01s (two 0.5005s samples). This explicitly specified reconstruction finds the reviewer two r1-960 near-path detections, including one 26.4px away (outside the 20px visible matching radius). The real gate always uses zero credits.

| r1-960 sensitivity scope | Strict false/10s All / H | Path-credited false/10s All / H | Credited detections All / H | Gate All / H |
|---|---:|---:|---:|---|
| Original R1 16-clip H | 2.42 / 2.64 | 2.20 / 2.50 | 2 / 1 | FAIL / FAIL |
| Common six-clip H | 2.42 / 3.00 | 2.20 / 3.00 | 2 / 0 | FAIL / FAIL |

The two credits reproduce 2.42 → 2.20 false/10s All, still failing. One is in the original R1 holdout; both are in the R2/R3 train set. No labels are changed.

## Track vs truth

All = all 20 clips (incl. training clips); H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate), using the fixed six clips unless explicitly stated otherwise. Paired cells are All / H.

Unchanged Kalman association reruns on saved detections without truth guidance. Track precision = points within 20px / track points where a visible label exists. Wrong rate = >50px points / that same denominator; report coverage alongside it so silence cannot look successful. Points on explicit no-ball and unlabelled frames are outside this precision denominator. Longest runs and episodes break on missing/no-ball/incorrect samples or fragment changes; seconds = correct samples/2.

| Candidate | Coverage All / H | Track precision All / H | Longest correct s All / H | Wrong frames / track points All / H | Wrong per track point All / H | Wrong per visible All / H | Episodes All / H |
|---|---:|---:|---:|---:|---:|---:|---:|
| rf_full | 23.20% / 27.05% | 24.02% / 27.85% | 8.00 / 8.00 | 591/845 / 155/237 | 69.94% / 65.40% | 67.54% / 63.52% | 193 / 60 |
| rf_2x2 | 32.91% / 39.34% | 32.95% / 39.34% | 12.50 / 8.00 | 491/874 / 121/244 | 56.18% / 49.59% | 56.11% / 49.59% | 132 / 46 |
| rf_3x3 | 27.20% / 35.66% | 27.20% / 35.66% | 12.50 / 7.50 | 557/875 / 140/244 | 63.66% / 57.38% | 63.66% / 57.38% | 122 / 45 |
| wasb | 4.69% / 2.46% | 11.58% / 5.22% | 3.50 / 0.50 | 311/354 / 108/115 | 87.85% / 93.91% | 35.54% / 44.26% | 151 / 60 |
| wasb_2x2 | 8.57% / 4.51% | 12.25% / 6.25% | 2.00 / 1.00 | 531/612 / 163/176 | 86.76% / 92.61% | 60.69% / 66.80% | 266 / 87 |
| tinyball-r1 | 51.20% / 27.46% | 79.01% / 68.37% | 24.50 / 3.00 | 77/567 / 22/98 | 13.58% / 22.45% | 8.80% / 9.02% | 54 / 19 |
| tinyball-r1-960 | 52.00% / 31.15% | 78.99% / 77.55% | 24.50 / 2.50 | 58/576 / 11/98 | 10.07% / 11.22% | 6.63% / 4.51% | 43 / 10 |
| tinyball-r2-a | 59.77% / 47.13% | 76.57% / 72.78% | 23.50 / 3.00 | 84/683 / 32/158 | 12.30% / 20.25% | 9.60% / 13.11% | 45 / 18 |
| tinyball-r2-b | 58.29% / 36.89% | 82.52% / 76.27% | 24.00 / 2.50 | 39/618 / 14/118 | 6.31% / 11.86% | 4.46% / 5.74% | 28 / 9 |
| tinyball-r2-c | 60.23% / 36.89% | 83.52% / 78.26% | 24.50 / 2.50 | 40/631 / 14/115 | 6.34% / 12.17% | 4.57% / 5.74% | 30 / 10 |
| tinyball-r2-d | 60.23% / 35.25% | 82.86% / 74.78% | 24.50 / 2.50 | 46/636 / 19/115 | 7.23% / 16.52% | 5.26% / 7.79% | 39 / 15 |
| tinyball-r3-a | 52.00% / 44.67% | 77.65% / 68.12% | 24.00 / 3.00 | 72/586 / 32/160 | 12.29% / 20.00% | 8.23% / 13.11% | 25 / 11 |
| tinyball-r3-b | 56.46% / 46.31% | 79.29% / 75.33% | 14.50 / 3.50 | 59/623 / 25/150 | 9.47% / 16.67% | 6.74% / 10.25% | 29 / 14 |

## Split, scale fit and the two new experiments

Same deterministic 14/6 split as round 2: 753 training labels (631 visible, 122 no-ball), 304 H labels (244 visible, 60 no-ball). H contains two on-ball, two off-pitch and two other clips. Round 1 fitted only its four on-ball training clips (300 visible labels). Exact original and current split IDs and source hashes remain in JSON.

| Role | Clip IDs |
|---|---|
| train | m04-n02-t3005-474114-478131<br>m04-n03-t1406-157170-158922<br>m04-n03-t1406-385962-387137<br>m04-n04-t3006-243433-247994<br>m04-n04-t3006-307417-310307<br>m04-n09-t1409-143096-143834<br>m04-n09-t1409-297601-298865<br>m04-n09-t1409-385922-386603<br>m04-n10-t711-186553-188161<br>m04-n12-t1411-237107-242145<br>m04-n15-t3010-164698-170777<br>m04-n17-t717-304624-307834<br>m04-n22-t3012-070707-074371<br>m04-n25-t3014-530600-532465 |
| held_out | m04-n05-t3007-284945-287898<br>m04-n12-t1411-679986-681985<br>m04-n17-t717-253073-260377<br>m04-n17-t717-416826-418915<br>m04-n21-t3011-390297-390800<br>m04-n24-t3013-679939-681217 |

Actual TRAIN targets: median 10.09px, p95 27.72px; 37 clipped at 6px and 1 at 48px. There are 37 targets ≥24px: one on-ball, four other and 32 off-pitch. Large-ball supervision remains weak in the on-ball training domain; size correction does not add missing examples.


Affine native size estimate: **side = -12.42058 + 0.04820987 × image_y**; **R² 0.4944**, 545 nearest matched TRAIN boxes. 86 of 631 visible train clicks need the affine fallback. Both recipes use the same train-only geometry fit. Matched apparent sizes are used directly where present; missing sizes use the fitted value, all clipped to [6,48] px. This replaces the fixed 18.68044 px side and removes its fixed doubling. Image y explains only part of scale variation; these detector extents are estimates, not human-drawn boxes.

Exactly two new neural fits: r3-a repeats COCO-initialised r2-a; r3-b repeats r1-960-initialised r2-b. Both use 2×2@960, 100 requested epochs, 20-minute budget, batch 16, patience 6, seed 42 and the same AdamW/augmentation settings. Only target sizing changes. Checkpoint selection and early stopping use TRAIN loss only; no held-out images enter fitting. Time-budget mode can finish partial epochs and alter the effective schedule; MPS is not guaranteed bitwise deterministic.

| Fit | Recipe / initial weights | MPS minutes | Recorded / selected epoch | Best TRAIN loss |
|---|---|---:|---:|---:|
| r2-a | 2×2@960 / yolo11n.pt | 20.18 | 11 / 10 | 4.48029 |
| r2-b | 2×2@960 / mj-r1-960/weights.pt | 20.14 | 10 / 10 | 3.98813 |
| r2-c | 2×2@1280 / mj-r1-960/weights.pt | 23.18 | 6 / 6 | 3.71372 |
| r2-d | 2×2@1280 / mj-r2-c/weights.pt | 33.79 | 7 / 1 | 3.64641 |
| r3-a | 2×2@960 / yolo11n.pt | 20.17 | 11 / 11 | 5.10102 |
| r3-b | 2×2@960 / mj-r1-960/weights.pt | 20.20 | 10 / 10 | 4.65844 |

Round-1 recipes and timings remain visible for comparison:

| Fit | Tile input | MPS minutes | Completed / requested epochs |
|---|---:|---:|---:|
| tinyball-r1 | 640 | 15.71 | 33 / 5 |
| tinyball-r1-960 | 960 | 15.80 | 18 / 20 |

Highest held-out on-ball top-1 recall among round2 a-d and round3 a-b with held-out all-no-ball false/10s <=2; ties lower false rate then candidate name. Gate remains top-1 >=80% AND <=1 false/10s. This intentionally selects using held-out data: selected estimate is optimistic. Fresh labelled club footage is the true test. No threshold search or additional fits.

Round 2 historically preselected d by TRAIN loss; that rule is superseded for current-best selection, not rewritten as if it had used evaluation. Its historical fit/selection snapshot remains in the execution fixture. The scale hypothesis itself was prompted by held-out error analysis, adding another source of optimism. Selection across R2 a–d and R3 a–b uses the common six-clip H subset; all runs and thresholds are reported.

## Size-bucket recall: old versus scale-aware targets

All = all 20 clips (incl. training clips); H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate), using the fixed six clips unless explicitly stated otherwise. Paired cells are All / H.

Independent size = median of nearest matched RF full/2×2/3×3 shorter sides within 20px. Trained box sizes never define these buckets. Some model misses can therefore receive an independent estimate; unmatched labels retain an unknown-size bucket. Sizes are association-confirmed detector extents, not true human-measured diameters.

| RF size estimator | Matched sizes All / H | Median / p95 native px All | Median / p95 native px H |
|---|---:|---:|---:|
| rf_full | 547 / 165 | 13.09 / 46.34 | 25.12 / 50.78 |
| rf_2x2 | 757 / 212 | 10.41 / 43.88 | 13.19 / 47.44 |
| rf_3x3 | 782 / 221 | 10.29 / 42.17 | 12.69 / 47.03 |

| Recipe / size px | Visible All / H | Old top-1 All / H | New top-1 All / H | Old oracle All / H | New oracle All / H |
|---|---:|---:|---:|---:|---:|
| a / <6 | 11 / 1 | 54.55% / 0.00% | 54.55% / 0.00% | 54.55% / 0.00% | 54.55% / 0.00% |
| a / 6–<10 | 210 / 39 | 81.90% / 82.05% | 67.62% / 61.54% | 81.90% / 82.05% | 67.62% / 61.54% |
| a / 10–<16 | 122 / 46 | 75.41% / 76.09% | 64.75% / 73.91% | 75.41% / 76.09% | 65.57% / 73.91% |
| a / 16–<24 | 22 / 3 | 95.45% / 100.00% | 77.27% / 100.00% | 95.45% / 100.00% | 77.27% / 100.00% |
| a / ≥24 | 23 / 22 | 65.22% / 63.64% | 86.96% / 86.36% | 73.91% / 72.73% | 86.96% / 86.36% |
| a / unknown | 34 / 11 | 26.47% / 9.09% | 0.00% / 0.00% | 26.47% / 9.09% | 0.00% / 0.00% |
| b / <6 | 11 / 1 | 81.82% / 0.00% | 72.73% / 0.00% | 81.82% / 0.00% | 72.73% / 0.00% |
| b / 6–<10 | 210 / 39 | 77.14% / 69.23% | 70.95% / 51.28% | 77.62% / 69.23% | 70.95% / 51.28% |
| b / 10–<16 | 122 / 46 | 79.51% / 73.91% | 74.59% / 73.91% | 79.51% / 73.91% | 74.59% / 73.91% |
| b / 16–<24 | 22 / 3 | 100.00% / 100.00% | 100.00% / 100.00% | 100.00% / 100.00% | 100.00% / 100.00% |
| b / ≥24 | 23 / 22 | 82.61% / 81.82% | 86.96% / 86.36% | 82.61% / 81.82% | 86.96% / 86.36% |
| b / unknown | 34 / 11 | 38.24% / 9.09% | 26.47% / 0.00% | 38.24% / 9.09% | 26.47% / 0.00% |

The per-label scale change recovers large balls but loses small balls in both repeats. Held-out >=24px top-1 matches: a 14/22 -> 19/22; b 18/22 -> 19/22 (All a 15/23 -> 20/23; b 19/23 -> 20/23). Held-out 6-<10px: a 32/39 -> 24/39, b 27/39 -> 20/39 (All a 172/210 -> 142/210; b 162/210 -> 149/210). H top-1 falls a 69.67% -> 65.57%, b 68.03% -> 62.30%; H no-ball false/10s is 2.33 and 3.00. Neither new run qualifies at <=2, and both FAIL the real gate. Current best remains r2-b: H top-1 68.03%, oracle precision 93.26%, false/10s 1.67. This supports a scale tradeoff, not a claim that target correction alone solves detection.


Current best tinyball-r2-b: **top-1** error buckets on on-ball clips. All = all 20 clips (incl. training clips); H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate), using the fixed six clips unless explicitly stated otherwise. Paired cells are All / H.

| Bucket | Misses / visible All | Misses / visible H | Top-1 recall All / H |
|---|---:|---:|---:|
| <6 | 2/11 | 1/1 | 81.82% / 0.00% |
| 6–<10 | 48/210 | 12/39 | 77.14% / 69.23% |
| 10–<16 | 25/122 | 12/46 | 79.51% / 73.91% |
| 16–<24 | 0/22 | 0/3 | 100.00% / 100.00% |
| ≥24 | 4/23 | 4/22 | 82.61% / 81.82% |
| unknown | 21/34 | 10/11 | 38.24% / 9.09% |
| image y <360 | 11/37 | 6/8 | 70.27% / 25.00% |
| image y 360–<720 | 86/373 | 30/102 | 76.94% / 70.59% |
| image y ≥720 | 3/12 | 3/12 | 75.00% / 75.00% |
| motion <10 px/sample | 11/64 | 2/7 | 82.81% / 71.43% |
| motion 10–<50 | 37/163 | 15/43 | 77.30% / 65.12% |
| motion ≥50 | 30/141 | 9/49 | 78.72% / 81.63% |
| motion unknown | 22/54 | 13/23 | 59.26% / 43.48% |
| inside player box | 60/160 | 25/47 | 62.50% / 46.81% |
| outside detected player boxes | 40/262 | 14/75 | 84.73% / 81.33% |
| player pass unknown | 0/0 | 0/0 | — / — |

Image y is an imperfect distance proxy; 2fps displacement includes camera movement and is not measured blur. A click inside a saved COCO person box is projected overlap, not verified occlusion. Error categories overlap and their miss counts must not be added.

- Current-best r2-b size misses (All / H): <6px 2/11 / 1/1; 6-<10px 48/210 / 12/39; 10-<16px 25/122 / 12/46; 16-<24px 0/22 / 0/3; >=24px 4/23 / 4/22; unknown 21/34 / 10/11. H has 39 total top-1 misses.
- Image-y misses (All / H): upper third 11/37 / 6/8; middle 86/373 / 30/102; lower 3/12 / 3/12. Far-side cases are weaker, but small upper/lower samples prevent a calibrated distance claim.
- Motion-proxy misses (All / H): <10px/sample 11/64 / 2/7; 10-<50px 37/163 / 15/43; >=50px 30/141 / 9/49; unknown predecessor 22/54 / 13/23. The fastest sampled displacement bucket is not worst; this is not direct blur measurement.
- Player-overlap misses (All / H): inside a saved person box 60/160 / 25/47, outside 40/262 / 14/75. H top-1 recall is 46.8% inside versus 81.3% outside. Projected overlap is not verified occlusion, and these buckets overlap the size/motion buckets.

Single next experiment: retain per-label sizing for large balls but restore an approximately 18.68px minimum point-target side for small balls; both controlled recipe repeats gained large-ball hits while losing 7-8 of 39 small-ball held-out hits. This is an evidence-based hypothesis for a future fit, not a third experiment in this round.

## What better footage would change

The frozen footage is a 1080p wide Veo export. Native 4K at the same field of view would double source ball diameter; follow-cam can put more pixels on the ball. Preserve those pixels through tile count/input resolution or a tighter field of view: resizing fixed 4K tiles to the same input can erase the gain. Upscaling the current video adds no detail.

**Better footage helps, but is not a fix on its own.** The historical r2-d oracle extrapolation was 60.7% → 66.4% H at 2× ball pixels, still below 80%; it is not measured 4K performance. Non-monotonic size recall and clear large-ball misses rule out presenting 4K as a solution by itself.

| Projection / matching rule | Observed All / H | Extrapolated at 2× px All / H | Supported frames All / H |
|---|---:|---:|---:|
| tinyball-r2-d / oracle | 76.30% / 60.66% | 75.50% / 66.37% | 388 / 111 |
| tinyball-r2-b / top1 | 76.30% / 68.03% | 87.33% / 82.96% | 388 / 111 |

Historical r2-d oracle extrapolation remains 60.66% -> 66.37% H (All 76.30% -> 75.50%): better footage helps but is not a fix on its own. Current-best r2-b top-1 bucket extrapolation is 68.03% -> 82.96% H (All 76.30% -> 87.33%), but relies partly on a three-example perfect 16-24px H bucket, uses selected/reused H data, and does not project the failing 1.67 false/10s. Neither is measured 4K performance or a demonstrated gate pass; fresh labelled club footage is the true test.

Projection maps each measurable ball to its doubled-size bucket and assigns that bucket’s empirical recall; unknown/unsupported bins retain observed outcomes. This is a fragile association, not a causal estimate. Sparse buckets, RF-conditioned size availability and reused evaluation clips limit it. The real test is new labelled club footage reserved before any tuning.

## Label provenance and forward bias

All = all 20 clips (incl. training clips); H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate), using the fixed six clips unless explicitly stated otherwise. Paired cells are All / H.

1,057 validated labels: 875 visible / 182 no-ball, 352 accepted / 705 manual, zero rejected. Coverage: 506/540 on-ball targets, 99/100 off-pitch targets, plus 452 extras. 48 frames remain unlabelled. Exact coverage keys, per-clip counts and label SHA256 remain in JSON; labels and weights stay outside Git.

Manual-only recall is beside pooled recall in every detection headline and group table. Acceptance records already require source_accepted, accepted_source and accepted_score in both Python and browser validation; Accept records the specific model source, and a hand click clears acceptance provenance. These fields survive import/export and allow next-round source-stratified scoring. Accepted/manual differences remain confounded by difficulty and source; they are not causal bias estimates.

| Candidate | Pooled top-1 All / H | Manual top-1 All / H | Accepted top-1 All / H | Manual oracle All / H | Accepted oracle All / H |
|---|---:|---:|---:|---:|---:|
| rf_full | 45.37% / 53.69% | 33.84% / 25.97% | 62.50% / 66.47% | 52.01% / 36.36% | 78.12% / 82.04% |
| rf_2x2 | 65.71% / 71.31% | 54.68% / 50.65% | 82.10% / 80.84% | 80.31% / 70.13% | 95.74% / 94.61% |
| rf_3x3 | 71.09% / 78.28% | 59.85% / 57.14% | 87.78% / 88.02% | 83.75% / 75.32% | 97.73% / 97.60% |
| wasb | 4.69% / 2.46% | 4.40% / 2.60% | 5.11% / 2.40% | 4.40% / 2.60% | 5.11% / 2.40% |
| wasb_2x2 | 9.94% / 6.56% | 9.18% / 9.09% | 11.08% / 5.39% | 13.77% / 15.58% | 18.75% / 12.57% |
| tinyball-r1 | 58.51% / 33.20% | 65.39% / 41.56% | 48.30% / 29.34% | 66.16% / 41.56% | 48.58% / 29.94% |
| tinyball-r1-960 | 60.57% / 36.48% | 65.58% / 38.96% | 53.12% / 35.33% | 66.35% / 38.96% | 54.83% / 35.93% |
| tinyball-r2-a | 71.66% / 52.87% | 71.70% / 49.35% | 71.59% / 54.49% | 73.23% / 50.65% | 74.15% / 56.89% |
| tinyball-r2-b | 67.77% / 45.49% | 69.02% / 42.86% | 65.91% / 46.71% | 70.55% / 42.86% | 67.33% / 46.71% |
| tinyball-r2-c | 69.49% / 43.03% | 75.53% / 53.25% | 60.51% / 38.32% | 76.48% / 53.25% | 61.36% / 38.92% |
| tinyball-r2-d | 68.00% / 40.98% | 72.08% / 46.75% | 61.93% / 38.32% | 73.80% / 46.75% | 63.92% / 39.52% |
| tinyball-r3-a | 59.89% / 52.46% | 53.15% / 37.66% | 69.89% / 59.28% | 55.83% / 40.26% | 71.88% / 61.68% |
| tinyball-r3-b | 67.43% / 53.28% | 62.33% / 35.06% | 75.00% / 61.68% | 63.48% / 36.36% | 76.14% / 62.87% |

RF3x3’s accepted-suggestion oracle recall was 97.73% versus 83.75% manual across visible labels. Round-1 kit build 5 seeded 606 suggestions from r1-960; round-2 build 6 actually seeded 663 from r2-d. Both can bias future acceptance toward the supplying model. Manual-only reporting and source recording expose this risk but cannot make reused clips a clean test set.

## Execution, kit and caveats

- Build 7 at ~/ball-truth-review/index.html uses current-best mj-r2-b saved suggestions: 636 unconfirmed points. All 1057 seed labels and the localStorage key are preserved; original label SHA256 is unchanged. Prior build 6 with 663 r2-d suggestions is recorded as historical.
- 48 frames remain unlabelled: seven have a suggestion and 41 have none. MJ: use Next unlabelled frame, confirm/correct or mark No ball visible; leave uncertain frames unlabelled, then export JSONL with accepted_source intact. Reserve a fresh labelled club-clip set as the true test.
- Copied suggestions to ~/ball-truth-review/suggestions.jsonl and ~/codex-runs/{suggestions.jsonl,ball-human-round3-suggestions.jsonl,ball-human-mj-r2-b-suggestions.jsonl}.
- Isolated Chromium acceptance/provenance/persistence check passed after refresh; screenshot visually inspected. MJ's actual browser profile was not used.

- Initial scoring-only scope extended by the same user request to exactly two scale-aware fits and their saved all-frame inference passes. Baseline and previous model scoring uses saved detections only.
- Use each training click nearest RF 2x2 short side when available; affine image-y fit supplies missing sizes. Fit and all targets use train clips only, clipped [6,48] native px. Same 20-minute budget/100 requested epochs, batch16, AdamW and train-only patience6 as round2 a/b.
- Preserve historical execution decisions as historical; supersede their oracle gate and TRAIN-loss model-selection ranking in current reporting.
- Completed exactly two new scale fits: a 20.17 minutes / 11 epochs, b 20.20 minutes / 10 epochs. These equal the original a/b recorded epoch counts; best checkpoints are new a11/b10 versus old a10/b10, under the same TRAIN-loss rule. Time-budget partial epochs and MPS nondeterminism remain potential run-to-run confounders.
- Current best is r2-b under the explicitly authorized held-out top-1/false-ceiling rule, superseding historical TRAIN-loss selection of r2-d. New scale a/b do not qualify. All six trained contenders and their failures remain visible; no third fit or threshold search.
- New saved-pass FPS All/H: a 51.49/51.01, b 51.12/50.85. Inputs/architecture are unchanged from old 960 recipes; the large difference versus historical ~11.5 FPS is runtime variability, not an established effect of target scale. Cause UNCONFIRMED; no earlier-model inference was rerun.
- Exact audit against parent 8da3390: every pre-existing oracle group metric, track count/rate and provenance metric in round1 and round2 fixtures is unchanged. Added metrics and corrected top-1 gates/bounds are intentional; reviewer top-1 and visible-frame boxes averages reproduce exactly.
- Permanent null controls use seed 20260911 and 100 repetitions, explicitly differing from reviewer seed-unspecified ranges. The 50px near-path sensitivity with <=1.01s bracketing reproduces two r1-960 credits, one in its original 16-clip H subset and neither in the common six H clips.

- Prior exposure: held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate). The r1-960 49.39% original held-out overall oracle recall also served as its own 640-vs-960 selection statistic: one binary aggregate choice. Round3 additionally uses held-out error analysis and explicit held-out model selection, so its selected estimate is more optimistic.
- Round-1 exported last.pt; no held-out-selected best.pt leak. Round2/3 best.pt is selected only by augmented TRAIN loss, with held-out validation and final validation disabled. Model selection after these fits is separate and explicitly evaluation-based in round3.
- The 20 clips come from one match; adjacent samples are correlated. Sample gate PASS/FAIL is legitimate under the stated labels and rules, but does not certify unseen matches or continuous event rates. False/10s is exposure-normalised from 2fps no-ball samples.
- human_measurements.json.gz and round2_measurements.json.gz are historical filenames for scored aggregate output, not raw measurements or human labels. round3_scored_output.json.gz follows the clearer naming. Ledger rendering requires no labels, weights, footage, torch or .git.
- All frozen numeric scoring is reproduced from saved detections; only the two newly authorized scale fits received new inference. The saved person pass is reused. No threshold search or third scale fit.

- Final worktree ball+bench pytest: 399 passed, six pre-existing Pillow deprecation warnings.
- Completed-evidence git archive export: 399 passed with full Python 3.11/OpenCV environment; 396 passed plus three OpenCV-dependent skips in the minimal Python 3.11 environment. Export has no .git, labels, weights or footage.
- Ruff check and ruff format --check pass across all 76 ball/bench Python files; mypy --check-untyped-defs passes ten changed implementation modules.
- Both JSON and Markdown ledgers regenerate byte-for-byte from committed aggregate fixtures in worktree and archive. Fixtures contain no human coordinates, per-label outcomes or weights.
- CLI score_from_saved.py --extra-detections for both new models agrees exactly with every All/H group and held-out headline gate in the paired report.
- Adversarial regression checks reproduce all supplied round1 top-1/boxes-per-visible-frame figures, r1-960 held-out 71/122 top-1 and 72/122 oracle hits with 72/86 oracle precision, and the supplied track-point denominators.
- Every pre-existing round1/round2 group, track and provenance metric matches parent 8da3390 exactly; no unexplained historical numeric changes.
- Kit build7 isolated Chromium check passes: 1057 exact seeds, no auto-save, newer labels/clears persist, accepting records actual model source/score, manual clicking clears acceptance provenance. Screenshot visually inspected.
- Staged paths are inside the requested ball/ledger fence; no .pt or .jsonl is staged. Labels SHA256 unchanged; training outputs and predictions remain local. One commit, no push; clean status is checked after commit.

Not done:

- No candidate passes the top-1 real gate; current-best r2-b remains below 80% H recall and above one false/10s.
- 48 frames remain unlabelled.
- No fresh labelled club-footage test set or measured 4K/follow-cam performance; these 20 clips are no longer clean test data.
- The proposed small-ball target floor is not trained: exactly two scale fits were authorized and completed.
- The cause of cross-run FPS variation is unconfirmed.
