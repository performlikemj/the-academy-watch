"""Linux supervisor for single-use analysis children and bounded plain-data pipes."""

import fcntl
import hashlib
import logging
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from src.services.gol_capabilities import ERROR, SIZE_ERROR, AnalysisRefused, AnalysisSizeLimit
from src.services.gol_process_policy import ADDRESS_SPACE_BYTES, RSS_BYTES
from src.services.gol_scope import analysis_frame_names
from src.services.gol_wire import MAX_INPUT_BYTES, MAX_OUTPUT_BYTES, decode_result, stream_request

logger = logging.getLogger(__name__)
STARTUP_SECONDS = 10
WALL_SECONDS = 10
SLOT_WAIT_SECONDS = 10
TIME_ERROR = "Analysis exceeded its execution limit."
BUSY_ERROR = "Analysis is busy. Retry later."
_WORKER = Path(__file__).with_name("gol_analysis_worker.py")
_SLOT_FILE = None  # Resolved lazily so an unavailable tmp directory cannot break imports.
_SLOT_LOCAL = threading.local()
_READINESS_LOCK = threading.Lock()
_READINESS = (0, 0.0, False)
READINESS_SECONDS = 600
READINESS_RETRY_SECONDS = 60
MEMORY_RESERVE_BYTES = 128 * 1024 * 1024
MIN_ADDRESS_SPACE_BYTES = 384 * 1024 * 1024


class IsolationFault(AnalysisRefused):
    """Fixed operational category; never retain child diagnostics or frame data."""

    def __init__(self, reason, measured=0, limit=0, unit="bytes"):
        super().__init__(ERROR)
        self.reason = reason
        self.measured = int(measured)
        self.limit = int(limit)
        self.unit = unit


def _report(fault):
    level = logging.WARNING if fault.reason in {"bootstrap_failed", "input_size", "headroom"} else logging.INFO
    logger.log(
        level,
        "Analysis process refused reason=%s measured=%d limit=%d unit=%s",
        fault.reason,
        fault.measured,
        fault.limit,
        fault.unit,
    )


def _unavailable():
    global _READINESS
    _READINESS = (os.getpid(), time.monotonic() + READINESS_RETRY_SECONDS, False)


def _slot_file():
    if _SLOT_FILE is not None:
        return _SLOT_FILE
    return Path(tempfile.gettempdir()) / (
        "aw-analysis-slot-" + hashlib.sha256(str(Path(__file__).resolve()).encode()).hexdigest()[:16]
    )


