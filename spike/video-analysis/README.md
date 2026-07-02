# Video-Analysis Spike (Phase 0)

Standalone validation harness for the match-video analysis pipeline
(ledger: `ledgers/CONTINUITY_video-analysis.md`). **Not product code** — nothing
here ships, imports project modules, or touches the backend.

## What it answers

1. **Cost gate (task 0.2):** does decode → RF-DETR detection → BoT-SORT tracking →
   SigLIP team clustering → render fit in **≤3.5 GPU-hours for a 90-min match**
   at 12.5 fps analysis rate? At ACA serverless T4 (~$0.84/hr all-in) that is
   ~$3/match compute; the business case breaks above ~3.7h.
2. **The slicer question:** a critic flagged that `supervision.InferenceSlicer`
   (needed for far-side players) multiplies detection cost ~4×. The harness
   times detection **both full-frame and sliced** and reports the measured
   multiplier — default `--slicer both`.
3. **Degradation inputs (task 0.3):** tracklet churn (ID-switch proxy) and
   team-cluster separation on broadcast vs amateur footage, feeding
   `report_template.md`.

License posture is inherited from the ledger: **RF-DETR (Apache-2.0), trackers
BoT-SORT (Apache-2.0), supervision (MIT), SigLIP weights (Apache-2.0). Never
ultralytics/YOLOv8 — it is AGPL and banned from the serving path.**

## Files

| file | purpose |
|---|---|
| `download_footage.py` | fetch license-verified footage (SoccerTrack v2, CC BY YouTube matches) |
| `run_spike.py` | per-stage timed pipeline run + 90-min cost extrapolation + pass/fail vs gate |
| `report_template.md` | skeleton for the Phase 0 degradation report (task 0.3) |
| `requirements.txt` | pinned deps (no ultralytics) |

## Quickstart on a rented GPU box

**Recommended rental:** RunPod Community Cloud, **Tesla T4 16 GB if available
(~$0.15–0.25/hr)** — it matches the ACA production target exactly, so measured
hours map 1:1 onto the cost model. If no T4 is listed, take an **L4 24 GB
(~$0.40–0.50/hr)** and note in the report that L4 is ~2–3× faster than T4
(scale measured detect fps down accordingly, or treat the result as a lower
bound). Lambda Labs has no T4s; their A10 (~$0.75/hr) works with the same
caveat. *Prices move — check the consoles; the approved spike budget is
$100–200 one-time, and a full run at these rates costs single-digit dollars.*

```bash
# on the box (PyTorch/CUDA 12.x template)
git clone <repo> && cd loanarmy/spike/video-analysis   # or scp this directory over
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# footage — both sources are license-verified CC BY (no accounts needed beyond pip deps)
python download_footage.py youtube-verified --ids Ryt6tidyYaI CqL3iTdRUlg   # VEO panning-cam full matches, 1080p
python download_footage.py soccertrack       # SoccerTrack v2: 4K Japanese university matches (interrupt after 2-3)

# the measurement that matters: full 1080p match, CUDA, slicer both ways
python run_spike.py --video "footage/youtube/Ryt6tidyYaI_<title>.mp4" --device cuda --slicer both

# then the 4K panoramic case (throughput stress + Japan-college degradation)
python run_spike.py --video footage/soccertrack-v2/<match>.mp4 --device cuda --slicer both
```

Each run writes `results/<video>-<timestamp>/{results.json, report.md, sample_clip.mp4}`.
Eyeball `sample_clip.mp4` — track-ID stability and obvious missed far-side
players go straight into `report_template.md`.

## Local smoke test (Apple Silicon)

```bash
python run_spike.py --video footage/youtube/<clip>.mp4 --smoke
```

`--smoke` = 60 s of footage, small batches, 10 s clip, MPS (or CPU) via
`--device auto`. **Sanity only**: it proves the pipeline wires up end-to-end.
MPS/CPU timings say nothing about T4 cost — only CUDA runs count for the gate.
If RF-DETR fails to initialize on MPS the harness retries on CPU automatically.

