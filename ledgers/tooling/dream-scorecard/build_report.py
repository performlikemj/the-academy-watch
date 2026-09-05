#!/usr/bin/env python3
"""scorecard.json + narrative -> ledger markdown + HTML artifact. Projections are computed, not typed."""
import json, os, copy, html
S=os.path.dirname(os.path.abspath(__file__))
d=json.load(open(os.path.join(S,"scorecard.json")))
W={p:v["weight"] for p,v in d["pillars"].items()}
caps={c["id"]:c for v in d["pillars"].values() for c in v["capabilities"]}
def overall(scores):
    tot=0
    for p,v in d["pillars"].items():
        cs=[scores[c["id"]] for c in v["capabilities"]]
        tot+= (100*sum(cs)/(4*len(cs)))*W[p]
    return round(tot/sum(W.values()),1)
def pillar_pct(scores,p):
    cs=[scores[c["id"]] for c in d["pillars"][p]["capabilities"]]
    return round(100*sum(cs)/(4*len(cs)),1)
base={cid:c["score"] for cid,c in caps.items()}
DATE="2026-09-02"
# ---------------- narrative (Fable-authored) ----------------
DREAM=("A place where young players share about themselves and get found by clubs and scouts, and have fans. "
       "Clubs track their players and analyze their growth with all the tools to improve players and the club. "
       "Scouts find and analyze players. Later: Patreon / BuyMeACoffee-style funding that makes supporters part-owners of grassroots clubs.")
SCALE=[("0","Missing","No code, no model, no route."),
       ("1","Designed / stub","A plan, a column, or a placeholder route. Nothing a user can do."),
       ("2","Built, unreachable","The backend works but the target user cannot use it: no button, flag off, admin-only, or an admin has to act every time."),
       ("3","Usable end-to-end","The target user can finish the job on at least one client in prod, with rough edges."),
       ("4","Complete","Every relevant client, tested, live, no known safety or correctness caveat.")]
BLOCKERS=[
 ("Self-made players are invisible.","Discovery, leaderboards, watchlists, follows and the contact rail all key on API-Football TrackedPlayer rows (scout.py:465, contact.py:419). A player who creates their own profile cannot be found, watched, or contacted. This is the dream's core subject.","1.4, 1.3, 1.7, 3.2"),
 ("Clubs cannot get in by themselves.","The visible club-claim button feeds a legacy claim that never grants the console (showcase.py:3109); the grant path needs an admin API key (funding.py:749) and is linked only from an approved program page. Prod has 0 clubs.","2.1, 2.6, 4.1"),
 ("No games or stats can be entered by people.","Season cells only accept provider sources (season_rollup.py:44); club matches store no result, minutes or goals (club.py:342). Growth analysis for anyone outside API-Football coverage is impossible.","1.3, 2.3, 2.5, 4.7"),
 ("Film Room is concierge.","A club's 'process' click only stamps a timestamp (club.py:601); an admin must queue CV, bind identities, run Qwen and finalize each upload, under a 3-lifetime-match quota (club.py:35). The worker has no managed deployment or alerts, and the nightly retention job is excluded from image updates (deploy.yml:224) so it runs a frozen build.","2.6, 5.4"),
 ("The front door is broken and unsafe.","Web tracked self-claims 400 because api.js:1403 omits the required contract_status (showcase.py:479); local self-claims accept minors (showcase.py:1371–1376, test_local_players.py:314) against decision D1; Film Room uploads carry no age/consent attestation; the web app has no delete, takedown or report control although the Terms promise one (only iOS has them).","1.1, 5.1, 5.7"),
 ("There is no money path.","No Stripe checkout, webhook, or /stripe route exists in the backend; the journalist subscribe box calls dead routes (SubscribeToJournalist.jsx:26). Scout Pro is copy plus an unused column. Donations are a registry without payment. Nothing about Patreon, BuyMeACoffee, or equity exists in code.","3.6, 4.2–4.5, 5.5"),
 ("Nobody is using it and nothing pulls them in.","9 accounts (5 are the team), 1 claim, 0 clubs, 0 intros, 0 revenue. Newsletters stopped 2026-04-21.","5.8"),
 ("Fans exist on web only:","follow + counts + share shipped (S2); iOS has no fan surface and local pages have no comments.","1.7"),
]
STAGES=[
 ("S0","Unbreak the front door","days",
  "Fix the web claim payload (send contract_status), add the age gate to local self-claims, bridge club claim → console grant without an admin API key, put the digest sender on the nightly job, fix the dead journalist /stripe box.",
  {"1.1":3,"2.1":3,"3.4":3}),
 ("S1","One player universe + a games grain","weeks",
  "Let local players into discovery/watchlists/contact/follows (shared subject id), and add a user-entered match row (player or club, provenance-labelled) that feeds the existing season cells. Show it in MyClub as a growth view.",
  {"1.3":3,"1.4":3,"2.3":3,"4.7":3,"2.5":3}),
 ("S2","Fans and reach","weeks",
  "Public follow for any account, fan counts on player pages, shareable player card with per-player og tags and a sitemap, trust-tiered auto-approval so edits stop hiding profiles, email notifications on the events that already exist.",
  {"1.7":3,"1.2":3,"5.3":3,"1.6":3}),
 ("S3","Money rails","weeks",
  "Stripe Checkout for Scout Pro at the committed price; club bundle subscription; donation checkout with donor-tip model once regulatory scoping is done; club-editable programs; Patreon/BuyMeACoffee link-out plus supporter import as the cheap first bridge.",
  {"4.1":3,"4.4":2,"4.6":3}),
 ("MS","money-safety (2026-09-05)","done",
  "independent audit 65.1%; 3 P1 + 3 launch blockers fixed; go-live (B2) projected next.",
  {}),
 ("B2","go-live prepaid GOL (review B2)","next",
  "Owner go-live checklist after the money-safety fixes: Stripe webhook endpoint + live GOL prices/credit envs, corrected prepaid-credit terms (VITE_BILLING_TERMS=1), then BILLING_ENABLED=1 with one real-card purchase + refund accepted; 3.6 and 5.5 return to 3 (review A1+B2, +1.2).",
  {"3.6":3,"5.5":3}),
 ("S4","Film Room self-serve + club tools","weeks–months",
  "Club-triggered processing with a monthly allowance instead of 3-lifetime, worker checkpointing and scheduling, coaching notes and shareable player reports, a manager-scoped club dashboard on the pathway data that already exists.",
  {"2.6":3,"2.7":3,"2.8":3,"5.4":3}),
 ("S5","Part-ownership","paper first",
  "Counsel decides the vehicle (crowd-equity is securities-regulated; a supporter-membership with governance perks may be the honest v1). Then recurring support tiers and the ownership ledger.",
  {"4.2":3,"4.3":3,"4.5":2}),
 ("S6","Ten real participants","ongoing",
  "The multiplier on everything above: pick one cohort (the Forest academy contact or one grassroots club), walk 10 real people through claim → console → intro by hand, instrument the funnel first.",
  {"5.8":3,"5.6":3}),
]
proj=[]; cur=copy.deepcopy(base)
for sid,name,when,what,targets in STAGES:
    for cid,sc in targets.items():
        if cid in cur and sc>cur[cid]: cur[cid]=sc
    proj.append((sid,name,when,what,targets,overall(cur),{p:pillar_pct(cur,p) for p in W}))
