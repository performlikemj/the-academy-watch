# MYC1 — club console reload access

- Goal: wait for all club-granting reads; errors show Retry; retain console sub-page URL.
- Owner: /root; branch fix/my-club-load-race; base 58ccb8c6.
- Authorization: loanarmy-ca BUS 2026-10-03 09:59 ASK + NOTE, user builder brief; push/ready PR, no merge or deployed changes.
- Constraints: governed foreground heavy commands; no delegated agents or background commands; no dependencies changed.
- Verified: legacy-only render readiness, swallowed program/staff failures, eligibility starts in delayed effect.
- Done: OSV547 clean before frozen frontend restore; unchanged lockfile. Before screenshots captured at 390/1440 (held program claims → erroneous empty state).
- Done: explicit program/staff/bootstrap/legacy error + readiness states; eligibility tied to candidate snapshot; failed-source Retry; retained URL.
- Validation: targeted slow/failure recovery and coach matrix pass; final owner/manager 12-view controls + bootstrap failure/retry + slow staff + bundled legacy + selective program retry: 8 PASS. Desktop rail/card-title selector corrections verified. Targeted ESLint clean.
- Screenshots: before/after pending + settled Matches at 390/1440 captured; inspected mobile/desktop console and desktop pending loader.
- Decision: extend matrix with player detail URL; unauthorized views keep existing map fallback and preserve URL.
- Typecheck: UNAVAILABLE — JavaScript frontend has no typecheck script or tsconfig; use required lint/build gates.
- State: implementation complete; final-head browser run, four cached gates, push/PR/CI and cleanup receipts are authoritative in the external MYC1.final.md (written after validation).
- Candidate validation 99ddbce8: browser 48 PASS / 1 test-selector FAIL (legacy club title appears in both claim h3 and moderation h2); corrected to assert moderation h2. Production sources unchanged. Three cached gates PASS; let running backend gate finish.
- Next: corrected final-head browser run and four cached gates; ready PR/CI bounded 25 min; external delivery receipt.
- Delivery receipt: ~/codex-runs/aw-redesign/logs/MYC1.final.md.

- Final candidate dddfec7a: four cached gates PASS (5028 backend / 1714 skipped; 319 Node; Ruff631; lint/build); MYC1+staff browser49 PASS. Ready PR1137 to main, pushed.
- CI 37088351280: frontend146 PASS / 2 old-message assertions FAIL; new club-entry bootstrap error intentionally replaces recruiting-local error. Updated both (single parametrized test), preserving no-coming-soon and adding Retry/no-empty/no-business-request controls. Added MYC1 browser spec to CI.
- Now: targeted two CI regressions, final commit/gates/browser/push/CI. Production code unchanged since 99ddbce8.
- Validation: revised 429 bootstrap contract targeted desktop/mobile 2 PASS; ESLint PASS. CI now runs MYC1+staff specs after the existing opportunity regressions. Final delivery remains authoritative externally.
- Candidate0bd7763a: browser49 PASS; four cached gates PASS (5028 backend / 1714 skipped; Node319; Ruff631; lint0 errors). CI did not enqueue because main advanced to53127a54 and PR became CONFLICTING (GitHub suppresses pull_request workflows with merge conflicts).
- Refresh: merge main53127a54; only AGENTS.md/CONTINUITY.md conflict, preserve both histories/patterns. MYC1 production sources unchanged; new main includes GOL maintenance. Final merge head needs four gates/browser/push and CI bounded25 minutes.

## MYC1F1 review union

- Status: complete; X1 and O1–O6 accepted from independent findings/probes; cross files absent per lead.
- Main8696a4de merged as d3b130fe; only master ledger conflict, both histories retained.
- Constraints: bounded15s reads including bodies, no timeout-to-OFF, old completions ignored, unchanged successful bootstrap/request counts. Silent refresh failure preserves workspace; working clubs remain available during failed-club retry.
- Now: implementation + reversed regression probes; targeted checks only.
- Next: final main check, commit, four cached gates + one lane browser run, screenshots, push/CI/cleanup.
- Final delivery ledger: ~/codex-runs/aw-redesign/logs/MYC1F1.final.md.
- Validation milestone: deadline/bootstrap Node6 PASS; reversed browser probes16 PASS (all six unanswered sources, bodies, late answers, mutation/refresh failures, per-club retry, combined retry, accessible presentation and live revocation). Targeted ESLint identified only redundant browser global declarations; removed.
- Targeted follow-up: failed-club URL7/9 + preserved unrelated draft4 PASS; existing desktop/mobile bootstrap2 PASS; changed-file ESLint PASS; diff check clean. Current origin/main8696a4de is included.
- Review disposition: X1/O3 deadline FIXED; O1 silent refresh FIXED; O2 per-club availability FIXED; O4 neutral single alert/44px Retry FIXED; O5 discovery/eligibility retry dedup FIXED; O6 gaps FIXED (including live403 revocation). No dismissed findings.
- State: implementation and targeted validation complete. Final-head governed gates, full lane browser/screenshots, push, boundedCI and cleanup are recorded in external MYC1F1.final.md after completion; do not alter tested head for delivery receipts.

## MYC1F2 review union

- Status: complete (delivery MYC1F2.final.md); X1–X3/O1–O5 accepted; cross files absent per dispatch.
- Main8696a4de already included; no stacked parents.
- Principle: checked program or established legacy workspace opens despite additive failure/slowness; only no-grant entry gates. Global features retain main slow-success/request sharing behavior.
- Now: local-only deadline and additive availability simplification; restore untouched main tests; reverse all probes.
- Next: targeted checks, final commit/four cached gates/one lane browser, shots, push/boundedCI/cleanup.
- Final delivery ledger: ~/codex-runs/aw-redesign/logs/MYC1F2.final.md.

