# Fair comparison — no winner at a strict budget

On these recipe-selected m04 clips no detector wins: RF-DETR and YOLO swap the lead every one or two false boxes, the unselected RF fit matches YOLO at equal held-out false rates, the large-ball result rests on one 12-second sequence, three of the n21 'false' boxes may be mislabelled real balls, and RF-DETR Nano@960 is about 8x slower at 2 fps (about 36 min per match) and 10-11x at native rate (about 8-9 h).

Gate on recipe-selected clips: **no candidate passes either operating point**.

This section supersedes the round-4 head-to-head headline. **A shared confidence threshold is not a fair operating point across model families.** Product direction remains RF-DETR (Apache-2.0); ultralytics is bench-only and must not enter the serving path.

Current RF model selected across FINAL checkpoints: **rf-r5-a** (eligible at ≤2 H false/10s). Each fit exports its FINAL checkpoint. Gate: H on-ball top-1 ≥80% AND strict H false/10s ≤1.0. Intermediate held-out learning-curve numbers do not select anything. Final H metrics select the model under the declared ≤2 false/10s rule (or an explicitly unqualified lowest-false fallback); this is optimistic.

T = 14 TRAIN clips (631 visible, 122 no-ball); H = **held-out (recipe-selected on these clips)**, six clips (244 visible, 60 no-ball). On-ball denominators: T 300, H 122. All includes training clips. All 20 clips are from match m04. H on-ball is just 102 frames of m04-n17-t717-253073-260377 and 20 of m04-n17-t717-416826-418915; player n17-t717 also appears in TRAIN. **Two clips from one match cannot establish a winner.**

Thresholds are chosen from TRAIN no-ball scores only: the lowest threshold retaining at most floor(target × 122 / 20) false boxes; >= comparison, ties removed together. Thus nominal TRAIN 1.0 and 2.0 budgets allow 6 and 12 boxes (0.984 and 1.967/10s). All 1105 scheduled frames were freshly inferred down to confidence 0.01. Scores below that floor are censored; the curve cannot describe lower thresholds.

Manual-only frames are harder: MJ hand-clicked frames where useful suggestions were absent. Lower manual-only recall is expected from that selection and is not, by itself, evidence of model bias. Accepted-source provenance remains attached to exported labels.

## Primary operating points

| Model | TRAIN target | Threshold | On-ball top-1 T / H | Manual top-1 T / H | Strict false/10s T / H | H McNemar wins / losses vs YOLO | Exact p | Gate H |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| yolo-r2-b | 1 | 0.12179460376501085 | 78.33% / 66.39% | 77.24% / 44.00% | 0.98 / 1.67 | 0 / 0 | 1 | FAIL |
| yolo-r2-b | 2 | 0.039273284375667579 | 86.00% / 70.49% | 84.55% / 44.00% | 1.97 / 3.00 | 0 / 0 | 1 | FAIL |
| rf-b | 1 | 0.19124995172023776 | 95.00% / 74.59% | 93.90% / 64.00% | 0.98 / 3.00 | 17 / 7 | 0.06391 | FAIL |
| rf-b | 2 | 0.066153332591056838 | 95.33% / 75.41% | 94.31% / 66.00% | 1.97 / 6.67 | 15 / 9 | 0.3075 | FAIL |
| rf-r5-a | 1 | 0.30314332246780401 | 81.67% / 62.30% | 80.49% / 48.00% | 0.98 / 2.00 | 7 / 12 | 0.3593 | FAIL |
| rf-r5-a | 2 | 0.062361281365156181 | 88.00% / 76.23% | 86.18% / 58.00% | 1.97 / 3.33 | 12 / 5 | 0.1435 | FAIL |
| rf-r5-b | 1 | 0.49416390061378485 | 72.33% / 61.48% | 69.51% / 38.00% | 0.98 / 1.33 | 6 / 12 | 0.2379 | FAIL |
| rf-r5-b | 2 | 0.19647511839866641 | 86.67% / 77.05% | 85.37% / 58.00% | 1.97 / 4.00 | 11 / 3 | 0.05737 | FAIL |

### Matched held-out false-rate budgets — diagnostic only

Maximum hits out of122 at or below each false-count budget. These thresholds use H, so this is descriptive, not deployable calibration. One false box is20/60=0.333 per10s; the lead changes hands every one or two boxes.

| H false/10s (box budget) | YOLO r2-b | RF b | RF r5-a | RF r5-b |
|---|---:|---:|---:|---:|
| 1.00 (3) | 69 | 74 | 63 | 68 |
| 1.33 (4) | 72 | 76 | 74 | 78 |
| 1.67 (5) | 83 | 78 | 74 | 81 |
| 2.00 (6) | 86 | 79 | 79 | 87 |
| 3.00 (9) | 86 | 91 | 89 | 93 |
| 3.33 (10) | 86 | 91 | 93 | 94 |

TRAIN calibration is in-sample: its no-ball frames were also training negatives. Approximate target1 H/TRAIN ratios are YOLO1.7×, r5-a2.0×, r5-b1.4×, RF b3.0×. Using the achieved0.9836 TRAIN rate, exact ratios are yolo-r2-b 1.69×, rf-b 3.05×, rf-r5-a 2.03×, rf-r5-b 1.36×. A TRAIN-chosen operating point does not imply an equal H error rate.

Selection is a knife-edge tie-break: rf-r5-a stays selected correctly at the exact ceiling (6/60×20=2.000), with 76 hits versus r5-b's 75. One more false box would select r5-b. At every attainable matched false-count budget from 0 through 10 boxes (3.33/10s), r5-b is at or above r5-a. This rule output is a kit-source choice, not evidence of superiority.

The cited 2.17 / 1.30 / 2.61 / 3.04 rates DO reproduce as groups.on_ball.false_per_10s: 5 / 3 / 6 / 7 false boxes ×20/46, using the 46 no-ball frames in the two n17 on-ball clips. Strict selection uses groups.all and all 60 held-out no-ball frames. At TRAIN-1 A has 6/60×20=2.000 and B 4/60×20=1.333. The earlier claim that these rates did not reproduce was wrong: it confused denominators.

Both new fits started from COCO and stopped at the 90-minute budget after three complete epochs plus part of epoch4. Only six hard tiles were mined (five negative, one positive retaining its annotation). No evidence more epochs help at strict budgets; do not plan longer m04 training.

Large-ball / n21 summary (H only, recipe-selected on these clips):

| Model | ≥24px hits/22 at TRAIN 1 / 2 / fixed0.1 | N21 false boxes on5 no-ball frames at TRAIN 1 / 2 / fixed0.1 |
|---|---:|---:|
| yolo-r2-b | 16/22 / 19/22 / 18/22 | 0 / 0 / 0 |
| rf-b | 11/22 / 11/22 / 11/22 | 3 / 5 / 5 |
| rf-r5-a | 9/22 / 16/22 / 12/22 | 1 / 3 / 3 |
| rf-r5-b | 12/22 / 19/22 / 19/22 | 1 / 3 / 4 |

Exact two-sided McNemar is a frame-level diagnostic; adjacent frames correlate, so its nominal p value is optimistic. YOLO comparisons use each model's own TRAIN-chosen threshold for the same target, not the same numeric threshold or a threshold matched on H.

## Precision, localisation and output volume

