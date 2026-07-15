# Lewis Hall loan mislabeling — final investigation report

**Investigation completed:** 2026-07-16  
**Code examined:** detached `main` at `8aac25f`  
**Mode:** read-only repository investigation; no network, database access, commits, or tracked-file changes  
**Production evidence:** supplied read-only query results plus fresh API-Football histories for the 13 proxy rows

## Executive finding

Lewis Hall is mislabeled because three independent consumers give an old loan precedence over later transfer state. The API fee string `€ 33M` is valid permanent-transfer evidence; fee parsing is not the cause. Current code opens Hall's 2023 Newcastle loan, never closes it on the 2024 permanent conversion, lets the old loan date block the later transfer date, returns `on_loan` because Newcastle was *ever* a Chelsea loan destination, and sets player-level status from *any* historical Newcastle loan entry.

The production timestamps now settle the June 24 question: Hall received an **incremental** journey sync. Seasons 2020–2024 retain their June 20 creation cluster, while only 2025–2026 were recreated at the June 24 `last_synced_at`. The exact trigger/actor is unrecoverable: `background_jobs` has no matching row, and `updated_at` is generic rather than provenance.

The 13-player durable proxy produced **10 confirmed current mislabels, 0 loans proven ongoing as of 2026-07-16, and 3 indeterminate old/unclosed loans**. Eight of the ten are the same loan-to-permanent precedence defect as Hall. Nine rows also have a definitely wrong current owner field. This is a strong lower bound, not a prevalence estimate: the proxy is deliberately enriched for one journey shape and fresh transfer-cache coverage of the active population was 0%.

Code must be fixed before data repair. The planned B2 pass is only a 2025–26 incremental sync; by itself it cannot repair older journey entries or their rollups. The preferred design is to persist the full transfer event stream during B2, drive all transfer consumers through one chronological resolver, and run a database-only all-history journey-entry reclassifier plus affected-season rollup refresh.

## 1. Symptom and established facts

The reported app label was:

```text
Lewis Hall — on loan · from Chelsea
```

The durable state behind it was:

- canonical Chelsea academy-origin `tracked_players.id=21704`: active, `status='on_loan'`, current club Newcastle, `sale_fee=NULL`;
- deprecated Newcastle owning-club `tracked_players.id=21705`: inactive;
- Newcastle journey entries in seasons 2024 and 2025: `entry_type='loan'`, `transfer_date='2023-08-22'`;
- journey player-level state: `current_status='on_loan'`, owner Chelsea.

The transfer history is unambiguous:

```text
2023-08-22  Loan    Chelsea (49) -> Newcastle (34)
2024-07-01  € 33M   Chelsea (49) -> Newcastle (34)
```

The correct canonical result is therefore:

```text
Chelsea academy-origin row 21704: active, sold/permanently departed,
current club Newcastle, sale_fee='€ 33M'

Newcastle owning-club row 21705: inactive

Newcastle entries from the conversion onward: not loan,
effective transfer date 2024-07-01, fee '€ 33M'

journey.current_status/current_owner: NULL/cleared
```

The inactive Newcastle row is not itself an inversion bug. The platform intentionally keeps one canonical row per academy parent and deprecates buying-club duplicates (`docs/agents/invariants.md:31-37`). Journey upsert deactivation is at `academy-watch-backend/src/services/journey_sync.py:1829-1891`; the recompute sweep is at `academy-watch-backend/src/routes/journey.py:243-278`; transfer-heal duplicate cleanup is at `academy-watch-backend/src/services/transfer_heal_service.py:412-435`. The Chelsea row's **status** is wrong; its role as the active academy-origin row is correct.

Round 1 also ran the exact Hall payload through the real `JourneySyncService.sync_player(..., force_full=True)` path with in-memory SQLite and fake API methods. Current `main` reproduced all of the production corruption: active Chelsea row, tracked status `on_loan`, Newcastle 2024/2025 entries typed `loan` with the 2023 date, journey status `on_loan`/owner Chelsea, and both fee fields null. A full sync on current code is therefore not a remedy.

## 2. Root cause: three stale-precedence paths

### 2.1 It is not a fee-string parser defect

`academy-watch-backend/src/api_football_client.py:35-38` defines exact loan and return types. `is_new_loan_transfer()` at lines 41–73 accepts only exact `loan` after excluding returns. `extract_transfer_fee()` at lines 76–88 returns `€ 33M` unchanged; it excludes loans, returns, blank values, and `N/A`.

