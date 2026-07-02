#!/usr/bin/env python3
"""Offline tracklet-merge pass: collapse BoT-SORT fragments into persistent entities.

Consumes the artifacts produced by run_spike.py (tracks.npz, tracklet_embeddings.npz,
results.json) and the source video. Camera pans break tracker identity constantly
(~8k raw tracklets per match); this pass merges fragments using appearance
(SigLIP tracklet embeddings), team labels, temporal gaps and spatial continuity,
detects actual-play windows (the footage opens with warmup), and renders a demo
clip with STABLE merged entity IDs.

Outputs in --results-dir:
  merge_report.json   counts, duration stats before/after, activity windows, kickoff
  entities.json       [{entity_id, member_tids, team, first_s, last_s, visible_s}]
  merged_clip.mp4     45s render, bbox + "E<id>" label colored by team

Usage:
  python merge_tracklets.py --results-dir results/match-XXX --video footage/match.mp4
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

import numpy as np


def _fail(what: str, hint: str) -> NoReturn:
    print(f"ERROR: {what}\n  fix: {hint}", file=sys.stderr)
    sys.exit(1)


try:
    import cv2
except ImportError as e:
    _fail(f"opencv import failed: {e}", "pip install opencv-python-headless==4.13.0.92")

try:
    import av
except ImportError as e:
    _fail(f"PyAV import failed: {e}", "pip install av==17.1.0")


ACTIVITY_BIN_S = 10.0
ACTIVITY_MIN_TRACKLETS = 12
KICKOFF_MIN_WINDOW_S = 180.0
MAX_OVERLAP_S = 0.3
SPATIAL_FRAC = 0.15  # end-center/start-center distance gate, fraction of frame width
NOEMB_MAX_GAP_S = 1.5
SPATIAL_GATE_MAX_GAP_S = 2.0
LONG_GAP_SIM_BONUS = 0.08
TEAM_COLORS_RGB = {0: (50, 120, 255), 1: (255, 60, 60), -1: (170, 170, 170)}


# --------------------------------------------------------------------------- loading


@dataclass
class Tracklets:
    """Per-tracklet summaries, parallel arrays of length K (one row per tid)."""

    tid: np.ndarray  # int32 K
    first_t: np.ndarray  # float32 K
    last_t: np.ndarray  # float32 K
    first_c: np.ndarray  # float32 K x 2, bbox center at first observation
    last_c: np.ndarray  # float32 K x 2, bbox center at last observation
    n_frames: np.ndarray  # int32 K
    team: np.ndarray  # int8 K, 0/1 or -1
    emb: np.ndarray  # float32 K x D, zero rows where missing
    has_emb: np.ndarray  # bool K

    def __len__(self) -> int:
        return len(self.tid)

    def durations(self, dt: float) -> np.ndarray:
        return (self.last_t - self.first_t) + dt


def load_config(results_dir: Path, video: Path) -> tuple[float, int, float]:
    """Return (sample_fps, frame_width, video_duration_s) from results.json, probing
    the video for anything missing."""
    sample_fps, width, duration = None, None, None
    rj = results_dir / "results.json"
    if rj.exists():
        data = json.loads(rj.read_text())
        sample_fps = data.get("config", {}).get("sample_fps")
        vid = data.get("video", {})
        width = vid.get("width")
        duration = vid.get("duration_s")
    if sample_fps is None or width is None or duration is None:
        print("WARNING: results.json missing or incomplete; probing video for metadata")
        with av.open(str(video)) as container:
            stream = container.streams.video[0]
            width = width or stream.codec_context.width
            if duration is None:
                duration = float(stream.duration * stream.time_base) if stream.duration else 0.0
        if sample_fps is None:
            _fail("sample_fps not found in results.json", "pass a results dir produced by run_spike.py")
    if not duration or float(duration) <= 0:
        _fail("video duration unknown", "results.json lacks video.duration_s and the file has no duration metadata")
    return float(sample_fps), int(width), float(duration)


def combine_chunks(chunk_dirs: list[Path], out_dir: Path) -> None:
    """Concatenate chunked run_spike outputs into one results dir.

    Chunks namespace tracker ids via --tid-offset, so concatenation is safe.
    Each chunk fit its own KMeans, so team label 0/1 is arbitrary per chunk —
    align every chunk to chunk 0 using the stored per-team mean embeddings.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    tr: dict[str, list[np.ndarray]] = {k: [] for k in ("frame", "t", "tid", "xyxy", "conf")}
    em: dict[str, list[np.ndarray]] = {k: [] for k in ("ids", "emb", "team", "n_crops")}
    ref_means: np.ndarray | None = None
    config: dict | None = None
    for ci, d in enumerate(chunk_dirs):
        tp = d / "tracks.npz"
        if not tp.exists():
            print(f"WARNING: {tp} missing — skipping chunk {ci}")
            continue
        td = np.load(tp)
        for k in tr:
            tr[k].append(td[k])
        rj = d / "results.json"
        if config is None and rj.exists():
            config = json.loads(rj.read_text())
        ep = d / "tracklet_embeddings.npz"
        if not ep.exists():
            print(f"WARNING: {ep} missing — chunk {ci} tracklets get no embeddings")
            continue
        ed = np.load(ep)
        team = ed["team"].copy()
        means = ed["team_means"] if "team_means" in ed.files else None
        if means is not None and means.any():
            if ref_means is None:
                ref_means = means
            else:
                straight = float(ref_means[0] @ means[0] + ref_means[1] @ means[1])
                flipped = float(ref_means[0] @ means[1] + ref_means[1] @ means[0])
                if flipped > straight:
                    print(f"chunk {ci}: flipping team labels to align with chunk 0")
                    swap = team >= 0
                    team[swap] = 1 - team[swap]
        em["ids"].append(ed["ids"])
        em["emb"].append(ed["emb"])
        em["team"].append(team)
        em["n_crops"].append(ed["n_crops"])
    if not tr["t"]:
        _fail("no chunk artifacts found", "check --chunk-dirs paths")
    np.savez_compressed(out_dir / "tracks.npz", **{k: np.concatenate(v) for k, v in tr.items()})
    if em["ids"]:
        np.savez_compressed(
            out_dir / "tracklet_embeddings.npz",
            ids=np.concatenate(em["ids"]),
            emb=np.concatenate(em["emb"]),
            team=np.concatenate(em["team"]),
            n_crops=np.concatenate(em["n_crops"]),
        )
    if config is not None:
        (out_dir / "results.json").write_text(json.dumps(config, indent=2))
    print(f"combined {len(chunk_dirs)} chunk(s) -> {out_dir}")


