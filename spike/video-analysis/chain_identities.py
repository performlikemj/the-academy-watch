#!/usr/bin/env python3
"""Appearance-chaining pass: assign unanchored entities to jersey-anchored players.

Consumes merge_tracklets.py artifacts (tracks.npz, entities.json,
tracklet_embeddings.npz) plus the anchor_identity.py output
(identity/identities.json). The jersey-number pass anchors only entities with
readable numbers (~126 of 995); most of the rest are appearance fragments of the
same players. This pass chains them in by SigLIP appearance with calibrated
precision: every entity gets an n_crops-weighted mean of its member tracklet
embeddings; the sim/margin gates are chosen by leave-one-out holdout over the
anchored members themselves (lowest gates achieving --target-precision); chaining
is greedy by descending similarity against FROZEN player centroids (anchored
members only — no drift) and never violates physics: an entity whose visibility
intervals overlap the player's accumulated intervals by more than --max-overlap
is rejected, because one player cannot be visible in two entities at once.
If NO gate combo reaches the precision target, chaining is DISABLED and the
report carries the full calibration curve as evidence — assigning at uncalibrated
precision would poison the player records. --sim-threshold/--margin force gates.

Outputs in <results-dir>/identity/:
  chained_identities.json  players with anchored_members + chained_members,
                           visible_s_total recomputed from coalesced intervals
  chain_report.json        calibration curve, chosen gates, funnel, coverage
  chained_clip.mp4         render: '#10' team-colored when player-attributed
                           (anchored or chained), grey 'E<id>' when still loose

Usage:
  python chain_identities.py --results-dir results/v8/combined --video footage/match.mp4
"""

from __future__ import annotations

import argparse
import json
import re
import sys
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
    from merge_tracklets import TEAM_COLORS_RGB, load_config, rows_by_frame_key
except ImportError as e:
    _fail(f"merge_tracklets import failed: {e}", "run from the directory containing merge_tracklets.py")

try:
    from anchor_identity import GREY_ROLES, default_window_start, render_anchored_clip
except ImportError as e:
    _fail(f"anchor_identity import failed: {e}", "run from the directory containing anchor_identity.py")


PLAYER_KEY_RE = re.compile(r"^T(\d+)#(\d+)$")
SIM_GRID = [round(0.30 + 0.02 * i, 2) for i in range(31)]  # 0.30 .. 0.90
MARGIN_GRID = (0.0, 0.03, 0.05, 0.08)
Interval = tuple[float, float]


# --------------------------------------------------------------------------- intervals


def coalesce(ivs: list[Interval]) -> list[Interval]:
    """Sort and merge touching/overlapping intervals (same as IntervalDSU._coalesce
    in merge_tracklets — per-tracklet [first_t, last_t] convention)."""
    ivs = sorted(ivs)
    out = [list(ivs[0])]
    for s, e in ivs[1:]:
        if s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def cross_overlap(a: list[Interval], b: list[Interval]) -> float:
    """Total overlap between two sorted coalesced interval sets (two-pointer,
    same as IntervalDSU._cross_overlap in merge_tracklets)."""
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


def visible_seconds(ivs: list[Interval], dt: float) -> float:
    """Same convention as merge_tracklets entity visibility: span sum + dt per interval."""
    return sum(e - s for s, e in ivs) + len(ivs) * dt


# --------------------------------------------------------------------------- loading


def split_identities(records: list[dict]) -> tuple[list[dict], set[int], set[int]]:
    """Partition identities.json into (player records, anchored entity ids,
    conflict-flagged entity ids). Player records carry 'T<team>#<num>' keys and no
    conflict flags; conflicted entities are excluded from chaining entirely
    (their jersey read disagrees with physics — appearance must not re-add them)."""
    players: list[dict] = []
    anchored: set[int] = set()
    conflicted: set[int] = set()
    for rec in records:
        if rec["conflict_flags"]:
            conflicted.update(rec["member_entity_ids"])
        elif PLAYER_KEY_RE.match(rec["player_key"]):
            players.append(rec)
            anchored.update(rec["member_entity_ids"])
    return players, anchored, conflicted


