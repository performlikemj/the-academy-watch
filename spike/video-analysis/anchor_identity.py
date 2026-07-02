#!/usr/bin/env python3
"""Jersey-number identity-anchor pass: name merged entities with a local MLX VLM.

Consumes the artifacts produced by merge_tracklets.py (tracks.npz, entities.json,
merge_report.json, results.json) plus the source video. Real players fragment into
several entities; this pass reads jersey numbers from large near-side crops with a
local VLM, votes per entity (a number is never trusted without >= 2 agreeing
reads), then merges entities that share (team, jersey_number) when their time
spans do not overlap. Far-side/small/blurry crops are gated out BEFORE the VLM —
they are empirically unreadable and the model is not relied on to refuse them.

Stages cache into --out-dir; the expensive stages (EXTRACT, READ) are skipped on
re-run when their cache exists, so gate/vote/merge thresholds can be iterated
cheaply. READ is incremental: only gated crops missing from reads.json hit the VLM.

Outputs in --out-dir:
  candidates.json    planned crop boxes per entity
  crops/ + crops_index.json   extracted JPEG crops with Laplacian sharpness
  reads.json         raw VLM reads per gated crop
  votes.json         per-entity jersey/role vote tallies
  identities.json    anchored players + conflicted + unanchored entities
  anchor_report.json funnel counts, gate distribution, anchors, VLM wall-clock
  anchored_clip.mp4  render with "#10" labels for anchored players

Usage:
  .venv-vlm/bin/python anchor_identity.py --results-dir results/v8/combined \
      --video footage/match.mp4
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NoReturn


def _fail(what: str, hint: str) -> NoReturn:
    print(f"ERROR: {what}\n  fix: {hint}", file=sys.stderr)
    sys.exit(1)


try:
    import numpy as np
except ImportError as e:
    _fail(f"numpy import failed: {e}", "pip install numpy")

try:
    import cv2
except ImportError as e:
    _fail(f"opencv import failed: {e}", "pip install opencv-python-headless==4.13.0.92")

try:
    import av
except ImportError as e:
    _fail(f"PyAV import failed: {e}", "pip install av==17.1.0")

try:
    from merge_tracklets import TEAM_COLORS_RGB, load_config, rows_by_frame_key
except ImportError as e:
    _fail(f"merge_tracklets import failed: {e}", "run from the directory containing merge_tracklets.py")


TEMPORAL_SPREAD_S = 15.0  # preferred min spacing between crops of one entity
SEEK_GAP_S = 5.0  # decode sequentially unless the next crop is further ahead
PAD_X_FRAC, PAD_Y_FRAC = 0.25, 0.12
UPSCALE = 2.0
JPEG_QUALITY = 95
MAX_TOKENS = 60
MIN_VOTES = 2  # single-frame reads are never trusted
GREY_ROLES = {"referee", "not_a_player"}
MIN_DRAW_X_SPREAD_PX = 250  # entities moving less than this (x-center 5-95pct) aren't drawn

PROMPT = (
    'Look at this football player. Reply ONLY with JSON: '
    '{"jersey_number": <number or null if not readable>, '
    '"shirt_color": "<color>", '
    '"role": "<outfield|goalkeeper|referee|not_a_player>"}'
)


def parse_json_block(text: str) -> dict | None:
    m = re.search(r"\{.*?\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------- 1. plan


def _pick_spread(ts: np.ndarray, max_n: int) -> list[int]:
    """Indices into ts (tallest-first order): greedy passes keeping picks
    >= spread apart, halving the spread requirement (15s -> 7.5s -> ... -> 0)
    until max_n picks — maximal temporal spread where possible, tallest preferred.
    Adjacent-frame duplicates would give correlated votes; avoid them when we can."""
    picked: list[int] = []
    chosen: set[int] = set()
    spread = TEMPORAL_SPREAD_S
    while len(picked) < max_n:
        for i in range(len(ts)):
            if len(picked) >= max_n:
                break
            if i in chosen:
                continue
            if all(abs(float(ts[i]) - float(ts[j])) >= spread for j in picked):
                picked.append(i)
                chosen.add(i)
        if spread == 0.0:
            break
        spread = spread / 2.0 if spread >= 0.16 else 0.0
    return picked


def plan_candidates(
    tracks_path: Path, entities: list[dict], min_height: float, max_crops: int
) -> dict[str, Any]:
    """Per team-labeled entity, pick up to max_crops boxes with height >= min_height,
    preferring the tallest, temporally spread where possible."""
    data = np.load(tracks_path)
    t, tid, frame_idx, xyxy = data["t"], data["tid"], data["frame"], data["xyxy"]
    heights = xyxy[:, 3] - xyxy[:, 1]

    eligible = [e for e in entities if e["team"] in (0, 1)]
    tid_to_eid = {int(m): int(e["entity_id"]) for e in eligible for m in e["member_tids"]}

    uniq, inv = np.unique(tid, return_inverse=True)
    eid_of_uniq = np.array([tid_to_eid.get(int(u), 0) for u in uniq], dtype=np.int64)
    row_eid = eid_of_uniq[inv]

    candidates: list[dict] = []
    sel = np.flatnonzero((row_eid > 0) & (heights >= min_height))
    if len(sel):
        order = sel[np.lexsort((-heights[sel], row_eid[sel]))]  # by entity, then tallest
        bounds = np.flatnonzero(np.r_[True, row_eid[order][1:] != row_eid[order][:-1]])
        bounds = np.r_[bounds, len(order)]
        for s, e in zip(bounds[:-1], bounds[1:]):
            rows = order[s:e]  # tallest-first within this entity
            eid = int(row_eid[rows[0]])
            picked = _pick_spread(t[rows], max_crops)
            for k, j in enumerate(sorted(picked, key=lambda j: float(t[rows[j]]))):
                r = rows[j]
                candidates.append(
                    {
                        "crop_id": f"e{eid:04d}_{k:02d}",
                        "entity_id": eid,
                        "t": round(float(t[r]), 4),
                        "frame": int(frame_idx[r]),
                        "xyxy": [round(float(v), 1) for v in xyxy[r]],
                        "height": round(float(heights[r]), 1),
                    }
                )

    return {
        "params": {
            "min_height_px": min_height,
            "max_crops_per_entity": max_crops,
            "temporal_spread_s": TEMPORAL_SPREAD_S,
        },
        "entities_total": len(entities),
        "entities_team_labeled": len(eligible),
        "entities_skipped_unlabeled_team": len(entities) - len(eligible),
        "entities_with_candidates": len({c["entity_id"] for c in candidates}),
        "candidates": candidates,
    }


# --------------------------------------------------------------------------- 2. extract


def _save_crop(rgb: np.ndarray, cand: dict, crops_dir: Path) -> dict | None:
    img_h, img_w = rgb.shape[:2]
    x1, y1, x2, y2 = cand["xyxy"]
    bw, bh = x2 - x1, y2 - y1
    xa = max(0, int(round(x1 - PAD_X_FRAC * bw)))
    xb = min(img_w, int(round(x2 + PAD_X_FRAC * bw)))
    ya = max(0, int(round(y1 - PAD_Y_FRAC * bh)))
    yb = min(img_h, int(round(y2 + PAD_Y_FRAC * bh)))
    if xb - xa < 4 or yb - ya < 4:
        print(f"WARNING: degenerate crop {cand['crop_id']} — skipped")
        return None
    crop = rgb[ya:yb, xa:xb]
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    up = cv2.resize(crop, None, fx=UPSCALE, fy=UPSCALE, interpolation=cv2.INTER_CUBIC)
    name = f"{cand['crop_id']}.jpg"
    cv2.imwrite(
        str(crops_dir / name),
        cv2.cvtColor(up, cv2.COLOR_RGB2BGR),
        [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
    )
    return {
        "file": name,
        "crop_id": cand["crop_id"],
        "entity_id": cand["entity_id"],
        "t": cand["t"],
        "frame": cand["frame"],
        "height": cand["height"],
        "laplacian_var": round(lap_var, 2),
    }


def extract_crops(video: Path, candidates: list[dict], crops_dir: Path) -> list[dict]:
    """Decode the video once in t-order over all candidates, seeking only across
    gaps > SEEK_GAP_S, and save padded upscaled JPEG crops."""
    crops_dir.mkdir(parents=True, exist_ok=True)
    cands = sorted(candidates, key=lambda c: c["t"])
    index: list[dict] = []
    t0 = time.perf_counter()
    with av.open(str(video)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        decoder: Iterator | None = None
        frame_t = -1e9
        i = 0
        while i < len(cands):
            target = cands[i]["t"]
            if decoder is None or target - frame_t > SEEK_GAP_S:
                container.seek(int(target / stream.time_base), stream=stream, backward=True)
                decoder = container.decode(stream)
            try:
                while True:
                    frame = next(decoder)
                    if frame.time is None:
                        continue
                    frame_t = float(frame.time)
                    if frame_t >= target - 1e-3:
                        break
            except StopIteration:
                print(f"WARNING: video ended before t={target:.1f}s — {len(cands) - i} candidate(s) skipped")
                break
            rgb = frame.to_ndarray(format="rgb24")
            while i < len(cands) and cands[i]["t"] <= frame_t + 1e-3:
                entry = _save_crop(rgb, cands[i], crops_dir)
                if entry is not None:
                    index.append(entry)
                i += 1
            if len(index) and len(index) % 200 == 0:
                el = time.perf_counter() - t0
                print(f"  extracted {len(index)}/{len(cands)} crops ({el:.0f}s)")
    return index


# --------------------------------------------------------------------------- 3. gate


def gate_crops(
    index: list[dict], min_sharpness: float, min_height: float
) -> tuple[list[dict], dict[str, Any]]:
    """Drop crops the VLM cannot read (small or blurry) BEFORE inference — far-side
    crops are empirically unreadable; do not rely on the model refusing them."""
    kept = [c for c in index if c["laplacian_var"] >= min_sharpness and c["height"] >= min_height]
    laps = np.array([c["laplacian_var"] for c in index], dtype=np.float64)
    deciles = np.percentile(laps, np.arange(0, 101, 10)).round(1).tolist() if len(laps) else []
    stats = {
        "crops_total": len(index),
        "crops_kept": len(kept),
        "crops_dropped": len(index) - len(kept),
        "min_sharpness": min_sharpness,
        "min_height_px": min_height,
        "laplacian_deciles_0_to_100": deciles,
    }
    return kept, stats


# --------------------------------------------------------------------------- 4. read


def read_crops(
    model_name: str, crops_dir: Path, kept: list[dict], reads_path: Path, force: bool
) -> tuple[dict[str, Any], bool]:
    """VLM-read gated crops. Incremental: crops already in reads.json are not
    re-read; the model is only loaded if there is new work. Returns (payload, changed)."""
    cached: dict[str, dict] = {}
    elapsed_prev = 0.0
    if reads_path.exists() and not force:
        prev = json.loads(reads_path.read_text())
        cached = {r["file"]: r for r in prev.get("reads", [])}
        elapsed_prev = float(prev.get("vlm_elapsed_s", 0.0))
    todo = [c for c in kept if c["file"] not in cached]
    if not todo:
        print(f"read     : cached ({len(cached)} reads, {elapsed_prev:.0f}s VLM wall-clock)")
        return {"model": model_name, "vlm_elapsed_s": elapsed_prev, "reads": list(cached.values())}, False

    try:
        from mlx_vlm import generate, load
        from mlx_vlm.prompt_utils import apply_chat_template
    except ImportError as e:
        _fail(f"mlx_vlm import failed: {e}", "pip install mlx-vlm (Apple Silicon only)")

    print(f"read     : loading {model_name} ... ({len(todo)} crops to read)")
    model, processor = load(model_name)
    config = model.config
    t0 = time.perf_counter()
    for i, entry in enumerate(todo):
        formatted = apply_chat_template(processor, config, PROMPT, num_images=1)
        out = generate(
            model, processor, formatted, [str(crops_dir / entry["file"])],
            max_tokens=MAX_TOKENS, temperature=0.0, verbose=False,
        )
        text = out.text if hasattr(out, "text") else str(out)
        parsed = parse_json_block(text)
        cached[entry["file"]] = {
            "file": entry["file"],
            "entity_id": entry["entity_id"],
            "parsed": parsed,
            "raw": None if parsed else text[:300],
        }
        if (i + 1) % 10 == 0 or i + 1 == len(todo):
            el = time.perf_counter() - t0
            eta = el / (i + 1) * (len(todo) - i - 1)
            print(f"  [{i + 1}/{len(todo)}] {el:.0f}s elapsed, ~{eta:.0f}s left")
    elapsed = elapsed_prev + (time.perf_counter() - t0)
    return {"model": model_name, "vlm_elapsed_s": round(elapsed, 1), "reads": list(cached.values())}, True


# --------------------------------------------------------------------------- 5. vote


def norm_number(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if 1 <= v <= 99 else None
    if isinstance(v, float) and v.is_integer():
        return norm_number(int(v))
    if isinstance(v, str) and v.strip().isdigit():
        return norm_number(int(v.strip()))
    return None


def _modal_role(roles: Counter) -> str | None:
    if not roles:
        return None
    return max(roles.items(), key=lambda kv: (kv[1], kv[0]))[0]


def vote_entities(reads: list[dict], kept_files: set[str], entities: list[dict]) -> dict[str, Any]:
    """Per entity: jersey anchored iff the modal number has >= MIN_VOTES reads AND
    strictly more votes than any rival number. Role is the modal role."""
    team_of = {e["entity_id"]: e["team"] for e in entities}
    by_entity: dict[int, list[dict]] = {}
    for r in reads:
        if r["file"] in kept_files and r["parsed"]:
            by_entity.setdefault(r["entity_id"], []).append(r["parsed"])

    rows: list[dict] = []
    for eid, parsed_list in sorted(by_entity.items()):
        nums = Counter(
            n for p in parsed_list if (n := norm_number(p.get("jersey_number"))) is not None
        )
        roles = Counter(p["role"] for p in parsed_list if isinstance(p.get("role"), str))
        number, anchored, confidence, contaminated = None, False, None, False
        if nums:
            mc = nums.most_common()
            top, top_n = mc[0]
            # OCR digit-doubling (4 vs 44) supports the top number rather than rivalling it.
            # Caveat: 1 vs 11 is genuinely ambiguous and also matches — accepted for now.
            def _is_doubling(a: int, b: int) -> bool:
                return str(a) * 2 == str(b) or str(b) * 2 == str(a)

            rivals = [(n, c) for n, c in mc[1:] if not _is_doubling(top, n)]
            second_n = rivals[0][1] if rivals else 0
            # Two multiply-attested numbers in ONE entity = likely tracker-swap splice
            # (two players' tracklets merged into one entity). Never anchor those.
            contaminated = second_n >= 2
            anchored = top_n >= MIN_VOTES and top_n > second_n and not contaminated
            if anchored:
                number = top
                confidence = "high" if (second_n == 0 or top_n >= max(3, 2 * second_n)) else "low"
        rows.append(
            {
                "entity_id": eid,
                "team": team_of.get(eid, -1),
                "n_parsed_reads": len(parsed_list),
                "number_votes": {str(k): v for k, v in sorted(nums.items())},
                "role_votes": dict(sorted(roles.items())),
                "jersey_number": number,
                "role": _modal_role(roles),
                "anchored": anchored,
                "confidence": confidence,
                "contaminated": contaminated,
            }
        )
    return {"params": {"min_votes": MIN_VOTES, "confidence_tiers": True}, "entities": rows}


# --------------------------------------------------------------------------- 6. anchor-merge


def _span_overlap(a: dict, b: dict) -> float:
    return max(0.0, min(a["last_s"], b["last_s"]) - max(a["first_s"], b["first_s"]))


def anchor_merge(
    votes_rows: list[dict], entities: list[dict], max_overlap: float
) -> tuple[list[dict], list[dict], list[dict]]:
    """Group anchored entities by (team, jersey_number); merge the ones whose spans
    are pairwise compatible (overlap <= max_overlap). Entities that overlap the
    group by more are left UNMERGED and conflict-flagged — never forced. Unanchored
    entities are only listed, nothing automatic.

    Returns (identities, players, conflicts)."""
    ent_by_id = {e["entity_id"]: e for e in entities}
    vote_by_id = {v["entity_id"]: v for v in votes_rows}

    groups: dict[tuple[int, int], list[dict]] = {}
    for v in votes_rows:
        if v["anchored"] and v["team"] in (0, 1):
            groups.setdefault((v["team"], v["jersey_number"]), []).append(ent_by_id[v["entity_id"]])

    players: list[dict] = []
    conflicts: list[dict] = []
    accounted: set[int] = set()
    for (team, num), members in sorted(groups.items()):
        members = sorted(members, key=lambda m: -m["visible_s"])
        cluster = [members[0]]
        rejected: list[dict] = []
        for m in members[1:]:
            if max(_span_overlap(m, c) for c in cluster) <= max_overlap:
                cluster.append(m)
            else:
                rejected.append(m)
        key = f"T{team}#{num}"
        roles: Counter = Counter()
        for m in cluster:
            roles.update(vote_by_id[m["entity_id"]]["role_votes"])
        players.append(
            {
                "player_key": key,
                "team": team,
                "jersey_number": num,
                "role": _modal_role(roles) or "outfield",
                "member_entity_ids": sorted(m["entity_id"] for m in cluster),
                "first_s": round(min(m["first_s"] for m in cluster), 2),
                "last_s": round(max(m["last_s"] for m in cluster), 2),
                "visible_s_total": round(sum(m["visible_s"] for m in cluster), 2),
                "conflict_flags": [],
            }
        )
        accounted.update(m["entity_id"] for m in cluster)
        for m in rejected:
            eid = m["entity_id"]
            conflicts.append(
                {
                    "player_key": f"E{eid}",
                    "team": team,
                    "jersey_number": num,
                    "role": vote_by_id[eid]["role"],
                    "member_entity_ids": [eid],
                    "first_s": m["first_s"],
                    "last_s": m["last_s"],
                    "visible_s_total": m["visible_s"],
                    "conflict_flags": [
                        f"span overlap > {max_overlap}s with {key} (possible misread or team error)"
                    ],
                }
            )
            accounted.add(eid)

    unanchored = sorted(
        (e for e in entities if e["entity_id"] not in accounted), key=lambda e: -e["visible_s"]
    )
    unanchored_records = [
        {
            "player_key": f"E{e['entity_id']}",
            "team": e["team"],
            "jersey_number": None,
            "role": vote_by_id.get(e["entity_id"], {}).get("role"),
            "member_entity_ids": [e["entity_id"]],
            "first_s": e["first_s"],
            "last_s": e["last_s"],
            "visible_s_total": e["visible_s"],
            "conflict_flags": [],
        }
        for e in unanchored
    ]
    identities = players + conflicts + unanchored_records
    return identities, players, conflicts


# --------------------------------------------------------------------------- 7. render


def build_labels(
    entities: list[dict],
    identities: list[dict],
    votes_rows: list[dict],
    drawable: set[int] | None = None,
) -> dict[int, tuple[str, tuple[int, int, int]]]:
    """entity_id -> (label, RGB color). Anchored players get '#10' in team color
    ('#10?' when no member has a high-confidence vote); other drawable entities
    'E<id>'; voted referee/not_a_player is grey. Entities outside `drawable`
    (and not player members) get no label at all — the render skips them."""
    grey = TEAM_COLORS_RGB[-1]
    role_of = {v["entity_id"]: v["role"] for v in votes_rows}
    conf_of = {v["entity_id"]: v.get("confidence") for v in votes_rows}
    labels: dict[int, tuple[str, tuple[int, int, int]]] = {}
    for e in entities:
        eid = e["entity_id"]
        if drawable is not None and eid not in drawable:
            continue
        color = grey if role_of.get(eid) in GREY_ROLES else TEAM_COLORS_RGB.get(e["team"], grey)
        labels[eid] = (f"E{eid}", color)
    for rec in identities:
        if rec["jersey_number"] is None or rec["conflict_flags"]:
            continue
        color = grey if rec["role"] in GREY_ROLES else TEAM_COLORS_RGB.get(rec["team"], grey)
        high = any(conf_of.get(m) == "high" for m in rec["member_entity_ids"])
        text = f"#{rec['jersey_number']}" + ("" if high else "?")
        for eid in rec["member_entity_ids"]:
            labels[eid] = (text, color)
    return labels


def _box_iou(a: np.ndarray, b: np.ndarray) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    area = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / max(area, 1e-6)


def occluded_indices(draw: list[tuple[int, np.ndarray]], iou_thr: float = 0.4) -> set[int]:
    """Indices of boxes tangled with another box — number labels are suppressed
    there because tracker identity is unreliable mid-occlusion."""
    out: set[int] = set()
    for i in range(len(draw)):
        for j in range(i + 1, len(draw)):
            if _box_iou(draw[i][1], draw[j][1]) > iou_thr:
                out.add(i)
                out.add(j)
    return out


def render_anchored_clip(
    video: Path,
    out_path: Path,
    sample_fps: float,
    start_s: float,
    duration_s: float,
    rows: dict[int, tuple[np.ndarray, np.ndarray]],
    entity_of_tid: dict[int, int],
    labels: dict[int, tuple[str, tuple[int, int, int]]],
) -> int:
    interval = 1.0 / sample_fps
    end_s = start_s + duration_s
    writer: cv2.VideoWriter | None = None
    written = 0
    with av.open(str(video)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        container.seek(int(start_s / stream.time_base), stream=stream, backward=True)
        next_t = math.floor(start_s / interval) * interval  # grid anchored at t=0
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
                draw: list[tuple[int, np.ndarray]] = []
                for tid, box in zip(tids, boxes):
                    eid = entity_of_tid.get(int(tid))
                    if eid is None or eid not in labels:  # filtered out or dropped
                        continue
                    draw.append((eid, box))
                suppressed = occluded_indices(draw)
                for i, (eid, box) in enumerate(draw):
                    label, color = labels[eid]
                    x1, y1, x2, y2 = (int(v) for v in box)
                    cv2.rectangle(scene, (x1, y1), (x2, y2), color, 2)
                    if i not in suppressed:  # no number claims mid-tangle
                        cv2.putText(
                            scene, label, (x1, max(12, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA,
                        )
            writer.write(cv2.cvtColor(scene, cv2.COLOR_RGB2BGR))
            written += 1
    if writer is not None:
        writer.release()
    if written == 0:
        print(f"WARNING: rendered 0 frames (window {start_s:.0f}s+{duration_s:.0f}s vs video) — no clip produced")
    return written


def default_window_start(results_dir: Path) -> float:
    mr = results_dir / "merge_report.json"
    if not mr.exists():
        _fail(f"{mr} not found and no --window-start given", "pass --window-start explicitly")
    rw = json.loads(mr.read_text()).get("render_window")
    if not rw:
        _fail("merge_report.json lacks render_window", "pass --window-start explicitly")
    return float(rw[0])


# --------------------------------------------------------------------------- main


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results-dir", required=True, type=Path, help="dir with tracks.npz, entities.json, merge_report.json")
    p.add_argument("--video", required=True, type=Path, help="source video (same file merge_tracklets.py used)")
    p.add_argument("--out-dir", type=Path, default=None, help="cache/output dir (default <results-dir>/identity)")
    p.add_argument("--model", default="mlx-community/gemma-4-E4B-it-qat-4bit")
    p.add_argument("--min-height", type=float, default=110.0, help="min bbox height (px) for crop candidates and gate")
    p.add_argument("--min-sharpness", type=float, default=40.0, help="min Laplacian variance to send a crop to the VLM")
    p.add_argument("--max-crops-per-entity", type=int, default=8)
    p.add_argument("--max-overlap", type=float, default=2.0, help="max pairwise span overlap (s) when merging anchored entities")
    p.add_argument("--window-start", type=float, default=None, help="render window start (s); default merge_report.json render_window")
    p.add_argument("--window-seconds", type=float, default=45.0)
    p.add_argument("--skip-render", action="store_true")
    p.add_argument("--force", action="store_true", help="ignore caches and recompute every stage")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    tracks_path = args.results_dir / "tracks.npz"
    entities_path = args.results_dir / "entities.json"
    if not tracks_path.exists() or not entities_path.exists():
        _fail(f"tracks.npz / entities.json not found in {args.results_dir}", "run merge_tracklets.py first")
    if not args.video.exists():
        _fail(f"video not found: {args.video}", "pass the same file merge_tracklets.py processed")

    out_dir = args.out_dir or (args.results_dir / "identity")
    out_dir.mkdir(parents=True, exist_ok=True)
    crops_dir = out_dir / "crops"
    entities: list[dict] = json.loads(entities_path.read_text())
    sample_fps, _frame_width, video_duration = load_config(args.results_dir, args.video)

    # 1. PLAN
    cand_path = out_dir / "candidates.json"
    plan = None
    if cand_path.exists() and not args.force:
        plan = json.loads(cand_path.read_text())
        cached = plan.get("params", {})
        if (
            cached.get("min_height_px") != args.min_height
            or cached.get("max_crops_per_entity") != args.max_crops_per_entity
        ):
            print("plan     : cached params differ from CLI args — re-planning")
            plan = None
        else:
            print(f"plan     : cached ({len(plan['candidates'])} candidates; --force to re-plan)")
    if plan is None:
        plan = plan_candidates(tracks_path, entities, args.min_height, args.max_crops_per_entity)
        cand_path.write_text(json.dumps(plan, indent=2))
        print(
            f"plan     : {plan['entities_team_labeled']}/{plan['entities_total']} entities team-labeled "
            f"({plan['entities_skipped_unlabeled_team']} skipped as team -1), "
            f"{plan['entities_with_candidates']} with candidates, {len(plan['candidates'])} crops planned"
        )

    # 2. EXTRACT
    index_path = out_dir / "crops_index.json"
    if index_path.exists() and not args.force:
        index = json.loads(index_path.read_text())
        print(f"extract  : cached ({len(index)} crops)")
    else:
        index = extract_crops(args.video, plan["candidates"], crops_dir)
        index_path.write_text(json.dumps(index, indent=2))
        print(f"extract  : {len(index)} crops -> {crops_dir}")

    # 3. GATE (recomputed every run so --min-sharpness can be iterated)
    kept, gate_stats = gate_crops(index, args.min_sharpness, args.min_height)
    print(
        f"gate     : {gate_stats['crops_kept']}/{gate_stats['crops_total']} crops kept; "
        f"laplacian deciles {gate_stats['laplacian_deciles_0_to_100']}"
    )
    missing = [c["file"] for c in kept if not (crops_dir / c["file"]).exists()]
    if missing:
        _fail(f"{len(missing)} gated crop file(s) missing (e.g. {missing[0]})", "re-run with --force to re-extract")

    # 4. READ (incremental: only gated crops absent from reads.json hit the VLM)
    reads_path = out_dir / "reads.json"
    reads, changed = read_crops(args.model, crops_dir, kept, reads_path, args.force)
    if changed or not reads_path.exists():
        reads_path.write_text(json.dumps(reads, indent=2))
    n_parsed_kept = sum(1 for r in reads["reads"] if r["parsed"] and r["file"] in {c["file"] for c in kept})

    # 5. VOTE (cheap — recomputed every run; votes.json is the cached artifact)
    kept_files = {c["file"] for c in kept}
    votes = vote_entities(reads["reads"], kept_files, entities)
    (out_dir / "votes.json").write_text(json.dumps(votes, indent=2))
    anchored_rows = [v for v in votes["entities"] if v["anchored"]]
    print(f"vote     : {len(votes['entities'])} entities with >=1 parsed read, {len(anchored_rows)} anchored")

    # 6. ANCHOR-MERGE
    identities, players, conflicts = anchor_merge(votes["entities"], entities, args.max_overlap)
    (out_dir / "identities.json").write_text(json.dumps(identities, indent=2))
    vote_by_id = {v["entity_id"]: v for v in votes["entities"]}
    report: dict[str, Any] = {
        "params": {
            "model": args.model,
            "min_height_px": args.min_height,
            "min_sharpness": args.min_sharpness,
            "max_crops_per_entity": args.max_crops_per_entity,
            "max_overlap_s": args.max_overlap,
            "min_votes": MIN_VOTES,
            "temporal_spread_s": TEMPORAL_SPREAD_S,
        },
        "funnel": {
            "entities": len(entities),
            "entities_team_labeled": plan["entities_team_labeled"],
            "entities_with_candidates": plan["entities_with_candidates"],
            "crops_planned": len(plan["candidates"]),
            "crops_extracted": len(index),
            "crops_gated": len(kept),
            "reads_parsed": n_parsed_kept,
            "entities_with_read": len(votes["entities"]),
            "entities_anchored": len(anchored_rows),
            "final_players": len(players),
            "conflict_entities": len(conflicts),
        },
        "vlm_elapsed_s": reads["vlm_elapsed_s"],
        "gate": gate_stats,
        "anchors": [
            {
                "player_key": pl["player_key"],
                "member_entity_ids": pl["member_entity_ids"],
                "visible_s_total": pl["visible_s_total"],
                "votes_per_member": {
                    str(eid): vote_by_id[eid]["number_votes"] for eid in pl["member_entity_ids"]
                },
            }
            for pl in players
        ],
        "conflicts": conflicts,
    }
    (out_dir / "anchor_report.json").write_text(json.dumps(report, indent=2))
    print(
        f"anchor   : {len(anchored_rows)} anchored entities -> {len(players)} players "
        f"({len(conflicts)} conflict-flagged): {', '.join(pl['player_key'] for pl in players) or 'none'}"
    )

    # 7. RENDER
    if args.skip_render:
        print("render   : skipped (--skip-render)")
    else:
        start = args.window_start if args.window_start is not None else default_window_start(args.results_dir)
        start = min(max(0.0, start), max(0.0, video_duration - args.window_seconds))
        print(f"render   : window [{start:.1f}s, {start + args.window_seconds:.1f}s]")
        rows = rows_by_frame_key(tracks_path, sample_fps, start, start + args.window_seconds)
        entity_of_tid = {
            int(tid): e["entity_id"] for e in entities for tid in e["member_tids"]
        }
        # Draw filter: player members always; otherwise only team-labeled entities
        # that actually MOVE (x-spread) — keeps coaches/subs idling on the turf
        # out of the demo clip. Reports never include them anyway (roster-tagged only).
        data = np.load(tracks_path)
        t_all, tid_all = data["t"], data["tid"]
        cx_all = (data["xyxy"][:, 0] + data["xyxy"][:, 2]) * 0.5
        drawable: set[int] = set()
        for e in entities:
            eid = e["entity_id"]
            if e["team"] not in (0, 1):
                continue
            mask = np.isin(tid_all, e["member_tids"])
            if mask.sum() < 2:
                continue
            spread = float(np.percentile(cx_all[mask], 95) - np.percentile(cx_all[mask], 5))
            if spread >= MIN_DRAW_X_SPREAD_PX:
                drawable.add(eid)
        for rec in identities:
            if rec["jersey_number"] is not None and not rec["conflict_flags"]:
                drawable.update(rec["member_entity_ids"])
        labels = build_labels(entities, identities, votes["entities"], drawable)
        clip_path = out_dir / "anchored_clip.mp4"
        frames = render_anchored_clip(
            args.video, clip_path, sample_fps, start, args.window_seconds,
            rows, entity_of_tid, labels,
        )
        print(f"wrote {clip_path} ({frames} frames)")

    print(f"wrote {out_dir / 'identities.json'}")
    print(f"wrote {out_dir / 'anchor_report.json'}")


if __name__ == "__main__":
    main()
