#!/usr/bin/env python3
"""
step1_identity.py — Step 1 of the player-identification fix: keyframe-weighted, non-player-
filtered voting that extracts MORE and CLEANER anchors from the SAME VLM reads.

WHY (diagnosis, multi-agent workflow 2026-06-25, on the v8 full match):
  Only 14% of player-visible-time gets a name. The reader (zero-shot Gemma) is NOT the
  bottleneck — a visual audit found 0/20 of its NULL crops were human-legible: the nulls are
  back-turned players (~55%, number physically not facing the panning cam) or non-players
  (~35%, coach/ref/sub/spectator with no number). read-success is FLAT vs crop size/sharpness.
  So "read harder" has a ~0 ceiling. But the current vote (anchor_identity.vote_entities)
  is an UNWEIGHTED count with a hard MIN_VOTES=2, which:
    - DISCARDS a single big/sharp/back-facing "keyframe" read (the most reliable kind), and
    - lets many tiny, side-on, noisy reads carry equal weight, and
    - reads/anchors non-player detections that have no jersey number by design.

WHAT THIS DOES (no new VLM calls — re-votes the cached reads):
  1. KEYFRAME WEIGHTING  weight each read by crop quality (height x sharpness). A single
     high-quality keyframe read can anchor; noisy small reads are down-weighted.
  2. NON-PLAYER GATE     drop entities whose role is dominantly referee/not_a_player and that
     carry no corroborated number — they pollute reads and the report.
  3. PRECISION GUARDS    OCR digit-doubling tolerance + contamination (splice) refusal, kept
     from the baseline so precision does not regress.

Validated against results/v8/combined/identity (reads/crops_index/votes) + entities.json:
prints the lift in NAMED visible-time and anchored-entity count vs the baseline, plus
precision sanity (agreement with existing high-confidence anchors, share of risky single-
keyframe anchors). The COMPLEMENTARY half — reading MORE crops per chain to catch the few
back-facing moments — is the crop-selection change in anchor_identity (needs a re-run); this
module proves the voting half on real data today.

License posture unchanged: pure-Python, no model. Apache/MIT/BSD only.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent

GREY_ROLES = {"referee", "not_a_player"}

# --- keyframe weighting tunables (a read's vote weight in [0, 2]) -----------------
KF_HEIGHT_REF = 160.0   # px; crop height at/above which the size term saturates
KF_SHARP_REF = 120.0    # laplacian variance at/above which the sharpness term saturates
KF_SHARP_FLOOR = 0.45   # a big-but-soft crop still counts this fraction
# --- anchor decision tunables ----------------------------------------------------
STRONG_KEYFRAME = 1.55  # weighted top must reach this to anchor via the keyframe path
DOMINANCE = 1.5         # weighted top must beat the best rival number by this factor
CONTAM_RIVAL_W = 1.55   # a rival number this well-supported => splice => refuse to anchor
SINGLE_KF_MIN = 1.75    # a SINGLE read may anchor only if it's this strong AND has no rival
GREY_MAX = 0.5          # refuse a single-read anchor if >= this fraction of the entity's reads
                        # are a NON-PLAYER role (coach/ref/spectator). Role distinguishes them
                        # from a legit back-turned player (still role=outfield) — the latter is
                        # mostly no-number reads too, so a no-number gate would wrongly drop it.
HIGH_CONF_W = 3.0       # weighted top at/above this (or zero rival) => confidence 'high'
MIN_VOTES = 2           # baseline count path: >= 2 agreeing reads (never regress this)


def norm_number(v: Any) -> int | None:
    """Mirror anchor_identity.norm_number: a jersey number is an int in [1, 99]."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if 1 <= v <= 99 else None
    if isinstance(v, float) and v.is_integer():
        return norm_number(int(v))
    if isinstance(v, str) and v.strip().isdigit():
        return norm_number(int(v.strip()))
    return None


