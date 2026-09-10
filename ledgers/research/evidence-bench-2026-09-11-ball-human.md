Human gate, all clips: no candidate passes. held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate): no candidate passes. Proxy verdicts retire for this human-labelled sample.

Selected by TRAIN loss: **tinyball-r2-d**, 4.65 FPS all clips; held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate): on-ball recall/precision **60.7% / 84.1%**, overall **41.8% / 72.9%**, **3.33 false/10 s**, **FAIL**.

# Ball human truth — round 2

All = 20 clips, including fitted clips. H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate). Every paired metric below uses this same fixed six-clip evaluation subset, including rescored round-1 baselines. H is mildly optimistic; these clips are no longer a clean test set.

## Split and experiment protocol

14 train / 6 H; 753 / 304 labels, 631 / 244 visible, 122 / 60 no-ball. Training uses 72.1% of the 875 visible labels, versus round 1's 300/875 (34.3%).

Deterministic rule: enumerate two on-ball, two off-pitch and two other holdout clips; retain round-1 fitted clips in train and reject train/holdout source-time overlap. Rank 65 feasible partitions by SHA256(seed + newline + sorted holdout IDs); seed `ball-human-r2-split-v1`, winning hash `03edd675929948d82afddb0b5b17bd987a1aff05695bfc5bf812ca9a8f3c300f`. Two overlapping held-out windows stay together; none crosses the fitting boundary.

Train IDs:

- `m04-n02-t3005-474114-478131` (other; 70 visible / 6 no-ball)
- `m04-n03-t1406-157170-158922` (on_ball; 30 visible / 6 no-ball)
- `m04-n03-t1406-385962-387137` (off_pitch; 0 visible / 24 no-ball)
- `m04-n04-t3006-243433-247994` (on_ball; 86 visible / 4 no-ball)
- `m04-n04-t3006-307417-310307` (other; 44 visible / 12 no-ball)
- `m04-n09-t1409-143096-143834` (off_pitch; 14 visible / 1 no-ball)
- `m04-n09-t1409-297601-298865` (other; 23 visible / 3 no-ball)
- `m04-n09-t1409-385922-386603` (off_pitch; 0 visible / 13 no-ball)
- `m04-n10-t711-186553-188161` (other; 33 visible / 0 no-ball)
- `m04-n12-t1411-237107-242145` (on_ball; 77 visible / 18 no-ball)
- `m04-n15-t3010-164698-170777` (on_ball; 107 visible / 10 no-ball)
- `m04-n17-t717-304624-307834` (other; 47 visible / 15 no-ball)
- `m04-n22-t3012-070707-074371` (off_pitch; 71 visible / 1 no-ball)
- `m04-n25-t3014-530600-532465` (off_pitch; 29 visible / 9 no-ball)

H IDs (held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate)):

- `m04-n05-t3007-284945-287898` (other; 50 visible / 9 no-ball)
- `m04-n12-t1411-679986-681985` (off_pitch; 40 visible / 0 no-ball)
- `m04-n17-t717-253073-260377` (on_ball; 102 visible / 29 no-ball)
- `m04-n17-t717-416826-418915` (on_ball; 20 visible / 17 no-ball)
- `m04-n21-t3011-390297-390800` (off_pitch; 6 visible / 5 no-ball)
- `m04-n24-t3013-679939-681217` (other; 26 visible / 0 no-ball)

