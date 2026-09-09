The frozen clips have no human notes: event CORRECTNESS is not measured until MJ supplies them. This run measures honesty/format/presence-only/number-invention/kit-colour and time bounds only.

E1c lane A — annotated dense frames, semantic-only contract

Honesty rates and events/clip: scored clips. Valid attempt rate and wall/clip: all attempts. Kit match excludes abstentions from the asserted-only rate; match/abstain/wrong rates use all scored clips. Time/clip means all event times pass (vacuously true with no events); event-time rate counts events. Fabricated rate: noted scored clips only. Presence-only read retains the original event-gated narrow regex; sentence-only presence ignores events and excludes the specified action-verb stems. Consistency requires every substantive event class in score._event_classes(sentence); unmatched/unmapped classes fail, and no substantive events pass vacuously. Zero-duration and window-filling rates count events, not clips. Events/sent-frame uses all frames of scored clips. Thinking rate counts recorded true flags across all attempts, including failures.

| Run | Scored / failed | valid_rate | empty_rate | presence_only_read_rate | presence_only_sentence_rate | sentence_event_consistency_rate | supplied_number_asserted_as_kit_detail_rate | number_invented_rate | kit_color_match_rate | kit_color_abstain_rate | kit_color_wrong_rate | time_in_window_rate | zero_duration_event_rate | window_filling_event_rate | events_per_sent_frame | high_confidence_completed_from_one_frame_count | from_thinking_rate | valid_attempt_rate | time_in_window_event_rate | fabricated_rate | events_per_clip | wall_s_per_clip |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| e1c-annotated-dense | 20 / 0 | 100.00% | 0.00% | 0.00% | 35.00% | 10.00% | 5.00% | 0.00% | 100.00% | 0.00% | 0.00% | 100.00% | 0.00% | 6.52% | 0.1933 | 0 | 100.00% | 100.00% | 100.00% | N/A | 2.3 | 58.417 |
| e1c-annotated-prod30 | 20 / 0 | 100.00% | 0.00% | 0.00% | 60.00% | 5.00% | 15.00% | 0.00% | 90.00% | 0.00% | 10.00% | 100.00% | 31.43% | 57.14% | 1.2069 | 12 | 100.00% | 100.00% | 100.00% | N/A | 1.75 | 9.898 |

- e1c-annotated-dense: 238 sent frames (11.9/attempt); 11 gap-adjusted timestamps, maximum shift 0.484s.
- e1c-annotated-prod30: 29 sent frames (1.45/attempt); 2 gap-adjusted timestamps, maximum shift 0.05s.

First five scored clips in manifest order, verbatim; no quality selection.

Five sentences — e1c-annotated-dense:

- `m04-n02-t3005-474114-478131`: “The marked player in red carries the ball and passes it during build-up play.”
- `m04-n03-t1406-157170-158922`: “Player in red kit visible on field throughout sequence.”
- `m04-n03-t1406-385962-387137`: “Player in red kit carries ball and engages in duel with opponent.”
- `m04-n04-t3006-243433-247994`: “Player in red kit visible moving across field during play.”
- `m04-n04-t3006-307417-310307`: “The marked player in red kit is seen running with the ball and engaging in a duel.”

Five sentences — e1c-annotated-prod30:

- `m04-n02-t3005-474114-478131`: “Player marked #2 carries the ball in attack then engages in a duel during defending.”
- `m04-n03-t1406-157170-158922`: “Player in red kit visible on right side of field.”
- `m04-n03-t1406-385962-387137`: “Player in red jersey with number 3 visible on the field.”
- `m04-n04-t3006-243433-247994`: “Player in red kit visible carrying ball and involved in duel.”
- `m04-n04-t3006-307417-310307`: “A player in red kit is visible running on the field.”

Caveats:

- Truth box_track stands in for the production tracker's persisted geometry on every sampled frame. Tracker accuracy and unlabelled-player grounding are not evaluated.
- No boxes are requested from the VLM, so rectangle echo is not a model-geometry failure mode in this lane. The supplied jersey label is not proof of number legibility.
- Dense samples are spread across the window, capped at 12; 30s/3 is a sparse annotated control. These isolate sampling under the same semantic contract, not a comparison to the old grounding score.
- Presence-only and jersey checks are narrow regex rules, not semantic judgments; kit-colour checks compare the explicit field only. Goal and name prohibitions are prompt rules, not verified truth guarantees.
- The conservative event keyword mismatch rule becomes available only on clips with human notes; it is neither a complete event taxonomy nor a measure of event correctness.
- Sequential single passes, without repeats or confidence intervals. Wall time includes extraction/drawing and all failed attempts; Ollama may reuse a warm model. Temporary frame paths record provenance but images are removed after each call.
- Uniform target samples falling in tracking gaps snap to the nearest recorded track timestamp within 0.5s, remaining distinct and chronological; target_t and sampling_shift_s record every adjustment. Larger gaps fail before inference. Geometry is never extrapolated across gaps.
- All 20 truths have red kits and both measured runs used red rectangles: kit-colour matching is uninformative until the frozen set includes non-red kits. Future lane-A model inputs use magenta; these saved outputs were not rerun.
- Every lane-A response (40/40) was read from Ollama's thinking field despite think=false. Schema-valid parsing is established; the format grammar's effect on that field is unverified. The transport is unchanged.
- Sentence-only presence applies the specified verb-stem exclusion literally: moving, interacting and holding are not excluded. Consistency uses the unchanged conservative score._event_classes vocabulary, so carrying/passing inflections and unmapped broad types may remain unmatched; these are lexical diagnostics, not semantic accuracy.
- Truth and note hashes describe the current rescoring snapshot across all manifest truth files. Historical run.json files retain their original launch metadata; absent inference-time hashes are not retroactively asserted.
- No adoption recommendation; MJ owns that decision.
