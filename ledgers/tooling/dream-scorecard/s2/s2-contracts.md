# S2 HTTP + module contracts (shared by P0–P4; frontend builds against these with mocks)

All player ids below are SIGNED logical ids (`player_api_id`; negative = local player). "Neutral 404" =
`{"error":"Player not found"}` with status 404, byte-identical for minor / suppressed / pending / unknown.

## Module contract (P0 provides; P1, P2, P4 consume — exact names)
- `src/services/public_player_subject.py`
  - `resolve_public_adult_subject(signed_id) -> PlayerSubject | None` (None for bool/0/None/non-int and for
    `abs(id) > 2147483647`; None if suppressed in either namespace — including ANY `LocalPlayer` whose
    `api_player_id == signed_id` being suppressed; None unless known adult)
  - `owned_public_adult_subjects(user_account_id: int) -> list[PlayerSubject]` (approved
    `relationship_type='player'` claims in BOTH namespaces → signed ids → each through the gate; deduped,
    sorted by signed_id)
  - `user_owns_subject(user_account_id: int, signed_id: int) -> bool` (one query, no gate)
  - `owner_account_ids_subquery(signed_id)` → SQLAlchemy subquery of `user_accounts.id` holding an approved
    player claim on that subject in either namespace (used to exclude owners from counts/is_fan)
- `src/services/reach_metrics.py` (pure query helpers, dialect-neutral; owners of the subject are ALWAYS excluded)
  - `fan_counts(signed_ids, *, since=None, exclude_user_ids=()) -> dict[int, tuple[int, int]]`  (total, added_since)
  - `watchlist_counts(signed_ids, *, since, exclude_user_ids=()) -> dict[int, tuple[int, int]]`  (distinct accounts; total, added_since)
  - `profile_view_counts(signed_ids, *, now=None) -> dict[int, dict[str, int]]`  → `{"last_7_days": n, "last_30_days": n}`
  - `profile_view_counts_since(signed_ids, *, since, now=None) -> dict[int, int]`
  - `is_fan(user_account_id, signed_id) -> bool`
- `src/models/player_fan.py`: `PlayerFan(id, user_account_id FK user_accounts.id ON DELETE CASCADE, player_api_id, created_at)`;
  `UniqueConstraint(user_account_id, player_api_id) uq_player_fans_user_player`; `Index ix_player_fans_player_created (player_api_id, created_at)`; CHECK `player_api_id <> 0`.
- `UserAccount.profile_activity_email_opt_in: bool (default False)`, `UserAccount.profile_activity_email_last_sent_at: datetime | None (naive UTC)`.
- Migration `s2f1` (down `pm01`): the table above (+ `ENABLE ROW LEVEL SECURITY`, no policies) and the two columns.

## P1 routes (players_bp is registered under `/api`)
### GET /api/players/<signed id>/followers/count — anonymous; optional Bearer
200 `{"player_api_id": <signed int>, "fans": <int>, "following": <bool|null>, "share_url": "<absolute url, always a string>"}`
- `following` = true/false for a valid Bearer, null when anonymous OR when the Bearer is malformed/expired/stale
  (optional-auth pattern of `routes/player_matches.py:58-63`; never 401 here).
- `share_url` = `<PUBLIC_API_BASE_URL>/p/<signed id>` (env required in prod; dev/test fallback `request.url_root`).
- Neutral 404 for every non-public subject. No extra rate limit (public cheap read; the limiter keys on the
  ingress address in prod — a per-route limit would be one global bucket).

### POST /api/players/<signed id>/follow — `@require_user_auth`, 30/minute per user
201 `{"player_api_id": ..., "following": true, "fans": <int>, "created": true}` on first insert;
200 same shape with `"created": false` on repeat (idempotent).
- Neutral 404 for non-public subjects (checked FIRST). Then 400 `{"error":"You cannot follow your own profile"}`
  when the caller owns the subject. 401 no/invalid Bearer.
- Server records a `product_events` row `fan_follow_added` (user_email = caller, props `{"player_api_id": id}`)
  in the same transaction, only when a row was actually created.

### DELETE /api/players/<signed id>/follow — `@require_user_auth`, 30/minute
200 `{"player_api_id": ..., "following": false, "deleted": <bool>}` — always this shape; deletes ONLY the
caller's own row; never resolves the subject. Records `fan_follow_removed` only when a row was deleted.

### POST /api/events (existing; P1 extends)
- ALLOWED_EVENTS += `profile_view` ONLY (`follow_removed` is NOT added; `fan_follow_*` are server-only names).
- `profile_view`: after syntactic validation (props dict with `player_api_id` non-bool nonzero int) the event
  COUNTS toward `accepted` whether or not the gate passes; gate failure only prevents persistence. Persisted rows
  have `user_email=None, session_id=None, path=None, referrer=None` and props exactly `{"player_api_id": <int>}`.
  A one-event batch for a public adult and for a minor return byte-identical 202 bodies.

### GET /api/showcase/mine/interest-signals (existing; P1 extends; iOS reads it — keep old fields)
200 `{"week_start": iso, "interest_signals": [ { "player_api_id": <signed>, "watchlists": {"total","added_this_week"},
 "follows": {"total","added_this_week"}, "fans": {"total","added_this_week"}, "profile_views": {"last_7_days","last_30_days"} } ]}`
- Subjects = `owned_public_adult_subjects(user.id)` (adds local/negative claims; unsafe subjects omitted).
- Accounts blocked by the owner are excluded from watchlists/fans counts (existing `blocked_user_ids`).

### GET/PATCH /api/user/email-preferences (existing; P1 extends)
GET 200 `{"user_id", "email_delivery_preference": "individual|digest", "profile_activity_email_opt_in": <bool>}`
PATCH body must be a JSON object with at least one supported field: `email_delivery_preference` (validated only
when present, must be a string in the allowed set) and/or `profile_activity_email_opt_in` (literal bool);
arrays/numbers/empty/unknown-only → 400; response = GET shape.

