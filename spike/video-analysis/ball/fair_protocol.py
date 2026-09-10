"""TRAIN-only operating points and paired diagnostics on recipe-selected clips."""

from __future__ import annotations
import math
from human_score import score_candidate
from metrics import clip_class
from round2_analysis import independent_sizes

BUCKETS = ("<6", "6–<10", "10–<16", "16–<24", ">=24", "unknown")


def threshold_for_budget(outputs, labels, train, target):
    """Keep >= threshold; remove tied scores together. Never inspect held-out."""
    selected = {k: v for k, v in labels.items() if k[0] in train}
    no_ball = sum(not v["visible"] for v in selected.values())
    if not no_ball or target < 0:
        raise ValueError("nonnegative budget and TRAIN no-ball labels required")
    scores = sorted(
        (
            d["confidence"]
            for cid in train
            for row in outputs[cid]["frames"]
            if (cid, row["t"]) in selected and not selected[(cid, row["t"])]["visible"]
            for d in row["detections"]
        ),
        reverse=True,
    )
    allowed = math.floor(target * no_ball / 20 + 1e-12)
    threshold = (
        0.01 if len(scores) <= allowed else math.nextafter(scores[allowed], math.inf)
    )
    actual = sum(s >= threshold for s in scores)
    return {
        "threshold": threshold,
        "target_false_per_10s": target,
        "train_no_ball": no_ball,
        "allowed_false_boxes": allowed,
        "achieved_false_boxes": actual,
        "achieved_false_per_10s": 20 * actual / no_ball,
    }


def hits(outputs, labels, cids, threshold):
    return {
        (cid, r["t"]): bool(
            (
                top := max(
                    (d for d in r["detections"] if d["confidence"] >= threshold),
                    key=lambda d: d["confidence"],
                    default=None,
                )
            )
            and math.dist(
                top["xy"], [labels[(cid, r["t"])]["x"], labels[(cid, r["t"])]["y"]]
            )
            <= 20
        )
        for cid in cids
        for r in outputs[cid]["frames"]
        if labels.get((cid, r["t"]), {}).get("visible")
    }


def mcnemar(candidate, baseline):
    if candidate.keys() != baseline.keys():
        raise ValueError("McNemar requires identical visible frames")
    wins = sum(v and not baseline[k] for k, v in candidate.items())
    losses = sum(not v and baseline[k] for k, v in candidate.items())
    n = wins + losses
    return {
        "n": len(candidate),
        "wins": wins,
        "losses": losses,
        "both_hit": sum(v and baseline[k] for k, v in candidate.items()),
        "both_miss": sum(not v and not baseline[k] for k, v in candidate.items()),
        "exact_two_sided_p": min(
            1.0, 2 * sum(math.comb(n, i) for i in range(min(wins, losses) + 1)) / 2**n
        )
        if n
        else 1.0,
        "limitation": "Frame independence is false; two clips from one match cannot establish a winner.",
    }


def size_scores(m, labels, outputs, cids, threshold):
    sizes = independent_sizes(m, labels)
    on = {c["clip_id"] for c in m["clips"] if clip_class(c) == "on_ball"} & set(cids)
    scored = hits(outputs, labels, on, threshold)
    result = {b: {"visible": 0, "hits": 0} for b in BUCKETS}
    for k, hit in scored.items():
        s = sizes.get(k)
        bucket = (
            "unknown"
            if s is None
            else next(
                (b for edge, b in zip((6, 10, 16, 24), BUCKETS) if s < edge), ">=24"
            )
        )
        result[bucket]["visible"] += 1
        result[bucket]["hits"] += hit
    for r in result.values():
        r["recall"] = r["hits"] / r["visible"] if r["visible"] else None
    return result


