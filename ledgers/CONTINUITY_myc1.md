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
