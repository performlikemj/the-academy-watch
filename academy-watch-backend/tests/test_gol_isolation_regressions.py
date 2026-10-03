"""Process isolation for the analysis tool: review parity and operational controls."""

import io
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import numpy as np
import pandas as pd
import pytest
from gol_plain_shape_cases import generated_cases
from src.services import gol_availability as availability
from src.services import gol_isolation as isolation
from src.services import gol_sandbox as sandbox
from src.services.gol_capabilities import ERROR, SIZE_ERROR, AnalysisRefused, validate_frame
from src.services.gol_dataframes import DataFrameCache
from src.services.gol_scope import HELPER_FRAMES, analysis_frame_names
from src.services.gol_wire import decode_request, encode_request, read_request, stream_request
from test_gol_isolation import _probe_worker, linux_policy
from test_gol_isolation import children as _children_fixture
from test_gol_sandbox import frames as reference_frames

children = _children_fixture
REAL_READINESS = isolation.isolation_ready


@pytest.fixture(autouse=True)
def known_unit_readiness(monkeypatch, tmp_path):
    monkeypatch.setattr(isolation, "_SLOT_FILE", tmp_path / "slot")
    monkeypatch.setenv("GOL_MAINTENANCE", "false")
    monkeypatch.setenv("GOL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    monkeypatch.setattr(isolation, "_READINESS", (os.getpid(), time.monotonic() + 600, True))


def shape_cases():
    cases = []
    for frequency in ("D", "2h", "ME"):
        cases.append(
            (
                f"datetime_{frequency}",
                pd.DataFrame({"x": [1, 2]}, index=pd.date_range("2026-01-01", periods=2, freq=frequency)),
            )
        )
    for frequency in ("2s", "D"):
        cases.append(
            (
                f"timedelta_{frequency}",
                pd.DataFrame({"x": [1, 2]}, index=pd.timedelta_range("1s", periods=2, freq=frequency)),
            )
        )
    for values in (
        [timedelta(days=1, seconds=5), timedelta(microseconds=-1)],
        [timedelta(days=999_999_999), timedelta(days=-999_999_999)],
        [pd.Timedelta(1, unit="s"), pd.Timedelta(2, unit="s")],
        [date(2026, 1, 1), None],
        [datetime(2026, 1, 1), None],
        [datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=9, minutes=30))), None],
        [Decimal("6.123456789"), Decimal("NaN")],
        [[1, 2], {"value": (3, 4)}],
        [2**100, None],
        [None, np.nan],
    ):
        cases.append((f"object_{len(cases)}", pd.DataFrame({"x": pd.Series(values, dtype=object)})))
    for dtype in (
        "int8",
        "int16",
        "int32",
        "int64",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
        "float16",
        "float32",
        "float64",
        ">i8",
        np.dtype(np.longdouble).name,
    ):
        cases.append((f"numpy_{dtype}", pd.DataFrame({"x": np.array([1, 2], dtype=dtype)})))
    for dtype in (
        "Int8",
        "Int16",
        "Int32",
        "Int64",
        "UInt8",
        "UInt16",
        "UInt32",
        "UInt64",
        "Float32",
        "Float64",
        "boolean",
        "string",
        "str",
    ):
        values = ["A", None] if dtype in ("string", "str") else [True, None] if dtype == "boolean" else [1, None]
        cases.append((f"nullable_{dtype}", pd.DataFrame({"x": pd.Series(values, dtype=dtype)})))
    for unit in ("s", "ms", "us", "ns"):
        for base in ("datetime64", "timedelta64"):
            cases.append((f"{base}_{unit}", pd.DataFrame({"x": np.array([0, 1], dtype=f"{base}[{unit}]")})))
    cases.extend(
        [
            (
                "category",
                pd.DataFrame({"x": pd.Categorical(["A", None], categories=["B", "A", "unused"], ordered=True)}),
            ),
            ("period", pd.DataFrame({"x": pd.period_range("2026-01", periods=2, freq="M")})),
            ("interval", pd.DataFrame({"x": pd.arrays.IntervalArray.from_tuples([(0, 1), (1, 2)])})),
            ("empty", pd.DataFrame({"x": pd.Series([], dtype="Int64")})),
            ("duplicate", pd.DataFrame([[1, 2]], columns=["x", "x"])),
            ("multicolumn", pd.DataFrame([[1, 2]], columns=pd.MultiIndex.from_tuples([("A", 1), ("B", 2)]))),
            (
                "multilevel_frequency",
                pd.DataFrame(
                    {"x": [1, 2]},
                    index=pd.MultiIndex.from_product([pd.date_range("2026-01-01", periods=2, freq="D"), ["A"]]),
                ),
            ),
            (
                "fixed_zone",
                pd.DataFrame(
                    {"x": pd.date_range("2026-01-01", periods=2, tz=timezone(timedelta(hours=9, minutes=30)))}
                ),
            ),
            ("named_zone", pd.DataFrame({"x": pd.date_range("2026-03-28", periods=2, tz="Europe/London")})),
        ]
    )
    return cases


