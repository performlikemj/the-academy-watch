On 20 shared scored clips: e1d-checks-dense (qwen3-vl:8b, 11.9 boxed frames/attempt): off-pitch false-yes 57.14%, off-pitch/idle touch false-yes 0.00%; e1d-checks-32b-dense (qwen3-vl:32b, 11.9 boxed frames/attempt): off-pitch false-yes 50.00%, off-pitch/idle touch false-yes 0.00%; e1d-checks-27b-dense (qwen3.8:27b-obliterated-q8, 11.9 boxed frames/attempt): off-pitch false-yes 64.29%, off-pitch/idle touch false-yes 0.00%; e1d-checks-prod30 (qwen3-vl:8b, 1.45 boxed frames/attempt): off-pitch false-yes 50.00%, off-pitch/idle touch false-yes 0.00%; e1d-checks-32b-prod30 (qwen3-vl:32b, 1.45 boxed frames/attempt): off-pitch false-yes 71.43%, off-pitch/idle touch false-yes 0.00%; e1d-checks-27b-prod30 (qwen3.8:27b-obliterated-q8, 1.45 boxed frames/attempt): off-pitch false-yes 78.57%, off-pitch/idle touch false-yes 0.00%. Adoption belongs to MJ.

Gate numbers (false-yes count / truth-no cells):

| Run | Off-pitch on-pitch/in-progress | Off-pitch + idle touch |
|---|---:|---:|
| e1d-checks-dense | 8/14 (57.14%) | 0/9 (0.00%) |
| e1d-checks-prod30 | 7/14 (50.00%) | 0/9 (0.00%) |
| e1d-checks-32b-dense | 7/14 (50.00%) | 0/9 (0.00%) |
| e1d-checks-32b-prod30 | 10/14 (71.43%) | 0/9 (0.00%) |
| e1d-checks-27b-dense | 9/14 (64.29%) | 0/9 (0.00%) |
| e1d-checks-27b-prod30 | 11/14 (78.57%) | 0/9 (0.00%) |

Shared scored clips: 20. All comparison rates use shared IDs scored in every saved report and current rescoring. Full-run reports retain every attempt. Frame facts use all raw attempts. Configured wall caps alone do not imply an incomplete run.

Accuracy = correct / graded answered (unclear excluded). Abstain = unclear / eligible; coverage = graded answered / eligible. Binary eligibility requires yes/no truth. Kit eligibility follows lane A: uncertain kit truth forces abstention even for an asserted colour. False-yes = yes / truth-no cells; false-no = no / truth-yes cells, including abstentions in those truth denominators. Kit has no yes/no rates. Macro accuracy averages available accuracies across six questions; macro false-yes averages available rates across five binary questions; overall abstain is pooled over eligible cells. Gate 1 pools player_on_pitch and play_in_progress over off-pitch clips (14 cells on full set); Gate 2 uses player_touches_ball over off-pitch or idle clips with truth no (9 clips; mixed receive excluded). All metrics exclude failed reads; attempted/scored/failed counts remain visible. Thinking rate and wall/clip include all attempts. Reasons are logged only, never scored.

Mixed settings explicitly allowed: {"27b_dense": {"model": "qwen3.8:27b-obliterated-q8"}, "27b_prod30": {"model": "qwen3.8:27b-obliterated-q8"}, "32b_dense": {"model": "qwen3-vl:32b"}, "32b_prod30": {"model": "qwen3-vl:32b"}}; scoring uses supplied truth.

