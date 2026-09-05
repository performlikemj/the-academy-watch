#!/usr/bin/env python3
import json, os, html as H, importlib.util
S=os.path.dirname(os.path.abspath(__file__))
spec=importlib.util.spec_from_file_location("br", os.path.join(S,"build_report.py")); br=importlib.util.module_from_spec(spec); spec.loader.exec_module(br)
d=br.d; proj=br.proj; BLOCKERS=br.BLOCKERS; STAGES=br.STAGES; SCALE=br.SCALE; DREAM=br.DREAM; DATE=br.DATE
e=H.escape
COUNTS=[("accounts","9","5 are the team"),("claimed players","1","of 9,654 tracked"),("clubs on the console","0",""),("watchlists / follows","0",""),("introductions","0","rail is on"),("revenue","$0","rail built, dark until go-live")]
def dots(s):
    return '<span class="dots" aria-label="score %d of 4">'%s + "".join('<i class="%s"></i>'%("on" if i<s else "") for i in range(4)) + "</span>"
def reach_pill(r):
    cls={"MISSING":"r0","DESIGNED_ONLY":"r1","BACKEND_ONLY":"r2","FLAGGED_OFF":"r2","ADMIN_ONLY":"r2","LIVE_WEB":"r3","LIVE_IOS":"r3","LIVE_WEB_IOS":"r4"}.get(r,"r0")
    return '<span class="pill %s">%s</span>'%(cls,e(r.replace("_"," ").lower()))