SHAPES = shape_cases()
GENERATED_SHAPES = generated_cases()


def _shape_analyses(row, frame):
    if row.domain == "timezone":
        if isinstance(frame.index, pd.DatetimeIndex):
            return ["result=df.index.strftime('%Z %z').tolist()", "result=df.index.to_period().astype(str).tolist()"]
        if type(frame.x.dtype) is pd.DatetimeTZDtype:
            return ["result=df.x.dt.strftime('%Z %z').tolist()", "result=df"]
        return ["result=df.loc[0,'x'].strftime('%Z %z')", "result=repr(df.loc[0,'x'])", "result=df"]
    if row.domain == "value" and row.name == "none":
        return ["result=[df.loc[0,'x']]", "result=df"]
    if row.domain == "value":
        return ["result=df.loc[0,'x']", "result=repr(df.loc[0,'x'])", "result=df"]
    if row.name == np.dtype(np.longdouble).name and np.longdouble is not np.float64:
        return ["result=len(df)"]  # Extended dtype is admitted; extended scalar output is refused.
    if row.domain == "index" and row.name == "index":
        return ["result=len(df)", "result=df.index.tolist()"]
    return ["result=df.x"] if row.domain == "frame" and row.name == "series" else ["result=df", "result=len(df)"]


def _assert_exact_plain_frame(expected, actual):
    from src.services.gol_wire import _encode_value

    # Pandas equality cannot compare ragged nested containers or nested NaN.
    # Compare their exact fixed-tag trees, and pandas schema/other cells normally.
    left, right = expected.copy(), actual.copy()
    for i, dtype in enumerate(expected.dtypes):
        if dtype == np.dtype("object"):
            for original, carried in zip(expected.iloc[:, i], actual.iloc[:, i], strict=True):
                assert type(original) is type(carried)
                assert _encode_value(original) == _encode_value(carried)
            left.isetitem(i, expected.iloc[:, i].map(lambda value: json.dumps(_encode_value(value))))
            right.isetitem(i, actual.iloc[:, i].map(lambda value: json.dumps(_encode_value(value))))
    if type(expected.index) is pd.Index and expected.index.dtype == np.dtype("object"):
        for original, carried in zip(expected.index, actual.index, strict=True):
            assert type(original) is type(carried)
            assert _encode_value(original) == _encode_value(carried)
        left.index = pd.Index(
            [json.dumps(_encode_value(value)) for value in expected.index], dtype=object, name=expected.index.name
        )
        right.index = pd.Index(
            [json.dumps(_encode_value(value)) for value in actual.index], dtype=object, name=actual.index.name
        )
    pd.testing.assert_frame_equal(left, right, check_exact=True)
    assert _encode_value(expected.attrs) == _encode_value(actual.attrs)


@pytest.mark.parametrize("name,row,frame", GENERATED_SHAPES, ids=[name for name, _, _ in GENERATED_SHAPES])
def test_generated_admission_table_roundtrip_and_results(name, row, frame):
    validate_frame(frame)
    payload = b"".join(stream_request("result=df", {"df": frame}))
    for decoded in (
        decode_request(encode_request("result=df", {"df": frame}))[1],
        read_request(io.BytesIO(payload))[1],
    ):
        _assert_exact_plain_frame(frame, decoded["df"])
        for code in _shape_analyses(row, frame):
            expected = sandbox._execute_analysis(code, {"df": frame})
            assert sandbox._execute_analysis(code, decoded) == expected


@linux_policy
@pytest.mark.parametrize("name,row,frame", GENERATED_SHAPES, ids=[name for name, _, _ in GENERATED_SHAPES])
def test_generated_admission_table_linux_results(name, row, frame):
    for code in _shape_analyses(row, frame):
        expected = sandbox._execute_analysis(code, {"df": frame})
        assert isolation._run_child(stream_request(code, {"df": frame})) == expected


