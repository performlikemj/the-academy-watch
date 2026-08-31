#!/usr/bin/env python3
"""Sample a match video and produce honest, jersey-number-only Qwen analysis."""

from __future__ import annotations

import argparse
import base64
import json
import logging
import math
import os
import shutil
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from game_time import in_play_plan

log = logging.getLogger("qwen_match_analysis")

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3.8:27b-obliterated-q8"
DEFAULT_SAMPLE_S = 30.0
DEFAULT_MAX_CALLS = 240
DEFAULT_TIMEOUT_S = 300.0
SCHEMA_VERSION = "qwen-analysis-v1"
PHASES = (
    "build-up",
    "attack",
    "defending",
    "transition",
    "set-piece",
    "stoppage",
    "unclear",
)

HONEST_LIMIT_TEMPLATES = (
    "Single-camera sampled-frame analysis.",
    "Players are identified by jersey number only.",
    "Observations are qualitative, not measured statistics.",
)


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _clean_number(value: float) -> int | float:
    rounded = round(float(value), 3)
    return int(rounded) if rounded.is_integer() else rounded


def build_in_play_windows(
    kickoff_s: float | None,
    halftime_s: float | None,
    second_half_kickoff_s: float | None,
    end_s: float | None,
    duration_s: float,
) -> list[tuple[float, float]]:
    """Turn ``in_play_plan`` into bounded, non-empty in-play windows."""
    if duration_s <= 0:
        raise ValueError("video duration must be positive")
    effective_end_s = end_s if end_s is not None else duration_s
    run_start, run_end, gap = in_play_plan(
        kickoff_s, halftime_s, second_half_kickoff_s, effective_end_s
    )
    start = max(0.0, float(run_start)) if run_start is not None else 0.0
    end = min(float(run_end), duration_s) if run_end is not None else duration_s
    if end <= start:
        raise ValueError(f"in-play window is empty ({start:g}s to {end:g}s)")
    if gap is None:
        return [(start, end)]
    gap_start = max(start, float(gap[0]))
    gap_end = min(end, float(gap[1]))
    if gap_start >= gap_end:
        return [(start, end)]
    return [(a, b) for a, b in ((start, gap_start), (gap_end, end)) if b > a]


def _timestamp_at_play_offset(
    windows: list[tuple[float, float]], offset_s: float
) -> float:
    remaining = offset_s
    for start, end in windows:
        length = end - start
        if remaining < length:
            return start + remaining
        remaining -= length
    return windows[-1][1]


def build_sampling_plan(
    kickoff_s: float | None,
    halftime_s: float | None,
    second_half_kickoff_s: float | None,
    end_s: float | None,
    duration_s: float,
    sample_s: float = DEFAULT_SAMPLE_S,
    max_calls: int = DEFAULT_MAX_CALLS,
) -> dict:
    """Build a full-window sampling plan, widening spacing to honor ``max_calls``."""
    if sample_s <= 0:
        raise ValueError("sample interval must be positive")
    if max_calls <= 0:
        raise ValueError("maximum calls must be positive")
    windows = build_in_play_windows(
        kickoff_s, halftime_s, second_half_kickoff_s, end_s, float(duration_s)
    )
    in_play_s = sum(end - start for start, end in windows)
    requested_count = max(1, math.ceil(in_play_s / sample_s))
    count = min(requested_count, max_calls)
    interval_s = (
        max(float(sample_s), in_play_s / count)
        if requested_count > max_calls
        else float(sample_s)
    )
    timestamps = [
        _timestamp_at_play_offset(windows, i * interval_s) for i in range(count)
    ]
    return {
        "interval_s": _clean_number(interval_s),
        "timestamps": [round(timestamp, 3) for timestamp in timestamps],
        "in_play_windows": [
            [_clean_number(start), _clean_number(end)] for start, end in windows
        ],
    }


def ffprobe_argv(ffprobe_path: str | Path, video_path: str | Path) -> list[str]:
    return [
        str(ffprobe_path),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]


def ffmpeg_argv(
    ffmpeg_path: str | Path,
    video_path: str | Path,
    timestamp_s: float,
    output_path: Path,
) -> list[str]:
    return [
        str(ffmpeg_path),
        "-y",
        "-v",
        "error",
        "-ss",
        str(_clean_number(timestamp_s)),
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "3",
        "-vf",
        "scale=1280:-2",
        str(output_path),
    ]


