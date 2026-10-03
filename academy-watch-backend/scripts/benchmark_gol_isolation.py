"""Local synthetic production-schema measurements for the analysis process."""

import argparse
import ast
import json
import logging
import resource
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.services import gol_isolation as isolation
from src.services.gol_wire import encode_request


def _columns(sql):
    selection = sql.split("SELECT", 1)[1].split("FROM", 1)[0]
    fields, depth, start = [], 0, 0
    for i, char in enumerate(selection):
        depth += (char == "(") - (char == ")")
        if char == "," and depth == 0:
            fields.append(selection[start:i].strip())
            start = i + 1
    fields.append(selection[start:].strip())
    return [field.split(" AS ")[-1].rsplit(".", 1)[-1].strip() for field in fields]


def production_schema_frames(rows):
    """Read only repository SELECT schemas; generate data without any DB access."""
    source = Path(__file__).resolve().parents[1] / "src/services/gol_dataframes.py"
    tree = ast.parse(source.read_text())
    names = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        target = node.targets[0]
        if (
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
            and target.value.id == "frames"
            and isinstance(target.slice, ast.Constant)
        ):
            names[target.slice.value] = _columns(node.value.args[1].value)
    sizes = {
        "teams": 32,
        "tracked": 2_000,
        "journeys": 4_000,
        "journey_entries": 10_000,
        "cohorts": 100,
        "cohort_members": 4_000,
        "fixtures": rows // 22,
        "team_profiles": 1_000,
        "players": 4_000,
        "fixture_stats": rows,
    }
    text = {
        "country",
        "nationality",
        "parent_club",
        "academy_club",
        "current_level",
        "level",
        "entry_type",
        "competition_name",
        "position",
        "formation",
        "grid",
        "formation_position",
        "data_source",
        "status",
        "current_status",
        "league_level",
        "sync_status",
        "logo_url",
        "birth_date",
    }
    frames = {}
    for name, columns in names.items():
        count = sizes[name]
        values = {}
        for column in columns:
            if column in {"updated_at", "date_utc"}:
                values[column] = pd.date_range("2026-01-01", periods=count, freq="s")
            elif column == "academy_club_ids":
                values[column] = pd.Series([[1, 2] for _ in range(count)], dtype=object)
            elif "name" in column or column in text:
                values[column] = pd.Series(
                    np.tile(["Alpha", "Bravo", "Charlie", None], (count + 3) // 4)[:count], dtype="str"
                )
            elif column.startswith("is_") or column == "journey_synced":
                values[column] = np.arange(count) % 2 == 0
            elif column == "rating":
                values[column] = np.arange(count) % 10 / 2.0 + 5
            else:
                values[column] = np.arange(count, dtype=np.int64) % 2_000
        frames[name] = pd.DataFrame(values)
    return frames


class _Measurements(logging.Handler):
    def __init__(self):
        super().__init__()
        self.latest = None

    def emit(self, record):
        if record.msg.startswith("Analysis process finished"):
            boot, elapsed, rss, incoming, outgoing = record.args
            self.latest = {
                "bootstrap_ms": boot,
                "process_ms": elapsed,
                "child_peak_rss_bytes": rss,
                "input_bytes": incoming,
                "output_bytes": outgoing,
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, nargs="+", default=[100_000, 200_000])
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    handler = _Measurements()
    isolation.logger.addHandler(handler)
    isolation.logger.setLevel(logging.INFO)
    report = {"platform": sys.platform, "python": sys.version.split()[0], "measurements": []}
    for rows in args.rows:
        frames = production_schema_frames(rows)
        for repeat in range(args.repeats):
            started = time.monotonic()
            payload = encode_request("result=fixture_stats.groupby('position')['goals'].sum()", frames)
            serialized = time.monotonic()
            result = isolation._run_child(payload)
            finished = time.monotonic()
            if result["result_type"] == "error":
                raise RuntimeError("Analysis measurement refused")
            record = {
                "rows": rows,
                "fixture_columns": len(frames["fixture_stats"].columns),
                "frames": len(frames),
                "repeat": repeat,
                "serialization_ms": (serialized - started) * 1000,
                "end_to_end_ms": (finished - started) * 1000,
                "parent_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                * (1024 if sys.platform == "linux" else 1),
                **handler.latest,
            }
            report["measurements"].append(record)
            del payload
        del frames
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
