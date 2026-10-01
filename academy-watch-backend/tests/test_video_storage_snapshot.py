"""Snapshot support in video_storage (club staff access N1a) against a fake Azure client."""

from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from src.services import video_storage


class _Blob:
    def __init__(self, log, fail=False):
        self.log, self.fail = log, fail

    def create_snapshot(self, **kwargs):
        self.log.append(("create_snapshot", kwargs))
        if self.fail:
            raise RuntimeError("ConditionNotMet")
        return {"snapshot": "2026-10-01T01:02:03.0000000Z"}

    def delete_blob(self, **kwargs):
        self.log.append(("delete_blob", kwargs))


class _Service:
    account_name = "syntheticaccount"
    url = "https://syntheticaccount.blob.core.windows.net/"
    credential = SimpleNamespace(account_key="c3ludGhldGljLXJldmlldy1rZXk=")

    def __init__(self, log, fail=False):
        self.log, self.fail = log, fail

    def get_blob_client(self, container, path):
        self.log.append(("client", path))
        return _Blob(self.log, self.fail)


@pytest.fixture
def storage(monkeypatch):
    log = []
    monkeypatch.setattr(video_storage, "_service_client", lambda: _Service(log))
    return log


def test_snapshot_is_conditional_on_the_verified_etag(storage):
    from azure.core import MatchConditions

    snapshot = video_storage.create_verified_snapshot("matches/1/a.mp4", "0xVERIFIED")
    assert snapshot == "2026-10-01T01:02:03.0000000Z"
    assert storage[-1] == ("create_snapshot", {"etag": "0xVERIFIED", "match_condition": MatchConditions.IfNotModified})


def test_snapshot_failure_or_missing_etag_yields_none(monkeypatch):
    log = []
    monkeypatch.setattr(video_storage, "_service_client", lambda: _Service(log, fail=True))
    assert video_storage.create_verified_snapshot("matches/1/a.mp4", "0xCHANGED") is None
    assert video_storage.create_verified_snapshot("matches/1/a.mp4", None) is None
    assert video_storage.create_verified_snapshot("", "0x1") is None


def test_snapshot_sas_targets_only_the_snapshot(storage):
    snap = "2026-10-01T01:02:03.0000000Z"
    scoped = urlsplit(video_storage.mint_media_read_sas("matches/1/a.mp4", seconds=120, snapshot=snap))
    base = urlsplit(video_storage.mint_media_read_sas("matches/1/a.mp4", seconds=120))
    scoped_q, base_q = parse_qs(scoped.query), parse_qs(base.query)
    assert scoped.path == base.path and scoped.path.endswith("/matches/1/a.mp4")
    # Signed resource is the blob SNAPSHOT (sr=bs), read-only, and the URL addresses that snapshot.
    assert scoped_q["snapshot"] == [snap] and scoped_q["sr"] == ["bs"] and scoped_q["sp"] == ["r"]
    assert "snapshot" not in base_q and base_q["sr"] == ["b"] and base_q["sp"] == ["r"]
    # Different string-to-sign: the snapshot signature is not valid for the mutable base blob.
    assert scoped_q["sig"] != base_q["sig"]


def test_retention_delete_includes_snapshots(storage):
    assert video_storage.delete_blob("matches/1/a.mp4") is True
    assert storage[-1] == ("delete_blob", {"delete_snapshots": "include"})
