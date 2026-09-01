#!/usr/bin/env python3
"""Sample a match video and produce honest, jersey-number-only Qwen analysis."""

from __future__ import annotations

import argparse
import base64
import json
import logging
import math
import os
import re
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
DEFAULT_AGGREGATION_TIMEOUT_S = 1200.0
FRAME_NUM_PREDICT = 600
CAPTION_NUM_PREDICT = 300
PLAYER_NUM_PREDICT = 500
TEAM_NUM_PREDICT = 1500
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
PITCH_ZONES = ("left", "central", "right", "unclear")
ACTION_TYPES = (
    "pass",
    "carry",
    "duel",
    "shot",
    "defensive_action",
    "set_piece",
    "off_ball",
    "goalkeeping",
    "unclear",
)

HONEST_LIMIT_TEMPLATES = (
    "Single-camera sampled-frame analysis.",
    "Players are identified by jersey number only.",
    "Observations are qualitative, not measured statistics.",
    "Pitch zones are camera-relative thirds, not calibrated positions.",
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
 "visible_pitch_zone":"left|central|right|unclear","observation":str,"notable_actions":[str]}}
Use kit colors and CLEARLY readable jersey numbers only. Never infer a number from an unclear shirt and never
identify or guess a player name. Empty jersey-number lists are correct when no number is clear. Count only visible
players. visible_pitch_zone means which camera-relative third of the PITCH is mainly in frame, not an attacking or
defensive zone. Keep the observation to one sentence and describe only evidence visible in this frame."""


def build_caption_prompt(window: dict) -> str:
    kit_color = window.get("kit_color")
    kit_description = (
        f"wearing {kit_color}"
        if isinstance(kit_color, str) and kit_color
        else "in the target kit"
    )
    return f"""These are consecutive sampled frames from one football clip, ordered from earliest to latest.
Describe in ONE sentence what the player {kit_description} #{int(window["roster_jersey_number"])} is doing across
the frames. Never name any player. Describe only actions and outcomes visibly supported by these frames: never say
a shot scores or becomes a goal unless the goal is visibly scored. If the numbered player cannot be located, set
player_visible=false and make the caption a general description of what the clip shows.
Return one JSON object only with this exact shape:
{{"caption":str,"action_type":"pass|carry|duel|shot|defensive_action|set_piece|off_ball|goalkeeping|unclear",
"player_visible":bool,"visible_pitch_zone":"left|central|right|unclear"}}
visible_pitch_zone is the camera-relative third of the PITCH mainly in frame, never an inferred attacking or
defensive zone."""


def caption_frame_timestamps(
    start_s: float, end_s: float, max_frames: int = 3
) -> list[float]:
    """Return up to ``max_frames`` timestamps evenly spaced across a caption window."""
    start = float(start_s)
    end = float(end_s)
    if (
        not math.isfinite(start)
        or not math.isfinite(end)
        or end <= start
        or max_frames <= 0
    ):
        return []
    if max_frames == 1:
        return [round((start + end) / 2, 3)]
    step = (end - start) / (max_frames - 1)
    return [round(start + index * step, 3) for index in range(max_frames)]


def scoped_recurring_jersey_evidence(
    observations: list[dict],
    context: dict | None = None,
    requested_scope: str = "ours",
) -> tuple[set[tuple[str, int]], str]:
    """Return recurring pairs in the effective uploader-side notes scope."""
    if requested_scope not in ("ours", "all"):
        raise ValueError("QWEN_NOTES_SCOPE must be ours or all")
    recurring = recurring_jersey_evidence(observations)
    our_kit_color = (context or {}).get("our_kit_color")
    if requested_scope == "ours" and isinstance(our_kit_color, str):
        normalized_ours = _normalized_kit_color(our_kit_color)
        if normalized_ours:
            return {pair for pair in recurring if pair[0] == normalized_ours}, "ours"
    return recurring, "all"


def player_evidence_frames(
    observations: list[dict], player_pair: tuple[str, int]
) -> list[dict]:
    """Return only frames where the normalized kit/number pair was readable."""
    normalized_pair = (_normalized_kit_color(player_pair[0]), player_pair[1])
    return sorted(
        [
            wrapped
            for wrapped in observations
            if normalized_pair in _frame_jersey_evidence(wrapped)
        ],
        key=lambda wrapped: float(wrapped.get("timestamp_s", 0)),
    )


def spread_evidence_frames(
    evidence_frames: list[dict], max_frames: int = 3
) -> list[dict]:
    """Select up to ``max_frames`` evidence rows, spread from first to last."""
    if max_frames <= 0 or not evidence_frames:
        return []
    ordered = sorted(
        evidence_frames, key=lambda wrapped: float(wrapped.get("timestamp_s", 0))
    )
    count = min(max_frames, len(ordered))
    if count == 1:
        return [ordered[len(ordered) // 2]]
    indices = [
        round(index * (len(ordered) - 1) / (count - 1)) for index in range(count)
    ]
    return [ordered[index] for index in indices]


def build_player_prompt(
    player_pair: tuple[str, int], evidence_frames: list[dict]
) -> str:
    kit_color, jersey_number = player_pair
    compact_evidence = []
    for wrapped in evidence_frames:
        observation = wrapped["observation"]
        compact_evidence.append(
            {
                "t": wrapped["timestamp_s"],
                "phase_of_play": observation["phase_of_play"],
                "visible_pitch_zone": observation["visible_pitch_zone"],
                "observation": observation["observation"],
                "notable_actions": observation["notable_actions"],
            }
        )
    evidence_json = json.dumps(
        compact_evidence, separators=(",", ":"), ensure_ascii=False
    )
    return f"""Write a trustworthy scout's read for the football player wearing {kit_color} #{jersey_number}.
