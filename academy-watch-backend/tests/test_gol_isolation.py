"""Process isolation for the analysis tool: parity, platform policy and lifecycle."""

import ctypes
import json
import os
import signal
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from src.services import gol_isolation as isolation
from src.services import gol_sandbox as sandbox
from src.services.gol_capabilities import ERROR, AnalysisRefused
from src.services.gol_wire import decode_request, decode_result, encode_request
from test_gol_sandbox import LEGITIMATE, ORDINARY, WINDOW_CORPUS
from test_gol_sandbox import frames as reference_frames


@pytest.fixture
def frames():
    return reference_frames.__wrapped__()


PROCESS_CORPUS = (
    LEGITIMATE
    + ORDINARY
    + [
        (f"{window}_{name}", f"result=fixture_stats['goals'].{window}.{call}")
        for window in ("rolling(5)", "expanding()")
        for name, call in WINDOW_CORPUS
    ]
)


@pytest.fixture
def children(monkeypatch):
    records = []
    popen = subprocess.Popen

    def record(*args, **kwargs):
        child = popen(*args, **kwargs)
        records.append((child, kwargs))
        return child

    monkeypatch.setattr(isolation.subprocess, "Popen", record)
    yield records
    for child, arguments in records:
        assert child.poll() is not None
        assert child.wait() == child.returncode
        assert not Path(arguments["cwd"]).exists()
        with pytest.raises(ChildProcessError):
            os.waitpid(child.pid, os.WNOHANG)


def _probe_worker(tmp_path, monkeypatch, body, cpu=10):
    """Tests alone replace the worker with trusted code after the real OS policy.

    This bypasses the first layer to exercise the independent platform boundary.
    No alternate execution mode or test switch is shipped in the worker.
    """
    backend = Path(__file__).resolve().parents[1]
    worker = tmp_path / "policy_probe.py"
    worker.write_text(
        f"""import os, sys, json, resource, socket, time
sys.path.insert(0, {str(backend)!r})
from src.services.gol_process_policy import set_limits, install_policy
set_limits(cpu_seconds={cpu})
INITIAL_LIMITS={{'AS':resource.getrlimit(resource.RLIMIT_AS)}}
os.environ.clear()
install_policy()
sys.stdout.write('READY\\n')
sys.stdout.flush()
sys.stdin.buffer.read()
{body}
"""
    )
    monkeypatch.setattr(isolation, "_WORKER", worker)


@pytest.mark.parametrize("name,code", PROCESS_CORPUS, ids=[name for name, _ in PROCESS_CORPUS])
def test_process_ordinary_analysis_parity(name, code, frames):
    expected = sandbox._execute_analysis(code, frames)
    assert expected["result_type"] != "error", name
    actual = isolation._run_child(encode_request(code, frames))
    assert actual == expected


def test_plain_frame_transport():
    frame = pd.DataFrame(
        {
            "numbers": pd.Series([np.inf, np.nan, -np.inf]),
            "objects": pd.Series([[1, 2], {"name": "Alpha"}, (3, 4)], dtype=object),
            "nullable": pd.Series([1, pd.NA, 3], dtype="Int64"),
            "text": pd.Series(["Alpha", None, "Bravo"], dtype="str"),
            "category": pd.Categorical(["A", "B", "A"], ordered=True),
            "clock": pd.date_range("2026-01-01", periods=3, tz="Europe/London"),
        }
    )
    frame.index = pd.MultiIndex.from_tuples([(1, "A"), (2, "B"), (3, "C")], names=["id", "label"])
    code, decoded = decode_request(encode_request("result=df", {"df": frame}))
    assert code == "result=df"
    pd.testing.assert_frame_equal(decoded["df"], frame)
    assert isolation._run_child(encode_request(code, decoded)) == sandbox._execute_analysis(code, decoded)