@pytest.mark.parametrize("name,frame", SHAPES, ids=[name for name, _ in SHAPES])
def test_plain_shape_roundtrip_and_trusted_reference(name, frame):
    validate_frame(frame)
    for code in ("result=df", "result=len(df)"):
        _, legacy = decode_request(encode_request(code, {"df": frame}))
        _, streamed = read_request(io.BytesIO(b"".join(stream_request(code, {"df": frame}))))
        pd.testing.assert_frame_equal(frame, legacy["df"])
        pd.testing.assert_frame_equal(frame, streamed["df"])
        expected = sandbox._execute_analysis(code, {"df": frame})
        assert sandbox._execute_analysis(code, streamed) == expected


@linux_policy
@pytest.mark.parametrize("name,frame", SHAPES, ids=[name for name, _ in SHAPES])
def test_linux_shape_process_parity(name, frame):
    code = "result=len(df)" if name.startswith("numpy_float128") else "result=df"
    assert isolation._run_child(stream_request(code, {"df": frame})) == sandbox._execute_analysis(code, {"df": frame})


@linux_policy
@pytest.mark.parametrize(
    "frame,code",
    [
        (
            pd.DataFrame({"x": [1, 2]}, index=pd.date_range("2026-01-01", periods=2, freq="D")),
            "result=df.index.to_period().astype(str).tolist()",
        ),
        (pd.DataFrame({"x": pd.Series([timedelta(days=1, seconds=5)], dtype=object)}), "result=df.loc[0,'x']"),
        (pd.DataFrame({"x": pd.Series([timedelta(days=1, seconds=5)], dtype=object)}), "result=df"),
    ],
)
def test_review_temporal_operations(frame, code):
    expected = sandbox._execute_analysis(code, {"df": frame})
    assert expected["result_type"] != "error"
    assert isolation._run_child(stream_request(code, {"df": frame})) == expected


@pytest.mark.parametrize("value", [UUID(int=1), b"x", {1, 2}, complex(1, 2), datetime(2026, 1, 1).time()])
def test_uncarried_objects_are_refused_by_both_paths(value):
    frame = pd.DataFrame({"x": pd.Series([value], dtype=object)})
    assert sandbox._execute_analysis("result=len(df)", {"df": frame})["error"] == ERROR
    with pytest.raises(AnalysisRefused):
        encode_request("result=len(df)", {"df": frame})


def test_custom_frequency_refused_by_both_paths():
    frame = pd.DataFrame(
        {"x": [1, 2]},
        index=pd.date_range("2026-01-01", periods=2, freq=pd.offsets.CustomBusinessDay(holidays=["2026-01-02"])),
    )
    assert sandbox._execute_analysis("result=len(df)", {"df": frame})["error"] == ERROR
    with pytest.raises(AnalysisRefused):
        encode_request("result=len(df)", {"df": frame})


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_unsupported_platform_refuses_without_starting_or_installing_policy(platform, monkeypatch):
    from src.services import gol_process_policy as policy

    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(isolation, "isolation_ready", REAL_READINESS)
    monkeypatch.setattr(
        isolation.subprocess, "Popen", lambda *a, **kw: pytest.fail("Unsupported platform started a child")
    )
    assert REAL_READINESS() is False
    assert availability.assistant_under_maintenance() is True
    assert sandbox.execute_analysis("result=1", {})["error"] == "maintenance"
    with pytest.raises(isolation.IsolationFault):
        isolation._run_child(b"")
    with pytest.raises(RuntimeError):
        policy.set_limits()
    with pytest.raises(RuntimeError):
        policy.install_policy()


@linux_policy
def test_child_cannot_signal_disposable_sibling(tmp_path, monkeypatch, children):
    sibling = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(60)"])
    try:
        _probe_worker(
            tmp_path,
            monkeypatch,
            f"""
import signal
try:
 os.kill({sibling.pid},signal.SIGTERM)
 signal_denied=False
except PermissionError:
 signal_denied=True
sys.stdout.write(json.dumps({{'result_type':'dict','data':{{'signal':signal_denied}}}}))
""",
        )
        result = isolation._run_child(b"")
        assert result["data"] == {"signal": True}
        assert sibling.poll() is None
    finally:
        sibling.kill()
        sibling.wait()


