"""Counterfactual n21 rules from saved boxes; never edits human labels."""

from output_guard import guard_outputs
from pathlib import Path
import gzip
import json
import math
from common import HERE, dump, sha256

CID = "m04-n21-t3011-390297-390800"
DEFINITIONS = {
    "yolo-r2-b": "r5-yolo-low",
    "rf-b": "r5-rfb-low",
    "rf-r5-a": "r5-rf-a-final-low",
    "rf-r5-b": "r5-rf-b-final-low",
}
PENDING = "one MJ decision covering n21 s0-s10: count any visible ball, or the match ball only; the current labels follow neither rule consistently"


def top_hit(detections, label, threshold):
    top = max(
        (d for d in detections if d["confidence"] >= threshold),
        key=lambda d: d["confidence"],
        default=None,
    )
    return bool(top and math.dist(top["xy"], label) <= 20)


def main():
    guard_outputs(HERE / "fixtures/n21_rule_sensitivity.json")
    root = Path.home() / "models/tinyball"
    label_path = Path.home() / "codex-runs/ball-human-truth.jsonl"
    e = json.loads(
        gzip.decompress((HERE / "fixtures/round5_scored_output.json.gz").read_bytes())
    )
    assert sha256(label_path) == e["labels_sha256"]
    labels = {
        (r["clip"], r["t"]): r
        for r in map(json.loads, label_path.read_text().splitlines())
    }
    held = set(e["protocol"]["split"]["held_out"])
    outputs = {}
    for name, folder in DEFINITIONS.items():
        path = root / folder / "detections.json"
        assert sha256(path) == e["models"][name]["detections_sha256"]
        payload = json.loads(path.read_text())
        assert payload["threshold"] == 0.01
        outputs[name] = payload["outputs"]
    n21 = {r["sample_index"]: r for r in outputs["rf-b"][CID]["frames"]}
    # Existing saved RF b boxes visually inspected in the source crops, not new human clicks.
    refs = {i: n21[i]["detections"][j]["xy"] for i, j in ((8, 0), (9, 0), (10, 1))}
    first = [labels[(CID, n21[i]["t"])] for i in range(6)]
    assert all(r["visible"] for r in first)
    assert all(not labels[(CID, n21[i]["t"])]["visible"] for i in range(6, 11))
    rows = []
    for name, outs in outputs.items():
        for budget, op in e["models"][name]["operating_points"].items():
            threshold = op["threshold"]
            hits = visible = false = no_ball = removed_hits = added_false = any_hits = (
                credits
            ) = nearby_nonball_hits = 0
            for cid, clip in outs.items():
                if cid not in held:
                    continue
                for frame in clip["frames"]:
                    label = labels.get((cid, frame["t"]))
                    if label is None:
                        continue
                    ds = [
                        d for d in frame["detections"] if d["confidence"] >= threshold
                    ]
                    if label["visible"]:
                        visible += 1
                        hit = top_hit(ds, [label["x"], label["y"]], threshold)
                        hits += hit
                        if cid == CID and frame["sample_index"] < 6:
                            removed_hits += hit
                            added_false += len(ds)
                    else:
                        no_ball += 1
                        false += len(ds)
                        if cid == CID and frame["sample_index"] in refs:
                            ref = refs[frame["sample_index"]]
                            credits += sum(math.dist(d["xy"], ref) <= 2 for d in ds)
                            hit = top_hit(ds, ref, threshold)
                            any_hits += hit
                            if hit:
                                top = max(ds, key=lambda d: d["confidence"])
                                nearby_nonball_hits += math.dist(top["xy"], ref) > 2
            current = op["held"]["groups"]["all"]
            assert (hits, visible, false, no_ball) == (
                current["top1_matched"],
                current["visible"],
                current["no_ball_predictions"],
                current["no_ball_frames"],
            )
            rules = {
                "as_labelled": {
                    "false_boxes": false,
                    "false_exposure_frames": no_ball,
                    "visible": visible,
                    "top1_hits": hits,
                },
                "any_visible_ball": {
                    "false_boxes": false - credits,
                    "false_exposure_frames": no_ball,
                    "visible": visible + 3,
                    "top1_hits": hits + any_hits,
                },
                "match_ball_only": {
                    "false_boxes": false + added_false,
                    "false_exposure_frames": no_ball + 6,
                    "visible": visible - 6,
                    "top1_hits": hits - removed_hits,
                },
            }
            for r in rules.values():
                r["false_per_10s"] = 20 * r["false_boxes"] / r["false_exposure_frames"]
                r["overall_top1_recall"] = r["top1_hits"] / r["visible"]
            rows.append(
                {
                    "model": name,
                    "train_budget": budget,
                    "threshold": threshold,
                    "rules": rules,
                    "s0_s5_retained_boxes": added_false,
                    "s0_s5_hits_removed": removed_hits,
                    "s8_s10_visible_ball_boxes_credited": credits,
                    "s8_s10_provisional_top1_hits": any_hits,
                    "s8_s10_nearby_footwear_top1_within20px": nearby_nonball_hits,
                    "on_ball_recall_unchanged": op["held"]["groups"]["on_ball"][
                        "top1_recall"
                    ],
                }
            )
    for row in rows:
        base = next(
            r
            for r in rows
            if r["model"] == "yolo-r2-b" and r["train_budget"] == row["train_budget"]
        )
        for rule, r in row["rules"].items():
            b = base["rules"][rule]
            r["false_delta_vs_yolo"] = r["false_per_10s"] - b["false_per_10s"]
            r["recall_delta_pp_vs_yolo"] = 100 * (
                r["overall_top1_recall"] - b["overall_top1_recall"]
            )

            def direction(delta):
                return "higher" if delta > 0 else "lower" if delta < 0 else "same"

            r["direction_vs_yolo"] = {
                "false": direction(r["false_delta_vs_yolo"]),
                "recall": direction(r["recall_delta_pp_vs_yolo"]),
            }
    result = {
        "pending": PENDING,
        "scorer_class": "off_pitch",
        "labels_sha256": sha256(label_path),
        "detections_sha256": {n: e["models"][n]["detections_sha256"] for n in outputs},
        "rows": rows,
        "reviewer_flagged_spot_distances_px": [86, 142, 164, 158, 118, 77],
        "old_rf_box_centre_distances_px": [
            math.dist([r["x"], r["y"]], refs[8]) for r in first
        ],
        "s0_s5_label_sources": [
            r.get("accepted_source") if r["source_accepted"] else "manual"
            for r in first
        ],
        "definition": "Counterfactuals only; labels, TRAIN thresholds, gate and selection unchanged. As-labelled uses244 visible /60 no-ball frames. Match-ball-only removes the six visible background-ball labels (238 visible), counts all their retained boxes false and expands the no-ball denominator to66. Any-visible-ball false rate preserves the prior credit-only sensitivity: subtract visually identified ball boxes on s8–s10 and retain the original60-frame exposure; it is not a fully relabelled no-ball-frame rate. For any-visible-ball overall top-1 recall only, add s8–s10 as three provisional visible references (247 total), using source-inspected old RF b box centres and the unchanged20px rule, not MJ-confirmed new clicks. s6 remains no-ball; s7 is unresolved and unchanged. At s10 a higher-confidence footwear box lies within20px of the ball, so the requested geometric metric can count it as a provisional hit even though only the actual ball box receives a false-box credit. These proxy recall numbers require MJ adjudication, and must not be used as new ground truth.",
    }
    dump(HERE / "fixtures/n21_rule_sensitivity.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
