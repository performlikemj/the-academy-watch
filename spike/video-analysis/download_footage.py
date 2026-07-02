#!/usr/bin/env python3
"""Fetch Phase 0 spike footage from license-verified sources.

Sources (verified 2026-06-10 — see ledgers/research/video-analysis/)
--------------------------------------------------------------------
soccertrack       SoccerTrack v2 — 10 full Japanese university-level matches,
                  4K panoramic full-pitch, CC BY 4.0 (LICENSE-DATA verified:
                  "any purpose, even commercially"). Attribution required:
                  cite arXiv:2508.01802. Serves BOTH throughput (4K, full
                  halves) and degradation (real amateur footage) measurement,
                  and ships per-frame tracking ground truth.
youtube-verified  Five individually license-checked CC BY YouTube matches
                  (VEO panning sideline, US college, semi-pro). Each watch
                  page showed "Creative Commons Attribution license (reuse
                  allowed)" on 2026-06-10; the downloader re-checks at fetch
                  time and aborts if the license has changed.
youtube           Any single YouTube URL — refuses to download unless the
                  license metadata says Creative Commons (override only with
                  --allow-unverified-license for footage you hold rights to).

BANNED sources — do not "fix" this script to add them back:
  * DFL Bundesliga Data Shootout (Kaggle): data removed from Kaggle, and the
    competition rules restricted use to the competition itself, required
    deletion of all copies afterwards, and ban redistribution.
  * roboflow/sports demo clips (0bfacc_0.mp4 etc.): re-hosted DFL competition
    clips — the repo's MIT license covers code only, not the footage.
  * Third-party Kaggle re-uploads of DFL clips: redistribution in violation
    of the competition rules.
  * SoccerNet videos: KAUST NDA, "research and non commercial use only".
  * Alfheim/Tromsø (Simula): "non-commercial research purposes" only, plus an
    explicit ban on player performance profiling.
  * ISSIA-CNR: original host dead, no recoverable license.

Every subcommand prints the licensing reminder for its source and verifies the
downloaded files exist with plausible sizes.

Requires: `pip install gdown yt-dlp` (in requirements.txt).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_DEST = Path(__file__).resolve().parent / "footage"

# SoccerTrack v2 Google Drive mirror (from the project page; verified live 2026-06-10).
SOCCERTRACK_V2_FOLDER = "1N2Qx2qkFgRtpbHitl2Vh6sLVYGgqkWwn"
SOCCERTRACK_V2_REPO = "https://github.com/AtomScott/SoccerTrack-v2"

# Individually license-verified on their watch pages, 2026-06-10. Re-checked at fetch time.
VERIFIED_CC_VIDEOS = {
    "Ryt6tidyYaI": "AFC Yorkies 4-0 AFC Wyke | VEO 2 panning sideline cam, 1080p, 1:55 (UK grassroots/university)",
    "bcoAMvp9ez8": "Bayhawks Men's Soccer vs Massasoit | US college, 1080p, 1:47",
    "yVMpFuMD71I": "Bayhawk Women's Soccer vs Monroe College | US college, 1080p, 1:34",
    "CqL3iTdRUlg": "Volsungur vs Sindri | VEO panning cam, 1080p, 1:52 (Icelandic lower division)",
    "C09BiuotZVM": "Bo'ness United v Linlithgow Rose | 720p, 1:11 (Scottish semi-pro; low-quality floor)",
}

LICENSE_NOTES = {
    "soccertrack": (
        "SoccerTrack v2 — CC BY 4.0 (verified from the repo's LICENSE-DATA file):\n"
        '  * "You may use the material for any purpose, even commercially."\n'
        "  * ATTRIBUTION REQUIRED: credit the dataset, link the license, cite\n"
        "    arXiv:2508.01802. report_template.md has an attribution slot.\n"
        "  * 10 Japanese university matches, 4K panoramic, per-frame ground truth\n"
        "    — covers throughput AND degradation, and is literally the product's\n"
        "    target footage (Japan college/amateur).\n"
        f"  * Repo (docs + ground-truth scripts): {SOCCERTRACK_V2_REPO}"
    ),
    "youtube": (
        "YouTube (Creative Commons only).\n"
        "  * YouTube's CC option is CC BY 3.0 — commercial reuse allowed WITH\n"
        "    ATTRIBUTION (channel, title, URL — slot in report_template.md).\n"
        "  * The downloader verifies the license metadata per video at fetch time\n"
        "    and writes the .info.json next to the video as provenance evidence.\n"
        "  * Standard-license uploads are NOT usable — do not override the check\n"
        "    for footage you don't hold rights to."
    ),
}

MIN_VIDEO_MB = 25.0


def _print_license(source: str) -> None:
    print("=" * 72)
    print("LICENSING — " + source)
    print(LICENSE_NOTES[source])
    print("=" * 72)


def _require_cli(name: str, install_hint: str) -> None:
    if shutil.which(name) is None:
        sys.exit(f"ERROR: `{name}` not found on PATH. Install with: {install_hint}")


def _run(cmd: list[str]) -> None:
    print("$ " + " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(f"ERROR: command failed with exit code {result.returncode}")


def _verify_videos(dest: Path, min_mb: float = MIN_VIDEO_MB) -> None:
    videos = sorted(
        p for p in dest.rglob("*") if p.suffix.lower() in {".mp4", ".mkv", ".webm", ".avi", ".mov"}
    )
    if not videos:
        sys.exit(f"VERIFY FAILED: no video files found under {dest}")
    print(f"\nVerified {len(videos)} video file(s) under {dest}:")
    ok = True
    for v in videos:
        mb = v.stat().st_size / 1e6
        flag = "OK " if mb >= min_mb else "SUSPICIOUSLY SMALL"
        if mb < min_mb:
            ok = False
        print(f"  [{flag}] {v.relative_to(dest)}  ({mb:.1f} MB)")
    if not ok:
        sys.exit(f"VERIFY FAILED: at least one video is under {min_mb:.0f} MB — likely a truncated download.")


def cmd_list(_: argparse.Namespace) -> None:
    print(__doc__)
    print("Verified CC BY YouTube set (youtube-verified):")
    for vid, desc in VERIFIED_CC_VIDEOS.items():
        print(f"  {vid}  {desc}")


def cmd_soccertrack(args: argparse.Namespace) -> None:
    _print_license("soccertrack")
    _require_cli("gdown", "pip install gdown")
    dest: Path = args.dest / "soccertrack-v2"
    dest.mkdir(parents=True, exist_ok=True)
    print(
        "NOTE: the full mirror is 10 matches of 4K video (tens of GB).\n"
        "gdown downloads the whole folder; interrupt once you have 2-3 matches,\n"
        "or download individual files via the Drive web UI / the repo's scripts.\n"
    )
    _run(
        [
            "gdown",
            "--folder",
            f"https://drive.google.com/drive/folders/{args.folder_id}",
            "-O",
            str(dest),
            "--remaining-ok",
        ]
    )
    _verify_videos(dest)


def _youtube_license(url: str) -> str:
    out = subprocess.run(
        ["yt-dlp", "--no-download", "--print", "%(license)s", url],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        sys.exit(f"ERROR: yt-dlp could not read metadata for {url}:\n{out.stderr.strip()}")
    return out.stdout.strip()


def _fetch_youtube(url: str, dest: Path, allow_unverified: bool) -> None:
    lic = _youtube_license(url)
    print(f"YouTube license metadata: {lic!r}")
    # YouTube exposes exactly one CC option: "Creative Commons Attribution license
    # (reuse allowed)" = CC BY 3.0. Anything else (standard license, empty) is refused.
    if "creative commons" not in lic.lower():
        if not allow_unverified:
            sys.exit(
                "REFUSED: video license is not Creative Commons.\n"
                "Only pass --allow-unverified-license for footage you hold the rights to."
            )
        print("WARNING: proceeding without a verified CC license (--allow-unverified-license).")
    else:
        print("CC BY confirmed. Remember attribution (channel + title + URL) in the report.")
    _run(
        [
            "yt-dlp",
            "-f",
            "bv*[height<=1080]+ba/b[height<=1080]",
            "--merge-output-format",
            "mp4",
            "--write-info-json",  # provenance: preserves the license field on disk
            "-o",
            str(dest / "%(id)s_%(title).60s.%(ext)s"),
            url,
        ]
    )


def cmd_youtube(args: argparse.Namespace) -> None:
    _print_license("youtube")
    _require_cli("yt-dlp", "pip install yt-dlp")
    dest: Path = args.dest / "youtube"
    dest.mkdir(parents=True, exist_ok=True)
    _fetch_youtube(args.url, dest, args.allow_unverified_license)
    _verify_videos(dest)


def cmd_youtube_verified(args: argparse.Namespace) -> None:
    _print_license("youtube")
    _require_cli("yt-dlp", "pip install yt-dlp")
    dest: Path = args.dest / "youtube"
    dest.mkdir(parents=True, exist_ok=True)
    ids = args.ids or list(VERIFIED_CC_VIDEOS)
    unknown = [i for i in ids if i not in VERIFIED_CC_VIDEOS]
    if unknown:
        sys.exit(f"ERROR: not in the verified set: {unknown}. Use the `youtube` subcommand for new URLs.")
    manifest = {i: VERIFIED_CC_VIDEOS[i] for i in ids}
    print("Fetching verified CC BY set (license re-checked per video):")
    print(json.dumps(manifest, indent=2))
    for vid in ids:
        _fetch_youtube(f"https://www.youtube.com/watch?v={vid}", dest, allow_unverified=False)
    _verify_videos(dest)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help=f"download root (default {DEFAULT_DEST})")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show sources and the verified CC video set").set_defaults(func=cmd_list)

    p_st = sub.add_parser("soccertrack", help="SoccerTrack v2 — CC BY 4.0 Japanese university matches (4K)")
    p_st.add_argument("--folder-id", default=SOCCERTRACK_V2_FOLDER, help="Drive mirror folder id override")
    p_st.set_defaults(func=cmd_soccertrack)

    p_ytv = sub.add_parser("youtube-verified", help="the five license-verified CC BY matches")
    p_ytv.add_argument("--ids", nargs="*", help=f"subset of {list(VERIFIED_CC_VIDEOS)} (default: all)")
    p_ytv.set_defaults(func=cmd_youtube_verified)

    p_yt = sub.add_parser("youtube", help="one Creative-Commons YouTube video by URL")
    p_yt.add_argument("url", help="YouTube video URL (must be CC-licensed)")
    p_yt.add_argument(
        "--allow-unverified-license",
        action="store_true",
        help="bypass the CC check — ONLY for footage you hold rights to",
    )
    p_yt.set_defaults(func=cmd_youtube)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
