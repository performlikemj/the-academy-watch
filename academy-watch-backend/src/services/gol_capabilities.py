"""Capabilities for model-written GOL analyses, never raw library namespaces.

RestrictedPython rewrites Python attribute access, but libraries can dispatch
methods themselves (notably pandas aggregation strings). Both boundaries need
positive allowlists. This is an in-process capability boundary, not OS isolation.
"""

import builtins
import inspect
import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from types import FunctionType, GeneratorType, ModuleType

import numpy as np
import pandas as pd
from pandas.core.groupby.generic import DataFrameGroupBy, SeriesGroupBy
from pandas.core.indexes.accessors import DatetimeProperties, PeriodProperties, TimedeltaProperties
from pandas.core.indexing import _AtIndexer, _iAtIndexer, _iLocIndexer, _LocIndexer
from pandas.core.strings.accessor import StringMethods
from pandas.core.window import Expanding, Rolling
from RestrictedPython.Guards import safer_getattr
from src.services.gol_plain_shapes import (
    FRAME_SHAPES,
    INDEX_SHAPES,
    TIMEZONE_NAMES,
    VALUE_SHAPES,
    canonical_frequency,
    canonical_timestamp,
    dtype_shape,
    timezone_shape,
)

ERROR = "Analysis refused: unsupported operation or result."
MAX_ARRAY_CELLS = 1_000_000
MAX_VALUE_ITEMS = 20_000
MAX_VALUE_DEPTH = 20
MAX_STRING_CHARS = 10_000
SIZE_ERROR = "Analysis exceeded its size limit."


class AnalysisSizeLimit(ValueError):
    """A fixed size failure, separate from unsupported operations."""


class AnalysisRefused(ValueError):
    """Neutral failure; never include the rejected object or exception text."""


def _names(names):
    return names.split()


# Deliberately do not inherit safe_builtins: it includes class construction,
# setattr/delattr, and version-dependent additions. No introspection or imports.
BUILTIN_NAMES = _names(
    "abs pow divmod ord chr all any bool dict enumerate filter float int isinstance len list map max min range round set slice sorted str sum tuple zip Exception ValueError TypeError KeyError IndexError ZeroDivisionError"
)
ALLOWED_BUILTINS = {name: getattr(builtins, name) for name in BUILTIN_NAMES}

PANDAS_NAMES = _names(
    "DataFrame Series concat merge to_numeric to_datetime to_timedelta cut qcut isna notna NA NaT Timestamp Timedelta pivot_table crosstab unique isnull notnull melt get_dummies date_range DateOffset NamedAgg Index Categorical"
)
NUMPY_NAMES = _names(
    "array asarray arange linspace zeros ones full abs absolute sqrt log log2 log10 exp expm1 log1p square power sign floor ceil trunc round around clip minimum maximum sum mean median std var min max nanmean nanmedian nanstd nanvar nansum nanmin nanmax percentile quantile nanpercentile nanquantile count_nonzero cumsum cumprod where select isnan isfinite isinf logical_and logical_or logical_not sort argsort unique concatenate stack hstack vstack dot int32 int64 float32 float64 bool_ nan inf pi e average diff any all argmax argmin isin nan_to_num divide corrcoef prod"
)

