# DIRECTIVE — Coach's brief first, positioning as the long pole, merge signals alongside

Status: AUTHORED 2026-09-02, REVISED same day after a codex read-only critique (21 findings, 11 blockers — all
folded in below; critique record in the session scratchpad, summary in §10). MJ: "lets go with 1" — brief first,
then positioning; E2 alongside. Author: Fable. Inputs: codex recon of main `bea9ec6`, `DIRECTIVE_evidence-bench.md`
(E2/E3, decisions D1–D5), `DIRECTIVE_scouting-viewer-completion.md` (W8 R3 ladder), regens 9–11 on match 4.
Decisions in THIS directive are numbered **B1–B5** to avoid colliding with the bench directive's D1–D5.

## 1. Why this exists

The honesty gate works end to end (regen 9: 33/56 clip notes and 10/15 read observations tracking-verified;
#956/#962 removed the plumbing losses). What a coach sees is true but thin, because the model has no idea what the
club wants to see. MJ's product read: a club identifies its players and corrects the system first (exists), then
positioning lets notes be about *where* a player is, and the club can state **what it expects from each player in
its system** — privately, never shared with other clubs. The coach's expectations become the question the model
answers; the report reads as *expected vs evidence found*, under the same evidence gate.

Order (MJ): **Track C — coach's brief ships first**; **Track P — positioning/calibration in parallel** (E3);
**Track M — merge signals as research** (E2). Nothing loosens the gate: a brief adds *questions*, never *claims*.

## 2. What exists (verified citations; build on it)

- **Club scope.** `ClubProgram` (`models/funding.py:114`), `ClubProgramManager` (`:275`), private roster
  `ClubRosterMember` (`:331`: `program_id`, `player_api_id` XOR `local_player_id`, `role` ≤80, `note` ≤500 —
  add-only via `POST /club/<pid>/roster` + `DELETE`, no PATCH; `routes/club.py:248-317`). `VideoRosterEntry`
  (`models/video.py:201`: `player_name`, `jersey_number`, `position`, `club_roster_member_id` SET NULL — set ONLY
  by the club roster PUT, `club.py:577`; the admin roster PUT sets name/position/tracked player only,
  `routes/video.py:266-270`). `VideoMatch.club_program_id` (`video.py:78`), `capture_meta` JSON (`:86`) whose
  recognised keys are `local`, `qwen_analysis`, frame-size keys and `attack_direction_first_half`
  (`routes/video.py:181-203`); `boxes_blob_path` (`:91`).
- **Authorisation contract.** `@require_club_manager()` returns a neutral **403** for unmanaged/unknown programs
  (`services/club_registry.py:184-185`); under an authorised program, foreign or missing child resources return a
  neutral **404** via `_club_match` (`club.py:142`); the reel route re-checks each roster binding (`club.py:490-517`);
  club media tokens carry `club_program_id` (`auth.py:247-276`), serving re-checks it (`video.py:792-811`).
  Tests: `tests/test_club_console.py:1017-1096`.
- **RLS + migrations.** Table-creating migrations enable RLS in the same upgrade (`c201_club_console_backend.py:103-150`);
  when the prod DB secret is available and the check connects, deploy fails on any public table without RLS
  (`deploy.yml:84-120`). Prod never runs Alembic: guarded DDL is pre-applied and `alembic_version` stamped
  (`docs/agents/backend.md:26`). Head **`lp01`** (← `bx01` ← `jk01`).
- **Analysis context.** `vision_worker._analysis_context` (`:211-258`): `opponent_name`, kit colours,
  `competition`, `attack_direction_first_half`, `frame_size`, `caption_windows[]` (`tracklet_id`, `roster_entry_id`,
  `roster_jersey_number`, `kit_color`, `start_s`, `end_s`, `box_track`), `player_tracks` keyed by roster-entry id.
  No `roster` key. **The team pass serialises the whole remaining context** after dropping only `caption_windows`,
  `frame_size`, `player_tracks` (`qwen_match_analysis.py:2200-2204`, `build_team_prompt :551`) — anything added to the
  context reaches the ungated team-summary call.
- **Reads.** `build_player_prompt(player_pair, evidence_frames, grounded_contract)` (`:477-512`) takes only
  `(kit_color, jersey_number)`; reads are scheduled ONLY for `required_player_pairs` = recurring readable jersey
  evidence (`:2205-2222`, loop at `:1736`); grounded schema `{"observations":[{observation, box_t, box}],
  "confidence"}` ≤3 (`validate_player_read_schema :956-1019`); `_gate_model_items` (`:1687-1697`) indexes
  `item["box"]`/`item["box_t"]` unconditionally; a note with zero surviving observations is dropped and
  `validate_analysis_schema` rejects hollow observation arrays (`:1183-1235`). Grounding counters:
  `:1115-1145` (validate), `:1472-1479` (init), `:2210-2217` (runtime); honest limits `:89-94`, `:1431-1442`.
- **Persistence + serialisers.** `video_analysis_store.py:33-36` writes `capture_meta["qwen_analysis"]`, and
  `VideoMatch.to_dict()` (`video.py:126-142`) returns `capture_meta` verbatim on admin create/upload-complete/
  PATCH/GET/finalize/report/team-list (`routes/video.py:106,170,209-224,623,678,694`) and on club create/list/
  upload-complete/PATCH/GET/process/report (`routes/club.py:354,377,434,460,469,616,664`). Public showcase
  footage selects explicit fields and excludes club-console matches (`showcase.py:1200-1229`); `feedback-export`
  and `training-manifest` serialise only feedback rows/crops (`video.py:1059-1070`, `:1117-1122`).
- **UI.** `PlayerReel.jsx TeamOverview` (`:689-776`) renders `match_summary`, `team_analysis`, `player_notes`;
  evidence is a non-interactive `<span>` (`:753-768`) — no seek callback. MyClub renders it `readOnly`
  (`MyClubConsole.jsx:650-702`). Roster tab: `AddRosterMemberDialog` (`:190-197`, `:370-377`), member rows show
  note + Remove (`:440-455`). Match creation uses `EMPTY_MATCH_FORM`/`CreateMatchDialog` (`:496-546`); detail
  reconciliation uses `MATCH_FORM_FIELDS` (`:77-87`). Admin PATCH and club PATCH can REPLACE `capture_meta`
  wholesale (`video.py:198-203`, `club.py:455-456`). `honest_limits` is persisted but rendered nowhere.
- **Sim/grader.** Every sim step screenshots the full page (`sim/lib/driver.mjs:85-99`); the grader sends it
  to Ollama and stores the note (`grade.mjs:81-94`); local-flows ingests notes + screenshot paths into PM findings
  (`local-flows/runner/sim_report_ingest.py:483-508`).
- **Positioning.** No homography/keypoint/calibration persistence anywhere; `docs/film-room.md:23-26` says so.
  Box tracks `[t,x1,y1,x2,y2]` source px ≤4 Hz, blob keyed by tracklet id (`video_boxes.py:12-110`). Local
  SoccerTrack slice = ONE scene: `117093_homography.npy` (3×3), `117093_keypoints.json` (65 pairs), a 47-frame
  (1.88 s) mp4; no MOT annotations. The 317-image CC-BY keypoint set is referenced, not downloaded, no
  source/version/checksum recorded. RF-DETR harness is inference-only (`bench_detect.py`).
- **Merging.** `candidate_pairs(tl, sim_threshold, max_gap, frame_width)` (`merge_tracklets.py:335-402`) gates
  on gap/team/spatial/SigLIP cosine; `IntervalDSU.try_union` (`:322-332`), called by `merge_entities` (`:415-447`),
  rejects impossible overlap. `chain_identities.calibrate/choose_gates` (`:202-283`) = leave-one-out
  precision/recall over anchored members. `build_feedback_labels` rows carry crop, final tracklet id and jersey
  number — not atomic fragment identity; tombstoned over-merged chains are skipped (`video_feedback.py:27-83`,
  `:38-43`). The bench has claim metrics only (`bench/score.py:307-373`).
- **Match 4 (the acceptance footage) is NOT a club match:** `club_program_id = NULL`, all 18 roster entries have
  `club_roster_member_id = NULL` (read-only DB query, 2026-09-02).

## 3. Track C — Coach's brief (ships first)

**Product rule.** A brief is the club's private statement of what it expects from a player in its system. The
model uses it as *the question to answer*. Each expectation gets exactly one verdict:
**`evidence_found`** — the model boxed the player in a sampled frame it says supports the expectation, and that
box passed the tracking gate — or **`no_evidence`**. The UI label is **"Evidence at mm:ss"**, with the disclosure
that *the player's identity and location were verified mechanically; the behaviour itself was not*. Never "seen",
never "not done" (absence is not decidable from sampled frames; B4). A coach can later confirm/reject each
evidence card; those confirmations are the only path to calling anything "verified behaviour".

**Privacy rule.** Brief text lives only on the owning club rows and is returned only by `@require_club_manager()`
club routes. **Brief text is never persisted in `capture_meta.qwen_analysis`** (every match serialiser returns
it): the analysis stores `brief_hash` (sha256 of the normalised brief), `expectation_index`, verdict and evidence
only; the club UI joins indexes to the current brief and shows "Brief changed — rerun analysis" when the hash
differs; admins see index + verdict only. Briefs never enter `feedback-export`, `training-manifest`, sim
screenshots/reports or PM ingest; they never train a shared model. Name screening: the system supplies no DB name
field to the model; the UI says "describe behaviours, not people"; the server rejects a brief line containing any
roster `player_name` / `display_name` token of that program (case-insensitive, ≥2 chars) with a plain message (B3).

**C1 — Storage + API (backend, migration `cb01` ← `lp01`).** Six guarded `add_column`s on the owning rows (RLS
already enabled; deletion cascades naturally; no new table):
`club_roster_members.coach_brief_body` Text, `.brief_updated_at`, `.brief_updated_by_user_id` FK
`user_accounts` nullable ON DELETE SET NULL; `club_programs.system_brief_body` Text, `.system_brief_updated_at`,
`.system_brief_updated_by_user_id` (same). Bounds: trimmed, ≤2000 chars, ≤12 non-empty lines, one expectation per
line. Routes (`@require_club_manager()`; unmanaged program → existing neutral 403; foreign/missing member under an
authorised program → neutral 404): `PUT /club/<pid>/roster/<member_id>/brief` (empty body clears — no separate
DELETE), `PUT /club/<pid>/system-brief`. The private roster response (`getClubRoster`) gains per-member `brief`
{body, updated_at} and a top-level `system_brief`. Tests: scoped write/read, foreign 403/404, clear-by-empty, name
screening, `feedback-export`/`training-manifest`/admin `match.to_dict()` sentinel-leak tests, single-head test,
idempotent migration test.

**C2 — Context + prompt + schema + gate (worker + spike).** `brief_context` is assembled SEPARATELY from
`analysis_context` (never added to it, so the team pass cannot see it): for each roster entry of a club match
with `club_roster_member_id → coach_brief_body`, `{roster_entry_id: {"lines": [...≤8], "hash": sha256}}` plus
`system_brief {lines, hash}`; written to `brief.json` beside `context.json`; admin matches without a program emit
none and follow the legacy path byte-for-byte. `position` and names are NOT passed (v1). **Scheduling:** brief
reads run for every briefed roster entry that has a resolvable `(kit, number)`, a `player_track`, and ≥1 grounded
evidence frame — independent of the OCR-recurrence rule that schedules ordinary reads; entries lacking those get
an honest limit line ("brief for #N could not be checked: no verified frames"). Prompt: per-player read call gains
"The coach's expectations for this player, numbered: …" (+ "How the team plays: …" when a system brief exists)
and "For each numbered expectation return {expectation_index, verdict:'evidence_found'|'no_evidence', box_t, box}.
`evidence_found` only when a frame visibly supports it AND you box the player there; otherwise `no_evidence`.
Never state an expectation was not met." Schema adds `expectation_checks` (exactly one entry per fed index;
`evidence_found` requires a sent timestamp + valid box; `no_evidence` requires null evidence). **New
`gate_brief_checks`** (separate from `_gate_model_items`): keeps every check, downgrades a failing
`evidence_found` to `no_evidence` and counts it; a player note may have zero observations when it carries
non-empty `brief_checks`. Persisted `player_notes[i].brief_checks = [{expectation_index, brief_hash, verdict,
t?, box?, iou?}]` (no text); counters `sampling.brief_checks_total/evidence_found/downgraded`; new honest limit
"Coach's-brief expectations were checked against sampled frames only; 'no evidence' is not 'did not happen'; an
evidence frame verifies the player's identity and location, not the behaviour." Caps re-checked with a mocked
size test (8 checks + 3 observations within `GROUNDED_PLAYER_NUM_PREDICT`; raise to 1200 if not). Tests: prompt
contains numbered brief + no-negatives rule; brief never in team-pass prompt; schema; gate downgrade counted;
zero-observation-with-checks accepted; legacy path byte-identical.

