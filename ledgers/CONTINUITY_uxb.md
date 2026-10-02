# UXB staging directory and opportunities polish

- Status: complete; draft PR #1124 (https://github.com/performlikemj/the-academy-watch/pull/1124), unmerged.
- Goal: P-01–P-07 and P-23 behind existing B1/B2 flags; draft PR, no merge.
- Base: main 784b1490; branch fix/staging-ux-opportunities.
- Constraints: foreground only; no migrations/dependency changes; minors/private applicant DTO invariants.
- Ownership: no UXM1/UXM2 files edited; P-02 uses their existing owner-only mount via the separate teaser component. App.jsx changes delimited.
- Done: public club opportunities; owner summary/home/menu; existing-application/age hints; signed-out auth gate; range/gender/email copy; mutually exclusive directory filters; published/activity-first recruiting.
- Gates: OSV547 clean; Ruff/check-format570; full flags-off pytest4083pass69skip0fail (900.09s), new focused8; Node222; lint0err189warn; build pass; Playwright65 + final extended real-rule2 pass.
- Screenshots: 60 PNGs, 1440×900/390×844 plus full-page variants; reviewed, no overflow.
- Cleanup: own5162/5212 stopped; aw_uxb dropped; dump/persona tokens/temp/browser/build outputs removed.
- Evidence: ~/codex-runs/aw-redesign/logs/UXB.final.md, logs/uxb/, shots/UXB/INDEX.md.
- Code: 204eb42e; draft PR against main.
- Next: independent review; keep draft, no merge.

## UXBF1 fix round (2026-10-01)

- Status: complete; source c8cf1a63 pushed to draft #1124; final documentation head recorded in UXBF1.final.md. Reviewed baseline07e2e102.
- Scope: shared dark flags, profile selector, title/venue wrapping, UUID validation, deterministic CI browser matrix, eligible-adult summary, pending-state flashes, formatter fallback, expired duplicate/status copy, parent-interest anchor.
- Lead rulings: preserve find/create below profile/applications; O-8 only confirmed flashes/expiry +409 copy; omit disputed cosmetic/invalid-range items.
- Now: all review findings + lead rulings and parent-interest anchor fixed; Next: independent review of draft #1124, no merge.
- Milestone: review regressions red (backend5/PG2/browser7/formatter1); fixes build; focused backend+PG37 and Node225 pass. Main784b1490 already ancestor (merge up-to-date); no lower stack. Full flags-off suite running; browser32 + screenshots/remaining gates next.
- Full flags-off pytest:4090pass72skip0fail147warnings (667.28s); PG22 pass (+focused15), Ruff/check-format570, Node225, OSV547 clean, lint0errors189existing warnings/build pass.
- Browser milestone: initial deterministic32 pass; expanded36 matrix and all69 existing/real browser cases now running together (separate HTTP DB avoids B2 PG fixture pollution; shared-artifact concurrent-run failures discarded).
- No migration/lockfile/dependency changes; refreshed origin/main784b1490 already included; no lower stack.
- Final browser gate:105pass0skip0fail (36 deterministic review cases +69 existing/real cases incl all12 live-persona checks); separate HTTP scratch snapshot, no mocks in those12 real checks.
- Screenshots:72 refreshed PNGs +INDEX/SHA256SUMS in shots/UXBF1, desktop1440/mobile390; selected states inspected, width assertions pass.
- Cleanup: owned5162/5212/temporary5173 servers stopped; aw_p2_b2 +aw_uxbf1_http dropped/confirmed absent; token/dump/server scripts/build/browser outputs removed. Shared aw_staging unchanged; original node_modules preserved.
- Delivery: source c8cf1a63 pushed; draft #1124 remains OPEN/DRAFT/unmerged. docs-only final delivery commit follows; hand-back logs/UXBF1.final.md records final pushed SHA and CI.

## UXBF2 fix round (2026-10-01)

