# Task brief — SMOKE: prove the pipe

**Pattern:** pure-core · **Thinking:** off · **Budget:** 15 min ·
**Files you will touch:** `academy-watch-backend/tests/test_lane_smoke.py` (NEW). Nothing else.

## The situation

This is the first run of the qwen lane in this repo. Nothing is broken. We need to see you read a
brief, write one file, run the gate, and file a handback. That is the whole task.

## The job

Create `academy-watch-backend/tests/test_lane_smoke.py` with exactly this content:

```python
"""Lane smoke test — proves the qwen pipe (brief -> file -> gate -> handback). The orchestrator deletes it."""


def test_lane_smoke_adds():
    assert 1 + 1 == 2
```

(Two blank lines between the docstring and the function — that is what `ruff format` wants.)

## How to start

1. Write `PLAN.md` (at most 3 lines). Then act.
2. Create the file above.
3. Run `make gate TASK=SMOKE`. It prints `GATE GREEN`. Done.

## When things go wrong

- `ruff format --check` says it would reformat your file → run
  `ruff format academy-watch-backend/tests/test_lane_smoke.py` and run the gate again.
- `make: *** No rule` / `lane-gate: no gate file` / `pinned python missing` → STOP. Say BLOCKED and
  paste the output. That is a setup problem, not yours.
- Same error twice → STOP, BLOCKED, paste it.
- After ANY interruption: run the gate; whatever is red is your next step.

## Do not

- Do not touch any other file. Do not add more tests. Do not "improve" anything.

## Done means

1. `make gate TASK=SMOKE` green — you ran it, you saw it.
2. `academy-watch-backend/tests/test_lane_smoke.py` exists with the content above.
3. Your report is on disk at `.harness/handback/$HARNESS_SESSION.md` and the LAST line of your final
   message is exactly: `HANDBACK-FILED: .harness/handback/$HARNESS_SESSION.md`
