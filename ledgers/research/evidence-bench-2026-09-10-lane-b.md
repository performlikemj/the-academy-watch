On 20 shared scored clips (wide runs only; crops excluded from gate-1 headline): e1d-checks-dense (qwen3-vl:8b, 11.9 boxed frames/attempt): off-pitch false-yes 57.14%, touch false-yes 0.00%, touch recall N/A (raw 0/6), gate 2 WITHHELD; e1d-checks-prod30 (qwen3-vl:8b, 1.45 boxed frames/attempt): off-pitch false-yes 50.00%, touch false-yes 0.00%, touch recall N/A (raw 0/6), gate 2 WITHHELD. Adoption belongs to MJ.

Gate numbers (false-yes count / truth-no cells):

| Run | Off-pitch on-pitch | Off-pitch in-progress | Gate 1 pooled | Touch false-yes | Raw touch yes/positive | Touch recall | Gate 2 | Confounds |
|---|---:|---:|---:|---:|---:|---|---|---|
| e1d-checks-dense | 7/7 (100.00%) | 1/7 (14.29%) | 8/14 (57.14%) | 0/9 (0.00%) | 0/6 | N/A | WITHHELD | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition.  |
| e1d-checks-prod30 | 6/7 (85.71%) | 1/7 (14.29%) | 7/14 (50.00%) | 0/9 (0.00%) | 0/6 | N/A | WITHHELD | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition.  |

Per-question comparison:

| Run | Question | Eligible/answered | Accuracy | Majority baseline | Accuracy minus baseline | Modal answer | Modal share | Information | Abstain | False-yes | Recall | False-no | Coverage | High-confidence wrong | Confound |
|---|---|---:|---:|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| e1d-checks-dense | player_on_pitch | 19/19 | 63.16% | 63.16% | 0.00% | yes | 100.00% | False | 0.00% | 100.00% | 100.00% | 0.00% | 100.00% | 7 | — |
| e1d-checks-dense | play_in_progress | 17/17 | 88.24% | 58.82% | 29.41% | yes | 55.00% | True | 0.00% | 14.29% | 90.00% | 10.00% | 100.00% | 0 | — |
| e1d-checks-dense | ball_near_player | 15/14 | 57.14% | 53.33% | 3.81% | no | 90.00% | False | 6.67% | 0.00% | 14.29% | 85.71% | 93.33% | 0 | — |
| e1d-checks-dense | player_touches_ball | 15/15 | 60.00% | 60.00% | 0.00% | no | 100.00% | False | 0.00% | 0.00% | N/A | 100.00% | 100.00% | 6 | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-dense | player_running | 13/13 | 30.77% | 69.23% | -38.46% | yes | 100.00% | False | 0.00% | 100.00% | 100.00% | 0.00% | 100.00% | 0 | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-dense | kit_color_seen | 20/18 | 94.44% | 94.44% | 0.00% | red | 100.00% | False | 10.00% | N/A | N/A | N/A | 90.00% | 1 | — |
| e1d-checks-prod30 | player_on_pitch | 19/19 | 68.42% | 63.16% | 5.26% | yes | 95.00% | False | 0.00% | 85.71% | 100.00% | 0.00% | 100.00% | 6 | — |
| e1d-checks-prod30 | play_in_progress | 17/17 | 41.18% | 58.82% | -17.65% | no | 85.00% | False | 0.00% | 14.29% | 10.00% | 90.00% | 100.00% | 0 | — |
| e1d-checks-prod30 | ball_near_player | 15/9 | 77.78% | 53.33% | 24.44% | no | 55.00% | True | 40.00% | 0.00% | 0.00% | 28.57% | 60.00% | 0 | — |
| e1d-checks-prod30 | player_touches_ball | 15/15 | 60.00% | 60.00% | 0.00% | no | 100.00% | False | 0.00% | 0.00% | N/A | 100.00% | 100.00% | 6 | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-prod30 | player_running | 13/13 | 46.15% | 69.23% | -23.08% | yes | 90.00% | False | 0.00% | 77.78% | 100.00% | 0.00% | 100.00% | 0 | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-prod30 | kit_color_seen | 20/18 | 83.33% | 94.44% | -11.11% | red | 80.00% | False | 10.00% | N/A | N/A | N/A | 90.00% | 3 | — |

Per-question deltas in percentage points versus dense (same metric denominators as above):

