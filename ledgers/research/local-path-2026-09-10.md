# Best LOCAL path forward — player + ball tracking and coach-grade analysis (2026-09-10)

Context: M4 Max 128 GB (basecamp), everything on-device. RF-DETR (COCO) + tracker already produces good player boxes.
This week's benches (#1072/#1073/#1077): local VLMs (8B/32B/27B, wide stills or crops) cannot read match stills; touches were never fairly
tested (stills seconds apart). Sources searched 2026-09-10 (Fable, WebSearch/WebFetch); codex research pass failed (laptop codex OAuth revoked).

## What the field actually does in 2026
- **Stats come from detectors + trackers, not VLMs.** Roboflow's sports pipeline = player/ball/pitch-keypoint models + ByteTrack + homography
  (blog.roboflow.com/sports-analytics-ai, /track-football-players, /camera-calibration-sports-computer-vision; repo roboflow/sports, MIT).
  Indie repos (tryolabs/soccer-video-analytics, mradovic38/football-analysis, AmmarMohamed0/Football-Analysis-System) compute possession as
  "nearest player to ball with a grace period", passes as possession changes within a team.
- **Tiny-ball detection is its own model class.** WASB (nttcom/WASB-SBDT, MIT, PyTorch, multi-sport incl. soccer, heatmap on stacked frames,
  pretrained weights; last activity Nov 2023) and TOTNet (AugustRushG/TOTNet, 2025, occlusion-aware 3D conv, builds on WASB) — plus Roboflow's
  trick for small balls: 2×2 tiling of each frame to 640² before a YOLOv8x ball detector (mAP@0.5 0.925 on their set).
- **SoccerNet 2026 (arXiv 2607.07320):** Player-Centric Ball Action Spotting winner (PAVE) 58.9 macro-F1@0.15 on BROADCAST video — i.e. even
  SOTA on TV footage is far from perfect; Spiideo Synloc (single calibrated static 4K camera → pitch coordinates) winner 97.7 mAP-LocSim with
  YOLO26-L + RTMPose + ray casting through calibration. No code releases noted in the paper.
- **Commercial one-camera bar:** Veo Cam 3 claims ~95% ball auto-tracking in grassroots trials and "every shot, pass, tackle attributed to the
  player" with Analytics 2 (veo.com); reviews say tracking "still needs improvement" in glare/low light. This is the bar a club compares us to.
- **Local video-LLMs:** mlx-vlm runs Qwen3-VL video natively; temporal-grounding research is active (surveys/papers mid-2026) but nothing shows
  small-player football reads working locally without fine-tuning. Not the core path.

## What we already have that the searches point at
- `spike/video-analysis/run_spike.py` L71–74: RF-DETR COCO already requests `{"person", "sports ball"}`; tracking then keeps only `person`.
  Ball detections exist at detector level and have never been benchmarked or tracked.
- Homography: parked Track P (pitch keypoints/calibration) — needed to turn pixels into metres for distance/speed/possession radius.

## Recommended sequence (local only)
1. **Ball detection bench (this week, 2–3 days).** Three candidates on the 20 frozen clips + MJ's notes: (a) RF-DETR COCO `sports ball` as-is,
   (b) RF-DETR/YOLO with 2×2 tiling at native 1080p, (c) WASB soccer weights (heatmap, stacked frames). Gate: ball found in ≥80% of frames
   where a human can see it on the six touch clips; false balls ≤1 per 10 s. MPS on M4 for (a)/(b); WASB on MPS/CPU.
2. **Ball track + touch/possession rules (2–3 days).** Kalman-smoothed ball track; possession = nearest foot-point within R m for ≥0.5 s
   (hysteresis, grace period); touch = ball path inflection within R of a player; contested when two players within R. Gate: the six
   human-noted touches recalled ≥4/6 with ≤1 false touch per clip on the 14 non-touch clips.
3. **Homography (Track P, 3–5 days).** Pitch keypoints (Roboflow field-keypoint style) → per-frame H; R in metres; distance/speed/sprints/heat
   maps. Gate: reprojection error on the 4 corners + centre circle < 1 m; speeds plausible (max < 10 m/s).
4. **Coach's brief from facts (2 days).** "Expected vs seen" answered from touches/possession/positions + reels; VLM only for kit/identity checks.
5. **Optional, later:** moment-window VLM bench (≥4 fps around tracker-found touches, native crops) — the first fair VLM touch test.

## First build: step 1 as a bench lane (`bench/ball_detect`), same 20 clips, same truth notes, same ledger discipline.