- Implementation milestone: checked clubs publish immediately during additive discovery and parallel roster checks/retries; established legacy workspace also survives additive errors. In-workspace errors use ordinary Retry, no empty flash. Unchanged reads are shared across candidate snapshots.
- Global feature deadline removed; only MyClub entry/body reads are bounded60s. Silent mutation refresh uses main's unbounded read timing and preserves successful confirmation/drafts on failure. Explicit local timeout Retry releases shared inflight promises with stale-write guards; other consumers still await valid late responses.
- Targeted validation: Node6 PASS (new4 + untouched mainfeatures2); reversed browser32 controls initial28PASS/4 asynchronous count assertions corrected; repeated recovery7 initial5PASS/2 initial-bootstrap-count assumptions corrected; compatibility13PASS (seven additive cases, mutation2, per-club2, mainUXBF1 bootstrap2). Changed-file lint corrected one accidental test reference; production lint has existing warnings only.
- Review disposition: X1/O1 availability FIXED; X2/O2 global deadline and cold starts FIXED; X3 mainUXBF1 spec restored byte-for-byte; O3 singular club banner FIXED; O4 saved-but-refresh-failed feedback FIXED; O5 regression gaps FIXED. No dismissed findings.
- Main advanced to e510612a (C4 dark); merge before final validation, retaining main's viewer boundaries.

- Main e510612a merged as4dc7fa5d; sole CONTINUITY conflict retained both histories. C4 components/ClubHome and viewer boundaries byte-identical to main; mainUXBF1/features tests byte-identical. Lane has no schema/migration/dependency delta; C4 migration is inherited verbatim from deployed main.
- Remaining targeted browser33PASS; one sequential-chain request assertion corrected to main's existing15s live-cache revalidation (product succeeded). Dedicated chain1PASS confirms three20s sequential entry reads accept success without Retry. Node6PASS repeated after refresh. Changed-file ESLint0errors (five existing console warnings); test typo corrected.
- State: review union implementation complete. Final-head four cached gates + one combined browser invocation (MYC1/staff and unchanged fullUXBF1), refreshed shots, push, boundedCI and cleanup receipts follow externally in MYC1F2.final.md; preserve tested final head.

- Preliminary head2d5e142f passed all four gates (backend5580/1769skip, unit407, lint668, frontend0errors/203warnings/build) and combined browser235 (MYC1 78/staff9/mainUXBF1 148). The temporary untracked browser config participated in the gate fingerprint, so those receipts are preliminary.
- Finalize combined selection as MYC1_MAIN_REGRESSIONS=1 in committed lane config; remove temporary config. New final commit needs clean-checkout gates and one browser run; no production-source change. This avoids reviewers missing the cached result after cleanup.

- Additional late-answer boundary: b2df5e4b clean gates/browser passed, but an added real-component control proved a timed-out feature answer arriving BEFORE Retry could still cache OFF and yield empty. Baseline1FAIL (product finding); moved existing abandon call from Retry to local expiry (no new mechanism). Other consumers keep the original promise; stale cache writes now blocked immediately. Reversed control plus deadline/body/working-console controls4PASS; updated Node6PASS covers late body before Retry and fetch after Retry.
- Final new head needs four cached gates + one combined236 browser run (MYC1 79/staff9/mainUXBF1 148). Main tests and production/C4 boundaries otherwise unchanged. Exact final delivery remains external.

## MYC1F3 review union

- Status: implementation complete; X1/X2 + O1–O4 FIXED; cross files absent per dispatch. Final validation/delivery receipts follow externally.
- Now: replace cancellation/rejection deadline with Retry notification; late current-attempt answers used, superseded/viewer answers ignored. Main-exact API/features/bootstrap hook; direct MyClub feature Retry.
- Other items: legacy+console eligibility errors get Retry; remove global retry guard; candidate-order switcher, pin bare-route first grant, explain named pending club. Body test clock must await body start.
- Next: targeted reversed probes, merge current main, final commit/four cached gates/one lane browser, affected shots, push/boundedCI/cleanup.
- Final delivery: ~/codex-runs/aw-redesign/logs/MYC1F3.final.md.

- X1 Medium FIXED: 60s complete-read threshold only notifies; current attempt remains alive. Seven 70s sole grants open automatically; never-answer/body reads show Retry; newer retry/viewer discards old answers. Added explicit viewer-switch regression and body-start barrier.
- O1 Medium FIXED: legacy+console owner/staff eligibility failures show ordinary Retry; 503 retry and 70s success recover the same console URL (four reversed controls).
- O2 Small FIXED: global Retry lock removed; each failed source retries independently while unrelated roster remains pending; three feature retries verified.
- O3 Small FIXED: candidate-order switcher; first-granted bare-route workspace pinned with draft/DOM retained; explicit pending URL names the upcoming club at390/1440.
- X2/O4 Small FIXED: API/features and normal staff hook restored byte-identical to main; MyClub first load shares bootstrap, Retry requests directly/local. Main feature/UXBF1 tests untouched. Real API directory20s/70s controls accept shared late success.
- Validation: targeted Node6 PASS; targeted browser25 + viewer/changed-mobile controls3 PASS; changed-file ESLint PASS; diff check clean. Main e510612a already merged, re-fetch/merge up to date. No migration/backend/dependency changes; no preapply CONTRACT applicable.
- State: final implementation complete. Four cached gates and one combined252-test browser run (MYC1 95/staff9/mainUXBF1 148), refreshed screenshots, push, bounded25-minuteCI, cleanup and exact delivery SHA recorded externally in MYC1F3.final.md after validation; preserve tested head.