def build_tracklets(tracks_path: Path, emb_path: Path) -> Tracklets:
    data = np.load(tracks_path)
    t, tid, xyxy = data["t"], data["tid"], data["xyxy"]
    if len(t) == 0:
        print("WARNING: tracks.npz is empty — no tracklets to merge")
        z = np.zeros(0)
        return Tracklets(
            tid=z.astype(np.int32), first_t=z.astype(np.float32), last_t=z.astype(np.float32),
            first_c=np.zeros((0, 2), dtype=np.float32), last_c=np.zeros((0, 2), dtype=np.float32),
            n_frames=z.astype(np.int32), team=z.astype(np.int8),
            emb=np.zeros((0, 1), dtype=np.float32), has_emb=z.astype(bool),
        )
    order = np.lexsort((t, tid))  # by tid, then time within tid
    tid_s, t_s, box_s = tid[order], t[order], xyxy[order]
    starts = np.flatnonzero(np.r_[True, tid_s[1:] != tid_s[:-1]])
    ends = np.r_[starts[1:], len(tid_s)] - 1
    centers = np.stack(
        [(box_s[:, 0] + box_s[:, 2]) * 0.5, (box_s[:, 1] + box_s[:, 3]) * 0.5], axis=1
    )
    tids = tid_s[starts].astype(np.int32)
    k = len(tids)

    team = np.full(k, -1, dtype=np.int8)
    emb = np.zeros((k, 1), dtype=np.float32)
    has_emb = np.zeros(k, dtype=bool)
    if emb_path.exists():
        ed = np.load(emb_path)
        eids, emat, eteam = ed["ids"], ed["emb"], ed["team"]
        emb = np.zeros((k, emat.shape[1]), dtype=np.float32)
        idx_of = {int(t_): i for i, t_ in enumerate(eids)}
        for j, t_ in enumerate(tids):
            i = idx_of.get(int(t_))
            if i is not None:
                row = emat[i]
                if not np.isfinite(row).all():  # bad crop → NaN embedding: treat as missing
                    continue
                emb[j] = row
                team[j] = eteam[i]
                has_emb[j] = True
    else:
        print(f"WARNING: {emb_path.name} not found — merging on spatial/gap rules only")

    return Tracklets(
        tid=tids,
        first_t=t_s[starts].astype(np.float32),
        last_t=t_s[ends].astype(np.float32),
        first_c=centers[starts].astype(np.float32),
        last_c=centers[ends].astype(np.float32),
        n_frames=(ends - starts + 1).astype(np.int32),
        team=team,
        emb=emb,
        has_emb=has_emb,
    )