| Run | Question | Accuracy Δ | Abstain Δ | False-yes Δ | Recall Δ | Confound |
|---|---|---:|---:|---:|---:|---|
| e1d-checks-dense | player_on_pitch | +0.00 | +0.00 | +0.00 | +0.00 | — |
| e1d-checks-dense | play_in_progress | +0.00 | +0.00 | +0.00 | +0.00 | — |
| e1d-checks-dense | ball_near_player | +0.00 | +0.00 | +0.00 | +0.00 | — |
| e1d-checks-dense | player_touches_ball | +0.00 | +0.00 | +0.00 | N/A | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-dense | player_running | +0.00 | +0.00 | +0.00 | +0.00 | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-dense | kit_color_seen | +0.00 | +0.00 | N/A | N/A | — |
| e1d-checks-prod30 | player_on_pitch | +5.26 | +0.00 | -14.29 | +0.00 | — |
| e1d-checks-prod30 | play_in_progress | -47.06 | +0.00 | +0.00 | -80.00 | — |
| e1d-checks-prod30 | ball_near_player | +20.63 | +33.33 | +0.00 | -14.29 | — |
| e1d-checks-prod30 | player_touches_ball | +0.00 | +0.00 | +0.00 | N/A | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-prod30 | player_running | +15.38 | +0.00 | -22.22 | +0.00 | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-prod30 | kit_color_seen | -11.11 | +0.00 | N/A | N/A | — |

Touch recall (raw counts retained; null recall is not a detector score):

| Run | Raw affirmative touches | Recall | Sampling confound |
|---|---:|---|---|
| e1d-checks-dense | 0/6 | N/A | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-prod30 | 0/6 | N/A | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |

Six truth-positive touch clips — answers/confidence and measured mean still spacing (single frame has no inter-still interval):

| Clip | dense | prod30 | Confound |
|---|---|---|---|
| m04-n03-t1406-157170-158922 | no/high; 1.58 s | no/high; single/missing frame | Temporal sampling; raw no/unclear is not evidence of inability to detect a visible touch. Reviewed dataset: dense true-touch still spacing is 1.58–6.62 s; run-wide mean spacing is 2.49 s dense and 23.99 s sparse. Review estimate: a perfect detector would score approximately 1/6 dense and 0/6 sparse, making the 2/6 crop scheduling rule 'unattainable by construction' under that assumption. This is not a measured detector bound: spacing alone cannot establish visibility, a perfect-detector score or mathematical impossibility. Human touch timestamps and frame-level visibility labels are still needed. |
| m04-n04-t3006-243433-247994 | no/high; 4.14 s | no/high; 45.51 s | Temporal sampling; raw no/unclear is not evidence of inability to detect a visible touch. Reviewed dataset: dense true-touch still spacing is 1.58–6.62 s; run-wide mean spacing is 2.49 s dense and 23.99 s sparse. Review estimate: a perfect detector would score approximately 1/6 dense and 0/6 sparse, making the 2/6 crop scheduling rule 'unattainable by construction' under that assumption. This is not a measured detector bound: spacing alone cannot establish visibility, a perfect-detector score or mathematical impossibility. Human touch timestamps and frame-level visibility labels are still needed. |
| m04-n12-t1411-237107-242145 | no/high; 4.57 s | no/high; 50.28 s | Temporal sampling; raw no/unclear is not evidence of inability to detect a visible touch. Reviewed dataset: dense true-touch still spacing is 1.58–6.62 s; run-wide mean spacing is 2.49 s dense and 23.99 s sparse. Review estimate: a perfect detector would score approximately 1/6 dense and 0/6 sparse, making the 2/6 crop scheduling rule 'unattainable by construction' under that assumption. This is not a measured detector bound: spacing alone cannot establish visibility, a perfect-detector score or mathematical impossibility. Human touch timestamps and frame-level visibility labels are still needed. |
| m04-n15-t3010-164698-170777 | no/high; 5.52 s | no/high; 30.35 s | Temporal sampling; raw no/unclear is not evidence of inability to detect a visible touch. Reviewed dataset: dense true-touch still spacing is 1.58–6.62 s; run-wide mean spacing is 2.49 s dense and 23.99 s sparse. Review estimate: a perfect detector would score approximately 1/6 dense and 0/6 sparse, making the 2/6 crop scheduling rule 'unattainable by construction' under that assumption. This is not a measured detector bound: spacing alone cannot establish visibility, a perfect-detector score or mathematical impossibility. Human touch timestamps and frame-level visibility labels are still needed. |
| m04-n17-t717-253073-260377 | no/high; 6.62 s | no/high; 36.43 s | Temporal sampling; raw no/unclear is not evidence of inability to detect a visible touch. Reviewed dataset: dense true-touch still spacing is 1.58–6.62 s; run-wide mean spacing is 2.49 s dense and 23.99 s sparse. Review estimate: a perfect detector would score approximately 1/6 dense and 0/6 sparse, making the 2/6 crop scheduling rule 'unattainable by construction' under that assumption. This is not a measured detector bound: spacing alone cannot establish visibility, a perfect-detector score or mathematical impossibility. Human touch timestamps and frame-level visibility labels are still needed. |
| m04-n17-t717-416826-418915 | no/high; 1.88 s | no/high; single/missing frame | Temporal sampling; raw no/unclear is not evidence of inability to detect a visible touch. Reviewed dataset: dense true-touch still spacing is 1.58–6.62 s; run-wide mean spacing is 2.49 s dense and 23.99 s sparse. Review estimate: a perfect detector would score approximately 1/6 dense and 0/6 sparse, making the 2/6 crop scheduling rule 'unattainable by construction' under that assumption. This is not a measured detector bound: spacing alone cannot establish visibility, a perfect-detector score or mathematical impossibility. Human touch timestamps and frame-level visibility labels are still needed. |