### Account export / delete (existing; P1 extends)
- Export includes `"fan_follows": [{"player_api_id", "created_at"}]` and `"profile_activity_email_opt_in"`.
- Delete removes the account's `player_fans` rows explicitly (do not rely on DB cascade alone; tests are SQLite).

### Identity lifecycle (existing; P1 extends)
- Local→API graduation and local merge re-key `player_fans` rows from the old signed id to the new one,
  collision-safe (a user already a fan of the target keeps one row; the source row is deleted), in the same
  transaction as the existing `_rekey_watchlists` / merge helpers. `product_events` props are telemetry and are not re-keyed.

## P2 routes (root-level `share_bp`, NO `/api` prefix, registered in `src/main.py`)
### GET /p/<signed id> — anonymous, `Cache-Control: no-store`
200 text/html: `<title>`, `<meta name=description>`, `<link rel=canonical href="{PUBLIC_BASE_URL}/players/<id>">`
(or `/local-players/<local id>` for negatives), og:type=profile, og:title, og:description, og:url (= THIS share
URL on the API origin), og:site_name, og:image (= absolute card.png URL on the API origin), og:image:width=1200,
og:image:height=630, twitter:card=summary_large_image, twitter:title/description/image, then
`<meta http-equiv="refresh" content="0; url={canonical}">` and a visible `<a href={canonical}>` link.
No inline `<script>` (CSP). All subject text HTML-escaped. Neutral 404 (JSON body, same as API) for non-public.
`GET /p/<anything non-integer>` (e.g. `/p/abc`, `/p/`) → the same neutral 404 (explicit catch route, never the SPA shell).
### GET /p/<signed id>/card.png — anonymous, `Cache-Control: no-store`
200 image/png exactly 1200×630, rendered in memory with Pillow + Inter/Manrope fonts found in this order:
repo `academy-watch-backend/fonts/`, then `/usr/share/fonts/truetype/theacademywatch/` (the Docker image path),
then Pillow default (tests assert a bundled font was selected). Content: name, position, club (precedence:
`LocalPlayer.club_name` → `TrackedPlayer.current_club_name` → `PlayerShadow.current_club_name`), a source chip
("Tracked player" for positives / "Community player" for locals), brand mark text "The Academy Watch". NO season
line (there is no reusable season-stats service). Deterministic bytes for identical inputs. Neutral 404 for non-public.
### GET /sitemap.xml — anonymous, `Cache-Control: no-store`; in-process cache 1h (`clear_sitemap_cache()` for tests)
200 application/xml (sitemaps.org urlset): `{PUBLIC_BASE_URL}/`, player URLs (`/players/<id>` for positives,
`/local-players/<local id>` for negatives), team URLs (`/teams/<TeamProfile.slug>` for non-empty slugs whose
`team_id` has a matching `Team`, as `resolve_team_by_identifier` does), published newsletters
(`/newsletters/<public_slug>`), programs (`/programs/<slug>` with EXACTLY the three predicates of
`routes/funding.py:_public_program_by_slug`: `platform_status='approved'`, `emergency_hidden IS FALSE`, joined
`FundingLeague.registry_status='approved'`). Player candidates come from a cheap SQL prefilter (active
`TrackedPlayer` not `owning-club`, and approved/unmerged `LocalPlayer` with negative `api_player_id`, both
`without_active_suppression`), ordered by id, capped at 2000 candidates — and EVERY emitted player id is passed
through `resolve_public_adult_subject` immediately before emission; failures are skipped silently. No string
`birth_date` comparisons in SQL (`TrackedPlayer.birth_date` is `String(20)`).
### GET /robots.txt — anonymous
`User-agent: *` / `Allow: /p/` / `Disallow: /api/` / `Sitemap: {PUBLIC_API_BASE_URL}/sitemap.xml`.
Frontend static `academy-watch-frontend/public/robots.txt`: `User-agent: *` / `Allow: /` /
`Sitemap: https://api.theacademywatch.com/sitemap.xml`; add `/robots.txt` to the SWA `navigationFallback.exclude`.

## P4 job contract
`python /app/src/jobs/run_profile_activity_notifications.py [--dry-run]` (the ACA job sets `PYTHONPATH=/app`
exactly like `job-scout-digest`; also support `python -m src.jobs.run_profile_activity_notifications`).
Env `PROFILE_ACTIVITY_DRY_RUN=1|true|yes|on` forces dry-run; env `PROFILE_ACTIVITY_MAX_SENDS` (default 500) is a
WHOLE-RUN cap on send attempts (previews in dry-run) — the runner passes the remaining budget to each page and
stops at zero. One JSON summary line on stdout:
`{"dry_run", "users_considered", "sent", "skipped_no_activity", "skipped_no_subjects", "errors", "pages", "budget_exhausted"}`;
exit 1 on errors. Service: `send_profile_activity_notifications(*, dry_run, cursor=None, limit=200, max_sends=500, now=None) -> dict`
with `next_cursor`. Per opted-in account: subjects = `owned_public_adult_subjects`; window = since
`profile_activity_email_last_sent_at` (fallback 7 days, never more than 30 days back; naive-UTC safe);
counts: `fan_counts(since=…)`, `watchlist_counts(since=…)`, `profile_view_counts_since(since=…)` (all with
`exclude_user_ids=blocked_user_ids(...)` where the helper accepts it); send only when any count > 0; set
`profile_activity_email_last_sent_at = now` only after a successful send; one email per account covering all
its subjects. Content: aggregate counts only. Preview recipients are masked exactly as
`email_service.py:598-606` does.