# ---------------- markdown ----------------
md=[]
md.append(f"# GRADING — How far is The Academy Watch from the dream? ({DATE})\n")
md.append(f"Parent: `CONTINUITY.md`. Method: three codex (gpt-5.6-sol, ultra) read-only code audits scored 31 capabilities 0–4 against the dream; two Fable adversarial reviewers re-verified every cite at origin/main `ade7bbc` and re-scored; Fable arbitrated. Prod counts measured read-only via the Supabase pooler. Raw evidence: session scratchpad `out-A/B/C.json`, `review-1/2.json`, merged `scorecard.json` (copied to `ledgers/research/dream-scorecard-{DATE}.json`).\n")
md.append("## The dream (graded against this)\n\n> "+DREAM+"\n")
md.append(f"## Headline\n\n**Built: {d['overall_pct']}%.** Weighted across five pillars. **Lived: ~0%.** Prod has 9 accounts (5 are the team), 1 claimed player, 0 clubs, 0 watchlists, 0 introductions, 0 revenue. The code is half a platform; the marketplace has no participants yet. Independently audited 2026-09-05 by gpt-6-astra (read-only, evidence-adjusted): `ledgers/research/astra-review-2026-09-05.md`.\n")
md.append("## Scale\n\n| Score | Label | Meaning |\n|---|---|---|")
for s,l,m in SCALE: md.append(f"| {s} | {l} | {m} |")
md.append("\nRule that decides most scores: backend-without-a-button is a 2, never a 3. Flag-off-in-prod is a 2. Admin-per-use is a 2.\n")
md.append("## Pillars\n\n| Pillar | Weight | Score |\n|---|---|---|")
for p,v in d["pillars"].items(): md.append(f"| {p} — {v['name']} | {v['weight']} | **{v['pct']}%** |")
for p,v in d["pillars"].items():
    md.append(f"\n### {p} — {v['name']} — {v['pct']}%\n")
    md.append("| # | Capability | Score | Reach | Blocker | Next step | Effort |\n|---|---|---|---|---|---|---|")
    for c in v["capabilities"]:
        cs=f"{c['score']}"+(f" (codex said {c['codex_score']})" if "codex_score" in c and c["codex_score"]!=c["score"] else "")
        md.append(f"| {c['id']} | {c['name']} | {cs} | {c.get('reach','-')} | {c.get('blocker','')} | {c.get('next_step','')} | {c.get('effort','-')} |")
