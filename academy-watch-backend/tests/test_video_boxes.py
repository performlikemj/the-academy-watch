import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from flask import Flask
from src.models.league import db
from src.models.video import VideoTracklet
from src.routes.video import get_tracklet_bbox
from src.services import video_boxes, video_storage
from src.workers.vision_worker import _persist_box_tracks


def _write_tracks(path: Path) -> None:
    np.savez_compressed(
        path,
        tid=np.array([7, 7, 7, 7, 99], dtype=np.int32),
        t=np.array([0.0, 0.1, 0.26, 0.51, 1.0], dtype=np.float32),
        xyxy=np.array(
            [
                [1.9, 2.1, 30.8, 40.2],
                [2.0, 3.0, 31.0, 41.0],
                [3.0, 4.0, 32.0, 42.0],
                [4.0, 5.0, 33.0, 43.0],
                [9.0, 9.0, 10.0, 10.0],
            ],
            dtype=np.float32,
        ),
    )


def test_box_tracks_derive_from_synthetic_npz_and_fragment_membership(tmp_path):
    tracks_path = tmp_path / "tracks.npz"
    _write_tracks(tracks_path)
    tracklets = [
        SimpleNamespace(id=11, kind="chain", evidence={"member_fragment_ids": [101]}, pipeline_key="T0#8"),
        SimpleNamespace(id=12, kind="fragment", evidence=None, pipeline_key="E404"),
    ]

    derived = video_boxes.box_tracks_from_npz(
        tracklets,
        [{"entity_id": 101, "member_tids": [7]}, {"entity_id": 404, "member_tids": []}],
        tracks_path,
    )

    assert derived == {
        "11": [[0.0, 1, 2, 30, 40], [0.26, 3, 4, 32, 42], [0.51, 4, 5, 33, 43]],
        "12": [],
    }


def test_cv_completion_uploads_box_json_and_stores_match_path(tmp_path):
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    tracks_path = tmp_path / "tracks.npz"
    _write_tracks(tracks_path)
    match = SimpleNamespace(id=42, boxes_blob_path=None)
    tracklet = SimpleNamespace(id=11, kind="chain", evidence={"member_fragment_ids": [101]}, pipeline_key="T0#8")
    uploaded = {}

    with app.app_context():
        with (
            patch.object(video_storage, "is_configured", return_value=True),
            patch.object(
                video_storage,
                "upload_json",
                side_effect=lambda path, payload: uploaded.update(path=path, payload=payload),
            ),
            patch.object(db.session, "query") as query,
            patch.object(db.session, "commit") as commit,
        ):
            query.return_value.filter.return_value.all.return_value = [tracklet]
            path = _persist_box_tracks(
                match,
                "job-abc",
                tracks_path,
                [{"entity_id": 101, "member_tids": [7]}],
            )

    assert path == "boxes/42/job-abc.json"
    assert match.boxes_blob_path == path
    assert uploaded == {
        "path": path,
        "payload": {"11": [[0.0, 1, 2, 30, 40], [0.26, 3, 4, 32, 42], [0.51, 4, 5, 33, 43]]},
    }
    commit.assert_called_once()


def test_bbox_route_serves_cached_blob_track_with_existing_auth_wrapper_untouched():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    match = SimpleNamespace(id=5, capture_meta={}, boxes_blob_path="boxes/5/job-1.json")
    tracklet = SimpleNamespace(id=9, video_match_id=5, kind="chain", evidence={}, pipeline_key="T0#8")
    boxes = [[1.0, 10, 20, 30, 40]]
    video_boxes._download_boxes_blob.cache_clear()

    def fake_get(model, _identifier):
        return tracklet if model is VideoTracklet else match

    with app.app_context(), app.test_request_context():
        with (
            patch.object(db.session, "get", side_effect=fake_get),
            patch("src.services.video_dev_artifacts.local_artifacts", return_value=None),
            patch.object(video_storage, "download_json", return_value={"9": boxes}) as download,
        ):
            first = get_tracklet_bbox.__wrapped__(5, 9)
            second = get_tracklet_bbox.__wrapped__(5, 9)

    assert first.get_json() == {"available": True, "boxes": boxes}
    assert second.get_json() == {"available": True, "boxes": boxes}
    download.assert_called_once_with("boxes/5/job-1.json")
    video_boxes._download_boxes_blob.cache_clear()


def test_storage_upload_and_download_json_use_application_json_and_overwrite():
    uploaded = {}

    class Blob:
        def upload_blob(self, payload, **kwargs):
            uploaded.update(payload=payload, kwargs=kwargs)

        def download_blob(self):
            return SimpleNamespace(readall=lambda: b'{"ok":true}')

    service = SimpleNamespace(get_blob_client=lambda container, path: Blob())
    with patch.object(video_storage, "_service_client", return_value=service):
        video_storage.upload_json("boxes/1/job.json", {"9": []})
        assert video_storage.download_json("boxes/1/job.json") == {"ok": True}

    assert json.loads(uploaded["payload"]) == {"9": []}
    assert uploaded["kwargs"]["overwrite"] is True
    assert uploaded["kwargs"]["content_settings"].content_type == "application/json"