## Footage licensing — do / don't (verified 2026-06-10, sources in ledgers/research/video-analysis/)

| | source | use for | rule |
|---|---|---|---|
| ✅ | **SoccerTrack v2** (10 Japanese university matches, 4K panoramic + ground-truth tracks) | throughput stress **and** degradation, plus quantitative accuracy vs ground truth | CC BY 4.0 verified from LICENSE-DATA ("any purpose, even commercially"); attribution + cite arXiv:2508.01802 |
| ✅ | **Verified CC BY YouTube set** (5 full matches: VEO panning sideline, US college, semi-pro) | throughput on 1080p (full 1:55 match) **and** the panning-sideline degradation case | license re-checked at fetch time; `.info.json` kept as provenance; CC BY attribution in report |
| ❌ | DFL Bundesliga Data Shootout (Kaggle) | — | data removed; rules were competition-use-only + mandatory deletion + no redistribution |
| ❌ | roboflow/sports demo clips (`0bfacc_0.mp4`…) | — | re-hosted DFL competition clips; the repo's MIT covers code only |
| ❌ | SoccerNet videos | — | KAUST NDA: "research and non commercial use only" |
| ❌ | Alfheim/Tromsø (Simula) | — | non-commercial research only + explicit player-profiling ban |
| ❌ | Standard-license YouTube broadcasts | — | no rights; don't bypass the CC check |
| ❌ | Training any commercial model on the above | — | this spike measures; it does not train (CC BY sources WOULD permit it, but training waits for Phase A's labeled set) |

**Key framing:** the VEO panning-cam CC matches are *exactly* customer-like
footage, so they serve both the throughput measurement (full-length 1080p) and
the degradation columns. SoccerTrack v2 adds the 4K stress case, the Japan
college target market, and per-frame ground truth for quantitative accuracy.
For a worse-quality floor, degrade synthetically with ffmpeg
(downscale/bitrate-crush) rather than hunting for worse sources.

## How results map to the go/no-go gates (ledger Phase 0)

| gate | source in harness output | GO condition |
|---|---|---|
| 0.2 job cost | `report.md` → extrapolation table | **≤3.5 GPU-hours** per 90-min match (full-frame AND the slicer variant you'd actually ship, on T4) |
| 0.3 degradation | `tracklets` + `team_cluster` JSON + `sample_clip.mp4`, broadcast vs amateur | far-side detection usable; ID churn and cluster separation documented in `report_template.md`; ~2k-frame labeling plan costed |
| 0.4 tagging time | *not this harness* — human test with the processed tracklets | ≤20 min/match |
| 0.5 decision | all of the above → recorded in `CONTINUITY_video-analysis.md` | all three pass ⇒ GO |

If full-frame passes but sliced fails the 3.5h gate, that is not an automatic
NO-GO — it forces an optimization decision (selective slicing on the far half,
lower slicer frequency + interpolation, TensorRT FP16, or a resolution bump
instead of slicing) which must be written up in the report.

## Notes / known sharp edges

- `--optimize` (torch.jit.trace via `optimize_for_inference`) is **off by
  default**: it traces a fixed batch size and conflicts with the slicer's
  single-tile calls. Use it only with `--slicer off` to measure its speedup.
- The production design uses TensorRT FP16 with pre-built engines; this spike
  measures plain PyTorch inference, so production should only ever be *faster*.
  Record that headroom in the report rather than relying on it for the gate.
- `umap-learn` pulls in `numba`; if it rejects the pinned numpy, downgrade to
  `numpy~=2.2` (noted in requirements.txt).
- If `trackers` BoT-SORT fails to import, the harness logs a warning and falls
  back to `supervision.ByteTrack` — the run is still valid for timing, but say
  so in the report (no camera-motion compensation).
