# Film Room — Match Video Analysis (User & Operator Manual)

> **Living document.** Last updated **2026-07-02**. When the feature changes, update the
> relevant section **and** add a line to the [Changelog](#15-changelog) at the bottom.
> This is the human-facing how-to; the internal build state lives in
> `ledgers/CONTINUITY_video-analysis.md`.

---

## 1. What Film Room is

Upload a match video → a computer-vision pipeline detects and tracks every player →
**you review and correct who is who** → you get a **per-player report**. It targets
college / grassroots / lower-division clubs that have video but no stats.

**What it gives you today (be honest about this):**

- **Identity** — which jersey number each tracked player is, with a confidence.
- **On-camera coverage** — how many minutes each player was actually visible (a panning
  camera never sees everyone all the time, so this is *on-camera*, never a full-match total).
- **Per-player report** — identity + coverage, every figure carrying its own confidence.

**What it does _not_ give yet (shown honestly as "pending calibration", never faked):**

- Distance, top speed, sprint counts, heatmaps — these need the pitch-calibration
  (homography) stage, which isn't wired yet.
- Touches — experimental ("beta — coming soon"), needs ball association.
- **Opposition players are numbers only** — no names, no reports (consent/safeguarding).

---

## 2. Current implementation status

| | Status |
|---|---|
| **Phase** | A — *concierge*. We operate it admin-side; no self-serve team accounts yet. |
| **Where it runs** | **Locally**, against a real already-processed match (`AFC Yorkies 4–0 AFC Wyke`, the v8 spike output). The GPU pipeline itself runs on Azure ACA; locally we replay its outputs. |
| **Footage/crops/boxes** | Served from local files in dev; in production they come from Azure Blob (footage works; **crops + per-frame boxes are a prod follow-up** — see §10). |
| **Billing** | Not wired (credits granted manually). |

---

## 3. Getting in (local)

1. **Start the servers** (two terminals):
   ```bash
   cd academy-watch-backend && ../.loan/bin/python src/main.py     # backend on :5001
   cd academy-watch-frontend && pnpm dev                            # frontend on :5173
   ```
2. **Log in as admin.** The admin pages need both an admin Bearer token *and* the
   `X-API-Key` in `localStorage`. Easiest path locally: open `http://localhost:5173`,
   open the browser console, and paste the snippet from **`/tmp/aw_admin_login.js`**
   (it sets the three keys and reloads). The values are your local `.env`
   `ADMIN_API_KEY` + a minted admin token.
3. Go to **`http://localhost:5173/admin/video`** (the "Film Room" item under *Club Services*).
   The demo match is **`/admin/video/4`**.

---

## 4. The end-to-end workflow

```
Create match → Upload footage → Mark kickoff → Enter squad → Process
   → Pick your side (auto-tags) → TAG REVIEW (correct identities) → Finalize
   → Per-player report → Export feedback / Build manifest (learning loop)
```

1. **Create a match** — team (the paying club), opponent name, kit colours, date.
2. **Upload footage** — browser uploads directly to storage (multi-GB, resumable). *In the
   local demo this is pre-loaded; you skip straight to review.*
3. **Mark kickoff / halftime** — 10 seconds of your input beats fragile auto-detection.
4. **Enter your squad** — one player per line, `number name` (e.g. `10 John Smith`). Your
   team only; opposition stays numbers-only.
5. **Process** — debits a credit and queues the GPU job. (Local demo: the processed
   output is loaded directly.)
6. **Pick your side** — tell it which colour is your team. High-confidence players on your
   side are **auto-tagged** immediately.
7. **Tag review** — the heart of the tool (§5).
8. **Finalize** — builds the per-player reports from *your* confirmed identities.

---

## 5. Tag review — the evidence panel

Each detected player ("tracklet") is a row. Click the **›** chevron to expand it:

- **Video window** — the match video auto-seeks to where this player appears and **loops
  that window**. Scrub with the slider; press the video to pause/play.
- **The tracking box** — a cyan box **follows the exact player** as the camera pans, so you
  can tell which of the ~11 players this row is. `box tracks this player (N detections)`.
  *If the box disappears, the model isn't confident there — that's honest, not a bug.*
- **Sharpest crops** — up to 8 clear cut-outs of the player (drawn from the most
  reliable parts of the track). Click a crop to jump the video to that moment.
- **Controls** — confirm / reassign / mark-not-a-player / **split** (§6).

### Reading the badges

| Badge | Meaning |
|---|---|
| `confident` / `uncertain` | the model's confidence in the number |
| `mixed identity?` | the chain's members disagree on the number (below 70% agreement) — **treat with suspicion**; auto-tagging is disabled for these |
| `us` / `opposition` | which side, once you've picked your team |
| `auto` | auto-tagged for you (high-confidence) — confirm or correct it |
| `confirmed` / `reassigned` / `split` | a review action you (or another operator) already took |
| `… % number agreement` | how internally consistent this player's number reads are |

---

## 6. Making corrections

In the expanded panel (or the row header):

- **Looks right** — confirm the auto-tag. (Confirming *is* a signal; it tells the model it
  was correct.)
- **Reassign** — pick the correct player from the dropdown when the number is wrong.
- **Not a player** (the person-with-x icon) — dismiss a spectator/coach/referee.
- **Split here (mm:ss)** — when one track is actually **two different players** (the box
  jumps from one player to another part-way through), this cuts it in two. See below.

Then click **Save tags**, and **Re-finalize** to rebuild the report from your truth.
Re-finalizing never re-runs the GPU — it just re-aggregates.

### What happens when you split (read this — it's the confusing bit)

1. **Scrub the video to the moment the box jumps** to a different player, then click
   **Split here (mm:ss)**. The cut happens at the playhead — so *scrub first*; clicking it
   at the very start/end does nothing useful.
2. The original row is **replaced by two new rows** — the "before" piece and the "after"
   piece. Each is re-scored its own jersey number.
3. Those two pieces are **pinned to the top of Tag review and highlighted (amber ring)**,
   with a banner telling you what happened, and the match drops back to **"needs tagging"**.
   (Before this, the pieces just scattered into the long list — that's why it felt like
   nothing happened.)
4. **Tag each piece** like any row: expand it, watch its window, then confirm the number or
   mark it "not a player".
5. **Save tags → Re-finalize.** Done.

A split is also a strong training signal — it tells the model "you merged two players here",
which feeds the learning loop (§9).

---

## 7. The per-player report

After finalizing, the **Player reports** card shows, per player:

- **Identity** — `human_confirmed` (you confirmed) > `high` > `low` > `unverified`. A stat
  is only as trustworthy as the identity it hangs on.
- **Coverage** — on-camera minutes · confident windows · % of match · the jersey-number reads.
- **Metrics** — `Minutes on camera` is real; `Distance / Top speed / Sprints / Heatmap`
  read **"pending calibration"** and `Touches` reads **"beta"** — present in the structure,
  never fabricated, filled in as capability lands.

A roster player we never confidently saw still gets a row ("unverified / 0 min") — "we saw
nothing of them" is more honest than silent omission.

---

## 8. How identity works (so the badges make sense)

The pipeline, in order: **detect** players → **track** them → **cluster** into two teams by
kit colour → **read jersey numbers** (a vision model votes across frames) → **chain**
fragments that share `(team, number)` into one player → **quality gate**.

The **quality gate** is why chains are cleaner than raw output. It drops:

1. **Wrong-shirt members** — a red player mis-clustered + mis-read into a blue chain (the
   classic "box switches to a different player" bug).
2. **Lone single-read members** — a fragment backed by only one read is too easily a misread.

It then scores each chain's **number agreement**. This is conservative on purpose: it would
rather show *less* and be right than draw a box it can't trust — the gaps are what your
review and the split tool fill in.

**Why a chain can still be wrong:** jersey numbers are often illegible on the far side of a
wide camera, and appearance alone can't tell two same-kit teammates apart. That's an
industry-wide limit — which is exactly why a human reviews, and why corrections feed the
learning loop (§9).

---

## 9. Feedback & the learning loop

Your corrections are ground truth that makes the model better — "learn from its mistakes".
It's **RLHF-style** (learn from human feedback), not literal reinforcement learning:

- **Model accuracy & learning** card (on a finalized match) shows how the model did vs your
  corrections: **auto-tag precision**, **number-read accuracy**, and the
  confirmed/reassigned/dismissed/split breakdown.
- **Recalibration signals** — plain-English suggestions for tuning the thresholds next round
  (e.g. *"high-confidence chains were wrong 2/6 times — raise the vote threshold"*).
- **Build fine-tune manifest** — turns your confirmed crops into a training set:
  `crop → number` for the jersey reader and `identity → crops` for a player-recognition
  model. **Consent-gated**: only your own (club-owned) players' crops; opposition never
  enters the training set.
- **Export feedback** — the same labels as NDJSON to download.

The actual model retraining (on Apple-silicon/MLX) is an **offline** step that consumes the
manifest; everything up to it runs in the app.

---

## 10. Known limitations & honest caveats

- **Residual mis-tracks** — the gate catches the obvious contamination; subtle tracker swaps
  (a single bad read) can still slip through. Use **Split** / **Not a player** on those.
- **Crop angles vary** — crops come from the player's own track, but individual frames can be
  occluded or from behind. Improving this is the learning loop's job.
- **Production follow-ups (not built):**
  - The vision worker must persist **crop JPEGs and per-frame box tracks to Blob** — today
    those come from local spike artifacts, so crops/boxes are **dev-only** (`serve_crop`
    returns 501 in prod).
  - The frontend's hosted Content-Security-Policy needs `media-src 'self' https: blob:` for
    the cross-origin video SAS.
- **Split re-run caveat** — if you split a chain and then re-run the pipeline, the original
  chain is rebuilt and duplicates the split segments (needs a "suppressed keys" record).
  Harmless in concierge use.

---

## 11. Operator / developer notes

- **Reload the demo match** (re-derive tracklets after a code change):
  ```bash
  cd academy-watch-backend
  ../.loan/bin/python src/scripts/load_video_artifacts.py \
    --match-id 4 --artifacts-dir ../spike/video-analysis/results/v8/combined/inverted
  # then POST /finalize
  ```
- **Local artifact map** — dev media is resolved from `match.capture_meta['local']`
  (`{footage, crops_dir, crops_index, tracks_dir, fragments}`), gated on
  `video_storage.is_configured() == False`. Never active in prod.
- **Media token** — `<video>`/`<img>` can't send admin headers, so footage/crop URLs carry a
  signed, match-scoped, **30-minute** token (`auth.py mint_media_token`). The UI re-mints on
  expiry.
- **Per-frame boxes** — joined from `spike/.../results/v8/chunk*/tracks.npz`
  (`tid` is chunk-namespaced, `t` is absolute match seconds).
- **Dev server must be threaded** (`app.run(threaded=True)`, already set) or streaming footage
  blocks API calls.
- **Migrations** — `vid01` (tables) → `vid02` (structured report) → `vid03` (review-audit
  columns + merged heads). Apply with `flask db upgrade vid03`.
- **Tests** — `pytest tests/test_video_*.py` (report, identity, feedback, learning).
  Frontend: `pnpm lint`.

---

## 12. Admin API reference

All under `/api`, all `@require_api_key` (admin Bearer + `X-API-Key`) unless noted.

| Method & path | Purpose |
|---|---|
| `POST /admin/video/matches` | create match (returns upload SAS) |
| `PUT  …/matches/<id>/roster` | upsert squad |
| `POST …/matches/<id>/process` | debit + queue the GPU job |
| `GET  …/matches/<id>` · `…/tracklets` | match + tracklet list (review queue) |
| `POST …/matches/<id>/tags` | bind / reassign / dismiss / confirm |
| `POST …/matches/<id>/tracklets/<tid>/split` | split a chain at `at_s` |
| `POST …/matches/<id>/finalize` | build per-player reports |
| `GET  …/matches/<id>/report` | structured per-player report |
| `GET  …/matches/<id>/media-token` | mint a media token |
| `GET  …/matches/<id>/footage?token=` | stream footage (Range) — *token-gated* |
| `GET  …/matches/<id>/crops/<file>?token=` | a crop image — *token-gated* |
| `GET  …/matches/<id>/tracklets/<tid>/crops` · `…/bbox-track` | crop list / box track |
| `GET  …/matches/<id>/accuracy` | model accuracy + recalibration signals |
| `GET  …/matches/<id>/feedback-export` | per-crop labels (NDJSON) |
| `GET  …/matches/<id>/training-manifest` | fine-tune manifest |

---

## 13. Glossary

- **Tracklet / chain** — one tracked on-pitch player the pipeline produced; you bind it to a
  roster player. A *chain* bundles many short *fragments* of the same player.
- **Quality gate** — the step that strips wrong-shirt / unreliable members from a chain.
- **Number agreement** — how unanimous a chain's jersey-number reads are (100% = clean).
- **Concierge** — we operate the tool admin-side on the club's behalf (Phase A).

---

## 14. Where things live (code map)

- Backend: `src/routes/video.py`, `src/models/video.py`, `src/services/video_{identity,report,
  feedback,learning,dev_artifacts,storage,queue}.py`, `src/workers/vision_worker.py`.
- Frontend: `src/pages/admin/AdminVideo.jsx`, `AdminVideoMatch.jsx`, `src/lib/api.js`.
- Local CV pipeline + harness: `spike/video-analysis/` — `run_spike.py` (detect/track/cluster),
  `merge_tracklets.py`, `anchor_identity.py` (MLX VLM), `invert_identity.py` (chains),
  `bench_detect.py` (backend benchmark), `run_local.py` (end-to-end orchestrator).
- Internal state/plan: `ledgers/CONTINUITY_video-analysis.md`.

---

## 15. Running the pipeline locally on Apple Silicon (GPU-free concierge)

The whole CV pipeline runs on an Apple-Silicon Mac (no cloud GPU) for the concierge
phase — `run_spike.py` is device-portable (`--device mps`). Benchmarked 2026-06-25 on an
M4 Pro: RF-DETR-medium detection = **~23 fps (1.88× realtime), numerically identical to
CPU** (parity match 1.0 / IoU 1.0, conf err 0.0). Detection is the heavy stage; tracking +
clustering are cheap, and the jersey VLM is the existing MLX step. This is the
concierge/design-partner architecture — one match at a time; it graduates to the T4 job at
volume (ledger).

**Venvs** (in `spike/video-analysis/`): `.venv-bench` (torch + rfdetr, detection),
`.venv-merge` (numpy/opencv, merge + invert), `.venv-vlm` (mlx-vlm, jersey reader).
Build the detection venv once:
```bash
cd spike/video-analysis
uv venv .venv-bench --python 3.13 --seed
uv pip install --python .venv-bench/bin/python rfdetr==1.7.1 supervision==0.28.0 \
  trackers==2.4.0 scikit-learn umap-learn opencv-python-headless av psutil
```

**Benchmark a backend** (CPU vs MPS vs CoreML, with numerical parity + per-match budget):
```bash
HF_HOME=.cache/hf TORCH_HOME=.cache/torch PYTORCH_ENABLE_MPS_FALLBACK=1 \
.venv-bench/bin/python bench_detect.py --video footage/<match>.mp4 \
  --frames 150 --backends cpu,mps --optimize     # writes results/bench/{json,md}
```

**Run the full local pipeline** (footage → loader-ready artifacts):
```bash
HF_HOME=.cache/hf TORCH_HOME=.cache/torch PYTORCH_ENABLE_MPS_FALLBACK=1 \
.venv-bench/bin/python run_local.py --video footage/<match>.mp4 --name <run> --match-id <id>
#   --skip-vlm        detection+merge only (fast proof, no chains)
#   --max-seconds N   process only a clip
```
It chains detect (MPS) → merge → VLM read → number-driven chains, then prints the
`load_video_artifacts.py` command and the `capture_meta['local']` dict to attach to the
VideoMatch (footage/crops_dir/crops_index/tracks_dir/fragments) so review playback works.

**Game-time windowing (save compute, cut warmup noise).** Pass operator-verified markers and
the pipeline processes ONLY the in-play halves, skipping warmup/halftime/post (~30–40% of a
full recording) — which also removes warmup/sideline non-player detections:
```bash
.venv-bench/bin/python run_local.py --video footage/<match>.mp4 --name <run> \
  --kickoff 1000 --halftime 3900 --second-half-kickoff 4700 --end 7000
#   --kickoff alone (or +--end) processes one in-play window (skips warmup+post)
```
It runs detect per half with tid-offset namespacing, then `merge --chunk-dirs` stitches them
(team labels aligned across halves). `game_window.py` can *suggest* these markers but is only a
rough guide — amateur warmups are both-goal shooting drills that span the pitch and fool it, so
**always verify/override** (manual marking is the reliable path; the product already requires it).

*Prod path (wired 2026-07-02):* the same markers now flow end-to-end. `vision_worker` forwards
`--kickoff-s/--halftime-s/--second-half-kickoff-s/--end-s` (from the VideoMatch row) to
`$VIDEO_PIPELINE_CMD`, and `run_spike.py` honours them in a **single pass** (`game_time.in_play_plan`):
it bounds the run to `[kickoff, end]` and skips the halftime gap in-loop, resetting the tracker at
the 2nd-half boundary (with a `+1_000_000` id offset) so first- and second-half tracks don't collide.
Single clustering pass over both halves keeps team labels consistent (no cross-segment re-alignment
needed). Without `--kickoff-s`, behaviour is unchanged (the `--start-seconds/--max-seconds` chunked path).

**Security:** Docker on macOS can't reach Metal/MPS, so sandbox the untrusted ffmpeg
*decode* (CPU, locked-down container) and run inference *native* on MPS over the clean
frames. The fast-MLX detectors (YOLO) are AGPL-banned, so detection stays on RF-DETR via
PyTorch-MPS; CoreML/ANE export is the escape hatch if MPS underperforms. Distance/speed/
heatmap stay suppressed until homography (unchanged).

---

## 16. Changelog

- **2026-07-02** — 2nd-half marker wired into the **prod** GPU pass. Previously `vision_worker`
  forwarded only `--kickoff-s/--halftime-s`, so the 2nd-half kickoff was collected-then-dropped and
  the pipeline couldn't skip halftime. Now the worker forwards all four markers and `run_spike.py`
  honours them (`game_time.in_play_plan` → single-pass in-play windowing: bound to `[kickoff, end]`,
  skip the halftime gap, reset+offset the tracker at the 2nd-half boundary). New pure helper
  `game_time.py` (+ selftest), worker cmd-builder test, UI guide copy updated to match. Non-marker
  runs are byte-for-byte unchanged.

- **2026-06-30** — `step1b_identity.py`: corroboration gate for Step 1's single-read anchors. A
  double-blind visual audit of all 40 v8 anchors corrected the earlier n=12 estimate — they are
  actually **17.5%** precise, dominated by **over-merge** (the anchor crop reads a real number off a
  real player, but the *entity* is a blob of several players). Crop re-reads and cheap structural
  signals can't fix this (ceiling ~22%); the gate that works is **VLM entity-consistency** on a
  center-cropped contact-sheet montage (gemma-4-12B — E4B is too trigger-happy), OR'd with a cheap
  ≥2-shirt-colour rule: **17.5 → 70% precision, keeping 100% of the genuinely-correct coverage.** The
  montage check doubles as a general over-merge detector; the real fix is merge quality upstream.
- **2026-06-25 (pm)** — Identity diagnosis + two levers. (1) `step1_identity.py`: keyframe-weighted
  vote + non-player gate (named coverage 19→25.9% on v8, but single-read anchors are ~70% precise
  — crop mis-association — so ship as low-confidence human-reviewed candidates). (2) `run_local`
  game-time windowing: operator markers (`--kickoff/--halftime/--second-half-kickoff/--end`) process
  only in-play halves, skipping warmup/halftime/post (~30–40% compute). `game_window.py` is a rough
  marker suggester (unreliable on warmup drills — verify). Root finding: poor ID is a COVERAGE +
  TRACKING problem, not the reader.
- **2026-06-25** — Local Apple-Silicon pipeline: `bench_detect.py` (RF-DETR CPU/MPS/CoreML
  benchmark + numerical parity; MPS = 1.88× realtime, parity PASS vs CPU) and `run_local.py`
  (end-to-end local orchestrator across the three venvs). `run_spike.py --device mps`
  validated end-to-end on a clip (footage → 26 entities). Detection venv `.venv-bench` built.
- **2026-06-18 (pm)** — Split UX: the two new pieces are now **pinned to the top of Tag
  review, highlighted**, with an explainer banner, and the match re-opens to "needs tagging"
  (previously the pieces scattered into the list and the split felt like it did nothing).
- **2026-06-18** — Tracklet **quality gate** (shirt-consistency + weak-corroboration), crop
  selection prefers strong fragments, **honest flags** (number-agreement %, "mixed identity?"),
  **Split tool**, and the **learning loop** (accuracy card, recalibration signals, fine-tune
  manifest). Per-row **video review** (window + tracking box + crops) and the **feedback
  export** shipped earlier the same day.
- **2026-06-16** — Structured confidence-per-field per-player report (migration vid02).
- **2026-06-12** — Phase A backbone (models, routes, tag-review UI) shipped.
</content>