The status classifier also treats a typed, non-loan parent departure with a concrete destination as permanent/sold at `academy-watch-backend/src/utils/academy_classifier.py:573-586`. The permanent event is valid. It is simply reached too late—or ignored—by the three consumers below.

### 2.2 Precedence bug 1: journey-entry classification

The sync fetches transfers and builds the loan timeline at `academy-watch-backend/src/services/journey_sync.py:227-229`, then applies loan classification before transfer dates at lines 274–279.

The failure trace is:

1. `_build_transfer_timeline()` (`journey_sync.py:570-608`) iterates provider order without sorting.
2. It opens exact loans at lines 589–599 and closes them only on recognized explicit return strings at lines 600–606.
3. Hall's later `€ 33M` Chelsea→Newcastle event is neither a new loan nor an explicit return, so it is ignored. The 2023 loan remains open with `end_date=None`.
4. `_loan_overlaps_season()` (`journey_sync.py:610-633`) lets an open loan overlap every future season.
5. `_apply_loan_classification()` (`journey_sync.py:683-702`) writes `entry_type='loan'` and `transfer_date='2023-08-22'` to Newcastle entries.
6. `_apply_permanent_transfer_dates()` actually collects **all** moves and sorts them at lines 721–735, so it could find `2024-07-01`. But lines 737–739 skip every entry whose loan pass already populated a date. The old loan date prevents the later event from replacing either state or date.

This path also explains stale dates on genuine re-loans: the first still-open matching episode wins, so a new loan to the same club can retain the earlier episode's date.

### 2.3 Precedence bug 2: academy-relative `TrackedPlayer.status`

`upgrade_status_from_transfers()` builds a set of **every historical** parent-to-loan destination at `academy-watch-backend/src/utils/academy_classifier.py:538-545`. If the current club is in that set, lines 547–551 immediately return `on_loan`.

For Hall, Newcastle is in the historical set, so the later date-sorted parent-departure logic at lines 557–586 never gets to classify the 2024 conversion as permanent. The existing `test_latest_departure_wins` at `academy-watch-backend/tests/test_journey.py:1104-1120` misses this shape: its historical loan destination differs from the later/current permanent destination.

A second historical-loan check at `academy_classifier.py:831-839` sets `has_confirmed_loan` and can suppress the squad-return safety net. It must use the same resolved active episode rather than `any()` historical destination.

### 2.4 Precedence bug 3: player-level current status and reverse owner

`_set_current_status()` at `academy-watch-backend/src/services/journey_sync.py:1266-1310` receives stored entries, not the transfer state. Line 1283 asks whether **any** entry at the current club is loan-typed. One old Newcastle entry therefore sets `journey.current_status='on_loan'` at line 1290 even if the loan ended years ago.

The owner is then guessed at lines 1291–1307 from the maximum-season non-current `first_team` journey entry. It is not read from an active loan event's `teams.out`, and ties have no transfer-date ordering. That is why a prior borrower can be displayed as the current owner in chained or repeated histories.

This field is load-bearing: the profile route overrides academy-relative status with it at `academy-watch-backend/src/routes/players.py:427-451`, and the frontend renders `from {owner}` at `academy-watch-frontend/src/pages/PlayerPage.jsx:624-627`. Fixing only `TrackedPlayer.status` would leave the reported UI symptom.

### 2.5 July 1 is incorrectly inclusive

`_loan_overlaps_season()` defines a season start as `YYYY-07-01` at `journey_sync.py:616-617`, but rejects a closed loan only when:

```python
loan_end < season_start
```

Equality still overlaps. A conversion or return on `2024-07-01` would therefore leave season 2024 loan-typed even after the timeline learned to close the loan. `academy-watch-backend/tests/test_journey.py:438-441` explicitly pins this incorrect behavior.

Loan episodes must be half-open intervals, `[start, end)`, so the comparison is effectively `loan_end <= season_start`. Seven of the ten confirmed histories have a decisive July 1 transition, making this an active amplifier rather than a theoretical edge case. A global implementation should also use the competition's season calendar where available; a universal July–June boundary is wrong for calendar-year leagues.

## 3. What happened on June 24

Production evidence for `player_journeys` player 284492 is:

```text
seasons_synced = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
last_synced_at = 2026-06-24 03:54:25
updated_at     = 2026-06-24 08:06:16
sync_error     = NULL

entry created_at:
2020–2024  all 2026-06-20 11:06:23
2025–2026  all 2026-06-24 03:54:24
```

`sync_player()` selects every season only when `force_full=True`; otherwise, in calendar year 2026, it selects unsynced seasons plus `season >= 2025` (`journey_sync.py:218-225`). It builds only those selected seasons at lines 238–255 and deletes/reinserts only rebuilt seasons at lines 301–310. `PlayerJourneyEntry.created_at` is insert-only (`academy-watch-backend/src/models/journey.py:345`).

The two creation clusters are therefore the signature of an **incremental sync**: the June 20 rows through 2024 survived, while 2025 and 2026 were rebuilt immediately before `last_synced_at`. This also explains why both old and new-season corruption coexist:

- season 2024 was not touched;
- season 2025 was regenerated, but current code regenerated the same wrong loan state.

The 08:06 `updated_at` is a generic SQLAlchemy `onupdate` field (`academy-watch-backend/src/models/journey.py:76-77`), not an actor or operation tag. The supplied `background_jobs` query returned no rows for either time window or Hall's player ID. The trigger/actor is consequently unrecoverable from retained database state; only retained application/platform logs or a future row-change audit could identify it.

## 4. Thirteen-player adjudication

Method: events were date-sorted independently of the raw API order. Same-day chains were ordered by causal direction—for example, a return to the parent must precede a new departure from that parent. `N/A` is interpreted using topology, not as universally permanent or universally ignorable. Classification is as of the fresh fetch on **2026-07-16**.

`A` means a later definitive event proves the stored current loan label false. `B` would require evidence that the loan is still current on the adjudication date. `C` means the event stream lacks a loan end/contract term or fresh registration evidence, so current state cannot be proved.

