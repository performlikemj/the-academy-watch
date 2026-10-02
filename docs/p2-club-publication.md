# C1: club-created adult publication

- Rollout flag: `CLUB_PLAYER_PUBLICATION_ENABLED`, default OFF. Migration `p2c1` follows `p2b3`; preapply schema before deploying, including `contact_requests.club_first`. No flag activation is implied by deployment.
- Club origin remains `LocalPlayer.provenance = club`. Only a known adult on the originating verified/listed club's roster can receive a private invitation. Verified `player_invitations` capability is required.
- Invitation tokens are random, hashed, single-use, expire after seven days and travel in a POST body. The web handoff uses `/player-publication-invite#token=…`, removes the fragment and retains the token only in memory through OTP sign-in. The signed-in email must match the invited recipient.
- Redemption creates a pending player self-claim. It grants no publication permission. A separate unchecked consent control sends `public_profile_consent: true`, the current consent version and `expected_version`. There is no guardian workflow.
- The admin queue names only claimed, consented, active pending rows. Admin-only evidence shows club/squad, adult yes/no and club DOB evidence source, masked invited/claimant/inviter emails, matching account/email flags and permission timestamps. The inviter claiming their own invitation blocks approval with `self_invitation_review_required`; keep private for independent identity review. Full DOB and raw emails are absent from that DTO.
- Moderation requires dual admin authentication, a reason, current version, live club association, adult evidence and the recipient's own claim/consent. Existing negative-ID collision checks and trusted local shadow minting are reused. Duplicate/conflicting identities return 409 for identity review; consent never transfers through merge/provider linking.
- Publication requires all live keys: approved unmerged deterministic local identity; adult at invitation and consent as well as now; approved recipient player claim; confirmed originating club association and roster; approved moderation; current consent version; active recipient; listed club; no withdrawal/revocation, suppression, contradictory child DOB or derived publication hold. There is no birthday publication transition.
- `public_adult_ids` is the shared batched policy. Resolver, local/showcase/media, discovery/compare/CSV/search, saved follows/watchlists, digest, reported stats, share and cached sitemap reads consume its club eligibility. C1 discovery is independent of `SCOUT_INCLUDE_LOCAL_PLAYERS`; community behavior retains that flag.
- Club-origin introductions always use `club_included`, including a free-agent declaration. The claim is pinned to the publication recipient. Player inbox/details/actions and account export withhold identifying requests until club grant and current publication eligibility; both club and player permission gate messages. Creation locks the club program before the publication and claim against withdrawal, retaking the same ordered locks after expiry commits. Either party can revoke a thread; publication withdrawal/revocation and moderation rejection close old threads permanently. Re-approval cannot revive them. Club thread revocation records a decline and starts the same scout cooldown as a club-consent decline.
- Neutral introduction notifications use transactional `notification_outbox`, with club recipients first and the player only after club grant. Delivery rechecks current publication, participant access, blocks and expiry; payloads contain no token, email, name or message text.
- Account export omits invitation hashes and recipient email; withheld club-first requests cannot disclose the scout or message. Account erasure deletes club-first request rows, their messages/outcomes/audits and notification intents even if the request was withheld from export. Erasure removes recipient/unredeemed-email records before deleting claims, invalidates conversations and notification intents, and clears creator/association/reviewer attribution without transferring publication. These privacy hooks run while dark too. Withdrawal/club revocation clear invited emails immediately. Schedule `python -m src.jobs.run_publication_retention --limit 100` daily before activation: expire unclaimed invites and purge invited emails after 180 days, retaining permission evidence without the address. Increase bounded batches if needed for the daily volume. The job also works while dark.
- Consent versions refer to the exact `CONSENT_TEXT` in `services/club_player_publication.py`; change the version when changing that permission. Optimistic versions protect review, consent, withdrawal, club revocation and invite replacement.

## API and web handoff

| Caller | Endpoint | Request |
|---|---|---|
| Club | `GET /api/club/{program}/player-publications`, `/publication-candidates` | First 100 private rows/candidates |
| Club | `POST /api/club/{program}/players/{local}/publication-invite` | `recipient_email`, `expected_version` when replacing |
| Recipient | `POST /api/me/player-publication-invites/preview`, `/accept` | `token`; accept additionally `self_claim: true` |
| Recipient | `GET /api/me/player-publications` | Own records |
| Recipient | `POST /api/me/player-publications/{id}/consent` | `expected_version`, `public_profile_consent: true`, `consent_version` |
| Recipient | `POST /api/me/player-publications/{id}/withdraw` | `expected_version` |
| Club | `POST /api/club/{program}/player-publications/{id}/revoke` | `expected_version` |
| Admin | `GET /api/admin/player-publications` | Claimed + consented + active pending moderation, first 100 |
| Admin | `POST /api/admin/player-publications/{id}/review` | `expected_version`, `action: approve/reject`, `reason` |
| Participant | `POST /api/contact/requests/{uuid}/revoke` | Existing club-origin introduction |

The publication DTO includes `id`, `program_id`, `local_player_id`, `player_name`, `claimed`, `consented`, `association_confirmed`, `moderation_status`, `withdrawn`, `club_revoked`, `version`, `consent_version`, `consent_text`, and live `public`. Raw `token` is returned only on invitation creation/replacement.

Web screens: `/club-publications/{program}`, `/player-publication-invite`, `/player-publications`, `/admin/player-publications`. Native signed-ID scout/contact clients can consume the same published subject and use the authenticated web handoff for consent; new native consent screens remain the iOS parity lane's work.

## Verification

