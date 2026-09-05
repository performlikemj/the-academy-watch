# DIRECTIVE — One-club pilot (clubs first), 2026-09-05

Joint decision (Fable orchestrator + codex gpt-6-astra; codex's full analysis: `ledgers/research/pilot-direction-codex-2026-09-05.md`).
Owner question: scouts first, players first, or reach out to clubs? **Answer: clubs first, ONE club, adult sub-group, concierge Film Room.**

## Why
- The product is built (audited 65.1%); nobody uses it (30-day sign-ups 2, claims 1, contact requests 0, club claims 0). Building more cannot earn adoption.
- Scouts can already browse provider data they can get elsewhere; the unique supply (grassroots/academy players with real games, club-confirmed stats, film) comes
  from clubs. One club brings a coach, players, results and footage at once and is the buyer of player analysis. Scouts follow supply.
- Individual adult players onboard slowly and produce thin data; no warm lead.

## What codex corrected in the orchestrator's plan (accepted)
1. Pitch ONE coach's recurring review problem (a weekly film-based player review), not "tracking + analysis + exposure" in one breath.
2. Invitations + feedback alone do not close the loop: local-player club attestation is rejected today (`showcase.py:~2669`) so club-included contact routing fails
   for player-created locals; result correction is missing (`club.py:~959`). Both are pilot dependencies.
3. The coach's brief is an INPUT to analysis, not player feedback; build a separate permissioned feedback record.
4. Club Film Room footage stays private (showcase excludes club matches by design); promise searchable adult profiles + private club review only.
5. U18: adult sub-group only. The code has no complete guardian-consent journey; staff-only youth review needs separately approved permissions.
6. "Ten people doing real things" is too weak → the register below.
7. Reach out BEFORE building; secure a named coach, authorized footage, a review date and agreement to discuss paid continuation.

## Sequence
Outreach now → **P0** real-club preflight (operator work + a rehearsal on the basecamp sim) → **P1** cohort register/report (S) → first staff session →
**P2** adult accepts the club relationship incl. local contact routing (M) → **P3** private player feedback + acknowledgment (M) → **P4** stable result
corrections (M; before repeat result entry). Billing go-live (B2) is a separate owner track and does not block the pilot.
Package details, acceptance evidence and risks: codex doc Part 3. Not built yet: A7 dashboard, A10 self-serve Film Room, native parity, U18 architecture.

## Definition of "ten real participants" (declare the register BEFORE counting)
Target: 2 club staff, 6 adult players, 1 external verified scout, 1 genuine supporter — each on their own account doing a role-relevant action
(staff: real result or published feedback; player: own approved claim + accepted relationship + logged game or acknowledged feedback; scout: discover + save a
pilot player, introduction only with a real reason; supporter: follow + return to view an update). Require a second review cycle with ≥1 coach and ≥3 players
returning in a later week. Excluded: founder-created records, registrations alone, test/reviewer accounts, controlled purchases. Report four separate results:
qualifying participants, repeat use, one genuine cross-person outcome, paid continuation decision.

## Owner track
Outreach message (codex draft, honest about concierge) and pilot terms (scope, promise, commercial boundary, footage/data permissions incl. derived data,
U18 exclusion, continuation decision): codex doc "Owner track". Warm lead: Head of Academy at Nottingham Forest asked for literature on 2026-04-08
(memory + `ledgers/academy-data-audit.md`).