| Run | Model | Boxed frames/attempt | Scored/failed | Wall s/clip (all attempts) | Macro accuracy | Macro false-yes | Abstain | From thinking (all attempts) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| e1d-checks-dense | qwen3-vl:8b | 11.9 | 20/0 | 51.651 | 66.71% | 44.72% | 2.91% | 100.00% |
| e1d-checks-prod30 | qwen3-vl:8b | 1.45 | 20/0 | 10.547 | 65.96% | 37.70% | 7.77% | 100.00% |
| e1d-checks-32b-dense | qwen3-vl:32b | 11.9 | 20/0 | 216.428 | 70.55% | 37.70% | 6.80% | 100.00% |
| e1d-checks-32b-prod30 | qwen3-vl:32b | 1.45 | 20/0 | 39.580 | 71.49% | 36.67% | 12.62% | 100.00% |
| e1d-checks-27b-dense | qwen3.8:27b-obliterated-q8 | 11.9 | 20/0 | 172.788 | 70.30% | 38.25% | 3.88% | 0.00% |
| e1d-checks-27b-prod30 | qwen3.8:27b-obliterated-q8 | 1.45 | 20/0 | 87.783 | 71.69% | 39.17% | 16.50% | 0.00% |

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
| m04-n03-t1406-157170-158922 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n03-t1406-157170-158922 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n03-t1406-157170-158922 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n03-t1406-157170-158922 | e1d-checks-32b-prod30 | scored | yes / high | no / medium | no / low | no / low | unclear / medium | red / high |
| m04-n03-t1406-157170-158922 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high |
| m04-n03-t1406-157170-158922 | e1d-checks-27b-prod30 | scored | yes / high | yes / medium | no / high | unclear / medium | no / high | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | yes / medium | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-27b-dense | scored | yes / high | no / medium | unclear / low | no / medium | no / medium | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-27b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high |
| m04-n04-t3006-243433-247994 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n04-t3006-243433-247994 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | blue / high |
| m04-n04-t3006-243433-247994 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n04-t3006-243433-247994 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n04-t3006-243433-247994 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / medium | yes / high | red / high |
| m04-n04-t3006-243433-247994 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1d-checks-prod30 | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high |
| m04-n05-t3007-284945-287898 | e1d-checks-dense | scored | yes / high | yes / high | no / medium | no / low | yes / high | red / high |
| m04-n05-t3007-284945-287898 | e1d-checks-prod30 | scored | yes / high | yes / high | no / medium | no / low | yes / high | blue / high |
| m04-n05-t3007-284945-287898 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n05-t3007-284945-287898 | e1d-checks-32b-prod30 | scored | yes / high | yes / high | no / medium | no / high | yes / high | red / high |
| m04-n05-t3007-284945-287898 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high |
| m04-n05-t3007-284945-287898 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | unclear / low | yellow / high |
| m04-n09-t1409-143096-143834 | e1d-checks-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n09-t1409-143096-143834 | e1d-checks-prod30 | scored | no / high | yes / medium | no / high | no / high | no / high | red / high |
| m04-n09-t1409-143096-143834 | e1d-checks-32b-dense | scored | no / high | yes / high | no / high | no / high | no / high | red / high |
| m04-n09-t1409-143096-143834 | e1d-checks-32b-prod30 | scored | yes / high | no / medium | no / low | no / low | no / medium | red / high |
| m04-n09-t1409-143096-143834 | e1d-checks-27b-dense | scored | no / high | yes / high | no / high | no / high | no / high | red / high |
| m04-n09-t1409-143096-143834 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | no / high | no / medium | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | unclear / low | yes / high | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | no / medium | unclear / low | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-dense | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | yes / medium | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-27b-dense | scored | yes / high | no / medium | unclear / low | no / medium | no / medium | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-27b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high |
| m04-n10-t711-186553-188161 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n10-t711-186553-188161 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | blue / high |
| m04-n10-t711-186553-188161 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n10-t711-186553-188161 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / high | no / high | no / medium | red / high |
| m04-n10-t711-186553-188161 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high |
| m04-n10-t711-186553-188161 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | no / medium | red / high |
| m04-n12-t1411-237107-242145 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n12-t1411-237107-242145 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n12-t1411-237107-242145 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n12-t1411-237107-242145 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n12-t1411-237107-242145 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / medium | yes / high | red / high |
| m04-n12-t1411-237107-242145 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-32b-dense | scored | yes / high | no / medium | yes / high | no / medium | no / high | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / high | no / high | no / medium | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-27b-dense | scored | yes / high | no / medium | yes / high | no / medium | no / high | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | no / high | unclear / low | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | no / medium | no / high | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / medium | yes / high | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | unclear / low | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-32b-prod30 | scored | yes / high | yes / high | no / medium | no / high | yes / high | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / medium | yes / high | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | no / medium | yes / high | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | no / medium | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | no / medium | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-32b-prod30 | scored | yes / high | no / medium | no / high | no / high | no / medium | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-27b-dense | scored | yes / high | no / medium | no / high | no / high | no / medium | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-27b-prod30 | scored | yes / high | no / medium | no / high | no / medium | no / high | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-dense | scored | yes / high | no / medium | yes / high | no / low | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high |
| m04-n24-t3013-679939-681217 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n24-t3013-679939-681217 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | black / high |
| m04-n24-t3013-679939-681217 | e1d-checks-32b-dense | scored | yes / high | no / medium | no / high | no / high | no / medium | red / high |
| m04-n24-t3013-679939-681217 | e1d-checks-32b-prod30 | scored | yes / high | no / medium | no / low | no / high | no / medium | black / high |
| m04-n24-t3013-679939-681217 | e1d-checks-27b-dense | scored | yes / high | no / medium | yes / high | no / medium | no / high | red / high |
| m04-n24-t3013-679939-681217 | e1d-checks-27b-prod30 | scored | yes / high | yes / medium | no / high | unclear / medium | yes / high | red / high |
| m04-n25-t3014-530600-532465 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n25-t3014-530600-532465 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n25-t3014-530600-532465 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | yes / medium | red / high |
| m04-n25-t3014-530600-532465 | e1d-checks-32b-prod30 | scored | yes / high | yes / high | no / medium | no / high | yes / high | red / high |
| m04-n25-t3014-530600-532465 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high |
| m04-n25-t3014-530600-532465 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | no / medium | yes / medium | red / high |

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

