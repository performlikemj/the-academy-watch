# N2 — hide legacy public pages

- Goal: Redirect and unlink 14 legacy public routes; retain components/data and player lookup, admin/writer/curator tools.
- State: implementation and verification complete; remote PR delivery next.
- Constraints: feat/hide-legacy-pages; aw_n2; backend 5131 / Vite 5194; no background commands; non-draft PR to main; no merge.
- Gates: lint/build/Node/relevant Playwright; Ruff/pytest sitemap; reviewed home/player desktop/mobile shots in external shots/N2.
- Next: central route gate, unlink public surfaces, de-index, tests, cleanup, commit/push/PR, BUS DONE.
- Done: route redirect gate + guarded lazy external page imports; noindex through replacement redirect; player writer coverage and request removed; global search is players only and suppresses old hidden recents; settings writer profiles plain text; newsletter markdown web CTA removed; club roster promotion removed; GOL markdown hidden links plain text; public robots disallows legacy collections; sitemap skips legacy enumeration and strips cached legacy URLs.
- Tests: OSV scan passes; lint 0 errors (183 existing warnings); build passes; 195 Node pass; 15 sitemap pytest pass; Ruff check/format pass. Relevant Playwright running.
- Isolation: aw_n2 cloned from soccer_newsletter, confirmed DB name and ch02 revision, upgraded to p2a1; own foreground server sessions on 5131/5194.
- Final gates: lint 0 errors / 183 existing warnings; build passes (existing chunk-size warning); 195 Node pass; 53 relevant Playwright pass; final N2 24 pass + six fixture/GOL/settings rechecks pass; 19 sitemap + publication-hold pytest pass (91 deselected); whole-backend Ruff check/format pass. No separate frontend typecheck script exists (JSX project).
- Existing hidden-page E2E cases retained with exact skip reason `legacy page hidden 2026-10-01`: two user flow cases, journalist public profile onboarding case, submit-take + two admin cases dependent on that public submission.
- Screenshots: six visually reviewed PNGs in `~/codex-runs/aw-redesign/shots/N2/`: home + fixture player + live copied-DB player, each 1440×900 and 390×844. Live `/players/148099` displays K. Dewsbury-Hall; no hidden anchors.
- Link inventory removed: player writer-author profiles and recent writeups (entire Writer Coverage); global search Teams/Newsletters/Journalists shortcuts, team/newsletter/writer/writeup results and their saved recents; settings followed-writer profile links/arrows; club Squad & academy team-roster promotion; admin newsletter markdown full-web-newsletter CTA; GOL hidden-route markdown anchors now plain text. Home/header/footer and player team labels already had no hidden anchors; GOL suggestion chips submit prompts and have no route links.
- Cleanup: both owned foreground servers stopped; aw_n2 dropped; copied backend .env and all /tmp/n2-* artifacts removed. Worktree retained; no simulator started.
