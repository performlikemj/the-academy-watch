"""Versioned plain-data transport for analysis frames; never object serialization."""

import base64
import json
import math
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from src.services.gol_capabilities import (
    ERROR,
    SIZE_ERROR,
    AnalysisRefused,
    AnalysisSizeLimit,
    plain_value,
    validate_frame,
)
from src.services.gol_plain_shapes import (
    INDEX_SHAPES,
    NUMERIC_NAMES,
    TIMEZONE_NAMES,
    VALUE_SHAPES,
    dtype_shape,
    timezone_shape,
)

MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
_NUMERIC_DTYPES = frozenset(NUMERIC_NAMES)


class InputSizeLimit(AnalysisSizeLimit):
    """Measured fixed input limits for operator telemetry, without input values."""

    def __init__(self, measured, limit, unit="bytes"):
        super().__init__(SIZE_ERROR)
        self.measured = measured
        self.limit = limit
        self.unit = unit


def _encode_value(value):
    """Only fixed tags and validated values, with no import/type names on the wire."""
    kind = type(value)
    row = VALUE_SHAPES.get(kind)
    if row is None:
        raise AnalysisRefused(ERROR)
    if value is pd.NA:
        return ["na"]
    if value is pd.NaT:
        return ["nat"]
    if kind is float and not math.isfinite(value):
        return ["float", "nan" if math.isnan(value) else "inf" if value > 0 else "-inf"]
    if row.wire == "numpy_scalar":
        return ["numpy_scalar", value.dtype.name, base64.b64encode(value.tobytes()).decode("ascii")]
    if row.wire in {"list", "tuple"}:
        return [row.wire, [_encode_value(v) for v in value]]
    if row.wire == "dict":
        return [row.wire, [[_encode_value(k), _encode_value(v)] for k, v in value.items()]]
    if row.wire == "timestamp":
        return ["timestamp", int(value.asm8.view("i8")), value.unit, _encode_zone(value.tzinfo), value.fold]
    if row.wire == "datetime":
        return ["datetime", value.isoformat(), _encode_zone(value.tzinfo), value.fold]
    if row.wire == "date":
        return ["date", value.isoformat()]
    if row.wire == "decimal":
        return ["decimal", str(value)]
    if row.wire == "python_timedelta":
        return ["python_timedelta", value.days, value.seconds, value.microseconds]
    if row.wire == "timedelta":
        return ["timedelta", int(value.asm8.view("i8")), value.unit]
    if row.wire == "period":
        return ["period", str(value), value.freqstr]
    if row.wire == "interval":
        return ["interval", _encode_value(value.left), _encode_value(value.right), value.closed]
    if row.wire not in {"value", "float"}:
        raise AnalysisRefused(ERROR)
    return ["value", plain_value(value)]


def _decode_value(value):
    tag = value[0]
    if tag == "value":
        return value[1]
    if tag == "na":
        return pd.NA
    if tag == "nat":
        return pd.NaT
    if tag == "float":
        return float(value[1])
    if tag == "numpy_scalar":
        if value[1] not in _NUMERIC_DTYPES:
            raise AnalysisRefused(ERROR)
        return np.frombuffer(base64.b64decode(value[2], validate=True), dtype=np.dtype(value[1]).newbyteorder("<"))[0]
    if tag == "list":
        return [_decode_value(v) for v in value[1]]
    if tag == "tuple":
        return tuple(_decode_value(v) for v in value[1])
    if tag == "dict":
        return {_decode_value(k): _decode_value(v) for k, v in value[1]}
    if tag == "timestamp":
        zone = _decode_zone(value[3])
        timestamp = pd.Timestamp(value[1], unit=value[2], tz="UTC" if zone is not None else None)
        return (timestamp.tz_convert(zone) if zone is not None else timestamp).replace(fold=value[4])
    if tag == "datetime":
        timestamp = datetime.fromisoformat(value[1])
        zone = _decode_zone(value[2])
        return timestamp.replace(tzinfo=zone, fold=value[3])
    if tag == "date":
        return date.fromisoformat(value[1])
    if tag == "decimal":
        return Decimal(value[1])
    if tag == "timedelta":
        return pd.Timedelta(value[1], unit=value[2])
    if tag == "python_timedelta":
        return timedelta(days=value[1], seconds=value[2], microseconds=value[3])
    if tag == "period":
        return pd.Period(value[1], freq=value[2])
    if tag == "interval":
        return pd.Interval(_decode_value(value[1]), _decode_value(value[2]), closed=value[3])
    raise AnalysisRefused(ERROR)


