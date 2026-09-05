# Brief: which road to 100 — and the smallest build that gets one real club through the whole loop

You are codex (gpt-6-astra), READ-ONLY, no network, at `/Users/michaeljones/Projects/loanarmy/.worktrees/strategy` (origin/main 2026-09-05). Your final message is
the deliverable (markdown; the orchestrator saves it and arbitrates with you). Be direct; disagree with the orchestrator where the evidence says so.

## Situation
- Product: The Academy Watch (read `CLAUDE.md`, `docs/agents/architecture.md`). Solo founder, revenue is the goal, no marketing budget.
- Your own audit two days ago: `ledgers/research/astra-review-2026-09-05.md` — honest 65.1%, ceiling ~94% by building; Part 3 plan A1–A10 / B1–B5 / C1–C3.
  Since then the money-safety stage shipped dark (`ledgers/DIRECTIVE_money-safety.md`, PRs #1028 #1029 #1030 #1032) and the scorecard was refreshed
  (`ledgers/tooling/dream-scorecard/scorecard.json`, `GRADING_dream-scorecard-2026-09-02.md`). Billing is still OFF in prod; go-live (B2) is the owner's checklist.
- Real adoption (read-only prod counts 2026-09-05): user_accounts created last 30/90 days = 2/3; approved player claims = 1; scout verifications = 1 (approved);
  contact_requests = 0; club_program_claims = 0; player_match_entries = 0; billing rows = 0; video_matches = 2 (1 failed, 1 created). App Store: 1.0 live with
  ~0 downloads, 1.0.1 waiting for review. In short: the product is built; nobody is using it.
- Warm lead: the Head of Academy at a Championship/Premier League academy (Nottingham Forest) expressed interest earlier this year (demo data was made airtight for
  him; see `ledgers/` for "Forest"). No other pipeline.
- The owner's question, verbatim: "what's the most pressing for getting scouts to find players and players to use the app? or for me to reach out to teams and ask
  if they'd like to use the service for scouting and player analysis. it's challenging deciding which road to take."
- The orchestrator's current recommendation (attack it): clubs first, ONE club, concierge-run Film Room, pitch "we track your academy players and loanees, give
  you a film-based coach's brief on your matches, and your players get profiles scouts can find"; build next = coach feedback delivered to players (A2) + club
  invitations a player can accept (part of A5); billing go-live can wait for the pilot; success = ten distinct people from that club doing real things in a month.

## Part 1 — Direction (decide, don't survey)
Compare three roads with the evidence in the code and the audit: (a) scouts first, (b) clubs first, (c) players first (individual adults claiming/creating profiles
and logging games). For each: what the product ALREADY offers that persona on day one (cite routes/screens), what they would hit first that makes them leave
(cite the gap), what supply/demand it creates for the other personas, revenue path, and what the founder must do by hand. Then pick ONE (or an explicit sequence)
and say why in ≤10 lines. Say whether the orchestrator's pick is right and what it gets wrong.

## Part 2 — The pilot loop, end to end, for the chosen road
Walk the concrete journey of the first real cohort through the CURRENT code, step by step (URL/screen → API → table), and mark each step GREEN (works today),
YELLOW (works with founder/admin hand-holding — say exactly what the founder does), RED (missing/blocked — cite file:line). Include: club claim/verification,
console access, roster (tracked + local players), results entry, Film Room upload → analysis → coach's brief → reel, feedback to players, players claiming their
profiles (adult gate), players logging games, fans/follows, scouts finding those players (discovery, compare, watchlist), scout → player/club contact with club
consent, and what the founder needs to observe (admin event summary). Note anything that would embarrass us in front of a real academy (data correctness, "Sold"
pill semantics, minors — academies are full of U18s: what does the product do with them today, and is that a blocker for an academy pilot?).

## Part 3 — Build plan for the pilot (packages the orchestrator can dispatch)
The smallest set of packages that turns every RED into GREEN or an acceptable YELLOW for ONE club, in dependency order. For each package: goal, files/endpoints/
screens (cite what exists to build on), reach (web / iOS / admin), acceptance tests a checker will demand, effort (S ≤2 codex-days / M 3–5 / L 6–15), risk.
Distinguish "needed before the first club session" from "needed within the first month". Include the owner's parallel track: outreach message (≤120 words, honest
about what is concierge), pilot terms (what we promise, what we don't, data/consent for U18s), and the measurement definition for "ten real participants".
State what NOT to build yet (and which audit items A1–A10 that defers).

## Output
`## Verdict` (≤12 lines) · `## Part 1` · `## Part 2` (table) · `## Part 3` (packages table + owner track) · `## Disagreements with the orchestrator` (explicit list).
Cite file:line for every product claim; never invent files; no numbers typed from memory — read scorecard.json for grades.