Every saved touch answer across the nine runs is no/unclear, but 12 frames spread over a long window leave multi-second gaps while a touch lasts a fraction of a second. The inspected n12 middle crop is clear and contains no nearby ball. Raw 0/6 is not evidence that the model cannot see a touch: these frames rarely contain one, and touch recall is not measurable at this sampling. Wide-frame on-pitch/sideline results retain context; crop on-pitch and ball-near results have a spatial confound. Follow-up: moment windows — at least 8 frames at at least 4 fps in the 2 s around a human-marked touch time; MJ must mark touch times on the six clips. No new inference in r2.

5 truth cells corrected. Pooled false-yes gate numbers unchanged. The headline changes: gate 2 now requires measurable recall as well as low false-yes, so its former false-yes-only PASS is WITHHELD at this sampling. Macro accuracies and per-question metrics changed as listed; raw touch counts remain visible. The requested information heuristic can flag selective-abstention outputs despite zero affirmative touches; it is not a calibrated measure of visual information.


Shared scored clips: 20. Comparison accuracy/error rates use shared IDs scored in every saved report and current rescoring. Modal distributions, majority baselines, touch counts/recall and temporal sampling use each full run, so abstention or another run's failure cannot remove valid answers or touch positives from those denominators. Full-run reports retain every attempt. Frame facts use all raw attempts. Configured wall caps alone do not imply an incomplete run.

Accuracy = correct / graded answered (unclear excluded). Abstain = unclear / eligible; coverage = graded answered / eligible. Binary eligibility requires yes/no truth. Kit eligibility follows lane A: uncertain kit truth forces abstention even for an asserted colour. False-yes = yes / truth-no cells; false-no = no / truth-yes cells, including abstentions in those truth denominators. Kit has no yes/no rates. Macro accuracy averages available accuracies across six questions; macro false-yes averages available rates across five binary questions; overall abstain is pooled over eligible cells. Gate 1 pools player_on_pitch and play_in_progress over off-pitch clips (14 cells on full set); Gate 2 uses player_touches_ball over off-pitch or idle clips with truth no (9 clips; mixed receive excluded). Modal answer/share uses every valid answer, including unclear and ungraded cells; ties sort lexically. Majority baseline uses all selected graded truth classes (uncertain kit excluded), independent of abstention; information requires modal share <90% and accuracy > baseline +5 percentage points. Gate 1 also splits its two questions. Gate 2 requires false-yes <=10% AND measurable touch recall >=50%. Raw recall = yes / all selected truth-positive clips, counting unclear/failed reads as misses. Touch recall is null when mean spacing >1s or sampling metadata is missing; raw counts remain. Accuracy metrics exclude failed reads; attempted/scored/failed counts remain visible. Thinking rate and wall/clip include all attempts. Reasons are logged only, never scored.

| Run | Model | Boxed frames/attempt | Scored/failed | Wall s/clip (all attempts) | Macro accuracy | Macro false-yes | Abstain | From thinking (all attempts) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| e1d-checks-dense | qwen3-vl:8b | 11.9 | 20/0 | 51.651 | 65.62% | 42.86% | 3.03% | 100.00% |
| e1d-checks-prod30 | qwen3-vl:8b | 1.45 | 20/0 | 10.547 | 62.81% | 35.56% | 8.08% | 100.00% |

Thresholds (MJ decides adoption):

| Run | Metric | Threshold | Measured | Result | Confound |
|---|---|---:|---:|---|---|
| e1d-checks-dense | off_pitch_false_yes_rate | <= 10.00% | 57.14% | FAIL | — |
| e1d-checks-dense | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-dense | touch_recall | >= 50.00% | N/A | WITHHELD | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-dense | macro_accuracy | >= 80.00% | 65.62% | FAIL | — |
| e1d-checks-dense | abstain_rate | <= 40.00% | 3.03% | PASS | — |
| e1d-checks-dense | gate2 | touch false-yes <=10% AND measurable touch recall >=50% | N/A | WITHHELD | not measurable at this sampling: mean frame spacing exceeds 1.0 s |
| e1d-checks-prod30 | off_pitch_false_yes_rate | <= 10.00% | 50.00% | FAIL | — |
| e1d-checks-prod30 | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-prod30 | touch_recall | >= 50.00% | N/A | WITHHELD | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-prod30 | macro_accuracy | >= 80.00% | 62.81% | FAIL | — |
| e1d-checks-prod30 | abstain_rate | <= 40.00% | 8.08% | PASS | — |
| e1d-checks-prod30 | gate2 | touch false-yes <=10% AND measurable touch recall >=50% | N/A | WITHHELD | not measurable at this sampling: mean frame spacing exceeds 1.0 s |

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

