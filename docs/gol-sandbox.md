# GOL analysis capability boundary

The chat service executes model-written analysis code from the `run_analysis` tool
against adult-filtered request DataFrames. Authentication and the 20/minute route
limit are access controls; they do not make generated code trustworthy.

RestrictedPython compiles the analysis code, while explicit capabilities restrict
library access and returned values. The executor runs synchronously inside a
fresh OS-restricted child; its parent owns the hard deadline and cleanup.

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
functions; their string dispatch is limited to statistical reductions; transform also permits an explicit list of in-memory transforms. This also
covers nested dictionaries/lists, named aggregates with a missing or explicit
`None` function, and positional or keyword pivot/crosstab reducers. Engine/parser arguments are unavailable, including positional engines. All callables obtainable from the boundary are restricted
functions, chosen safe builtins/constructors, wrapped in-memory operations or
scalar-argument stored-data helpers; reflection on them is refused.

Item, iterator/unpacking, write and augmented-assignment guards restrict receiver
kinds. Attribute writes permit only validated DataFrame labels and Series
labels/name. Input cells/labels/metadata must contain plain data. Pandas 3 copy-on-write isolates table mutations without another deep data copy; nested object containers are still cloned. Helpers never fall back to a DB/API name
resolver. New library capabilities require classification and compatibility tests.

The result must be an exact DataFrame/Series or approved scalar/list/tuple/dict.
Cells, labels, index and metadata are recursively validated before row conversion
or JSON. Unknown objects, subclasses, callables, cycles and unsafe nested values
are refused without calling representation/serialization hooks. Even omitted rows are validated by dtype or object-cell checks. Interval and Period values render as text. Existing column/index labels support attribute access through the guarded item operation, with approved methods taking precedence. String extension arrays support guarded iteration/items and in-memory list/numpy conversion. Existing numeric display/rounding is preserved; date cells
now serialize as ISO strings with their offsets, missing/nonfinite values as null.
Errors never echo rejected values, compiler details or exception text.

## Limits and remaining risk

Transfer, preparation, execution and formatting share the parent's 10-second
analysis wall budget after bootstrap.
Code is limited to 20,000 characters and 4,000 AST nodes; restricted Python frames
have a 3,000,000 trace-event budget and deadline check. Imports/classes/async code,
bare exception handlers and `finally` clauses are refused. Rendered output has a shared 20,000-value budget, depth20 and a 10,000-character limit per string (including dictionary keys); tables still truncate to100 rows with `truncated: true`. Typed columns and indexes are validated by dtype; only object columns/indexes and categorical labels need Python value checks, including omitted rows. Common numpy shape
allocators have a one-million-cell precheck and explicit allocation dtypes are
limited to16 bytes per element.

The first-layer bounds limit common resident operations. The process layer below
adds mandatory filesystem/network restrictions, hard CPU/address-space limits,
RSS supervision, bounded concurrency and parent SIGKILL/reaping. Large joins,
callbacks and native operations can still reach a resource limit and return a
neutral refusal. The capability and process policies depend on library and OS
implementations; dependency/platform changes must rerun the corpus.

## Operational control

`GOL_MAINTENANCE` pauses the assistant at request time. Missing credentials for
the selected provider also pause it. The maintenance section below documents
fresh questions, reservation recovery, active streams and browser availability.
`API_FOOTBALL_FROZEN` keeps stored analysis available and does not replace the
maintenance switch. This lane changes no production configuration.

## Verification and adjacent evaluation audit

`tests/test_gol_sandbox.py` compares ordinary analyses against plain pandas/numpy
and the frozen main formatter, including 100,000/200,000-row frames, restricted
callbacks, extension strings, column attributes and all added operations. An
explicit classification table covers every allowed name for each reachable
receiver family; new unclassified names fail the test. Public names from the real
libraries drive refusal checks, without route-specific recipes. Unsupported
properties are checked before lookup; nested reducer strings, positional engines,
unsafe omitted cells and metadata have separate controls. The explicit historical
case list is kept outside the public repository and exercised separately.

Fixed, value-free errors distinguish missing columns, syntax, import attempts,
size/time limits and unsupported operations; compiler/exception text never reaches
the response. Service retry hints recognize the execution-limit category. Runaway
restricted Python loops stop at the event cap or 10-second wall-clock deadline,
whichever comes first, even inside a permitted exception handler. Native library
work is bounded by the child resource limits and the parent's hard deadline.