@linux_policy
@pytest.mark.parametrize("step", ["landlock", "seccomp"])
def test_real_policy_failure_warns_and_pauses_before_input(step, tmp_path, monkeypatch, caplog, children):
    backend = Path(__file__).resolve().parents[1]
    source = isolation._WORKER.read_text().replace(
        "sys.path.insert(0, str(Path(__file__).resolve().parents[2]))",
        f"sys.path.insert(0, {str(backend)!r})",
    )
    injection = f"""
    import ctypes
    from src.services import gol_process_policy as policy
    original_cdll=ctypes.CDLL
    class DeniedCall:
        def __call__(self,*args):
            ctypes.set_errno(38 if {step!r}=='landlock' else 1)
            return -1
    class PolicyLibrary:
        def __init__(self,original):
            self.original=original
        def __getattr__(self,name):
            if {step!r}=='landlock' and name=='syscall':
                return DeniedCall()
            if {step!r}=='seccomp' and name=='seccomp_load':
                return DeniedCall()
            return getattr(self.original,name)
    def controlled_cdll(name,*args,**kwargs):
        original=original_cdll(name,*args,**kwargs)
        if (name is None and {step!r}=='landlock') or (name=='libseccomp.so.2' and {step!r}=='seccomp'):
            return PolicyLibrary(original)
        return original
    policy.ctypes.CDLL=controlled_cdll
    install_policy()
"""
    source = source.replace("    install_policy()", injection)
    worker = tmp_path / "policy_failure.py"
    worker.write_text(source)
    monkeypatch.setattr(isolation, "_WORKER", worker)
    monkeypatch.setattr(isolation, "isolation_ready", REAL_READINESS)
    monkeypatch.setattr(isolation, "_READINESS", (0, 0, False))
    caplog.set_level(logging.WARNING)
    assert REAL_READINESS() is False
    assert availability.assistant_under_maintenance() is True
    assert sandbox.execute_analysis("result=1", {})["error"] == "maintenance"
    assert len(children) == 1
    assert any(
        record.levelno == logging.WARNING and "reason=bootstrap_failed" in record.getMessage()
        for record in caplog.records
    )


