# DIRECTIVE — Dream roadmap handoff: S0 + S1 shipped (59.8%), S2 "fans + reach" next

Written 2026-09-02 (evening JST) by the orchestrating Fable session (`loanarmy-1b`) for the NEXT session. The previous
session stays open for questions for a while; ask it only what this file and the linked ledgers do not answer.
Read in this order: this file → `ledgers/GRADING_dream-scorecard-2026-09-02.md` (rubric + every row) →
`ledgers/CONTINUITY_dream-s1.md` (what shipped, how, debts) → `ledgers/CONTINUITY_dream-s0.md` → `ledgers/tooling/dream-scorecard/README.md`.

## 1. Where things stand (verified, not remembered)

- **Score:** baseline 51.9% (morning) → S0 54.1% → **S1 59.8%** (`ledgers/tooling/dream-scorecard/scorecard.json`, weights P1 25/P2 25/P3 20/P4 15/P5 15).
  Lived adoption is still ~0 (9 accounts, 5 = team; 1 claim; 0 clubs; 0 intros; $0). Artifact page (republish to THIS url with
  the Artifact tool's `url` param): https://claude.ai/code/artifact/1ac9cfc9-9540-4a41-80a6-1e3846fbb8d9
- **Merged today (all live):** S0 #957 A, #958 C (+ ACA job `job-scout-digest`), #960 D, #961 E, #959 B · S1 #963 P1, #965 P2, #968 P3,
  #964 P4, #969 P5, #974 hygiene · docs #967, #971?/#972? (n/a), docs tails. Other session merged #966, #970, #975 (video/regen work).
- **Prod (RG `rg-nbhd-prod`, app `ca-loan-army-backend`, FQDN `ca-loan-army-backend.victoriousocean-5cdd2683.westus2.azurecontainerapps.io`,
  ACR `acrbwmj`):** revision r422-x healthy; env `CONTACT_RAIL_ENABLED=1`, `SCOUT_INCLUDE_LOCAL_PLAYERS=1`, `SHOWCASE_TRUST_MIN_ACCOUNT_AGE_DAYS=14`;
  Alembic head `pm01` (pre-applied via pooler + stamped); tables `player_match_entries`, `showcase_moderation_events` (RLS on, no
  policies); `local_players.birth_date` (lp01). Secrets are `kvref:` pointers into `kv-loan-army` (resolve with `az keyvault secret show
  --id`); DB via `supabase-db-*` vault secrets + session pooler; never print values. Mailgun key rotated by MJ (vault copy in sync).
  Orphan negative `players` rows deleted (MJ approved). ACA jobs: job-sync-fixtures 05:00, job-transfer-heal 03:00, job-video-maintenance 03:00,
  job-scout-digest Mon 07:00 UTC (manual run: `az containerapp job start ... --command python /app/src/jobs/run_scout_digests.py`; use env
  `SCOUT_DIGEST_DRY_RUN=1` — `--args` overrides do NOT reach the container).
- **Repo:** main was `ec4b42b` at handoff. Primary checkout `/Users/michaeljones/Projects/loanarmy` is an integration station (keep clean;
  `git pull --ff-only`). `ledgers/CONTINUITY*.md` are gitignored → `git add -f`. Worktrees from other sessions exist under `.worktrees/`
  (`local-app` serves MJ's live dev app on ports **5001/5173 — never touch**; owned by session `loanarmy-ac`). Stray local branch named
  `origin/main` was deleted today — if `origin/main` ever resolves ambiguously, use `refs/remotes/origin/main`.
- **Peers (ListAgents):** `video-analysis` (basecamp regen work; coordinate the deploy lane — EVERY merge incl. docs triggers the full Deploy
  and locks ACA ~5 min; message before merging), `loanarmy-ac` (holds 5001/5173), sautai sessions (codex account load; ~8–9 concurrent
  codex runs is the practical ceiling; stagger). Basecamp: SSH `mjjones@100.82.160.117` (`ssh-add --apple-load-keychain`); check
  `pgrep -f "qwen_match_analysis|run_bench"` before any graded sim/ollama use; Ollama calls omit `num_ctx` or pin 65536.
- **PR review bot (`chatgpt-codex-connector`)** hit its daily quota mid-day; when it works, READ its threads before merging (it caught 3 real
  defects on #963). Branch protection `strict` is OFF (keep it off); a "Head branch is out of date" merge error → `gh pr update-branch`.

## 2. The method that worked (reuse exactly)

1. **Recon** (codex, `--sandbox read-only`, ultra effort, strict JSON final message via `-o`): re-verify every anchor of the design doc
   against a detached worktree at `refs/remotes/origin/main` (the primary checkout can be stale). Extract a package split with DISJOINT
   file sets + HTTP contracts so frontend can build against mocks in parallel.
2. **Briefs**: `ledgers/tooling/dream-scorecard/codex-brief-common.md` header + package body (numbered requirements with path:line anchors,
   ALLOWED file list, gates with exact interpreters, ONE commit with exact message, final-report contract). Worktree per package
   (`git worktree add .worktrees/<pkg> -b <branch> refs/remotes/origin/main`).
3. **Launch** codex ONLY from a foreground Bash with a generous timeout (≥120 s):
   `nohup caffeinate -is codex exec --cd <wt> --sandbox danger-full-access -o <report> "$(cat brief)" < /dev/null > <log> 2>&1 &`.
   Never inside a background waiter (a TaskStop/timeout cascade killed two runs today). Watch with a persistent Monitor that checks the
   report file, `pgrep -f <report>` and death strings — EXCLUDE lines containing `chatgpt-codex-connector` (the bot's own "usage limits"
   comment false-alarmed). A killed run with WIP on disk → `codex exec resume <session id> "killed externally… finish per brief"`.
4. **Check**: a `model:'fable'` general-purpose subagent per package using `checker-brief-template.md` (read-only; own Vite on 5185; JSON
   verdict CLEAN|FIX-FIRST|REJECT). Every package today needed 1–3 fix rounds; fix rounds resume the same codex session with a numbered
   fix brief; re-check each round (SendMessage to the same checker). Orchestrator arbitrates and extends ALLOWED when a fix genuinely needs it.
5. **Land**: push → draft PR → CI (`gh pr checks --watch`) → `basecamp_sim.sh <branch>` (9/9) → bot threads read/answered/resolved →
   `gh pr ready` → lane idle (`gh run list --branch main --limit 1` completed; message peers) → `gh pr merge --squash` → prod DDL pre-apply
   BEFORE merge / `alembic_version` stamp AFTER → watch Deploy (frontend-only merges use "Deploy Frontend (fast)") → verify the user-facing
   symptom live (health, routes, bundle strings) → cleanup gated on `MERGED` with `&&` only (a `;`-chained branch delete after a failed merge
   auto-closed a PR today; recovered via re-push + `gh pr reopen`).
6. **Re-score**: put verdicts in `overrides.json` (score, reach, blocker), run `score.py` → `build_report.py` → `build_html.py`, copy the
   ledger md + bundle into `ledgers/`, republish the artifact with `url`, update `CONTINUITY.md` §Now, `~/Projects/FEATURES.md` row, memory.

## 3. S2 — "fans + reach" (next stage; MJ said "say go S2" → wait for that)

**Target rows → 3:** 1.7 have fans (now 2), 5.3 reach (now 2), 1.6 know-you're-watched on web (now LIVE_IOS only), plus 1.2 already 3.
Projected after S2 ≈ 61–62% (compute, don't type). Decisions already made: fans = ANY signed-in account may follow a player (no scout
verification), public fan counts only for adult public subjects, share cards only for public adult profiles, notifications email-first (no APNs
exists), everything minor-safe (neutral 404s, never expose minors).

**What the code already has (today's verified anchors):**
- `Follow` (`models/follow.py`, kinds player|academy_club|geo|query, JSON selector) written by ANY authenticated account via
  `POST /api/scout/lists/<id>/follows` (scout.py ~L1935) — the "fan follow" primitive exists but is scout-branded; `follow_resolver.py`
  accepts negative ids for approved adult locals (S1 P2). `PlayerInterestSignalsViewModel` (iOS) shows Watchlists/Follows counts via
  showcase.py ~L1805 (owner-only "scouts watching you" — web has NO surface).
- Comments on tracked-player pages (`PlayerPage.jsx` ~L1426); nothing on `LocalPlayerPage`.
- Product events: `routes/events.py` allowlist (pageview, claim_submitted, search_performed, list_created, follow add/remove) + AdminDashboard.
- Email: `email_service.send_email` — 7 send sites (login codes, claim/scout/club decisions, subscriber verification, newsletter digest,
  scout digest). Weekly `job-scout-digest`. No push.
- SEO: SPA shell served at every route (no `sitemap.xml`, homepage-only og tags; newsletters carry og); `academy-watch-frontend/public/
  staticwebapp.config.json` is the SWA routing file; Pillow IS in backend requirements (share image rendering feasible server-side).
- Trust tiers live (P5) so profile edits no longer hide profiles.

**Smallest correct mechanisms (recon must re-verify before briefs):**
- F1 Public follow: a default per-account "Following" FollowList (kind player) + `POST/DELETE /api/players/<signed id>/follow` wrapper +
  `GET .../followers/count` (adults/public only; negative ids via resolver; minors → neutral 404). Web "Follow" button on PlayerPage +
  LocalPlayerPage; fan count on the page (owner + public). Emit product events `follow_added/removed` (already allowlisted).
- F2 "Who's watching me" on web: reuse showcase.py ~L1805 for the owner card (counts of watchlists/follows/profile views last 7/30 days —
  add `profile_view` product event emitted by PlayerPage/LocalPlayerPage).
- R1 Share card + per-player og tags: backend `GET /share/players/<signed id>` returns minimal HTML with og:title/description/image
  (+ `<meta http-equiv=refresh>`/JS redirect to the SPA route for humans) and `GET /share/players/<id>/card.png` (Pillow-rendered 1200×630:
  name, position, club, season line, provenance chip); SWA `staticwebapp.config.json` route for `/p/<id>` → backend (verify SWA can proxy to
  the API host; else serve share links on the API FQDN). Public adult subjects only; suppression + minor bridges apply.
- R2 Sitemap + robots: backend `GET /sitemap.xml` (public adult players + local adults + teams + newsletters, cached) + `robots.txt`
  pointing to it; SWA route to proxy `/sitemap.xml`. Check `PUBLIC_BASE_URL`.
- R3 Email notifications (opt-in, per-account setting): "new follower", "someone watchlisted you" (aggregate, never identity unless the
  scout opts in), weekly "N scouts viewed you" — via the existing email service; a small `notification_preferences` (env-gated) OR reuse
  `user_accounts.email_delivery_preference` (recon: what values exist). Send from the digest job or a new weekly job (ACA job creation
  = orchestrator, same pattern as job-scout-digest; secrets copied vault→vault).
- Package split suggestion: S2-P1 backend follow/count/events (+ notifications prefs), S2-P2 backend share/og/sitemap (+ SWA config),
  S2-P3 web (follow button, fan count, watching-me card, share button), S2-P4 notifications job. Disjoint files; contracts first.

**Acceptance (live):** an anonymous visitor sees a fan count on a public adult player; a signed-in non-scout account can follow/unfollow;
`curl -A facebookexternalhit https://theacademywatch.com/p/<id>` (or the API-host share URL) returns og tags with the player's name;
`https://theacademywatch.com/sitemap.xml` is real XML; a follow triggers an email to an opted-in owner (dry-run in prod first).

## 4. Debts / queue (do not lose)
- S1: partial unique index `(player_api_id, match_date, opponent, club_program_id) WHERE source='club'` + persisted
  `player_match_entries.video_match_id` (migration; dedupe first); iOS has no add-a-game / birth_date on local create; `lock_player_refresh`
  public name; club dialog re-open pre-fill by member id; pre-existing failing tests `tests/test_local_clubs.py TestAffiliationVisibility` ×3,
  `tests/test_account.py` ×1 (on main before S1); CLAUDE.md lists "13 blueprints" — now more.
- S0: iOS local-create lacks birth_date; upload attestation (5.1); paid-subscriber cancel/billing-portal route; default `playwright.config.js`
  webServer targets 5173 (use `E2E_BASE_URL` + own Vite).
- Roadmap after S2: S3 money rails (Stripe checkout; needs the Phase-0 paper items), S4 Film Room self-serve, S5 part-ownership (counsel first),
  S6 ten real participants (the multiplier). See the scorecard ledger's stage table.

## 5. Questions worth asking the previous session (while it is open)
Only things not written down: judgement calls behind a decision, why a checker finding was accepted/deferred, or where a scratchpad-only
artefact lived. Everything else is in the ledgers, the evidence bundle (`ledgers/research/dream-scorecard-2026-09-02.json`: recon, every
checker verdict, prod counts) and `ledgers/tooling/dream-scorecard/`.