- Round 1 trained on 300/875 visible labels (34.3%); round 2 trains on 631/875 (72.1%).
- a: COCO YOLO11n, 2x2@960, 20-minute fit budget. b: same from mj-r1-960 weights, 20-minute budget. c: 2x2@1280 from same round-1 weights, batch 8 and 23-minute fit budget (<25 minutes target). All request 100 epochs; budget/patience may stop earlier.
- For a-c, early-stop after six epochs without TRAIN-loss improvement; select best.pt only by minimum epoch mean augmented training box+cls+dfl loss. Validator overridden to consume no images or held-out metrics; final validation disabled.
- d is fixed in advance: continue the lowest-TRAIN-loss a-c checkpoint at its same resolution, up to 40 minutes / 200 requested epochs, TRAIN-only patience six. No evaluation is run until d and final model selection are fixed.
- Final best = lowest minimum TRAIN loss across a-d; no choice uses evaluation recall, precision or gate results. Comparing augmented training losses across input sizes is imperfect and can favour overfitting; disclose this risk.
- The real test is new club footage, ideally native 4K / follow-cam. These 20 clips cannot serve as a clean test set; future work requires a fresh labelled clip set as the true holdout.
- A native 4K export at identical FOV doubles source ball diameter, but fixed 2x2 tiles resized to the same model input erase that scale gain. Preserve effective pixels with more tiles/larger inputs or a tighter follow-cam view. A 2x-ball recall projection is conditional extrapolation, not measured 4K performance.
- Pin AdamW lr0=0.002, momentum=0.9, warmup_bias_lr=0.0 to match round-1 auto-selected optimizer. A larger requested epoch count would otherwise silently choose MuSGD. Seeds fixed, but MPS warns some scatter/index operations are nondeterministic.
- Training tiles: 3,012 from 753 labelled frames, with 631 positive tiles and 2,381 negative tiles. No held-out images are decoded into fitting datasets. Ultralytics time-budget mode adjusts its epoch count and learning-rate schedule; epochs requested are caps/inputs, not promises of completed epochs.
- The training-only RF 2x2 apparent-size median is 9.34022 native px. Effective median is the same at 2x2@960 or 3x3@640, and 12.45362 px at 2x2@1280. This sizing sample contains matched RF detections (including multiple matches), not manually drawn ball extents. Point supervision uses a fixed 18.68044 native-px target side.
- Observed a-c TRAIN losses: a=4.48029, b=3.98813, c=3.71372. The predeclared rule therefore starts d from c at 1280. c took 23.18 MPS minutes, satisfying <=25 minutes. No round-2 evaluation predictions existed at this choice.
- d early-stopped after seven epochs / 33.79 minutes: six epochs did not beat epoch one. Final selected model d has minimum TRAIN loss 3.64641. Selection was frozen in round2-selection.json before any round-2 inference; no fifth fit or evaluation-based model/threshold choice.
- No candidate passes either scope. among round-2 fits, c alone exceeds 80% All on-ball recall (80.57%) but fails the false-rate gate (2.09/10s); H recall is 65.57%. d remains the kit model because it was preselected on TRAIN loss; it is not the best evaluation-ranked model. b has the cleanest round-2 predictions; a has the highest H recall. No choice or extra fit was made from these evaluation numbers.
- Current saved-pass FPS: a 11.85, b 11.55, c 8.53, d 4.65; c/d have identical 2,590,035-parameter architectures. Timing varied substantially during d; AC power and no recorded OS thermal/performance warning were observed, but cause is UNCONFIRMED. Baseline/round-1 FPS is historical, not a contemporaneous speed control.

2x2@1280 scales source ball pixels by 1280/960=1.333; 3x3@640 scales by 640/640=1.0. 1280 is 33.3% larger effective ball diameter than either 3x3@640 or 2x2@960; use a 23-minute fit budget with train-only validation to leave room below 25 minutes.

Exactly four ball-model fits, a–d; no recipe, checkpoint, threshold or kit-model choice used their evaluation scores. Best-checkpoint loss is the mean augmented training box+cls+dfl loss, not validation loss. All share confidence 0.1 and inclusive 20 native-pixel centre matching. The table below describes fits shared by both reported evaluation scopes; it contains no evaluation metric.

| Fit | Tile input | Initial weights | MPS minutes | Recorded epochs / best epoch | Best TRAIN loss |
|---|---:|---|---:|---:|---:|
| a | 2×2@960 | yolo11n.pt | 20.18 | 11 / 10 | 4.48029 |
| b | 2×2@960 | mj-r1-960/weights.pt | 20.14 | 10 / 10 | 3.98813 |
| c | 2×2@1280 | mj-r1-960/weights.pt | 23.18 | 6 / 6 | 3.71372 |
| d | 2×2@1280 | mj-r2-c/weights.pt | 33.79 | 7 / 1 | 3.64641 |