| Model / TRAIN target / group | Top-1 recall T / H | Top-1 precision T / H | Manual recall T / H | Oracle over N boxes T / H | Boxes/visible frame T / H | Median top-1 error px T / H |
|---|---:|---:|---:|---:|---:|---:|
| yolo-r2-b / 1 / on_ball | 78.33% / 66.39% | 97.92% / 95.29% | 77.24% / 44.00% | 78.67% / 66.39% | 0.81 / 0.67 | 1.96 / 1.30 |
| yolo-r2-b / 1 / all | 74.64% / 43.44% | 95.15% / 90.60% | 71.97% / 42.86% | 76.39% / 43.44% | 0.86 / 0.47 | 1.75 / 1.41 |
| yolo-r2-b / 2 / on_ball | 86.00% / 70.49% | 95.91% / 88.66% | 84.55% / 44.00% | 87.00% / 70.49% | 0.98 / 0.80 | 1.99 / 1.36 |
| yolo-r2-b / 2 / all | 81.93% / 47.95% | 93.15% / 81.25% | 79.15% / 45.45% | 84.47% / 48.36% | 1.06 / 0.61 | 1.80 / 1.48 |
| rf-b / 1 / on_ball | 95.00% / 74.59% | 99.65% / 93.81% | 93.90% / 64.00% | 95.00% / 74.59% | 0.98 / 0.80 | 2.08 / 1.38 |
| rf-b / 1 / all | 94.61% / 52.87% | 98.68% / 76.79% | 93.72% / 62.34% | 94.93% / 52.87% | 1.00 / 0.69 | 1.87 / 1.45 |
| rf-b / 2 / on_ball | 95.33% / 75.41% | 98.62% / 87.62% | 94.31% / 66.00% | 95.33% / 76.23% | 1.11 / 0.89 | 2.12 / 1.39 |
| rf-b / 2 / all | 95.72% / 53.69% | 97.26% / 71.58% | 95.07% / 63.64% | 96.35% / 54.51% | 1.14 / 0.78 | 1.88 / 1.45 |
| rf-r5-a / 1 / on_ball | 81.67% / 62.30% | 99.19% / 93.83% | 80.49% / 48.00% | 82.33% / 62.30% | 0.84 / 0.64 | 2.17 / 1.03 |
| rf-r5-a / 1 / all | 83.52% / 45.90% | 97.59% / 80.58% | 81.61% / 53.25% | 84.47% / 46.72% | 0.88 / 0.57 | 1.84 / 1.18 |
| rf-r5-a / 2 / on_ball | 88.00% / 76.23% | 97.42% / 93.94% | 86.18% / 58.00% | 88.67% / 76.23% | 1.01 / 0.83 | 2.19 / 1.12 |
| rf-r5-a / 2 / all | 90.49% / 54.51% | 96.13% / 80.12% | 88.79% / 59.74% | 91.44% / 55.74% | 1.06 / 0.72 | 1.93 / 1.26 |
| rf-r5-b / 1 / on_ball | 72.33% / 61.48% | 99.54% / 96.15% | 69.51% / 38.00% | 72.33% / 61.48% | 0.74 / 0.61 | 2.19 / 0.84 |
| rf-r5-b / 1 / all | 77.81% / 44.67% | 98.20% / 83.21% | 73.99% / 44.16% | 78.13% / 45.08% | 0.80 / 0.53 | 1.83 / 0.95 |
| rf-r5-b / 2 / on_ball | 86.67% / 77.05% | 97.38% / 93.07% | 85.37% / 58.00% | 87.67% / 77.05% | 0.96 / 0.82 | 2.29 / 1.01 |
| rf-r5-b / 2 / all | 90.02% / 54.10% | 97.09% / 78.57% | 88.34% / 58.44% | 90.97% / 56.56% | 0.99 / 0.72 | 2.03 / 1.08 |

## False boxes by clip

No-ball means **no ball visible to the labeller**. Every retained detection on such a frame counts false, even an actual ball the labeller missed or an apparent spare ball. Path credits are a sensitivity analysis only, never used to choose thresholds or pass the gate.

The path-credit rule is unchanged: within 50 native px of the linear interpolation between bracketing visible clicks, with a total bracket gap ≤1.01s. Terminal no-ball frames without both brackets receive no credit; this includes the n21 examples.

| Model / TRAIN target | Strict false/10s T / H | Path-credited false/10s T / H | Credits T / H |
|---|---:|---:|---:|
| yolo-r2-b / 1 | 0.98 / 1.67 | 0.66 / 1.67 | 2 / 0 |
| yolo-r2-b / 2 | 1.97 / 3.00 | 1.48 / 3.00 | 3 / 0 |
| rf-b / 1 | 0.98 / 3.00 | 0.66 / 3.00 | 2 / 0 |
| rf-b / 2 | 1.97 / 6.67 | 1.64 / 6.33 | 2 / 1 |
| rf-r5-a / 1 | 0.98 / 2.00 | 0.66 / 1.67 | 2 / 1 |
| rf-r5-a / 2 | 1.97 / 3.33 | 1.48 / 3.00 | 3 / 1 |
| rf-r5-b / 1 | 0.98 / 1.33 | 0.66 / 1.33 | 2 / 0 |
| rf-r5-b / 2 | 1.97 / 4.00 | 1.48 / 4.00 | 3 / 0 |

TRAIN clip counts (columns are model / TRAIN target):

| Clip | No-ball frames | yolo-r2-b / 1 | yolo-r2-b / 2 | rf-b / 1 | rf-b / 2 | rf-r5-a / 1 | rf-r5-a / 2 | rf-r5-b / 1 | rf-r5-b / 2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| m04-n02-t3005-474114-478131 | 6 | 1 | 2 | 3 | 5 | 2 | 3 | 2 | 2 |
| m04-n03-t1406-157170-158922 | 6 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| m04-n03-t1406-385962-387137 | 24 | 0 | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| m04-n04-t3006-243433-247994 | 4 | 1 | 1 | 1 | 1 | 0 | 2 | 0 | 3 |
| m04-n04-t3006-307417-310307 | 12 | 0 | 1 | 0 | 1 | 1 | 2 | 1 | 3 |
| m04-n09-t1409-143096-143834 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| m04-n09-t1409-297601-298865 | 3 | 0 | 0 | 0 | 1 | 0 | 1 | 1 | 1 |
| m04-n09-t1409-385922-386603 | 13 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| m04-n10-t711-186553-188161 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| m04-n12-t1411-237107-242145 | 18 | 3 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| m04-n15-t3010-164698-170777 | 10 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 1 |
| m04-n17-t717-304624-307834 | 15 | 1 | 1 | 1 | 1 | 2 | 3 | 2 | 2 |
| m04-n22-t3012-070707-074371 | 1 | 0 | 0 | 0 | 0 | 1 | 1 | 0 | 0 |
| m04-n25-t3014-530600-532465 | 9 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |

HELD clip counts (columns are model / TRAIN target):