def filter_min_duration(tl: Tracklets, min_duration: float, dt: float) -> tuple[Tracklets, int]:
    keep = tl.durations(dt) >= min_duration
    dropped = int((~keep).sum())
    kept = Tracklets(
        tid=tl.tid[keep],
        first_t=tl.first_t[keep],
        last_t=tl.last_t[keep],
        first_c=tl.first_c[keep],
        last_c=tl.last_c[keep],
        n_frames=tl.n_frames[keep],
        team=tl.team[keep],
        emb=tl.emb[keep],
        has_emb=tl.has_emb[keep],
    )
    return kept, dropped


# --------------------------------------------------------------------------- activity windows


def detect_activity_windows(tl: Tracklets) -> tuple[list[list[float]], float | None]:
    """Per 10s bin, count distinct tracklets with a team label overlapping the bin.
    Active bin: >= ACTIVITY_MIN_TRACKLETS. Returns (windows, estimated_kickoff_s)."""
    if len(tl) == 0:
        return [], None
    # Count ALL kept tracklets: the pitch mask upstream already removed sideline
    # people, and short tracklets often lack embeddings/team labels — filtering to
    # team-labeled ones would undercount activity by however many missed the crop
    # sampler. Refs/keepers counting toward "people on pitch" is fine for this signal.
    use = np.ones(len(tl), dtype=bool)
    n_bins = int(float(tl.last_t.max()) // ACTIVITY_BIN_S) + 1
    counts = np.zeros(n_bins, dtype=np.int32)
    for f, last in zip(tl.first_t[use], tl.last_t[use]):
        b0 = int(f // ACTIVITY_BIN_S)
        b1 = int(last // ACTIVITY_BIN_S)
        counts[b0 : b1 + 1] += 1
    active = counts >= ACTIVITY_MIN_TRACKLETS
    windows: list[list[float]] = []
    i = 0
    while i < n_bins:
        if active[i]:
            j = i
            while j + 1 < n_bins and active[j + 1]:
                j += 1
            windows.append([i * ACTIVITY_BIN_S, (j + 1) * ACTIVITY_BIN_S])
            i = j + 1
        else:
            i += 1
    kickoff = next((s for s, e in windows if e - s >= KICKOFF_MIN_WINDOW_S), None)
    return windows, kickoff


# --------------------------------------------------------------------------- union-find merge


class IntervalDSU:
    """Union-find whose roots carry a coalesced interval set; unions that would
    create > MAX_OVERLAP_S of cross-overlap (one person in two places) are rejected."""

    def __init__(self, intervals: list[tuple[float, float]]) -> None:
        self.parent = list(range(len(intervals)))
        self.iv: dict[int, list[tuple[float, float]]] = {i: [v] for i, v in enumerate(intervals)}

    def find(self, x: int) -> int:
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    @staticmethod
    def _cross_overlap(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
        i = j = 0
        total = 0.0
        while i < len(a) and j < len(b):
            s = max(a[i][0], b[j][0])
            e = min(a[i][1], b[j][1])
            if e > s:
                total += e - s
            if a[i][1] < b[j][1]:
                i += 1
            else:
                j += 1
        return total

    @staticmethod
    def _coalesce(ivs: list[tuple[float, float]]) -> list[tuple[float, float]]:
        ivs.sort()
        out = [list(ivs[0])]
        for s, e in ivs[1:]:
            if s <= out[-1][1]:
                out[-1][1] = max(out[-1][1], e)
            else:
                out.append([s, e])
        return [(s, e) for s, e in out]

    def try_union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self._cross_overlap(self.iv[ra], self.iv[rb]) > MAX_OVERLAP_S:
            return False
        if len(self.iv[ra]) < len(self.iv[rb]):  # attach smaller interval set
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.iv[ra] = self._coalesce(self.iv[ra] + self.iv.pop(rb))
        return True


def candidate_pairs(
    tl: Tracklets, sim_threshold: float, max_gap: float, frame_width: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """All gated (A, B) pairs with A.last_t < B.first_t <= A.last_t + max_gap.

    Returns (a_idx, b_idx, score) sorted by score DESCENDING. Score is cosine
    similarity for embedding pairs; no-embedding pairs get a negative pseudo-score
    (-gap - dist_frac) so they sort after every embedding pair, closest-first.
    """
    k = len(tl)
    order = np.argsort(tl.first_t, kind="stable")
    sorted_firsts = tl.first_t[order]
    spatial_max = SPATIAL_FRAC * frame_width

    a_out: list[np.ndarray] = []
    b_out: list[np.ndarray] = []
    s_out: list[np.ndarray] = []
    for a in range(k):
        lo = int(np.searchsorted(sorted_firsts, tl.last_t[a], side="right"))
        hi = int(np.searchsorted(sorted_firsts, tl.last_t[a] + max_gap, side="right"))
        if lo >= hi:
            continue
        cand = order[lo:hi]
        cand = cand[cand != a]
        if len(cand) == 0:
            continue
        gap = tl.first_t[cand] - tl.last_t[a]
        team_ok = (tl.team[cand] == tl.team[a]) | (tl.team[cand] < 0) | (tl.team[a] < 0)
        dist = np.linalg.norm(tl.first_c[cand] - tl.last_c[a], axis=1)
        near = dist < spatial_max

        if tl.has_emb[a]:
            both = tl.has_emb[cand]
            sims = np.full(len(cand), -1.0, dtype=np.float32)
            if both.any():
                sims[both] = tl.emb[cand[both]] @ tl.emb[a]  # unit-norm: dot == cosine
            short_gap = gap < SPATIAL_GATE_MAX_GAP_S
            emb_pass = both & team_ok & np.where(
                short_gap,
                near & (sims >= sim_threshold),
                sims >= sim_threshold + LONG_GAP_SIM_BONUS,
            )
        else:
            both = np.zeros(len(cand), dtype=bool)
            sims = np.full(len(cand), -1.0, dtype=np.float32)
            emb_pass = both  # all False

        # either side lacks an embedding: short-gap spatial continuity only
        noemb_pass = (~both | ~tl.has_emb[a]) & team_ok & (gap < NOEMB_MAX_GAP_S) & near
        noemb_pass &= ~emb_pass

        if emb_pass.any():
            a_out.append(np.full(int(emb_pass.sum()), a, dtype=np.int32))
            b_out.append(cand[emb_pass].astype(np.int32))
            s_out.append(sims[emb_pass].astype(np.float32))
        if noemb_pass.any():
            a_out.append(np.full(int(noemb_pass.sum()), a, dtype=np.int32))
            b_out.append(cand[noemb_pass].astype(np.int32))
            score = (-gap[noemb_pass] - dist[noemb_pass] / frame_width).astype(np.float32)
            s_out.append(score)

    if not a_out:
        return np.zeros(0, np.int32), np.zeros(0, np.int32), np.zeros(0, np.float32)
    a_arr = np.concatenate(a_out)
    b_arr = np.concatenate(b_out)
    s_arr = np.concatenate(s_out)
    desc = np.argsort(-s_arr, kind="stable")
    return a_arr[desc], b_arr[desc], s_arr[desc]


@dataclass
class Entity:
    entity_id: int
    member_idx: list[int]  # indices into the filtered Tracklets arrays
    team: int
    first_s: float
    last_s: float
    visible_s: float


def merge_entities(tl: Tracklets, a: np.ndarray, b: np.ndarray, dt: float) -> tuple[list[Entity], int]:
    intervals = [(float(f), float(last)) for f, last in zip(tl.first_t, tl.last_t)]
    dsu = IntervalDSU(intervals)
    merges = 0
    for ai, bi in zip(a, b):
        if dsu.try_union(int(ai), int(bi)):
            merges += 1

    groups: dict[int, list[int]] = {}
    for i in range(len(tl)):
        groups.setdefault(dsu.find(i), []).append(i)

    entities: list[Entity] = []
    for root, members in groups.items():
        teams = tl.team[members]
        v0, v1 = int((teams == 0).sum()), int((teams == 1).sum())
        team = 0 if v0 > v1 else 1 if v1 > v0 else -1
        ivs = dsu.iv[root]
        visible = sum(e - s for s, e in ivs) + len(ivs) * dt
        entities.append(
            Entity(
                entity_id=0,
                member_idx=members,
                team=team,
                first_s=float(tl.first_t[members].min()),
                last_s=float(tl.last_t[members].max()),
                visible_s=float(visible),
            )
        )
    entities.sort(key=lambda en: -en.visible_s)
    for n, en in enumerate(entities, start=1):
        en.entity_id = n
    return entities, merges


# --------------------------------------------------------------------------- render


def choose_window(
    windows: list[list[float]],
    kickoff: float | None,
    window_seconds: float,
    override: float | None,
    video_duration: float,
) -> float:
    latest_valid = max(0.0, video_duration - window_seconds)
    if override is not None:
        return min(max(0.0, override), latest_valid)
    ordered = list(windows)
    if kickoff is not None:  # prefer the kickoff window
        ordered.sort(key=lambda w: (w[0] != kickoff,))
    for s, e in ordered:
        if e - s >= window_seconds:
            # skip the opening scramble where there's room, stay inside the window
            return min(s + min(60.0, (e - s) - window_seconds), latest_valid)
    if windows:
        return min(windows[0][0], latest_valid)
    print("WARNING: no activity windows found — rendering from 40% of the video")
    return min(max(0.0, 0.4 * video_duration), latest_valid)


def rows_by_frame_key(
    tracks_path: Path, sample_fps: float, start_s: float, end_s: float
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """Map int(round(t * sample_fps)) -> (tids, xyxy) for rows near the window.
    Keying on the rounded sample grid gives a +/- 1/(2*sample_fps) match tolerance."""
    data = np.load(tracks_path)
    t, tid, xyxy = data["t"], data["tid"], data["xyxy"]
    sel = (t >= start_s - 1.0) & (t <= end_s + 1.0)
    t, tid, xyxy = t[sel], tid[sel], xyxy[sel]
    if len(t) == 0:
        return {}
    keys = np.round(t.astype(np.float64) * sample_fps).astype(np.int64)
    out: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    order = np.argsort(keys, kind="stable")
    keys, tid, xyxy = keys[order], tid[order], xyxy[order]
    starts = np.flatnonzero(np.r_[True, keys[1:] != keys[:-1]])
    ends = np.r_[starts[1:], len(keys)]
    for s, e in zip(starts, ends):
        out[int(keys[s])] = (tid[s:e], xyxy[s:e])
    return out


def render_clip(
    video: Path,
    out_path: Path,
    sample_fps: float,
    start_s: float,
    duration_s: float,
    rows: dict[int, tuple[np.ndarray, np.ndarray]],
    entity_of_tid: dict[int, int],
    team_of_entity: dict[int, int],
) -> int:
    interval = 1.0 / sample_fps
    end_s = start_s + duration_s
    writer: cv2.VideoWriter | None = None
    written = 0
    with av.open(str(video)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        container.seek(int(start_s / stream.time_base), stream=stream, backward=True)
        # same cadence as run_spike.iter_sampled_frames: grid anchored at t=0
        next_t = math.floor(start_s / interval) * interval
        for frame in container.decode(stream):
            t = frame.time
            if t is None:
                continue
            if t > end_s:
                break
            if t + 1e-9 < next_t:
                continue
            while next_t <= t:
                next_t += interval
            if t < start_s:  # pre-roll from the seek keyframe; cadence already advanced
                continue
            rgb = frame.to_ndarray(format="rgb24")
            if writer is None:
                h, w = rgb.shape[:2]
                out_path.parent.mkdir(parents=True, exist_ok=True)
                writer = cv2.VideoWriter(
                    str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), sample_fps, (w, h)
                )
            scene = rgb.copy()
            match = rows.get(int(np.round(np.float64(t) * sample_fps)))  # same rounding as rows_by_frame_key
            if match is not None:
                tids, boxes = match
                for tid, box in zip(tids, boxes):
                    eid = entity_of_tid.get(int(tid))
                    if eid is None:  # tracklet dropped by the min-duration filter
                        continue
                    color = TEAM_COLORS_RGB[team_of_entity.get(eid, -1)]
                    x1, y1, x2, y2 = (int(v) for v in box)
                    cv2.rectangle(scene, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(
                        scene, f"E{eid}", (x1, max(12, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA,
                    )
            writer.write(cv2.cvtColor(scene, cv2.COLOR_RGB2BGR))
            written += 1
    if writer is not None:
        writer.release()
    if written == 0:
        print(f"WARNING: rendered 0 frames (window {start_s:.0f}s+{duration_s:.0f}s vs video) — no clip produced")
    return written


# --------------------------------------------------------------------------- reporting


def duration_stats(values: np.ndarray | list[float]) -> dict[str, float]:
    vals = [float(v) for v in values]
    if not vals:
        return {"mean_s": 0.0, "median_s": 0.0, "max_s": 0.0}
    return {
        "mean_s": round(statistics.mean(vals), 2),
        "median_s": round(statistics.median(vals), 2),
        "max_s": round(max(vals), 2),
    }


# --------------------------------------------------------------------------- main


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results-dir", required=True, type=Path, help="dir with tracks.npz etc. (or combine target with --chunk-dirs)")
    p.add_argument("--chunk-dirs", nargs="+", type=Path, default=None,
                   help="chunked run_spike output dirs to combine into --results-dir first")
    p.add_argument("--video", required=True, type=Path, help="source video for rendering")
    p.add_argument("--window-start", type=float, default=None, help="render window start (s)")
    p.add_argument("--window-seconds", type=float, default=45.0)
    p.add_argument("--sim-threshold", type=float, default=0.60, help="cosine sim merge threshold")
    p.add_argument("--max-gap", type=float, default=15.0, help="max temporal gap to bridge (s)")
    p.add_argument("--min-duration", type=float, default=1.0, help="drop shorter tracklets (s)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.chunk_dirs:
        combine_chunks(args.chunk_dirs, args.results_dir)
    tracks_path = args.results_dir / "tracks.npz"
    if not tracks_path.exists():
        _fail(f"tracks.npz not found in {args.results_dir}", "run run_spike.py first")
    if not args.video.exists():
        _fail(f"video not found: {args.video}", "pass the same file run_spike.py processed")

    sample_fps, frame_width, video_duration = load_config(args.results_dir, args.video)
    dt = 1.0 / sample_fps

    raw = build_tracklets(tracks_path, args.results_dir / "tracklet_embeddings.npz")
    tl, dropped = filter_min_duration(raw, args.min_duration, dt)
    print(
        f"tracklets: {len(raw)} raw -> {len(tl)} after min-duration filter "
        f"({dropped} dropped as < {args.min_duration:.1f}s noise); "
        f"{int(tl.has_emb.sum())} have embeddings"
    )

    windows, kickoff = detect_activity_windows(tl)
    print(f"activity : {len(windows)} window(s), estimated kickoff "
          f"{'n/a' if kickoff is None else f'{kickoff:.0f}s'}")

    a, b, scores = candidate_pairs(tl, args.sim_threshold, args.max_gap, frame_width)
    entities, merges = merge_entities(tl, a, b, dt)
    print(f"merging  : {len(a)} candidate pairs, {merges} unions accepted -> {len(entities)} entities")

    entity_of_tid: dict[int, int] = {}
    team_of_entity: dict[int, int] = {}
    for en in entities:
        team_of_entity[en.entity_id] = en.team
        for i in en.member_idx:
            entity_of_tid[int(tl.tid[i])] = en.entity_id

    visible = sorted((en.visible_s for en in entities), reverse=True)
    ten_min_plus = sum(1 for en in entities if en.visible_s >= 600.0)
    top22 = round(sum(visible[:22]), 1)
    start = choose_window(windows, kickoff, args.window_seconds, args.window_start, video_duration)

    report: dict[str, Any] = {
        "raw_tracklets": len(raw),
        "after_min_duration_filter": len(tl),
        "merged_entities": len(entities),
        "params": {
            "sim_threshold": args.sim_threshold,
            "max_gap_s": args.max_gap,
            "min_duration_s": args.min_duration,
            "sample_fps": sample_fps,
            "max_overlap_s": MAX_OVERLAP_S,
            "spatial_gate_frac_of_width": SPATIAL_FRAC,
            "long_gap_sim_bonus": LONG_GAP_SIM_BONUS,
            "activity_bin_s": ACTIVITY_BIN_S,
            "activity_min_tracklets": ACTIVITY_MIN_TRACKLETS,
        },
        "duration_stats_before": duration_stats(raw.durations(dt)),
        "duration_stats_after": duration_stats([en.visible_s for en in entities]),
        "activity_windows": [[round(s, 1), round(e, 1)] for s, e in windows],
        "estimated_kickoff_s": kickoff,
        "entities_covering_10min_plus": ten_min_plus,  # visible_s >= 600
        "sum_visible_seconds_top22": top22,
        "render_window": [round(start, 1), round(start + args.window_seconds, 1)],
    }
    (args.results_dir / "merge_report.json").write_text(json.dumps(report, indent=2))
    (args.results_dir / "entities.json").write_text(
        json.dumps(
            [
                {
                    "entity_id": en.entity_id,
                    "member_tids": sorted(int(tl.tid[i]) for i in en.member_idx),
                    "team": en.team,
                    "first_s": round(en.first_s, 2),
                    "last_s": round(en.last_s, 2),
                    "visible_s": round(en.visible_s, 2),
                }
                for en in entities
            ],
            indent=2,
        )
    )

    print(f"render   : window [{start:.1f}s, {start + args.window_seconds:.1f}s]")
    rows = rows_by_frame_key(tracks_path, sample_fps, start, start + args.window_seconds)
    clip_path = args.results_dir / "merged_clip.mp4"
    frames = render_clip(
        args.video, clip_path, sample_fps, start, args.window_seconds,
        rows, entity_of_tid, team_of_entity,
    )

    before, after = report["duration_stats_before"], report["duration_stats_after"]
    print(
        f"\nsummary  : {len(raw)} raw tracklets -> {len(entities)} entities | "
        f"median duration {before['median_s']:.1f}s -> {after['median_s']:.1f}s | "
        f"{ten_min_plus} entities visible 10min+ | top-22 visible sum {top22:.0f}s"
    )
    print(f"wrote {args.results_dir / 'merge_report.json'}")
    print(f"wrote {args.results_dir / 'entities.json'}")
    print(f"wrote {clip_path} ({frames} frames)")


if __name__ == "__main__":
    main()