A time limit can finish on a partial last epoch. Actual minutes include trainer setup; all fit histories and checkpoint hashes are retained in JSON. TRAIN-loss comparisons across resolutions/initialisations can favour overfitting and are not a guarantee of best generalisation.

## Detection results: round 1 retained alongside round 2

H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate). R/P = recall / precision; all rates use confirmed labels only.

| Candidate | All on-ball R/P | H on-ball R/P | All overall R/P | H overall R/P | All gate | H gate |
|---|---:|---:|---:|---:|---|---|
| rf_2x2 | 83.2% / 9.1% | 84.4% / 9.2% | 86.5% / 9.2% | 86.9% / 9.9% | FAIL | FAIL |
| rf_3x3 | 87.2% / 6.7% | 86.9% / 6.2% | 89.4% / 6.8% | 90.6% / 7.0% | FAIL | FAIL |
| rf_full | 57.6% / 10.5% | 62.3% / 10.9% | 62.5% / 10.6% | 67.6% / 11.0% | FAIL | FAIL |
| wasb | 3.6% / 10.6% | 3.3% / 6.6% | 4.7% / 10.2% | 2.5% / 4.3% | FAIL | FAIL |
| wasb_2x2 | 18.2% / 11.4% | 22.1% / 10.0% | 15.8% / 11.4% | 13.5% / 8.1% | FAIL | FAIL |
| tinyball-r1 | 75.4% / 86.9% | 54.1% / 78.6% | 59.1% / 76.7% | 33.6% / 73.2% | FAIL | FAIL |
| tinyball-r1-960 | 77.7% / 90.4% | 59.0% / 83.7% | 61.7% / 81.1% | 36.9% / 82.6% | FAIL | FAIL |
| tinyball-r2-a | 75.1% / 86.1% | 71.3% / 82.9% | 73.6% / 72.2% | 54.9% / 67.7% | FAIL | FAIL |
| tinyball-r2-b | 76.5% / 93.6% | 68.0% / 93.3% | 69.3% / 86.7% | 45.5% / 88.8% | FAIL | FAIL |
| tinyball-r2-c | 80.6% / 91.4% | 65.6% / 87.0% | 70.4% / 86.2% | 43.4% / 80.9% | FAIL | FAIL |
| tinyball-r2-d | 76.3% / 89.4% | 60.7% / 84.1% | 69.8% / 80.7% | 41.8% / 72.9% | FAIL | FAIL |

H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate). False rates use only explicit no-ball labels (182 All / 60 H); 2 fps gives false/10 s = 20 × false/frame. Median error uses matched visible labels. FPS includes native decoding plus inference, excludes loading/warmup/scoring/tracking; paired H timing uses only those six clips. Baseline/round-1 FPS is historical; round-2 FPS is newly measured, so cross-round speed differences include runtime conditions and are not an isolated resolution effect.

