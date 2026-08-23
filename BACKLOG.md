# Backlog — platform review 2026-08-23 build-out (qwen lane)

Source plan: `docs/platform-review-2026-08-23.md` (Phase 0 first). Executor: qwen3.8:27b on basecamp via
`./run-qwen.sh <TASK>`; orchestrator: Fable. One task per session. Your prompt names the task. Work only
that one. Every task has a full brief in `briefs/<TASK>.md` — READ IT FIRST and follow it exactly — and a
gate list in `briefs/<TASK>.gate` that `make gate TASK=<TASK>` reads.

| Task | Brief | What it is | Status |
|---|---|---|---|
| SMOKE | `briefs/SMOKE.md` | Prove the pipe: one trivial backend test file. | done 08-23 (pipe proven: file + gate green; handback missed on a 15-min budget) |
| P0-C1 | `briefs/P0-C1.md` | `RequireAuth` honors its `requireJournalist` prop (dead prop today). | done 08-23 (84369d1) |
| P0-A1 | `briefs/P0-A1.md` | Club-consent email links point at the web page `/contact/club-consent/<token>`, not `/api/...`. | done 08-23 (e54a750) |
| P0-B1 | `briefs/P0-B1.md` | Backend `GET /api/club/<program_id>/matches` (club match list; kills the localStorage history). | done (bdae27f) |
| P0-A3b | `briefs/P0-A3b.md` | Consent page: only the API 404 is "invalid link"; transient failures get Retry (codex P2 on PR #887). Shipped page, one `cp`. | done (cbe5a1e) |
| P0-A0 | `briefs/P0-A0.md` | `contactable` flag on `/api/scout/players` rows (approved self-claim exists) — one batched query. | done (95a70f9) |
| P0-C2 | `briefs/P0-C2.md` | Index `scout_watchlist_entries.player_api_id` (model + guarded migration `sw01` off head `c201`). | done (8be23f8) |
| P0-C3 | `briefs/P0-C3.md` | `club_registry._table_columns` introspects once per HTTP request (no cache outside requests). | done (fffe186) |
| P0-C4 | `briefs/P0-C4.md` | New scheduled job `src/jobs/run_video_maintenance.py` that calls `reap_stale_jobs()`. | done (3f0957c) |
| P0-A2 | `briefs/P0-A2.md` | `api.js` learns the contact rail (13 user-level methods) + source test. | done 08-23 (b0690df) |
| P0-B2 | `briefs/P0-B2.md` | Club console reads `listClubMatches`; localStorage index deleted. Depends on P0-B1. | done (6352091) |
| P0-B2b | `briefs/P0-B2b.md` | Roster editor opens only a fully fetched match (codex P1 on PR #888: list rows carry no roster → a save could wipe it). Two step scripts + test. | done (99134a8) |
| P0-D1a | `briefs/P0-D1a.md` | `video_storage.delete_blob` + `services/video_retention.py` (`due_matches`, `expire_raw_footage`). | done (8e8e435) |
| P0-D1b | `briefs/P0-D1b.md` | Maintenance job runs the retention sweep. Depends on P0-C4 + P0-D1a. | done (ce302cb) |
| P0-D2 | `briefs/P0-D2.md` | Footage redirect uses a 30-min media read SAS + `Cache-Control: private, no-store`. | done (8307865) |
| P0-D3 | `briefs/P0-D3.md` | Footage SAS ≤ token remaining life; sweeper keeps blob rows when storage unconfigured; preflight not swept (codex on PR #890). 3 step scripts + 3 shipped files. | done (2ffed49) |
| P0-D4 | `briefs/P0-D4.md` | Reaped jobs move their match processing→failed; sweeper re-checks under lock before delete (codex round 2 on PR #890). 1 step script + 3 shipped files. | done (5fe2124) |
| P0-D5 | `briefs/P0-D5.md` | Abandoned created uploads swept by age; /process + /requeue FOR UPDATE; reaper CAS with RETURNING (codex round 3 on PR #890). 2 step scripts + 2 shipped files. | done (81752c8) |
| P0-D6 | `briefs/P0-D6.md` | Reaped workers fenced (conditional heartbeat, completion guard, keepalive thread); upload-complete FOR UPDATE (codex round 4 on PR #890). 3 step scripts + 2 shipped files. | done (26b42e1) |
| P0-D7 | `briefs/P0-D7.md` | Reaper + worker failure path move queued matches too, only while no other job is live; fail_running_job CAS (codex round 5 on PR #890). 1 step script + 3 shipped files. | done (93db06c) |
| P0-D8 | `briefs/P0-D8.md` | Completion fenced end-to-end; re-mint SAS refuses grants that would outlive the deadline; sweep waits a grant-lifetime (codex round 6 on PR #890). 2 step scripts + 3 shipped files. | done (77e56e7) |
| P0-A3 | `briefs/P0-A3.md` | Public club-consent page `/contact/club-consent/:token` (+ pure copy helper). Depends on P0-A2. | done 08-23 (aedad98) |
| P0-A5 | `briefs/P0-A5.md` | Scout verification page `/scout/verification` (status + apply form). Depends on P0-A2. | done (4244034) |
| P0-A4 | `briefs/P0-A4.md` | "Introduce" action on the Scout Desk + `IntroduceDialog` (server codes mapped). Depends on P0-A0, P0-A2. | done (2d518d0) |
| P0-A6b | `briefs/P0-A6b.md` | `ContactThread` component: messages + send + outcome report (shared by scout/player/club views). Depends on P0-A2. | done (9feaf78) |
| P0-A6 | `briefs/P0-A6.md` | `/introductions` page: Sent (scout) and Inbox (player) tabs, accept/decline/withdraw, opens the thread. Depends on P0-A6b. | done (0e73fe1) |
| P0-A8 | `briefs/P0-A8.md` | Club console "Introductions" tab: `box=club`, grant/decline consent, thread. Depends on P0-A6b. | done (ef5f113) |
| P0-A9 | `briefs/P0-A9.md` | Nav: "Introductions" item for signed-in users; Scout Desk header links (Introductions, Get verified). | done (c02f96a) |
| P0-A6c | `briefs/P0-A6c.md` | Thread pages through every message; `canReportOutcome` prop; club panel passes false (codex P2s on PR #889). Four shipped files. | done (f396991) |
| P0-A10b | `briefs/P0-A10b.md` | Public `GET /api/features` → `{contact_rail}` (codex P1 on PR #889, backend half). | done (46c6c3f) |
| P0-A10 | `briefs/P0-A10.md` | Contact entry points gated on the flag (nav, desk, club tab, /introductions page) (codex P1, frontend half). | done (6ff3693) |
| P0-A11 | `briefs/P0-A11.md` | Stale thread loads discarded; request lists paged; consent controls only on active requests; stale test fixed (codex round 2 on PR #889). Eight shipped files. | done (b0f2548) |
| P0-A11b | `briefs/P0-A11b.md` | Stale send/outcome results discarded after a thread switch (codex round 3 on PR #889). Two shipped files. | done (78c0a87) |
| P0-A11c | `briefs/P0-A11c.md` | Late Introduce send / late box load discarded (codex round 4 on PR #889, P2 ×2). Four shipped files. | done (a32f6ec) |
| P0-A11d | `briefs/P0-A11d.md` | Introduction actions sequenced per box (codex round 5 on PR #889, P2; lands in PR-4). Two shipped files. | done (6d316b8) |

Done means BOTH: (1) `make gate TASK=<id>` green — you ran it, you saw it; (2) the brief's observable
is real. Then write your handback file and end with the `HANDBACK-FILED:` line, exactly as the brief says.

Status is maintained by the orchestrator (ready → in-progress → done/blocked). Do not edit this file.