def test_environment_and_runtime_are_empty(tmp_path, monkeypatch, children):
    monkeypatch.setenv("AW_ANALYSIS_PLANTED", "fixture-value")
    # Copy the real bootstrap; only its final trusted test result is substituted.
    worker = tmp_path / "runtime_probe.py"
    source = (
        isolation._WORKER.read_text()
        .replace(
            "sys.path.insert(0, str(Path(__file__).resolve().parents[2]))",
            f"sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})",
        )
        .replace(
            "result = _execute_analysis(code, frames)",
            "result={'result_type':'dict','data':{'environment':dict(os.environ),"
            "'application':any(name.startswith(('flask','sqlalchemy','src.models')) for name in sys.modules)}}",
        )
    )
    worker.write_text(source)
    monkeypatch.setattr(isolation, "_WORKER", worker)
    assert isolation._run_child(encode_request("result=1", {}))["data"] == {"environment": {}, "application": False}
    assert children[0][1]["env"] == {}
    assert children[0][1]["close_fds"] is True


def test_filesystem_and_network_policy_independent_of_first_layer(tmp_path, monkeypatch, children):
    outside = tmp_path / "outside.txt"
    outside.write_text("fixture-value")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        # The same connection succeeds outside the child policy.
        with socket.socket() as control:
            control.connect(("127.0.0.1", port))
        _probe_worker(
            tmp_path,
            monkeypatch,
            f"""results={{}}
for name, operation in [
 ('outside', lambda:open({str(outside)!r}).read()),
 ('write', lambda:open('new.txt','w').write('fixture-value')),
 ('network', lambda:socket.socket(socket.AF_INET,socket.SOCK_STREAM).connect(('127.0.0.1',{port}))),
 ('process', lambda:os.fork()),
]:
 try:
  operation()
  results[name]=False
 except OSError as error:
  results[name]=error.errno in (1,13)
sys.stdout.write(json.dumps({{'result_type':'dict','data':results}}))
""",
        )
        assert isolation._run_child(b"")["data"] == {"outside": True, "write": True, "network": True, "process": True}


def test_no_inherited_descriptor(tmp_path, monkeypatch, children):
    outside = tmp_path / "descriptor.txt"
    outside.write_text("fixture-value")
    with outside.open() as handle:
        descriptor = handle.fileno()
        os.set_inheritable(descriptor, True)
        _probe_worker(
            tmp_path,
            monkeypatch,
            f"""try:
 os.read({descriptor},1)
 value=False
except OSError:
 value=True
sys.stdout.write(json.dumps({{'result_type':'scalar','value':value}}))
""",
        )
        assert isolation._run_child(b"")["value"] is True