| Candidate | All false/frame | H false/frame | All false/10 s | H false/10 s | All median error px | H median error px | All FPS | H FPS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| rf_2x2 | 5.9176 | 7.6667 | 118.35 | 153.33 | 1.23 | 0.41 | 8.33 | 8.28 |
| rf_3x3 | 9.6209 | 11.6833 | 192.42 | 233.67 | 1.06 | 0.00 | 1.57 | 1.33 |
| rf_full | 3.6374 | 4.3833 | 72.75 | 87.67 | 1.65 | 1.00 | 26.88 | 26.86 |
| wasb | 0.2692 | 0.4167 | 5.38 | 8.33 | 3.44 | 5.77 | 37.90 | 37.71 |
| wasb_2x2 | 1.1429 | 1.4833 | 22.86 | 29.67 | 2.15 | 1.71 | 12.90 | 12.82 |
| tinyball-r1 | 0.1868 | 0.1167 | 3.74 | 2.33 | 1.80 | 1.33 | 51.51 | 49.90 |
| tinyball-r1-960 | 0.1209 | 0.1500 | 2.42 | 3.00 | 1.92 | 1.55 | 37.90 | 38.18 |
| tinyball-r2-a | 0.1484 | 0.1500 | 2.97 | 3.00 | 1.85 | 1.68 | 11.85 | 11.92 |
| tinyball-r2-b | 0.0659 | 0.0833 | 1.32 | 1.67 | 1.72 | 1.45 | 11.55 | 11.51 |
| tinyball-r2-c | 0.1044 | 0.1167 | 2.09 | 2.33 | 1.71 | 1.57 | 8.53 | 8.58 |
| tinyball-r2-d | 0.0989 | 0.1667 | 1.98 | 3.33 | 1.73 | 1.18 | 4.65 | 5.95 |

Gate = pooled on-ball visible-label recall ≥80% AND ≤1 predicted ball/10 s on explicit no-ball labels across that scope. All uses six on-ball clips; H uses two. A sample gate is legitimate, but does not certify unlabelled frames, continuous false-event frequency or unseen matches.

Off-pitch clips can contain visible balls; their visible/no-ball labels are scored literally. H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate).

| Candidate | All off-pitch R/P | H off-pitch R/P | All off-pitch false/10 s | H off-pitch false/10 s |
|---|---:|---:|---:|---:|
| rf_2x2 | 96.2% / 13.7% | 100.0% / 22.2% | 37.74 | 32.00 |
| rf_3x3 | 93.8% / 8.7% | 100.0% / 14.6% | 129.43 | 188.00 |
| rf_full | 80.0% / 15.6% | 93.5% / 19.8% | 39.62 | 24.00 |
| wasb | 3.8% / 6.6% | 2.2% / 3.3% | 5.28 | 16.00 |
| wasb_2x2 | 6.2% / 6.5% | 0.0% / 0.0% | 14.34 | 32.00 |
| tinyball-r1 | 36.2% / 61.7% | 6.5% / 42.9% | 4.15 | 0.00 |
| tinyball-r1-960 | 42.5% / 67.3% | 8.7% / 80.0% | 1.89 | 4.00 |
| tinyball-r2-a | 78.8% / 64.9% | 52.2% / 58.5% | 1.89 | 12.00 |
| tinyball-r2-b | 66.2% / 84.8% | 15.2% / 77.8% | 0.00 | 0.00 |
| tinyball-r2-c | 55.6% / 81.7% | 8.7% / 44.4% | 0.75 | 8.00 |
| tinyball-r2-d | 64.4% / 67.3% | 13.0% / 46.2% | 1.51 | 8.00 |

## Track vs human truth

Unchanged Kalman tracker rerun independently of labels. Coverage means a filtered track point within 20 px on a visible label; >50 px is a wrong-object frame. Correct runs and wrong episodes break at missing/no-ball labels and fragment changes; longest run is sample-count/2 seconds, not native-frame continuity. H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate).

| Candidate | All coverage | H coverage | All longest s | H longest s | All wrong frames | H wrong frames | All wrong episodes | H wrong episodes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| rf_2x2 | 32.9% | 39.3% | 12.50 | 8.00 | 491 | 121 | 132 | 46 |
| rf_3x3 | 27.2% | 35.7% | 12.50 | 7.50 | 557 | 140 | 122 | 45 |
| rf_full | 23.2% | 27.0% | 8.00 | 8.00 | 591 | 155 | 193 | 60 |
| wasb | 4.7% | 2.5% | 3.50 | 0.50 | 311 | 108 | 151 | 60 |
| wasb_2x2 | 8.6% | 4.5% | 2.00 | 1.00 | 531 | 163 | 266 | 87 |
| tinyball-r1 | 51.2% | 27.5% | 24.50 | 3.00 | 77 | 22 | 54 | 19 |
| tinyball-r1-960 | 52.0% | 31.1% | 24.50 | 2.50 | 58 | 11 | 43 | 10 |
| tinyball-r2-a | 59.8% | 47.1% | 23.50 | 3.00 | 84 | 32 | 45 | 18 |
| tinyball-r2-b | 58.3% | 36.9% | 24.00 | 2.50 | 39 | 14 | 28 | 9 |
| tinyball-r2-c | 60.2% | 36.9% | 24.50 | 2.50 | 40 | 14 | 30 | 10 |
| tinyball-r2-d | 60.2% | 35.2% | 24.50 | 2.50 | 46 | 19 | 39 | 15 |