@linux_policy
def test_readiness_is_pid_scoped_cached_and_skips_maintenance(monkeypatch, children):
    monkeypatch.setattr(isolation, "isolation_ready", REAL_READINESS)
    monkeypatch.setattr(isolation, "_READINESS", (0, 0, False))
    assert availability.assistant_under_maintenance() is False
    assert REAL_READINESS() is True
    assert len(children) == 1
    monkeypatch.setattr(isolation, "_READINESS", (-1, time.monotonic() + 600, True))
    assert REAL_READINESS() is True
    assert len(children) == 1  # Another worker can use recent trusted slot evidence.
    monkeypatch.setenv("GOL_MAINTENANCE", "true")
    monkeypatch.setattr(isolation, "_READINESS", (0, 0, False))
    assert availability.assistant_under_maintenance() is True
    assert len(children) == 1
    monkeypatch.setenv("GOL_MAINTENANCE", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert availability.assistant_under_maintenance() is True
    assert len(children) == 1


def test_health_reports_cached_state_without_database_or_probe(app, monkeypatch):
    monkeypatch.setattr(isolation, "isolation_ready", lambda: pytest.fail("Health started a probe"))
    monkeypatch.setattr(isolation, "_analysis_slot", lambda: pytest.fail("Health acquired admission"))
    for state in ("available", "unavailable", "unknown", "unsupported"):
        monkeypatch.setattr(isolation, "isolation_status", lambda: state)
        monkeypatch.setenv("GOL_MAINTENANCE", "true")
        result = app.test_client().get("/api/health").json
        assert result["analysis_isolation_available"] is (state == "available")
        assert result["analysis_isolation_state"] == state
        assert result["assistant_maintenance_enabled"] is True
        assert result["assistant_provider_configured"] is True
    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert app.test_client().get("/api/health").json["assistant_provider_configured"] is False


def test_scope_includes_aliased_helpers_and_all_resident_dependencies():
    frames = reference_frames.__wrapped__()
    helpers = sandbox._build_helpers(frames)
    assert set(helpers) == set(HELPER_FRAMES)
    for name in helpers:
        assert analysis_frame_names(f"f={name}\nresult=f()") >= HELPER_FRAMES[name]
    assert "fixture_stats" not in analysis_frame_names("result=tracked")
    assert not (set(frames) & analysis_frame_names("result=1"))


def test_cache_loads_and_copies_only_selected_frames(monkeypatch):
    cache = DataFrameCache()
    frames = reference_frames.__wrapped__()
    loaded = []

    def load(app, names=None):
        loaded.append(names)
        return {name: frame for name, frame in frames.items() if names is None or name in names}

    monkeypatch.setattr(cache, "_load_all", load)
    monkeypatch.setattr(
        cache, "_adult_frames", lambda app, selected: {name: frame.copy() for name, frame in selected.items()}
    )
    assert cache.get_frames(None, names=set()) == {}
    assert loaded == []
    assert set(cache.get_frames(None, names={"tracked", "pd"})) == {"tracked"}
    assert loaded == [{"tracked"}]
    assert set(cache.get_frames(None, names={"teams"})) == {"teams"}
    first_load = cache._loaded_at
    assert set(cache.get_frames(None)) == set(frames)
    assert cache._loaded_at == first_load
    assert loaded[-1] is None


@linux_policy
def test_admission_precedes_loader_and_no_copy_while_busy(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(isolation, "_SLOT_FILE", tmp_path / "admission")
    monkeypatch.setattr(isolation, "SLOT_WAIT_SECONDS", 0.05)
    loaded = []
    with isolation._analysis_slot():
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(isolation.run_analysis, "result=1", lambda: loaded.append(True) or {}).result()
    assert result["error"] == isolation.BUSY_ERROR
    assert loaded == []
    from src.services.gol_service import GolService

    assert "without rewriting" in GolService._sanitize_for_llm(result)["error"]


@linux_policy
def test_headroom_refuses_before_loader_or_child(monkeypatch, caplog):
    monkeypatch.setattr(isolation, "_memory_available", lambda: 128 * 1024 * 1024)
    monkeypatch.setattr(
        isolation.subprocess, "Popen", lambda *a, **kw: pytest.fail("Child started with insufficient headroom")
    )
    caplog.set_level(logging.WARNING)
    result = isolation.run_analysis("result=1", lambda: pytest.fail("Frames copied before headroom"))
    assert result["error"] == isolation.BUSY_ERROR
    assert "reason=headroom" in caplog.text


@linux_policy
def test_memory_caps_use_available_container_budget(monkeypatch):
    free = 640 * 1024 * 1024
    monkeypatch.setattr(isolation, "_memory_available", lambda: free)
    address_space, rss = isolation._memory_budget()
    assert address_space + isolation.MEMORY_RESERVE_BYTES <= free
    assert rss <= address_space and rss <= isolation.RSS_BYTES


@linux_policy
def test_300k_unreferenced_frames_do_not_refuse_small_analysis():
    from scripts.benchmark_gol_isolation import production_schema_frames

    frames = production_schema_frames(300_000)
    assert sum(int(frame.memory_usage(index=True, deep=True).sum()) for frame in frames.values()) > 128 * 1024 * 1024
    assert isolation.run_analysis("result=1", frames)["value"] == 1
    assert sandbox._execute_analysis("result=1", frames)["value"] == 1


def test_lazy_temp_resolution_refuses_cleanly(monkeypatch):
    monkeypatch.setattr(isolation, "_SLOT_FILE", None)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: (_ for _ in ()).throw(OSError("Unavailable")))
    with pytest.raises(isolation.IsolationFault):
        with isolation._analysis_slot():
            pytest.fail("Acquired unavailable tmp slot")


@linux_policy
def test_empty_orphan_directory_cleanup_preserves_live_and_foreign_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    stale = tmp_path / "aw-analysis-999999999-abcdefgh"
    live = tmp_path / f"aw-analysis-{os.getpid()}-abcdefgh"
    other = tmp_path / "aw-analysis-unrelated"
    nonempty = tmp_path / "aw-analysis-999999999-12345678"
    for path in (stale, live, other, nonempty):
        path.mkdir()
    (nonempty / "retained").write_text("fixture")
    isolation._cleanup_stale_directories()
    assert not stale.exists()
    assert live.exists() and other.exists() and nonempty.exists()


def test_linux_ci_rejects_policy_skip(monkeypatch):
    import conftest

    messages = []
    reporter = SimpleNamespace(
        stats={"skipped": [SimpleNamespace(nodeid="tests/test_gol_isolation.py::test_policy")]},
        write_sep=lambda *args: messages.append(args),
    )
    session = SimpleNamespace(
        config=SimpleNamespace(pluginmanager=SimpleNamespace(getplugin=lambda name: reporter)), exitstatus=0
    )
    monkeypatch.setattr(sys, "platform", "linux")
    conftest.pytest_sessionfinish(session, 0)
    assert session.exitstatus == 1 and messages


def test_model_deadline_hint_is_preserved():
    from src.services.gol_service import GolService

    assert "too long" in GolService._sanitize_for_llm({"error": isolation.TIME_ERROR})["error"]


@linux_policy
def test_child_cannot_cancel_or_mask_backup_deadline(tmp_path, monkeypatch, children):
    _probe_worker(
        tmp_path,
        monkeypatch,
        """import signal
for operation in (
 lambda:signal.alarm(0),
 lambda:signal.setitimer(signal.ITIMER_REAL,0),
 lambda:signal.signal(signal.SIGALRM,signal.SIG_IGN),
 lambda:signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGALRM}),
):
 try: operation()
 except OSError: pass
time.sleep(4)
""",
    )
    worker = isolation._WORKER
    worker.write_text(
        worker.read_text().replace("install_policy()", "import signal; signal.alarm(1)\ninstall_policy()")
    )
    started = time.monotonic()
    with pytest.raises(AnalysisRefused):
        isolation._run_child(b"")
    assert children[0][0].returncode == -signal.SIGALRM
    assert time.monotonic() - started < 3


@linux_policy
def test_deadline_reason_and_public_model_hint(tmp_path, monkeypatch, caplog, children):
    _probe_worker(tmp_path, monkeypatch, "time.sleep(60)")
    monkeypatch.setattr(isolation, "WALL_SECONDS", 0.05)
    caplog.set_level(logging.INFO)
    result = isolation.run_analysis("result=1", {})
    assert result["error"] == isolation.TIME_ERROR
    assert "reason=deadline" in caplog.text
    assert children[0][0].returncode == -signal.SIGKILL


@linux_policy
def test_input_size_reports_measured_limit(tmp_path, monkeypatch, caplog, children):
    from src.services import gol_wire

    monkeypatch.setattr(gol_wire, "MAX_INPUT_BYTES", 512)
    caplog.set_level(logging.WARNING)
    frame = pd.DataFrame({"x": np.arange(1000)})
    result = isolation.run_analysis("result=df", {"df": frame})
    assert result["error"] == SIZE_ERROR
    record = next(r for r in caplog.records if "reason=input_size" in r.getMessage())
    assert record.levelno == logging.WARNING
    assert record.args[1] > record.args[2] == 512
    assert all(child.poll() is not None for child, _ in children)


def test_helper_frame_closure_matches_stored_helper_inventory():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(sandbox._build_helpers))
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name != "_build_helpers"
    }
    direct = {}
    calls = {}
    for name, function in functions.items():
        names = set()
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "dataframes"
                and node.func.attr == "get"
            ):
                key = node.args[0]
                if isinstance(key, ast.Constant):
                    names.add(key.value)
                else:
                    loop = next(
                        loop
                        for loop in ast.walk(function)
                        if isinstance(loop, ast.For) and isinstance(loop.target, ast.Name) and loop.target.id == key.id
                    )
                    assert isinstance(loop.iter, ast.Tuple)
                    names.update(value.value for value in loop.iter.elts)
        direct[name] = names
        calls[name] = {
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in functions
        }

    def closure(name, seen):
        if name in seen:
            return set()
        return direct[name] | set().union(*(closure(call, seen | {name}) for call in calls[name]))

    for name, selected in HELPER_FRAMES.items():
        assert closure(name, set()) <= selected, name


