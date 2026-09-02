# GRADING — How far is The Academy Watch from the dream? (2026-09-02)

Parent: `CONTINUITY.md`. Method: three codex (gpt-5.6-sol, ultra) read-only code audits scored 31 capabilities 0–4 against the dream; two Fable adversarial reviewers re-verified every cite at origin/main `ade7bbc` and re-scored; Fable arbitrated. Prod counts measured read-only via the Supabase pooler. Raw evidence: session scratchpad `out-A/B/C.json`, `review-1/2.json`, merged `scorecard.json` (copied to `ledgers/research/dream-scorecard-2026-09-02.json`).

## The dream (graded against this)

> A place where young players share about themselves and get found by clubs and scouts, and have fans. Clubs track their players and analyze their growth with all the tools to improve players and the club. Scouts find and analyze players. Later: Patreon / BuyMeACoffee-style funding that makes supporters part-owners of grassroots clubs.

## Headline

**Built: 54.1%.** Weighted across five pillars. **Lived: ~0%.** Prod has 9 accounts (5 are the team), 1 claimed player, 0 clubs, 0 watchlists, 0 introductions, 0 revenue. The code is half a platform; the marketplace has no participants yet.

## Scale

| Score | Label | Meaning |
|---|---|---|
| 0 | Missing | No code, no model, no route. |
| 1 | Designed / stub | A plan, a column, or a placeholder route. Nothing a user can do. |
| 2 | Built, unreachable | The backend works but the target user cannot use it: no button, flag off, admin-only, or an admin has to act every time. |
| 3 | Usable end-to-end | The target user can finish the job on at least one client in prod, with rough edges. |
| 4 | Complete | Every relevant client, tested, live, no known safety or correctness caveat. |

Rule that decides most scores: backend-without-a-button is a 2, never a 3. Flag-off-in-prod is a 2. Admin-per-use is a 2.

## Pillars

| Pillar | Weight | Score |
|---|---|---|
| P1 — Players: share, be found, have fans | 25 | **56.2%** |
| P2 — Clubs: track, analyze growth, tools to improve | 25 | **61.1%** |
| P3 — Scouts: find and analyze | 20 | **67.9%** |
| P4 — Funding: Patreon/BMAC → club part-ownership | 15 | **21.4%** |
| P5 — Foundation: safety, correctness, reach, ops, money, adoption | 15 | **53.1%** |

### P1 — Players: share, be found, have fans — 56.2%

