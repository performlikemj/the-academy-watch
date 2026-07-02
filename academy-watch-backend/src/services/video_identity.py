"""
Jersey-number identity logic + worker-artifact persistence (Phase A).

The algorithms here were validated on real VEO footage in the Phase 0 spike
(spike/video-analysis/invert_identity.py — read purity 0.847 -> 0.927):

- A jersey number is NEVER trusted from a single read (MIN_VOTES=2 within a
  fragment); a fragment with two multiply-attested numbers is a tracker-swap
  splice and is refused outright.
- OCR digit-doubling ("4" vs "44") supports the top number rather than
  rivalling it.
- Long-gap merging is driven BY NUMBERS: fragments sharing (team, number) with
  pairwise-disjoint time spans form one player chain. Appearance embeddings are
  non-discriminative within a team and are never the merge signal.
- Single-read (weak) fragments may only JOIN a strong-seeded chain; two
  independent agreeing weak fragments may seed one.

Worker contract: the GPU pipeline produces an artifacts payload
  {fragments: [...], votes: {entities: [...]}, chains: [...], thumbnails: {...}}
and `persist_artifacts()` turns it into VideoTracklet rows + flips the match
to needs_tagging. Human tags and auto-bindings share the same rows.
"""

import logging
from collections import Counter
from datetime import UTC, datetime

from src.models.league import db
from src.models.video import VideoMatch, VideoRosterEntry, VideoTracklet

logger = logging.getLogger(__name__)

MIN_VOTES = 2  # single-frame reads are never trusted
GREY_ROLES = {"referee", "not_a_player"}
MAX_FRAGMENT_ROWS = 200  # cap leftover-fragment rows persisted for review
MIN_FRAGMENT_VISIBLE_S = 30.0  # leftover fragments below this aren't worth human time
NUMBER_AGREEMENT_MIN = 0.7  # below this, a chain's members disagree on the number → flag mixed


# --------------------------------------------------------------------------- voting


def norm_number(v) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if 1 <= v <= 99 else None
    if isinstance(v, float) and v.is_integer():
        return norm_number(int(v))
    if isinstance(v, str) and v.strip().isdigit():
        return norm_number(int(v.strip()))
    return None


def modal_role(roles: Counter) -> str | None:
    if not roles:
        return None
    return max(roles.items(), key=lambda kv: (kv[1], kv[0]))[0]


def _is_doubling(a: int, b: int) -> bool:
    # OCR doubling (4 vs 44) supports the top number. Caveat: 1 vs 11 is
    # genuinely ambiguous and also matches — accepted, same as the spike.
    return str(a) * 2 == str(b) or str(b) * 2 == str(a)


def vote_fragment(parsed_reads: list[dict]) -> dict:
    """Vote one fragment's VLM/OCR reads into a jersey decision.

    Returns {number_votes, role_votes, jersey_number, role, anchored,
    confidence, contaminated, weak_number}.
    """
    nums = Counter(n for p in parsed_reads if (n := norm_number(p.get("jersey_number"))) is not None)
    roles = Counter(p["role"] for p in parsed_reads if isinstance(p.get("role"), str))
    number, anchored, confidence, contaminated = None, False, None, False
    if nums:
        mc = nums.most_common()
        top, top_n = mc[0]
        rivals = [(n, c) for n, c in mc[1:] if not _is_doubling(top, n)]
        second_n = rivals[0][1] if rivals else 0
        # Two multiply-attested numbers in ONE fragment = tracker-swap splice.
        contaminated = second_n >= 2
        anchored = top_n >= MIN_VOTES and top_n > second_n and not contaminated
        if anchored:
            number = top
            confidence = "high" if (second_n == 0 or top_n >= max(3, 2 * second_n)) else "low"
    weak_number = None
    if not anchored and not contaminated and sum(nums.values()) == 1:
        weak_number = next(iter(nums))
    return {
        "number_votes": {str(k): v for k, v in sorted(nums.items())},
        "role_votes": dict(sorted(roles.items())),
        "jersey_number": number,
        "role": modal_role(roles),
        "anchored": anchored,
        "confidence": confidence,
        "contaminated": contaminated,
        "weak_number": weak_number,
    }


# --------------------------------------------------------------------------- chains


def _span_overlap(a: dict, b: dict) -> float:
    return max(0.0, min(a["last_s"], b["last_s"]) - max(a["first_s"], b["first_s"]))


