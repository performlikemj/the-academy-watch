#!/usr/bin/env python3
"""Reproduce the E1b comparison from immutable reports, raw claims and truth metadata."""

from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path

HEADLINE = (
    "On these 20 clips no lane — sampled stills at 5 s, sampled stills at production's "
    "30 s, or native video at 2/4 fps — ever grounded the player on a frame without "
    "the red rectangle; every supported claim is a box at the anchor time plus a "
    "presence sentence."
)
VERDICT = "no clear winner on the headline (unboxed grounding is 0 in every lane); frames on cost"
COLORS = "red|blue|black|white|yellow|green|orange|purple|pink|grey|gray"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def mean(values: list) -> float | None:
    return round(statistics.mean(values), 3) if values else None


def raw_claims(raw: dict) -> list[dict]:
    """Include assertions in mechanically failed outputs as well as scored ones."""
    try:
        payload = json.loads(raw.get("claims_raw", ""))
    except (TypeError, ValueError):
        return raw.get("claims", [])
    if isinstance(payload, dict) and isinstance(payload.get("claims"), list):
        return [c for c in payload["claims"] if isinstance(c, dict)]
    return raw.get("claims", [])


def claim_text(claim: dict) -> str:
    value = claim.get("claim")
    return value if isinstance(value, str) else ""