| Clip | Run | Status | player_on_pitch | play_in_progress | ball_near_player | player_touches_ball (temporal confound) | player_running (temporal confound) | kit_color_seen | Confounds |
|---|---|---|---|---|---|---|---|---|---|
| m04-n02-t3005-474114-478131 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n02-t3005-474114-478131 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n03-t1406-157170-158922 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n03-t1406-157170-158922 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n03-t1406-385962-387137 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n03-t1406-385962-387137 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n04-t3006-243433-247994 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n04-t3006-243433-247994 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | blue / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n04-t3006-307417-310307 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n04-t3006-307417-310307 | e1d-checks-prod30 | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n05-t3007-284945-287898 | e1d-checks-dense | scored | yes / high | yes / high | no / medium | no / low | yes / high | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n05-t3007-284945-287898 | e1d-checks-prod30 | scored | yes / high | yes / high | no / medium | no / low | yes / high | blue / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-143096-143834 | e1d-checks-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-143096-143834 | e1d-checks-prod30 | scored | no / high | yes / medium | no / high | no / high | no / high | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-297601-298865 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-297601-298865 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-385922-386603 | e1d-checks-dense | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-385922-386603 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n10-t711-186553-188161 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n10-t711-186553-188161 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | blue / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n12-t1411-237107-242145 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n12-t1411-237107-242145 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n12-t1411-679986-681985 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n12-t1411-679986-681985 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n15-t3010-164698-170777 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n15-t3010-164698-170777 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-253073-260377 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-253073-260377 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-304624-307834 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-304624-307834 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-416826-418915 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-416826-418915 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n21-t3011-390297-390800 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n21-t3011-390297-390800 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | no / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n22-t3012-070707-074371 | e1d-checks-dense | scored | yes / high | no / medium | yes / high | no / low | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n22-t3012-070707-074371 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n24-t3013-679939-681217 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n24-t3013-679939-681217 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | black / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n25-t3014-530600-532465 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n25-t3014-530600-532465 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |

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

Thinking-channel diagnostic:

- saved / schema: JSON field=message.thinking; content empty=True; validates=True; selected=message.thinking; done_reason=stop; error=none.
- saved / json: JSON field=message.thinking; content empty=True; validates=True; selected=message.thinking; done_reason=stop; error=none.
- saved / none: JSON field=none; content empty=True; validates=False; selected=message.thinking; done_reason=length; error=none.

Model/frame facts from run.json and raw attempts:

- dense: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frames_per_second_of_window": {"mean": 0.7109915728989717, "min": 0.16429353778751377}, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "mean_spacing_s": 2.4899898989899, "model": "qwen3-vl:8b", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- prod30: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frames_per_second_of_window": {"mean": 0.0701758236166358, "min": 0.033863867253640136}, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "mean_spacing_s": 23.98825000000001, "model": "qwen3-vl:8b", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}

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
- Every saved touch answer across the nine runs is no/unclear, but 12 frames spread over a long window leave multi-second gaps while a touch lasts a fraction of a second. The inspected n12 middle crop is clear and contains no nearby ball. Raw 0/6 is not evidence that the model cannot see a touch: these frames rarely contain one, and touch recall is not measurable at this sampling. Wide-frame on-pitch/sideline results retain context; crop on-pitch and ball-near results have a spatial confound. Follow-up: moment windows — at least 8 frames at at least 4 fps in the 2 s around a human-marked touch time; MJ must mark touch times on the six clips. No new inference in r2.
- Confidence is uncalibrated and prompt-sensitive: on both pilot clips, touch no/low changed to no/high after the reason instruction changed. Modal share and baseline comparisons expose near-constant priors; low touch false-yes alone is not sensitivity.

Temporal sampling (distinct timestamps; context pairs counted once):

