"""
Structured confidence-per-field player report (Phase A).

A per-player video report is NOT a flat row of stats — it is a structured object
where every data point carries its own confidence, gated by identity:

  identity  → the gate. A stat is only as trustworthy as the identity it hangs on.
  coverage  → how much of this player we actually, confidently observed.
  metrics   → each tagged with a `kind` (point / lower_bound / partial_observed /
              beta / suppressed) so a biased partial is never shown as a full total.
  events    → confidence-flagged partial outputs (confirmed sprints/shots/sequences).

This module is the contract builder. It is deliberately HONEST about Phase A
capability: only identity, coverage, and on-camera minutes are real today;
distance/speed/heatmap/touches are emitted as `suppressed` (value null) until the
homography stage lands — present in the structure, never fabricated.

`build_player_report` is a pure function over plain dicts so it can be unit-tested
without a database; `tracklet_to_bound` bridges a VideoTracklet ORM row into it.
"""

from collections import Counter

# Metrics that need pitch calibration (homography) before they can be trusted.
# Listed here so the contract is stable now and fields fill in as capability arrives.
_PENDING_HOMOGRAPHY_NOTE = "awaits pitch calibration (homography stage)"


def tracklet_number_votes(evidence) -> Counter:
    """Pull jersey-number vote tallies out of a tracklet's evidence JSON.

    Handles both shapes persist_artifacts writes:
      chain    {"votes": {"<frag_id>": {"10": 4, ...}}, ...}
      fragment {"number_votes": {"10": 1, ...}}
    """
    c: Counter = Counter()
    if not isinstance(evidence, dict):
        return c
    nv = evidence.get("number_votes")
    if isinstance(nv, dict):
        for k, v in nv.items():
            try:
                c[str(k)] += int(v)
            except (TypeError, ValueError):
                continue
    votes = evidence.get("votes")
    if isinstance(votes, dict):
        for per_frag in votes.values():
            if isinstance(per_frag, dict):
                for k, v in per_frag.items():
                    try:
                        c[str(k)] += int(v)
                    except (TypeError, ValueError):
                        continue
    return c


def _member_window_count(evidence) -> int:
    """How many underlying confident windows this tracklet represents. A chain
    bundles many short fragments into one row, so the meaningful window count is
    its member-fragment count — not 1. (Matches MJ's 'confident windows, combined'
    framing.) A leftover fragment is a single window."""
    if isinstance(evidence, dict):
        members = evidence.get("member_fragment_ids")
        if isinstance(members, list) and members:
            return len(members)
    return 1


def tracklet_to_bound(t) -> dict:
    """VideoTracklet ORM row -> the plain dict build_player_report consumes."""
    return {
        "confidence": t.confidence,
        "visible_s": float(t.visible_s or 0.0),
        "first_s": float(t.first_s) if t.first_s is not None else None,
        "last_s": float(t.last_s) if t.last_s is not None else None,
        "tag_source": t.tag_source,
        "contaminated": bool(t.contaminated),
        "number_votes": dict(tracklet_number_votes(t.evidence)),
        "windows": _member_window_count(t.evidence),
    }


def _metric(key, value, *, kind, confidence, unit=None, note=None):
    return {
        "key": key,
        "value": value,
        "unit": unit,
        "confidence": confidence,
        "kind": kind,
        "note": note,
        "suppressed": value is None,
    }


