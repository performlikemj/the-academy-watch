Across 8B, 32B and 27B, wide frames or 768-px crops, every model says 'on pitch, high confidence' for players stretching, warming up or in warm-up kit on the sideline, and no run could have detected a touch because the stills are 1.6–6.6 s apart — the bench has shown the checks are blind to sideline context and has not yet tested touch detection at all.

Review-requested synthesis, reproduced verbatim. The categorical wording is not a measured perfect-detector bound or a claim that every individual read was identical. Actual counts and confounds follow: temporal spacing does not prove that zero touches were visible, and crop views also remove sideline/ball context.

On 20 shared scored clips (wide runs only; crops excluded from gate-1 headline): e1d-checks-dense (qwen3-vl:8b, 11.9 boxed frames/attempt): off-pitch false-yes 57.14%, touch false-yes 0.00%, touch recall N/A (raw 0/6), gate 2 WITHHELD; e1d-checks-32b-dense (qwen3-vl:32b, 11.9 boxed frames/attempt): off-pitch false-yes 50.00%, touch false-yes 0.00%, touch recall N/A (raw 0/6), gate 2 WITHHELD; e1d-checks-27b-dense (qwen3.8:27b-obliterated-q8, 11.9 boxed frames/attempt): off-pitch false-yes 64.29%, touch false-yes 0.00%, touch recall N/A (raw 0/6), gate 2 WITHHELD; e1d-checks-prod30 (qwen3-vl:8b, 1.45 boxed frames/attempt): off-pitch false-yes 50.00%, touch false-yes 0.00%, touch recall N/A (raw 0/6), gate 2 WITHHELD; e1d-checks-32b-prod30 (qwen3-vl:32b, 1.45 boxed frames/attempt): off-pitch false-yes 71.43%, touch false-yes 0.00%, touch recall N/A (raw 0/6), gate 2 WITHHELD; e1d-checks-27b-prod30 (qwen3.8:27b-obliterated-q8, 1.45 boxed frames/attempt): off-pitch false-yes 78.57%, touch false-yes 0.00%, touch recall N/A (raw 0/6), gate 2 WITHHELD. Adoption belongs to MJ.

Gate numbers (false-yes count / truth-no cells):

| Run | Off-pitch on-pitch | Off-pitch in-progress | Gate 1 pooled | Touch false-yes | Raw touch yes/positive | Touch recall | Gate 2 | Confounds |
|---|---:|---:|---:|---:|---:|---|---|---|
| e1d-checks-dense | 7/7 (100.00%) | 1/7 (14.29%) | 8/14 (57.14%) | 0/9 (0.00%) | 0/6 | N/A | WITHHELD | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition.  |
| e1d-checks-prod30 | 6/7 (85.71%) | 1/7 (14.29%) | 7/14 (50.00%) | 0/9 (0.00%) | 0/6 | N/A | WITHHELD | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition.  |
| e1d-checks-32b-dense | 6/7 (85.71%) | 1/7 (14.29%) | 7/14 (50.00%) | 0/9 (0.00%) | 0/6 | N/A | WITHHELD | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition.  |
| e1d-checks-32b-prod30 | 7/7 (100.00%) | 3/7 (42.86%) | 10/14 (71.43%) | 0/9 (0.00%) | 0/6 | N/A | WITHHELD | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition.  |
| e1d-checks-27b-dense | 6/7 (85.71%) | 3/7 (42.86%) | 9/14 (64.29%) | 0/9 (0.00%) | 0/6 | N/A | WITHHELD | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition.  |
| e1d-checks-27b-prod30 | 7/7 (100.00%) | 4/7 (57.14%) | 11/14 (78.57%) | 0/9 (0.00%) | 0/6 | N/A | WITHHELD | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition.  |

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
| e1d-checks-32b-dense | player_on_pitch | 19/19 | 68.42% | 63.16% | 5.26% | yes | 95.00% | False | 0.00% | 85.71% | 100.00% | 0.00% | 100.00% | 6 | — |
| e1d-checks-32b-dense | play_in_progress | 17/12 | 91.67% | 58.82% | 32.84% | yes | 65.00% | True | 29.41% | 14.29% | 100.00% | 0.00% | 70.59% | 1 | — |
| e1d-checks-32b-dense | ball_near_player | 15/15 | 46.67% | 53.33% | -6.67% | no | 95.00% | False | 0.00% | 12.50% | 0.00% | 100.00% | 100.00% | 8 | — |
| e1d-checks-32b-dense | player_touches_ball | 15/15 | 60.00% | 60.00% | 0.00% | no | 100.00% | False | 0.00% | 0.00% | N/A | 100.00% | 100.00% | 6 | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-32b-dense | player_running | 13/13 | 53.85% | 69.23% | -15.38% | yes | 80.00% | False | 0.00% | 66.67% | 100.00% | 0.00% | 100.00% | 0 | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-32b-dense | kit_color_seen | 20/18 | 94.44% | 94.44% | 0.00% | red | 100.00% | False | 10.00% | N/A | N/A | N/A | 90.00% | 1 | — |
| e1d-checks-32b-prod30 | player_on_pitch | 19/19 | 63.16% | 63.16% | 0.00% | yes | 100.00% | False | 0.00% | 100.00% | 100.00% | 0.00% | 100.00% | 7 | — |
| e1d-checks-32b-prod30 | play_in_progress | 17/12 | 66.67% | 58.82% | 7.84% | yes | 55.00% | True | 29.41% | 42.86% | 60.00% | 10.00% | 70.59% | 1 | — |
| e1d-checks-32b-prod30 | ball_near_player | 15/13 | 61.54% | 53.33% | 8.21% | no | 85.00% | True | 13.33% | 0.00% | 0.00% | 71.43% | 86.67% | 1 | — |
| e1d-checks-32b-prod30 | player_touches_ball | 15/15 | 60.00% | 60.00% | 0.00% | no | 100.00% | False | 0.00% | 0.00% | N/A | 100.00% | 100.00% | 5 | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-32b-prod30 | player_running | 13/10 | 70.00% | 69.23% | 0.77% | yes | 55.00% | False | 23.08% | 33.33% | 75.00% | 0.00% | 76.92% | 1 | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-32b-prod30 | kit_color_seen | 20/18 | 100.00% | 94.44% | 5.56% | red | 95.00% | False | 10.00% | N/A | N/A | N/A | 90.00% | 0 | — |
| e1d-checks-27b-dense | player_on_pitch | 19/19 | 68.42% | 63.16% | 5.26% | yes | 95.00% | False | 0.00% | 85.71% | 100.00% | 0.00% | 100.00% | 6 | — |
| e1d-checks-27b-dense | play_in_progress | 17/17 | 82.35% | 58.82% | 23.53% | yes | 75.00% | True | 0.00% | 42.86% | 100.00% | 0.00% | 100.00% | 3 | — |
| e1d-checks-27b-dense | ball_near_player | 15/13 | 38.46% | 53.33% | -14.87% | no | 80.00% | False | 13.33% | 12.50% | 0.00% | 100.00% | 86.67% | 1 | — |
| e1d-checks-27b-dense | player_touches_ball | 15/15 | 60.00% | 60.00% | 0.00% | no | 95.00% | False | 0.00% | 0.00% | N/A | 100.00% | 100.00% | 2 | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-27b-dense | player_running | 13/13 | 69.23% | 69.23% | 0.00% | yes | 70.00% | False | 0.00% | 44.44% | 100.00% | 0.00% | 100.00% | 0 | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-27b-dense | kit_color_seen | 20/18 | 94.44% | 94.44% | 0.00% | red | 100.00% | False | 10.00% | N/A | N/A | N/A | 90.00% | 1 | — |
| e1d-checks-27b-prod30 | player_on_pitch | 19/19 | 63.16% | 63.16% | 0.00% | yes | 100.00% | False | 0.00% | 100.00% | 100.00% | 0.00% | 100.00% | 7 | — |
| e1d-checks-27b-prod30 | play_in_progress | 17/15 | 73.33% | 58.82% | 14.51% | yes | 85.00% | True | 11.76% | 57.14% | 100.00% | 0.00% | 88.24% | 4 | — |
| e1d-checks-27b-prod30 | ball_near_player | 15/15 | 53.33% | 53.33% | 0.00% | no | 100.00% | False | 0.00% | 0.00% | 0.00% | 100.00% | 100.00% | 1 | — |
| e1d-checks-27b-prod30 | player_touches_ball | 15/7 | 85.71% | 60.00% | 25.71% | unclear | 60.00% | True | 53.33% | 0.00% | N/A | 16.67% | 46.67% | 0 | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-27b-prod30 | player_running | 13/8 | 62.50% | 69.23% | -6.73% | yes | 55.00% | False | 38.46% | 33.33% | 50.00% | 0.00% | 61.54% | 0 | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-27b-prod30 | kit_color_seen | 20/18 | 88.89% | 94.44% | -5.56% | red | 95.00% | False | 10.00% | N/A | N/A | N/A | 90.00% | 2 | — |

