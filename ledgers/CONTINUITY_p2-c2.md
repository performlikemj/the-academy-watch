# Phase 2 C2 — two-key highlights

## Goal / constraints
- Club picks a server reel window; independent adult self-claimant approves; standalone private clip output; revoke on next request.
- Branch p2/c2-highlights from origin/p2/b3-admin; PR against main stacked on #1115, ready at end; no merge/deploy.
- HIGHLIGHTS_ENABLED default OFF; p2c2 -> real p2c1 ancestor copied verbatim; no placeholder.
- Reuse A1 adult/holds/outbox/audit, A2 capability+byte scope, B1 is_listed. No public minors, youth/mixed footage, raw match SAS or metadata.
- C2F2 owns foreground Vite5204 and scratch aw_c2f2/aw_c2f2_upgrade/aw_c2f2_preapply/aw_c2f2_reverse; clean own resources. Historical C2F1 resources were already cleaned.

## State
- C2F2 final C1F2 integration/gates in progress: review-duel union; O1 first-use autoflush first. Lead rulings: unknown senior attestation verified-manager-only, sticky admin takedown, source revocation notified/recoverable. No 14-day expiry; unanswered follows raw deadline, declined ready assets deleted immediately.
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
- Final modern Playwright269pass/5 existing opt-in skips/0fail; relevant32pass/3opt-in skips incl15 C2. OSV547 clean; Node221/lint0errors193 inherited warnings/build/Ruff-format611 pass; JS repo has no separate TypeScript gate.
- Final full flags-OFF4574pass117skip0fail153warnings881.07s; application source freeze c2521e6b includes B3F5. Later changes only dark-lift test (targeted7pass) and docs/ledgers; Ruff/format rerun green.
- FINAL p2c2 migration58af1d880ef55e7dccd1182ec5f827c3d5a9c9bd1aa8537ab0467d635a58acfc; preapply751d8879e46f941952d760c1373eadf5ddf57f41e7dc03f77fb0f2fa50572a37 repo/external equal. CONTRACT posted for C4 verbatim copy; supersedes early7a523 contract.
- Whole public schema upgrade==preapply twice + guarded upgrade; normalized4b560bf86c929de7aef991b967b916a21ec7d3213a8db629dfb56e158ef997fd/RLS5/source guards7; empty downgrade/re-upgrade pass. C1 7ff6c7d2 and B3 f073ecc8 copied verbatim.
- Latest published main784b1490/C1d9105c37/B3F551f30f5b merged before final gates; final re-fetch confirms all ancestors included. BUS re-read: no C2 ruling override.
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
