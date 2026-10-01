# Clubs near you (Phase 2 · B1) — read before enabling or touching the club directory

Dark behind `CLUB_DIRECTORY_ENABLED` (default off). With it off: `/clubs` is the Phase 1 teaser,
`GET /api/programs` and `POST /api/club-directory/search` answer exactly as an unrouted path did before
(GET/HEAD go to the app's catch-all, every other method gets its 405), no payload gains a key, a club
profile save ignores the new fields, and a console-local club still has no public page.

## The model in one screen

- **No new table.** Migration `p2b1` (after `p2a2`) adds seven nullable columns to
  `club_program_profile_revisions`: `venue_name`, `postcode`, `latitude`, `longitude`, `geocode_source`,
  `club_level` (`grassroots|amateur|semi_pro|professional`), `gender_programs` (JSON list of
  `men|women|boys|girls`), plus two CHECKs. Pre-apply SQL: `~/codex-runs/aw-redesign/p2b1_preapply.sql`.
- **The pin CHECK says `IS NOT NULL` on both sides on purpose.** A CHECK accepts UNKNOWN, so a bare
  range test lets a half-populated pin through. The migration and the pre-apply SQL drop and re-add that
  one constraint on every run, so a database that got the first draft ends up with the right one.
- **Moderated like the rest of the profile.** A club edits these in Club Home → Settings → Club profile;
  they are saved on the *pending* revision (`PUT /api/club/<id>/profile`, body key `directory`). The public
  only ever reads the **approved** revision, so nothing changes until an admin approves it in the existing
  profile-revision review (`/admin/funding`), which now shows the fields and a "check it on a map" link.
- **A save without `directory` never erases the location.** A new draft starts from the approved
  location (`carry_directory_forward`); `directory: null` clears it (still subject to review). This also
  protects clients that do not know the fields (and every save while the flag is off).
- **`revision_dict` is untouched.** Routes use `club_directory.revision_payload`, which equals
  `revision_dict` while the flag is off and adds a `directory` object while it is on.
- **An approval never publishes what the reviewer could not see.** While the flag is off the review
  payloads hide these fields, so `settle_directory_on_approval` makes an approved revision keep the
  location that was already approved (or none). A club's location edit that was pending across a flag-off
  approval is dropped, not promoted: the club sends it again once the flag is back on.
- **Who may edit:** `PUT /api/club/<id>/profile` needs the `branding` capability — owner and manager
  only. A coach/analyst/viewer never has it, including with "all squads" (A2: that widens the squad list,
  never the gates).
- **Club text is bounded before it is decoded.** `_clean_text` refuses input over 4× the field limit and
  decodes HTML entities at most three passes; deeper nesting is a 400, not CPU time.

## Who is listed — `services/club_directory.directory_eligibility`

Approved program · not emergency-hidden · with an **active manager whose source claim is approved** ·
and, **only when the club sits under a real funding league**, that league has `registry_status =
'approved'`.

- **Console-local clubs are listed** (orchestrator decision, 2026-10-01). Clubs that came in through the
  club-claim bridge sit on the reserved "Console (unlisted)" league, which is never an approved funding
  league; they are exactly the clubs being onboarded, so the league check does not apply to them. They
  still need everything else. A club under a real league that is proposed/rejected is not listed.
- The console league is plumbing: a console club's card and page carry `league: null`, never its name.
- It deliberately does **not** use `ClubProgram.is_verified_program`: that property means "payments are
  set up" for US clubs. A US club with no Stripe account is listed; do not "simplify" this back.
- **Every card opens, and the page obeys the same rule.** While the flag is on,
  `GET /api/programs/<slug>` also serves a listed console-local club (flag off it is a 404, as before),
  and `program.directory` is the list's predicate for one club (`is_listed`): a club whose manager was
  revoked or whose claim was rejected gets `directory: null` (a console-local club's page becomes a 404;
  the legacy registry page of a club in an approved league is otherwise unchanged).
- Emergency hide (A1) removes a club from the list, search, radius results and counts on the next
  request; lifting restores it. Responses are `Cache-Control: no-store`.

## What the public payload may contain

`club_card` is the single projection and an explicit allowlist: club identity, colours, place, league
name, approved venue/level/programmes/age groups/activities, **an aggregate `squad_count`**, optional
`distance_km`, optional `open_opportunities` (only if B2's `services.opportunities.open_opportunity_counts`
exists). Never add roster, staff, squad names, banners or anything about a person — of any age — here.

## A visitor's position and search words never go in a URL

A URL is written to the server's access log (gunicorn logs the request line), kept in browser history
and stored by product analytics as the page path. So:

- **Searches go in a request body.** `POST /api/club-directory/search` takes the whole search as JSON.
  `GET /api/programs` refuses `q`, `lat`, `lng` and `radius_km` with a 400 so no client can drift back.
- **The page URL carries only `for` and `level`.** The search box and the position are React state; a
  `q` left in an old link is not run and is removed from the address bar.
- **Analytics keeps an allowlist on `/clubs`.** `lib/track.js` and, for older clients, `routes/events.py`
  drop every query param on a `/clubs` path or referrer except `for` and `level`.
- The position is read from the browser only when the visitor presses "Use my location", rounded to two
  decimals (~1 km) before it is sent, and never stored. Responses do not echo it.

## Distance, without a map provider

- Clubs type their own coordinates (or paste "lat, lng" from a maps app). No geocoding, no paid provider.
  No coordinates → the club is still listed, with "distance unavailable".
- `lat`+`lng` sorts nearest-first (clubs without a pin last, then name, then id, so pages never repeat or
  skip a club); `radius_km` (1–250) keeps only pinned clubs in range.
- **The SQL distance is exact great-circle.** `_haversine_term` is `hav(d/R)` — it needs only `sin` and
  `cos`, rises with distance over the whole globe (poles and the antimeridian included), and a radius is
  `<= sin(r/2R)²`. It decides membership, counts and order before pagination; the kilometres shown are
  the same haversine, computed for the page's rows. Postgres has the functions; on SQLite (tests, local)
  `_sqlite_trig` registers them. Do not swap in a flat approximation: it dropped clubs near the poles.
- The "map" is a north-up plot of the real coordinates to one scale, with an OpenStreetMap link per
  club. No tiles are loaded and nothing is sent to a third party unless the visitor follows that link.

## API

Both anonymous, one shared budget of 60/min per IP, `Cache-Control: no-store`, bad input → 400 `{error}`.

- `GET /api/programs`: `country`/`region`/`city` (exact, case-insensitive — both sides folded by the
  database), `level`, `programme` (comma lists, any-of), `page` (≤100), `per_page` (≤50, default 20).
- `POST /api/club-directory/search` (JSON body ≤ 2 kB, else 413 — a cap on the request stream itself, so chunked
  bodies with no `Content-Length` are cut off at 2049 bytes too, never buffered): all of the above (`level`/`programme`
  may be lists) plus `q` (2–80 chars, LIKE-escaped; matches name, city, region, approved venue and
  postcode), `lat`,`lng` (numbers), `radius_km` (1–250).

`GET /api/programs/<slug>` gains `program.directory` (object, or `null` when the club is not listed) and
`/api/features` gains `club_directory: true` only while the flag is on.

## Tests that pin this

`tests/test_club_directory.py` (eligibility incl. hidden/console-local/unapproved league/US, the real
claim bridge end to end, exact card allowlist with minors and staff seeded, approval-only promotion,
flag-off approval, search escaping, great-circle radius/order/pagination, access-log and analytics
privacy, input bounds, flag-off parity for every method),
`academy-watch-frontend/tests/club-directory.test.mjs`, `e2e/club-directory.spec.mjs`.