def keyframe_weight(height: float | None, sharpness: float | None) -> float:
    """Crop quality -> read weight in [0, 2]. Needs BOTH size and (some) sharpness to count
    as a strong keyframe; a tiny crop is ~0 regardless of sharpness."""
    h = max(0.0, min(1.0, (height or 0.0) / KF_HEIGHT_REF))
    s = KF_SHARP_FLOOR + (1.0 - KF_SHARP_FLOOR) * max(0.0, min(1.0, (sharpness or 0.0) / KF_SHARP_REF))
    return round(2.0 * h * s, 4)


def _is_doubling(a: int, b: int) -> bool:
    return str(a) * 2 == str(b) or str(b) * 2 == str(a)


def keyframe_vote(reads: list[dict]) -> dict[str, Any]:
    """Weighted vote over one entity's reads. `reads` = [{number:int|None, role:str|None,
    weight:float, shirt:str|None}]. Returns a vote row mirroring anchor_identity.vote_entities
    plus keyframe weighting and single-read consistency guards."""
    wnum: dict[int, float] = defaultdict(float)
    cnum: Counter = Counter()
    role_w: dict[str, float] = defaultdict(float)
    noisy_reads = 0  # reads that saw no number OR a non-player role (diagnostic only)
    grey_reads = 0   # reads with a NON-PLAYER role (the single-read anchor guard)
    for r in reads:
        role = r.get("role")
        if isinstance(role, str):
            role_w[role] += max(r.get("weight", 0.0), 0.05)
            if role in GREY_ROLES:
                grey_reads += 1
        n = r.get("number")
        if n is not None:
            wnum[n] += r.get("weight", 0.0)
            cnum[n] += 1
        if n is None or role in GREY_ROLES:
            noisy_reads += 1
    noisy_frac = noisy_reads / len(reads) if reads else 0.0
    grey_frac = grey_reads / len(reads) if reads else 0.0

    number = None
    anchored = False
    confidence = None
    contaminated = False
    via = None
    guard_failed = None
    if wnum:
        # COUNT path = baseline anchor_identity semantics (>=2 agreeing reads), kept verbatim
        # so Step 1 never regresses an anchor the baseline already trusts.
        cm = cnum.most_common()
        c_top, c_topn = cm[0]
        c_rivals = [(n, c) for n, c in cm[1:] if not _is_doubling(c_top, n)]
        c_second = c_rivals[0][1] if c_rivals else 0
        count_contam = c_second >= MIN_VOTES
        count_ok = c_topn >= MIN_VOTES and c_topn > c_second and not count_contam
        count_num = c_top if count_ok else None

        # KEYFRAME path = weighted: one excellent (big, sharp, back-facing) read can anchor.
        wr = sorted(wnum.items(), key=lambda kv: (-kv[1], kv[0]))
        w_top, w_topw = wr[0]
        w_rivals = [(n, w) for n, w in wr[1:] if not _is_doubling(w_top, n)]
        w_rival_w = w_rivals[0][1] if w_rivals else 0.0
        kf_contam = w_rival_w >= CONTAM_RIVAL_W
        kf_ok = w_topw >= STRONG_KEYFRAME and w_topw >= DOMINANCE * w_rival_w and not kf_contam
        if cnum.get(w_top, 0) == 1:
            # Anchoring on a SINGLE read is the risky class (spot-check: failures are crop
            # mis-association, NOT soft reads — they're the sharpest crops). Demand an excellent
            # crop, no rival, and an entity NOT dominated by NON-PLAYER-role reads (coach /
            # spectator / a number read off a sideline figure). Role-gating (not no-number-
            # gating) keeps legit back-turned players, who are still tagged outfield.
            ok = w_topw >= SINGLE_KF_MIN and w_rival_w == 0.0 and grey_frac < GREY_MAX
            if not ok:
                kf_ok = False
                guard_failed = ("rival" if w_rival_w > 0 else "weak" if w_topw < SINGLE_KF_MIN
                                else "nonplayer")
        kf_num = w_top if kf_ok else None

        # contaminated = baseline splice meaning only (count second>=2), plus a genuine
        # count-vs-keyframe number disagreement. kf_contam only gates kf_ok, never exported.
        contaminated = count_contam
        if count_ok and kf_ok and count_num != kf_num and not _is_doubling(count_num, kf_num):
            contaminated = True
        elif count_ok or kf_ok:
            anchored = True
            number = kf_num if kf_ok else count_num
            via = "both" if (count_ok and kf_ok) else ("keyframe" if kf_ok else "count")
            top_w = wnum[number]
            rival_w = max((w for n, w in wr if n != number and not _is_doubling(number, n)), default=0.0)
            confidence = "high" if ((rival_w == 0.0 and cnum[number] >= MIN_VOTES) or top_w >= HIGH_CONF_W) else "low"

    modal_role = max(role_w.items(), key=lambda kv: (kv[1], kv[0]))[0] if role_w else None
    nonplayer = modal_role in GREY_ROLES and not anchored
    return {
        "number_votes_weighted": {str(k): round(v, 3) for k, v in sorted(wnum.items())},
        "number_votes": {str(k): cnum[k] for k in sorted(cnum)},
        "role": modal_role,
        "noisy_frac": round(noisy_frac, 2),
        "grey_frac": round(grey_frac, 2),
        "jersey_number": number,
        "anchored": anchored,
        "confidence": confidence,
        "contaminated": contaminated,
        "nonplayer": nonplayer,
        "via": via,
        "guard_failed": guard_failed,
        "top_weight": round(wnum.get(number, max(wnum.values(), default=0.0)), 3) if number
        else round(max(wnum.values(), default=0.0), 3),
        "single_keyframe": anchored and cnum.get(number, 0) == 1,
    }