Stored-frame team-name helpers use `Team <id>` when neither the `teams` nor
`team_profiles` frame contains the name. They do not consult a database or API.

Release note: team labels now fall back to `Team <id>` when both stored team
frames lack a name; there is no external name lookup during analysis.

SQL Numeric values are explicitly loaded with pandas' `coerce_float=True`,
preserving its existing float64/NaN behavior without a second frame conversion.
Validation and formatting also accept exact `decimal.Decimal` values in object
columns or results: finite values render as floats rounded like numpy floats,
and nonfinite values (including finite values overflowing float) render as null.
Subclasses remain refused; Decimal attributes are not exposed.

`tests/test_gol_dataframes.py` exercises all ten frames through the actual
PostgreSQL/psycopg loader, including a Numeric rating variant, SQL NULLs, dates,
JSON arrays and text, then calls the service tool on the complete frame set.
It also covers native PostgreSQL arrays/object JSON and SQLite Numeric values.
The public sandbox suite has 255 checks, including 191 ordinary reference cases
(the existing 183 plus eight resident-data idioms). The loader suite adds two
checks; its PostgreSQL check is opt-in locally and required by CI.
CI runs this against a disposable database migrated from a model baseline;
the older migration graph cannot replay from an empty database. Run locally with
`GOL_POSTGRES_URL` pointing to the local disposable `aw_sbxf2` database, bootstrap
using `python scripts/gol_postgres_fixture.py`, run
`python -m flask --app scripts.gol_postgres_fixture db upgrade`, then
`python -m pytest -q tests/test_gol_dataframes.py`. Set `GOL_DTYPE_REPORT` to retain
the dtype of every selected column. Drop the disposable database afterwards.
The builtin allowlist must equal its explicit reviewed classification inventory.
Size-limit errors ask the assistant to simplify or reduce the data scope.

Earlier commits remain visible in the public branch history. No history is
rewritten or force-pushed. The operational mitigation is to keep the assistant
offline until this change is deployed and verified live, then rotate backend
secrets. This lane performs local validation only; it has not verified production
configuration or performed deployment/rotation.

A repository-wide Python/code/template search found no other production execution
of model/user-written Python or template source. Newsletter Jinja environments
load named repository templates through FileSystemLoader; model/user content is
render data. Spike test `exec` calls compile selected trusted repository ASTs;
other matches were regex/SQL compilation and neural-network `.eval()` mode calls.

## Added in-memory operations

- `DataFrame/Series.add_prefix`: creates labels for a resident table/series.
- `Series.dot`: computes a dot product over resident numeric values.
- `numpy facade.trunc`: removes fractional parts from resident numeric values.
- `str.center`: pads resident text to a requested width.
- `str.ljust`: pads resident text to a requested width.
- `set.update`: adds elements from resident iterables.
- `set.issubset`: compares resident set elements.
- `pandas facade.Categorical` as a discarded expression uses the existing constructor capability; no additional result or attribute type is exposed.