def build_entity_embeddings(emb_path: Path, entities: list[dict]) -> dict[int, np.ndarray]:
    """entity_id -> unit-norm n_crops-weighted mean of member tracklet embeddings.
    Tracklets without an embedding row (or with non-finite rows — same treatment
    as merge_tracklets.build_tracklets) are skipped; entities with no embedded
    member are absent from the result (unchainable)."""
    ed = np.load(emb_path)
    ids, emat, n_crops = ed["ids"], ed["emb"], ed["n_crops"]
    finite = np.isfinite(emat).all(axis=1)
    idx_of = {int(t): i for i, t in enumerate(ids)}
    out: dict[int, np.ndarray] = {}
    for e in entities:
        rows = [i for m in e["member_tids"] if (i := idx_of.get(int(m))) is not None and finite[i]]
        if not rows:
            continue
        w = np.maximum(n_crops[rows].astype(np.float64), 1.0)  # guard 0-crop weights
        v = (emat[rows].astype(np.float64) * w[:, None]).sum(axis=0)
        n = float(np.linalg.norm(v))
        if n > 1e-9:
            out[e["entity_id"]] = v / n
    return out


def build_entity_intervals(tracks_path: Path, entities: list[dict]) -> dict[int, list[Interval]]:
    """entity_id -> coalesced [first_t, last_t] spans of its member tracklets."""
    data = np.load(tracks_path)
    t, tid = data["t"], data["tid"]
    order = np.lexsort((t, tid))  # by tid, then time within tid
    tid_s, t_s = tid[order], t[order]
    starts = np.flatnonzero(np.r_[True, tid_s[1:] != tid_s[:-1]])
    ends = np.r_[starts[1:], len(tid_s)] - 1
    span_of = {int(tid_s[s]): (float(t_s[s]), float(t_s[e])) for s, e in zip(starts, ends)}
    out: dict[int, list[Interval]] = {}
    for e in entities:
        spans = [span_of[int(m)] for m in e["member_tids"] if int(m) in span_of]
        if spans:
            out[e["entity_id"]] = coalesce(spans)
    return out


def read_sample_fps(results_dir: Path) -> float:
    rj = results_dir / "results.json"
    if rj.exists():
        fps = json.loads(rj.read_text()).get("config", {}).get("sample_fps")
        if fps:
            return float(fps)
    _fail("sample_fps not found in results.json", "pass a results dir produced by run_spike.py")


# --------------------------------------------------------------------------- calibration


def player_member_embeddings(
    players: list[dict], ent_emb: dict[int, np.ndarray]
) -> dict[str, list[tuple[int, np.ndarray]]]:
    return {
        pl["player_key"]: [
            (eid, ent_emb[eid]) for eid in pl["member_entity_ids"] if eid in ent_emb
        ]
        for pl in players
    }


def player_centroids(members_of: dict[str, list[tuple[int, np.ndarray]]]) -> dict[str, np.ndarray]:
    """Unweighted mean of unit member-entity embeddings, re-normalized — each
    anchored entity gets one vote regardless of size, keeping holdout symmetric."""
    cents: dict[str, np.ndarray] = {}
    for pk, mem in members_of.items():
        if not mem:
            continue
        s = np.sum([m[1] for m in mem], axis=0)
        n = float(np.linalg.norm(s))
        if n > 1e-9:
            cents[pk] = s / n
    return cents