@pytest.mark.parametrize("body", ["os._exit(7)", "sys.stdout.write('invalid')", "sys.stdout.write('x'*3000000)"])
def test_crash_or_malformed_output_is_neutral(tmp_path, monkeypatch, children, body):
    _probe_worker(tmp_path, monkeypatch, body)
    with pytest.raises(AnalysisRefused, match=ERROR):
        isolation._run_child(b"")
    # The public parent mapping retains the existing neutral error.
    monkeypatch.setenv("GOL_MAINTENANCE", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-provider")
    assert sandbox.execute_analysis("result=1", {})["error"] == ERROR


def test_wall_limit_hard_kills_and_reaps(tmp_path, monkeypatch, children):
    _probe_worker(tmp_path, monkeypatch, "while True: time.sleep(1)")
    monkeypatch.setattr(isolation, "WALL_SECONDS", 0.15)
    started = time.monotonic()
    with pytest.raises(AnalysisRefused):
        isolation._run_child(b"")
    assert children[0][0].returncode == -signal.SIGKILL
    assert time.monotonic() - started < 5


def test_cpu_limit_hard_kills_and_reaps(tmp_path, monkeypatch, children):
    _probe_worker(tmp_path, monkeypatch, "while True: pass", cpu=1)
    monkeypatch.setattr(isolation, "WALL_SECONDS", 8)
    with pytest.raises(AnalysisRefused):
        isolation._run_child(b"")
    assert children[0][0].returncode in {-signal.SIGKILL, -signal.SIGXCPU}


def test_memory_limit_hard_kills_and_reaps(tmp_path, monkeypatch, children):
    _probe_worker(tmp_path, monkeypatch, "blocks=[]\nwhile True: blocks.append(bytearray(8*1024*1024))")
    monkeypatch.setattr(isolation, "RSS_BYTES", 64 * 1024 * 1024)
    with pytest.raises(AnalysisRefused):
        isolation._run_child(b"")
    assert children[0][0].returncode == -signal.SIGKILL


@pytest.mark.skipif(os.uname().sysname != "Linux", reason="Linux address-space policy")
def test_linux_address_space_limit(tmp_path, monkeypatch, children):
    _probe_worker(
        tmp_path,
        monkeypatch,
        """limits=INITIAL_LIMITS['AS']
try:
 bytearray(limits[0]+1)
 value=False
except MemoryError:
 value=True
sys.stdout.write(json.dumps({'result_type':'scalar','value':value}))
""",
    )
    assert isolation._run_child(b"")["value"] is True


@pytest.mark.skipif(os.uname().sysname != "Linux", reason="Linux parent lifecycle policy")
def test_linux_parent_exit_kills_and_reaps_worker(tmp_path, monkeypatch):
    _probe_worker(tmp_path, monkeypatch, "time.sleep(3600)")
    worker = isolation._WORKER
    # Adopt the temporary parent's child so this test can reap it itself.
    libc = ctypes.CDLL(None, use_errno=True)
    prior = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(prior), 0, 0, 0) == 0  # PR_GET_CHILD_SUBREAPER
    assert libc.prctl(36, 1, 0, 0, 0) == 0  # PR_SET_CHILD_SUBREAPER
    child_pid = None
    parent = subprocess.Popen(
        [
            os.sys.executable,
            "-I",
            "-B",
            "-c",
            "import subprocess,sys,time; "
            f"child=subprocess.Popen([sys.executable,'-I','-B',{str(worker)!r}],stdin=subprocess.PIPE,stdout=subprocess.PIPE); "
            "assert child.stdout.readline()==b'READY\\n'; "
            "print(child.pid,flush=True); time.sleep(3600)",
        ],
        stdout=subprocess.PIPE,
    )
    try:
        child_pid = int(parent.stdout.readline())
        parent.kill()
        parent.wait()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            done, status = os.waitpid(child_pid, os.WNOHANG)
            if done:
                assert os.waitstatus_to_exitcode(status) == -signal.SIGKILL
                child_pid = None
                break
            time.sleep(0.025)
        assert child_pid is None, "Analysis worker survived its parent"
    finally:
        if parent.poll() is None:
            parent.kill()
        parent.wait()
        parent.stdout.close()
        if child_pid is not None:
            os.kill(child_pid, signal.SIGKILL)
            os.waitpid(child_pid, 0)
        assert libc.prctl(36, prior.value, 0, 0, 0) == 0


def test_concurrent_requests_have_distinct_children_and_directories(frames, children):
    payload = encode_request("result=teams", frames)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(isolation._run_child, [payload, payload]))
    assert results[0] == results[1]
    assert len({child.pid for child, _ in children}) == 2
    assert len({arguments["cwd"] for _, arguments in children}) == 2


def test_public_requests_share_memory_admission_only(frames, children, monkeypatch, tmp_path):
    monkeypatch.setenv("GOL_MAINTENANCE", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-provider")
    monkeypatch.setattr(isolation, "_SLOT_FILE", tmp_path / "admission")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: sandbox.execute_analysis("result=teams", frames), range(2)))
    assert results[0] == results[1]
    assert results[0]["result_type"] == "table"
    assert len({child.pid for child, _ in children}) == 2


