# Phase 2 C2 — two-key highlights

## Goal / constraints
- Club picks a server reel window; independent adult self-claimant approves; standalone private clip output; revoke on next request.
- Branch p2/c2-highlights from origin/p2/b3-admin; PR against main stacked on #1115, ready at end; no merge/deploy.
- HIGHLIGHTS_ENABLED default OFF; p2c2 -> real p2c1 ancestor copied verbatim; no placeholder.
- Reuse A1 adult/holds/outbox/audit, A2 capability+byte scope, B1 is_listed. No public minors, youth/mixed footage, raw match SAS or metadata.
- C2F2 owns foreground Vite5204 and scratch aw_c2f2/aw_c2f2_upgrade/aw_c2f2_preapply/aw_c2f2_reverse; clean own resources. Historical C2F1 resources were already cleaned.

## State
- C2F2 implementation complete; exact final gate/delivery outcome is recorded in external logs/C2F2.final.md and durable C2F2.report.md: review-duel union; O1 first-use autoflush first. Lead rulings: unknown senior attestation verified-manager-only, sticky admin takedown, source revocation notified/recoverable. No 14-day expiry; unanswered follows raw deadline, declined ready assets deleted immediately.
- Complete (fix round 1): all RC2 F1–F16 FIXED; final application d2c9750f verified; delivery/cleanup below.
- Fix gates: final focused102 pass1 optional C1 skip; PG57 pass; query/failure-download4 pass (SQL10/11/12/14 at1/25/100 clips); exact real-app98 dark-method/path pairs/zeroSQL; modern browser242 pass4skip. OSV547/Node219/lint0errors192warnings/build pass; Ruff598 clean.
- Full gate: final flags-OFF4343 pass94skip0fail149warnings (1054.65s), DB_SSLMODE=disable corrected local SSL-only fixture errors. Unfiltered browser240pass20fail5skip16serial-not-run:18 historical legacy/live-fixture failures +2 C4 fixed1s initialization races under parallel load; same C4 file4/4 pass with normal worker setting (and included in modern242-pass suite).
- Fix migration: p2c1 copied verbatim c11e36f; p2c2 6a641362 (C4 copied); whole public schema upgrade == preapply twice (38ffed21), RLS4/guards7; empty downgrade/re-upgrade pass.
- Integration: latest main/B2 784b1490/55b1d3ac and B3 46a4274f included; C2 application/test bytes preserved by release refresh.
- Fix policy: raw-independent revoke; 60s single-clip redirects; verified club key; preview-ready approvals; institutional staff keys survive erasure; unanswered follows raw deadline; declined immediate with fenced live-attempt cleanup (C2F2 final user/BUS ruling).
- Complete: private tables, source fences, capability routes, independent consent, standalone worker+private bytes, outbox, erasure/export and dark web mounts.
- Complete: dependency cut B1811fabca/B216540e03/B3d49ec794/N3adea5177; main B1 squash e82bb4e3 refreshed with byte-identical application/test tree.
- Complete: recording-date DOB checks prevent childhood/unknown/future footage; independent clips survive raw expiry; UTC SQL/ORM guards fence source/date/identity changes and delayed cleanup.
- Complete: UUID leases, concurrent pick/decision/job fencing, late-upload cleanup; public reads recheck both keys/current canonical adult eligibility/holds/suppression/source.
- Gates: final full pytest4285 pass91skip0fail; focused46 + PG5 (combined51 pass1 optional C1-code skip); current C1 canonical overlay integration1 pass.
- Gates: current offline Playwright238 pass4skip incl13 C2 tests; Node219; Ruff check/format594 clean; lint0errors192warnings; Vite build pass; OSV547 clean, unchanged lockfiles.
- Gates: real chain p2c1/p2c2 upgraded; guarded upgrades/preapply twice, RLS4/source guards6, retained downgrade refused, empty rollback/upgraded; real ffmpeg1.001s/video-only/1280px.
- Evidence: fix round19 refreshed/reviewed desktop/mobile synthetic-fixture PNGs in ~/codex-runs/aw-redesign/shots/C2; full logs under C2F1.*.
- Limit: broad legacy browser suite still fails obsolete frozen routes and live email/admin fixtures; current offline suite is green. No provider sends or production data changes.
- Rollout: apply real C1 then C2 schema before deployment; build/schedule independent ffmpeg worker and existing outbox before enabling. Native views are I1, sharing these APIs.
- Delivery: final C2F1 per-finding hand-back/logs and19 shots outside repo; PR1122 remains open/unmerged. Latest main/B2/B3 included; C1 c11e36f verified unchanged at C1 final hand-back.
- Cleanup: own Vite5202 stopped; own aw_c2f1/aw_c2f1_pre and generated/temp outputs removed before delivery. Existing dependencies retained; no provider sends/deploy/merge. Independent dual review is orchestrator next step.