def build_chains(
    vote_by_fragment: dict[int, dict],
    fragments: list[dict],
    max_overlap: float = 2.0,
) -> tuple[list[dict], list[dict]]:
    """Number-driven long-gap merge over fragment dicts
    ({entity_id, team, first_s, last_s, visible_s}).

    Returns (chains, conflicts). Chain: {player_key, team, jersey_number, role,
    confidence, member_fragment_ids, strong_fragment_ids, first_s, last_s,
    visible_s_total}. Validity: >= 1 strong fragment, or >= 2 weak.
    """
    frag_by_id = {f["entity_id"]: f for f in fragments}
    groups: dict[tuple[int, int], dict[str, list[dict]]] = {}
    for fid, v in vote_by_fragment.items():
        f = frag_by_id.get(fid)
        if f is None or f.get("team") not in (0, 1):
            continue
        if v["anchored"]:
            g = groups.setdefault((f["team"], v["jersey_number"]), {"strong": [], "weak": []})
            g["strong"].append(f)
        elif v["weak_number"] is not None:
            g = groups.setdefault((f["team"], v["weak_number"]), {"strong": [], "weak": []})
            g["weak"].append(f)

    chains: list[dict] = []
    conflicts: list[dict] = []
    for (team, num), g in sorted(groups.items()):
        strong = sorted(g["strong"], key=lambda f: -f["visible_s"])
        weak = sorted(g["weak"], key=lambda f: -f["visible_s"])
        seeds = strong if strong else weak
        cluster = [seeds[0]]
        rejected: list[dict] = []
        for f in seeds[1:]:
            if max(_span_overlap(f, c) for c in cluster) <= max_overlap:
                cluster.append(f)
            else:
                rejected.append(f)
        strong_ids = {f["entity_id"] for f in cluster} if strong else set()
        if strong:  # weak fragments only ever JOIN a strong-seeded chain
            for f in weak:
                if max(_span_overlap(f, c) for c in cluster) <= max_overlap:
                    cluster.append(f)
                else:
                    rejected.append(f)

        n_strong = len(strong_ids)
        if n_strong == 0 and len(cluster) < 2:
            continue  # one lone read never names a player

        roles: Counter = Counter()
        for f in cluster:
            roles.update(vote_by_fragment.get(f["entity_id"], {}).get("role_votes", {}))
        confidence = "low"
        if any(vote_by_fragment[i].get("confidence") == "high" for i in strong_ids):
            confidence = "high"
        chains.append(
            {
                "player_key": f"T{team}#{num}",
                "team": team,
                "jersey_number": num,
                "role": modal_role(roles) or "outfield",
                "confidence": confidence,
                "member_fragment_ids": sorted(f["entity_id"] for f in cluster),
                "strong_fragment_ids": sorted(strong_ids),
                "first_s": round(min(f["first_s"] for f in cluster), 2),
                "last_s": round(max(f["last_s"] for f in cluster), 2),
                "visible_s_total": round(sum(f["visible_s"] for f in cluster), 2),
            }
        )
        for f in rejected:
            conflicts.append(
                {
                    "fragment_id": f["entity_id"],
                    "team": team,
                    "jersey_number": num,
                    "flag": "span overlap with chain (duplicate number, misread, or team error)",
                }
            )
    return chains, conflicts


# --------------------------------------------------------------------------- quality gate

# Shirt-colour bases the VLM reports; used to detect cross-team contamination.
_SHIRT_BASES = ("red", "blue", "yellow", "orange", "green", "white", "black", "purple", "pink")


def base_shirt(shirt_votes) -> str | None:
    """Dominant base shirt colour from a fragment's VLM shirt votes
    ('blue and yellow' / 'light blue' -> 'blue')."""
    if not isinstance(shirt_votes, dict) or not shirt_votes:
        return None
    agg: Counter = Counter()
    for label, n in shirt_votes.items():
        for b in _SHIRT_BASES:
            if b in str(label).lower():
                try:
                    agg[b] += int(n)
                except (TypeError, ValueError):
                    pass
                break
    if not agg:
        return None
    # deterministic: highest count, ties broken by canonical colour order (not dict order)
    return max(agg.items(), key=lambda kv: (kv[1], -_SHIRT_BASES.index(kv[0])))[0]


def _is_corroborated(vote: dict) -> bool:
    """Trustworthy iff identity is backed by more than a single read — a lone
    (<=1 number-read AND <=1 shirt-read) fragment is too easily a misread or
    tracker-swap to anchor a player (e.g. a blue-voted fragment whose tracker is
    actually on a red player → a box that switches players mid-tracklet)."""
    nv = vote.get("number_votes") or {}
    sv = vote.get("shirt_votes") or {}
    n_num = sum(int(x) for x in nv.values() if str(x).lstrip("-").isdigit())
    n_shirt = sum(int(x) for x in sv.values() if str(x).lstrip("-").isdigit())
    return not (n_num <= 1 and n_shirt <= 1)


