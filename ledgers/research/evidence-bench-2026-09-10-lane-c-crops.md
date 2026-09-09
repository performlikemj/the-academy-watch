On 20 shared scored clips: e1e-cropctx-8b-dense (qwen3-vl:8b, 23.8 boxed frames/attempt): off-pitch false-yes 50.00%, off-pitch/idle touch false-yes 0.00%; e1d-checks-dense (qwen3-vl:8b, 11.9 boxed frames/attempt): off-pitch false-yes 57.14%, off-pitch/idle touch false-yes 0.00%; e1d-checks-32b-dense (qwen3-vl:32b, 11.9 boxed frames/attempt): off-pitch false-yes 50.00%, off-pitch/idle touch false-yes 0.00%; e1d-checks-27b-dense (qwen3.8:27b-obliterated-q8, 11.9 boxed frames/attempt): off-pitch false-yes 64.29%, off-pitch/idle touch false-yes 0.00%; e1e-crop-8b-dense (qwen3-vl:8b, 11.9 boxed frames/attempt): off-pitch false-yes 50.00%, off-pitch/idle touch false-yes 0.00%; e1d-checks-prod30 (qwen3-vl:8b, 1.45 boxed frames/attempt): off-pitch false-yes 50.00%, off-pitch/idle touch false-yes 0.00%; e1d-checks-32b-prod30 (qwen3-vl:32b, 1.45 boxed frames/attempt): off-pitch false-yes 71.43%, off-pitch/idle touch false-yes 0.00%; e1d-checks-27b-prod30 (qwen3.8:27b-obliterated-q8, 1.45 boxed frames/attempt): off-pitch false-yes 78.57%, off-pitch/idle touch false-yes 0.00%; e1e-crop-8b-prod30 (qwen3-vl:8b, 1.45 boxed frames/attempt): off-pitch false-yes 50.00%, off-pitch/idle touch false-yes 0.00%. Adoption belongs to MJ.

Gate numbers (false-yes count / truth-no cells):

| Run | Off-pitch on-pitch/in-progress | Off-pitch + idle touch |
|---|---:|---:|
| e1d-checks-dense | 8/14 (57.14%) | 0/9 (0.00%) |
| e1d-checks-prod30 | 7/14 (50.00%) | 0/9 (0.00%) |
| e1d-checks-32b-dense | 7/14 (50.00%) | 0/9 (0.00%) |
| e1d-checks-32b-prod30 | 10/14 (71.43%) | 0/9 (0.00%) |
| e1d-checks-27b-dense | 9/14 (64.29%) | 0/9 (0.00%) |
| e1d-checks-27b-prod30 | 11/14 (78.57%) | 0/9 (0.00%) |
| e1e-crop-8b-dense | 7/14 (50.00%) | 0/9 (0.00%) |
| e1e-crop-8b-prod30 | 7/14 (50.00%) | 0/9 (0.00%) |
| e1e-cropctx-8b-dense | 7/14 (50.00%) | 0/9 (0.00%) |

Touch recall — yes / all six truth-positive clips (no, unclear and failures are misses):

| Run | Touch recall |
|---|---:|
| e1d-checks-dense | 0/6 (0.00%) |
| e1d-checks-prod30 | 0/6 (0.00%) |
| e1d-checks-32b-dense | 0/6 (0.00%) |
| e1d-checks-32b-prod30 | 0/6 (0.00%) |
| e1d-checks-27b-dense | 0/6 (0.00%) |
| e1d-checks-27b-prod30 | 0/6 (0.00%) |
| e1e-crop-8b-dense | 0/6 (0.00%) |
| e1e-crop-8b-prod30 | 0/6 (0.00%) |
| e1e-cropctx-8b-dense | 0/6 (0.00%) |

32B crop run: NO — requires at least 2/6 in any 8B variant; observed e1e-crop-8b-dense: 0/6, e1e-crop-8b-prod30: 0/6, e1e-cropctx-8b-dense: 0/6.

Shared scored clips: 20. All comparison rates use shared IDs scored in every saved report and current rescoring. Full-run reports retain every attempt. Frame facts use all raw attempts. Configured wall caps alone do not imply an incomplete run.

