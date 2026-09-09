On 20 shared scored clips: e1d-checks-dense (qwen3-vl:8b, 11.9 boxed frames/attempt): off-pitch false-yes 57.14%, off-pitch/idle touch false-yes 0.00%; e1d-checks-32b-dense (qwen3-vl:32b, 11.9 boxed frames/attempt): off-pitch false-yes 50.00%, off-pitch/idle touch false-yes 0.00%; e1d-checks-prod30 (qwen3-vl:8b, 1.45 boxed frames/attempt): off-pitch false-yes 50.00%, off-pitch/idle touch false-yes 0.00%; e1d-checks-32b-prod30 (qwen3-vl:32b, 1.45 boxed frames/attempt): off-pitch false-yes 71.43%, off-pitch/idle touch false-yes 0.00%. Adoption belongs to MJ.

Gate numbers (false-yes count / truth-no cells):

| Run | Off-pitch on-pitch/in-progress | Off-pitch + idle touch |
|---|---:|---:|
| e1d-checks-dense | 8/14 (57.14%) | 0/9 (0.00%) |
| e1d-checks-prod30 | 7/14 (50.00%) | 0/9 (0.00%) |
| e1d-checks-32b-dense | 7/14 (50.00%) | 0/9 (0.00%) |
| e1d-checks-32b-prod30 | 10/14 (71.43%) | 0/9 (0.00%) |

Shared scored clips: 20. All comparison rates use shared IDs scored in every saved report and current rescoring. Full-run reports retain every attempt. Frame facts use all raw attempts. Configured wall caps alone do not imply an incomplete run.

Accuracy = correct / graded answered (unclear excluded). Abstain = unclear / eligible; coverage = graded answered / eligible. Binary eligibility requires yes/no truth. Kit eligibility follows lane A: uncertain kit truth forces abstention even for an asserted colour. False-yes = yes / truth-no cells; false-no = no / truth-yes cells, including abstentions in those truth denominators. Kit has no yes/no rates. Macro accuracy averages available accuracies across six questions; macro false-yes averages available rates across five binary questions; overall abstain is pooled over eligible cells. Gate 1 pools player_on_pitch and play_in_progress over off-pitch clips (14 cells on full set); Gate 2 uses player_touches_ball over off-pitch or idle clips with truth no (9 clips; mixed receive excluded). All metrics exclude failed reads; attempted/scored/failed counts remain visible. Thinking rate and wall/clip include all attempts. Reasons are logged only, never scored.

Mixed settings explicitly allowed: {"32b_dense": {"model": "qwen3-vl:32b"}, "32b_prod30": {"model": "qwen3-vl:32b"}}; scoring uses supplied truth.