- `pandas facade.Categorical`: constructs categorical values from resident data, with no exposed class attributes.
- `pandas facade.DateOffset`: constructs a calendar offset value, with no exposed class attributes.
- `pandas facade.Index`: constructs an index from resident values, with no exposed class attributes.
- `pandas facade.NamedAgg`: constructs a column/reducer description; reducer strings are validated.
- `pandas facade.date_range`: constructs date values in memory; timezone arguments are validated.
- `pandas facade.get_dummies`: encodes resident categories.
- `pandas facade.isnull`: checks resident missing values.
- `pandas facade.melt`: reshapes a resident table.
- `pandas facade.notnull`: checks resident missing values.
- `numpy facade.all`: reduces resident booleans.
- `numpy facade.any`: reduces resident booleans.
- `numpy facade.argmax`: returns the position of a resident maximum.
- `numpy facade.argmin`: returns the position of a resident minimum.
- `numpy facade.average`: computes a weighted statistic over resident arrays.
- `numpy facade.corrcoef`: computes correlation of resident numeric arrays.
- `numpy facade.diff`: computes adjacent differences over resident arrays.
- `numpy facade.divide`: divides resident numbers.
- `numpy facade.isin`: compares resident arrays.
- `numpy facade.nan_to_num`: replaces nonfinite resident numbers.
- `numpy facade.prod`: multiplies resident values.
- `DataFrame.bfill`: fills missing resident values from following values.
- `DataFrame.combine_first`: combines two resident tables/series at missing cells.
- `DataFrame.expanding`: creates a cumulative window over resident data, with only reviewed reducers exposed.
- `DataFrame.ffill`: fills missing resident values from preceding values.
- `DataFrame.filter`: selects resident labels/groups; callback bodies stay restricted.
- `DataFrame.insert`: adds a resident column to the request copy.
- `DataFrame.keys`: returns resident column/index labels.
- `DataFrame.kurt`: computes a statistic over resident numeric values.
- `DataFrame.mask`: selects existing values using an in-memory condition; callable conditions remain restricted.
- `DataFrame.rolling`: creates a window over resident data, with only reviewed window reducers exposed.
- `DataFrame.sample`: samples resident rows; a fixed random seed is supported.
- `DataFrame.skew`: computes a statistic over resident numeric values.
- `DataFrame.where`: selects existing values using an in-memory condition; callable conditions remain restricted.
- `Series.argmax`: returns the position of a resident maximum.
- `Series.argmin`: returns the position of a resident minimum.
- `Series.bfill`: fills missing resident values from following values.
- `Series.combine_first`: combines two resident tables/series at missing cells.
- `Series.expanding`: creates a cumulative window over resident data, with only reviewed reducers exposed.
- `Series.ffill`: fills missing resident values from preceding values.
- `Series.filter`: selects resident labels/groups; callback bodies stay restricted.
- `Series.insert`: adds a resident column to the request copy.
- `Series.kurt`: computes a statistic over resident numeric values.
- `Series.mask`: selects existing values using an in-memory condition; callable conditions remain restricted.
- `Series.rolling`: creates a window over resident data, with only reviewed window reducers exposed.
- `Series.sample`: samples resident rows; a fixed random seed is supported.
- `Series.skew`: computes a statistic over resident numeric values.
- `Series.to_frame`: wraps a resident Series as a table.
- `Series.where`: selects existing values using an in-memory condition; callable conditions remain restricted.
- `Index.difference`: compares resident index labels.
- `Index.get_loc`: locates an existing in-memory index label.
- `GroupBy.bfill`: fills missing resident values from following values.
- `GroupBy.cumcount`: counts resident group positions.
- `GroupBy.ffill`: fills missing resident values from preceding values.
- `GroupBy.nth`: selects resident group rows.
- `string accessor/string.findall`: matches text already in memory.
- `string accessor/string.islower`: checks resident text casing.
- `string accessor/string.isupper`: checks resident text casing.
- `string accessor/string.removeprefix`: removes a literal prefix from resident text.
- `string accessor/string.removesuffix`: removes a literal suffix from resident text.
- `date accessor/scalar.to_period`: converts resident date values to calendar periods.
- `date accessor/scalar.tz_convert`: converts resident date values using only validated named zones.
- `date accessor/scalar.tz_localize`: converts resident date values using only validated named zones.
- `date accessor/scalar.weekday`: extracts the weekday from resident date values.
- `builtin.pow`: computes numeric powers from resident scalar arguments.
- `builtin.divmod`: computes scalar quotient and remainder.
- `builtin.ord`: returns the codepoint of resident text.
- `builtin.chr`: constructs a character from a scalar codepoint.
- `builtin.repr`: represents only recursively validated plain data; arbitrary object hooks are refused.
- `Timestamp.now`: returns a clock value; timezone arguments are validated and all other class attributes stay refused.
- `Rolling/Expanding.agg`: computes only over the resident window; string reducers are allowlisted and callbacks/engines use the same guards as table analysis.
- `Rolling/Expanding.aggregate`: computes only over the resident window; string reducers are allowlisted and callbacks/engines use the same guards as table analysis.
- `Rolling/Expanding.apply`: computes only over the resident window; string reducers are allowlisted and callbacks/engines use the same guards as table analysis.
- `Rolling/Expanding.corr`: computes only over the resident window; string reducers are allowlisted and callbacks/engines use the same guards as table analysis.
- `Rolling/Expanding.count`: computes only over the resident window; string reducers are allowlisted and callbacks/engines use the same guards as table analysis.
- `Rolling/Expanding.cov`: computes only over the resident window; string reducers are allowlisted and callbacks/engines use the same guards as table analysis.
- `Rolling/Expanding.kurt`: computes only over the resident window; string reducers are allowlisted and callbacks/engines use the same guards as table analysis.
- `Rolling/Expanding.max`: computes only over the resident window; string reducers are allowlisted and callbacks/engines use the same guards as table analysis.
- `Rolling/Expanding.mean`: computes only over the resident window; string reducers are allowlisted and callbacks/engines use the same guards as table analysis.
- `Rolling/Expanding.median`: computes only over the resident window; string reducers are allowlisted and callbacks/engines use the same guards as table analysis.
- `Rolling/Expanding.min`: computes only over the resident window; string reducers are allowlisted and callbacks/engines use the same guards as table analysis.
- `Rolling/Expanding.quantile`: computes only over the resident window; string reducers are allowlisted and callbacks/engines use the same guards as table analysis.
- `Rolling/Expanding.sem`: computes only over the resident window; string reducers are allowlisted and callbacks/engines use the same guards as table analysis.
- `Rolling/Expanding.skew`: computes only over the resident window; string reducers are allowlisted and callbacks/engines use the same guards as table analysis.
- `Rolling/Expanding.std`: computes only over the resident window; string reducers are allowlisted and callbacks/engines use the same guards as table analysis.
- `Rolling/Expanding.sum`: computes only over the resident window; string reducers are allowlisted and callbacks/engines use the same guards as table analysis.
- `Rolling/Expanding.var`: computes only over the resident window; string reducers are allowlisted and callbacks/engines use the same guards as table analysis.
- `ExtensionArray.tolist`: converts resident values without persistence or external lookup.
- `ExtensionArray.to_numpy`: converts resident values without persistence or external lookup.
- `DatetimeIndex.ceil`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.date`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.day`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.day_name`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.day_of_week`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.day_of_year`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.dayofweek`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.dayofyear`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.days`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.days_in_month`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.daysinmonth`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.floor`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.hour`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.is_leap_year`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.is_month_end`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.is_month_start`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.is_quarter_end`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.is_quarter_start`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.is_year_end`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.is_year_start`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.isocalendar`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.microsecond`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.minute`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.month`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.month_name`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.nanosecond`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.normalize`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.quarter`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.round`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.second`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.seconds`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.strftime`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.time`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.to_period`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.total_seconds`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.tz_convert`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.tz_localize`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.weekday`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `DatetimeIndex.year`: reads/converts resident calendar values; timezone arguments are validated where applicable.
- `transform("bfill")`: dispatches only this reviewed resident-data transform, rather than an arbitrary method name.
- `transform("cumcount")`: dispatches only this reviewed resident-data transform, rather than an arbitrary method name.
- `transform("diff")`: dispatches only this reviewed resident-data transform, rather than an arbitrary method name.
- `transform("ffill")`: dispatches only this reviewed resident-data transform, rather than an arbitrary method name.
- `transform("pct_change")`: dispatches only this reviewed resident-data transform, rather than an arbitrary method name.
- `transform("rank")`: dispatches only this reviewed resident-data transform, rather than an arbitrary method name.
- `transform("shift")`: dispatches only this reviewed resident-data transform, rather than an arbitrary method name.

## Process isolation for the analysis tool

Production `execute_analysis` supervises a fresh Linux Python interpreter for each
analysis. RestrictedPython capability guards remain the first layer inside that
child. The synchronous executor, frame checks and formatter run only after the
mandatory OS policy. There is no in-process fallback. The child imports analysis
modules, without Flask, models, database services or provider clients. Bootstrap
disables native BLAS threads and retains both C and pure-Python timezone caches
and required lazy pandas/NumPy formatting modules before filesystem lockdown.

macOS and other platforms pause assistant chat and suggestions as maintenance,
without starting an analysis child. Transcript export remains available. The local
Seatbelt interface cannot supply all the Linux lifecycle guarantees, so it is
not used. Clearly named trusted test helpers can exercise the first layer and
transport on macOS; they are not a production execution path or policy test.
Developers needing the analysis tool must use a supported Linux container.

The parent starts with `env={}`, isolated Python settings (`-I -B`), closed
inherited descriptors and three pipes. Bootstrap temporarily sets fixed thread
settings, then clears its environment before input. Each call gets an empty
private temporary working directory. No analysis data is written to files.
Normal completion or failure kills/reaps the child and removes the directory;
readiness probes clean only empty owned directories whose creating PID has gone.
A parent crash may leave an empty directory until a later probe or container exit.

Production transport is versioned column-by-column JSON over the pipe. Fixed
numeric buffers use base64 and explicit dtype/byte order; strings use dictionary
encoding and object values use fixed plain-data tags. It cannot import types or
carry executable objects and never uses pickle. Each column is released before
encoding the next, rather than retaining a whole JSON document and its copies.
The earlier single-document codec remains covered by trusted transport tests.
Only conservatively referenced frames and transitive helper dependencies are
loaded and sent. Helpers obtain data from those frames, never the database.

The authoritative admission/transport table is `src/services/gol_plain_shapes.py`.
`plain_value`, dtype/index/frame validation and the encoders require a row in
that table. `tests/gol_plain_shape_cases.py` generates recipes for every row; a
new row without a recipe fails collection. Each recipe checks exact frame/type
round-trip and ordinary analysis results through both the trusted reference and
real Linux child. This includes fixed-offset names/UTC identity, aware object
cells and Timestamp units/fold, timezone/frequency-bearing indices, timedelta,
Decimal, categorical metadata, nullable dtypes, MultiIndex, empty frames and
mixed null kinds. All existing ordinary analyses remain in the process corpus.

Both paths validate frames and plain results. Native timedelta identity,
datetime/timedelta units, timezone, category, index frequency and multi-level
metadata are preserved. Custom index frequencies that cannot be represented by
the canonical frequency string are refused by both paths. Supported timezones
are exact cached standard `ZoneInfo` directory entries and `datetime.timezone` offsets
in whole minutes, with arbitrary plain names preserved. Other timezone
implementations, uncached/file-loaded zone objects and sub-minute offsets are
refused by shared validation. A file-loaded zone's key need not identify its
rules; only canonical cached entries can be reconstructed by key. Pandas
cannot consistently reconstruct their Timestamp/typed-column semantics. String
extension storage must be Python, with either NA or NaN missing semantics; other
storage and extension dtypes refuse in both paths. Integer values are limited
to 14,000 bits so both result JSON parsers can carry them within their native
decimal-digit bound. Nonfinite dictionary keys are refused because NaN key
identity cannot be preserved by plain data; missing/nonfinite values in cells
and lists remain supported. Input limits apply to
actual encoded bytes (128 MiB) and cells (16 million), rather than deep object
memory for unreferenced tables. The output cap is 2 MiB; the parent checks the
DTO and existing `plain_value` validator. The existing 100-row/result-value limits
still apply. Tests compare the full ordinary-analysis corpus and extended dtype,
index and temporal shapes against the trusted in-process reference.

Linux requires Landlock ABI 3 or later and libseccomp. Landlock grants reads only
below the disposable working directory and denies filesystem writes, creation,
execution and truncation. Default-deny seccomp admits resident computation and
pipe syscalls, while denying sockets/network, process/thread creation, exec,
other-process signalling and memory access, namespaces and resource-limit
changes. The bootstrap must have one thread; seccomp uses thread synchronization.
`no_new_privs` makes restrictions irreversible. Metadata calls remain available
but do not permit file contents. The image installs `libseccomp2` and runs as the
non-root `app` user; these policies need no additional container capabilities on
a supporting host/runtime. See [Landlock](https://www.kernel.org/doc/html/latest/userspace-api/landlock.html)
and [seccomp](https://man7.org/linux/man-pages/man2/seccomp.2.html).

Children have a 10-second hard CPU limit, zero file/core size, zero process
allowance and niceness +10. The parent allows 10 seconds for bootstrap, followed
by 10 seconds for transfer, reconstruction, execution and formatting. At wall,
RSS or output limits it sends SIGKILL and waits. RSS is sampled every 25 ms and
may briefly overshoot; Linux also enforces an address-space limit. Parent death
causes an unmaskable SIGKILL, with an expected-parent recheck during setup. An
independent 20-second backup alarm bounds interrupted supervision; policy denies
changing handlers, masks and timers after installation. These controls are tested
with first-layer guards deliberately bypassed inside test-owned workers only.

One analysis/serialization at a time is admitted across container workers using
an owned regular mode-0600 advisory-lock file opened without following symlinks.
It waits at most 10 seconds. Admission precedes database frame loading and cache
copies; the owned lock file stays in the temporary directory to preserve identity.
It contains only a bounded monotonic timestamp and policy-ready bit, written by
the supervisor while holding admission; children cannot access its contents.
Maintenance is rechecked at admission and input boundaries. Every child is
single-use across all requests/users. Startup measurements do not justify a pool.

Before loading frames and again before starting a child, the parent checks Linux
MemAvailable and cgroup remaining memory. It reserves 128 MiB for the parent and
other requests. The child address-space cap is at most 768 MiB and never exceeds
remaining memory minus that reserve; below 384 MiB it refuses. Its RSS cap is at
most 448 MiB and at least 128 MiB below the assigned address-space cap. Bootstrap
raises the child's OOM score preference to 500. These checks bound admission;
they do not reserve memory against unrelated allocations in other application
threads. Larger real caches or concurrent non-analysis requests can still require
more container memory. Use measured application headroom, not just child RSS.

Availability uses a PID-scoped real-policy self-test with `result=1`, cached for
10 minutes. Every child READY refreshes evidence after mandatory policy installs;
a cold worker can use recent trusted evidence from the container admission file.
Only definite setup/handshake failure pauses readiness for 60 seconds. Contention,
headroom, startup deadlines and unexpected child exits preserve previous policy
proof and retry after one second. Without prior proof they remain unavailable
with an unknown state and short retry; every actual analysis still installs the
full policy before input. Loader and output-validation errors remain neutral
per-analysis errors and do not revoke readiness. Headroom/slot refusals ask for a
later retry, while child memory/input size refusals ask to reduce the data scope.
The maintenance switch or missing provider key short-circuits before any probe.
Missing policy support produces a WARNING with fixed `bootstrap_failed` reason
and pauses the assistant before a new debit.

`/api/health` reads only cached in-memory state and never probes, loads data or
waits for admission. `analysis_isolation_state` distinguishes `available`,
`unavailable`, `unknown` (cold/expired/transient) and `unsupported`;
`analysis_isolation_available` is true only for available. Separate
`assistant_maintenance_enabled` and `assistant_provider_configured` booleans
report the other pause reasons without exposing credentials. Backend liveness
remains healthy. A trusted operator can independently test policy while the
maintenance switch stays ON, from `/app` inside the intended Linux revision:

```sh
python -c 'from src.services.gol_isolation import isolation_ready; ok=isolation_ready(); print("analysis_policy_ready="+str(ok)); raise SystemExit(0 if ok else 1)'
```

This command deliberately starts a policy probe (or uses recent shared evidence),
independent of provider credentials and maintenance; run it through the existing
trusted container console. This lane does not access or change production.
Fixed logs distinguish `bootstrap_failed`, `deadline`, `memory`, `busy`,
`input_size`, `bad_output`, `child_exit`, `input_validation`, `loader_failed`,
`analysis_failed` and `headroom`; bootstrap/headroom/input size failures are
WARNINGs. Size logs include measured bytes/cells and limits. Success logs include
timing, sampled RSS and wire sizes. No code, frame values or raw child diagnostics
are logged. Alert on any `input_size` warning and on successful `input_bytes`
approaching 75% of 128 MiB; trend this alongside selected table rows, cache memory,
headroom and resource refusals. The synthetic 29-column fixture table reaches
the wire cap near 500k rows; real text lengths can reach it earlier. Revisit
capacity before doubling the measured 200k-row envelope rather than raising the
cap without application-memory measurements.

The five-minute table cache is not a transactionally consistent database snapshot:
partial loads later in that window can have different observation times. Helpers
receive their entire dependency set together, but reads may combine cached tables
of different ages. Current public-adult eligibility is rechecked on every read.
A transaction-consistent analytical snapshot is separate data-loader work.

Normal supervisors kill and wait for children in `finally`. After supervisor
death, the mandatory parent-death signal kills the child; its adopting process
must reap it. The Docker exec-form command runs Gunicorn as PID1, whose arbiter
reaps unknown adopted children. Preserve that exec form. A deployment wrapper
that interposes a shell must use `exec` or an init/subreaper; otherwise a dead
child can remain a zombie until container exit. Linux regressions exercise both
parent death and Gunicorn's real unknown-child reaper.

Azure Container Apps kernel support is UNCONFIRMED by local work. Before resuming
the assistant, verify the real non-root revision passes readiness and an ordinary
stored analysis. Unsupported host kernels or outer runtime restrictions pause
analysis; there is no reduced policy. No privileged containers or network/mount
namespaces are requested. The stronger infrastructure option is a separate
credential-free job/container with supplied frames, a dedicated resource budget
and independently enforced deny-all egress. The current implementation shares
the application's host kernel and depends on its security and availability.

Run `python scripts/benchmark_gol_isolation.py --rows 100000 200000 --repeats 3`
in Linux for real loader-schema synthetic frames, including the 29-column table,
without database access. At 0.5 CPU / 1 GiB, current median bootstrap is 299/308 ms,
serialization 177/221 ms, and end-to-end 718/1000 ms for 100k/200k rows. Child peak
RSS is approximately 108/133 MiB for that workload. The full-app measurement
`python scripts/benchmark_gol_application.py --rows 200000` preloads Flask and
runs two workers with two concurrent requests each under the same container
limits; both workers first verify the rows/columns of an ordinary stored-table
read, then it asserts no OOM, no worker loss and bounded total memory. Every
pressure response must be a success or a fixed deadline/busy/size refusal; a
slower host can reach the hard deadline on every large row-wise call. It uses synthetic eligibility/frames and no database/provider calls. Add
`--warm-caches` to populate all ten frame caches in both workers first. That
pressure case peaked near 795 MiB locally: one analysis completed, two reached
the reduced RSS budget and one received busy, with no container OOM or worker
loss. The successful/refused mix varies with workload scheduling.

The mandatory Linux Backend Tests job exercises real policy failures, signalling,
immutable deadlines, parent death, CPU/memory limits, parity and cleanup. Any skip
in either isolation test module fails the Linux job. Analysis Container Memory
builds the production image and exercises the full-application memory envelope on
Linux x86_64. Local Linux measurements use aarch64. macOS runs the trusted corpus
and tests explicit runtime refusal; its real-policy tests are intentionally Linux
only. Watch fixed refusal reasons, readiness/health, queue waits, child/container
RSS, OOM events and cache size before changing resource settings or dependencies.

## Maintenance switch for the assistant

For operational control, set `GOL_MAINTENANCE=true` on the backend container environment to pause the assistant; set it to `false` or remove it to resume. No code deploy is needed after this release; the container must restart with the updated environment (an environment update may create a new container revision). The flag is read at request time. Values `1`, `true`, `yes`, and `on` enable it, ignoring surrounding whitespace and case; unset and unrecognised values mean OFF, matching other feature flags. The selected provider must also have a nonblank configured credential before the assistant resumes.

Chat returns HTTP 503 with `error: maintenance`, `retryable: true`, `Retry-After: 60`, and `Cache-Control: no-store`, before constructing a provider client. Fresh questions write no rows. Previously debited questions for the same account and client message ID retain the existing reservation path: completed answers replay, live leases return `in_flight`, and stale leases are reclaimed and refunded. Web users see “The assistant is under maintenance. Back soon.” inside the conversation with sending disabled; the launcher and displayed balances remain available. The existing suggestions read returns an empty list plus the same maintenance state, adding no requests to `/api/features`. The web rechecks availability when the panel opens or when “Check availability” is selected, respecting the retry deadline. Clear resets the conversation and maintenance state and checks again. A persistent polite live region announces maintenance and describes the disabled input; submitted questions keep their retry identity. The browser regression spec runs in CI through `playwright.uxb.config.js`. Saved transcript PDF export and the authenticated admin cache-refresh endpoint remain available; neither needs the model provider. Authentication and rate limits still apply.

The current iOS app displays “GOL is temporarily unavailable. Please try again.” below the conversation, with a “Retry answer” button and sending still enabled. It keeps the submitted question and an empty assistant turn, without changing balances. Suggestions are empty. The next iOS round should map HTTP 503 with `error: maintenance` to the maintenance copy, disable sending while that state is active, and provide a way to recheck availability. No iOS code changes are included here.