| Clip | No-ball frames | yolo-r2-b / 1 | yolo-r2-b / 2 | rf-b / 1 | rf-b / 2 | rf-r5-a / 1 | rf-r5-a / 2 | rf-r5-b / 1 | rf-r5-b / 2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| m04-n05-t3007-284945-287898 | 9 | 1 | 1 | 1 | 4 | 0 | 1 | 0 | 2 |
| m04-n12-t1411-679986-681985 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| m04-n17-t717-253073-260377 | 29 | 3 | 7 | 3 | 7 | 4 | 5 | 2 | 4 |
| m04-n17-t717-416826-418915 | 17 | 1 | 1 | 2 | 4 | 1 | 1 | 1 | 3 |
| m04-n21-t3011-390297-390800 | 5 | 0 | 0 | 3 | 5 | 1 | 3 | 1 | 3 |
| m04-n24-t3013-679939-681217 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

### N21 source-pixel inspection

N21 is scorer class off_pitch, based on MJ's note. s8-s10 show a football; s6 none visible; s7 ambiguous. YOLO has no retained boxes on these no-ball frames. The RF models' s9 boxes cover the visible ball; at TRAIN-2 two of each r5 fit's three boxes cover the ball and one covers footwear. MJ's s0-s5 click distances to the reviewer's flagged spot are86,142,164,158,118,77px: away, then back, not a monotonic approach. s0-s5 label the same background ball VISIBLE: s0 accepted rf_3x3, s1-s4 accepted rf_2x2, s5 manual. Their clicks sit68–149px left and37–69px above the reviewer's s8 spot. Every candidate, including YOLO, has retained boxes in s0-s5 (not necessarily every frame); then s6-s10 are labelled no-ball. No labels, thresholds, selection or strict gate were changed.

Original RF b fixed0.1 inspection: five boxes on s8-s10, three on a ball and two on footwear. The new s0-s10 sheet covers all four models at both TRAIN budgets, including the six currently visible labels.

TRAIN replay must not mine these held-out frames. No relabelling or kit change in this round.

~/codex-runs/ball-r5-n21/adjudicate-s0-s10.png; current labels and saved boxes only, no model inference.

Counterfactuals only; labels, TRAIN thresholds, gate and selection unchanged. As-labelled uses244 visible /60 no-ball frames. Match-ball-only removes the six visible background-ball labels (238 visible), counts all their retained boxes false and expands the no-ball denominator to66. Any-visible-ball false rate preserves the prior credit-only sensitivity: subtract visually identified ball boxes on s8–s10 and retain the original60-frame exposure; it is not a fully relabelled no-ball-frame rate. For any-visible-ball overall top-1 recall only, add s8–s10 as three provisional visible references (247 total), using source-inspected old RF b box centres and the unchanged20px rule, not MJ-confirmed new clicks. s6 remains no-ball; s7 is unresolved and unchanged. At s10 a higher-confidence footwear box lies within20px of the ball, so the requested geometric metric can count it as a provisional hit even though only the actual ball box receives a false-box credit. These proxy recall numbers require MJ adjudication, and must not be used as new ground truth.

Each cell: false/10s; overall top-1 recall (hits/visible). Directions are false/recall versus YOLO at the same TRAIN budget. On-ball recall is unchanged: n21 is off_pitch.

| Model / TRAIN budget | As labelled | Any visible ball (credit-only false; provisional recall) | Match ball only | Directions vs YOLO: labelled / any / match |
|---|---:|---:|---:|---|
| yolo-r2-b / 1 | 1.67; 43.44% (106/244) | 1.67; 42.91% (106/247) | 3.03; 42.44% (101/238) | same false, same recall / same false, same recall / same false, same recall |
| yolo-r2-b / 2 | 3.00; 47.95% (117/244) | 3.00; 47.37% (117/247) | 4.24; 47.06% (112/238) | same false, same recall / same false, same recall / same false, same recall |
| rf-b / 1 | 3.00; 52.87% (129/244) | 2.33; 53.44% (132/247) | 4.55; 51.68% (123/238) | higher false, higher recall / higher false, higher recall / higher false, higher recall |
| rf-b / 2 | 6.67; 53.69% (131/244) | 5.67; 54.25% (134/247) | 8.18; 52.52% (125/238) | higher false, higher recall / higher false, higher recall / higher false, higher recall |
| rf-r5-a / 1 | 2.00; 45.90% (112/244) | 1.67; 45.75% (113/247) | 3.33; 44.96% (107/238) | higher false, higher recall / same false, higher recall / higher false, higher recall |
| rf-r5-a / 2 | 3.33; 54.51% (133/244) | 2.67; 54.66% (135/247) | 4.85; 53.36% (127/238) | higher false, higher recall / lower false, higher recall / higher false, higher recall |
| rf-r5-b / 1 | 1.33; 44.67% (109/244) | 1.00; 44.53% (110/247) | 2.73; 43.70% (104/238) | lower false, higher recall / lower false, higher recall / lower false, higher recall |
| rf-r5-b / 2 | 4.00; 54.10% (132/244) | 3.33; 54.25% (134/247) | 5.45; 52.94% (126/238) | higher false, higher recall / higher false, higher recall / higher false, higher recall |

At TRAIN-2 r5-a changes from more false alarms than YOLO under as-labelled and match-ball-only rules to fewer under visible-ball credits; r5-b remains higher under all three displayed rules only with credit-only false counting. All RF models have higher overall recall than YOLO under each displayed sensitivity, but these are recipe-selected clips with provisional semantics, not evidence of a winner.

The any-visible-ball false column is credit-only: s8-s10 remain among the original 60 no-ball frames. A full relabel removes those three frames from false exposure (57 no-ball frames) and all their detections from false counts. Strict false/10s after full relabelling, in order YOLO r2-b / rf-b / r5-a / r5-b: TRAIN-1 1.75 / 2.11 / 1.75 / 1.05; TRAIN-2 3.16 / 5.26 / 2.46 / 3.16. At TRAIN-2 r5-b ties YOLO under full relabelling: its higher-false direction under all three displayed rules applies only to the credit-only version. R5-a has fewer false alarms than YOLO under either visible-ball interpretation. These are sensitivities only; no label or primary result changed.

One MJ decision covering n21 s0-s10: count any visible ball, or the match ball only; the current labels follow neither rule consistently. Adjudication sheet: ~/codex-runs/ball-r5-n21/adjudicate-s0-s10.png. No label was changed. The new sheet includes all11 current labels, source context, an enlarged background region and retained boxes from all four models at both budgets.

## Size buckets: top-1 hits / visible labels

Sizes are the same independent matched RF baseline-box short sides as previous rounds, not inferred from this round's successes. Unknown sizes stay in the denominator. These are teacher box estimates, not human-drawn boundaries. TRAIN has only one independently sized ≥24px on-ball example; H has 22.

Zoom fits recover more large balls only at the looser threshold, within one 12-second sequence; run-to-run noise is as large as the effect. All 22 held-out ≥24px labels belong to m04-n17-t717-253073-260377, in relative intervals 0–1.5s, 3.0–3.5s and 4.5–12.0s. At TRAIN-1 selected A has 9 hits, below no-zoom RF b's 11; A and B share zoom yet differ by 3 frames. These are teacher-estimated sizes, not independent human box measurements.

TRAIN targets are synthetic:592/631 sit at the18.680435px floor,23 are≥24px, maximum32.85px. A1.2× zoom raises the floor to22.42px, still below24px. These631 targets differ from the independent matched-size on-ball bucket (only1 TRAIN label≥24px).