Thinking-channel diagnostic:

- schema: JSON field=message.content; content empty=False; validates=True; selected=message.content; done_reason=stop; error=none.
- json: JSON field=message.content; content empty=False; validates=False; selected=message.content; done_reason=stop; error=none.
- none: JSON field=message.content; content empty=False; validates=False; selected=message.content; done_reason=stop; error=none.

Model/frame facts from run.json and raw attempts:

- 8b_dense: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "model": "qwen3-vl:8b", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- 8b_prod30: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "model": "qwen3-vl:8b", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}
- 32b_dense: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "model": "qwen3-vl:32b", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- 32b_prod30: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "model": "qwen3-vl:32b", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}
- 27b_dense: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "model": "qwen3.8:27b-obliterated-q8", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- 27b_prod30: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "model": "qwen3.8:27b-obliterated-q8", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}

Provenance:

- Truth SHA-256: `b0701190324ab2527d400b2b176da67291a5efffc11fd314068b343e9f74e8ed`
- Human-note SHA-256: `5944679d0b576bfd8790d9d1206def9485f7618b0c6d53d4c7593c266d51d59f`
- Contract: film-room-checks-v1; truth rules: film-room-checks-truth-v1.

Caveats:

- n=20, single sequential pass per model/sampling configuration; no repeats or causal claim about density or model size. Smoke and diagnostic are separate from the comparison.
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
- 32B and 27B use orchestrator-approved 900s request timeouts versus 120s for 8B. 27B full-run cap is 90 minutes, 32B cap was 150 minutes; none reached its cap. All other input/scoring settings match within each sampling policy. Model loading and cache warmth limit wall-time comparisons.
- 27B accepted all requested images and JSON-schema format; no fallback or sample reduction was used. Dense sends 10–12 images (238 total); prod30 sends 1–3 (29 total), identically to both earlier models.
- 27B per-clip wall times varied substantially during each pass; no cause was established. A mid-prod30 snapshot found only this task in the benchmark process guard and the 27B model fully GPU-resident at context 65536. Treat latency figures as this pass’s measurements, not controlled model-speed rankings.

Execution/gates:

```json
{
  "base_commit": "78b7643c",
  "model": {
    "name": "qwen3.8:27b-obliterated-q8",
    "model": "qwen3.8:27b-obliterated-q8",
    "modified_at": "2026-08-26T22:36:31.192076241+09:00",
    "size": 29978233703,
    "digest": "08d425ffbe92b2dfff3e0183f4b8db0962964e413d05e6348c9e05c65c5e886c",
    "details": {
      "parent_model": "hf.co/OBLITERATUS/Qwen3.8-27B-OBLITERATED:Q8_0",
      "format": "gguf",
      "family": "qwen35",
      "families": [
        "qwen35"
      ],
      "parameter_size": "27.3B",
      "quantization_level": "Q8_0"
    },
    "capabilities": [
      "completion",
      "vision",
      "tools",
      "thinking"
    ]
  },
  "timeout_s": 900,
  "per_run_wall_cap_s": 5400,
  "decision_authority": "MJ authorized full score; orchestrator specified 900s request timeout",
  "transport": "Unchanged checks adapter reuses qwen_match_analysis.ollama_chat via /api/chat, schema format, existing channel handling. No format or image-count fallback needed.",
  "status": "Measured: smoke, two full runs, diagnostic, comparison and validation complete; prepared for one local commit",
  "process_guard": "Only match is this task launch wrapper PID 29739: caffeinate/harness codex resume of this session and exact user brief. No competing benchmark.",
  "source_changes": "None. Ledger pair renamed and regenerated; all bench Python byte-identical to 78b7643c.",
  "smoke": {
    "run": "e1d-checks-27b-smoke",
    "validated": true,
    "image_count": 12,
    "format": "schema",
    "wall_s": 80.395,
    "over_240_s": false,
    "from_thinking": false,
    "checks": {
      "ball_near_player": {
        "answer": "no",
        "confidence": "medium",
        "reason": "Ball not within two body-lengths"
      },
      "kit_color_seen": {
        "answer": "red",
        "confidence": "high",
        "reason": "Red jersey and black shorts"
      },
      "play_in_progress": {
        "answer": "yes",
        "confidence": "high",
        "reason": "Active match play observed"
      },
      "player_on_pitch": {
        "answer": "yes",
        "confidence": "high",
        "reason": "Visible on the field of play"
      },
      "player_running": {
        "answer": "yes",
        "confidence": "high",
        "reason": "Running motion clearly seen"
      },
      "player_touches_ball": {
        "answer": "no",
        "confidence": "medium",
        "reason": "No clear ball contact visible"
      }
    }
  },
  "format_fallback": false,
  "image_limit_fallback": false,
  "sequential_execution": {
    "request_timeout_s": 900,
    "per_run_wall_cap_s": 5400,
    "runs": {
      "e1d-checks-27b-smoke": {
        "argv": [
          "/Users/mjjones/Projects/loanarmy/.loan/bin/python",
          "-u",
          "/Users/mjjones/Projects/loanarmy/.worktrees/lane-b/spike/video-analysis/bench/run_bench.py",
          "--adapter",
          "qwen3vl_checks",
          "--model",
          "qwen3.8:27b-obliterated-q8",
          "--timeout",
          "900",
          "--manifest",
          "/Users/mjjones/Projects/loanarmy-bench-frozen/manifest.json",
          "--report-root",
          "/Users/mjjones/Projects/loanarmy-bench-reports",
          "--clips",
          "m04-n12-t1411-237107-242145",
          "--sample-interval",
          "0.5",
          "--sample-limit",
          "12",
          "--run-id",
          "e1d-checks-27b-smoke"
        ],
        "started_at": "2026-09-09T13:19:14.782695+00:00",
        "pid": 30644,
        "wall_cap_s": 5400,
        "cap_exceeded": false,
        "exit_code": 0,
        "wall_s": 80.505,
        "completed_at": "2026-09-09T13:20:35.287553+00:00"
      },
      "e1d-checks-27b-dense": {
        "argv": [
          "/Users/mjjones/Projects/loanarmy/.loan/bin/python",
          "-u",
          "/Users/mjjones/Projects/loanarmy/.worktrees/lane-b/spike/video-analysis/bench/run_bench.py",
          "--adapter",
          "qwen3vl_checks",
          "--model",
          "qwen3.8:27b-obliterated-q8",
          "--timeout",
          "900",
          "--manifest",
          "/Users/mjjones/Projects/loanarmy-bench-frozen/manifest.json",
          "--report-root",
          "/Users/mjjones/Projects/loanarmy-bench-reports",
          "--clips",
          "all",
          "--sample-interval",
          "0.5",
          "--sample-limit",
          "12",
          "--run-id",
          "e1d-checks-27b-dense"
        ],
        "started_at": "2026-09-09T13:21:46.947159+00:00",
        "pid": 31328,
        "wall_cap_s": 5400,
        "cap_exceeded": false,
        "exit_code": 0,
        "wall_s": 3455.951,
        "completed_at": "2026-09-09T14:19:22.949256+00:00"
      },
      "e1d-checks-27b-prod30": {
        "argv": [
          "/Users/mjjones/Projects/loanarmy/.loan/bin/python",
          "-u",
          "/Users/mjjones/Projects/loanarmy/.worktrees/lane-b/spike/video-analysis/bench/run_bench.py",
          "--adapter",
          "qwen3vl_checks",
          "--model",
          "qwen3.8:27b-obliterated-q8",
          "--timeout",
          "900",
          "--manifest",
          "/Users/mjjones/Projects/loanarmy-bench-frozen/manifest.json",
          "--report-root",
          "/Users/mjjones/Projects/loanarmy-bench-reports",
          "--clips",
          "all",
          "--sample-interval",
          "30",
          "--sample-limit",
          "3",
          "--run-id",
          "e1d-checks-27b-prod30"
        ],
        "started_at": "2026-09-09T14:19:22.989781+00:00",
        "pid": 50309,
        "wall_cap_s": 5400,
        "cap_exceeded": false,
        "exit_code": 0,
        "wall_s": 1755.86,
        "completed_at": "2026-09-09T14:48:38.863162+00:00"
      },
      "e1d-checks-27b-diagnostic": {
        "argv": [
          "/Users/mjjones/Projects/loanarmy/.loan/bin/python",
          "-u",
          "/Users/mjjones/Projects/loanarmy/.worktrees/lane-b/spike/video-analysis/bench/diag_format_channel.py",
          "--model",
          "qwen3.8:27b-obliterated-q8",
          "--timeout",
          "900",
          "--manifest",
          "/Users/mjjones/Projects/loanarmy-bench-frozen/manifest.json",
          "--out-json",
          "/Users/mjjones/Projects/loanarmy-bench-reports/e1d-checks-27b-format-diagnostic.json"
        ],
        "started_at": "2026-09-09T14:48:38.904497+00:00",
        "pid": 58580,
        "wall_cap_s": 5400,
        "cap_exceeded": false,
        "exit_code": 0,
        "wall_s": 203.263,
        "completed_at": "2026-09-09T14:52:02.167743+00:00"
      }
    },
    "guard_checks": [
      {
        "before": "e1d-checks-27b-smoke",
        "matched_pids": [
          29739
        ],
        "foreign_pids": [],
        "at": "2026-09-09T13:19:14.781643+00:00",
        "own_wrapper_pid": 29739
      },
      {
        "before": "e1d-checks-27b-dense",
        "matched_pids": [
          29739
        ],
        "foreign_pids": [],
        "at": "2026-09-09T13:21:46.945838+00:00",
        "own_wrapper_pid": 29739
      },
      {
        "before": "e1d-checks-27b-prod30",
        "matched_pids": [
          29739
        ],
        "foreign_pids": [],
        "at": "2026-09-09T14:19:22.987825+00:00",
        "own_wrapper_pid": 29739
      },
      {
        "before": "e1d-checks-27b-diagnostic",
        "matched_pids": [
          29739
        ],
        "foreign_pids": [],
        "at": "2026-09-09T14:48:38.901837+00:00",
        "own_wrapper_pid": 29739
      }
    ],
    "state": "runs_and_diagnostic_finished"
  },
  "settings_diff_vs_32b": {
    "dense": {
      "fingerprint": {
        "32b": "c12f1158110948ea918d2467603161215c4c1f1bdf41e02dc6d192216c4bbf17",
        "27b": "1364f39d13af862dff3f275a415e811d8e39763125595529454d9a8139282ca1"
      },
      "model": {
        "32b": "qwen3-vl:32b",
        "27b": "qwen3.8:27b-obliterated-q8"
      }
    },
    "prod30": {
      "fingerprint": {
        "32b": "cd9c98b6218ef4b0fde79117a438f2a74898be0e374eb81d4eb4752d2229d687",
        "27b": "f176c385c3578d867c68b8357e1a0811afedf40fb1f07c08e17794289c1fb788"
      },
      "model": {
        "32b": "qwen3-vl:32b",
        "27b": "qwen3.8:27b-obliterated-q8"
      }
    }
  },
  "image_counts": {
    "dense": {
      "counts_by_clip": {
        "m04-n02-t3005-474114-478131": 12,
        "m04-n03-t1406-157170-158922": 12,
        "m04-n03-t1406-385962-387137": 12,
        "m04-n04-t3006-243433-247994": 12,
        "m04-n04-t3006-307417-310307": 12,
        "m04-n05-t3007-284945-287898": 12,
        "m04-n09-t1409-143096-143834": 12,
        "m04-n09-t1409-297601-298865": 12,
        "m04-n09-t1409-385922-386603": 12,
        "m04-n10-t711-186553-188161": 12,
        "m04-n12-t1411-237107-242145": 12,
        "m04-n12-t1411-679986-681985": 12,
        "m04-n15-t3010-164698-170777": 12,
        "m04-n17-t717-253073-260377": 12,
        "m04-n17-t717-304624-307834": 12,
        "m04-n17-t717-416826-418915": 12,
        "m04-n21-t3011-390297-390800": 10,
        "m04-n22-t3012-070707-074371": 12,
        "m04-n24-t3013-679939-681217": 12,
        "m04-n25-t3014-530600-532465": 12
      },
      "min": 10,
      "max": 12,
      "total": 238,
      "mean": 11.9
    },
    "prod30": {
      "counts_by_clip": {
        "m04-n02-t3005-474114-478131": 2,
        "m04-n03-t1406-157170-158922": 1,
        "m04-n03-t1406-385962-387137": 1,
        "m04-n04-t3006-243433-247994": 2,
        "m04-n04-t3006-307417-310307": 1,
        "m04-n05-t3007-284945-287898": 1,
        "m04-n09-t1409-143096-143834": 1,
        "m04-n09-t1409-297601-298865": 1,
        "m04-n09-t1409-385922-386603": 1,
        "m04-n10-t711-186553-188161": 1,
        "m04-n12-t1411-237107-242145": 2,
        "m04-n12-t1411-679986-681985": 1,
        "m04-n15-t3010-164698-170777": 3,
        "m04-n17-t717-253073-260377": 3,
        "m04-n17-t717-304624-307834": 2,
        "m04-n17-t717-416826-418915": 1,
        "m04-n21-t3011-390297-390800": 1,
        "m04-n22-t3012-070707-074371": 2,
        "m04-n24-t3013-679939-681217": 1,
        "m04-n25-t3014-530600-532465": 1
      },
      "min": 1,
      "max": 3,
      "total": 29,
      "mean": 1.45
    }
  },
  "unchanged_proof": {
    "base_commit": "78b7643c",
    "source_sha256": {
      "spike/video-analysis/bench/adapters/__init__.py": "f1c9bc9b2711b8202a046445637358057a05f8e9cce4b72521cd450a823d57ba",
      "spike/video-analysis/bench/adapters/baseline.py": "5b54a03d1396a687701b4defff2a10639e86bcef40fa6da65e06d5b57e8ce9c0",
      "spike/video-analysis/bench/adapters/common.py": "bbc42955d2d6fd2f4b1a7cea8278803f066dfadba6ae87a0d86862906c2e277a",
      "spike/video-analysis/bench/adapters/mlx_worker.py": "99cc1a514385636c5a89f1c8405968571bc0023f050ea605f3b2ec78bfdf010d",
      "spike/video-analysis/bench/adapters/qwen3vl_annotated.py": "d6d7b484420c3bde476d80aa7a41587f489b8e4403e110cfd142ca39c606a743",
      "spike/video-analysis/bench/adapters/qwen3vl_checks.py": "92f070b614adf821628c228685deba4ac99a1a63cc21c0f02015253b6d3ec394",
      "spike/video-analysis/bench/adapters/qwen3vl_mlx.py": "45daf3d1a4ea9b4f44dd7cd6d294f3a4adb900a7fdd4b09177f0554148578da0",
      "spike/video-analysis/bench/adapters/qwen3vl_ollama.py": "1404a11e120eae44c2de3c7ac5ac072a090b5d61e17b2d65e4b37e47acad403b",
      "spike/video-analysis/bench/apply_notes.py": "624ae60c39b28a7f1a759a2d39f4f27a1825f34a0152b8d34d0189b5fed8ed13",
      "spike/video-analysis/bench/build_manifest.py": "ed7f3cec39feccdb1591d22ce0aaaee43563cac70c3def6c38666acd73b93128",
      "spike/video-analysis/bench/checks_contract.py": "579d1ca7d6f01a95c33c36bd072ee7b56016eab752b5a8cc5cb8ce2c22b048d8",
      "spike/video-analysis/bench/checks_score.py": "29f5d71602b1fa0b19881afe624b2a32606169691ab5bbbdca8259a1a4ad2a7f",
      "spike/video-analysis/bench/checks_truth.py": "d847e4934d1774914e4df44b0797521c4c9695fff281d58a6afdabf0f6f204e7",
      "spike/video-analysis/bench/compare_checks.py": "b012370b8d13528f9ac4d2ee5527c3aecdcf8f951e96b37a76edbfd3f90c49bc",
      "spike/video-analysis/bench/compare_runs.py": "0c2d7a8835c8ab79acf74d1cd8b85494abeb2845f760d5d7c8ae52a86c4ae188",
      "spike/video-analysis/bench/compare_semantic.py": "c55e94b3155de1df0c83736f40bee41fea999eed947dcd2278bb9652204d85d0",
      "spike/video-analysis/bench/contract.py": "9b9c6dee3aa9f2b7680d15532df58c18f074359427d014dda8c76f03021b27c7",
      "spike/video-analysis/bench/diag_format_channel.py": "4bfc993e99cf9855d6097e1236595c222514f9da7568f37bccbebcc6667c0f88",
      "spike/video-analysis/bench/identity_truth.py": "0718a39402b73fe220a695199e1306a672742df3d358eef0aa8de0116b0f7f04",
      "spike/video-analysis/bench/provenance.py": "2459798f5c7a8d47b6d71037cd9558535b12e9cd05543ccf3c373e6b62ef236a",
      "spike/video-analysis/bench/review_kit.py": "85044bec7171c7c0697ba37f0a76270c282991da10c4867dec3329b48687c8c9",
      "spike/video-analysis/bench/run_bench.py": "d44d9f4746823e5f9e2b5548318efbb3d59f243e36e8a0e966401f5f875cf24b",
      "spike/video-analysis/bench/score.py": "326cc4301150c5b3aa10d5a3bf54c75c5edec22f70b31cf40c603393c5bd23b6",
      "spike/video-analysis/bench/semantic_activity.py": "5a114717535212ed76bad545562b40579290b67445d1fc31309ed9dfd95ec8ae",
      "spike/video-analysis/bench/semantic_contract.py": "257203aea1a93f329488085779229fea513cd10a05ef479bb10610799aac71af",
      "spike/video-analysis/bench/semantic_score.py": "8b335aa740412dff0960031c3cddbaf2b6fad82ea8d75b14b57f82654f447b9b",
      "spike/video-analysis/bench/test_bench.py": "37feeec5b7939d71d19bd732419f099fbed496bfc8f03186021032f6b7ce4a48",
      "spike/video-analysis/bench/test_checks.py": "35026553eff43b580c10e9a0775ed947b59d1f594244be104e8386229e4c07de",
      "spike/video-analysis/bench/test_semantic.py": "bc5e0b3544bf491bd209ad908ae994d4006a83ffad0bcc701e9ae08e39f6efd3"
    },
    "old_run_json_sha256": {
      "e1d-checks-dense": "88585b81f76b12ebf48b5811d9576a63c4d0b517d6a2ae6457dd1f729db88599",
      "e1d-checks-prod30": "f55cbac67500dde234b02c196d4b7873b12a25b991cafd77cf4cf93b3bfcbdc7",
      "e1d-checks-32b-dense": "202ba5e4027c1fb5d4dc6581ed0b079fab0db37bd6d874ca95d23cbfbc339d33",
      "e1d-checks-32b-prod30": "a798c8b7c578a5625dd341a1804f7529e3e8e59720b9f5e5b9bb8dae88a8400e"
    }
  },
  "gates": {
    "pytest": "307 passed in 1.00s; BENCH_REQUIRE_CV2=1 /Users/mjjones/Projects/loanarmy/.loan/bin/python -m pytest spike/video-analysis/bench -q",
    "ruff_check": "PASS; ruff check spike/video-analysis/bench",
    "ruff_format": "PASS, 29 files; ruff format --check spike/video-analysis/bench",
    "six_run_guards": "PASS: mixed-model rejection, deterministic six-run comparison, shared saved-score intersection, incomplete sixth-run claim withholds all thresholds",
    "artifact_verification": "PASS: 20 x 6 coverage, 40 matched 27B/8B frame feeds, source hashes, previous run.json hashes, truth hashes and caps",
    "diff_check": "PASS; git diff --check"
  },
  "not_done": "Known truth error and r2 fix round pending; no adoption decision, production integration or push.",
  "runtime_snapshot": {
    "at": "2026-09-09T14:22:08.740376+00:00",
    "matched_pids": [
      29739,
      50309
    ],
    "own_task_pids": [
      29739,
      50309
    ],
    "foreign_pids": [],
    "ollama_ps": {
      "models": [
        {
          "name": "qwen3.8:27b-obliterated-q8",
          "model": "qwen3.8:27b-obliterated-q8",
          "size": 34169379879,
          "digest": "08d425ffbe92b2dfff3e0183f4b8db0962964e413d05e6348c9e05c65c5e886c",
          "details": {
            "parent_model": "",
            "format": "gguf",
            "family": "qwen35",
            "families": [
              "qwen35"
            ],
            "parameter_size": "27.3B",
            "quantization_level": "Q8_0"
          },
          "expires_at": "2318-12-20T23:08:55.419165807+09:00",
          "size_vram": 34169379879,
          "context_length": 65536
        }
      ]
    }
  },
  "wall_time_variability": {
    "dense": {
      "min_s": 95.3,
      "max_s": 288.274,
      "over_240_s_count": 4
    },
    "prod30": {
      "min_s": 45.217,
      "max_s": 158.45,
      "over_240_s_count": 0
    }
  },
  "diagnostic_interpretation": "All modes returned JSON in message.content. Schema validated; json/none returned a checks array instead of the required named question fields and failed strict validation. No transport changes or retries."
}
```

Six truth-positive touch clips — 27B answer / confidence:

| Clip | 27B dense | 27B prod30 |
|---|---|---|
| m04-n03-t1406-157170-158922 | no / high | unclear / medium |
| m04-n04-t3006-243433-247994 | no / medium | unclear / low |
| m04-n12-t1411-237107-242145 | no / medium | unclear / low |
| m04-n15-t3010-164698-170777 | no / high | unclear / low |
| m04-n17-t717-253073-260377 | no / medium | unclear / low |
| m04-n17-t717-416826-418915 | no / medium | no / medium |

Historical channel diagnostics (retained from previous runs):

- 8b / schema: JSON field=message.thinking; content empty=True; validates=True; done_reason=stop.
- 8b / json: JSON field=message.thinking; content empty=True; validates=True; done_reason=stop.
- 8b / none: JSON field=none; content empty=True; validates=False; done_reason=length.
- 32b / schema: JSON field=message.thinking; content empty=True; validates=True; done_reason=stop.
- 32b / json: JSON field=message.thinking; content empty=True; validates=True; done_reason=stop.
- 32b / none: JSON field=none; content empty=True; validates=False; done_reason=length.