def path_credit(outputs, labels, cids, threshold):
    false = credit = no_ball = 0
    for cid in cids:
        visible = sorted(
            (t, v) for (c, t), v in labels.items() if c == cid and v["visible"]
        )
        for row in outputs[cid]["frames"]:
            label = labels.get((cid, row["t"]))
            if label is None or label["visible"]:
                continue
            no_ball += 1
            ds = [d for d in row["detections"] if d["confidence"] >= threshold]
            false += len(ds)
            before = [(t, v) for t, v in visible if t < row["t"]]
            after = [(t, v) for t, v in visible if t > row["t"]]
            if not before or not after or after[0][0] - before[-1][0] > 1.01:
                continue
            t0, v0 = before[-1]
            t1, v1 = after[0]
            f = (row["t"] - t0) / (t1 - t0)
            point = [v0[k] + f * (v1[k] - v0[k]) for k in ("x", "y")]
            credit += sum(math.dist(d["xy"], point) <= 50 for d in ds)
    return {
        "false": false,
        "credits": credit,
        "no_ball": no_ball,
        "false_per_10s": 20 * false / no_ball if no_ball else None,
        "path_credited_false_per_10s": 20 * (false - credit) / no_ball
        if no_ball
        else None,
    }


def cohort(m, labels, outputs, cids, threshold):
    subset = {**m, "clips": [c for c in m["clips"] if c["clip_id"] in cids]}
    scored = score_candidate(
        subset,
        labels,
        "candidate",
        {cid: outputs[cid] for cid in cids},
        threshold=threshold,
    )
    scored["headline_scope"] = (
        "Explicit cohort only; TRAIN/H membership is given by the parent scope"
    )
    scored["size_buckets"] = size_scores(m, labels, outputs, cids, threshold)
    scored["path_sensitivity"] = path_credit(outputs, labels, cids, threshold)
    return scored


def diagnostic_curve(m, outputs, labels, held):
    """Every prediction-score breakpoint; no threshold or checkpoint selection."""
    on = {c["clip_id"] for c in m["clips"] if clip_class(c) == "on_ball"} & set(held)
    events = {}
    visible = sum(v["visible"] for (cid, _), v in labels.items() if cid in on)
    no_ball = sum(not v["visible"] for (cid, _), v in labels.items() if cid in held)
    for cid in held:
        for row in outputs[cid]["frames"]:
            label = labels.get((cid, row["t"]))
            if not label:
                continue
            ds = row["detections"]
            if not label["visible"]:
                for d in ds:
                    events.setdefault(d["confidence"], [0, 0])[1] += 1
            elif cid in on and ds:
                top = max(ds, key=lambda d: d["confidence"])
                if math.dist(top["xy"], [label["x"], label["y"]]) <= 20:
                    events.setdefault(top["confidence"], [0, 0])[0] += 1
    curve = [
        {
            "threshold": math.nextafter(max(events, default=1.0), math.inf),
            "top1_hits": 0,
            "false_boxes": 0,
            "recall": 0.0,
            "false_per_10s": 0.0,
        }
    ]
    h = f = 0
    for threshold, (dh, df) in sorted(events.items(), reverse=True):
        h += dh
        f += df
        curve.append(
            {
                "threshold": threshold,
                "top1_hits": h,
                "false_boxes": f,
                "recall": h / visible,
                "false_per_10s": 20 * f / no_ball,
            }
        )
    return curve


def evaluate(m, labels, outputs, split):
    points = {}
    for budget in (1.0, 2.0):
        op = threshold_for_budget(outputs, labels, split["train"], budget)
        points[str(int(budget))] = {
            **op,
            **{
                scope: cohort(m, labels, outputs, split[key], op["threshold"])
                for scope, key in (("train", "train"), ("held", "held_out"))
            },
        }
    return {
        "operating_points": points,
        "fixed_0.1_not_comparable": {
            scope: cohort(m, labels, outputs, cids, 0.1)
            for scope, cids in (
                ("all", list(outputs)),
                ("train", split["train"]),
                ("held", split["held_out"]),
            )
        },
        "held_curve_diagnostic_only": diagnostic_curve(
            m, outputs, labels, split["held_out"]
        ),
    }