# --------------------------------------------------------------------------- evaluation

def _load(results_dir: Path) -> dict[str, Any]:
    idd = results_dir / "identity"
    reads = json.loads((idd / "reads.json").read_text())["reads"]
    ci = {c["file"]: c for c in json.loads((idd / "crops_index.json").read_text())}
    base_votes = json.loads((idd / "votes.json").read_text())["entities"]
    ents = json.loads((results_dir / "entities.json").read_text())
    return {"reads": reads, "ci": ci, "base_votes": base_votes,
            "vis": {e["entity_id"]: e.get("visible_s", 0.0) for e in ents},
            "team": {e["entity_id"]: e.get("team", -1) for e in ents},
            "total_vis": sum(e.get("visible_s", 0.0) for e in ents)}


def evaluate(results_dir: Path) -> dict[str, Any]:
    d = _load(results_dir)
    reads, ci, vis = d["reads"], d["ci"], d["vis"]

    # group reads by entity, attaching keyframe weight from the crop index
    by_entity: dict[int, list[dict]] = defaultdict(list)
    for r in reads:
        p = r.get("parsed")
        if not p:
            continue
        crop = ci.get(r["file"], {})
        by_entity[r["entity_id"]].append({
            "number": norm_number(p.get("jersey_number")),
            "role": p.get("role"),
            "shirt": p.get("shirt_color"),
            "weight": keyframe_weight(crop.get("height"), crop.get("laplacian_var")),
        })

    step1 = {eid: keyframe_vote(rs) for eid, rs in by_entity.items()}
    base = {v["entity_id"]: v for v in d["base_votes"]}

    base_anc = {e for e, v in base.items() if v.get("anchored")}
    step1_anc = {e for e, v in step1.items() if v.get("anchored")}
    gated = {e for e, v in step1.items() if v.get("nonplayer")}

    def vsum(ids):
        return round(sum(vis.get(e, 0.0) for e in ids), 1)

    new = step1_anc - base_anc
    lost = base_anc - step1_anc
    both = base_anc & step1_anc
    agree = sum(1 for e in both if step1[e]["jersey_number"] == base[e].get("jersey_number"))
    new_single = {e for e in new if step1[e]["single_keyframe"]}
    new_corroborated = new - new_single
    # precision sanity on lost: were these baseline 'high' confidence?
    lost_high = sum(1 for e in lost if base[e].get("confidence") == "high")
    # would-be single-read anchors REFUSED by the consistency guards (the precision fix)
    guarded = {e: step1[e]["guard_failed"] for e in step1 if step1[e].get("guard_failed")}
    guard_reasons = dict(Counter(guarded.values()))
    addr_ids = set(step1.keys())  # entities with >=1 parsed read (the addressable denominator)
    addr_total = round(sum(vis.get(e, 0.0) for e in addr_ids), 1) or 1.0

    total = d["total_vis"] or 1.0
    return {
        "results_dir": str(results_dir),
        "total_entity_visible_s": round(total, 1),
        "baseline": {"anchored": len(base_anc), "named_visible_s": vsum(base_anc),
                     "named_pct": round(100 * vsum(base_anc) / total, 1)},
        "step1": {"anchored": len(step1_anc), "named_visible_s": vsum(step1_anc),
                  "named_pct": round(100 * vsum(step1_anc) / total, 1)},
        "delta": {"anchored": len(step1_anc) - len(base_anc),
                  "named_visible_s": round(vsum(step1_anc) - vsum(base_anc), 1),
                  "named_pct_points": round(100 * (vsum(step1_anc) - vsum(base_anc)) / total, 1)},
        "new_anchors": {"count": len(new), "visible_s": vsum(new),
                        "corroborated": len(new_corroborated), "corroborated_visible_s": vsum(new_corroborated),
                        "single_keyframe": len(new_single), "single_keyframe_visible_s": vsum(new_single)},
        "guarded_out": {"count": len(guarded), "visible_s": vsum(set(guarded)), "by_reason": guard_reasons},
        "addressable": {"entities_with_reads": len(addr_ids), "visible_s": round(addr_total, 1),
                        "step1_named_pct": round(100 * vsum(step1_anc) / addr_total, 1)},
        "lost_anchors": {"count": len(lost), "visible_s": vsum(lost),
                         "were_high_confidence": lost_high},
        "agreement_on_shared": {"shared": len(both), "same_number": agree,
                                "pct": round(100 * agree / len(both), 1) if both else None},
        "nonplayer_gate": {"entities_dropped": len(gated), "visible_s_dropped": vsum(gated),
                           "reads_saved": sum(1 for r in reads
                                              if r.get("entity_id") in gated and r.get("parsed"))},
    }