def calibrate(
    players: list[dict], members_of: dict[str, list[tuple[int, np.ndarray]]]
) -> tuple[list[dict], list[dict], dict[str, Any]]:
    """Leave-one-out holdout over anchored members of multi-member players: hold
    out entity e, rebuild P's centroid without it, score e against all same-team
    player centroids. Returns (holdout rows, precision/recall curve over
    SIM_GRID x MARGIN_GRID, stats)."""
    cents = player_centroids(members_of)
    sums = {pk: np.sum([m[1] for m in mem], axis=0) for pk, mem in members_of.items() if mem}
    team_of = {pl["player_key"]: pl["team"] for pl in players}

    holdout: list[dict] = []
    n_multi = 0
    skipped_degenerate = 0
    for pl in players:
        pk = pl["player_key"]
        mem = members_of.get(pk, [])
        if len(mem) < 2:  # LOO centroid needs >= 2 EMBEDDED members
            continue
        n_multi += 1
        rivals = [(qk, cents[qk]) for qk in cents if qk != pk and team_of[qk] == team_of[pk]]
        for eid, emb in mem:
            loo = sums[pk] - emb
            n = float(np.linalg.norm(loo))
            if n < 1e-9:
                skipped_degenerate += 1
                continue
            scored = [(float(emb @ (loo / n)), pk)] + [(float(emb @ c), qk) for qk, c in rivals]
            scored.sort(reverse=True)
            sim_top, top_pk = scored[0]
            second = scored[1][0] if len(scored) > 1 else -1.0
            holdout.append(
                {
                    "entity_id": eid,
                    "true_player": pk,
                    "top_player": top_pk,
                    "sim": round(sim_top, 4),
                    "margin": round(sim_top - second, 4),
                    "correct": top_pk == pk,
                }
            )

    sims = np.array([h["sim"] for h in holdout], dtype=np.float64)
    margins = np.array([h["margin"] for h in holdout], dtype=np.float64)
    correct = np.array([h["correct"] for h in holdout], dtype=bool)
    curve: list[dict] = []
    for m in MARGIN_GRID:
        for s in SIM_GRID:
            mask = (sims >= s) & (margins >= m)
            n_pass = int(mask.sum())
            n_corr = int((mask & correct).sum())
            curve.append(
                {
                    "sim": s,
                    "margin": m,
                    "n_pass": n_pass,
                    "n_correct": n_corr,
                    "precision": round(n_corr / n_pass, 4) if n_pass else None,
                    "recall": round(n_corr / len(holdout), 4) if holdout else 0.0,
                }
            )
    stats = {
        "players": len(players),
        "players_multi_member_embedded": n_multi,
        "holdout_entities": len(holdout),
        "holdout_top1_accuracy": round(float(correct.mean()), 4) if len(holdout) else None,
        "skipped_degenerate_loo": skipped_degenerate,
    }
    return holdout, curve, stats


def choose_gates(curve: list[dict], target: float) -> tuple[dict | None, dict | None]:
    """Lowest gates achieving the precision target: among qualifying combos pick
    max recall, then lower sim, then lower margin. Returns (chosen, best_available);
    chosen is None when the target is unreachable — the caller must then DISABLE
    chaining rather than assign at uncalibrated precision."""
    scored = [c for c in curve if c["n_pass"]]
    best = max(scored, key=lambda c: (c["precision"], c["recall"])) if scored else None
    ok = [c for c in scored if c["precision"] >= target]
    if not ok:
        return None, best
    return max(ok, key=lambda c: (c["recall"], -c["sim"], -c["margin"])), best


# --------------------------------------------------------------------------- chain


def chain_entities(
    candidates: list[dict],
    ent_emb: dict[int, np.ndarray],
    ent_ivs: dict[int, list[Interval]],
    players: list[dict],
    cents: dict[str, np.ndarray],
    player_ivs: dict[str, list[Interval]],
    sim_gate: float,
    margin_gate: float,
    max_overlap: float,
) -> tuple[dict[str, list[int]], list[dict], dict[str, int]]:
    """Greedy assignment by descending top similarity against frozen centroids.
    Gates in order: sim, margin over the second-best same-team player, temporal
    cross-overlap vs the player's CURRENT accumulated intervals (updated after
    each assignment, so earlier = stronger matches claim time first)."""
    team_players: dict[int, list[str]] = {}
    for pl in players:
        if pl["player_key"] in cents:
            team_players.setdefault(pl["team"], []).append(pl["player_key"])

    scored: list[tuple[float, float, str, dict]] = []
    for e in candidates:
        pks = team_players.get(e["team"], [])
        if not pks:
            continue
        sims = sorted(((float(ent_emb[e["entity_id"]] @ cents[pk]), pk) for pk in pks), reverse=True)
        sim_top, pk_top = sims[0]
        margin = sim_top - (sims[1][0] if len(sims) > 1 else -1.0)
        scored.append((sim_top, margin, pk_top, e))
    scored.sort(key=lambda r: (-r[0], r[3]["entity_id"]))  # deterministic on sim ties

    assigned_of: dict[str, list[int]] = {}
    assignments: list[dict] = []
    rejected = {"sim": 0, "margin": 0, "overlap": 0}
    for sim_top, margin, pk, e in scored:
        eid = e["entity_id"]
        if sim_top < sim_gate:
            rejected["sim"] += 1
            continue
        if margin < margin_gate:
            rejected["margin"] += 1
            continue
        overlap = cross_overlap(ent_ivs[eid], player_ivs[pk])
        if overlap > max_overlap:
            rejected["overlap"] += 1
            continue
        assigned_of.setdefault(pk, []).append(eid)
        player_ivs[pk] = coalesce(player_ivs[pk] + ent_ivs[eid])
        assignments.append(
            {
                "entity_id": eid,
                "player_key": pk,
                "sim": round(sim_top, 4),
                "margin": round(margin, 4),
                "overlap_s": round(overlap, 3),
                "visible_s": e["visible_s"],
            }
        )
    return assigned_of, assignments, rejected


