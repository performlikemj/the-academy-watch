# Match Video Analysis ("Film Room") — Architecture

**Feature:** Teams upload match video (their own games or rivals'), tag the players they care about, and receive a per-player performance report. Teams pre-pay per match for the GPU processing.

---

## 1. Product flow (uploader's perspective)

### 1.1 End-to-end journey

```
Buy credits → Create match → Upload video (direct to Blob) → Enter roster (pre-tag)
   → [GPU processing 1–4 hrs, progress bar] → Tag review screen (bind tracks to players)
   → Finalize → Report (per-player stats, heatmaps, clips)
```

1. **Create match.** Uploader (team manager or admin acting as concierge) creates a `VideoMatch`: opponent name, date, which side is "ours", kit colors for both teams (two color swatches each — outfield + GK), optional final score, and a camera-setup questionnaire (elevation, panning/fixed, resolution). The questionnaire feeds the per-video quality score (§7).
2. **Upload.** Browser uploads the file directly to Azure Blob via a short-lived SAS (§3.1). Flask never touches video bytes. Resumable; 6 GB files are fine.
3. **Roster entry (pre-processing, lightweight).** Before processing starts, the uploader enters a roster: for each player they want a report on — name, jersey number, side (ours/theirs), optional link to a `TrackedPlayer` (autocomplete against the team's academy players). This takes 2 minutes and is *not* frame-level work.
4. **Pay & process.** Submitting for processing atomically debits one match credit and enqueues the GPU job. The match page shows live progress (decode → detection → tracking → calibration → metrics → rendering) by polling the job endpoint.
5. **Tag review (post-processing, the core interaction).** When processing completes, the uploader lands on the **Track Review screen**: a grid of detected player tracklets, each shown as 3–5 thumbnail crops + team color + minutes visible + (when available) an OCR-suggested jersey number. The uploader drags roster entries onto tracklets, or accepts auto-suggestions (matched by team side + OCR number). Because ID switches are inevitable, one roster entry can be bound to **multiple tracklets**; the UI prompts "Is this still #7?" with side-by-side crops when the pipeline's tracklet-merge confidence is low. Unbound tracklets (opposition players nobody cares about, referees mis-merged, etc.) are simply left untagged.
6. **Finalize → Report.** Finalizing aggregates all tracklets bound to each roster entry into a per-player report: minutes on camera, distance, speed bands, sprint count, heatmap, near-side touch estimate (beta), plus an annotated highlight strip. Reports are shareable within the team and, where the player is a `TrackedPlayer`, surfaced on their existing player page as a "Video analysis" tab.

### 1.2 Where manual tagging happens — decision: **both, deliberately split**

- **Pre-processing roster entry** (names, numbers, sides, TrackedPlayer links) — because it's cheap for the user, it gives the pipeline priors (kit colors for team classification seeding, jersey numbers for OCR matching), and it lets us auto-suggest most bindings.
- **Post-processing track-tagging review** — because this is where identity is actually resolved. The CV research is unambiguous: full-match identity persistence does **not** work automatically anywhere — even broadcast-grade GSR pipelines with re-ID + jersey OCR leave substantial identity errors, and on amateur footage with identical kits and a panning camera, ID switches every few minutes are normal. Promising automatic identity would be fabrication; the honest design makes the human the identity oracle and makes that job as fast as possible (thumbnails, auto-suggestions, merge confirmations).
- What we explicitly **don't** do: ask the user to scrub video and draw boxes pre-processing (too laborious), or trust raw track IDs (tags bind to *merged tracklet entities* that survive re-linking, per the recon recommendation).

---

## 2. CV pipeline

### 2.1 Licensing strategy (hard constraint)

**No AGPL or GPL code or weights anywhere in the serving path.** The ultralytics ecosystem (YOLOv8/v11, including the pretrained soccer weights bundled with `roboflow/sports` and used by `sn-gamestate`) is AGPL-3.0 with an explicit position that fine-tuned weights are covered and that server-side SaaS use triggers the license. We use `roboflow/sports` (MIT code) and `sn-gamestate` purely as **architectural references** and rebuild every model on Apache/MIT parts, retraining on the CC BY 4.0 Roboflow Universe datasets (attribution in our docs) plus self-labeled customer-style footage. Encumbered repos we will not copy from: `football_analysis` (no license), `jersey-number-pipeline` (CC BY-NC), PnLCalib/NBJW (GPL-2.0), SportsLabKit code (GPL-3.0). SoccerNet raw video is NDA/broadcast-encumbered — not used for training.

### 2.2 Stages

| Stage | Choice | License | Notes |
|---|---|---|---|
| Decode | ffmpeg/PyAV with NVDEC hwaccel | LGPL/MIT bindings | Analysis at **12.5 fps** (every other frame at 25fps) with track interpolation — halves GPU cost |
| Detection | **RF-DETR Small/Medium** (`roboflow/rf-detr`), fine-tuned on CC BY 4.0 `football-players-detection` + ~3–5k self-labeled grassroots frames | Apache-2.0 (Nano–Large only; never XL/2XL/PML) | TensorRT FP16, batched. `supervision.InferenceSlicer` for far-side players. **D-FINE** (Apache-2.0) kept as A/B benchmark. The grassroots fine-tune is the single highest-leverage investment in the project |
| Tracking | **BoT-SORT from `roboflow/trackers`** (Apache-2.0 clean-room) | Apache-2.0 | Camera-motion compensation is essential for panning sideline cameras; ByteTrack (via `supervision`, MIT) as cheap fallback. Offline **tracklet merging** pass afterward (appearance embedding + team + temporal constraints) producing the merged tracklet entities tags bind to |
| Team assignment | Reimplement `roboflow/sports` recipe: SigLIP crop embeddings → UMAP → KMeans, fit per match | SigLIP weights Apache-2.0; recipe MIT | Seeded/validated against uploader-supplied kit colors; flag low-separation matches (similar kits, bibs) in the quality score |
| Pitch homography | **Own 32-keypoint pitch model** (RTMPose-style Apache-2.0 keypoint head) trained on CC BY 4.0 `football-field-detection` + self-annotated grassroots frames → per-frame DLT homography in OpenCV with Kalman/Savitzky-Golay temporal smoothing; keypoints run at 2–5 Hz, not per-frame | Apache-2.0 throughout | Do NOT ship the AGPL YOLOv8x-pose weights or GPL calibration repos. Expect meters-level far-side error on low cameras → far-side metrics flagged low-confidence |
| Metrics | Own code (~the easy part once positions are on the pitch plane) | ours | Distance covered (clamped/smoothed), speed bands, **sprint counts** (>5.5 m/s sustained), "fastest sustained speed" (never instantaneous max — homography jitter fakes 40 km/h spikes), heatmaps via `supervision` draw utils |
| Ball + touches (**beta flag**) | RF-DETR ball fine-tune on sliced inference + trajectory interpolation; touches/possession-involvement only inside high-confidence ball windows via player-ball proximity | Apache-2.0 | Low recall on 1080p amateur footage by design; labeled "beta" in UI, gated on quality score |
| Jersey OCR (**tagging assist only**) | Reimplement Koshkina recipe from the paper with clean parts: own legibility classifier → RTMPose torso crop → **PARSeq** (`baudm/parseq`, Apache-2.0) fine-tuned on self-labeled/synthetic crops → tracklet-level voting | Apache-2.0 | Surfaces as "suggested #" on the tag review screen — never an identity backbone. Phase C |
| Rendering | 720p H.264 annotated preview clip via NVENC in the same job; per-tracklet thumbnail crops; heatmap PNGs | — | NVENC is effectively free alongside inference |

### 2.3 Explicitly OUT of scope for v1 (and why)

- **Pass networks / pass detection / event spotting** — all open baselines (T-DEED etc.) are trained on broadcast framing, license-encumbered (sn-spotting has no license), and there is no evidence of transfer to a single amateur sideline camera.
- **xG / shot quality** — requires reliable ball + event detection we don't have.
- **Possession chains** — player-ball proximity heuristics are too noisy below the touch level; we ship only per-player near-side touch *estimates*, beta-flagged.
- **Automatic full-match identity / face recognition** — solved by the human-in-the-loop tagging design instead (and face recognition of minors is a compliance non-starter for academies).
- **Live/real-time analysis** — offline batch only.

---

## 3. Infrastructure

### 3.1 Upload path (browser → Blob, never through Flask)

1. `POST /api/video/matches` creates the `VideoMatch` row and mints a 60-minute **user-delegation SAS** (create+write only) scoped to a single blob path `raw/{team_id}/{match_id}.mp4`, via the backend's existing managed identity.
2. Browser uses `@azure/storage-blob` `BlockBlobClient.uploadData` (16 MiB blocks, concurrency 4–6). Resumable: staged block IDs tracked client-side; on reconnect only missing blocks are re-staged before `commitBlockList`.
3. Client calls `upload-complete`; backend verifies blob existence/size and marks the match `uploaded`. (Event Grid `BlobCreated` as a belt-and-braces reconciler later.)
4. Add `MAX_CONTENT_LENGTH` to Flask anyway as a guard — no multipart endpoints exist today and we are not adding any for video.

### 3.2 Job orchestration — **ACA serverless GPU (T4) event-driven Jobs, westus2**

Chosen per the infra research: zero new vendors, video never leaves Azure (matters for the Forest academy relationship and minors' footage), scale-to-zero per-second billing fits a lumpy weekend workload, T4 serverless is available in our region (~$3.10/match at 4 vCPU/16 GiB). Fallback at >100 matches/month: AML batch endpoints on `NC8as_T4_v3` **Spot** (~$0.69/match; Low-Priority VMs are retired — Spot only). External escape hatch if Azure quota blocks us: Modal A10 (~$2.35/match incl. egress).

- New **workload-profile ACA environment** with a Consumption-GPU T4 profile in `rg-loan-army-westus2`; new container image `academy-watch-vision` (own directory + Dockerfile; PyTorch/TensorRT — deliberately **not** the Flask image, which only copies `src/` and `migrations/`).
- **Enqueue:** on `process`, Flask atomically debits a credit, creates a `VideoAnalysisJob` row (reusing the existing `BackgroundJob` UUID/status/progress conventions from `src/utils/background_jobs.py`), and drops a message on an **Azure Storage Queue** (`video-jobs`): `{job_id, match_id, blob_path}`.
- **Trigger:** KEDA `azure-storage-queue` scaler on the ACA Job; 1 GPU replica per message; parallelism = queue depth (cap 3 initially); retry policy 2 attempts; job timeout 5 h (mirrors the existing 4-h stale-job auto-fail).
- **Progress:** the GPU worker connects to the **same PostgreSQL** (managed identity / existing conn secrets) and updates its `VideoAnalysisJob` row (`status`, `progress/total`, `current_stage`) every ~30 s — identical shape to what the admin UI already polls. On completion it writes `results_json` (report summary + artifact paths); on failure it sets `error` and Flask's webhook-free reconciler refunds the credit.
- **Cancellation:** worker checks the row's status each stage boundary, same as `is_job_cancelled()` today.

### 3.3 Artifact storage

```
videos-container/
  raw/{team_id}/{match_id}.mp4                  # original upload
  results/{match_id}/report.json                # full per-player metrics + per-tracklet data
  results/{match_id}/tracklets/{tid}/thumb_{n}.jpg   # 3–5 crops per merged tracklet (tag UI)
  results/{match_id}/heatmaps/{roster_entry_id}.png
  results/{match_id}/preview_720p.mp4           # annotated NVENC proxy for tag review playback
  results/{match_id}/positions.parquet          # smoothed pitch-plane positions (re-aggregation without re-running GPU)
```

`positions.parquet` is the key artifact: re-tagging and finalization re-aggregate from it in Flask/CPU — **no GPU re-run when the user fixes a tag**. Read access to artifacts via short-lived read SAS minted per request.

### 3.4 Retention policy

- **Raw video:** Hot on upload → Cool at 14 days → **deleted at 90 days** (stated in ToS; teams keep their own originals). ≈ $0.10–0.20/match amortized.
- **Results** (JSON, parquet, thumbnails, heatmaps, preview clip — tens of MB): Hot, retained for the life of the account.
- Lifecycle rules on the container; deletion job also nulls `video_blob_path` on `VideoMatch`.

---

## 4. Data model

New file `src/models/video.py` (mirrors `models/journey.py` convention). Migration `aw14_video_analysis` chained after `aw13`, using `_migration_helpers.py` idempotent guards (`table_exists`, `create_index_safe`, `server_default` on NOT NULL booleans), downgrade drops indexes before tables, `ON DELETE CASCADE` from child tables to `video_matches`.

```python
class VideoMatch(db.Model):
    __tablename__ = "video_matches"
    id            = db.Column(db.Integer, primary_key=True)
    team_id       = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False, index=True)  # paying/owning team
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=True)
    opponent_name = db.Column(db.String(200), nullable=False)        # rival may not be in DB
    is_home       = db.Column(db.Boolean, nullable=False, server_default="true")
    match_date    = db.Column(db.Date)
    our_score, opp_score = db.Column(db.Integer), db.Column(db.Integer)     # nullable
    our_kit_colors, opp_kit_colors = db.Column(db.String(100)), db.Column(db.String(100))  # hex pairs
    video_blob_path   = db.Column(db.String(500))
    video_duration_s  = db.Column(db.Integer)
    capture_meta      = db.Column(db.Text)            # JSON: resolution, fps, elevation, panning answers
    quality_score     = db.Column(db.Float)           # 0–1, computed by pipeline; gates beta metrics
    status        = db.Column(db.String(30), nullable=False, server_default="created", index=True)
                   # created → uploaded → queued → processing → needs_tagging → finalized → failed → expired
    credit_ledger_id  = db.Column(db.Integer, db.ForeignKey("video_credit_ledger.id"), nullable=True)
    created_at, updated_at = ...

class VideoAnalysisJob(db.Model):                      # same shape as BackgroundJob, video-specific
    __tablename__ = "video_analysis_jobs"
    id            = db.Column(db.String(36), primary_key=True)        # UUID
    video_match_id = db.Column(db.Integer, db.ForeignKey("video_matches.id", ondelete="CASCADE"), nullable=False, index=True)
    status        = db.Column(db.String(20), nullable=False, server_default="queued")  # queued/running/completed/failed/cancelled
    current_stage = db.Column(db.String(50))           # decode/detect/track/calibrate/metrics/render
    progress, total = db.Column(db.Integer), db.Column(db.Integer)
    gpu_seconds   = db.Column(db.Integer)              # for COGS tracking
    results_json  = db.Column(db.Text)
    error         = db.Column(db.Text)
    started_at, updated_at = ...

class VideoRosterEntry(db.Model):                      # pre-processing roster (the user's intent)
    __tablename__ = "video_roster_entries"
    id            = db.Column(db.Integer, primary_key=True)
    video_match_id = db.Column(db.Integer, db.ForeignKey("video_matches.id", ondelete="CASCADE"), nullable=False, index=True)
    tracked_player_id = db.Column(db.Integer, db.ForeignKey("tracked_players.id"), nullable=True)  # NULL for rivals/untracked
    player_name   = db.Column(db.String(200), nullable=False)         # free text fallback
    jersey_number = db.Column(db.Integer)
    side          = db.Column(db.String(10), nullable=False)          # 'ours' | 'theirs'
    position_hint = db.Column(db.String(50))
    __table_args__ = (db.UniqueConstraint("video_match_id", "side", "jersey_number"),)

class VideoTracklet(db.Model):                         # CV output: one MERGED track entity
    __tablename__ = "video_tracklets"
    id            = db.Column(db.Integer, primary_key=True)
    video_match_id = db.Column(db.Integer, db.ForeignKey("video_matches.id", ondelete="CASCADE"), nullable=False, index=True)
    pipeline_track_key = db.Column(db.String(50), nullable=False)     # stable key into positions.parquet
    team_cluster  = db.Column(db.String(10))           # 'A'|'B'|'ref'|'unknown' → mapped to ours/theirs
    suggested_number = db.Column(db.Integer)           # jersey OCR vote (nullable, Phase C)
    suggested_roster_entry_id = db.Column(db.Integer, db.ForeignKey("video_roster_entries.id"), nullable=True)
    first_seen_s, last_seen_s = db.Column(db.Float), db.Column(db.Float)
    seconds_visible = db.Column(db.Float)
    merge_confidence = db.Column(db.Float)             # how sure the offline merge pass is
    thumb_paths   = db.Column(db.Text)                 # JSON list of blob paths
    roster_entry_id = db.Column(db.Integer, db.ForeignKey("video_roster_entries.id"), nullable=True, index=True)  # the TAG
    tagged_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=True)
    tagged_at     = db.Column(db.DateTime)

class VideoPlayerReport(db.Model):                     # per-roster-entry aggregation, rebuilt on finalize
    __tablename__ = "video_player_reports"
    id            = db.Column(db.Integer, primary_key=True)
    video_match_id = db.Column(db.Integer, db.ForeignKey("video_matches.id", ondelete="CASCADE"), nullable=False)
    roster_entry_id = db.Column(db.Integer, db.ForeignKey("video_roster_entries.id", ondelete="CASCADE"), nullable=False)
    tracked_player_id = db.Column(db.Integer, db.ForeignKey("tracked_players.id"), nullable=True, index=True)  # denorm for PlayerPage join
    minutes_visible   = db.Column(db.Float)
    distance_m        = db.Column(db.Float)
    distance_confidence = db.Column(db.String(10))     # 'high'|'medium'|'low' (near/far-side weighting)
    top_sustained_speed_ms = db.Column(db.Float)
    speed_bands_json  = db.Column(db.Text)             # walk/jog/run/sprint seconds
    sprint_count      = db.Column(db.Integer)
    touches_estimate  = db.Column(db.Integer)          # nullable; beta, only if quality gate passes
    touches_is_beta   = db.Column(db.Boolean, nullable=False, server_default="true")
    heatmap_blob_path = db.Column(db.String(500))
    metrics_json      = db.Column(db.Text)             # full detail incl. per-half splits
    __table_args__ = (db.UniqueConstraint("video_match_id", "roster_entry_id"),)

class VideoCreditLedger(db.Model):                     # append-only credit ledger per team
    __tablename__ = "video_credit_ledger"
    id            = db.Column(db.Integer, primary_key=True)
    team_id       = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False, index=True)
    delta         = db.Column(db.Integer, nullable=False)             # +10 purchase, -1 debit, +1 refund
    reason        = db.Column(db.String(30), nullable=False)          # 'purchase'|'debit'|'refund'|'grant'
    stripe_checkout_session_id = db.Column(db.String(120), unique=True, nullable=True)  # idempotency
    video_match_id = db.Column(db.Integer, db.ForeignKey("video_matches.id"), nullable=True)
    created_at    = db.Column(db.DateTime, ...)
```

**FK semantics (per codebase conventions):** `team_id` NOT NULL — the uploading team owns everything; `tracked_player_id` nullable everywhere — rival/untracked players live as `player_name` free text, exactly like the recon's proposed linkage; the denormalized `tracked_player_id` on `VideoPlayerReport` lets `PlayerPage.jsx` query video reports for an academy player with one indexed lookup. Reports for tracked players are **kept separate from `FixturePlayerStats`** — video-derived physical metrics are a different trust class than API-Football data and must never silently mix into `compute_stats()`.

---

## 5. API surface

New blueprint `src/routes/video.py`, registered in `main.py` alongside `journey_bp`/`academy_bp` (after `players_bp`, no route overlap). Frontend methods added to `src/lib/api.js`; new pages `src/pages/team/VideoMatchesPage.jsx`, `TagReviewPage.jsx`, `VideoReportPage.jsx`, plus `admin/AdminVideos.jsx`.

### Auth model (reusing what exists — decision)

There is **no team-account concept** today (`UserAccount` is journalist-focused; teams are org data). We reuse the existing pattern rather than invent team logins:

- **Phase A:** all endpoints under `@require_api_key` (admin) — we run it concierge-style for the Forest demo.
- **Phase B:** add `is_team_manager` boolean to `UserAccount` and a **`VideoTeamAccess`** link table (clone of the `JournalistTeamAssignment` pattern: `user_id`, `team_id`, `role`). Endpoints use `@require_user_auth` + a `_require_team_access(user, team_id)` helper. Credits belong to the **team**, not the user, so a club's coaches share a balance. Admin retains god-mode via `@require_api_key` variants.

### Endpoints

| Method & path | Auth | Purpose |
|---|---|---|
| `POST /api/video/matches` | team | Create match (opponent, date, kits, capture questionnaire) → returns match + **write SAS** for `raw/{team_id}/{match_id}.mp4` |
| `POST /api/video/matches/<id>/upload-complete` | team | Verify blob, set `uploaded` |
| `PUT  /api/video/matches/<id>/roster` | team | Bulk upsert `VideoRosterEntry` list (with TrackedPlayer autocomplete via existing player endpoints) |
| `POST /api/video/matches/<id>/process` | team | Atomic credit debit (single UPDATE-guarded ledger insert) + create `VideoAnalysisJob` + enqueue Storage Queue msg → `202 {job_id}`; `402` if no credits |
| `GET  /api/video/matches/<id>` | team | Match + job status/stage/progress (poll target, same UX as existing admin job polling) |
| `GET  /api/video/matches/<id>/tracklets` | team | Tracklet list: thumbs (read-SAS'd), team cluster, suggested number/roster match, current tag, merge confidence |
| `POST /api/video/matches/<id>/tags` | team | Bulk bind/unbind `{tracklet_id → roster_entry_id}`; also `confirm_merge: bool` answers for low-confidence merges |
| `POST /api/video/matches/<id>/finalize` | team | CPU re-aggregation from `positions.parquet` → builds `VideoPlayerReport` rows; re-runnable after tag fixes |
| `GET  /api/video/matches/<id>/report` | team | Full report JSON + SAS'd heatmaps/preview clip |
| `GET  /api/video/teams/<team_id>/matches` | team | List + statuses |
| `GET  /api/video/teams/<team_id>/credits` | team | Balance + ledger |
| `POST /api/video/teams/<team_id>/credits/checkout` | team | Create Stripe Checkout Session for a pack → redirect URL |
| `POST /api/video/stripe/webhook` | Stripe sig | `checkout.session.completed` → ledger credit (idempotent on session id) |
| `GET/DELETE /api/admin/video/matches/...` | `@require_api_key` | Admin oversight, manual refunds, credit grants, job cancel/requeue |
| `GET /players/<id>/video-reports` | public/existing | Video analysis tab on `PlayerPage` for tracked players (added to `players.py`) |

---

## 6. Billing

**Pattern: Stripe Checkout one-time payments + our own Postgres credit ledger** (`VideoCreditLedger`). Per the infra research this is the standard pattern for high-COGS per-job AI products: cash arrives **before** GPU dollars burn, no meter plumbing, no invoice-in-arrears non-payment exposure on real COGS. Explicitly **avoid** Stripe metered/usage-based billing for v1; Stripe's native billing-credits machinery is deferred until an enterprise club wants monthly invoicing with committed grants.

Note: the codebase's old Stripe Connect integration is **deprecated/removed** (recon: no active webhook handlers, `stripe_config.py` not imported). We do *not* resurrect Connect — we add a minimal new `src/services/video_billing.py` with exactly three Stripe touchpoints: create Checkout Session, verify webhook signature, handle `checkout.session.completed`. Phase A is even simpler: one Checkout Session per match, pay-then-process, no ledger needed.

**Pricing & margin math** (COGS ≈ **$3.50/match** all-in on ACA T4: $3.10 compute + ~$0.20 storage + ~$0.10 egress + ~$0.05 ops, with ~5% retry budget):

| SKU | Price | $/match | Gross margin vs $3.50 |
|---|---|---|---|
| Single match | **$25** | $25 | **86%** |
| 10-pack | **$200** | $20 | 82.5% |
| 50-pack / season deal | **$750** | $15 | **77%** |

Comparable products (Veo, Trace, Spiideo per-match analysis) sit at $25–75/match, so $25 is competitive. **Floor price $8/match** (keeps >50% margin even at worst-case $6.45 job sizing). On the later AML Spot path (~$1.10–1.30 COGS) margins exceed 90%. Refund rule: hard job failure auto-credits the ledger (+1, reason `refund`); a poor-quality-but-completed analysis is a support decision, not automatic.

---

## 7. Honest accuracy expectations

What the report can credibly claim on single-camera amateur footage (panning sideline tripod, 1080p), and how the UI says it:

**Reliable (shown plainly):** player detection near-side; team split when kits contrast; per-player heatmaps; **distance covered ±10–20%** (shown as a range, e.g. "8.2–9.0 km"); sprint counts after heavy smoothing; speed bands.

**Partial (shown with confidence badges):** far-side positions carry meters-level homography error → far-side distance/speed segments are down-weighted and the per-player `distance_confidence` badge (high/medium/low) reflects the near/far time split. Top speed is reported only as **"fastest sustained speed"** with clamping — never an instantaneous max, because homography jitter manufactures fake 40 km/h spikes. Similar kits / bibs / backlight degrade team split — flagged at processing time.

**Beta or absent (labeled, gated, or not promised):** ball-dependent metrics (touches, possession involvement) ship behind a **"Beta — estimate"** chip, computed only in high-confidence ball windows, and are entirely suppressed when `quality_score` is below threshold. Jersey OCR is only ever a tagging *suggestion*. No pass maps, no xG, no events, and **no claim of automatic player identity** — identity is what the tag review screen is for, and the marketing copy must say "you tag, we measure."

**UI mechanics:** every metric card carries a confidence badge + tooltip explaining the limitation; the match page shows the **capture quality score** with concrete improvement tips ("filming from 3–4 m elevation roughly doubles what we can extract; 4K unlocks touch detection"); we publish **filming guidelines** and gate beta metrics per-video on the quality score. This honesty is also a moat with an academy audience (Forest relationship) — per the project's no-fabrication principle, we never present a guess as a measurement.

---

## 8. Phased delivery plan (each phase shippable)

### Phase 0 — Validation spike (1–2 weeks, 1 eng)
Hand-run the open-parts pipeline (RF-DETR pretrained + roboflow/trackers BoT-SORT + roboflow/sports team-classification recipe) on 3–5 real grassroots videos on a rented GPU. Output: degradation report vs broadcast, frame-labeling plan, go/no-go on the quality bar. **No product code.**

### Phase A — Concierge MVP (4–6 weeks, 1–2 eng)
- Migration `aw14`; models from §4; `video.py` blueprint (admin-auth only); SAS upload flow; Storage Queue + ACA GPU Job env + `academy-watch-vision` image.
- Pipeline v1: RF-DETR fine-tune #1 (Universe dataset + ~2k self-labeled frames), BoT-SORT + offline tracklet merge, team clustering, pitch keypoint model v1 + smoothed homography, metrics layer (distance/speed bands/sprints/heatmaps), thumbnails + preview clip + `positions.parquet`.
- Tag review screen + report page (admin-visible); finalize/re-aggregate path.
- Billing: one Stripe Checkout Session per match, pay-then-process. Run end-to-end with the Forest academy contact as design partner.
- **Ships:** real reports for real matches, operated concierge-style.

### Phase B — Self-serve teams + credits (3–4 weeks)
- `is_team_manager` + `VideoTeamAccess`; team-facing pages (matches list, upload wizard with roster entry, credits page); credit packs + `VideoCreditLedger` + webhook; auto-refund on failure; retention lifecycle rules; `PlayerPage` "Video analysis" tab for tracked players; filming-guidelines page + capture questionnaire → quality score gating.
- **Ships:** a team can buy a 10-pack and run matches without us.

### Phase C — Accuracy + COGS (4–6 weeks, parallelizable)
- Fine-tune round #2 on accumulated consented customer footage (detector + pitch keypoints — the highest-leverage work).
- Jersey OCR assist (PARSeq recipe) feeding tag suggestions; ball model + beta touches behind the quality gate; 4K ingestion path.
- COGS: move steady-state volume to AML batch on `NC8as_T4_v3` **Spot** (~$0.69/match, ACA stays as on-demand overflow); NVDEC/TensorRT/12.5 fps optimizations locked in.
- **Ships:** noticeably better reports, ~80% COGS cut at volume.

### Phase D — Later bets (post-PMF)
Multi-match player trends ("distance per match across the season") joined to `TrackedPlayer`; opponent scouting packs; elevated-camera partnerships; event detection **only** if/when a license-clean model demonstrably transfers to customer footage; Stripe billing-credits for enterprise club invoicing.

**Dependency note:** Phase A's riskiest item is the grassroots fine-tune (everything else is plumbing this codebase already has patterns for — background jobs, polling, blueprints, admin UI). Phase 0 exists to de-risk exactly that before any product code is written.