# Contact locking after C1F9

P = club program; U = club publication; C = player profile claim; R = contact request.
Resolve IDs with plain reads, acquire all P → all U → all C → all R in one helper call,
with IDs ascending inside each table, then recheck policy on the locked rows.
All batch callers pass their complete selection before their item loop. Scope expansion
locks related rows; it never expands the set of records a caller is authorized to mutate.
The helper retains ORM rows only inside the current transaction, restores its bookkeeping
on savepoint rollback, and discards it on root completion. Repeated exact scopes require
no SQL; P-only policy checks require one narrow locking query (zero if already held).

The helper no longer manufactures a serialization failure because an earlier rank was
requested. For genuinely dynamic, incremental legacy callers, an earlier rank/ID uses
FOR UPDATE NOWAIT: it either succeeds immediately or raises a real PostgreSQL 55P03.
Known multi-item application paths use the full upfront batch, so their acquisition
order does not depend on item order. Real 40P01/40001 map to 409; 55P03 maps to 503;
all such responses follow rollback. Concurrent binding changes still invalidate unlocked
scope hints and require a transaction retry.

## Full path inventory: locks on main → locks now

Main means `ee16572f` (the reviewed main ancestor; the account/contact code inspected
on `eddba4ac` has the same relevant behavior). C1-only routes do not exist on main;
for those rows the old order is explicitly the reviewed C1 base `c7cf6c11`.
`A` = account rows, `I` = pilot invitation, `F` = feedback revisions, `G` = club
manager/source grants, `S` = purchase settlement advisory locks. Missing tables/IDs
are omitted from the canonical prefix; direct ordinary threads normally use C → R.
Every P/U/C/R batch is sorted per table. Additional domain rows follow that prefix.

