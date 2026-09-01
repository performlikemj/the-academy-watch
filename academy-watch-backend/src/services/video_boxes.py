"""Shared derivation and retrieval for per-tracklet player box tracks."""

import logging
import math
from functools import lru_cache
from pathlib import Path

from src.services import video_storage

logger = logging.getLogger(__name__)

BOX_TRACK_HZ = 4
BOX_BLOB_CACHE_SIZE = 16


def _row_value(row, name, default=None):
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def member_entity_ids(tracklet) -> list[int]:
    """Return the fragment entity ids represented by a persisted tracklet."""
    if _row_value(tracklet, "kind") == "chain":
        evidence = _row_value(tracklet, "evidence") or {}
        values = evidence.get("member_fragment_ids") if isinstance(evidence, dict) else []
    else:
        pipeline_key = _row_value(tracklet, "pipeline_key", "") or ""
        values = [pipeline_key[1:]] if pipeline_key[:1] in ("E", "e") else []
    out = []
    for value in values or []:
        try:
            out.append(int(value))
        except (TypeError, ValueError):
            continue
    return out


def sample_box_track(points, max_hz: float = BOX_TRACK_HZ) -> list[list]:
    """Normalize, time-sort, and cadence-limit [t, x1, y1, x2, y2] rows."""
    if max_hz <= 0:
        return []
    normalized = []
    for point in points or []:
        if not isinstance(point, (list, tuple)) or len(point) != 5:
            continue
        try:
            values = [float(value) for value in point]
        except (TypeError, ValueError):
            continue
        if not all(math.isfinite(value) for value in values):
            continue
        normalized.append(values)
    normalized.sort(key=lambda point: point[0])

    interval = 1.0 / max_hz
    sampled = []
    last_t = None
    for t, x1, y1, x2, y2 in normalized:
        if last_t is not None and t < last_t + interval - 1e-6:
            continue
        sampled.append([round(t, 2), int(x1), int(y1), int(x2), int(y2)])
        last_t = t
    return sampled


def box_track_from_arrays(tracklet, fragment_member_tids: dict, tid_arr, t_arr, xy_arr, *, max_hz=BOX_TRACK_HZ):
    """Pure box derivation from one tracklet, fragment membership, and track arrays."""
    import numpy as np

    member_tids = []
    for entity_id in member_entity_ids(tracklet):
        member_tids.extend(fragment_member_tids.get(entity_id, []))
    if not member_tids:
        return []
    mask = np.isin(tid_arr, np.asarray(sorted(set(member_tids)), dtype=tid_arr.dtype))
    indexes = np.nonzero(mask)[0]
    if indexes.size == 0:
        return []
    indexes = indexes[np.argsort(t_arr[indexes], kind="stable")]
    return sample_box_track(
        [[t_arr[index], *xy_arr[index]] for index in indexes],
        max_hz=max_hz,
    )


def box_tracks_from_npz(tracklets, fragments: list[dict], tracks_path: str | Path, *, max_hz=BOX_TRACK_HZ) -> dict:
    """Derive every persisted tracklet's box track from a pipeline tracks.npz."""
    import numpy as np

    fragment_member_tids = {
        int(fragment["entity_id"]): list(fragment.get("member_tids") or [])
        for fragment in fragments
        if fragment.get("entity_id") is not None
    }
    with np.load(tracks_path, allow_pickle=False) as tracks:
        tid_arr = tracks["tid"]
        t_arr = tracks["t"]
        xy_arr = tracks["xyxy"]
        return {
            str(int(_row_value(tracklet, "id"))): box_track_from_arrays(
                tracklet,
                fragment_member_tids,
                tid_arr,
                t_arr,
                xy_arr,
                max_hz=max_hz,
            )
            for tracklet in tracklets
        }


def clip_box_track(track, start_s: float, end_s: float) -> list[list]:
    return [point for point in track or [] if start_s <= point[0] <= end_s]


def union_box_tracks(tracks, *, max_hz=BOX_TRACK_HZ) -> list[list]:
    return sample_box_track([point for track in tracks for point in (track or [])], max_hz=max_hz)


@lru_cache(maxsize=BOX_BLOB_CACHE_SIZE)
def _download_boxes_blob(blob_path: str) -> dict:
    payload = video_storage.download_json(blob_path)
    if not isinstance(payload, dict):
        raise ValueError("box-track blob must contain a JSON object")
    return payload


def box_track_for(match, tracklet) -> list[list]:
    """Resolve a track from dev artifacts first, then the match's cached prod blob."""
    from src.services import video_dev_artifacts

    artifacts = video_dev_artifacts.local_artifacts(match)
    if artifacts:
        return video_dev_artifacts.tracklet_bbox_track(tracklet, artifacts)

    blob_path = _row_value(match, "boxes_blob_path")
    tracklet_id = _row_value(tracklet, "id")
    if not blob_path or tracklet_id is None:
        return []
    try:
        payload = _download_boxes_blob(blob_path)
        return sample_box_track(payload.get(str(int(tracklet_id))) or [])
    except Exception as exc:
        logger.warning("could not load box track blob %s: %s", blob_path, exc)
        return []