md.append("\n## Blockers, ranked by how much of the dream they hold back\n")
for i,(t,w,ids) in enumerate(BLOCKERS,1): md.append(f"{i}. **{t}** {w} _(caps {ids})_")
md.append("\n## Steps to 100% — projected score after each stage (computed from the target scores, same weights)\n")
md.append(f"| Stage | Name | When | What | Overall after |\n|---|---|---|---|---|\n| — | Today | — | — | **{d['overall_pct']}%** |")
for sid,name,when,what,targets,o,pp in proj: md.append(f"| {sid} | {name} | {when} | {what} | **{o}%** |")
md.append(f"\nAfter S6 every remaining point is polish to 4s: iOS parity, E2E on the core journeys, tests, the U18 expansion (ROADMAP Phase 5). Reaching 100% means all 32 rows at 4 — that is the finished dream, not a launch bar. A credible launch bar is **S0–S2 done (~{proj[2][5]}%) plus S6 started**.\n")
md.append("## What is already strong (do not rebuild)\n")
for s in d.get("strong_already",[])[:10]: md.append(f"- {s}")
md.append("\n## Corrections to the 2026-08-23 platform review\n")
for s in d.get("surprises",[]): md.append(f"- {s}")
md.append(f"\n## Status\n\n- {DATE}: scorecard created (baseline **51.9%**).\n- {DATE} (later): **S0 executed and live** — PRs #957 (A), #958 (C), #960 (D), #961 (E hygiene), #959 (B); ACA job `job-scout-digest` created; prod `local_players.birth_date` pre-applied + stamped lp01. Re-scored rows 1.1, 2.1, 3.4 → 3 (see `ledgers/CONTINUITY_dream-s0.md`).\n- {DATE} (evening): **S1 executed and live** — PRs #963 (P1 games grain + pm01), #965 (P2 local players in the universe, negative ids), #968 (P3 club results), #964 (P4 web), #969 (P5 trust tiers + graduation/backfill); prod `SCOUT_INCLUDE_LOCAL_PLAYERS=1`. Re-scored rows 1.2, 1.3, 1.4, 2.3, 4.7 → 3 (see `ledgers/CONTINUITY_dream-s1.md`). Next: S2 (fans + reach).\n- {DATE} (night → 2026-09-03): **S2 executed and live** — PRs #978 (P0 foundation + s2f1), #983 (P1 fan follow/counts/events/signals/prefs), #980 (P2 share + sitemap + robots), #984 (P4 weekly activity email job), #979 (P3 web); prod `PUBLIC_API_BASE_URL` set, `alembic_version` s2f1 (now cb01 after #973), ACA job `job-profile-activity` created. Re-scored rows 1.6, 1.7, 5.3 → 3 (see `ledgers/CONTINUITY_dream-s2.md`). Next: S3 (money rails).\n")
md.append(f"- 2026-09-04: **S3 money rails — shipped dark 2026-09-04; actual = {d['overall_pct']}%.** Re-scored rows 3.6, 5.5, 4.1, 4.4, 4.6 → 3 (see `ledgers/CONTINUITY_dream-s3.md`).\n")
md.append("- 2026-09-05: **MS money-safety (2026-09-05): independent audit 65.1%; 3 P1 + 3 launch blockers fixed; go-live (B2) projected next.** Grade corrections from the independent gpt-6-astra review, Part 1 (`ledgers/research/astra-review-2026-09-05.md`): 3.6 3→2 and 5.5 3→2 (billing dark — the rail is complete and now includes the money-safety fixes from `ledgers/DIRECTIVE_money-safety.md`, shipped dark in #1028–#1030 with migration s3e1; becomes 3 at go-live per review B2), 2.7 1→2 (coaching briefs exist: club.py:879/:898, MyClubConsole.jsx:549). Stale evidence refreshed per the review: 1.2 (trust flag deployed in prod), 1.7 (iOS fan surface exists), 3.2 (locals are in discovery), 3.5 (not tracked-players-only), 4.4 (reach MISSING→LIVE_WEB), 5.4 (deploy.yml:225 includes the maintenance job). Every other score kept.\n")
open(os.path.join(S,"GRADING_dream-scorecard.md"),"w").write("\n".join(md))
json.dump({"stages":[{"id":s[0],"name":s[1],"overall_after":s[5],"pillars_after":s[6]} for s in proj]},open(os.path.join(S,"projection.json"),"w"),indent=1)
print("md written;", "projection:", [(s[0],s[5]) for s in proj])
