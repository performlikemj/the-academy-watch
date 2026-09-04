# Brief: independent review of The Academy Watch against its "dream scorecard" — how do we get from 65.6% to 100?

You are an independent senior reviewer (codex, model gpt-6-astra) with READ-ONLY access to the repo checkout at
`/Users/michaeljones/Projects/loanarmy/.worktrees/astra-review` (origin/main, 2026-09-05). No network. You cannot run the app; you can read
everything and run pure-local commands (python3, grep, git log). Do not edit files. Your final message IS the deliverable (markdown, as long as it
needs to be; it will be saved to the repo's ledgers by the orchestrator).

## What this product is
Read `CLAUDE.md`, `docs/agents/architecture.md`, `docs/agents/invariants.md`, then `CONTINUITY.md` (§Key Decisions and the top ~60 lines of §Now).
Monorepo: Flask backend (`academy-watch-backend/`), React/Vite web (`academy-watch-frontend/`), SwiftUI iOS (`academy-watch-ios/`), Supabase Postgres,
Azure Container Apps. The owner (solo founder, revenue is the goal) grades the product with a "dream scorecard".

## The scorecard (read these carefully — they define "score")
- `ledgers/GRADING_dream-scorecard-2026-09-02.md` — the rubric, pillars, criteria, the 0–3 scale, reach labels (LIVE_WEB_IOS / LIVE_WEB / ADMIN_ONLY / …),
  and the stage plan S0…S6 with target scores.
- `ledgers/tooling/dream-scorecard/GRADING_dream-scorecard.md`, `README.md`, `score.py`, `scorecard.json`, `overrides.json`, `projection.json` —
  how the number is computed (never type numbers by hand — run `python3 ledgers/tooling/dream-scorecard/score.py` from that directory to see the current
  65.6% breakdown per criterion, and read `scorecard.json` for the evidence strings behind each grade).
- Stage ledgers with what was claimed shipped: `ledgers/CONTINUITY_dream-s3.md` (S3 money rails + GOL credits), `ledgers/DIRECTIVE_dream-s3-handoff.md`,
  `ledgers/DIRECTIVE_gol-credits.md`, `ledgers/ROADMAP_vision-gaps.md`, and the S0–S2 entries in `CONTINUITY.md` §Now. Recent PRs (git log since 2026-09-01)
  show the actual code: S1 player universe + games grain, S2 fans/reach/share/email, S3 Stripe billing foundation + club programs + Scout Pro entitlements
  + GOL chatbot credits (3 free questions, $20 starter), iOS fixes (#1010 dead host, #1012 season-stats decode, #1014 sign-in cap + XCUITest walks, #1016 1.0.1).

## Your job (three parts, in this order)
### Part 1 — Verify the scorecard against the code (be adversarial)
For EVERY criterion in `scorecard.json`: does the code actually deliver what the grade and evidence string claim, at the reach label claimed?
Read the load-bearing routes/models/components for each (the evidence strings name them). Classify each criterion as CONFIRMED / OVERSTATED (say what
grade the code really earns and why) / UNDERSTATED (the code does more than credited). Pay special attention to: things marked LIVE that are actually behind
a flag or admin-only; iOS parity claims (the iOS app is thinner than the web — check what each "LIVE_WEB_IOS" criterion really has on iOS); money paths
(billing is dark behind `BILLING_ENABLED`; GOL credits); "adoption" criteria that cannot be earned by code.

### Part 2 — Quality review of the recent work (S1–S3 + iOS), as a reviewer who will be blamed if it breaks
Read the diffs of the last ~30 merged PRs (`git log --since=2026-09-01 --merges` or the squash commits on main) with emphasis on: Stripe webhook +
credit ledger correctness (idempotency, refunds, races), entitlement gating, RLS on new tables, migrations guard, the season-rollup read path, the iOS
decoders vs live JSON shapes (fixtures under `academy-watch-ios/AcademyWatchTests/Fixtures/`), the XCUITest walks. Report concrete defects (file:line,
failure scenario), not style. Rank by user/revenue impact.

### Part 3 — The plan to 100 (the part the owner will act on)
Produce a ranked list of the moves that raise the score the most per unit of work, with for each: criterion ids affected, current→target grade,
what exactly to build/change (files, endpoints, screens), the reach it must ship at, an effort estimate (S/M/L in codex-days), risks, and the
evidence a checker should demand. Separate three buckets honestly:
  A. Code-only gains (we can ship these with codex + Fable checkers).
  B. Owner-action gains (env flags to flip, Stripe/Apple setup, legal copy, pricing decisions) — say exactly what the owner must do.
  C. Not earnable by code (real adoption, ten real participants, revenue actually flowing) — say what the product must make easy so those can happen,
     and which criteria will cap the score until they do.
End with: the realistic maximum score if A and B are fully done and C is not; what 100 would require.

## Output format (markdown; the orchestrator saves it verbatim)
1. `## Verdict` — 10 lines max: current honest score per your Part 1 (if different from 65.6%, explain the delta), top 5 moves, the ceiling.
2. `## Part 1 — Criterion audit` — one table per pillar: id | claimed grade/reach | your grade/reach | verdict | evidence (file:line).
3. `## Part 2 — Defects` — ranked table: severity | area | file:line | scenario | fix.
4. `## Part 3 — Plan to 100` — buckets A/B/C as above, ranked inside each.
5. `## Appendix` — anything you could not verify without network/prod access, and what command/query would settle it.
Rules: cite file paths and line numbers for every claim; never invent files; never print secrets or env values (there are none in the repo, but if you find any,
report the path only); do not propose "unified frameworks" — smallest correct mechanism on top of what exists.