def jersey_review(raw: dict, truth: dict) -> dict:
    supplied = truth.get("jersey_number")
    color = truth.get("kit_color")
    claims = []
    malformed_text_count = 0
    for claim in raw_claims(raw):
        invalid_text = not isinstance(claim.get("claim"), str)
        malformed_text_count += invalid_text
        text = claim_text(claim)
        mentions = []
        for match in re.finditer(
            r"#\s*(\d+)\b|\bnumber\s+(\d+)\b|\b(?:jersey|shirt|kit)\s+(\d+)\b",
            text,
            re.I,
        ):
            number = int(next(g for g in match.groups() if g is not None))
            before = text[max(0, match.start() - 100) : match.start()]
            after = text[match.end() : match.end() + 30]
            kit_detail = bool(
                re.search(
                    r"(?:jersey|shirt|kit)\s*(?:(?:with\s+)?(?:the\s+)?)$", before, re.I
                )
                or re.match(r"\s+on (?:his|the player's) back", after, re.I)
                or match.group(3)
            )
            mentions.append(
                {
                    "text": match.group(),
                    "number": number,
                    "matches_supplied": None
                    if supplied is None
                    else number == supplied,
                    "asserted_as_kit_detail": kit_detail,
                }
            )
        colors = []
        patterns = [
            rf"\b({COLORS})\s+(?:jersey|shirt|kit|top)\b",
            rf"\b(?:player in|wearing)\s+(?:a\s+)?({COLORS})\b(?!\s+rectangle)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.I):
                value = match.group(1).lower().replace("gray", "grey")
                if value not in colors:
                    colors.append(value)
        vague_colors = re.findall(r"\b(dark|light)\s+clothing\b", text, re.I)
        claims.append(
            {
                "claim": text,
                **(
                    {"malformed": True, "malformed_fields": ["claim"]}
                    if invalid_text
                    else {}
                ),
                "vague_clothing_descriptions": [
                    f"{c.lower()} clothing" for c in vague_colors
                ],
                "jersey_mentions": mentions,
                "kit_colours_mentioned": colors,
                "kit_colour_check": (
                    "unconfirmed: vague clothing description"
                    if vague_colors
                    else "not mentioned"
                )
                if not colors
                else (
                    "truth unavailable"
                    if color is None
                    else "match"
                    if all(c == color.lower().replace("gray", "grey") for c in colors)
                    else "mismatch"
                ),
            }
        )
    unsupplied = [
        m["number"]
        for c in claims
        for m in c["jersey_mentions"]
        if m["matches_supplied"] is False
    ]
    return {
        "adapter_error": raw.get("error"),
        "supplied_jersey_number": supplied,
        "truth_kit_colour": color,
        "claims": claims,
        "malformed_claim_text_count": malformed_text_count,
        "non_jersey_numbers": sorted(
            {
                m["number"]
                for c in claims
                for m in c["jersey_mentions"]
                if not m["asserted_as_kit_detail"]
            }
        ),
        "unsupplied_numbers": sorted(set(unsupplied)),
        "supplied_number_asserted_as_kit_detail": any(
            m["asserted_as_kit_detail"] and m["matches_supplied"] is True
            for c in claims
            for m in c["jersey_mentions"]
        ),
        "invented_jersey_number_kill": any(
            m["matches_supplied"] is False and m["asserted_as_kit_detail"]
            for c in claims
            for m in c["jersey_mentions"]
        ),
        "kit_colour_mismatch": any(c["kit_colour_check"] == "mismatch" for c in claims),
    }


def sent_frames(raw: dict) -> list[dict]:
    # The legacy Ollama adapter records extracted frames even when anchoring fails
    # before its HTTP call. These frames were never sent to inference.
    if "truth box is unavailable" in (raw.get("error") or ""):
        return []
    return raw.get("sent_frames", [])


def anchor_only_attempt(raw: dict) -> bool:
    """Count actual sent stills all at the sole anchor, never nearby video frames."""
    frames = sent_frames(raw)
    anchors = raw.get("anchored_frames", [])
    return bool(
        frames
        and len(anchors) == 1
        and all(abs(float(f["t"]) - float(anchors[0]["t"])) < 0.001 for f in frames)
    )


def claim_evidence(scored: dict, raw: dict) -> dict:
    keys = (
        "claim",
        "box_t",
        "supported",
        "boxed_frame",
        "malformed",
        "malformed_fields",
        "time_grounded",
        "box_grounded",
        "iou",
        "claim_box_containment",
    )
    return {
        "status": scored["status"],
        "error": scored.get("error"),
        "claims": [
            {k: c[k] for k in keys if k in c}
            for c in (scored.get("claims") or raw.get("claims", []))
        ],
        "raw_claim_texts": [claim_text(c) for c in raw_claims(raw)],
    }


def experiment_caveats(lanes: dict, reviews: dict) -> list[str]:
    """Apparatus notes for the frozen E1b experiment, plus derived identity review."""
    notes = [
        "Policies: 5s/≤6 stills versus production 30s/≤3 stills, versus dense full-clip video; short production windows receive just the anchor. All use a truth-aware first sample, not production's full upstream scheduling/identity pipeline.",
        "MLX adds a separately marked image while its raw video begins at 0s; still anchors usually begin at 0.05s. The unchanged ±0.5s boxed-frame rule counts nearby unlabelled video frames as boxed. No supported unboxed claim is hidden by the headline denominator: N/A means none was attempted.",
        "MLX video resolution falls as frame count rises under a fixed pixel budget: the 73s clip at 4fps has 292 frames at 384×192, versus 1280×720 stills. The separate anchor is excluded from video-frame counts; means include pre-inference failures as zero sent frames.",
        "",  # Filled from immutable launch metadata below.
        "MLX uses native temporal patch grids but its installed Qwen processor omits HF per-pair timestamp tokens; decoder timestamps are supplied in text. This is not full HF timestamp-token parity.",
        "Ollama GGUF Q4_K_M and MLX's separately converted 4-bit weights, preprocessing, repetition handling and JSON enforcement differ. MLX uses prompt-only JSON instructions and the same strict parser; invalid responses remain failed.",
        "MLX starts a fresh worker/model per clip; Ollama reuses a model server and the 5s smoke warmed one prompt. Sequential single passes have no repeated trials or machine-workload isolation; prod30 ran later after the GPU gate opened.",
        "Rates exclude failed clips; wall and sent-frame means include every attempt. Hollow/malformed=0 among scored claims does not erase failed outputs. Full metrics, available token counts, failures and claim-level jersey/colour review are in JSON.",
        "Shared anchor lookup fails for m04-n02-t3005-474114-478131 before inference; historical E1 instead counted it unsupported. Frozen truth is unchanged and no human_note is populated, so action semantics are ungraded.",
        "",  # Filled from the complete claim-text review below.
        "Historical MLX runs used ignored report/.worker-deps via PYTHONPATH (preserved in their original run metadata); Jinja2 3.1.6/MarkupSafe 3.0.3 are now installed in the MLX venv. Earlier failed smokes were missing Jinja2 and fenced JSON; no video rerun was requested for this repair.",
    ]
    # Review findings are derived from all emitted claims, including failed clips.
    kits, mismatches = [], []
    invented = False
    for name, clips in reviews.items():
        numbers = sorted(
            {
                m["number"]
                for r in clips.values()
                for c in r["claims"]
                for m in c["jersey_mentions"]
                if m["asserted_as_kit_detail"] and m["matches_supplied"] is True
            }
        )
        kits.append(f"{name}: {numbers}")
        invented = invented or any(
            r["invented_jersey_number_kill"] for r in clips.values()
        )
        for cid, review in clips.items():
            for claim in review["claims"]:
                if claim["kit_colour_check"] == "mismatch":
                    mismatches.append(
                        f"{name} {cid}: {', '.join(claim['kit_colours_mentioned'])} vs truth {review['truth_kit_colour']}"
                    )
    notes[-2] = (
        "Supplied numbers restated as kit detail — "
        + "; ".join(kits)
        + (
            "; unsupplied numbers observed (see JSON)."
            if invented
            else "; no unsupplied numbers observed."
        )
        + " Kit-colour mismatches: "
        + ("; ".join(mismatches) or "none")
        + ". Geometry scoring does not penalize colour errors or establish number legibility."
    )
    fps2, fps4 = lanes["video_fps2"], lanes["video_fps4"]
    cap2 = fps2["settings"].get("wall_cap_s", "absent")
    cap4 = fps4["settings"].get("wall_cap_s", "absent")
    largest = max(fps2["max_wall_s"], fps4["max_wall_s"])
    notes[3] = (
        f"fps2 run.json wall_cap_s={cap2}; fps4 wall_cap_s={cap4}. Different launch flags; largest video wall time {largest}s. "
        + (
            "No behavioural effect: every clip finished below the 120s cap."
            if largest <= 120
            else "See early-stop metadata for cap effects."
        )
    )
    return notes


def paired_flips(
    control_name: str,
    compared_name: str,
    reports: dict,
    raw_runs: dict,
    selected_ids: list[str] | None = None,
) -> list[dict]:
    control = {c["clip_id"]: c for c in reports[control_name]["clips"]}
    compared = {c["clip_id"]: c for c in reports[compared_name]["clips"]}
    clip_ids = (
        selected_ids
        if selected_ids is not None
        else list(dict.fromkeys([*control, *compared]))
    )
    not_attempted = {"status": "not_attempted", "claims": []}
    rows = []
    for cid in clip_ids:
        first = control.get(cid, not_attempted)
        other = compared.get(cid, not_attempted)
        missing = "not_attempted" in (first["status"], other["status"])
        a = any(c.get("supported") for c in first.get("claims", []))
        b = any(c.get("supported") for c in other.get("claims", []))
        if missing or a != b or first["status"] != other["status"]:
            rows.append(
                {
                    "clip_id": cid,
                    "winner": None
                    if missing
                    else compared_name
                    if b and not a
                    else control_name
                    if a and not b
                    else None,
                    "kind": "not_attempted"
                    if missing
                    else "supported_clip"
                    if a != b
                    else "availability_only",
                    "control": claim_evidence(
                        first, raw_runs[control_name].get(cid, {})
                    ),
                    "compared": claim_evidence(
                        other, raw_runs[compared_name].get(cid, {})
                    ),
                }
            )
    return rows


def compare(
    reports_root: Path, runs: dict[str, str], manifest_path: Path | None = None
) -> dict:
    if len(runs) < 2:
        raise ValueError("comparison requires at least two runs")
    manifest = read_json(manifest_path) if manifest_path else {}
    truths = {
        c["clip_id"]: read_json(manifest_path.parent / c["truth"])
        for c in manifest.get("clips", [])
    }
    lanes, reports, raw_runs, reviews = {}, {}, {}, {}
    frozen_id, selected = None, None
    incomplete = {}
    for name, directory in runs.items():
        path = reports_root / directory
        report, config = read_json(path / "report.json"), read_json(path / "run.json")
        if frozen_id is None:
            frozen_id, selected = config["frozen_set_id"], config["clips"]
        if config["frozen_set_id"] != frozen_id or config["clips"] != selected:
            raise ValueError("runs must use the same frozen set and selected clips")
        if manifest and manifest["frozen_set_id"] != frozen_id:
            raise ValueError("truth manifest does not match runs")
        raw = {
            cid: read_json(path / "claims" / f"{cid}.json")
            for cid in selected
            if (path / "claims" / f"{cid}.json").exists()
        }
        # The scored report is authoritative for comparison coverage; a failed
        # entry is attempted, whereas leftover raw files cannot fill a report gap.
        covered = {
            c["clip_id"] for c in report["clips"] if c["status"] != "not_attempted"
        }
        missing = [cid for cid in selected if cid not in covered]
        stop_markers = {
            f"{source}.{key}": payload[key]
            for source, payload in (("run", config), ("report", report))
            for key in ("stopped_early", "wall_cap_exceeded")
            if key in payload and payload[key] is not None and payload[key] is not False
        }
        if missing or stop_markers:
            incomplete[name] = {
                "missing_clip_ids": missing,
                "stop_markers": stop_markers,
            }
        reports[name], raw_runs[name] = report, raw
        reviews[name] = {
            cid: jersey_review(raw.get(cid, {}), truths.get(cid, {}))
            for cid in selected
        }
        metrics = report["overall"]
        values = list(raw.values())
        sizes = sorted(
            {(f["sent_w"], f["sent_h"]) for c in values for f in sent_frames(c)},
            key=lambda s: (s[0] * s[1], s),
        )
        tokens = {}
        for key in ("prompt_tokens", "generation_tokens"):
            available = [c[key] for c in values if c.get(key) is not None]
            tokens[key] = {
                "available_clips": len(available),
                "total": sum(available) if available else None,
                "mean": mean(available),
            }
        max_wall = max((c["wall_s"] for c in values), default=None)
        lanes[name] = {
            "run": directory,
            "model": config["model"],
            "adapter": config["adapter"],
            "settings": config,
            "metrics": metrics,
            "fps": config.get("fps"),
            "attempted_clips": len(values),
            "anchor_only_attempts": sum(anchor_only_attempt(c) for c in values),
            "clips_with_any_supported_claim": sum(
                any(c.get("supported") for c in row.get("claims", []))
                for row in report["clips"]
            ),
            "sent_frames_per_clip": mean([len(sent_frames(c)) for c in values]),
            "recorded_sent_frames_per_clip": mean(
                [len(c.get("sent_frames", [])) for c in values]
            ),
            "sent_frames_mean_denominator": "all attempted clips; pre-inference anchor failures count zero; separate MLX anchor excluded",
            "sent_sizes": sizes,
            "sent_resolution_min": sizes[0] if sizes else None,
            "sent_resolution_max": sizes[-1] if sizes else None,
            "tokens": tokens,
            "max_wall_s": max_wall,
            "stopped_early": report.get("stopped_early"),
            "failures": [
                {"clip_id": cid, "error": c["error"], "claims_raw": c.get("claims_raw")}
                for cid, c in raw.items()
                if c.get("error")
            ],
            "thresholds": {
                "unsupported_le_10_percent": metrics.get("unsupported_rate") is not None
                and metrics["unsupported_rate"] <= 0.1,
                "supported_ge_2x_historical_baseline_zero": metrics.get(
                    "supported_rate"
                )
                is not None
                and metrics["supported_rate"] >= 0,
                "hollow_lt_5_percent": metrics.get("hollow_rate") is not None
                and metrics["hollow_rate"] < 0.05,
                "every_attempt_le_120s": max_wall is not None and max_wall <= 120,
                "kill_unsupported_gt_25_percent": metrics.get("unsupported_rate")
                is not None
                and metrics["unsupported_rate"] > 0.25,
                "invented_jersey_number_kill": any(
                    c["invented_jersey_number_kill"] for c in reviews[name].values()
                ),
            },
        }
    control_name = next(iter(runs))
    flips = {
        name: paired_flips(control_name, name, reports, raw_runs, selected)
        for name in list(runs)[1:]
    }
    production_flips = {
        name: paired_flips("frames_prod30", name, reports, raw_runs, selected)
        for name, lane in lanes.items()
        if "frames_prod30" in lanes and lane["adapter"] == "qwen3vl_mlx"
    }
    grounded_unboxed = sum(
        c.get("supported", False) and not c.get("boxed_frame", False)
        for r in reports.values()
        for row in r["clips"]
        for c in row.get("claims", [])
    )
    historical_shape = (
        not incomplete
        and set(runs) == {"frames", "frames_prod30", "video_fps2", "video_fps4"}
        and len(selected) == 20
        and frozen_id
        == "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f"
    )
    headline = (
        "INCOMPLETE COMPARISON — some selected clips were not attempted or a stop marker is present."
        if incomplete
        else HEADLINE
        if historical_shape and grounded_unboxed == 0
        else f"Across these runs, {grounded_unboxed} claims grounded the player on an unboxed frame."
    )
    return {
        "experiment": "E1b — Qwen3-VL native-video versus sampled-frame grounded-claim bench",
        "date": min(r["generated_at"][:10] for r in reports.values()),
        "frozen_set": f"{len(selected)} evaluation-only clips (frozen_set_id {frozen_id})",
        "basecamp": "Apple silicon Mac, 128 GB; Ollama 0.33.2, num_ctx=65536; mlx-vlm 0.6.17; Python 3.12.14 worker, Python 3.11.16 bench",
        "worker_dependencies": {
            "Jinja2": "3.1.6",
            "MarkupSafe": "3.0.3",
            "location": "installed in MLX venv via requirements-worker.txt; historical video runs used report/.worker-deps",
        },
        **({"incomplete_lanes": incomplete} if incomplete else {}),
        "lane_order": list(runs),
        **lanes,
        "per_clip_flips": flips,
        "per_clip_flips_vs_production": production_flips,
        "jersey_review": reviews,
        "jersey_review_method": "All emitted claim texts, including contract failures; explicit #N/number N/jersey N and jersey/shirt/kit colour assertions checked against truth metadata. Supplied numbers are not proof of visual legibility; action semantics are ungraded.",
        "caveats": experiment_caveats(lanes, reviews)
        if historical_shape
        else [
            "Rates exclude failed clips; wall/frame means include every attempt. Supplied jersey numbers are not proof of visual legibility.",
            "Jersey/kit checks require the optional matching frozen truth manifest; without it comparisons are marked unavailable.",
        ],
        "headline": headline,
        "verdict": "incomplete comparison; verdict withheld"
        if incomplete
        else VERDICT
        if historical_shape and grounded_unboxed == 0
        else "no clear winner",
        "verdict_evidence": "; ".join(
            f"{n}: {v['clips_with_any_supported_claim']}/{v['attempted_clips']} supported clips, {v['metrics']['wall_s_per_clip']}s/attempt"
            for n, v in lanes.items()
        )
        + ".",
    }


def percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2%}"


