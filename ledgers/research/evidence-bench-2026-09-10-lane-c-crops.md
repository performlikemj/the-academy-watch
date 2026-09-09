On 20 shared scored clips: e1e-cropctx-8b-dense (qwen3-vl:8b, 23.8 boxed frames/attempt): off-pitch false-yes 50.00%, touch false-yes 0.00%, touch recall N/A (raw 0/6), gate 2 WITHHELD; e1d-checks-dense (qwen3-vl:8b, 11.9 boxed frames/attempt): off-pitch false-yes 57.14%, touch false-yes 0.00%, touch recall N/A (raw 0/6), gate 2 WITHHELD; e1d-checks-32b-dense (qwen3-vl:32b, 11.9 boxed frames/attempt): off-pitch false-yes 50.00%, touch false-yes 0.00%, touch recall N/A (raw 0/6), gate 2 WITHHELD; e1d-checks-27b-dense (qwen3.8:27b-obliterated-q8, 11.9 boxed frames/attempt): off-pitch false-yes 64.29%, touch false-yes 0.00%, touch recall N/A (raw 0/6), gate 2 WITHHELD; e1e-crop-8b-dense (qwen3-vl:8b, 11.9 boxed frames/attempt): off-pitch false-yes 50.00%, touch false-yes 0.00%, touch recall N/A (raw 0/6), gate 2 WITHHELD; e1d-checks-prod30 (qwen3-vl:8b, 1.45 boxed frames/attempt): off-pitch false-yes 50.00%, touch false-yes 0.00%, touch recall N/A (raw 0/6), gate 2 WITHHELD; e1d-checks-32b-prod30 (qwen3-vl:32b, 1.45 boxed frames/attempt): off-pitch false-yes 71.43%, touch false-yes 0.00%, touch recall N/A (raw 0/6), gate 2 WITHHELD; e1d-checks-27b-prod30 (qwen3.8:27b-obliterated-q8, 1.45 boxed frames/attempt): off-pitch false-yes 78.57%, touch false-yes 0.00%, touch recall N/A (raw 0/6), gate 2 WITHHELD; e1e-crop-8b-prod30 (qwen3-vl:8b, 1.45 boxed frames/attempt): off-pitch false-yes 50.00%, touch false-yes 0.00%, touch recall N/A (raw 0/6), gate 2 WITHHELD. Adoption belongs to MJ.

Gate numbers (false-yes count / truth-no cells):

| Run | Off-pitch on-pitch | Off-pitch in-progress | Gate 1 pooled | Touch false-yes | Raw touch yes/positive | Touch recall | Gate 2 |
|---|---:|---:|---:|---:|---:|---|---|
| e1d-checks-dense | 7/7 (100.00%) | 1/7 (14.29%) | 8/14 (57.14%) | 0/9 (0.00%) | 0/6 | N/A | WITHHELD |
| e1d-checks-prod30 | 6/7 (85.71%) | 1/7 (14.29%) | 7/14 (50.00%) | 0/9 (0.00%) | 0/6 | N/A | WITHHELD |
| e1d-checks-32b-dense | 6/7 (85.71%) | 1/7 (14.29%) | 7/14 (50.00%) | 0/9 (0.00%) | 0/6 | N/A | WITHHELD |
| e1d-checks-32b-prod30 | 7/7 (100.00%) | 3/7 (42.86%) | 10/14 (71.43%) | 0/9 (0.00%) | 0/6 | N/A | WITHHELD |
| e1d-checks-27b-dense | 6/7 (85.71%) | 3/7 (42.86%) | 9/14 (64.29%) | 0/9 (0.00%) | 0/6 | N/A | WITHHELD |
| e1d-checks-27b-prod30 | 7/7 (100.00%) | 4/7 (57.14%) | 11/14 (78.57%) | 0/9 (0.00%) | 0/6 | N/A | WITHHELD |
| e1e-crop-8b-dense | 7/7 (100.00%) | 0/7 (0.00%) | 7/14 (50.00%) | 0/9 (0.00%) | 0/6 | N/A | WITHHELD |
| e1e-crop-8b-prod30 | 6/7 (85.71%) | 1/7 (14.29%) | 7/14 (50.00%) | 0/9 (0.00%) | 0/6 | N/A | WITHHELD |
| e1e-cropctx-8b-dense | 7/7 (100.00%) | 0/7 (0.00%) | 7/14 (50.00%) | 0/9 (0.00%) | 0/6 | N/A | WITHHELD |

Per-question comparison:

| Run | Question | Eligible/answered | Accuracy | Majority baseline | Accuracy minus baseline | Modal answer | Modal share | Information | Abstain | False-yes | Recall | False-no | Coverage | High-confidence wrong |
|---|---|---:|---:|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---:|
| e1d-checks-dense | player_on_pitch | 19/19 | 63.16% | 63.16% | 0.00% | yes | 100.00% | False | 0.00% | 100.00% | 100.00% | 0.00% | 100.00% | 7 |
| e1d-checks-dense | play_in_progress | 17/17 | 88.24% | 58.82% | 29.41% | yes | 55.00% | True | 0.00% | 14.29% | 90.00% | 10.00% | 100.00% | 0 |
| e1d-checks-dense | ball_near_player | 15/14 | 57.14% | 53.33% | 3.81% | no | 90.00% | False | 6.67% | 0.00% | 14.29% | 85.71% | 93.33% | 0 |
| e1d-checks-dense | player_touches_ball | 15/15 | 60.00% | 60.00% | 0.00% | no | 100.00% | False | 0.00% | 0.00% | N/A | 100.00% | 100.00% | 6 |
| e1d-checks-dense | player_running | 13/13 | 30.77% | 69.23% | -38.46% | yes | 100.00% | False | 0.00% | 100.00% | 100.00% | 0.00% | 100.00% | 0 |
| e1d-checks-dense | kit_color_seen | 20/18 | 94.44% | 94.44% | 0.00% | red | 100.00% | False | 10.00% | N/A | N/A | N/A | 90.00% | 1 |
| e1d-checks-prod30 | player_on_pitch | 19/19 | 68.42% | 63.16% | 5.26% | yes | 95.00% | False | 0.00% | 85.71% | 100.00% | 0.00% | 100.00% | 6 |
| e1d-checks-prod30 | play_in_progress | 17/17 | 41.18% | 58.82% | -17.65% | no | 85.00% | False | 0.00% | 14.29% | 10.00% | 90.00% | 100.00% | 0 |
| e1d-checks-prod30 | ball_near_player | 15/9 | 77.78% | 53.33% | 24.44% | no | 55.00% | True | 40.00% | 0.00% | 0.00% | 28.57% | 60.00% | 0 |
| e1d-checks-prod30 | player_touches_ball | 15/15 | 60.00% | 60.00% | 0.00% | no | 100.00% | False | 0.00% | 0.00% | N/A | 100.00% | 100.00% | 6 |
| e1d-checks-prod30 | player_running | 13/13 | 46.15% | 69.23% | -23.08% | yes | 90.00% | False | 0.00% | 77.78% | 100.00% | 0.00% | 100.00% | 0 |
| e1d-checks-prod30 | kit_color_seen | 20/18 | 83.33% | 94.44% | -11.11% | red | 80.00% | False | 10.00% | N/A | N/A | N/A | 90.00% | 3 |
| e1d-checks-32b-dense | player_on_pitch | 19/19 | 68.42% | 63.16% | 5.26% | yes | 95.00% | False | 0.00% | 85.71% | 100.00% | 0.00% | 100.00% | 6 |
| e1d-checks-32b-dense | play_in_progress | 17/12 | 91.67% | 58.82% | 32.84% | yes | 65.00% | True | 29.41% | 14.29% | 100.00% | 0.00% | 70.59% | 1 |
| e1d-checks-32b-dense | ball_near_player | 15/15 | 46.67% | 53.33% | -6.67% | no | 95.00% | False | 0.00% | 12.50% | 0.00% | 100.00% | 100.00% | 8 |
| e1d-checks-32b-dense | player_touches_ball | 15/15 | 60.00% | 60.00% | 0.00% | no | 100.00% | False | 0.00% | 0.00% | N/A | 100.00% | 100.00% | 6 |
| e1d-checks-32b-dense | player_running | 13/13 | 53.85% | 69.23% | -15.38% | yes | 80.00% | False | 0.00% | 66.67% | 100.00% | 0.00% | 100.00% | 0 |
| e1d-checks-32b-dense | kit_color_seen | 20/18 | 94.44% | 94.44% | 0.00% | red | 100.00% | False | 10.00% | N/A | N/A | N/A | 90.00% | 1 |
| e1d-checks-32b-prod30 | player_on_pitch | 19/19 | 63.16% | 63.16% | 0.00% | yes | 100.00% | False | 0.00% | 100.00% | 100.00% | 0.00% | 100.00% | 7 |
| e1d-checks-32b-prod30 | play_in_progress | 17/12 | 66.67% | 58.82% | 7.84% | yes | 55.00% | True | 29.41% | 42.86% | 60.00% | 10.00% | 70.59% | 1 |
| e1d-checks-32b-prod30 | ball_near_player | 15/13 | 61.54% | 53.33% | 8.21% | no | 85.00% | True | 13.33% | 0.00% | 0.00% | 71.43% | 86.67% | 1 |
| e1d-checks-32b-prod30 | player_touches_ball | 15/15 | 60.00% | 60.00% | 0.00% | no | 100.00% | False | 0.00% | 0.00% | N/A | 100.00% | 100.00% | 5 |
| e1d-checks-32b-prod30 | player_running | 13/10 | 70.00% | 69.23% | 0.77% | yes | 55.00% | False | 23.08% | 33.33% | 75.00% | 0.00% | 76.92% | 1 |
| e1d-checks-32b-prod30 | kit_color_seen | 20/18 | 100.00% | 94.44% | 5.56% | red | 95.00% | False | 10.00% | N/A | N/A | N/A | 90.00% | 0 |
| e1d-checks-27b-dense | player_on_pitch | 19/19 | 68.42% | 63.16% | 5.26% | yes | 95.00% | False | 0.00% | 85.71% | 100.00% | 0.00% | 100.00% | 6 |
| e1d-checks-27b-dense | play_in_progress | 17/17 | 82.35% | 58.82% | 23.53% | yes | 75.00% | True | 0.00% | 42.86% | 100.00% | 0.00% | 100.00% | 3 |
| e1d-checks-27b-dense | ball_near_player | 15/13 | 38.46% | 53.33% | -14.87% | no | 80.00% | False | 13.33% | 12.50% | 0.00% | 100.00% | 86.67% | 1 |
| e1d-checks-27b-dense | player_touches_ball | 15/15 | 60.00% | 60.00% | 0.00% | no | 95.00% | False | 0.00% | 0.00% | N/A | 100.00% | 100.00% | 2 |
| e1d-checks-27b-dense | player_running | 13/13 | 69.23% | 69.23% | 0.00% | yes | 70.00% | False | 0.00% | 44.44% | 100.00% | 0.00% | 100.00% | 0 |
| e1d-checks-27b-dense | kit_color_seen | 20/18 | 94.44% | 94.44% | 0.00% | red | 100.00% | False | 10.00% | N/A | N/A | N/A | 90.00% | 1 |
| e1d-checks-27b-prod30 | player_on_pitch | 19/19 | 63.16% | 63.16% | 0.00% | yes | 100.00% | False | 0.00% | 100.00% | 100.00% | 0.00% | 100.00% | 7 |
| e1d-checks-27b-prod30 | play_in_progress | 17/15 | 73.33% | 58.82% | 14.51% | yes | 85.00% | True | 11.76% | 57.14% | 100.00% | 0.00% | 88.24% | 4 |
| e1d-checks-27b-prod30 | ball_near_player | 15/15 | 53.33% | 53.33% | 0.00% | no | 100.00% | False | 0.00% | 0.00% | 0.00% | 100.00% | 100.00% | 1 |
| e1d-checks-27b-prod30 | player_touches_ball | 15/7 | 85.71% | 60.00% | 25.71% | unclear | 60.00% | True | 53.33% | 0.00% | N/A | 16.67% | 46.67% | 0 |
| e1d-checks-27b-prod30 | player_running | 13/8 | 62.50% | 69.23% | -6.73% | yes | 55.00% | False | 38.46% | 33.33% | 50.00% | 0.00% | 61.54% | 0 |
| e1d-checks-27b-prod30 | kit_color_seen | 20/18 | 88.89% | 94.44% | -5.56% | red | 95.00% | False | 10.00% | N/A | N/A | N/A | 90.00% | 2 |
| e1e-crop-8b-dense | player_on_pitch | 19/19 | 63.16% | 63.16% | 0.00% | yes | 100.00% | False | 0.00% | 100.00% | 100.00% | 0.00% | 100.00% | 7 |
| e1e-crop-8b-dense | play_in_progress | 17/17 | 52.94% | 58.82% | -5.88% | no | 90.00% | False | 0.00% | 0.00% | 20.00% | 80.00% | 100.00% | 0 |
| e1e-crop-8b-dense | ball_near_player | 15/15 | 53.33% | 53.33% | 0.00% | no | 100.00% | False | 0.00% | 0.00% | 0.00% | 100.00% | 100.00% | 0 |
| e1e-crop-8b-dense | player_touches_ball | 15/15 | 60.00% | 60.00% | 0.00% | no | 100.00% | False | 0.00% | 0.00% | N/A | 100.00% | 100.00% | 6 |
| e1e-crop-8b-dense | player_running | 13/13 | 46.15% | 69.23% | -23.08% | yes | 90.00% | False | 0.00% | 77.78% | 100.00% | 0.00% | 100.00% | 0 |
| e1e-crop-8b-dense | kit_color_seen | 20/18 | 94.44% | 94.44% | 0.00% | red | 100.00% | False | 10.00% | N/A | N/A | N/A | 90.00% | 1 |
| e1e-crop-8b-prod30 | player_on_pitch | 19/19 | 68.42% | 63.16% | 5.26% | yes | 95.00% | False | 0.00% | 85.71% | 100.00% | 0.00% | 100.00% | 6 |
| e1e-crop-8b-prod30 | play_in_progress | 17/17 | 35.29% | 58.82% | -23.53% | no | 95.00% | False | 0.00% | 14.29% | 0.00% | 100.00% | 100.00% | 0 |
| e1e-crop-8b-prod30 | ball_near_player | 15/11 | 63.64% | 53.33% | 10.30% | no | 65.00% | True | 26.67% | 0.00% | 0.00% | 57.14% | 73.33% | 1 |
| e1e-crop-8b-prod30 | player_touches_ball | 15/15 | 60.00% | 60.00% | 0.00% | no | 100.00% | False | 0.00% | 0.00% | N/A | 100.00% | 100.00% | 6 |
| e1e-crop-8b-prod30 | player_running | 13/13 | 53.85% | 69.23% | -15.38% | yes | 85.00% | False | 0.00% | 66.67% | 100.00% | 0.00% | 100.00% | 0 |
| e1e-crop-8b-prod30 | kit_color_seen | 20/18 | 100.00% | 94.44% | 5.56% | red | 95.00% | False | 10.00% | N/A | N/A | N/A | 90.00% | 0 |
| e1e-cropctx-8b-dense | player_on_pitch | 19/19 | 63.16% | 63.16% | 0.00% | yes | 100.00% | False | 0.00% | 100.00% | 100.00% | 0.00% | 100.00% | 7 |
| e1e-cropctx-8b-dense | play_in_progress | 17/17 | 64.71% | 58.82% | 5.88% | no | 80.00% | True | 0.00% | 0.00% | 40.00% | 60.00% | 100.00% | 0 |
| e1e-cropctx-8b-dense | ball_near_player | 15/14 | 57.14% | 53.33% | 3.81% | no | 95.00% | False | 6.67% | 0.00% | 0.00% | 85.71% | 93.33% | 0 |
| e1e-cropctx-8b-dense | player_touches_ball | 15/15 | 60.00% | 60.00% | 0.00% | no | 100.00% | False | 0.00% | 0.00% | N/A | 100.00% | 100.00% | 6 |
| e1e-cropctx-8b-dense | player_running | 13/13 | 38.46% | 69.23% | -30.77% | yes | 95.00% | False | 0.00% | 88.89% | 100.00% | 0.00% | 100.00% | 0 |
| e1e-cropctx-8b-dense | kit_color_seen | 20/18 | 94.44% | 94.44% | 0.00% | red | 100.00% | False | 10.00% | N/A | N/A | N/A | 90.00% | 1 |

