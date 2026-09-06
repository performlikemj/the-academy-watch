# Coach-to-player development workflow

Parent: ledgers/CONTINUITY_player-club-product-direction.md
Root: CONTINUITY.md
Related: ledgers/CONTINUITY_ios-player-club-experience.md
Owner: /root

## Goal / acceptance
- A club coach can select a verified, player-bound AI observation from finalized match analysis and edit it into private feedback.
- Coach can specify one clear focus, practice action, success criterion, and optional review date, then preview and explicitly publish.
- Player can see the action on web/iOS, record working-on-it / ready-for-review plus a reflection, and revisit persisted progress.
- Coach can read that reflection, respond with a review, and request more practice or mark the action reviewed.
- Preserve exact claimant/club authorization, private-media boundaries, revision isolation, withdrawal/retention/account deletion, and stale-write protection.
- Test native and web journeys plus real backend persistence/permissions, and provide screenshots.

## Constraints / assumptions
- User authorized implementation on 2026-09-06. No production release, feature-flag changes, automatic message publication, or real participant data mutations.
- New isolated worktree `.worktrees/coach-player-development`, branch `feat/coach-player-development`, based on 713afb41 / open PR #1045. Latest main differs only by owner-direction documentation (#1046).
- Existing generated, grounded match observations are the draft source; no new AI model/cost or self-serve analysis pipeline is introduced.
- Private actions and player reflections never automatically appear on a public profile.
- Single workstream, no delegated agents.

## Work breakdown
1. Backend: additive action/progress fields, guarded migration, coach-only evidence candidates, revision-bound player updates and coach review.
2. Web: evidence-to-draft selection, action authoring/preview, player progress form, coach review in history.
3. iOS: typed action/progress models and API, native practice/reflection/review UI, offline fixture journey.
4. Validation: backend privacy/concurrency/migration tests, web real components, native tests/screenshots; reviewable branch delivery.

## State
- Done: Backend, web and native practice/review workflow implemented; Basecamp QA passes; 14 screenshots visually inspected.
- Now: Packaging reviewable branch and draft PR.
- Next: Review/merge parent and feature PR; apply s4d1 before updated backend; release web and iOS/TestFlight separately.

## Decisions
- Add nullable JSON action/progress fields to existing feedback revisions so current private-record deletion/retention remains authoritative.
- Keep progress version separate from feedback revision; reject stale changes and edits to superseded revisions.
- Grounded captions must map through finalized reports to the exact accepted player identity before becoming coach draft suggestions.

## Open questions
- None blocking implementation.

## Validation progress (2026-09-06)
- Backend implemented, 21 SQLite development tests pass; migration repeat/partial recovery passes on Basecamp PostgreSQL; historical migration fixture updated to distinguish original 19-column schema from current 21-column model.
- Web authoring, preview, player reflections and coach review integrated; frontend lint 0 errors (178 existing warnings), production build passes. Basecamp 24 mocked browser journeys pass at desktop/phone widths; conflict/account-switch cases added next.
- Native action/progress UI implemented. Basecamp light-mode 10 offline UI walks pass including persisted practice and coach review screenshots. Added native API/version/conflict/access-loss unit tests; final suite in progress.
- Basecamp isolation: `/Users/mjjones/Projects/loanarmy-development-qa`, dedicated DB `pilot_p2_development_20260906`, simulator `C99B52E6-CA79-4B9A-866D-DC7A9FD41D59`. No production mutations.
- Final backend command initially referenced nonexistent `test_account_lifecycle.py`; corrected to actual `test_account.py` before rerunning.

## Final checks
- Basecamp: 224 backend tests including real PostgreSQL; 201 native unit/API; 26 browser journeys; 10 light native UI plus 2 dark/XXXL development UI all pass.
- Ruff check/format, frontend lint (0 errors, existing warnings), production build, and git diff --check pass.
- Evidence: primary workspace `scratchpad/coach-player-development/index.html`, `SCREENSHOTS.md`, `QA_REPORT.md`; 14 screenshots, original export manifests retained.
- Native whitespace-only formatter churn removed after QA; token-equivalence asserted. No behavior change.
- Delivery limits: no deployment or TestFlight submission; coach authoring/review is the existing web workspace, player practice is native.