@linux_policy
def test_numeric_team_helper_names_survive_scoped_transport():
    frames = reference_frames.__wrapped__()
    frames["tracked"]["current_club_name"] = "777"
    frames["team_profiles"] = pd.DataFrame({"team_id": [777], "name": ["Fixture Club"]})
    frames["fixture_stats"]["team_api_id"] = 777
    for code in ("result=top_loan_performers()", "result=active_academy_pipeline()"):
        expected = sandbox._execute_analysis(code, frames)
        assert expected["result_type"] == "table"
        assert isolation.run_analysis(code, frames) == expected


def test_import_with_unavailable_tmp_is_safe_and_public_path_refuses(monkeypatch):
    import importlib.util

    monkeypatch.setattr(tempfile, "gettempdir", lambda: (_ for _ in ()).throw(OSError("Unavailable")))
    spec = importlib.util.spec_from_file_location("isolated_tmp_import_test", isolation.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._SLOT_FILE is None
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **kw: pytest.fail("Child started without tmp"))
    assert module.run_analysis("result=1", {})["error"] == "maintenance"


@linux_policy
def test_cache_expiry_does_not_reverse_readiness_and_admission_locks(monkeypatch, tmp_path):
    monkeypatch.setattr(isolation, "_SLOT_FILE", tmp_path / "admission")
    monkeypatch.setattr(isolation, "_READINESS", (os.getpid(), time.monotonic() - 1, True))
    isolation._READINESS_LOCK.acquire()

    def admitted():
        with isolation._analysis_slot():
            return REAL_READINESS()

    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            pending = executor.submit(admitted)
            assert pending.result(timeout=1) is True
        finally:
            isolation._READINESS_LOCK.release()