Per-question deltas in percentage points versus 8b_dense (same metric denominators as above):

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
| e1d-checks-32b-dense | player_on_pitch | +5.26 | +0.00 | -14.29 | +0.00 | — |
| e1d-checks-32b-dense | play_in_progress | +3.43 | +29.41 | +0.00 | +10.00 | — |
| e1d-checks-32b-dense | ball_near_player | -10.48 | -6.67 | +12.50 | -14.29 | — |
| e1d-checks-32b-dense | player_touches_ball | +0.00 | +0.00 | +0.00 | N/A | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-32b-dense | player_running | +23.08 | +0.00 | -33.33 | +0.00 | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-32b-dense | kit_color_seen | +0.00 | +0.00 | N/A | N/A | — |
| e1d-checks-32b-prod30 | player_on_pitch | +0.00 | +0.00 | +0.00 | +0.00 | — |
| e1d-checks-32b-prod30 | play_in_progress | -21.57 | +29.41 | +28.57 | -30.00 | — |
| e1d-checks-32b-prod30 | ball_near_player | +4.40 | +6.67 | +0.00 | -14.29 | — |
| e1d-checks-32b-prod30 | player_touches_ball | +0.00 | +0.00 | +0.00 | N/A | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-32b-prod30 | player_running | +39.23 | +23.08 | -66.67 | -25.00 | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-32b-prod30 | kit_color_seen | +5.56 | +0.00 | N/A | N/A | — |
| e1d-checks-27b-dense | player_on_pitch | +5.26 | +0.00 | -14.29 | +0.00 | — |
| e1d-checks-27b-dense | play_in_progress | -5.88 | +0.00 | +28.57 | +10.00 | — |
| e1d-checks-27b-dense | ball_near_player | -18.68 | +6.67 | +12.50 | -14.29 | — |
| e1d-checks-27b-dense | player_touches_ball | +0.00 | +0.00 | +0.00 | N/A | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-27b-dense | player_running | +38.46 | +0.00 | -55.56 | +0.00 | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-27b-dense | kit_color_seen | +0.00 | +0.00 | N/A | N/A | — |
| e1d-checks-27b-prod30 | player_on_pitch | +0.00 | +0.00 | +0.00 | +0.00 | — |
| e1d-checks-27b-prod30 | play_in_progress | -14.90 | +11.76 | +42.86 | +10.00 | — |
| e1d-checks-27b-prod30 | ball_near_player | -3.81 | -6.67 | +0.00 | -14.29 | — |
| e1d-checks-27b-prod30 | player_touches_ball | +25.71 | +53.33 | +0.00 | N/A | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-27b-prod30 | player_running | +31.73 | +38.46 | -66.67 | -50.00 | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-27b-prod30 | kit_color_seen | -5.56 | +0.00 | N/A | N/A | — |

Touch recall (raw counts retained; null recall is not a detector score):

| Run | Raw affirmative touches | Recall | Sampling confound |
|---|---:|---|---|
| e1d-checks-dense | 0/6 | N/A | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-prod30 | 0/6 | N/A | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-32b-dense | 0/6 | N/A | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-32b-prod30 | 0/6 | N/A | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-27b-dense | 0/6 | N/A | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-27b-prod30 | 0/6 | N/A | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |

Six truth-positive touch clips — answers/confidence and measured mean still spacing (single frame has no inter-still interval):

| Clip | 8b_dense | 8b_prod30 | 32b_dense | 32b_prod30 | 27b_dense | 27b_prod30 | Confound |
|---|---|---|---|---|---|---|---|
| m04-n03-t1406-157170-158922 | no/high; 1.58 s | no/high; single/missing frame | no/high; 1.58 s | no/low; single/missing frame | no/high; 1.58 s | unclear/medium; single/missing frame | Temporal sampling; raw no/unclear is not evidence of inability to detect a visible touch. Reviewed dataset: dense true-touch still spacing is 1.58–6.62 s; run-wide mean spacing is 2.49 s dense and 23.99 s sparse. Review estimate: a perfect detector would score approximately 1/6 dense and 0/6 sparse, making the 2/6 crop scheduling rule 'unattainable by construction' under that assumption. This is not a measured detector bound: spacing alone cannot establish visibility, a perfect-detector score or mathematical impossibility. Human touch timestamps and frame-level visibility labels are still needed. |
| m04-n04-t3006-243433-247994 | no/high; 4.14 s | no/high; 45.51 s | no/high; 4.14 s | no/high; 45.51 s | no/medium; 4.14 s | unclear/low; 45.51 s | Temporal sampling; raw no/unclear is not evidence of inability to detect a visible touch. Reviewed dataset: dense true-touch still spacing is 1.58–6.62 s; run-wide mean spacing is 2.49 s dense and 23.99 s sparse. Review estimate: a perfect detector would score approximately 1/6 dense and 0/6 sparse, making the 2/6 crop scheduling rule 'unattainable by construction' under that assumption. This is not a measured detector bound: spacing alone cannot establish visibility, a perfect-detector score or mathematical impossibility. Human touch timestamps and frame-level visibility labels are still needed. |
| m04-n12-t1411-237107-242145 | no/high; 4.57 s | no/high; 50.28 s | no/high; 4.57 s | no/high; 50.28 s | no/medium; 4.57 s | unclear/low; 50.28 s | Temporal sampling; raw no/unclear is not evidence of inability to detect a visible touch. Reviewed dataset: dense true-touch still spacing is 1.58–6.62 s; run-wide mean spacing is 2.49 s dense and 23.99 s sparse. Review estimate: a perfect detector would score approximately 1/6 dense and 0/6 sparse, making the 2/6 crop scheduling rule 'unattainable by construction' under that assumption. This is not a measured detector bound: spacing alone cannot establish visibility, a perfect-detector score or mathematical impossibility. Human touch timestamps and frame-level visibility labels are still needed. |
| m04-n15-t3010-164698-170777 | no/high; 5.52 s | no/high; 30.35 s | no/high; 5.52 s | no/high; 30.35 s | no/high; 5.52 s | unclear/low; 30.35 s | Temporal sampling; raw no/unclear is not evidence of inability to detect a visible touch. Reviewed dataset: dense true-touch still spacing is 1.58–6.62 s; run-wide mean spacing is 2.49 s dense and 23.99 s sparse. Review estimate: a perfect detector would score approximately 1/6 dense and 0/6 sparse, making the 2/6 crop scheduling rule 'unattainable by construction' under that assumption. This is not a measured detector bound: spacing alone cannot establish visibility, a perfect-detector score or mathematical impossibility. Human touch timestamps and frame-level visibility labels are still needed. |
| m04-n17-t717-253073-260377 | no/high; 6.62 s | no/high; 36.43 s | no/high; 6.62 s | no/high; 36.43 s | no/medium; 6.62 s | unclear/low; 36.43 s | Temporal sampling; raw no/unclear is not evidence of inability to detect a visible touch. Reviewed dataset: dense true-touch still spacing is 1.58–6.62 s; run-wide mean spacing is 2.49 s dense and 23.99 s sparse. Review estimate: a perfect detector would score approximately 1/6 dense and 0/6 sparse, making the 2/6 crop scheduling rule 'unattainable by construction' under that assumption. This is not a measured detector bound: spacing alone cannot establish visibility, a perfect-detector score or mathematical impossibility. Human touch timestamps and frame-level visibility labels are still needed. |
| m04-n17-t717-416826-418915 | no/high; 1.88 s | no/high; single/missing frame | no/high; 1.88 s | no/high; single/missing frame | no/medium; 1.88 s | no/medium; single/missing frame | Temporal sampling; raw no/unclear is not evidence of inability to detect a visible touch. Reviewed dataset: dense true-touch still spacing is 1.58–6.62 s; run-wide mean spacing is 2.49 s dense and 23.99 s sparse. Review estimate: a perfect detector would score approximately 1/6 dense and 0/6 sparse, making the 2/6 crop scheduling rule 'unattainable by construction' under that assumption. This is not a measured detector bound: spacing alone cannot establish visibility, a perfect-detector score or mathematical impossibility. Human touch timestamps and frame-level visibility labels are still needed. |

Every saved touch answer across the nine runs is no/unclear, but 12 frames spread over a long window leave multi-second gaps while a touch lasts a fraction of a second. The inspected n12 middle crop is clear and contains no nearby ball. Raw 0/6 is not evidence that the model cannot see a touch: these frames rarely contain one, and touch recall is not measurable at this sampling. Wide-frame on-pitch/sideline results retain context; crop on-pitch and ball-near results have a spatial confound. Follow-up: moment windows — at least 8 frames at at least 4 fps in the 2 s around a human-marked touch time; MJ must mark touch times on the six clips. No new inference in r2.

5 truth cells corrected. Pooled false-yes gate numbers unchanged. The headline changes: gate 2 now requires measurable recall as well as low false-yes, so its former false-yes-only PASS is WITHHELD at this sampling. Macro accuracies and per-question metrics changed as listed; raw touch counts remain visible. The requested information heuristic can flag selective-abstention outputs despite zero affirmative touches; it is not a calibrated measure of visual information.


