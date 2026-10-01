# Clubs near you (Phase 2 · B1) — read before enabling or touching the club directory

Dark behind `CLUB_DIRECTORY_ENABLED` (default off). With it off: `/clubs` is the Phase 1 teaser,
`GET /api/programs` answers exactly as an unrouted path did before (it hands the request to the app's
catch-all), no payload gains a key, and a club profile save ignores the new fields.

## The model in one screen

- **No new table.** Migration `p2b1` (after `p2a2`) adds seven nullable columns to
  `club_program_profile_revisions`: `venue_name`, `postcode`, `latitude`, `longitude`, `geocode_source`,
  `club_level` (`grassroots|amateur|semi_pro|professional`), `gender_programs` (JSON list of
  `men|women|boys|girls`), plus two CHECKs. Pre-apply SQL: `~/codex-runs/aw-redesign/p2b1_preapply.sql`.
- **Moderated like the rest of the profile.** A club edits these in Club Home → Settings → Club profile;
  they are saved on the *pending* revision (`PUT /api/club/<id>/profile`, body key `directory`). The public
  only ever reads the **approved** revision, so nothing changes until an admin approves it in the existing
  profile-revision review (`/admin/funding`), which now shows the fields and a "check it on a map" link.
- **A save without `directory` never erases the location.** A new draft starts from the approved
  location (`carry_directory_forward`); `directory: null` clears it (still subject to review). This also
  protects clients that do not know the fields (and every save while the flag is off).
- **`revision_dict` is untouched.** Routes use `club_directory.revision_payload`, which equals
  `revision_dict` while the flag is off and adds a `directory` object while it is on.

## Who is listed — `services/club_directory.directory_eligibility`

Approved program · not emergency-hidden · in a league with `registry_status = 'approved'` · with an
**active manager whose source claim is approved**. That is the same public base as
`GET /api/programs/<slug>` (every card has a page to open) plus the manager check.

- It deliberately does **not** use `ClubProgram.is_verified_program`: that property means "payments are
  set up" for US clubs. A US club with no Stripe account is listed; do not "simplify" this back.
- Clubs on the **"Console (unlisted)" league are not listed.** Clubs that came in through the club-claim
  bridge sit on that league, which the code keeps permanently unlisted (their `/programs/<slug>` page is
  also a 404). They appear once admitted to a listed league. Changing that is a product decision.
- Emergency hide (A1) removes a club from the list, search, radius results and counts on the next
  request; lifting restores it. Responses are `Cache-Control: no-store`.

## What the public payload may contain

`club_card` is the single projection and an explicit allowlist: club identity, colours, place, league
name, approved venue/level/programmes/age groups/activities, **an aggregate `squad_count`**, optional
`distance_km`, optional `open_opportunities` (only if B2's `services.opportunities.open_opportunity_counts`
exists). Never add roster, staff, squad names, banners or anything about a person — of any age — here.

## Distance, without a map provider

- Clubs type their own coordinates (or paste "lat, lng" from a maps app). No geocoding, no paid provider.
  No coordinates → the club is still listed, with "distance unavailable".
- The visitor's position comes from the browser only when they press "Use my location", is rounded to
  two decimals (~1 km) before it is sent, lives in memory only (never the URL, storage or database).
- `lat`+`lng` sorts nearest-first (clubs without a pin last); `radius_km` (1–250) keeps only pinned clubs
  in range. The SQL distance is trig-free so it runs on SQLite and Postgres alike (flat projection with
  the east-west scale at the mid latitude; within 250 km it is within a fraction of a percent of
  great-circle). The distance shown to people is exact haversine, computed for the page's rows.
- The "map" is a north-up plot of the real coordinates to one scale, with an OpenStreetMap link per
  club. No tiles are loaded and nothing is sent to a third party unless the visitor follows that link.

## API

`GET /api/programs` (anonymous, 60/min per IP): `q` (2–80 chars, LIKE-escaped; matches name, city,
region, approved venue and postcode), `country`/`region`/`city` (exact, case-insensitive), `level`,
`programme` (comma lists, any-of), `lat`,`lng`,`radius_km`, `page` (≤100), `per_page` (≤50, default 20).
Bad input → 400 `{error}`. `GET /api/programs/<slug>` gains `program.directory` and `/api/features`
gains `club_directory: true` only while the flag is on.

## Tests that pin this

`tests/test_club_directory.py` (eligibility incl. hidden/unlisted/US, exact card allowlist with minors
and staff seeded, approval-only promotion, search escaping, distance, pagination bounds, flag-off parity),
`academy-watch-frontend/tests/club-directory.test.mjs`, `e2e/club-directory.spec.mjs`.
