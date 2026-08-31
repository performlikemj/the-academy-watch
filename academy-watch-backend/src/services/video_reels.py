"""Pure aggregation for Film Room per-player highlight reels.

The identity pipeline stores a chain's underlying entity ids in
``evidence.member_fragment_ids`` and their production-safe windows in
``evidence.member_spans``. Those ids are also the keys exposed by
``video_dev_artifacts.fragment_spans`` and encoded by leftover fragment rows as
``pipeline_key='E<entity_id>'``. Keeping that linkage here makes reel windows
match the split-tracklet workflow instead of treating a chain's broad span as
continuous visibility.
"""

import math
from collections import defaultdict

WINDOW_MERGE_GAP_S = 3.0
MIN_WINDOW_S = 1.0


def _value(item, name, default=None):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def aggregate_votes(evidence: dict) -> tuple[int | None, int]:
    """Return the strongest jersey number and its read count across fragments."""
    if not isinstance(evidence, dict) or not isinstance(evidence.get("votes"), dict):
        return None, 0

    totals = defaultdict(int)
    for fragment_votes in evidence["votes"].values():
        if not isinstance(fragment_votes, dict):
            continue
        for raw_number, raw_count in fragment_votes.items():
            try:
                number = int(raw_number)
            except (TypeError, ValueError):
                continue
            if number < 0 or isinstance(raw_count, bool):
                continue
            if isinstance(raw_count, int):
                count = raw_count
            elif isinstance(raw_count, float) and math.isfinite(raw_count) and raw_count.is_integer():
                count = int(raw_count)
            else:
                continue
            if count > 0:
                totals[number] += count

    if not totals:
        return None, 0
    winner = min(totals, key=lambda number: (-totals[number], number))
    return winner, totals[winner]


def _finite_span(first_s, last_s):
    try:
        first = float(first_s)
        last = float(last_s)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(first) or not math.isfinite(last) or first < 0 or last <= first:
        return None
    return first, last


def fragment_spans_from_tracklets(tracklets) -> dict[int, tuple[float, float, float]]:
    """Recover entity-id spans from legacy persisted ``E<id>`` fragment rows.

    This is a best-effort version of the same entity-id linkage used by the
    split endpoint. Chained fragments are normally absent as standalone rows;
    current chain rows instead carry ``member_spans`` in their evidence.
    """
    spans = {}
    for tracklet in tracklets:
        if _value(tracklet, "kind") != "fragment":
            continue
        key = _value(tracklet, "pipeline_key") or ""
        if key[:1] not in ("E", "e") or not key[1:].isdigit():
            continue
        span = _finite_span(_value(tracklet, "first_s"), _value(tracklet, "last_s"))
        if span is None:
            continue
        spans[int(key[1:])] = (*span, float(_value(tracklet, "visible_s") or 0.0))
    return spans


