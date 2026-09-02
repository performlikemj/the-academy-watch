# DIRECTIVE — Film Room Evidence Bench: measure honesty before swapping models

Status: AUTHORED 2026-09-01 (MJ: "let's take this and plan out the directive for this testing").
Author: Fable. Inputs: `ledgers/research/hf-scouting-models-2026-09-01.md` (codex, verified
licences), `DIRECTIVE_scouting-viewer-completion.md` (W4 quality round, W8 R3 ladder),
`CONTINUITY_video-analysis.md` §scouting-viewer. Companion: `harness/DIRECTIVE_app_sim_lane.md`
(the deterministic-grading pattern this reuses).

## 1. Why this exists

The product promise is that a club can evaluate a player who has no stats, and that a scout can
**trust every sentence** of the written read because it traces back to footage. Today "does the
read feel honest" is judged by eye. This bench turns it into numbers we can compare across models,
prompts and merge rules — so the D3 model decision, the per-player read design (W4d) and the
merge-quality work are decided by measurements on our own footage, not by model-card claims.
Rule of the bench: **a claim without evidence is a defect, not a style problem.**

## 2. What already exists (build on it, do not rebuild)

- Frame observations + per-player reads: `spike/video-analysis/qwen_match_analysis.py`
  (`validate_observation_schema`, `recurring_jersey_evidence`, W4c non-hollow rule, W4d per-player
  bounded calls, multi-image `ollama_chat(images=…)` pattern from the caption stage).
