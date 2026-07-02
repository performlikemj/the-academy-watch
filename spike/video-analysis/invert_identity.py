#!/usr/bin/env python3
"""Inverted identity pipeline: conservative merge -> fragment anchors -> number-driven chains.

The original order (merge_tracklets long-gap appearance merges, THEN jersey anchoring)
bakes in same-team splices: SigLIP is non-discriminative within a team (LOO 8.7%), so
long-gap merges routinely stitch teammates together and one jersey read then mislabels
the whole splice ("#10 on a #4 shirt"). This pass inverts the order:

  1. FRAGMENT  conservative merge only — short gaps (<2s), spatially gated. These are
               the merges the tracker geometry actually supports.
  2. REATTACH  re-attribute the cached VLM reads (identity/reads.json) onto the new
               fragments via (frame, bbox) -> tid -> fragment. Zero new VLM calls.
  3. VOTE      per-fragment jersey vote, same rules as anchor_identity (>= 2 agreeing
               reads to anchor, contamination refusal, digit-doubling tolerance).
               Single-read fragments become WEAK evidence, never anchors on their own.
  4. CHAIN     long-gap merging driven BY NUMBERS: fragments sharing (team, number)
               with pairwise-disjoint spans form one player chain. Appearance is
               demoted to a weak-attach sanity guard. A chain needs >= 1 strong
               fragment or >= 2 independent weak fragments.
  5. RENDER    comparison window + densest-anchor window. not_a_player fragments are
               not drawn at all (sideline spectators), referees stay grey.

Consumes a results dir produced by merge_tracklets.py + anchor_identity.py and the
source video. Outputs land in --out-dir (default <results-dir>/inverted):
  fragments.json     conservative entities (same schema as entities.json)
  votes.json         per-fragment vote rows (anchor_identity schema + weak tier)
  chains.json        number-driven player chains with evidence lists
  invert_report.json funnel, purity old-vs-new, splice suspects, unattached reads
  clip_cmp.mp4       render at --window-start (compare against identity/anchored_clip.mp4)
  clip_best.mp4      render at the auto-picked densest-anchor window

Usage:
  .venv-merge/bin/python invert_identity.py --results-dir results/v8/combined \
      --video "footage/youtube/<match>.mp4" --window-start 1400
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
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
    from merge_tracklets import (
        SPATIAL_GATE_MAX_GAP_S,
        TEAM_COLORS_RGB,
        build_tracklets,
        candidate_pairs,
        filter_min_duration,
        load_config,
        merge_entities,
        rows_by_frame_key,
    )
    from anchor_identity import (
        GREY_ROLES,
        MIN_DRAW_X_SPREAD_PX,
        _modal_role,
        render_anchored_clip,
        vote_entities,
    )
except ImportError as e:
    _fail(f"sibling import failed: {e}", "run from the directory containing merge_tracklets.py")


BBOX_MATCH_TOL = 0.5  # L1 distance allowed when matching a cached crop bbox to a track row
WEAK_ATTACH_MIN_SIM = 0.45  # gross-mismatch appearance guard for single-read attaches
BEST_WINDOW_STEP_S = 5.0
BEST_WINDOW_MIN_BINS = 2  # chain must be present in >= 2 bins of a window to count

# draw colors by kit color name (VLM shirt_color reads), substring-matched
KIT_RGB = {
    "red": (235, 45, 45),
    "blue": (45, 110, 255),
    "white": (240, 240, 240),
    "black": (70, 70, 70),
    "yellow": (240, 200, 40),
    "green": (40, 180, 90),
    "orange": (255, 140, 0),
    "purple": (165, 70, 220),
    "maroon": (150, 35, 60),
    "pink": (255, 105, 180),
}


def team_draw_colors(chains: list[dict]) -> dict[int, tuple[int, int, int]]:
    """Box color per team from the modal kit color across that team's chains —
    the KMeans 0/1 cluster label is arbitrary, so without this the demo paints
    red shirts blue. Falls back to the legacy palette when colors are unknown
    or both teams resolve to the same one."""
    modal: dict[int, str | None] = {}
    for team in (0, 1):
        c = Counter(
            ch["modal_shirt_color"] for ch in chains
            if ch["team"] == team and ch["modal_shirt_color"]
        )
        modal[team] = c.most_common(1)[0][0] if c else None

    def to_rgb(name: str | None) -> tuple[int, int, int] | None:
        if not name:
            return None
        return next((rgb for key, rgb in KIT_RGB.items() if key in name), None)

    rgb0, rgb1 = to_rgb(modal[0]), to_rgb(modal[1])
    if rgb0 is None or rgb1 is None or rgb0 == rgb1:
        return dict(TEAM_COLORS_RGB)
    print(f"colors   : team0 kit '{modal[0]}' -> {rgb0}, team1 kit '{modal[1]}' -> {rgb1}")
    return {0: rgb0, 1: rgb1, -1: TEAM_COLORS_RGB[-1]}


# --------------------------------------------------------------------------- 1. fragment


def conservative_fragments(
    results_dir: Path, sim_threshold: float, min_duration: float, frame_width: int, dt: float
) -> tuple[list[dict], dict[int, int], np.ndarray, dict[str, Any]]:
    """Short-gap spatially-gated merge only. Returns (fragments, frag_of_tid,
    frag_emb [F x D unit rows, zero where missing], stats)."""
    raw = build_tracklets(results_dir / "tracks.npz", results_dir / "tracklet_embeddings.npz")
    tl, dropped = filter_min_duration(raw, min_duration, dt)
    # cap the pair search just under the spatial-gate boundary so candidate_pairs'
    # long-gap (appearance-only) branch can never fire
    a, b, _scores = candidate_pairs(tl, sim_threshold, SPATIAL_GATE_MAX_GAP_S - 1e-3, frame_width)
    entities, merges = merge_entities(tl, a, b, dt)

    fragments: list[dict] = []
    frag_of_tid: dict[int, int] = {}
    emb_dim = tl.emb.shape[1] if len(tl) else 1
    frag_emb = np.zeros((len(entities) + 1, emb_dim), dtype=np.float32)  # 1-indexed by entity_id
    for en in entities:
        fragments.append(
            {
                "entity_id": en.entity_id,
                "member_tids": sorted(int(tl.tid[i]) for i in en.member_idx),
                "team": en.team,
                "first_s": round(en.first_s, 2),
                "last_s": round(en.last_s, 2),
                "visible_s": round(en.visible_s, 2),
            }
        )
        for i in en.member_idx:
            frag_of_tid[int(tl.tid[i])] = en.entity_id
        rows = [i for i in en.member_idx if tl.has_emb[i]]
        if rows:
            m = tl.emb[rows].mean(axis=0)
            n = float(np.linalg.norm(m))
            if n > 1e-8:
                frag_emb[en.entity_id] = m / n
    stats = {
        "raw_tracklets": len(raw),
        "after_min_duration": len(tl),
        "dropped_short": dropped,
        "pairs_considered": len(a),
        "unions": merges,
        "fragments": len(entities),
    }
    return fragments, frag_of_tid, frag_emb, stats


# --------------------------------------------------------------------------- 2. reattach


def reattribute_reads(
    identity_dir: Path,
    tracks_path: Path,
    frag_of_tid: dict[int, int],
    min_sharpness: float,
    min_height: float,
) -> tuple[list[dict], dict[str, int]]:
    """Map cached VLM reads onto the new fragment partition. Each read's crop was cut
    at a known (frame, bbox); that pins it to exactly one track row -> tid -> fragment.
    Returns (reads in anchor_identity schema with entity_id = fragment id, counters)."""
    cands = json.loads((identity_dir / "candidates.json").read_text())["candidates"]
    cand_by_id = {c["crop_id"]: c for c in cands}
    lap_by_id = {
        c["crop_id"]: c["laplacian_var"]
        for c in json.loads((identity_dir / "crops_index.json").read_text())
    }
    reads = json.loads((identity_dir / "reads.json").read_text())["reads"]

    data = np.load(tracks_path)
    frame_arr, tid_arr, xyxy_arr = data["frame"], data["tid"], data["xyxy"]
    order = np.argsort(frame_arr, kind="stable")
    f_sorted = frame_arr[order]

    out: list[dict] = []
    n = Counter()
    for r in reads:
        if not r.get("parsed"):
            n["unparsed"] += 1
            continue
        crop_id = r["file"].removesuffix(".jpg")
        cand = cand_by_id.get(crop_id)
        if cand is None:
            n["no_candidate"] += 1
            continue
        lap = lap_by_id.get(crop_id)
        if lap is None or lap < min_sharpness or cand["height"] < min_height:
            n["gated_out"] += 1
            continue
        lo = int(np.searchsorted(f_sorted, cand["frame"], side="left"))
        hi = int(np.searchsorted(f_sorted, cand["frame"], side="right"))
        if lo >= hi:
            n["no_frame_rows"] += 1
            continue
        rows = order[lo:hi]
        dists = np.abs(xyxy_arr[rows] - np.asarray(cand["xyxy"], dtype=np.float64)).sum(axis=1)
        best = int(np.argmin(dists))
        if float(dists[best]) > BBOX_MATCH_TOL:
            n["bbox_mismatch"] += 1
            continue
        frag = frag_of_tid.get(int(tid_arr[rows[best]]))
        if frag is None:
            n["tid_dropped"] += 1  # tracklet fell to the min-duration filter
            continue
        out.append({"file": r["file"], "entity_id": frag, "parsed": r["parsed"]})
        n["attached"] += 1
    return out, dict(n)


# --------------------------------------------------------------------------- 4. chain


def _span_overlap(a: dict, b: dict) -> float:
    return max(0.0, min(a["last_s"], b["last_s"]) - max(a["first_s"], b["first_s"]))


def _weak_rows(vote_rows: list[dict]) -> list[dict]:
    """Single-number-read fragments: usable as supporting evidence, never as anchors."""
    out = []
    for v in vote_rows:
        if v["anchored"] or v["contaminated"]:
            continue
        votes = v["number_votes"]
        if sum(votes.values()) == 1:
            v = dict(v)
            v["jersey_number"] = int(next(iter(votes)))
            out.append(v)
    return out


def build_chains(
    vote_rows: list[dict],
    fragments: list[dict],
    frag_emb: np.ndarray,
    max_overlap: float,
) -> tuple[list[dict], list[dict]]:
    """Number-driven long-gap merge. Per (team, number): cluster strong fragments by
    pairwise span compatibility, then attach weak (single-read) fragments that fit the
    span AND pass a gross appearance check. Validity: >= 1 strong, or >= 2 weak.
    Returns (chains, conflicts)."""
    frag_by_id = {f["entity_id"]: f for f in fragments}
    vote_by_id = {v["entity_id"]: v for v in vote_rows}

    groups: dict[tuple[int, int], dict[str, list[dict]]] = {}
    for v in vote_rows:
        if v["anchored"] and v["team"] in (0, 1):
            g = groups.setdefault((v["team"], v["jersey_number"]), {"strong": [], "weak": []})
            g["strong"].append(frag_by_id[v["entity_id"]])
    for v in _weak_rows(vote_rows):
        if v["team"] in (0, 1):
            g = groups.setdefault((v["team"], v["jersey_number"]), {"strong": [], "weak": []})
            g["weak"].append(frag_by_id[v["entity_id"]])

    chains: list[dict] = []
    conflicts: list[dict] = []
    for (team, num), g in sorted(groups.items()):
        strong = sorted(g["strong"], key=lambda f: -f["visible_s"])
        weak = sorted(g["weak"], key=lambda f: -f["visible_s"])
        seeds = strong if strong else weak
        cluster: list[dict] = [seeds[0]]
        rejected: list[dict] = []
        for f in seeds[1:]:
            if max(_span_overlap(f, c) for c in cluster) <= max_overlap:
                cluster.append(f)
            else:
                rejected.append(f)
        strong_ids = {f["entity_id"] for f in cluster} if strong else set()

        mean = None
        embs = [frag_emb[f["entity_id"]] for f in cluster if frag_emb[f["entity_id"]].any()]
        if embs:
            m = np.mean(embs, axis=0)
            nrm = float(np.linalg.norm(m))
            mean = m / nrm if nrm > 1e-8 else None

        attached_weak: list[dict] = []
        if strong:  # weak fragments only ever JOIN a strong-seeded chain
            for f in weak:
                if max(_span_overlap(f, c) for c in cluster) > max_overlap:
                    rejected.append(f)
                    continue
                e = frag_emb[f["entity_id"]]
                if mean is not None and e.any() and float(e @ mean) < WEAK_ATTACH_MIN_SIM:
                    rejected.append(f)
                    continue
                cluster.append(f)
                attached_weak.append(f)

        n_strong = len(strong_ids)
        n_weak = len(cluster) - n_strong
        if n_strong == 0 and n_weak < 2:
            continue  # one lone read never names a player; stays in the verify queue

        roles: Counter = Counter()
        shirts: Counter = Counter()
        for f in cluster:
            v = vote_by_id.get(f["entity_id"], {})
            roles.update(v.get("role_votes", {}))
            for s in v.get("shirt_votes", {}) or {}:
                shirts[s] += v["shirt_votes"][s]
        confidence = "low"
        if any(vote_by_id[i].get("confidence") == "high" for i in strong_ids):
            confidence = "high"
        chains.append(
            {
                "player_key": f"T{team}#{num}",
                "team": team,
                "jersey_number": num,
                "role": _modal_role(roles) or "outfield",
                "confidence": confidence,
                "member_fragment_ids": sorted(f["entity_id"] for f in cluster),
                "strong_fragment_ids": sorted(strong_ids),
                "weak_fragment_ids": sorted(f["entity_id"] for f in attached_weak),
                "first_s": round(min(f["first_s"] for f in cluster), 2),
                "last_s": round(max(f["last_s"] for f in cluster), 2),
                "visible_s_total": round(sum(f["visible_s"] for f in cluster), 2),
                "modal_shirt_color": shirts.most_common(1)[0][0] if shirts else None,
                "conflict_flags": [],
            }
        )
        for f in rejected:
            conflicts.append(
                {
                    "fragment_id": f["entity_id"],
                    "team": team,
                    "jersey_number": num,
                    "first_s": f["first_s"],
                    "last_s": f["last_s"],
                    "flag": f"span overlap > {max_overlap}s with T{team}#{num} "
                            "(duplicate number, misread, or team-label error)",
                }
            )
    return chains, conflicts


# --------------------------------------------------------------------------- 5. render


def pick_best_window(
    chains: list[dict],
    fragments: list[dict],
    tracks_path: Path,
    window_seconds: float,
    video_duration: float,
) -> float:
    """Start of the window where the most chains are concurrently visible (each must
    appear in >= BEST_WINDOW_MIN_BINS of the window's 5s bins)."""
    if not chains:
        return 0.0
    frag_by_id = {f["entity_id"]: f for f in fragments}
    data = np.load(tracks_path)
    t_all, tid_all = data["t"], data["tid"]
    n_bins = int(video_duration // BEST_WINDOW_STEP_S) + 1
    presence = np.zeros((len(chains), n_bins), dtype=bool)
    for ci, ch in enumerate(chains):
        tids = [tid for fid in ch["member_fragment_ids"] for tid in frag_by_id[fid]["member_tids"]]
        ts = t_all[np.isin(tid_all, tids)]
        presence[ci, np.minimum((ts // BEST_WINDOW_STEP_S).astype(np.int64), n_bins - 1)] = True
    w_bins = max(1, int(window_seconds // BEST_WINDOW_STEP_S))
    best_start, best_score = 0.0, -1
    for b0 in range(0, max(1, n_bins - w_bins)):
        score = int((presence[:, b0 : b0 + w_bins].sum(axis=1) >= BEST_WINDOW_MIN_BINS).sum())
        if score > best_score:
            best_score, best_start = score, b0 * BEST_WINDOW_STEP_S
    print(f"best win : {best_score} chains concurrently visible at {best_start:.0f}s")
    return min(best_start, max(0.0, video_duration - window_seconds))


def role_memory(
    identity_dir: Path, results_dir: Path, fragments: list[dict], vote_rows: list[dict]
) -> dict[int, str]:
    """Carry non-player roles from the OLD entity partition down to fragments.

    Spectators got their not_a_player votes on old entities; after re-fragmenting,
    most of their fragments hold zero reads and would draw again. An old entity
    whose modal role is non-player AND that never anchored a number passes its role
    to every fragment built entirely from its tracklets — unless the fragment has
    number reads of its own (protects against E118-style spectator<->player splices
    inside the old entity)."""
    old_votes = {
        v["entity_id"]: v
        for v in json.loads((identity_dir / "votes.json").read_text())["entities"]
    }
    grey_tids: set[int] = set()
    role_of_tid: dict[int, str] = {}
    for e in json.loads((results_dir / "entities.json").read_text()):
        v = old_votes.get(e["entity_id"])
        if not v or v["anchored"] or v["role"] not in GREY_ROLES:
            continue
        for tid in e["member_tids"]:
            grey_tids.add(int(tid))
            role_of_tid[int(tid)] = v["role"]
    has_own_number = {
        v["entity_id"] for v in vote_rows if sum(v["number_votes"].values()) > 0
    }
    out: dict[int, str] = {}
    for f in fragments:
        if f["entity_id"] in has_own_number:
            continue
        if all(int(t) in grey_tids for t in f["member_tids"]):
            out[f["entity_id"]] = role_of_tid[int(f["member_tids"][0])]
    return out


def build_labels(
    fragments: list[dict],
    chains: list[dict],
    vote_rows: list[dict],
    tracks_path: Path,
    inherited_roles: dict[int, str],
) -> dict[int, tuple[str, tuple[int, int, int]]]:
    """fragment_id -> (label, RGB). Chain members get '#N'/'#N?' in kit color.
    not_a_player fragments (voted or inherited) are NOT drawn (sideline
    spectators). Referees grey. Other fragments draw 'E<id>' only if
    team-labeled and actually moving."""
    role_of = dict(inherited_roles)
    role_of.update({v["entity_id"]: v["role"] for v in vote_rows if v["role"]})
    team_rgb = team_draw_colors(chains)
    grey = team_rgb[-1]

    data = np.load(tracks_path)
    tid_all = data["tid"]
    cx_all = (data["xyxy"][:, 0] + data["xyxy"][:, 2]) * 0.5

    labels: dict[int, tuple[str, tuple[int, int, int]]] = {}
    for f in fragments:
        fid = f["entity_id"]
        role = role_of.get(fid)
        if role == "not_a_player":
            continue
        if role == "referee":
            labels[fid] = (f"E{fid}", grey)
            continue
        if f["team"] not in (0, 1):
            continue
        mask = np.isin(tid_all, f["member_tids"])
        if mask.sum() < 2:
            continue
        spread = float(np.percentile(cx_all[mask], 95) - np.percentile(cx_all[mask], 5))
        if spread >= MIN_DRAW_X_SPREAD_PX:
            labels[fid] = (f"E{fid}", team_rgb[f["team"]])
    for ch in chains:
        text = f"#{ch['jersey_number']}" + ("" if ch["confidence"] == "high" else "?")
        color = team_rgb.get(ch["team"], grey)
        for fid in ch["member_fragment_ids"]:
            labels[fid] = (text, color)
    return labels


# --------------------------------------------------------------------------- purity


def read_purity(player_records: list[dict], votes_by_entity: dict[int, dict]) -> dict[str, Any]:
    """Across named players: fraction of member number-reads that agree with the
    player's number. The before/after headline for the inversion."""
    agree = total = 0
    worst: list[tuple[float, str]] = []
    for rec in player_records:
        num = rec.get("jersey_number")
        if num is None:
            continue
        a = t = 0
        for eid in rec.get("member_entity_ids") or rec.get("member_fragment_ids") or []:
            for k, c in (votes_by_entity.get(eid, {}).get("number_votes") or {}).items():
                t += c
                if int(k) == num:
                    a += c
        agree += a
        total += t
        if t:
            worst.append((a / t, rec["player_key"]))
    worst.sort()
    return {
        "reads_agreeing": agree,
        "reads_total": total,
        "purity": round(agree / total, 4) if total else None,
        "worst_players": [f"{k}={p:.2f}" for p, k in worst[:5]],
    }


# --------------------------------------------------------------------------- main


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results-dir", required=True, type=Path, help="dir with tracks.npz, tracklet_embeddings.npz, results.json")
    p.add_argument("--identity-dir", type=Path, default=None, help="cached anchor_identity outputs (default <results-dir>/identity)")
    p.add_argument("--out-dir", type=Path, default=None, help="output dir (default <results-dir>/inverted)")
    p.add_argument("--video", required=True, type=Path)
    p.add_argument("--sim-threshold", type=float, default=0.60)
    p.add_argument("--min-duration", type=float, default=1.0)
    p.add_argument("--min-sharpness", type=float, default=40.0)
    p.add_argument("--min-height", type=float, default=110.0)
    p.add_argument("--max-overlap", type=float, default=2.0, help="max pairwise span overlap (s) inside a chain")
    p.add_argument("--window-start", type=float, default=1400.0, help="comparison render window start (s)")
    p.add_argument("--window-seconds", type=float, default=45.0)
    p.add_argument("--skip-render", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    identity_dir = args.identity_dir or (args.results_dir / "identity")
    out_dir = args.out_dir or (args.results_dir / "inverted")
    tracks_path = args.results_dir / "tracks.npz"
    for need in (tracks_path, identity_dir / "reads.json", identity_dir / "candidates.json",
                 identity_dir / "crops_index.json"):
        if not need.exists():
            _fail(f"{need} not found", "run merge_tracklets.py + anchor_identity.py first")
    if not args.video.exists():
        _fail(f"video not found: {args.video}", "pass the same file the spike processed")
    out_dir.mkdir(parents=True, exist_ok=True)

    sample_fps, frame_width, video_duration = load_config(args.results_dir, args.video)
    dt = 1.0 / sample_fps

    # 1. FRAGMENT
    fragments, frag_of_tid, frag_emb, fstats = conservative_fragments(
        args.results_dir, args.sim_threshold, args.min_duration, frame_width, dt
    )
    (out_dir / "fragments.json").write_text(json.dumps(fragments, indent=2))
    print(
        f"fragment : {fstats['raw_tracklets']} raw -> {fstats['after_min_duration']} kept -> "
        f"{fstats['fragments']} fragments ({fstats['unions']} short-gap unions)"
    )

    # 2. REATTACH
    reads, rstats = reattribute_reads(
        identity_dir, tracks_path, frag_of_tid, args.min_sharpness, args.min_height
    )
    print(f"reattach : {rstats}")

    # 3. VOTE (reuse anchor_identity's exact rules; also tally shirt colors for chains)
    votes = vote_entities(reads, {r["file"] for r in reads}, fragments)
    shirt_by_frag: dict[int, Counter] = {}
    for r in reads:
        c = r["parsed"].get("shirt_color")
        if isinstance(c, str) and c.strip():
            shirt_by_frag.setdefault(r["entity_id"], Counter())[c.strip().lower()] += 1
    for v in votes["entities"]:
        v["shirt_votes"] = dict(shirt_by_frag.get(v["entity_id"], {}))
    (out_dir / "votes.json").write_text(json.dumps(votes, indent=2))
    n_anchored = sum(1 for v in votes["entities"] if v["anchored"])
    n_weak = len(_weak_rows(votes["entities"]))
    n_contam = sum(1 for v in votes["entities"] if v["contaminated"])
    print(
        f"vote     : {len(votes['entities'])} fragments with reads -> "
        f"{n_anchored} strong, {n_weak} weak, {n_contam} contaminated"
    )

    # 4. CHAIN
    chains, conflicts = build_chains(votes["entities"], fragments, frag_emb, args.max_overlap)
    (out_dir / "chains.json").write_text(json.dumps(chains, indent=2))
    print(
        f"chain    : {len(chains)} players ({sum(1 for c in chains if c['confidence'] == 'high')} high-conf, "
        f"{len(conflicts)} conflict fragments): "
        f"{', '.join(c['player_key'] for c in chains) or 'none'}"
    )

    # purity: old pipeline vs inverted
    old_votes = {
        v["entity_id"]: v
        for v in json.loads((identity_dir / "votes.json").read_text())["entities"]
    }
    old_players = [
        r for r in json.loads((identity_dir / "identities.json").read_text())
        if r.get("jersey_number") is not None and not r.get("conflict_flags")
    ]
    purity_old = read_purity(old_players, old_votes)
    purity_new = read_purity(chains, {v["entity_id"]: v for v in votes["entities"]})
    old_minutes = round(sum(r["visible_s_total"] for r in old_players) / 60.0, 1)
    new_minutes = round(sum(c["visible_s_total"] for c in chains) / 60.0, 1)
    print(
        f"purity   : old {purity_old['purity']} ({purity_old['reads_agreeing']}/{purity_old['reads_total']} reads, "
        f"{len(old_players)} players, {old_minutes} min) -> "
        f"new {purity_new['purity']} ({purity_new['reads_agreeing']}/{purity_new['reads_total']} reads, "
        f"{len(chains)} players, {new_minutes} min)"
    )

    splice_suspects = [
        {"fragment_id": v["entity_id"], "number_votes": v["number_votes"]}
        for v in votes["entities"]
        if v["contaminated"]
    ]
    report: dict[str, Any] = {
        "params": {
            "sim_threshold": args.sim_threshold,
            "conservative_max_gap_s": SPATIAL_GATE_MAX_GAP_S,
            "min_duration_s": args.min_duration,
            "min_sharpness": args.min_sharpness,
            "min_height_px": args.min_height,
            "max_overlap_s": args.max_overlap,
            "weak_attach_min_sim": WEAK_ATTACH_MIN_SIM,
        },
        "fragment_stage": fstats,
        "reattach_stage": rstats,
        "vote_stage": {
            "fragments_with_reads": len(votes["entities"]),
            "strong": n_anchored,
            "weak": n_weak,
            "contaminated": n_contam,
        },
        "chains": {
            "players": len(chains),
            "high_confidence": sum(1 for c in chains if c["confidence"] == "high"),
            "conflict_fragments": len(conflicts),
            "attributed_minutes": new_minutes,
            "keys": [c["player_key"] for c in chains],
        },
        "purity_old_pipeline": purity_old | {"players": len(old_players), "attributed_minutes": old_minutes},
        "purity_inverted": purity_new | {"players": len(chains), "attributed_minutes": new_minutes},
        "conflicts": conflicts,
        "splice_suspects": splice_suspects,
    }
    (out_dir / "invert_report.json").write_text(json.dumps(report, indent=2))
    print(f"wrote {out_dir / 'invert_report.json'}")

    # 5. RENDER
    if args.skip_render:
        print("render   : skipped (--skip-render)")
        return
    inherited = role_memory(identity_dir, args.results_dir, fragments, votes["entities"])
    print(f"rolemem  : {len(inherited)} fragments inherit a non-player role from the old partition")
    labels = build_labels(fragments, chains, votes["entities"], tracks_path, inherited)
    entity_of_tid = dict(frag_of_tid)
    for name, start in (
        ("clip_cmp.mp4", args.window_start),
        ("clip_best.mp4", pick_best_window(chains, fragments, tracks_path, args.window_seconds, video_duration)),
    ):
        start = min(max(0.0, start), max(0.0, video_duration - args.window_seconds))
        rows = rows_by_frame_key(tracks_path, sample_fps, start, start + args.window_seconds)
        frames = render_anchored_clip(
            args.video, out_dir / name, sample_fps, start, args.window_seconds,
            rows, entity_of_tid, labels,
        )
        print(f"wrote {out_dir / name} [{start:.0f}s, {start + args.window_seconds:.0f}s] ({frames} frames)")


if __name__ == "__main__":
    main()