def sc_class(pct): return "hi" if pct>=60 else ("mid" if pct>=40 else "lo")
parts=[]
parts.append(f"""<title>Dream Scorecard</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{{--bg:#F1F4F2;--surface:#FFFFFF;--ink:#16221E;--muted:#5F6F69;--line:#D5DDD9;--accent:#1E6E58;--hi:#2F7D4F;--mid:#B8791A;--lo:#A8402C;--zero:#7A8580;--pillbg:#E8EEEB;--shadow:0 1px 2px rgba(22,34,30,.06)}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#0F1613;--surface:#172019;--ink:#E7EDE9;--muted:#9AA8A1;--line:#2A3631;--accent:#4FB08E;--hi:#5CC08A;--mid:#D9A03A;--lo:#E0664E;--zero:#8A9691;--pillbg:#1F2B25;--shadow:none}}}}
:root[data-theme="dark"]{{--bg:#0F1613;--surface:#172019;--ink:#E7EDE9;--muted:#9AA8A1;--line:#2A3631;--accent:#4FB08E;--hi:#5CC08A;--mid:#D9A03A;--lo:#E0664E;--zero:#8A9691;--pillbg:#1F2B25;--shadow:none}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font-family:"IBM Plex Sans",system-ui,-apple-system,Segoe UI,sans-serif;font-size:15px;line-height:1.5}}
.wrap{{max-width:1000px;margin:0 auto;padding:40px 24px 80px}}
h1,h2,h3,.big{{font-family:"Barlow Condensed","Arial Narrow",Impact,sans-serif;text-wrap:balance;margin:0}}
h1{{font-size:44px;font-weight:700;line-height:1;letter-spacing:.01em}} h2{{font-size:26px;font-weight:600;margin:48px 0 14px;padding-top:18px;border-top:1px solid var(--line)}} h3{{font-size:21px;font-weight:600}}
.eyebrow{{font-family:"IBM Plex Mono",monospace;font-size:11.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}}
.dream{{max-width:66ch;margin:14px 0 0;color:var(--muted);font-size:15.5px}}
.sheet{{display:grid;grid-template-columns:1.1fr 1fr;gap:16px;margin-top:28px}} @media(max-width:720px){{.sheet{{grid-template-columns:1fr}}}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:20px 22px;box-shadow:var(--shadow)}}
.big{{font-size:84px;font-weight:700;line-height:.9;font-variant-numeric:tabular-nums}} .big small{{font-size:30px;color:var(--muted);font-weight:600}}
.sub{{color:var(--muted);margin-top:8px;max-width:40ch}}
.counts{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px 14px;margin-top:14px}} .counts div{{border-top:2px solid var(--line);padding-top:6px}} .counts b{{font-family:"Barlow Condensed";font-size:28px;font-weight:600;display:block;line-height:1;font-variant-numeric:tabular-nums}} .counts span{{font-size:12.5px;color:var(--muted);display:block}}
.bars{{display:grid;gap:10px;margin-top:16px}} .bar{{display:grid;grid-template-columns:230px 1fr 64px;align-items:center;gap:12px}} @media(max-width:720px){{.bar{{grid-template-columns:1fr 60px;}} .bar .track{{grid-column:1/3}}}}
.bar .lab{{font-weight:500}} .bar .lab small{{color:var(--muted);font-weight:400;margin-left:6px;font-family:"IBM Plex Mono";font-size:11.5px}}
.track{{height:14px;background:var(--pillbg);border-radius:3px;overflow:hidden}} .fill{{height:100%;background:var(--accent)}} .fill.lo{{background:var(--lo)}} .fill.mid{{background:var(--mid)}} .fill.hi{{background:var(--hi)}}
.pct{{font-family:"Barlow Condensed";font-size:22px;font-weight:600;text-align:right;font-variant-numeric:tabular-nums}}
.scale{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:12px}} @media(max-width:720px){{.scale{{grid-template-columns:1fr 1fr}}}} .scale div{{background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:10px 12px;font-size:13px}} .scale b{{font-family:"Barlow Condensed";font-size:26px;display:block;line-height:1;margin-bottom:4px}} .scale span{{color:var(--muted)}}
.rule{{margin:10px 0 0;color:var(--muted);font-size:13.5px}}
.caps{{border:1px solid var(--line);border-radius:6px;background:var(--surface);overflow:hidden}}
.cap{{display:grid;grid-template-columns:44px 1fr 80px 128px;gap:12px;padding:12px 16px;border-top:1px solid var(--line);align-items:start}} .cap:first-child{{border-top:0}} @media(max-width:720px){{.cap{{grid-template-columns:44px 1fr;}} .cap .dots,.cap .pill{{justify-self:start}}}}
.cap .id{{font-family:"IBM Plex Mono";font-size:12.5px;color:var(--muted);padding-top:3px}} .cap .name{{font-weight:600}} .cap .why{{color:var(--muted);font-size:13.5px;margin-top:3px;max-width:70ch}}
details{{margin-top:6px;font-size:13.5px}} summary{{cursor:pointer;color:var(--accent);font-weight:500}} details p{{margin:6px 0 0;max-width:70ch}} details .eff{{font-family:"IBM Plex Mono";font-size:11.5px;color:var(--muted)}}
.dots{{display:inline-flex;gap:3px;padding-top:6px}} .dots i{{width:14px;height:14px;border-radius:2px;background:var(--pillbg);border:1px solid var(--line);display:block}} .dots i.on{{background:var(--accent);border-color:var(--accent)}}
.pill{{display:inline-block;font-family:"IBM Plex Mono";font-size:11px;letter-spacing:.04em;padding:3px 8px;border-radius:3px;background:var(--pillbg);color:var(--muted);margin-top:4px;white-space:nowrap}} .pill.r4{{color:var(--hi);border:1px solid var(--hi);background:transparent}} .pill.r3{{color:var(--hi)}} .pill.r2{{color:var(--mid)}} .pill.r1,.pill.r0{{color:var(--lo)}}
.ph{{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin:34px 0 10px}} .ph .pct{{font-size:30px}}
ol.block{{padding-left:0;list-style:none;counter-reset:b;display:grid;gap:10px;margin:0}} ol.block li{{counter-increment:b;display:grid;grid-template-columns:46px 1fr;gap:12px;background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:14px 16px}} ol.block li::before{{content:counter(b);font-family:"Barlow Condensed";font-size:34px;font-weight:700;line-height:1;color:var(--lo)}} ol.block b{{display:block;font-size:15.5px}} ol.block p{{margin:4px 0 0;color:var(--muted);font-size:13.5px;max-width:75ch}} ol.block .caps-ref{{font-family:"IBM Plex Mono";font-size:11.5px;color:var(--muted);margin-top:6px;display:block}}
.stages{{display:grid;gap:8px}} .stage{{display:grid;grid-template-columns:54px 1fr 190px 74px;gap:12px;align-items:center;background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:12px 16px}} @media(max-width:720px){{.stage{{grid-template-columns:54px 1fr 74px}} .stage .track{{display:none}}}}
.stage .sid{{font-family:"Barlow Condensed";font-size:26px;font-weight:700;color:var(--accent)}} .stage .what{{color:var(--muted);font-size:13.5px;margin-top:2px;max-width:72ch}} .stage .when{{font-family:"IBM Plex Mono";font-size:11.5px;color:var(--muted);margin-left:8px}}
.note{{color:var(--muted);font-size:13.5px;max-width:75ch;margin-top:12px}}
.method{{font-size:13px;color:var(--muted);max-width:75ch}} .method code{{font-family:"IBM Plex Mono";font-size:12px}}
ul.plain{{margin:8px 0 0;padding-left:18px;color:var(--muted);font-size:13.5px}} ul.plain li{{margin:4px 0;max-width:80ch}}
a:focus-visible,summary:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
@media(prefers-reduced-motion:no-preference){{.fill{{transition:width .5s ease}}}}
</style>
<div class="wrap">
<div class="eyebrow">The Academy Watch · dream scorecard · {DATE} · updated after S0–S3 + the money-safety audit (2026-09-05)</div>
<h1>How far is the app from the dream?</h1>
<p class="dream">{e(DREAM)}</p>
<div class="sheet">
 <div class="card"><div class="eyebrow">Built</div><div class="big">{d['overall_pct']}<small>%</small></div><p class="sub">Of the dream exists as code a user can reach, weighted across five pillars. Backend without a button counts as half-built.</p></div>
 <div class="card"><div class="eyebrow">Lived</div><div class="big">~0<small>%</small></div><p class="sub">What is happening in prod today, measured read-only on {DATE}.</p>
 <div class="counts">{"".join(f'<div><b>{e(v)}</b><span>{e(k)}</span><span>{e(n)}</span></div>' for k,v,n in COUNTS)}</div></div>
</div>
<div class="bars">""")
for p,v in d["pillars"].items():
    parts.append(f'<div class="bar"><div class="lab">{e(v["name"])}<small>w {v["weight"]}</small></div><div class="track"><div class="fill {sc_class(v["pct"])}" style="width:{v["pct"]}%"></div></div><div class="pct">{v["pct"]}%</div></div>')