Shared scored clips: 20. Comparison accuracy/error rates use shared IDs scored in every saved report and current rescoring. Modal distributions, majority baselines, touch counts/recall and temporal sampling use each full run, so abstention or another run's failure cannot remove valid answers or touch positives from those denominators. Full-run reports retain every attempt. Frame facts use all raw attempts. Configured wall caps alone do not imply an incomplete run.

Accuracy = correct / graded answered (unclear excluded). Abstain = unclear / eligible; coverage = graded answered / eligible. Binary eligibility requires yes/no truth. Kit eligibility follows lane A: uncertain kit truth forces abstention even for an asserted colour. False-yes = yes / truth-no cells; false-no = no / truth-yes cells, including abstentions in those truth denominators. Kit has no yes/no rates. Macro accuracy averages available accuracies across six questions; macro false-yes averages available rates across five binary questions; overall abstain is pooled over eligible cells. Gate 1 pools player_on_pitch and play_in_progress over off-pitch clips (14 cells on full set); Gate 2 uses player_touches_ball over off-pitch or idle clips with truth no (9 clips; mixed receive excluded). Modal answer/share uses every valid answer, including unclear and ungraded cells; ties sort lexically. Majority baseline uses all selected graded truth classes (uncertain kit excluded), independent of abstention; information requires modal share <90% and accuracy > baseline +5 percentage points. Gate 1 also splits its two questions. Gate 2 requires false-yes <=10% AND measurable touch recall >=50%. Raw recall = yes / all selected truth-positive clips, counting unclear/failed reads as misses. Touch recall is null when mean spacing >1s or sampling metadata is missing; raw counts remain. Accuracy metrics exclude failed reads; attempted/scored/failed counts remain visible. Thinking rate and wall/clip include all attempts. Reasons are logged only, never scored.

Mixed settings explicitly allowed: {"27b_dense": {"model": "qwen3.8:27b-obliterated-q8"}, "27b_prod30": {"model": "qwen3.8:27b-obliterated-q8"}, "32b_dense": {"model": "qwen3-vl:32b"}, "32b_prod30": {"model": "qwen3-vl:32b"}}; scoring uses supplied truth.

| Run | Model | Boxed frames/attempt | Scored/failed | Wall s/clip (all attempts) | Macro accuracy | Macro false-yes | Abstain | From thinking (all attempts) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| e1d-checks-dense | qwen3-vl:8b | 11.9 | 20/0 | 51.651 | 65.62% | 42.86% | 3.03% | 100.00% |
| e1d-checks-prod30 | qwen3-vl:8b | 1.45 | 20/0 | 10.547 | 62.81% | 35.56% | 8.08% | 100.00% |
| e1d-checks-32b-dense | qwen3-vl:32b | 11.9 | 20/0 | 216.428 | 69.17% | 35.83% | 7.07% | 100.00% |
| e1d-checks-32b-prod30 | qwen3-vl:32b | 1.45 | 20/0 | 39.580 | 70.23% | 35.24% | 12.12% | 100.00% |
| e1d-checks-27b-dense | qwen3.8:27b-obliterated-q8 | 11.9 | 20/0 | 172.788 | 68.82% | 37.10% | 4.04% | 0.00% |
| e1d-checks-27b-prod30 | qwen3.8:27b-obliterated-q8 | 1.45 | 20/0 | 87.783 | 71.15% | 38.10% | 17.17% | 0.00% |

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
| e1d-checks-32b-dense | off_pitch_false_yes_rate | <= 10.00% | 50.00% | FAIL | — |
| e1d-checks-32b-dense | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-32b-dense | touch_recall | >= 50.00% | N/A | WITHHELD | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-32b-dense | macro_accuracy | >= 80.00% | 69.17% | FAIL | — |
| e1d-checks-32b-dense | abstain_rate | <= 40.00% | 7.07% | PASS | — |
| e1d-checks-32b-dense | gate2 | touch false-yes <=10% AND measurable touch recall >=50% | N/A | WITHHELD | not measurable at this sampling: mean frame spacing exceeds 1.0 s |
| e1d-checks-32b-prod30 | off_pitch_false_yes_rate | <= 10.00% | 71.43% | FAIL | — |
| e1d-checks-32b-prod30 | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-32b-prod30 | touch_recall | >= 50.00% | N/A | WITHHELD | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-32b-prod30 | macro_accuracy | >= 80.00% | 70.23% | FAIL | — |
| e1d-checks-32b-prod30 | abstain_rate | <= 40.00% | 12.12% | PASS | — |
| e1d-checks-32b-prod30 | gate2 | touch false-yes <=10% AND measurable touch recall >=50% | N/A | WITHHELD | not measurable at this sampling: mean frame spacing exceeds 1.0 s |
| e1d-checks-27b-dense | off_pitch_false_yes_rate | <= 10.00% | 64.29% | FAIL | — |
| e1d-checks-27b-dense | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-27b-dense | touch_recall | >= 50.00% | N/A | WITHHELD | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-27b-dense | macro_accuracy | >= 80.00% | 68.82% | FAIL | — |
| e1d-checks-27b-dense | abstain_rate | <= 40.00% | 4.04% | PASS | — |
| e1d-checks-27b-dense | gate2 | touch false-yes <=10% AND measurable touch recall >=50% | N/A | WITHHELD | not measurable at this sampling: mean frame spacing exceeds 1.0 s |
| e1d-checks-27b-prod30 | off_pitch_false_yes_rate | <= 10.00% | 78.57% | FAIL | — |
| e1d-checks-27b-prod30 | off_pitch_idle_touch_false_yes_rate | <= 10.00% | 0.00% | PASS | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-27b-prod30 | touch_recall | >= 50.00% | N/A | WITHHELD | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| e1d-checks-27b-prod30 | macro_accuracy | >= 80.00% | 71.15% | FAIL | — |
| e1d-checks-27b-prod30 | abstain_rate | <= 40.00% | 17.17% | PASS | — |
| e1d-checks-27b-prod30 | gate2 | touch false-yes <=10% AND measurable touch recall >=50% | N/A | WITHHELD | not measurable at this sampling: mean frame spacing exceeds 1.0 s |

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
| m04-n02-t3005-474114-478131 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n02-t3005-474114-478131 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n02-t3005-474114-478131 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / medium | yes / high | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n02-t3005-474114-478131 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n03-t1406-157170-158922 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n03-t1406-157170-158922 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n03-t1406-157170-158922 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n03-t1406-157170-158922 | e1d-checks-32b-prod30 | scored | yes / high | no / medium | no / low | no / low | unclear / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n03-t1406-157170-158922 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n03-t1406-157170-158922 | e1d-checks-27b-prod30 | scored | yes / high | yes / medium | no / high | unclear / medium | no / high | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n03-t1406-385962-387137 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n03-t1406-385962-387137 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n03-t1406-385962-387137 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n03-t1406-385962-387137 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n03-t1406-385962-387137 | e1d-checks-27b-dense | scored | yes / high | no / medium | unclear / low | no / medium | no / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n03-t1406-385962-387137 | e1d-checks-27b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n04-t3006-243433-247994 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n04-t3006-243433-247994 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | blue / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n04-t3006-243433-247994 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n04-t3006-243433-247994 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n04-t3006-243433-247994 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / medium | yes / high | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n04-t3006-243433-247994 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n04-t3006-307417-310307 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n04-t3006-307417-310307 | e1d-checks-prod30 | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n04-t3006-307417-310307 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n04-t3006-307417-310307 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n04-t3006-307417-310307 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n04-t3006-307417-310307 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n05-t3007-284945-287898 | e1d-checks-dense | scored | yes / high | yes / high | no / medium | no / low | yes / high | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n05-t3007-284945-287898 | e1d-checks-prod30 | scored | yes / high | yes / high | no / medium | no / low | yes / high | blue / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n05-t3007-284945-287898 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n05-t3007-284945-287898 | e1d-checks-32b-prod30 | scored | yes / high | yes / high | no / medium | no / high | yes / high | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n05-t3007-284945-287898 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n05-t3007-284945-287898 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | unclear / low | yellow / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-143096-143834 | e1d-checks-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-143096-143834 | e1d-checks-prod30 | scored | no / high | yes / medium | no / high | no / high | no / high | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-143096-143834 | e1d-checks-32b-dense | scored | no / high | yes / high | no / high | no / high | no / high | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-143096-143834 | e1d-checks-32b-prod30 | scored | yes / high | no / medium | no / low | no / low | no / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-143096-143834 | e1d-checks-27b-dense | scored | no / high | yes / high | no / high | no / high | no / high | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-143096-143834 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | no / high | no / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-297601-298865 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-297601-298865 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-297601-298865 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-297601-298865 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-297601-298865 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | unclear / low | yes / high | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-297601-298865 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | no / medium | unclear / low | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-385922-386603 | e1d-checks-dense | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-385922-386603 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-385922-386603 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-385922-386603 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-385922-386603 | e1d-checks-27b-dense | scored | yes / high | no / medium | unclear / low | no / medium | no / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n09-t1409-385922-386603 | e1d-checks-27b-prod30 | scored | yes / high | unclear / low | no / high | no / high | unclear / low | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n10-t711-186553-188161 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n10-t711-186553-188161 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | blue / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n10-t711-186553-188161 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n10-t711-186553-188161 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / high | no / high | no / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n10-t711-186553-188161 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n10-t711-186553-188161 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | no / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n12-t1411-237107-242145 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n12-t1411-237107-242145 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n12-t1411-237107-242145 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n12-t1411-237107-242145 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n12-t1411-237107-242145 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / medium | yes / high | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n12-t1411-237107-242145 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n12-t1411-679986-681985 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n12-t1411-679986-681985 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n12-t1411-679986-681985 | e1d-checks-32b-dense | scored | yes / high | no / medium | yes / high | no / medium | no / high | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n12-t1411-679986-681985 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / high | no / high | no / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n12-t1411-679986-681985 | e1d-checks-27b-dense | scored | yes / high | no / medium | yes / high | no / medium | no / high | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n12-t1411-679986-681985 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | no / high | unclear / low | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n15-t3010-164698-170777 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n15-t3010-164698-170777 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n15-t3010-164698-170777 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n15-t3010-164698-170777 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | no / medium | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n15-t3010-164698-170777 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n15-t3010-164698-170777 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-253073-260377 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-253073-260377 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-253073-260377 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-253073-260377 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-253073-260377 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / medium | yes / high | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-253073-260377 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-304624-307834 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-304624-307834 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-304624-307834 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-304624-307834 | e1d-checks-32b-prod30 | scored | yes / high | unclear / low | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-304624-307834 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-304624-307834 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-416826-418915 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-416826-418915 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-416826-418915 | e1d-checks-32b-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-416826-418915 | e1d-checks-32b-prod30 | scored | yes / high | yes / high | no / medium | no / high | yes / high | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-416826-418915 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / medium | yes / high | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n17-t717-416826-418915 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | no / medium | yes / high | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n21-t3011-390297-390800 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n21-t3011-390297-390800 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | no / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n21-t3011-390297-390800 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | no / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n21-t3011-390297-390800 | e1d-checks-32b-prod30 | scored | yes / high | no / medium | no / high | no / high | no / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n21-t3011-390297-390800 | e1d-checks-27b-dense | scored | yes / high | no / medium | no / high | no / high | no / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n21-t3011-390297-390800 | e1d-checks-27b-prod30 | scored | yes / high | no / medium | no / high | no / medium | no / high | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n22-t3012-070707-074371 | e1d-checks-dense | scored | yes / high | no / medium | yes / high | no / low | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n22-t3012-070707-074371 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n22-t3012-070707-074371 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n22-t3012-070707-074371 | e1d-checks-32b-prod30 | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n22-t3012-070707-074371 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n22-t3012-070707-074371 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | unclear / low | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n24-t3013-679939-681217 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n24-t3013-679939-681217 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | black / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n24-t3013-679939-681217 | e1d-checks-32b-dense | scored | yes / high | no / medium | no / high | no / high | no / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n24-t3013-679939-681217 | e1d-checks-32b-prod30 | scored | yes / high | no / medium | no / low | no / high | no / medium | black / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n24-t3013-679939-681217 | e1d-checks-27b-dense | scored | yes / high | no / medium | yes / high | no / medium | no / high | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n24-t3013-679939-681217 | e1d-checks-27b-prod30 | scored | yes / high | yes / medium | no / high | unclear / medium | yes / high | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n25-t3014-530600-532465 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n25-t3014-530600-532465 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n25-t3014-530600-532465 | e1d-checks-32b-dense | scored | yes / high | unclear / low | no / high | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n25-t3014-530600-532465 | e1d-checks-32b-prod30 | scored | yes / high | yes / high | no / medium | no / high | yes / high | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n25-t3014-530600-532465 | e1d-checks-27b-dense | scored | yes / high | yes / high | no / medium | no / high | yes / medium | red / high | Temporal confound: mean spacing 2.49 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |
| m04-n25-t3014-530600-532465 | e1d-checks-27b-prod30 | scored | yes / high | yes / high | no / medium | no / medium | yes / medium | red / high | Temporal confound: mean spacing 23.99 s; touch recall not measurable at this sampling: mean frame spacing exceeds 1.0 s. Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition. |

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

