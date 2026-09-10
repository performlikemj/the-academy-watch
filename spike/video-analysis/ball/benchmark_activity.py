"""Observe known competing work without reading prompts or pausing processes."""

from __future__ import annotations
import json
import os
import re
import subprocess
import threading
import time
import urllib.request

CLIENTS = {"llama-server", "ollama", "mediaanalysisd", "PhotosReliveWidget"}
ACTIVE_GENERATORS = {"llama-server", "ollama"}


def bench_job(pid, argv, cwd=""):
    """Record only script names, never unrelated process arguments or prompts."""
    if pid == os.getpid():
        return None
    for arg in argv or []:
        name = arg.rsplit("/", 1)[-1]
        if name.endswith(".py") and name.startswith(
            (
                "train_",
                "infer",
                "round5_inference",
                "throughput_",
                "run_round",
                "run_bench",
                "mlx_worker",
                "run_ball",
                "detect_",
            )
        ):
            if any(
                token in arg or token in (cwd or "")
                for token in ("ball", "video-analysis/bench")
            ) or any("tinyball" in a for a in argv):
                return {"pid": pid, "script": name}
    return None


def busy(sample, *, preflight=False):
    return bool(
        sample["comfy"].get("queue_running", 0)
        or sample["comfy"].get("queue_pending", 0)
        or sample["new_clients"]
        or sample.get("bench_jobs", [])
        or any(
            p["name"] in ACTIVE_GENERATORS and p["cpu_percent"] >= 2
            for p in sample["clients"]
        )
        or (preflight and (sample["gpu_percent"] or 0) > 10)
    )


class Activity:
    def __init__(self, max_wait_s=900):
        self.max_wait_s = max_wait_s
        self.waited_s = 0.0
        self.samples = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        import psutil

        previous, last = {}, time.perf_counter()
        while not self.stop.wait(1):
            now = time.perf_counter()
            current, clients, jobs = {}, [], []
            for p in psutil.process_iter(["name", "cpu_times", "cmdline", "cwd"]):
                job = bench_job(p.pid, p.info["cmdline"], p.info["cwd"])
                if job:
                    jobs.append(job)
                if p.info["name"] not in CLIENTS or p.info["cpu_times"] is None:
                    continue
                total = p.info["cpu_times"].user + p.info["cpu_times"].system
                current[p.pid] = total
                clients.append(
                    {
                        "pid": p.pid,
                        "name": p.info["name"],
                        "cpu_percent": 100
                        * max(0, total - previous.get(p.pid, total))
                        / (now - last),
                    }
                )
            try:
                with urllib.request.urlopen(
                    "http://127.0.0.1:8188/queue", timeout=3
                ) as r:
                    q = json.load(r)
                comfy = {k: len(q[k]) for k in ("queue_running", "queue_pending")}
            except OSError:
                comfy = {"server": "unavailable"}
            raw = subprocess.check_output(
                ["ioreg", "-r", "-c", "AGXAccelerator", "-l"], text=True, timeout=3
            )
            match = re.search(r'"Device Utilization %"=(\d+)', raw)
            self.samples.append(
                {
                    "t": now,
                    "comfy": comfy,
                    "bench_jobs": jobs,
                    "clients": clients,
                    "new_clients": sorted(
                        p["pid"]
                        for p in clients
                        if p["name"] in ACTIVE_GENERATORS and p["pid"] not in previous
                    ),
                    "gpu_percent": int(match[1]) if match else None,
                }
            )
            previous, last = current, now

    def wait_idle(self):
        """Share one finite wait budget across all repeats; contention is evidence."""
        started = time.perf_counter()
        last_message = 0
        while True:
            if not self.thread.is_alive():
                raise RuntimeError(
                    "activity monitor failed; cannot record timing caveats"
                )
            recent = self.samples[-3:]
            quiet = len(recent) == 3 and not any(
                busy(s, preflight=True) for s in recent
            )
            elapsed = time.perf_counter() - started
            if quiet or self.waited_s + elapsed >= self.max_wait_s:
                self.waited_s = min(self.max_wait_s, self.waited_s + elapsed)
                return {
                    **(recent[-1] if recent else {}),
                    "quiet_wait_total_s": self.waited_s,
                    "timing_status": "quiet known clients (steady background load)"
                    if quiet
                    else "contended (steady background load)",
                }
            if time.perf_counter() - last_message > 30:
                print(
                    "Waiting for quiet interval (total cap 900s):",
                    recent[-1:] or "starting probe",
                    flush=True,
                )
                last_message = time.perf_counter()
            time.sleep(min(1, self.max_wait_s - self.waited_s - elapsed))

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)

    def after(self, end):
        while not self.samples or self.samples[-1]["t"] <= end:
            if not self.thread.is_alive():
                raise RuntimeError("activity monitor failed during timing")
            time.sleep(0.05)
        return self.samples[-1]
