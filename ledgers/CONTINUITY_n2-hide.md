# N2 — hide legacy public pages

- Goal: Redirect and unlink 14 legacy public routes; retain components/data and player lookup, admin/writer/curator tools.
- State: complete; non-draft PR #1112 to main: https://github.com/performlikemj/the-academy-watch/pull/1112.
- Constraints: feat/hide-legacy-pages; aw_n2; backend 5131 / Vite 5194; no background commands; non-draft PR to main; no merge.
- Gates: lint/build/Node/relevant Playwright; Ruff/pytest sitemap; reviewed home/player desktop/mobile shots in external shots/N2.
- Next: PR review; no merge authorized in this lane.
- Done: route redirect gate + guarded lazy external page imports; legacy-path noindex before replacement redirect (fixed round 3); player writer coverage and request removed; global search is players only and suppresses old hidden recents; settings writer profiles plain text; newsletter markdown web CTA removed; club roster promotion removed; GOL markdown hidden links plain text; public robots permits legacy crawling (fix round 1); sitemap skips legacy enumeration and strips cached legacy URLs.
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

## Fix round 2

- State: complete; fix pushed and inline reply / @codex review posted.
- Now: PR #1112 awaits fresh review; no merge.
- Next: lead review of PR #1112; no merge in this lane.
- Constraints: newsletter sending/freeze/content unchanged; player/settings links retained; True restores prior URLs; no background commands.
- Done: moved backend LEGACY_PUBLIC_PAGES to utils/legacy_pages.py; sitemap enumeration and cached XML filtering share it. API newsletter web/submit links and canonical/OG URL, digest HTML/text read-more, weekly commentary snippets, both Reddit routes + markdown renderer, public-program team-page link and generated GOL PDF team anchors use legacy_public_url.
- Template audit: newsletter_email.html and newsletter_digest_email.html already guard all CTA blocks on a truthy URL; no template edits needed for those links. newsletter_web.html now omits absent og:url. Player/settings/unsubscribe/API links and editorial content unchanged.
- Audit: src/ all files searched for seven hidden route roots, plus URL/share/RSS/push callsites. Player share surfaces emit /p + /players + /local-players; scout/profile activity/trust/outbox emails emit player/watchlist/club/auth paths. No RSS/push emitter found. Other matches: API endpoint decorators, provider team-image paths, comments/docs, old src/static/assets client bundle; no compiled artifact edits.
- Tests: false/true render and actual mocked delivery assertions for individual/digest/snippet HTML/text, newsletter metadata, cached/fresh sitemap, Reddit auto/manual posts, public-program URL and GOL export template; no real provider sends. Initial local tests needed the same placeholder OPENAI_API_KEY as CI; fixtures corrected to valid funding model values and Reddit adapter mocked (local PRAW absent).
- Gates: full pytest 3273 passed / 47 skipped (offline CI placeholder key); final focused render/emitter suite 117 passed, including the two GOL PDF template cases added after full-suite collection. Final extra-emitter suite 24 passed. Node 197 passed. Whole-backend Ruff check/format (534 files) and git diff --check pass. Backend-only change; no frontend dependency restore, lint/build not required this round.
- Cleanup: no servers, DBs, copied env or provider sends; temporary emitter audit moved to external logs and removed. Worktree retained.
- Delivery: fix 1c26b269c5274f05b6ea2dd2f04a962182c17392 pushed; inline finding discussion_r4151061526 replied as discussion_r4151175737; @codex review issuecomment-5923385347; PR description refreshed. No merge. Hand-back ~/codex-runs/aw-redesign/logs/N2F2.final.md. BUS DONE after final ledger push.

## Fix round 3

- State: complete; fix pushed and inline P1 replied; PR description includes SWA redirects and post-deploy curl check.
- Now: PR #1112 awaits fresh review; final ledger push precedes @codex review request.
- Next: lead review and deployed HTTP verification; no merge in this lane.
- Constraints: no background commands; no dependency changes; backend remains unchanged unless audit identifies a dependency.
- Done: noindex depends only on current legacy pathname; Navigate carries no redirect state. Home and all tested non-legacy pages have no robots meta, including old persisted redirect state.
- Done: 11 Azure SWA 301-to-/ rules: /dream-team; /academy + /academy/*; /teams + /teams/*; /newsletters + /newsletters/*; /journalists + /journalists/*; /writeups/*; /submit-take. Original fallback/excludes, asset-cache rule and security headers retained. Built dist config matches source byte-for-byte.
- Tests: Node config parsing/pattern agreement derived from LEGACY_PUBLIC_ROUTES, every hidden route + deep wildcard samples, protected operational/account/share paths, static assets and look-alikes; browser all 14 direct redirects + all 14 in-app redirects, direct home desktop/mobile, stale redirect state, noindex absence on active routes.
- Audit: workflow bakes https://api.theacademywatch.com/api and deploys only frontend dist to SWA; main.py registers share_bp on Flask API host, serving /p/<id> and /p/<id>/card.png, sitemap/robots. public_share_origin defaults to API origin; runtime override UNCONFIRMED (no production config accessed). Email unsubscribe /subscriptions/unsubscribe/<token>, one-click /api/subscriptions/one-click-unsubscribe/<token>, API verify /api/verify/<token>, SPA /verify, /manage, /unsubscribe, /settings and auth paths are outside redirects. Prior backend legacy URL gate covers hidden email/OG emitters; no backend edits required.
- Gates: OSV clean, frozen dependencies already installed (no restore/lockfile change); lint 0 errors / 181 existing warnings; build pass (existing chunk-size warning); 200 Node pass; legacy Playwright 29 pass (43.2s); git diff --check pass. No separate JSX typecheck script. Ruff/pytest not rerun because backend unchanged this round.
- Cleanup: owned foreground Vite on 5194 stopped; generated Playwright reports/test-results removed. No backend/DB/env/tmp/simulator/provider/prod work. Build output retained for redirect-config inspection.
- Delivery: code fix d9ccb5a23a7716a871058801fa62e245ba3f8b67 pushed; inline P1 discussion_r4151200839 replied as discussion_r4151278405; PR body refreshed. Final head/review-request receipt and BUS DONE recorded in external ~/codex-runs/aw-redesign/logs/N2F3.final.md after ledger push. No merge.
