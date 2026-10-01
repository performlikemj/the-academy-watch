# C1: club-created adult publication

- Rollout flag: `CLUB_PLAYER_PUBLICATION_ENABLED`, default OFF. Migration `p2c1` follows `p2b3`; preapply schema before deploying, including `contact_requests.club_first`. No flag activation is implied by deployment.
- Club origin remains `LocalPlayer.provenance = club`. Only a known adult on the originating verified/listed club's roster can receive a private invitation. Verified `player_invitations` capability is required.
- Invitation tokens are random, hashed, single-use, expire after seven days and travel in a POST body. The web handoff uses `/player-publication-invite#token=…`, removes the fragment and retains the token only in memory through OTP sign-in. The signed-in email must match the invited recipient.
- Redemption creates a pending player self-claim. It grants no publication permission. A separate unchecked consent control sends `public_profile_consent: true`, the current consent version and `expected_version`. There is no guardian workflow.
- Moderation requires dual admin authentication, a reason, current version, live club association, adult evidence and the recipient's own claim/consent. Existing negative-ID collision checks and trusted local shadow minting are reused. Duplicate/conflicting identities return 409 for identity review; consent never transfers through merge/provider linking.
- Publication requires all live keys: approved unmerged deterministic local identity; adult at invitation and consent as well as now; approved recipient player claim; confirmed originating club association and roster; approved moderation; current consent version; active recipient; listed club; no withdrawal/revocation, suppression, contradictory child DOB or derived publication hold. There is no birthday publication transition.
- `public_adult_ids` is the shared batched policy. Resolver, local/showcase/media, discovery/compare/CSV/search, saved follows/watchlists, digest, reported stats, share and cached sitemap reads consume its club eligibility. C1 discovery is independent of `SCOUT_INCLUDE_LOCAL_PLAYERS`; community behavior retains that flag.
- Club-origin introductions always use `club_included`, including a free-agent declaration. The claim is pinned to the publication recipient. Player inbox/details/actions are unavailable until club grant; both club and player permission gate messages. Creation locks publication against withdrawal. Either party can revoke a thread; publication withdrawal/revocation closes old threads permanently.
- Neutral introduction notifications use transactional `notification_outbox`, with club recipients first and the player only after club grant. Delivery rechecks current publication, participant access, blocks and expiry; payloads contain no token, email, name or message text.
- Account export omits invitation hashes and recipient email. Erasure removes recipient/unredeemed-email records before deleting claims, invalidates conversations and notification intents, and clears creator/association/reviewer attribution without transferring publication. These privacy hooks run while dark too.
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
| Admin | `GET /api/admin/player-publications` | Pending moderation, first 100 |
| Admin | `POST /api/admin/player-publications/{id}/review` | `expected_version`, `action: approve/reject`, `reason` |
| Participant | `POST /api/contact/requests/{uuid}/revoke` | Existing club-origin introduction |

The publication DTO includes `id`, `program_id`, `local_player_id`, `player_name`, `claimed`, `consented`, `association_confirmed`, `moderation_status`, `withdrawn`, `club_revoked`, `version`, `consent_version`, `consent_text`, and live `public`. Raw `token` is returned only on invitation creation/replacement.

Web screens: `/club-publications/{program}`, `/player-publication-invite`, `/player-publications`, `/admin/player-publications`. Native signed-ID scout/contact clients can consume the same published subject and use the authenticated web handoff for consent; new native consent screens remain the iOS parity lane's work.

## Verification

- `tests/test_club_player_publication.py`: all permission keys, children/unknown DOB/birthday correction, token expiry/rotation/recipient binding, duplicate namespace, cross-surface consent/withdrawal, cached aliases, notification ordering, erasure and real SPA dark-route parity.
- `C1_POSTGRES_URL=postgresql+psycopg://…/aw_p2_c1`: opt-in tests refuse other databases/hosts; row-lock claim/review races, real deletion FKs, repeated migration/RLS and retained-consent downgrade guard.
- `e2e/club-player-publication.spec.mjs`: explicit desktop/mobile permission controls and dark requests, labelled synthetic browser fixtures.
- `C1_HTTP_AUTH_FILE=… e2e/club-player-publication-live.spec.mjs`: opt-in isolated PostgreSQL HTTP workflow, no mocked application API. The auth file is private/local and removed after verification. No provider sends run.
- Screenshots are external `~/codex-runs/aw-redesign/shots/C1/`; fixture names remain explicit. Production UI always loads real API responses.

Migration downgrade refuses retained publication evidence. Empty-table downgrade removes the new table and retains the backward-compatible `club_first` column; re-upgrade is guarded. Never delete real consent evidence to force a rollback.