Accuracy = correct / graded answered (unclear excluded). Abstain = unclear / eligible; coverage = graded answered / eligible. Binary eligibility requires yes/no truth. Kit eligibility follows lane A: uncertain kit truth forces abstention even for an asserted colour. False-yes = yes / truth-no cells; false-no = no / truth-yes cells, including abstentions in those truth denominators. Kit has no yes/no rates. Macro accuracy averages available accuracies across six questions; macro false-yes averages available rates across five binary questions; overall abstain is pooled over eligible cells. Gate 1 pools player_on_pitch and play_in_progress over off-pitch clips (14 cells on full set); Gate 2 uses player_touches_ball over off-pitch or idle clips with truth no (9 clips; mixed receive excluded). All metrics exclude failed reads; attempted/scored/failed counts remain visible. Thinking rate and wall/clip include all attempts. Reasons are logged only, never scored.

Mixed settings explicitly allowed: {"27b_dense": {"model": "qwen3.8:27b-obliterated-q8"}, "27b_prod30": {"model": "qwen3.8:27b-obliterated-q8"}, "32b_dense": {"model": "qwen3-vl:32b"}, "32b_prod30": {"model": "qwen3-vl:32b"}, "crop8_dense": {"adapter": "qwen3vl_checks_crop"}, "crop8_prod30": {"adapter": "qwen3vl_checks_crop"}, "cropctx8_dense": {"adapter": "qwen3vl_checks_crop"}}; scoring uses supplied truth.

| Run | Model | Boxed frames/attempt | Scored/failed | Wall s/clip (all attempts) | Macro accuracy | Macro false-yes | Abstain | From thinking (all attempts) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| e1d-checks-dense | qwen3-vl:8b | 11.9 | 20/0 | 51.651 | 66.71% | 44.72% | 2.91% | 100.00% |
| e1d-checks-prod30 | qwen3-vl:8b | 1.45 | 20/0 | 10.547 | 65.96% | 37.70% | 7.77% | 100.00% |
| e1d-checks-32b-dense | qwen3-vl:32b | 11.9 | 20/0 | 216.428 | 70.55% | 37.70% | 6.80% | 100.00% |
| e1d-checks-32b-prod30 | qwen3-vl:32b | 1.45 | 20/0 | 39.580 | 71.49% | 36.67% | 12.62% | 100.00% |
| e1d-checks-27b-dense | qwen3.8:27b-obliterated-q8 | 11.9 | 20/0 | 172.788 | 70.30% | 38.25% | 3.88% | 0.00% |
| e1d-checks-27b-prod30 | qwen3.8:27b-obliterated-q8 | 1.45 | 20/0 | 87.783 | 71.69% | 39.17% | 16.50% | 0.00% |
| e1e-crop-8b-dense | qwen3-vl:8b | 11.9 | 20/0 | 53.431 | 64.90% | 35.56% | 1.94% | 100.00% |
| e1e-crop-8b-prod30 | qwen3-vl:8b | 1.45 | 20/0 | 11.068 | 67.09% | 32.98% | 5.83% | 100.00% |
| e1e-cropctx-8b-dense | qwen3-vl:8b | 23.8 | 20/0 | 122.840 | 66.43% | 37.78% | 2.91% | 100.00% |

Per-question comparison:

| Run | Question | Eligible/answered | Accuracy | Abstain | False-yes | False-no | Coverage | High-confidence wrong |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| e1d-checks-dense | player_on_pitch | 19/19 | 63.16% | 0.00% | 100.00% | 0.00% | 100.00% | 7 |
| e1d-checks-dense | play_in_progress | 18/18 | 88.89% | 0.00% | 12.50% | 10.00% | 100.00% | 0 |
| e1d-checks-dense | ball_near_player | 15/14 | 50.00% | 6.67% | 11.11% | 100.00% | 93.33% | 1 |
| e1d-checks-dense | player_touches_ball | 15/15 | 60.00% | 0.00% | 0.00% | 100.00% | 100.00% | 6 |
| e1d-checks-dense | player_running | 16/16 | 43.75% | 0.00% | 100.00% | 0.00% | 100.00% | 0 |
| e1d-checks-dense | kit_color_seen | 20/18 | 94.44% | 10.00% | N/A | N/A | 90.00% | 1 |
| e1d-checks-prod30 | player_on_pitch | 19/19 | 68.42% | 0.00% | 85.71% | 0.00% | 100.00% | 6 |
| e1d-checks-prod30 | play_in_progress | 18/18 | 38.89% | 0.00% | 25.00% | 90.00% | 100.00% | 0 |
| e1d-checks-prod30 | ball_near_player | 15/9 | 88.89% | 40.00% | 0.00% | 16.67% | 60.00% | 0 |
| e1d-checks-prod30 | player_touches_ball | 15/15 | 60.00% | 0.00% | 0.00% | 100.00% | 100.00% | 6 |
| e1d-checks-prod30 | player_running | 16/16 | 56.25% | 0.00% | 77.78% | 0.00% | 100.00% | 0 |
| e1d-checks-prod30 | kit_color_seen | 20/18 | 83.33% | 10.00% | N/A | N/A | 90.00% | 3 |
| e1d-checks-32b-dense | player_on_pitch | 19/19 | 68.42% | 0.00% | 85.71% | 0.00% | 100.00% | 6 |
| e1d-checks-32b-dense | play_in_progress | 18/13 | 84.62% | 27.78% | 25.00% | 0.00% | 72.22% | 1 |
| e1d-checks-32b-dense | ball_near_player | 15/15 | 53.33% | 0.00% | 11.11% | 100.00% | 100.00% | 7 |
| e1d-checks-32b-dense | player_touches_ball | 15/15 | 60.00% | 0.00% | 0.00% | 100.00% | 100.00% | 6 |
| e1d-checks-32b-dense | player_running | 16/16 | 62.50% | 0.00% | 66.67% | 0.00% | 100.00% | 0 |
| e1d-checks-32b-dense | kit_color_seen | 20/18 | 94.44% | 10.00% | N/A | N/A | 90.00% | 1 |
| e1d-checks-32b-prod30 | player_on_pitch | 19/19 | 63.16% | 0.00% | 100.00% | 0.00% | 100.00% | 7 |
| e1d-checks-32b-prod30 | play_in_progress | 18/13 | 61.54% | 27.78% | 50.00% | 10.00% | 72.22% | 1 |
| e1d-checks-32b-prod30 | ball_near_player | 15/13 | 69.23% | 13.33% | 0.00% | 66.67% | 86.67% | 1 |
| e1d-checks-32b-prod30 | player_touches_ball | 15/15 | 60.00% | 0.00% | 0.00% | 100.00% | 100.00% | 5 |
| e1d-checks-32b-prod30 | player_running | 16/12 | 75.00% | 25.00% | 33.33% | 0.00% | 75.00% | 1 |
| e1d-checks-32b-prod30 | kit_color_seen | 20/18 | 100.00% | 10.00% | N/A | N/A | 90.00% | 0 |
| e1d-checks-27b-dense | player_on_pitch | 19/19 | 68.42% | 0.00% | 85.71% | 0.00% | 100.00% | 6 |
| e1d-checks-27b-dense | play_in_progress | 18/18 | 77.78% | 0.00% | 50.00% | 0.00% | 100.00% | 4 |
| e1d-checks-27b-dense | ball_near_player | 15/13 | 46.15% | 13.33% | 11.11% | 100.00% | 86.67% | 1 |
| e1d-checks-27b-dense | player_touches_ball | 15/15 | 60.00% | 0.00% | 0.00% | 100.00% | 100.00% | 2 |
| e1d-checks-27b-dense | player_running | 16/16 | 75.00% | 0.00% | 44.44% | 0.00% | 100.00% | 0 |
| e1d-checks-27b-dense | kit_color_seen | 20/18 | 94.44% | 10.00% | N/A | N/A | 90.00% | 1 |
| e1d-checks-27b-prod30 | player_on_pitch | 19/19 | 63.16% | 0.00% | 100.00% | 0.00% | 100.00% | 7 |
| e1d-checks-27b-prod30 | play_in_progress | 18/16 | 68.75% | 11.11% | 62.50% | 0.00% | 88.89% | 5 |
| e1d-checks-27b-prod30 | ball_near_player | 15/15 | 60.00% | 0.00% | 0.00% | 100.00% | 100.00% | 1 |
| e1d-checks-27b-prod30 | player_touches_ball | 15/7 | 85.71% | 53.33% | 0.00% | 16.67% | 46.67% | 0 |
| e1d-checks-27b-prod30 | player_running | 16/11 | 63.64% | 31.25% | 33.33% | 14.29% | 68.75% | 1 |
| e1d-checks-27b-prod30 | kit_color_seen | 20/18 | 88.89% | 10.00% | N/A | N/A | 90.00% | 2 |
| e1e-crop-8b-dense | player_on_pitch | 19/19 | 63.16% | 0.00% | 100.00% | 0.00% | 100.00% | 7 |
| e1e-crop-8b-dense | play_in_progress | 18/18 | 55.56% | 0.00% | 0.00% | 80.00% | 100.00% | 0 |
| e1e-crop-8b-dense | ball_near_player | 15/15 | 60.00% | 0.00% | 0.00% | 100.00% | 100.00% | 0 |
| e1e-crop-8b-dense | player_touches_ball | 15/15 | 60.00% | 0.00% | 0.00% | 100.00% | 100.00% | 6 |
| e1e-crop-8b-dense | player_running | 16/16 | 56.25% | 0.00% | 77.78% | 0.00% | 100.00% | 0 |
| e1e-crop-8b-dense | kit_color_seen | 20/18 | 94.44% | 10.00% | N/A | N/A | 90.00% | 1 |
| e1e-crop-8b-prod30 | player_on_pitch | 19/19 | 68.42% | 0.00% | 85.71% | 0.00% | 100.00% | 6 |
| e1e-crop-8b-prod30 | play_in_progress | 18/18 | 38.89% | 0.00% | 12.50% | 100.00% | 100.00% | 0 |
| e1e-crop-8b-prod30 | ball_near_player | 15/11 | 72.73% | 26.67% | 0.00% | 50.00% | 73.33% | 1 |
| e1e-crop-8b-prod30 | player_touches_ball | 15/15 | 60.00% | 0.00% | 0.00% | 100.00% | 100.00% | 6 |
| e1e-crop-8b-prod30 | player_running | 16/16 | 62.50% | 0.00% | 66.67% | 0.00% | 100.00% | 0 |
| e1e-crop-8b-prod30 | kit_color_seen | 20/18 | 100.00% | 10.00% | N/A | N/A | 90.00% | 0 |
| e1e-cropctx-8b-dense | player_on_pitch | 19/19 | 63.16% | 0.00% | 100.00% | 0.00% | 100.00% | 7 |
| e1e-cropctx-8b-dense | play_in_progress | 18/18 | 66.67% | 0.00% | 0.00% | 60.00% | 100.00% | 0 |
| e1e-cropctx-8b-dense | ball_near_player | 15/14 | 64.29% | 6.67% | 0.00% | 83.33% | 93.33% | 0 |
| e1e-cropctx-8b-dense | player_touches_ball | 15/15 | 60.00% | 0.00% | 0.00% | 100.00% | 100.00% | 6 |
| e1e-cropctx-8b-dense | player_running | 16/16 | 50.00% | 0.00% | 88.89% | 0.00% | 100.00% | 0 |
| e1e-cropctx-8b-dense | kit_color_seen | 20/18 | 94.44% | 10.00% | N/A | N/A | 90.00% | 1 |