AGGREGATIONS = frozenset(
    _names(
        "all any count size sum mean median min max std var prod first last nunique idxmin idxmax quantile sem skew kurt cumsum cumprod cummin cummax"
    )
)
FRAME_METHODS = frozenset(
    _names(
        "head tail copy get iterrows itertuples to_dict to_numpy isin isna notna isnull notnull fillna dropna replace astype sort_values sort_index nlargest nsmallest drop drop_duplicates duplicated rename rename_axis reset_index set_index reindex reindex_like merge join groupby pivot pivot_table melt stack unstack transpose squeeze round abs clip add sub mul div truediv floordiv mod pow eq ne lt le gt ge sum mean median min max std var prod count nunique all any idxmin idxmax quantile describe corr cov rank diff pct_change shift cumsum cumprod cummin cummax value_counts mode select_dtypes apply map applymap agg aggregate transform pipe assign explode where mask rolling expanding ffill bfill insert sample filter skew kurt combine_first keys add_prefix"
    )
)
SERIES_METHODS = FRAME_METHODS | frozenset(
    _names("tolist to_list to_numpy unique between nlargest nsmallest items keys repeat to_frame argmax argmin dot")
)
INDEX_METHODS = frozenset(
    _names(
        "tolist to_list to_numpy unique nunique isin isna notna dropna fillna astype copy sort_values drop drop_duplicates duplicated get_level_values droplevel min max argmin argmax value_counts map rename get_loc difference"
    )
)
ARRAY_METHODS = frozenset(
    _names(
        "tolist item astype copy reshape flatten ravel transpose squeeze sum mean min max std var prod all any argmin argmax argsort sort round clip cumsum cumprod"
    )
)
GROUP_METHODS = AGGREGATIONS | frozenset(
    _names(
        "agg aggregate apply transform filter head tail get_group rank diff shift value_counts cumcount nth ffill bfill"
    )
)
STRING_METHODS = frozenset(
    _names(
        "contains startswith endswith lower upper casefold title capitalize strip lstrip rstrip replace split rsplit partition rpartition len get slice slice_replace find rfind count match fullmatch extract extractall normalize pad zfill cat join repeat isalpha isdigit isnumeric isalnum isspace findall isupper islower removeprefix removesuffix"
    )
)
DATE_ATTRS = frozenset(
    _names(
        "weekday year month day hour minute second microsecond nanosecond dayofweek day_of_week dayofyear day_of_year quarter days_in_month daysinmonth is_month_start is_month_end is_quarter_start is_quarter_end is_year_start is_year_end is_leap_year date time days seconds total_seconds"
    )
)
DATE_METHODS = frozenset(
    _names("strftime floor ceil round normalize month_name day_name isocalendar to_period tz_localize tz_convert")
)
TRANSFORMS = AGGREGATIONS | frozenset(_names("rank diff shift pct_change ffill bfill cumcount"))
WINDOW_METHODS = frozenset(
    _names("sum mean median min max std var count quantile sem skew kurt corr cov agg aggregate apply")
)
EXTENSION_ARRAY_TYPES = (
    pd.arrays.StringArray,
    pd.arrays.ArrowStringArray,
    pd.arrays.Categorical,
    pd.arrays.DatetimeArray,
    pd.arrays.TimedeltaArray,
    pd.arrays.PeriodArray,
    pd.arrays.IntervalArray,
    pd.arrays.IntegerArray,
    pd.arrays.FloatingArray,
    pd.arrays.BooleanArray,
)
INDEXERS = (_LocIndexer, _iLocIndexer, _AtIndexer, _iAtIndexer)


class Facade:
    """Immutable namespace. Only guarded_getattr can expose its capabilities."""

    __slots__ = ("_entries", "_call")

    def __init__(self, entries, call=None):
        self._entries = entries
        self._call = call

    def __call__(self, *args, **kwargs):
        if self._call is None:
            raise AnalysisRefused(ERROR)
        return self._call(*args, **kwargs)


def _check_dispatch(spec, depth=0, allowed=AGGREGATIONS):
    """Pandas dispatch strings must name statistical reductions, not methods."""
    if depth > MAX_VALUE_DEPTH:
        raise AnalysisRefused(ERROR)
    if isinstance(spec, str):
        if spec not in allowed:
            raise AnalysisRefused(ERROR)
    elif type(spec) is dict:
        for value in spec.values():
            _check_dispatch(value, depth + 1, allowed)
    elif type(spec) in (list, tuple):
        for value in spec:
            _check_dispatch(value, depth + 1, allowed)
    elif not callable(spec) and spec is not None:
        raise AnalysisRefused(ERROR)


def _bounded_shape(shape):
    dimensions = shape if type(shape) in (tuple, list) else (shape,)
    if not all(type(d) is int and 0 <= d <= MAX_ARRAY_CELLS for d in dimensions):
        raise AnalysisSizeLimit(SIZE_ERROR)
    if math.prod(dimensions) > MAX_ARRAY_CELLS:
        raise AnalysisSizeLimit(SIZE_ERROR)