- `tests/test_club_publication_flag_parity.py`: actual main baseline counts pinned for journey/profile/season-stats/cached sitemap (9/11/21/1 in its fixture); both flags, linked provider parity and admin unlink.
- `tests/test_club_publication_rc1.py`: club-first export/erasure, masked evidence/self-invites, queue privacy, decline cooldown, permanent moderation rejection, bounded email retention and 624-request eight-state sweep (seven private + published control), including anonymous/scout/other account audiences.
- `tests/test_club_player_publication.py`: all permission keys, children/unknown DOB/birthday correction, token expiry/rotation/recipient binding, duplicate namespace, cross-surface consent/withdrawal, cached aliases, notification ordering, erasure and real SPA dark-route parity.
- `C1_POSTGRES_URL=postgresql+psycopg://…/aw_p2_c1`: opt-in tests refuse other databases/hosts; row-lock claim/review races, real deletion FKs, repeated migration/RLS and retained-consent downgrade guard.
- `e2e/club-player-publication.spec.mjs`: explicit desktop/mobile permission controls and dark requests, labelled synthetic browser fixtures.
- `C1_HTTP_AUTH_FILE=… e2e/club-player-publication-live.spec.mjs`: opt-in isolated PostgreSQL HTTP workflow, no mocked application API. The auth file is private/local and removed after verification. No provider sends run.
- Screenshots are external `~/codex-runs/aw-redesign/shots/C1/`; fixture names remain explicit. Production UI always loads real API responses.

Migration downgrade refuses retained publication evidence. Empty-table downgrade removes the new table and retains the backward-compatible `club_first` column; re-upgrade is guarded. Never delete real consent evidence to force a rollback.

Flag OFF adds no publication SQL to public player decorators, list predicates or cached sitemap hits. When ON, the additional public read check is negative/local only; positive provider surfaces preserve legacy behavior. A sitemap built while ON is discarded without SQL on flag withdrawal. Resolver-backed identity rules still reject a club/provider consent bridge. Admin can remove a legacy club provider mapping via `POST /api/admin/local-players/{id}/link-api` with `{"player_api_id": null}` while ON; this keeps provider content with its provider, returns the club local identity to pending/private and revokes retained club permissions. New positive club links and merges remain blocked.

## REVIEW-DUEL recovery and retained data
- Expected-version fresh invitation after club revocation or pre-consent recipient withdrawal retires the prior C1 claim; its subject/account and permanently closed introductions remain historical. Fresh invitation, independent self-claim, current consent and moderation are required. Consented withdrawal alone permits renewed consent, not recipient replacement.
- The local-player/account unique index excludes only `club_vouch_retired`; preapply and p2c1 upgrade rebuild it idempotently. C2/C4 must carry the migration verbatim at the posted BUS CONTRACT hash.
- Generated club-player follow names are never stored in new follows. Migration, daily dark retention and export repair old labels. Unavailable subjects are redacted in exports under withdrawal, revocation, rejection, flag OFF, erasure, suspension, suppression and holds. Authored messages remain exportable through an own-content-only projection without restoring counterpart access.
- Re-consent after rejection re-enters moderation with previous decisions visible; no new cooldown. Legacy claim queues/review/recheck exclude retained C1 evidence. Publication/contact lists batch per-response eligibility and evidence; public/follow searches apply canonical eligibility before LIMIT and enforce the final deduplicated cap.

C1F4 retirement and response contract:
- Every contact response names its authenticated viewer, including mutation/error envelopes; pre-grant scout responses withhold recipient identity. Admin API-key reads explicitly use the administrative projection. Club notes are withheld with counterpart history; a plain, eligible club decline keeps its explanation.
- Retirement quarantines self-reported matches and rebuilds affected seasons. Club-verified facts retain their provenance. Photos, links, affiliations and profile evidence are archived separately by author; fresh owners start blank. Legacy mixed archives are repaired transactionally before export/erasure, including while dark, and exports omit internal actor identifiers. Each contributor’s archive follows their own erasure and the original 180-day deadline.
- Erasure-safe reapproval requires the existing canonical club-local shadow plus preserved nonpersonal approval audit; foreign signed claims and mismatched shadow evidence still block approval. Fresh invite, self-claim, consent and moderation remain required.
- Introduction creation re-takes and rechecks the publication after expiry commits; existing no-expiry locking remains intact. Owner match writes serialize with retirement. Thread revocation confirms permanent closure and disables repeated writes while pending.
- Inherited showcase erasure is a separate account-policy change: delete owned photos/affiliations rather than re-pointing them; blob cleanup waits for the root commit and rolls back with the deletion, including savepoints.


C1F5 follow-up contract:
- Publication routes and introduction creation return retryable 409 for PostgreSQL deadlocks/serialization conflicts and 503 for lock timeout, rolling back the failed transaction. Invitation and introduction use program → publication order, including expiry re-takes.
- Scout projections add `public_profile: {player_api_id, display_name}` only for live, eligible pending/accepted requests pinned to the same publication claim and program. It is a public profile title/link, separate from the redacted player account participant. Unavailable, closed or replaced histories omit it.
- Public search merges eligible club adults and enabled community adults through the same normalized-name insertion and deduplication, preserving provider relative order; one final eight-row cap applies in both community-flag states. Dark main behavior remains unchanged.
- Club-first outcomes require live eligibility, club grant and player acceptance. Unavailable/pre-grant/pre-acceptance calls return `409 outcome_unavailable` without an outcome/audit write. Ordinary requests retain their existing reporting policy.
- Flag-independent account export includes only the person's uploaded `showcase_media` file references/status and authored `showcase_affiliations`, with no uploader/author/reviewer identity fields. This inherited portability fix is isolated in its own commit.
