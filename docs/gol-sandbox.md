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
functions; their string dispatch is limited to statistical reductions; transform also permits an explicit list of in-memory transforms. This also
covers nested dictionaries/lists, named aggregates with a missing or explicit
`None` function, and positional or keyword pivot/crosstab reducers. Engine/parser arguments are unavailable, including positional engines. All callables obtainable from the boundary are restricted
functions, chosen safe builtins/constructors, wrapped in-memory operations or
scalar-argument stored-data helpers; reflection on them is refused.

Item, iterator/unpacking, write and augmented-assignment guards restrict receiver
kinds. Attribute writes permit only validated DataFrame labels and Series
labels/name. Input cells/labels/metadata must contain plain data. Pandas 3 copy-on-write isolates table mutations without another deep data copy; nested object containers are still cloned. Helpers never fall back to a DB/API name
resolver. New library capabilities require compatibility and escape tests.

The result must be an exact DataFrame/Series or approved scalar/list/tuple/dict.
Cells, labels, index and metadata are recursively validated before row conversion
or JSON. Unknown objects, subclasses, callables, cycles and unsafe nested values
are refused without calling representation/serialization hooks. Even omitted rows are validated by dtype or object-cell checks. Interval and Period values render as text. Existing column/index labels support attribute access through the guarded item operation, with approved methods taking precedence. String extension arrays support guarded iteration/items and in-memory list/numpy conversion. Existing numeric display/rounding is preserved; date cells
now serialize as ISO strings with their offsets, missing/nonfinite values as null.
Errors never echo rejected values, compiler details or exception text.

## Limits and remaining risk

Preparation, execution and formatting share the existing 10-second thread wait.
Code is limited to 20,000 characters and 4,000 AST nodes; restricted Python frames
have a 3,000,000 trace-event budget and deadline check. Imports/classes/async code,
bare exception handlers and `finally` clauses are refused. Rendered output has a shared 20,000-value budget, depth20 and a 10,000-character limit per string (including dictionary keys); tables still truncate to100 rows with `truncated: true`. Typed columns and indexes are validated by dtype; only object columns/indexes and categorical labels need Python value checks, including omitted rows. Common numpy shape
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
work retains the thread-isolation limitation described above.

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

## Maintenance switch for the assistant

For operational control, set `GOL_MAINTENANCE=true` on the backend container environment to pause the assistant; set it to `false` or remove it to resume. No code deploy is needed after this release; the container must restart with the updated environment (an environment update may create a new container revision). The flag is read at request time. Values `1`, `true`, `yes`, and `on` enable it, ignoring surrounding whitespace and case; unset and unrecognised values mean OFF, matching other feature flags. The selected provider must also have a nonblank configured credential before the assistant resumes.

Chat returns HTTP 503 with `error: maintenance`, `retryable: true`, `Retry-After: 60`, and `Cache-Control: no-store`, before constructing a provider client. Fresh questions write no rows. Previously debited questions for the same account and client message ID retain the existing reservation path: completed answers replay, live leases return `in_flight`, and stale leases are reclaimed and refunded. Web users see “The assistant is under maintenance. Back soon.” inside the conversation with sending disabled; the launcher and displayed balances remain available. The existing suggestions read returns an empty list plus the same maintenance state, adding no requests to `/api/features`. The web rechecks availability when the panel opens or when “Check availability” is selected, respecting the retry deadline. Clear resets the conversation and maintenance state and checks again. A persistent polite live region announces maintenance and describes the disabled input; submitted questions keep their retry identity. The browser regression spec runs in CI through `playwright.uxb.config.js`. Saved transcript PDF export and the authenticated admin cache-refresh endpoint remain available; neither needs the model provider. Authentication and rate limits still apply.

The current iOS app displays “GOL is temporarily unavailable. Please try again.” below the conversation, with a “Retry answer” button and sending still enabled. It keeps the submitted question and an empty assistant turn, without changing balances. Suggestions are empty. The next iOS round should map HTTP 503 with `error: maintenance` to the maintenance copy, disable sending while that state is active, and provide a way to recheck availability. No iOS code changes are included here.