## Ball pixels and error analysis

Independent RF matched boxes below measure native shorter box sides associated with MJ's centres; centres do not establish true ball boundaries. No size exists for an unmatched ball. Trained boxes reflect fixed roughly 18–19 px point-supervision targets and are excluded from independent size analysis. H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate).

| Candidate | All matched sizes | H matched sizes | All median / p95 px | H median / p95 px |
|---|---:|---:|---:|---:|
| rf_2x2 | 757 | 212 | 10.41 / 43.88 | 13.19 / 47.44 |
| rf_3x3 | 782 | 221 | 10.29 / 42.17 | 12.69 / 47.03 |
| rf_full | 547 | 165 | 13.09 / 46.34 | 25.12 / 50.78 |

Error buckets concern the selected model on on-ball clips only. Size per label is the median of nearest matching RF full/2×2/3×3 sizes; this provides independent size estimates for some model misses, with an explicit unknown bucket. H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate).

| Bucket | All misses / visible | H misses / visible | All recall | H recall |
|---|---:|---:|---:|---:|
| size <6 px | 2 / 11 | 1 / 1 | 81.8% | 0.0% |
| size 6–<10 px | 36 / 210 | 12 / 39 | 82.9% | 69.2% |
| size 10–<16 px | 26 / 122 | 11 / 46 | 78.7% | 76.1% |
| size 16–<24 px | 1 / 22 | 0 / 3 | 95.5% | 100.0% |
| size ≥24 px | 14 / 23 | 14 / 22 | 39.1% | 36.4% |
| size unknown | 21 / 34 | 10 / 11 | 38.2% | 9.1% |
| image y <360 | 18 / 37 | 7 / 8 | 51.4% | 12.5% |
| image y 360–<720 | 73 / 373 | 32 / 102 | 80.4% | 68.6% |
| image y ≥720 | 9 / 12 | 9 / 12 | 25.0% | 25.0% |
| displacement <10 px/sample | 8 / 64 | 2 / 7 | 87.5% | 71.4% |
| displacement 10–<50 px/sample | 40 / 163 | 18 / 43 | 75.5% | 58.1% |
| displacement ≥50 px/sample | 36 / 141 | 16 / 49 | 74.5% | 67.3% |
| displacement unknown | 16 / 54 | 12 / 23 | 70.4% | 47.8% |
| inside person box | 54 / 160 | 25 / 47 | 66.2% | 46.8% |
| outside detected person boxes | 46 / 262 | 23 / 75 | 82.4% | 69.3% |
| person pass missing | 0 / 0 | 0 / 0 | — | — |

Image y is a camera-dependent distance proxy. Displacement uses the immediately preceding visible scheduled sample and includes camera motion; it is not measured shutter blur. A point inside a COCO person box is projected overlap, not proven physical occlusion; missed people can appear outside. Unknown labels break motion pairs. Correlated samples and size-conditioned RF availability limit causal interpretation.

