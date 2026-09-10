"""Deterministic timestamp ties, without model/runtime or browser dependencies."""

import json
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent
KEY = "test|1.000000"


def state(kind, time=100, x=10):
    if kind == "clear":
        return {"labels": {}, "deleted": {KEY: time}}
    row = {
        "clip": "test",
        "t": 1,
        "x": x,
        "y": 20,
        "visible": True,
        "schema_version": 2,
        "match_ball": False,
        "updated_at": time,
        "review_frame": True,
        "review_confirmed": kind == "confirmed",
        "needs_any_ball_review": kind != "confirmed",
    }
    return {"labels": {KEY: row}, "deleted": {}}


def merge(local, stored):
    script = """
      globalThis.BallTruth=require(process.argv[1]);require(process.argv[2]);
      const [a,b]=JSON.parse(process.argv[3]), conflicts=[];
      const result=BallStorage.merge(a,b,(...args)=>conflicts.push(args));
      process.stdout.write(JSON.stringify({result,conflicts}));
    """
    return json.loads(
        subprocess.check_output(
            [
                "node",
                "-e",
                script,
                str(HERE / "truth_io.js"),
                str(HERE / "truth_storage.js"),
                json.dumps([local, stored]),
            ],
            text=True,
        )
    )


KINDS = ("unconfirmed", "clear", "confirmed")


@pytest.mark.parametrize("local", KINDS)
@pytest.mark.parametrize("stored", KINDS)
def test_every_equal_timestamp_pair(local, stored):
    result = merge(state(local), state(stored))
    winner = max((local, stored), key=KINDS.index)
    if winner == "clear":
        assert result["result"]["labels"] == {}
        assert result["result"]["deleted"] == {KEY: 100}
    else:
        assert result["result"]["labels"][KEY] == state(winner)["labels"][KEY]
        assert result["result"]["deleted"] == {}
    assert result["conflicts"] == []


@pytest.mark.parametrize("local", KINDS)
@pytest.mark.parametrize("stored", KINDS)
@pytest.mark.parametrize("newer", ["local", "stored"])
def test_newer_timestamp_always_wins(local, stored, newer):
    a, b = (
        state(local, 101 if newer == "local" else 100),
        state(stored, 101 if newer == "stored" else 100),
    )
    result = merge(a, b)["result"]
    winner = local if newer == "local" else stored
    if winner == "clear":
        assert not result["labels"]
        assert result["deleted"][KEY] == 101
    else:
        assert result["labels"][KEY] == state(winner, 101)["labels"][KEY]


@pytest.mark.parametrize("a,b", [(10, 30), (30, 10)])
def test_confirmed_conflict_keeps_stored_and_reports(a, b):
    local, stored = state("confirmed", x=a), state("confirmed", x=b)
    result = merge(local, stored)
    assert result["result"]["labels"][KEY] == stored["labels"][KEY]
    assert len(result["conflicts"]) == 1
    assert result["conflicts"][0][0] == KEY


def test_unconfirmed_tie_keeps_stored_without_lexicographic_choice():
    local, stored = state("unconfirmed", x=99), state("unconfirmed", x=10)
    result = merge(local, stored)
    assert result["result"]["labels"][KEY] == stored["labels"][KEY]
    assert result["conflicts"] == []