@lru_cache(maxsize=256)
def _function_signature(function, bound):
    signature = inspect.signature(function)
    if bound:
        signature = signature.replace(parameters=list(signature.parameters.values())[1:])
    return signature


def _signature(func):
    function = getattr(func, "__func__", func)
    if type(function) is FunctionType:
        return _function_signature(function, function is not func)
    return inspect.signature(func)


def _safe_call(func, name):
    def call(*args, **kwargs):
        # A callable engine can run outside the restricted compiler. Only the
        # normal pandas implementation is permitted; numba/string eval are out.
        if "engine" in kwargs or "engine_kwargs" in kwargs or "parser" in kwargs:
            raise AnalysisRefused(ERROR)
        if args and name in {
            "apply",
            "map",
            "sum",
            "mean",
            "median",
            "min",
            "max",
            "std",
            "var",
            "transform",
            "aggregate",
            "agg",
        }:
            try:
                bound = _signature(func).bind_partial(*args, **kwargs).arguments
            except ValueError:
                bound = {}
            if "engine" in bound or "engine_kwargs" in bound or "parser" in bound:
                raise AnalysisRefused(ERROR)
        if name in {"agg", "aggregate", "apply", "transform", "pivot_table", "crosstab"}:
            if args and name not in {"pivot_table", "crosstab"}:
                _check_dispatch(args[0], allowed=TRANSFORMS if name == "transform" else AGGREGATIONS)
            if name in {"pivot_table", "crosstab"}:
                spec = _signature(func).bind_partial(*args, **kwargs).arguments.get("aggfunc")
                _check_dispatch(spec)
            if "func" in kwargs:
                _check_dispatch(kwargs["func"], allowed=TRANSFORMS if name == "transform" else AGGREGATIONS)
            # Named aggregations: labels/columns are data, only check reducer.
            if name in {"agg", "aggregate"} and (args[0] if args else kwargs.get("func")) is None:
                for label, spec in kwargs.items():
                    if label == "func":
                        continue
                    if type(spec) is pd.NamedAgg:
                        _check_dispatch(spec.aggfunc)
                    elif type(spec) is tuple and len(spec) == 2:
                        _check_dispatch(spec[1])
                    else:
                        _check_dispatch(spec)
        if name in {"Timestamp", "now", "date_range", "tz_localize", "tz_convert"}:
            bound = _signature(func).bind_partial(*args, **kwargs).arguments
            # Pandas accepts dateutil timezone strings that can open arbitrary
            # tzfiles. Only named zones from its packaged timezone directory.
            for key in ("tz", "tzinfo"):
                zone = bound.get(key)
                if zone is not None and (type(zone) is not str or zone not in TIMEZONE_NAMES):
                    raise AnalysisRefused(ERROR)
        if name in {"array", "asarray", "arange", "zeros", "ones", "full", "linspace"}:
            dtype = kwargs.get("dtype")
            dtype_position = {"array": 1, "asarray": 1, "zeros": 1, "ones": 1, "full": 2}.get(name)
            if dtype_position is not None and len(args) > dtype_position:
                dtype = args[dtype_position]
            if dtype is not None and np.dtype(dtype).itemsize > 16:
                raise AnalysisSizeLimit(SIZE_ERROR)
        if name in {"zeros", "ones", "full", "reshape"}:
            shape = args[0] if args else kwargs.get("shape")
            if name == "reshape":
                shape = args if len(args) > 1 else (args[0] if args else kwargs.get("shape", kwargs.get("newshape")))
                # One inferred dimension is normal in reshaping existing data.
                if type(shape) in (list, tuple) and -1 in shape:
                    shape = [1 if d == -1 else d for d in shape]
            _bounded_shape(shape)
        if name == "arange":
            # Bound before allocation; invalid signatures fail neutrally below.
            start, stop = (0, args[0]) if len(args) == 1 else args[:2]
            step = args[2] if len(args) > 2 else kwargs.get("step", 1)
            if not step:
                raise AnalysisRefused(ERROR)
            if abs((stop - start) / step) > MAX_ARRAY_CELLS:
                raise AnalysisSizeLimit(SIZE_ERROR)
        if name == "linspace" and (args[2] if len(args) > 2 else kwargs.get("num", 50)) > MAX_ARRAY_CELLS:
            raise AnalysisSizeLimit(SIZE_ERROR)
        return _check_reachable(func(*args, **kwargs))

    return call


