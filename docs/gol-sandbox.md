# GOL analysis capability boundary

The chat service executes model-written analysis code from the `run_analysis` tool
against adult-filtered request DataFrames. Authentication and the 20/minute route
limit are access controls; they do not make generated code trustworthy.

The original implementation compiled with RestrictedPython, omitted imports,
restricted underscore/inspection/format attributes, limited displayed rows to 100,
and waited 10 seconds on a daemon thread. It nevertheless exposed full pandas and
numpy module namespaces, inherited mutable/version-dependent safe builtins, added
`type`, returned every object from the item/write guards, and formatted unknown
results with `str`. The module namespaces exposed operating-system capabilities.

`src/services/gol_capabilities.py` now owns the explicit library names, builtins,
receiver types, attributes and methods. Guard checks happen before attribute
lookup; returned modules are also refused. Library classes needed for DataFrame,
Series and numeric dtype construction are callable but have no class attributes.
Timestamp construction is wrapped and accepts named timezone-directory entries
only. Arbitrary timezone-file syntax is unavailable.

Only in-memory table/series/index/array analysis methods and selected string/date
accessor operations are available. Writers, readers, plotting/Styler, metadata,
buffers/pointers, object internals and string evaluation are unavailable. Both
`query` and `eval` are refused. Callback methods retain restricted lambdas and
functions; their string dispatch is limited to statistical reductions. This also
covers nested dictionaries/lists, named aggregates with a missing or explicit
`None` function, and positional or keyword pivot/crosstab reducers. Engine/parser
kwargs are unavailable. All callables obtainable from the boundary are restricted
functions, chosen safe builtins/constructors, wrapped in-memory operations or
scalar-argument stored-data helpers; reflection on them is refused.

Item, iterator/unpacking, write and augmented-assignment guards restrict receiver
kinds. Attribute writes permit only validated DataFrame labels and Series
labels/name. Input cells/labels/metadata must contain plain data; request copies
also clone nested lists/dictionaries. Helpers never fall back to a DB/API name
resolver. New library capabilities require compatibility and escape tests.

The result must be an exact DataFrame/Series or approved scalar/list/tuple/dict.
Cells, labels, index and metadata are recursively validated before row conversion
or JSON. Unknown objects, subclasses, callables, cycles and unsafe nested values
are refused without calling representation/serialization hooks. Even omitted
rows are validated. Existing numeric display/rounding is preserved; date cells
now serialize as ISO strings with their offsets, missing/nonfinite values as null.
Errors never echo rejected values, compiler details or exception text.

## Limits and remaining risk

Preparation, execution and formatting share the existing 10-second thread wait.
Code is limited to 20,000 characters and 4,000 AST nodes; restricted Python frames
have a 100,000 trace-event budget and deadline check. Imports/classes/async code,
bare exception handlers and `finally` clauses are refused. Output has a shared
20,000-value budget and depth20; display still caps at100 rows. Common numpy shape
allocators have a one-million-cell precheck and explicit allocation dtypes are
limited to16 bytes per element.

These are cheap bounds, **not hard CPU or memory isolation**. Large string/list
multiplications, joins, repeats, casts, regexes and native numerical work can still
consume resources before a guard runs. Native code can delay asynchronous thread
termination. A thread timeout stops waiting, then requests best-effort SystemExit;
it does not guarantee the thread died. On the 0.5CPU/1Gi production container this
can starve workers/health checks or OOM/restart the process. No intentionally huge
allocation or native runaway is exercised in tests. The allowlists also depend on
pandas/numpy implementations; dependency changes must rerun the corpus.

The stronger follow-up is a separate, killable worker process/container with a
minimal environment and no credentials, denied network/filesystem access, strict
CPU/address-space limits (or cgroup limits), bounded concurrency and plain bounded
IPC. Pass only eligible frame data; enforce the deadline in the parent, kill and
reap on timeout, and validate returned data again. Account for dataframe copying,
spawn/startup cost, Linux production vs macOS tests, and deployment packaging.

## Interim operational control

There is **no existing dedicated analysis/chat OFF flag**. `API_FOOTBALL_FROZEN`
removes live lookups but keeps `run_analysis`; billing flags only control metering.
`GOL_PROVIDER` chooses the client in `GolService.__init__`: `openrouter` requires
`OPENROUTER_API_KEY`; other values select OpenAI and require `OPENAI_API_KEY`.
Absent credentials for the selected provider cause initialization to raise and
`routes/gol.py` to return503 for new executions. Removing a selected provider key
is an operator configuration option, not a dedicated switch: it can affect other
features, does not cancel existing streams, and stored replays do not initialize
that client. No production configuration change was made or tested by this lane.

## Verification and adjacent evaluation audit

`tests/test_gol_sandbox.py` contains67 legitimate analyses (including all10 helpers
on nonempty fixtures),169 escape cases and34 boundary/resource checks. The
legitimate corpus uses raw libraries plus a frozen pre-fix formatter as its
reference; added date-serialization and nested-copy fixes have separate assertions.
The escape corpus covers modules, readers/writers/SSRF/pickle, execution/string
reductions, classes/reflection/formatting, functions/frames/tracebacks, numpy
pointers/vectorization, metadata/accessors, malicious result cells/labels/keys,
mutations and positional/None dispatch. Forbidden I/O/evaluation functions are
spied on; attempts must return neutral errors without calling them. A local fake
provider runs the real tool/completion path and verifies refused results emit no
card and only sanitized errors reach model context.

A repository-wide Python/code/template search found no other production execution
of model/user-written Python or template source. Newsletter Jinja environments
load named repository templates through FileSystemLoader; model/user content is
render data. Spike test `exec` calls compile selected trusted repository ASTs;
other matches were regex/SQL compilation and neural-network `.eval()` mode calls.