| Run | Model | Boxed frames/attempt | Scored/failed | Wall s/clip (all attempts) | Macro accuracy | Macro false-yes | Abstain | From thinking (all attempts) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| e1d-checks-dense | qwen3-vl:8b | 11.9 | 20/0 | 51.651 | 66.71% | 44.72% | 2.91% | 100.00% |
| e1d-checks-prod30 | qwen3-vl:8b | 1.45 | 20/0 | 10.547 | 65.96% | 37.70% | 7.77% | 100.00% |
| e1d-checks-32b-dense | qwen3-vl:32b | 11.9 | 20/0 | 216.428 | 70.55% | 37.70% | 6.80% | 100.00% |
| e1d-checks-32b-prod30 | qwen3-vl:32b | 1.45 | 20/0 | 39.580 | 71.49% | 36.67% | 12.62% | 100.00% |

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
| m04-n03-t1406-157170-158922 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n03-t1406-157170-158922 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n03-t1406-157170-158922 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n03-t1406-157170-158922 | e1d-checks-32b-prod30 | scored | yes / high | no / medium | no / low | no / low | unclear / medium | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | yes / medium | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high |
| m04-n04-t3006-243433-247994 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n04-t3006-243433-247994 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | blue / high |
| m04-n04-t3006-243433-247994 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n04-t3006-243433-247994 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1d-checks-prod30 | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n05-t3007-284945-287898 | e1d-checks-dense | scored | yes / high | yes / high | no / medium | no / low | yes / high | red / high |
| m04-n05-t3007-284945-287898 | e1d-checks-prod30 | scored | yes / high | yes / high | no / medium | no / low | yes / high | blue / high |
| m04-n05-t3007-284945-287898 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n05-t3007-284945-287898 | e1d-checks-32b-prod30 | scored | yes / high | yes / high | no / medium | no / high | yes / high | red / high |
| m04-n09-t1409-143096-143834 | e1d-checks-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n09-t1409-143096-143834 | e1d-checks-prod30 | scored | no / high | yes / medium | no / high | no / high | no / high | red / high |
| m04-n09-t1409-143096-143834 | e1d-checks-32b-dense | scored | no / high | yes / high | no / high | no / high | no / high | red / high |
| m04-n09-t1409-143096-143834 | e1d-checks-32b-prod30 | scored | yes / high | no / medium | no / low | no / low | no / medium | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-dense | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | yes / medium | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high |
| m04-n10-t711-186553-188161 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n10-t711-186553-188161 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | blue / high |
| m04-n10-t711-186553-188161 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n10-t711-186553-188161 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / high | no / high | no / medium | red / high |
| m04-n12-t1411-237107-242145 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n12-t1411-237107-242145 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n12-t1411-237107-242145 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n12-t1411-237107-242145 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-32b-dense | scored | yes / high | no / medium | yes / high | no / medium | no / high | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / high | no / high | no / medium | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | no / medium | no / high | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | unclear / low | no / high | yes / medium | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-32b-prod30 | scored | yes / high | yes / high | no / medium | no / high | yes / high | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | no / medium | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | no / medium | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-32b-prod30 | scored | yes / high | no / medium | no / high | no / high | no / medium | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-dense | scored | yes / high | no / medium | yes / high | no / low | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n24-t3013-679939-681217 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n24-t3013-679939-681217 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | black / high |
| m04-n24-t3013-679939-681217 | e1d-checks-32b-dense | scored | yes / high | no / medium | no / high | no / high | no / medium | red / high |
| m04-n24-t3013-679939-681217 | e1d-checks-32b-prod30 | scored | yes / high | no / medium | no / low | no / high | no / medium | black / high |
| m04-n25-t3014-530600-532465 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n25-t3014-530600-532465 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n25-t3014-530600-532465 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | yes / medium | red / high |
| m04-n25-t3014-530600-532465 | e1d-checks-32b-prod30 | scored | yes / high | yes / high | no / medium | no / high | yes / high | red / high |

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

Thinking-channel diagnostic:

- schema: JSON field=message.thinking; content empty=True; validates=True; selected=message.thinking; done_reason=stop; error=none.
- json: JSON field=message.thinking; content empty=True; validates=True; selected=message.thinking; done_reason=stop; error=none.
- none: JSON field=none; content empty=True; validates=False; selected=message.thinking; done_reason=length; error=none.

Model/frame facts from run.json and raw attempts:

- 8b_dense: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "model": "qwen3-vl:8b", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- 8b_prod30: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "model": "qwen3-vl:8b", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}
- 32b_dense: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "model": "qwen3-vl:32b", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- 32b_prod30: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "model": "qwen3-vl:32b", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}

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
- 32B requests use the orchestrator-approved 900s timeout versus 120s for 8B; all other input/scoring settings match within each sampling policy. Timeout and warm-model effects limit wall-time comparisons.

Execution/gates:

```json
{
  "state": "runs, diagnostic, comparison and validation complete; prepared for one local commit",
  "decision_authority": "orchestrator (not MJ), explicit user instruction",
  "timeout_s_32b": 900,
  "timeout_s_8b": 120,
  "per_run_wall_cap_s": 9000,
  "timeout_delivery": "Existing --timeout flag; timeout_s recorded and fingerprinted by unchanged runner. Diagnostic also receives --timeout 900.",
  "settings_diff_vs_8b": {
    "dense": {
      "fingerprint": {
        "8b": "6e8ec883c4c453d2b77bd098f2c7ea710b56036607883ffbe4a76fa899ad29da",
        "32b": "c12f1158110948ea918d2467603161215c4c1f1bdf41e02dc6d192216c4bbf17"
      },
      "model": {
        "8b": "qwen3-vl:8b",
        "32b": "qwen3-vl:32b"
      },
      "timeout_s": {
        "8b": 120.0,
        "32b": 900.0
      }
    },
    "prod30": {
      "fingerprint": {
        "8b": "a860576279b9090df7917701ba1996faa214b862d2286a9c9ce4f29da73e5065",
        "32b": "cd9c98b6218ef4b0fde79117a438f2a74898be0e374eb81d4eb4752d2229d687"
      },
      "model": {
        "8b": "qwen3-vl:8b",
        "32b": "qwen3-vl:32b"
      },
      "timeout_s": {
        "8b": 120.0,
        "32b": 900.0
      }
    }
  },
  "unchanged": "Prompt, contract, truth rules, scorer, transport, runner, diagnostic and frame feed byte-identical to bcb1699a; truth hashes match both 8B launches.",
  "model": {
    "tag": "qwen3-vl:32b",
    "size_bytes": 20910297800,
    "quantization": "Q4_K_M",
    "pull_wall_s": 2232.383,
    "pull_log": "/Users/mjjones/codex-runs/pull-qwen3vl-32b.log"
  },
  "smokes": {
    "original_120s": {
      "run": "e1d-checks-32b-smoke",
      "wall_s": 121.514,
      "error": "TimeoutError: timed out",
      "included_in_comparison": false
    },
    "approved_900s": {
      "run": "e1d-checks-32b-smoke-900",
      "wall_s": 201.795,
      "validated": true,
      "from_thinking": true,
      "over_240_s": false,
      "included_in_comparison": false
    }
  },
  "sequential_execution": {
    "decision_authority": "orchestrator, explicit user instruction",
    "request_timeout_s": 900,
    "per_run_wall_cap_s": 9000,
    "runs": {
      "e1d-checks-32b-dense": {
        "argv": [
          "/Users/mjjones/Projects/loanarmy/.loan/bin/python",
          "-u",
          "/Users/mjjones/Projects/loanarmy/.worktrees/lane-b/spike/video-analysis/bench/run_bench.py",
          "--adapter",
          "qwen3vl_checks",
          "--model",
          "qwen3-vl:32b",
          "--clips",
          "all",
          "--timeout",
          "900",
          "--manifest",
          "/Users/mjjones/Projects/loanarmy-bench-frozen/manifest.json",
          "--report-root",
          "/Users/mjjones/Projects/loanarmy-bench-reports",
          "--sample-interval",
          "0.5",
          "--sample-limit",
          "12",
          "--run-id",
          "e1d-checks-32b-dense"
        ],
        "started_at": "2026-09-09T11:43:45.357835+00:00",
        "wall_cap_s": 9000,
        "cap_exceeded": false,
        "pid": 6678,
        "exit_code": 0,
        "wall_s": 4328.737,
        "completed_at": "2026-09-09T12:55:54.128699+00:00"
      },
      "e1d-checks-32b-prod30": {
        "argv": [
          "/Users/mjjones/Projects/loanarmy/.loan/bin/python",
          "-u",
          "/Users/mjjones/Projects/loanarmy/.worktrees/lane-b/spike/video-analysis/bench/run_bench.py",
          "--adapter",
          "qwen3vl_checks",
          "--model",
          "qwen3-vl:32b",
          "--clips",
          "all",
          "--timeout",
          "900",
          "--manifest",
          "/Users/mjjones/Projects/loanarmy-bench-frozen/manifest.json",
          "--report-root",
          "/Users/mjjones/Projects/loanarmy-bench-reports",
          "--sample-interval",
          "30",
          "--sample-limit",
          "3",
          "--run-id",
          "e1d-checks-32b-prod30"
        ],
        "started_at": "2026-09-09T12:55:54.149842+00:00",
        "wall_cap_s": 9000,
        "cap_exceeded": false,
        "pid": 24602,
        "exit_code": 0,
        "wall_s": 791.775,
        "completed_at": "2026-09-09T13:09:05.902524+00:00"
      },
      "e1d-checks-32b-diagnostic": {
        "argv": [
          "/Users/mjjones/Projects/loanarmy/.loan/bin/python",
          "-u",
          "/Users/mjjones/Projects/loanarmy/.worktrees/lane-b/spike/video-analysis/bench/diag_format_channel.py",
          "--model",
          "qwen3-vl:32b",
          "--timeout",
          "900",
          "--manifest",
          "/Users/mjjones/Projects/loanarmy-bench-frozen/manifest.json",
          "--out-json",
          "/Users/mjjones/Projects/loanarmy-bench-reports/e1d-checks-32b-format-diagnostic.json"
        ],
        "started_at": "2026-09-09T13:09:05.921697+00:00",
        "wall_cap_s": 9000,
        "cap_exceeded": false,
        "pid": 27751,
        "exit_code": 0,
        "wall_s": 270.306,
        "completed_at": "2026-09-09T13:13:36.227916+00:00"
      }
    },
    "guard_checks": [
      {
        "before": "e1d-checks-32b-dense",
        "matched_pids": [],
        "foreign_pids": [],
        "at": "2026-09-09T11:43:45.357334+00:00"
      },
      {
        "before": "e1d-checks-32b-prod30",
        "matched_pids": [],
        "foreign_pids": [],
        "at": "2026-09-09T12:55:54.149160+00:00"
      },
      {
        "before": "e1d-checks-32b-diagnostic",
        "matched_pids": [],
        "foreign_pids": [],
        "at": "2026-09-09T13:09:05.921169+00:00"
      }
    ],
    "state": "runs_and_diagnostic_finished"
  },
  "gates": {
    "pytest": "307 passed in 1.36s; BENCH_REQUIRE_CV2=1; /Users/mjjones/Projects/loanarmy/.loan/bin/python -m pytest spike/video-analysis/bench -q",
    "ruff_check": "PASS; /Users/mjjones/.local/bin/ruff check spike/video-analysis/bench",
    "ruff_format": "PASS, 29 files; /Users/mjjones/.local/bin/ruff format --check spike/video-analysis/bench",
    "four_run_checks": "PASS",
    "diff_check": "PASS; git diff --check"
  },
  "verification": "Four-run guards passed; mixed models rejected without flag; deterministic comparison repeated identically; protected source hashes and launch truth hashes verified; every frame timestamp, sampling shift and anchor matches the corresponding 8B raw attempt.",
  "scope": "Only compare_checks.py and this ledger pair; one local commit; no push.",
  "not_done": "Known truth correction and separate fix round remain pending; no adoption decision, production integration or push."
}
```