def test_slot_timeout_never_starts_child(monkeypatch, tmp_path):
    monkeypatch.setenv("GOL_MAINTENANCE", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-provider")
    monkeypatch.setattr(isolation, "_SLOT_FILE", tmp_path / "admission")
    monkeypatch.setattr(isolation, "SLOT_WAIT_SECONDS", 0.05)
    monkeypatch.setattr(isolation.subprocess, "Popen", lambda *a, **kw: pytest.fail("Started while slot held"))
    with isolation._analysis_slot():
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(sandbox.execute_analysis, "result=1", {}).result()
    assert result["error"] == ERROR


@pytest.mark.parametrize("text", ["6.50", "6.123456", "NaN", "sNaN", "Infinity", "-Infinity", "1e9999"])
def test_process_decimal_parity(text):
    frames = {"df": pd.DataFrame({"rating": pd.Series([Decimal(text), None], dtype=object)})}
    assert isolation._run_child(encode_request("result=df", frames)) == sandbox._execute_analysis("result=df", frames)


@pytest.mark.parametrize(
    "value,code",
    [
        (np.float64(1.23456789), "result=int(df.loc[0,'value'].item()*10000000)"),
        (pd.Timestamp("2026-07-01", tz="Europe/London"), "result=df.loc[0,'value'].strftime('%Z')"),
    ],
)
def test_process_object_scalars_keep_analysis_semantics(value, code):
    frames = {"df": pd.DataFrame({"value": pd.Series([value], dtype=object)})}
    _, decoded = decode_request(encode_request(code, frames))
    pd.testing.assert_frame_equal(decoded["df"], frames["df"])
    assert isolation._run_child(encode_request(code, frames)) == sandbox._execute_analysis(code, frames)


@pytest.mark.parametrize("rows", [100_000, 200_000])
@pytest.mark.parametrize(
    "code",
    [
        "result=df",
        "result=df[df.goals>3]",
        "result=df.goals.map(lambda value:value+1)",
        "result=df.apply(lambda row:row.goals+row.minutes,axis=1)",
    ],
)
def test_process_production_size_parity(rows, code):
    frames = {
        "df": pd.DataFrame(
            {
                **{f"c{i}": np.arange(rows) for i in range(25)},
                "goals": np.arange(rows) % 10,
                "minutes": np.arange(rows),
                "club": pd.Series(["Club"] * rows, dtype="str"),
                "when": pd.date_range("2026-01-01", periods=rows, freq="s"),
            }
        )
    }
    assert isolation._run_child(encode_request(code, frames)) == sandbox._execute_analysis(code, frames)


def test_maintenance_never_starts_child(monkeypatch):
    from src.services.gol_service import GolService

    monkeypatch.setenv("GOL_MAINTENANCE", "true")
    monkeypatch.setattr(isolation.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Started analysis child"))
    assert sandbox.execute_analysis("result=1", {})["error"] == "maintenance"
    assert GolService.__new__(GolService)._execute_tool("run_analysis", {"code": "result=1"})["error"] == "maintenance"


def test_policy_setup_failure_never_executes_analysis(tmp_path, monkeypatch, children):
    monkeypatch.setenv("GOL_MAINTENANCE", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-provider")
    monkeypatch.setattr(sandbox, "_execute_analysis", lambda *a, **kw: pytest.fail("Executed in parent"))
    worker = tmp_path / "unavailable_policy.py"
    worker.write_text("import sys\nsys.exit(1)\n")
    monkeypatch.setattr(isolation, "_WORKER", worker)
    with pytest.raises(AnalysisRefused):
        isolation._run_child(b"")
    assert sandbox.execute_analysis("result=1", {})["error"] == ERROR


@pytest.mark.parametrize(
    "result",
    [
        {"result_type": "table", "columns": ["x"], "rows": [[1, 2]], "total_rows": 1, "truncated": False},
        {"result_type": "dict", "data": []},
        {"result_type": "list", "items": list(range(101))},
        {"result_type": "scalar"},
        {"result_type": "unknown"},
        {"result_type": "error", "error": "Unrecognised error"},
        {"result_type": "scalar", "value": 1, "extra": 2},
        {"result_type": "scalar", "value": {"extra": 2}},
    ],
)
def test_parent_revalidates_result_shape(result):
    with pytest.raises(AnalysisRefused):
        decode_result(json.dumps(result).encode())


def test_parent_normalizes_nonfinite_json_numbers():
    assert decode_result(b'{"result_type":"scalar","value":1e9999}')["value"] is None
