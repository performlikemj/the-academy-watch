# N2 — hide legacy public pages

- Goal: Redirect and unlink 14 legacy public routes; retain components/data and player lookup, admin/writer/curator tools.
- State: complete; non-draft PR #1112 to main: https://github.com/performlikemj/the-academy-watch/pull/1112.
- Constraints: feat/hide-legacy-pages; aw_n2; backend 5131 / Vite 5194; no background commands; non-draft PR to main; no merge.
- Gates: lint/build/Node/relevant Playwright; Ruff/pytest sitemap; reviewed home/player desktop/mobile shots in external shots/N2.
- Next: PR review; no merge authorized in this lane.
- Done: route redirect gate + guarded lazy external page imports; noindex through replacement redirect; player writer coverage and request removed; global search is players only and suppresses old hidden recents; settings writer profiles plain text; newsletter markdown web CTA removed; club roster promotion removed; GOL markdown hidden links plain text; public robots permits legacy crawling (fix round 1); sitemap skips legacy enumeration and strips cached legacy URLs.
- Tests: OSV scan passes; lint 0 errors (183 existing warnings); build passes; 195 Node pass; 15 sitemap pytest pass; Ruff check/format pass. Relevant Playwright passed (see final gates).
- Isolation: aw_n2 cloned from soccer_newsletter, confirmed DB name and ch02 revision, upgraded to p2a1; own foreground server sessions on 5131/5194.
- Final gates: lint 0 errors / 183 existing warnings; build passes (existing chunk-size warning); 195 Node pass; 53 relevant Playwright pass; final N2 24 pass + six fixture/GOL/settings rechecks pass; 19 sitemap + publication-hold pytest pass (91 deselected); whole-backend Ruff check/format pass. No separate frontend typecheck script exists (JSX project).
- Existing hidden-page E2E cases retained with exact skip reason `legacy page hidden 2026-10-01`: two user flow cases, journalist public profile onboarding case, submit-take + two admin cases dependent on that public submission.
- Screenshots: six visually reviewed PNGs in `~/codex-runs/aw-redesign/shots/N2/`: home + fixture player + live copied-DB player, each 1440×900 and 390×844. Live `/players/148099` displays K. Dewsbury-Hall; no hidden anchors.
- Link inventory removed: player writer-author profiles and recent writeups (entire Writer Coverage); global search Teams/Newsletters/Journalists shortcuts, team/newsletter/writer/writeup results and their saved recents; settings followed-writer profile links/arrows; club Squad & academy team-roster promotion; admin newsletter markdown full-web-newsletter CTA; GOL hidden-route markdown anchors now plain text. Home/header/footer and player team labels already had no hidden anchors; GOL suggestion chips submit prompts and have no route links.
- Cleanup: both owned foreground servers stopped; aw_n2 dropped; copied backend .env and all /tmp/n2-* artifacts removed. Worktree retained; no simulator started.
- Delivery: implementation commit e42f47dc pushed to feat/hide-legacy-pages; PR #1112 open against main; no merge. BUS DONE appended; all N2 claims released.

## Fix round 1

- State: complete; fixes pushed and both inline findings replied to; @codex review requested.
- Now: PR #1112 awaits fresh review; no merge.
- Next: lead review of PR #1112; no merge in this lane.
- Done: Settings uses existing unsubscribeFromJournalist(follow.journalist_id), per-card pending/disabled state + accessible Unfollow name + inline alert/retry; removes only the succeeded follow and hides the empty section.
- Done: removed all seven legacy Disallow lines; sitemap exclusion, noindex and redirects retained; updated robots regression.
- Email audit: no unsubscribe/manage link targets /journalists/... or /newsletters/... in checked templates/routes/services/weekly-agent. Route/weekly manage uses PUBLIC_MANAGE_PATH (default /manage); token unsubscribe uses /subscriptions/unsubscribe/<token> and one-click /api/subscriptions/one-click-unsubscribe/<token>. Found separate dead digest manage /subscriptions (no SPA route) and changed it to /settings; templates unchanged. Deployment overrides UNCONFIRMED, no production configuration accessed.
- Gates: lint 0 errors / 181 warnings; build passes (existing size warning); Node 197 pass; Playwright 27 pass (four Settings success/pending/error/retry checks at 1440/390, plus all legacy route/link cases); Ruff check/format all 532 backend files pass; digest/subscriptions pytest 26 pass. No separate frontend typecheck script exists; no dependency restore or lockfile changes.
- Evidence: visually reviewed synthetic Settings follow screenshots settings-following-desktop.png (1440px) and settings-following-mobile.png (390px) in external shots/N2; no horizontal overflow.
- Cleanup: owned foreground Vite stopped; no backend server/DB/env/temp files created this round; generated Playwright report/test-results removed. Worktree retained.
- Delivery: fix commit ff486d1ca8a2670196204f798231bb9402818e8e pushed. Inline replies discussion_r4151045454 (P1) and discussion_r4151045580 (P2); @codex review issuecomment-5923115483. PR description refreshed; no merge. Hand-back ~/codex-runs/aw-redesign/logs/N2F1.final.md.