## C2F2 evidence
- All duel-union findings plus lead rulings FIXED. First unseeded recording review populated before session add; both classifications SQLite/PG pass. Robust normalized youth labels/upper-age unknown guards; senior attestation audited/withdrawable and verified-owner/manager-only.
- Unanswered follows raw90-day expiry; completed declined output immediately worker-deleted; live/late attempts separately fenced. Live consent history retained; permanently broken claim/recipient keys revoked/cleaned, reversible holds preserve consent.
- Three grants batch both initial/fresh final evidence; absolute deadline set before storage, then fresh consent/source/standing/actor checks. Cold1/21-person rosters equal SQL <=32. Concurrent PostgreSQL grant/revoke passes.
- Preview authenticated JSON URL -> native video src; real three-origin no-CORS MP4/range test passes without bearer/referrer/Origin:null at storage. Effective real-app no-referrer. Shared features/positive schema discovery cache; dark guards retained and request cache reset.
- Minimal recording/window takedown hold survives clip audit/subject erasure; existing duplicate windows revoked. Dual-auth admin lift by archived ID restores no old consent. Source edits still fail-closed, neutral player/club outbox, fresh pick+approval allowed. Cancelled cuts stale/retryable; staff public wording corrected.
- Reversed reviewed a1c5584c final69 regressions:66fail/3controls; current69pass. PG166 final +10 added distinct =176 unique pass/0skip; overlapping race/SQL11 pass. Focused162 incl real C1; actual dark7 pass/105 method-path comparisons/zeroSQL, including lift.
- Pre-refresh modern Playwright269pass/5 existing opt-in skips/0fail; relevant32pass/3opt-in skips incl15 C2. OSV547 clean; Node221/lint0errors193 inherited warnings/build/Ruff-format611 pass; JS repo has no separate TypeScript gate.
- Pre-refresh full flags-OFF4574pass117skip0fail153warnings881.07s; application source freeze c2521e6b includes B3F5. Later changes only dark-lift test (targeted7pass) and docs/ledgers; Ruff/format rerun green.
- FINAL p2c2 migration58af1d880ef55e7dccd1182ec5f827c3d5a9c9bd1aa8537ab0467d635a58acfc; preapply751d8879e46f941952d760c1373eadf5ddf57f41e7dc03f77fb0f2fa50572a37 repo/external equal. CONTRACT posted for C4 verbatim copy; supersedes early7a523 contract.
- Whole public schema upgrade==preapply twice + guarded upgrade; normalized4b560bf86c929de7aef991b967b916a21ec7d3213a8db629dfb56e158ef997fd/RLS5/source guards7; empty downgrade/re-upgrade pass. C1 7ff6c7d2 and B3 f073ecc8 copied verbatim.
- Pre-refresh main784b1490/C1d9105c37/B3F551f30f5b merged before gates; final re-fetch confirms all ancestors included. BUS re-read: no C2 ruling override.
-23 refreshed synthetic-fixture desktop/mobile PNGs shots/C2F2 with INDEX/SHA256SUMS; affected mobile inbox/club-approved/admin-lift/three-origin captures inspected, mobile overflow checks green.
- Own Vite5204 stopped; four owned scratch DBs/temp/browser/build/cache outputs cleaned. Final per-finding evidence/contract/gates/screenshots in external logs/C2F2.final.md and durable C2F2.report.md; exact pushed local/remote/PR SHA and BUS DONE recorded there. PR1122 remains open/unmerged; no deploy/provider sends/flag activation.

