#!/usr/bin/env python3
"""Render scorecard.json -> markdown tables (mechanical part of the ledger)."""
import json, os
S=os.path.dirname(os.path.abspath(__file__))
d=json.load(open(os.path.join(S,"scorecard.json")))
out=[]
out.append(f"**Overall: {d['overall_pct']}% of the dream** (weighted).\n")
out.append("| Pillar | Weight | Score |\n|---|---|---|")
for p,v in d["pillars"].items():
    out.append(f"| {p} — {v['name']} | {v['weight']} | **{v['pct']}%** |")
out.append("")
for p,v in d["pillars"].items():
    out.append(f"\n### {p} — {v['name']} — {v['pct']}%\n")
    out.append("| # | Capability | Score | Reach | Blocker (one thing stopping the next level) | Next step | Effort |\n|---|---|---|---|---|---|---|")
    for c in v["capabilities"]:
        cs = f"{c['score']}" + (f" (codex {c['codex_score']})" if "codex_score" in c and c["codex_score"]!=c["score"] else "")
        out.append(f"| {c['id']} | {c['name']} | {cs} | {c.get('reach','-')} | {c.get('blocker','')} | {c.get('next_step','')} | {c.get('effort','-')} |")
print("\n".join(out))