The attached images are up to three of that player's readable-number evidence frames, ordered across time.
All readable evidence frames for this player: {evidence_json}

Return one JSON object only with this exact shape:
{{"observations":[str],"confidence":"low|medium"}}
Provide 1 to 3 concrete observations about what #{jersey_number} was seen doing or where #{jersey_number} was
seen. Tie every observation to an evidence timestamp using "t=<seconds>". Never name or identify any player, and
never invent an event, action, statistic, location, or certainty. Use only the supplied evidence for this player.
Prefer a concise scout's read over a sighting log. If no action is safely supportable, "Seen at t=X in zone Y" is
the honest floor."""


def compact_team_evidence(observations: list[dict]) -> list[dict]:
    """Drop prose and jersey lists from the evidence supplied to the team pass."""
    compacted = []
    for wrapped in observations:
        observation = wrapped["observation"]
        compacted.append(
            {
                "t": wrapped["timestamp_s"],
                "phase_of_play": observation["phase_of_play"],
                "visible_pitch_zone": observation["visible_pitch_zone"],
                "ball_visible": observation["ball_visible"],
                "kits": [
                    {
                        "kit_color": team["kit_color"],
                        "visible_players": team["visible_players"],
                    }
                    for team in observation["teams"]
                ],
                "notable_actions": observation["notable_actions"],
            }
        )
    return compacted


def build_team_prompt(observations: list[dict], context: dict | None = None) -> str:
    context_json = json.dumps(context or {}, separators=(",", ":"), ensure_ascii=False)
    evidence_json = json.dumps(
        compact_team_evidence(observations),
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return f"""Produce an honest team-level analysis from compact sampled football-frame evidence.
Optional match context: {context_json}
Compacted timestamped evidence: {evidence_json}