def number_agreement(members: list[int], vote_by_fragment: dict[int, dict], num: int) -> float:
    """Fraction of a chain's number-reads that agree with its jersey number
    (doubling-tolerant: a '22' read supports a '2' chain). 1.0 = internally
    unanimous; a low value means the chain still bundles disagreeing identities."""
    total = agree = 0
    for fid in members:
        nv = (vote_by_fragment.get(fid) or {}).get("number_votes") or {}
        for k, n in nv.items():
            try:
                kk, c = int(k), int(n)
            except (TypeError, ValueError):
                continue
            total += c
            if kk == num or _is_doubling(num, kk):
                agree += c
    return round(agree / total, 3) if total else 1.0


def split_chain(member_ids, strong_ids, votes_by_member, frag_spans, at_s):
    """Partition a chain's members at `at_s` seconds into ['a' before, 'b' after]
    by each member fragment's midpoint, re-tallying number/agreement/span per side.
    The human's split = ground truth that the merge fused two players (a strong
    learning signal). votes_by_member: {fid: {number: count}}; frag_spans:
    {fid: (first_s, last_s, visible_s)}. Returns 0-2 segment dicts."""
    strong = set(strong_ids or [])
    sides: dict[str, list[int]] = {"a": [], "b": []}
    for fid in member_ids:
        sp = frag_spans.get(fid)
        if not sp:
            continue
        mid = (sp[0] + sp[1]) / 2.0
        sides["a" if mid <= at_s else "b"].append(fid)
    segs = []
    for key in ("a", "b"):
        ids = sides[key]
        spans = [frag_spans[i] for i in ids if i in frag_spans]
        if not spans:
            continue
        tally: Counter = Counter()
        vbf = {}
        for fid in ids:
            nv = votes_by_member.get(fid) or {}
            vbf[fid] = {"number_votes": nv}
            for k, n in nv.items():
                try:
                    tally[int(k)] += int(n)
                except (TypeError, ValueError):
                    continue
        num = tally.most_common(1)[0][0] if tally else None
        first = min(s[0] for s in spans)
        last = max(s[1] for s in spans)
        # clamp to the cut so the two halves don't overlap in displayed time
        if key == "a":
            last = min(last, at_s)
        else:
            first = max(first, at_s)
        segs.append(
            {
                "key": key,
                "member_fragment_ids": sorted(ids),
                "strong_fragment_ids": sorted(strong & set(ids)),
                "suggested_number": num,
                "number_agreement": number_agreement(ids, vbf, num) if num is not None else 1.0,
                "first_s": round(first, 2),
                "last_s": round(last, 2),
                "visible_s": round(sum(s[2] for s in spans), 2),
            }
        )
    return segs