| Run | FPS mean | FPS min | Mean spacing s | Touch recall reason |
|---|---:|---:|---:|---|
| e1d-checks-dense | 0.7109915728989717 | 0.16429353778751377 | 2.4899898989899 | not measurable at this sampling: mean frame spacing exceeds 1.0 s |
| e1d-checks-prod30 | 0.0701758236166358 | 0.033863867253640136 | 23.98825000000001 | not measurable at this sampling: mean frame spacing exceeds 1.0 s |

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
  "dense": {
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
  "prod30": {
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
  }
}
```

Execution/gates:

```json
{
  "round": "r3; code/ledger only; no new inference",
  "base_commit": "b96e6b2",
  "historical_execution": {
    "state": "complete; final evidence for the lane B local commit",
    "base_commit": "0ffcfb5a756c72b3c3bfd838ad1e8d2de8d9f6e7",
    "branch": "feat/bench-lane-b-checks",
    "host": "basecamp: 100.82.160.117, 128 GiB; hostname MJs-MacBook-Pro.local",
    "environment": {
      "python": "3.11.16",
      "pydantic": "2.13.4",
      "opencv": "4.13.0",
      "ollama": "0.33.2"
    },
    "model_digest": "901cae73216286ea8c5aba8b46d307ff7188f737285ec500c795a12f05225d28",
    "model_quantization": "Q4_K_M",
    "gpu_exclusivity": "Before each benchmark launch and diagnostic, pgrep -f run_bench|qwen_match_analysis showed only the task launcher (PID 79163); no competing benchmark process. No GPU gate file required by MJ.",
    "smoke": {
      "original_run": "e1d-checks-smoke",
      "scored": 1,
      "failed": 0,
      "wall_s": 35.301,
      "reason": "Original prompt omitted optional reasons; revised prompt requests short reasons without changing the optional schema or scoring."
    },
    "final_prompt_smoke": {
      "run": "e1d-checks-smoke-reasons",
      "clip_id": "m04-n12-t1411-237107-242145",
      "scored": 1,
      "failed": 0,
      "wall_s": 5.486,
      "reasons": 6,
      "from_thinking": true
    },
    "excluded_pilot": {
      "run": "e1d-checks-dense-prompt-pilot",
      "saved_claims": 1,
      "interruption": "Only own runner PID 81855 interrupted during second-clip extraction; first claim preserved externally. Excluded from final comparison. No other process stopped."
    },
    "sampling_passes": "One full pass per final policy; smoke and partial prompt pilot are separate and excluded. Warm model/image cache may affect latency, especially the first dense clip.",
    "validation": {
      "pytest_command": "BENCH_REQUIRE_CV2=1 ~/Projects/loanarmy/.loan/bin/python -m pytest spike/video-analysis/bench -q",
      "pytest": "307 passed in 0.92s",
      "ruff_check": "PASS: ruff check spike/video-analysis/bench",
      "ruff_format": "PASS: ruff format --check spike/video-analysis/bench (29 files)",
      "git_diff_check": "PASS",
      "live_comparison": "Deterministic repeat over saved outputs; complete 20 shared scored IDs; both launch and rescoring truth/note hashes match.",
      "scope": "Only bench code/docs/explicit note fixtures/tests and the requested lane-B ledger pair changed; no frozen/report paths or unrelated files staged."
    },
    "positive_touch_caveat": "Both final runs answer no on all six truth-positive touch clips; all six errors per run have high confidence. Passing the 0/9 false-yes touch gate does not establish touch sensitivity.",
    "diagnostic_caveat": "Schema and json returned valid JSON via thinking with empty content. No format returned prose via thinking and hit the 400-token cap; no JSON validated. Three calls on one clip do not establish grammar enforcement generally.",
    "not_done": [
      "No adoption decision (MJ owns it).",
      "No production honesty-gate integration (bench-only scope).",
      "No push; no frozen/report files or CONTINUITY/AGENTS/FEATURES edits staged."
    ]
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
    "experiment": "E1d lane B \u2014 yes/no checks under the honesty gate",
    "thinking_channel_diagnostic": {
      "clip_id": "m04-n12-t1411-237107-242145",
      "model": "qwen3-vl:8b",
      "ollama_url": "http://127.0.0.1:11434",
      "contract_version": "film-room-checks-v1",
      "prompt_version": "film-room-checks-prompt-v1-reasons",
      "truth_set_sha256_after_notes": "b0701190324ab2527d400b2b176da67291a5efffc11fd314068b343e9f74e8ed",
      "human_notes_sha256": "5944679d0b576bfd8790d9d1206def9485f7618b0c6d53d4c7593c266d51d59f",
      "think": false,
      "num_ctx": 65536,
      "num_predict": 400,
      "prompt_sha256": "287d8f0a39d23969fa5b2fb1423ebb02d913ad16cf676fc8faf77f81fb8b670b",
      "sent_frames": [
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-sjj8ptcg/frame-00.jpg",
          "t": 2371.12,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2371.12,
          "sampling_shift_s": 0.0,
          "sha256": "f20ef87f0d917e203f2b5c807a8f133c6d57eb7d35f9e5818d1656af1a6e3091"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-sjj8ptcg/frame-01.jpg",
          "t": 2375.691,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2375.691,
          "sampling_shift_s": 0.0,
          "sha256": "98a1da458e1175777b79536d238643bcce868d593bbb92683c3971af18957245"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-sjj8ptcg/frame-02.jpg",
          "t": 2380.262,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2380.262,
          "sampling_shift_s": 0.0,
          "sha256": "e19fdb7d839de9e9ae89b223cd61fef1f82deb6ee9f113b08f2f58996c11adc9"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-sjj8ptcg/frame-03.jpg",
          "t": 2384.833,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2384.833,
          "sampling_shift_s": 0.0,
          "sha256": "4ab2524c9e96e49c307a0e3fb980973dd0817a2324262eda4fb6cfa9631a4e45"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-sjj8ptcg/frame-04.jpg",
          "t": 2389.404,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2389.404,
          "sampling_shift_s": 0.0,
          "sha256": "bfe74bd2998dfb232fa913c2483ed02af0a69461c1c254bbc8f8a19572d26041"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-sjj8ptcg/frame-05.jpg",
          "t": 2393.975,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2393.975,
          "sampling_shift_s": 0.0,
          "sha256": "e8080e71d4040c287a3495026a46fe90c97a4a0104803df0ebd186884a0730b2"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-sjj8ptcg/frame-06.jpg",
          "t": 2398.545,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2398.545,
          "sampling_shift_s": 0.0,
          "sha256": "9295c6361175368f80814da708c7f7767f3e9b193eeaad2e0a39c79f67a04362"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-sjj8ptcg/frame-07.jpg",
          "t": 2403.6,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2403.116,
          "sampling_shift_s": 0.484,
          "sha256": "3a2c2e7c2a3e376b732c5c4fb2843d33c382b5303f20852ec0e72c3ef6e0e268"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-sjj8ptcg/frame-08.jpg",
          "t": 2407.687,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2407.687,
          "sampling_shift_s": 0.0,
          "sha256": "fd839f08c1717586566e226d563ea4ae5a7f3d93bc563f582988a1e827d2ea5b"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-sjj8ptcg/frame-09.jpg",
          "t": 2412.258,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2412.258,
          "sampling_shift_s": 0.0,
          "sha256": "437f6cf74ef3c834bc11ca3a4d8bd840b02d9c5781458a1f449f7e6602c2423f"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-sjj8ptcg/frame-10.jpg",
          "t": 2416.829,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2416.829,
          "sampling_shift_s": 0.0,
          "sha256": "fe12f40b2d73c7609981a7586b91243dc43d6a7b149c8da150731fd87b20fc8c"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-sjj8ptcg/frame-11.jpg",
          "t": 2421.4,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2421.4,
          "sampling_shift_s": 0.0,
          "sha256": "e7f65f8d516e6c5d2bb6f1e9a4e234216f2904aed4a555e239399757c3b86917"
        }
      ],
      "anchored_frames": [
        {
          "t": 2371.12,
          "box": [
            936.1904761904767,
            241.14285714285654,
            952.285714285713,
            291.3333333333333
          ],
          "box_source_space": [
            1404.2857142857151,
            361.7142857142848,
            1428.4285714285695,
            437.0
          ],
          "sent_w": 1280,
          "sent_h": 720
        },
        {
          "t": 2375.691,
          "box": [
            845.3999999999833,
            241.206666666665,
            865.3999999999833,
            289.07999999999663
          ],
          "box_source_space": [
            1268.099999999975,
            361.8099999999975,
            1298.099999999975,
            433.619999999995
          ],
          "sent_w": 1280,
          "sent_h": 720
        },
        {
          "t": 2380.262,
          "box": [
            613.8799999999608,
            267.62666666667076,
            634.9066666666419,
            324.73333333334364
          ],
          "box_source_space": [
            920.8199999999413,
            401.4400000000062,
            952.3599999999628,
            487.1000000000155
          ],
          "sent_w": 1280,
          "sent_h": 720
        },
        {
          "t": 2384.833,
          "box": [
            24.666666666666664,
            359.3333333333333,
            66.70000000000681,
            447.8555555555563
          ],
          "box_source_space": [
            37.0,
            539.0,
            100.05000000001023,
            671.7833333333344
          ],
          "sent_w": 1280,
          "sent_h": 720
        },
        {
          "t": 2389.404,
          "box": [
            24.511111111109592,
            358.86666666666207,
            59.46666666669395,
            444.66666666666663
          ],
          "box_source_space": [
            36.76666666666439,
            538.2999999999931,
            89.20000000004093,
            667.0
          ],
          "sent_w": 1280,
          "sent_h": 720
        },
        {
          "t": 2393.975,
          "box": [
            184.90000000000228,
            346.66666666666663,
            213.20000000000303,
            418.66666666666663
          ],
          "box_source_space": [
            277.35000000000343,
            520.0,
            319.80000000000456,
            628.0
          ],
          "sent_w": 1280,
          "sent_h": 720
        },
        {
          "t": 2398.545,
          "box": [
            308.66666666666663,
            248.33333333333587,
            331.6666666666692,
            297.50000000000375
          ],
          "box_source_space": [
            463.0,
            372.5000000000038,
            497.5000000000038,
            446.2500000000057
          ],
          "sent_w": 1280,
          "sent_h": 720
        },
        {
          "t": 2403.6,
          "box": [
            669.3333333333333,
            326.66666666666663,
            697.3333333333333,
            398.0
          ],
          "box_source_space": [
            1004.0,
            490.0,
            1046.0,
            597.0
          ],
          "sent_w": 1280,
          "sent_h": 720
        },
        {
          "t": 2407.687,
          "box": [
            1040.6666666666665,
            333.72916666667,
            1068.3708333333352,
            397.4083333333373
          ],
          "box_source_space": [
            1561.0,
            500.593750000005,
            1602.556250000003,
            596.112500000006
          ],
          "sent_w": 1280,
          "sent_h": 720
        },
        {
          "t": 2412.258,
          "box": [
            827.2933333333374,
            321.76000000000045,
            847.7200000000046,
            374.0
          ],
          "box_source_space": [
            1240.9400000000062,
            482.6400000000007,
            1271.580000000007,
            561.0
          ],
          "sent_w": 1280,
          "sent_h": 720
        },
        {
          "t": 2416.829,
          "box": [
            772.971428571425,
            320.66666666666663,
            793.3333333333333,
            367.51428571428744
          ],
          "box_source_space": [
            1159.4571428571376,
            481.0,
            1190.0,
            551.2714285714312
          ],
          "sent_w": 1280,
          "sent_h": 720
        },
        {
          "t": 2421.4,
          "box": [
            989.5555555556061,
            308.1111111111136,
            1020.0000000000455,
            365.1111111111061
          ],
          "box_source_space": [
            1484.3333333334092,
            462.16666666667044,
            1530.0000000000682,
            547.6666666666591
          ],
          "sent_w": 1280,
          "sent_h": 720
        }
      ],
      "calls": [
        {
          "format_mode": "schema",
          "wall_s": 50.326,
          "json_field": "message.thinking",
          "json_fields": [
            "message.thinking"
          ],
          "content_empty": true,
          "content_missing": false,
          "validated": true,
          "validation_by_field": {
            "content": false,
            "thinking": true
          },
          "selected_field": "message.thinking",
          "message": {
            "role": "assistant",
            "content": "",
            "thinking": "{\"player_on_pitch\": {\"answer\": \"yes\", \"confidence\": \"high\", \"reason\": \"Visible on field in all frames\"}, \"play_in_progress\": {\"answer\": \"yes\", \"confidence\": \"medium\", \"reason\": \"Players moving actively\"}, \"ball_near_player\": {\"answer\": \"no\", \"confidence\": \"low\", \"reason\": \"Ball not visible near player\"}, \"player_touches_ball\": {\"answer\": \"no\", \"confidence\": \"high\", \"reason\": \"No ball contact shown\"}, \"player_running\": {\"answer\": \"yes\", \"confidence\": \"medium\", \"reason\": \"Player moving quickly in frames\"}, \"kit_color_seen\": {\"answer\": \"red\", \"confidence\": \"high\", \"reason\": \"Red jersey visible consistently\"}}"
          },
          "done_reason": "stop",
          "error": null
        },
        {
          "format_mode": "json",
          "wall_s": 6.458,
          "json_field": "message.thinking",
          "json_fields": [
            "message.thinking"
          ],
          "content_empty": true,
          "content_missing": false,
          "validated": true,
          "validation_by_field": {
            "content": false,
            "thinking": true
          },
          "selected_field": "message.thinking",
          "message": {
            "role": "assistant",
            "content": "",
            "thinking": "{\"player_on_pitch\": {\"answer\": \"yes\", \"confidence\": \"high\", \"reason\": \"Visible on field in all frames\"}, \"play_in_progress\": {\"answer\": \"yes\", \"confidence\": \"medium\", \"reason\": \"Players moving actively\"}, \"ball_near_player\": {\"answer\": \"no\", \"confidence\": \"low\", \"reason\": \"Ball not visible near player\"}, \"player_touches_ball\": {\"answer\": \"no\", \"confidence\": \"high\", \"reason\": \"No ball contact shown\"}, \"player_running\": {\"answer\": \"yes\", \"confidence\": \"medium\", \"reason\": \"Player moving quickly in frames\"}, \"kit_color_seen\": {\"answer\": \"red\", \"confidence\": \"high\", \"reason\": \"Red jersey visible consistently\"}}"
          },
          "done_reason": "stop",
          "error": null
        },
        {
          "format_mode": "none",
          "wall_s": 15.403,
          "json_field": "none",
          "json_fields": [],
          "content_empty": true,
          "content_missing": false,
          "validated": false,
          "validation_by_field": {
            "content": false,
            "thinking": false
          },
          "selected_field": "message.thinking",
          "message": {
            "role": "assistant",
            "content": "",
            "thinking": "<think>\nGot it, let's tackle each question one by one based on the provided frames.\n\nFirst, player_on_pitch: We need to check if the marked player is on the field of play (not sideline, bench, warm-up). Looking at all frames, the magenta box (#12) is consistently on the main playing area. So yes.\n\nplay_in_progress: Is the ball in play? In some frames, we can see the ball moving. For example, frame 4 shows a player with the ball, and others have the ball visible. Since there's movement of the ball (not warm-up or stoppages), it should be yes.\n\nball_near_player: Does the ball come within two body-lengths? Let's check each frame. In some frames like frame 7, the ball is near the player. But we need to see if at any point it's close. Since in multiple frames (like frame 4, 5) the ball is nearby, so yes.\n\nplayer_touches_ball: Does the marked player play the ball? Looking for clear actions\u2014pass, shot, header, control. In frame 7, there's a player with the ball near #12, but does #12 touch it? Wait, need to check if in any frame the marked player is interacting with the ball. Let's see: frame 4 has the ball near them, maybe they're controlling it. But do we have clear evidence? The problem says \"clearly play the ball\". If there's a moment where the ball is near and they touch it, but since it's still frames, maybe not. Wait, in some frames like frame 7, the player might be touching the ball. Let me check again. Hmm, maybe unclear because we can't see the exact action between frames.\n\nplayer_running: Does the marked player run? Looking at the frames, in several frames (like frame 4, 5) they are moving quickly"
          },
          "done_reason": "length",
          "error": null
        }
      ],
      "scope": "Three single requests, identical dense frames and prompt, only format varies. Raw message fields retained. No repairs, retries or shared-transport changes."
    },
    "known_truth_error": "Five explicit rule-derived cells corrected in r2. MJ source notes remain unchanged; no additional specific correction received."
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
    "dense": {
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
    "prod30": {
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
    }
  },
  "regeneration": {
    "runs": {
      "dense": "e1d-checks-dense",
      "prod30": "e1d-checks-prod30"
    },
    "allow_mixed": false,
    "output_stem": "evidence-bench-2026-09-10-lane-b",
    "baseline_run": "dense"
  },
  "not_done": "No new inference or moment-window bench. MJ touch times and sampled-frame visibility labels are needed; the review perfect-detector estimate/unattainable wording is not a measured bound. No adoption decision or push.",
  "round_base_commit": "60d5772",
  "r2_verification": "Before changes, all three JSON/MD pairs regenerated byte-for-byte from committed r2 comparator and execution inputs. Existing null recall and FPS metrics retained.",
  "positive_touch_caveat": "Temporal confound: dense true-touch mean still spacing is 1.58, 4.14, 4.57, 5.52, 6.62 and 1.88 s; run-wide mean spacing is 2.49 s dense and 23.99 s sparse. Raw 0/6 is not a detector score. Review estimate of perfect-detector 1/6 dense or 0/6 sparse, and 2/6 being unattainable by construction, is an assumption rather than a bound proved by these stills. Running rows share the temporal confound; crop sideline and ball-near rows also have spatial confounds.",
  "exact_regeneration_command": "/Users/mjjones/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/compare_checks.py --reports-root /Users/mjjones/Projects/loanarmy-bench-reports --manifest /Users/mjjones/Projects/loanarmy-bench-frozen/manifest.json --execution spike/video-analysis/bench/fixtures/lane-b-execution.json --runs dense=e1d-checks-dense prod30=e1d-checks-prod30 --touch-clips --baseline-run dense --out-json ledgers/research/evidence-bench-2026-09-10-lane-b.json --out-md ledgers/research/evidence-bench-2026-09-10-lane-b.md",
  "regeneration_cwd": "/Users/mjjones/Projects/loanarmy/.worktrees/lane-b",
  "validation_r2": {
    "status": "passed",
    "pytest": "333 passed in 1.19s; BENCH_REQUIRE_CV2=1 /Users/mjjones/Projects/loanarmy/.loan/bin/python -m pytest spike/video-analysis/bench -q",
    "ruff_check": "PASS; ruff check spike/video-analysis/bench",
    "ruff_format": "PASS, 33 files; ruff format --check spike/video-analysis/bench",
    "diff_check": "PASS; git diff --check",
    "regeneration": "All three JSON/Markdown ledger pairs regenerated twice with byte-for-byte equality using regenerate_checks_ledgers.py and these committed execution fixtures.",
    "preserved": "All nine run.json settings and 180 reads equal b96e6b2 ledger; frozen truth bytes and human note hashes unchanged; contract, prompts, transport, image adapters, runner and lane-A scorer unchanged.",
    "no_inference": true
  },
  "validation": {
    "status": "PASS",
    "worktree_pytest": "BENCH_REQUIRE_CV2=1; 336 passed in 1.35s with isolated Pillow 11.3.0; installed Pillow 12.3.0 also passed 336 tests (six getdata deprecation warnings).",
    "archive_pytest": "BENCH_REQUIRE_CV2=1; 336 passed in 1.52s with Pillow 11.3.0; installed Pillow 12.3.0 also passed 336 tests in the earlier export. No .git directory.",
    "python": "/Users/mjjones/Projects/loanarmy/.loan/bin/python, CPython 3.11.16",
    "pillow_compatibility": "Pillow 11.3.0 installed with uv pip --no-deps --target in an isolated temporary directory and selected with PYTHONPATH; .loan unchanged.",
    "export": {
      "tree": "a78a23a12e4c51418d63c613b633dd46d68a8d4c",
      "directory": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/lane-bc-r3-export-gt8g4lea/tree-final",
      "archive": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/lane-bc-r3-export-gt8g4lea/source-final.tar"
    },
    "export_note": "Git archive of staged tree before final validation records were stamped; all Python sources byte-identical to tested export. Export uses no Git checkout.",
    "pytest_command": "BENCH_REQUIRE_CV2=1 /Users/mjjones/Projects/loanarmy/.loan/bin/python -m pytest spike/video-analysis/bench -q",
    "ruff_check": "PASS; ruff check spike/video-analysis/bench",
    "ruff_format": "PASS, 35 files; ruff format --check spike/video-analysis/bench",
    "diff_check": "PASS; git diff --check",
    "regeneration": "All three ledger pairs regenerate byte-for-byte using each exact_regeneration_command below; six files, zero diff. R2 inputs were independently verified byte-identical before changing code.",
    "unchanged": "All nine numeric report overalls identical to r2; checks_score.py, truth rules, contract, prompts, image adapters, transport and runner unchanged. No model calls."
  }
}
```