## Acceptance / checks
- Both keys required; revoke removes lists+bytes immediately; minors/unknown ages/private matches blocked.
- Source/identity/window changes invalidate consent; concurrent job completion fenced.
- Candidate preview only standalone clip; 60s read-only single-blob redirect, expected ETag, no raw/container grant; documented expiry plus in-flight-transfer bound.
- Every new table guarded DDL + RLS; export/erasure remains effective when flag OFF.
- Full Ruff/format/backend/Node/lint/build and current Playwright completed before push.

## Final C1F2 refresh
- C1 aafb11d5 published during first delivery verification; first64855e1f push is interim, no BUS DONE/final hand-back. Final full gates repeated on merged current lower head.
- API conflict adopts C1 shared15s feature cache, preserving C2 native preview URL API; cache failure/TTL behavior covered by inherited C1 Node regressions, C2 bootstrap test keeps concurrent dedup assertions. All C2 server/migration/worker code unchanged.
- CONTINUITY retains both current C1 evidence and C2 history. C1/B3 migration contracts unchanged.
- Final source frozen3bbdea20 after raw-expiry worker deletion assertion: completed unanswered outputs delete immediately at raw expiry; only live attempt paths retain late-upload fence. Targeted PG1 pass; first integrated176 pass. Frozen PG176 passed; full run stopped at65% by MJ fleet pause, final governed gate required; intermediate full run intentionally interrupted1659pass/56skip/0fail after change.
- Final C1-integrated browser277pass/5existing skips/0fail, all15 C2 cases; Node223/lint0err193warnings/build/Ruff-format612/OSV547 pass; no dependency restore.23 shots refreshed/indexed; Vite5204 stopped.
- Actual parent p2b2→p2b3→p2c1 upgraded before cloning schema gate; final upgrade==preapply twice + guarded upgrade, normalizedd6726bb718c5ed8efc77e90aa4390f6580215c007b66a710df765ae82b2a07f9/RLS5/guards7, empty rollback pass. Supersedes earlier4b560bf8 evidence baseline; migration58af1d88 unchanged/CONTRACT reconfirmed.

## C2F2R governed resume (2026-10-02)
- Saved source3bbdea20 and one ledger WIP preserved; same fix round, no restart. Read BUS from MJ-PAUSE through renewal22:51 final rulings; existing implementation matches all three confirmed policies and final retention.
- Current main784b1490/B351f30f5b/C1aafb11d5 fetched/included; latest migration files copied verbatim. Source/migration/frontend/test files unchanged on resume.
- Before pause: frozen PostgreSQL176pass0skip698.14s; final modern browser277pass5opt-in skips0fail11.3m; Node223/lint0err193warnings/build/Ruff-format612/OSV547 pass. Final full backend at65% was intentionally stopped by MJ, so no pass claimed.
- Commit final ledgers before governed cached gates so pushed-head results remain reusable. Four exact-head gate outcomes/cache keys/log paths and final pushed SHA are authoritative in external logs/C2F2.final.md/C2F2.report.md. No further source changes are planned.
- Final schema equality from actual upgraded B3/C1 parent: d6726bb7/RLS5/guards7/empty rollback pass; C2 migration58af1d88 and preapply751d8879 unchanged, C4 verbatim copy checked.23 final refreshed/inspected screenshots retained.
- Resume owns only remaining aw_c2f2 scratch; no dev server is running. Drop it and remove owned temp/generated artifacts after the remaining governed gate. No merge/deploy/provider/flag actions.
- Resume targeted governed first-review classifications + completed unanswered raw-expiry deletion:3pass66deselected (resume-targeted.log). No source changes. Final cached full/style/unit/build gates run after this ledger commit; exact results and pushed SHA are recorded in the external delivery ledger/hand-back.