Thresholds (MJ decides adoption):

| Run | Metric | Threshold | Measured | Result |
|---|---|---:|---:|---|
| e1d-checks-dense | off_pitch_false_yes_rate | <= 10.00% | 57.14% | FAIL |
| e1d-checks-dense | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1d-checks-dense | macro_accuracy | >= 80.00% | 66.71% | FAIL |
| e1d-checks-dense | abstain_rate | <= 40.00% | 2.91% | PASS |
| e1d-checks-prod30 | off_pitch_false_yes_rate | <= 10.00% | 50.00% | FAIL |
| e1d-checks-prod30 | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1d-checks-prod30 | macro_accuracy | >= 80.00% | 65.96% | FAIL |
| e1d-checks-prod30 | abstain_rate | <= 40.00% | 7.77% | PASS |
| e1d-checks-32b-dense | off_pitch_false_yes_rate | <= 10.00% | 50.00% | FAIL |
| e1d-checks-32b-dense | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1d-checks-32b-dense | macro_accuracy | >= 80.00% | 70.55% | FAIL |
| e1d-checks-32b-dense | abstain_rate | <= 40.00% | 6.80% | PASS |
| e1d-checks-32b-prod30 | off_pitch_false_yes_rate | <= 10.00% | 71.43% | FAIL |
| e1d-checks-32b-prod30 | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1d-checks-32b-prod30 | macro_accuracy | >= 80.00% | 71.49% | FAIL |
| e1d-checks-32b-prod30 | abstain_rate | <= 40.00% | 12.62% | PASS |
| e1d-checks-27b-dense | off_pitch_false_yes_rate | <= 10.00% | 64.29% | FAIL |
| e1d-checks-27b-dense | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1d-checks-27b-dense | macro_accuracy | >= 80.00% | 70.30% | FAIL |
| e1d-checks-27b-dense | abstain_rate | <= 40.00% | 3.88% | PASS |
| e1d-checks-27b-prod30 | off_pitch_false_yes_rate | <= 10.00% | 78.57% | FAIL |
| e1d-checks-27b-prod30 | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1d-checks-27b-prod30 | macro_accuracy | >= 80.00% | 71.69% | FAIL |
| e1d-checks-27b-prod30 | abstain_rate | <= 40.00% | 16.50% | PASS |
| e1e-crop-8b-dense | off_pitch_false_yes_rate | <= 10.00% | 50.00% | FAIL |
| e1e-crop-8b-dense | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1e-crop-8b-dense | macro_accuracy | >= 80.00% | 64.90% | FAIL |
| e1e-crop-8b-dense | abstain_rate | <= 40.00% | 1.94% | PASS |
| e1e-crop-8b-prod30 | off_pitch_false_yes_rate | <= 10.00% | 50.00% | FAIL |
| e1e-crop-8b-prod30 | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1e-crop-8b-prod30 | macro_accuracy | >= 80.00% | 67.09% | FAIL |
| e1e-crop-8b-prod30 | abstain_rate | <= 40.00% | 5.83% | PASS |
| e1e-cropctx-8b-dense | off_pitch_false_yes_rate | <= 10.00% | 50.00% | FAIL |
| e1e-cropctx-8b-dense | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS |
| e1e-cropctx-8b-dense | macro_accuracy | >= 80.00% | 66.43% | FAIL |
| e1e-cropctx-8b-dense | abstain_rate | <= 40.00% | 2.91% | PASS |