def _encode_zone(zone):
    if zone is None:
        return None
    row = timezone_shape(zone)
    if row is None:
        raise AnalysisRefused(ERROR)
    if row.name == "fixed":
        offset = zone.utcoffset(None)
        return [
            row.wire,
            offset.days,
            offset.seconds,
            offset.microseconds,
            zone.tzname(None),
            "utc" if zone is UTC else "auto" if repr(zone) == repr(timezone(offset)) else "named",
        ]
    return [row.wire, zone.key]


def _decode_zone(value):
    if value is None:
        return None
    if value[0] == "fixed":
        offset = timedelta(days=value[1], seconds=value[2], microseconds=value[3])
        if value[5] == "utc":
            return UTC
        if value[5] == "auto":
            return timezone(offset)
        if value[5] == "named":
            return timezone(offset, value[4])
        raise AnalysisRefused(ERROR)
    if value[0] == "zoneinfo" and value[1] in TIMEZONE_NAMES:
        return ZoneInfo(value[1])
    raise AnalysisRefused(ERROR)


def _encode_column(column):
    dtype = column.dtype
    row = dtype_shape(dtype)
    if row is None:
        raise AnalysisRefused(ERROR)
    if row.wire == "string":
        codes, values = column.factorize(sort=False)
        return {
            "kind": "string",
            "dtype": str(dtype),
            "values": values.tolist(),
            "codes": _encode_column(pd.Series(codes.astype(np.int32))),
        }
    if row.wire == "numeric":
        array = np.asarray(column).astype(dtype.newbyteorder("<"), copy=False)
        return {
            "kind": "numeric",
            "dtype": dtype.name,
            "byteorder": dtype.byteorder,
            "data": base64.b64encode(array.tobytes()).decode("ascii"),
        }
    if row.wire == "temporal":
        return {
            "kind": "temporal",
            "dtype": dtype.name,
            "data": base64.b64encode(np.asarray(column).astype(dtype.newbyteorder("<"), copy=False).tobytes()).decode(
                "ascii"
            ),
        }
    if row.wire == "category":
        return {
            "kind": "category",
            "categories": _encode_index(dtype.categories),
            "ordered": dtype.ordered,
            "codes": _encode_column(pd.Series(column.array.codes)),
        }
    if row.wire == "datetime_tz":
        return {
            "kind": "datetime_tz",
            "unit": dtype.unit,
            "zone": _encode_zone(dtype.tz),
            "data": base64.b64encode(column.array.asi8.astype("<i8", copy=False).tobytes()).decode("ascii"),
        }
    if row.wire != "values":
        raise AnalysisRefused(ERROR)
    # Pandas nullable/object columns preserve their dtype and null kinds.
    return {"kind": "values", "dtype": str(dtype), "values": [_encode_value(v) for v in column]}


def _decode_column(column):
    kind = column["kind"]
    if kind in ("numeric", "temporal"):
        name = column["dtype"]
        if kind == "numeric" and name not in _NUMERIC_DTYPES:
            raise AnalysisRefused(ERROR)
        if kind == "temporal" and name not in {
            f"{base}[{unit}]" for base in ("datetime64", "timedelta64") for unit in ("s", "ms", "us", "ns")
        }:
            raise AnalysisRefused(ERROR)
        dtype = np.dtype(name).newbyteorder("<")
        values = np.frombuffer(base64.b64decode(column["data"], validate=True), dtype=dtype).copy()
        if kind == "numeric":
            order = column.get("byteorder", "=")
            if order not in {"<", ">", "=", "|"}:
                raise AnalysisRefused(ERROR)
            values = values.astype(dtype.newbyteorder(order), copy=False)
        return values
    if kind == "category":
        return pd.Categorical.from_codes(
            _decode_column(column["codes"]),
            categories=_decode_index(column["categories"]),
            ordered=column["ordered"],
        )
    if kind == "string":
        if column["dtype"] not in {"str", "string"} or any(type(v) is not str for v in column["values"]):
            raise AnalysisRefused(ERROR)
        values = np.asarray([*column["values"], None], dtype=object)
        return pd.array(values[_decode_column(column["codes"])], dtype=column["dtype"])
    if kind == "datetime_tz":
        unit = column["unit"]
        if unit not in {"s", "ms", "us", "ns"}:
            raise AnalysisRefused(ERROR)
        numbers = np.frombuffer(base64.b64decode(column["data"], validate=True), dtype="<i8").copy()
        return pd.array(numbers.view(f"datetime64[{unit}]"), dtype=pd.DatetimeTZDtype(unit=unit, tz="UTC")).tz_convert(
            _decode_zone(column["zone"])
        )
    if kind == "values":
        series = pd.Series([_decode_value(v) for v in column["values"]], dtype=column["dtype"])
        return series.to_numpy(copy=False) if column["dtype"] == "object" else series.array
    raise AnalysisRefused(ERROR)


