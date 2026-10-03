#!/usr/bin/env python3
"""Inspect a player's journey stop ordering to debug timeline display."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.main import app
from src.models.journey import PlayerJourney
from src.utils.log_privacy import log_metadata

player_id = int(sys.argv[1]) if len(sys.argv) > 1 else 18

with app.app_context():
    j = PlayerJourney.query.filter_by(player_api_id=player_id).first()
    if not j:
        print("No journey found")
        exit(1)

    data = j.to_map_dict()

    print(f"\n=== STOPS ORDER for {log_metadata(j.player_name)} (as sent to frontend) ===\n")
    for i, stop in enumerate(data["stops"]):
        print(
            f"  Stop {log_metadata(i)}: {log_metadata(stop['club_name'])} years={log_metadata(stop['years'])} levels={log_metadata(stop['levels'])}  apps={log_metadata(stop['total_apps'])}"
        )

    # Simulate buildProgressionNodes with the global sort fix
    nodes = []
    node_id = 0
    for si, stop in enumerate(data["stops"]):
        comps_by_season = {}
        for comp in stop.get("competitions") or []:
            s = comp.get("season")
            if s is not None:
                comps_by_season.setdefault(s, []).append(comp)

        for season in sorted(comps_by_season.keys()):
            comps = comps_by_season[season]
            apps = sum(c.get("apps", 0) for c in comps)
            nodes.append(
                {
                    "id": node_id,
                    "season": season,
                    "club": stop["club_name"],
                    "apps": apps,
                    "levels": stop["levels"],
                    "stopIndex": si,
                }
            )
            node_id += 1

    # Apply the global sort fix
    nodes.sort(key=lambda n: (n["season"] or 0, n["stopIndex"]))
    for i, n in enumerate(nodes):
        n["id"] = i

    print("\n=== PROGRESSION NODES (with global sort fix) ===\n")
    for n in nodes:
        marker = " <-- CURRENT" if n["id"] == len(nodes) - 1 else ""
        print(
            f"  Node {log_metadata(n['id'])}: {log_metadata(n['season'])}  {log_metadata(n['club'])} {log_metadata(n['apps'])} apps  {log_metadata(n['levels'])}{log_metadata(marker)}"
        )

    # Check for out-of-order
    print("\n=== OUT-OF-ORDER NODES ===\n")
    found = False
    for i in range(1, len(nodes)):
        if nodes[i]["season"] < nodes[i - 1]["season"]:
            found = True
            print(
                f"  Node {log_metadata(nodes[i - 1]['id'])} ({log_metadata(nodes[i - 1]['season'])} {log_metadata(nodes[i - 1]['club'])}) -> Node {log_metadata(nodes[i]['id'])} ({log_metadata(nodes[i]['season'])} {log_metadata(nodes[i]['club'])}) -- GOES BACKWARD"
            )
    if not found:
        print("  None found - all nodes in chronological order")