Every saved touch answer across the nine runs is no/unclear, but 12 frames spread over a long window leave multi-second gaps while a touch lasts a fraction of a second. The inspected n12 middle crop is clear and contains no nearby ball. Raw 0/6 is not evidence that the model cannot see a touch: these frames rarely contain one, and touch recall is not measurable at this sampling. The on-pitch/sideline failures are unaffected because that distinction is visible in any frame. Follow-up: moment windows — at least 8 frames at at least 4 fps in the 2 s around a human-marked touch time; MJ must mark touch times on the six clips. No new inference in r2.

5 truth cells corrected. Pooled false-yes gate numbers unchanged. The headline changes: gate 2 now requires measurable recall as well as low false-yes, so its former false-yes-only PASS is WITHHELD at this sampling. Macro accuracies and per-question metrics changed as listed; raw touch counts remain visible. The requested information heuristic can flag selective-abstention outputs despite zero affirmative touches; it is not a calibrated measure of visual information.


Shared scored clips: 20. Comparison accuracy/error rates use shared IDs scored in every saved report and current rescoring. Modal distributions, majority baselines, touch counts/recall and temporal sampling use each full run, so abstention or another run's failure cannot remove valid answers or touch positives from those denominators. Full-run reports retain every attempt. Frame facts use all raw attempts. Configured wall caps alone do not imply an incomplete run.

Accuracy = correct / graded answered (unclear excluded). Abstain = unclear / eligible; coverage = graded answered / eligible. Binary eligibility requires yes/no truth. Kit eligibility follows lane A: uncertain kit truth forces abstention even for an asserted colour. False-yes = yes / truth-no cells; false-no = no / truth-yes cells, including abstentions in those truth denominators. Kit has no yes/no rates. Macro accuracy averages available accuracies across six questions; macro false-yes averages available rates across five binary questions; overall abstain is pooled over eligible cells. Gate 1 pools player_on_pitch and play_in_progress over off-pitch clips (14 cells on full set); Gate 2 uses player_touches_ball over off-pitch or idle clips with truth no (9 clips; mixed receive excluded). Modal answer/share uses every valid answer, including unclear and ungraded cells; ties sort lexically. Majority baseline uses all selected graded truth classes (uncertain kit excluded), independent of abstention; information requires modal share <90% and accuracy > baseline +5 percentage points. Gate 1 also splits its two questions. Gate 2 requires false-yes <=10% AND measurable touch recall >=50%. Raw recall = yes / all selected truth-positive clips, counting unclear/failed reads as misses. Touch recall is null when mean spacing >1s or sampling metadata is missing; raw counts remain. Accuracy metrics exclude failed reads; attempted/scored/failed counts remain visible. Thinking rate and wall/clip include all attempts. Reasons are logged only, never scored.

Mixed settings explicitly allowed: {"27b_dense": {"model": "qwen3.8:27b-obliterated-q8"}, "27b_prod30": {"model": "qwen3.8:27b-obliterated-q8"}, "32b_dense": {"model": "qwen3-vl:32b"}, "32b_prod30": {"model": "qwen3-vl:32b"}, "crop8_dense": {"adapter": "qwen3vl_checks_crop"}, "crop8_prod30": {"adapter": "qwen3vl_checks_crop"}, "cropctx8_dense": {"adapter": "qwen3vl_checks_crop"}}; scoring uses supplied truth.

| Run | Model | Boxed frames/attempt | Scored/failed | Wall s/clip (all attempts) | Macro accuracy | Macro false-yes | Abstain | From thinking (all attempts) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| e1d-checks-dense | qwen3-vl:8b | 11.9 | 20/0 | 51.651 | 65.62% | 42.86% | 3.03% | 100.00% |
| e1d-checks-prod30 | qwen3-vl:8b | 1.45 | 20/0 | 10.547 | 62.81% | 35.56% | 8.08% | 100.00% |
| e1d-checks-32b-dense | qwen3-vl:32b | 11.9 | 20/0 | 216.428 | 69.17% | 35.83% | 7.07% | 100.00% |
| e1d-checks-32b-prod30 | qwen3-vl:32b | 1.45 | 20/0 | 39.580 | 70.23% | 35.24% | 12.12% | 100.00% |
| e1d-checks-27b-dense | qwen3.8:27b-obliterated-q8 | 11.9 | 20/0 | 172.788 | 68.82% | 37.10% | 4.04% | 0.00% |
| e1d-checks-27b-prod30 | qwen3.8:27b-obliterated-q8 | 1.45 | 20/0 | 87.783 | 71.15% | 38.10% | 17.17% | 0.00% |
| e1e-crop-8b-dense | qwen3-vl:8b | 11.9 | 20/0 | 53.431 | 61.67% | 35.56% | 2.02% | 100.00% |
| e1e-crop-8b-prod30 | qwen3-vl:8b | 1.45 | 20/0 | 11.068 | 63.53% | 33.33% | 6.06% | 100.00% |
| e1e-cropctx-8b-dense | qwen3-vl:8b | 23.8 | 20/0 | 122.840 | 62.99% | 37.78% | 3.03% | 100.00% |

Thresholds (MJ decides adoption):

| Run | Metric | Threshold | Measured | Result |
|---|---|---:|---:|---|
| e1d-checks-dense | off_pitch_false_yes_rate | <= 10.00% | 57.14% | FAIL |
| e1d-checks-dense | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1d-checks-dense | touch_recall | >= 50.00% | N/A | WITHHELD |
| e1d-checks-dense | macro_accuracy | >= 80.00% | 65.62% | FAIL |
| e1d-checks-dense | abstain_rate | <= 40.00% | 3.03% | PASS |
| e1d-checks-dense | gate2 | touch false-yes <=10% AND measurable touch recall >=50% | N/A | WITHHELD |
| e1d-checks-prod30 | off_pitch_false_yes_rate | <= 10.00% | 50.00% | FAIL |
| e1d-checks-prod30 | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1d-checks-prod30 | touch_recall | >= 50.00% | N/A | WITHHELD |
| e1d-checks-prod30 | macro_accuracy | >= 80.00% | 62.81% | FAIL |
| e1d-checks-prod30 | abstain_rate | <= 40.00% | 8.08% | PASS |
| e1d-checks-prod30 | gate2 | touch false-yes <=10% AND measurable touch recall >=50% | N/A | WITHHELD |
| e1d-checks-32b-dense | off_pitch_false_yes_rate | <= 10.00% | 50.00% | FAIL |
| e1d-checks-32b-dense | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1d-checks-32b-dense | touch_recall | >= 50.00% | N/A | WITHHELD |
| e1d-checks-32b-dense | macro_accuracy | >= 80.00% | 69.17% | FAIL |
| e1d-checks-32b-dense | abstain_rate | <= 40.00% | 7.07% | PASS |
| e1d-checks-32b-dense | gate2 | touch false-yes <=10% AND measurable touch recall >=50% | N/A | WITHHELD |
| e1d-checks-32b-prod30 | off_pitch_false_yes_rate | <= 10.00% | 71.43% | FAIL |
| e1d-checks-32b-prod30 | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1d-checks-32b-prod30 | touch_recall | >= 50.00% | N/A | WITHHELD |
| e1d-checks-32b-prod30 | macro_accuracy | >= 80.00% | 70.23% | FAIL |
| e1d-checks-32b-prod30 | abstain_rate | <= 40.00% | 12.12% | PASS |
| e1d-checks-32b-prod30 | gate2 | touch false-yes <=10% AND measurable touch recall >=50% | N/A | WITHHELD |
| e1d-checks-27b-dense | off_pitch_false_yes_rate | <= 10.00% | 64.29% | FAIL |
| e1d-checks-27b-dense | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1d-checks-27b-dense | touch_recall | >= 50.00% | N/A | WITHHELD |
| e1d-checks-27b-dense | macro_accuracy | >= 80.00% | 68.82% | FAIL |
| e1d-checks-27b-dense | abstain_rate | <= 40.00% | 4.04% | PASS |
| e1d-checks-27b-dense | gate2 | touch false-yes <=10% AND measurable touch recall >=50% | N/A | WITHHELD |
| e1d-checks-27b-prod30 | off_pitch_false_yes_rate | <= 10.00% | 78.57% | FAIL |
| e1d-checks-27b-prod30 | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1d-checks-27b-prod30 | touch_recall | >= 50.00% | N/A | WITHHELD |
| e1d-checks-27b-prod30 | macro_accuracy | >= 80.00% | 71.15% | FAIL |
| e1d-checks-27b-prod30 | abstain_rate | <= 40.00% | 17.17% | PASS |
| e1d-checks-27b-prod30 | gate2 | touch false-yes <=10% AND measurable touch recall >=50% | N/A | WITHHELD |
| e1e-crop-8b-dense | off_pitch_false_yes_rate | <= 10.00% | 50.00% | FAIL |
| e1e-crop-8b-dense | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1e-crop-8b-dense | touch_recall | >= 50.00% | N/A | WITHHELD |
| e1e-crop-8b-dense | macro_accuracy | >= 80.00% | 61.67% | FAIL |
| e1e-crop-8b-dense | abstain_rate | <= 40.00% | 2.02% | PASS |
| e1e-crop-8b-dense | gate2 | touch false-yes <=10% AND measurable touch recall >=50% | N/A | WITHHELD |
| e1e-crop-8b-prod30 | off_pitch_false_yes_rate | <= 10.00% | 50.00% | FAIL |
| e1e-crop-8b-prod30 | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1e-crop-8b-prod30 | touch_recall | >= 50.00% | N/A | WITHHELD |
| e1e-crop-8b-prod30 | macro_accuracy | >= 80.00% | 63.53% | FAIL |
| e1e-crop-8b-prod30 | abstain_rate | <= 40.00% | 6.06% | PASS |
| e1e-crop-8b-prod30 | gate2 | touch false-yes <=10% AND measurable touch recall >=50% | N/A | WITHHELD |
| e1e-cropctx-8b-dense | off_pitch_false_yes_rate | <= 10.00% | 50.00% | FAIL |
| e1e-cropctx-8b-dense | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1e-cropctx-8b-dense | touch_recall | >= 50.00% | N/A | WITHHELD |
| e1e-cropctx-8b-dense | macro_accuracy | >= 80.00% | 62.99% | FAIL |
| e1e-cropctx-8b-dense | abstain_rate | <= 40.00% | 3.03% | PASS |
| e1e-cropctx-8b-dense | gate2 | touch false-yes <=10% AND measurable touch recall >=50% | N/A | WITHHELD |

Truth rules:

- player_on_pitch: off_pitch=no; other classified=yes; unclassified (n24)=ungraded
- play_in_progress: off_pitch=no; on_ball_action/defensive_track_back/positional_only=yes; idle throw-in without running=no; mixed running/throw-in (n04-307417)=ungraded; other idle (n10)=ungraded; mixed receive (n04-243433)=yes
- ball_near_player: misses/missed header=yes (takes precedence over off_pitch); off_pitch=no; on_ball_action=yes; other idle=no; defensive/positional/unclassified=ungraded
- player_touches_ball: off_pitch=no; on_ball_action=yes (including mixed n04-243433); other idle=no; defensive/positional/unclassified=ungraded
- player_running: off_pitch or non-on-ball walk/stand=no; mixed receive/walking n04-243433=ungraded; run/track back/goes or went forward=yes; challenge alone and receive without running=ungraded; other=ungraded
- kit_color_seen: identity_truth.kit_truth: uncertainty takes precedence and counts as abstention; verified override restores colour independently of disputed label; unavailable disputed colour=ungraded

Full truth table — ungraded cells shown as —; uncertain kit cells force abstention:

| Clip | MJ note | player_on_pitch | play_in_progress | ball_near_player | player_touches_ball | player_running | kit_color_seen |
|---|---|---|---|---|---|---|---|
| m04-n02-t3005-474114-478131 | playing right-side center back in a three at the back system. close to the touchline. | yes | yes | — | — | — | red |
| m04-n03-t1406-157170-158922 | either playing left-sided center back or left wing. nice move to win his challenge and passes it along to winger | yes | yes | yes | yes | — | red |
| m04-n03-t1406-385962-387137 | putting on their warmup kit. and walks to sideline | no | no | no | no | no | uncertain / abstain |
| m04-n04-t3006-243433-247994 | playing up top. just walks around and waits until the keeper boots it to halfway line and then receives and does a half turn. | yes | yes | yes | yes | — | red |
| m04-n04-t3006-307417-310307 | a bit of running. ball doesn't come and waits for opposite team to throw in | yes | — | no | no | yes | red |
| m04-n05-t3007-284945-287898 | seems to be playing defense. tracked back. | yes | yes | — | — | yes | red |
| m04-n09-t1409-143096-143834 | on the sideline | no | no | no | no | no | red |
| m04-n09-t1409-297601-298865 | tracked back for defense and then went forward when team recovered. | yes | yes | — | — | yes | red |
| m04-n09-t1409-385922-386603 | stretching on sidelines | no | no | no | no | no | red |
| m04-n10-t711-186553-188161 | just walking around. | yes | — | no | no | no | red |
| m04-n12-t1411-237107-242145 | intercepts a ball but passes to opposite team | yes | yes | yes | yes | — | red |
| m04-n12-t1411-679986-681985 | walking off the field. | no | no | no | no | no | red |
| m04-n15-t3010-164698-170777 | multiple challenges for the ball | yes | yes | yes | yes | — | red |
| m04-n17-t717-253073-260377 | heads the ball off defender for a throw-in. and goes forward when team recovers the ball. | yes | yes | yes | yes | yes | red |
| m04-n17-t717-304624-307834 | walking back on defense as play is on the opposite side. stays wide. | yes | yes | — | — | no | red |
| m04-n17-t717-416826-418915 | receives ball in midfield. playing as false 9 or 10 spot. loses the ball | yes | yes | yes | yes | — | red |
| m04-n21-t3011-390297-390800 | warming up sideline. grabs hamstring | no | no | no | no | no | red |
| m04-n22-t3012-070707-074371 | walking off field in warmup suit. misses header | no | no | yes | no | no | uncertain / abstain |
| m04-n24-t3013-679939-681217 | wrong number. this is number 12 from the shorts | — | — | — | — | — | black |
| m04-n25-t3014-530600-532465 | coming off the pitch. | no | no | no | no | no | red |

All per-clip answers (answer / confidence):

