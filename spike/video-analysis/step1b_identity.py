#!/usr/bin/env python3
"""
step1b_identity.py — Step 1b: corroboration gate that turns Step 1's single-read keyframe
anchors into a small, HIGH-PRECISION set (and demotes the rest to human-review-only).

WHY (ground-truth audit 2026-06-30 — n=40 double-blind visual audit + tiebreak, 39/40 auditor
agreement, on the v8 full match):
  Step 1's single-read keyframe anchors are only **17.5% correct** (7 of 40), NOT the ~70% an
  earlier n=12 spot-check suggested. The dominant failure is **OVER-MERGE (24 of 33 wrong)**:
  the anchor crop legitimately reads a real number off a real player, but the ENTITY is a blob
  of several different players (the tracker/merge fused them), so labelling the whole entity that
  number is wrong. The remaining 9 are crop-level mis-association: carried jersey, background
  bleed, misread number.

  What was MEASURED on the labelled set (this is the design rationale — see ledger 2026-06-30):
    * crop-grounding re-read ALONE  -> 13-16% precision. The over-merged entity's anchor crop
      looks perfect, so an independent re-read just confirms it. It also false-rejects some
      correct anchors. Insufficient, and costs recall.
    * cheap STRUCTURAL signals — tid_share, member-tracklet count, appearance cosine-to-centroid,
      SigLIP cohesion, temporal self-overlap, jersey-number uniqueness — DO NOT separate
      over-merge from correct: a correct entity can be a 20-tracklet blob (e0138), a wrong one
      can be 2 clean-looking tracklets (e0088). Best cheap gate ceiling ~22%. (Within-team SigLIP
      ~= chance, exactly as the identity diagnosis warned.)
    * the ONLY reliable over-merge detector is VISUAL ENTITY-CONSISTENCY: render the entity's
      crops as a center-cropped contact-sheet montage and ask a capable VLM "is every panel the
      same one player?". gemma-4-12B keeps the correct entities (one_player=true) and flags the
      blobs (one_player=false); gemma-4-E4B is too trigger-happy (counts edge-padding neighbours
      as extra people) — use the 12B for THIS gate only (it runs on a handful of montages).

WHAT THIS DOES (corroboration only — it does NOT change upstream tracking/merge):
  For each Step-1 single-keyframe anchor, two gates; PROMOTE to a trusted (confidence='low')
  anchor only if BOTH pass, else DEMOTE to review-only (never auto-trusted):
    1. ENTITY-CONSISTENCY (montage VLM, primary)        -> kills the over-merge bulk + the
       carried/bleed/misread cases too (they also show up as inconsistent panels).
    2. CHEAP >=2 distinct strong shirt colours (no VLM)  -> obvious cross-team over-merge with
       ZERO false-positives on the correct set; a free pre-filter so the caller can skip the VLM
       on clearly-broken entities.
  Multi-read anchors (the baseline count path, and keyframe anchors with >=2 agreeing reads) are
  NOT touched — Step 1 already trusts those and they are not the failure population.

Subcommands:
  build-montages  center-cropped contact sheet per single-keyframe-anchor entity (step1b/montages/)
  consistency     entity-consistency over montages with gemma-4-12B          (step1b/consistency.json)
  eval            pure decision + precision/lift report (+ --labels JSON for a confusion matrix)
  --selftest      unit checks for the pure decision logic

License posture unchanged: pure-Python decision + Apache-2.0 Gemma on consented footage. Apache/MIT/BSD only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from step1_identity import keyframe_vote, keyframe_weight, norm_number  # noqa: E402

# --- gate tunables ---------------------------------------------------------------
STRONG_COLOR_MIN_READS = 2   # a shirt colour counts as "strong" for an entity at >= this many reads
MAX_STRONG_COLORS = 1        # >= 2 distinct strong shirt colours => cross-team over-merge => reject
CONSISTENCY_MODEL = "mlx-community/gemma-4-12B-it-qat-4bit"  # E4B is too trigger-happy for this gate
# center-crop fractions to isolate the tracked box from its padding (PAD_X=0.25, PAD_Y=0.12):
PANEL_CROP_W, PANEL_CROP_H = 0.66, 0.80
PANEL_W, PANEL_H, MONTAGE_COLS = 200, 300, 4

CONSISTENCY_PROMPT = (
    "This is a contact sheet of numbered panels. Each panel is CENTERED on one tracked figure; "
    "ignore any small/partial people at the panel edges and look only at the CENTRAL figure. "
    "A tracker claims every panel's central figure is the SAME ONE football player. "
    "Compare the central figures across panels: same shirt COLOUR and PATTERN? same hair? same "
    "build/skin? (Plain tracksuit/coat figures standing still are coaches/subs = a different "
    "person.) Reply ONLY with JSON: "
    '{"one_player": <true only if every panel\'s central figure is plausibly the same one player>, '
    '"distinct_people": <int>, "reason": "<brief, cite panel numbers that differ>"}'
)


# --------------------------------------------------------------------------- shared loading

def _single_keyframe_anchors(results_dir: Path) -> dict[int, dict[str, Any]]:
    """Reproduce Step 1's vote and return {eid: vote_row} for the single-keyframe anchors only,
    each augmented with the anchoring crop file and the entity's per-read shirt colours."""
    idd = results_dir / "identity"
    reads = json.loads((idd / "reads.json").read_text())["reads"]
    ci = {c["file"]: c for c in json.loads((idd / "crops_index.json").read_text())}

    by_entity: dict[int, list[dict]] = defaultdict(list)
    for r in reads:
        p = r.get("parsed")
        if not p:
            continue
        crop = ci.get(r["file"], {})
        by_entity[r["entity_id"]].append({
            "file": r["file"],
            "number": norm_number(p.get("jersey_number")),
            "role": p.get("role"),
            "shirt": p.get("shirt_color"),
            "weight": keyframe_weight(crop.get("height"), crop.get("laplacian_var")),
        })

    out: dict[int, dict[str, Any]] = {}
    for eid, rs in by_entity.items():
        v = keyframe_vote(rs)
        if not (v.get("anchored") and v.get("single_keyframe")):
            continue
        num = v["jersey_number"]
        anchoring = sorted((r for r in rs if r["number"] == num), key=lambda r: -r["weight"])
        v["anchor_file"] = anchoring[0]["file"] if anchoring else None
        v["n_strong_colors"] = _n_strong_colors(rs)
        out[eid] = v
    return out


