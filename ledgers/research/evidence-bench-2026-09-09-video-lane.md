# E1b — native video versus sampled frames, 2026-09-09

Completed: all three lanes attempted all 20 clips sequentially, after separate one-clip smokes; no wall-cap stop or fallback.
Frozen set: `1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f`, all 20 windows; evaluation only.
Reports: `~/Projects/loanarmy-bench-reports/e1b-{ollama-frames,mlx-video-fps2,mlx-video-fps4}/`.

| Lane | Scored / failed | Supported overall | Unboxed supported | Unsupported | Hollow | Seconds / attempt |
|---|---:|---:|---:|---:|---:|---:|
| Frames | 19 / 1 | 73.68% | 0/2 = 0% | 26.32% | 0% | 12.759 |
| Video 2 FPS | 16 / 4 | 68.75% | 0/1 = 0% | 31.25% | 0% | 56.017 |
| Video 4 FPS | 18 / 2 | 77.78% | N/A (0 unboxed) | 22.22% | 0% | 63.771 |

E1: all lanes fail unsupported ≤10%; frames and 2 FPS exceed the >25% kill threshold, while 4 FPS does not. All pass hollow <5% and every-attempt time ≤120s (maxima 22.463s / 98.052s / 95.118s).
The 4 FPS unsupported-rate improvement does not increase supported-clip coverage: it has the same 14/20 supported clips and one additional failure excluded from the scored denominator.
The ≥2× historical baseline threshold is mathematically met but vacuous: the baseline never returned boxes and supported=0%; unboxed support is zero for frames/2 FPS and not measurable for 4 FPS.

Mean frames actually sent per attempt: 4.15 / 49.6 / 100.5 (MLX anchor image excluded); frames records 4.45 extracted frames including six never sent on the shared failure. MLX prompt/generated token means per available response: 13,501/85.737 at 2 FPS and 13,892.053/89.684 at 4 FPS; Ollama tokens unavailable.

Per-clip 2 FPS changes (full IDs; support is geometry/time, not semantic action verification):

- Video gains `m04-n17-t717-253073-260377`: frames say “holding a football” at 2535.83 with an unsupported box; video says “visible on the field” at the supported anchor time 2530.83.
- Video gains `m04-n24-t3013-679939-681217`: frames describe a “referee holding a white object” at 6804.44 with zero containment; video says “walking on the field” and grounds at the anchor (6799.44).
- Video gains `m04-n25-t3014-530600-532465`: frames claim first-image position “(178,349)” with zero containment; video says “Player #25 is visible” and grounds at the same anchor time.
- Video loses `m04-n04-t3006-243433-247994`: “visible across multiple subsequent frames” has a zero-height box; failed contract, versus supported frames “standing near the goal area”.
- Video loses `m04-n05-t3007-284945-287898`: empty claims versus frames “visible in subsequent frames”; failed by the existing no-parseable-claims rule.
- Video loses `m04-n09-t1409-143096-143834`: both describe arms crossed near the sideline, but video's box_t is 0.517s before t0, exceeding the 0.5s contract tolerance.
- Video loses `m04-n10-t711-186553-188161`: “visible on the field” cites an unlabelled later frame with zero box containment; frames cite the supported anchor.
- Video loses `m04-n15-t3010-164698-170777`: “tracked through the video” has only 3.77% box containment at the anchor; frames locate the marked red-shirted player.
- Video loses `m04-n17-t717-416826-418915`: “wearing a red jersey with the number 17” has only 62.21% containment and fails IoU; frames “visible running” grounds at the same anchor time.

Per-clip 4 FPS changes versus frames:

- Gains `m04-n24-t3013-679939-681217` and `m04-n25-t3014-530600-532465`: “identified by the red rectangle ... visible in subsequent frames” grounds both boxes at the anchor; the control boxes have zero containment (details above).
- Loses `m04-n04-t3006-243433-247994`: “A player in a red jersey is tracked across multiple frames” returns an anchor-time box with zero containment, versus the supported control near the goal.
- Loses `m04-n15-t3010-164698-170777`: video says “blue jersey” and its box has zero containment; the control describes the marked red-shirted player and grounds its box.
- Contract availability loss on `m04-n17-t717-253073-260377`: “running with the ball” has box_t 0.667s before t0; it fails, while the control was valid but unsupported. This is not an additional grounded-clip win for frames.
- All other attempted clip support/status outcomes match frames; 4 FPS and frames each support 14/20 attempted clips. The video gains above remain anchor controls.

Like-for-like limitations:

- E1 frames sample every 5s, at most six stills; production's ≤3 stills every 30s is a different sampling policy.
- MLX uses native temporal patch grids, not multi-image stills. Its installed Qwen processor omits HF per-pair timestamp tokens; actual decoder times are supplied in text. This is not full HF timestamp encoding parity.
- MLX adds a separate marked image at the same truth-aware first time (usually 0.05s); raw video starts at 0s and remains unlabelled. The unchanged ±0.5s rule can count nearby raw video frames as boxed.
- Spatial resolution and coverage differ: MLX samples the full clip and spends a fixed total video pixel budget; doubling FPS reduces each frame's resolution. Frames are 1280×720.
- Ollama GGUF Q4_K_M and the MLX 4-bit conversion are different weights/engines; tokenizer, preprocessing, repetition implementations and output formatting can differ despite shared temperature 0, 400-token cap and penalty 1.15. Ollama enforces JSON mode; MLX uses prompt instructions with the same strict parser.
- MLX includes a fresh Python process/model load for every clip. Ollama keeps a shared server/model and its smoke prompt cache sped the repeated control clip to 2.248s. Single sequential passes, no repeated trials or machine workload isolation.
- Rates exclude failed clips; 0% hollow/malformed among scored claims hides failed empty/invalid outputs. Count successful grounded clips over all 20 as well: frames 14, 2 FPS 11, 4 FPS 14. Wall means include early failures; token means cover available worker responses only.
- `m04-n02-t3005-474114-478131` fails the current shared anchor lookup in all lanes at 4741.19s. Historical E1 counted it unsupported; 14 supported claims persist in today's frames control, but the scored denominator is 19 instead of 20.
- No frozen clip has a human note; action semantics/fabrication are not graded. On the designated unreadable-number clip, both video rates assert jersey 17 as kit detail; 17 was supplied, so new-number invention is UNCONFIRMED, but the wording is flagged for the jersey-number kill criterion. Frames refers to the marked #17 label.
- Two unsuccessful MLX smoke attempts are retained: missing Jinja2, then fenced JSON. Jinja2 3.1.6/MarkupSafe 3.0.3 were installed only under this worktree's ignored report directory; the final prompt forbids Markdown and the parser was not relaxed.

Verdict: **frames** — frames match 4 FPS at 14/20 supported clips with fewer failures (1 versus 2) and approximately 5× lower wall time (12.759 versus 63.771s); neither video rate demonstrates unboxed grounding. This is a comparison verdict, not an adoption decision.
