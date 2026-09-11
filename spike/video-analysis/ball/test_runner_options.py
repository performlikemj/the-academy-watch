"""Runner preflight/device regressions with stub models only; no inference."""

from __future__ import annotations
import sys
from types import SimpleNamespace
import numpy as np
import pytest
import detectors
import run_ball
import wasb_parity


@pytest.fixture(autouse=True)
def isolated_report_destination(monkeypatch, tmp_path):
    # Runner tests must never target the real report directory, even with stubs.
    monkeypatch.setattr(run_ball, "DEFAULT_REPORT", tmp_path / "reports")


@pytest.mark.parametrize("device", ["cpu", "mps"])
@pytest.mark.parametrize("grid", [1, 2, 3])
def test_rf_selected_device_reaches_loader(monkeypatch, device, grid):
    calls = []

    def load(size, selected, resolution):
        calls.append((size, selected, resolution))
        return SimpleNamespace(
            model=SimpleNamespace(device=selected, resolution=resolution)
        )

    monkeypatch.setitem(
        sys.modules,
        "run_spike",
        SimpleNamespace(load_detector=load, detect_batch=None, keep_classes=None),
    )
    monkeypatch.setitem(
        sys.modules,
        "supervision",
        SimpleNamespace(
            InferenceSlicer=lambda **kw: kw,
            OverlapFilter=SimpleNamespace(NON_MAX_SUPPRESSION="nms"),
        ),
    )
    detector = detectors.RFDetector(grid, (1920, 1080), 640, device=device)
    assert calls == [("medium", device, 640)]
    assert detector.device == device


@pytest.mark.parametrize("requested,loaded", [("mps", "cpu"), ("cpu", "mps")])
def test_rf_rejects_wrong_device(monkeypatch, requested, loaded):
    monkeypatch.setitem(sys.modules, "supervision", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "run_spike",
        SimpleNamespace(
            load_detector=lambda *a: SimpleNamespace(
                model=SimpleNamespace(device=loaded)
            ),
            detect_batch=None,
            keep_classes=None,
        ),
    )
    with pytest.raises(
        RuntimeError, match=f"requested {requested}, loaded on {loaded}"
    ):
        detectors.RFDetector(1, (1920, 1080), device=requested)


def clips(n=3, end=5):
    return [
        {
            "clip_id": f"clip{i}",
            "video": "unused",
            "native_source": True,
            "window": {"start_s": 0, "end_s": end},
        }
        for i in range(n)
    ]


def fake_runtime(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "cv2", SimpleNamespace(setNumThreads=lambda n: None)
    )
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            set_num_threads=lambda n: None,
            backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: True)),
            mps=SimpleNamespace(synchronize=lambda: None),
        ),
    )


@pytest.mark.parametrize("device", ["cpu", "mps"])
@pytest.mark.parametrize("candidate", ["rf_full", "rf_2x2", "rf_3x3"])
def test_runner_forwards_rf_device(monkeypatch, device, candidate):
    fake_runtime(monkeypatch)
    monkeypatch.setattr(
        sys, "argv", ["run_ball", "--candidate", candidate, "--device", device]
    )
    monkeypatch.setattr(run_ball, "load_dataset", lambda *a: ({}, clips()))
    monkeypatch.setattr(run_ball, "probe", lambda _: {"width": 1920, "height": 1080})

    class StopBeforeInference(Exception):
        pass

    def constructor(grid, size, resolution, *, device):
        assert device == sys.argv[-1]
        assert grid == {"rf_full": 1, "rf_2x2": 2, "rf_3x3": 3}[candidate]
        raise StopBeforeInference

    monkeypatch.setattr(run_ball, "RFDetector", constructor)
    with pytest.raises(StopBeforeInference):
        run_ball.main()


def test_parity_three_available_clips_five_distinct_frames(monkeypatch):
    fake_runtime(monkeypatch)
    monkeypatch.setattr(wasb_parity, "probe", lambda _: {"avg_frame_rate": "10/1"})
    available = clips()
    plan = wasb_parity.plan_parity(available)
    assert len(plan) == 5
    assert len({(p["clip"], p["sample_index"]) for p in plan}) == 5
    assert {p["clip"] for p in plan} == {"clip0", "clip1", "clip2"}
    assert [p["sample_index"] for p in plan if p["clip"] == "clip0"] == [1, 9]
    seen = []

    def samples(clip):
        for i in range(10):
            yield {"t": i * 0.5}, (clip["clip_id"], i)

    monkeypatch.setattr(wasb_parity, "samples", samples)
    model = SimpleNamespace(device="cpu", model=SimpleNamespace(to=lambda d: None))

    def heatmaps(stack):
        seen.append((model.device, stack))
        return [(None, np.zeros((3, 2, 2)))] * 4

    model.heatmaps = heatmaps
    result = wasb_parity.check_parity(model, available, plan)
    assert len(result["frames"]) == 5 and len(seen) == 10
    assert model.device == "cpu"
    assert result["max_abs_heatmap_diff"] == 0
    larger = wasb_parity.plan_parity(clips(20))
    assert [p["clip"] for p in larger] == [
        "clip0",
        "clip5",
        "clip10",
        "clip14",
        "clip19",
    ]


@pytest.mark.parametrize("end,valid", [(5, True), (0.1, False)])
def test_parity_preflight_before_model_loading(monkeypatch, end, valid, capsys):
    fake_runtime(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_ball",
            "--candidate",
            "wasb_2x2",
            "--parity-frames",
            "5",
            "--clips",
            "clip0,clip1,clip2",
        ],
    )
    monkeypatch.setattr(run_ball, "load_dataset", lambda *a: ({}, clips(20, end)))
    monkeypatch.setattr(wasb_parity, "probe", lambda _: {"avg_frame_rate": "10/1"})
    loaded = []

    class StopBeforeInference(Exception):
        pass

    def constructor(*args, **kwargs):
        loaded.append(True)
        raise StopBeforeInference

    monkeypatch.setattr(run_ball, "WASBDetector", constructor)
    if valid:
        with pytest.raises(StopBeforeInference):
            run_ball.main()
        assert loaded
    else:
        with pytest.raises(SystemExit) as exc:
            run_ball.main()
        assert exc.value.code == 2
        assert not loaded
        assert "parity needs 5 distinct available frames" in capsys.readouterr().err
