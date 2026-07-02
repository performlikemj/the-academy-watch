# Spike timing report — match.mp4

Generated 2026-06-10T09:54:49+00:00 · device `cuda` · detector `rfdetr-medium` · tracker `trackers.BoTSORTTracker (CMC on)`

## Per-stage wall-clock (measured)

| stage | seconds | units | units/sec |
|---|---:|---:|---:|
| model_load | 11.0 | 0 | 0.00 |
| decode | 330.1 | 86525 | 262.13 |
| detect | 3969.8 | 86525 | 21.80 |
| track | 1136.4 | 86525 | 76.14 |
| render | 5.7 | 375 | 65.51 |
| cluster_model_load | 7.2 | 0 | 0.00 |
| cluster_embed | 21.4 | 1982 | 92.57 |
| cluster_fit | 14.3 | 1982 | 138.91 |

Frames processed: 86525 (6921s of footage at 12.5 fps analysis rate)

## Extrapolation to a 90-minute match

Assumes 67500 analysed frames; decode/detect/track scale linearly, cluster scaled to a 2000-crop cap, model load + render counted as fixed (59.8s).

| variant | detect fps | GPU-hours | $ @ ACA T4 $0.84/hr | $ @ Spot $0.32/hr | ≤3.5h gate |
|---|---:|---:|---:|---:|---|
| fullframe | 21.80 | 1.20 | $1.00 | $0.38 | **PASS** |
| sliced | 3.18 | 6.22 | $5.23 | $1.99 | **FAIL** |

Measured slicer detection-cost multiplier: **6.85×**

## Tracklets (ID-switch proxy)

```json
{
  "n_tracklets": 8277,
  "mean_duration_s": 8.93,
  "median_duration_s": 4.85,
  "max_duration_s": 137.05,
  "tracklets_per_minute": 71.76,
  "note": "tracklets/min is an ID-switch proxy: ~22-30/90min would be perfect persistence; hundreds/min means constant identity churn"
}
```

## Team clustering

```json
{
  "status": "ok",
  "n_crops": 1982,
  "cluster_sizes": [
    1117,
    865
  ],
  "silhouette_umap3d": 0.479,
  "note": "silhouette > ~0.5 with roughly balanced clusters = clean kit separation; low/lopsided = kit clash, bibs, or referee/keeper contamination"
}
```

Caveats: smoke/MPS runs measure nothing about GPU cost — only CUDA runs count for the gate. Broadcast footage answers throughput only; degradation needs amateur footage (see report_template.md).