def build_chained_players(
    players: list[dict],
    assigned_of: dict[str, list[int]],
    ent_ivs: dict[int, list[Interval]],
    dt: float,
) -> list[dict]:
    out: list[dict] = []
    for pl in players:
        pk = pl["player_key"]
        anchored = sorted(pl["member_entity_ids"])
        chained = sorted(assigned_of.get(pk, []))
        ivs = coalesce([iv for eid in anchored + chained for iv in ent_ivs.get(eid, [])])
        if not ivs:
            print(f"WARNING: player {pk} has no intervals — skipping record")
            continue
        out.append(
            {
                "player_key": pk,
                "team": pl["team"],
                "jersey_number": pl["jersey_number"],
                "role": pl["role"],
                "anchored_members": anchored,
                "chained_members": chained,
                "member_entity_ids": sorted(anchored + chained),
                "first_s": round(ivs[0][0], 2),
                "last_s": round(max(e for _, e in ivs), 2),
                "visible_s_total": round(visible_seconds(ivs, dt), 2),
                "conflict_flags": [],
            }
        )
    return out


# --------------------------------------------------------------------------- render


def build_chain_labels(
    entities: list[dict], chained_players: list[dict]
) -> dict[int, tuple[str, tuple[int, int, int]]]:
    """entity_id -> (label, RGB). Player-attributed entities — anchored or chained —
    get '#10' in team color; everything still-unattributed renders grey 'E<id>'
    so chained coverage is visually obvious against the anchored clip."""
    grey = TEAM_COLORS_RGB[-1]
    labels = {e["entity_id"]: (f"E{e['entity_id']}", grey) for e in entities}
    for rec in chained_players:
        color = grey if rec["role"] in GREY_ROLES else TEAM_COLORS_RGB.get(rec["team"], grey)
        for eid in rec["member_entity_ids"]:
            labels[eid] = (f"#{rec['jersey_number']}", color)
    return labels