@contextmanager
def _analysis_slot():
    """Admit before loading/copying frames, shared by all Gunicorn workers."""
    if getattr(_SLOT_LOCAL, "held", False):
        yield
        return
    descriptor = os.open(_slot_file(), os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        status = os.fstat(descriptor)
        if status.st_uid != os.getuid() or status.st_mode & 0o077 or not stat.S_ISREG(status.st_mode):
            raise IsolationFault("bootstrap_failed")
        deadline = time.monotonic() + SLOT_WAIT_SECONDS
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise IsolationFault("busy") from None
                time.sleep(0.025)
        _SLOT_LOCAL.held = True
        try:
            yield
        finally:
            _SLOT_LOCAL.held = False
    finally:
        os.close(descriptor)


def _cleanup_stale_directories():
    """Remove only empty owned analysis directories whose creating PID is gone."""
    for directory in Path(tempfile.gettempdir()).glob("aw-analysis-*"):
        match = re.fullmatch(r"aw-analysis-([1-9][0-9]*)-[a-z0-9_]{8}", directory.name)
        if not match:
            continue
        try:
            status = directory.lstat()
            if not stat.S_ISDIR(status.st_mode) or status.st_uid != os.getuid():
                continue
            try:
                os.kill(int(match[1]), 0)
            except ProcessLookupError:
                directory.rmdir()
        except (OSError, ValueError):
            continue


def _memory_available():
    """Container memory is authoritative; MemAvailable also bounds bare Linux."""
    meminfo = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    available = int(meminfo["MemAvailable"].split()[0]) * 1024
    roots = [Path("/sys/fs/cgroup")]
    # A namespaced container reports '/', while an ordinary process may have a
    # delegated cgroup path. Check both without allowing '..' traversal.
    for line in Path("/proc/self/cgroup").read_text().splitlines():
        hierarchy, controllers, relative = line.split(":", 2)
        if ".." in Path(relative).parts:
            raise IsolationFault("headroom")
        if hierarchy == "0" and not controllers:
            roots.append(Path("/sys/fs/cgroup") / relative.lstrip("/"))
        elif "memory" in controllers.split(","):
            roots.append(Path("/sys/fs/cgroup/memory") / relative.lstrip("/"))
    for root in roots:
        for maximum, current in (("memory.max", "memory.current"), ("memory.limit_in_bytes", "memory.usage_in_bytes")):
            if (root / maximum).exists():
                value = (root / maximum).read_text().strip()
                if value != "max":
                    available = min(available, int(value) - int((root / current).read_text()))
    return max(0, available)


def _memory_budget():
    try:
        available = _memory_available()
    except IsolationFault:
        raise
    except (OSError, ValueError, KeyError):
        raise IsolationFault("headroom") from None
    address_space = min(ADDRESS_SPACE_BYTES, available - MEMORY_RESERVE_BYTES)
    if address_space < MIN_ADDRESS_SPACE_BYTES:
        raise IsolationFault("headroom", available, MIN_ADDRESS_SPACE_BYTES + MEMORY_RESERVE_BYTES)
    # Native mappings need virtual headroom too. The AS cap is also no larger
    # than current free container memory minus a parent/other-request reserve.
    rss = min(RSS_BYTES, address_space - 128 * 1024 * 1024)
    return address_space, rss


def isolation_ready():
    """PID-scoped, cached real-policy self-test; no Flask/DB/provider access."""
    global _READINESS
    if sys.platform != "linux":
        return False
    # An admitted operation already checked readiness. Do not reverse the
    # readiness-lock -> admission-lock order at a cache-expiry boundary.
    if getattr(_SLOT_LOCAL, "held", False) and _READINESS[0] == os.getpid():
        return _READINESS[2]
    now = time.monotonic()
    if _READINESS[0] == os.getpid() and now < _READINESS[1]:
        return _READINESS[2]
    with _READINESS_LOCK:
        now = time.monotonic()
        if _READINESS[0] == os.getpid() and now < _READINESS[1]:
            return _READINESS[2]
        try:
            with _analysis_slot():
                _cleanup_stale_directories()
                result = _run_child(stream_request("result=1", {}))
            if result.get("result_type") != "scalar" or result.get("value") != 1:
                raise IsolationFault("bootstrap_failed")
        except Exception as error:
            fault = error if isinstance(error, IsolationFault) else IsolationFault("bootstrap_failed")
            _report(fault)
            _unavailable()
            return False
        _READINESS = (os.getpid(), time.monotonic() + READINESS_SECONDS, True)
        return True


def _resident_bytes(pid):
    try:
        fields = Path(f"/proc/{pid}/statm").read_text().split()
        return int(fields[1]) * os.sysconf("SC_PAGE_SIZE")
    except FileNotFoundError:
        return 0


def _kill_and_wait(process):
    if process.returncode is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            if process.poll() is None:
                process.kill()
    process.wait()


def _exchange(process, payload, rss_limit):
    """Full-duplex bounded I/O; encode and release one input column at a time."""
    output = bytearray()
    errors = 0
    incoming = 0
    pending = memoryview(b"")
    chunks = iter([payload]) if isinstance(payload, bytes) else iter(payload)
    ready = False
    started = time.monotonic()
    bootstrap_seconds = 0
    peak_rss = 0
    deadline = started + STARTUP_SECONDS
    with selectors.DefaultSelector() as selector:
        for pipe in (process.stdout, process.stderr):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ)
        os.set_blocking(process.stdin.fileno(), False)
        while selector.get_map():
            resident = _resident_bytes(process.pid)
            peak_rss = max(peak_rss, resident)
            if time.monotonic() >= deadline:
                raise IsolationFault("deadline" if ready else "bootstrap_failed")
            if resident > rss_limit:
                raise IsolationFault("memory", resident, rss_limit)
            for key, _ in selector.select(timeout=min(0.025, max(0, deadline - time.monotonic()))):
                pipe = key.fileobj
                if pipe is process.stdin:
                    if not pending:
                        try:
                            chunk = next(chunks)
                        except StopIteration:
                            selector.unregister(pipe)
                            pipe.close()
                            continue
                        incoming += len(chunk)
                        if incoming > MAX_INPUT_BYTES:
                            raise IsolationFault("input_size", incoming, MAX_INPUT_BYTES)
                        pending = memoryview(chunk)
                    try:
                        written = os.write(pipe.fileno(), pending[:65536])
                        pending = pending[written:]
                    except BrokenPipeError:
                        raise IsolationFault("child_exit") from None
                    continue
                chunk = os.read(pipe.fileno(), 65536)
                if not chunk:
                    selector.unregister(pipe)
                    continue
                if pipe is process.stderr:
                    errors += len(chunk)
                    if errors > 65536:
                        raise IsolationFault("bad_output")
                    continue
                output.extend(chunk)
                if not ready and len(output) >= 6:
                    if output != b"READY\n":
                        raise IsolationFault("bootstrap_failed")
                    ready = True
                    bootstrap_seconds = time.monotonic() - started
                    output.clear()
                    deadline = time.monotonic() + WALL_SECONDS
                    selector.register(process.stdin, selectors.EVENT_WRITE)
                if len(output) > MAX_OUTPUT_BYTES:
                    raise IsolationFault("bad_output", len(output), MAX_OUTPUT_BYTES)
        remaining = deadline - time.monotonic()
        if not ready:
            raise IsolationFault("bootstrap_failed")
        if remaining <= 0:
            raise IsolationFault("deadline")
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            raise IsolationFault("deadline") from None
        if returncode != 0:
            raise IsolationFault("child_exit")
    try:
        result = decode_result(output)
    except AnalysisRefused:
        raise IsolationFault("bad_output") from None
    logger.info(
        "Analysis process finished bootstrap_ms=%.1f elapsed_ms=%.1f rss_bytes=%d input_bytes=%d output_bytes=%d",
        bootstrap_seconds * 1000,
        (time.monotonic() - started) * 1000,
        peak_rss,
        incoming,
        len(output),
    )
    return result