- Size (All / H): <6 px misses 2/11 / 1/1; 6–<10 px 36/210 / 12/39; 10–<16 px 26/122 / 11/46; 16–<24 px 1/22 / 0/3; >=24 px 14/23 / 14/22; unknown size 21/34 / 10/11. Recall is not monotonic in size. Only one >=24 px on-ball training label has an independent RF size estimate, versus 22 in H.
- Image y (All / H): upper third misses 18/37 / 7/8, middle third 73/373 / 32/102, lower third 9/12 / 9/12. Both far-side and close-touchline views fail; image y alone is not a reliable distance explanation.
- Motion proxy (All / H): <10 px/sample misses 8/64 / 2/7; 10–<50 px 40/163 / 18/43; >=50 px 36/141 / 16/49; unknown predecessor 16/54 / 12/23. H recall is 71.4%, 58.1%, 67.3% in the three measured bins; this is not a monotonic blur relationship.
- Player-box overlap (All / H): inside misses 54/160 / 25/47 versus outside 46/262 / 23/75. H recall is 46.8% inside versus 69.3% outside. Two post-selection visual spot checks of >=24 px misses show clear roughly 29 px touchline balls; projected overlap and scale mismatch remain plausible failure factors, not proven causes.

Single next change (inference from the error buckets): add scale-diverse human ball-box supervision from fresh close-touchline/player-overlap clips, replacing the fixed 18.68 px point targets; clear large balls and overlapping-player cases account for substantial misses, while more epochs did not improve the selected model’s evaluation results. Categories overlap; their miss counts must not be added.

## What better footage would change

The frozen clips are a 1080p wide Veo export. A native 4K export at the same field of view doubles source ball diameter; follow-cam crops can also increase ball pixels. To preserve that gain at the detector, increase tile count/model input or tighten the field of view: resizing fixed 2×2 4K crops to the same 960/1280 input would erase the scale gain. Merely upscaling this 1080p video adds no detail.

The table maps each measured ball size to twice its size and uses observed recall in that destination bucket. Unknown sizes or unsupported destination bins retain observed outcomes. This is an **associational extrapolation, not measured recall on better footage**, and inherits sparse-bucket and RF-detection bias. H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate).

| All observed recall | H observed recall | All projected at 2× px | H projected at 2× px | All supported / unchanged | H supported / unchanged |
|---:|---:|---:|---:|---:|---:|
| 76.3% | 60.7% | 75.5% | 66.4% | 388 / 34 | 111 / 11 |

At 2x apparent ball pixels, the fixed bucket extrapolation gives 75.50% All (observed 76.30%) and 66.37% H (observed 60.66%); not measured 4K recall and not evidence that pixels alone reach 80%. Non-monotonic size recall, three H examples in 16–24 px, and 11 unknown-size H labels make this an unstable associational projection.

The real test is fresh labelled club footage, ideally native 4K / follow-cam, held out before any recipe choice. These 20 clips can no longer serve as a clean test set.

## Label provenance and suggestion bias

1,057 validated rows: 875 visible / 182 no-ball; 352 accepted suggestions / 705 hand decisions, zero rejected. Coverage is 506/540 planned on-ball targets, 99/100 off-pitch targets, plus 452 extra labels; 48 of the 1,105 scheduled frames remain unlabelled (35 planned targets plus 13 extras). The JSON retains every covered/missing target and per-clip count. No labels or weights are committed.

Accepted/manual comparisons are descriptive, confounded by suggestion source and frame difficulty; manual includes no-ball decisions. H = held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate).