def _print(rep: dict[str, Any]) -> None:
    b, s, dl = rep["baseline"], rep["step1"], rep["delta"]
    print(f"\n{'='*66}\nSTEP 1 — keyframe-weighted vote + non-player gate")
    print(f"results: {rep['results_dir']} | total entity visible {rep['total_entity_visible_s']}s")
    print(f"{'='*66}")
    print(f"  baseline anchors : {b['anchored']:4d}  named {b['named_visible_s']:>8.1f}s  ({b['named_pct']}%)")
    print(f"  step1    anchors : {s['anchored']:4d}  named {s['named_visible_s']:>8.1f}s  ({s['named_pct']}%)")
    print(f"  DELTA            : {dl['anchored']:+4d}  named {dl['named_visible_s']:+8.1f}s  ({dl['named_pct_points']:+}pp)")
    na, la, ag = rep["new_anchors"], rep["lost_anchors"], rep["agreement_on_shared"]
    go, ad, ng = rep["guarded_out"], rep["addressable"], rep["nonplayer_gate"]
    print(f"  new anchors      : {na['count']} (+{na['visible_s']}s) = "
          f"{na['corroborated']} corroborated + {na['single_keyframe']} single-keyframe ({na['single_keyframe_visible_s']}s)")
    print(f"  guarded out      : {go['count']} risky single-reads refused ({go['visible_s']}s) {go['by_reason']}")
    print(f"  lost anchors     : {la['count']} ({la['visible_s']}s) | were high-conf: {la['were_high_confidence']}  <- want 0")
    print(f"  agreement shared : {ag['same_number']}/{ag['shared']} ({ag['pct']}%)  <- want ~100% (precision sanity)")
    print(f"  addressable view : {ad['step1_named_pct']}% of entities-with-reads named ({ad['visible_s']}s readable)")
    print(f"  non-player gate  : dropped {ng['entities_dropped']} entities ({ng['visible_s_dropped']}s), "
          f"saved {ng['reads_saved']} wasted reads")
    print(f"{'='*66}\n")


