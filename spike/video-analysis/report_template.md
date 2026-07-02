# Phase 0 Degradation & Cost Report — Match Video Analysis

> Fill from `run_spike.py` outputs (`results/<video>-<ts>/results.json`, `report.md`,
> `sample_clip.mp4`). One column per footage class. This document is the evidence
> for ledger tasks 0.2/0.3 and feeds the 0.5 GO/NO-GO decision in
> `ledgers/CONTINUITY_video-analysis.md`.

- Date:
- GPU used (must be T4-class for the cost gate; note scaling caveat otherwise):
- Harness commit / config (`sample_fps`, detector size, resolution, slicer params):

## 1. Footage inventory

| id | source | license (verified where/when) | attribution (CC BY) | camera type | resolution/fps | duration | class |
|---|---|---|---|---|---|---|---|
| F1 | YouTube CC (VEO match, e.g. Ryt6tidyYaI) | CC BY 3.0 (.info.json on disk) | channel/title/URL: | panning sideline (amateur) |  |  | THROUGHPUT + DEGRADATION |
| F2 | SoccerTrack v2 | CC BY 4.0 (repo LICENSE-DATA) | dataset + arXiv:2508.01802 | 4K panoramic full-pitch (amateur) |  |  | THROUGHPUT (4K) + DEGRADATION + ground truth |
| F3 | YouTube CC (second camera style, e.g. bcoAMvp9ez8 college or C09BiuotZVM 720p floor) | CC BY 3.0 (.info.json on disk) | channel/title/URL: | static-ish college cam / 720p floor |  |  | DEGRADATION |

## 2. Per-stage timings (from results.json `stages` + `extrapolation_90min`)

| stage | F1 VEO 1080p (s / fps) | F2 4K panoramic (s / fps) | F3 amateur (s / fps) |
|---|---|---|---|
| decode |  |  |  |
| detect (full-frame) |  |  |  |
| detect (sliced) — benchmark |  |  |  |
| track |  |  |  |
| cluster (embed + fit) |  |  |  |
| render (30s clip) |  |  |  |

**90-min extrapolation:**

| variant | GPU-hours | $ @ ACA T4 $0.84/hr | $ @ Spot $0.32/hr | ≤3.5h gate |
|---|---:|---:|---:|---|
| full-frame |  |  |  |  |
| sliced |  |  |  |  |

- Measured slicer cost multiplier: ___× (critic's estimate was ~4×)
- If sliced fails the gate — chosen optimization path (selective far-half slicing /
  reduced slicer frequency + interpolation / TensorRT FP16 / resolution bump):

## 3. Detection quality across camera classes (eyeball `sample_clip.mp4` + mean detections/frame; F2 ground truth enables real recall numbers)

| observation | F1 VEO panning | F2/F3 other amateur |
|---|---|---|
| mean detections per frame (expect ~22–25 incl. refs) |  |  |
| near-side players |  |  |
| **far-side players (the known weakness)** |  |  |
| ball detected at all? |  |  |
| false positives (spectators, bench, ball boys) |  |  |

Notes (lighting, motion blur, occlusion clumps, camera pans):

## 4. ID-switch observations (results.json `tracklets`)

| metric | F1 | F2 | F3 |
|---|---|---|---|
| tracklet count |  |  |  |
| mean / median tracklet duration (s) |  |  |  |
| tracklets per minute (proxy: ~0.25/min ideal; higher = churn) |  |  |  |
| BoT-SORT or ByteTrack fallback? |  |  |  |

Qualitative (from the clip): switches at occlusions? after pans? far side worse?
Implication for the tracklet-merge pass and the ≤20 min tagging budget (task 0.4):

## 5. Team-cluster separation (results.json `team_cluster`)

| metric | F1 | F2 | F3 |
|---|---|---|---|
| silhouette (UMAP-3D, k=2) |  |  |  |
| cluster size balance |  |  |  |

Kit colors in footage; keeper/referee contamination; would uploader-supplied kit
colors (the production seeding plan) have helped?

## 6. Labeling plan sizing (input to detector fine-tune, task A4)

- Frames where pretrained COCO detection is weakest (far-side, blur, dense):
- Proposed labeling set: ~2,000 frames; mix: ___% amateur far-side, ___% dense
  midfield, ___% panning blur; source split across F1–F3 (all CC BY — training
  permitted with attribution) + self-captured:
- Estimated cost (tool, $/frame or hours):
- Expected lift worth it? (gut + evidence from §3)

## 7. GO / NO-GO recommendation

| gate | result | pass? |
|---|---|---|
| job ≤3.5 GPU-h (T4, shippable slicer config) |  |  |
| far-side detection usable on amateur footage |  |  |
| tagging ≤20 min (task 0.4 — separate human test) |  |  |

**Recommendation:**

**Conditions / follow-ups before Phase A:**

**Record the decision in `ledgers/CONTINUITY_video-analysis.md` (task 0.5).**