# --------------------------------------------------------------------------- main


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results-dir", required=True, type=Path, help="dir with tracks.npz, entities.json, identity/identities.json")
    p.add_argument("--video", type=Path, default=None, help="source video (required unless --skip-render)")
    p.add_argument("--target-precision", type=float, default=0.95, help="holdout precision the chosen gates must achieve")
    p.add_argument("--max-overlap", type=float, default=0.3, help="max temporal overlap (s) between an entity and its player")
    p.add_argument("--sim-threshold", type=float, default=None, help="bypass calibration: explicit cosine sim gate (requires --margin)")
    p.add_argument("--margin", type=float, default=None, help="bypass calibration: explicit margin gate (requires --sim-threshold)")
    p.add_argument("--window-start", type=float, default=None, help="render window start (s); default merge_report.json render_window")
    p.add_argument("--window-seconds", type=float, default=45.0)
    p.add_argument("--skip-render", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if (args.sim_threshold is None) != (args.margin is None):
        _fail("--sim-threshold and --margin must be given together", "pass both or neither")
    results_dir = args.results_dir
    out_dir = results_dir / "identity"
    tracks_path = results_dir / "tracks.npz"
    entities_path = results_dir / "entities.json"
    emb_path = results_dir / "tracklet_embeddings.npz"
    identities_path = out_dir / "identities.json"
    for path, producer in (
        (tracks_path, "merge_tracklets.py"),
        (entities_path, "merge_tracklets.py"),
        (emb_path, "run_spike.py"),
        (identities_path, "anchor_identity.py"),
    ):
        if not path.exists():
            _fail(f"{path} not found", f"run {producer} first")
    if not args.skip_render:
        if args.video is None or not args.video.exists():
            _fail(f"video not found: {args.video}", "pass the same file merge_tracklets.py processed, or --skip-render")
        sample_fps, _frame_width, video_duration = load_config(results_dir, args.video)
    else:
        sample_fps, video_duration = read_sample_fps(results_dir), 0.0
    dt = 1.0 / sample_fps

    # LOAD
    entities: list[dict] = json.loads(entities_path.read_text())
    players, anchored_ids, conflict_ids = split_identities(json.loads(identities_path.read_text()))
    print(
        f"load     : {len(entities)} entities, {len(players)} players "
        f"({len(anchored_ids)} anchored members, {len(conflict_ids)} conflict-flagged)"
    )

    # EMBED + INTERVALS
    ent_emb = build_entity_embeddings(emb_path, entities)
    ent_ivs = build_entity_intervals(tracks_path, entities)
    print(f"embed    : {len(ent_emb)}/{len(entities)} entities embedded "
          f"({len(entities) - len(ent_emb)} have no embedded tracklet — unchainable)")

    # CALIBRATE (always computed — cheap, and the curve is the evidence)
    members_of = player_member_embeddings(players, ent_emb)
    holdout, curve, cal_stats = calibrate(players, members_of)
    print(
        f"calibrate: {cal_stats['holdout_entities']} holdout entities from "
        f"{cal_stats['players_multi_member_embedded']} multi-member players; "
        f"top-1 accuracy {cal_stats['holdout_top1_accuracy']}"
    )
    for m in MARGIN_GRID:
        ok = [c for c in curve if c["margin"] == m and c["n_pass"] and c["precision"] >= args.target_precision]
        if ok:
            low = min(ok, key=lambda c: c["sim"])
            print(f"           margin {m:.2f}: sim>={low['sim']:.2f} -> P={low['precision']:.3f} R={low['recall']:.3f}")
        else:
            print(f"           margin {m:.2f}: precision {args.target_precision} unreachable")
    best_available: dict | None = None
    if args.sim_threshold is not None:
        sim_gate, margin_gate, source = args.sim_threshold, args.margin, "override"
        chain_enabled = True
        print(f"           gates OVERRIDDEN: sim>={sim_gate} margin>={margin_gate} (calibration bypassed)")
    else:
        chosen, best_available = choose_gates(curve, args.target_precision)
        if chosen is not None:
            sim_gate, margin_gate, source = chosen["sim"], chosen["margin"], "calibrated"
            chain_enabled = True
            print(
                f"           chosen sim>={sim_gate:.2f} margin>={margin_gate:.2f} -> "
                f"P={chosen['precision']:.3f} R={chosen['recall']:.3f} (target {args.target_precision})"
            )
        else:  # assigning at uncalibrated precision would poison the player records
            sim_gate, margin_gate, source = None, None, "calibration-failed"
            chain_enabled = False
            bp = f"{best_available['precision']:.3f} at sim>={best_available['sim']:.2f}/margin>={best_available['margin']:.2f}" if best_available else "n/a"
            print(
                f"WARNING: chaining DISABLED — best achievable holdout precision {bp} "
                f"< target {args.target_precision}; pass --sim-threshold/--margin to force"
            )

    # CHAIN
    attributed = anchored_ids | conflict_ids
    unanchored = [e for e in entities if e["entity_id"] not in attributed]
    team_eligible = [e for e in unanchored if e["team"] in (0, 1)]
    candidates = [e for e in team_eligible if e["entity_id"] in ent_emb and e["entity_id"] in ent_ivs]
    cents = player_centroids(members_of)  # frozen: anchored members only
    player_ivs = {
        pl["player_key"]: coalesce(
            [iv for eid in pl["member_entity_ids"] for iv in ent_ivs.get(eid, [])]
        )
        for pl in players
    }
    before_minutes = sum(visible_seconds(ivs, dt) for ivs in player_ivs.values()) / 60.0
    if chain_enabled:
        assigned_of, assignments, rejected = chain_entities(
            candidates, ent_emb, ent_ivs, players, cents, player_ivs,
            sim_gate, margin_gate, args.max_overlap,
        )
        print(
            f"chain    : {len(unanchored)} unanchored -> {len(team_eligible)} team-eligible -> "
            f"{len(candidates)} embedded; {len(assignments)} assigned, "
            f"{rejected['sim']} rejected by sim, {rejected['margin']} by margin, {rejected['overlap']} by overlap"
        )
    else:
        assigned_of, assignments, rejected = {}, [], {"sim": 0, "margin": 0, "overlap": 0}
        print(
            f"chain    : {len(unanchored)} unanchored -> {len(team_eligible)} team-eligible -> "
            f"{len(candidates)} embedded; 0 assigned (chaining disabled — calibration failed)"
        )

    # OUTPUTS
    chained_players = build_chained_players(players, assigned_of, ent_ivs, dt)
    (out_dir / "chained_identities.json").write_text(json.dumps(chained_players, indent=2))
    after_minutes = sum(visible_seconds(ivs, dt) for ivs in player_ivs.values()) / 60.0
    # Denominator includes ALL entities (even conflicted/bystanders) for comparability
    # with the pre-chaining baseline; conflicted entities never enter the numerator,
    # so the fraction slightly UNDERSTATES player-attributable coverage.
    total_vis = sum(e["visible_s"] for e in entities)
    vis_of = {e["entity_id"]: e["visible_s"] for e in entities}
    before_vis = sum(vis_of[eid] for eid in anchored_ids)
    after_vis = before_vis + sum(a["visible_s"] for a in assignments)
    report: dict[str, Any] = {
        "params": {
            "target_precision": args.target_precision,
            "max_overlap_s": args.max_overlap,
            "sim_grid": [SIM_GRID[0], SIM_GRID[-1], 0.02],
            "margin_grid": list(MARGIN_GRID),
            "gates": {"sim_threshold": sim_gate, "margin_threshold": margin_gate,
                      "source": source, "chain_enabled": chain_enabled,
                      "best_available_combo": best_available},
        },
        "calibration": {**cal_stats, "holdout": holdout, "curve": curve},
        "funnel": {
            "entities": len(entities),
            "anchored_member_entities": len(anchored_ids),
            "conflict_entities_excluded": len(conflict_ids),
            "unanchored": len(unanchored),
            "team_eligible": len(team_eligible),
            "embedded_candidates": len(candidates),
            "assigned": len(assignments),
            "rejected_by_sim": rejected["sim"],
            "rejected_by_margin": rejected["margin"],
            "rejected_by_overlap": rejected["overlap"],
            "not_attempted_calibration_failed": 0 if chain_enabled else len(candidates),
        },
        "coverage": {
            "player_minutes_before": round(before_minutes, 1),
            "player_minutes_after": round(after_minutes, 1),
            "entity_visible_s_total": round(total_vis, 1),
            "attributed_visible_fraction_before": round(before_vis / total_vis, 4) if total_vis else 0.0,
            "attributed_visible_fraction_after": round(after_vis / total_vis, 4) if total_vis else 0.0,
        },
        "assignments": assignments,
    }
    (out_dir / "chain_report.json").write_text(json.dumps(report, indent=2))
    cov = report["coverage"]
    print(
        f"coverage : attributed visible {100 * cov['attributed_visible_fraction_before']:.1f}% -> "
        f"{100 * cov['attributed_visible_fraction_after']:.1f}%; "
        f"player-minutes {cov['player_minutes_before']:.1f} -> {cov['player_minutes_after']:.1f}"
    )

    # RENDER
    if args.skip_render:
        print("render   : skipped (--skip-render)")
    else:
        start = args.window_start if args.window_start is not None else default_window_start(results_dir)
        start = min(max(0.0, start), max(0.0, video_duration - args.window_seconds))
        print(f"render   : window [{start:.1f}s, {start + args.window_seconds:.1f}s]")
        rows = rows_by_frame_key(tracks_path, sample_fps, start, start + args.window_seconds)
        entity_of_tid = {int(m): e["entity_id"] for e in entities for m in e["member_tids"]}
        labels = build_chain_labels(entities, chained_players)
        clip_path = out_dir / "chained_clip.mp4"
        frames = render_anchored_clip(
            args.video, clip_path, sample_fps, start, args.window_seconds,
            rows, entity_of_tid, labels,
        )
        print(f"wrote {clip_path} ({frames} frames)")

    print(f"wrote {out_dir / 'chained_identities.json'}")
    print(f"wrote {out_dir / 'chain_report.json'}")


if __name__ == "__main__":
    main()