def evidence_summary(evidence: dict) -> str:
    if evidence["status"] == "not_attempted":
        return "not_attempted (no scored report entry)"
    text = " / ".join(evidence["raw_claim_texts"]) or "(no claims)"
    if evidence["status"] != "scored":
        fields = sorted(
            {
                field
                for c in evidence["claims"]
                for field in c.get("malformed_fields", [])
            }
        )
        detail = f"; contract: {', '.join(fields)}" if fields else ""
        return f"“{text}” → failed ({evidence['error']}{detail})"
    reasons = []
    for c in evidence["claims"]:
        reasons.append(
            f"{'supported' if c.get('supported') else 'unsupported'} {'anchor' if c.get('boxed_frame') else 'unboxed'} box at {c.get('box_t')} (containment {c.get('claim_box_containment')}, IoU {c.get('iou')})"
        )
    return f"“{text}” → " + ", ".join(reasons)


def markdown(result: dict) -> str:
    names = result["lane_order"]
    incomplete_lines = []
    if result.get("incomplete_lanes"):
        incomplete_lines = ["", "Missing selected clips / stop markers by lane:", ""]
        for name in names:
            details = result["incomplete_lanes"].get(name, {})
            missing = ", ".join(details.get("missing_clip_ids", [])) or "none"
            markers = json.dumps(details.get("stop_markers", {}), sort_keys=True)
            incomplete_lines.append(
                f"- {name}: missing clip IDs: {missing}; stop markers: {markers}."
            )
        incomplete_lines.append("")
    lines = [
        result["headline"],
        *incomplete_lines,
        f"E1b comparison, {result['date']}. {result['frozen_set']}.",
        "",
        "| Lane | Scored / failed | Supported | Unboxed supported | Unsupported | Hollow | Wall s/clip | Stills/video frames per attempt | Sent resolution (min–max WxH) | Anchor-only attempts |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for name in names:
        lane = result[name]
        m = lane["metrics"]
        sizes = [
            "×".join(map(str, lane[k])) if lane[k] else "N/A"
            for k in ("sent_resolution_min", "sent_resolution_max")
        ]
        lines.append(
            f"| {name} | {m['scored_clips']} / {m['failed_clips']} | {percent(m['supported_rate'])} | {percent(m['supported_rate_unboxed'])} ({m['unboxed_claim_count']} claims) | {percent(m['unsupported_rate'])} | {percent(m['hollow_rate'])} | {m['wall_s_per_clip']} | {lane['sent_frames_per_clip']} | {'–'.join(sizes)} | {lane['anchor_only_attempts']}/{lane['attempted_clips']} |"
        )
    if "frames_prod30" in names and result["headline"] == HEADLINE:
        lines += [
            "",
            "Prod30's 84% supported rate is single-still anchor echo, not grounding.",
        ]
    lines += [
        "",
        "E1 thresholds per lane (≥2× a zero-box baseline is vacuous, not evidence of improvement):",
        "",
    ]
    for name in names:
        t = result[name]["thresholds"]

        def status(key):
            return "PASS" if t[key] else "FAIL"

        lines.append(
            f"- {name}: unsupported ≤10% {status('unsupported_le_10_percent')}; ≥2× zero baseline {status('supported_ge_2x_historical_baseline_zero')}; hollow <5% {status('hollow_lt_5_percent')}; every attempt ≤120s {status('every_attempt_le_120s')} (max {result[name]['max_wall_s']}s); >25% unsupported kill {'yes' if t['kill_unsupported_gt_25_percent'] else 'no'}; invented-number kill {'yes' if t['invented_jersey_number_kill'] else 'no'}."
        )
    lines += [
        "",
        f"Per-clip changes versus {names[0]} (all other supported/status outcomes match; action meaning is not scored):",
        "",
    ]
    for name, rows in result["per_clip_flips"].items():
        for row in rows:
            lines.append(
                f"- {name} `{row['clip_id']}`: {row['winner'] or 'availability only'}; control {evidence_summary(row['control'])}; compared {evidence_summary(row['compared'])}."
            )
    if result["per_clip_flips_vs_production"]:
        lines += [
            "",
            "Video versus production 30s control (shared-control explanations above; full paired claim/box records in JSON):",
            "",
        ]
        for name, rows in result["per_clip_flips_vs_production"].items():
            wins = [r["clip_id"] for r in rows if r["winner"] == name]
            losses = [r["clip_id"] for r in rows if r["winner"] == "frames_prod30"]
            availability = [r["clip_id"] for r in rows if r["winner"] is None]
            lines.append(
                f"- {name}: gains {', '.join(wins) or 'none'}; loses {', '.join(losses) or 'none'}; availability-only changes {', '.join(availability) or 'none'}."
            )
    lines += ["", "Like-for-like caveats:", ""]
    lines += [f"- {note}" for note in result["caveats"]]
    lines += ["", f"Verdict: **{result['verdict']}** — {result['verdict_evidence']}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-root", type=Path, required=True)
    parser.add_argument("--runs", nargs="+", required=True, metavar="NAME=DIR")
    parser.add_argument(
        "--manifest", type=Path, help="frozen truth metadata for jersey/kit review"
    )
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args(argv)
    runs = {}
    for entry in args.runs:
        name, separator, directory = entry.partition("=")
        if not separator or not name or not directory or name in runs:
            parser.error("--runs entries must be unique NAME=DIR pairs")
        runs[name] = directory
    result = compare(args.reports_root, runs, args.manifest)
    args.out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    args.out_md.write_text(markdown(result))
    print(f"Wrote comparison for {len(runs)} lanes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
