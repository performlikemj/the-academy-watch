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
- Next: before/after Matches 390/1440; role/page/slow/failure browser matrix; four cached final-head gates; push/PR/CI bounded 25 min.
- Delivery receipt: ~/codex-runs/aw-redesign/logs/MYC1.final.md.