def library_facades():
    def facade(module, names):
        return Facade(
            {
                name: _safe_call(getattr(module, name), name)
                if callable(getattr(module, name))
                and (name == "Timestamp" or not isinstance(getattr(module, name), type))
                else getattr(module, name)
                for name in names
            }
        )

    pandas = facade(pd, PANDAS_NAMES)
    pandas._entries["Timestamp"] = Facade(
        {"now": _safe_call(pd.Timestamp.now, "now")}, _safe_call(pd.Timestamp, "Timestamp")
    )
    return pandas, facade(np, NUMPY_NAMES)


def _check_reachable(value):
    if isinstance(value, ModuleType):
        raise AnalysisRefused(ERROR)
    return value


def guarded_getattr(obj, name, default=None):
    # Check BEFORE getattr: a property can create a Styler/accessor or perform
    # work before its returned type is checked. Unknown receiver types fail shut.
    if type(name) is not str or name.startswith("_"):
        raise AnalysisRefused(ERROR)
    if type(obj) is Facade:
        if name not in obj._entries:
            raise AnalysisRefused(ERROR)
        return _check_reachable(obj._entries[name])

    methods = frozenset()
    attrs = frozenset()
    if type(obj) is pd.DataFrame:
        methods = FRAME_METHODS
        attrs = frozenset(_names("columns index shape size ndim empty dtypes values T loc iloc at iat"))
    elif type(obj) is pd.Series:
        methods = SERIES_METHODS
        attrs = frozenset(_names("index name shape size ndim empty dtype values T loc iloc at iat str dt"))
    elif isinstance(obj, pd.Index):
        methods = INDEX_METHODS
        attrs = frozenset(_names("name names shape size ndim empty dtype values str"))
        if type(obj) is pd.DatetimeIndex:
            attrs = attrs | DATE_ATTRS
            methods = methods | DATE_METHODS
    elif type(obj) in EXTENSION_ARRAY_TYPES:
        methods = frozenset({"tolist", "to_numpy"})
    elif type(obj) in (Rolling, Expanding):
        methods = WINDOW_METHODS
    elif type(obj) is np.ndarray:
        methods = ARRAY_METHODS
        attrs = frozenset(["shape", "size", "ndim", "dtype", "T"])
    elif type(obj) in (DataFrameGroupBy, SeriesGroupBy):
        methods = GROUP_METHODS
        attrs = frozenset({"ngroups", "groups", "indices"})
    elif type(obj) is StringMethods:
        methods = STRING_METHODS
    elif type(obj) in (DatetimeProperties, TimedeltaProperties, PeriodProperties):
        methods = DATE_METHODS
        attrs = DATE_ATTRS
    elif type(obj) in (pd.Timestamp, pd.Timedelta, datetime, date, timedelta):
        methods = DATE_METHODS | frozenset({"isoformat", "total_seconds"})
        attrs = DATE_ATTRS
    elif isinstance(obj, np.dtype):
        attrs = frozenset({"name", "kind", "itemsize"})
    elif type(obj) is str:
        methods = STRING_METHODS | frozenset({"join", "splitlines", "index", "rindex", "center", "ljust"})
    elif isinstance(obj, tuple) and type(obj).__module__ == "pandas.core.frame" and hasattr(type(obj), "_fields"):
        attrs = frozenset(type(obj)._fields)
    elif type(obj) in (list, tuple):
        methods = frozenset(_names("append extend insert pop remove clear copy count index reverse sort"))
    elif type(obj) is dict:
        methods = frozenset(_names("get items keys values copy update pop setdefault clear"))
    elif type(obj) is set:
        methods = frozenset(_names("add discard remove union intersection difference copy update issubset"))
    elif isinstance(obj, (int, float, np.number)):
        methods = frozenset({"item"}) if isinstance(obj, np.generic) else frozenset()
        attrs = frozenset({"real", "imag"})
    if name not in methods and name not in attrs:
        if type(obj) is pd.DataFrame and name in obj.columns:
            return guarded_getitem(obj, name)
        if type(obj) is pd.Series and name in obj.index:
            return guarded_getitem(obj, name)
        if type(obj) is DataFrameGroupBy and name in obj.obj.columns:
            return guarded_getitem(obj, name)
        raise AnalysisRefused(ERROR)
    value = _check_reachable(safer_getattr(obj, name, default))
    if name in {"names", "groups", "indices"}:
        value = dict(value) if isinstance(value, dict) else list(value)
    return _safe_call(value, name) if name in methods and callable(value) else value