Truth rules:

- player_on_pitch: off_pitch=no; other classified=yes; unclassified (n24)=ungraded
- play_in_progress: off_pitch=no; on_ball_action/defensive_track_back/positional_only=yes; idle throw-in (n04-307417)=no; other idle (n10)=ungraded; mixed receive (n04-243433)=yes
- ball_near_player: off_pitch=no; on_ball_action=yes; other idle=no; defensive/positional/unclassified=ungraded
- player_touches_ball: off_pitch=no; on_ball_action=yes (including mixed n04-243433); other idle=no; defensive/positional/unclassified=ungraded
- player_running: off_pitch or non-on-ball walk/stand=no; mixed receive/walking n04-243433=ungraded; run/track back/goes or went forward/challenge=yes; n17-416826=yes by explicit directive override; other=ungraded
- kit_color_seen: identity_truth.kit_truth: uncertainty takes precedence and counts as abstention; verified override restores colour independently of disputed label; unavailable disputed colour=ungraded

Full truth table — ungraded cells shown as —; uncertain kit cells force abstention:

| Clip | MJ note | player_on_pitch | play_in_progress | ball_near_player | player_touches_ball | player_running | kit_color_seen |
|---|---|---|---|---|---|---|---|
| m04-n02-t3005-474114-478131 | playing right-side center back in a three at the back system. close to the touchline. | yes | yes | — | — | — | red |
| m04-n03-t1406-157170-158922 | either playing left-sided center back or left wing. nice move to win his challenge and passes it along to winger | yes | yes | yes | yes | yes | red |
| m04-n03-t1406-385962-387137 | putting on their warmup kit. and walks to sideline | no | no | no | no | no | uncertain / abstain |
| m04-n04-t3006-243433-247994 | playing up top. just walks around and waits until the keeper boots it to halfway line and then receives and does a half turn. | yes | yes | yes | yes | — | red |
| m04-n04-t3006-307417-310307 | a bit of running. ball doesn't come and waits for opposite team to throw in | yes | no | no | no | yes | red |
| m04-n05-t3007-284945-287898 | seems to be playing defense. tracked back. | yes | yes | — | — | yes | red |
| m04-n09-t1409-143096-143834 | on the sideline | no | no | no | no | no | red |
| m04-n09-t1409-297601-298865 | tracked back for defense and then went forward when team recovered. | yes | yes | — | — | yes | red |
| m04-n09-t1409-385922-386603 | stretching on sidelines | no | no | no | no | no | red |
| m04-n10-t711-186553-188161 | just walking around. | yes | — | no | no | no | red |
| m04-n12-t1411-237107-242145 | intercepts a ball but passes to opposite team | yes | yes | yes | yes | — | red |
| m04-n12-t1411-679986-681985 | walking off the field. | no | no | no | no | no | red |
| m04-n15-t3010-164698-170777 | multiple challenges for the ball | yes | yes | yes | yes | yes | red |
| m04-n17-t717-253073-260377 | heads the ball off defender for a throw-in. and goes forward when team recovers the ball. | yes | yes | yes | yes | yes | red |
| m04-n17-t717-304624-307834 | walking back on defense as play is on the opposite side. stays wide. | yes | yes | — | — | no | red |
| m04-n17-t717-416826-418915 | receives ball in midfield. playing as false 9 or 10 spot. loses the ball | yes | yes | yes | yes | yes | red |
| m04-n21-t3011-390297-390800 | warming up sideline. grabs hamstring | no | no | no | no | no | red |
| m04-n22-t3012-070707-074371 | walking off field in warmup suit. misses header | no | no | no | no | no | uncertain / abstain |
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

