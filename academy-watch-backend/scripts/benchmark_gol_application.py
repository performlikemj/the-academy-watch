"""Synthetic full-application memory check in a disposable Linux container."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contextlib import redirect_stdout

with redirect_stdout(sys.stderr):
    from src.main import app
import argparse
import json
import logging
import multiprocessing as mp
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from scripts.benchmark_gol_isolation import production_schema_frames
from src.services import gol_isolation
from src.services.gol_dataframes import DataFrameCache
from src.services.gol_isolation import _resident_bytes
from src.services.gol_service import GolService

logging.getLogger().setLevel(logging.WARNING)


def run_worker(rows, event, queue, warm_caches):
    cache = DataFrameCache()
    cache._load_all = lambda app, names=None: production_schema_frames(rows, only=names)
    # Synthetic fixture IDs alone; no DB or provider operation is measured.
    cache._adult_frames = lambda app, frames: {name: frame.copy() for name, frame in frames.items()}
    service = GolService.__new__(GolService)
    service.df_cache = cache
    if warm_caches:
        with app.app_context():
            cache.get_frames(app)
    # Complete the actual policy probe before measuring steady-state admission.
    assert gol_isolation.isolation_ready()
    queue.put({"pid": os.getpid(), "baseline_rss": _resident_bytes(os.getpid())})
    event.wait()

    class Metrics(logging.Handler):
        def __init__(self):
            super().__init__()
            self.owner = threading.get_ident()
            self.events = []

        def emit(self, record):
            if record.thread != self.owner:
                return
            if record.msg.startswith("Analysis process finished"):
                self.events.append(
                    {"bootstrap_ms": record.args[0], "elapsed_ms": record.args[1], "child_rss": record.args[2]}
                )
            if record.msg.startswith("Analysis process refused"):
                self.events.append({"reason": record.args[0], "measured": record.args[1], "limit": record.args[2]})

    gol_isolation.logger.setLevel(logging.INFO)
    gol_isolation.logger.propagate = False

    def request(index):
        metrics = Metrics()
        gol_isolation.logger.addHandler(metrics)
        code = (
            "helper=find_similar_players\nresult=fixture_stats.apply(lambda row:row.goals+row.minutes,axis=1).head(3)"
        )
        with app.app_context():
            started = time.monotonic()
            result = service._execute_tool("run_analysis", {"code": code})
        gol_isolation.logger.removeHandler(metrics)
        return {
            "metrics": metrics.events,
            "result_type": result.get("result_type"),
            "error": result.get("error"),
            "elapsed_ms": (time.monotonic() - started) * 1000,
        }

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(request, range(2)))
    queue.put({"pid": os.getpid(), "results": results, "final_rss": _resident_bytes(os.getpid())})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=200000)
    parser.add_argument("--warm-caches", action="store_true")
    args = parser.parse_args()
    ctx = mp.get_context("fork")
    queue = ctx.Queue()
    event = ctx.Event()
    workers = [ctx.Process(target=run_worker, args=(args.rows, event, queue, args.warm_caches)) for _ in range(2)]
    for worker in workers:
        worker.start()
    try:
        measure(args, queue, event, workers)
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.kill()
            worker.join()
        queue.close()
        queue.join_thread()


def measure(args, queue, event, workers):
    baseline = [queue.get(timeout=30) for _ in workers]
    root = Path("/sys/fs/cgroup")
    events_before = (root / "memory.events").read_text()
    baseline_current = int((root / "memory.current").read_text())
    event.set()
    peak = baseline_current
    deadline = time.monotonic() + 90
    while any(worker.is_alive() for worker in workers):
        if time.monotonic() > deadline:
            raise RuntimeError("Local measurement exceeded deadline")
        peak = max(peak, int((root / "memory.current").read_text()))
        for worker in workers:
            worker.join(timeout=0.025)
    results = [queue.get(timeout=10) for _ in workers]
    for worker in workers:
        worker.join()
        assert worker.exitcode == 0
    report = {
        "rows": args.rows,
        "warm_caches": args.warm_caches,
        "workers": 2,
        "threads_per_worker": 2,
        "full_flask_master_rss": _resident_bytes(os.getpid()),
        "baseline": baseline,
        "baseline_cgroup_bytes": baseline_current,
        "peak_cgroup_bytes": peak,
        "memory_events_before": events_before,
        "memory_events_after": (root / "memory.events").read_text(),
        "results": results,
        "exitcodes": [worker.exitcode for worker in workers],
    }
    print(json.dumps(report, indent=2))
    assert "oom_kill 0" in report["memory_events_after"]
    assert "oom 0" in report["memory_events_after"]
    if not args.warm_caches:
        assert any(item["result_type"] == "table" for result in results for item in result["results"])
    else:
        from src.services.gol_capabilities import SIZE_ERROR
        from src.services.gol_isolation import BUSY_ERROR, TIME_ERROR

        assert all(
            item["result_type"] == "table" or item["error"] in {SIZE_ERROR, BUSY_ERROR, TIME_ERROR}
            for result in results
            for item in result["results"]
        )
    assert peak < 960 * 1024 * 1024


if __name__ == "__main__":
    main()
