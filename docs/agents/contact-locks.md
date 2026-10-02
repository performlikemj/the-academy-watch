# Contact locking after C1F8

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

## Paths changed in C1F8, compared with origin/main and reviewed 16810d53

| Path | origin/main | 16810d53 | C1F8 |
|---|---|---|---|
| Player and club feedback lists | Each thread locks accounts/C/P/grants/invitation/feedback; lazy closure writes | Each thread resolves P/U/C/R then the other rows; later scope can permanently reject | Plain SELECTs only; current durable closure and eligibility checked; no locks or writes |
| Feedback details/acknowledge/publish/correct/withdraw | Per-thread locks | P/U/C/R scope then accounts/grants/invitation/feedback | Same write/detail locking; helper reuses held scope, no fabricated rank conflict |
| Feedback purge | Per-item account/C/P/grant/invitation/feedback locks | Per-item helper; later item can permanently reject | Read all bounded-page invitations, one complete P/U/C/R batch, all accounts sorted, then invitation/revision locks |
| Account deletion / pilot erasure | Settlement advisory locks → user; per-item pilot locks later | User → partial contact scope; omitted recipient/source-owned claims permanently reject; account inversion | Settlement advisory locks → one complete P/U/C/R batch → all involved accounts sorted; preserve purchase retry savepoint; per-item pilot locks reuse scope |
| Pilot invitation resolution / exact relationship revoke | Account/C/P then selected R | P/U/C/R then accounts; expanded helper result used as mutation selection | Same P/U/C/R prefix; revoke updates only original selected club-included requests and rechecks binding/status |
| Club inbox operational program checks | One scalar P lock/query per managed program | Four statements per program | One narrow P lock/query; policy read from returned row |
| Contact message read/send and messaging eligibility | R lock (plus operational P where applicable) | P/U/C/R, repeatedly resolved/re-read | Same canonical scope, hints read once, rows returned from locking query; repeated exact scope costs zero SQL |
| Owner approved-media preview | Plain ownership reads | Owner helper takes publication/contact locks for club-origin | Plain publication/ownership reads for GET/HEAD |
| Club-origin owner profile/contract write | Plain ownership gate; local attestation locks accounts/C/P | Publication scope first, later chosen club can extend backwards | Payload chosen club included in same publication batch before owner gate; attestation reuses prefix |
| Identity merge/provider relink | Per-claim and R locks in stages | Initial two-identity helper scope | Initial batch also includes retained provider IDs from claims, so old provider requests are resolved before rekey |

Main's feedback lists already locked rows. C1F8 intentionally makes the list endpoints
true reads, while keeping existing detail and write serialization. Durable closure remains
visible immediately; withdrawal/revocation and the retention worker persist its deadline.

The inherited Sent-list club label now wraps unbroken names. The introduction revoke
button also wraps inside narrow cards (320px) rather than enforcing a fixed one-line width.

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
