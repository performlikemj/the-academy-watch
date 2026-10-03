"""Parent supervisor for single-use analysis children and capped plain-data pipes."""

import ctypes
import errno
import fcntl
import hashlib
import logging
import os
import selectors
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from src.services.gol_capabilities import ERROR, SIZE_ERROR, AnalysisRefused, AnalysisSizeLimit
from src.services.gol_process_policy import RSS_BYTES
from src.services.gol_wire import MAX_OUTPUT_BYTES, decode_result, encode_request

logger = logging.getLogger(__name__)
STARTUP_SECONDS = 10
WALL_SECONDS = 10
_WORKER = Path(__file__).with_name("gol_analysis_worker.py")
SLOT_WAIT_SECONDS = 30
_SLOT_FILE = Path(tempfile.gettempdir()) / (
    "aw-analysis-slot-" + hashlib.sha256(str(Path(__file__).resolve()).encode()).hexdigest()[:16]
)


@contextmanager
def _analysis_slot():
    """One memory-intensive analysis per container, shared by Gunicorn workers."""
    descriptor = os.open(_SLOT_FILE, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        status = os.fstat(descriptor)
        if status.st_uid != os.getuid() or status.st_mode & 0o077:
            raise AnalysisRefused(ERROR)
        deadline = time.monotonic() + SLOT_WAIT_SECONDS
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise AnalysisRefused(ERROR) from None
                time.sleep(0.025)
        yield
    finally:
        os.close(descriptor)


if sys.platform == "darwin":

    class _TaskInfo(ctypes.Structure):
        _fields_ = [
            ("virtual_size", ctypes.c_uint64),
            ("resident_size", ctypes.c_uint64),
            ("total_user", ctypes.c_uint64),
            ("total_system", ctypes.c_uint64),
            ("threads_user", ctypes.c_uint64),
            ("threads_system", ctypes.c_uint64),
        ] + [
            (name, ctypes.c_int32)
            for name in (
                "policy",
                "faults",
                "pageins",
                "cow_faults",
                "messages_sent",
                "messages_received",
                "syscalls_mach",
                "syscalls_unix",
                "csw",
                "threadnum",
                "numrunning",
                "priority",
            )
        ]

    _LIBPROC = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)


def _resident_bytes(pid):
    if sys.platform == "linux":
        try:
            fields = Path(f"/proc/{pid}/statm").read_text().split()
            return int(fields[1]) * os.sysconf("SC_PAGE_SIZE")
        except FileNotFoundError:
            return 0
    if sys.platform == "darwin":
        info = _TaskInfo()
        count = _LIBPROC.proc_pidinfo(pid, 4, 0, ctypes.byref(info), ctypes.sizeof(info))
        if count == ctypes.sizeof(info):
            return info.resident_size
        if count == 0 and ctypes.get_errno() in (0, errno.ESRCH):
            return 0
    raise RuntimeError("Analysis isolation unavailable")


def _kill_and_wait(process):
    # start_new_session owns this process group. Killing it also covers cleanup
    # if a future bootstrap library ever starts a helper before policy setup.
    if process.returncode is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            if process.poll() is None:
                process.kill()
    process.wait()


def _exchange(process, payload):
    """Nonblocking full-duplex I/O keeps output, memory and wall limits bounded."""
    output = bytearray()
    errors = 0
    sent = 0
    ready = False
    started = time.monotonic()
    bootstrap_seconds = 0
    peak_rss = 0
    deadline = time.monotonic() + STARTUP_SECONDS
    with selectors.DefaultSelector() as selector:
        for pipe in (process.stdout, process.stderr):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ)
        os.set_blocking(process.stdin.fileno(), False)
        while selector.get_map():
            resident = _resident_bytes(process.pid)
            peak_rss = max(peak_rss, resident)
            if time.monotonic() >= deadline or resident > RSS_BYTES:
                raise AnalysisRefused(ERROR)
            for key, _ in selector.select(timeout=min(0.025, max(0, deadline - time.monotonic()))):
                pipe = key.fileobj
                if pipe is process.stdin:
                    try:
                        sent += os.write(pipe.fileno(), memoryview(payload)[sent : sent + 65536])
                    except BrokenPipeError:
                        raise AnalysisRefused(ERROR) from None
                    if sent == len(payload):
                        selector.unregister(pipe)
                        pipe.close()
                    continue
                chunk = os.read(pipe.fileno(), 65536)
                if not chunk:
                    selector.unregister(pipe)
                    continue
                if pipe is process.stderr:
                    errors += len(chunk)
                    if errors > 65536:
                        raise AnalysisRefused(ERROR)
                    continue
                output.extend(chunk)
                if not ready and len(output) >= 6:
                    if output != b"READY\n":
                        raise AnalysisRefused(ERROR)
                    ready = True
                    bootstrap_seconds = time.monotonic() - started
                    output.clear()
                    deadline = time.monotonic() + WALL_SECONDS
                    selector.register(process.stdin, selectors.EVENT_WRITE)
                if len(output) > MAX_OUTPUT_BYTES:
                    raise AnalysisRefused(ERROR)
        remaining = deadline - time.monotonic()
        if not ready or remaining <= 0 or process.wait(timeout=remaining) != 0:
            raise AnalysisRefused(ERROR)
    result = decode_result(output)
    logger.info(
        "Analysis process finished bootstrap_ms=%.1f elapsed_ms=%.1f rss_bytes=%d input_bytes=%d output_bytes=%d",
        bootstrap_seconds * 1000,
        (time.monotonic() - started) * 1000,
        peak_rss,
        len(payload),
        len(output),
    )
    return result


def _run_child(payload):
    with tempfile.TemporaryDirectory(prefix="aw-analysis-") as directory:
        process = subprocess.Popen(
            [sys.executable, "-I", "-B", str(_WORKER), str(os.getpid())],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=directory,
            env={},
            close_fds=True,
            start_new_session=True,
        )
        try:
            return _exchange(process, payload)
        finally:
            _kill_and_wait(process)
            for pipe in (process.stdin, process.stdout, process.stderr):
                pipe.close()


def run_analysis(code, frames, display="table", description=""):
    # This direct entry point preserves the service's early maintenance check.
    from src.services.gol_availability import assistant_under_maintenance, maintenance_payload
    from src.services.gol_sandbox import MAX_CODE_CHARS

    if assistant_under_maintenance():
        return {"result_type": "error", **maintenance_payload()}
    if code is None or (type(code) is str and not code.strip()):
        return {"result_type": "error", "error": "No code provided", "display": display}
    if type(code) is not str or len(code) > MAX_CODE_CHARS:
        return {"result_type": "error", "error": SIZE_ERROR if type(code) is str else ERROR, "display": display}
    try:
        with _analysis_slot():
            if assistant_under_maintenance():
                return {"result_type": "error", **maintenance_payload()}
            payload = encode_request(code, frames)
            if assistant_under_maintenance():
                return {"result_type": "error", **maintenance_payload()}
            result = _run_child(payload)
    except AnalysisSizeLimit:
        result = {"result_type": "error", "error": SIZE_ERROR}
    except Exception:
        logger.info("Analysis process unavailable or refused")
        result = {"result_type": "error", "error": ERROR}
    result["display"] = display
    if description and result["result_type"] != "error":
        result["meta"] = {"description": description}
    return result