- Status: complete; reviewed head0a2b6e99, draft#1124 remains OPEN/DRAFT/unmerged, no lower stack. Final pushed SHA in external UXBF2.final.md.
- Scope: O1 failure retains header/find/create + contextual retry; O2 settled adult anchor; X2 both invitation surfaces wrap; X3 maximum profile name wraps; X1 open meta rows-only; O4 N4 draft skip restored. Optional O3 skipped unless trivial.
- Now: required union fixes and N4 decision complete. Next: independent review of pushed head; no merge.
- Milestone: main784b1490 already included (fresh fetch/merge up-to-date); OSV547 clean/existing deps retained, initial Ruff/format570 green, own snapshot PG22 pass10.41s. CI policy regression red (Frontend Tests guard missing, four controls pass); browser failure probes running. No migrations changed.
- Milestone: initial18 browser regressions red at reviewed code; fixes pass16 focused cases, claims fixture corrected to keep outage until explicit retry (header also reads eligibility), then claims2 green. Added delayed retry/discovery preservation + loading/error meta + both invitation surfaces. Node230/lint0errors189existing warnings/build pass; full pytest and final real+synthetic browser/screenshot gate running foreground.
- Full flags-off pytest:4090pass72skip0fail147warnings719.00s; PG22pass10.41s. Corrected persistent-claims outage and separate maximum home invitation probes fail4/4 on isolated reviewed0a2b6e99 source; active worktree fixes unchanged. Fresh main784b1490 still current/ancestor.
- Final broad Playwright gate:125pass0skip0fail4.5m; all12 live PostgreSQL-persona checks +60 deterministic cases. Refreshed96 PNGs in shots/UXBF2 with INDEX/SHA256SUMS; selected failure/anchor/maximum-text desktop/mobile states inspected. Own managed5162/5212 stopped; aw_uxbf2_pg/aw_uxbf2_http dropped and absent; snapshots/persona tokens/server/copy/temp config removed. CI60-case timing run + final lint pending.
- Final gates: full flags-off4090/72skip/0fail719.00s; PG22/Node230/pinnedRuff0.16.0-format579/OSV547/lint0errors189inherited warnings/build green. Broad browser125pass0skip4.5m incl12 live HTTP checks; exact deterministic CI command60pass0skip2.5m. Frontend Tests restored to ready-PR/main guard; five N4 policy checks pass. No separate JSX typecheck script.
- Hand-back: logs/UXBF2.final.md maps O1/O2/X2/X3/X1/O4 to FIXED and reverse-probe evidence; optional O3 skipped per brief.96 refreshed shots/UXBF2 with INDEX/SHA256SUMS. Main784b1490 current/included; no migration/dependency changes.
- Cleanup: own managed5162/5212/5173 stopped; aw_uxbf2_pg/aw_uxbf2_http absent; dumps/persona tokens/server/temp configs/isolated reviewed copy/build/browser outputs removed. Original dependencies retained; shared staging unchanged. Final delivery SHA/CI in external hand-back.
- Delivery verification: source62ad447a pushed; draft CI36850169022 SUCCESS with all four non-security jobs SKIPPED, security SUCCESS. Pinned Ruff0.16.0/check-format579 passes; final documentation-only correction follows, final pushed SHA in external hand-back.

## UXBF3 fix round (2026-10-02)

- Status: in-progress; reviewed ac877e05; draft #1124, no lower stack.
- Scope: X1=O1 shared user-keyed retry/navigation; O2 canonical UUID anchor; O3 readable maximum-name pill; safe no-id list hash.
- Now: reverse reviewers’ probes into regressions; Next: tiny fixes, merge origin/main, final four cached gates + PG + lane Playwright, refresh screenshots, push; no merge.
- Constraints: foreground only/machine governor, flags-OFF request parity and auth-change clearing; no migration/dependency changes planned.
- Regression milestone: original reviewed source fails9/14 targeted browser cases (4 navigation recovery,4 UUID anchor,1 mobile pill contrast);5 controls/no-id hash pass. OSV547 clean; dependencies already current. Provider now shares recovery; auth-switch/stale-response coverage added.
- Implementation complete: X1=O1 shared provider/retry with token-transition clearing; O2 case-folded UUID with stale-item/adult-layout guards retained; O3 rounded-xl wrapping pill preserves full name. No-id list/teaser has no parents interest block, so unmatched hash is safely ignored (4 flag/width regressions).
- Targeted verification:36 browser cases PASS (recovery, auth switches/logout/stale response, both widths, UUID case/name contrast, flags-OFF and discovery); changed-file ESLint PASS. Bootstrap activation remains consumer-driven so routes without consumers stay lazy.
- Main integration: fresh origin/main784b1490 already ancestor; merge up-to-date, no lower stack. No migration/dependency/lockfile changes; preapply/CONTRACT not applicable.
- Final verification/delivery is recorded in external `~/codex-runs/aw-redesign/logs/UXBF3.final.md` for the exact pushed head (four cached gates, PostgreSQL22, combined lane browser once, refreshed shots, resource cleanup); no docs-only commit after those gates.

## UXBF4 fix round (2026-10-02)

