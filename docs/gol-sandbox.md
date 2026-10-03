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

`execute_analysis` supervises a new Python interpreter for every call. The
RestrictedPython capability guards remain the first layer inside that interpreter.
The synchronous executor, frame checks and result formatter run only after the
worker has installed its mandatory OS policy. There is no in-process fallback.
The worker imports analysis modules and the standard library, without importing
Flask, the application, models, provider clients or database services. Native BLAS
threads are disabled during the trusted bootstrap. Named timezone data and the
required lazy NumPy/pandas modules are loaded before filesystem restrictions.

The parent launches with `env={}`, isolated Python settings (`-I -B`), closed
inherited descriptors and three pipes. Bootstrap uses fixed thread settings and
clears its environment before accepting input. Each call has its own empty
temporary working directory, removed after the child has been killed/reaped.
No analysis input or output is written to a file. The transport is versioned JSON:
fixed numeric dtypes use base64 little-endian buffers, strings use dictionary
encoding, and object values use a fixed set of plain-data tags. It never uses
pickle or imports types named by the payload. Numeric buffers cannot carry
executable objects. Frame dtype/index/category checks run before encoding and
after reconstruction. The input cap is 128 MiB and 16 million resident cells,
with an additional 128 MiB deep frame-memory budget before serialization. The
output cap is 2 MiB; the parent checks the DTO shape and reuses `plain_value`.
The existing 100-row and result-value limits still apply.

Linux requires Landlock ABI 3 or later and libseccomp. Landlock permits file and
directory reads only below the disposable working directory; filesystem writes,
execution, creation and truncation are denied. A default-deny seccomp filter
allows the syscalls needed for resident analysis and pipes, while denying socket
creation, network operations, process/thread creation, exec, other-process memory
access, namespace changes and resource-limit changes. The bootstrap must have
one thread before Landlock is installed; seccomp also requires thread
synchronization. `no_new_privs` makes these restrictions irreversible. Linux
filesystem metadata calls remain available; they do not grant file contents.
The Docker image installs `libseccomp2` and runs as the existing non-root `app`
user. Landlock and seccomp can be installed without additional capabilities when
the host kernel/runtime supports them. See the [Linux Landlock documentation](https://www.kernel.org/doc/html/latest/userspace-api/landlock.html)
and [seccomp API](https://man7.org/linux/man-pages/man2/seccomp.2.html).

macOS requires a Seatbelt policy: external file reads, all filesystem writes,
network operations, process creation/exec, process information, Mach operations
and named POSIX/System V IPC are denied. This uses the deprecated local
`sandbox_init` interface; if a future macOS release cannot install it, analysis
refuses. The Linux syscall allowlist and address-space limit are Linux-specific.

Every child has a 10-second hard CPU limit, zero file/core size and niceness +10.
Linux also has a 768 MiB address-space limit and zero process allowance. The
parent samples RSS and kills above 448 MiB on Linux or 640 MiB on macOS (which
has higher measured native allocator overhead). It allows up to
10 seconds for bootstrap, then 10 seconds for transfer, reconstruction, execution
and formatting. Expiry, excessive RSS/output, crashes and invalid output produce
the existing neutral refusal. The parent sends SIGKILL to its owned process
group and waits; it never relies on thread cancellation. RSS sampling runs every
25 ms and is a secondary guard; it can briefly overshoot between samples.
Linux additionally binds the child to its creating parent with an unmaskable
parent-death SIGKILL and rechecks the expected parent PID during setup. A
secondary 20-second child alarm bounds interrupted supervision on both systems;
Linux also blocks changing signal handlers/masks/timers after policy setup.

One analysis/serialization at a time is admitted across Gunicorn workers in the
container using an advisory file lock. Admission waits at most 30 seconds; a
full queue refuses. The lock is owned by the application user, mode 0600, opened
without following symlinks, and released by closing its descriptor. Its empty
file stays in the container's temporary directory to preserve lock identity.
Every admitted request gets a distinct single-use child. Maintenance is checked
before admission, after admission and after serialization; the service also
retains its early maintenance check. There is no worker pool or reuse between
users. Logs include bootstrap/elapsed time, peak sampled child RSS and transport
byte counts; they contain no code, frame values or child exception messages.

Azure Container Apps host kernel support has not been verified by local tests.
Before release, the operator must confirm a normal stored analysis works on the
actual non-root image with Landlock and seccomp installed. Unsupported kernels,
outer runtime restrictions or missing libraries leave the analysis tool refusing;
they never reduce its isolation. This implementation requests neither privileged
containers nor network/mount namespaces. Container-wide memory includes the
Flask workers, cached frames, pending request frames and serialization buffers;
the per-child limits do not reserve memory for the rest of the application.
Watch neutral refusal rates, bootstrap/time/RSS logs, admission wait, container
RSS/OOM events and health-probe latency. Keep adequate measured headroom before
resuming the assistant. A stronger infrastructure option is a separate
credential-free analysis job/container with only supplied frames, a dedicated
resource budget and independently enforced deny-all egress. This separates the
application's filesystem and credentials; stronger kernel separation would
require an infrastructure runtime that supplies it.

Run `python scripts/benchmark_gol_isolation.py --rows 100000 200000 --repeats 3`
for synthetic data with all ten real loader schemas, including the 29-column
fixture table. It reads repository SQL schemas only and never connects to a DB.
The hand-back records measurements on macOS and a non-root Linux container
limited to 0.5 CPU / 1 GiB. Linux policy/resource tests run in the existing
mandatory Backend Tests CI job; the same corpus also covers macOS locally.

## Maintenance switch for the assistant

For operational control, set `GOL_MAINTENANCE=true` on the backend container environment to pause the assistant; set it to `false` or remove it to resume. No code deploy is needed after this release; the container must restart with the updated environment (an environment update may create a new container revision). The flag is read at request time. Values `1`, `true`, `yes`, and `on` enable it, ignoring surrounding whitespace and case; unset and unrecognised values mean OFF, matching other feature flags. The selected provider must also have a nonblank configured credential before the assistant resumes.

Chat returns HTTP 503 with `error: maintenance`, `retryable: true`, `Retry-After: 60`, and `Cache-Control: no-store`, before constructing a provider client. Fresh questions write no rows. Previously debited questions for the same account and client message ID retain the existing reservation path: completed answers replay, live leases return `in_flight`, and stale leases are reclaimed and refunded. Web users see “The assistant is under maintenance. Back soon.” inside the conversation with sending disabled; the launcher and displayed balances remain available. The existing suggestions read returns an empty list plus the same maintenance state, adding no requests to `/api/features`. The web rechecks availability when the panel opens or when “Check availability” is selected, respecting the retry deadline. Clear resets the conversation and maintenance state and checks again. A persistent polite live region announces maintenance and describes the disabled input; submitted questions keep their retry identity. The browser regression spec runs in CI through `playwright.uxb.config.js`. Saved transcript PDF export and the authenticated admin cache-refresh endpoint remain available; neither needs the model provider. Authentication and rate limits still apply.

The current iOS app displays “GOL is temporarily unavailable. Please try again.” below the conversation, with a “Retry answer” button and sending still enabled. It keeps the submitted question and an empty assistant turn, without changing balances. Suggestions are empty. The next iOS round should map HTTP 503 with `error: maintenance` to the maintenance copy, disable sending while that state is active, and provide a way to recheck availability. No iOS code changes are included here.