Per-question changes: percentage points, 32B minus 8B. Each cell is accuracy / abstain / false-yes.

| Question | Dense delta (pp) | Prod30 delta (pp) |
|---|---:|---:|
| player_on_pitch | +5.26 / +0.00 / -14.29 | -5.26 / +0.00 / +14.29 |
| play_in_progress | -4.27 / +27.78 / +12.50 | +22.65 / +27.78 / +25.00 |
| ball_near_player | +3.33 / -6.67 / +0.00 | -19.66 / -26.67 / +0.00 |
| player_touches_ball | +0.00 / +0.00 / +0.00 | +0.00 / +0.00 / +0.00 |
| player_running | +18.75 / +0.00 / -33.33 | +18.75 / +25.00 / -44.44 |
| kit_color_seen | +0.00 / +0.00 / N/A | +16.67 / +0.00 / N/A |

The six truth-positive touch clips, unchanged truth:

| Clip | 32B dense touch / confidence | 32B prod30 touch / confidence |
|---|---|---|
| m04-n03-t1406-157170-158922 | no / high | no / low |
| m04-n04-t3006-243433-247994 | no / high | no / high |
| m04-n12-t1411-237107-242145 | no / high | no / high |
| m04-n15-t3010-164698-170777 | no / high | no / high |
| m04-n17-t717-253073-260377 | no / high | no / high |
| m04-n17-t717-416826-418915 | no / high | no / high |
