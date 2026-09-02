#!/usr/bin/env python3
"""Merge codex pillar audits (out-A/B/C.json) + orchestrator overrides -> weighted scorecard JSON."""
import json, re, sys, glob, os
S = os.path.dirname(os.path.abspath(__file__))
WEIGHTS = {"P1": 25, "P2": 25, "P3": 20, "P4": 15, "P5": 15}
NAMES = {"P1":"Players: share, be found, have fans","P2":"Clubs: track, analyze growth, tools to improve","P3":"Scouts: find and analyze","P4":"Funding: Patreon/BMAC → club part-ownership","P5":"Foundation: safety, correctness, reach, ops, money, adoption"}
def load(path):
    txt = open(path).read()
    m = re.search(r'\{.*\}', txt, re.S)
    return json.loads(m.group(0))
caps = {}
meta = {"surprises": [], "strong_already": [], "admin_count_endpoints": []}
for f in sorted(glob.glob(os.path.join(S, "out-*.json"))):
    d = load(f)
    for c in d.get("capabilities", []):
        caps[c["id"]] = c
    for k in meta: meta[k] += d.get(k, [])
# orchestrator overrides (Fable adversarial-review verdicts) live in overrides.json: {"1.4": {"score": 2, "why": "..."}}
ov_path = os.path.join(S, "overrides.json")
overrides = json.load(open(ov_path)) if os.path.exists(ov_path) else {}
for cid, o in overrides.items():
    if cid in caps:
        caps[cid]["codex_score"] = caps[cid]["score"]; caps[cid]["score"] = o["score"]; caps[cid]["override_why"] = o["why"]
        if "reach" in o: caps[cid]["codex_reach"] = caps[cid]["reach"]; caps[cid]["reach"] = o["reach"]
        if "blocker" in o: caps[cid]["codex_blocker"] = caps[cid]["blocker"]; caps[cid]["blocker"] = o["blocker"]
        if o["score"] != caps[cid]["codex_score"]:
            caps[cid]["codex_blocker"] = caps[cid]["blocker"]
            caps[cid]["blocker"] = re.sub(r"^\[adversary-\d (up|down|keep)\] ", "", o["why"])
    else:
        caps[cid] = {"id": cid, "name": o.get("name", cid), "score": o["score"], "reach": o.get("reach","-"), "exists": o.get("exists", []), "missing": o.get("missing", []), "blocker": o.get("blocker",""), "next_step": o.get("next_step",""), "effort": o.get("effort","-"), "confidence": o.get("confidence","high"), "override_why": o["why"]}
for c in list(caps.values()):
    for k in ("blocker", "next_step", "name"):
        if isinstance(c.get(k), str): c[k] = c[k].replace("`", "")
pillars = {}
for p in WEIGHTS:
    cs = [c for c in caps.values() if c["id"].split(".")[0] == p[1:]]
    cs.sort(key=lambda c: [int(x) for x in c["id"].split(".")])
    pct = round(100 * sum(c["score"] for c in cs) / (4 * len(cs)), 1) if cs else 0.0
    pillars[p] = {"name": NAMES[p], "weight": WEIGHTS[p], "pct": pct, "capabilities": cs}
overall = round(sum(pillars[p]["pct"] * WEIGHTS[p] for p in WEIGHTS) / sum(WEIGHTS.values()), 1)
out = {"overall_pct": overall, "pillars": pillars, **meta}
json.dump(out, open(os.path.join(S, "scorecard.json"), "w"), indent=2)
print(f"OVERALL {overall}%")
for p, v in pillars.items():
    print(f"  {p} {v['pct']:5.1f}%  w={v['weight']}  n={len(v['capabilities'])}  {v['name']}")
    for c in v["capabilities"]:
        flag = f" (codex {c['codex_score']}→{c['score']})" if "codex_score" in c else ""
        print(f"     {c['id']:>4} [{c['score']}] {c.get('reach','-'):14} {c['name'][:60]}{flag}")
