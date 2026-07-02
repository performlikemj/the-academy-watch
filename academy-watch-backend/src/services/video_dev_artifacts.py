"""Dev-only local artifact resolution for the Film Room video-review tool.

In production, footage + crops live in Azure Blob (served via read SAS). Locally
there is no blob — this module resolves the spike's on-disk artifacts (the full
match mp4, per-entity crop JPEGs, per-frame tracks.npz, inverted fragments.json)
so the tag-review UI can play each tracklet's video window, show its crops, and
draw a box that follows the player.

Gated entirely on `video_storage.is_configured() is False` AND a
`match.capture_meta['local']` map — never active in production. The map:
  {footage, crops_dir, crops_index, tracks_dir, fragments}  (all absolute paths)
"""

import json
import logging
import os
import re
from functools import lru_cache
from glob import glob

from src.services import video_storage

logger = logging.getLogger(__name__)

CROP_CAP = 8  # sharpest crops surfaced per tracklet row
BBOX_MAX_POINTS = 8000  # safety cap on a returned bbox track
_CROP_NAME = re.compile(r"e\d+_\d+\.jpg")


def local_artifacts(match) -> dict | None:
    """The local artifact map for a match in dev, or None in prod / when unmapped."""
    if video_storage.is_configured():
        return None
    meta = match.capture_meta if isinstance(match.capture_meta, dict) else {}
    local = meta.get("local")
    return local if isinstance(local, dict) else None


@lru_cache(maxsize=4)
def _crops_by_entity(path: str) -> dict:
    with open(path) as f:
        rows = json.load(f)
    by_ent: dict[int, list] = {}
    for r in rows:
        by_ent.setdefault(int(r["entity_id"]), []).append(r)
    return by_ent


@lru_cache(maxsize=4)
def _member_tids_by_entity(fragments_path: str) -> dict:
    with open(fragments_path) as f:
        frags = json.load(f)
    return {int(fr["entity_id"]): list(fr.get("member_tids") or []) for fr in frags}


@lru_cache(maxsize=4)
def _spans_by_entity(fragments_path: str) -> dict:
    with open(fragments_path) as f:
        frags = json.load(f)
    return {
        int(fr["entity_id"]): (
            float(fr.get("first_s") or 0),
            float(fr.get("last_s") or 0),
            float(fr.get("visible_s") or 0),
        )
        for fr in frags
    }


def fragment_spans(art: dict) -> dict:
    """{entity_id: (first_s, last_s, visible_s)} — used to split a chain by time."""
    return _spans_by_entity(art["fragments"])


@lru_cache(maxsize=2)
def _tracks(tracks_dir: str):
    """Concatenated (tid, t, xyxy) across all chunk*/tracks.npz. t is absolute match
    seconds; tid is chunk-namespaced so a single global index is unambiguous."""
    import numpy as np

    files = sorted(glob(os.path.join(tracks_dir, "chunk*", "tracks.npz")))
    if not files:
        return None
    tids, ts, xys = [], [], []
    for f in files:
        z = np.load(f, allow_pickle=True)
        tids.append(z["tid"])
        ts.append(z["t"])
        xys.append(z["xyxy"])
    return np.concatenate(tids), np.concatenate(ts), np.concatenate(xys)


def _member_entity_ids(tracklet) -> list[int]:
    """The fragment entity_ids a tracklet is built from (chain: stored member ids;
    fragment: parsed from the 'E<id>' pipeline_key)."""
    if tracklet.kind == "chain":
        ev = tracklet.evidence or {}
        return [int(x) for x in (ev.get("member_fragment_ids") or [])]
    pk = tracklet.pipeline_key or ""
    if pk[:1] in ("E", "e") and pk[1:].isdigit():
        return [int(pk[1:])]
    return []


def tracklet_crops(tracklet, art: dict) -> list[dict]:
    """Sharpest-first crop rows for a tracklet: [{file, t, frame, laplacian_var}], capped.

    Drawn PREFERENTIALLY from the tracklet's well-attested (strong) fragments, so a
    noisy weak member (often a spectator or a mis-track that survived the gate)
    can't dominate the strip with an incidentally-sharp crop."""
    by_ent = _crops_by_entity(art["crops_index"])
    ev = tracklet.evidence if isinstance(tracklet.evidence, dict) else {}
    strong = {int(x) for x in (ev.get("strong_fragment_ids") or [])}
    rows: list[tuple[int, dict]] = []
    for eid in _member_entity_ids(tracklet):
        tier = 0 if eid in strong else 1  # strong fragments first
        for c in by_ent.get(eid, []):
            rows.append((tier, c))
    rows.sort(key=lambda tc: (tc[0], -float(tc[1].get("laplacian_var") or 0)))
    out, seen = [], set()
    for _tier, r in rows:
        if r["file"] in seen:
            continue
        seen.add(r["file"])
        out.append(
            {
                "file": r["file"],
                "t": round(float(r.get("t") or 0), 2),
                "frame": int(r.get("frame") or 0),
                "laplacian_var": round(float(r.get("laplacian_var") or 0), 1),
            }
        )
        if len(out) >= CROP_CAP:
            break
    return out


def crop_path(art: dict, crop_file: str) -> str | None:
    """Resolve a crop file inside the allowed dir, rejecting traversal."""
    if not _CROP_NAME.fullmatch(crop_file):
        return None
    base = os.path.realpath(art["crops_dir"])
    full = os.path.realpath(os.path.join(base, crop_file))
    if not (full == base or full.startswith(base + os.sep)):
        return None
    return full if os.path.exists(full) else None


def tracklet_bbox_track(tracklet, art: dict) -> list[list]:
    """Per-frame [t, x1, y1, x2, y2] (absolute seconds, source pixels), time-sorted."""
    import numpy as np

    tracks = _tracks(art["tracks_dir"])
    if tracks is None:
        return []
    tid_arr, t_arr, xy_arr = tracks
    frag_map = _member_tids_by_entity(art["fragments"])
    member_tids: list[int] = []
    for eid in _member_entity_ids(tracklet):
        member_tids.extend(frag_map.get(eid, []))
    if not member_tids:
        return []
    mask = np.isin(tid_arr, np.array(sorted(set(member_tids)), dtype=tid_arr.dtype))
    idx = np.nonzero(mask)[0]
    if idx.size == 0:
        return []
    idx = idx[np.argsort(t_arr[idx])]
    if idx.size > BBOX_MAX_POINTS:  # downsample huge tracks (keeps box smooth enough)
        idx = idx[:: int(np.ceil(idx.size / BBOX_MAX_POINTS))]
    out = []
    for i in idx:
        x1, y1, x2, y2 = xy_arr[i]
        out.append([round(float(t_arr[i]), 2), int(x1), int(y1), int(x2), int(y2)])
    return out