| Model / TRAIN target | Bucket | TRAIN hits / labels | H hits / labels |
|---|---|---:|---:|
| yolo-r2-b / 1 | <6 | 9/10 | 0/1 |
| yolo-r2-b / 1 | 6–<10 | 133/171 | 27/39 |
| yolo-r2-b / 1 | 10–<16 | 61/76 | 34/46 |
| yolo-r2-b / 1 | 16–<24 | 19/19 | 3/3 |
| yolo-r2-b / 1 | >=24 | 1/1 | 16/22 |
| yolo-r2-b / 1 | unknown | 12/23 | 1/11 |
| yolo-r2-b / 2 | <6 | 9/10 | 0/1 |
| yolo-r2-b / 2 | 6–<10 | 144/171 | 27/39 |
| yolo-r2-b / 2 | 10–<16 | 68/76 | 36/46 |
| yolo-r2-b / 2 | 16–<24 | 19/19 | 3/3 |
| yolo-r2-b / 2 | >=24 | 1/1 | 19/22 |
| yolo-r2-b / 2 | unknown | 17/23 | 1/11 |
| rf-b / 1 | <6 | 9/10 | 0/1 |
| rf-b / 1 | 6–<10 | 163/171 | 33/39 |
| rf-b / 1 | 10–<16 | 75/76 | 42/46 |
| rf-b / 1 | 16–<24 | 18/19 | 3/3 |
| rf-b / 1 | >=24 | 1/1 | 11/22 |
| rf-b / 1 | unknown | 19/23 | 2/11 |
| rf-b / 2 | <6 | 9/10 | 0/1 |
| rf-b / 2 | 6–<10 | 164/171 | 33/39 |
| rf-b / 2 | 10–<16 | 75/76 | 42/46 |
| rf-b / 2 | 16–<24 | 18/19 | 3/3 |
| rf-b / 2 | >=24 | 1/1 | 11/22 |
| rf-b / 2 | unknown | 19/23 | 3/11 |
| rf-r5-a / 1 | <6 | 6/10 | 0/1 |
| rf-r5-a / 1 | 6–<10 | 148/171 | 27/39 |
| rf-r5-a / 1 | 10–<16 | 64/76 | 37/46 |
| rf-r5-a / 1 | 16–<24 | 18/19 | 3/3 |
| rf-r5-a / 1 | >=24 | 1/1 | 9/22 |
| rf-r5-a / 1 | unknown | 8/23 | 0/11 |
| rf-r5-a / 2 | <6 | 8/10 | 0/1 |
| rf-r5-a / 2 | 6–<10 | 156/171 | 29/39 |
| rf-r5-a / 2 | 10–<16 | 69/76 | 43/46 |
| rf-r5-a / 2 | 16–<24 | 19/19 | 3/3 |
| rf-r5-a / 2 | >=24 | 1/1 | 16/22 |
| rf-r5-a / 2 | unknown | 11/23 | 2/11 |
| rf-r5-b / 1 | <6 | 4/10 | 0/1 |
| rf-r5-b / 1 | 6–<10 | 138/171 | 26/39 |
| rf-r5-b / 1 | 10–<16 | 55/76 | 34/46 |
| rf-r5-b / 1 | 16–<24 | 16/19 | 3/3 |
| rf-r5-b / 1 | >=24 | 1/1 | 12/22 |
| rf-r5-b / 1 | unknown | 3/23 | 0/11 |
| rf-r5-b / 2 | <6 | 7/10 | 0/1 |
| rf-r5-b / 2 | 6–<10 | 156/171 | 30/39 |
| rf-r5-b / 2 | 10–<16 | 70/76 | 40/46 |
| rf-r5-b / 2 | 16–<24 | 18/19 | 3/3 |
| rf-r5-b / 2 | >=24 | 1/1 | 19/22 |
| rf-r5-b / 2 | unknown | 8/23 | 2/11 |

## Fixed 0.1, not comparable across models

These secondary numbers reproduce the prior convention. All explicitly includes training clips. They must not be read as an equal-error head-to-head.

| Model | On-ball top-1 All / T / H | Manual-only All / T / H | Oracle over N All / T / H | Top-1 precision All / T / H | Strict false/10s All / T / H | Boxes/visible on-ball All / T / H |
|---|---:|---:|---:|---:|---:|---:|
| yolo-r2-b | 76.30% / 79.67% / 68.03% | 72.97% / 78.86% / 44.00% | 76.54% / 80.00% / 68.03% | 96.99% / 97.95% / 94.32% | 1.32 / 1.15 / 1.67 | 0.80 / 0.84 / 0.70 |
| rf-b | 89.10% / 95.00% / 74.59% | 88.85% / 93.90% / 64.00% | 89.34% / 95.00% / 75.41% | 96.66% / 98.96% / 90.10% | 2.42 / 1.31 / 4.67 | 0.99 / 1.04 / 0.85 |
| rf-r5-a | 82.23% / 86.67% / 71.31% | 79.73% / 84.96% / 54.00% | 82.70% / 87.33% / 71.31% | 97.20% / 98.11% / 94.57% | 2.09 / 1.80 / 2.67 | 0.89 / 0.95 / 0.75 |
| rf-r5-b | 86.02% / 88.67% / 79.51% | 82.77% / 87.40% / 60.00% | 86.73% / 89.67% / 79.51% | 93.80% / 95.68% / 88.99% | 4.73 / 4.10 / 6.00 | 1.00 / 1.05 / 0.88 |

## Training and diagnostic learning curves

Uniform zoom [0.8,1.2] about native content centre (480,270), translation +/-5% of native width/height, horizontal flip p=0.5; pad to 960 square; no squash

100-step linear warmup; step decay x0.1 after epochs 2 and 4. AdamW, FP32, batch8, seed42; official layer-wise parameter groups, gradient norm clipping0.1. Native 960×540 content is padded to 960², never squashed. Scale targets remain clamp(TRAIN affine(y),18.6804351807,48). No observed-box override from the superseded long-training brief. Pseudo labels off.

Mine original unaugmented TRAIN tiles at >=0.3, centre in content and no human click within 20 native px. Start empty; refresh after each 2 complete epochs (first from trained epoch2, never the reset COCO head); add one extra copy per hard tile per epoch, retaining all original annotations.

Before fit b: defer first hard-negative mining until trained epoch2; the reset COCO ball classifier is not informative. This removes only an unexecuted replay branch from fit a; its training path and parameters are unchanged. No held-out results informed the correction.

During fit a epoch1, before either new fit had any held-out evaluation: replace preliminary TRAIN-ranked model choice with the primary final-checkpoint H metric. This is explicitly optimistic selection on recipe-selected clips; no fit, checkpoint stopping, or TRAIN calibration changes.

Fit A launched under a TRAIN-only rule; it was amended to the held-out ≤2 ceiling after old rf-b's held-out false rates were known (before any new-fit held-out evaluation); under the original rule rf-b (95.00% TRAIN top-1 at TRAIN-1) would have won, changing the kit suggestion source.

Equal wall time was unequal compute: A received1,233 optimizer steps /9,852 tile-views; B1,325 /10,586 (+7.5% views) in the same90-minute budget. A ComfyUI job was active at some point; its effect on fitting time is unconfirmed. Future fits must be budgeted by optimizer steps, not wall clock.

