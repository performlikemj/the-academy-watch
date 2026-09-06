# Coach-to-player development

A coach turns an observation into a private practice action. The player practises, records a reflection, and asks for review. The coach responds with more practice or a completed review.

## Coach journey

1. Open the club roster and the accepted player's **Publish feedback** panel.
2. Choose **Find AI observations**, then select an observation, or write feedback from your own coaching.
3. Add one focus, what to practise, what progress looks like, and an optional review date.
4. Edit the interpretation and advice, preview the exact text, then confirm publication.
5. Return to publication history and refresh. When the player is ready, read their reflection and write a response. Choose **Keep practising** or **Mark reviewed**.

AI suggestions use existing grounded captions from finalized match reports bound to the exact player and club. They are draft material requiring coach judgment. No new model call or automatic practice prescription runs. If suitable footage is unavailable, the coach can still author an action.

## Player journey

On iOS: **Home → My profiles → your profile → Coach feedback**. On web, open private feedback on your owned profile.

Read the action, practise, then save a reflection or choose **Ready for coach review**. Reopening feedback restores progress and the coach's response. Reading acknowledgment is a separate explicit action. Players can continue practising after a review.

Private feedback, reflections, and reviews never automatically appear on public profiles. Public profile editing, following, and approved highlights remain separate existing features.

## API and data contract

Publication and correction accept optional `development_action`:

```json
{
  "focus": "Scan before receiving",
  "practice": "Check both shoulders before five receptions.",
  "success": "Identify the forward option before the ball arrives.",
  "review_on": "2026-09-12"
}
```

`review_on` may be null. Limits: focus 160, practice 1000, success 500 characters. Omitting the action preserves legacy publication behavior and request hashing.

- `GET /api/club/:program/player-feedback/suggestions?invitation_id=:uuid` — authorized coach; up to 12 grounded observations across the latest six matching finalized reports. No footage URLs or raw match metadata.
- `POST /api/me/player-feedback/:revision/progress` — exact accepted claimant; body `{expected_version, status, note}`. Player statuses: `working_on_it`, `ready_for_review`.
- `POST /api/club/:program/player-feedback/:thread/progress-review` — current coach; body `{expected_revision, expected_version, status, note}`. Review statuses: `working_on_it`, `reviewed`; requires a player submission ready for review.

Progress starts at version 0. Updates increment it under existing relationship/thread row locks. Stale versions and superseded feedback revisions return 409. Notes are limited to 1000 characters; ready-for-review and coach responses require text. The latest 20 history events are retained, with the current reflection and current coach response separately available. A correction starts a new progress record; the prior revision remains historical.

Actions and progress are nullable JSON fields on the existing private feedback record. Withdrawal, relationship closure, account export/deletion, and audit retention follow that record's existing policy. There is no separate public projection or browser storage of reflections.

## Release and QA

Apply migration `s4d1` before starting the updated backend. Existing feature flags and accepted club relationships are required. Publish the backend before the updated clients. Coach authoring/review uses the web club workspace, accessible from the iOS club area; player actions are native on iOS.

This branch is stacked on `feat/ios-player-club-experience` (PR #1045). It has not been deployed or submitted to TestFlight.

Automated evidence uses synthetic accounts and isolated Basecamp PostgreSQL, browser mocks, and explicit offline native API fixtures. Native fixtures intercept every request and never contact production. Real-player adoption and a distributed TestFlight session remain release-stage checks.

Validation details and screenshot locations are recorded in `ledgers/CONTINUITY_coach-player-development.md` and the local `scratchpad/coach-player-development/QA_REPORT.md`.
