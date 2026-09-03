# S3-P2a — Club program profile editing, moderated updates, external support link-out (backend only, NO money)

Worktree: __WT__ (branch `feat/s3-p2a-clubs`, base `origin/main`). Common brief: __COMMON__. Contracts: __CONTRACTS__ (the "P2a contracts" section is authoritative).

## Requirements
1. `src/models/funding.py`: `ClubProgramProfileRevision` += `external_support_provider`, `external_support_url`; new
   `ClubProgramUpdate` model per the contract; a shared `revision_dict(revision)` and `update_dict(update)` helper (module level
   or in the routes — one definition, used by manager, admin and public code).
2. Migration `migrations/versions/s3c1_club_program_editing.py`: revision `s3c1`, down_revision `cb01` (the orchestrator will
   re-chain to `s3b1` before merge — leave a one-line comment saying so). Guarded DDL (inspector checks, pattern `s2f1_fans_reach.py`),
   RLS enabled on `club_program_updates` (no policies), guarded downgrade. `flask db heads` prints exactly `s3c1`.
3. `src/routes/club.py` (manager routes, decorator `require_club_manager()` from `src/services/club_registry.py`, rate limits: `club.py` has no
   limiter today — `from src.extensions import limiter` and a local `_user_rate_limit_key` returning `g.user_email or request.remote_addr or "anon"`
   mirroring `src/routes/funding.py:122-123`; 20/hour on PUT profile, 10/hour on POST updates): `GET/PUT /club/<program_id>/profile`, `GET/POST /club/<program_id>/updates`,
   `DELETE /club/<program_id>/updates/<update_id>` exactly per the contract. Validation helpers: reuse `_clean`/`_https`-style
   helpers from `src/routes/funding.py` if importable without cycles, else write local equivalents (report which). The external
   support URL validator MUST reject: http, userinfo (`https://user@patreon.com/x`), ports, query strings, fragments, subdomains
   other than `www.`, look-alike hosts (`patreon.com.evil.tld`, `notpatreon.com`), empty path, `javascript:`; accept
   `https://www.patreon.com/creator` and `https://buymeacoffee.com/creator` (normalised).
4. `src/routes/funding.py` (admin, `@require_api_key`): the two queues and two review routes per the contract, each decision
   writing `_audit(...)`. Approve on a revision sets `program.approved_profile_revision_id`. Public `public_program` gains
   `external_support` and `updates` (approved only, ≤10, newest `published_at` first); `is_fundable` untouched.
5. Tests `tests/test_club_program_editing.py` (new; seed a league + approved program + approved claim + active manager the
   way `tests/test_club_console_bridge.py` / `tests/test_funding_registry.py` do — reuse their helpers if importable):
   a) non-manager and pending-claim user → the neutral 403 on every manager route; b) PUT creates a pending revision, a second
   PUT replaces it in place (still one pending row), approved revision unchanged, public page unchanged until approval;
   c) validation matrix for `external_support` (all rejects above + both accepts), list/length limits, https-only URLs;
   d) admin approve → public payload shows the new summary + `external_support` with the right `label`; reject → public unchanged,
   revision `rejected`, `FundingAdminEvent` written for both; 409 on re-review; e) updates: create (pending, not public),
   6th pending → 409, admin approve → public `updates` contains it with `published_at`, manager DELETE of an approved update →
   `withdrawn` and gone from public, DELETE of another program's update → 404; f) `is_fundable` is `false` in the public payload
   before and after. Run also `tests/test_funding_registry.py` and `tests/test_club_console_bridge.py` (must stay green).

## ALLOWED
`academy-watch-backend/src/models/funding.py`, `academy-watch-backend/migrations/versions/s3c1_club_program_editing.py` (new),
`academy-watch-backend/src/routes/club.py`, `academy-watch-backend/src/routes/funding.py`,
`academy-watch-backend/tests/test_club_program_editing.py` (new). Nothing else (if `club_registry.py` truly needs a helper, STOP and report). NEVER edit `src/services/account.py` — P0 owns it and
   pre-declares your `author_user_id`/`reviewed_by` compatibility with schema guards.

## Commit (exactly one)
`feat(club): S3-P2a manager-editable program profiles, moderated updates, and Patreon/BMC link-out (no money)`