@linux_policy
@pytest.mark.parametrize("shared", [False, True])
def test_expired_or_cold_readiness_during_other_request_keeps_policy_proof(shared, monkeypatch):
    monkeypatch.setattr(isolation, "SLOT_WAIT_SECONDS", 0.05)
    monkeypatch.setattr(isolation, "_READINESS", (os.getpid(), time.monotonic() - 1, True))
    monkeypatch.setattr(isolation, "_run_child", lambda *a: pytest.fail("Started while another request held admission"))
    with isolation._analysis_slot():
        if shared:
            isolation._policy_ready()
            monkeypatch.setattr(isolation, "_READINESS", (0, 0, False))
        with ThreadPoolExecutor(max_workers=1) as executor:
            assert executor.submit(REAL_READINESS).result(timeout=1) is True
    assert isolation._READINESS[2] is True


@linux_policy
@pytest.mark.parametrize("reason", ["busy", "headroom", "deadline", "child_exit", "bad_output"])
def test_transient_readiness_fault_keeps_previous_proof_with_short_retry(reason, monkeypatch, caplog):
    monkeypatch.setattr(isolation, "_READINESS", (os.getpid(), time.monotonic() - 1, True))
    monkeypatch.setattr(isolation, "_run_child", lambda *a: (_ for _ in ()).throw(isolation.IsolationFault(reason)))
    assert REAL_READINESS() is True
    assert 0 < isolation._READINESS[1] - time.monotonic() <= isolation.READINESS_TRANSIENT_SECONDS
    assert "reason=bootstrap_failed" not in caplog.text


@linux_policy
def test_cold_transient_failure_is_unknown_and_retries_promptly(monkeypatch):
    monkeypatch.setattr(isolation, "_READINESS", (0, 0, False))
    monkeypatch.setattr(isolation, "_run_child", lambda *a: (_ for _ in ()).throw(isolation.IsolationFault("headroom")))
    assert REAL_READINESS() is False
    assert isolation.isolation_status() == "unknown"
    assert isolation._READINESS[1] - time.monotonic() <= isolation.READINESS_TRANSIENT_SECONDS


@linux_policy
def test_loader_failure_is_neutral_and_does_not_revoke_readiness(caplog):
    def loader():
        raise ConnectionError("Fixture transient connection failure")

    caplog.set_level(logging.INFO)
    assert isolation.run_analysis("result=1", loader)["error"] == ERROR
    assert isolation._READINESS[2] is True
    assert "reason=loader_failed" in caplog.text
    assert "reason=bootstrap_failed" not in caplog.text
    assert isolation.run_analysis("result=1", {})["value"] == 1


@linux_policy
@pytest.mark.parametrize("depth", [30, 1500])
def test_deep_child_output_is_per_analysis_refusal(depth, tmp_path, monkeypatch, caplog, children):
    real_worker = isolation._WORKER
    _probe_worker(
        tmp_path,
        monkeypatch,
        f"sys.stdout.write('{{\"result_type\":\"dict\",\"data\":'+('['*{depth})+'0'+(']'*{depth})+'}}')",
    )
    caplog.set_level(logging.INFO)
    result = isolation.run_analysis("result=1", {})
    assert result["error"] == ERROR
    assert isolation._READINESS[2] is True
    assert "reason=bad_output" in caplog.text
    assert "reason=input_size" not in caplog.text
    assert "reason=bootstrap_failed" not in caplog.text
    monkeypatch.setattr(isolation, "_WORKER", real_worker)
    assert isolation.run_analysis("result=1", {})["value"] == 1


@linux_policy
def test_long_output_string_is_bad_output_not_input_size(tmp_path, monkeypatch, caplog):
    _probe_worker(tmp_path, monkeypatch, "sys.stdout.write(json.dumps({'result_type':'scalar','value':'x'*100000}))")
    caplog.set_level(logging.INFO)
    assert isolation.run_analysis("result=1", {})["error"] == ERROR
    assert "reason=bad_output" in caplog.text and "reason=input_size" not in caplog.text
    assert isolation._READINESS[2] is True


