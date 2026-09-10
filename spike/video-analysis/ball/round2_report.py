"""Corrected standalone round-2 view; historical selection is explicitly preserved."""

from __future__ import annotations
from round3_report import f, headline, pair


def markdown(data):
    protocol = data["round2"]
    evidence = protocol["measurements"]
    results = evidence["results"]
    lines = [
        "Human gate uses top-1 on-ball recall ≥80% AND ≤1 no-ball detection/10s. Proxy verdicts retire.",
        "",
        "H = "
        + protocol["evaluation_label"]
        + "; the same six clips for every candidate. All = all 20 clips (incl. training clips). Headline training-model numbers are H-only; secondary columns expose training contamination.",
        "",
        "Round-2 historical model choice was d, selected by TRAIN loss before evaluation. This does not establish it as the best held-out model. The round-3 ledger supersedes that selection under its explicitly authorized evaluation-based rule.",
        "",
    ]
    lines += headline(results)
    lines += [
        "",
        "| Candidate | Overall top-1 All / H | Overall manual top-1 All / H | Overall oracle over N boxes All / H | Overall oracle precision All / H | False/frame All / H | Top-1 median px All / H |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        a, h = (r[s]["groups"]["all"] for s in ("all", "held"))
        lines.append(
            f"| {r['candidate']} | {pair(a['top1_recall'], h['top1_recall'], True)} | {pair(a['manual_top1_recall'], h['manual_top1_recall'], True)} | {pair(a['oracle_recall'], h['oracle_recall'], True)} | {pair(a['precision'], h['precision'], True)} | {a['false_per_frame']:.4f} / {h['false_per_frame']:.4f} | {pair(a['top1_error_px']['median'], h['top1_error_px']['median'])} |"
        )
    lines += [
        "",
        "| Candidate | Track coverage All / H | Track precision All / H | Longest s All / H | Wrong frames / points All / H | Wrong rate per point All / H |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        a, h = (r[s]["tracks"]["groups"]["all"] for s in ("all", "held"))
        lines.append(
            f"| {r['candidate']} | {pair(a['coverage'], h['coverage'], True)} | {pair(a['track_precision'], h['track_precision'], True)} | {pair(a['longest_correct_s'], h['longest_correct_s'])} | {a['wrong_object_frames']}/{a['track_points_on_visible_frames']} / {h['wrong_object_frames']}/{h['track_points_on_visible_frames']} | {pair(a['wrong_per_track_point'], h['wrong_per_track_point'], True)} |"
        )
    lines += [
        "",
        "Track precision and wrong-per-point denominators contain only track points where a visible label exists; coverage penalises silence. No-ball = no ball visible to the labeller, including potentially real detections that the labeller could not see. False/10s normalises 2fps no-ball exposure; it is not a continuous event count.",
        "",
        "Recorded fits (no evaluation metric in this table):",
        "",
        "| Fit | Input | MPS minutes | Recorded / best epoch | TRAIN loss |",
        "|---|---:|---:|---:|---:|",
    ]
    for letter, fit in evidence["selection"]["fits"].items():
        lines.append(
            f"| {letter} | {fit['model_input_px']} | {f(fit['training_s'] / 60)} | {fit['epochs_recorded']} / {fit['best_epoch']} | {fit['best_train_loss']:.5f} |"
        )
    lines += [
        "",
        "Exact splits, per-clip metrics, provenance, error buckets, historical oracle projection, fit/checkpoint hashes and execution decisions remain in JSON. The original r2-d oracle 2×-pixel projection was 60.7→66.4% H: better footage helps but is not a fix on its own. Fresh labelled club footage is the true test; these 20 clips are no longer a clean test set.",
        "",
    ]
    return "\n".join(lines)