| Candidate | All accepted R/P | H accepted R/P | All manual R/P | H manual R/P |
|---|---:|---:|---:|---:|
| rf_2x2 | 95.7% / 13.2% | 94.6% / 15.3% | 80.3% / 7.4% | 70.1% / 4.8% |
| rf_3x3 | 97.7% / 9.4% | 97.6% / 10.7% | 83.7% / 5.6% | 75.3% / 3.6% |
| rf_full | 78.1% / 14.8% | 82.0% / 15.5% | 52.0% / 8.2% | 36.4% / 4.6% |
| wasb | 5.1% / 11.2% | 2.4% / 5.0% | 4.4% / 9.5% | 2.6% / 3.3% |
| wasb_2x2 | 18.8% / 17.6% | 12.6% / 11.0% | 13.8% / 8.6% | 15.6% / 5.5% |
| tinyball-r1 | 48.6% / 81.4% | 29.9% / 74.6% | 66.2% / 74.6% | 41.6% / 71.1% |
| tinyball-r1-960 | 54.8% / 81.4% | 35.9% / 90.9% | 66.3% / 80.9% | 39.0% / 69.8% |
| tinyball-r2-a | 74.1% / 71.9% | 56.9% / 66.9% | 73.2% / 72.4% | 50.6% / 69.6% |
| tinyball-r2-b | 67.3% / 91.2% | 46.7% / 92.9% | 70.6% / 84.1% | 42.9% / 80.5% |
| tinyball-r2-c | 61.4% / 87.8% | 38.9% / 81.2% | 76.5% / 85.3% | 53.2% / 80.4% |
| tinyball-r2-d | 63.9% / 81.2% | 39.5% / 75.0% | 73.8% / 80.4% | 46.8% / 69.2% |

## Kit, reproducibility and caveats

- Build 6 at ~/ball-truth-review/index.html, refreshed from frozen selected model mj-r2-d; 663 unconfirmed suggestions. Existing localStorage key and all 1,057 seed labels preserved; original label SHA256 unchanged.
- 48 frames remain unlabelled: 10 with a model suggestion and 38 without. MJ: use Next unlabelled frame, confirm/correct or mark No ball only when no ball is visible; leave uncertain frames unknown, then export JSONL. Fresh labelled club clips are needed for the next true test.
- Suggestion copies updated at ~/ball-truth-review/suggestions.jsonl, ~/codex-runs/suggestions.jsonl, ~/codex-runs/ball-human-round2-suggestions.jsonl and ~/codex-runs/ball-human-mj-r2-d-suggestions.jsonl.
- Isolated Chromium check passed: exact seed labels, no automatic saves, new labels/clears survive reload, next-unlabelled navigation works. Screenshot: ~/codex-runs/ball-mj-r2-kit-final.png.

- Worktree pytest ball+bench: 391 passed, six pre-existing Pillow deprecation warnings.
- git archive export with full Python 3.11 environment: 391 passed, no skips; minimal Python 3.11 archive environment without torch/OpenCV: 388 passed, three OpenCV-dependent tests skipped. Saved scoring, tracking and byte-for-byte ledger generation run in both.
- Ruff check and ruff format --check pass across all 68 ball/bench Python files.
- Mypy --check-untyped-defs passes for all nine changed implementation modules.
- Isolated Chromium kit check passes; all 1057 labels exact, storage key preserved, no automatic save, new browser labels and explicit clears survive reload. Screenshot visually inspected.
- Both ledgers regenerate byte-for-byte from committed aggregate fixtures; no label coordinates or weights in fixtures. All staged paths are inside the requested fence; no .pt or .jsonl staged.

- Evaluation disclosure: held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate). Prior exposure was the single aggregate binary 640-vs-960 recipe decision in round 1. No further recipe selection used H scores; round-2 model selection was frozen before inference. This does not make the subset a clean test set.
- All clips come from one match; neither split measures cross-club or cross-camera generalisation. The All/H gap exposes resubstitution optimism.
- Independent RF boxes estimate apparent size but can still associate a nearby wrong object within 20 px. Size/height/displacement/person-overlap buckets are correlated proxies, not causal diagnoses.
- MPS deterministic mode warns about unsupported deterministic scatter/index operations. Saved measurements reproduce exactly; retraining is not promised bitwise identical.
- Round-1 full-corpus numbers are preserved above and in the original JSON results. Its original 16-clip evaluation split and fit records remain under execution/results; those historical estimates also have the same prior tuning exposure and must not be confused with the six-clip H columns here.
- Ledger generation uses committed aggregate fixtures without labels, weights, footage, torch or .git. Model files, predictions, suggestions and detailed logs remain local under ~/models/tinyball/ and ~/codex-runs/.
- Scope: ball tooling and the two requested ledgers only; no push; one commit. CONTINUITY.md remains outside the user-authorised fence.
