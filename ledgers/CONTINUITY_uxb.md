# UXB staging directory and opportunities polish

- Status: implementation complete; draft PR delivery next.
- Goal: P-01–P-07 and P-23 behind existing B1/B2 flags; draft PR, no merge.
- Base: main 784b1490; branch fix/staging-ux-opportunities.
- Constraints: foreground only; no migrations/dependency changes; minors/private applicant DTO invariants.
- Ownership: no UXM1/UXM2 files edited; P-02 uses their existing owner-only mount via the separate teaser component. App.jsx changes delimited.
- Done: public club opportunities; owner summary/home/menu; existing-application/age hints; signed-out auth gate; range/gender/email copy; mutually exclusive directory filters; published/activity-first recruiting.
- Gates: OSV547 clean; Ruff/check-format570; full flags-off pytest4083pass69skip0fail (900.09s), new focused8; Node222; lint0err189warn; build pass; Playwright65 + final extended real-rule2 pass.
- Screenshots: 60 PNGs, 1440×900/390×844 plus full-page variants; reviewed, no overflow.
- Cleanup: own5162/5212 stopped; aw_uxb dropped; dump/persona tokens/temp/browser/build outputs removed.
- Evidence: ~/codex-runs/aw-redesign/logs/UXB.final.md, logs/uxb/, shots/UXB/INDEX.md.
- Next: push and open draft PR against main; independent review, no merge.
