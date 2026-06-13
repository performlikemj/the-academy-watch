# Admin Overhaul — Implementation Contract (fixed spec)

Every implementation agent codes against THIS contract. Where the contract
names an APIService method, call it exactly as specified — do not invent
names. Where it names a component and props, import and use exactly that.
Verify backend endpoint paths against the source before wrapping them.

## Visual language

Match the existing admin pages: shadcn/Radix primitives from
`@/components/ui/*` (Card, Button, Badge, Tabs, Dialog, Input, Select,
Skeleton, Collapsible), lucide-react icons, Tailwind. Status colors via
existing patterns (emerald=ok, amber=warn, red=destructive). Every page:
`<div className="space-y-6">` root, an `<header>` with title +
one-line description, then Cards. Loading = Skeletons, never spinners-only.
All new interactive elements get `data-testid` attributes.

## Routes (final)

| Route | Component | File |
|---|---|---|
| /admin/dashboard | AdminDashboard | pages/admin/AdminDashboard.jsx (overhaul) |
| /admin/inbox | AdminInbox | pages/admin/AdminInbox.jsx (NEW) |
| /admin/operations | AdminOperations | pages/admin/AdminOperations.jsx (NEW) |
| /admin/seeding | AdminSeeding | pages/admin/AdminSeeding.jsx (NEW) |
| /admin/newsletters/:newsletterId | AdminNewsletterDetail | pages/admin/AdminNewsletterDetail.jsx (NEW, promoted from legacy) |
| /admin/curation | `<Navigate to="/admin/inbox?tab=takes" replace />` | — |
| /admin/flags | `<Navigate to="/admin/inbox?tab=flags" replace />` | — |
| /admin/old | DELETED | — |
| all other existing /admin/* routes | unchanged | — |

## Sidebar (AdminSidebar.jsx — owned by the lead, do not edit)

Dashboard / Inbox(badge) / ACADEMY DATA: Players, Teams, Youth Leagues(→/admin/academy),
Cohorts, Seeding & Rebuild(→/admin/seeding) / CONTENT: Newsletters, Sponsors /
PEOPLE: Users & Writers(→/admin/users) / CLUB SERVICES: Film Room(→/admin/video) /
SYSTEM: Operations, API & Configs(→/admin/tools), Classifier Tester(→/admin/sandbox), Settings

## New backend endpoint (Agent A1)

`GET /api/admin/ops/overview` (@require_api_key) — ONE cheap pass, response:

```json
{
  "tracked": {"active": 0, "inactive": 0, "placeholder_names": 0,
               "null_position": 0, "null_birth_date": 0, "null_age": 0,
               "owning_club_active": 0},
  "journeys": {"total": 0, "with_entries": 0},
  "crawl": {"supported_leagues": [{"id": 39, "name": "Premier League", "region": "Europe"}],
             "crawl_league_ids": [39, 140, 135, 78, 61]},
  "jobs": {"active": 0},
  "runs_paused": false,
  "api_usage_today": null
}
```
(api_usage_today int when APIUsageDaily is available, else null. runs_paused
from the existing run-status source. crawl from utils/supported_leagues.py.)

Also (A1):
- Add `"applied": <bool not dry_run>` to the JSON responses of
  POST /admin/journeys/recompute-academy, POST /admin/players/backfill-names,
  POST /scout/admin/send-digests.
- Replace the body of legacy POST /api/admin/tracked-players/recompute-academy-ids
  with a 410 response pointing at /api/admin/journeys/recompute-academy
  (single-transaction pattern took prod down; keep the route, kill the behavior).
- Delete src/routes/subscriptions.py IF VERIFIED unregistered + unimported.
- pytest for ops/overview + the 410 + applied flags.

## APIService contract (Agent A2 owns lib/api.js — sole writer)

Add (verify each path/params against backend source first):

```js
// Operations
adminOpsOverview()                                   // GET  /admin/ops/overview
adminRecomputeAcademy({ dryRun=true, limit=100, cursor=0 })   // POST /admin/journeys/recompute-academy {dry_run, limit, cursor}
adminBackfillPlayerNames({ dryRun=true, fetchMissing=false, fetchLimit=50 }) // POST /admin/players/backfill-names
adminSendScoutDigests({ dryRun=true, limit=50, cursor=0 })    // POST /scout/admin/send-digests
adminSyncLeagues()                                   // POST /sync-leagues
adminSyncTeams(season)                               // POST /sync-teams/<season>
adminRunsHistory()                                   // GET  /admin/runs/history
adminGetRunStatus() / adminSetRunStatus(paused)      // GET/POST /admin/run-status  (a wrapper may already exist — reuse/rename carefully, do not duplicate)
adminApiUsage()                                      // GET  /admin/api-usage
adminApiCacheStats()                                 // GET  /admin/api-cache/stats
adminJobForceFail(jobId)                             // POST /admin/jobs/<id>/force-fail
adminJobsForceFailAll()                              // POST /admin/jobs/force-fail-all
adminVideoReapStaleJobs()                            // POST /admin/video/reap-stale-jobs
adminTeamVerify(teamId, { dryRun=true, forceResyncJourneys=false }) // POST /admin/teams/<id>/verify
// Backfills (Operations page)
adminSyncAllPlayerFixtures(params)                   // POST /admin/sync-all-player-fixtures
adminBackfillRawJson(params)                         // POST /admin/fixtures/backfill-raw-json
adminBackfillAges(params)                            // POST /admin/tracked-players/backfill-ages
adminBackfillFormations(params)                      // POST /admin/fixtures/backfill-formations
// Newsletters money/digests
adminDeadlineInfo()                                  // GET  /newsletters/deadline/info
adminWriterSubmissionStatus()                        // GET  /newsletters/writers/submission-status
adminProcessDeadline({ weekStartDate })              // POST /newsletters/deadline/process
adminDigestQueue(weekKey)                            // GET  /admin/newsletters/digest-queue
adminSendNewsletterDigests(payload)                  // POST /admin/newsletters/send-digests
adminNewsletterRender(id, variant)                   // may exist; verify
adminNewsletterSend(id, { testTo, dryRun })          // POST /newsletters/<id>/send
// Writers
adminInviteJournalist(payload)                       // POST /journalists/invite
adminJournalistAllAssignments(journalistId)          // GET  /admin/journalists/<id>/all-assignments
adminSetLoanTeamAssignments(journalistId, teamIds)   // wrapper may exist unused — reuse it
adminCoverageRequests() / adminApproveCoverageRequest(id) / adminDenyCoverageRequest(id)
adminJournalistStats()                               // GET  /admin/journalist-stats
// Player links queue (Inbox)
adminPlayerLinksPending() / adminApprovePlayerLink(id) / adminRejectPlayerLink(id)
```

Existing sandbox-task wrappers (adminSandboxTasks/adminSandboxRun) stay. Do
NOT remove existing methods. Keep house style (request() helper, error paths).

## Shared components (Agent A3 creates; everyone imports)

`components/admin/ConfirmGate.jsx`
```jsx
<ConfirmGate
  open onOpenChange
  title="Run Full Rebuild"
  description="This DELETES all tracked players…"
  confirmWord="REBUILD"        // user must type this exactly
  confirmLabel="Run it"
  destructive                   // red styling
  onConfirm={() => …}
/>
```

`components/admin/CursorRunner.jsx` — drives any cursor-paged admin op.
```jsx
<CursorRunner
  title="Provenance repair (recompute-academy)"
  description="…"
  runPage={async ({ dryRun, cursor }) => {       // returns the endpoint JSON
    const r = await APIService.adminRecomputeAcademy({ dryRun, cursor, limit: 100 })
    return { nextCursor: r.next_cursor, counters: {processed: r.journeys_processed, deactivated: r.rows_deactivated, errors: r.errors}, examples: r.examples, applied: r.applied }
  }}
  dryRunDefault={true}
  confirmWord="APPLY"           // required before the first non-dry page
/>
```
Behavior: Dry-run button runs ONE page and renders counters+examples;
"Run all (dry)" loops pages until nextCursor null, accumulating counters with
a progress line; switching dry-run OFF requires ConfirmGate(confirmWord);
live run loops with the same progress UI; errors surface inline and pause the
loop with a Resume-from-cursor field. Expose data-testids:
`cursor-runner-dry`, `cursor-runner-live`, `cursor-runner-progress`.

## Page specs

### A3 — AdminOperations (+ AdminLayout bootstrap fix)
Sections (Cards, in order):
1. "System status" — adminOpsOverview(): tracked counts grid (active, placeholder
   names, NULL position/birth, owning-club active — each with an "OK/needs repair"
   badge), runs_paused toggle (adminSetRunStatus), api_usage_today, active jobs
   count + force-fail-all (ConfirmGate confirmWord="FAIL").
2. "Duties" — static registry table of every periodic duty (no scheduler exists;
   this is the manual cockpit and says so): weekly newsletter generation, Monday
   deadline processing (link→Newsletters), scout digests (runner below), transfer-
   window heal (via refresh-statuses), video stale-job reaper (link→Film Room),
   provenance repair (runners below). Columns: duty, intended cadence, last run
   (adminRunsHistory when matchable, else "unknown"), action link/button.
3. "Provenance repair" — CursorRunner for recompute-academy, then a
   backfill-names runner (single-shot with dryRun + fetchMissing + fetchLimit
   controls and a quota warning when fetchMissing), then a "Verify applied state"
   panel that re-fetches adminOpsOverview and shows before/after counts (the
   dry-run trap is real: counters look identical — verification is the only proof).
4. "Scout digests" — CursorRunner for adminSendScoutDigests (dry pages render
   recipient preview from the response).
5. "Global footprint" — crawl panel (supported vs CRAWL_LEAGUE_IDS), Sync
   leagues button, Sync teams (season Select, current default), both behind
   small confirm dialogs with a quota note.
6. "Backfills & data tools" — adminSyncAllPlayerFixtures / backfill-raw-json /
   backfill-ages / backfill-formations forms: scope inputs, ALWAYS send
   dry_run explicitly when the endpoint supports it; show returned counts; the
   background one polls jobs.
AdminLayout.jsx fix: when `token && isAdmin && !hasApiKey`, render an inline
"Enter admin API key" screen (reuse the Settings page's storage mechanism via
AuthContext) instead of redirecting home. Only non-admins get redirected.

### A4 — AdminInbox
Tabs (URL-synced ?tab=): Manual players | Community takes | User submissions |
Flags | Tracking requests | Player links. Each tab = list with approve/reject
(+ reason where the API supports it) reusing the SAME api methods the old
pages used (AdminCuration.jssx, AdminFlags.jsx, AdminPlayers Submissions tab,
AdminTeams Tracking Requests tab are the reference implementations — port the
behavior, not the layout). Header shows per-tab pending counts; export a
`fetchInboxCounts()` helper from the page module for the sidebar badge
(lead wires it). Keep "Add Community Take" creation dialog on the takes tab.
Also check e2e specs referencing /admin/curation or /admin/flags and update
them to the new routes/testids.

### A5 — AdminSeeding + AdminDashboard overhaul
AdminSeeding: decision-tree header explaining the four paths (seed one team /
seed all tracked / cohort seeding / full rebuild — when to use which);
sections: Per-team seed (port from AdminPlayers Seed tab), Seed All Tracked
(port from AdminTeams), Cohorts quick links (Big 6 + single — thin wrappers
calling the same APIs as AdminCohorts, or link there), Newsletter loan-data
seeding (reuse lib/admin-newsletters-seeding.js), Full Rebuild: rebuild-config
Select (from the same API AdminTools uses) + config editor link + variant
choice + ConfirmGate(confirmWord="REBUILD") + job progress (port from
AdminDashboard). AdminDashboard: REMOVE Full Rebuild (link to /admin/seeding),
fix duplicate quick-action cards, fix the false "writers are assigned via
Curation" copy (now Users & Writers), add: ops snapshot strip (from
adminOpsOverview: active tracked, placeholder names, owning-club actives,
active jobs), inbox pending strip, and honest Getting Started copy.

### A6 — App.jsx surgery + rescues
1. Create pages/admin/AdminNewsletterDetail.jsx from the legacy
   AdminNewsletterDetailPage (App.jsx ~515-890): render viewer + send-preview /
   test-send (adminNewsletterSend with testTo/dryRun; ConfirmGate for real
   send), YouTube links CRUD + commentary management if the APIs still exist
   (verify; drop dead calls).
2. AdminSandbox.jsx: add a second tab "Diagnostics" hosting the sandbox task
   runner (adminSandboxTasks/adminSandboxRun — port the legacy runner UI).
   Rename page header to "Classifier Tester & Diagnostics".
3. App.jsx: add routes per the table above (Inbox/Operations/Seeding/
   NewsletterDetail + redirects), DELETE the /admin/old route, the AdminPage
   monolith, AdminSandboxPage dead component, unused admin imports
   (admin-tabs.js, admin-quick-links.js usage), and delete those two lib files
   if nothing else imports them. VERIFY nothing else in App.jsx references the
   deleted components before removing; run a build.

### A7 — AdminUsers → Users & Writers
Add: Invite writer dialog (adminInviteJournalist), per-journalist expandable
assignments editor (adminJournalistAllAssignments + adminSetLoanTeamAssignments
with team multi-select), Coverage Requests tab (list/approve/deny), journalist
stats summary, curator/author toggles if endpoints exist (verify in backend;
skip silently if absent). Keep existing role toggles working.

### A8 — AdminNewsletters slim-down + AdminTeams verify + AdminVideo reaper
AdminNewsletters: DELETE the broken Missing Names section (and its dead lib
helpers), DELETE the Loan Data Seeding accordion (now on /admin/seeding —
leave a small link), add a "Deadline" card (adminDeadlineInfo +
adminWriterSubmissionStatus + Process button behind ConfirmGate
confirmWord="CHARGE" — it charges writers), add "Digest queue" card
(adminDigestQueue viewer + adminSendNewsletterDigests behind ConfirmGate),
link list rows to /admin/newsletters/:id detail page (keep the dialog for now
if removal is risky). AdminTeams: add per-team "Verify & repair" action →
dialog that runs adminTeamVerify dry-run, renders pre/post audit diff, then
Apply via ConfirmGate; forceResyncJourneys checkbox labeled quota-spending.
AdminVideo: maintenance card with "Reap stale jobs" button
(adminVideoReapStaleJobs) showing reaped count.

## Hard rules for every agent

- File ownership is EXCLUSIVE per the assignments above. Never edit a file
  another agent owns (especially lib/api.js — that is A2's alone; App.jsx is
  A6's alone). If you need a method/component, code against this contract.
- pnpm lint must pass on your files (run `pnpm exec eslint <your files>`).
- Do not run `pnpm build` (integration does); do not commit; leave changes in
  the working tree.
- Reuse existing api methods where they exist — check lib/api.js READ-ONLY.
- Every destructive or money action goes behind ConfirmGate.
- Dry-run defaults ON everywhere the backend supports it; send dry_run
  explicitly always.