def build_player_report(
    *,
    jersey_number: int,
    team_cluster: int | None,
    our_team_cluster: int | None,
    bound: list[dict],
    match_duration_s: float | None,
) -> dict:
    """Build the structured confidence-per-field report for one player.

    `bound` is the list of (non-dismissed) tracklets tagged to this roster entry,
    each: {confidence, visible_s, first_s, last_s, tag_source, contaminated, number_votes}.
    Returns {identity, coverage, metrics, events} — the report contract.
    """
    if not bound:
        # No confident attribution — identity unverified, nothing to report.
        return {
            "identity": {
                "confidence": "unverified",
                "source": "unresolved",
                "votes": {},
                "splice_risk": False,
                "human_reviewed": False,
                "jersey_number": jersey_number,
                "team": _team_label(team_cluster, our_team_cluster),
            },
            "coverage": {
                "on_camera_min": 0.0,
                "confident_windows": 0,
                "pct_of_match": None,
                "span_s": None,
                "near_side_pct": None,
                "sampling": "no confident windows",
            },
            "metrics": _metrics(0.0),
            "events": [],
        }

    any_human = any(b.get("tag_source") == "human" for b in bound)
    any_high = any(b.get("confidence") == "high" for b in bound)
    any_contaminated = any(b.get("contaminated") for b in bound)

    if any_human:
        identity_conf = "human_confirmed"
    elif any_high and not any_contaminated:
        identity_conf = "high"
    else:
        identity_conf = "low"

    votes: Counter = Counter()
    for b in bound:
        for k, v in (b.get("number_votes") or {}).items():
            try:  # same defensive coercion as tracklet_number_votes
                votes[str(k)] += int(v)
            except (TypeError, ValueError):
                continue

    attributed_s = sum(float(b.get("visible_s") or 0.0) for b in bound)
    firsts = [b["first_s"] for b in bound if b.get("first_s") is not None]
    lasts = [b["last_s"] for b in bound if b.get("last_s") is not None]
    on_camera_min = round(attributed_s / 60.0, 1)
    pct_of_match = round(attributed_s / match_duration_s, 3) if match_duration_s and match_duration_s > 0 else None

    coverage = {
        "on_camera_min": on_camera_min,
        # underlying confident windows (chains expand to their member-fragment count)
        "confident_windows": sum(int(b.get("windows", 1)) for b in bound),
        "pct_of_match": pct_of_match,
        "span_s": [round(min(firsts), 1), round(max(lasts), 1)] if firsts and lasts else None,
        # near/far split needs per-frame positions (not in the DB yet) — forward-compatible,
        # never guessed. The sampling note keeps the bias caveat visible meanwhile.
        "near_side_pct": None,
        "sampling": "confident windows only; near/far split not yet measured",
    }

    return {
        "identity": {
            "confidence": identity_conf,
            "source": "human" if any_human else "auto",
            "votes": {k: votes[k] for k in sorted(votes, key=lambda x: -votes[x])},
            "splice_risk": any_contaminated,
            "human_reviewed": any_human,
            "jersey_number": jersey_number,
            "team": _team_label(team_cluster, our_team_cluster),
        },
        "coverage": coverage,
        "metrics": _metrics(on_camera_min),
        "events": [],  # event detection not in Phase A; structure ready for it
    }


def _team_label(team_cluster: int | None, our_team_cluster: int | None) -> str | None:
    if our_team_cluster is None or team_cluster not in (0, 1):
        return None
    return "ours" if team_cluster == our_team_cluster else "opposition"


def _metrics(on_camera_min: float) -> list[dict]:
    """The metric list. Today only minutes-on-camera is real; the rest are
    structurally present but suppressed until pitch calibration — never faked."""
    return [
        _metric("minutes_on_camera", on_camera_min, kind="point", confidence="high", unit="min"),
        _metric("distance_m", None, kind="suppressed", confidence=None, unit="m", note=_PENDING_HOMOGRAPHY_NOTE),
        _metric(
            "fastest_sustained_kmh",
            None,
            kind="suppressed",
            confidence=None,
            unit="km/h",
            note=_PENDING_HOMOGRAPHY_NOTE,
        ),
        _metric("sprint_count", None, kind="suppressed", confidence=None, note=_PENDING_HOMOGRAPHY_NOTE),
        _metric("touches", None, kind="beta", confidence=None, note="experimental; needs ball association"),
        _metric("heatmap", None, kind="suppressed", confidence=None, note=_PENDING_HOMOGRAPHY_NOTE),
    ]