def _coarse_color(c: Any) -> str | None:
    return str(c).split()[0].lower() if c else None


def _n_strong_colors(reads: list[dict]) -> int:
    """Distinct shirt colours read >= STRONG_COLOR_MIN_READS times across the entity's crops."""
    cols = Counter(_coarse_color(r.get("shirt")) for r in reads if r.get("shirt"))
    return sum(1 for c, n in cols.items() if c and n >= STRONG_COLOR_MIN_READS)


# --------------------------------------------------------------------------- pure decision

def corroborate(n_strong_colors: int, consistency_one_player: bool | None) -> dict[str, Any]:
    """Pure Step-1b decision for one single-keyframe anchor.
      n_strong_colors        : distinct strong shirt colours among the entity's reads (cheap gate)
      consistency_one_player : the montage VLM verdict (True keep / False reject / None = not run)
    Returns {corroborated, reason}. PROMOTE only if both gates pass; the VLM gate must have run
    AND returned True (precision-first: an un-checked entity is not auto-trusted)."""
    if n_strong_colors >= 2:
        return {"corroborated": False, "reason": "multi_color_overmerge"}
    if consistency_one_player is False:
        return {"corroborated": False, "reason": "entity_not_one_player"}
    if consistency_one_player is None:
        return {"corroborated": False, "reason": "consistency_not_checked"}
    return {"corroborated": True, "reason": "ok"}


# --------------------------------------------------------------------------- montage build

