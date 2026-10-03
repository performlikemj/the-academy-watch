"""Shared admission table for plain analysis data and its fixed transport rules.

Every admitted family has a wire rule. Validators and encoders classify through
this table; the generated parity corpus must cover every row. Unknown families,
custom timezones/calendars and unsupported extension storage refuse in both paths.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, available_timezones

import numpy as np
import pandas as pd

TIMEZONE_NAMES = frozenset(available_timezones())
NUMERIC_NAMES = tuple(
    dict.fromkeys(
        ["bool"]
        + [f"{kind}{bits}" for kind in ("int", "uint") for bits in (8, 16, 32, 64)]
        + ["float16", "float32", "float64", np.dtype(np.longdouble).name]
    )
)
TEMPORAL_NAMES = tuple(f"{base}[{unit}]" for base in ("datetime64", "timedelta64") for unit in ("s", "ms", "us", "ns"))
NULLABLE_NAMES = (
    "Int8",
    "Int16",
    "Int32",
    "Int64",
    "UInt8",
    "UInt16",
    "UInt32",
    "UInt64",
    "Float32",
    "Float64",
    "boolean",
)


@dataclass(frozen=True)
class Shape:
    domain: str
    name: str
    wire: str
    kind: type | None = None

    @property
    def id(self):
        return f"{self.domain}:{self.name}"


SHAPES = (
    *(
        Shape("value", name, wire, kind)
        for name, kind, wire in (
            ("none", type(None), "value"),
            ("na", type(pd.NA), "na"),
            ("nat", type(pd.NaT), "nat"),
            ("str", str, "value"),
            ("bool", bool, "value"),
            ("int", int, "value"),
            ("float", float, "float"),
            ("date", date, "date"),
            ("datetime", datetime, "datetime"),
            ("timestamp", pd.Timestamp, "timestamp"),
            ("decimal", Decimal, "decimal"),
            ("python_timedelta", timedelta, "python_timedelta"),
            ("timedelta", pd.Timedelta, "timedelta"),
            ("period", pd.Period, "period"),
            ("interval", pd.Interval, "interval"),
            ("list", list, "list"),
            ("tuple", tuple, "tuple"),
            ("dict", dict, "dict"),
        )
    ),
    *(
        Shape("value", "numpy_" + name, "numpy_scalar", np.dtype(name).type)
        for name in NUMERIC_NAMES
        if name != np.dtype(np.longdouble).name or np.dtype(name).type is np.float64
    ),
    *(Shape("dtype", name, "numeric") for name in NUMERIC_NAMES),
    *(Shape("dtype", name, "temporal") for name in TEMPORAL_NAMES),
    *(Shape("dtype", name, "values", type(pd.api.types.pandas_dtype(name))) for name in NULLABLE_NAMES),
    Shape("dtype", "object", "values", np.dtype),
    Shape("dtype", "string", "string", pd.StringDtype),
    Shape("dtype", "category", "category", pd.CategoricalDtype),
    Shape("dtype", "datetime_tz", "datetime_tz", pd.DatetimeTZDtype),
    Shape("dtype", "period", "values", pd.PeriodDtype),
    Shape("dtype", "interval", "values", pd.IntervalDtype),
    *(
        Shape("index", name, wire, kind)
        for name, kind, wire in (
            ("range", pd.RangeIndex, "range"),
            ("multi", pd.MultiIndex, "multi"),
            ("index", pd.Index, "index"),
            ("datetime", pd.DatetimeIndex, "index"),
            ("timedelta", pd.TimedeltaIndex, "index"),
            ("category", pd.CategoricalIndex, "index"),
            ("period", pd.PeriodIndex, "index"),
            ("interval", pd.IntervalIndex, "index"),
        )
    ),
    Shape("timezone", "fixed", "fixed", timezone),
    Shape("timezone", "zoneinfo", "zoneinfo", ZoneInfo),
    Shape("frame", "dataframe", "frame", pd.DataFrame),
    Shape("frame", "series", "series", pd.Series),
)
VALUE_SHAPES = {row.kind: row for row in SHAPES if row.domain == "value"}
INDEX_SHAPES = {row.kind: row for row in SHAPES if row.domain == "index"}
DTYPE_SHAPES = {row.name: row for row in SHAPES if row.domain == "dtype"}
ZONE_SHAPES = {row.name: row for row in SHAPES if row.domain == "timezone"}
FRAME_SHAPES = {row.kind: row for row in SHAPES if row.domain == "frame"}


def timezone_shape(zone):
    if type(zone) is timezone:
        offset = zone.utcoffset(None)
        if type(offset) is not timedelta or type(zone.tzname(None)) is not str:
            return None
        if offset.microseconds or offset.seconds % 60:
            return None
        return ZONE_SHAPES["fixed"]
    if type(zone) is ZoneInfo and type(zone.key) is str and zone.key in TIMEZONE_NAMES:
        return ZONE_SHAPES["zoneinfo"]
    return None


def dtype_shape(dtype):
    if isinstance(dtype, np.dtype):
        return DTYPE_SHAPES.get(dtype.name)
    for row in DTYPE_SHAPES.values():
        if type(dtype) is row.kind:
            if row.name == "string" and (
                dtype.storage != "python" or dtype.na_value is not pd.NA and not isinstance(dtype.na_value, float)
            ):
                return None
            if row.name == "datetime_tz" and (
                dtype.unit not in {"s", "ms", "us", "ns"} or timezone_shape(dtype.tz) is None
            ):
                return None
            if row.name == "interval" and (
                not isinstance(dtype.subtype, np.dtype) or dtype.subtype.name not in NUMERIC_NAMES
            ):
                return None
            return row
    return None