@linux_policy
def test_startup_deadline_is_transient_and_parent_kills(tmp_path, monkeypatch, caplog, children):
    _probe_worker(tmp_path, monkeypatch, "pass")
    worker = isolation._WORKER
    worker.write_text(
        worker.read_text().replace("sys.stdout.write('READY\\n')", "time.sleep(60)\nsys.stdout.write('READY\\n')")
    )
    monkeypatch.setattr(isolation, "STARTUP_SECONDS", 0.05)
    caplog.set_level(logging.INFO)
    assert isolation.run_analysis("result=1", {})["error"] == isolation.TIME_ERROR
    assert children[0][0].returncode == -signal.SIGKILL
    assert isolation._READINESS[2] is True
    assert "reason=deadline" in caplog.text and "reason=bootstrap_failed" not in caplog.text


def test_noncanonical_timezone_refuses_identically():
    from zoneinfo._zoneinfo import ZoneInfo as PythonZoneInfo

    frame = pd.DataFrame({"x": pd.Series([datetime(2026, 1, 1, tzinfo=PythonZoneInfo("Europe/London"))], dtype=object)})
    assert sandbox._execute_analysis("result=len(df)", {"df": frame})["error"] == ERROR
    with pytest.raises(AnalysisRefused):
        b"".join(stream_request("result=len(df)", {"df": frame}))


@pytest.mark.parametrize("kind", ["datetime", "timestamp", "column", "index"])
def test_subminute_timezone_refuses_identically(kind):
    zone = timezone(timedelta(seconds=30, microseconds=1), "Fixture Seconds")
    value = datetime(2026, 1, 1, tzinfo=zone)
    if kind in {"datetime", "timestamp"}:
        frame = pd.DataFrame({"x": pd.Series([value if kind == "datetime" else pd.Timestamp(value)], dtype=object)})
    else:
        index = pd.date_range(value, periods=2, freq="D")
        frame = pd.DataFrame({"x": index}) if kind == "column" else pd.DataFrame({"x": [1, 2]}, index=index)
    assert sandbox._execute_analysis("result=len(df)", {"df": frame})["error"] == ERROR
    with pytest.raises(AnalysisRefused):
        b"".join(stream_request("result=len(df)", {"df": frame}))


def test_integer_outside_json_digit_bound_refuses_identically():
    frame = pd.DataFrame({"x": pd.Series([2**14000], dtype=object)})
    assert sandbox._execute_analysis("result=len(df)", {"df": frame})["error"] == ERROR
    with pytest.raises(AnalysisRefused):
        b"".join(stream_request("result=len(df)", {"df": frame}))
    assert sandbox._execute_analysis("result=2**14000", {})["error"] == ERROR


def test_new_admission_row_without_parity_recipe_fails(monkeypatch):
    import gol_plain_shape_cases as cases
    from src.services.gol_plain_shapes import Shape

    monkeypatch.setattr(cases, "SHAPES", (*cases.SHAPES, Shape("value", "future_shape", "future_wire")))
    with pytest.raises(AssertionError, match="explicit parity recipe"):
        cases.generated_cases()


def test_cached_health_state_is_memory_only(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(isolation, "_slot_file", lambda: pytest.fail("Health performed filesystem I/O"))
    assert isolation.isolation_status() == "available"
    monkeypatch.setattr(isolation, "_READINESS", (os.getpid(), time.monotonic() - 1, True))
    assert isolation.isolation_status() == "unknown"
    isolation._unavailable()
    assert isolation.isolation_status() == "unavailable"


@pytest.mark.parametrize("key", [np.nan, np.inf, -np.inf])
def test_nonfinite_dictionary_keys_refuse_identically(key):
    frame = pd.DataFrame({"x": pd.Series([{key: 1}], dtype=object)})
    assert sandbox._execute_analysis("result=len(df)", {"df": frame})["error"] == ERROR
    with pytest.raises(AnalysisRefused):
        b"".join(stream_request("result=len(df)", {"df": frame}))


def test_timezone_name_subclass_refuses_before_coercion():
    class UncarriedName(str):
        def __repr__(self):
            pytest.fail("Uncarried timezone name was coerced")

    zone = timezone(timedelta(hours=9), UncarriedName("Fixture Zone"))
    frame = pd.DataFrame({"x": pd.Series([datetime(2026, 1, 1, tzinfo=zone)], dtype=object)})
    assert sandbox._execute_analysis("result=len(df)", {"df": frame})["error"] == ERROR
    with pytest.raises(AnalysisRefused):
        b"".join(stream_request("result=len(df)", {"df": frame}))