- 8b / schema: JSON field=message.thinking; content empty=True; validates=True; selected=message.thinking; done_reason=stop; error=none.
- 8b / json: JSON field=message.thinking; content empty=True; validates=True; selected=message.thinking; done_reason=stop; error=none.
- 8b / none: JSON field=none; content empty=True; validates=False; selected=message.thinking; done_reason=length; error=none.
- 32b / schema: JSON field=message.thinking; content empty=True; validates=True; selected=message.thinking; done_reason=stop; error=none.
- 32b / json: JSON field=message.thinking; content empty=True; validates=True; selected=message.thinking; done_reason=stop; error=none.
- 32b / none: JSON field=none; content empty=True; validates=False; selected=message.thinking; done_reason=length; error=none.
- 27b / schema: JSON field=message.content; content empty=False; validates=True; selected=message.content; done_reason=stop; error=none.
- 27b / json: JSON field=message.content; content empty=False; validates=False; selected=message.content; done_reason=stop; error=none.
- 27b / none: JSON field=message.content; content empty=False; validates=False; selected=message.content; done_reason=stop; error=none.

Model/frame facts from run.json and raw attempts:

- 8b_dense: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frames_per_second_of_window": {"mean": 0.7109915728989717, "min": 0.16429353778751377}, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "mean_spacing_s": 2.4899898989899, "model": "qwen3-vl:8b", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- 8b_prod30: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frames_per_second_of_window": {"mean": 0.0701758236166358, "min": 0.033863867253640136}, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "mean_spacing_s": 23.98825000000001, "model": "qwen3-vl:8b", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}
- 32b_dense: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frames_per_second_of_window": {"mean": 0.7109915728989717, "min": 0.16429353778751377}, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "mean_spacing_s": 2.4899898989899, "model": "qwen3-vl:32b", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- 32b_prod30: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frames_per_second_of_window": {"mean": 0.0701758236166358, "min": 0.033863867253640136}, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "mean_spacing_s": 23.98825000000001, "model": "qwen3-vl:32b", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}
- 27b_dense: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frames_per_second_of_window": {"mean": 0.7109915728989717, "min": 0.16429353778751377}, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "mean_spacing_s": 2.4899898989899, "model": "qwen3.8:27b-obliterated-q8", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- 27b_prod30: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frames_per_second_of_window": {"mean": 0.0701758236166358, "min": 0.033863867253640136}, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "mean_spacing_s": 23.98825000000001, "model": "qwen3.8:27b-obliterated-q8", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}

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
| e1d-checks-32b-dense | 0.7109915728989717 | 0.16429353778751377 | 2.4899898989899 | not measurable at this sampling: mean frame spacing exceeds 1.0 s |
| e1d-checks-32b-prod30 | 0.0701758236166358 | 0.033863867253640136 | 23.98825000000001 | not measurable at this sampling: mean frame spacing exceeds 1.0 s |
| e1d-checks-27b-dense | 0.7109915728989717 | 0.16429353778751377 | 2.4899898989899 | not measurable at this sampling: mean frame spacing exceeds 1.0 s |
| e1d-checks-27b-prod30 | 0.0701758236166358 | 0.033863867253640136 | 23.98825000000001 | not measurable at this sampling: mean frame spacing exceeds 1.0 s |

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
  }
}
```

Execution/gates:

```json
{
  "round": "r3; code/ledger only; no new inference",
  "base_commit": "b96e6b2",
  "historical_execution": {
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
    "experiment": "E1d lane B \u2014 unchanged checks, three-model comparison (8B / 32B / 27B)",
    "base_commit": "78b7643c",
    "thinking_channel_diagnostic": {
      "clip_id": "m04-n12-t1411-237107-242145",
      "model": "qwen3.8:27b-obliterated-q8",
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
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-00.jpg",
          "t": 2371.12,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2371.12,
          "sampling_shift_s": 0.0,
          "sha256": "f20ef87f0d917e203f2b5c807a8f133c6d57eb7d35f9e5818d1656af1a6e3091"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-01.jpg",
          "t": 2375.691,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2375.691,
          "sampling_shift_s": 0.0,
          "sha256": "98a1da458e1175777b79536d238643bcce868d593bbb92683c3971af18957245"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-02.jpg",
          "t": 2380.262,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2380.262,
          "sampling_shift_s": 0.0,
          "sha256": "e19fdb7d839de9e9ae89b223cd61fef1f82deb6ee9f113b08f2f58996c11adc9"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-03.jpg",
          "t": 2384.833,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2384.833,
          "sampling_shift_s": 0.0,
          "sha256": "4ab2524c9e96e49c307a0e3fb980973dd0817a2324262eda4fb6cfa9631a4e45"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-04.jpg",
          "t": 2389.404,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2389.404,
          "sampling_shift_s": 0.0,
          "sha256": "bfe74bd2998dfb232fa913c2483ed02af0a69461c1c254bbc8f8a19572d26041"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-05.jpg",
          "t": 2393.975,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2393.975,
          "sampling_shift_s": 0.0,
          "sha256": "e8080e71d4040c287a3495026a46fe90c97a4a0104803df0ebd186884a0730b2"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-06.jpg",
          "t": 2398.545,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2398.545,
          "sampling_shift_s": 0.0,
          "sha256": "9295c6361175368f80814da708c7f7767f3e9b193eeaad2e0a39c79f67a04362"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-07.jpg",
          "t": 2403.6,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2403.116,
          "sampling_shift_s": 0.484,
          "sha256": "3a2c2e7c2a3e376b732c5c4fb2843d33c382b5303f20852ec0e72c3ef6e0e268"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-08.jpg",
          "t": 2407.687,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2407.687,
          "sampling_shift_s": 0.0,
          "sha256": "fd839f08c1717586566e226d563ea4ae5a7f3d93bc563f582988a1e827d2ea5b"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-09.jpg",
          "t": 2412.258,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2412.258,
          "sampling_shift_s": 0.0,
          "sha256": "437f6cf74ef3c834bc11ca3a4d8bd840b02d9c5781458a1f449f7e6602c2423f"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-10.jpg",
          "t": 2416.829,
          "sent_w": 1280,
          "sent_h": 720,
          "target_t": 2416.829,
          "sampling_shift_s": 0.0,
          "sha256": "fe12f40b2d73c7609981a7586b91243dc43d6a7b149c8da150731fd87b20fc8c"
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-11.jpg",
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
          "wall_s": 143.705,
          "json_field": "message.content",
          "json_fields": [
            "message.content"
          ],
          "content_empty": false,
          "content_missing": false,
          "validated": true,
          "validation_by_field": {
            "content": true,
            "thinking": false
          },
          "selected_field": "message.content",
          "message": {
            "role": "assistant",
            "content": "{\n  \"player_on_pitch\": {\n    \"answer\": \"yes\",\n    \"confidence\": \"high\",\n    \"reason\": \"Visible on the field of play\"\n  },\n  \"play_in_progress\": {\n    \"answer\": \"yes\",\n    \"confidence\": \"high\",\n    \"reason\": \"Active match play observed\"\n  },\n  \"ball_near_player\": {\n    \"answer\": \"no\",\n    \"confidence\": \"medium\",\n    \"reason\": \"Ball not within two body-lengths\"\n  },\n  \"player_touches_ball\": {\n    \"answer\": \"no\",\n    \"confidence\": \"medium\",\n    \"reason\": \"No clear ball contact visible\"\n  },\n  \"player_running\": {\n    \"answer\": \"yes\",\n    \"confidence\": \"high\",\n    \"reason\": \"Running motion clearly seen\"\n  },\n  \"kit_color_seen\": {\n    \"answer\": \"red\",\n    \"confidence\": \"high\",\n    \"reason\": \"Red jersey and black shorts\"\n  }\n}"
          },
          "done_reason": "stop",
          "error": null
        },
        {
          "format_mode": "json",
          "wall_s": 28.152,
          "json_field": "message.content",
          "json_fields": [
            "message.content"
          ],
          "content_empty": false,
          "content_missing": false,
          "validated": false,
          "validation_by_field": {
            "content": false,
            "thinking": false
          },
          "selected_field": "message.content",
          "message": {
            "role": "assistant",
            "content": "{\n  \"checks\": [\n    {\n      \"answer\": \"yes\",\n      \"confidence\": \"high\",\n      \"reason\": \"Visible on pitch\"\n    },\n    {\n      \"answer\": \"yes\",\n      \"confidence\": \"high\",\n      \"reason\": \"Active play observed\"\n    },\n    {\n      \"answer\": \"no\",\n      \"confidence\": \"medium\",\n      \"reason\": \"Ball stays distant\"\n    },\n    {\n      \"answer\": \"unclear\",\n      \"confidence\": \"low\",\n      \"reason\": \"No clear ball contact\"\n    },\n    {\n      \"answer\": \"yes\",\n      \"confidence\": \"medium\",\n      \"reason\": \"Running motion visible\"\n    },\n    {\n      \"answer\": \"red\",\n      \"confidence\": \"high\",\n      \"reason\": \"Red shirt and shorts\"\n    }\n  ]\n}"
          },
          "done_reason": "stop",
          "error": null
        },
        {
          "format_mode": "none",
          "wall_s": 28.785,
          "json_field": "message.content",
          "json_fields": [
            "message.content"
          ],
          "content_empty": false,
          "content_missing": false,
          "validated": false,
          "validation_by_field": {
            "content": false,
            "thinking": false
          },
          "selected_field": "message.content",
          "message": {
            "role": "assistant",
            "content": "{\n  \"checks\": [\n    {\n      \"answer\": \"yes\",\n      \"confidence\": \"high\",\n      \"reason\": \"Visible on pitch\"\n    },\n    {\n      \"answer\": \"yes\",\n      \"confidence\": \"high\",\n      \"reason\": \"Active play observed\"\n    },\n    {\n      \"answer\": \"no\",\n      \"confidence\": \"medium\",\n      \"reason\": \"Ball stays distant\"\n    },\n    {\n      \"answer\": \"unclear\",\n      \"confidence\": \"low\",\n      \"reason\": \"No clear ball contact\"\n    },\n    {\n      \"answer\": \"yes\",\n      \"confidence\": \"medium\",\n      \"reason\": \"Running motion visible\"\n    },\n    {\n      \"answer\": \"red\",\n      \"confidence\": \"high\",\n      \"reason\": \"Red shirt and shorts\"\n    }\n  ]\n}"
          },
          "done_reason": "stop",
          "error": null
        }
      ],
      "scope": "Three single requests, identical dense frames and prompt, only format varies. Raw message fields retained. No repairs, retries or shared-transport changes."
    },
    "thinking_channel_diagnostics": {
      "8b": {
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
      "32b": {
        "clip_id": "m04-n12-t1411-237107-242145",
        "model": "qwen3-vl:32b",
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
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-e93n8w67/frame-00.jpg",
            "t": 2371.12,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2371.12,
            "sampling_shift_s": 0.0,
            "sha256": "f20ef87f0d917e203f2b5c807a8f133c6d57eb7d35f9e5818d1656af1a6e3091"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-e93n8w67/frame-01.jpg",
            "t": 2375.691,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2375.691,
            "sampling_shift_s": 0.0,
            "sha256": "98a1da458e1175777b79536d238643bcce868d593bbb92683c3971af18957245"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-e93n8w67/frame-02.jpg",
            "t": 2380.262,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2380.262,
            "sampling_shift_s": 0.0,
            "sha256": "e19fdb7d839de9e9ae89b223cd61fef1f82deb6ee9f113b08f2f58996c11adc9"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-e93n8w67/frame-03.jpg",
            "t": 2384.833,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2384.833,
            "sampling_shift_s": 0.0,
            "sha256": "4ab2524c9e96e49c307a0e3fb980973dd0817a2324262eda4fb6cfa9631a4e45"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-e93n8w67/frame-04.jpg",
            "t": 2389.404,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2389.404,
            "sampling_shift_s": 0.0,
            "sha256": "bfe74bd2998dfb232fa913c2483ed02af0a69461c1c254bbc8f8a19572d26041"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-e93n8w67/frame-05.jpg",
            "t": 2393.975,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2393.975,
            "sampling_shift_s": 0.0,
            "sha256": "e8080e71d4040c287a3495026a46fe90c97a4a0104803df0ebd186884a0730b2"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-e93n8w67/frame-06.jpg",
            "t": 2398.545,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2398.545,
            "sampling_shift_s": 0.0,
            "sha256": "9295c6361175368f80814da708c7f7767f3e9b193eeaad2e0a39c79f67a04362"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-e93n8w67/frame-07.jpg",
            "t": 2403.6,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2403.116,
            "sampling_shift_s": 0.484,
            "sha256": "3a2c2e7c2a3e376b732c5c4fb2843d33c382b5303f20852ec0e72c3ef6e0e268"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-e93n8w67/frame-08.jpg",
            "t": 2407.687,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2407.687,
            "sampling_shift_s": 0.0,
            "sha256": "fd839f08c1717586566e226d563ea4ae5a7f3d93bc563f582988a1e827d2ea5b"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-e93n8w67/frame-09.jpg",
            "t": 2412.258,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2412.258,
            "sampling_shift_s": 0.0,
            "sha256": "437f6cf74ef3c834bc11ca3a4d8bd840b02d9c5781458a1f449f7e6602c2423f"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-e93n8w67/frame-10.jpg",
            "t": 2416.829,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2416.829,
            "sampling_shift_s": 0.0,
            "sha256": "fe12f40b2d73c7609981a7586b91243dc43d6a7b149c8da150731fd87b20fc8c"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-e93n8w67/frame-11.jpg",
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
            "wall_s": 181.093,
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
              "thinking": "{\n    \"player_on_pitch\": {\n        \"answer\": \"yes\",\n        \"confidence\": \"high\",\n        \"reason\": \"Player on field in all frames\"\n    },\n    \"play_in_progress\": {\n        \"answer\": \"yes\",\n        \"confidence\": \"medium\",\n        \"reason\": \"Players moving, ball visible\"\n    },\n    \"ball_near_player\": {\n        \"answer\": \"no\",\n        \"confidence\": \"high\",\n        \"reason\": \"Ball not near player in frames\"\n    },\n    \"player_touches_ball\": {\n        \"answer\": \"no\",\n        \"confidence\": \"high\",\n        \"reason\": \"No ball contact observed\"\n    },\n    \"player_running\": {\n        \"answer\": \"yes\",\n        \"confidence\": \"medium\",\n        \"reason\": \"Player running in some frames\"\n    },\n    \"kit_color_seen\": {\n        \"answer\": \"red\",\n        \"confidence\": \"high\",\n        \"reason\": \"Red jersey visible on player\"\n    }\n}"
            },
            "done_reason": "stop",
            "error": null
          },
          {
            "format_mode": "json",
            "wall_s": 29.786,
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
              "thinking": "{\n    \"player_on_pitch\": {\n        \"answer\": \"yes\",\n        \"confidence\": \"high\",\n        \"reason\": \"Player on field in all frames\"\n    },\n    \"play_in_progress\": {\n        \"answer\": \"yes\",\n        \"confidence\": \"medium\",\n        \"reason\": \"Players moving, ball visible\"\n    },\n    \"ball_near_player\": {\n        \"answer\": \"no\",\n        \"confidence\": \"high\",\n        \"reason\": \"Ball not near player in frames\"\n    },\n    \"player_touches_ball\": {\n        \"answer\": \"no\",\n        \"confidence\": \"high\",\n        \"reason\": \"No ball contact observed\"\n    },\n    \"player_running\": {\n        \"answer\": \"yes\",\n        \"confidence\": \"medium\",\n        \"reason\": \"Player running in some frames\"\n    },\n    \"kit_color_seen\": {\n        \"answer\": \"red\",\n        \"confidence\": \"high\",\n        \"reason\": \"Red jersey visible on player\"\n    }\n}"
            },
            "done_reason": "stop",
            "error": null
          },
          {
            "format_mode": "none",
            "wall_s": 57.426,
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
              "thinking": "<think>\nSo, let's go through each question one by one for the marked player (magenta box #12).\n\nFirst, player_on_pitch: Check if the player is on the field of play. In all frames, the magenta box is on the grassy pitch area, not on the sideline or bench. So yes.\n\nplay_in_progress: The ball should be in play. Looking at the images, there's a soccer ball visible (e.g., some frames show it moving), and players are actively playing. No stoppages like walking off. So yes.\n\nball_near_player: Does the ball come within two body-lengths? Let's check each frame. In some frames, maybe not obvious, but need to see if at any point. Wait, in one of the images (like 2384.833), is there a ball near? Hmm, but let's think: do we have evidence that the ball comes close? The problem says \"at any point\" in these frames. If not clearly visible, then no or unclear. But maybe in some frame it does. Wait, need to check all.\n\nWait, for example, in image 2384.833 (fourth image), there's a ball on the field but is it near #12? Let me see: the player is running towards the action. Maybe not. But let's think again. The question says \"at any point\" during these frames. If in one of the images, the ball is close to the marked player (within two body-lengths), then yes.\n\nBut maybe it's unclear because we can't see the ball near them in all frames. Wait, but need to check each frame for presence of ball and proximity.\n\nWait, let's look at image 2384.833: there's a ball on the field (top left). The marked player is on the right side. Not sure if close"
            },
            "done_reason": "length",
            "error": null
          }
        ],
        "scope": "Three single requests, identical dense frames and prompt, only format varies. Raw message fields retained. No repairs, retries or shared-transport changes."
      },
      "27b": {
        "clip_id": "m04-n12-t1411-237107-242145",
        "model": "qwen3.8:27b-obliterated-q8",
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
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-00.jpg",
            "t": 2371.12,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2371.12,
            "sampling_shift_s": 0.0,
            "sha256": "f20ef87f0d917e203f2b5c807a8f133c6d57eb7d35f9e5818d1656af1a6e3091"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-01.jpg",
            "t": 2375.691,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2375.691,
            "sampling_shift_s": 0.0,
            "sha256": "98a1da458e1175777b79536d238643bcce868d593bbb92683c3971af18957245"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-02.jpg",
            "t": 2380.262,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2380.262,
            "sampling_shift_s": 0.0,
            "sha256": "e19fdb7d839de9e9ae89b223cd61fef1f82deb6ee9f113b08f2f58996c11adc9"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-03.jpg",
            "t": 2384.833,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2384.833,
            "sampling_shift_s": 0.0,
            "sha256": "4ab2524c9e96e49c307a0e3fb980973dd0817a2324262eda4fb6cfa9631a4e45"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-04.jpg",
            "t": 2389.404,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2389.404,
            "sampling_shift_s": 0.0,
            "sha256": "bfe74bd2998dfb232fa913c2483ed02af0a69461c1c254bbc8f8a19572d26041"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-05.jpg",
            "t": 2393.975,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2393.975,
            "sampling_shift_s": 0.0,
            "sha256": "e8080e71d4040c287a3495026a46fe90c97a4a0104803df0ebd186884a0730b2"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-06.jpg",
            "t": 2398.545,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2398.545,
            "sampling_shift_s": 0.0,
            "sha256": "9295c6361175368f80814da708c7f7767f3e9b193eeaad2e0a39c79f67a04362"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-07.jpg",
            "t": 2403.6,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2403.116,
            "sampling_shift_s": 0.484,
            "sha256": "3a2c2e7c2a3e376b732c5c4fb2843d33c382b5303f20852ec0e72c3ef6e0e268"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-08.jpg",
            "t": 2407.687,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2407.687,
            "sampling_shift_s": 0.0,
            "sha256": "fd839f08c1717586566e226d563ea4ae5a7f3d93bc563f582988a1e827d2ea5b"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-09.jpg",
            "t": 2412.258,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2412.258,
            "sampling_shift_s": 0.0,
            "sha256": "437f6cf74ef3c834bc11ca3a4d8bd840b02d9c5781458a1f449f7e6602c2423f"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-10.jpg",
            "t": 2416.829,
            "sent_w": 1280,
            "sent_h": 720,
            "target_t": 2416.829,
            "sampling_shift_s": 0.0,
            "sha256": "fe12f40b2d73c7609981a7586b91243dc43d6a7b149c8da150731fd87b20fc8c"
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/checks-format-diagnostic-kv0rdrkk/frame-11.jpg",
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
            "wall_s": 143.705,
            "json_field": "message.content",
            "json_fields": [
              "message.content"
            ],
            "content_empty": false,
            "content_missing": false,
            "validated": true,
            "validation_by_field": {
              "content": true,
              "thinking": false
            },
            "selected_field": "message.content",
            "message": {
              "role": "assistant",
              "content": "{\n  \"player_on_pitch\": {\n    \"answer\": \"yes\",\n    \"confidence\": \"high\",\n    \"reason\": \"Visible on the field of play\"\n  },\n  \"play_in_progress\": {\n    \"answer\": \"yes\",\n    \"confidence\": \"high\",\n    \"reason\": \"Active match play observed\"\n  },\n  \"ball_near_player\": {\n    \"answer\": \"no\",\n    \"confidence\": \"medium\",\n    \"reason\": \"Ball not within two body-lengths\"\n  },\n  \"player_touches_ball\": {\n    \"answer\": \"no\",\n    \"confidence\": \"medium\",\n    \"reason\": \"No clear ball contact visible\"\n  },\n  \"player_running\": {\n    \"answer\": \"yes\",\n    \"confidence\": \"high\",\n    \"reason\": \"Running motion clearly seen\"\n  },\n  \"kit_color_seen\": {\n    \"answer\": \"red\",\n    \"confidence\": \"high\",\n    \"reason\": \"Red jersey and black shorts\"\n  }\n}"
            },
            "done_reason": "stop",
            "error": null
          },
          {
            "format_mode": "json",
            "wall_s": 28.152,
            "json_field": "message.content",
            "json_fields": [
              "message.content"
            ],
            "content_empty": false,
            "content_missing": false,
            "validated": false,
            "validation_by_field": {
              "content": false,
              "thinking": false
            },
            "selected_field": "message.content",
            "message": {
              "role": "assistant",
              "content": "{\n  \"checks\": [\n    {\n      \"answer\": \"yes\",\n      \"confidence\": \"high\",\n      \"reason\": \"Visible on pitch\"\n    },\n    {\n      \"answer\": \"yes\",\n      \"confidence\": \"high\",\n      \"reason\": \"Active play observed\"\n    },\n    {\n      \"answer\": \"no\",\n      \"confidence\": \"medium\",\n      \"reason\": \"Ball stays distant\"\n    },\n    {\n      \"answer\": \"unclear\",\n      \"confidence\": \"low\",\n      \"reason\": \"No clear ball contact\"\n    },\n    {\n      \"answer\": \"yes\",\n      \"confidence\": \"medium\",\n      \"reason\": \"Running motion visible\"\n    },\n    {\n      \"answer\": \"red\",\n      \"confidence\": \"high\",\n      \"reason\": \"Red shirt and shorts\"\n    }\n  ]\n}"
            },
            "done_reason": "stop",
            "error": null
          },
          {
            "format_mode": "none",
            "wall_s": 28.785,
            "json_field": "message.content",
            "json_fields": [
              "message.content"
            ],
            "content_empty": false,
            "content_missing": false,
            "validated": false,
            "validation_by_field": {
              "content": false,
              "thinking": false
            },
            "selected_field": "message.content",
            "message": {
              "role": "assistant",
              "content": "{\n  \"checks\": [\n    {\n      \"answer\": \"yes\",\n      \"confidence\": \"high\",\n      \"reason\": \"Visible on pitch\"\n    },\n    {\n      \"answer\": \"yes\",\n      \"confidence\": \"high\",\n      \"reason\": \"Active play observed\"\n    },\n    {\n      \"answer\": \"no\",\n      \"confidence\": \"medium\",\n      \"reason\": \"Ball stays distant\"\n    },\n    {\n      \"answer\": \"unclear\",\n      \"confidence\": \"low\",\n      \"reason\": \"No clear ball contact\"\n    },\n    {\n      \"answer\": \"yes\",\n      \"confidence\": \"medium\",\n      \"reason\": \"Running motion visible\"\n    },\n    {\n      \"answer\": \"red\",\n      \"confidence\": \"high\",\n      \"reason\": \"Red shirt and shorts\"\n    }\n  ]\n}"
            },
            "done_reason": "stop",
            "error": null
          }
        ],
        "scope": "Three single requests, identical dense frames and prompt, only format varies. Raw message fields retained. No repairs, retries or shared-transport changes."
      }
    },
    "historical_32b_preflight": {
      "model": {
        "name": "qwen3-vl:32b",
        "model": "qwen3-vl:32b",
        "modified_at": "2026-09-09T20:32:20.39442735+09:00",
        "size": 20910297800,
        "digest": "ff2e46876908853b8d0872595047c46d599d970056277e4864c8a1f0fd93fd3b",
        "details": {
          "parent_model": "",
          "format": "gguf",
          "family": "qwen3vl",
          "families": [
            "qwen3vl"
          ],
          "parameter_size": "33.4B",
          "quantization_level": "Q4_K_M",
          "context_length": 262144,
          "embedding_length": 5120
        },
        "capabilities": [
          "vision",
          "completion",
          "tools",
          "thinking"
        ]
      },
      "pull": {
        "tag": "qwen3-vl:32b",
        "started_at": "2026-09-09T10:55:08.054192+00:00",
        "pull_wall_s": 2232.383,
        "exit_code": 0,
        "log": "/Users/mjjones/codex-runs/pull-qwen3vl-32b.log"
      },
      "vision_check": {
        "model": "qwen3-vl:32b",
        "wall_s": 10.029,
        "num_ctx": 65536,
        "image_sha256": "8cd751ba4b95bc2b9b958717cd3dd27e89e6709057787196a19c61f63ebf9374",
        "fixture": "solid red 224x224 PNG",
        "expected_color": "red",
        "response": {
          "model": "qwen3-vl:32b",
          "created_at": "2026-09-09T11:32:50.448811Z",
          "message": {
            "role": "assistant",
            "content": "",
            "thinking": "{\"color\": \"red\"}"
          },
          "done": true,
          "done_reason": "stop",
          "total_duration": 10027427584,
          "load_duration": 3380623000,
          "prompt_eval_count": 1054,
          "prompt_eval_duration": 6362924000,
          "eval_count": 7,
          "eval_duration": 277828000
        },
        "matched": true
      },
      "smoke": {
        "anchor_color": "magenta",
        "anchor_mode": "all",
        "anchored_frames": [
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2371.12
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2375.691
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2380.262
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2384.833
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2389.404
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2393.975
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2398.545
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2403.6
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2407.687
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2412.258
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2416.829
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2421.4
          }
        ],
        "checks": null,
        "checks_raw": "",
        "clip_id": "m04-n12-t1411-237107-242145",
        "contract_version": "film-room-checks-v1",
        "done_reason": null,
        "error": "TimeoutError: timed out",
        "format_mode": "schema",
        "from_thinking": false,
        "model": "qwen3-vl:32b",
        "sent_frames": [
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-eo1pjvng/frame-00.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2371.12,
            "target_t": 2371.12
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-eo1pjvng/frame-01.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2375.691,
            "target_t": 2375.691
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-eo1pjvng/frame-02.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2380.262,
            "target_t": 2380.262
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-eo1pjvng/frame-03.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2384.833,
            "target_t": 2384.833
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-eo1pjvng/frame-04.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2389.404,
            "target_t": 2389.404
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-eo1pjvng/frame-05.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2393.975,
            "target_t": 2393.975
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-eo1pjvng/frame-06.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2398.545,
            "target_t": 2398.545
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-eo1pjvng/frame-07.jpg",
            "sampling_shift_s": 0.484,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2403.6,
            "target_t": 2403.116
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-eo1pjvng/frame-08.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2407.687,
            "target_t": 2407.687
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-eo1pjvng/frame-09.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2412.258,
            "target_t": 2412.258
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-eo1pjvng/frame-10.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2416.829,
            "target_t": 2416.829
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-eo1pjvng/frame-11.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2421.4,
            "target_t": 2421.4
          }
        ],
        "wall_s": 121.514
      },
      "smoke_900": {
        "anchor_color": "magenta",
        "anchor_mode": "all",
        "anchored_frames": [
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2371.12
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2375.691
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2380.262
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2384.833
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2389.404
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2393.975
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2398.545
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2403.6
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2407.687
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2412.258
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2416.829
          },
          {
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
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2421.4
          }
        ],
        "checks": {
          "ball_near_player": {
            "answer": "no",
            "confidence": "high",
            "reason": "Ball not near player in frames"
          },
          "kit_color_seen": {
            "answer": "red",
            "confidence": "high",
            "reason": "Red jersey visible on player"
          },
          "play_in_progress": {
            "answer": "yes",
            "confidence": "medium",
            "reason": "Players moving, ball visible"
          },
          "player_on_pitch": {
            "answer": "yes",
            "confidence": "high",
            "reason": "Player on field in all frames"
          },
          "player_running": {
            "answer": "yes",
            "confidence": "medium",
            "reason": "Player running in some frames"
          },
          "player_touches_ball": {
            "answer": "no",
            "confidence": "high",
            "reason": "No ball contact observed"
          }
        },
        "checks_raw": "{\n    \"player_on_pitch\": {\n        \"answer\": \"yes\",\n        \"confidence\": \"high\",\n        \"reason\": \"Player on field in all frames\"\n    },\n    \"play_in_progress\": {\n        \"answer\": \"yes\",\n        \"confidence\": \"medium\",\n        \"reason\": \"Players moving, ball visible\"\n    },\n    \"ball_near_player\": {\n        \"answer\": \"no\",\n        \"confidence\": \"high\",\n        \"reason\": \"Ball not near player in frames\"\n    },\n    \"player_touches_ball\": {\n        \"answer\": \"no\",\n        \"confidence\": \"high\",\n        \"reason\": \"No ball contact observed\"\n    },\n    \"player_running\": {\n        \"answer\": \"yes\",\n        \"confidence\": \"medium\",\n        \"reason\": \"Player running in some frames\"\n    },\n    \"kit_color_seen\": {\n        \"answer\": \"red\",\n        \"confidence\": \"high\",\n        \"reason\": \"Red jersey visible on player\"\n    }\n}",
        "clip_id": "m04-n12-t1411-237107-242145",
        "contract_version": "film-room-checks-v1",
        "done_reason": "stop",
        "error": null,
        "format_mode": "schema",
        "from_thinking": true,
        "model": "qwen3-vl:32b",
        "sent_frames": [
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-bui55noe/frame-00.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2371.12,
            "target_t": 2371.12
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-bui55noe/frame-01.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2375.691,
            "target_t": 2375.691
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-bui55noe/frame-02.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2380.262,
            "target_t": 2380.262
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-bui55noe/frame-03.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2384.833,
            "target_t": 2384.833
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-bui55noe/frame-04.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2389.404,
            "target_t": 2389.404
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-bui55noe/frame-05.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2393.975,
            "target_t": 2393.975
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-bui55noe/frame-06.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2398.545,
            "target_t": 2398.545
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-bui55noe/frame-07.jpg",
            "sampling_shift_s": 0.484,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2403.6,
            "target_t": 2403.116
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-bui55noe/frame-08.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2407.687,
            "target_t": 2407.687
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-bui55noe/frame-09.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2412.258,
            "target_t": 2412.258
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-bui55noe/frame-10.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2416.829,
            "target_t": 2416.829
          },
          {
            "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-bui55noe/frame-11.jpg",
            "sampling_shift_s": 0.0,
            "sent_h": 720,
            "sent_w": 1280,
            "t": 2421.4,
            "target_t": 2421.4
          }
        ],
        "wall_s": 201.795
      },
      "unchanged": {
        "source_sha256": {
          "checks_contract.py": "579d1ca7d6f01a95c33c36bd072ee7b56016eab752b5a8cc5cb8ce2c22b048d8",
          "checks_truth.py": "d847e4934d1774914e4df44b0797521c4c9695fff281d58a6afdabf0f6f204e7",
          "checks_score.py": "29f5d71602b1fa0b19881afe624b2a32606169691ab5bbbdca8259a1a4ad2a7f",
          "semantic_activity.py": "5a114717535212ed76bad545562b40579290b67445d1fc31309ed9dfd95ec8ae",
          "adapters/qwen3vl_checks.py": "92f070b614adf821628c228685deba4ac99a1a63cc21c0f02015253b6d3ec394",
          "adapters/qwen3vl_annotated.py": "d6d7b484420c3bde476d80aa7a41587f489b8e4403e110cfd142ca39c606a743",
          "adapters/common.py": "bbc42955d2d6fd2f4b1a7cea8278803f066dfadba6ae87a0d86862906c2e277a",
          "run_bench.py": "d44d9f4746823e5f9e2b5548318efbb3d59f243e36e8a0e966401f5f875cf24b",
          "diag_format_channel.py": "4bfc993e99cf9855d6097e1236595c222514f9da7568f37bccbebcc6667c0f88"
        },
        "truth_set_sha256_after_notes": "b0701190324ab2527d400b2b176da67291a5efffc11fd314068b343e9f74e8ed",
        "human_notes_sha256": "5944679d0b576bfd8790d9d1206def9485f7618b0c6d53d4c7593c266d51d59f",
        "four_run_comparison_checks": "PASS",
        "protected_code": "byte-identical to bcb1699a",
        "truth_snapshot": "matches both 8B launches"
      },
      "execution": {
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
    },
    "model_27b": {
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
    "smoke_27b": {
      "anchor_color": "magenta",
      "anchor_mode": "all",
      "anchored_frames": [
        {
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
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2371.12
        },
        {
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
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2375.691
        },
        {
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
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2380.262
        },
        {
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
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2384.833
        },
        {
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
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2389.404
        },
        {
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
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2393.975
        },
        {
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
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2398.545
        },
        {
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
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2403.6
        },
        {
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
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2407.687
        },
        {
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
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2412.258
        },
        {
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
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2416.829
        },
        {
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
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2421.4
        }
      ],
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
      },
      "checks_raw": "{\n  \"player_on_pitch\": {\n    \"answer\": \"yes\",\n    \"confidence\": \"high\",\n    \"reason\": \"Visible on the field of play\"\n  },\n  \"play_in_progress\": {\n    \"answer\": \"yes\",\n    \"confidence\": \"high\",\n    \"reason\": \"Active match play observed\"\n  },\n  \"ball_near_player\": {\n    \"answer\": \"no\",\n    \"confidence\": \"medium\",\n    \"reason\": \"Ball not within two body-lengths\"\n  },\n  \"player_touches_ball\": {\n    \"answer\": \"no\",\n    \"confidence\": \"medium\",\n    \"reason\": \"No clear ball contact visible\"\n  },\n  \"player_running\": {\n    \"answer\": \"yes\",\n    \"confidence\": \"high\",\n    \"reason\": \"Running motion clearly seen\"\n  },\n  \"kit_color_seen\": {\n    \"answer\": \"red\",\n    \"confidence\": \"high\",\n    \"reason\": \"Red jersey and black shorts\"\n  }\n}",
      "clip_id": "m04-n12-t1411-237107-242145",
      "contract_version": "film-room-checks-v1",
      "done_reason": "stop",
      "error": null,
      "format_mode": "schema",
      "from_thinking": false,
      "model": "qwen3.8:27b-obliterated-q8",
      "sent_frames": [
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-i1fsajdu/frame-00.jpg",
          "sampling_shift_s": 0.0,
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2371.12,
          "target_t": 2371.12
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-i1fsajdu/frame-01.jpg",
          "sampling_shift_s": 0.0,
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2375.691,
          "target_t": 2375.691
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-i1fsajdu/frame-02.jpg",
          "sampling_shift_s": 0.0,
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2380.262,
          "target_t": 2380.262
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-i1fsajdu/frame-03.jpg",
          "sampling_shift_s": 0.0,
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2384.833,
          "target_t": 2384.833
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-i1fsajdu/frame-04.jpg",
          "sampling_shift_s": 0.0,
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2389.404,
          "target_t": 2389.404
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-i1fsajdu/frame-05.jpg",
          "sampling_shift_s": 0.0,
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2393.975,
          "target_t": 2393.975
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-i1fsajdu/frame-06.jpg",
          "sampling_shift_s": 0.0,
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2398.545,
          "target_t": 2398.545
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-i1fsajdu/frame-07.jpg",
          "sampling_shift_s": 0.484,
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2403.6,
          "target_t": 2403.116
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-i1fsajdu/frame-08.jpg",
          "sampling_shift_s": 0.0,
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2407.687,
          "target_t": 2407.687
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-i1fsajdu/frame-09.jpg",
          "sampling_shift_s": 0.0,
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2412.258,
          "target_t": 2412.258
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-i1fsajdu/frame-10.jpg",
          "sampling_shift_s": 0.0,
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2416.829,
          "target_t": 2416.829
        },
        {
          "path": "/var/folders/z8/ytqjknls5lz7klz3p2jq7x_00000gn/T/evidence-checks-i1fsajdu/frame-11.jpg",
          "sampling_shift_s": 0.0,
          "sent_h": 720,
          "sent_w": 1280,
          "t": 2421.4,
          "target_t": 2421.4
        }
      ],
      "wall_s": 80.395
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
    }
  },
  "regeneration": {
    "runs": {
      "8b_dense": "e1d-checks-dense",
      "8b_prod30": "e1d-checks-prod30",
      "32b_dense": "e1d-checks-32b-dense",
      "32b_prod30": "e1d-checks-32b-prod30",
      "27b_dense": "e1d-checks-27b-dense",
      "27b_prod30": "e1d-checks-27b-prod30"
    },
    "allow_mixed": true,
    "output_stem": "evidence-bench-2026-09-10-lane-b-models",
    "baseline_run": "8b_dense"
  },
  "not_done": "No new inference or moment-window bench. MJ touch times and sampled-frame visibility labels are needed; the review perfect-detector estimate/unattainable wording is not a measured bound. No adoption decision or push.",
  "round_base_commit": "60d5772",
  "r2_verification": "Before changes, all three JSON/MD pairs regenerated byte-for-byte from committed r2 comparator and execution inputs. Existing null recall and FPS metrics retained.",
  "review_headline": "Across 8B, 32B and 27B, wide frames or 768-px crops, every model says 'on pitch, high confidence' for players stretching, warming up or in warm-up kit on the sideline, and no run could have detected a touch because the stills are 1.6\u20136.6 s apart \u2014 the bench has shown the checks are blind to sideline context and has not yet tested touch detection at all.",
  "positive_touch_caveat": "Temporal confound: dense true-touch mean still spacing is 1.58, 4.14, 4.57, 5.52, 6.62 and 1.88 s; run-wide mean spacing is 2.49 s dense and 23.99 s sparse. Raw 0/6 is not a detector score. Review estimate of perfect-detector 1/6 dense or 0/6 sparse, and 2/6 being unattainable by construction, is an assumption rather than a bound proved by these stills. Running rows share the temporal confound; crop sideline and ball-near rows also have spatial confounds.",
  "exact_regeneration_command": "/Users/mjjones/Projects/loanarmy/.loan/bin/python spike/video-analysis/bench/compare_checks.py --reports-root /Users/mjjones/Projects/loanarmy-bench-reports --manifest /Users/mjjones/Projects/loanarmy-bench-frozen/manifest.json --execution spike/video-analysis/bench/fixtures/lane-b-models-execution.json --runs 8b_dense=e1d-checks-dense 8b_prod30=e1d-checks-prod30 32b_dense=e1d-checks-32b-dense 32b_prod30=e1d-checks-32b-prod30 27b_dense=e1d-checks-27b-dense 27b_prod30=e1d-checks-27b-prod30 --touch-clips --baseline-run 8b_dense --allow-mixed --out-json ledgers/research/evidence-bench-2026-09-10-lane-b-models.json --out-md ledgers/research/evidence-bench-2026-09-10-lane-b-models.md",
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