| Tracked ID / player | Decisive chronological evidence | Class and corrected state | Owner adjudication |
|---|---|---|---|
| 19101 — A. Knauff (161922) | `2022-01-20 Loan` Dortmund→Frankfurt; **`2023-07-01 € 5M` Dortmund→Frankfurt** | **A — confirmed.** Permanent at Frankfurt; the 2023–2025 old-loan entries are contradicted. | Dortmund is stale; current owner fields must clear. |
| 23289 — K. Asllani (275776) | `2022-07-01 Loan` Empoli→Inter; **`2023-07-01 € 10M` Empoli→Inter**. Inter later loaned him to Torino and Beşiktaş; latest **`2026-06-29 Return from loan` Beşiktaş→Inter**. | **A — confirmed.** Inter has owned him since 2023 and is his latest location after return. | Empoli is stale; current owner fields must clear. Later loans themselves corroborate Inter ownership. |
| 18561 — D. Herold (162536) | `2023-07-01 Loan` Bayern→Karlsruhe; **`2024-07-01 N/A` Bayern→Karlsruhe**; then **`2026-06-29/30 Transfer` Karlsruhe→Mönchengladbach** (near-duplicate provider rows). | **A — confirmed.** The loan converted in 2024; the latest current club is Gladbach, not Karlsruhe. | SCR Altach appears nowhere in the supplied history and is not a sub-loan owner. Clear owner. |
| 23554 — F. Christophe (200827) | Only `2023-07-17 Loan` Strasbourg→Châteauroux. | **C — indeterminate.** A three-year-old start has no closure, conversion, renewal, term, or 2026 registration evidence. It cannot prove an ongoing loan. | If active, owner should be Strasbourg, so null is incomplete; if expired, status/owner should clear. |
| 19872 — W. Rovida (336703) | `2023-07-20 Loan` Inter→Pro Patria; **`2024-07-03 N/A` Inter→Pro Patria**. | **A — confirmed.** Same-direction non-loan move supersedes the loan; permanent at Pro Patria. | Inter is stale; current owner fields must clear. |
| 18564 — J. Schenk (203331) | `2023-07-26 Loan` Bayern→Preußen Münster; **`2024-07-01 Free` Bayern→Preußen Münster**. | **A — confirmed.** Permanent/free move to Münster. | Bayern is stale; current owner fields must clear. |
| 20577 — S. Mills (284187) | `2023-07-27 Loan` Everton→Oxford; **`2024-01-08 N/A` Oxford→Everton U21**. | **A — confirmed.** Reverse direction to the owner's affiliate is an end/return; no later Oxford re-loan exists. Current club should resolve to the Everton organization. | Everton was the historical owner, but there is no current loan; owner fields must clear. |
| 21704 — L. Hall (284492) | `2023-08-22 Loan` Chelsea→Newcastle; **`2024-07-01 € 33M` Chelsea→Newcastle**. | **A — confirmed.** Permanent Newcastle player. | Chelsea is stale; current owner fields must clear. |
| 22797 — C. Pierobon (265552) | Earlier Verona loans to Mantova and Triestina; `2024-01-31 Loan` Verona→Juve Stabia; **`2024-07-07 N/A` Verona→Juve Stabia**. | **A — confirmed.** Permanent/definitive move to Juve Stabia. | Triestina was a former borrower, never the owner of the Juve loan. Clear owner. |
| 22780 — D. Tufekcic (406483) | Only `2024-06-17 Loan` Brann→Kristiansund. | **C — indeterminate.** No end, return, conversion, renewal, contract term, or 2026 registration evidence; two loan-typed seasons do not prove July 2026 state. | Brann is correct only if the loan remains active. |
| 19671 — F. Zuccon (336639) | `2024-08-23 Loan` Atalanta→Juve Stabia; fresh **`2025-08-31 Loan` Atalanta→Juve Stabia** and **`2025-09-01 Loan` Atalanta II→Juve Stabia** show a real re-loan represented through senior/reserve affiliates. No later closure is present. | **C — indeterminate as of 2026-07-16.** The 2025 season's loan status is supported, but the stored 2024 date is wrong and the events contain no term proving that the 2025–26 loan survived season end. | Mantova is unsupported and definitely wrong. If active, owner is the Atalanta organization; if expired, owner is null. |
| 24661 — Jalil Saadi (298095) | `2024-09-09 Loan` Blackburn→Ethnikos; on **`2025-07-01`**, `Back from Loan` Ethnikos→Blackburn followed causally by `Free Transfer` Blackburn→Ethnikos. | **A — confirmed.** Loan ended and Ethnikos then acquired him permanently. | Null owner is correct for the corrected permanent state; `on_loan` is not. |
| 18622 — N. Aséko Nkili (342171) | `2025-02-03 Loan` Bayern II→Hannover; `2025-07-01 N/A` Hannover→Bayern II; latest **`2026-06-29 Return from loan` Hannover→Bayern**. The missing intervening re-loan makes the history internally incomplete, but both later directions end rather than extend a Hannover loan. | **A — confirmed current-state error.** Latest state is back in the Bayern organization, not at Hannover. The explicit return postdates the June 24 journey sync, so part of this row is ordinary freshness lag. | Null is correct after return; the stored `on_loan` status/current club are not. |

### Adjudication totals

- **10 confirmed current mislabels**
  - 8 same-destination loan→permanent/definitive conversions: Knauff, Asllani, Herold, Rovida, Schenk, Hall, Pierobon, Saadi;
  - 2 return/end cases: Mills and Aséko Nkili.
- **0 proven genuine ongoing loans as of 2026-07-16.** Absence of a return event is not a contract end date.
- **3 indeterminate:** Christophe, Tufekcic, Zuccon.
- **9 definite owner-field errors:** the eight confirmed non-loan rows retaining a named owner, plus Zuccon. Herold's SCR Altach, Pierobon's Triestina, and Zuccon's Mantova are prior/unsupported journey clubs, not evidence of sub-loans.
- At least three current-club fields are also superseded: Herold (Gladbach), Mills (Everton organization), and Aséko (Bayern organization). Herold's and Aséko's latest events occurred after the June 24 sync, so current-club freshness and historical classifier correctness must be measured separately.

## 5. Systemic verdict

### 5.1 What is proven

The fresh-cache coverage query reported:

```text
active tracked players:       3,544
fresh transfer-cache rows:        3
distinct cached player IDs:       2
active-population coverage:    0.00%
```

The exact raw-cache census was therefore correctly skipped. Transfer cache is not evidence storage: summer transfer TTL is 24 hours (`academy-watch-backend/src/api_football_client.py:471-477`), and expired rows are deleted daily (`academy-watch-backend/migrations/maintenance/api_cache_purge_cron.sql:25-32`).