def _encode_index(index):
    row = INDEX_SHAPES.get(type(index))
    if row is None:
        raise AnalysisRefused(ERROR)
    if row.wire == "range":
        return {
            "kind": "range",
            "start": index.start,
            "stop": index.stop,
            "step": index.step,
            "name": _encode_value(index.name),
        }
    if row.wire == "multi":
        return {
            "kind": "multi",
            "levels": [_encode_index(level) for level in index.levels],
            "codes": [_encode_column(pd.Series(codes)) for codes in index.codes],
            "names": [_encode_value(v) for v in index.names],
            "sortorder": index.sortorder,
        }
    return {
        "kind": "index",
        "column": _encode_column(pd.Series(index)),
        "name": _encode_value(index.name),
        "frequency": index.freqstr if type(index) in (pd.DatetimeIndex, pd.TimedeltaIndex) else None,
    }


def _decode_index(index):
    if index["kind"] == "range":
        return pd.RangeIndex(index["start"], index["stop"], index["step"], name=_decode_value(index["name"]))
    if index["kind"] == "multi":
        return pd.MultiIndex(
            levels=[_decode_index(level) for level in index["levels"]],
            codes=[_decode_column(codes) for codes in index["codes"]],
            names=[_decode_value(v) for v in index["names"]],
            sortorder=index["sortorder"],
        )
    column = index["column"]
    result = pd.Index(
        _decode_column(column),
        dtype=object if column.get("dtype") == "object" else None,
        name=_decode_value(index["name"]),
    )
    if type(result) in (pd.DatetimeIndex, pd.TimedeltaIndex):
        result.freq = index["frequency"]
    return result


def encode_request(code, frames):
    encoded = {}
    cells = 0
    for name, frame in frames.items():
        if type(name) is not str or type(frame) is not pd.DataFrame:
            raise AnalysisRefused(ERROR)
        validate_frame(frame)
        cells += frame.size
        if cells > 16_000_000:
            raise InputSizeLimit(cells, 16_000_000, "cells")
    for name, frame in frames.items():
        encoded[name] = {
            "index": _encode_index(frame.index),
            "columns": _encode_index(frame.columns),
            "data": [_encode_column(frame.iloc[:, i]) for i in range(len(frame.columns))],
            "attrs": _encode_value(frame.attrs),
            "duplicates": frame.flags.allows_duplicate_labels,
        }
    data = json.dumps({"version": 1, "code": code, "frames": encoded}, allow_nan=False, separators=(",", ":")).encode()
    if len(data) > MAX_INPUT_BYTES:
        raise InputSizeLimit(len(data), MAX_INPUT_BYTES)
    return data


def stream_request(code, frames):
    """Version 2 sends a column at a time without retaining the whole payload."""
    cells = 0
    for name, frame in frames.items():
        if type(name) is not str or type(frame) is not pd.DataFrame:
            raise AnalysisRefused(ERROR)
        validate_frame(frame)
        cells += frame.size
        if cells > 16_000_000:
            raise InputSizeLimit(cells, 16_000_000, "cells")
    incoming = 0
    messages = [{"version": 2, "code": code}]

    def frame_messages():
        yield from messages
        for name, frame in frames.items():
            yield {
                "frame": name,
                "index": _encode_index(frame.index),
                "columns": _encode_index(frame.columns),
                "attrs": _encode_value(frame.attrs),
                "duplicates": frame.flags.allows_duplicate_labels,
            }
            for i in range(len(frame.columns)):
                yield {"column": _encode_column(frame.iloc[:, i])}
        yield {"done": True}

    for message in frame_messages():
        chunk = json.dumps(message, allow_nan=False, separators=(",", ":")).encode() + b"\n"
        incoming += len(chunk)
        if incoming > MAX_INPUT_BYTES:
            raise InputSizeLimit(incoming, MAX_INPUT_BYTES)
        yield chunk