def guarded_getitem(obj, key):
    if not (
        type(obj)
        in (
            dict,
            list,
            tuple,
            str,
            np.ndarray,
            pd.DataFrame,
            pd.Series,
            *INDEXERS,
            DataFrameGroupBy,
            SeriesGroupBy,
            StringMethods,
        )
        or isinstance(obj, pd.Index)
        or type(obj) in EXTENSION_ARRAY_TYPES
        or (
            type(obj) is tuple
            or (
                isinstance(obj, tuple) and type(obj).__module__ == "pandas.core.frame" and hasattr(type(obj), "_fields")
            )
        )
    ):
        raise AnalysisRefused(ERROR)
    return _check_reachable(obj[key])


_ITERATOR_TYPES = tuple(
    type(value)
    for value in (
        iter([]),
        iter(()),
        iter({}),
        iter(set()),
        iter(""),
        iter(range(0)),
        {}.keys(),
        {}.values(),
        {}.items(),
        enumerate([]),
        zip([]),
        map(str, []),
        filter(None, []),
    )
)


def guarded_getiter(obj):
    if not (
        type(obj)
        in (
            dict,
            list,
            tuple,
            str,
            set,
            range,
            np.ndarray,
            pd.DataFrame,
            pd.Series,
            DataFrameGroupBy,
            SeriesGroupBy,
            GeneratorType,
            *_ITERATOR_TYPES,
        )
        or isinstance(obj, pd.Index)
        or type(obj) in EXTENSION_ARRAY_TYPES
        or (
            type(obj) is tuple
            or (
                isinstance(obj, tuple) and type(obj).__module__ == "pandas.core.frame" and hasattr(type(obj), "_fields")
            )
        )
    ):
        raise AnalysisRefused(ERROR)
    for value in obj:
        yield _check_reachable(value)


class _WriteProxy:
    __slots__ = ("_obj",)

    def __init__(self, obj):
        object.__setattr__(self, "_obj", obj)

    def __setitem__(self, key, value):
        _check_reachable(value)
        self._obj[key] = value

    def __delitem__(self, key):
        del self._obj[key]

    def __setattr__(self, name, value):
        obj = self._obj
        if (type(obj) is pd.DataFrame and name in {"columns", "index"}) or (
            type(obj) is pd.Series and name in {"index", "name"}
        ):
            plain_value(value.tolist() if isinstance(value, pd.Index) else value)
            setattr(obj, name, value)
            return
        raise AnalysisRefused(ERROR)

    def __delattr__(self, name):
        raise AnalysisRefused(ERROR)


def guarded_write(obj):
    if type(obj) not in (dict, list, np.ndarray, pd.DataFrame, pd.Series, *INDEXERS):
        raise AnalysisRefused(ERROR)
    return _WriteProxy(obj)