The durable proxy selects a narrow journey shape: an active `on_loan` row whose current club differs from the academy parent and whose journey repeats the same dated loan at that club across at least two seasons. It found 13 rows. Fresh histories then confirmed 10 current errors.

Those ten are the minimum demonstrated exposure:

- 10 / 3,544 active players ≈ **0.28%**;
- 10 / 8,009 candidates ≈ **0.12%**, only if `8,009` has a compatible player grain.

These percentages are lower-bound fractions, **not prevalence estimates**. The 13 rows are not a random sample, so its 10/13 hit rate must not be extrapolated to 8,009.

### 5.2 Relative exposure classes in the observed proxy

| Overlapping class | Observed count | Relative conclusion |
|---|---:|---|
| Same destination: loan followed by permanent/definitive move | 8 | Dominant confirmed mechanism; Hall's exact class |
| Later return/end while current state remains loan | 2 | Smaller confirmed class; includes topology-aware `N/A` and post-sync freshness |
| Old/unclosed loan lacking expiry/current-registration evidence | 3 | Indeterminate queue, not proof of either correctness or corruption |
| Definitely wrong current owner | 9 | Broad cross-cutting defect that also affects real re-loans |
| Definitely superseded current club | at least 3 | Mix of reducer defects and ordinary sync freshness |

The provider histories expose inconsistent `N/A` handling as another contributor. Academy status currently treats `N/A` plus a real destination as a permanent move (`academy_classifier.py:573-585` and tests 1076–1088), while journey current-club override skips all `N/A` as ambiguous (`journey_sync.py:1165-1202`) and club-ID correction excludes it (`journey_sync.py:783-786`). Mills and Aséko show why direction and active topology—not the string alone—must decide whether `N/A` is a permanent move or a return.

### 5.3 What the proxy misses

The true total is necessarily unknown because the proxy has unknown recall. It misses at least:

- conversions represented in only one journey season;
- players who have since moved to a third club;
- return-only histories without a repeated loan date;
- rows where `TrackedPlayer.status` was fixed but `journey.current_status` still overrides it;
- stale historical loan entries when the current tracked status is no longer `on_loan`;
- new/repeated loans whose second episode has a different date;
- affiliate/B-team chains whose raw IDs differ;
- owner errors on otherwise genuine loans;
- inactive candidates, players without a journey, and players whose season fetch returned no entries.

The best defensible platform verdict is therefore:

> At least ten active rows are currently wrong. Same-destination loan conversion is the modal observed failure, and owner inference is a broad overlapping risk. The total across 8,009 candidates cannot be estimated responsibly from current durable data and is likely higher than the demonstrated lower bound.

## 6. Requirements for a definitive census

A definitive census needs durable transfer evidence for every player in the chosen denominator, not a 24-hour cache sample.

### 6.1 Persist evidence during the API pass

Add two durable concepts:

1. **Per-player fetch/snapshot audit**
   - player ID, requested/fetched time, source/batch ID;
   - success with events, successful empty history, failure, or not attempted;
   - response/event count, response hash, error category, resolver version.
2. **Normalized transfer event**
   - player ID and effective date;
   - raw type and normalized kind;
   - raw incoming/outgoing IDs and names plus normalized organization IDs;
   - raw JSON or immutable snapshot reference;
   - deterministic fingerprint, first/last seen, and source fetch ID.

The distinction between successful-empty, failed, and not-fetched is mandatory. Current journey flow returns before fetching transfers when no seasons exist (`journey_sync.py:206-228`), and several fetch paths collapse errors into an empty list. Without an audit row, apparent coverage cannot be trusted.

Raw events should be preserved even when normalized duplicates are coalesced. The supplied histories contain same-day causal chains, consecutive duplicate transfers, affiliate-equivalent records, and provider gaps; future adjudication must be reproducible after the provider revises its payload.

Any new public table must enable RLS in its migration per `docs/agents/invariants.md:22-29`.

### 6.2 Resolve and compare every axis

For every successfully covered player, the census must compare the resolved event state with:

1. each academy-relative `TrackedPlayer.status`, destination, and fee;
2. journey current club, active-loan status, owner organization, and immediate loan source;
3. every journey entry's effective loan episode, type, transfer date, and fee;
4. aggregate `total_loan_apps` and affected season-rollup cells;
5. an explicit unresolved/conflict class rather than forcing incomplete histories to `on_loan` or `sold`.

