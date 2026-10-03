"""Generated examples for every row of the shared plain-data admission table."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from src.services.gol_plain_shapes import INTERVAL_NAMES, NULLABLE_NAMES, NUMERIC_NAMES, SHAPES, TEMPORAL_NAMES


def _objects(values):
    return pd.DataFrame({"x": pd.Series(values, dtype=object)})


def generated_cases():
    """No default recipe: a newly admitted row without examples fails collection."""
    examples = {
        "value:none": [None],
        "value:na": [pd.NA],
        "value:nat": [pd.NaT],
        "value:str": ["Fixture", "", "λ\n"],
        "value:bool": [True, False],
        "value:int": [-(2**100), 2**100, 2**13999],
        "value:float": [np.nan, np.inf, -np.inf, -0.0, 1.25],
        "value:date": [date(2026, 1, 1), date(1, 1, 1)],
        "value:datetime": [datetime(2026, 1, 1, fold=1), datetime(1, 1, 1)],
        "value:timestamp": [pd.Timestamp(1, unit=unit) for unit in ("s", "ms", "us", "ns")],
        "value:decimal": [Decimal("1.123456789123456789"), Decimal("NaN"), Decimal("Infinity"), Decimal("1e1000")],
        "value:python_timedelta": [timedelta(days=999999999), timedelta(days=-999999999), timedelta(microseconds=-1)],
        "value:timedelta": [pd.Timedelta(1, unit=unit) for unit in ("s", "ms", "us", "ns")],
        "value:period": [pd.Period("2026-01", freq="M")],
        "value:interval": [pd.Interval(1, 2, closed="both")],
        "value:list": [[None, np.nan, pd.NaT, pd.NA, (1, {"x": Decimal("1.2")})]],
        "value:tuple": [(None, np.nan, pd.NaT, pd.NA, [1, 2])],
        "value:dict": [{"x": [None, np.nan, pd.NaT, pd.NA], 2: (3, 4)}],
    }
    recipes = {key: [_objects(values)] for key, values in examples.items()}
    temporal_edges = [
        datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=9), "Fixture East")),
        datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone(timedelta(hours=-9), "Fixture West")),
        datetime(2026, 3, 29, 1, 30, tzinfo=ZoneInfo("Europe/London")),
        datetime(2026, 10, 25, 1, 30, tzinfo=ZoneInfo("Europe/London"), fold=1),
    ]
    recipes["value:datetime"].extend(_objects([value]) for value in temporal_edges)
    recipes["value:timestamp"].extend(
        _objects([pd.Timestamp(value)]) for value in (temporal_edges[0], temporal_edges[1], temporal_edges[3])
    )
    for name in NUMERIC_NAMES:
        dtype = np.dtype(name)
        if dtype.type is not np.longdouble or dtype.type is np.float64:
            recipes[f"value:numpy_{name}"] = [_objects([dtype.type(1), dtype.type(0)])]
        values = [True, False] if name == "bool" else [1, 2]
        recipes[f"dtype:{name}"] = [
            pd.DataFrame({"x": np.array(values, dtype=dtype.newbyteorder(order))}) for order in ("<", ">")
        ]
    for name in TEMPORAL_NAMES:
        recipes[f"dtype:{name}"] = [pd.DataFrame({"x": np.array([1, "NaT"], dtype=name)})]
    for name in NULLABLE_NAMES:
        recipes[f"dtype:{name}"] = [
            pd.DataFrame({"x": pd.Series([True, None] if name == "boolean" else [1, None], dtype=name)})
        ]
    for name in INTERVAL_NAMES:
        recipes[f"interval_subtype:{name}"] = [
            pd.DataFrame(
                {
                    "x": pd.arrays.IntervalArray.from_arrays(
                        np.array([1, 2], dtype=np.dtype(name).newbyteorder(order)),
                        np.array([2, 3], dtype=np.dtype(name).newbyteorder(order)),
                        dtype=pd.IntervalDtype(np.dtype(name).newbyteorder(order), closed),
                        closed=closed,
                    )
                }
            )
            for order in ("<", ">")
            for closed in ("left", "right", "both", "neither")
        ]
        if name.startswith("float"):
            recipes[f"interval_subtype:{name}"].append(
                pd.DataFrame(
                    {
                        "x": pd.arrays.IntervalArray.from_arrays(
                            np.array([1, np.nan], dtype=name), np.array([2, np.nan], dtype=name)
                        )
                    }
                )
            )
    recipes.update(
        {
            "dtype:object": [_objects([None, np.nan, pd.NaT, pd.NA, "Fixture"])],
            "dtype:string": [
                pd.DataFrame({"x": pd.Series(["Fixture", None, ""], dtype=name)}) for name in ("str", "string")
            ],
            "dtype:category": [
                pd.DataFrame({"x": pd.Categorical([values[0], None], categories=values, ordered=True)})
                for values in (
                    pd.Index(["A", "B", "unused"], dtype="str", name="categories"),
                    pd.date_range("2026-01-01", periods=3, tz="Europe/London", freq="D", name="categories"),
                    pd.Index([Decimal("1.2"), Decimal("2.3")], dtype=object),
                )
            ],
            "dtype:datetime_tz": [
                pd.DataFrame({"x": pd.date_range("2026-03-28", periods=2, tz="Europe/London").as_unit(unit)})
                for unit in ("s", "ms", "us", "ns")
            ],
            "dtype:period": [
                pd.DataFrame({"x": pd.period_range("2026-01-01", periods=2, freq=frequency)})
                for frequency in ("M", "2B", "W-MON", "2Q-JAN", "2Y-JAN", "D", "2h", "2min", "2s", "2ms", "2us", "2ns")
            ],
            "dtype:interval": [
                pd.DataFrame({"x": pd.arrays.IntervalArray.from_tuples([(0, 1), (1, 2)], closed=closed)})
                for closed in ("left", "right", "both", "neither")
            ],
        }
    )
    indices = {
        "range": [pd.RangeIndex(2, -2, -2, name="Fixture")],
        "index": [
            pd.Index([None, pd.NaT, np.nan, (1, 2)], dtype=object, name="Fixture"),
            pd.Index([1, None], dtype="Int64"),
        ],
        "multi": [
            pd.MultiIndex.from_product(
                [pd.date_range("2026-03-28", periods=2, tz="Europe/London", freq="D"), ["A"]], names=["date", "group"]
            )
        ],
        "datetime": [
            pd.date_range("2026-03-28", periods=2, tz=zone, freq=freq)
            for zone in (None, "Europe/London", "Asia/Tokyo")
            for freq in ("D", "2h", "ME")
        ],
        "timedelta": [pd.timedelta_range("1s", periods=2, freq=freq) for freq in ("2s", "D")],
        "category": [pd.CategoricalIndex(["A", None], categories=["B", "A", "unused"], ordered=True)],
        "period": [pd.period_range("2026-01", periods=2, freq="M")],
        "interval": [pd.IntervalIndex.from_tuples([(0, 1), (1, 2)])],
    }
    for name, values in indices.items():
        recipes[f"index:{name}"] = [pd.DataFrame({"x": range(len(index))}, index=index) for index in values]
    zones = {
        "fixed": [
            timezone(offset, name)
            for offset, name in (
                (timedelta(hours=9), "Fixture Zone"),
                (timedelta(0), "Fixture UTC"),
            )
        ]
        + [UTC, timezone(timedelta(hours=9, minutes=30))],
        "zoneinfo": [ZoneInfo("Europe/London"), ZoneInfo("Asia/Tokyo")],
    }
    for name, values in zones.items():
        frames = []
        for zone in values:
            value = datetime(2026, 10, 25, 1, 30, tzinfo=zone, fold=1)
            frames.extend([_objects([value, None]), _objects([pd.Timestamp(value), pd.NaT])])
            for unit in ("s", "ms", "us", "ns"):
                index = pd.date_range("2026-10-24 12:00", periods=2, tz=zone, freq="D").as_unit(unit)
                frames.extend([pd.DataFrame({"x": index}), pd.DataFrame({"x": [1, 2]}, index=index)])
        recipes[f"timezone:{name}"] = frames
    frame = pd.DataFrame({"x": [1, 2]}).set_flags(allows_duplicate_labels=False)
    frame.attrs = {"fixture": [Decimal("1.2"), (None, pd.NaT)]}
    # Generic object indices must remain generic even when all cells are temporal.
    for values in examples.values():
        objects = np.empty(len(values), dtype=object)
        objects[:] = values
        index = pd.Index(objects, dtype=object, name="Fixture")
        recipes["index:index"].append(pd.DataFrame({"x": range(len(values))}, index=index))
    recipes["frame:dataframe"] = [
        frame,
        frame.iloc[:0],
        pd.DataFrame(),
        pd.DataFrame([[1, 2]], columns=["x", "x"]),
        pd.DataFrame([[1, 2]], columns=pd.MultiIndex.from_tuples([("A", 1), ("B", 2)])),
    ]
    recipes["frame:series"] = [pd.DataFrame({"x": pd.Series([1, None], dtype="Int64", name="x")})]
    assert set(recipes) == {row.id for row in SHAPES}, "Every admission row needs an explicit parity recipe"
    assert len({row.id for row in SHAPES}) == len(SHAPES)
    return [(f"{row.id}/{i}", row, frame) for row in SHAPES for i, frame in enumerate(recipes[row.id])]