def read_request(stream):
    """Decode a bounded column stream; version 1 remains a parity test input."""
    incoming = 0

    def next_message():
        nonlocal incoming
        data = stream.readline(MAX_INPUT_BYTES - incoming + 1)
        incoming += len(data)
        if not data or incoming > MAX_INPUT_BYTES:
            raise AnalysisRefused(ERROR)
        return json.loads(data)

    header = next_message()
    if header.get("version") == 1:
        return _decode_document(header)
    if header != {"version": 2, "code": header.get("code")} or type(header["code"]) is not str:
        raise AnalysisRefused(ERROR)
    frames = {}
    while True:
        message = next_message()
        if message == {"done": True}:
            if stream.read(1):
                raise AnalysisRefused(ERROR)
            return header["code"], frames
        if set(message) != {"frame", "index", "columns", "attrs", "duplicates"} or type(message["frame"]) is not str:
            raise AnalysisRefused(ERROR)
        index = _decode_index(message["index"])
        labels = _decode_index(message["columns"])
        columns = {}
        for i in range(len(labels)):
            column_message = next_message()
            if set(column_message) != {"column"}:
                raise AnalysisRefused(ERROR)
            column = column_message["column"]
            values = _decode_column(column)
            columns[i] = pd.Series(values, dtype=object, copy=False) if column.get("dtype") == "object" else values
            del column_message, column, values
        result = pd.DataFrame(columns, index=pd.RangeIndex(len(index)), copy=False)
        result.index = index
        result.columns = labels
        result.attrs = _decode_value(message["attrs"])
        result.flags.allows_duplicate_labels = message["duplicates"]
        validate_frame(result)
        frames[message["frame"]] = result


def decode_request(data):
    return _decode_document(json.loads(data))


def _decode_document(request):
    if request["version"] != 1 or type(request["code"]) is not str:
        raise AnalysisRefused(ERROR)
    frames = {}
    for name, frame in request["frames"].items():
        # Integer temporary labels preserve duplicate column names.
        index = _decode_index(frame["index"])
        columns = {}
        for i, column in enumerate(frame["data"]):
            values = _decode_column(column)
            columns[i] = pd.Series(values, dtype=object, copy=False) if column.get("dtype") == "object" else values
        result = pd.DataFrame(columns, index=pd.RangeIndex(len(index)))
        result.index = index
        result.columns = _decode_index(frame["columns"])
        result.attrs = _decode_value(frame["attrs"])
        result.flags.allows_duplicate_labels = frame["duplicates"]
        validate_frame(result)
        frames[name] = result
    return request["code"], frames


def decode_result(data):
    """Revalidate the capped child DTO with the same plain-value boundary."""
    if len(data) > MAX_OUTPUT_BYTES:
        raise AnalysisRefused(ERROR)
    try:
        result = json.loads(data, parse_constant=lambda value: (_ for _ in ()).throw(AnalysisRefused(ERROR)))
        result = plain_value(result, cap_strings=True)
    except (ValueError, UnicodeError, RecursionError):
        raise AnalysisRefused(ERROR) from None
    if type(result) is not dict or result.get("result_type") not in {"error", "table", "list", "dict", "scalar"}:
        raise AnalysisRefused(ERROR)
    fields = {
        "error": {"result_type", "error"},
        "table": {"result_type", "columns", "rows", "total_rows", "truncated"},
        "list": {"result_type", "items"},
        "dict": {"result_type", "data"},
        "scalar": {"result_type", "value"},
    }[result["result_type"]]
    if set(result) not in (fields, fields | {"display"}):
        raise AnalysisRefused(ERROR)
    if result["result_type"] == "table":
        if (
            type(result.get("columns")) is not list
            or any(type(v) is not str for v in result["columns"])
            or type(result.get("rows")) is not list
            or len(result["rows"]) > 100
            or any(type(row) is not list or len(row) != len(result["columns"]) for row in result["rows"])
            or type(result.get("total_rows")) is not int
            or result["total_rows"] < len(result["rows"])
            or type(result.get("truncated")) is not bool
        ):
            raise AnalysisRefused(ERROR)
    if result["result_type"] == "list" and (type(result.get("items")) is not list or len(result["items"]) > 100):
        raise AnalysisRefused(ERROR)
    if result["result_type"] == "dict" and type(result.get("data")) is not dict:
        raise AnalysisRefused(ERROR)
    if result["result_type"] == "scalar" and type(result.get("value")) not in (str, int, float, bool, type(None)):
        raise AnalysisRefused(ERROR)
    if result["result_type"] == "error":
        if type(result.get("error")) is not str or result["error"] not in {
            ERROR,
            SIZE_ERROR,
            "No code provided",
            "Analysis refused: import statements are unavailable.",
            "Analysis refused: syntax error.",
            "Analysis refused: KeyError (missing column or label).",
            "Analysis exceeded its execution limit.",
            "No `result` variable set. Your code must assign to `result`.",
        }:
            raise AnalysisRefused(ERROR)
    return result
