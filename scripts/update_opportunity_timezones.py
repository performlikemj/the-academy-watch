"""Regenerate the browser snapshot, accepted aliases and zoneinfo intersection.

Run with the backend Python runtime and Node used by the frontend gate. Intl's
supportedValuesOf still lists legacy spellings on some ICU releases; aliases
are accepted only if Intl resolves them to a supported entry (or UTC).
"""

import json
import subprocess
from pathlib import Path
from zoneinfo import available_timezones

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "academy-watch-backend/src/data"
SCRIPT = """
const candidates = JSON.parse(process.argv[1]);
const snapshot = Intl.supportedValuesOf('timeZone');
const supported = new Set([...snapshot, 'UTC']);
const aliases = {};
for (const zone of candidates) {
  if (supported.has(zone)) continue;
  try {
    const formatter = new Intl.DateTimeFormat('en-GB', {timeZone: zone});
    formatter.format(new Date());
    const canonical = formatter.resolvedOptions().timeZone;
    if (supported.has(canonical)) aliases[zone] = canonical;
  } catch { /* Unsupported by this browser runtime. */ }
}
process.stdout.write(JSON.stringify({snapshot, aliases}));
"""
candidates = sorted(
    z
    for z in available_timezones()
    if z == "UTC"
    or z.split("/")[0]
    in {
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
)
result = json.loads(
    subprocess.check_output(["node", "-e", SCRIPT, json.dumps(candidates)], text=True)
)
for name, value in (
    ("opportunity_timezone_browser_snapshot", result["snapshot"]),
    ("opportunity_timezone_aliases", result["aliases"]),
):
    (DATA / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n")
zones = sorted(
    set(candidates) & (set(result["snapshot"]) | set(result["aliases"]) | {"UTC"})
)
serialized = json.dumps(zones, indent=2) + "\n"
(DATA / "opportunity_timezones.json").write_text(serialized)
(ROOT / "academy-watch-frontend/src/lib/opportunity-timezones.json").write_text(
    serialized
)
print(f"{len(zones)} zones, {len(result['aliases'])} browser-accepted aliases")