| # | Capability | Score | Reach | Blocker | Next step | Effort |
|---|---|---|---|---|---|---|
| 1.1 | Create or claim my profile | 3 (codex said 2) | LIVE_WEB_IOS | [S0 A LIVE #957] web self-claim now sends contract_status (dialog mirrors iOS); local self-claims require birth_date ≥18 or fail-closed year (D1); birth_date stored (lp01) so exact-18 adults are public. Remaining: every claim still needs one admin review; iOS local-create lacks birthDate. | Pass contract_status through ShowcaseSection.submitClaim and APIService.submitProfileClaim; enforce is_minor_birth_year in create_local_player and admin_review_claim. | S |
| 1.2 | Share about myself | 2 | LIVE_WEB | Every edit hides the approved profile until another manual admin review. | Diff fields inside _upsert_subject_showcase_profile, preserving approved low-risk fields while staging contract, club, and agent changes. | M |
| 1.3 | Add my own games and stats | 1 | DESIGNED_ONLY | No persisted user-reported match grain exists. | Implement PlayerMatchEntry and owner-gated CRUD, append _user_cells to _FEEDERS, call refresh_player, then add the web form. | M |
| 1.4 | Be found in scout discovery | 1 | DESIGNED_ONLY | Every discovery and save schema assumes a positive TrackedPlayer player_api_id. | Mint PlayerShadow during local approval, union eligible local shadows in _base_scout_query, then extend watchlist, follow, and client subject routing. | L |
| 1.5 | Be contacted safely | 3 (codex said 2) | LIVE_WEB_IOS | Prod CONTACT_RAIL_ENABLED=1 opens the 404 gate (contact.py:83-93). Player accept/decline is live on web (App.jsx:4215 route, :590 nav; IntroductionsPage.jsx:49) and iOS (IncomingContactRequestsView.swift:249); replies at ContactThread.jsx:82. Gap: only tracked-player self-claims are contactable (contact.py:419). | Encode CONTACT_RAIL_ENABLED=true in deployment configuration after smoke-checking the existing direct, notified, and club-included flows. | S |
| 1.6 | Know I am being watched | 3 (codex said 2) | LIVE_IOS | Flag is on in prod; iOS owner card (PlayerDetailView.swift:199) reads showcase.py:1805 for approved self-claims. Codex's 'labelled scouts' claim is wrong: labels are Watchlists/Follows (PlayerInterestSignalsViewModel.swift:13-15). No web surface, so LIVE_IOS, but usable. | Filter aggregates through approved ScoutVerification rows, then enable CONTACT_RAIL_ENABLED and reuse the existing iOS card. | S |
| 1.7 | Have fans | 2 (codex said 3) | LIVE_WEB | Fan surface exists only for API-Football TrackedPlayers: comments (PlayerPage.jsx:1426) and a scout-branded watchlist star (PlayerPage.jsx:319). LocalPlayerPage.jsx:1-11 mounts no comments, follow, or share; no fan concept in code; no public counts. The dream's self-showcased player cannot have fans. | Extend follow_resolver._validate_player and Follow.selector for local_player_id, then expose generic Follow controls on both player pages. | M |
| 1.8 | Player growth view | 3 | LIVE_WEB_IOS | Growth storage and routes remain keyed solely by player_api_id. | After PlayerMatchEntry exists, extend season-rollup subjects for LocalPlayer and expose approved Qwen evidence through _verified_footage. | L |

### P2 — Clubs: track, analyze growth, tools to improve — 61.1%

| # | Capability | Score | Reach | Blocker | Next step | Effort |
|---|---|---|---|---|---|---|
| 2.1 | Claim, verify my club, and reach the console | 3 (codex said 2) | LIVE_WEB | [S0 B LIVE #959] approving a club-official claim now grants the console (bridge → program + approved claim + active manager); console-first clubs can adopt into a public funding league on claim. Remaining: one admin approval step; adoption pauses the console until funding review; local console programs not yet adoptable. | Extract the grant logic from approve_program_claim() into a shared service; after verified social proof plus authority evidence, create the ClubProgramClaim and ClubProgramManager automatically, routing ambiguous claims to admin review. | M |
| 2.2 | Roster, local-profile adoption, tracked links, and match squads | 3 | LIVE_WEB | The creator-only check in add_club_roster_member() prevents clubs adopting profiles created by their own players. | Add program-scoped LocalPlayer roster invitations, resolve the profile owner through PlayerProfileClaim, require owner acceptance, then create the existing ClubRosterMember and expose local search. | M |
| 2.3 | Track games without video | 2 | LIVE_WEB | VideoMatch is the only manager-writable match aggregate, assumes footage, consumes Film Room quota, and lacks result or appearance-stat fields. | Add ClubMatch and ClubMatchAppearance keyed to ClubProgram and ClubRosterMember, with manager CRUD for scores, lineups, minutes, goals, and an optional VideoMatch link. | M |
| 2.4 | Track academy graduates and loanees | 3 | LIVE_WEB | MyClub's ClubRosterMember roster is not joined through ClubProgram.team_api_id to Team and TrackedPlayer. Provider-covered managers can use the public page, but community clubs cannot. | Add manager-gated GET /club/<program_id>/tracked-players using require_club_manager(), ClubProgram.team_api_id, TrackedPlayer, and rollup_stats_by_player(); render a MyClub Academy Pathway tab. | M |
| 2.5 | Analyze player growth over time and compare roster players | 3 (codex said 2) | LIVE_WEB_IOS | Prod SEASON_ROLLUP_READS lists every surface in feature_flags.py:5, so codex's only blocker is gone. JourneyTimeline.jsx:21-61 reads journey stops (PlayerPage.jsx:364), never the flag; compare on ScoutPage.jsx:324 and CompareView.swift:202. No MyClub view, locals excluded, backfill state unverified. | Backfill PlayerSeasonTotal with refresh_player(), verify /api/admin/season-rollup/status, then deploy SEASON_ROLLUP_READS=season_stats,player_stats,scout,teams. | S |
| 2.6 | Film Room upload, analysis, reports, and reels | 2 | ADMIN_ONLY | Each club upload stops at a request timestamp; only an admin can queue computer vision, review identities, run Qwen, and finalize. | Factor routes/video.py:process_match() job creation into a shared service called by request_club_match_processing(), then expose club-scoped identity binding and finalization through require_club_manager() and the existing PlayerReels UI. | M |
| 2.7 | Tools to improve players | 1 | LIVE_WEB | There is no player-addressable development record with permissioned delivery from manager to player. | Add append-only ClubRosterFeedback keyed to ClubRosterMember, manager CRUD in routes/club.py, recipient reads resolving player_api_id or local_player_id, then MyClub composer and player inbox views. | M |
| 2.8 | Tools to improve the club | 2 (codex said 3) | LIVE_WEB | Every 'club tool' is a public provider benchmark: cohorts are admin-seeded and synced (cohort.py:31-163, all /admin/), analytics filtered to seeded cohorts (:339); ProgramPage.jsx:150 says support is not live; is_fundable False (funding.py:208). A manager gets nothing for their own club. | Build a manager ClubProgram dashboard joining team_api_id to AcademyCohort and academy-network outcomes, add demand metrics, recurring Checkout and a payment ledger, then expose equivalent iOS views. | L |
| 2.9 | Club-to-scout consent loop | 3 | LIVE_WEB | A club manager cannot list or decide club-consent requests natively on iOS. | Extend iOS ContactRequestBox and APIClient with box=club plus the existing club-consent POST, add an Account-tab manager inbox, and pin the production flag in deployment configuration. | M |

### P3 — Scouts: find and analyze — 67.9%

| # | Capability | Score | Reach | Blocker | Next step | Effort |
|---|---|---|---|---|---|---|
| 3.1 | Scout account and verification | 3 | LIVE_WEB_IOS | Approval records neither D1 adult verification nor authoritative credential validation. | Extend ScoutVerification with adult_verified_at, credential_issuer, and credential_reference; enforce them inside _review_scout_verification. | M |
| 3.2 | Find players | 3 | LIVE_WEB_IOS | User-created players remain invisible throughout scout discovery. | Add local subject support to ScoutWatchlistEntry, Follow, and comparison, then union eligible LocalPlayer rows into _base_scout_query. | L |
| 3.3 | Analyze players | 3 | LIVE_WEB_IOS | Grounded video notes remain confined to club and admin consoles. | Project sanitized capture_meta.qwen_analysis from eligible finalized matches through _verified_footage, then render it in ShowcaseSection and iOS PlayerDetail. | M |
| 3.4 | Organize prospects and receive alerts | 3 | LIVE_WEB_IOS | Alerts are email-only; no push; no opted-in users yet. | Add a scheduled deployment job that pages send_scout_digests with dry_run=False until next_cursor is null. | S |
| 3.5 | Reach out | 3 (codex said 2) | LIVE_WEB_IOS | Prod flag is on. Web Send button + IntroduceDialog (ScoutPage.jsx:986-996, :1110; IntroduceDialog.jsx:33) and iOS (PlayerDetailView.swift:259) post contact.py:405. Reachable only from the ScoutPage table and only to approved self-claimed TrackedPlayers (one in prod). | Smoke-test each routing mode, then encode CONTACT_RAIL_ENABLED=true in the deployed Container App configuration. | S |
| 3.6 | Pay for Scout Pro | 1 | DESIGNED_ONLY | Scout Pro is marketing copy plus an unused tier column. | Add Stripe Checkout and webhook handling that updates UserAccount.scout_tier, then gate selected Pro features through one entitlement helper. | M |
| 3.7 | Club managers recruit as scouts | 3 | LIVE_WEB_IOS | Recruitment cannot prove which managed club the scout represents. | Add acting_club_program_id to ContactRequest, validate it through is_active_program_manager, and expose a managed-club selector before outreach. | M |

### P4 — Funding: Patreon/BMAC → club part-ownership — 21.4%

| # | Capability | Score | Reach | Blocker | Next step | Effort |
|---|---|---|---|---|---|---|
| 4.1 | Club funding registry / programs | 2 | LIVE_WEB | Claim form and public program page work, but there is no program directory, no manager edit route (the ClubProgramProfileRevision table exists unused), is_fundable is hard-coded False, and prod has 0 programs. | Add manager-gated ClubProgramProfileRevision creation through ClubProgramManager, safe-field publication, and a MyClubConsole editor. | M |
| 4.2 | Money movement | 1 | DESIGNED_ONLY | The donation payment, transfer, webhook, receipt, and refund state machine does not exist. | Extend ClubProgram and ClubConnectAccount with idempotent donation records, signed Checkout webhooks, destination transfers, receipts, tips, and refunds. | L |
| 4.3 | Recurring support | 0 | MISSING | There is no recurring-support domain model or subscription lifecycle. | Define ClubProgram-keyed tiers, subscriptions, supporter visibility, and ProgramUpdate rows before wiring recurring Checkout. | L |
| 4.4 | External platform connection | 0 | MISSING | No external funding identity or URL is associated with ClubProgram. | Add moderated provider and external_support_url fields to ClubProgramProfileRevision and render a labeled ProgramPage link-out. | M |
| 4.5 | Part-ownership / investment mechanic | 0 | MISSING | No counsel-approved securities structure or regulatory posture exists. | Complete jurisdiction-specific securities scoping before defining any ClubProgram-linked stake, governance, or investment mechanism. | L |
| 4.6 | Supporter/fan-facing club page | 2 | LIVE_WEB | Public program page + 'Save this program' work, but it is reachable only by exact slug (the only in-app link is in the admin UI) and shows 'Support is not live yet'. | Add moderated ClubProgram updates and impact entries through ClubProgramManager and render them on ProgramPage. | M |
| 4.7 | Grassroots attested manual-data path | 1 | DESIGNED_ONLY | The provenance-aware per-player match-entry grain does not exist. | Implement ClubFixture and PlayerMatchEntry through ClubRosterMember manager routes, then invoke season_rollup_service.refresh_player. | M |

### P5 — Foundation: safety, correctness, reach, ops, money, adoption — 53.1%

| # | Capability | Score | Reach | Blocker | Next step | Effort |
|---|---|---|---|---|---|---|
| 5.1 | Minor safety | 2 | LIVE_WEB_IOS | Adult gate covers self-claims only; guardian/agent/club-official claims and local-player creation skip it; Film Room upload-complete has no rights/age/consent attestation (club.py:398-434); web has no delete, takedown, or report component although the Terms promise website deletion (LegalPages.jsx:23) — only iOS has them. | Extract a subject-eligibility guard from _adult_player_claim_error, enforce it across claims/contact/media, and require versioned VideoMatch attestation plus quarantine scanning. | L |
| 5.2 | Data correctness and dispute | 3 | LIVE_WEB | The public dispute queue and authoritative correction mechanisms remain disconnected manual workflows. | Link PlayerFlag resolution to apply_manual_transfer or admin_update_tracked_player, persist the correction event, notify reporters, and expose flags/submit on iOS. | M |
| 5.3 | Reach | 2 | LIVE_WEB | Player and club pages are SPA-generic (homepage-only OG tags, no sitemap), no push (no APNs code), digests have no scheduler; emails do fire for login, claim/scout decisions and club consent. | Add sitemap and player/program metadata endpoints backed by TrackedPlayer and ClubProgram, then generate OG cards for those URLs. | M |
| 5.4 | Ops and scale | 2 | ADMIN_ONLY | No managed worker deployment, KEDA or alerts anywhere; deploy.yml:224 leaves job-video-maintenance out of image updates so the retention sweeper runs a frozen build; every club processing request still needs an admin. | Deploy vision_worker.main through ACA Service Bus/KEDA, persist chunk checkpoints, schedule maintenance, and alert on queued, stale, and failed VideoAnalysisJob rows. | L |
| 5.5 | Revenue rails | 2 | ADMIN_ONLY | Credit ledger + admin grant/debit/refund serve concierge sales only (require_api_key); no Checkout or webhook; pricing CTA disabled (PricingPage.jsx:94); writer subscribe UI targets /stripe routes that do not exist. | Create Checkout and signed webhook routes that append VideoCreditLedger purchase rows, then enable the Film Room pricing CTA. | M |
| 5.6 | Adoption instrumentation | 3 | ADMIN_ONLY | Six web events are wired (pageview, claim_submitted, search_performed, list_created, follow added/removed) and shown on AdminDashboard; prod is pageview-only because nobody has acted yet; iOS emits nothing. | Extend analytics_summary with counts from UserAccount, PlayerProfileClaim, ClubProgram, ScoutVerification, and ContactRequest, then surface them in AdminDashboard. | M |
| 5.7 | Legal and paper | 2 | LIVE_WEB_IOS | Phase-0 counsel artefacts are incomplete and not mechanically bound to uploads or funding. | Version legal acceptance, require VideoMatch attestation fields, obtain redistribution and donation opinions, and update Privacy to the actual data inventory. | L |
| 5.8 | Real adoption (people actually using it) | 1 | LIVE_WEB_IOS | Nobody outside the team has claimed a profile, claimed a club, watchlisted, introduced, uploaded, or paid; the content engine (newsletters) has been idle since April. | Pick ONE beachhead cohort (e.g. the Forest academy contact or one grassroots club) and drive 10 real participants through claim → console → intro by hand; instrument the funnel first (5.6). | M |

## Blockers, ranked by how much of the dream they hold back

1. **Self-made players are invisible.** Discovery, leaderboards, watchlists, follows and the contact rail all key on API-Football TrackedPlayer rows (scout.py:465, contact.py:419). A player who creates their own profile cannot be found, watched, or contacted. This is the dream's core subject. _(caps 1.4, 1.3, 1.7, 3.2)_
2. **Clubs cannot get in by themselves.** The visible club-claim button feeds a legacy claim that never grants the console (showcase.py:3109); the grant path needs an admin API key (funding.py:749) and is linked only from an approved program page. Prod has 0 clubs. _(caps 2.1, 2.6, 4.1)_
3. **No games or stats can be entered by people.** Season cells only accept provider sources (season_rollup.py:44); club matches store no result, minutes or goals (club.py:342). Growth analysis for anyone outside API-Football coverage is impossible. _(caps 1.3, 2.3, 2.5, 4.7)_
4. **Film Room is concierge.** A club's 'process' click only stamps a timestamp (club.py:601); an admin must queue CV, bind identities, run Qwen and finalize each upload, under a 3-lifetime-match quota (club.py:35). The worker has no managed deployment or alerts, and the nightly retention job is excluded from image updates (deploy.yml:224) so it runs a frozen build. _(caps 2.6, 5.4)_
5. **The front door is broken and unsafe.** Web tracked self-claims 400 because api.js:1403 omits the required contract_status (showcase.py:479); local self-claims accept minors (showcase.py:1371–1376, test_local_players.py:314) against decision D1; Film Room uploads carry no age/consent attestation; the web app has no delete, takedown or report control although the Terms promise one (only iOS has them). _(caps 1.1, 5.1, 5.7)_
6. **There is no money path.** No Stripe checkout, webhook, or /stripe route exists in the backend; the journalist subscribe box calls dead routes (SubscribeToJournalist.jsx:26). Scout Pro is copy plus an unused column. Donations are a registry without payment. Nothing about Patreon, BuyMeACoffee, or equity exists in code. _(caps 3.6, 4.2–4.5, 5.5)_
7. **Nobody is using it and nothing pulls them in.** 9 accounts (5 are the team), 1 claim, 0 clubs, 0 intros, 0 revenue. Newsletters stopped 2026-04-21. No sitemap or per-player share tags (SPA shell at every route), digests need an admin POST per send. _(caps 5.8, 5.3, 3.4)_
8. **'Fans' do not exist as a concept.** Only comments and a scout-branded watchlist star on tracked-player pages; local player pages have neither; no public follow, counts, or share card. _(caps 1.7)_

## Steps to 100% — projected score after each stage (computed from the target scores, same weights)

| Stage | Name | When | What | Overall after |
|---|---|---|---|---|
| — | Today | — | — | **54.1%** |
| S0 | Unbreak the front door | days | Fix the web claim payload (send contract_status), add the age gate to local self-claims, bridge club claim → console grant without an admin API key, put the digest sender on the nightly job, fix the dead journalist /stripe box. | **54.1%** |
| S1 | One player universe + a games grain | weeks | Let local players into discovery/watchlists/contact/follows (shared subject id), and add a user-entered match row (player or club, provenance-labelled) that feeds the existing season cells. Show it in MyClub as a growth view. | **59.0%** |
| S2 | Fans and reach | weeks | Public follow for any account, fan counts on player pages, shareable player card with per-player og tags and a sitemap, trust-tiered auto-approval so edits stop hiding profiles, email notifications on the events that already exist. | **61.0%** |
| S3 | Money rails | weeks | Stripe Checkout for Scout Pro at the committed price; club bundle subscription; donation checkout with donor-tip model once regulatory scoping is done; club-editable programs; Patreon/BuyMeACoffee link-out plus supporter import as the cheap first bridge. | **66.1%** |
| S4 | Film Room self-serve + club tools | weeks–months | Club-triggered processing with a monthly allowance instead of 3-lifetime, worker checkpointing and scheduling, coaching notes and shareable player reports, a manager-scoped club dashboard on the pathway data that already exists. | **69.4%** |
| S5 | Part-ownership | paper first | Counsel decides the vehicle (crowd-equity is securities-regulated; a supporter-membership with governance perks may be the honest v1). Then recurring support tiers and the ownership ledger. | **72.1%** |
| S6 | Ten real participants | ongoing | The multiplier on everything above: pick one cohort (the Forest academy contact or one grassroots club), walk 10 real people through claim → console → intro by hand, instrument the funnel first. | **73.0%** |

After S6 every remaining point is polish to 4s: iOS parity, E2E on the core journeys, tests, the U18 expansion (ROADMAP Phase 5). Reaching 100% means all 32 rows at 4 — that is the finished dream, not a launch bar. A credible launch bar is **S0–S2 done (~61.0%) plus S6 started**.

## What is already strong (do not rebuild)

- academy-watch-backend/src/routes/showcase.py:1085 — Keep persisted-DOB claim eligibility resolution.
- academy-watch-backend/src/models/showcase.py:457 — Keep exclusive tracked-or-local showcase ownership constraints.
- academy-watch-backend/src/routes/scout.py:383 — Keep suppression-aware TrackedPlayer discovery and extend it.
- academy-watch-backend/src/routes/scout.py:625 — Keep the broad phase and per-90 sorting.
- academy-watch-backend/src/services/trust.py:14 — Keep live derivation of revocable scout verification.
- academy-watch-backend/src/services/contact.py:173 — Keep conservative contract-aware contact routing.
- academy-watch-backend/src/routes/contact.py:1070 — Keep participant authorization, blocking, and message gates.
- academy-watch-backend/src/services/scout_digest_service.py:472 — Keep cursor-paged digest generation and sending.
- academy-watch-backend/src/services/video_analysis_store.py:10 — Keep fenced atomic Qwen analysis persistence.
- academy-watch-ios/AcademyWatch/Features/Compare/CompareView.swift:202 — Keep the deep native comparison surface.

## Corrections to the 2026-08-23 platform review

- Prior C1 is now WRONG: academy-watch-frontend/src/pages/ScoutPage.jsx:986 and academy-watch-ios/AcademyWatch/Features/PlayerDetail/PlayerDetailView.swift:259 now initiate contact.
- Prior C2 is now WRONG on web: academy-watch-frontend/src/components/contact/ClubIntroductionsPanel.jsx:53 executes club consent from My Club.
- Prior B2 is now WRONG: academy-watch-backend/src/routes/club.py:366 persists club match history, consumed at academy-watch-frontend/src/pages/MyClubConsole.jsx:1198.
- Prior B3 is now WRONG: academy-watch-frontend/src/pages/MyClubConsole.jsx:633 loads private media and mounts PlayerReels.
- Prior C5 is now WRONG: academy-watch-backend/src/models/scout_watchlist.py:26 has the leading watchlist player index.
- The prior empty-box-track claim is now WRONG: origin/main:academy-watch-backend/src/models/video.py:91 persists boxes and origin/main:academy-watch-backend/src/services/video_boxes.py:129 reloads them; crop remains a 501 stub.
- The prior web tracked-claim lifecycle claim is now WRONG: academy-watch-backend/src/routes/showcase.py:479 requires contract_status, while academy-watch-frontend/src/lib/api.js:1403 omits it.
- Grounded Qwen3-VL notes shipped at academy-watch-frontend/src/components/video/PlayerReel.jsx:608, but PlayerPage and ShowcaseSection still expose none to scouts.
- D1 is incompletely enforced: academy-watch-backend/tests/test_local_players.py:314 demonstrates an underage local self-claim is accepted.
- Audit basis: the checked-out main branch is 16 commits behind local origin/main; code evidence uses origin/main, which contains PRs #936-#938.
- Prior audit line 56 is WRONG: legacy social-proof approval only changes ClubOfficialClaim at showcase.py:3109-3148; only funding.py:749-834 creates ClubProgramManager.
- Prior B2 is now WRONG: club.py:366-380 and MyClubConsole.jsx:1060-1093 provide server-backed cross-device match history.
- Prior B1 remains correct for results and player statistics; VideoMatch only adds metadata and shirt-number squads at club.py:321-592.
- Prior B5 remains correct: club.py:267-285 and test_club_console.py:333-348 enforce creator-only local adoption.
- Prior B3 is now partly WRONG: MyClubConsole.jsx:633-705 plays processed reels, although raw uploaded-match playback remains missing.
- Prior B4 and B6 remain correct: club.py:331-338 keeps a three-lifetime quota and api.js:3122-3157 remains sequential and non-resumable.
- Prior retention claim is now WRONG in code: video_retention.py:83-149 deletes blobs and marks expiry; production scheduling remains unproven.
- Prior report description is incomplete: qwen_match_analysis.py:1875-1907 adds tracking-grounded qualitative notes, while video_report.py:13-16 remains visibility-only numerically.
- Prior C1 and C2 are now WRONG for web: ClubIntroductionsPanel.jsx:24-115 and ClubConsentPage.jsx:17-168 perform consent decisions; native iOS still cannot.
- The contact rail is default-off in contact.py:83-94, but CONTINUITY_platform-review-qwen.md:131 records a successful production smoke with it enabled.
- Prior audit C1/C2 is now WRONG: components/contact/IntroduceDialog.jsx:11, MyClubConsole.jsx:1289, and routes/contact.py:914 provide scout initiation and club consent; CONTACT_RAIL_ENABLED still defaults off.
- Prior audit B2 is now WRONG: academy-watch-backend/src/routes/club.py:366 and MyClubConsole.jsx:1193 replace browser-local match history with a server list.
- Prior audit retention claims are now WRONG in code: video_retention.py:114-149 and run_video_maintenance.py:21-36 enforce expiry; deploy.yml:222-234 still does not prove scheduling.
- Prior audit production-artifact claim is partly WRONG: vision_worker.py:279-300 and video_boxes.py:129-146 persist and read box tracks; video.py:878-889 still returns 501 for crops.
- Prior audit's 'minor gates everywhere' claim is WRONG: showcase.py:1639-1675 gates only self-claims, and club.py:398-434 accepts footage without age or consent attestation.
- Prior audit's 'suppression applied consistently across every surface' claim is WRONG: routes/api.py:1184-1189 serves stored newsletter content unchanged, and ScoutResponseCache.swift:74-90 ignores cache age.
- Prior audit's zero club-manager E2E claim is narrowly stale because club-reels.spec.mjs:246 now exists, but every requested core write journey remains uncovered.

## Status

- 2026-09-02: scorecard created (baseline **51.9%**).
- 2026-09-02 (later): **S0 executed and live** — PRs #957 (A), #958 (C), #960 (D), #961 (E hygiene), #959 (B); ACA job `job-scout-digest` created; prod `local_players.birth_date` pre-applied + stamped lp01. Re-scored rows 1.1, 2.1, 3.4 → 3 (see `ledgers/CONTINUITY_dream-s0.md`). Next: S1 (one player universe + games grain) — decisions in `ledgers/DIRECTIVE_phase1-user-fed-data.md` §4.