No evidence more epochs help at strict budgets; do not plan longer m04 training. Epoch-2 curves are censored at confidence0.01: TRAIN false/10s reaches only1.48 (A) and1.64 (B), not the requested2.0 budget. Their H endpoints are3.00 and2.00 respectively (the approximate2/10s censoring description applies to B). At TRAIN-2 H hits ROSE epoch-2→FINAL: A84→93 with false/10s3.00→3.33; B87→94 with2.00→4.00. Only the first of the two declared LR decays took effect: epoch3 uses0.1× LR, and training stops during epoch4 before the epoch5 0.01× stage. Intermediate checkpoints remain diagnostic, never selected.

Every base TRAIN tile is included in each complete epoch (631 positive, 2381 negative); replay adds one copy of each mined hard tile, retaining its positive annotation when present. Mining is performed on unaugmented TRAIN images only. Stopping compares unaugmented base-TRAIN loss, avoiding a changing replay mixture; three complete epochs without >1% improvement, 12-epoch / 90-minute phase-boundary budget. Final partial epochs are reported, never called complete.

Seed42 is shared, but MPS uses deterministic-algorithm warnings rather than guaranteed bitwise determinism. The TRAIN histories already differ before replay begins. A single fit per setting cannot isolate replay's causal effect from run variation; full per-epoch losses are retained in the JSON.

| Fit | Complete epochs + partial tiles | Total tile views | Minutes | Stop reason | Hard negatives per refresh (epoch: count) |
|---|---:|---:|---:|---|---|
| rf-r5-a | 3 + 816/3012 tiles | 9852 | 90.03 | 90-minute wall budget | none |
| rf-r5-b | 3 + 1544/3018 tiles | 10586 | 90.04 | 90-minute wall budget | 0: 0 (0 negative), 2: 6 (5 negative) |

Checkpoints below are diagnostic only. Both fits had finished before any of these held-out evaluations. Thresholds are re-chosen on TRAIN for each checkpoint; no number below selects a checkpoint or alters a fit.

| Fit / checkpoint | TRAIN target | Threshold | Top-1 on-ball T / H | False/10s T / H | Censoring |
|---|---:|---:|---:|---:|---|
| rf-r5-a / FINAL | 1 | 0.30314332246780401 | 81.67% / 62.30% | 0.98 / 2.00 | — |
| rf-r5-a / FINAL | 2 | 0.062361281365156181 | 88.00% / 76.23% | 1.97 / 3.33 | — |
| rf-r5-a / epoch-2 | 1 | 0.017670813947916034 | 71.33% / 65.57% | 0.98 / 2.00 | — |
| rf-r5-a / epoch-2 | 2 | 0.01 | 75.67% / 68.85% | 1.48 / 3.00 | SAVE FLOOR: target not reached |
| rf-r5-b / FINAL | 1 | 0.49416390061378485 | 72.33% / 61.48% | 0.98 / 1.33 | — |
| rf-r5-b / FINAL | 2 | 0.19647511839866641 | 86.67% / 77.05% | 1.97 / 4.00 | — |
| rf-r5-b / epoch-2 | 1 | 0.031473584473133094 | 70.33% / 68.03% | 0.98 / 1.00 | — |
| rf-r5-b / epoch-2 | 2 | 0.01 | 77.67% / 71.31% | 1.64 / 2.00 | SAVE FLOOR: target not reached |

The full held-out recall-versus-false/10s staircase (all score breakpoints down to 0.01) is committed in the JSON at round5.measurements.models.<model>.held_curve_diagnostic_only. It is a diagnostic curve, not an operating-point selection source.

## Track versus truth at TRAIN-chosen operating points

| Model / TRAIN target | Coverage T / H | Longest correct seconds T / H | Wrong / track points T / H | Track precision T / H | Wrong frames T / H |
|---|---:|---:|---:|---:|---:|
| yolo-r2-b / 1 | 66.56% / 38.11% | 24.00 / 2.50 | 4.29% / 8.04% | 85.89% / 83.04% | 21 / 9 |
| yolo-r2-b / 2 | 68.94% / 38.52% | 24.00 / 3.00 | 6.99% / 19.26% | 79.96% / 69.63% | 38 / 26 |
| rf-b / 1 | 76.70% / 44.26% | 25.00 / 6.00 | 3.83% / 23.27% | 80.67% / 67.92% | 23 / 37 |
| rf-b / 2 | 75.75% / 44.67% | 24.50 / 6.00 | 5.24% / 25.60% | 78.23% / 64.88% | 32 / 43 |
| rf-r5-a / 1 | 71.47% / 39.34% | 19.50 / 3.00 | 3.18% / 21.05% | 84.46% / 72.18% | 17 / 28 |
| rf-r5-a / 2 | 73.38% / 42.62% | 24.00 / 3.50 | 5.15% / 22.93% | 79.55% / 66.24% | 30 / 36 |
| rf-r5-b / 1 | 67.19% / 36.89% | 19.50 / 3.00 | 3.04% / 18.11% | 85.83% / 70.87% | 15 / 23 |
| rf-r5-b / 2 | 72.90% / 43.03% | 24.00 / 4.50 | 3.66% / 21.66% | 80.14% / 66.88% | 21 / 34 |

Track precision and wrong-point rates use track points on visible labelled frames; no-ball and unlabelled frames do not enter those denominators. Coverage penalises a tracker that emits little.

## Controlled throughput and a 90-minute match

3 interleaved repeats per model per sampling mode after bench training/inference stopped. Before each repeat require three quiet one-second observations: GPU utilization <=10%, empty ComfyUI queue, and Ollama workers below2% CPU. Poll active llama-server/Ollama, bench training/inference and ComfyUI during timing. The total quiet wait across all repeats is capped at 15 minutes; after exhaustion repeats proceed and are labelled contended (steady background load). Activity starting during a repeat also labels that repeat contended. Every repeat records mediaanalysisd CPU and ioreg AGX GPU summaries; per-second process samples remain private. Retrospective flags mark mean mediaanalysisd CPU >=30% as contended, without changing the nonblocking wait policy or excluding any timing repeat. macOS media-analysis CPU load is recorded separately: sustained roughly two-core housekeeping was observed with0% GPU utilization, so it is not treated as active GPU work. These are observed desktop conditions, not an otherwise-idle-CPU laboratory. This detects known competing work, not every possible GPU client. Sampled mode covers all 2fps samples of the three TRAIN clips; native mode covers the first 64 consecutive native frames of each (192 frames/repeat). Warmup/compile excluded; source decode (including skipped frames), RGB conversion, cropping/padding, four-tile batched inference and prediction materialization included. Merge/JSON writing excluded consistently. Accuracy passes use eager FP32 separately; these optimized throughput measurements do not substitute for scored outputs.

Timing status: **mixed contention: four repeats flagged by mediaanalysisd mean CPU >=30%**; total quiet wait 73.7s of the shared 900s cap. mediaanalysisd and PhotosReliveWidget are nonblocking steady background by orchestrator decision; active model generation and bench jobs remain blocking until the wait budget expires.

On this M4 Max, RF-DETR Nano@960 is about 7.6-7.8x slower than YOLO11n at 2 fps sampling and 10.0-10.9x at native rate. The ratio is conservative: YOLO ran FP32 eager on a ~960x544 letterbox with the GPU 40-58% busy; RF ran FP16 JIT on 960x960. YOLO native55.2 exceeds sampled37.7 FPS because common.samples decodes and RGB-converts approximately14 skipped frames per2fps sample inside the timer. The GPU40–58% characterization is approximate; measured per-repeat GPU means/ranges remain below. Historical11.5-vs51FPS cause remains unconfirmed.