def apply_quality_gate(chains: list[dict], vote_by_fragment: dict[int, dict], fragments: list[dict]) -> list[dict]:
    """Remove contaminating members the number-driven merge let in, and tag each
    chain with its internal number-agreement:
      1. shirt-consistency — drop members whose shirt colour disagrees with the
         chain's dominant colour (a red player mis-clustered + mis-read into a
         blue #2 chain — the cause of a box that switches players);
      2. weak corroboration — drop lone single-read members.
    Recomputes span/visible/strong from survivors; drops a chain emptied out.
    Degrades gracefully when shirt votes are absent (keeps the member)."""
    frag_by_id = {f["entity_id"]: f for f in fragments}
    out: list[dict] = []
    for ch in chains:
        members = ch.get("member_fragment_ids") or []
        # dominant shirt colour, WEIGHTED by how much we actually saw each member
        # (visible_s) so a long-visible anchor isn't outvoted by short mis-clustered
        # intruders.
        shirts: Counter = Counter()
        for fid in members:
            s = base_shirt((vote_by_fragment.get(fid) or {}).get("shirt_votes"))
            if s:
                shirts[s] += max(1.0, float((frag_by_id.get(fid) or {}).get("visible_s") or 1.0))
        total_w = sum(shirts.values())
        dom = max(shirts.items(), key=lambda kv: kv[1])[0] if shirts else None
        # only enforce shirt-consistency when there's a CLEAR dominant colour — an
        # even split is genuinely ambiguous, so keep all and let number-agreement /
        # the human judge rather than risk deleting the correct player.
        dom_clear = bool(dom) and total_w and (shirts[dom] / total_w) >= 0.6
        strong_in = set(ch.get("strong_fragment_ids") or [])
        kept = []
        for fid in members:
            v = vote_by_fragment.get(fid) or {}
            s = base_shirt(v.get("shirt_votes"))
            if dom_clear and s is not None and s != dom:
                continue  # wrong-shirt contamination
            # weak corroboration: drop a lone single-read member — but ONLY where we
            # have shirt evidence to judge it. Raw-read artifacts (worker path) carry
            # no shirt votes, so we trust build_chains' vetting and keep the member.
            sv = v.get("shirt_votes") or {}
            has_shirt = any(str(x).lstrip("-").isdigit() for x in sv.values())
            if fid not in strong_in and has_shirt and not _is_corroborated(v):
                continue
            kept.append(fid)
        if not kept:
            continue
        frs = [frag_by_id[i] for i in kept if i in frag_by_id]
        if not frs:
            continue
        ch = dict(ch)
        if len(kept) != len(members):
            surviving_strong = strong_in & set(kept)
            ch["member_fragment_ids"] = sorted(kept)
            ch["strong_fragment_ids"] = sorted(surviving_strong)
            ch["first_s"] = round(min(f["first_s"] for f in frs), 2)
            ch["last_s"] = round(max(f["last_s"] for f in frs), 2)
            ch["visible_s_total"] = round(sum(f["visible_s"] for f in frs), 2)
            # re-derive confidence exactly as build_chains does: if the gate dropped
            # the chain's only strong high-confidence member, it must fall from 'high'
            # so a weak-only chain can never auto-bind (single reads are never trusted).
            ch["confidence"] = (
                "high"
                if any((vote_by_fragment.get(i) or {}).get("confidence") == "high" for i in surviving_strong)
                else "low"
            )
        if dom:
            ch["modal_shirt_color"] = dom  # set for every chain, not only trimmed ones
        ch["number_agreement"] = number_agreement(kept, vote_by_fragment, ch["jersey_number"])
        out.append(ch)
    return out


# --------------------------------------------------------------------------- persistence


def persist_artifacts(match: VideoMatch, artifacts: dict) -> dict:
    """Turn worker artifacts into VideoTracklet rows and flip the match to
    needs_tagging. Re-runs replace prior pipeline rows but keep human work:
    a row whose tag_source='human' (or dismissed) survives by pipeline_key.

    artifacts: {fragments: [...], votes: {entities: [{entity_id, ...vote}]},
                chains: [...]?, thumbnails: {pipeline_key: [blob paths]}?}
    Chains are rebuilt here when absent so the worker may ship votes only.
    """
    fragments = artifacts.get("fragments") or []
    vote_rows = (artifacts.get("votes") or {}).get("entities") or []
    vote_by_fragment: dict[int, dict] = {}
    for v in vote_rows:
        fid = v.get("entity_id")
        if fid is None:
            continue
        if "anchored" in v:  # already-voted row (spike schema)
            v.setdefault("weak_number", None)
            if v.get("weak_number") is None and not v["anchored"] and not v.get("contaminated"):
                votes = v.get("number_votes") or {}
                if sum(votes.values()) == 1:
                    v["weak_number"] = int(next(iter(votes)))
            vote_by_fragment[fid] = v
        else:  # raw reads → vote here
            vote_by_fragment[fid] = vote_fragment(v.get("reads") or [])

    chains = artifacts.get("chains")
    if chains is None:
        chains, _conflicts = build_chains(vote_by_fragment, fragments)
    # strip cross-team / single-read contamination so a chain's box stays on ONE player
    chains = apply_quality_gate(chains, vote_by_fragment, fragments)
    thumbnails = artifacts.get("thumbnails") or {}

    # preserve human decisions across pipeline re-runs
    prior = {
        t.pipeline_key: t
        for t in db.session.query(VideoTracklet).filter(VideoTracklet.video_match_id == match.id)
        if t.tag_source == "human" or t.dismissed or t.review_action is not None
    }
    db.session.query(VideoTracklet).filter(
        VideoTracklet.video_match_id == match.id,
        VideoTracklet.id.notin_([t.id for t in prior.values()] or [0]),
    ).delete(synchronize_session=False)

    frag_by_id = {f["entity_id"]: f for f in fragments}
    chained_fragment_ids: set[int] = set()
    created = 0
    for ch in chains:
        chained_fragment_ids.update(ch["member_fragment_ids"])
        if ch["player_key"] in prior:
            continue
        agreement = ch.get("number_agreement", 1.0)
        db.session.add(
            VideoTracklet(
                video_match_id=match.id,
                kind="chain",
                pipeline_key=ch["player_key"],
                team_cluster=ch["team"],
                suggested_number=ch["jersey_number"],
                suggested_role=ch.get("role"),
                confidence=ch.get("confidence"),
                # internally-inconsistent identity (members disagree on the number even
                # after the gate) is flagged mixed → honest badge + blocks auto-bind.
                contaminated=agreement < NUMBER_AGREEMENT_MIN,
                first_s=ch.get("first_s"),
                last_s=ch.get("last_s"),
                visible_s=ch.get("visible_s_total"),
                thumbnail_paths=thumbnails.get(ch["player_key"]),
                evidence={
                    "member_fragment_ids": ch["member_fragment_ids"],
                    "strong_fragment_ids": ch.get("strong_fragment_ids", []),
                    "number_agreement": agreement,
                    "modal_shirt_color": ch.get("modal_shirt_color"),
                    "votes": {
                        str(fid): vote_by_fragment.get(fid, {}).get("number_votes")
                        for fid in ch["member_fragment_ids"]
                        if fid in vote_by_fragment
                    },
                },
            )
        )
        created += 1

    leftovers = [
        f
        for f in fragments
        if f["entity_id"] not in chained_fragment_ids
        and (f.get("visible_s") or 0) >= MIN_FRAGMENT_VISIBLE_S
        and vote_by_fragment.get(f["entity_id"], {}).get("role") not in GREY_ROLES
    ]
    leftovers.sort(key=lambda f: -(f.get("visible_s") or 0))
    for f in leftovers[:MAX_FRAGMENT_ROWS]:
        key = f"E{f['entity_id']}"
        if key in prior:
            continue
        v = vote_by_fragment.get(f["entity_id"], {})
        db.session.add(
            VideoTracklet(
                video_match_id=match.id,
                kind="fragment",
                pipeline_key=key,
                team_cluster=f.get("team"),
                suggested_number=v.get("jersey_number") or v.get("weak_number"),
                suggested_role=v.get("role"),
                confidence=v.get("confidence"),
                contaminated=bool(v.get("contaminated")),
                first_s=f.get("first_s"),
                last_s=f.get("last_s"),
                visible_s=f.get("visible_s"),
                thumbnail_paths=thumbnails.get(key),
                evidence={"number_votes": v.get("number_votes")} if v else None,
            )
        )
        created += 1

    match.status = "needs_tagging"
    db.session.commit()

    bound = auto_bind(match) if match.our_team_cluster is not None else 0
    logger.info(
        "video match %s: persisted %d tracklet rows (%d chains), auto-bound %d",
        match.id,
        created,
        len(chains),
        bound,
    )
    return {"tracklets": created, "chains": len(chains), "auto_bound": bound}


