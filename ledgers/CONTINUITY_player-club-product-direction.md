# Player and club product direction

Parent: CONTINUITY.md
Root: CONTINUITY.md
Related: ledgers/CONTINUITY_ios-player-club-experience.md; ledgers/CONTINUITY_ios-basecamp-qa.md
Owner: /root

## Goal
- Clubs join, bring their players onto the platform, and turn AI match analysis into actionable feedback shared with those players.
- Players enrich their profiles and build a following through visible development, creating opportunities for career progression without promising outcomes.

## Key decisions
- 2026-09-06 user direction: connect the club development workflow and the player's public profile/following experience as one product journey.
- Prioritize the complete club-to-player feedback and development journey when assessing future work.

## Constraints / Assumptions
- Existing consent, privacy, moderation, and account authorization rules still apply.
- Private coach feedback and club footage do not automatically become public profile content.
- Current implementation supports coach-authored publication; automating the conversion of AI observations into coach-reviewable feedback is not confirmed as shipped by this discussion.
- 2026-09-06: user subsequently authorized building the coach-reviewed action/progress workflow; implementation tracked in CONTINUITY_coach-player-development.md. Release and automatic publication are not authorized by that request.

## State
- Done: Product direction captured from the user.
- Now: Use this journey to evaluate priorities after the current iOS changes.
- Next: Complete the deployed club/player QA loop; assess remaining friction between AI analysis, coach-reviewed feedback, player action, and approved public development evidence.

## Links
- Upstream: CONTINUITY.md
- Related: ledgers/CONTINUITY_ios-player-club-experience.md

## Open questions
- None blocking recording the direction.

## Implementation rollup
- 2026-09-06: First private development loop built on `feat/coach-player-development`; coach-reviewed AI draft, structured practice, player reflection and coach review. Basecamp automated QA passes; screenshot gallery available. See `CONTINUITY_coach-player-development.md`.
