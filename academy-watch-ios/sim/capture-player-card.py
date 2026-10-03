#!/usr/bin/env python3
"""Capture the player-card review states from an already built/installed DEBUG app.

  python3 sim/capture-player-card.py --simulator <UDID> --output <dir>

Every launch uses `-floodlightPreview pc-<state>`: requests are answered inside
the app from bundled fixtures, so nothing reaches a server. This script never
builds, installs, boots or shuts down a simulator.
"""
import argparse
from pathlib import Path
import subprocess
import time

BUNDLE = "com.theacademywatch.app"
# state -> the scroll anchors worth a picture.
STATES = {
    "photo": ["top", "facts", "season", "matches"],
    "no-photo": ["top"],
    "no-matches": ["top", "season"],
    "full-season": ["top", "season", "matches", "end"],
    "mismatch": ["season", "matches"],
    "keeper": ["top", "season", "matches"],
    "long-names": ["top", "facts", "season", "matches"],
    "several-photos": ["top"],
    "white-photo": ["top"],
    "read-failed": ["season"],
    "provider": ["season", "matches"],
    "totals-failed": ["season"],
    "desk": ["results"],
    "desk-next": ["results"],
}
LARGE = "UICTContentSizeCategoryAccessibilityL"


def simctl(*args, check=True):
    return subprocess.run(["xcrun", "simctl", *args], capture_output=True, check=check)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulator", required=True, help="Dedicated, booted simulator UUID")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--states", nargs="+", choices=sorted(STATES))
    parser.add_argument("--appearance", nargs="+", default=["light", "dark"], choices=["light", "dark"])
    parser.add_argument("--text", nargs="+", default=["standard", "large"], choices=["standard", "large"])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for state, anchors in STATES.items():
        if args.states and state not in args.states:
            continue
        for appearance in args.appearance:
            simctl("ui", args.simulator, "appearance", appearance)
            for text in args.text:
                for anchor in anchors:
                    launch = ["-floodlightPreview", f"pc-{state}", "-reviewAppearance", appearance]
                    if anchor != "top":
                        launch += ["-pcAnchor", anchor]
                    if text == "large":
                        launch += ["-UIPreferredContentSizeCategoryName", LARGE]
                    simctl("terminate", args.simulator, BUNDLE, check=False)
                    simctl("launch", args.simulator, BUNDLE, *launch)
                    time.sleep(6 if state.startswith("desk") else 4.5)
                    name = f"{state}-{anchor}-{appearance}-{text}.png"
                    simctl("io", args.simulator, "screenshot", str(args.output / name))
                    print(name, flush=True)


if __name__ == "__main__":
    main()