## C2F3 — RC2V2 union (2026-10-02)
- State: in-progress at38512c3d; all four reports read.
- Scope: X1 bridge retention; X2/O2 overlap holds; O1 youth normalization; O3 finalized/context-bound review; O4 unique pinned owner; O5 narrow tracklets; O6 grouped neutral source notices; X3/O7 flags/media retry.
- Next: reverse probes, targeted tests, main/B3/C1F3 integration and verbatim migrations, final four gov gates/PG/Playwright/schema equality, screenshots, push + hand-back.
- Serious reverse probes:4fail on38512c3d; first green4 pending broader verification (raw-expired harness now obtains the newly required context review).
- New backend regression selection78pass3PG-onlyskip; broadened run117pass plus missing imported fixture (Ruff removed unused pytest fixture import) and1 old squad-context expectation; both harness issues corrected.
- Implementation: shared claim subject resolution; active interval holds with batched reads; NFKC/youth/ambiguous digits; finalized context review with fail-closed context invalidation; unique pinned self-owner; referenced tracklets; grouped player+manager notices excluding declined; shared feature cache and native media retry.
- New source_context column, squad context SQL guard and notification SQL changed; final preapply/upgrade equality and CONTRACT pending.
- Final gates delayed until code committed/integrated. Governor waiting at high shared load is normal; no retry/bypass.
- Integrated origin/main784b1490 + B3F551f30f5b + C1F328cb333e; ancestor migrations re-copied verbatim (B3f073ecc8/C1 172d6c0a).
- Reverse full backend probes:73fail5controls3PG-onlyskip on38512c3d; hook reverse2fail1control, current3pass. Real PostgreSQL new82pass44.61s + existing lane176pass255.17s. Final source additionally pins review context in clip fingerprint and adds raw SQL/admin-route regressions.
- NEW p2c2 CONTRACT posted: migration3504f91e0e0fdaa0185a92b0e5c0a9f716aa8baef8513a69ae4bf1e9691ba410; SQL9462f0687b29c5608366bc04d542edbf11478b806429c14da24acf5f408cf64f; guard16285d11fafc3c2592bcf4e35a738ef053a638b12cc17099122012f87990ddd4.
- Actual parent whole schema directupgrade==preapply twice+upgrade233e4a58;RLS5/source7+delete1; both DDL paths5s lock bound. Legacy reviews without context require fresh verified review; no consent transfer/backfill.
- Next: final commit, four cached gov gates, full final C2 PostgreSQL selection and one lane browser run with refreshed shots; push/hand-back/cleanup.
- Candidate c317de4b: C2 PostgreSQL263pass146.00s; frontend-unit226pass, backend Ruff-format615, frontend lint0err193 inherited warnings/build pass, OSV547 no issues. Browser one full run17pass1TTL-harness failure; two media-retry and real feature recovery cases pass. Fake clock installed after shared cache captured original Date.now; corrected to install before page/module load; targeted TTL/recovery1pass3.2s.
- Refreshed25 screenshot PNGs shots/C2F3, INDEX/SHA256SUMS; new390px retry and clubreview visually inspected, no overflow. Native three-origin playback remains green.
- Implementation and regression source complete; final head re-verification/push outcome recorded in external logs/C2F3.final.md and C2F3.gate-manifest.json. Repository ledger intentionally precedes exact-head gates; no further source edits planned.
- Final fetch moved main784b1490→33bf30bd (B3 squash #1115); mechanical12-conflict integration preserved already-stacked B3/C1/C2 code, p2c2 head pins and both ledgers. Duplicate B3 imports/export/features avoided; existing dark Allow-order fix retained. B3/C1 migration hashes unchanged. Final gate suite on prior candidate was in flight at fetch and is not final verification; final merged head is re-gated.

## C2F4 — RC2V3 union (2026-10-02)
- State: in-progress; all four reviews read; O3 Serious, O1/O2/X1 Medium, X2/O4/O5/O6 Small accepted. O7 lead conservative year attestation control.
- Main ee16572f integration; preserve UXM1 and C1 gates. No delegation or dependency restore.
- Next: reverse regressions, safe classification-context guards including SQL, final current lower-head integration, CONTRACT/schema equality, final cached gates/PG/Playwright/screenshots, push/hand-back/cleanup.
- O3 first PostgreSQL19pass: cosmetic ORM/real invited-route/SQL edits ON/OFF/live/raw-expired preserve clips+assets; unsafe youth/unknown rename+revert permanently invalidates. Checked legacy context bridge preserves fingerprint only for exact valid prior contexts; Unicode controls pass.
- Reversed reviewed behavior42fail4PG-onlyskip; first greenSQLite61pass1harness-fail7PG-onlyskip. Combined PG154pass3old-harness-fail; fixtures now review changed roster context and use an unknown non-youth label. Targeted rerun governed queue is normal.
- Implementation complete: classifier allow-list/stems, every member squad context, suspension-independent ambiguity + indexed GET evidence, public club admission, held picker/refusal, visibility recovery. New p2c2 classification_context and static helper guards require CONTRACT/schema equality.
- Integrated current lower C1F4 c7cf6c11 (local/announced final candidate) before final gates;10 mechanical conflicts preserve C1 latest serializers/erasure/search and C2 highlights/exports/dark Allow ordering/head pins. Main ee16572f current; B3 ancestor; prerequisite migration bytes unchanged.
- Source complete on42f37f8d after main/C1F4 merge corrections; O3 PG19pass, combined regression PG154pass plus corrected targeted10pass. Checked legacy Unicode controls passed.
- FINAL p2c2 CONTRACT migration2600cef5a4a45e0bcc344b699092103ecbc0cd2a00a9a17deec0de125471ab23/preapply0d79f07c39e32d1ff5674d669d504d17936847678cefee09cac57ef1b260f51e/guardsafe16025addafbf04c01337e81128d03a99230e79fe7d6e3a4455b7e948a79ec; repo/redesign preapply equal; BUS posted for C4/staging. Whole schema upgrade==preapply twice+upgrade3f5b22a2/RLS5/source7+delete1.
- All RC2V3 union groups implemented with regressions; final exact-head gates, C2 PG selection, lane browser/screenshots and pushed SHA/cleanup are authoritative in external logs/C2F4.final.md + C2F4.gate-manifest.json. Repository ledger precedes these checks so gate caches are reusable. No merge/deploy/flag activation.
- Candidate a259a1fc gates: backend4848pass162skip2old-fixturefail (provider re-key/member squad removal), PG331pass2samefail; all runtime/new regressions pass. Corrected inherited duel fixtures assert refusal then explicitly obtain fresh verified review/senior attestation; targeted PG2pass. No runtime/schema/frontend changes.
- Candidate lint623/Node285/frontend lint0err193warnings/build PASS; browser21pass26.2s/29 refreshed inspected shots. Initial browser setup-only timeout from pnpm double-dash forwarding corrected; no tests ran in that attempt. Final exact-head four gates/PG/browser repeated after the justified fixture commit; final receipts external.

## C2F5 — RC2V4 union (2026-10-02)
- State: in-progress at19705a36; all four reviews read.
- O1 Medium: live source context required for review no-op; route-created change/revert/re-confirm regression for ORM/SQL. Shared review fixture gets both context fields.
- X1 Small: queued polling must recover after failed load with bounded backoff, visibility/unmount cancellation.
- O2 lead ruling: retain fail-closed structural squad kind/age-limit withdrawal; clarify staff copy. Migration/preapply/guard hashes unchanged.
- Next: reverse probes, fix, merge current main/lower lanes, final governed gates/PG/lane Playwright/screenshots, push + external C2F5.final.md.
- Reverse evidence on19705a36: real-route O1 PostgreSQL14fail/2cosmetic-controls-pass; failed-poll browser2fail at1440/390px.
- Fixed O1 live marker + complete shared review fixture: PostgreSQL20pass (14renewal variants,2cosmetic idempotency controls,4structural raw-expired ON/OFF route/SQL controls); inherited review/unsafe/legacy selection12pass.
- X1 implementation re-arms on load completion with30/60/120/240/300s delay, active/visibility guards; removes double backoff on failure. Staff copy explains structural withdrawals and fresh review/pick/approval with retained raw. Targeted ESLint0errors/2existing effect warnings.
- Current origin/main ee16572f and C1 c7cf6c11 merges already up to date; B3 ancestor. Migration2600cef5/preapply0d79f07c/guardsafe16025 unchanged; no schema/preapply rerun or new CONTRACT needed.
- Source complete; exact final four cached gates, C2 PostgreSQL selection, one full lane browser run/refreshed screenshots, pushed SHA and cleanup are authoritative in external logs/C2F5.final.md + manifests. Ledger precedes final-head checks to preserve reusable gate caches; no merge/deploy/flag activation.
- Candidate62e5738d four cached gatesPASS: backend4860pass172skip0fail521.51s/Ruff624/Node285/frontend lint0err193warnings/build; C2 PostgreSQL353pass189.44s. Browser25pass1inherited-preview-fixture-fail: unmocked fake storage DNS triggers real onError before transport assertion. Fixture now serves existing local MP4 and asserts no storage bearer; targeted1pass2.0s. Runtime/migrations unchanged. Final exact-head gates/PG/browser repeat after this justified test-only commit; candidate receipts retained externally.

## C2F6 — dark retention safety (implementation complete)
- Read both loanarmy-ca 16:35 BUS ASK lines (items 1–4); resumed same round after provider capacity interruption.
- Separate `HIGHLIGHT_RETENTION_SWEEP_ENABLED` defaults OFF; sweeper returns zero without SQL/mutations. Worker excludes delete claims and guards both leased delete and immediate cut-cleanup storage paths. Feature flag retains cut gating.
- Explicit `--dry-run`/`sweep_highlights(dry_run=True)` logs proposed row revocations/deletes and exact cleanup paths; no leases, writes, locks, storage or ffmpeg. Default OFF logs a disabled/dry-run no-op.
- Exact recorded highlight attempt paths required before storage deletion; raw-match aliases, prefix and match-derived paths refused. Enabled policy/age windows and public API unchanged.
- PostgreSQL safety27pass14.27s:3raw matches120days old (overdue finalized, expired, abandoned),1roster/tracklet/report,0rows in all5highlight tables. All4feature/sweep combinations select/delete0; storage0; raw rows unchanged. Raw retention control has2due matches; highlight paths never call it. SQLite retention/cleanup regression54pass2PG-onlyskip312deselected.
- Added generated owned-path subset properties (8seeds, retained approved controls, orphan attempts, malicious raw/prefix/derived paths), unset/OFF values, explicit ON values, leased/immediate deletion shutdown and populated dry-run read-only SQL/proposal consistency.
- Scheduling audit: deploy.yml builds normal backend and updates8existing jobs, not highlights; raw-video maintenance calls only video_queue/video_retention. No infra/cron/loop starts highlights; Dockerfile.highlights defines only a bounded command. Removed dark daily-sweep instruction; lane doc and PR go-live checklist require separate build → explicit retention ON → explicit scheduling → MJ's release go, activation operations only with MJ's go.
- p2c2 migration2600cef5/preapply0d79f07c/sourceguardsafe16025 byte-identical to ca856840; no schema/frontend/dependency changes. Main eddba4ac read-only merge preview conflicts in shared lane frontend files; refresh deferred to release as directed.
- Implementation/tests/docs frozen before final commit. Required final-head cached backend-full/backend-lint, complete lane PostgreSQL suite, pushed SHA/PR body/BUS DONE and cleanup are authoritative in external `logs/C2F6.final.md`, `logs/C2F6.sweeper-answer.md` and `logs/C2F6.gate-manifest.json`; repository ledger precedes verification to preserve reusable commit-keyed gates. No merge/deploy/activation; no owned dev server or simulator.
