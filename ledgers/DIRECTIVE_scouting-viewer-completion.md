# DIRECTIVE — Scouting Viewer & Sim Standard: remaining work

Status: AUTHORED 2026-08-31 (MJ: "create a directive for the remaining work"). Author: Fable.
Scope: everything left open by the 2026-08-31 arc (PRs #909–#914). Cross-repo: loanarmy (most),
local-flows (W5), basecamp ops (W6), harness (W7 pointer). Companion directives:
`harness/DIRECTIVE_app_sim_lane.md` (the sim standard) and this repo's
`ledgers/CONTINUITY_video-analysis.md` §scouting-viewer / §basecamp-analysis (evidence + R3 specs).

## Ground truth (what is DONE and live)

Basecamp qwen analysis lane (#910), Player Reels (#911), Identity Verify (#912), R2 top-moments +
clip captions + zones + direction question (#913), App Sim Lane S1 merged and proven running from
basecamp (#914). All squash-merged, deployed, prod health 200. Do not rebuild any of it; extend.

## Execution rules (unchanged, restated once)

Fable orchestrates and verifies; codex implements from surgical briefs; every PR waits for the
codex-connector review (fresh findings identified via `original_commit_id`, never re-anchored
threads); merge on a clean round via `--auto`; live-verify the user-facing behavior before any
merge. For UI-touching PRs, run `node sim/run.mjs` (SIM_EXTERNAL against the dev app) as a
pre-merge regression pass — a new `fail` verdict blocks, `concern` gets triaged in the PR text.
Sims and workers never touch prod data except the explicitly created test fixtures.

## Workstreams, in priority order

### W1 — Triage the CONFIRMED finding: player page stalls when opened from Scout Desk
Reproduced 3× by the sim (laptop ×2, basecamp ×1; screenshots in `sim/report/*/shots/`).
Suspect class: oversized/slow payload (see memory `feedback_check_payload_sizes`) or a data
dependency that hangs in dev. Investigate BEFORE feature work — the sim's credibility depends on
its first finding being acted on. Acceptance: root cause named; fix or documented wontfix with
the journey expectation updated; the sim step goes `pass`.

### W2 — Per-job pipeline `kind` → loop-mode analysis worker on basecamp
The queued follow-up from #910: migration (next head after `sw01`; guarded DDL + RLS rules per
`docs/agents/invariants.md`) adding `pipeline_kind` to `video_analysis_jobs` (default `cv`);
`process_match` stamps it; `claim_next_job`/`claim_job` filter by the worker's kind; remove the
one-shot-only guard for non-CV workers. Then an always-on basecamp analysis worker becomes safe:
launchd service (basecamp repo pattern, e.g. `com.mj.filmroom-worker`, one heavy job at a time,
memory-guard etiquette per the media lanes) polling PROD queue for `qwen_analysis` jobs.
Prod credentials handling stays orchestrator-owned; decide at install time whether the worker
gets a basecamp-resident env file (chmod 600) — flag to MJ. Acceptance: a submitted prod request
processes on basecamp with NO operator involvement; CV jobs untouched.

### W3 — R1b: club-scoped reels in the MyClub console
Auth design FIRST (Fable): club-scoped media tokens — today's media token is admin-minted and
match-scoped (`auth.py` media token, 30-min); extend minting to a club-console session for
matches belonging to the club's program, and add scope checks on footage/crops/bbox endpoints
(admin OR matching club scope; neutral 404s). Then console UI: reels view (reuse PlayerReel)
inside MyClub ▸ Matches & Reports, read-only, no verify/rebind controls for v1 (identity
corrections stay admin-side). Minor privacy rules from C2 apply unchanged (fail-closed on
minors). Acceptance: a club manager account sees ONLY their program's matches' reels; admin
surfaces unchanged; Playwright-verified both allowed and denied paths.

### W4 — Analysis quality round (assessment follow-ups)
(a) Aggregation prompt: force a player note for every RECURRING (kit, number) pair in the frame
evidence (rails still cap: only evidenced pairs); trim boilerplate team analysis (style/
strengths must cite observed phases or stay empty). (b) Regenerate captions/analysis for
existing matches after (a) — legacy captions deliberately never match post-#913. (c) Model
provenance decision for user-facing prose (MJ, decision register below): keep
`qwen3.8:27b-obliterated-q8` or pull the clean official tag — env-swappable via
`QWEN_VISION_MODEL`, zero code. (d) Cosmetic: reel-card thumbnail can show a wrong-kit crop
(crops_index keyed by merge-entity ids — ALOCAL limitation, pre-existing); fix by preferring
strong-fragment crops for the card thumbnail. Acceptance: rerun the match-4 job; player_notes
non-empty for the known recurring pairs; captions display again; MJ eyeballs one reel.

### W5 — PM ingest of sim reports (local-flows repo — run from a session with that repo's context)
A flow that reads new `sim/report/<ts>/report.json` files (loanarmy first; path config per app),
emits PM queue events: one event per `fail` and per `concern` (dedupe on app+journey+step+note
fingerprint across runs; a repeated concern escalates rather than duplicates), a quiet daily
rollup for all-pass runs, and surfaces `proposals` as their own low-priority docket item for
MJ's gavel. Morning brief cites the report path + worst step. Follow local-flows conventions
(directive → codex → its own test suite; its CONTINUITY updated). Acceptance: the W1 concern
(before its fix) or a seeded defect appears in the docket + next morning brief.

### W6 — Nightly self-boot sims on basecamp — GATED on MJ decision D1
Once D1 lands: corepack-enable pnpm; install postgres (per D1's chosen form); restore a seeded
dump of the laptop `soccer_newsletter` fixture (match 4 + roster + chains); minimal backend
`.env` on basecamp (chmod 600: DB_*, SECRET_KEY, ADMIN_API_KEY, API_USE_STUB_DATA=true,
SKIP_API_HANDSHAKE=1); replace the temporary `@playwright/test` shim with a real frontend
`setup_frontend.sh` install; launchd `com.mj.sim-loanarmy` nightly (staggered off PM jobs; plist
committed to the basecamp repo per its service pattern). Acceptance = app-sim directive §5:
a full nightly run produces a graded report; a seeded deliberate defect is caught as `fail`;
the PM docket shows it next morning (with W5).

### W7 — Sim rollout S2–S4
Per `harness/DIRECTIVE_app_sim_lane.md`: sautai + nbhd web journey packs (S2); iOS lane b-first
— laptop/Xcode Cloud simulators shipping screenshots + step logs to basecamp for grading and PM
ingest (S3b; S3a full Xcode-on-basecamp is decision D2); harness-pack scaffolding so
`harness-init` creates `sim/` for new apps (S4).

### W8 — R3 pitch analytics ladder (design-ready, build later)
Specs already recorded in `CONTINUITY_video-analysis.md`: camera-class triage at preflight →
venue calibration profiles (one-time human landmark clicks + CMC propagation) → own Apache-2.0
keypoint model + SAM3 pitch segmentation → phase-bucketed relative shape with coverage %
disclosed, fractional (0–1) pitch coordinates until venue dimensions are known. Entry condition:
W1–W4 done and at least one club actively using reels. T1 zones + T2 direction (shipped) feed it.

### W9 — Evidence Bench (added 2026-09-01)
See `ledgers/DIRECTIVE_evidence-bench.md`: honesty/merge/calibration measurements on a frozen set,
feeding D3 and the W8 entry condition. E1 (grounded-claim contract on Qwen3-VL) is the next
experiment after W4(d) lands.

### Hygiene (any quiet moment)
Delete the ~25 fully-merged stale branches (each verified tip==merged-PR-head on 2026-08-31;
`fix/transfer-resolver` `4127971` stays — frozen salvage). Remove today's worktrees when their
servers stop (`.worktrees/{qwen-analysis,player-reels,reel-verify,reel-moments,sim-lane}`,
`.claude/worktrees/season-tiebreak`). Decide prod test match 2 (keep as standing smoke fixture —
recommended — or refund+expire). The identity-correction manifests keep accumulating toward the
PARSeq jersey-reader fine-tune (existing plan; revisit when manifest count is meaningful).

## Decision register — ANSWERED by MJ 2026-08-31

- **D1 = YES, Homebrew route**: install Homebrew + postgresql@16 + corepack pnpm on basecamp.
  W6 unblocked.
- **D2 = YES, install Xcode on basecamp** (~50GB): S3a approved — full always-on iOS simulators.
  Install path: brew → mas → Xcode from the App Store (needs the box's App Store sign-in), then
  `sudo xcodebuild -license accept` + first-launch (sudo steps may need MJ at the keyboard once).
- **D3 = KEEP the current model** (`qwen3.8:27b-obliterated-q8`) for analysis prose. Revisit
  before clubs pay for outputs (env-swap via QWEN_VISION_MODEL, zero code).
- **D4 = PARK the medical-staff proposal**: logged in Marketing/ideas as parked pending a
  validate-idea run at the next ideas grooming.

## Definition of done for this directive

W1–W5 shipped and verified; W6 executed or still cleanly gated on D1; FEATURES.md rows and this
repo's ledgers updated per workstream; every merged PR carried a clean codex review round and a
sim regression pass.

## SESSION COORDINATION (added 2026-08-31 — two sessions active; SUPERSEDED 2026-09-01: the
original 08-31 session stood down; loanarmy-1a owns basecamp + codex; W6 is DONE — see BASECAMP READY)

MJ is running this directive from a SEPARATE session. Ownership split to prevent collisions:

- **The original orchestrator session OWNS the D1/D2 basecamp install chain** (Homebrew watcher
  armed → on brew appearing it proceeds: postgresql@16, corepack pnpm, seeded sim DB restore,
  mas/Xcode install attempt). Directive session: do NOT run W6 basecamp installs/ops; treat W6
  as blocked until this ledger gains a line saying "BASECAMP READY (brew/postgres/pnpm)".
  Everything else (W1–W5, W7 code work, hygiene) is the directive session's to take.
- **Ports 5001/5173 on the laptop are OCCUPIED**: MJ's browsing app runs from worktree
  `.worktrees/reel-moments` (post-#913 build; backend log /tmp/moments-backend.log, frontend
  /tmp/moments-frontend.log). For W1 triage, use these running servers (SIM_EXTERNAL=1) or boot
  on other ports — never kill by bare port (the listener-vs-client lsof lesson: use
  `lsof -ti tcp:<port> -sTCP:LISTEN`), and don't restart MJ's app without telling him.
- Worktrees `.worktrees/{qwen-analysis,player-reels,reel-verify,sim-lane}` and
  `.claude/worktrees/season-tiebreak` are FINISHED (merged) — safe for the directive session to
  remove; `.worktrees/reel-moments` stays while its servers run.
- Basecamp facts the directive session will need: ssh `mjjones@100.82.160.117` (key
  `~/.ssh/id_ed25519`, passphrase in keychain → `ssh-add --apple-load-keychain` first);
  loanarmy clone on `main` at `a591790`; `@playwright/test` there is a machine-local shim onto
  `~/Projects/visual-qa/node_modules/playwright`; ollama loopback `127.0.0.1:11434`.
- Codex lane: this session runs NO further codex dispatches — the directive session has it.

### BASECAMP READY — 2026-09-01 17:4x JST (loanarmy-1a, correcting the block above)
The "Homebrew and postgres ABSENT" observation above looked at `/opt/homebrew` — W6 was executed
2026-08-31 night via the **sudo-free user-prefix route** (basecamp's own no-sudo rule; MJ's password
was never needed): Homebrew at `~/homebrew`, `postgresql@16` running under launchd
`com.mj.postgres16` (KeepAlive; `~/homebrew/var/postgresql@16`), corepack `pnpm@10.4.1` at
`~/.local/bin`, `osv-scanner`, a REAL frontend install via `setup_frontend.sh` (the
`@playwright/test` shim is gone) + Playwright chromium, seeded `soccer_newsletter` restored
(plain-SQL dump — PG17→16), `capture_meta['local']` paths rewritten to `/Users/mjjones`, match-4
footage + v8 artifacts rsynced, minimal chmod-600 backend `.env`. Proven: graded self-boot sim
8 pass/0 fail, seeded-defect drill caught as FAIL, PM docket shows the sim card
(`com.mj.sim-loanarmy` 03:30 JST + `com.mj.localflows.sim-report-ingest` 04:15 loaded; basecamp
repo `84c7cdf`, `40aae65`, `85a1a4e`). **D2 (Xcode on basecamp, S3a) is NOT done** — parked under
W7; needs MJ at the keyboard once for `xcodebuild -license accept`. Shared-box rule since today:
another session reloading `com.mj.ollama` killed two 2-hour analysis runs — message the owning
session (local-flows) before service restarts; see memory
`feedback_basecamp_cross_session_coordination`.