- Tracked player boxes per second: `src/services/video_dev_artifacts.py`
  `tracklet_bbox_track` (from `tracks.npz`), sharpest crops via `tracklet_crops`, reel windows via
  `src/services/video_reels.py` (bound chains' member-fragment spans, ≥1s, merged <3s gaps).
- Merge machinery: `spike/video-analysis/merge_tracklets.py` `candidate_pairs` (cosine on the
  tracker's own embeddings, gap + spatial gates) and `chain_identities.py` `calibrate` /
  `choose_gates` (leave-one-out precision/recall curves over anchored members).
- Human truth: reviewed bindings from the Verify panel (`bind_tags`, recorded as human review
  actions), exported per crop by `src/services/video_feedback.py` `build_feedback_labels`
  (`/feedback-export`, `/training-manifest`; our-side, finalized matches, consent-gated).
- Domain data: local match 4 (AFC Yorkies, real v8 chains, 13 bound players, human-corrected
  No.2/No.12 case) and the SoccerTrack v2 slice `spike/video-analysis/footage/soccertrack-v2/`
  (`117093_calibrated_1st.mp4` + `117093_homography.npy` + `117093_keypoints.json`); the full
  dataset is CC-BY-4.0 on HF (`atomscott/soccertrack-v2`, 145 GB, gated).
- Grading pattern: `sim/lib/grade.mjs` + `report.json` — deterministic scorer, VLM verdicts are
  measurements, mechanical outcomes cap verdicts (PR #919). Reuse the shape, not the code.
- Basecamp: ollama 0.33.2 with `qwen3.8:27b-obliterated-q8` resident; **no `qwen3-vl` pulled, no
  `mlx-vlm` installed** (decision D1 below); 128 GB RAM, 1.4 TB free.

## 3. The bench (E0) — `spike/video-analysis/bench/`

**Frozen evidence set** (never used for training; versioned by a manifest hash):
- `clips/`: 20 reel windows from match 4 across ≥8 of our players, deliberately including the hard
  cases: the No.2/No.12 mis-binding window, back-to-camera stretches, far-side panning, a set piece,
  and two windows where the player is present but the number is never readable.
- Per clip, the **truth** the scorer needs, all derived from data we already hold: the tracked box
  track (`tracklet_bbox_track`), the human-confirmed identity (post-review binding), the window
  bounds, and — decision D2 — an optional one-line human note of what visibly happens.
- `soccertrack/`: the local 117093 slice for tracking/merge/calibration truth (IDs, homography).

**Deterministic scorer** `bench/score.py` → `bench/report/<ts>/report.json`, never a model verdict:
- *Grounding:* a claim counts as **supported** only if its returned box overlaps the tracked box
  (IoU ≥ 0.5 or ≥ 80 % containment) at its stated time AND its `[t0,t1]` lies inside the window.
  Everything else is **unsupported**. Metrics: supported rate, unsupported rate, hollow rate
  (claim with no time/box), claims per clip, wall time and tokens per clip.
- *Non-fabrication* (when D2 notes exist): a claim naming an event absent from the human note is
  **fabricated**; counted separately from unsupported.
- *Merge:* on clips with truth IDs — merge **precision first** (a false merge is more dishonest
  than a missed one), then recall and IDF1.
- *Calibration:* reprojection error against the SoccerTrack homography; success rate per camera
  class (from the preflight questionnaire in `capture_meta`).
- Honest rules carried over from the sim lane: a mechanically failed run is a fail whatever the
  prose says; a clip with no expectation is "observed", never "pass".

## 4. Experiments (each = one codex brief, one worktree, one PR, results in `ledgers/research/`)

### E1 — Grounded-claim contract (cheapest, decides the D3 model question)
Run the 20 clips through (a) today's flow and (b) **Qwen3-VL-8B** (Apache-2.0; ollama tag for
images, `mlx-vlm` for native video) with the tracked jersey box overlaid, requiring
`{claim, t0, t1, box, confidence, visibility}` per claim; code rejects unsupported claims.
Accept when, on the same clips, (b) has **unsupported ≤ 10 % and supported ≥ 2× (a)**, hollow < 5 %,
and wall time per clip ≤ 2 min on basecamp. Then flip `QWEN_VISION_MODEL` for the caption + player
stages (zero code beyond the contract parser). Kill criteria: unsupported > 25 % or the model
invents numbers on the "number never readable" clips.

### E2 — Merge signal challengers (the known identity bottleneck)
Compute OSNet-x0.25 (MIT) and DINOv2-small (Apache) embeddings over the sharpest torso crops and
compare against the tracker embedding in `candidate_pairs` scoring, on SoccerTrack-v2 MOT clips
(truth IDs) and match 4's human-confirmed chains, via the existing `calibrate` curves.
Accept only as an **additional** signal (time gap, kit colour, number posterior and impossible-
overlap constraints stay) and only if merge precision rises at equal or better recall. An
embedding alone never auto-merges. Kill: precision does not improve on the human-confirmed set.

### E3 — Own pitch keypoint model (unlocks R3)
Convert the 317 CC-BY pitch-keypoint images to **RF-DETR Keypoints** (Apache; never Ultralytics),
train small, test on 50 club-owned panoramic/panning frames bucketed by camera class, and score
reprojection error against the SoccerTrack homography. Accept when the "panoramic" class reaches
a calibration success rate worth offering formations on (target ≥ 80 %; disclosed per match);
lower classes stay "reels only" per the R3 ladder. Then SAM 2.1 (Apache) mask refinement.

### E4 — LoRA on corrected reads (later; gated)
Only after E1's contract is adopted and ≥ 200 human-corrected notes exist: Qwen3-VL-4B/8B 4-bit
LoRA via `mlx-vlm` on club-owned examples, vision tower frozen, with a held-out clip/player/venue
set. Not before — a LoRA on today's hollow or unverified notes would train the wrong thing.

## 5. Guardrails

- Licence policy is a gate, not a note: production = Apache/MIT/BSD/CC-BY only. **KILL** for prod:
  Molmo (non-commercial training data → internal judge only), SAM 3, SoccerNet family,
  SportsMOT, Sapiens, Ultralytics YOLO, PnLCalib/NBJW, Qwen2.5-VL-3B, synthetic scouting-text sets.
- Never prod data or prod endpoints; the frozen set is club-owned footage plus CC-BY data.
- Basecamp etiquette: one heavy job at a time, `caffeinate` every run, respect the resident PM
  brain's memory; new model pulls/installs only under D1.
- No names, ever: the scorer identifies players by roster binding and number, never by face.
- Frozen set never trains anything; E4's training data is disjoint by construction.
- VLM outputs are measurements; the merge gate and the honesty rails stay deterministic code.

## 6. Execution

Fable orchestrates and verifies; codex implements from briefs (E0 first, then E1); basecamp runs
the heavy passes. Every PR: connector review round, sim regression where UI is touched, results
file in `ledgers/research/evidence-bench-<date>.json` + a paragraph in
`CONTINUITY_video-analysis.md`. Decisions flow back into the register below and into the
completion directive's D3 / W8 entries.

## 7. Decision register — MJ

- **D1 = YES (MJ 2026-09-01, "quack quack quack"; codex does the heavy lifting):** `qwen3-vl:8b`
  pull + `mlx-vlm` venv (`~/mlx-vlm-venv`, py3.12) + `mlx-community/Qwen3-VL-8B-Instruct-4bit`
  download started on basecamp 2026-09-01 (logs `~/d1-ollama-pull.log`, `~/d1-mlx.log`).
  E0 dispatched to codex the same moment (worktree `.worktrees/evidence-bench`,
  branch `feat/evidence-bench`). D2/D3/D4 = the recommendations below stand unless MJ says otherwise.
- **D2:** who writes the one-line human truth note for the 20 clips (≈30 min of MJ) — or run E1 on
  grounding-only scoring first and add notes later. Recommendation: grounding-only first; add
  notes for the 5 hardest clips.
- **D3:** download the full SoccerTrack v2 (145 GB, gated HF acceptance) for E2/E3, or start with
  the local 117093 slice. Recommendation: slice first; full set only if E2 shows promise.
- **D4:** order. Recommendation: E0 → E1 → E2 → E3; E4 gated.
- **D5 (MJ 2026-09-02, "lets go with 1"):** after E1's adoption, product order is Coach's brief FIRST, then
  positioning (E3) as the parallel long pole, E2 alongside — see `ledgers/DIRECTIVE_coach-brief.md` (Tracks C/P/M).

## E1 RESULT — 2026-09-02 (see ledgers/research/evidence-bench-2026-09-01.json)
Qwen3-VL-8B grounds **14/20 claims (70%)** on the tracked player, 0 failed clips, 0 hollow/malformed,
**16.5 s/clip vs 145 s** for today's flow (structurally 0% — it never returns a box). Passes
"supported ≥ 2× baseline" and "hollow < 5%"; misses "unsupported ≤ 10%" (30%). **D3 = YES (MJ 2026-09-02, "i'm cool with qwen vl"): ADOPT qwen3-vl:8b for clip claims AND per-player reads with the
honesty gate (only tracking-verified claims are published); frame observations stay on qwen3.8.**
Integration in flight as three parallel codex builds: A `feat/grounded-vl-pipeline` (shared `grounding.py`,
gated captions + reads), B `feat/persisted-box-tracks` (box tracks persisted at CV completion → prod reel overlay
+ analysis context; migration after jk01), C `feat/verified-reel-notes` (reels show verified notes only).
Four bench faults were found and fixed with regression tests before this number was trusted
(PRs #927–#930: thinking-field answers, 1280-vs-1920 coordinate space, 0–1000 normalized boxes,
box scored at the observed frame `box_t` not the span midpoint). Four wasted passes preceded it.

## 8. Definition of done

E0 bench + scorer merged and reproducible on basecamp; E1 answered with numbers (adopt or kill,
recorded in D3); E2 and E3 each answered or explicitly parked with their measured reason; the
research ledger carries every report; no non-permissive licence anywhere in the production path.