def build_sandbox_argv(
    profile_path: str | Path,
    out_dir: str | Path,
    video_dir: str | Path,
    ffmpeg_dir: str | Path,
    command: list[str],
    sandbox_exec: str | Path = "sandbox-exec",
) -> list[str]:
    """Wrap a media command in the static parameterized Seatbelt profile."""
    return [
        str(sandbox_exec),
        "-f",
        str(profile_path),
        "-D",
        f"OUT_DIR={Path(out_dir).resolve()}",
        "-D",
        f"VIDEO_DIR={Path(video_dir).resolve()}",
        "-D",
        f"FFMPEG_DIR={Path(ffmpeg_dir).resolve()}",
        "-D",
        f"EXECUTABLE={command[0]}",
        *command,
    ]


def _ffmpeg_tree(ffmpeg_path: Path, ffprobe_path: Path) -> Path:
    """Return the smallest practical common install tree containing Homebrew/MacPorts libs."""
    resolved = (ffmpeg_path.resolve(), ffprobe_path.resolve())
    for prefix in (Path("/opt/homebrew"), Path("/usr/local"), Path("/opt/local")):
        if all(path.is_relative_to(prefix) for path in resolved):
            return prefix
    return Path(os.path.commonpath([str(path.parent) for path in resolved]))


def _decode_env(out_dir: Path) -> dict[str, str]:
    """A credential-free environment for code processing attacker-supplied media."""
    return {
        "HOME": str(out_dir),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.defpath,
        "TMPDIR": str(out_dir),
    }


def _media_command(
    command: list[str],
    *,
    sandboxed: bool,
    sandbox_exec: Path | None,
    profile_path: Path,
    out_dir: Path,
    video_path: Path,
    ffmpeg_dir: Path,
) -> list[str]:
    if not sandboxed:
        return command
    if sandbox_exec is None:
        raise RuntimeError(
            "VIDEO_DECODE_SANDBOX=1 but sandbox-exec is unavailable; refusing unsandboxed decode"
        )
    return build_sandbox_argv(
        profile_path,
        out_dir,
        video_path.parent,
        ffmpeg_dir,
        command,
        sandbox_exec=sandbox_exec,
    )