Four repeats had mean mediaanalysisd CPU≥30%, each also the slowest repeat of its model/sampling mode: r5-a native1, rf-b native1, rf-b sampled2, YOLO sampled2. They are labelled contended and retained in medians/ranges. This coincidence does not establish causation. RF b's2fps match projection ranges25.54–41.09min across repeats (about25–41min).

Separate linear projections from measured 2fps-pipeline and native-pipeline throughput; native does not inherit skipped-frame decode cost. These are not actual 90-minute match runs. Native bursts include three seeks per192 frames, a conservative overhead versus continuous match decoding; long-run thermal behaviour is unmeasured.

UNCONFIRMED: historical 11.51 vs 50.9–51.0 FPS were separate sessions. Current controlled session resolves present throughput, not their historical cause.

An unrelated ComfyUI job was active during accuracy inference; this can affect incidental wall times. Its start time and any effect on training are unconfirmed. This does not establish the cause of historical YOLO 11.5-versus-51 FPS. No unrelated process was interrupted. Controlled timing waits for an empty ComfyUI queue and monitors it during all repeats. The first timing session was also discarded after independent Ollama/media-analysis activity appeared (GPU89% after our process stopped). YOLO sampled throughput swung39.03 to7.87FPS in that discarded session. This reproduces large timing variability coincident with competing work, but does not prove the historical11.5-versus51FPS cause. The final guard has a shared 900s quiet-wait cap and labels contended repeats rather than discarding or waiting indefinitely. mediaanalysisd and PhotosReliveWidget are recorded nonblocking background, not evidence by themselves of competing generation.

| Model | Mode | Repeat FPS: sampled / native | Median FPS: sampled / native | 90 min at 2fps: wall min | 90 min at native fps: wall min |
|---|---|---:|---:|---:|---:|
| mj-r5-rf-a | optimize_for_inference JIT batch4 FP16 | 4.98, 5.06, 4.93 / 3.30, 5.08, 5.37 | 4.98 / 5.08 | 36.15 | 530.77 |
| rf-b | optimize_for_inference JIT batch4 FP16 | 7.05, 4.38, 4.81 / 3.41, 5.53, 5.51 | 4.81 / 5.51 | 37.39 | 489.77 |
| yolo-r2-b | Ultralytics FP32 raw 960x540, imgsz960, batch4 | 40.46, 27.57, 37.70 / 51.60, 55.38, 55.21 | 37.70 / 55.21 | 4.77 | 48.86 |

Per-repeat caveats (summaries only; process IDs, resident memory and per-second traces are private):

| Model / sampling / repeat | Status | mediaanalysisd CPU mean / max % | AGX GPU mean / max % |
|---|---|---:|---:|
| mj-r5-rf-a / sampled / 1 | no flagged contention (background load recorded) | 28.5 / 109.1 | 96.2 / 97.0 |
| mj-r5-rf-a / sampled / 2 | no flagged contention (background load recorded) | 16.2 / 97.7 | 96.5 / 98.0 |
| mj-r5-rf-a / sampled / 3 | no flagged contention (background load recorded) | 0.0 / 0.4 | 96.6 / 97.0 |
| mj-r5-rf-a / native / 1 | contended (mediaanalysisd mean CPU >=30%) | 61.9 / 113.1 | 96.1 / 99.0 |
| mj-r5-rf-a / native / 2 | no flagged contention (background load recorded) | 0.0 / 0.3 | 96.8 / 98.0 |
| mj-r5-rf-a / native / 3 | no flagged contention (background load recorded) | 0.0 / 0.1 | 96.7 / 97.0 |
| rf-b / sampled / 1 | no flagged contention (background load recorded) | 0.0 / 0.5 | 95.2 / 96.0 |
| rf-b / sampled / 2 | contended (mediaanalysisd mean CPU >=30%) | 37.0 / 111.1 | 96.7 / 100.0 |
| rf-b / sampled / 3 | no flagged contention (background load recorded) | 0.0 / 0.1 | 96.6 / 98.0 |
| rf-b / native / 1 | contended (mediaanalysisd mean CPU >=30%) | 59.8 / 111.8 | 94.3 / 98.0 |
| rf-b / native / 2 | no flagged contention (background load recorded) | 1.6 / 55.4 | 93.9 / 97.0 |
| rf-b / native / 3 | no flagged contention (background load recorded) | 0.0 / 0.1 | 94.0 / 97.0 |
| yolo-r2-b / sampled / 1 | no flagged contention (background load recorded) | 0.0 / 0.1 | 41.8 / 45.0 |
| yolo-r2-b / sampled / 2 | contended (mediaanalysisd mean CPU >=30%) | 39.8 / 98.6 | 31.3 / 56.0 |
| yolo-r2-b / sampled / 3 | no flagged contention (background load recorded) | 0.0 / 0.0 | 40.1 / 45.0 |
| yolo-r2-b / native / 1 | no flagged contention (background load recorded) | 0.0 / 0.1 | 45.2 / 67.0 |
| yolo-r2-b / native / 2 | no flagged contention (background load recorded) | 0.0 / 0.0 | 45.8 / 60.0 |
| yolo-r2-b / native / 3 | no flagged contention (background load recorded) | 0.0 / 0.1 | 44.6 / 60.0 |

| Model | Sampled FPS min–max | Native FPS min–max | 2fps match minutes min–max | Native match minutes min–max |
|---|---:|---:|---:|---:|
| mj-r5-rf-a | 4.93–5.06 | 3.30–5.37 | 35.55–36.51 | 502.17–816.70 |
| rf-b | 4.38–7.05 | 3.41–5.53 | 25.54–41.09 | 487.55–790.24 |
| yolo-r2-b | 27.57–40.46 | 51.60–55.38 | 4.45–6.53 | 48.70–52.28 |

Source frame rate: 29.97002997 fps. Mode fallback errors: none.

Optimized-versus-eager TRAIN probe: {'mj-r5-rf-a': {'maximum_top1_centre_delta_px': 0.14277268734639317, 'maximum_top1_score_delta': 0.007046103477478027, 'note': '15 TRAIN frames, not full optimized-accuracy validation; primary metrics remain eager FP32.', 'threshold': 0.303143322467804, 'top1_presence_changes': 0, 'train_frames': 15}, 'rf-b': {'maximum_top1_centre_delta_px': 0.16704292540239415, 'maximum_top1_score_delta': 0.003093242645263672, 'note': '15 TRAIN frames, not full optimized-accuracy validation; primary metrics remain eager FP32.', 'threshold': 0.19124995172023776, 'top1_presence_changes': 0, 'train_frames': 15}}.

## Method for future rounds

Calibrate thresholds on TRAIN-disjoint clips; budget fits by optimizer steps; always show matched-false-rate curves and per-clip counts beside TRAIN operating points. No further m04 training. The next real evidence is a fresh labelled match from a different venue and day.

## What a fresh match must test

Label a different match at a different venue/day, with players absent from training; freeze it as the true holdout before any recipe or threshold choice. Use blind initial annotation or an independently reviewed sample to check suggestion conditioning. Include distant balls, close/large balls, blur and occlusion, no-visible-ball intervals, footwear/line distractors and spare balls. Define the match-ball identity explicitly. Compare at TRAIN-chosen operating points with per-clip/sequence counts, not independent-frame claims. These 20 clips cannot support a product winner claim.

