# M1 determination

- No persistent app UX glitch (ii) was reproduced.
- Direct inspection of both PNGs cited in the verdict shows the Home navigation
  title and the visibly selected Home tab. This conflicts with the review's
  description; a capture/settle timing incident (i) was not itself reproduced.
- Applied the requested (i)-style assertion hardening: native isSelected alone
  is insufficient; require hittability, a nonempty onscreen frame, and visible,
  hittable Home navigation chrome. Wait for this state before settling, capture,
  then recheck it.
- Production app source is unchanged from 3cd3c29. The isolated stronger-runner
  test on that app passed 16/16 steps, before the inventory/journey extensions.
- Fresh full GREEN also passes and its named screenshot visibly includes both
  the selected native Home tab and Home title.

Diagnostic run tail (unchanged app, strengthened runner):

```text
stories-proof: {"proven":1,"unproven":5,"failing":0,"judged":0,"contradicted":0,"confusing":0}
sim-report: PASS (16 steps; 0 observed; 0 proposals; 0 recommendations)
TOTAL steps=16 ok=16 pass=0 concern=0 fail=0 ungraded=16 observed=0
exit 0
```

Fresh evidence: `green-88f013a/shots/change-home-changes-home__009-home-selected-for-player.png`.