def auto_bind(match: VideoMatch) -> int:
    """Default-accept high-confidence bindings: an our-side chain whose
    suggested number matches exactly one roster entry binds automatically
    (tag_source='auto'); the review UI shows these as accepted-by-default.
    Requires match.our_team_cluster (human confirms which side is ours)."""
    if match.our_team_cluster not in (0, 1):
        return 0
    roster_by_number: dict[int, VideoRosterEntry] = {r.jersey_number: r for r in match.roster_entries}
    bound = 0
    rows = (
        db.session.query(VideoTracklet)
        .filter(
            VideoTracklet.video_match_id == match.id,
            VideoTracklet.kind == "chain",
            VideoTracklet.confidence == "high",
            VideoTracklet.team_cluster == match.our_team_cluster,
            VideoTracklet.roster_entry_id.is_(None),
            VideoTracklet.dismissed.is_(False),
            VideoTracklet.contaminated.is_(False),  # never auto-bind a mixed-identity chain
        )
        .all()
    )
    for t in rows:
        entry = roster_by_number.get(t.suggested_number)
        if entry is None or t.suggested_role in GREY_ROLES:
            continue
        t.roster_entry_id = entry.id
        t.tag_source = "auto"
        bound += 1
    db.session.commit()
    return bound


def complete_job_with_artifacts(job_id: str, artifacts: dict, gpu_seconds: float | None = None) -> dict:
    """Worker entry point: mark the job succeeded and persist its artifacts."""
    from src.models.video import VideoAnalysisJob  # local import avoids cycles

    job = db.session.get(VideoAnalysisJob, job_id)
    if job is None:
        raise ValueError(f"job {job_id} not found")
    match = db.session.get(VideoMatch, job.video_match_id)
    result = persist_artifacts(match, artifacts)
    job.status = "succeeded"
    job.stage = "persist"
    job.progress = 100
    job.gpu_seconds = gpu_seconds
    job.completed_at = datetime.now(UTC)
    db.session.commit()
    return result
