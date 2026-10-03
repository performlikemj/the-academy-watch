"""Standalone, single-use analysis worker. Never import the application or DB."""

import os
import sys
from pathlib import Path

# -I ignores inherited Python settings and the working directory on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    from src.services.gol_process_policy import install_policy, set_limits

    set_limits(
        expected_parent_pid=int(sys.argv[1]),
        address_space_bytes=int(sys.argv[2]) if len(sys.argv) > 2 else 768 * 1024 * 1024,
    )
    # Fixed bootstrap-only settings prevent native libraries creating a pool.
    # The launch environment is empty; analysis sees an empty mapping too.
    os.environ.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    import importlib
    import json
    from zoneinfo import ZoneInfo
    from zoneinfo._zoneinfo import ZoneInfo as PythonZoneInfo

    import pandas as pd
    from src.services.gol_capabilities import ERROR, TIMEZONE_NAMES
    from src.services.gol_sandbox import _execute_analysis
    from src.services.gol_wire import MAX_OUTPUT_BYTES, read_request

    # Timezone readers are warmed while the trusted bootstrap can read packages.
    zones = [ZoneInfo(name) for name in TIMEZONE_NAMES] + [PythonZoneInfo(name) for name in TIMEZONE_NAMES]
    for name in TIMEZONE_NAMES:
        pd.Timestamp("2026-01-01", tz=name).tz_convert("UTC")
    for module in (
        "numpy.rec",
        "numpy.ma",
        "numpy.linalg",
        "numpy.random",
        "numpy.fft",
        "pandas.core.reshape.pivot",
        "pandas.core.reshape.reshape",
        "pandas.core.methods.to_dict",
        "pandas.io.formats.string",
    ):
        importlib.import_module(module)
    os.environ.clear()
    install_policy()
    # Parent starts the analysis wall budget after this bounded bootstrap.
    sys.stdout.buffer.write(b"READY\n")
    sys.stdout.buffer.flush()
    code, frames = read_request(sys.stdin.buffer)
    result = _execute_analysis(code, frames)
    output = json.dumps(result, allow_nan=False, separators=(",", ":")).encode()
    if len(output) > MAX_OUTPUT_BYTES:
        raise ValueError(ERROR)
    sys.stdout.buffer.write(output)
    sys.stdout.buffer.flush()
    # Keep named-zone cache objects alive until the analysis has finished.
    del zones


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        # No exception details, frame contents or child diagnostics cross here.
        sys.exit(1)