| # | Touched path / entry point | Locks on main (C1-only: reviewed base) | Locks now |
|---|---|---|---|
| 1 | Club-first `POST /contact/requests` | Absent on main; base P/U before expiry, C/R acquired later | Finish/commit due expiry first; resolve one P → U → C → R prefix; insert new R afterward |
| 2 | Ordinary `POST /contact/requests` | Due R expiry then commit; scout verification → C; operational P where applicable | Due canonical expiry then commit; existing scope P → C (U if required by identity); scout verification; insert new R |
| 3 | `POST /contact/requests/:id/accept` and `/decline` | R → C | P → U → C → R; permission/status rechecked |
| 4 | Club-first `/club-consent`, `/contact/club-consent/:token`, `/revoke` | Absent on main; base R then publication/claim/program checks | P → U → C → R; live publication/grant/claim rechecked |
| 5 | Ordinary `/club-consent` and consent-token GET/POST | R → P (plus scout verification/A for token summary) | P → C → R; scout verification/A follow prefix |
| 6 | `POST /contact/requests/:id/withdraw` | R | P → U → C → R, with missing ranks omitted |
| 7 | Scout `POST /contact/requests/:id/messages` | Participant checks → R refresh; operational P for club participant | P → U → C → R once; same scope retained for messaging check and insert |
| 8 | Player `POST /contact/requests/:id/messages` | R refresh → C ownership lock | P → U → C → R; ownership checked on held C |
| 9 | Club `GET/POST /contact/requests/:id/messages` | Operational P → R refresh | P → U → C → R once; no scope narrowing |
| 10 | Scout/player `GET /contact/requests/:id/messages` | R refresh after participant check | P → U → C → R once; no scope narrowing |
| 11 | `POST /contact/requests/:id/outcome` | Participant/operational P check; C for player; R FK key-share on inserts (R update lock only for due expiry) | P → U → C → R before outcome/audit inserts |
| 12 | `GET /contact/requests` (sent/inbox/club); `_expire_visible_rows` | P per managed club; due R page → commit | Same narrow P per managed club; due full P → U → C → R page → commit; ordinary successful list does not lock non-due R |
| 13 | `POST /club/:program/local-players/:local/publication-invite`; recovery/`retire_claim` | Absent on main; base P → U, then C and old R during recovery | One P → U → C → R prefix; locked claim/publication used for retirement |
| 14 | Publication player withdraw, club revoke, admin reject; `close_threads` | Absent on main; base U → R, plus evidence rows on club revoke | P → U → C → R; evidence locks and thread closure follow prefix |
| 15 | `POST /admin/player-publications/:id/review` approve | Absent on main; base U → shadow → C | P → U → C → R, then shadow/evidence rows |
| 16 | Publication invite redeem/preview and `POST /me/player-publications/:id/consent` | Absent on main; base U then existing/new C | P → U → C → R for existing bindings; new claim inserted afterward; token/version rechecked |
| 17 | Owner showcase profile, affiliations, photos and reel writes; local attestation; self-match writes | Plain owner gate; low-risk approval C; pilot local attestation A → C → P; match/profile domain rows | Club-origin owner P → U → C → R, with payload-selected attestation P in same batch; ordinary attestation P → C → A; domain rows follow |
| 18 | Club provider unlink `POST /admin/local-players/:id/link-api` with null provider | Absent on main; base local identity → U → old R | Local identity → P → U → C → R; recheck publication ID set; revoke only original matching publications |
| 19 | `POST /account/delete`; `delete_account` | S → A; own claims selected after A; pilot A → C → P → I/F per item | S → complete P → U → C → R → sorted full A batch; re-read every selection/purchase after A; rollback acquisition savepoint and retry at most five times on change |
| 20 | Pilot invitation create/replay `/club/:program/invitations` | A → C → P → G → I | P → U → C → R → sorted A → G → I; newest claimant/grant/status checked after locking |
| 21 | Pilot invitation accept/decline/revoke; club revoke; roster-removal revoke | A → C → P → G → I → selected R on revoke | P → U → C → R → sorted A → G → I; invitation binding rechecked; mutation stays on original matching R; revoke stamps all feedback revision deadlines |
| 22 | Player/club feedback lists `GET /me/player-feedback`, `/club/:program/player-feedback` | Per thread A → C → P → G → I → F; lazy closure writes | Plain SELECT only, including live durable-closure/adult/squad checks; zero row locks/writes |
| 23 | Feedback detail, acknowledge and development-progress update | A → C → P → G → I → F | P → U → C → R → sorted A → G → I → F; binding checked after I |
| 24 | Feedback publish, correct/revision and withdraw | A → C → P → G → I → F | P → U → C → R → sorted A → G → I → F; existing deadline never cleared |
| 25 | `POST /admin/player-feedback/purge` | Same A/C/P/G/I/F locks acquired progressively per revision | One whole bounded-page P → U → C → R → sorted A prefix; revalidate selected request IDs and invitation bindings; then each I/F; stamp older closed rows without deadlines |
| 26 | `_erase_pilot_rows`: manager, recipient, manager/scout and source-claim-owner variants | Account held; per-invitation A → C → P → G → I/F | Reuses root's complete prefix/A batch, including recipient/source-owned claims and their requests; fresh locked invitation binding before each mutation |
| 27 | `erase_publications` (recipient/email/creator/association evidence) | Absent on main; base U/evidence/R per row | Reuses complete root prefix; reselect recipient publication IDs; only original matching IDs revoked/deleted; creator/association references redacted |
| 28 | `erase_introductions` including withheld club-first histories | Absent on main; base selected R deletion | Reuses root's complete P → U → C → R selection, independent of export visibility |
| 29 | Identity merge `/admin/local-players/:id/merge`; `_merge_subject_claims` | Local identities → source C → target C, then retained application/contact stages | Local identities → complete P → U → C → R batch, including retained provider IDs; re-read source/target C and R membership before rekey |
| 30 | Provider relink `/admin/local-players/:id/link-api`; `_rekey_contacts` | Local identity → source C → target C; source R → target R in stages | Same full P → U → C → R merge batch; recheck signed-subject R membership; retain subject filters when consuming helper result |
| 31 | Opportunity submission `/opportunities/:id/applications` | P → opportunity; approved C read; application rows | P → U → C → R before opportunity/application rows; reload approved claim and subject after prefix |
| 32 | `_has_approved_subject_claim(..., for_update=True)` and `vouch_for_player_claim` | Direct approved C / selected C lock | P → U → C → R helper; approved-claim membership rechecked; vouch uses returned locked C |
| 33 | `_legacy_negative_identity_conflict` | Direct C lock for referenced signed ID | P → U → C → R batch; signed-ID claim membership rechecked; other namespace evidence locks unchanged |
| 34 | `POST /admin/showcase/claims/:id/review` revoke/reject/reapprove | Plain C read then status UPDATE | Canonical P → U → C → R prefix; reject/revoke sets all F deadlines in same write transaction; reapprove preserves deadline |
| 35 | Owner approved-media preview / owner GET/HEAD gate | Plain ownership reads | Plain publication/ownership reads; no contact/publication locks |
| 36 | `program_is_operational(..., for_update=True)` including club inbox and opportunity prefix | One narrow P SELECT FOR UPDATE | One narrow P helper SELECT FOR UPDATE; held P reused with zero SQL |
| 37 | `messaging_is_open`, request/claim loaders, publication loaders and repeated helper calls | Direct R refresh / C or U lock in each loader | Resolve hints once; canonical P → U → C → R; reuse transaction-owned rows/scopes; no repeated exact-scope SQL |
| 38 | Publication invited-email retention; retired-showcase repair/delete; account export | C1 retention absent on main; base U retention query; other evidence queries lock rows as selected | U-only bounded retention locking query unchanged; evidence locks unchanged; no pre-read ID set reused after a later lock |
| 39 | Other touched exception wrappers: account export; club results; showcase affiliation/media/profile/reel/admin-review/local-club/video-roster routes; opportunity routes; public signed-ID readers | Existing domain locks, or plain public reads | Domain locks unchanged except explicit rows above; added neutral contention rollback mapping / eligibility projection does not acquire another P/U/C/R prefix |

