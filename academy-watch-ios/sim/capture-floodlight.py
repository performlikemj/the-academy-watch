#!/usr/bin/env python3
"""Capture an already built/installed DEBUG app's generic offline review views.

Example:
  python3 sim/capture-floodlight.py --simulator <UDID>
  python3 sim/capture-floodlight.py --simulator <UDID> --before

Install the baseline build first for --before. The same launch harness must be
applied over origin/main's views (see Debug/README.md). This script never signs
in, builds, installs, boots or shuts down a simulator.
"""
import argparse
from pathlib import Path
import subprocess
import time

SCREENS = [
    "chooser", "home", "club-home", "scout", "scout-empty", "scout-error",
    "loading", "player", "season", "player-error", "showcase", "compare",
    "watchlist", "watchlist-empty", "watchlist-error", "lists", "lists-empty",
    "list-detail", "introduction", "introductions", "introductions-empty",
    "incoming", "thread", "gol", "gol-answer", "player-onboarding",
    "create-profile", "worldwide", "club-onboarding", "profiles",
    "profile-editor", "invitations", "feedback", "development", "auth",
    "account", "account-signed-out", "verification", "blocked", "legal",
    "report", "removal", "add-game", "my-club",
]


def run(*args):
    return subprocess.run(["xcrun", "simctl", *args], capture_output=True, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulator", required=True, help="Dedicated, booted simulator UUID")
    parser.add_argument("--output", type=Path, default=Path.home() / "codex-runs/aw-redesign/shots/ios")
    parser.add_argument("--before", action="store_true")
    parser.add_argument("--screens", nargs="+", choices=SCREENS)
    parser.add_argument("--appearance", choices=["light", "dark", "both"], default="both")
    parser.add_argument("--suffix", default="", help="Optional evidence suffix, e.g. xxxl")
    args = parser.parse_args()
    bundle = "com.theacademywatch.app"
    output = args.output / "before" if args.before else args.output
    output.mkdir(parents=True, exist_ok=True)
    styles = ["light"] if args.before else ["light", "dark"] if args.appearance == "both" else [args.appearance]
    for style in styles:
        run("ui", args.simulator, "appearance", style)
        for number, screen in enumerate(SCREENS, 1):
            if args.screens and screen not in args.screens:
                continue
            subprocess.run(["xcrun", "simctl", "terminate", args.simulator, bundle], capture_output=True)
            run("launch", args.simulator, bundle, "-floodlightPreview", screen)
            time.sleep(5 if screen in ["season", "scout"] else 3)
            suffix = f"-{args.suffix}" if args.suffix else ""
            file = output / f"{number:02}-{screen}{suffix}-{style}.png"
            run("io", args.simulator, "screenshot", str(file))
            print(f"{number:02} {screen} {style}{suffix}", flush=True)


if __name__ == "__main__":
    main()