Thinking-channel diagnostic: not requested for lane C; prior model diagnostics remain in the lane-B models ledger.


Model/frame facts from run.json and raw attempts:

- 8b_dense: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "model": "qwen3-vl:8b", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- 8b_prod30: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "model": "qwen3-vl:8b", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}
- 32b_dense: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "model": "qwen3-vl:32b", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- 32b_prod30: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "model": "qwen3-vl:32b", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}
- 27b_dense: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "model": "qwen3.8:27b-obliterated-q8", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- 27b_prod30: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "model": "qwen3.8:27b-obliterated-q8", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}
- crop8_dense: {"adapter": "qwen3vl_checks_crop", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "model": "qwen3-vl:8b", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- crop8_prod30: {"adapter": "qwen3vl_checks_crop", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "model": "qwen3-vl:8b", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}
- cropctx8_dense: {"adapter": "qwen3vl_checks_crop", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 23.8, "model": "qwen3-vl:8b", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 476, "shifted_frame_count": 22, "single_frame_attempts": 0}

Provenance:

- Truth SHA-256: `b0701190324ab2527d400b2b176da67291a5efffc11fd314068b343e9f74e8ed`
- Human-note SHA-256: `5944679d0b576bfd8790d9d1206def9485f7618b0c6d53d4c7593c266d51d59f`
- Contract: film-room-checks-v1; truth rules: film-room-checks-truth-v1.

Caveats:

- n=20, one sequential pass per model, sampling policy and image variant. No repeats or causal claim; smoke is excluded from the comparison.
- Truth is derived deterministically from MJ's notes via semantic_activity plus the explicit checks rules. This is not independent exhaustive video annotation. n17-416826 running=yes is a directive override without a running keyword; mixed n04-243433 running remains ungraded.
- Gate 2 excludes mixed idle/on-ball n04-243433 because its note explicitly records a receive; it is not truth-negative. The two gates measure individual check assertions, not a production gate's combined decision.
- Lane A's saved reads used red boxes; this lane uses magenta. Most kits remain red, with one verified black override and two uncertain warm-up kits forced to abstain. These data do not isolate annotation colour effects.
- MJ reports tracker misses. Supplied truth box_track stands in for production tracking; identity/input mistakes may affect readings. Labels are supplied identity, not independent jersey evidence.
- Every frame imports lane A's spread sampling and magenta drawing. Targets in tracking gaps snap to a recorded timestamp within 0.5s; larger gaps fail. Temporary frame files are removed after each call.
- Schema validation establishes the contract, not visual correctness or whether Ollama applies format grammar to thinking. The production transport and its existing thinking fallback are unchanged.
- Reason strings are verbatim audit text and never scored. Failed reads remain failed; comparison metrics use only shared scored IDs. Thresholds are withheld for incomplete coverage or no shared scores.
- Wall time includes extraction/drawing and failures, with warm-model effects possible. Thinking rate counts all attempts in full-run reports; comparison rates use shared attempts.
- No adoption call: MJ owns that decision. This bench does not wire checks into the production honesty gate.
- One known error pending MJ correction; exact cell UNCONFIRMED in brief. Truth unchanged.
- Crops use the same 1280x720 decoded frames as lane B, not native-resolution redecodes. Resizing magnifies available pixels without restoring detail; 384px minimum context may still include multiple players.
- Crop translation at edges moves the marked player away from the exact crop centre. Crops can remove the ball, touchline or other evidence needed by the questions; context images may help but add image tokens.
- Crop+context interleaves 768x768 crops and 512-wide marked full frames. Comparator boxed-frame counts count images, not distinct timestamps; per-clip temporal/image counts are listed separately.
- Touch recall is yes/6 over the fixed true-touch clips, with no/unclear/failure counted as misses. Conditional 32B execution requires at least 2/6 in any 8B crop variant. This is an experiment scheduling rule, not an adoption threshold.
- Crop requests use 900s timeout; baseline 8B uses 120s, earlier 32B/27B 900s. This single-pass latency comparison is sensitive to model loading, cache warmth and runtime variability. No old outputs or fingerprints were rewritten.

Execution/gates:

```json
{
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
}
```

Crop geometry and image counts:

| Run | Side px range | Scale range | Sampled instants | Sent images |
|---|---:|---:|---:|---:|
| e1e-crop-8b-dense | 384–689 | 1.115–2.000 | 238 | 238 |
| e1e-crop-8b-prod30 | 384–689 | 1.115–2.000 | 29 | 29 |
| e1e-cropctx-8b-dense | 384–689 | 1.115–2.000 | 238 | 476 |

Six true-touch clips — answer / confidence:

| Clip | 8b_dense | 8b_prod30 | 32b_dense | 32b_prod30 | 27b_dense | 27b_prod30 | crop8_dense | crop8_prod30 | cropctx8_dense |
|---|---|---|---|---|---|---|---|---|---|
| m04-n03-t1406-157170-158922 | no / high | no / high | no / high | no / low | no / high | unclear / medium | no / high | no / high | no / high |
| m04-n04-t3006-243433-247994 | no / high | no / high | no / high | no / high | no / medium | unclear / low | no / high | no / high | no / high |
| m04-n12-t1411-237107-242145 | no / high | no / high | no / high | no / high | no / medium | unclear / low | no / high | no / high | no / high |
| m04-n15-t3010-164698-170777 | no / high | no / high | no / high | no / high | no / high | unclear / low | no / high | no / high | no / high |
| m04-n17-t717-253073-260377 | no / high | no / high | no / high | no / high | no / medium | unclear / low | no / high | no / high | no / high |
| m04-n17-t717-416826-418915 | no / high | no / high | no / high | no / high | no / medium | no / medium | no / high | no / high | no / high |

Three example crops (local report artifacts, not committed):

- /Users/mjjones/Projects/loanarmy-bench-reports/e1e-crop-examples/m04-n12-t1411-237107-242145-sample-00.png — t=2371.12, side=384px, scale=2.0; SHA-256 f124e405b5f90d6fe7f68cdf4bc799a0370f6324ffcd7d97685232c1be5fc8a7
- /Users/mjjones/Projects/loanarmy-bench-reports/e1e-crop-examples/m04-n12-t1411-237107-242145-sample-05.png — t=2393.975, side=384px, scale=2.0; SHA-256 56e99a5e7fe703016f6bc5768a3eeb0194b8b0a9d5f933bc113f8818312aa13b
- /Users/mjjones/Projects/loanarmy-bench-reports/e1e-crop-examples/m04-n12-t1411-237107-242145-sample-11.png — t=2421.4, side=384px, scale=2.0; SHA-256 6b0dbfc380de794aa5538bd3a548d23df1e96a3dd3b7699a6b08703b0fcfffa2
