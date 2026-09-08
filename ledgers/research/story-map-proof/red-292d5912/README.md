# Reproducible RED overlay

Baseline: `292d5912` (full revision in `apply-result.txt`). Apply
`instrumentation.patch` at the repository root of a detached baseline worktree.
Its SHA-256 is in `instrumentation.patch.sha256`; every resulting tracked iOS
file's SHA-256 is in `applied-source-sha256.json`.

The patch adds the offline fixture transport, simulator-only role seeding,
native tab and chooser accessibility IDs, the journey runner, and its host,
inventory/resources and generated scheme. RootTabView retains baseline
`$selectedTab`, its unconditional five tabs, and its original initial-tab logic.
Account has no changes. PlayerHome changes only equivalent accessibility IDs.
The original scout routing defect is deliberately preserved.

Reproduction (in an isolated baseline worktree):

```sh
git apply --check /path/to/instrumentation.patch
git apply --index /path/to/instrumentation.patch
HARNESS_RECLAIM_BUSY=1 HARNESS_ROOT=/path/to/harness bash academy-watch-ios/sim/run.sh --no-grade
HARNESS_RECLAIM_BUSY=1 HARNESS_ROOT=/path/to/harness bash academy-watch-ios/sim/run.sh --no-grade
```

The first run earns real launch receipts; the second executes full journeys.
The retained report is the second run. A successful host exit means a valid
report, including honest behavioral failures; it does not mean RED stories pass.
The report records the baseline revision with `source_dirty: true`; release
acceptance deliberately rejects an instrumented baseline. The exact applied
source is identified by the patch and per-file manifest above.