def plain_value(value, depth=0, budget=None, cap_strings=False):
    """Validate exact data types BEFORE invoking coercion/serialization hooks."""
    if budget is None:
        budget = [MAX_VALUE_ITEMS]
    budget[0] -= 1
    if budget[0] < 0 or depth > MAX_VALUE_DEPTH:
        raise AnalysisSizeLimit(SIZE_ERROR)
    kind = type(value)
    if kind not in VALUE_SHAPES:
        raise AnalysisRefused(ERROR)
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if kind is str:
        if cap_strings and len(value) > MAX_STRING_CHARS:
            raise AnalysisSizeLimit(SIZE_ERROR)
        return value
    if kind in (bool, int):
        if kind is int and value.bit_length() > 14_000:
            raise AnalysisRefused(ERROR)
        return value
    if kind is float:
        return value if math.isfinite(value) else None
    if kind in (np.int8, np.int16, np.int32, np.int64, np.uint8, np.uint16, np.uint32, np.uint64):
        return int(value)
    if kind is Decimal and not value.is_finite():
        return None
    if kind in (np.float16, np.float32, np.float64, Decimal):
        v = float(value)
        return round(v, 4) if math.isfinite(v) else None
    if kind is np.bool_:
        return bool(value)
    if kind in (pd.Timestamp, datetime, date):
        # Timezone values use reviewed exact types and transport rules.
        if kind in (pd.Timestamp, datetime) and value.tzinfo is not None:
            if timezone_shape(value.tzinfo) is None:
                raise AnalysisRefused(ERROR)
        if kind is pd.Timestamp and not canonical_timestamp(value):
            raise AnalysisRefused(ERROR)
        return value.isoformat()
    if kind is pd.Interval:
        plain_value(value.left, depth + 1, budget, cap_strings)
        plain_value(value.right, depth + 1, budget, cap_strings)
        return str(value)
    if kind is pd.Period:
        if not canonical_frequency(value.freq):
            raise AnalysisRefused(ERROR)
        return str(value)
    if kind in (pd.Timedelta, timedelta):
        return str(value)
    if kind in (list, tuple):
        return [plain_value(v, depth + 1, budget, cap_strings) for v in value]
    if kind is dict:
        out = {}
        for key, v in value.items():
            if type(key) not in (str, bool, int, float):
                raise AnalysisRefused(ERROR)
            if type(key) is float and not math.isfinite(key):
                raise AnalysisRefused(ERROR)
            plain_value(key, depth + 1, budget, cap_strings)
            out[str(key)] = plain_value(v, depth + 1, budget, cap_strings)
        return out
    raise AnalysisRefused(ERROR)


def safe_helper(helper):
    def call(*args, **kwargs):
        for value in (*args, *kwargs.values()):
            if type(value) not in (str, int, float, bool, type(None)):
                raise AnalysisRefused(ERROR)
        return helper(*args, **kwargs)

    return call


def _validate_dtype(dtype):
    """Admission uses the same finite shape table as the transport encoder."""
    row = dtype_shape(dtype)
    if row is None:
        raise AnalysisRefused(ERROR)
    if row.name == "category":
        validate_values(dtype.categories)
    if row.name == "object":
        return False
    return True


def validate_values(values):
    """Typed arrays cannot hide Python objects; inspect only object/category data."""
    if isinstance(values, pd.Index) and type(values) not in INDEX_SHAPES:
        raise AnalysisRefused(ERROR)
    if type(values) in (pd.DatetimeIndex, pd.TimedeltaIndex) and values.freq is not None:
        # Only canonical frequency text is carried by the plain-data boundary.
        # Custom calendars must be refused equally by both execution paths.
        if not canonical_frequency(values.freq):
            raise AnalysisRefused(ERROR)
    if isinstance(values, pd.MultiIndex):
        for level in values.levels:
            validate_values(level)
    elif not _validate_dtype(values.dtype):
        for value in values:
            plain_value(value)


def validate_frame(frame):
    """Validate the whole frame before copying metadata or converting output."""
    if type(frame) not in FRAME_SHAPES:
        raise AnalysisRefused(ERROR)
    plain_value(frame.attrs)
    plain_value(list(frame.index.names))
    validate_values(frame.index)
    if type(frame) is pd.Series:
        plain_value(frame.name)
        validate_values(frame)
    else:
        plain_value(list(frame.columns.names))
        validate_values(frame.columns)
        # Inspect the schema without boxing every numeric column into a Series.
        for i, dtype in enumerate(frame.dtypes):
            if not _validate_dtype(dtype):
                validate_values(frame.iloc[:, i])


def _plain_repr(value):
    plain_value(value)
    return repr(value)


ALLOWED_BUILTINS["repr"] = _plain_repr