The inherited Sent-list club label and introduction revoke button wrap unbroken names
inside 320/390px cards. This round has no frontend file changes.

## Selection audit (C1F9)

- **Root account deletion, including plain, manager, scout, manager/scout, recipient and source-manager-claim-owner variants:** pre-A hints were authoritative after A (X-1). Re-read owned claims (including approval/identity), contacts, publications, pilot invitations, club-program memberships and purchase intents after sorted A locks. Compare immutable membership/binding snapshots. On change release the savepoint's entire prefix/A locks and rebuild; five-attempt cap returns neutral `contact_conflict` 409 after rollback. Final deletion uses refreshed claim IDs; exhaustive FK erasure guard unchanged. All variants share this one implementation.
- **Pilot invitation erasure:** root now validates the complete invitation/recipient/source-owned claim/request/account scope. `_erase_pilot_rows` selects again under that prefix and checks the newly locked invitation's binding. Pending invitation deletion and retained accepted-evidence redaction remain unchanged.
- **Feedback purge batch:** bounded feedback page is intentional, so new feedback outside the page need not enlarge it. Invitation bindings and the selected claims' contact IDs did need post-prefix checks; now validated after canonical scope/account locks. Each candidate F is reloaded under its own lock. Missing I/F is skipped; newly discovered earlier scope raises real changed-scope 409 after rollback, never adds locks while A is held.
- **Publication email/retired-content purge batches:** bounded predicates and FOR UPDATE are one query; no authoritative pre-lock ID snapshot. No change required. Worker still stamps older closed feedback lacking a deadline.
- **Merge and provider relink:** source/target claim IDs and signed-subject request IDs were plain pre-prefix hints. Now reread those same selections after the helper, reject changed membership before mutation, and retain the caller's subject selection. The later contact rekey also validates its selected ID set. Existing application uniqueness/retained-history conflict handling remains.
- **Publication erasure:** root validates the full recipient/creator/association publication scope after A. The recipient subset is additionally reselected after its helper call; revoke/delete consume original matching IDs instead of every expanded helper result.
- **Club retirement/recovery, publication consent/revoke/reject/approval:** publication and pinned claim come from refreshed helper rows; the helper already validates their identity bindings. Showcase/evidence selections acquire FOR UPDATE in the selecting query, and thread candidates are selected after owning the full publication prefix. No stale authoritative pre-lock ID set was found. Provider-unlink publication membership is now explicitly checked after the helper and its mutation selection remains local-ID scoped.
- **Pilot invitation resolution and feedback detail/write:** selected program/claim/recipient/creator/source binding now compared after I locking; pre-lock permission hints cannot select a different account/claim/program for the mutation. Invitation creation already reselects newest claimant and source grant after locking.
- **Owner trusted-approval gate and legacy namespace lookup:** approved/signed-identity claim sets now checked after helper locking. Single selected vouch/claim-review IDs use the helper's refreshed C; no membership expansion.
- **Opportunity application:** selected program/C enters the prefix; approved C and resolved subject are reloaded and policy checked before application insert. No unvalidated selected ID set found.

Feedback lists remain pure reads. Relationship revoke and profile-claim reject/revoke
persist the 30-day `audit_expires_at` deadline on every affected revision in their write
transaction. Reapproval does not clear that deadline or reopen closed feedback. The purge
worker retains its backfill for older terminal records with no deadline.

Ordinary C1-OFF SQL is pinned exactly in `test_contact_lock_queries.py`: sent/inbox/club
lists **13/13/24**; scout/player/club included-thread opens **16/16/20**; direct scout
open **11**; scout included/direct sends **20/13**. No statement or scope lock was removed.

CI's exact check name is **Contact Lock PostgreSQL Regressions** (job ID
`contact-lock-postgres`). It runs named reviewer controls and C1F9 scope-gap regressions
on drafts; required-check configuration and `deploy.yml` are unchanged by release-lead
ruling. Full 1,392-pair inventory remains an additional lane run on a migrated database.

## Validation contract

- RC1XV3-O eight sequential probes must all succeed on the first attempt; C1 is OFF.
- Both reviewers' real PostgreSQL pair/gap/erasure/list probes are retained as tests.
- The matrix seeds two clubs, three adults (ordinary and club-published), multi-club
  accepted relationships and feedback, a manager/scout, and retained old requests.
- Successful controls require 200/201. Independent accepted message/read/outcome races
  require success on both sides; every independent review pairing requires useful success,
  stored writes and matching audit, not merely a status below 500.
- CI runs the named PostgreSQL regressions and successful controls on draft PRs too.
  Its disposable metadata schema is separate from migration compatibility verification;
  historical migrations need production-era prerequisites absent in an empty database.
- Lane validation additionally runs the full PostgreSQL inventory matrix and existing
  migration/retention/race tests on an actually migrated disposable database.