def _run_child(payload):
    if sys.platform != "linux":
        raise IsolationFault("bootstrap_failed")
    address_space, rss_limit = _memory_budget()
    with tempfile.TemporaryDirectory(prefix=f"aw-analysis-{os.getpid()}-") as directory:
        process = subprocess.Popen(
            [sys.executable, "-I", "-B", str(_WORKER), str(os.getpid()), str(address_space)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=directory,
            env={},
            close_fds=True,
            start_new_session=True,
        )
        try:
            return _exchange(process, payload, rss_limit)
        finally:
            _kill_and_wait(process)
            for pipe in (process.stdin, process.stdout, process.stderr):
                pipe.close()


def run_analysis(code, frames, display="table", description=""):
    from src.services.gol_availability import assistant_under_maintenance, maintenance_payload
    from src.services.gol_sandbox import MAX_CODE_CHARS

    if assistant_under_maintenance():
        return {"result_type": "error", **maintenance_payload()}
    if sys.platform != "linux":
        _report(IsolationFault("bootstrap_failed"))
        return {"result_type": "error", **maintenance_payload()}
    if code is None or (type(code) is str and not code.strip()):
        return {"result_type": "error", "error": "No code provided", "display": display}
    if type(code) is not str or len(code) > MAX_CODE_CHARS:
        return {"result_type": "error", "error": SIZE_ERROR if type(code) is str else ERROR, "display": display}
    try:
        with _analysis_slot():
            if assistant_under_maintenance():
                return {"result_type": "error", **maintenance_payload()}
            _memory_budget()
            # A service loader is invoked only after admission and headroom.
            supplied = frames() if callable(frames) else frames
            names = analysis_frame_names(code)
            selected = {name: frame for name, frame in supplied.items() if name in names}
            if assistant_under_maintenance():
                return {"result_type": "error", **maintenance_payload()}
            result = _run_child(stream_request(code, selected))
    except AnalysisSizeLimit as fault:
        _report(
            IsolationFault(
                "input_size", getattr(fault, "measured", 0), getattr(fault, "limit", 0), getattr(fault, "unit", "bytes")
            )
        )
        result = {"result_type": "error", "error": SIZE_ERROR}
    except IsolationFault as fault:
        _report(fault)
        if fault.reason == "bootstrap_failed":
            _unavailable()
            result = {"result_type": "error", **maintenance_payload()}
        else:
            result = {
                "result_type": "error",
                "error": TIME_ERROR
                if fault.reason == "deadline"
                else BUSY_ERROR
                if fault.reason == "busy"
                else SIZE_ERROR
                if fault.reason in {"input_size", "memory", "headroom"}
                else ERROR,
            }
    except AnalysisRefused:
        _report(IsolationFault("input_validation"))
        result = {"result_type": "error", "error": ERROR}
    except Exception:
        _report(IsolationFault("bootstrap_failed"))
        _unavailable()
        result = {"result_type": "error", **maintenance_payload()}
    result["display"] = display
    if description and result["result_type"] != "error":
        result["meta"] = {"description": description}
    return result