def probe_duration(
    video_path: Path,
    out_dir: Path,
    ffprobe_path: Path,
    ffmpeg_dir: Path,
    profile_path: Path,
    sandboxed: bool,
    sandbox_exec: Path | None,
) -> float:
    command = _media_command(
        ffprobe_argv(ffprobe_path, video_path),
        sandboxed=sandboxed,
        sandbox_exec=sandbox_exec,
        profile_path=profile_path,
        out_dir=out_dir,
        video_path=video_path,
        ffmpeg_dir=ffmpeg_dir,
    )
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=_decode_env(out_dir),
        )
        duration = float(result.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        mode = "sandboxed " if sandboxed else ""
        raise RuntimeError(
            f"{mode}ffprobe failed; refusing to analyze unbounded footage: {exc}"
        ) from exc
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError(f"ffprobe returned invalid duration: {duration!r}")
    return duration


def extract_frame(
    video_path: Path,
    output_path: Path,
    timestamp_s: float,
    ffmpeg_path: Path,
    ffmpeg_dir: Path,
    profile_path: Path,
    sandboxed: bool,
    sandbox_exec: Path | None,
) -> None:
    command = _media_command(
        ffmpeg_argv(ffmpeg_path, video_path, timestamp_s, output_path),
        sandboxed=sandboxed,
        sandbox_exec=sandbox_exec,
        profile_path=profile_path,
        out_dir=output_path.parent.parent,
        video_path=video_path,
        ffmpeg_dir=ffmpeg_dir,
    )
    try:
        subprocess.run(command, check=True, env=_decode_env(output_path.parent.parent))
    except (OSError, subprocess.SubprocessError) as exc:
        mode = "sandboxed " if sandboxed else ""
        raise RuntimeError(
            f"{mode}ffmpeg frame extraction failed at {timestamp_s:g}s: {exc}"
        ) from exc


def build_observation_prompt(timestamp_s: float) -> str:
    return f"""Analyze this single football-match frame at {timestamp_s:.3f} seconds.
Return one JSON object only, with this shape:
{{"teams":[{{"kit_color":str,"visible_players":int,"readable_jersey_numbers":[int]}}],
 "ball_visible":bool,"phase_of_play":"build-up|attack|defending|transition|set-piece|stoppage|unclear",
 "observation":str,"notable_actions":[str]}}
Use kit colors and CLEARLY readable jersey numbers only. Never infer a number from an unclear shirt and never
identify or guess a player name. Empty jersey-number lists are correct when no number is clear. Count only visible
players. Keep the observation to one sentence and describe only evidence visible in this frame."""


def build_aggregation_prompt(
    observations: list[dict], context: dict | None = None
) -> str:
    context_json = json.dumps(context or {}, separators=(",", ":"), ensure_ascii=False)
    observations_json = json.dumps(
        observations, separators=(",", ":"), ensure_ascii=False
    )
    return f"""Aggregate these sampled football-frame observations into one honest match analysis JSON object.
Optional match context: {context_json}
Timestamped observations: {observations_json}

Return exactly this shape:
{{"schema_version":"qwen-analysis-v1","model":str,"generated_at":str,
"sampling":{{"interval_s":number,"frames_analyzed":int,"frames_failed":int,
"in_play_windows":[[number,number]]}},"match_summary":str,
"team_analysis":[{{"kit_color":str,"is_ours":bool|null,"style":str,"strengths":[str],
"weaknesses":[str],"shape_notes":str}}],
"player_notes":[{{"kit_color":str,"jersey_number":int,"observations":[str],"times_seen":int,
"confidence":"low|medium"}}],"honest_limits":[str]}}
Use no player names. A player may appear only when that jersey number was explicitly readable in the supplied
frame observations. Do not invent events, players, statistics, formations, or certainty. Distinguish the uploader's
side only when the supplied kit-color context supports it. Empty player_notes is valid."""


def ollama_chat(
    prompt: str,
    *,
    ollama_url: str,
    model: str,
    timeout_s: float,
    image_path: Path | None = None,
) -> str:
    """Make the one permitted network call shape, using only urllib."""
    message: dict[str, object] = {"role": "user", "content": prompt}
    if image_path is not None:
        message["images"] = [base64.b64encode(image_path.read_bytes()).decode("ascii")]
    body = {
        "model": model,
        "think": False,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [message],
    }
    request = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        payload = json.loads(response.read().decode("utf-8"))
    content = payload.get("message", {}).get("content")
    if not isinstance(content, str):
        raise ValueError("ollama response is missing message.content")
    return content


def parse_observation(content: str) -> dict:
    observation = json.loads(content)
    validate_observation_schema(observation)
    return observation


def _is_str_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def validate_observation_schema(observation: object) -> None:
    """Reject parsed frame rows that cannot provide trustworthy aggregation evidence."""
    if not isinstance(observation, dict):
        raise ValueError("frame observation must be a JSON object")
    required = {
        "teams",
        "ball_visible",
        "phase_of_play",
        "observation",
        "notable_actions",
    }
    missing = required - observation.keys()
    if missing:
        raise ValueError(
            f"frame observation is missing required keys: {', '.join(sorted(missing))}"
        )
    teams = observation["teams"]
    if not isinstance(teams, list):
        raise ValueError("frame observation.teams must be a list")
    for team in teams:
        if not isinstance(team, dict):
            raise ValueError("each frame observation team must be an object")
        if "kit_color" not in team or "readable_jersey_numbers" not in team:
            raise ValueError("frame observation team is missing required keys")
        if not isinstance(team["kit_color"], str):
            raise ValueError("frame observation team.kit_color must be a string")
        numbers = team["readable_jersey_numbers"]
        if not isinstance(numbers, list) or not all(
            isinstance(number, int) and not isinstance(number, bool)
            for number in numbers
        ):
            raise ValueError(
                "frame observation team.readable_jersey_numbers must be a list of integers"
            )
        if "visible_players" in team and (
            not isinstance(team["visible_players"], int)
            or isinstance(team["visible_players"], bool)
        ):
            raise ValueError(
                "frame observation team.visible_players must be an integer"
            )
    if not isinstance(observation["ball_visible"], bool):
        raise ValueError("frame observation.ball_visible must be a boolean")
    if not isinstance(observation["phase_of_play"], str):
        raise ValueError("frame observation.phase_of_play must be a string")
    if not isinstance(observation["observation"], str):
        raise ValueError("frame observation.observation must be a string")
    if not _is_str_list(observation["notable_actions"]):
        raise ValueError("frame observation.notable_actions must be a string list")


def validate_analysis_schema(analysis: object) -> None:
    """Raise ``ValueError`` unless all required qwen-analysis-v1 fields have valid types."""
    if not isinstance(analysis, dict):
        raise ValueError("analysis must be a JSON object")
    required = {
        "schema_version",
        "model",
        "generated_at",
        "sampling",
        "match_summary",
        "team_analysis",
        "player_notes",
        "honest_limits",
    }
    missing = required - analysis.keys()
    if missing:
        raise ValueError(
            f"analysis is missing required keys: {', '.join(sorted(missing))}"
        )
    for key in ("schema_version", "model", "generated_at", "match_summary"):
        if not isinstance(analysis[key], str):
            raise ValueError(f"{key} must be a string")
    sampling = analysis["sampling"]
    if not isinstance(sampling, dict):
        raise ValueError("sampling must be an object")
    for key in ("interval_s", "frames_analyzed", "frames_failed", "in_play_windows"):
        if key not in sampling:
            raise ValueError(f"sampling is missing {key}")
    if not _number(sampling["interval_s"]):
        raise ValueError("sampling.interval_s must be numeric")
    for key in ("frames_analyzed", "frames_failed"):
        if not isinstance(sampling[key], int) or isinstance(sampling[key], bool):
            raise ValueError(f"sampling.{key} must be an integer")
    windows = sampling["in_play_windows"]
    if not isinstance(windows, list) or not all(
        isinstance(window, list)
        and len(window) == 2
        and all(_number(bound) for bound in window)
        for window in windows
    ):
        raise ValueError(
            "sampling.in_play_windows must contain numeric [start, end] pairs"
        )
    if not isinstance(analysis["team_analysis"], list):
        raise ValueError("team_analysis must be a list")
    for team in analysis["team_analysis"]:
        if not isinstance(team, dict):
            raise ValueError("each team_analysis entry must be an object")
        if (
            set(
                (
                    "kit_color",
                    "is_ours",
                    "style",
                    "strengths",
                    "weaknesses",
                    "shape_notes",
                )
            )
            - team.keys()
        ):
            raise ValueError("team_analysis entry is missing required keys")
        if not all(
            isinstance(team[key], str) for key in ("kit_color", "style", "shape_notes")
        ):
            raise ValueError("team_analysis string fields must be strings")
        if team["is_ours"] is not None and not isinstance(team["is_ours"], bool):
            raise ValueError("team_analysis.is_ours must be boolean or null")
        if not _is_str_list(team["strengths"]) or not _is_str_list(team["weaknesses"]):
            raise ValueError("team strengths and weaknesses must be string lists")
    if not isinstance(analysis["player_notes"], list):
        raise ValueError("player_notes must be a list")
    for player in analysis["player_notes"]:
        if not isinstance(player, dict):
            raise ValueError("each player_note must be an object")
        if (
            set(
                (
                    "kit_color",
                    "jersey_number",
                    "observations",
                    "times_seen",
                    "confidence",
                )
            )
            - player.keys()
        ):
            raise ValueError("player_note is missing required keys")
        if not isinstance(player["kit_color"], str) or not _is_str_list(
            player["observations"]
        ):
            raise ValueError("player_note kit_color/observations have invalid types")
        if not isinstance(player["jersey_number"], int) or isinstance(
            player["jersey_number"], bool
        ):
            raise ValueError("player_note.jersey_number must be an integer")
        if not isinstance(player["times_seen"], int) or isinstance(
            player["times_seen"], bool
        ):
            raise ValueError("player_note.times_seen must be an integer")
        if player["confidence"] not in ("low", "medium"):
            raise ValueError("player_note.confidence must be low or medium")
    if not _is_str_list(analysis["honest_limits"]):
        raise ValueError("honest_limits must be a string list")


def _normalized_kit_color(value: str) -> str:
    return value.strip().lower()


def _frame_jersey_evidence(wrapped: dict) -> set[tuple[str, int]]:
    evidence: set[tuple[str, int]] = set()
    observation = wrapped.get("observation", wrapped)
    if not isinstance(observation, dict):
        return evidence
    teams = observation.get("teams")
    if not isinstance(teams, list):
        return evidence
    for team in teams:
        if not isinstance(team, dict) or not isinstance(team.get("kit_color"), str):
            continue
        numbers = team.get("readable_jersey_numbers")
        if not isinstance(numbers, list):
            continue
        kit_color = _normalized_kit_color(team["kit_color"])
        for number in numbers:
            if isinstance(number, int) and not isinstance(number, bool):
                evidence.add((kit_color, number))
    return evidence


def readable_jersey_evidence(observations: list[dict]) -> set[tuple[str, int]]:
    seen: set[tuple[str, int]] = set()
    for wrapped in observations:
        seen.update(_frame_jersey_evidence(wrapped))
    return seen


def jersey_evidence_counts(
    observations: list[dict],
) -> dict[tuple[str, int], int]:
    counts: dict[tuple[str, int], int] = {}
    for wrapped in observations:
        for evidence in _frame_jersey_evidence(wrapped):
            counts[evidence] = counts.get(evidence, 0) + 1
    return counts


def filter_player_notes(
    player_notes: list[dict], seen_evidence: set[tuple[str, int]]
) -> list[dict]:
    return [
        dict(player)
        for player in player_notes
        if isinstance(player.get("kit_color"), str)
        and isinstance(player.get("jersey_number"), int)
        and not isinstance(player.get("jersey_number"), bool)
        and (
            _normalized_kit_color(player["kit_color"]),
            player.get("jersey_number"),
        )
        in seen_evidence
    ]


def compute_player_confidence(player_notes: list[dict]) -> list[dict]:
    result = []
    for player in player_notes:
        normalized = dict(player)
        normalized["confidence"] = (
            "medium" if normalized.get("times_seen", 0) >= 3 else "low"
        )
        result.append(normalized)
    return result


def append_honest_limits(analysis: dict, interval_s: int | float) -> dict:
    result = dict(analysis)
    limits = list(result.get("honest_limits") or [])
    required = [
        *HONEST_LIMIT_TEMPLATES,
        f"Frames were sampled every {_clean_number(float(interval_s))} seconds, so most of the match was not seen.",
    ]
    for limit in required:
        if limit not in limits:
            limits.append(limit)
    result["honest_limits"] = limits
    return result


def finalize_analysis(
    analysis: dict,
    observations: list[dict],
    *,
    model: str,
    sampling: dict,
    frames_failed: int,
) -> dict:
    """Apply non-negotiable provenance, player filtering, confidence, and limits."""
    result = dict(analysis)
    result["schema_version"] = SCHEMA_VERSION
    result["model"] = model
    result["generated_at"] = datetime.now(UTC).isoformat()
    result["sampling"] = {
        "interval_s": sampling["interval_s"],
        "frames_analyzed": len(observations),
        "frames_failed": frames_failed,
        "in_play_windows": sampling["in_play_windows"],
    }
    evidence_counts = jersey_evidence_counts(observations)
    filtered = filter_player_notes(result.get("player_notes", []), set(evidence_counts))
    for player in filtered:
        evidence = (
            _normalized_kit_color(player["kit_color"]),
            player["jersey_number"],
        )
        player["times_seen"] = evidence_counts[evidence]
    result["player_notes"] = compute_player_confidence(filtered)
    result = append_honest_limits(result, sampling["interval_s"])
    validate_analysis_schema(result)
    return result


def too_many_frame_failures(total_frames: int, failed_frames: int) -> bool:
    if total_frames <= 0:
        return True
    return failed_frames / total_frames > 0.5


def _load_context(path: Path | None) -> dict:
    if path is None:
        return {}
    context = json.loads(path.read_text())
    if not isinstance(context, dict):
        raise ValueError("--context-json must contain a JSON object")
    allowed = ("opponent_name", "our_kit_color", "opponent_kit_color", "competition")
    return {key: context[key] for key in allowed if isinstance(context.get(key), str)}


def _parse_bool_env(name: str, default: str) -> bool:
    value = os.getenv(name, default).strip()
    if value not in ("0", "1"):
        raise ValueError(f"{name} must be 0 or 1")
    return value == "1"


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--kickoff-s", type=float)
    parser.add_argument("--halftime-s", type=float)
    parser.add_argument("--second-half-kickoff-s", type=float)
    parser.add_argument("--end-s", type=float)
    parser.add_argument("--context-json", type=Path)
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = _args(argv)
    video_path = args.video.resolve()
    out_dir = args.out.resolve()
    if not video_path.is_file():
        raise FileNotFoundError(f"video does not exist: {video_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    sample_s = float(os.getenv("QWEN_ANALYSIS_SAMPLE_S", str(DEFAULT_SAMPLE_S)))
    max_calls = int(os.getenv("QWEN_ANALYSIS_MAX_CALLS", str(DEFAULT_MAX_CALLS)))
    timeout_s = float(os.getenv("QWEN_ANALYSIS_TIMEOUT_S", str(DEFAULT_TIMEOUT_S)))
    ollama_url = os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL)
    model = os.getenv("QWEN_VISION_MODEL", DEFAULT_MODEL)
    sandboxed = _parse_bool_env("VIDEO_DECODE_SANDBOX", "1")

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe must both be available")
    ffmpeg_path, ffprobe_path = Path(ffmpeg).resolve(), Path(ffprobe).resolve()
    sandbox_path = shutil.which("sandbox-exec") if sandboxed else None
    if sandboxed and sandbox_path is None:
        raise RuntimeError(
            "VIDEO_DECODE_SANDBOX=1 but sandbox-exec is unavailable; refusing unsandboxed decode"
        )
    if not sandboxed:
        log.warning(
            "!!! VIDEO_DECODE_SANDBOX=0: DECODING ATTACKER-SUPPLIED VIDEO WITHOUT SEATBELT SANDBOX !!!"
        )
    profile_path = Path(__file__).resolve().parent / "sandbox" / "ffmpeg_decode.sb"
    if sandboxed and not profile_path.is_file():
        raise RuntimeError(f"Seatbelt profile is missing: {profile_path}")
    ffmpeg_dir = _ffmpeg_tree(ffmpeg_path, ffprobe_path)
    sandbox_exec = Path(sandbox_path) if sandbox_path else None

    duration_s = args.end_s
    if args.kickoff_s is None or duration_s is None:
        duration_s = probe_duration(
            video_path,
            out_dir,
            ffprobe_path,
            ffmpeg_dir,
            profile_path,
            sandboxed,
            sandbox_exec,
        )
    plan = build_sampling_plan(
        args.kickoff_s,
        args.halftime_s,
        args.second_half_kickoff_s,
        args.end_s,
        duration_s,
        sample_s,
        max_calls,
    )

    frame_rows = []
    for index, timestamp_s in enumerate(plan["timestamps"], start=1):
        filename = f"frame_{index:04d}_{float(timestamp_s):010.3f}.jpg"
        frame_path = frames_dir / filename
        extract_frame(
            video_path,
            frame_path,
            float(timestamp_s),
            ffmpeg_path,
            ffmpeg_dir,
            profile_path,
            sandboxed,
            sandbox_exec,
        )
        frame_rows.append(
            {"timestamp_s": timestamp_s, "filename": filename, "status": "pending"}
        )

    observations = []
    failed = 0
    for row in frame_rows:
        frame_path = frames_dir / row["filename"]
        error: Exception | None = None
        for attempt in range(2):
            try:
                content = ollama_chat(
                    build_observation_prompt(float(row["timestamp_s"])),
                    ollama_url=ollama_url,
                    model=model,
                    timeout_s=timeout_s,
                    image_path=frame_path,
                )
                observation = parse_observation(content)
                observations.append(
                    {"timestamp_s": row["timestamp_s"], "observation": observation}
                )
                row["status"] = "ok"
                error = None
                break
            except (json.JSONDecodeError, ValueError) as exc:
                error = exc
                if attempt == 0:
                    log.warning(
                        "invalid JSON for frame at %ss; retrying once",
                        row["timestamp_s"],
                    )
                    continue
            except Exception as exc:
                error = exc
                break
        if error is not None:
            failed += 1
            row["status"] = "failed"
            row["error"] = str(error)[:500]
            log.warning(
                "frame observation failed at %ss: %s", row["timestamp_s"], error
            )

    (out_dir / "frames_index.json").write_text(
        json.dumps({"frames": frame_rows}, indent=2) + "\n"
    )
    if too_many_frame_failures(len(frame_rows), failed):
        raise RuntimeError(
            f"{failed} of {len(frame_rows)} frame observations failed (>50%); refusing analysis"
        )

    context = _load_context(args.context_json)
    aggregation_prompt = build_aggregation_prompt(observations, context)
    last_error: Exception | None = None
    final = None
    for attempt in range(3):
        try:
            content = ollama_chat(
                aggregation_prompt,
                ollama_url=ollama_url,
                model=model,
                timeout_s=timeout_s,
            )
            candidate = json.loads(content)
            validate_analysis_schema(candidate)
            final = finalize_analysis(
                candidate,
                observations,
                model=model,
                sampling=plan,
                frames_failed=failed,
            )
            break
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                log.warning(
                    "invalid aggregate analysis; retrying (%d/2): %s", attempt + 1, exc
                )
    if final is None:
        raise RuntimeError(
            f"aggregation remained invalid after 3 attempts: {last_error}"
        )

    (out_dir / "analysis.json").write_text(
        json.dumps(final, indent=2, ensure_ascii=False) + "\n"
    )
    return 0


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        code = run()
    except Exception as exc:
        log.error("qwen match analysis failed: %s", exc)
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