**C3 — Club UI + display (frontend).** Roster tab: per-member "Coach's brief" editor (textarea, 2000 chars, "one
expectation per line — describe behaviours, not people", Save / Clear, shows updated time) and a "How we play"
system brief at the top; `api.js`: `setRosterMemberBrief`, `setClubSystemBrief` (club calls never send admin
headers — extend `tests/player-reels.test.mjs`). Reel display (`TeamOverview` player note, admin and MyClub
read-only alike): a "Coach's brief" block after the observations — each expectation line joined by index when the
hash matches (club view) showing **Evidence at mm:ss** (same chip family as verified marks; timestamp only, no
seek in v1 — seeking is a separate task) or **No evidence in sampled frames**; the disclosure line; "Brief changed —
rerun analysis" on hash mismatch; admin view shows "Expectation 3: evidence at 42:00". Also render
`honest_limits` as a collapsed "What this read cannot tell you". Tests: unit (api paths/headers), `e2e/club-reels
.spec.mjs` (block visible in MyClub; foreign denial unchanged; brief text absent from any admin payload). **Sim:**
`club-console` journey gains `brief-edit` + `brief-in-reel` steps that run ONLY against the synthetic club fixture
with synthetic brief text; MJ's real briefs never appear in any graded/ingested run.

**Acceptance (Track C).** (1) Acceptance footage = match 4 via a **basecamp-only fixture bridge** (script, never
prod): assign the AFC Yorkies program to match 4 and map its roster entries to same-program `ClubRosterMember`s;
OR a genuine club upload of the same footage through MyClub (B1). (2) MJ writes briefs for three *eligible*
entries (have `(kit, number)`, a player track and grounded frames — the pipeline lists eligible entries) plus a
system brief. (3) Regen on basecamp → `brief_checks` for those three, every `evidence_found` gate-verified,
counters present, `brief.json` absent from the team-pass inputs (test). (4) MyClub shows the block; admin payloads
contain no brief text (sentinel test); foreign club sees nothing. (5) MJ eyeballs one player: is *expected vs
evidence found* the shape a coach wants? (6) Bench addendum: per-expectation truth records
`{expectation_id, adjudicated_verdict, t, box}` for the 5 hardest frozen clips (this is `DIRECTIVE_evidence-bench.md
§7 D2`'s human labelling, made structured); report precision of `evidence_found` over those labels with sample
size — report only, no gate change.

## 4. Track P — Positioning / calibration (parallel long pole; = E3, made concrete)

**P1 — Camera preflight (small, rides with C3).** Two fields, separate axes: `capture_meta.camera_view ∈
{panoramic, wide_fixed, broadcast}` and `capture_meta.camera_motion ∈ {fixed, panning, handheld}` (+ optional
`pitch_lines_visible ∈ {all, partial, none}`). Collected in BOTH the club create dialog and the detail form, and
by admins; validated by ONE shared backend helper used by admin POST/PATCH and club POST/PATCH that **merges only
these named keys into the existing `capture_meta`** — never replaces the object (today's PATCH can erase
`qwen_analysis`/`local`; fix that in the same PR). Purpose: bucket every calibration result by class.

**P2 — Calibration research on basecamp (no product code).** Record provenance first (dataset source, licence,
version, split, checksums for the 317-image CC-BY set and the SoccerTrack v2 slice). Convert to RF-DETR Keypoints
(Apache; never Ultralytics); train small; write `bench/calibration.py`. **Report separately:** (a) reprojection
accuracy on the single labelled SoccerTrack scene (the only truth we hold); (b) homography-production and
plausibility rate on 50 match-4 panoramic frames (unlabelled — overlays for human inspection); (c) failure modes
by P1 class. **An ≥80% accuracy gate is not claimable until truth exists**: either annotate pitch landmarks on
those 50 match-4 frames (a ~1 h human click task; B5) or obtain an independently labelled multi-scene set (full
SoccerTrack v2, gated). Kill: unusable on panoramic after two iterations → park; Track C does not depend on P.

**P3 — Wiring (only after P2 passes on real truth).** Persist calibration per match (`video_match_calibrations`
with RLS, or a namespaced `capture_meta.calibration`, decided with P2 numbers): homography (time-indexed samples
for moving cameras, one matrix for fixed), `camera_view/motion`, `success`, `reprojection_error_px`, keypoints.
Pitch coordinates from persisted box tracks as **fractional 0–1**; first-half attack direction reversed after
`second_half_kickoff_s`. Unlocks **normalised heatmaps and pitch thirds only**; distance/speed/sprints stay
`suppressed` in `video_report.py` until pitch dimensions and scale are known and validated. Brief prompts may
then carry *numbers* ("left third in 64% of sampled frames"), never positional prose. Formation view stays
behind the R3 ladder.

## 5. Track M — Merge signals (research alongside; = E2, made concrete)

**M0 — Truth first.** Merge precision/recall/IDF1 need identity truth we do not have: feedback rows carry final
tracklet id + number, skip tombstoned over-merges, and hold no frame-level associations; the local SoccerTrack
slice has no MOT file. M0 builds a **chain-truth artifact** for match 4: a consent-gated chain export with
`member_fragment_ids`, split tombstones and false-merge records, plus frame-level predicted→truth associations
for IDF1; and obtains SoccerTrack v2 MOT annotations before that dataset is listed as truth.
**M1 — Scorer.** `bench/merge_score.py` over the M0 artifact: merge precision (first), recall, IDF1 per gate
setting; until M0 exists the bench reports crop/ReID accuracy only and says so.
**M2 — Challengers.** OSNet-x0.25 (MIT) and DINOv2-small (Apache) over sharpest torso crops as an *additional*
score term in `candidate_pairs` behind the existing gates; adopt only if M1 precision rises at ≥ recall on the
human-confirmed set; an embedding alone never merges. Kill: no precision gain → keep SigLIP.

## 6. Guardrails

- Briefs: club rows only; club routes only; hash+index in analysis, never text; name screening; never in
  exports, manifests, sim screenshots/reports, PM ingest, or shared training. Verdicts `evidence_found |
  no_evidence` only; the label discloses what was verified (identity + location) and what was not (behaviour).
- No DB name field to the model; `position` withheld in v1. Opposition players never get briefs or reads.
- Licence gate unchanged (Apache/MIT/BSD/CC-BY in production paths; RF-DETR Keypoints, not Ultralytics).
- Basecamp etiquette: `pgrep -f "qwen_match_analysis|run_bench"` + message the owning session; omit `num_ctx`
  or pin 65536 (portfolio rule 2026-09-02).
- Every PR: connector review read, Fable-subagent adversarial pass, sim regression where UI changes.

## 7. Rollout order (explicit)

1. C1 PR reviewed → **pre-apply guarded DDL on prod via the pooler**, verify columns + stamp `cb01` → merge C1 →
   deploy. 2. Upgrade basecamp's seeded DB (`flask db upgrade`) + run the match-4 fixture bridge (B1) + seed the
   synthetic club fixture for sims. 3. C2 PR (worker + spike) → merge → basecamp pulls. 4. C3 (+P1) PR → sim
   regression on the synthetic fixture → merge → deploy. 5. MJ writes the three briefs + system brief in MyClub
   (basecamp app or prod, per B1). 6. Regen → acceptance §3. In parallel from step 1: P2 and M0 as research
   briefs on basecamp; M1/M2 after M0.

## 8. Decision register — MJ (B-numbers; the bench directive owns D-numbers)

- **B1 — acceptance footage:** basecamp-only fixture bridge for match 4 (recommended: reuses the finished CV run;
  script lives outside prod) vs. a genuine MyClub upload of the same footage (slower, but exercises the whole
  club flow — worth doing once as the first "club actively using reels").
- **B2 — system brief in v1:** yes (recommended; three guarded columns on `club_programs`).
- **B3 — free text with roster-name screening + "behaviours, not people" (recommended)** vs. a structured
  expectation vocabulary (safer, less expressive; can come later from confirmed cards).
- **B4 — verdicts `evidence_found | no_evidence` with the identity/location-only disclosure (recommended);** no
  "seen", no "not done" in v1; coach confirm/reject on evidence cards is the path to "verified behaviour".
- **B5 — P2 truth:** annotate pitch landmarks on 50 match-4 frames (~1 h of clicks, MJ or a delegated labeller)
  once P2 shows feasibility on the SoccerTrack scene (recommended) vs. acquiring the gated full SoccerTrack v2 now.

## 9. Definition of done

C1–C3 (+P1) merged and deployed with `cb01` pre-applied on prod and basecamp; the acceptance regen shows
`brief_checks` for MJ's three briefs with every `evidence_found` gate-verified and no brief text in any match
serialiser (sentinel tests green); MyClub renders expected-vs-evidence + honest limits; foreign-club, export and
sim-privacy tests green; P1 fields live and `capture_meta` never replaced wholesale; P2 answered with the two
separate numbers (SoccerTrack accuracy, match-4 plausibility) and a provenance record; M0 artifact defined and
M1 reporting honestly (ReID-only until truth exists); B1–B5 recorded here.

## 10. Critique record (2026-09-02, codex read-only)

21 findings: 5 citation fixes (wrong file for `attack_direction_first_half`, `candidate_pairs` vs `try_union`,
grounding-counter lines, conditional RLS check, 403-vs-404 contract); data model → columns on owning rows (§3 C1);
match 4 not a club match → fixture bridge (B1); read scheduler excludes briefed players → explicit eligibility
(§3 C2); context leaks to the team pass → separate `brief.json`; free text vs "no names" → screening (B3);
gate/schema incompatibility → `gate_brief_checks` + zero-observation notes; box ≠ behaviour → `evidence_found`
+ disclosure (B4); verbatim text in `qwen_analysis` → hash+index only; sim screenshots/PM ingest → synthetic
fixture only; P1 form/PATCH surface + capture_meta replacement bug; P2 has no truth denominator → split
reporting + B5; P3 scale → heatmaps/zones only; M1 truth impossible from feedback rows → M0; bench acceptance
needs structured per-expectation truth; UI seek does not exist → timestamp only; rollout order made explicit.
