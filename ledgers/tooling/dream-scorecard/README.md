# Dream-scorecard tooling (copied from the 2026-09-02 orchestration session)

Every script starts with `S=<scratchpad dir>`; set `S` to your own session scratchpad (or this directory) before use.

- `score.py` — merges codex audit JSON (`out-*.json`) + `overrides.json` (checker/orchestrator verdicts, reach, blocker text) → `scorecard.json`; prints pillar %. Weights P1 25 / P2 25 / P3 20 / P4 15 / P5 15; row score 0–4.
- `build_report.py` — `scorecard.json` + hand-written narrative (blockers, stages S0–S6 with target scores) → ledger markdown + `projection.json` (computed, never typed).
- `build_html.py` — renders the artifact page `dream-scorecard.html` (republish to the SAME artifact URL, see DIRECTIVE_dream-s2-handoff.md).
- `render_md.py` — mechanical tables only.
- `basecamp_sim.sh <origin-ref>` — runs the web sim (SIM_GRADE=0, no ollama) on basecamp in a separate worktree `~/Projects/loanarmy-sim` (runs `flask --app src.main db upgrade` there first; tolerates a DB ahead of the branch). Prints `SIM RESULT n/9 ok`.
- `prod_counts.sh` — READ-ONLY prod adoption counts via the Supabase pooler (secrets resolved from kvref → Key Vault, never printed).
- `prod_preapply_pm01.sh` + `pm01_preapply.sql`, `prod_stamp_pm01.sh` — the pattern for pre-applying a guarded migration's DDL to prod BEFORE merge and stamping `alembic_version` AFTER merge (nothing runs migrations automatically in prod).
- `codex-brief-common.md` — the shared header for codex package briefs (fences, gates, port fence, decisions). `checker-brief-template.md` — the Fable-subagent adversarial checker brief (JSON verdict contract).
- `overrides.json` / `scorecard.json` / `projection.json` — the post-S1 state (59.8%). `s1-hygiene-items.md` — leftover polish list.