def _selftest() -> None:
    """Unit checks for keyframe_weight + keyframe_vote semantics."""
    assert keyframe_weight(0, 999) == 0.0
    assert keyframe_weight(200, 200) == 2.0
    assert 0 < keyframe_weight(80, 60) < 2.0
    # NEW: one excellent keyframe read anchors via the keyframe path (count MIN_VOTES=2 would NOT)
    v = keyframe_vote([{"number": 7, "role": "outfield", "weight": 1.8}])
    assert v["anchored"] and v["jersey_number"] == 7 and v["single_keyframe"] and v["via"] == "keyframe", v
    # a SINGLE weak read never anchors (count<2 AND weight<SINGLE_KF_MIN)
    v = keyframe_vote([{"number": 7, "role": "outfield", "weight": 0.3}])
    assert not v["anchored"], v
    # baseline preserved: two agreeing reads anchor via the count path even if small/soft
    v = keyframe_vote([{"number": 7, "role": "outfield", "weight": 0.3},
                       {"number": 7, "role": "outfield", "weight": 0.3}])
    assert v["anchored"] and v["via"] == "count", v
    # two well-supported rival numbers (2 reads each) = contaminated splice -> refuse
    v = keyframe_vote([{"number": 7, "weight": 1.6, "role": "outfield"}] * 2
                      + [{"number": 4, "weight": 1.6, "role": "outfield"}] * 2)
    assert v["contaminated"] and not v["anchored"], v
    # OCR doubling: 44 doesn't rival 4; 4 anchors on its own >=2 reads
    v = keyframe_vote([{"number": 4, "weight": 0.8, "role": "outfield"},
                       {"number": 4, "weight": 0.8, "role": "outfield"},
                       {"number": 44, "weight": 1.6, "role": "outfield"}])
    assert v["anchored"] and v["jersey_number"] == 4 and not v["contaminated"], v
    # non-player with no number is gated
    v = keyframe_vote([{"number": None, "role": "not_a_player", "weight": 1.5},
                       {"number": None, "role": "not_a_player", "weight": 1.2}])
    assert v["nonplayer"] and not v["anchored"], v
    # GUARD nonplayer: one big read but the entity is mostly NON-PLAYER role -> refuse
    # (the spot-check failure class: coach/spectator, or a number read off a sideline figure)
    v = keyframe_vote([{"number": 77, "role": "outfield", "weight": 2.0},
                       {"number": None, "role": "not_a_player", "weight": 1.5},
                       {"number": None, "role": "not_a_player", "weight": 1.2}])
    assert not v["anchored"] and v["guard_failed"] == "nonplayer", v
    # KEEP legit back-turned player: one excellent read + many no-number OUTFIELD reads -> anchors
    # (role-gating, not no-number-gating: the player is still tagged a player when facing away)
    v = keyframe_vote([{"number": 9, "role": "outfield", "weight": 1.9}]
                      + [{"number": None, "role": "outfield", "weight": 0.6}] * 4)
    assert v["anchored"] and v["jersey_number"] == 9 and v["via"] == "keyframe", v
    # GUARD weak: a lone read that isn't an excellent keyframe -> refuse
    v = keyframe_vote([{"number": 5, "role": "outfield", "weight": 1.6}])
    assert not v["anchored"] and v["guard_failed"] == "weak", v
    # clean lone keyframe (excellent crop) still anchors
    v = keyframe_vote([{"number": 9, "role": "outfield", "weight": 1.9}])
    assert v["anchored"] and v["jersey_number"] == 9 and v["via"] == "keyframe" and v["single_keyframe"], v
    print("step1_identity selftest: OK")


def main() -> None:
    p = argparse.ArgumentParser(description="Step 1: keyframe-weighted identity re-vote + lift report")
    p.add_argument("--results-dir", type=Path, default=SCRIPT_DIR / "results" / "v8" / "combined")
    p.add_argument("--json", action="store_true", help="dump full JSON report")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    if args.selftest:
        _selftest()
        return
    rep = evaluate(args.results_dir)
    _print(rep)
    if args.json:
        print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
