"""Versioned plain-data transport for analysis frames; never object serialization."""

import base64
import json
import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from src.services.gol_capabilities import (
    ERROR,
    SIZE_ERROR,
    TIMEZONE_NAMES,
    AnalysisRefused,
    AnalysisSizeLimit,
    plain_value,
    validate_frame,
)

MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
_NUMERIC_DTYPES = frozenset(
    ["bool"]
    + [f"{kind}{bits}" for kind in ("int", "uint") for bits in (8, 16, 32, 64)]
    + ["float16", "float32", "float64"]
    + [np.dtype(np.longdouble).name]
)


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
    if value is pd.NA:
        return ["na"]
    if value is pd.NaT:
        return ["nat"]
    if kind is float and not math.isfinite(value):
        return ["float", "nan" if math.isnan(value) else "inf" if value > 0 else "-inf"]
    if kind in (
        np.int8,
        np.int16,
        np.int32,
        np.int64,
        np.uint8,
        np.uint16,
        np.uint32,
        np.uint64,
        np.float16,
        np.float32,
        np.float64,
        np.bool_,
    ):
        return ["numpy_scalar", value.dtype.name, base64.b64encode(value.tobytes()).decode("ascii")]
    if kind in (list, tuple):
        return ["tuple" if kind is tuple else "list", [_encode_value(v) for v in value]]
    if kind is dict:
        return ["dict", [[_encode_value(k), _encode_value(v)] for k, v in value.items()]]
    if kind in (datetime, date, pd.Timestamp):
        zone = str(value.tzinfo) if kind is not date and value.tzinfo is not None else None
        return [
            "timestamp" if kind is pd.Timestamp else "datetime" if kind is datetime else "date",
            value.isoformat(),
            zone if zone in TIMEZONE_NAMES else None,
        ]
    if kind is Decimal:
        return ["decimal", str(value)]
    if kind is timedelta:
        return ["python_timedelta", value.days, value.seconds, value.microseconds]
    if kind is pd.Timedelta:
        return ["timedelta", int(value.asm8.view("i8")), value.unit]
    if kind is pd.Period:
        return ["period", str(value), value.freqstr]
    if kind is pd.Interval:
        return ["interval", _encode_value(value.left), _encode_value(value.right), value.closed]
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
        timestamp = pd.Timestamp(value[1])
        return timestamp.tz_convert(value[2]) if value[2] in TIMEZONE_NAMES else timestamp
    if tag == "datetime":
        timestamp = datetime.fromisoformat(value[1])
        return timestamp.astimezone(ZoneInfo(value[2])) if value[2] in TIMEZONE_NAMES else timestamp
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


def _encode_column(column):
    dtype = column.dtype
    if type(dtype) is pd.StringDtype:
        codes, values = column.factorize(sort=False)
        return {
            "kind": "string",
            "dtype": str(dtype),
            "values": values.tolist(),
            "codes": _encode_column(pd.Series(codes.astype(np.int32))),
        }
    if isinstance(dtype, np.dtype) and dtype.name in _NUMERIC_DTYPES:
        array = np.asarray(column).astype(dtype.newbyteorder("<"), copy=False)
        return {
            "kind": "numeric",
            "dtype": dtype.name,
            "byteorder": dtype.byteorder,
            "data": base64.b64encode(array.tobytes()).decode("ascii"),
        }
    if isinstance(dtype, np.dtype) and dtype.kind in "Mm":
        return {
            "kind": "temporal",
            "dtype": dtype.name,
            "data": base64.b64encode(np.asarray(column).astype(dtype.newbyteorder("<"), copy=False).tobytes()).decode(
                "ascii"
            ),
        }
    if type(dtype) is pd.CategoricalDtype:
        return {
            "kind": "category",
            "categories": [_encode_value(v) for v in dtype.categories],
            "ordered": dtype.ordered,
            "codes": _encode_column(pd.Series(column.array.codes)),
        }
    if type(dtype) is pd.DatetimeTZDtype:
        return {"kind": "datetime_tz", "dtype": str(dtype), "values": [_encode_value(v) for v in column]}
    # Pandas string/nullable/object columns preserve their dtype and null kinds.
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
            categories=[_decode_value(v) for v in column["categories"]],
            ordered=column["ordered"],
        )
    if kind == "string":
        if column["dtype"] not in {"str", "string"} or any(type(v) is not str for v in column["values"]):
            raise AnalysisRefused(ERROR)
        values = np.asarray([*column["values"], None], dtype=object)
        return pd.array(values[_decode_column(column["codes"])], dtype=column["dtype"])
    if kind in ("values", "datetime_tz"):
        series = pd.Series([_decode_value(v) for v in column["values"]], dtype=column["dtype"])
        return series.to_numpy(copy=False) if column["dtype"] == "object" else series.array
    raise AnalysisRefused(ERROR)


def _encode_index(index):
    if type(index) is pd.RangeIndex:
        return {
            "kind": "range",
            "start": index.start,
            "stop": index.stop,
            "step": index.step,
            "name": _encode_value(index.name),
        }
    if type(index) is pd.MultiIndex:
        return {
            "kind": "multi",
            "levels": [_encode_index(level) for level in index.levels],
            "codes": [_encode_column(pd.Series(codes)) for codes in index.codes],
            "names": [_encode_value(v) for v in index.names],
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
        )
    result = pd.Index(_decode_column(index["column"]), name=_decode_value(index["name"]))
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
            yield {"frame": name, "index": _encode_index(frame.index), "columns": _encode_index(frame.columns)}
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
        if set(message) != {"frame", "index", "columns"} or type(message["frame"]) is not str:
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
        validate_frame(result)
        frames[name] = result
    return request["code"], frames


def decode_result(data):
    """Revalidate the capped child DTO with the same plain-value boundary."""
    if len(data) > MAX_OUTPUT_BYTES:
        raise AnalysisRefused(ERROR)
    try:
        result = json.loads(data, parse_constant=lambda value: (_ for _ in ()).throw(AnalysisRefused(ERROR)))
    except (ValueError, UnicodeError):
        raise AnalysisRefused(ERROR) from None
    result = plain_value(result, cap_strings=True)
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