- Status: in-progress; reviewed a54427cc; draft #1124, no lower stack.
- Scope: O1 Medium recover failed shared feature/claim reads on consumer arrivals; X1=O2 Small refresh claims on player-home/owner-summary visits, retain value while loading, update menu.
- Now: reverse navigation probes; Next: targeted fixes, merge current main, final four cached gates + PG + lane browser once, screenshots, push and cleanup.
- Constraints: foreground/governor; bounded deduplicated reads, token clearing/stale-response rejection; flags-OFF zero business requests.
- Milestone: reviewed-head regressions fail on club/owner startup recovery and approval (both widths); raw12 red, four initial list/detail assertions corrected to real teaser title. Stable post-main targeted56 PASS; earlier context/reload count assumptions corrected; token test affected by mid-run HMR rechecked green.
- Main integration: origin/main advanced to33bf30bd/B3; three conflicts resolved with union ledgers and feature keys; inherited p2b3 migration verbatim, no lane schema edits.
- Added router-arrival key tracking for reused detail components and bounded same-arrival failure recovery; targeted verification next.
- Implementation complete: failed feature/claim recovery bounded per router-key+pathname arrival; successful feature cache reused, claims refreshed by player-home/owner-summary consumers with retained content and in-flight dedup. Token lifetimes reject late replies including returning accounts. Flags-OFF zero business requests preserved.
- Verification: post-main56 targeted checks PASS; route follow-up exposed default-key synthetic navigation, arrival identity now includes pathname;29 remaining cases including reused-detail/privacy/persistent bounds PASS. Final16 startup checks PASS after normal governor wait at high machine load; changed-file ESLint zero errors/warnings.
- Exact FINAL-head four cached gates, PG22, combined lane browser once, screenshots, pushed SHA and cleanup are recorded in `~/codex-runs/aw-redesign/logs/UXBF4.final.md` + `UXBF4.report.md`; no docs-only commit after those gates.
- Candidate7ee95d9f four cached gates PASS(full4273/104skip149warnings450.44s; Ruff-format588/Node230/lint0err193inheritedwarnings/build), PG22PASS5.22s; combined browser187PASS/2FAIL owner claims count, revealing recovery-before-summary duplicate. All foreground commands completed normally.
- Coordination correction: pending/recovered read satisfies the same arrival’s late-mounted summary; reset the refresh marker on route transitions so return/back navigation still revalidates. Delayed owner-metadata regression makes the race deterministic; isolated candidate20/24 exposed reusable-history-key marker case, now fixed. Changed-file lint zero warnings; targeted final correction checks running.
- Final correction targeted24 PASS1.5m: delayed owner-summary mount makes exactly one shared recovery read, approval/removal revalidate after return navigation, overlap shares pending reads, persistent failures bounded, auth clearing/late-answer guards pass. Changed-file lint zero warnings.
- Current main33bf30bd freshly fetched/already merged; B3 f073ecc8 migration matches main byte-for-byte, no UXBF4 migration/preapply/dependency changes. Final corrected head gets all four cached gates/PG22/combined189-case browser once; final delivery record remains external so no documentation-only commit changes that tested head.

## UXBF5 fix round (2026-10-02)

- Status: in-progress; reviewed942c0f2f, PR1124, no lower stack.
- Scope: only RUXBV5-X1=O1 signed-out failed-bootstrap Back/Forward recovery.
- Now: reverse independent probes into list/detail/club history regressions,390/1440,flags ON/OFF; give navigation helper real keys.
- Next: marker-only tracking on every route transition, merge origin/main preserving UXM1 and delimited UXB blocks; final four cached gates/PG/lane browser/screenshots, push, ready, CI.
- Constraints: foreground/governor, lazy bootstrap/one retry per arrival/shared success cache/token clearing/zero dark business reads; no migration/dependency changes.
- Reverse-probe milestone: reviewed code fails all12 Back-return cases at the expected normal-content assertion; first bootstrap remains the only read. Added Forward-return coverage (24 total); Navigation reports every arrival, including disabled signed-out consumers, to a marker-only provider callback; enable also observes arrivals for shared claims coordination.
- Candidate diagnostics: synthetic SPA history tests initially traversed again before Home committed (networkidle is already satisfied on SPA routes); require the actual Home heading. Club bootstrap can have an independent initial read, so assert exactly one additional recovery read relative to settled failure. Diagnostic real logo/Home/Back detailed trace passes. Temporary instrumentation removed.
- Stable reverse proof: all24 final history regressions FAIL on reviewed942c0f2f after Home commits (2s assertion timeout); exact same24 pass with the fix. Focused48 PASS1.5m, changed-file lint0 errors/warnings. No backend production edits.
- Main integration: origin/main ee16572f (B3 + UXM1) merged; AGENTS.md sole conflict resolved as a union. PlayerPage.jsx/ScoutPage.jsx byte-identical to main; existing App.jsx UXB delimited blocks retained. Inherited p2b3 SHA256 f073ecc8 unchanged; no UXBF5 migration/preapply/CONTRACT/dependency change.
- Fix implementation and targeted48 verification complete. Exact FINAL-head four cached gates, PG22, combined lane browser once, refreshed screenshots, pushed SHA, ready/CI and cleanup are recorded in external `~/codex-runs/aw-redesign/logs/UXBF5.final.md`; no documentation-only commit after those gates.
