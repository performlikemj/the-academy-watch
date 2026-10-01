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