| Clip | Run | Status | player_on_pitch | play_in_progress | ball_near_player | player_touches_ball | player_running | kit_color_seen |
|---|---|---|---|---|---|---|---|---|
| m04-n02-t3005-474114-478131 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n02-t3005-474114-478131 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n02-t3005-474114-478131 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n02-t3005-474114-478131 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n02-t3005-474114-478131 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / medium | yes / high | red / high |
| m04-n02-t3005-474114-478131 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high |
| m04-n02-t3005-474114-478131 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n02-t3005-474114-478131 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n02-t3005-474114-478131 | e1e-cropctx-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n03-t1406-157170-158922 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n03-t1406-157170-158922 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n03-t1406-157170-158922 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n03-t1406-157170-158922 | e1d-checks-32b-prod30 | scored | yes / high | no / medium | no / low | no / low | unclear / medium | red / high |
| m04-n03-t1406-157170-158922 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high |
| m04-n03-t1406-157170-158922 | e1d-checks-27b-prod30 | scored | yes / high | yes / medium | no / high | unclear / medium | no / high | red / high |
| m04-n03-t1406-157170-158922 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n03-t1406-157170-158922 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | no / high | no / high | yes / medium | red / high |
| m04-n03-t1406-157170-158922 | e1e-cropctx-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | yes / medium | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-27b-dense | scored | yes / high | no / medium | unclear / low | no / medium | no / medium | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-27b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high |
| m04-n03-t1406-385962-387137 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n03-t1406-385962-387137 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n03-t1406-385962-387137 | e1e-cropctx-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n04-t3006-243433-247994 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n04-t3006-243433-247994 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | blue / high |
| m04-n04-t3006-243433-247994 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n04-t3006-243433-247994 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n04-t3006-243433-247994 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / medium | yes / high | red / high |
| m04-n04-t3006-243433-247994 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high |
| m04-n04-t3006-243433-247994 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n04-t3006-243433-247994 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n04-t3006-243433-247994 | e1e-cropctx-8b-dense | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1d-checks-prod30 | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1e-cropctx-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n05-t3007-284945-287898 | e1d-checks-dense | scored | yes / high | yes / high | no / medium | no / low | yes / high | red / high |
| m04-n05-t3007-284945-287898 | e1d-checks-prod30 | scored | yes / high | yes / high | no / medium | no / low | yes / high | blue / high |
| m04-n05-t3007-284945-287898 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n05-t3007-284945-287898 | e1d-checks-32b-prod30 | scored | yes / high | yes / high | no / medium | no / high | yes / high | red / high |
| m04-n05-t3007-284945-287898 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high |
| m04-n05-t3007-284945-287898 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | unclear / low | yellow / high |
| m04-n05-t3007-284945-287898 | e1e-crop-8b-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n05-t3007-284945-287898 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n05-t3007-284945-287898 | e1e-cropctx-8b-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n09-t1409-143096-143834 | e1d-checks-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n09-t1409-143096-143834 | e1d-checks-prod30 | scored | no / high | yes / medium | no / high | no / high | no / high | red / high |
| m04-n09-t1409-143096-143834 | e1d-checks-32b-dense | scored | no / high | yes / high | no / high | no / high | no / high | red / high |
| m04-n09-t1409-143096-143834 | e1d-checks-32b-prod30 | scored | yes / high | no / medium | no / low | no / low | no / medium | red / high |
| m04-n09-t1409-143096-143834 | e1d-checks-27b-dense | scored | no / high | yes / high | no / high | no / high | no / high | red / high |
| m04-n09-t1409-143096-143834 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | no / high | no / medium | red / high |
| m04-n09-t1409-143096-143834 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / high | no / high | no / high | red / high |
| m04-n09-t1409-143096-143834 | e1e-crop-8b-prod30 | scored | no / high | yes / medium | no / high | no / high | no / high | red / high |
| m04-n09-t1409-143096-143834 | e1e-cropctx-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | unclear / low | yes / high | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | no / medium | unclear / low | red / high |
| m04-n09-t1409-297601-298865 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n09-t1409-297601-298865 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n09-t1409-297601-298865 | e1e-cropctx-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-dense | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | yes / medium | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-27b-dense | scored | yes / high | no / medium | unclear / low | no / medium | no / medium | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-27b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high |
| m04-n09-t1409-385922-386603 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n09-t1409-385922-386603 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | no / low | no / high | no / medium | red / high |
| m04-n09-t1409-385922-386603 | e1e-cropctx-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n10-t711-186553-188161 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n10-t711-186553-188161 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | blue / high |
| m04-n10-t711-186553-188161 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n10-t711-186553-188161 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / high | no / high | no / medium | red / high |
| m04-n10-t711-186553-188161 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high |
| m04-n10-t711-186553-188161 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | no / medium | red / high |
| m04-n10-t711-186553-188161 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n10-t711-186553-188161 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | no / high | no / high | yes / medium | red / high |
| m04-n10-t711-186553-188161 | e1e-cropctx-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n12-t1411-237107-242145 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n12-t1411-237107-242145 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n12-t1411-237107-242145 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n12-t1411-237107-242145 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n12-t1411-237107-242145 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / medium | yes / high | red / high |
| m04-n12-t1411-237107-242145 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high |
| m04-n12-t1411-237107-242145 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n12-t1411-237107-242145 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n12-t1411-237107-242145 | e1e-cropctx-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-32b-dense | scored | yes / high | no / medium | yes / high | no / medium | no / high | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / high | no / high | no / medium | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-27b-dense | scored | yes / high | no / medium | yes / high | no / medium | no / high | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | no / high | unclear / low | red / high |
| m04-n12-t1411-679986-681985 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / high | no / high | no / high | red / high |
| m04-n12-t1411-679986-681985 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n12-t1411-679986-681985 | e1e-cropctx-8b-dense | scored | yes / high | no / medium | no / low | no / high | no / high | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | no / medium | no / high | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1e-cropctx-8b-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / medium | yes / high | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1e-cropctx-8b-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | unclear / low | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1e-cropctx-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-32b-prod30 | scored | yes / high | yes / high | no / medium | no / high | yes / high | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / medium | yes / high | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | no / medium | yes / high | red / high |
| m04-n17-t717-416826-418915 | e1e-crop-8b-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-416826-418915 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n17-t717-416826-418915 | e1e-cropctx-8b-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | no / medium | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | no / medium | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-32b-prod30 | scored | yes / high | no / medium | no / high | no / high | no / medium | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-27b-dense | scored | yes / high | no / medium | no / high | no / high | no / medium | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-27b-prod30 | scored | yes / high | no / medium | no / high | no / medium | no / high | red / high |
| m04-n21-t3011-390297-390800 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n21-t3011-390297-390800 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | no / low | no / high | no / medium | red / high |
| m04-n21-t3011-390297-390800 | e1e-cropctx-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-dense | scored | yes / high | no / medium | yes / high | no / low | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1e-cropctx-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n24-t3013-679939-681217 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n24-t3013-679939-681217 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | black / high |
| m04-n24-t3013-679939-681217 | e1d-checks-32b-dense | scored | yes / high | no / medium | no / high | no / high | no / medium | red / high |
| m04-n24-t3013-679939-681217 | e1d-checks-32b-prod30 | scored | yes / high | no / medium | no / low | no / high | no / medium | black / high |
| m04-n24-t3013-679939-681217 | e1d-checks-27b-dense | scored | yes / high | no / medium | yes / high | no / medium | no / high | red / high |
| m04-n24-t3013-679939-681217 | e1d-checks-27b-prod30 | scored | yes / high | yes / medium | no / high | unclear / medium | yes / high | red / high |
| m04-n24-t3013-679939-681217 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n24-t3013-679939-681217 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | black / high |
| m04-n24-t3013-679939-681217 | e1e-cropctx-8b-dense | scored | yes / high | no / medium | no / high | no / high | yes / medium | red / high |
| m04-n25-t3014-530600-532465 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n25-t3014-530600-532465 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n25-t3014-530600-532465 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | yes / medium | red / high |
| m04-n25-t3014-530600-532465 | e1d-checks-32b-prod30 | scored | yes / high | yes / high | no / medium | no / high | yes / high | red / high |
| m04-n25-t3014-530600-532465 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high |
| m04-n25-t3014-530600-532465 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | no / medium | yes / medium | red / high |
| m04-n25-t3014-530600-532465 | e1e-crop-8b-dense | scored | yes / high | no / medium | no / high | no / high | yes / medium | red / high |
| m04-n25-t3014-530600-532465 | e1e-crop-8b-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n25-t3014-530600-532465 | e1e-cropctx-8b-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |

First available question reason per scored clip, in contract question order; first five such clips in selected manifest order, verbatim. Missing optional reasons are never invented.

Five reasons — e1d-checks-dense:

- `m04-n02-t3005-474114-478131` / player_on_pitch: “Visible on field in all frames”
- `m04-n03-t1406-157170-158922` / player_on_pitch: “Player visible on field in all frames”
- `m04-n03-t1406-385962-387137` / player_on_pitch: “Player visible on field”
- `m04-n04-t3006-243433-247994` / player_on_pitch: “Player visible on field in all frames”
- `m04-n04-t3006-307417-310307` / player_on_pitch: “Visible on field throughout frames”

Five reasons — e1d-checks-prod30:

- `m04-n02-t3005-474114-478131` / player_on_pitch: “Player visible on field”
- `m04-n03-t1406-157170-158922` / player_on_pitch: “Player is on field within play area”
- `m04-n03-t1406-385962-387137` / player_on_pitch: “Player on green field”
- `m04-n04-t3006-243433-247994` / player_on_pitch: “Player visible on field”
- `m04-n04-t3006-307417-310307` / player_on_pitch: “Player within field boundaries”

Five reasons — e1d-checks-32b-dense:

- `m04-n02-t3005-474114-478131` / player_on_pitch: “Player on field throughout”
- `m04-n03-t1406-157170-158922` / player_on_pitch: “Player on field throughout”
- `m04-n03-t1406-385962-387137` / player_on_pitch: “Player on field throughout”
- `m04-n04-t3006-243433-247994` / player_on_pitch: “Player on field throughout”
- `m04-n04-t3006-307417-310307` / player_on_pitch: “Player on field throughout”

Five reasons — e1d-checks-32b-prod30:

- `m04-n02-t3005-474114-478131` / player_on_pitch: “Player on field”
- `m04-n03-t1406-157170-158922` / player_on_pitch: “on field”
- `m04-n03-t1406-385962-387137` / player_on_pitch: “Player on field”
- `m04-n04-t3006-243433-247994` / player_on_pitch: “Player on field”
- `m04-n04-t3006-307417-310307` / player_on_pitch: “on field”

Five reasons — e1d-checks-27b-dense:

- `m04-n02-t3005-474114-478131` / player_on_pitch: “Visible on the field of play”
- `m04-n03-t1406-157170-158922` / player_on_pitch: “Visible on the field of play”
- `m04-n03-t1406-385962-387137` / player_on_pitch: “Visible on the field of play”
- `m04-n04-t3006-243433-247994` / player_on_pitch: “Visible on the field of play”
- `m04-n04-t3006-307417-310307` / player_on_pitch: “Visible on the field of play”

Five reasons — e1d-checks-27b-prod30:

- `m04-n02-t3005-474114-478131` / player_on_pitch: “Visible on the field of play”
- `m04-n03-t1406-157170-158922` / player_on_pitch: “Visible on the field of play”
- `m04-n03-t1406-385962-387137` / player_on_pitch: “Visible on the field”
- `m04-n04-t3006-243433-247994` / player_on_pitch: “Visible on the field of play”
- `m04-n04-t3006-307417-310307` / player_on_pitch: “Visible on the field of play”

Five reasons — e1e-crop-8b-dense:

- `m04-n02-t3005-474114-478131` / player_on_pitch: “Player visible on field in all frames”
- `m04-n03-t1406-157170-158922` / player_on_pitch: “Player visible on field in all frames”
- `m04-n03-t1406-385962-387137` / player_on_pitch: “Player visible on field”
- `m04-n04-t3006-243433-247994` / player_on_pitch: “Player visible on field in all frames”
- `m04-n04-t3006-307417-310307` / player_on_pitch: “Player visible on field in all frames”

Five reasons — e1e-crop-8b-prod30:

- `m04-n02-t3005-474114-478131` / player_on_pitch: “Player visible on field”
- `m04-n03-t1406-157170-158922` / player_on_pitch: “Player on green field within pitch boundaries”
- `m04-n03-t1406-385962-387137` / player_on_pitch: “Player on green field”
- `m04-n04-t3006-243433-247994` / player_on_pitch: “Player visible on field”
- `m04-n04-t3006-307417-310307` / player_on_pitch: “Player is on green field within play area”

Five reasons — e1e-cropctx-8b-dense:

- `m04-n02-t3005-474114-478131` / player_on_pitch: “Player visible on field in all frames”
- `m04-n03-t1406-157170-158922` / player_on_pitch: “Player visible on field in all frames”
- `m04-n03-t1406-385962-387137` / player_on_pitch: “Player visible on field”
- `m04-n04-t3006-243433-247994` / player_on_pitch: “Player visible on field in all frames”
- `m04-n04-t3006-307417-310307` / player_on_pitch: “Visible on field in all frames”

Thinking-channel diagnostic:


Model/frame facts from run.json and raw attempts:

- 8b_dense: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frames_per_second_of_window": {"mean": 0.7109915728989717, "min": 0.16429353778751377}, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "mean_spacing_s": 2.4899898989899, "model": "qwen3-vl:8b", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- 8b_prod30: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frames_per_second_of_window": {"mean": 0.0701758236166358, "min": 0.033863867253640136}, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "mean_spacing_s": 23.98825000000001, "model": "qwen3-vl:8b", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}
- 32b_dense: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frames_per_second_of_window": {"mean": 0.7109915728989717, "min": 0.16429353778751377}, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "mean_spacing_s": 2.4899898989899, "model": "qwen3-vl:32b", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- 32b_prod30: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frames_per_second_of_window": {"mean": 0.0701758236166358, "min": 0.033863867253640136}, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "mean_spacing_s": 23.98825000000001, "model": "qwen3-vl:32b", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}
- 27b_dense: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frames_per_second_of_window": {"mean": 0.7109915728989717, "min": 0.16429353778751377}, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "mean_spacing_s": 2.4899898989899, "model": "qwen3.8:27b-obliterated-q8", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- 27b_prod30: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frames_per_second_of_window": {"mean": 0.0701758236166358, "min": 0.033863867253640136}, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "mean_spacing_s": 23.98825000000001, "model": "qwen3.8:27b-obliterated-q8", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}
- crop8_dense: {"adapter": "qwen3vl_checks_crop", "anchor_color": "magenta", "attempted_clips": 20, "frames_per_second_of_window": {"mean": 0.7109915728989717, "min": 0.16429353778751377}, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "mean_spacing_s": 2.4899898989899, "model": "qwen3-vl:8b", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- crop8_prod30: {"adapter": "qwen3vl_checks_crop", "anchor_color": "magenta", "attempted_clips": 20, "frames_per_second_of_window": {"mean": 0.0701758236166358, "min": 0.033863867253640136}, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "mean_spacing_s": 23.98825000000001, "model": "qwen3-vl:8b", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}
- cropctx8_dense: {"adapter": "qwen3vl_checks_crop", "anchor_color": "magenta", "attempted_clips": 20, "frames_per_second_of_window": {"mean": 0.7109915728989717, "min": 0.16429353778751377}, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 23.8, "mean_spacing_s": 2.4899898989899, "model": "qwen3-vl:8b", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 476, "shifted_frame_count": 22, "single_frame_attempts": 0}

Provenance:

- Truth SHA-256: `b0701190324ab2527d400b2b176da67291a5efffc11fd314068b343e9f74e8ed`
- Human-note SHA-256: `5944679d0b576bfd8790d9d1206def9485f7618b0c6d53d4c7593c266d51d59f`
- Contract: film-room-checks-v1; truth rules: film-room-checks-truth-v2.

Caveats:

- n=20, one sequential pass per sampling policy; no repeats or causal claim about density. Smoke and diagnostic are separate from the comparison.
- Truth is derived deterministically from MJ's notes via semantic_activity plus the explicit checks rules. This is not independent exhaustive video annotation. Challenges and receives alone do not establish running; mixed running/throw-in does not establish play-in-progress; a missed header establishes ball proximity.
- Gate 2 excludes mixed idle/on-ball n04-243433 because its note explicitly records a receive; it is not truth-negative. The two gates measure individual check assertions, not a production gate's combined decision.
- Lane A's saved reads used red boxes; this lane uses magenta. Most kits remain red, with one verified black override and two uncertain warm-up kits forced to abstain. These data do not isolate annotation colour effects.
- MJ reports tracker misses. Supplied truth box_track stands in for production tracking; identity/input mistakes may affect readings. Labels are supplied identity, not independent jersey evidence.
- Every frame imports lane A's spread sampling and magenta drawing. Targets in tracking gaps snap to a recorded timestamp within 0.5s; larger gaps fail. Temporary frame files are removed after each call.
- Schema validation establishes the contract, not visual correctness or whether Ollama applies format grammar to thinking. The production transport and its existing thinking fallback are unchanged.
- Reason strings are verbatim audit text and never scored. Failed reads remain failed; comparison metrics use only shared scored IDs. Thresholds are withheld for incomplete coverage or no shared scores.
- Wall time includes extraction/drawing and failures, with warm-model effects possible. Thinking rate counts all attempts in full-run reports; comparison rates use shared attempts.
- No adoption call: MJ owns that decision. This bench does not wire checks into the production honesty gate.
- Every saved touch answer across the nine runs is no/unclear, but 12 frames spread over a long window leave multi-second gaps while a touch lasts a fraction of a second. The inspected n12 middle crop is clear and contains no nearby ball. Raw 0/6 is not evidence that the model cannot see a touch: these frames rarely contain one, and touch recall is not measurable at this sampling. The on-pitch/sideline failures are unaffected because that distinction is visible in any frame. Follow-up: moment windows — at least 8 frames at at least 4 fps in the 2 s around a human-marked touch time; MJ must mark touch times on the six clips. No new inference in r2.
- Confidence is uncalibrated and prompt-sensitive: on both pilot clips, touch no/low changed to no/high after the reason instruction changed. Modal share and baseline comparisons expose near-constant priors; low touch false-yes alone is not sensitivity.

Temporal sampling (distinct timestamps; context pairs counted once):

| Run | FPS mean | FPS min | Mean spacing s | Touch recall reason |
|---|---:|---:|---:|---|
| e1d-checks-dense | 0.7109915728989717 | 0.16429353778751377 | 2.4899898989899 | not measurable at this sampling: mean frame spacing exceeds 1.0 s |
| e1d-checks-prod30 | 0.0701758236166358 | 0.033863867253640136 | 23.98825000000001 | not measurable at this sampling: mean frame spacing exceeds 1.0 s |
| e1d-checks-32b-dense | 0.7109915728989717 | 0.16429353778751377 | 2.4899898989899 | not measurable at this sampling: mean frame spacing exceeds 1.0 s |
| e1d-checks-32b-prod30 | 0.0701758236166358 | 0.033863867253640136 | 23.98825000000001 | not measurable at this sampling: mean frame spacing exceeds 1.0 s |
| e1d-checks-27b-dense | 0.7109915728989717 | 0.16429353778751377 | 2.4899898989899 | not measurable at this sampling: mean frame spacing exceeds 1.0 s |
| e1d-checks-27b-prod30 | 0.0701758236166358 | 0.033863867253640136 | 23.98825000000001 | not measurable at this sampling: mean frame spacing exceeds 1.0 s |
| e1e-crop-8b-dense | 0.7109915728989717 | 0.16429353778751377 | 2.4899898989899 | not measurable at this sampling: mean frame spacing exceeds 1.0 s |
| e1e-crop-8b-prod30 | 0.0701758236166358 | 0.033863867253640136 | 23.98825000000001 | not measurable at this sampling: mean frame spacing exceeds 1.0 s |
| e1e-cropctx-8b-dense | 0.7109915728989717 | 0.16429353778751377 | 2.4899898989899 | not measurable at this sampling: mean frame spacing exceeds 1.0 s |

Truth cells changed in r2:

| Clip | Question | Before | After |
|---|---|---|---|
| m04-n03-t1406-157170-158922 | player_running | yes | None |
| m04-n04-t3006-307417-310307 | play_in_progress | no | None |
| m04-n15-t3010-164698-170777 | player_running | yes | None |
| m04-n17-t717-416826-418915 | player_running | yes | None |
| m04-n22-t3012-070707-074371 | ball_near_player | no | yes |

Metric changes from the preceding ledger (including per-question counts):

```json
{
  "8b_dense": {
    "questions": {
      "play_in_progress": {
        "eligible_count": {
          "before": 18,
          "after": 17
        },
        "answered_count": {
          "before": 18,
          "after": 17
        },
        "correct_count": {
          "before": 16,
          "after": 15
        },
        "truth_no_count": {
          "before": 8,
          "after": 7
        },
        "accuracy": {
          "before": 0.8888888888888888,
          "after": 0.8823529411764706
        },
        "false_yes_rate": {
          "before": 0.125,
          "after": 0.14285714285714285
        }
      },
      "ball_near_player": {
        "correct_count": {
          "before": 7,
          "after": 8
        },
        "truth_no_count": {
          "before": 9,
          "after": 8
        },
        "truth_yes_count": {
          "before": 6,
          "after": 7
        },
        "false_yes_count": {
          "before": 1,
          "after": 0
        },
        "accuracy": {
          "before": 0.5,
          "after": 0.5714285714285714
        },
        "false_yes_rate": {
          "before": 0.1111111111111111,
          "after": 0.0
        },
        "false_no_rate": {
          "before": 1.0,
          "after": 0.8571428571428571
        },
        "confident_wrong_count": {
          "before": 1,
          "after": 0
        }
      },
      "player_running": {
        "eligible_count": {
          "before": 16,
          "after": 13
        },
        "answered_count": {
          "before": 16,
          "after": 13
        },
        "correct_count": {
          "before": 7,
          "after": 4
        },
        "truth_yes_count": {
          "before": 7,
          "after": 4
        },
        "accuracy": {
          "before": 0.4375,
          "after": 0.3076923076923077
        }
      }
    },
    "macro_accuracy": {
      "before": 0.6670687134502923,
      "after": 0.6562495353517025
    },
    "macro_false_yes_rate": {
      "before": 0.44722222222222224,
      "after": 0.42857142857142855
    },
    "abstain_rate": {
      "before": 0.02912621359223301,
      "after": 0.030303030303030304
    }
  },
  "8b_prod30": {
    "questions": {
      "play_in_progress": {
        "eligible_count": {
          "before": 18,
          "after": 17
        },
        "answered_count": {
          "before": 18,
          "after": 17
        },
        "truth_no_count": {
          "before": 8,
          "after": 7
        },
        "false_yes_count": {
          "before": 2,
          "after": 1
        },
        "accuracy": {
          "before": 0.3888888888888889,
          "after": 0.4117647058823529
        },
        "false_yes_rate": {
          "before": 0.25,
          "after": 0.14285714285714285
        }
      },
      "ball_near_player": {
        "correct_count": {
          "before": 8,
          "after": 7
        },
        "truth_no_count": {
          "before": 9,
          "after": 8
        },
        "truth_yes_count": {
          "before": 6,
          "after": 7
        },
        "false_no_count": {
          "before": 1,
          "after": 2
        },
        "accuracy": {
          "before": 0.8888888888888888,
          "after": 0.7777777777777778
        },
        "false_no_rate": {
          "before": 0.16666666666666666,
          "after": 0.2857142857142857
        }
      },
      "player_running": {
        "eligible_count": {
          "before": 16,
          "after": 13
        },
        "answered_count": {
          "before": 16,
          "after": 13
        },
        "correct_count": {
          "before": 9,
          "after": 6
        },
        "truth_yes_count": {
          "before": 7,
          "after": 4
        },
        "accuracy": {
          "before": 0.5625,
          "after": 0.46153846153846156
        }
      }
    },
    "macro_accuracy": {
      "before": 0.6596369395711501,
      "after": 0.628104134141286
    },
    "macro_false_yes_rate": {
      "before": 0.376984126984127,
      "after": 0.3555555555555555
    },
    "abstain_rate": {
      "before": 0.07766990291262135,
      "after": 0.08080808080808081
    }
  },
  "32b_dense": {
    "questions": {
      "play_in_progress": {
        "eligible_count": {
          "before": 18,
          "after": 17
        },
        "answered_count": {
          "before": 13,
          "after": 12
        },
        "truth_no_count": {
          "before": 8,
          "after": 7
        },
        "false_yes_count": {
          "before": 2,
          "after": 1
        },
        "accuracy": {
          "before": 0.8461538461538461,
          "after": 0.9166666666666666
        },
        "abstain_rate": {
          "before": 0.2777777777777778,
          "after": 0.29411764705882354
        },
        "coverage": {
          "before": 0.7222222222222222,
          "after": 0.7058823529411765
        },
        "false_yes_rate": {
          "before": 0.25,
          "after": 0.14285714285714285
        }
      },
      "ball_near_player": {
        "correct_count": {
          "before": 8,
          "after": 7
        },
        "truth_no_count": {
          "before": 9,
          "after": 8
        },
        "truth_yes_count": {
          "before": 6,
          "after": 7
        },
        "false_no_count": {
          "before": 6,
          "after": 7
        },
        "accuracy": {
          "before": 0.5333333333333333,
          "after": 0.4666666666666667
        },
        "false_yes_rate": {
          "before": 0.1111111111111111,
          "after": 0.125
        },
        "confident_wrong_count": {
          "before": 7,
          "after": 8
        }
      },
      "player_running": {
        "eligible_count": {
          "before": 16,
          "after": 13
        },
        "answered_count": {
          "before": 16,
          "after": 13
        },
        "correct_count": {
          "before": 10,
          "after": 7
        },
        "truth_yes_count": {
          "before": 7,
          "after": 4
        },
        "accuracy": {
          "before": 0.625,
          "after": 0.5384615384615384
        }
      }
    },
    "macro_accuracy": {
      "before": 0.7055236917079023,
      "after": 0.691741640425851
    },
    "macro_false_yes_rate": {
      "before": 0.376984126984127,
      "after": 0.3583333333333333
    },
    "abstain_rate": {
      "before": 0.06796116504854369,
      "after": 0.0707070707070707
    }
  },
  "32b_prod30": {
    "questions": {
      "play_in_progress": {
        "eligible_count": {
          "before": 18,
          "after": 17
        },
        "answered_count": {
          "before": 13,
          "after": 12
        },
        "truth_no_count": {
          "before": 8,
          "after": 7
        },
        "false_yes_count": {
          "before": 4,
          "after": 3
        },
        "accuracy": {
          "before": 0.6153846153846154,
          "after": 0.6666666666666666
        },
        "abstain_rate": {
          "before": 0.2777777777777778,
          "after": 0.29411764705882354
        },
        "coverage": {
          "before": 0.7222222222222222,
          "after": 0.7058823529411765
        },
        "false_yes_rate": {
          "before": 0.5,
          "after": 0.42857142857142855
        }
      },
      "ball_near_player": {
        "correct_count": {
          "before": 9,
          "after": 8
        },
        "truth_no_count": {
          "before": 9,
          "after": 8
        },
        "truth_yes_count": {
          "before": 6,
          "after": 7
        },
        "false_no_count": {
          "before": 4,
          "after": 5
        },
        "accuracy": {
          "before": 0.6923076923076923,
          "after": 0.6153846153846154
        },
        "false_no_rate": {
          "before": 0.6666666666666666,
          "after": 0.7142857142857143
        }
      },
      "player_running": {
        "eligible_count": {
          "before": 16,
          "after": 13
        },
        "answered_count": {
          "before": 12,
          "after": 10
        },
        "correct_count": {
          "before": 9,
          "after": 7
        },
        "abstain_count": {
          "before": 4,
          "after": 3
        },
        "truth_yes_count": {
          "before": 7,
          "after": 4
        },
        "accuracy": {
          "before": 0.75,
          "after": 0.7
        },
        "abstain_rate": {
          "before": 0.25,
          "after": 0.23076923076923078
        },
        "coverage": {
          "before": 0.75,
          "after": 0.7692307692307693
        }
      }
    },
    "macro_accuracy": {
      "before": 0.7148785425101215,
      "after": 0.7022717049032838
    },
    "macro_false_yes_rate": {
      "before": 0.36666666666666664,
      "after": 0.35238095238095235
    },
    "abstain_rate": {
      "before": 0.1262135922330097,
      "after": 0.12121212121212122
    }
  },
  "27b_dense": {
    "questions": {
      "play_in_progress": {
        "eligible_count": {
          "before": 18,
          "after": 17
        },
        "answered_count": {
          "before": 18,
          "after": 17
        },
        "truth_no_count": {
          "before": 8,
          "after": 7
        },
        "false_yes_count": {
          "before": 4,
          "after": 3
        },
        "accuracy": {
          "before": 0.7777777777777778,
          "after": 0.8235294117647058
        },
        "false_yes_rate": {
          "before": 0.5,
          "after": 0.42857142857142855
        },
        "confident_wrong_count": {
          "before": 4,
          "after": 3
        }
      },
      "ball_near_player": {
        "correct_count": {
          "before": 6,
          "after": 5
        },
        "truth_no_count": {
          "before": 9,
          "after": 8
        },
        "truth_yes_count": {
          "before": 6,
          "after": 7
        },
        "false_no_count": {
          "before": 6,
          "after": 7
        },
        "accuracy": {
          "before": 0.46153846153846156,
          "after": 0.38461538461538464
        },
        "false_yes_rate": {
          "before": 0.1111111111111111,
          "after": 0.125
        }
      },
      "player_running": {
        "eligible_count": {
          "before": 16,
          "after": 13
        },
        "answered_count": {
          "before": 16,
          "after": 13
        },
        "correct_count": {
          "before": 12,
          "after": 9
        },
        "truth_yes_count": {
          "before": 7,
          "after": 4
        },
        "accuracy": {
          "before": 0.75,
          "after": 0.6923076923076923
        }
      }
    },
    "macro_accuracy": {
      "before": 0.7029952016794122,
      "after": 0.6881845765746695
    },
    "macro_false_yes_rate": {
      "before": 0.38253968253968257,
      "after": 0.371031746031746
    },
    "abstain_rate": {
      "before": 0.038834951456310676,
      "after": 0.04040404040404041
    }
  },
  "27b_prod30": {
    "questions": {
      "play_in_progress": {
        "eligible_count": {
          "before": 18,
          "after": 17
        },
        "answered_count": {
          "before": 16,
          "after": 15
        },
        "truth_no_count": {
          "before": 8,
          "after": 7
        },
        "false_yes_count": {
          "before": 5,
          "after": 4
        },
        "accuracy": {
          "before": 0.6875,
          "after": 0.7333333333333333
        },
        "abstain_rate": {
          "before": 0.1111111111111111,
          "after": 0.11764705882352941
        },
        "coverage": {
          "before": 0.8888888888888888,
          "after": 0.8823529411764706
        },
        "false_yes_rate": {
          "before": 0.625,
          "after": 0.5714285714285714
        },
        "confident_wrong_count": {
          "before": 5,
          "after": 4
        }
      },
      "ball_near_player": {
        "correct_count": {
          "before": 9,
          "after": 8
        },
        "truth_no_count": {
          "before": 9,
          "after": 8
        },
        "truth_yes_count": {
          "before": 6,
          "after": 7
        },
        "false_no_count": {
          "before": 6,
          "after": 7
        },
        "accuracy": {
          "before": 0.6,
          "after": 0.5333333333333333
        }
      },
      "player_running": {
        "eligible_count": {
          "before": 16,
          "after": 13
        },
        "answered_count": {
          "before": 11,
          "after": 8
        },
        "correct_count": {
          "before": 7,
          "after": 5
        },
        "truth_yes_count": {
          "before": 7,
          "after": 4
        },
        "false_no_count": {
          "before": 1,
          "after": 0
        },
        "accuracy": {
          "before": 0.6363636363636364,
          "after": 0.625
        },
        "abstain_rate": {
          "before": 0.3125,
          "after": 0.38461538461538464
        },
        "coverage": {
          "before": 0.6875,
          "after": 0.6153846153846154
        },
        "false_no_rate": {
          "before": 0.14285714285714285,
          "after": 0.0
        },
        "confident_wrong_count": {
          "before": 1,
          "after": 0
        }
      }
    },
    "macro_accuracy": {
      "before": 0.7169123882939671,
      "after": 0.7115462266778056
    },
    "macro_false_yes_rate": {
      "before": 0.39166666666666666,
      "after": 0.38095238095238093
    },
    "abstain_rate": {
      "before": 0.1650485436893204,
      "after": 0.1717171717171717
    }
  },
  "crop8_dense": {
    "questions": {
      "play_in_progress": {
        "eligible_count": {
          "before": 18,
          "after": 17
        },
        "answered_count": {
          "before": 18,
          "after": 17
        },
        "correct_count": {
          "before": 10,
          "after": 9
        },
        "truth_no_count": {
          "before": 8,
          "after": 7
        },
        "accuracy": {
          "before": 0.5555555555555556,
          "after": 0.5294117647058824
        }
      },
      "ball_near_player": {
        "correct_count": {
          "before": 9,
          "after": 8
        },
        "truth_no_count": {
          "before": 9,
          "after": 8
        },
        "truth_yes_count": {
          "before": 6,
          "after": 7
        },
        "false_no_count": {
          "before": 6,
          "after": 7
        },
        "accuracy": {
          "before": 0.6,
          "after": 0.5333333333333333
        }
      },
      "player_running": {
        "eligible_count": {
          "before": 16,
          "after": 13
        },
        "answered_count": {
          "before": 16,
          "after": 13
        },
        "correct_count": {
          "before": 9,
          "after": 6
        },
        "truth_yes_count": {
          "before": 7,
          "after": 4
        },
        "accuracy": {
          "before": 0.5625,
          "after": 0.46153846153846156
        }
      }
    },
    "macro_accuracy": {
      "before": 0.6490131578947369,
      "after": 0.6167178252317571
    },
    "abstain_rate": {
      "before": 0.019417475728155338,
      "after": 0.020202020202020204
    }
  },
  "crop8_prod30": {
    "questions": {
      "play_in_progress": {
        "eligible_count": {
          "before": 18,
          "after": 17
        },
        "answered_count": {
          "before": 18,
          "after": 17
        },
        "correct_count": {
          "before": 7,
          "after": 6
        },
        "truth_no_count": {
          "before": 8,
          "after": 7
        },
        "accuracy": {
          "before": 0.3888888888888889,
          "after": 0.35294117647058826
        },
        "false_yes_rate": {
          "before": 0.125,
          "after": 0.14285714285714285
        }
      },
      "ball_near_player": {
        "correct_count": {
          "before": 8,
          "after": 7
        },
        "truth_no_count": {
          "before": 9,
          "after": 8
        },
        "truth_yes_count": {
          "before": 6,
          "after": 7
        },
        "false_no_count": {
          "before": 3,
          "after": 4
        },
        "accuracy": {
          "before": 0.7272727272727273,
          "after": 0.6363636363636364
        },
        "false_no_rate": {
          "before": 0.5,
          "after": 0.5714285714285714
        }
      },
      "player_running": {
        "eligible_count": {
          "before": 16,
          "after": 13
        },
        "answered_count": {
          "before": 16,
          "after": 13
        },
        "correct_count": {
          "before": 10,
          "after": 7
        },
        "truth_yes_count": {
          "before": 7,
          "after": 4
        },
        "accuracy": {
          "before": 0.625,
          "after": 0.5384615384615384
        }
      }
    },
    "macro_accuracy": {
      "before": 0.6708953570795676,
      "after": 0.6353294796019254
    },
    "macro_false_yes_rate": {
      "before": 0.32976190476190476,
      "after": 0.3333333333333333
    },
    "abstain_rate": {
      "before": 0.05825242718446602,
      "after": 0.06060606060606061
    }
  },
  "cropctx8_dense": {
    "questions": {
      "play_in_progress": {
        "eligible_count": {
          "before": 18,
          "after": 17
        },
        "answered_count": {
          "before": 18,
          "after": 17
        },
        "correct_count": {
          "before": 12,
          "after": 11
        },
        "truth_no_count": {
          "before": 8,
          "after": 7
        },
        "accuracy": {
          "before": 0.6666666666666666,
          "after": 0.6470588235294118
        }
      },
      "ball_near_player": {
        "correct_count": {
          "before": 9,
          "after": 8
        },
        "truth_no_count": {
          "before": 9,
          "after": 8
        },
        "truth_yes_count": {
          "before": 6,
          "after": 7
        },
        "false_no_count": {
          "before": 5,
          "after": 6
        },
        "accuracy": {
          "before": 0.6428571428571429,
          "after": 0.5714285714285714
        },
        "false_no_rate": {
          "before": 0.8333333333333334,
          "after": 0.8571428571428571
        }
      },
      "player_running": {
        "eligible_count": {
          "before": 16,
          "after": 13
        },
        "answered_count": {
          "before": 16,
          "after": 13
        },
        "correct_count": {
          "before": 8,
          "after": 5
        },
        "truth_yes_count": {
          "before": 7,
          "after": 4
        },
        "accuracy": {
          "before": 0.5,
          "after": 0.38461538461538464
        }
      }
    },
    "macro_accuracy": {
      "before": 0.6642578668894458,
      "after": 0.6298543618977055
    },
    "abstain_rate": {
      "before": 0.02912621359223301,
      "after": 0.030303030303030304
    }
  }
}
```

Crop geometry (decoded lane-B frames, resized to 768 square):

- crop8_dense: side 384–689 px; scale 1.115–2.000; 238 instants / 238 images.
- crop8_prod30: side 384–689 px; scale 1.115–2.000; 29 instants / 29 images.
- cropctx8_dense: side 384–689 px; scale 1.115–2.000; 238 instants / 476 images.

32B crop run remained skipped under the original scheduling rule. Its raw 0/6 trigger is confounded by temporal sampling; r2 makes no model-capability inference from it.

Three inspected example crop PNGs (external, not committed):

- /Users/mjjones/Projects/loanarmy-bench-reports/e1e-crop-examples/m04-n12-t1411-237107-242145-sample-00.png — SHA-256 f124e405b5f90d6fe7f68cdf4bc799a0370f6324ffcd7d97685232c1be5fc8a7
- /Users/mjjones/Projects/loanarmy-bench-reports/e1e-crop-examples/m04-n12-t1411-237107-242145-sample-05.png — SHA-256 56e99a5e7fe703016f6bc5768a3eeb0194b8b0a9d5f933bc113f8818312aa13b
- /Users/mjjones/Projects/loanarmy-bench-reports/e1e-crop-examples/m04-n12-t1411-237107-242145-sample-11.png — SHA-256 6b0dbfc380de794aa5538bd3a548d23df1e96a3dd3b7699a6b08703b0fcfffa2

Execution/gates:

```json
{
  "round": "r2; scorer/ledger only; no new inference",
  "base_commit": "b96e6b2",
  "historical_execution": {
    "timeout_s": 900,
    "num_ctx": 65536,
    "crop_coordinate_space": "Same decoded frame as lane B (1280x720 in frozen set); truth box scaled before crop calculation",
    "geometry": "ceil(max(3*height,4*width,384)), capped to shorter frame dimension; square translated inside frame; resize 768x768; annotate after resizing",
    "context": "Crop followed by 512-wide aspect-preserving wide frame at same timestamp, both marked magenta; unique timestamps unchanged in prompt",
    "prompt": "Lane B unchanged plus one crop-description sentence; version suffix -crop",
    "32b_rule": "Only if at least 2 of 6 true-touch clips answered yes in any completed 8B run",
    "status": "Smoke, requested runs, conditional 32B decision, comparison and validation complete; prepared for one local commit",
    "constraints": "No scorer, comparison, contract, truth or question wording changes. No push. One commit.",
    "smoke": {
      "wall_s": 38.809,
      "validated": true,
      "checks": {
        "ball_near_player": {
          "answer": "no",
          "confidence": "low",
          "reason": "Ball not seen near player"
        },
        "kit_color_seen": {
          "answer": "red",
          "confidence": "high",
          "reason": "Red jersey clearly seen"
        },
        "play_in_progress": {
          "answer": "no",
          "confidence": "medium",
          "reason": "No ball movement observed"
        },
        "player_on_pitch": {
          "answer": "yes",
          "confidence": "high",
          "reason": "Player visible on field in all frames"
        },
        "player_running": {
          "answer": "yes",
          "confidence": "medium",
          "reason": "Player moving in some frames"
        },
        "player_touches_ball": {
          "answer": "no",
          "confidence": "high",
          "reason": "No contact with ball visible"
        }
      },
      "images": 12,
      "from_thinking": true
    },
    "per_run_wall_cap_s": 5400,
    "wall_cap_choice": "Carry forward 90-minute cap from preceding lane; external watchdog only, no early per-clip stop.",
    "sequential_execution": {
      "request_timeout_s": 900,
      "per_run_wall_cap_s": 5400,
      "runs": {
        "e1e-crop-8b-smoke": {
          "argv": [
            "/Users/mjjones/Projects/loanarmy/.loan/bin/python",
            "-u",
            "/Users/mjjones/Projects/loanarmy/.worktrees/lane-b/spike/video-analysis/bench/run_bench.py",
            "--adapter",
            "qwen3vl_checks_crop",
            "--timeout",
            "900",
            "--manifest",
            "/Users/mjjones/Projects/loanarmy-bench-frozen/manifest.json",
            "--report-root",
            "/Users/mjjones/Projects/loanarmy-bench-reports",
            "--model",
            "qwen3-vl:8b",
            "--clips",
            "m04-n12-t1411-237107-242145",
            "--sample-interval",
            "0.5",
            "--sample-limit",
            "12",
            "--run-id",
            "e1e-crop-8b-smoke"
          ],
          "started_at": "2026-09-09T15:00:44.682866+00:00",
          "pid": 62381,
          "wall_cap_s": 5400,
          "cap_exceeded": false,
          "exit_code": 0,
          "wall_s": 38.964,
          "completed_at": "2026-09-09T15:01:23.646852+00:00"
        },
        "e1e-crop-8b-dense": {
          "argv": [
            "/Users/mjjones/Projects/loanarmy/.loan/bin/python",
            "-u",
            "/Users/mjjones/Projects/loanarmy/.worktrees/lane-b/spike/video-analysis/bench/run_bench.py",
            "--adapter",
            "qwen3vl_checks_crop",
            "--timeout",
            "900",
            "--manifest",
            "/Users/mjjones/Projects/loanarmy-bench-frozen/manifest.json",
            "--report-root",
            "/Users/mjjones/Projects/loanarmy-bench-reports",
            "--model",
            "qwen3-vl:8b",
            "--clips",
            "all",
            "--sample-interval",
            "0.5",
            "--sample-limit",
            "12",
            "--run-id",
            "e1e-crop-8b-dense"
          ],
          "started_at": "2026-09-09T15:01:57.792816+00:00",
          "pid": 62718,
          "wall_cap_s": 5400,
          "cap_exceeded": false,
          "exit_code": 0,
          "wall_s": 1068.807,
          "completed_at": "2026-09-09T15:19:46.573435+00:00"
        },
        "e1e-crop-8b-prod30": {
          "argv": [
            "/Users/mjjones/Projects/loanarmy/.loan/bin/python",
            "-u",
            "/Users/mjjones/Projects/loanarmy/.worktrees/lane-b/spike/video-analysis/bench/run_bench.py",
            "--adapter",
            "qwen3vl_checks_crop",
            "--timeout",
            "900",
            "--manifest",
            "/Users/mjjones/Projects/loanarmy-bench-frozen/manifest.json",
            "--report-root",
            "/Users/mjjones/Projects/loanarmy-bench-reports",
            "--model",
            "qwen3-vl:8b",
            "--clips",
            "all",
            "--sample-interval",
            "30",
            "--sample-limit",
            "3",
            "--run-id",
            "e1e-crop-8b-prod30"
          ],
          "started_at": "2026-09-09T15:19:46.634641+00:00",
          "pid": 67668,
          "wall_cap_s": 5400,
          "cap_exceeded": false,
          "exit_code": 0,
          "wall_s": 221.621,
          "completed_at": "2026-09-09T15:23:28.254386+00:00"
        },
        "e1e-cropctx-8b-dense": {
          "argv": [
            "/Users/mjjones/Projects/loanarmy/.loan/bin/python",
            "-u",
            "/Users/mjjones/Projects/loanarmy/.worktrees/lane-b/spike/video-analysis/bench/run_bench.py",
            "--adapter",
            "qwen3vl_checks_crop",
            "--timeout",
            "900",
            "--manifest",
            "/Users/mjjones/Projects/loanarmy-bench-frozen/manifest.json",
            "--report-root",
            "/Users/mjjones/Projects/loanarmy-bench-reports",
            "--model",
            "qwen3-vl:8b",
            "--clips",
            "all",
            "--sample-interval",
            "0.5",
            "--sample-limit",
            "12",
            "--run-id",
            "e1e-cropctx-8b-dense",
            "--crop-context"
          ],
          "started_at": "2026-09-09T15:23:28.328967+00:00",
          "pid": 68744,
          "wall_cap_s": 5400,
          "cap_exceeded": false,
          "exit_code": 0,
          "wall_s": 2457.213,
          "completed_at": "2026-09-09T16:04:25.551457+00:00"
        }
      },
      "guard_checks": [
        {
          "before": "e1e-crop-8b-smoke",
          "matched_pids": [],
          "foreign_pids": [],
          "at": "2026-09-09T15:00:44.681784+00:00"
        },
        {
          "before": "e1e-crop-8b-dense",
          "matched_pids": [],
          "foreign_pids": [],
          "at": "2026-09-09T15:01:57.791608+00:00"
        },
        {
          "before": "e1e-crop-8b-prod30",
          "matched_pids": [],
          "foreign_pids": [],
          "at": "2026-09-09T15:19:46.631581+00:00"
        },
        {
          "before": "e1e-cropctx-8b-dense",
          "matched_pids": [],
          "foreign_pids": [],
          "at": "2026-09-09T15:23:28.325308+00:00"
        }
      ],
      "state": "all_runs_finished",
      "decision_32b": {
        "recalls": {
          "e1e-crop-8b-dense": {
            "hits": [],
            "count": 0,
            "denominator": 6
          },
          "e1e-crop-8b-prod30": {
            "hits": [],
            "count": 0,
            "denominator": 6
          },
          "e1e-cropctx-8b-dense": {
            "hits": [],
            "count": 0,
            "denominator": 6
          }
        },
        "run": false,
        "rule": "At least 2/6 yes on true-touch clips in any 8B run"
      }
    },
    "gates": {
      "pytest": "317 passed in 1.37s; BENCH_REQUIRE_CV2=1 /Users/mjjones/Projects/loanarmy/.loan/bin/python -m pytest spike/video-analysis/bench -q",
      "ruff_check": "PASS; ruff check spike/video-analysis/bench",
      "ruff_format": "PASS, 31 files; ruff format --check spike/video-analysis/bench",
      "diff_check": "PASS; git diff --check"
    },
    "not_done": "Known truth correction/r2 pending. No adoption decision, production integration or push. Channel diagnostic was not requested for crop lane.",
    "unchanged_proof": {
      "protected_source_sha256": {
        "checks_contract.py": "579d1ca7d6f01a95c33c36bd072ee7b56016eab752b5a8cc5cb8ce2c22b048d8",
        "checks_truth.py": "d847e4934d1774914e4df44b0797521c4c9695fff281d58a6afdabf0f6f204e7",
        "checks_score.py": "29f5d71602b1fa0b19881afe624b2a32606169691ab5bbbdca8259a1a4ad2a7f",
        "compare_checks.py": "b012370b8d13528f9ac4d2ee5527c3aecdcf8f951e96b37a76edbfd3f90c49bc",
        "adapters/qwen3vl_checks.py": "92f070b614adf821628c228685deba4ac99a1a63cc21c0f02015253b6d3ec394",
        "semantic_activity.py": "5a114717535212ed76bad545562b40579290b67445d1fc31309ed9dfd95ec8ae"
      },
      "previous_six_run_fingerprints": "exact match from current runner",
      "truth_provenance": {
        "truth_set_sha256_after_notes": "b0701190324ab2527d400b2b176da67291a5efffc11fd314068b343e9f74e8ed",
        "human_notes_sha256": "5944679d0b576bfd8790d9d1206def9485f7618b0c6d53d4c7593c266d51d59f"
      }
    }
  },
  "historical_execution_note": "Archived pre-r2 execution, validation and interpretation. R2 metrics, truth and temporal caveats supersede historical metric conclusions and unchanged-scorer statements.",
  "prompt_history": {
    "verbatim_diff": "- Return one JSON object matching the supplied schema. Each question has answer and confidence (low, medium, high), and optionally one short reason (at most 80 characters). Keep reasons very brief. No other text.\n+ Return one JSON object matching the supplied schema. Each question has answer and confidence (low, medium, high), and one short reason (at most 80 characters). Include a reason for each answer, in at most five words. No other text.",
    "PROMPT_VERSION_before": null,
    "PROMPT_VERSION_after": "film-room-checks-prompt-v1-reasons",
    "version_provenance": "Pilot PROMPT_VERSION is not persisted in the saved run metadata (UNCONFIRMED); do not reconstruct it. Final saved run.json records film-room-checks-prompt-v1-reasons; committed adapter bcb1699a contains the final wording. The pilot wording is recorded verbatim from the r2 review brief. No prompt edited in r2.",
    "confidence_shift": [
      {
        "clip_id": "m04-n12-t1411-237107-242145",
        "pilot_run": "e1d-checks-smoke",
        "pilot": {
          "answer": "no",
          "confidence": "low",
          "reason": null
        },
        "final_run": "e1d-checks-dense",
        "final": {
          "answer": "no",
          "confidence": "high",
          "reason": "No ball contact shown"
        },
        "pilot_prompt_version": null,
        "final_prompt_version": "film-room-checks-prompt-v1-reasons",
        "final_version_source": "run.json (not the raw claim)"
      },
      {
        "clip_id": "m04-n02-t3005-474114-478131",
        "pilot_run": "e1d-checks-dense-prompt-pilot",
        "pilot": {
          "answer": "no",
          "confidence": "low",
          "reason": null
        },
        "final_run": "e1d-checks-dense",
        "final": {
          "answer": "no",
          "confidence": "high",
          "reason": "No visible contact with ball"
        },
        "pilot_prompt_version": null,
        "final_prompt_version": "film-room-checks-prompt-v1-reasons",
        "final_version_source": "run.json (not the raw claim)"
      }
    ],
    "caveat": "Confidence is uncalibrated and prompt-sensitive; both pilot clips changed touch no/low to no/high."
  },
  "notes_check": {
    "path": "/Users/mjjones/codex-runs/lane-a-notes.md",
    "source_file_sha256": "0fb137cf89ebb46352d48b3283eed62464aad3d95b3f2d8ff7e9b99e4ede022a",
    "source_human_notes_sha256": "5944679d0b576bfd8790d9d1206def9485f7618b0c6d53d4c7593c266d51d59f",
    "applied_human_notes_sha256": "5944679d0b576bfd8790d9d1206def9485f7618b0c6d53d4c7593c266d51d59f",
    "reapplied": false,
    "changed_clip_ids": [],
    "lane_a_regenerated": false,
    "reason": "Normalized ID-to-note mapping matches applied truth exactly; lane-A activity/identity rules unchanged."
  },
  "artifacts": {
    "experiment": "E1e lane C \u2014 player-centred crops with unchanged six checks",
    "base_commit": "113624e6",
    "thinking_channel_diagnostic": {},
    "crop_geometry": {
      "crop8_dense": {
        "crop_side_px_min": 384,
        "crop_side_px_max": 689,
        "crop_scale_min": 1.1146589259796806,
        "crop_scale_max": 2.0,
        "crop_output_size": [
          768,
          768
        ],
        "context_width": null,
        "per_clip_counts": [
          {
            "clip_id": "m04-n02-t3005-474114-478131",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n03-t1406-157170-158922",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n03-t1406-385962-387137",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n04-t3006-243433-247994",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n04-t3006-307417-310307",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n05-t3007-284945-287898",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n09-t1409-143096-143834",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n09-t1409-297601-298865",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n09-t1409-385922-386603",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n10-t711-186553-188161",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n12-t1411-237107-242145",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n12-t1411-679986-681985",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n15-t3010-164698-170777",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n17-t717-253073-260377",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n17-t717-304624-307834",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n17-t717-416826-418915",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n21-t3011-390297-390800",
            "sampled_instants": 10,
            "sent_images": 10,
            "crop_images": 10,
            "context_images": 0
          },
          {
            "clip_id": "m04-n22-t3012-070707-074371",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n24-t3013-679939-681217",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          },
          {
            "clip_id": "m04-n25-t3014-530600-532465",
            "sampled_instants": 12,
            "sent_images": 12,
            "crop_images": 12,
            "context_images": 0
          }
        ],
        "sampled_instants": 238,
        "sent_images": 238,
        "coordinate_space": "Decoded lane-B frames; source truth scaled before crop geometry"
      },
      "crop8_prod30": {
        "crop_side_px_min": 384,
        "crop_side_px_max": 689,
        "crop_scale_min": 1.1146589259796806,
        "crop_scale_max": 2.0,
        "crop_output_size": [
          768,
          768
        ],
        "context_width": null,
        "per_clip_counts": [
          {
            "clip_id": "m04-n02-t3005-474114-478131",
            "sampled_instants": 2,
            "sent_images": 2,
            "crop_images": 2,
            "context_images": 0
          },
          {
            "clip_id": "m04-n03-t1406-157170-158922",
            "sampled_instants": 1,
            "sent_images": 1,
            "crop_images": 1,
            "context_images": 0
          },
          {
            "clip_id": "m04-n03-t1406-385962-387137",
            "sampled_instants": 1,
            "sent_images": 1,
            "crop_images": 1,
            "context_images": 0
          },
          {
            "clip_id": "m04-n04-t3006-243433-247994",
            "sampled_instants": 2,
            "sent_images": 2,
            "crop_images": 2,
            "context_images": 0
          },
          {
            "clip_id": "m04-n04-t3006-307417-310307",
            "sampled_instants": 1,
            "sent_images": 1,
            "crop_images": 1,
            "context_images": 0
          },
          {
            "clip_id": "m04-n05-t3007-284945-287898",
            "sampled_instants": 1,
            "sent_images": 1,
            "crop_images": 1,
            "context_images": 0
          },
          {
            "clip_id": "m04-n09-t1409-143096-143834",
            "sampled_instants": 1,
            "sent_images": 1,
            "crop_images": 1,
            "context_images": 0
          },
          {
            "clip_id": "m04-n09-t1409-297601-298865",
            "sampled_instants": 1,
            "sent_images": 1,
            "crop_images": 1,
            "context_images": 0
          },
          {
            "clip_id": "m04-n09-t1409-385922-386603",
            "sampled_instants": 1,
            "sent_images": 1,
            "crop_images": 1,
            "context_images": 0
          },
          {
            "clip_id": "m04-n10-t711-186553-188161",
            "sampled_instants": 1,
            "sent_images": 1,
            "crop_images": 1,
            "context_images": 0
          },
          {
            "clip_id": "m04-n12-t1411-237107-242145",
            "sampled_instants": 2,
            "sent_images": 2,
            "crop_images": 2,
            "context_images": 0
          },
          {
            "clip_id": "m04-n12-t1411-679986-681985",
            "sampled_instants": 1,
            "sent_images": 1,
            "crop_images": 1,
            "context_images": 0
          },
          {
            "clip_id": "m04-n15-t3010-164698-170777",
            "sampled_instants": 3,
            "sent_images": 3,
            "crop_images": 3,
            "context_images": 0
          },
          {
            "clip_id": "m04-n17-t717-253073-260377",
            "sampled_instants": 3,
            "sent_images": 3,
            "crop_images": 3,
            "context_images": 0
          },
          {
            "clip_id": "m04-n17-t717-304624-307834",
            "sampled_instants": 2,
            "sent_images": 2,
            "crop_images": 2,
            "context_images": 0
          },
          {
            "clip_id": "m04-n17-t717-416826-418915",
            "sampled_instants": 1,
            "sent_images": 1,
            "crop_images": 1,
            "context_images": 0
          },
          {
            "clip_id": "m04-n21-t3011-390297-390800",
            "sampled_instants": 1,
            "sent_images": 1,
            "crop_images": 1,
            "context_images": 0
          },
          {
            "clip_id": "m04-n22-t3012-070707-074371",
            "sampled_instants": 2,
            "sent_images": 2,
            "crop_images": 2,
            "context_images": 0
          },
          {
            "clip_id": "m04-n24-t3013-679939-681217",
            "sampled_instants": 1,
            "sent_images": 1,
            "crop_images": 1,
            "context_images": 0
          },
          {
            "clip_id": "m04-n25-t3014-530600-532465",
            "sampled_instants": 1,
            "sent_images": 1,
            "crop_images": 1,
            "context_images": 0
          }
        ],
        "sampled_instants": 29,
        "sent_images": 29,
        "coordinate_space": "Decoded lane-B frames; source truth scaled before crop geometry"
      },
      "cropctx8_dense": {
        "crop_side_px_min": 384,
        "crop_side_px_max": 689,
        "crop_scale_min": 1.1146589259796806,
        "crop_scale_max": 2.0,
        "crop_output_size": [
          768,
          768
        ],
        "context_width": 512,
        "per_clip_counts": [
          {
            "clip_id": "m04-n02-t3005-474114-478131",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n03-t1406-157170-158922",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n03-t1406-385962-387137",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n04-t3006-243433-247994",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n04-t3006-307417-310307",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n05-t3007-284945-287898",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n09-t1409-143096-143834",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n09-t1409-297601-298865",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n09-t1409-385922-386603",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n10-t711-186553-188161",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n12-t1411-237107-242145",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n12-t1411-679986-681985",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n15-t3010-164698-170777",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n17-t717-253073-260377",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n17-t717-304624-307834",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n17-t717-416826-418915",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n21-t3011-390297-390800",
            "sampled_instants": 10,
            "sent_images": 20,
            "crop_images": 10,
            "context_images": 10
          },
          {
            "clip_id": "m04-n22-t3012-070707-074371",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n24-t3013-679939-681217",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          },
          {
            "clip_id": "m04-n25-t3014-530600-532465",
            "sampled_instants": 12,
            "sent_images": 24,
            "crop_images": 12,
            "context_images": 12
          }
        ],
        "sampled_instants": 238,
        "sent_images": 476,
        "coordinate_space": "Decoded lane-B frames; source truth scaled before crop geometry"
      }
    },
    "example_crops": [
      {
        "path": "/Users/mjjones/Projects/loanarmy-bench-reports/e1e-crop-examples/m04-n12-t1411-237107-242145-sample-00.png",
        "t": 2371.12,
        "sent_w": 768,
        "sent_h": 768,
        "target_t": 2371.12,
        "sampling_shift_s": 0.0,
        "crop_side_px": 384,
        "crop_scale": 2.0,
        "crop_rect": [
          752,
          74,
          1136,
          458
        ],
        "decoded_frame_size": [
          1280,
          720
        ],
        "box_decoded_space": [
          936.1904761904767,
          241.14285714285654,
          952.285714285713,
          291.3333333333333
        ],
        "box": [
          368.38095238095343,
          334.2857142857131,
          400.57142857142594,
          434.66666666666663
        ],
        "image_kind": "crop",
        "sha256": "f124e405b5f90d6fe7f68cdf4bc799a0370f6324ffcd7d97685232c1be5fc8a7"
      },
      {
        "path": "/Users/mjjones/Projects/loanarmy-bench-reports/e1e-crop-examples/m04-n12-t1411-237107-242145-sample-05.png",
        "t": 2393.975,
        "sent_w": 768,
        "sent_h": 768,
        "target_t": 2393.975,
        "sampling_shift_s": 0.0,
        "crop_side_px": 384,
        "crop_scale": 2.0,
        "crop_rect": [
          7,
          191,
          391,
          575
        ],
        "decoded_frame_size": [
          1280,
          720
        ],
        "box_decoded_space": [
          184.90000000000228,
          346.66666666666663,
          213.20000000000303,
          418.66666666666663
        ],
        "box": [
          355.80000000000456,
          311.33333333333326,
          412.40000000000606,
          455.33333333333326
        ],
        "image_kind": "crop",
        "sha256": "56e99a5e7fe703016f6bc5768a3eeb0194b8b0a9d5f933bc113f8818312aa13b"
      },
      {
        "path": "/Users/mjjones/Projects/loanarmy-bench-reports/e1e-crop-examples/m04-n12-t1411-237107-242145-sample-11.png",
        "t": 2421.4,
        "sent_w": 768,
        "sent_h": 768,
        "target_t": 2421.4,
        "sampling_shift_s": 0.0,
        "crop_side_px": 384,
        "crop_scale": 2.0,
        "crop_rect": [
          813,
          145,
          1197,
          529
        ],
        "decoded_frame_size": [
          1280,
          720
        ],
        "box_decoded_space": [
          989.5555555556061,
          308.1111111111136,
          1020.0000000000455,
          365.1111111111061
        ],
        "box": [
          353.11111111121227,
          326.2222222222272,
          414.00000000009095,
          440.22222222221217
        ],
        "image_kind": "crop",
        "sha256": "6b0dbfc380de794aa5538bd3a548d23df1e96a3dd3b7699a6b08703b0fcfffa2"
      }
    ],
    "decision_32b": {
      "recalls": {
        "e1e-crop-8b-dense": {
          "hits": [],
          "count": 0,
          "denominator": 6
        },
        "e1e-crop-8b-prod30": {
          "hits": [],
          "count": 0,
          "denominator": 6
        },
        "e1e-cropctx-8b-dense": {
          "hits": [],
          "count": 0,
          "denominator": 6
        }
      },
      "run": false,
      "rule": "At least 2/6 yes on true-touch clips in any 8B run"
    }
  },
  "previous_truth": {
    "m04-n02-t3005-474114-478131": {
      "player_on_pitch": "yes",
      "play_in_progress": "yes",
      "ball_near_player": null,
      "player_touches_ball": null,
      "player_running": null,
      "kit_color_seen": "red"
    },
    "m04-n03-t1406-157170-158922": {
      "player_on_pitch": "yes",
      "play_in_progress": "yes",
      "ball_near_player": "yes",
      "player_touches_ball": "yes",
      "player_running": "yes",
      "kit_color_seen": "red"
    },
    "m04-n03-t1406-385962-387137": {
      "player_on_pitch": "no",
      "play_in_progress": "no",
      "ball_near_player": "no",
      "player_touches_ball": "no",
      "player_running": "no",
      "kit_color_seen": null
    },
    "m04-n04-t3006-243433-247994": {
      "player_on_pitch": "yes",
      "play_in_progress": "yes",
      "ball_near_player": "yes",
      "player_touches_ball": "yes",
      "player_running": null,
      "kit_color_seen": "red"
    },
    "m04-n04-t3006-307417-310307": {
      "player_on_pitch": "yes",
      "play_in_progress": "no",
      "ball_near_player": "no",
      "player_touches_ball": "no",
      "player_running": "yes",
      "kit_color_seen": "red"
    },
    "m04-n05-t3007-284945-287898": {
      "player_on_pitch": "yes",
      "play_in_progress": "yes",
      "ball_near_player": null,
      "player_touches_ball": null,
      "player_running": "yes",
      "kit_color_seen": "red"
    },
    "m04-n09-t1409-143096-143834": {
      "player_on_pitch": "no",
      "play_in_progress": "no",
      "ball_near_player": "no",
      "player_touches_ball": "no",
      "player_running": "no",
      "kit_color_seen": "red"
    },
    "m04-n09-t1409-297601-298865": {
      "player_on_pitch": "yes",
      "play_in_progress": "yes",
      "ball_near_player": null,
      "player_touches_ball": null,
      "player_running": "yes",
      "kit_color_seen": "red"
    },
    "m04-n09-t1409-385922-386603": {
      "player_on_pitch": "no",
      "play_in_progress": "no",
      "ball_near_player": "no",
      "player_touches_ball": "no",
      "player_running": "no",
      "kit_color_seen": "red"
    },
    "m04-n10-t711-186553-188161": {
      "player_on_pitch": "yes",
      "play_in_progress": null,
      "ball_near_player": "no",
      "player_touches_ball": "no",
      "player_running": "no",
      "kit_color_seen": "red"
    },
    "m04-n12-t1411-237107-242145": {
      "player_on_pitch": "yes",
      "play_in_progress": "yes",
      "ball_near_player": "yes",
      "player_touches_ball": "yes",
      "player_running": null,
      "kit_color_seen": "red"
    },
    "m04-n12-t1411-679986-681985": {
      "player_on_pitch": "no",
      "play_in_progress": "no",
      "ball_near_player": "no",
      "player_touches_ball": "no",
      "player_running": "no",
      "kit_color_seen": "red"
    },
    "m04-n15-t3010-164698-170777": {
      "player_on_pitch": "yes",
      "play_in_progress": "yes",
      "ball_near_player": "yes",
      "player_touches_ball": "yes",
      "player_running": "yes",
      "kit_color_seen": "red"
    },
    "m04-n17-t717-253073-260377": {
      "player_on_pitch": "yes",
      "play_in_progress": "yes",
      "ball_near_player": "yes",
      "player_touches_ball": "yes",
      "player_running": "yes",
      "kit_color_seen": "red"
    },
    "m04-n17-t717-304624-307834": {
      "player_on_pitch": "yes",
      "play_in_progress": "yes",
      "ball_near_player": null,
      "player_touches_ball": null,
      "player_running": "no",
      "kit_color_seen": "red"
    },
    "m04-n17-t717-416826-418915": {
      "player_on_pitch": "yes",
      "play_in_progress": "yes",
      "ball_near_player": "yes",
      "player_touches_ball": "yes",
      "player_running": "yes",
      "kit_color_seen": "red"
    },
    "m04-n21-t3011-390297-390800": {
      "player_on_pitch": "no",
      "play_in_progress": "no",
      "ball_near_player": "no",
      "player_touches_ball": "no",
      "player_running": "no",
      "kit_color_seen": "red"
    },
    "m04-n22-t3012-070707-074371": {
      "player_on_pitch": "no",
      "play_in_progress": "no",
      "ball_near_player": "no",
      "player_touches_ball": "no",
      "player_running": "no",
      "kit_color_seen": null
    },
    "m04-n24-t3013-679939-681217": {
      "player_on_pitch": null,
      "play_in_progress": null,
      "ball_near_player": null,
      "player_touches_ball": null,
      "player_running": null,
      "kit_color_seen": "black"
    },
    "m04-n25-t3014-530600-532465": {
      "player_on_pitch": "no",
      "play_in_progress": "no",
      "ball_near_player": "no",
      "player_touches_ball": "no",
      "player_running": "no",
      "kit_color_seen": "red"
    }
  },
  "previous_metrics": {
    "8b_dense": {
      "attempted_clips": 20,
      "scored_clips": 20,
      "failed_clips": 0,
      "questions": {
        "player_on_pitch": {
          "eligible_count": 19,
          "answered_count": 19,
          "correct_count": 12,
          "abstain_count": 0,
          "truth_no_count": 7,
          "truth_yes_count": 12,
          "false_yes_count": 7,
          "false_no_count": 0,
          "accuracy": 0.631578947368421,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 1.0,
          "false_no_rate": 0.0,
          "confident_wrong_count": 7
        },
        "play_in_progress": {
          "eligible_count": 18,
          "answered_count": 18,
          "correct_count": 16,
          "abstain_count": 0,
          "truth_no_count": 8,
          "truth_yes_count": 10,
          "false_yes_count": 1,
          "false_no_count": 1,
          "accuracy": 0.8888888888888888,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.125,
          "false_no_rate": 0.1,
          "confident_wrong_count": 0
        },
        "ball_near_player": {
          "eligible_count": 15,
          "answered_count": 14,
          "correct_count": 7,
          "abstain_count": 1,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 1,
          "false_no_count": 6,
          "accuracy": 0.5,
          "abstain_rate": 0.06666666666666667,
          "coverage": 0.9333333333333333,
          "false_yes_rate": 0.1111111111111111,
          "false_no_rate": 1.0,
          "confident_wrong_count": 1
        },
        "player_touches_ball": {
          "eligible_count": 15,
          "answered_count": 15,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 0,
          "false_no_count": 6,
          "accuracy": 0.6,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": 1.0,
          "confident_wrong_count": 6
        },
        "player_running": {
          "eligible_count": 16,
          "answered_count": 16,
          "correct_count": 7,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 7,
          "false_yes_count": 9,
          "false_no_count": 0,
          "accuracy": 0.4375,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 1.0,
          "false_no_rate": 0.0,
          "confident_wrong_count": 0
        },
        "kit_color_seen": {
          "eligible_count": 20,
          "answered_count": 18,
          "correct_count": 17,
          "abstain_count": 2,
          "truth_no_count": 0,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 0.9444444444444444,
          "abstain_rate": 0.1,
          "coverage": 0.9,
          "false_yes_rate": null,
          "false_no_rate": null,
          "confident_wrong_count": 1
        }
      },
      "gates": {
        "off_pitch": {
          "eligible_count": 14,
          "answered_count": 14,
          "correct_count": 6,
          "abstain_count": 0,
          "truth_no_count": 14,
          "truth_yes_count": 0,
          "false_yes_count": 8,
          "false_no_count": 0,
          "accuracy": 0.42857142857142855,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.5714285714285714,
          "false_no_rate": null,
          "confident_wrong_count": 7
        },
        "off_pitch_idle_touch": {
          "eligible_count": 9,
          "answered_count": 9,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 1.0,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": null,
          "confident_wrong_count": 0
        }
      },
      "off_pitch_false_yes_rate": 0.5714285714285714,
      "off_pitch_idle_touch_false_yes_rate": 0.0,
      "macro_accuracy": 0.6670687134502923,
      "macro_false_yes_rate": 0.44722222222222224,
      "abstain_rate": 0.02912621359223301,
      "from_thinking_rate": 1.0,
      "wall_s_per_clip": 51.65084999999999
    },
    "8b_prod30": {
      "attempted_clips": 20,
      "scored_clips": 20,
      "failed_clips": 0,
      "questions": {
        "player_on_pitch": {
          "eligible_count": 19,
          "answered_count": 19,
          "correct_count": 13,
          "abstain_count": 0,
          "truth_no_count": 7,
          "truth_yes_count": 12,
          "false_yes_count": 6,
          "false_no_count": 0,
          "accuracy": 0.6842105263157895,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.8571428571428571,
          "false_no_rate": 0.0,
          "confident_wrong_count": 6
        },
        "play_in_progress": {
          "eligible_count": 18,
          "answered_count": 18,
          "correct_count": 7,
          "abstain_count": 0,
          "truth_no_count": 8,
          "truth_yes_count": 10,
          "false_yes_count": 2,
          "false_no_count": 9,
          "accuracy": 0.3888888888888889,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.25,
          "false_no_rate": 0.9,
          "confident_wrong_count": 0
        },
        "ball_near_player": {
          "eligible_count": 15,
          "answered_count": 9,
          "correct_count": 8,
          "abstain_count": 6,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 0,
          "false_no_count": 1,
          "accuracy": 0.8888888888888888,
          "abstain_rate": 0.4,
          "coverage": 0.6,
          "false_yes_rate": 0.0,
          "false_no_rate": 0.16666666666666666,
          "confident_wrong_count": 0
        },
        "player_touches_ball": {
          "eligible_count": 15,
          "answered_count": 15,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 0,
          "false_no_count": 6,
          "accuracy": 0.6,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": 1.0,
          "confident_wrong_count": 6
        },
        "player_running": {
          "eligible_count": 16,
          "answered_count": 16,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 7,
          "false_yes_count": 7,
          "false_no_count": 0,
          "accuracy": 0.5625,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.7777777777777778,
          "false_no_rate": 0.0,
          "confident_wrong_count": 0
        },
        "kit_color_seen": {
          "eligible_count": 20,
          "answered_count": 18,
          "correct_count": 15,
          "abstain_count": 2,
          "truth_no_count": 0,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 0.8333333333333334,
          "abstain_rate": 0.1,
          "coverage": 0.9,
          "false_yes_rate": null,
          "false_no_rate": null,
          "confident_wrong_count": 3
        }
      },
      "gates": {
        "off_pitch": {
          "eligible_count": 14,
          "answered_count": 14,
          "correct_count": 7,
          "abstain_count": 0,
          "truth_no_count": 14,
          "truth_yes_count": 0,
          "false_yes_count": 7,
          "false_no_count": 0,
          "accuracy": 0.5,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.5,
          "false_no_rate": null,
          "confident_wrong_count": 6
        },
        "off_pitch_idle_touch": {
          "eligible_count": 9,
          "answered_count": 9,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 1.0,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": null,
          "confident_wrong_count": 0
        }
      },
      "off_pitch_false_yes_rate": 0.5,
      "off_pitch_idle_touch_false_yes_rate": 0.0,
      "macro_accuracy": 0.6596369395711501,
      "macro_false_yes_rate": 0.376984126984127,
      "abstain_rate": 0.07766990291262135,
      "from_thinking_rate": 1.0,
      "wall_s_per_clip": 10.5474
    },
    "32b_dense": {
      "attempted_clips": 20,
      "scored_clips": 20,
      "failed_clips": 0,
      "questions": {
        "player_on_pitch": {
          "eligible_count": 19,
          "answered_count": 19,
          "correct_count": 13,
          "abstain_count": 0,
          "truth_no_count": 7,
          "truth_yes_count": 12,
          "false_yes_count": 6,
          "false_no_count": 0,
          "accuracy": 0.6842105263157895,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.8571428571428571,
          "false_no_rate": 0.0,
          "confident_wrong_count": 6
        },
        "play_in_progress": {
          "eligible_count": 18,
          "answered_count": 13,
          "correct_count": 11,
          "abstain_count": 5,
          "truth_no_count": 8,
          "truth_yes_count": 10,
          "false_yes_count": 2,
          "false_no_count": 0,
          "accuracy": 0.8461538461538461,
          "abstain_rate": 0.2777777777777778,
          "coverage": 0.7222222222222222,
          "false_yes_rate": 0.25,
          "false_no_rate": 0.0,
          "confident_wrong_count": 1
        },
        "ball_near_player": {
          "eligible_count": 15,
          "answered_count": 15,
          "correct_count": 8,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 1,
          "false_no_count": 6,
          "accuracy": 0.5333333333333333,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.1111111111111111,
          "false_no_rate": 1.0,
          "confident_wrong_count": 7
        },
        "player_touches_ball": {
          "eligible_count": 15,
          "answered_count": 15,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 0,
          "false_no_count": 6,
          "accuracy": 0.6,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": 1.0,
          "confident_wrong_count": 6
        },
        "player_running": {
          "eligible_count": 16,
          "answered_count": 16,
          "correct_count": 10,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 7,
          "false_yes_count": 6,
          "false_no_count": 0,
          "accuracy": 0.625,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.6666666666666666,
          "false_no_rate": 0.0,
          "confident_wrong_count": 0
        },
        "kit_color_seen": {
          "eligible_count": 20,
          "answered_count": 18,
          "correct_count": 17,
          "abstain_count": 2,
          "truth_no_count": 0,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 0.9444444444444444,
          "abstain_rate": 0.1,
          "coverage": 0.9,
          "false_yes_rate": null,
          "false_no_rate": null,
          "confident_wrong_count": 1
        }
      },
      "gates": {
        "off_pitch": {
          "eligible_count": 14,
          "answered_count": 9,
          "correct_count": 2,
          "abstain_count": 5,
          "truth_no_count": 14,
          "truth_yes_count": 0,
          "false_yes_count": 7,
          "false_no_count": 0,
          "accuracy": 0.2222222222222222,
          "abstain_rate": 0.35714285714285715,
          "coverage": 0.6428571428571429,
          "false_yes_rate": 0.5,
          "false_no_rate": null,
          "confident_wrong_count": 7
        },
        "off_pitch_idle_touch": {
          "eligible_count": 9,
          "answered_count": 9,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 1.0,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": null,
          "confident_wrong_count": 0
        }
      },
      "off_pitch_false_yes_rate": 0.5,
      "off_pitch_idle_touch_false_yes_rate": 0.0,
      "macro_accuracy": 0.7055236917079023,
      "macro_false_yes_rate": 0.376984126984127,
      "abstain_rate": 0.06796116504854369,
      "from_thinking_rate": 1.0,
      "wall_s_per_clip": 216.42754999999997
    },
    "32b_prod30": {
      "attempted_clips": 20,
      "scored_clips": 20,
      "failed_clips": 0,
      "questions": {
        "player_on_pitch": {
          "eligible_count": 19,
          "answered_count": 19,
          "correct_count": 12,
          "abstain_count": 0,
          "truth_no_count": 7,
          "truth_yes_count": 12,
          "false_yes_count": 7,
          "false_no_count": 0,
          "accuracy": 0.631578947368421,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 1.0,
          "false_no_rate": 0.0,
          "confident_wrong_count": 7
        },
        "play_in_progress": {
          "eligible_count": 18,
          "answered_count": 13,
          "correct_count": 8,
          "abstain_count": 5,
          "truth_no_count": 8,
          "truth_yes_count": 10,
          "false_yes_count": 4,
          "false_no_count": 1,
          "accuracy": 0.6153846153846154,
          "abstain_rate": 0.2777777777777778,
          "coverage": 0.7222222222222222,
          "false_yes_rate": 0.5,
          "false_no_rate": 0.1,
          "confident_wrong_count": 1
        },
        "ball_near_player": {
          "eligible_count": 15,
          "answered_count": 13,
          "correct_count": 9,
          "abstain_count": 2,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 0,
          "false_no_count": 4,
          "accuracy": 0.6923076923076923,
          "abstain_rate": 0.13333333333333333,
          "coverage": 0.8666666666666667,
          "false_yes_rate": 0.0,
          "false_no_rate": 0.6666666666666666,
          "confident_wrong_count": 1
        },
        "player_touches_ball": {
          "eligible_count": 15,
          "answered_count": 15,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 0,
          "false_no_count": 6,
          "accuracy": 0.6,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": 1.0,
          "confident_wrong_count": 5
        },
        "player_running": {
          "eligible_count": 16,
          "answered_count": 12,
          "correct_count": 9,
          "abstain_count": 4,
          "truth_no_count": 9,
          "truth_yes_count": 7,
          "false_yes_count": 3,
          "false_no_count": 0,
          "accuracy": 0.75,
          "abstain_rate": 0.25,
          "coverage": 0.75,
          "false_yes_rate": 0.3333333333333333,
          "false_no_rate": 0.0,
          "confident_wrong_count": 1
        },
        "kit_color_seen": {
          "eligible_count": 20,
          "answered_count": 18,
          "correct_count": 18,
          "abstain_count": 2,
          "truth_no_count": 0,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 1.0,
          "abstain_rate": 0.1,
          "coverage": 0.9,
          "false_yes_rate": null,
          "false_no_rate": null,
          "confident_wrong_count": 0
        }
      },
      "gates": {
        "off_pitch": {
          "eligible_count": 14,
          "answered_count": 12,
          "correct_count": 2,
          "abstain_count": 2,
          "truth_no_count": 14,
          "truth_yes_count": 0,
          "false_yes_count": 10,
          "false_no_count": 0,
          "accuracy": 0.16666666666666666,
          "abstain_rate": 0.14285714285714285,
          "coverage": 0.8571428571428571,
          "false_yes_rate": 0.7142857142857143,
          "false_no_rate": null,
          "confident_wrong_count": 8
        },
        "off_pitch_idle_touch": {
          "eligible_count": 9,
          "answered_count": 9,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 1.0,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": null,
          "confident_wrong_count": 0
        }
      },
      "off_pitch_false_yes_rate": 0.7142857142857143,
      "off_pitch_idle_touch_false_yes_rate": 0.0,
      "macro_accuracy": 0.7148785425101215,
      "macro_false_yes_rate": 0.36666666666666664,
      "abstain_rate": 0.1262135922330097,
      "from_thinking_rate": 1.0,
      "wall_s_per_clip": 39.57985000000001
    },
    "27b_dense": {
      "attempted_clips": 20,
      "scored_clips": 20,
      "failed_clips": 0,
      "questions": {
        "player_on_pitch": {
          "eligible_count": 19,
          "answered_count": 19,
          "correct_count": 13,
          "abstain_count": 0,
          "truth_no_count": 7,
          "truth_yes_count": 12,
          "false_yes_count": 6,
          "false_no_count": 0,
          "accuracy": 0.6842105263157895,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.8571428571428571,
          "false_no_rate": 0.0,
          "confident_wrong_count": 6
        },
        "play_in_progress": {
          "eligible_count": 18,
          "answered_count": 18,
          "correct_count": 14,
          "abstain_count": 0,
          "truth_no_count": 8,
          "truth_yes_count": 10,
          "false_yes_count": 4,
          "false_no_count": 0,
          "accuracy": 0.7777777777777778,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.5,
          "false_no_rate": 0.0,
          "confident_wrong_count": 4
        },
        "ball_near_player": {
          "eligible_count": 15,
          "answered_count": 13,
          "correct_count": 6,
          "abstain_count": 2,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 1,
          "false_no_count": 6,
          "accuracy": 0.46153846153846156,
          "abstain_rate": 0.13333333333333333,
          "coverage": 0.8666666666666667,
          "false_yes_rate": 0.1111111111111111,
          "false_no_rate": 1.0,
          "confident_wrong_count": 1
        },
        "player_touches_ball": {
          "eligible_count": 15,
          "answered_count": 15,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 0,
          "false_no_count": 6,
          "accuracy": 0.6,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": 1.0,
          "confident_wrong_count": 2
        },
        "player_running": {
          "eligible_count": 16,
          "answered_count": 16,
          "correct_count": 12,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 7,
          "false_yes_count": 4,
          "false_no_count": 0,
          "accuracy": 0.75,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.4444444444444444,
          "false_no_rate": 0.0,
          "confident_wrong_count": 0
        },
        "kit_color_seen": {
          "eligible_count": 20,
          "answered_count": 18,
          "correct_count": 17,
          "abstain_count": 2,
          "truth_no_count": 0,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 0.9444444444444444,
          "abstain_rate": 0.1,
          "coverage": 0.9,
          "false_yes_rate": null,
          "false_no_rate": null,
          "confident_wrong_count": 1
        }
      },
      "gates": {
        "off_pitch": {
          "eligible_count": 14,
          "answered_count": 14,
          "correct_count": 5,
          "abstain_count": 0,
          "truth_no_count": 14,
          "truth_yes_count": 0,
          "false_yes_count": 9,
          "false_no_count": 0,
          "accuracy": 0.35714285714285715,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.6428571428571429,
          "false_no_rate": null,
          "confident_wrong_count": 9
        },
        "off_pitch_idle_touch": {
          "eligible_count": 9,
          "answered_count": 9,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 1.0,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": null,
          "confident_wrong_count": 0
        }
      },
      "off_pitch_false_yes_rate": 0.6428571428571429,
      "off_pitch_idle_touch_false_yes_rate": 0.0,
      "macro_accuracy": 0.7029952016794122,
      "macro_false_yes_rate": 0.38253968253968257,
      "abstain_rate": 0.038834951456310676,
      "from_thinking_rate": 0.0,
      "wall_s_per_clip": 172.7882
    },
    "27b_prod30": {
      "attempted_clips": 20,
      "scored_clips": 20,
      "failed_clips": 0,
      "questions": {
        "player_on_pitch": {
          "eligible_count": 19,
          "answered_count": 19,
          "correct_count": 12,
          "abstain_count": 0,
          "truth_no_count": 7,
          "truth_yes_count": 12,
          "false_yes_count": 7,
          "false_no_count": 0,
          "accuracy": 0.631578947368421,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 1.0,
          "false_no_rate": 0.0,
          "confident_wrong_count": 7
        },
        "play_in_progress": {
          "eligible_count": 18,
          "answered_count": 16,
          "correct_count": 11,
          "abstain_count": 2,
          "truth_no_count": 8,
          "truth_yes_count": 10,
          "false_yes_count": 5,
          "false_no_count": 0,
          "accuracy": 0.6875,
          "abstain_rate": 0.1111111111111111,
          "coverage": 0.8888888888888888,
          "false_yes_rate": 0.625,
          "false_no_rate": 0.0,
          "confident_wrong_count": 5
        },
        "ball_near_player": {
          "eligible_count": 15,
          "answered_count": 15,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 0,
          "false_no_count": 6,
          "accuracy": 0.6,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": 1.0,
          "confident_wrong_count": 1
        },
        "player_touches_ball": {
          "eligible_count": 15,
          "answered_count": 7,
          "correct_count": 6,
          "abstain_count": 8,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 0,
          "false_no_count": 1,
          "accuracy": 0.8571428571428571,
          "abstain_rate": 0.5333333333333333,
          "coverage": 0.4666666666666667,
          "false_yes_rate": 0.0,
          "false_no_rate": 0.16666666666666666,
          "confident_wrong_count": 0
        },
        "player_running": {
          "eligible_count": 16,
          "answered_count": 11,
          "correct_count": 7,
          "abstain_count": 5,
          "truth_no_count": 9,
          "truth_yes_count": 7,
          "false_yes_count": 3,
          "false_no_count": 1,
          "accuracy": 0.6363636363636364,
          "abstain_rate": 0.3125,
          "coverage": 0.6875,
          "false_yes_rate": 0.3333333333333333,
          "false_no_rate": 0.14285714285714285,
          "confident_wrong_count": 1
        },
        "kit_color_seen": {
          "eligible_count": 20,
          "answered_count": 18,
          "correct_count": 16,
          "abstain_count": 2,
          "truth_no_count": 0,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 0.8888888888888888,
          "abstain_rate": 0.1,
          "coverage": 0.9,
          "false_yes_rate": null,
          "false_no_rate": null,
          "confident_wrong_count": 2
        }
      },
      "gates": {
        "off_pitch": {
          "eligible_count": 14,
          "answered_count": 12,
          "correct_count": 1,
          "abstain_count": 2,
          "truth_no_count": 14,
          "truth_yes_count": 0,
          "false_yes_count": 11,
          "false_no_count": 0,
          "accuracy": 0.08333333333333333,
          "abstain_rate": 0.14285714285714285,
          "coverage": 0.8571428571428571,
          "false_yes_rate": 0.7857142857142857,
          "false_no_rate": null,
          "confident_wrong_count": 11
        },
        "off_pitch_idle_touch": {
          "eligible_count": 9,
          "answered_count": 6,
          "correct_count": 6,
          "abstain_count": 3,
          "truth_no_count": 9,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 1.0,
          "abstain_rate": 0.3333333333333333,
          "coverage": 0.6666666666666666,
          "false_yes_rate": 0.0,
          "false_no_rate": null,
          "confident_wrong_count": 0
        }
      },
      "off_pitch_false_yes_rate": 0.7857142857142857,
      "off_pitch_idle_touch_false_yes_rate": 0.0,
      "macro_accuracy": 0.7169123882939671,
      "macro_false_yes_rate": 0.39166666666666666,
      "abstain_rate": 0.1650485436893204,
      "from_thinking_rate": 0.0,
      "wall_s_per_clip": 87.78285000000002
    },
    "crop8_dense": {
      "attempted_clips": 20,
      "scored_clips": 20,
      "failed_clips": 0,
      "questions": {
        "player_on_pitch": {
          "eligible_count": 19,
          "answered_count": 19,
          "correct_count": 12,
          "abstain_count": 0,
          "truth_no_count": 7,
          "truth_yes_count": 12,
          "false_yes_count": 7,
          "false_no_count": 0,
          "accuracy": 0.631578947368421,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 1.0,
          "false_no_rate": 0.0,
          "confident_wrong_count": 7
        },
        "play_in_progress": {
          "eligible_count": 18,
          "answered_count": 18,
          "correct_count": 10,
          "abstain_count": 0,
          "truth_no_count": 8,
          "truth_yes_count": 10,
          "false_yes_count": 0,
          "false_no_count": 8,
          "accuracy": 0.5555555555555556,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": 0.8,
          "confident_wrong_count": 0
        },
        "ball_near_player": {
          "eligible_count": 15,
          "answered_count": 15,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 0,
          "false_no_count": 6,
          "accuracy": 0.6,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": 1.0,
          "confident_wrong_count": 0
        },
        "player_touches_ball": {
          "eligible_count": 15,
          "answered_count": 15,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 0,
          "false_no_count": 6,
          "accuracy": 0.6,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": 1.0,
          "confident_wrong_count": 6
        },
        "player_running": {
          "eligible_count": 16,
          "answered_count": 16,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 7,
          "false_yes_count": 7,
          "false_no_count": 0,
          "accuracy": 0.5625,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.7777777777777778,
          "false_no_rate": 0.0,
          "confident_wrong_count": 0
        },
        "kit_color_seen": {
          "eligible_count": 20,
          "answered_count": 18,
          "correct_count": 17,
          "abstain_count": 2,
          "truth_no_count": 0,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 0.9444444444444444,
          "abstain_rate": 0.1,
          "coverage": 0.9,
          "false_yes_rate": null,
          "false_no_rate": null,
          "confident_wrong_count": 1
        }
      },
      "gates": {
        "off_pitch": {
          "eligible_count": 14,
          "answered_count": 14,
          "correct_count": 7,
          "abstain_count": 0,
          "truth_no_count": 14,
          "truth_yes_count": 0,
          "false_yes_count": 7,
          "false_no_count": 0,
          "accuracy": 0.5,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.5,
          "false_no_rate": null,
          "confident_wrong_count": 7
        },
        "off_pitch_idle_touch": {
          "eligible_count": 9,
          "answered_count": 9,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 1.0,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": null,
          "confident_wrong_count": 0
        }
      },
      "off_pitch_false_yes_rate": 0.5,
      "off_pitch_idle_touch_false_yes_rate": 0.0,
      "macro_accuracy": 0.6490131578947369,
      "macro_false_yes_rate": 0.3555555555555555,
      "abstain_rate": 0.019417475728155338,
      "from_thinking_rate": 1.0,
      "wall_s_per_clip": 53.43065
    },
    "crop8_prod30": {
      "attempted_clips": 20,
      "scored_clips": 20,
      "failed_clips": 0,
      "questions": {
        "player_on_pitch": {
          "eligible_count": 19,
          "answered_count": 19,
          "correct_count": 13,
          "abstain_count": 0,
          "truth_no_count": 7,
          "truth_yes_count": 12,
          "false_yes_count": 6,
          "false_no_count": 0,
          "accuracy": 0.6842105263157895,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.8571428571428571,
          "false_no_rate": 0.0,
          "confident_wrong_count": 6
        },
        "play_in_progress": {
          "eligible_count": 18,
          "answered_count": 18,
          "correct_count": 7,
          "abstain_count": 0,
          "truth_no_count": 8,
          "truth_yes_count": 10,
          "false_yes_count": 1,
          "false_no_count": 10,
          "accuracy": 0.3888888888888889,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.125,
          "false_no_rate": 1.0,
          "confident_wrong_count": 0
        },
        "ball_near_player": {
          "eligible_count": 15,
          "answered_count": 11,
          "correct_count": 8,
          "abstain_count": 4,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 0,
          "false_no_count": 3,
          "accuracy": 0.7272727272727273,
          "abstain_rate": 0.26666666666666666,
          "coverage": 0.7333333333333333,
          "false_yes_rate": 0.0,
          "false_no_rate": 0.5,
          "confident_wrong_count": 1
        },
        "player_touches_ball": {
          "eligible_count": 15,
          "answered_count": 15,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 0,
          "false_no_count": 6,
          "accuracy": 0.6,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": 1.0,
          "confident_wrong_count": 6
        },
        "player_running": {
          "eligible_count": 16,
          "answered_count": 16,
          "correct_count": 10,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 7,
          "false_yes_count": 6,
          "false_no_count": 0,
          "accuracy": 0.625,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.6666666666666666,
          "false_no_rate": 0.0,
          "confident_wrong_count": 0
        },
        "kit_color_seen": {
          "eligible_count": 20,
          "answered_count": 18,
          "correct_count": 18,
          "abstain_count": 2,
          "truth_no_count": 0,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 1.0,
          "abstain_rate": 0.1,
          "coverage": 0.9,
          "false_yes_rate": null,
          "false_no_rate": null,
          "confident_wrong_count": 0
        }
      },
      "gates": {
        "off_pitch": {
          "eligible_count": 14,
          "answered_count": 14,
          "correct_count": 7,
          "abstain_count": 0,
          "truth_no_count": 14,
          "truth_yes_count": 0,
          "false_yes_count": 7,
          "false_no_count": 0,
          "accuracy": 0.5,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.5,
          "false_no_rate": null,
          "confident_wrong_count": 6
        },
        "off_pitch_idle_touch": {
          "eligible_count": 9,
          "answered_count": 9,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 1.0,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": null,
          "confident_wrong_count": 0
        }
      },
      "off_pitch_false_yes_rate": 0.5,
      "off_pitch_idle_touch_false_yes_rate": 0.0,
      "macro_accuracy": 0.6708953570795676,
      "macro_false_yes_rate": 0.32976190476190476,
      "abstain_rate": 0.05825242718446602,
      "from_thinking_rate": 1.0,
      "wall_s_per_clip": 11.068200000000001
    },
    "cropctx8_dense": {
      "attempted_clips": 20,
      "scored_clips": 20,
      "failed_clips": 0,
      "questions": {
        "player_on_pitch": {
          "eligible_count": 19,
          "answered_count": 19,
          "correct_count": 12,
          "abstain_count": 0,
          "truth_no_count": 7,
          "truth_yes_count": 12,
          "false_yes_count": 7,
          "false_no_count": 0,
          "accuracy": 0.631578947368421,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 1.0,
          "false_no_rate": 0.0,
          "confident_wrong_count": 7
        },
        "play_in_progress": {
          "eligible_count": 18,
          "answered_count": 18,
          "correct_count": 12,
          "abstain_count": 0,
          "truth_no_count": 8,
          "truth_yes_count": 10,
          "false_yes_count": 0,
          "false_no_count": 6,
          "accuracy": 0.6666666666666666,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": 0.6,
          "confident_wrong_count": 0
        },
        "ball_near_player": {
          "eligible_count": 15,
          "answered_count": 14,
          "correct_count": 9,
          "abstain_count": 1,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 0,
          "false_no_count": 5,
          "accuracy": 0.6428571428571429,
          "abstain_rate": 0.06666666666666667,
          "coverage": 0.9333333333333333,
          "false_yes_rate": 0.0,
          "false_no_rate": 0.8333333333333334,
          "confident_wrong_count": 0
        },
        "player_touches_ball": {
          "eligible_count": 15,
          "answered_count": 15,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 6,
          "false_yes_count": 0,
          "false_no_count": 6,
          "accuracy": 0.6,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": 1.0,
          "confident_wrong_count": 6
        },
        "player_running": {
          "eligible_count": 16,
          "answered_count": 16,
          "correct_count": 8,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 7,
          "false_yes_count": 8,
          "false_no_count": 0,
          "accuracy": 0.5,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.8888888888888888,
          "false_no_rate": 0.0,
          "confident_wrong_count": 0
        },
        "kit_color_seen": {
          "eligible_count": 20,
          "answered_count": 18,
          "correct_count": 17,
          "abstain_count": 2,
          "truth_no_count": 0,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 0.9444444444444444,
          "abstain_rate": 0.1,
          "coverage": 0.9,
          "false_yes_rate": null,
          "false_no_rate": null,
          "confident_wrong_count": 1
        }
      },
      "gates": {
        "off_pitch": {
          "eligible_count": 14,
          "answered_count": 14,
          "correct_count": 7,
          "abstain_count": 0,
          "truth_no_count": 14,
          "truth_yes_count": 0,
          "false_yes_count": 7,
          "false_no_count": 0,
          "accuracy": 0.5,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.5,
          "false_no_rate": null,
          "confident_wrong_count": 7
        },
        "off_pitch_idle_touch": {
          "eligible_count": 9,
          "answered_count": 9,
          "correct_count": 9,
          "abstain_count": 0,
          "truth_no_count": 9,
          "truth_yes_count": 0,
          "false_yes_count": 0,
          "false_no_count": 0,
          "accuracy": 1.0,
          "abstain_rate": 0.0,
          "coverage": 1.0,
          "false_yes_rate": 0.0,
          "false_no_rate": null,
          "confident_wrong_count": 0
        }
      },
      "off_pitch_false_yes_rate": 0.5,
      "off_pitch_idle_touch_false_yes_rate": 0.0,
      "macro_accuracy": 0.6642578668894458,
      "macro_false_yes_rate": 0.37777777777777777,
      "abstain_rate": 0.02912621359223301,
      "from_thinking_rate": 1.0,
      "wall_s_per_clip": 122.83994999999997
    }
  },
  "regeneration": {
    "runs": {
      "8b_dense": "e1d-checks-dense",
      "8b_prod30": "e1d-checks-prod30",
      "32b_dense": "e1d-checks-32b-dense",
      "32b_prod30": "e1d-checks-32b-prod30",
      "27b_dense": "e1d-checks-27b-dense",
      "27b_prod30": "e1d-checks-27b-prod30",
      "crop8_dense": "e1e-crop-8b-dense",
      "crop8_prod30": "e1e-crop-8b-prod30",
      "cropctx8_dense": "e1e-cropctx-8b-dense"
    },
    "allow_mixed": true,
    "output_stem": "evidence-bench-2026-09-10-lane-c-crops"
  },
  "validation": {
    "status": "passed",
    "pytest": "333 passed in 1.19s; BENCH_REQUIRE_CV2=1 /Users/mjjones/Projects/loanarmy/.loan/bin/python -m pytest spike/video-analysis/bench -q",
    "ruff_check": "PASS; ruff check spike/video-analysis/bench",
    "ruff_format": "PASS, 33 files; ruff format --check spike/video-analysis/bench",
    "diff_check": "PASS; git diff --check",
    "regeneration": "All three JSON/Markdown ledger pairs regenerated twice with byte-for-byte equality using regenerate_checks_ledgers.py and these committed execution fixtures.",
    "preserved": "All nine run.json settings and 180 reads equal b96e6b2 ledger; frozen truth bytes and human note hashes unchanged; contract, prompts, transport, image adapters, runner and lane-A scorer unchanged.",
    "no_inference": true
  },
  "not_done": "No new model runs, moment windows, production integration or adoption decision. MJ must mark touch times on all six clips. Pilot PROMPT_VERSION was not persisted and remains unconfirmed; final version verified from run.json. No notes-file correction appeared; no lane-A rescore needed. No push."
}
```