parts.append('</div>')
parts.append('<h2>The scale</h2><div class="scale">'+"".join(f'<div><b>{s}</b>{e(l)}<br><span>{e(m)}</span></div>' for s,l,m in SCALE)+'</div><p class="rule">The rule that decides most rows: backend without a button is a 2, never a 3. Flag off in prod is a 2. Admin has to act every time is a 2.</p>')
parts.append('<h2>Every capability, scored</h2>')
for p,v in d["pillars"].items():
    parts.append(f'<div class="ph"><h3>{e(p)} · {e(v["name"])}</h3><div class="pct">{v["pct"]}%</div></div><div class="caps">')
    for c in v["capabilities"]:
        note=f' <span class="eyebrow" style="letter-spacing:.04em">codex said {c["codex_score"]}</span>' if "codex_score" in c and c["codex_score"]!=c["score"] else ""
        parts.append(f'<div class="cap"><div class="id">{e(c["id"])}</div><div><div class="name">{e(c["name"])}{note}</div><div class="why">{e(c.get("blocker",""))}</div><details><summary>Next step · {e(c.get("effort","-"))}</summary><p>{e(c.get("next_step",""))}</p></details></div>{dots(c["score"])}{reach_pill(c.get("reach","MISSING"))}</div>')
    parts.append('</div>')
parts.append('<h2>What holds the dream back, ranked</h2><ol class="block">'+"".join(f'<li><div><b>{e(t)}</b><p>{e(w)}</p><span class="caps-ref">caps {e(ids)}</span></div></li>' for t,w,ids in BLOCKERS)+'</ol>')
parts.append(f'<h2>Steps toward 100%</h2><p class="note"><b>S0–S3 and the money-safety stage are done</b> (S0: front door — five PRs; S1: one player universe + a games grain — five PRs: self-made players join scout discovery with provenance chips, players add their own games, clubs record results and lineups, trust-tiered edits; S2: fans + reach — five PRs: web fan follow/counts, owner signals, per-player share cards, sitemap/robots, and the weekly activity email job; S3: money rails shipped dark; 2026-09-05: independently audited at {d["overall_pct"]}% by gpt-6-astra — 3.6/5.5 fall to 2 while billing is dark, 2.7 rises to 2, and the audit\'s 3 P1 + 3 launch blockers are fixed, awaiting the go-live checklist). Baseline before S0 was 51.9%, after S0 54.1%. Projected score after each stage, computed from the target scores with the same weights. Stages aim at 3 (usable), not 4; the last quarter is polish, iOS parity, tests, and the under-18 expansion.</p><div class="stages">')
parts.append(f'<div class="stage"><div class="sid">now</div><div><b>Today</b></div><div class="track"><div class="fill" style="width:{d["overall_pct"]}%"></div></div><div class="pct">{d["overall_pct"]}%</div></div>')
for sid,name,when,what,targets,o,pp in proj:
    parts.append(f'<div class="stage"><div class="sid">{e(sid)}</div><div><b>{e(name)}</b><span class="when">{e(when)}</span><div class="what">{e(what)}</div></div><div class="track"><div class="fill" style="width:{o}%"></div></div><div class="pct">{o}%</div></div>')
parts.append(f'</div><p class="note">A credible launch bar is S0–S2 done (about {proj[2][5]}%) with S6 already started: the number only means something once real players, clubs and scouts are in it.</p>')
parts.append('<h2>Already strong, do not rebuild</h2><ul class="plain">'+"".join(f'<li>{e(s)}</li>' for s in d.get("strong_already",[])[:10])+'</ul>')
parts.append('<h2>Corrections to the 23 Aug review</h2><ul class="plain">'+"".join(f'<li>{e(s)}</li>' for s in d.get("surprises",[]))+'</ul>')
parts.append(f'<h2>Method</h2><p class="method">Three codex (gpt-5.6-sol, ultra effort) read-only audits scored 31 capabilities against the dream with path:line evidence. Two Fable adversarial reviewers re-read every cite at <code>origin/main ade7bbc</code>, re-scored against prod flag values, and answered targeted attack questions; Fable arbitrated. Prod counts came from read-only SQL on the Supabase pooler. Independently re-audited 2026-09-05 by gpt-6-astra (read-only, checkout fe7d25f): <code>ledgers/research/astra-review-2026-09-05.md</code>. Ledger copy: <code>ledgers/GRADING_dream-scorecard-{DATE}.md</code>.</p></div>')
open(os.path.join(S,"dream-scorecard.html"),"w").write("\n".join(parts))
print("html written", os.path.getsize(os.path.join(S,"dream-scorecard.html")))
