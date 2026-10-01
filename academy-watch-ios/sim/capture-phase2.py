#!/usr/bin/env python3
"""Capture Phase 2's actual native views with process-local offline fixtures.
Requires a booted dedicated simulator and an installed DEBUG app. No network,
login email, build, or install is performed. Captures are never live-world proof.
"""
import argparse
from pathlib import Path
import subprocess
import time

SCREENS = ["N01", "N02", "N02b", "N03", "N04", "N05", "N06", "N06b", "N09", "N09b", "N10", "N13", "N14", "N17"]


def run(*args):
    return subprocess.run(["xcrun", "simctl", *args], check=True, capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulator", required=True)
    parser.add_argument("--output", type=Path, default=Path.home() / "codex-runs/aw-redesign/shots/I1")
    parser.add_argument("--appearance", choices=["light", "dark"], required=True)
    parser.add_argument("--screens", nargs="+", choices=SCREENS, default=SCREENS)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    run("ui", args.simulator, "appearance", args.appearance)
    run("status_bar", args.simulator, "override", "--time", "9:41", "--dataNetwork", "wifi", "--wifiMode", "active", "--wifiBars", "3", "--batteryState", "charged", "--batteryLevel", "100")
    for screen in args.screens:
        subprocess.run(["xcrun", "simctl", "terminate", args.simulator, "com.theacademywatch.app"], capture_output=True)
        run("launch", args.simulator, "com.theacademywatch.app", "-phase2Preview", screen, "-reviewCapture", *(["-reviewLocation"] if screen in ["N02", "N02b"] else []))
        time.sleep(4)
        run("io", args.simulator, "screenshot", str(args.output / f"{screen}-{args.appearance}.png"))
        print(f"{screen} {args.appearance}", flush=True)


if __name__ == "__main__":
    main()