def _center_crop(im, fw: float, fh: float):
    import numpy as np  # local: only needed for the VLM-side subcommands
    h, w = im.shape[:2]
    x0, x1 = int(w * (1 - fw) / 2), int(w * (1 + fw) / 2)
    y0, y1 = int(h * (1 - fh) / 2), int(h * (1 + fh) / 2)
    return np.ascontiguousarray(im[y0:y1, x0:x1])


def build_montages(results_dir: Path, out_dir: Path, max_panels: int = 8) -> int:
    """One center-cropped contact-sheet montage per single-keyframe-anchor entity."""
    import re as _re

    import cv2
    import numpy as np
    crops_dir = results_dir / "identity" / "crops"
    anchors = _single_keyframe_anchors(results_dir)
    by_ent: dict[int, list[str]] = defaultdict(list)
    for f in crops_dir.glob("e*.jpg"):
        m = _re.match(r"e(\d+)_\d+\.jpg", f.name)
        if m and int(m.group(1)) in anchors:
            by_ent[int(m.group(1))].append(f.name)
    out_dir.mkdir(parents=True, exist_ok=True)

    def panel(path: Path):
        im = cv2.imread(str(path))
        if im is None:
            return np.full((PANEL_H, PANEL_W, 3), 64, np.uint8)
        im = _center_crop(im, PANEL_CROP_W, PANEL_CROP_H)
        h, w = im.shape[:2]
        s = min(PANEL_W / w, PANEL_H / h)
        im = cv2.resize(im, (max(1, int(w * s)), max(1, int(h * s))))
        canvas = np.full((PANEL_H, PANEL_W, 3), 32, np.uint8)
        yh, xw = im.shape[:2]
        canvas[(PANEL_H - yh) // 2:(PANEL_H - yh) // 2 + yh,
               (PANEL_W - xw) // 2:(PANEL_W - xw) // 2 + xw] = im
        return canvas

    n = 0
    for eid in sorted(by_ent):
        files = sorted(by_ent[eid])
        anchor = anchors[eid].get("anchor_file")
        if anchor in files:  # put the anchoring crop first
            files = [anchor] + [f for f in files if f != anchor]
        files = files[:max_panels]
        panels = []
        for i, fn in enumerate(files):
            p = panel(crops_dir / fn)
            cv2.putText(p, str(i + 1), (6, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            panels.append(p)
        rows = []
        for r in range(0, len(panels), MONTAGE_COLS):
            row = panels[r:r + MONTAGE_COLS]
            while len(row) < MONTAGE_COLS:
                row.append(np.full((PANEL_H, PANEL_W, 3), 16, np.uint8))
            rows.append(np.hstack(row))
        cv2.imwrite(str(out_dir / f"e{eid:04d}.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])
        n += 1
    return n


# --------------------------------------------------------------------------- consistency VLM

def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    m2 = re.search(r'"one_player"\s*:\s*(true|false)', text)
    return {"one_player": m2.group(1) == "true"} if m2 else {}


def run_consistency(results_dir: Path, montage_dir: Path, model_name: str, out_path: Path) -> dict[str, Any]:
    """Entity-consistency over the montages. Incremental: cached entities are not re-read."""
    anchors = _single_keyframe_anchors(results_dir)
    cached: dict[str, dict] = {}
    if out_path.exists():
        cached = {str(r["eid"]): r for r in json.loads(out_path.read_text()).get("entities", [])}
    todo = [eid for eid in sorted(anchors) if str(eid) not in cached]
    if not todo:
        print(f"consistency: cached ({len(cached)} entities)")
        return {"model": model_name, "entities": list(cached.values())}

    try:
        from mlx_vlm import generate, load
        from mlx_vlm.prompt_utils import apply_chat_template
    except ImportError as e:
        raise SystemExit(f"mlx_vlm import failed: {e} (pip install mlx-vlm, Apple Silicon only)")

    print(f"consistency: loading {model_name} ... ({len(todo)} montages)")
    model, processor = load(model_name)
    cfg = model.config
    t0 = time.perf_counter()
    for eid in todo:
        f = montage_dir / f"e{eid:04d}.jpg"
        formatted = apply_chat_template(processor, cfg, CONSISTENCY_PROMPT, num_images=1)
        r = generate(model, processor, formatted, [str(f)], max_tokens=150, temperature=0.0, verbose=False)
        txt = r.text if hasattr(r, "text") else str(r)
        p = _parse_json(txt)
        op = p.get("one_player")
        cached[str(eid)] = {
            "eid": eid,
            "one_player": bool(op) if op is not None else None,
            "distinct_people": p.get("distinct_people"),
            "reason": str(p.get("reason", ""))[:120],
        }
    payload = {"model": model_name, "vlm_elapsed_s": round(time.perf_counter() - t0, 1),
               "entities": [cached[str(e)] for e in sorted(anchors)]}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=1))
    print(f"consistency: {len(todo)} read in {payload['vlm_elapsed_s']}s -> {out_path}")
    return payload


# --------------------------------------------------------------------------- evaluation

def evaluate(results_dir: Path, consistency_path: Path, labels_path: Path | None) -> dict[str, Any]:
    anchors = _single_keyframe_anchors(results_dir)
    ents = {e["entity_id"]: e for e in json.loads((results_dir / "entities.json").read_text())}
    vis = {eid: ents.get(eid, {}).get("visible_s", 0.0) for eid in anchors}

    cons = {}
    if consistency_path.exists():
        cons = {r["eid"]: r for r in json.loads(consistency_path.read_text()).get("entities", [])}

    decisions: dict[int, dict] = {}
    for eid, v in anchors.items():
        one = cons.get(eid, {}).get("one_player")
        d = corroborate(v["n_strong_colors"], one)
        d["visible_s"] = round(vis.get(eid, 0.0), 1)
        d["jersey_number"] = v["jersey_number"]
        d["one_player"] = one
        d["n_strong_colors"] = v["n_strong_colors"]
        decisions[eid] = d

    promoted = {e for e, d in decisions.items() if d["corroborated"]}
    demoted = set(anchors) - promoted

    def vsum(ids):
        return round(sum(vis.get(e, 0.0) for e in ids), 1)

    rep: dict[str, Any] = {
        "results_dir": str(results_dir),
        "single_keyframe_anchors": len(anchors),
        "consistency_checked": sum(1 for e in anchors if cons.get(e, {}).get("one_player") is not None),
        "promoted": {"count": len(promoted), "visible_s": vsum(promoted)},
        "demoted": {"count": len(demoted), "visible_s": vsum(demoted),
                    "by_reason": dict(Counter(decisions[e]["reason"] for e in demoted))},
    }

    if labels_path and labels_path.exists():
        labels = {lb["eid"]: lb for lb in json.loads(labels_path.read_text())}
        rep["confusion"] = _confuse(anchors, decisions, labels, vis)
    return rep, decisions


def _confuse(anchors, decisions, labels, vis) -> dict[str, Any]:
    def wrong(e):
        return labels.get(e, {}).get("final_verdict") == "wrong"

    TK = MISS = FR = TR = 0
    tk_s = miss_s = fr_s = tr_s = 0.0
    for e in anchors:
        if e not in labels:
            continue
        rej = not decisions[e]["corroborated"]
        w = wrong(e)
        s = vis.get(e, 0.0)
        if w and rej:
            TR += 1
            tr_s += s
        elif w and not rej:
            MISS += 1
            miss_s += s
        elif (not w) and rej:
            FR += 1
            fr_s += s
        else:
            TK += 1
            tk_s += s
    n_corr = sum(1 for e in anchors if e in labels and not wrong(e))
    base_prec = n_corr / len([e for e in anchors if e in labels]) if anchors else None
    return {
        "baseline_precision_pct": round(100 * base_prec, 1) if base_prec is not None else None,
        "promoted_precision_pct": round(100 * TK / (TK + MISS), 1) if (TK + MISS) else None,
        "correct_recall_pct": round(100 * TK / (TK + FR), 1) if (TK + FR) else None,
        "promoted_correct": TK, "promoted_wrong": MISS,
        "dropped_wrong": TR, "dropped_correct": FR,
        "promoted_good_s": round(tk_s, 1), "promoted_bad_s": round(miss_s, 1),
        "dropped_bad_s": round(tr_s, 1), "dropped_good_s": round(fr_s, 1),
    }


def _print(rep: dict[str, Any]) -> None:
    p, d = rep["promoted"], rep["demoted"]
    print(f"\n{'='*70}\nSTEP 1b — corroboration gate (entity-consistency + cheap colour)")
    print(f"results: {rep['results_dir']}")
    print(f"{'='*70}")
    print(f"  single-keyframe anchors : {rep['single_keyframe_anchors']}  "
          f"(consistency-checked: {rep['consistency_checked']})")
    print(f"  PROMOTED (trusted)      : {p['count']}  ({p['visible_s']}s)")
    print(f"  demoted (review-only)   : {d['count']}  ({d['visible_s']}s)  {d['by_reason']}")
    if "confusion" in rep:
        c = rep["confusion"]
        print(f"  {'-'*60}")
        print(f"  PRECISION  baseline {c['baseline_precision_pct']}%  ->  promoted {c['promoted_precision_pct']}%"
              f"   (correct-recall {c['correct_recall_pct']}%)")
        print(f"  promoted: {c['promoted_correct']} correct + {c['promoted_wrong']} wrong "
              f"({c['promoted_good_s']}s good / {c['promoted_bad_s']}s bad)")
        print(f"  dropped : {c['dropped_wrong']} wrong + {c['dropped_correct']} correct "
              f"({c['dropped_bad_s']}s bad / {c['dropped_good_s']}s good lost)")
    print(f"{'='*70}\n")


# --------------------------------------------------------------------------- selftest

def _selftest() -> None:
    # cheap colour gate fires first (cross-team over-merge), regardless of VLM
    assert corroborate(2, True)["corroborated"] is False
    assert corroborate(3, None)["reason"] == "multi_color_overmerge"
    # VLM says not-one-player -> reject (the over-merge bulk)
    assert corroborate(1, False) == {"corroborated": False, "reason": "entity_not_one_player"}
    # VLM not run -> precision-first refusal (never auto-trust an unchecked entity)
    assert corroborate(1, None)["reason"] == "consistency_not_checked"
    assert corroborate(0, None)["corroborated"] is False
    # both gates pass -> promote
    assert corroborate(1, True) == {"corroborated": True, "reason": "ok"}
    assert corroborate(0, True)["corroborated"] is True
    # _n_strong_colors: needs >=2 reads of a colour to count it
    assert _n_strong_colors([{"shirt": "red"}, {"shirt": "red"}, {"shirt": "blue"}]) == 1
    assert _n_strong_colors([{"shirt": "red"}, {"shirt": "red"}, {"shirt": "blue"}, {"shirt": "blue"}]) == 2
    assert _n_strong_colors([{"shirt": "red and white"}, {"shirt": "red"}]) == 1  # coarse first token
    print("step1b_identity selftest: OK")


def main() -> None:
    ap = argparse.ArgumentParser(description="Step 1b corroboration gate for single-read anchors")
    ap.add_argument("cmd", nargs="?", default="eval",
                    choices=["build-montages", "consistency", "eval"])
    ap.add_argument("--results-dir", type=Path, default=SCRIPT_DIR / "results" / "v8" / "combined")
    ap.add_argument("--model", default=CONSISTENCY_MODEL)
    ap.add_argument("--labels", type=Path, default=None, help="ground-truth labels JSON for a confusion matrix")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
        return

    step1b_dir = args.results_dir / "identity" / "step1b"
    montage_dir = step1b_dir / "montages"
    consistency_path = step1b_dir / "consistency.json"

    if args.cmd == "build-montages":
        n = build_montages(args.results_dir, montage_dir)
        print(f"built {n} montages -> {montage_dir}")
        return
    if args.cmd == "consistency":
        if not montage_dir.exists():
            build_montages(args.results_dir, montage_dir)
        run_consistency(args.results_dir, montage_dir, args.model, consistency_path)
        return

    rep, _ = evaluate(args.results_dir, consistency_path, args.labels)
    _print(rep)
    if args.json:
        print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