Better source pixels help, but do not fix the problem alone: the prior bucket extrapolation was 60.7% → 66.4% held-out for 2× ball pixels, not a measurement. Scale diversity and semantic negatives still matter. A 4K/follow-cam export is a hypothesis to test on fresh footage, not a guarantee.

## Kit and execution

{'browser_verification': 'PASS: 1057 exact seeded labels, no auto-save, all-frame navigation, newer labels and accepted-source/manual-clear provenance preserved', 'build': {'build_version': 8, 'clips': 20, 'confirmed_seed_labels': 1057, 'fps': 2, 'frames': 1105, 'frozen_set_id': '1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f', 'suggestions': 688, 'suggestions_by_source': {'model:mj-r5-rf-a:r5-train-fp1': 688}}, 'build_version': 8, 'confirmed_seed_labels': 1057, 'existing_labels_sha256': 'a0f51b42cb95e5327bf45fd353fd46f50495f99c096709b8836c7309ed2373ff', 'index_sha256': '164ed33753991ef381f706d880936b9190056512add26c9e110e29a5c00e39a7', 'model': 'rf-r5-a', 'source': 'model:mj-r5-rf-a:r5-train-fp1', 'suggestions': 688, 'suggestions_sha256': '57f722898f0d9caa46673997a5a142636fa4f809e7fefbb5e82b6d3bb0ed0b97', 'threshold': 0.303143322467804, 'unlabelled': 48, 'unlabelled_with_suggestion': 9}

The kit is seeded only from the selected RF-DETR model at its TRAIN-chosen 1.0 operating point. MJ's existing 1057 labels are preserved, including accepted-source provenance; 48 scheduled frames remain unlabelled. Review suggestions, click remaining visible balls or mark no ball, then export. Keep new-match labels separate as the true holdout.

Player-overlap buckets in historical analyses still use YOLO11n person detections: bench-only, not a licence-clean serving dependency. Frozen aggregate fixtures contain no label coordinates, images or checkpoints. Original protocol snapshots retain historical wording for hash verification; all current evaluation presentation uses ‘recipe-selected on these clips’.

Round4 calibration effect superseded; RF a+b 4.33 passes/13052 views/58 min; YOLO r2-b 10 epochs/30120 views/20.1 min, r2-a/r3-a 11, r3-b 10. Historical round-4 interpretation only, superseded by the current epoch/budget framing: RF flat train loss plus train/held gap suggested generalisation, not proven undertraining. Floor recipe also selected using these held-out clips.

User reports orchestrator pushed d2268bd; round-4 agent did not push.

Canonical tracker fixture environment: CPython3.11.16 / NumPy2.4.6, no SciPy installed (~/Projects/loanarmy/.loan). RF environment: CPython3.12.14 / NumPy2.3.5 / SciPy1.18.1 (~/models/tinyball/.venv-mj). Chosen fix: only duration-weighted group-continuity comparisons allow rel/abs tolerance1e-12; per-clip tracks and all counts remain exact. The reproduced failure involved three aggregate float differences of5.6e-17–1.1e-16. Canonical saved values are returned after validation, preserving report bytes. No SciPy function is called on this path; attributing the discrepancy to SciPy itself is unconfirmed. RF full suite passes429 tests including the framing regressions, in the worktree and git-archive export.

{'git_archive_pytest': {'canonical': 455, 'minimal_passed': 452, 'minimal_skipped': 3, 'rf_venv': 455}, 'rebuild': 'JSON and Markdown byte-for-byte from committed fixtures in minimal git-archive export', 'round': 'P1 checkpoint integrity on c8eb5e67 (PR #1081)', 'ruff': 'check and format --check PASS in worktree and archive', 'summary': 'All gates passed in .loan and RF environments, including 23 checkpoint-integrity regressions. Final staged-tree verification repeats after recording this result; external receipt records exact tree/ledger hashes, one commit and clean status. All six on-disk checkpoint hashes match fit declarations and saved envelopes; model, learning-curve, selection, throughput and kit aggregates are unchanged from c8eb5e67. No labels, weights, detections, images or crops committed. No training, inference, kit changes or push.', 'worktree_pytest': {'canonical': 455, 'rf_venv': 455}}

### Checkpoint integrity verification

Before runtime/model loading or output creation, compare --model SHA256 to the independent fit final hash (default) or the checkpoint hash selected explicitly with --checkpoint-epoch N, without overwriting the final declaration. Capture and finish validate every saved final and diagnostic envelope against the registered candidate fit summary before scoring or artifact writes.

all saved passes verified against their declared weights; no result changes

SHA256 prefixes below; full hashes and audit reproduction are in the execution fixture. No passes rerun; no table cells changed.

| Pass | Weights path (private) | Declared | Recorded | On disk | Status |
|---|---|---|---|---|---|
| yolo-r2-b | /Users/mjjones/models/tinyball/mj-r2-b/weights.pt | 5571f285a130 | 5571f285a130 | 5571f285a130 | MATCH |
| rf-b | /Users/mjjones/models/tinyball/mj-r4-rf-b/weights.pt | 8c94d8e80c91 | 8c94d8e80c91 | 8c94d8e80c91 | MATCH |
| rf-r5-a | /Users/mjjones/models/tinyball/mj-r5-rf-a/weights.pt | 9dfafa1c3faa | 9dfafa1c3faa | 9dfafa1c3faa | MATCH |
| rf-r5-a / epoch-2 | /Users/mjjones/models/tinyball/mj-r5-rf-a/epoch-02.pt | da08669e538e | da08669e538e | da08669e538e | MATCH |
| rf-r5-b | /Users/mjjones/models/tinyball/mj-r5-rf-b/weights.pt | 5cb57f0cc262 | 5cb57f0cc262 | 5cb57f0cc262 | MATCH |
| rf-r5-b / epoch-2 | /Users/mjjones/models/tinyball/mj-r5-rf-b/epoch-02.pt | 23cc66053331 | 23cc66053331 | 23cc66053331 | MATCH |

Outstanding limits: N21 ball-identity adjudication remains outstanding. No further m04 training; fresh venue/day match labels and TRAIN-disjoint calibration remain outstanding. No labels changed, model inference, timing repeats, training, kit reselection or push.

# Historical rounds 1–4 — fixed 0.1, not comparable across model families

The following numeric tables are retained for audit and comparison. Their fixed-confidence head-to-head interpretation and prior optimistic-exposure wording are superseded above.

Trainer swap — held-out top-1 real gate: **no candidate passes**.

No RF-DETR model qualifies at ≤2 false/10s; diagnostic recall leader: **tinyball-r4-rf-b**, H on-ball top-1 **74.59%**, manual-only 64.00%, **4.67 false/10s**, 3.72 FPS. Versus YOLO r2-b: **+6.56 percentage points** H on-ball recall.

Improvement under the required recall-and-false-rate rule: **none**. The RF-DETR product direction does not depend on YOLO winning this benchmark.

ultralytics is bench-only and must not enter the serving path; the product model is RF-DETR (Apache-2.0).