Return one JSON object only with this exact shape:
{{"match_summary":str,"team_analysis":[{{"kit_color":str,"is_ours":bool|null,"style":str,
"strengths":[str],"weaknesses":[str],"shape_notes":str}}],"honest_limits":[str]}}
Use no player names and invent no events, statistics, formations, or certainty. Distinguish the uploader's side only
when the supplied kit-color context supports it. Every non-empty style, strength, or weakness must cite a
phase_of_play present in the compacted evidence and ground it in an observed timestamp, visible pitch zone, or
concrete notable action; otherwise use an empty style string and empty strengths/weaknesses lists."""


def ollama_chat(
    prompt: str,
    *,
    ollama_url: str,
    model: str,
    timeout_s: float,
    num_predict: int | None = None,
    image_path: Path | None = None,
    image_paths: list[Path] | None = None,
) -> str:
    """Make the one permitted network call shape, using only urllib."""
    if image_path is not None and image_paths is not None:
        raise ValueError("pass image_path or image_paths, not both")
    message: dict[str, object] = {"role": "user", "content": prompt}
    paths = (
        image_paths
        if image_paths is not None
        else ([image_path] if image_path is not None else [])
    )
    if paths:
        message["images"] = [
            base64.b64encode(path.read_bytes()).decode("ascii") for path in paths
        ]
    options: dict[str, int | float] = {
        "temperature": 0,
        "repeat_penalty": 1.15,
    }
    if num_predict is not None:
        if (
            not isinstance(num_predict, int)
            or isinstance(num_predict, bool)
            or num_predict <= 0
        ):
            raise ValueError("num_predict must be a positive integer")
        options["num_predict"] = num_predict
    body = {
        "model": model,
        "think": False,
        "stream": False,
        "format": "json",
        "options": options,
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


def parse_window_caption(content: str) -> dict:
    caption = json.loads(content)
    validate_window_caption_schema(caption)
    return caption


def parse_player_read(content: str, evidence_frames: list[dict] | None = None) -> dict:
    player_read = json.loads(content)
    validate_player_read_schema(player_read, evidence_frames)
    return player_read


def parse_team_pass(content: str) -> dict:
    team_pass = json.loads(content)
    validate_team_pass_schema(team_pass)
    return team_pass


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
        "visible_pitch_zone",
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
        if {"kit_color", "visible_players", "readable_jersey_numbers"} - team.keys():
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
        if not isinstance(team["visible_players"], int) or isinstance(
            team["visible_players"], bool
        ):
            raise ValueError(
                "frame observation team.visible_players must be an integer"
            )
    if not isinstance(observation["ball_visible"], bool):
        raise ValueError("frame observation.ball_visible must be a boolean")
    if not isinstance(observation["phase_of_play"], str):
        raise ValueError("frame observation.phase_of_play must be a string")
    if observation["visible_pitch_zone"] not in PITCH_ZONES:
        raise ValueError("frame observation.visible_pitch_zone is invalid")
    if not isinstance(observation["observation"], str):
        raise ValueError("frame observation.observation must be a string")
    if not _is_str_list(observation["notable_actions"]):
        raise ValueError("frame observation.notable_actions must be a string list")


def validate_window_caption_schema(caption: object) -> None:
    if not isinstance(caption, dict):
        raise ValueError("window caption must be a JSON object")
    required = {"caption", "action_type", "player_visible", "visible_pitch_zone"}
    missing = required - caption.keys()
    if missing:
        raise ValueError(
            f"window caption is missing required keys: {', '.join(sorted(missing))}"
        )
    if not isinstance(caption["caption"], str) or not caption["caption"].strip():
        raise ValueError("window caption.caption must be a non-empty string")
    if caption["action_type"] not in ACTION_TYPES:
        raise ValueError("window caption.action_type is invalid")
    if not isinstance(caption["player_visible"], bool):
        raise ValueError("window caption.player_visible must be a boolean")
    if caption["visible_pitch_zone"] not in PITCH_ZONES:
        raise ValueError("window caption.visible_pitch_zone is invalid")


def validate_player_read_schema(
    player_read: object, evidence_frames: list[dict] | None = None
) -> None:
    if not isinstance(player_read, dict):
        raise ValueError("player read must be a JSON object")
    if {"observations", "confidence"} - player_read.keys():
        raise ValueError("player read is missing required keys")
    observations = player_read["observations"]
    if (
        not _is_str_list(observations)
        or not 1 <= len(observations) <= 3
        or not all(observation.strip() for observation in observations)
    ):
        raise ValueError("player read must contain 1 to 3 non-empty observations")
    if player_read["confidence"] not in ("low", "medium"):
        raise ValueError("player read confidence must be low or medium")
    if evidence_frames is not None:
        evidence_timestamps = {
            round(float(frame["timestamp_s"]), 3) for frame in evidence_frames
        }
        for observation in observations:
            cited_timestamps = {
                round(float(match), 3)
                for match in re.findall(
                    r"\bt\s*=\s*(-?\d+(?:\.\d+)?)", observation, re.IGNORECASE
                )
            }
            if not cited_timestamps & evidence_timestamps:
                raise ValueError(
                    "each player observation must cite an evidence timestamp as t=<seconds>"
                )


def validate_team_pass_schema(team_pass: object) -> None:
    if not isinstance(team_pass, dict):
        raise ValueError("team pass must be a JSON object")
    required = {"match_summary", "team_analysis", "honest_limits"}
    if required - team_pass.keys():
        raise ValueError("team pass is missing required keys")
    if not isinstance(team_pass["match_summary"], str):
        raise ValueError("team pass match_summary must be a string")
    if not _is_str_list(team_pass["honest_limits"]):
        raise ValueError("team pass honest_limits must be a string list")
    if not isinstance(team_pass["team_analysis"], list):
        raise ValueError("team pass team_analysis must be a list")
    for team in team_pass["team_analysis"]:
        if not isinstance(team, dict):
            raise ValueError("each team pass entry must be an object")
        required_team = {
            "kit_color",
            "is_ours",
            "style",
            "strengths",
            "weaknesses",
            "shape_notes",
        }
        if required_team - team.keys():
            raise ValueError("team pass entry is missing required keys")
        if not all(
            isinstance(team[key], str) for key in ("kit_color", "style", "shape_notes")
        ):
            raise ValueError("team pass string fields must be strings")
        if team["is_ours"] is not None and not isinstance(team["is_ours"], bool):
            raise ValueError("team pass is_ours must be boolean or null")
        if not _is_str_list(team["strengths"]) or not _is_str_list(team["weaknesses"]):
            raise ValueError("team pass strengths and weaknesses must be string lists")


def validate_analysis_schema(
    analysis: object,
    *,
    require_computed: bool = True,
    required_player_pairs: set[tuple[str, int]] | None = None,
) -> None:
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
    if require_computed:
        if "zone_coverage" not in sampling:
            raise ValueError("sampling is missing zone_coverage")
        coverage = sampling["zone_coverage"]
        if not isinstance(coverage, dict) or set(coverage) != set(PITCH_ZONES):
            raise ValueError("sampling.zone_coverage must contain all pitch zones")
        if not all(
            isinstance(count, int) and not isinstance(count, bool) and count >= 0
            for count in coverage.values()
        ):
            raise ValueError(
                "sampling.zone_coverage counts must be non-negative integers"
            )
        if not isinstance(sampling.get("captions_failed"), int) or isinstance(
            sampling.get("captions_failed"), bool
        ):
            raise ValueError("sampling.captions_failed must be an integer")
        if sampling.get("notes_scope") not in ("ours", "all"):
            raise ValueError("sampling.notes_scope must be ours or all")
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
    present_player_pairs = set()
    hollow_player_pairs = set()
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
        player_pair = (
            _normalized_kit_color(player["kit_color"]),
            player["jersey_number"],
        )
        if player_pair in present_player_pairs:
            raise ValueError(
                "player_notes contains duplicate normalized pair: "
                f"{player_pair[0]} #{player_pair[1]}"
            )
        present_player_pairs.add(player_pair)
        if not any(observation.strip() for observation in player["observations"]):
            hollow_player_pairs.add(player_pair)
    if hollow_player_pairs:
        rendered = ", ".join(
            f"{kit_color} #{jersey_number}"
            for kit_color, jersey_number in sorted(hollow_player_pairs)
        )
        raise ValueError(
            "player_notes contains hollow pairs (no non-empty observations): "
            f"{rendered}"
        )
    missing_player_pairs = (required_player_pairs or set()) - present_player_pairs
    if missing_player_pairs:
        rendered = ", ".join(
            f"{kit_color} #{jersey_number}"
            for kit_color, jersey_number in sorted(missing_player_pairs)
        )
        raise ValueError(
            f"player_notes is missing recurring evidenced pairs: {rendered}"
        )
    if not _is_str_list(analysis["honest_limits"]):
        raise ValueError("honest_limits must be a string list")
    if require_computed:
        if not isinstance(analysis.get("window_captions"), list):
            raise ValueError("window_captions must be a list")
        for window_caption in analysis["window_captions"]:
            if not isinstance(window_caption, dict):
                raise ValueError("each window_caption must be an object")
            if {
                "tracklet_id",
                "roster_entry_id",
                "roster_jersey_number",
                "start_s",
                "end_s",
            } - window_caption.keys():
                raise ValueError("window_caption is missing window identity fields")
            if not isinstance(window_caption["tracklet_id"], int) or isinstance(
                window_caption["tracklet_id"], bool
            ):
                raise ValueError("window_caption.tracklet_id must be an integer")
            if not isinstance(window_caption["roster_entry_id"], int) or isinstance(
                window_caption["roster_entry_id"], bool
            ):
                raise ValueError("window_caption.roster_entry_id must be an integer")
            if not isinstance(
                window_caption["roster_jersey_number"], int
            ) or isinstance(window_caption["roster_jersey_number"], bool):
                raise ValueError(
                    "window_caption.roster_jersey_number must be an integer"
                )
            if not _number(window_caption["start_s"]) or not _number(
                window_caption["end_s"]
            ):
                raise ValueError("window_caption bounds must be numeric")
            validate_window_caption_schema(window_caption)


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


def recurring_jersey_evidence(
    observations: list[dict], min_count: int = 2
) -> set[tuple[str, int]]:
    """Return normalized kit/number pairs readable in at least ``min_count`` frames."""
    return {
        evidence
        for evidence, count in jersey_evidence_counts(observations).items()
        if count >= min_count
    }


def zone_coverage_counts(observations: list[dict]) -> dict[str, int]:
    counts = {zone: 0 for zone in PITCH_ZONES}
    for wrapped in observations:
        observation = wrapped.get("observation", wrapped)
        if (
            isinstance(observation, dict)
            and observation.get("visible_pitch_zone") in counts
        ):
            counts[observation["visible_pitch_zone"]] += 1
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
    notes_scope: str = "all",
    required_player_pairs: set[tuple[str, int]] | None = None,
    omitted_player_pairs: set[tuple[str, int]] | None = None,
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
        "zone_coverage": zone_coverage_counts(observations),
        "captions_failed": 0,
        "notes_scope": notes_scope,
    }
    result["window_captions"] = []
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
    required_pairs = (
        recurring_jersey_evidence(observations)
        if required_player_pairs is None
        else required_player_pairs
    )
    omitted_pairs = omitted_player_pairs or set()
    if not omitted_pairs <= required_pairs:
        raise ValueError("omitted player pairs must belong to the required scoped set")
    validate_analysis_schema(
        result,
        required_player_pairs=required_pairs - omitted_pairs,
    )
    return result


def too_many_frame_failures(total_frames: int, failed_frames: int) -> bool:
    if total_frames <= 0:
        return True
    return failed_frames / total_frames > 0.5


def too_many_player_read_failures(total_players: int, failed_players: int) -> bool:
    if total_players <= 0:
        return False
    return failed_players / total_players > 0.5


def _load_context(path: Path | None) -> dict:
    if path is None:
        return {}
    context = json.loads(path.read_text())
    if not isinstance(context, dict):
        raise ValueError("--context-json must contain a JSON object")
    allowed = (
        "opponent_name",
        "our_kit_color",
        "opponent_kit_color",
        "competition",
        "attack_direction_first_half",
    )
    cleaned = {
        key: context[key] for key in allowed if isinstance(context.get(key), str)
    }
    if cleaned.get("attack_direction_first_half") not in (None, "left", "right"):
        cleaned.pop("attack_direction_first_half")
    caption_windows = []
    raw_caption_windows = context.get("caption_windows")
    for window in raw_caption_windows if isinstance(raw_caption_windows, list) else []:
        if not isinstance(window, dict):
            continue
        try:
            tracklet_id = window["tracklet_id"]
            roster_entry_id = window["roster_entry_id"]
            jersey_number = window["roster_jersey_number"]
            start_s = float(window["start_s"])
            end_s = float(window["end_s"])
        except (KeyError, TypeError, ValueError):
            continue
        if (
            not isinstance(tracklet_id, int)
            or isinstance(tracklet_id, bool)
            or not isinstance(roster_entry_id, int)
            or isinstance(roster_entry_id, bool)
            or not isinstance(jersey_number, int)
            or isinstance(jersey_number, bool)
            or not math.isfinite(start_s)
            or not math.isfinite(end_s)
            or start_s < 0
            or end_s <= start_s
        ):
            continue
        caption_windows.append(
            {
                "tracklet_id": tracklet_id,
                "roster_entry_id": roster_entry_id,
                "roster_jersey_number": jersey_number,
                "kit_color": window.get("kit_color")
                if isinstance(window.get("kit_color"), str)
                else None,
                "start_s": start_s,
                "end_s": end_s,
            }
        )
    cleaned["caption_windows"] = caption_windows
    return cleaned


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


def player_image_paths(
    evidence_frames: list[dict], frames_dir: Path, max_images: int = 3
) -> list[Path]:
    rows_with_images = [
        wrapped
        for wrapped in evidence_frames
        if isinstance(wrapped.get("filename"), str)
    ]
    return [
        frames_dir / wrapped["filename"]
        for wrapped in spread_evidence_frames(rows_with_images, max_images)
    ]


def generate_player_reads(
    required_player_pairs: set[tuple[str, int]],
    observations: list[dict],
    *,
    frames_dir: Path,
    ollama_url: str,
    model: str,
    timeout_s: float,
) -> tuple[list[dict], list[str], set[tuple[str, int]]]:
    """Generate independent reads; a twice-failed player is honestly omitted."""
    player_notes = []
    failure_limits = []
    omitted_pairs = set()
    for player_pair in sorted(required_player_pairs):
        evidence_frames = player_evidence_frames(observations, player_pair)
        image_paths = player_image_paths(evidence_frames, frames_dir)
        parsed = None
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                content = ollama_chat(
                    build_player_prompt(player_pair, evidence_frames),
                    ollama_url=ollama_url,
                    model=model,
                    timeout_s=timeout_s,
                    num_predict=PLAYER_NUM_PREDICT,
                    image_paths=image_paths,
                )
                parsed = parse_player_read(content, evidence_frames)
                break
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    log.warning(
                        "invalid player read for %s #%s; retrying once: %s",
                        player_pair[0],
                        player_pair[1],
                        exc,
                    )
        if parsed is None:
            omitted_pairs.add(player_pair)
            reason = "unknown error" if last_error is None else str(last_error)
            reason = " ".join(reason.split())[:300]
            failure_limits.append(
                f"no read produced for {player_pair[0]} #{player_pair[1]}: {reason}"
            )
            continue
        player_notes.append(
            {
                "kit_color": player_pair[0],
                "jersey_number": player_pair[1],
                "observations": parsed["observations"],
                "times_seen": len(evidence_frames),
                "confidence": parsed["confidence"],
            }
        )
    return player_notes, failure_limits, omitted_pairs


def generate_team_pass(
    observations: list[dict],
    context: dict,
    *,
    ollama_url: str,
    model: str,
    timeout_s: float,
) -> dict:
    """Generate team analysis from compact evidence, retrying once."""
    prompt = build_team_prompt(observations, context)
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            content = ollama_chat(
                prompt,
                ollama_url=ollama_url,
                model=model,
                timeout_s=timeout_s,
                num_predict=TEAM_NUM_PREDICT,
            )
            return parse_team_pass(content)
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                log.warning("invalid team analysis; retrying once: %s", exc)
    raise RuntimeError(f"team analysis remained invalid after 2 attempts: {last_error}")


def generate_window_captions(
    caption_windows: list[dict],
    *,
    video_path: Path,
    out_dir: Path,
    ffmpeg_path: Path,
    ffmpeg_dir: Path,
    profile_path: Path,
    sandboxed: bool,
    sandbox_exec: Path | None,
    ollama_url: str,
    model: str,
    timeout_s: float,
) -> tuple[list[dict], int]:
    """Caption windows independently; no one window can fail the analysis job."""
    captions_dir = out_dir / "frames" / "captions"
    captions_dir.mkdir(parents=True, exist_ok=True)
    captions = []
    failed = 0
    for window_index, window in enumerate(caption_windows, start=1):
        try:
            frame_paths = []
            for frame_index, timestamp_s in enumerate(
                caption_frame_timestamps(window["start_s"], window["end_s"]),
                start=1,
            ):
                frame_path = captions_dir / (
                    f"caption_{window_index:04d}_t{window['tracklet_id']}_{frame_index}_{timestamp_s:010.3f}.jpg"
                )
                extract_frame(
                    video_path,
                    frame_path,
                    timestamp_s,
                    ffmpeg_path,
                    ffmpeg_dir,
                    profile_path,
                    sandboxed,
                    sandbox_exec,
                )
                frame_paths.append(frame_path)
            if not frame_paths:
                raise ValueError("caption window produced no frame timestamps")

            parsed = None
            last_error: Exception | None = None
            for attempt in range(2):
                try:
                    content = ollama_chat(
                        build_caption_prompt(window),
                        ollama_url=ollama_url,
                        model=model,
                        timeout_s=timeout_s,
                        num_predict=CAPTION_NUM_PREDICT,
                        image_paths=frame_paths,
                    )
                    parsed = parse_window_caption(content)
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt == 0:
                        log.warning(
                            "invalid caption for tracklet %s at %ss; retrying once: %s",
                            window["tracklet_id"],
                            window["start_s"],
                            exc,
                        )
            if parsed is None:
                raise ValueError(f"caption remained invalid after retry: {last_error}")
            captions.append(
                {
                    "tracklet_id": window["tracklet_id"],
                    "roster_entry_id": window["roster_entry_id"],
                    "roster_jersey_number": window["roster_jersey_number"],
                    "start_s": _clean_number(window["start_s"]),
                    "end_s": _clean_number(window["end_s"]),
                    **parsed,
                }
            )
        except Exception as exc:
            failed += 1
            log.warning(
                "caption window failed for tracklet %s at %ss: %s",
                window.get("tracklet_id"),
                window.get("start_s"),
                exc,
            )
    return captions, failed


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
    aggregation_timeout_s = float(
        os.getenv("QWEN_AGGREGATION_TIMEOUT_S", str(DEFAULT_AGGREGATION_TIMEOUT_S))
    )
    requested_notes_scope = os.getenv("QWEN_NOTES_SCOPE", "ours").strip().lower()
    if requested_notes_scope not in ("ours", "all"):
        raise ValueError("QWEN_NOTES_SCOPE must be ours or all")
    ollama_url = os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL)
    model = os.getenv("QWEN_VISION_MODEL", DEFAULT_MODEL)
    sandboxed = _parse_bool_env("VIDEO_DECODE_SANDBOX", "1")
    captions_enabled = _parse_bool_env("QWEN_CAPTIONS", "1")

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
                    num_predict=FRAME_NUM_PREDICT,
                    image_path=frame_path,
                )
                observation = parse_observation(content)
                observations.append(
                    {
                        "timestamp_s": row["timestamp_s"],
                        "filename": row["filename"],
                        "observation": observation,
                    }
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
    analysis_context = {
        key: value for key, value in context.items() if key != "caption_windows"
    }
    required_player_pairs, effective_notes_scope = scoped_recurring_jersey_evidence(
        observations,
        analysis_context,
        requested_notes_scope,
    )
    player_notes, player_failure_limits, omitted_player_pairs = generate_player_reads(
        required_player_pairs,
        observations,
        frames_dir=frames_dir,
        ollama_url=ollama_url,
        model=model,
        timeout_s=timeout_s,
    )
    if too_many_player_read_failures(
        len(required_player_pairs), len(omitted_player_pairs)
    ):
        raise RuntimeError(
            f"{len(omitted_player_pairs)} of {len(required_player_pairs)} required "
            "player reads failed (>50%); refusing analysis"
        )

    team_pass = generate_team_pass(
        observations,
        analysis_context,
        ollama_url=ollama_url,
        model=model,
        timeout_s=aggregation_timeout_s,
    )
    candidate = {
        "schema_version": SCHEMA_VERSION,
        "model": model,
        "generated_at": datetime.now(UTC).isoformat(),
        "sampling": {
            "interval_s": plan["interval_s"],
            "frames_analyzed": len(observations),
            "frames_failed": failed,
            "in_play_windows": plan["in_play_windows"],
        },
        "match_summary": team_pass["match_summary"],
        "team_analysis": team_pass["team_analysis"],
        "player_notes": player_notes,
        "honest_limits": [
            *team_pass["honest_limits"],
            *player_failure_limits,
        ],
    }
    validate_analysis_schema(
        candidate,
        require_computed=False,
        required_player_pairs=required_player_pairs - omitted_player_pairs,
    )
    final = finalize_analysis(
        candidate,
        observations,
        model=model,
        sampling=plan,
        frames_failed=failed,
        notes_scope=effective_notes_scope,
        required_player_pairs=required_player_pairs,
        omitted_player_pairs=omitted_player_pairs,
    )

    if captions_enabled and context.get("caption_windows"):
        try:
            captions, captions_failed = generate_window_captions(
                context["caption_windows"],
                video_path=video_path,
                out_dir=out_dir,
                ffmpeg_path=ffmpeg_path,
                ffmpeg_dir=ffmpeg_dir,
                profile_path=profile_path,
                sandboxed=sandboxed,
                sandbox_exec=sandbox_exec,
                ollama_url=ollama_url,
                model=model,
                timeout_s=timeout_s,
            )
        except Exception as exc:
            log.warning("caption stage failed without failing analysis: %s", exc)
            captions = []
            captions_failed = len(context["caption_windows"])
        final["window_captions"] = captions
        final["sampling"]["captions_failed"] = captions_failed
        validate_analysis_schema(final)

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