Transfer events alone still cannot certify whether an old unclosed loan is current. Christophe, Tufekcic, and Zuccon demonstrate the need for a contract end date or a fresh registration/current-squad source. Until then, those cases must remain indeterminate.

### 6.3 Denominator and B2 scope

The documented B2 scope is a 2025–26 journey re-sync of about 3,544 active players (`ledgers/research/seasons-design-proposal.md:133-136,230,243-244`). If 8,009 is the intended platform denominator, B2 must be explicitly widened or followed by a bounded transfer-only fetch for every distinct uncovered player ID. Coverage is definitive only when every denominator member has a success/empty/error/not-attempted audit outcome.

## 7. Remediation design — code first, data second

### 7.1 Build one chronological transfer-state resolver

The resolver should be pure, deterministic, and independent of API array order.

It must:

1. normalize type strings and validate dates/teams once;
2. sort by effective date and resolve same-day events from state continuity and direction, not provider order;
3. preserve raw IDs while normalizing senior/reserve/youth affiliates to an owning organization;
4. deduplicate exact, near-date, and affiliate-equivalent provider records without discarding audit evidence;
5. represent separately:
   - academy parent/provenance;
   - legal owning organization;
   - current registered/playing club;
   - immediate loan source;
   - active loan episode and confidence;
6. emit conflicts/unknowns rather than manufacture a state from incomplete data.

Permanent moves change ownership and location. Loans change location while retaining ownership. Returns restore location. If a real sub-loan produces an immediate source different from legal owner, preserve both and flag the chain; do not infer owner from whichever club supplied the latest journey statistics.

### 7.2 Model distinct, end-exclusive loan episodes

Open a new episode for every genuine re-loan. Close an active episode on:

- a recognized explicit return;
- a reverse-direction move to the owner or its affiliate, including directionally clear `N/A`;
- a later permanent owner→loan-destination conversion;
- another definitive ownership/location event that supersedes it.

Use `[start, end)` intervals. Select the episode effective for a journey entry's season/calendar; do not let an older matching destination win. An unclosed event without expiry/current evidence is unresolved, not automatically open forever.

### 7.3 Replace every ad hoc consumer

The resolver must feed all of these together:

- journey entry loan classification and effective transfer date;
- academy-relative `TrackedPlayer.status`;
- journey current status, current club, legal owner, and immediate source;
- current-club transfer override and historical club-ID correction;
- squad-check loan confirmation (`academy_classifier.py:831-839`);
- owning-club determination;
- fee propagation and any transfer-heal decision.

Later effective state must replace older fields. Remove the `if entry.transfer_date: continue` precedence. A permanent conversion must clear loan state, set the effective permanent date, and propagate fee to both `PlayerJourneyEntry.transfer_fee` and `TrackedPlayer.sale_fee`. The separate fee backfill at `academy-watch-backend/src/routes/api.py:5368-5381` should use the resolver; it currently says “most recent” but iterates raw transfers in reverse, another provider-order dependency.

### 7.4 Repair all history, not only B2 seasons

This is the key refinement from the production timestamps.

B2 is documented as a **2025–26 incremental** pass. In 2026, `sync_player(force_full=False)` selects seasons 2025+ (`journey_sync.py:218-225`), deletes/recreates only successfully rebuilt seasons (`journey_sync.py:301-310`), and refreshes rollups only for `seasons_to_sync` (`journey_sync.py:326-343`). Hall's June 20/June 24 creation clusters prove that behavior in production.

Therefore, resolver fix + ordinary B2 would still leave Hall's 2024 rows, other older loan dates/types, `total_loan_apps`, and historical rollups corrupt.

Preferred repair:

1. deploy the durable event schema, resolver, consumer changes, and regressions;
2. force-full sync Hall as a canary and verify every axis below;
3. run B2 off-container/scaled while persisting complete transfer snapshots for its active cohort;
4. extend transfer collection to the remaining 8,009-denominator players if platform-wide census is required;
5. run a batched **database-only all-history journey-entry reclassifier** from persisted events;
6. recompute journey aggregates and refresh every changed season's rollup, not only 2025–26;
7. re-run the census and require zero determinate contradictions; retain unresolved histories as unresolved.

The alternative is an all-season `force_full` sync for every player, which costs many more API calls and still needs durable event coverage for auditing. A data-first sync on current code would merely rewrite the corruption.

Hall canary acceptance criteria:

```text
row 21704: active, sold/permanently departed, Newcastle, sale_fee='€ 33M'
row 21705: inactive
Newcastle 2024/2025 entries: non-loan, date 2024-07-01, fee '€ 33M'
journey.current_club: Newcastle
journey.current_status/current_owner: NULL
total_loan_apps and all affected 2024/2025 rollups: recomputed
profile, Scout, compare, team, and journey surfaces: mutually consistent
```

Rollup failures are isolated by a savepoint and logged while the journey may still commit (`journey_sync.py:326-343`), so the repair must monitor warnings and retry failed derived refreshes.

## 8. Regression list

### Pure resolver and event normalization

- Hall's exact payload in original, reversed, and shuffled order.
- Same-destination loan→permanent for `€ fee`, `Transfer`, `Free`, `Free Transfer`, and topology-resolved `N/A`.
- Hall/Knauff July 1 conversions.
- Herold's later move to a third club plus consecutive duplicate records.
- Mills's reverse-direction `N/A` return to Everton U21.
- Saadi's same-day return then permanent departure even when raw order is reversed.
- Asllani's same-day return then new loan, followed by a later return.
- Zuccon's same-destination re-loan, new episode/date, and Atalanta/Atalanta II normalization.
- Pierobon's former borrowers never becoming owners.
- Aséko's Bayern II/Bayern affiliate return and missing-event conflict: no active current Hannover loan.
- Explicit returns in newest-first and oldest-first arrays.
- Missing/invalid date, type, incoming ID, or outgoing ID.
- Successful empty history distinct from fetch failure and not-attempted coverage.
- Idempotent event upsert and provider-revision audit behavior.

### Intervals and seasons

- A loan ending on July 1 does **not** overlap the season starting July 1; replace the current expectation at `test_journey.py:438-441`.
- A June 30 end preserves prior-season loan classification under the configured calendar.
- A re-loan to the same destination creates a distinct episode and uses the new date.
- Calendar-year competition boundaries.
- Explicit policy for a mid-season loan→permanent conversion.
- An old open loan without expiry/current evidence resolves indeterminate, not “active forever.”

### End-to-end integration

- Strengthen `test_latest_departure_wins` so the old loan destination and later permanent/current destination are the **same club**.
- Full and incremental Hall syncs converge on the same current state.
- Incremental B2 plus the database repair corrects pre-existing older journey entries.
- Assert tracked status/current club/fee; journey status/current club/owner; entry type/date/fee; and canonical row activation together.
- Assert `total_loan_apps` and every affected rollup cell after reclassification.
- Canonical academy-origin row remains active; deprecated buying-club row remains inactive.
- Profile, Scout list/filter, Scout compare, team, and journey payloads agree.
- Repeated sync/repair is idempotent.
- A failed transfer fetch does not clear or falsely “repair” known state and is visible in coverage.

## 9. Open questions and rollout decisions

1. What is the grain of `8,009`: unique players, candidate rows, or player×academy relationships? The census denominator and dedup key depend on it.
2. Is the required definitive scope the 3,544 active/displayed players, all 8,009 candidates, or both with separate metrics?
3. What source certifies an unclosed loan as current: contractual expiry, current registration/squad, provider player profile, or an explicit product-level `unknown` state?
4. Should legal owner and immediate loan source be stored separately for genuine sub-loans and affiliate chains?
5. What is the canonical ordering policy when same-day events remain irreconcilable after direction/state analysis?
6. How should one season entry be labeled when a loan converts permanently mid-season? A separate movement-status dimension may be cleaner than overloading `entry_type`, which also carries academy/development/first-team semantics.
7. How long should raw provider snapshots and event revisions be retained?
8. What current-state refresh cadence is acceptable during transfer windows? Herold and Aséko show that correct historical logic still needs freshness.
9. The June 24 actor is unrecoverable from current DB state. Should future background syncs write a run ID/actor/source to the journey and tracked rows?

## Final conclusion

Hall is not an isolated fee-format edge case. He is the clearest instance of a chronology/state-model defect repeated across journey entries, academy-relative status, and player-level status/owner. The 13-player audit confirms that same-destination loan conversions are the largest observed class and that reverse-owner inference is independently unsafe. Fix one shared transfer resolver, bank the evidence, then repair every historical entry and affected rollup. Running B2 first—or limiting the repair to B2's recent seasons—would leave known corruption behind.