RF-DETR Nano uses the Apache-2.0 implementation and official COCO weights; the installed package licence is recorded with its hash in the execution fixture. [Upstream package and model licensing](https://github.com/roboflow/rf-detr#license).

# Trainer swap: RF-DETR versus YOLO11-nano

All = all 20 clips (incl. training clips); H = held-out (recipe-selected on these clips). All / H always uses the same fixed 14/6 split. H has 244 visible / 60 no-ball labels overall, including 122 visible on-ball labels. These clips have also informed subsequent error analysis and model selection; H is optimistic and is not a clean test set.

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

All = all 20 clips (incl. training clips); H = held-out (recipe-selected on these clips). All / H always uses the same fixed 14/6 split. H has 244 visible / 60 no-ball labels overall, including 122 visible on-ball labels. These clips have also informed subsequent error analysis and model selection; H is optimistic and is not a clean test set.

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

All = all 20 clips (incl. training clips); H = held-out (recipe-selected on these clips). All / H always uses the same fixed 14/6 split. H has 244 visible / 60 no-ball labels overall, including 122 visible on-ball labels. These clips have also informed subsequent error analysis and model selection; H is optimistic and is not a clean test set.

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

### held-out (recipe-selected on these clips): clip ids

- `m04-n05-t3007-284945-287898`
- `m04-n12-t1411-679986-681985`
- `m04-n17-t717-253073-260377`
- `m04-n17-t717-416826-418915`
- `m04-n21-t3011-390297-390800`
- `m04-n24-t3013-679939-681217`

## Size buckets: highest-confidence hits / visible labels

All = all 20 clips (incl. training clips); H = held-out (recipe-selected on these clips). All / H always uses the same fixed 14/6 split. H has 244 visible / 60 no-ball labels overall, including 122 visible on-ball labels. These clips have also informed subsequent error analysis and model selection; H is optimistic and is not a clean test set.

Sizes are the same frozen independent RF full/2×2/3×3 matched-box short-side median used in round 3. RF-DETR's learned target sizes do not define these buckets. Missing teacher matches remain unknown; excluding them would flatter recall.

| Candidate | <6px All / H | 6–<10px All / H | 10–<16px All / H | 16–<24px All / H | ≥24px All / H | Unknown All / H |
|---|---:|---:|---:|---:|---:|---:|
| tinyball-r2-b | 9/11 / 0/1 | 162/210 / 27/39 | 97/122 / 34/46 | 22/22 / 3/3 | 19/23 / 18/22 | 13/34 / 1/11 |
| tinyball-r3-a | 6/11 / 0/1 | 142/210 / 24/39 | 79/122 / 34/46 | 17/22 / 3/3 | 20/23 / 19/22 | 0/34 / 0/11 |
| tinyball-r3-b | 8/11 / 0/1 | 149/210 / 20/39 | 91/122 / 34/46 | 22/22 / 3/3 | 20/23 / 19/22 | 9/34 / 0/11 |
| tinyball-r4-rf-a | 9/11 / 0/1 | 189/210 / 28/39 | 111/122 / 41/46 | 22/22 / 3/3 | 13/23 / 12/22 | 19/34 / 3/11 |
| tinyball-r4-rf-b | 9/11 / 0/1 | 196/210 / 33/39 | 117/122 / 42/46 | 21/22 / 3/3 | 12/23 / 11/22 | 21/34 / 2/11 |

## Matching-rule sanity floors

All = all 20 clips (incl. training clips); H = held-out (recipe-selected on these clips). All / H always uses the same fixed 14/6 split. H has 244 visible / 60 no-ball labels overall, including 122 visible on-ball labels. These clips have also informed subsequent error analysis and model selection; H is optimistic and is not a clean test set.

Same permanent seed 20260911, 100 repetitions; corrupt label positions within each evaluation scope while keeping detections fixed. Means below are sanity floors, not alternate truth or a threshold-tuning set.

| RF candidate / control | On-ball top-1 mean All / H | On-ball oracle mean All / H |
|---|---:|---:|
| tinyball-r4-rf-a / shuffled_within_clip | 4.16% / 2.24% | 4.32% / 2.44% |
| tinyball-r4-rf-a / uniform_random | 0.06% / 0.02% | 0.07% / 0.02% |
| tinyball-r4-rf-b / shuffled_within_clip | 4.11% / 2.17% | 4.25% / 2.31% |
| tinyball-r4-rf-b / uniform_random | 0.06% / 0.03% | 0.07% / 0.05% |

## Track versus truth

All = all 20 clips (incl. training clips); H = held-out (recipe-selected on these clips). All / H always uses the same fixed 14/6 split. H has 244 visible / 60 no-ball labels overall, including 122 visible on-ball labels. These clips have also informed subsequent error analysis and model selection; H is optimistic and is not a clean test set.

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

held-out (recipe-selected on these clips). **Current-best selection now uses held-out results and is optimistic beyond that prior exposure.** Fresh labelled club footage is the true test; these 20 clips are no longer a clean test set.

# Ball human truth — round 3 review and scale targets

Gate = highest-confidence top-1 on-ball recall ≥80% AND ≤1 detection/10s on explicit no-ball frames. Model eligibility at ≤2 false/10s is a separate selection rule, not a PASS. Matching is inclusive 20 native px at confidence ≥0.1; ties use saved order. Oracle precision credits at most one nearest box per visible label and penalises all duplicate guesses. Top-1 precision is reported separately below. Boxes/frame in headlines uses visible on-ball frames, matching the reviewer; JSON also retains boxes per all labelled frames.

## Corrected round-1 headline (original 4/16 split)

H = held-out (recipe-selected on these clips): original 16 evaluation clips for this table, 575 visible / 144 no-ball. On-ball H is the same two clips and 122 visible labels used below. Baselines are filtered to those same clips for comparability; none was fitted on this dataset. The All column preserves the reviewer’s six-on-ball-clip ranking.

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

All = all 20 clips (incl. training clips); H = held-out (recipe-selected on these clips), using the fixed six clips unless explicitly stated otherwise. Paired cells are All / H.

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

All = all 20 clips (incl. training clips); H = held-out (recipe-selected on these clips), using the fixed six clips unless explicitly stated otherwise. Paired cells are All / H.

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

All = all 20 clips (incl. training clips); H = held-out (recipe-selected on these clips), using the fixed six clips unless explicitly stated otherwise. Paired cells are All / H.

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

All = all 20 clips (incl. training clips); H = held-out (recipe-selected on these clips), using the fixed six clips unless explicitly stated otherwise. Paired cells are All / H.

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

All = all 20 clips (incl. training clips); H = held-out (recipe-selected on these clips), using the fixed six clips unless explicitly stated otherwise. Paired cells are All / H.

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


Current best tinyball-r2-b: **top-1** error buckets on on-ball clips. All = all 20 clips (incl. training clips); H = held-out (recipe-selected on these clips), using the fixed six clips unless explicitly stated otherwise. Paired cells are All / H.

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

All = all 20 clips (incl. training clips); H = held-out (recipe-selected on these clips), using the fixed six clips unless explicitly stated otherwise. Paired cells are All / H.

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

- Prior exposure: held-out (recipe-selected on these clips). The r1-960 49.39% original held-out overall oracle recall also served as its own 640-vs-960 selection statistic: one binary aggregate choice. Round3 additionally uses held-out error analysis and explicit held-out model selection, so its selected estimate is more optimistic.
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
