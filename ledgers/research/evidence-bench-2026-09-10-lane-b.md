On 20 shared scored clips: e1d-checks-dense (qwen3-vl:8b, 11.9 boxed frames/attempt): off-pitch false-yes 57.14%, off-pitch/idle touch false-yes 0.00%; e1d-checks-prod30 (qwen3-vl:8b, 1.45 boxed frames/attempt): off-pitch false-yes 50.00%, off-pitch/idle touch false-yes 0.00%. Adoption belongs to MJ.

Gate numbers (false-yes count / truth-no cells):

| Run | Off-pitch on-pitch/in-progress | Off-pitch + idle touch |
|---|---:|---:|
| e1d-checks-dense | 8/14 (57.14%) | 0/9 (0.00%) |
| e1d-checks-prod30 | 7/14 (50.00%) | 0/9 (0.00%) |

Shared scored clips: 20. All comparison rates use shared IDs scored in both saved reports and current rescoring. Full-run reports retain every attempt. Frame facts use all raw attempts. Configured wall caps alone do not imply an incomplete run.

Accuracy = correct / graded answered (unclear excluded). Abstain = unclear / eligible; coverage = graded answered / eligible. Binary eligibility requires yes/no truth. Kit eligibility follows lane A: uncertain kit truth forces abstention even for an asserted colour. False-yes = yes / truth-no cells; false-no = no / truth-yes cells, including abstentions in those truth denominators. Kit has no yes/no rates. Macro accuracy averages available accuracies across six questions; macro false-yes averages available rates across five binary questions; overall abstain is pooled over eligible cells. Gate 1 pools player_on_pitch and play_in_progress over off-pitch clips (14 cells on full set); Gate 2 uses player_touches_ball over off-pitch or idle clips with truth no (9 clips; mixed receive excluded). All metrics exclude failed reads; attempted/scored/failed counts remain visible. Thinking rate and wall/clip include all attempts. Reasons are logged only, never scored.

| Run | Scored/failed | Wall s/clip (all attempts) | Macro accuracy | Macro false-yes | Abstain | From thinking (all attempts) |
|---|---:|---:|---:|---:|---:|---:|
| e1d-checks-dense | 20/0 | 51.651 | 66.71% | 44.72% | 2.91% | 100.00% |
| e1d-checks-prod30 | 20/0 | 10.547 | 65.96% | 37.70% | 7.77% | 100.00% |

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
| m04-n03-t1406-157170-158922 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n03-t1406-157170-158922 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n03-t1406-385962-387137 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n04-t3006-243433-247994 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n04-t3006-243433-247994 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | blue / high |
| m04-n04-t3006-307417-310307 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n04-t3006-307417-310307 | e1d-checks-prod30 | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n05-t3007-284945-287898 | e1d-checks-dense | scored | yes / high | yes / high | no / medium | no / low | yes / high | red / high |
| m04-n05-t3007-284945-287898 | e1d-checks-prod30 | scored | yes / high | yes / high | no / medium | no / low | yes / high | blue / high |
| m04-n09-t1409-143096-143834 | e1d-checks-dense | scored | yes / high | yes / medium | no / high | no / high | yes / medium | red / high |
| m04-n09-t1409-143096-143834 | e1d-checks-prod30 | scored | no / high | yes / medium | no / high | no / high | no / high | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n09-t1409-297601-298865 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-dense | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n09-t1409-385922-386603 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n10-t711-186553-188161 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n10-t711-186553-188161 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | blue / high |
| m04-n12-t1411-237107-242145 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n12-t1411-237107-242145 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n12-t1411-679986-681985 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n15-t3010-164698-170777 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-253073-260377 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-304624-307834 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-dense | scored | yes / high | yes / medium | no / low | no / high | yes / medium | red / high |
| m04-n17-t717-416826-418915 | e1d-checks-prod30 | scored | yes / high | no / medium | unclear / low | no / high | yes / medium | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n21-t3011-390297-390800 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | no / medium | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-dense | scored | yes / high | no / medium | yes / high | no / low | yes / medium | red / high |
| m04-n22-t3012-070707-074371 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n24-t3013-679939-681217 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n24-t3013-679939-681217 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | black / high |
| m04-n25-t3014-530600-532465 | e1d-checks-dense | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |
| m04-n25-t3014-530600-532465 | e1d-checks-prod30 | scored | yes / high | no / medium | no / low | no / high | yes / medium | red / high |

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

- schema: JSON field=message.thinking; content empty=True; validates=True; selected=message.thinking; done_reason=stop; error=none.
- json: JSON field=message.thinking; content empty=True; validates=True; selected=message.thinking; done_reason=stop; error=none.
- none: JSON field=none; content empty=True; validates=False; selected=message.thinking; done_reason=length; error=none.

Model/frame facts from run.json and raw attempts:

- dense: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.484, "mean_boxed_frames_per_clip": 11.9, "model": "qwen3-vl:8b", "sample_interval": 0.5, "sample_limit": 12, "sent_frame_count": 238, "shifted_frame_count": 11, "single_frame_attempts": 0}
- prod30: {"adapter": "qwen3vl_checks", "anchor_color": "magenta", "attempted_clips": 20, "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f", "max_sampling_shift_s": 0.05, "mean_boxed_frames_per_clip": 1.45, "model": "qwen3-vl:8b", "sample_interval": 30.0, "sample_limit": 3, "sent_frame_count": 29, "shifted_frame_count": 2, "single_frame_attempts": 13}

Provenance:

- Truth SHA-256: `b0701190324ab2527d400b2b176da67291a5efffc11fd314068b343e9f74e8ed`
- Human-note SHA-256: `5944679d0b576bfd8790d9d1206def9485f7618b0c6d53d4c7593c266d51d59f`
- Contract: film-room-checks-v1; truth rules: film-room-checks-truth-v1.

Caveats:

- n=20, one sequential pass per sampling policy; no repeats or causal claim about density. Smoke and diagnostic are separate from the comparison.
- Truth is derived deterministically from MJ's notes via semantic_activity plus the explicit checks rules. This is not independent exhaustive video annotation. n17-416826 running=yes is a directive override without a running keyword; mixed n04-243433 running remains ungraded.
- Gate 2 excludes mixed idle/on-ball n04-243433 because its note explicitly records a receive; it is not truth-negative. The two gates measure individual check assertions, not a production gate's combined decision.
- Lane A's saved reads used red boxes; this lane uses magenta. Most kits remain red, with one verified black override and two uncertain warm-up kits forced to abstain. These data do not isolate annotation colour effects.
- MJ reports tracker misses. Supplied truth box_track stands in for production tracking; identity/input mistakes may affect readings. Labels are supplied identity, not independent jersey evidence.
- Every frame imports lane A's spread sampling and magenta drawing. Targets in tracking gaps snap to a recorded timestamp within 0.5s; larger gaps fail. Temporary frame files are removed after each call.
- Schema validation establishes the contract, not visual correctness or whether Ollama applies format grammar to thinking. The production transport and its existing thinking fallback are unchanged.
- Reason strings are verbatim audit text and never scored. Failed reads remain failed; comparison metrics use only shared scored IDs. Thresholds are withheld for incomplete coverage or no shared scores.
- Wall time includes extraction/drawing and failures, with warm-model effects possible. Thinking rate counts all attempts in full-run reports; comparison rates use shared attempts.
- No adoption call: MJ owns that decision. This bench does not wire checks into the production honesty gate.

Execution/gates:

```json
{
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
}
```
