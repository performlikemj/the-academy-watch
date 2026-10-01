"""Regenerate browser zones and legacy -> canonical IANA mappings.

Run with Node and --tzdata-zi pointing to IANA's compiled source (tzdata.zi,
including backward links). Canonical targets are committed, so production
never needs legacy links installed. The current data uses IANA 2026c.
"""

import argparse
import json
import subprocess
from pathlib import Path
from zoneinfo import available_timezones

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "academy-watch-backend/src/data"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--tzdata-zi", type=Path, default=Path("/usr/share/zoneinfo/tzdata.zi")
)
args = parser.parse_args()
links = {}
for line in args.tzdata_zi.read_text().splitlines():
    parts = line.split()
    if parts and parts[0] in {"L", "Link"}:
        links[parts[2]] = parts[1]


def canonical(zone):
    seen = set()
    while zone in links:
        if zone in seen:
            raise ValueError(f"cyclic IANA link: {zone}")
        seen.add(zone)
        zone = links[zone]
    return "UTC" if zone == "Etc/UTC" else zone


SCRIPT = """
const candidates = JSON.parse(process.argv[1]);
const snapshot = Intl.supportedValuesOf('timeZone');
const accepted = candidates.filter(zone => {
  try { new Intl.DateTimeFormat('en-GB', {timeZone: zone}).format(new Date()); return true; }
  catch { return false; }
});
process.stdout.write(JSON.stringify({snapshot, accepted}));
"""
regions = {
    "Africa",
    "America",
    "Antarctica",
    "Arctic",
    "Asia",
    "Atlantic",
    "Australia",
    "Europe",
    "Indian",
    "Pacific",
}
candidates = sorted(
    zone
    for zone in available_timezones()
    | set(json.loads((DATA / "opportunity_timezones.json").read_text()))
    if zone == "UTC" or zone.split("/")[0] in regions
)
result = json.loads(
    subprocess.check_output(["node", "-e", SCRIPT, json.dumps(candidates)], text=True)
)
zones = sorted(
    zone for zone in result["accepted"] if canonical(zone) in available_timezones()
)
aliases = {zone: canonical(zone) for zone in zones if canonical(zone) != zone}
for name, value in (
    ("opportunity_timezone_browser_snapshot", result["snapshot"]),
    ("opportunity_timezone_aliases", aliases),
    ("opportunity_timezones", zones),
):
    serialized = json.dumps(value, indent=2) + "\n"
    (DATA / f"{name}.json").write_text(serialized)
    if name != "opportunity_timezone_browser_snapshot":
        frontend_name = (
            "opportunity-timezones"
            if name == "opportunity_timezones"
            else "opportunity-timezone-aliases"
        )
        (ROOT / f"academy-watch-frontend/src/lib/{frontend_name}.json").write_text(
            serialized
        )
print(f"{len(zones)} zones, {len(aliases)} legacy -> canonical IANA aliases")