def tracklet_windows(tracklet, fragment_spans) -> list[dict]:
    """Resolve one tracklet to honest on-camera windows.

    Persisted member spans use the same entity ids as ``member_fragment_ids``.
    Older/dev rows then resolve missing members exactly like ``split_tracklet``:
    cast the evidence values to integers and look them up in the entity-id span
    map. If none resolve, the tracklet's own span is the only safe fallback.
    """
    tracklet_id = int(_value(tracklet, "id"))
    evidence = _value(tracklet, "evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    members = evidence.get("member_fragment_ids") or []
    member_spans = evidence.get("member_spans")
    member_spans = member_spans if isinstance(member_spans, dict) else {}
    resolved = []
    for raw_id in members:
        try:
            member_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        member_key = str(member_id)
        has_persisted_span = member_key in member_spans or member_id in member_spans
        if has_persisted_span:
            span = member_spans.get(member_key, member_spans.get(member_id))
        else:
            span = fragment_spans.get(member_id)
        valid = _finite_span(span[0], span[1]) if isinstance(span, (list, tuple)) and len(span) >= 2 else None
        if valid is not None:
            resolved.append({"start_s": valid[0], "end_s": valid[1], "tracklet_id": tracklet_id})
    if resolved:
        return resolved

    own_span = _finite_span(_value(tracklet, "first_s"), _value(tracklet, "last_s"))
    if own_span is None:
        return []
    return [{"start_s": own_span[0], "end_s": own_span[1], "tracklet_id": tracklet_id}]


def merge_windows(windows, merge_gap_s=WINDOW_MERGE_GAP_S, min_window_s=MIN_WINDOW_S) -> list[dict]:
    """Order, merge gaps shorter than ``merge_gap_s``, then drop short windows."""
    ordered = []
    for window in windows:
        span = _finite_span(window.get("start_s"), window.get("end_s"))
        if span is None:
            continue
        ordered.append(
            {
                "start_s": span[0],
                "end_s": span[1],
                "tracklet_id": int(window["tracklet_id"]),
            }
        )
    ordered.sort(key=lambda window: (window["start_s"], window["end_s"], window["tracklet_id"]))

    merged = []
    for window in ordered:
        if (
            merged
            and window["tracklet_id"] == merged[-1]["tracklet_id"]
            and window["start_s"] - merged[-1]["end_s"] < merge_gap_s
        ):
            merged[-1]["end_s"] = max(merged[-1]["end_s"], window["end_s"])
        else:
            merged.append(window.copy())
    return [window for window in merged if window["end_s"] - window["start_s"] >= min_window_s]


def reel_confidence(tracklets) -> str:
    """Collapse chain confidence without overstating contaminated identities."""
    if tracklets and all(_value(tracklet, "confidence") == "high" for tracklet in tracklets):
        if not any(bool(_value(tracklet, "contaminated")) for tracklet in tracklets):
            return "high"
    if tracklets and all(_value(tracklet, "confidence") == "low" for tracklet in tracklets):
        return "low"
    return "mixed"


def build_reel_payload(match, roster_entries, tracklets, fragment_spans=None) -> dict:
    """Build the JSON-ready reel response from ORM-like rows or plain dicts."""
    tracklets = list(tracklets)
    roster_entries = list(roster_entries)
    spans = fragment_spans_from_tracklets(tracklets)
    spans.update(fragment_spans or {})

    active = [
        tracklet
        for tracklet in tracklets
        if not bool(_value(tracklet, "dismissed")) and _value(tracklet, "kind") != "tombstone"
    ]
    bound_by_roster = defaultdict(list)
    for tracklet in active:
        roster_id = _value(tracklet, "roster_entry_id")
        if roster_id is not None:
            bound_by_roster[int(roster_id)].append(tracklet)

    players = []
    roster_by_id = {int(_value(entry, "id")): entry for entry in roster_entries}
    for roster_id, entry in roster_by_id.items():
        bound = bound_by_roster.get(roster_id, [])
        if not bound:
            continue
        bound.sort(
            key=lambda tracklet: (
                float(_value(tracklet, "first_s") or 0.0),
                int(_value(tracklet, "id")),
            )
        )
        raw_windows = []
        for tracklet in bound:
            raw_windows.extend(tracklet_windows(tracklet, spans))
        windows = merge_windows(raw_windows)
        clusters = [int(cluster) for tracklet in bound if (cluster := _value(tracklet, "team_cluster")) in (0, 1)]
        chains = []
        for tracklet in bound:
            if _value(tracklet, "kind") != "chain":
                continue
            voted_number, vote_total = aggregate_votes(_value(tracklet, "evidence"))
            suggested_number = _value(tracklet, "suggested_number")
            chains.append(
                {
                    "tracklet_id": int(_value(tracklet, "id")),
                    "suggested_number": int(suggested_number) if suggested_number is not None else None,
                    "voted_number": voted_number,
                    "vote_total": vote_total,
                    "confidence": _value(tracklet, "confidence"),
                    "contaminated": bool(_value(tracklet, "contaminated")),
                }
            )
        jersey_number = int(_value(entry, "jersey_number"))
        players.append(
            {
                "roster_entry_id": roster_id,
                "player_name": _value(entry, "player_name"),
                "jersey_number": jersey_number,
                "position": _value(entry, "position"),
                "team_cluster": clusters[0] if clusters and len(set(clusters)) == 1 else None,
                "tracklet_ids": [int(_value(tracklet, "id")) for tracklet in bound],
                "chains": chains,
                "number_mismatch": any(
                    (chain["voted_number"] if chain["voted_number"] is not None else chain["suggested_number"])
                    not in (None, jersey_number)
                    for chain in chains
                ),
                "total_visible_s": round(sum(w["end_s"] - w["start_s"] for w in windows), 2),
                "confidence": reel_confidence(bound),
                "windows": [
                    {
                        "start_s": round(window["start_s"], 2),
                        "end_s": round(window["end_s"], 2),
                        "tracklet_id": window["tracklet_id"],
                    }
                    for window in windows
                ],
            }
        )
    players.sort(key=lambda player: (player["jersey_number"], player["roster_entry_id"]))

    unassigned_chains = [
        tracklet
        for tracklet in active
        if _value(tracklet, "kind") == "chain" and _value(tracklet, "roster_entry_id") is None
    ]

    clusters = []
    our_cluster = _value(match, "our_team_cluster")
    for cluster in (0, 1):
        cluster_tracklets = [
            tracklet
            for tracklet in active
            if _value(tracklet, "kind") == "chain" and _value(tracklet, "team_cluster") == cluster
        ]
        if not cluster_tracklets:
            continue
        player_ids = sorted(
            {
                int(roster_id)
                for tracklet in cluster_tracklets
                if (roster_id := _value(tracklet, "roster_entry_id")) is not None and int(roster_id) in roster_by_id
            }
        )
        clusters.append(
            {
                "cluster": cluster,
                "is_ours": None if our_cluster is None else cluster == our_cluster,
                "players": player_ids,
                "total_visible_s": round(
                    sum(float(_value(tracklet, "visible_s") or 0.0) for tracklet in cluster_tracklets), 2
                ),
            }
        )

    capture_meta = _value(match, "capture_meta")
    return {
        "players": players,
        "unassigned": {
            "count": len(unassigned_chains),
            "visible_s": round(sum(float(_value(tracklet, "visible_s") or 0.0) for tracklet in unassigned_chains), 2),
        },
        "team_overview": {
            "clusters": clusters,
            "qwen_analysis_present": isinstance(capture_meta, dict) and "qwen_analysis" in capture_meta,
        },
    }
