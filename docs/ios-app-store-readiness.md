# iOS App Store readiness assessment

**Task:** IR-1

**Branch assessed:** `docs/ios-readiness`

**Assessment date:** 2026-07-24

**Verdict:** **Not ready to submit.** Ten launch-readiness blockers remain. Six contain unequivocal Apple/App Store Connect gates (in-app deletion, review access, privacy policy/disclosures, a live support contact, the required-reason privacy manifest, and complete metadata plus a selectable build); the others are product-scope, safety, policy-timeline, or quality gates called out explicitly below. The clearest rejection risk is the absence of in-app account deletion even though passwordless verification automatically creates an account.

## Scope, method, and status language

This was a read-only audit of all 116 tracked files under `academy-watch-ios/`: 53 production Swift files, 23 XCTest files containing 108 test methods, 25 JSON fixtures, the plist and Xcode/XcodeGen configuration, assets, scripts, and project files. Feature coverage includes Account, Auth, Compare, Contact, Lists, Player Detail, Reporting, Scout Desk, Showcase, and Watchlist under `academy-watch-ios/AcademyWatch/Features/`; shared authentication, availability, models, networking, performance, and caching under `academy-watch-ios/AcademyWatch/Core/`; and the complete unit-test/fixture corpus under `academy-watch-ios/AcademyWatchTests/`.

The backend review covered the requested scout, showcase, contact, trust, account, and player-suppression blueprints under `academy-watch-backend/src/routes/`, registered under `/api` in `academy-watch-backend/src/main.py:109-121`, plus the auth and player-detail routes directly required by the two stories.

The status terms used below are:

- **GREEN** — the core user step can be completed and its supporting route is available today; a row can still record a degraded subsection or readiness defect.
- **DARK** — the app surface is present, but its required contact/interest route deliberately returns 404 while `CONTACT_RAIL_ENABLED` is false.
- **MISSING / INCOMPLETE** — the required in-app surface, distribution state, or an explicitly requested part of the step is absent.
- **LIVE** — registered and not gated by `CONTACT_RAIL_ENABLED`; for public/auth-bound contracts this was corroborated by a safe production probe where possible.

`CONTACT_RAIL_ENABLED` defaults to false and the guard aborts with 404 in `academy-watch-backend/src/services/contact.py:74-87`. Every `/api/contact/*` request is hidden before authentication in `academy-watch-backend/src/routes/contact.py:58-64`, and `/api/showcase/mine/interest-signals` is hidden in `academy-watch-backend/src/routes/showcase.py:80-84,1733-1736`. The iOS app intentionally converts those 404s into sticky feature-unavailable state in `academy-watch-ios/AcademyWatch/Core/FeatureAvailability/ContactFeatureAvailability.swift:10-16,27-43`.

### Audit coverage checkpoints

| Area | Evidence and finding |
|---|---|
| App shell and navigation | `academy-watch-ios/AcademyWatch/App/AcademyWatchApp.swift` and `academy-watch-ios/AcademyWatch/App/RootTabView.swift:132-229` compose Scout Desk, Watchlist, Lists, Account, sign-in, and authenticated refreshes. |
| Authentication and secure local state | `academy-watch-ios/AcademyWatch/Features/Auth/SignInView.swift:59-73,106-191,222-263`, `academy-watch-ios/AcademyWatch/Core/Auth/AuthManager.swift:54-94`, and `academy-watch-ios/AcademyWatch/Core/Auth/KeychainTokenStore.swift:44-74` implement email-code login and this-device-only Keychain token storage. |
| Feature surfaces | All production feature files under `academy-watch-ios/AcademyWatch/Features/Account/`, `Auth/`, `Compare/`, `Contact/`, `Lists/`, `PlayerDetail/`, `Reporting/`, `ScoutDesk/`, `Showcase/`, and `Watchlist/` were traced to their API methods in `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:165-520`. |
| Models and fixtures | All app models under `academy-watch-ios/AcademyWatch/Core/Models/` were checked against all 25 payload fixtures under `academy-watch-ios/AcademyWatchTests/Fixtures/`. |
| Tests | All 23 Swift test files under `academy-watch-ios/AcademyWatchTests/` were reviewed; they cover auth, Keychain behavior, API decoding, caching, Scout Desk, details, watchlists, lists, compare, claims, showcase, verification, contact, reports, and mutation concurrency. There is no XCUITest target; `academy-watch-ios/project.yml:40-52` defines only a unit-test target. |
| Plist and build project | `academy-watch-ios/AcademyWatch/Info.plist:5-33`, `academy-watch-ios/project.yml:3-38`, and `academy-watch-ios/AcademyWatch.xcodeproj/project.pbxproj:907-925` agree on version/build, deployment, bundle, and signing configuration. |
| Assets | The universal 1024 icon is declared in `academy-watch-ios/AcademyWatch/Assets.xcassets/AppIcon.appiconset/Contents.json:2-8`; launch image/color assets are declared in `academy-watch-ios/AcademyWatch/Assets.xcassets/LaunchBoot.imageset/Contents.json:2-17` and `academy-watch-ios/AcademyWatch/Assets.xcassets/LaunchBackground.colorset/Contents.json:2-14` and wired by `academy-watch-ios/AcademyWatch/Info.plist:24-32`. |
| Entitlements and dependencies | No `.entitlements` file, push capability, `aps-environment`, or notification registration exists. The target has no package products in `academy-watch-ios/AcademyWatch.xcodeproj/project.pbxproj:530-566`, and `academy-watch-ios/project.yml:14-62` declares no external package dependency. |

### Safe production corroboration

On 2026-07-24, read-only GET/OPTIONS probes used the exact HTTPS base URL hard-coded by the release client in `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:118-120`. No account was created and no state-changing route was called.

| Probe | Result | Interpretation |
|---|---:|---|
| `/api/health`, `/api/scout/players?per_page=1&page=1`, `/api/scout/leaderboards?limit=1` | 200 | Production service and public Scout Desk contracts respond. |
| `/api/players/403064/profile`, `/season-stats`, `/stats`, `/journey`, `/showcase` | 200 | Sampled player-detail sections respond. |
| `/api/players/403064/availability` | 500 | A production defect is visible for the sampled player; the body returned reference `0f47a6b8`. The route is implemented at `academy-watch-backend/src/routes/players.py:1097-1152`. |
| `/api/scout/watchlist`, `/api/scout/lists`, `/api/me/claims`, `/api/scout/verification`, `/api/account/export` | 401 | Routes are registered and authentication-gated, rather than flag-dark. |
| `/api/contact/requests`, `/api/showcase/mine/interest-signals` | 404 | Matches the source-controlled dark rail. |

The task statement supplies the remaining production facts that cannot safely be proven by mutation: account deletion/export, reports, and takedown intake are live; the contact rail is dark pending publication of the Terms of Service (ToS).

---

## Part A — user-story completeness matrix

### SCOUT story

| # | User step | In-app implementation | Backend state | Works today? | Gap / assessment |
|---:|---|---|---|---|---|
| 1 | Install | The app target, launch configuration, Release archive action, iPhone device family, automatic signing, and team are configured in `academy-watch-ios/project.yml:15-38` and `academy-watch-ios/AcademyWatch.xcodeproj/xcshareddata/xcschemes/AcademyWatch.xcscheme:112-115`. | N/A | **MISSING / UNVERIFIED** as a public install. | No archive upload, processed build, TestFlight installation, or App Store version is evidenced in the repository. |
| 2 | Sign in with passwordless email | The two-stage email/code UI and API calls are in `academy-watch-ios/AcademyWatch/Features/Auth/SignInView.swift:59-73,106-191,222-263`, `academy-watch-ios/AcademyWatch/Core/Auth/AuthManager.swift:54-94`, and `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:268-285`; the token is stored in `academy-watch-ios/AcademyWatch/Core/Auth/KeychainTokenStore.swift:44-74`. | **LIVE.** `POST /api/auth/request-code`, `POST /api/auth/verify-code`, and `GET /api/auth/me` are in `academy-watch-backend/src/routes/auth_routes.py:138-259`. Successful verification creates the account at `:197-205`. | **GREEN for a user with inbox access.** | App Review cannot depend on access to a private inbox. There is no Release reviewer-code path; the fixture identities are `#if DEBUG` only in `academy-watch-ios/AcademyWatch/App/RootTabView.swift:51-77`. |
| 3 | Browse Scout Desk | Search, filters, sort, pagination, rows, and leaderboards are in `academy-watch-ios/AcademyWatch/Features/ScoutDesk/ScoutDeskView.swift:55-109,112-189,192-419` and `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:165-197`. | **LIVE/public.** `GET /api/scout/players` and `/leaderboards` are in `academy-watch-backend/src/routes/scout.py:657-808`; both returned 200 in the production sample. | **GREEN.** | None found for the core browse step. |
| 4 | Open player detail | Navigation and independently loaded profile, stats, journey, availability, and showcase sections are in `academy-watch-ios/AcademyWatch/Features/PlayerDetail/PlayerDetailView.swift:81-180`, `academy-watch-ios/AcademyWatch/Features/PlayerDetail/PlayerDetailViewModel.swift:145-226`, and `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:200-221`. | **LIVE/public.** Routes are in `academy-watch-backend/src/routes/players.py:241-251,493-710,1097-1152`, `academy-watch-backend/src/routes/journey.py:36`, and `academy-watch-backend/src/routes/showcase.py:1494-1508`. | **GREEN with a defect.** | The sampled production availability call returned 500. Because sections load independently, the rest of the sampled detail remained available, but this is not review-ready. |
| 5 | Use watchlist, lists, and compare | Watchlist, custom-list creation/detail/add/remove, and compare are in `academy-watch-ios/AcademyWatch/Features/Watchlist/WatchlistView.swift:58-203`, `academy-watch-ios/AcademyWatch/Features/Lists/ListsView.swift:33-196,235-386`, `academy-watch-ios/AcademyWatch/Features/Lists/AddPlayerToListButton.swift:14-150`, `academy-watch-ios/AcademyWatch/Features/Compare/CompareView.swift:12-40`, and `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:414-521`. | **LIVE.** Compare is `academy-watch-backend/src/routes/scout.py:817-1010`; watchlists are `:1072-1279`; lists are `:1610-1947`. | **GREEN after sign-in.** | Watchlist note/digest mutation exists in the API client but has no current editing UI; web-created non-player follows are display-only in `academy-watch-ios/AcademyWatch/Features/Lists/ListsView.swift:270-279`. Neither prevents the named core step. |
| 6 | Apply for scout verification | Account navigation, application/status form, identity, role, statement, and evidence URLs are in `academy-watch-ios/AcademyWatch/Features/Account/AccountView.swift:179-212`, `academy-watch-ios/AcademyWatch/Features/Account/ScoutVerificationView.swift:111-358`, `academy-watch-ios/AcademyWatch/Features/Account/ScoutVerificationViewModel.swift:55-146,232-240`, and `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:254-266`. | **LIVE.** Authenticated GET/POST are in `academy-watch-backend/src/routes/trust.py:168-233`; admin review is at `:236-335`. | **GREEN for submission/status polling.** | Approval is an operator workflow; no applicant push/email notification path was found. |
| 7 | Request introduction, including contracted-player attestation | The CTA conditions are in `academy-watch-ios/AcademyWatch/Features/PlayerDetail/PlayerDetailView.swift:201-214`; request, privacy disclosure, and permission-attestation retry are in `academy-watch-ios/AcademyWatch/Features/Contact/IntroductionRequestView.swift:220-328` and `academy-watch-ios/AcademyWatch/Features/Contact/IntroductionRequestViewModel.swift:20-27,215-239`. | **DARK.** `POST /api/contact/requests` is flag-gated at `academy-watch-backend/src/routes/contact.py:246-398`. It requires a verified scout and approved self-claim; contract routing and literal off-platform permission attestation are at `academy-watch-backend/src/services/contact.py:36-39,153-170` and `academy-watch-backend/src/routes/contact.py:288-367`. | **DARK and semantically incomplete.** | The backend's `club_notified` path requires the scout to confirm that current-club permission **already exists**, while the app says the scout “has, or will obtain” permission (`academy-watch-ios/AcademyWatch/Features/Contact/IntroductionRequestViewModel.swift:26-27`). The `club_included` path does not use that attestation; it requires a separate club-manager consent operation. |
| 8 | Open the thread | Sent requests and the message thread/composer are in `academy-watch-ios/AcademyWatch/Features/Contact/SentContactRequestsView.swift:11-121`, `academy-watch-ios/AcademyWatch/Features/Contact/ContactThreadView.swift:31-246`, and `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:304-390`. | **DARK.** GET/POST messages are flag-gated at `academy-watch-backend/src/routes/contact.py:597-684` and require accepted player consent plus club consent when applicable (`:183-196`). | **DARK; club-included is additionally incomplete.** | No thread can be fetched while the rail is off. After enablement, a `club_included` thread still depends on a club-manager client/API operation that is not evidenced in the audited repo. |
| 9 | Report an outcome | The outcome sheet and mutation are in `academy-watch-ios/AcademyWatch/Features/Contact/ContactThreadView.swift:374-463` and `academy-watch-ios/AcademyWatch/Features/Contact/ContactThreadViewModel.swift:194-245`. | **DARK.** `POST /api/contact/requests/<id>/outcome` is flag-gated at `academy-watch-backend/src/routes/contact.py:687-739`. | **DARK — no.** | Depends on an accessible contact thread. |
| 10 | Report abusive content | Message/report actions and reason/details submission are in `academy-watch-ios/AcademyWatch/Features/Contact/ContactThreadView.swift:295-372`, `academy-watch-ios/AcademyWatch/Features/Reporting/ContentReportView.swift:20-111`, and `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:396-412`. | **LIVE intake.** `POST /api/reports` remains independent of the rail in `academy-watch-backend/src/routes/trust.py:343-371`; admin list/resolve/dismiss is at `:374-431`. | **DARK from the app today.** | The only iOS report entry points are a dark incoming request/thread. The app also lacks a report action for public showcase/profile content. |

**SCOUT summary:** primary works-today tally **5 GREEN / 4 DARK / 1 MISSING**. The missing step is public/TestFlight installation evidence. The introduction and thread rows are counted DARK because the rail is the immediate blocker, but both carry additional contracted-player gaps that a flag flip alone will not cure: permission copy conflicts with the backend attestation, and no club-manager consent client is evidenced. Reviewer authentication remains a blocker even though user authentication is green.

### PLAYER story

| # | User step | In-app implementation | Backend state | Works today? | Gap / assessment |
|---:|---|---|---|---|---|
| 1 | Install | Same app/archive configuration as SCOUT: `academy-watch-ios/project.yml:15-38` and `academy-watch-ios/AcademyWatch.xcodeproj/xcshareddata/xcschemes/AcademyWatch.xcscheme:112-115`. | N/A | **MISSING / UNVERIFIED** as a public install. | No TestFlight/App Store distribution evidence. |
| 2 | Sign in | Same first-party email-code flow in `academy-watch-ios/AcademyWatch/Features/Auth/SignInView.swift:59-73,106-191,222-263` and `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:268-285`. | **LIVE** at `academy-watch-backend/src/routes/auth_routes.py:138-259`. | **GREEN for a user with inbox access.** | Reviewer access is still blocked. |
| 3 | Claim own profile with 18+ gate and contract attestation | “This is me,” relationship, contract status, current club/program, and submission are in `academy-watch-ios/AcademyWatch/Features/Showcase/PlayerClaimSectionView.swift:247-290,400-465,551-590`, `academy-watch-ios/AcademyWatch/Core/Models/PlayerClaimModels.swift:3-97`, and `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:239-252`. | **LIVE.** `POST /api/players/<id>/claim` creates a pending claim in `academy-watch-backend/src/routes/showcase.py:1567-1652`; known DOB and age 18+ are enforced at `:1040-1089`; admin approval is at `:3766-3803`. | **MISSING / INCOMPLETE in-app gate.** An eligible adult can submit and the server blocks a minor/unknown DOB. | The app has no age statement, DOB explanation, or 18+ acknowledgement; the user encounters only a backend error. Claim proof verification also exists at `academy-watch-backend/src/routes/showcase.py:1696-1730` but has no iOS API method among `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:239-251`. |
| 4 | See “Scouts are watching you” | The approved-owner-only card is in `academy-watch-ios/AcademyWatch/Features/PlayerDetail/PlayerDetailView.swift:142-145,183-186`, `academy-watch-ios/AcademyWatch/Features/Showcase/PlayerInterestSignalsCard.swift:13-46`, and `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:392-394`. | **DARK.** The identity-free aggregate route is flag-gated at `academy-watch-backend/src/routes/showcase.py:1733-1846`. | **DARK — no.** | The 404 records shared unavailability and hides the card in `academy-watch-ios/AcademyWatch/Features/Showcase/PlayerInterestSignalsViewModel.swift:139-145,192-204` and `academy-watch-ios/AcademyWatch/Core/FeatureAvailability/ContactFeatureAvailability.swift:38-42`. |
| 5 | Receive an introduction | The incoming inbox and refresh/load behavior are in `academy-watch-ios/AcademyWatch/Features/Contact/IncomingContactRequestsView.swift:14-119` and `academy-watch-ios/AcademyWatch/Features/Contact/IncomingContactRequestsViewModel.swift:135-190`. | **DARK.** Inbox is `GET /api/contact/requests?box=inbox` at `academy-watch-backend/src/routes/contact.py:408-450`. | **DARK — no.** | Delivery is pull-only. No APNs registration/device token exists; project capabilities contain no push entitlement in `academy-watch-ios/project.yml:15-38` or `academy-watch-ios/AcademyWatch.xcodeproj/project.pbxproj:907-925`. |
| 6 | Accept/decline, including club-consent case | Player accept/decline and waiting-for-club copy are in `academy-watch-ios/AcademyWatch/Features/Contact/IncomingContactRequestsView.swift:203-310,325-375` and `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:324-351`. | **DARK.** Player actions are at `academy-watch-backend/src/routes/contact.py:457-501`; an active club manager must separately grant/decline club consent at `:504-565`, and messaging requires both gates. | **DARK and incomplete after enablement.** | The iOS client has no club-consent method or manager surface in `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:288-390`, and no other club-manager client/API operation is evidenced in the audited repo. |
| 7 | Open the thread | The incoming-player path navigates to `academy-watch-ios/AcademyWatch/Features/Contact/ContactThreadView.swift:31-246`. | **DARK** at `academy-watch-backend/src/routes/contact.py:597-684`. | **DARK — no.** | Requires player acceptance and, when routed through a club, external club consent. |
| 8 | Report a message | The app offers report for counterpart/club messages in `academy-watch-ios/AcademyWatch/Features/Contact/ContactThreadView.swift:295-372` and submits through `academy-watch-ios/AcademyWatch/Features/Reporting/ContentReportView.swift:20-111`. | Report intake is **LIVE** at `academy-watch-backend/src/routes/trust.py:343-371`; message access is **DARK**. | **DARK from the app today.** | The live report route does not help when the app cannot fetch the message ID. |
| 9 | Intended web-only takedown request | No suppression/takedown API method or Account/Player Detail link exists in `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:239-520` or `academy-watch-ios/AcademyWatch/Features/Account/AccountView.swift:94-340`. | **LIVE.** Public neutral-response `POST /api/players/<id>/takedown-request` is in `academy-watch-backend/src/routes/player_suppression.py:71-131`. | **MISSING in app; backend-only in the audited repo.** | The task classifies completion as web-only, but no user-facing web surface was verified. Add an in-app explanatory deep link after the live web URL is confirmed. |
| 10 | Intended web-only account deletion | The signed-in Account surface ends with sign-out in `academy-watch-ios/AcademyWatch/Features/Account/AccountView.swift:94-115,309-318`; no delete method exists in `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:1-116,239-520`. | **LIVE.** `POST /api/account/delete` requires `{ "confirm": "DELETE" }` and deletes immediately at `academy-watch-backend/src/routes/account.py:33-59`. | **MISSING in app; backend-only in the audited repo.** | **Guideline 5.1.1(v) blocker.** A user-facing web surface was not verified, and a web-only flow would still need to be directly initiated from the app under Apple's guidance. |
| 11 | Intended web-only data export | No export method or Account link exists in `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:1-116,239-520` or `academy-watch-ios/AcademyWatch/Features/Account/AccountView.swift:94-340`. | **LIVE.** `GET /api/account/export` is in `academy-watch-backend/src/routes/account.py:20-30`; its data domains are assembled in `academy-watch-backend/src/services/account.py:163-303`. | **MISSING in app; backend-only in the audited repo.** | No user-facing web surface was verified. This is not the same explicit App Review requirement as deletion, but the app should expose a confirmed web link or native download. |

**PLAYER summary:** primary works-today tally **1 GREEN / 5 DARK / 5 MISSING or incomplete**. The missing/incomplete rows are distribution, the in-app 18+ gate, takedown, deletion, and export. Accept/decline is counted DARK because the rail is the immediate blocker, but the club-consent case remains incomplete after enablement until a manager client exists. Thus the primary count is useful for today's state but understates one additional structural gap.

### Backend contract state at a glance

| Contract family | State today | Evidence |
|---|---|---|
| Auth | **LIVE** | `academy-watch-backend/src/routes/auth_routes.py:138-259`; auto-account creation at `:197-205`. |
| Scout browse/compare/watchlists/lists | **LIVE** | `academy-watch-backend/src/routes/scout.py:657-1010,1072-1279,1610-1947`. |
| Showcase, claims, claim review | **LIVE** | `academy-watch-backend/src/routes/showcase.py:1494-1730,2360-2367,3766-3803`. |
| Interest signals | **DARK** | `academy-watch-backend/src/routes/showcase.py:80-84,1733-1846`. |
| Contact request/inboxes/consent/messages/outcomes | **DARK** | Global 404 at `academy-watch-backend/src/routes/contact.py:58-64`; routes at `:246-739`. |
| Scout verification and content reports | **LIVE** | `academy-watch-backend/src/routes/trust.py:168-431`. |
| Account export and deletion | **LIVE** | `academy-watch-backend/src/routes/account.py:20-59`; services at `academy-watch-backend/src/services/account.py:163-303,563-699`. |
| Player takedown/suppression request | **LIVE** | `academy-watch-backend/src/routes/player_suppression.py:71-131`. |

---

## Part B — App Store submission gaps

### Policy-source freshness

The following assessment was checked against Apple's official [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/) on 2026-07-24; that page reported an update date of 2026-06-08. Apple can change guidance, App Store Connect fields, rating logic, and enforcement without a repository change. **The operator must re-verify every policy answer immediately before upload/submission.**

### 1. Account deletion — Guideline 5.1.1(v): BLOCKER

The email-code flow creates an account on first successful verification in `academy-watch-backend/src/routes/auth_routes.py:197-205`. Apple says that an app supporting account creation must also let users initiate deletion within the app; that includes automatically created accounts. See [Guideline 5.1.1(v)](https://developer.apple.com/app-store/review/guidelines/) and Apple's [account-deletion implementation guidance](https://developer.apple.com/support/offering-account-deletion-in-your-app/).

The backend is ready: `POST /api/account/delete` is live at `academy-watch-backend/src/routes/account.py:33-59`. The app is not: Account offers sign-out but no delete action in `academy-watch-ios/AcademyWatch/Features/Account/AccountView.swift:94-115,309-318`, and `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:1-116,239-520` has no account-deletion method.

Required remediation: add a discoverable Account action, explain scope and immediacy, require an intentional destructive confirmation, call the existing endpoint, and clear the local Keychain credential on success. A support-email-only process is not sufficient.

### 2. User-generated content — Guideline 1.2: high-risk BLOCKER / operator judgment

[Guideline 1.2](https://developer.apple.com/app-store/review/guidelines/) currently requires safeguards for UGC including filtering objectionable material, reporting with timely response, blocking abusive users, and published developer contact information.

| 1.2 safeguard | Evidence | Assessment |
|---|---|---|
| Report | iOS reports an incoming request in `academy-watch-ios/AcademyWatch/Features/Contact/IncomingContactRequestsView.swift:203-210,287-295` or another participant's message through `academy-watch-ios/AcademyWatch/Features/Contact/ContactThreadView.swift:295-372`, `academy-watch-ios/AcademyWatch/Features/Reporting/ContentReportView.swift:20-111`, and `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:396-412`. Backend intake/admin handling is `academy-watch-backend/src/routes/trust.py:343-431`. | **Implemented**, but its only iOS entry paths are dark today and there is no report affordance on public showcase/profile UGC. The endpoint stores caller-supplied subject type/ID without verifying subject existence or participant access (`academy-watch-backend/src/routes/trust.py:343-364`), so report-integrity hardening is also warranted. |
| Block abusive users | The app explicitly says a report does not block the scout and an accepted request can no longer be declined in `academy-watch-ios/AcademyWatch/Core/Models/FullCircleModels.swift:482-513`. Decline is a pending-request action in `academy-watch-ios/AcademyWatch/Features/Contact/IncomingContactRequestsView.swift:247-295,361-375`; the backend cooldown is only same-scout/same-player and defaults to 30 days in `academy-watch-backend/src/services/contact.py:24-26,62-71` and `academy-watch-backend/src/routes/contact.py:306-323`. | **Not implemented.** Decline + report is not an enduring user block and cannot stop an accepted thread. Whether Apple accepts that v1 interpretation is a review judgment, but the literal control is absent; the safe decision is to add a persistent block (with mute as an optional supplement). |
| Filtering | Introduction and message POSTs are length-bounded/rate-limited and HTML-sanitized in `academy-watch-backend/src/routes/contact.py:246-249,632-676`, `academy-watch-backend/src/services/contact.py:90-105`, and `academy-watch-backend/src/utils/sanitize.py:22-29`; owner showcase content is held for approval as described in `academy-watch-backend/src/routes/showcase.py:4-15`. | **Incomplete.** Sanitization is not objectionable-content filtering, and private messages have no filter or quarantine path. Define a defensible pre/post filtering and containment policy before review. |
| Moderation response | Admin queue/resolve/dismiss exists at `academy-watch-backend/src/routes/trust.py:374-431`, and `docs/runbooks/incident-response.md:1-16,919-971` covers the trust workflow. | **Backend/runbook present; staffed timely-response process unverified.** The runbook says reports do not automatically stop contact, so containment remains a separate operator action. |
| Published contact method | Account has no privacy/terms/support/contact link in `academy-watch-ios/AcademyWatch/Features/Account/AccountView.swift:94-340`; `academy-watch-ios/AcademyWatch/Features/Account/ScoutVerificationView.swift:477-483` says “Contact Academy Watch” without an actionable link. | **Missing.** Supply a live support URL/contact method in-app and in App Store metadata; Guideline 1.5 is also relevant. |
| Terms/community rules | No ToS/EULA/community-rules URL or acceptance exists in the iOS feature/account files or `academy-watch-ios/AcademyWatch/Info.plist:5-33`. The task states that service ToS is drafted but unpublished. | **Missing.** Apple's standard EULA may govern the binary if no custom EULA is supplied, but it does not replace service UGC rules, moderation terms, or the task's ToS prerequisite. |

The incident-response runbook exists at `docs/runbooks/incident-response.md`, but it also records missing paging/legal/evidence-system destinations at `docs/runbooks/incident-response.md:1158-1160`. Operational response ownership and response time cannot be verified from code.

### 3. Privacy policy and App Privacy

#### Privacy policy — Guideline 5.1.1(i): BLOCKER

[Guideline 5.1.1(i)](https://developer.apple.com/app-store/review/guidelines/) requires a privacy-policy link in App Store Connect and easy access inside the app. No privacy URL or in-app link exists in `academy-watch-ios/AcademyWatch/Features/Account/AccountView.swift:94-340` or `academy-watch-ios/AcademyWatch/Info.plist:5-33`. No published policy is evidenced in the repository. The operator must publish a policy covering collection, use, sharing/processors, retention, deletion, and withdrawal, then link it in both places.

#### Privacy Nutrition Label filling checklist

Apple's [App Privacy details](https://developer.apple.com/app-store/app-privacy-details/) and [App Store Connect privacy reference](https://developer.apple.com/help/app-store-connect/reference/app-privacy/) govern the final classifications. “Transmitted” below is code evidence; Apple generally treats off-device data retained beyond servicing the real-time request as collected. Final labels must cover backend and all partners, not only Swift code.

| Data / Apple label candidate | Exact app transmission or storage evidence | Recommended submission answer / operator check |
|---|---|---|
| **Name** | Account display name is returned in `academy-watch-ios/AcademyWatch/Core/Models/AuthModels.swift:24-75`; scout full name plus organization, role/title, statement, and public evidence URLs are submitted by `academy-watch-ios/AcademyWatch/Features/Account/ScoutVerificationView.swift:192-358` and modeled in `academy-watch-ios/AcademyWatch/Core/Models/FullCircleModels.swift:40-60`. | **Collected, linked, App Functionality.** Classify professional fields/evidence as Other User Content or Other Data as the current questionnaire directs. |
| **Email Address** | Email and the entered 11-character code are sent by `academy-watch-ios/AcademyWatch/Features/Auth/SignInView.swift:106-175` and `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:268-281`; account email is returned in `academy-watch-ios/AcademyWatch/Core/Models/AuthModels.swift:24-75`. | **Collected, linked, App Functionality.** |
| **User ID** | Account/user identifiers are returned in `academy-watch-ios/AcademyWatch/Core/Models/AuthModels.swift:24-87`; bearer credentials are attached to protected requests in `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:575-583`. | **Collected, linked, App Functionality.** Do not classify the opaque bearer token itself as a device identifier. |
| **Emails or Text Messages** | Introduction text, thread messages, and outcome text are sent in `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:288-301,367-389` and modeled in `academy-watch-ios/AcademyWatch/Core/Models/FullCircleModels.swift:297-390`. | **Collected, linked, App Functionality** when the contact rail is enabled; Apple's taxonomy puts private in-app message content here. |
| **Other User Content** | Custom list names/player follows use `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:455-508`; claim contract status/current club is in `academy-watch-ios/AcademyWatch/Core/Models/PlayerClaimModels.swift:44-97`; reports send subject/reason/details at `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:396-411`. Approved-owner attestation updates also resend profile bio/positions/foot/height from `academy-watch-ios/AcademyWatch/Core/Models/ShowcaseModels.swift:145-199`. Watchlist notes are received/displayed and a mutation method exists at `academy-watch-ios/AcademyWatch/Features/Watchlist/WatchlistViewModel.swift:150-174`, but no current UI caller was found. | **Collected, linked, App Functionality.** Include verification statements/evidence, claim attestations, list names, report details, outcome notes, profile-edit fields, and server-held watchlist notes. Do not claim new note collection from this build unless another client supplies them or the dormant mutation becomes reachable. |
| **Product Interaction** | Server-linked watchlist membership, list follows, contact accept/decline/withdraw/outcome transitions, and compare player IDs are transmitted at `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:304-390,414-521`. Digest settings are received, but the mutation method at `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:447-453` has no current caller. | **Collected, linked, App Functionality;** evaluate **Product Personalization** too because saved player choices shape the experience. Classify from all clients/backend retention, not only the reachable iOS mutations. |
| **Search History** | Free-text search and browse filters are sent as URL query parameters by `academy-watch-ios/AcademyWatch/Features/ScoutDesk/ScoutBrowseConfiguration.swift:252-269` and `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:165-197`. | Answer **Yes only if** application, Azure ingress, proxy, or analytics logs retain those queries. Retention was not verifiable from app code. |
| **IP/network and coarse-location implications** | The backend reads remote IP for auth/rate limiting in `academy-watch-backend/src/routes/auth_routes.py:147-161,183-210` and `academy-watch-backend/src/routes/contact.py:67-68`; URLSession also exposes ordinary network metadata to servers. | Verify Azure/app/log-processor retention and use. IP transit alone is not a Device ID; classify coarse location or Other Data only if actually derived/retained. |
| **External media traffic** | Player photos/club logos load through remote `AsyncImage` in `academy-watch-ios/AcademyWatch/Features/PlayerDetail/PlayerDetailView.swift:423-467`; YouTube thumbnails/page traffic is external in `academy-watch-ios/AcademyWatch/Features/Showcase/ShowcaseSectionView.swift:177-230,308-322` and `academy-watch-ios/AcademyWatch/Core/Models/ShowcaseModels.swift:245-262`. | Name hosting/CDN/YouTube processors in the policy as applicable and verify whether their handling changes labels. The app does not upload a user's photos/videos. |
| **Local-only data** | Token: this-device-only Keychain in `academy-watch-ios/AcademyWatch/Core/Auth/KeychainTokenStore.swift:44-67`. Public Scout JSON: Caches/URL cache in `academy-watch-ios/AcademyWatch/Core/Performance/ScoutResponseCache.swift:35-129`. Authenticated requests set `no-store` at `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:575-590`. | Local-only storage is not “collected” merely because it remains on device. Explain local retention/security in the policy where helpful. |
| **Explicitly absent in app code** | There is no IDFA/IDFV/device ID, contacts, location, camera, microphone, photo-library, health, payment, ad, analytics, crash-reporting, or social-login SDK/capability in `academy-watch-ios/project.yml:14-62`, `academy-watch-ios/AcademyWatch.xcodeproj/project.pbxproj:530-566`, or the imports under `academy-watch-ios/AcademyWatch/`. | Answer **No** only after confirming backend/vendors and the final archive add none of these. Remote content display is not a user-media upload. |

#### Tracking and ATT

No `AppTrackingTransparency`, AdSupport/IDFA, `NSUserTrackingUsageDescription`, analytics/ad/social SDK, or tracking-domain declaration exists in `academy-watch-ios/project.yml:14-62`, `academy-watch-ios/AcademyWatch/Info.plist:5-33`, or `academy-watch-ios/AcademyWatch.xcodeproj/project.pbxproj:530-566`. On code evidence, tracking is **No** and an ATT prompt is not expected. This conclusion depends on the operator confirming that backend/vendors do not link or share data across companies for targeted advertising, advertising measurement, or data-broker purposes; see Apple's [user privacy and data use guidance](https://developer.apple.com/app-store/user-privacy-and-data-use/).

#### Privacy manifest / required-reason API: BLOCKER

No `PrivacyInfo.xcprivacy` exists under `academy-watch-ios/`, yet Release code calls `ProcessInfo.processInfo.systemUptime` for elapsed-time UI behavior in `academy-watch-ios/AcademyWatch/Features/ScoutDesk/ScoutDeskViewModel.swift:89-99,342-355`. Apple lists `systemUptime` as a required-reason API and says undeclared uses are not accepted; see [systemUptime](https://developer.apple.com/documentation/foundation/processinfo/systemuptime) and [required-reason API guidance](https://developer.apple.com/documentation/bundleresources/describing-use-of-required-reason-api).

Add a target-bundled `PrivacyInfo.xcprivacy` declaring `NSPrivacyAccessedAPICategorySystemBootTime` with the accurate elapsed-event/timer reason, currently `35F9.1`; include accurate collected-data and tracking fields aligned with the final label; and run an archive privacy report to identify any additional categories. Re-verify the reason identifier and manifest schema against Apple's live documentation before upload.

### 4. Sign-in — Guideline 4.8

The app supports only its own email-code login in `academy-watch-ios/AcademyWatch/Features/Auth/SignInView.swift:59-73,106-174,222-264` and `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:268-281`. No third-party/social auth SDK or package product exists in `academy-watch-ios/project.yml:14-62` or `academy-watch-ios/AcademyWatch.xcodeproj/project.pbxproj:530-566`. Under the current first-party account exception in [Guideline 4.8](https://developer.apple.com/app-store/review/guidelines/), **Sign in with Apple is not required** on this evidence. Recheck if any social/third-party login is added.

### 5. App Review access — Guideline 2.1(a): BLOCKER

The production contract generates a random 11-character code with a five-minute expiry and emails it in `academy-watch-backend/src/routes/auth_routes.py:53-125,138-220`. The release app has no static reviewer credential or demo mode; debug destinations are compiled out at `academy-watch-ios/AcademyWatch/App/RootTabView.swift:51-77`.

Apple's [Guideline 2.1(a)](https://developer.apple.com/app-store/review/guidelines/) and [Review Information reference](https://developer.apple.com/help/app-store-connect/reference/app-information/platform-version-information) require usable review access and a live backend. Supply non-expiring review access before submission.

Recommended implementation:

1. Add an allowlisted reviewer email/static code controlled only by a server environment secret, with rate limiting, audit logging, and easy post-review revocation.
2. Seed at least one verified-scout state and one approved adult-player state, plus representative contact/club-consent data, so both stories are inspectable.
3. Put exact credentials and deterministic navigation steps in Review Notes.
4. If choosing a fully featured demo mode instead, obtain Apple's prior approval as the guideline requests; a debug-only UI is not sufficient.

### 6. Dark-feature review risk — Guidelines 2.1(a) and 2.3.1(a): BLOCKER until scope is decided

The app probes contact after authentication in `academy-watch-ios/AcademyWatch/App/RootTabView.swift:214-222`, hides Account contact links unless available in `academy-watch-ios/AcademyWatch/Features/Account/AccountView.swift:214-301`, and requires availability for the introduction CTA in `academy-watch-ios/AcademyWatch/Features/PlayerDetail/PlayerDetailView.swift:201-214`. Reviewers therefore see a coherent reduced app, but cannot inspect the product's distinguishing introduction, consent, thread, outcome, or contextual-report stories.

[Guideline 2.3.1(a)](https://developer.apple.com/app-store/review/guidelines/) bars hidden, dormant, or undocumented functionality and asks that new functionality be accessible and described in Review Notes. **Recommended decision: submit after the ToS/privacy/support material is live, the UGC controls are closed, `CONTACT_RAIL_ENABLED` is on in production, and both roles pass TestFlight.**

If the operator intentionally ships a Scout-Desk-only v1 while dark, metadata and screenshots must not promise contact, Review Notes must disclose the server-gated scope, and inaccessible contact code still carries dormant-feature risk. Review Notes do not make an inaccessible feature reviewable.

### 7. Metadata and assets

No tracked `AppStore/metadata/`, `fastlane/metadata/`, screenshot set, description, keywords, support URL, copyright, review credentials, privacy answers, or age-rating worksheet exists in the repository; the corresponding App Store Connect state is unverified. [Guideline 2.3](https://developer.apple.com/app-store/review/guidelines/) governs accurate metadata; 2.3.3 covers screenshots, 2.3.6 honest age-rating answers, 2.3.7 names/keywords, and 2.3.9 content rights and fictional screenshot data. The required fields and current screenshot rules are in Apple's [platform-version information reference](https://developer.apple.com/help/app-store-connect/reference/app-information/platform-version-information) and [screenshot specifications](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications/).

| Item | Readiness | Evidence / required action |
|---|---|---|
| App icon | **Ready.** | P4b's universal 1024 icon is declared at `academy-watch-ios/AcademyWatch/Assets.xcassets/AppIcon.appiconset/Contents.json:2-8`; the audited PNG is 1024×1024, opaque RGB. |
| Launch screen | **Ready.** | `academy-watch-ios/AcademyWatch/Info.plist:24-32`, `academy-watch-ios/project.yml:26-29`, `academy-watch-ios/AcademyWatch/Assets.xcassets/LaunchBoot.imageset/Contents.json:2-17`, and `academy-watch-ios/AcademyWatch/Assets.xcassets/LaunchBackground.colorset/Contents.json:2-14`. |
| Screenshots | **Missing from repo; ASC unverified.** | Supply 1–10 iPhone screenshots if not already present in ASC. Prepare the current 6.9-inch set at an accepted portrait size such as 1260×2736, 1290×2796, or 1320×2868 pixels (swap dimensions for landscape), and confirm the live App Store Connect device-class prompts at upload. The target is iPhone-only in `academy-watch-ios/project.yml:38`, so no iPad set is required unless device-family support changes. |
| Description and keywords | **Missing from repo; ASC unverified.** | Write an accurate description (currently up to 4,000 characters) and a ≤100-byte keyword field if absent in ASC. Per the portfolio rule, lead with useful generic football/scouting terms before branded/niche variants; do not repeat the app/company name or use competitors' marks. |
| Support and privacy URLs | **Missing/unverified.** | Publish working HTTPS pages with real contact information and place both URLs in App Store Connect and the app; Account currently has none at `academy-watch-ios/AcademyWatch/Features/Account/AccountView.swift:94-340`. |
| Copyright | **Missing from repo; ASC unverified.** | Supply the year the rights were obtained and the verified rights-owning entity; ownership cannot be inferred from code. |
| Review notes/account | **Missing from repo; ASC unverified.** | Explain the rail, consent routing, moderation, and exact reviewer credentials/steps. |
| App Privacy answers | **Missing from repo; ASC unverified.** | Complete from the checklist above and actual processor/log-retention facts. |

#### Age-rating questionnaire inputs

Use Apple's current [age-rating definitions](https://developer.apple.com/help/app-store-connect/reference/app-information/age-ratings-values-and-definitions/) at submission:

- **User-Generated Content: Yes** — approved owner-created showcase bio/reel content is publicly distributed by `academy-watch-backend/src/routes/showcase.py:1-15,2436-2509,2853-2908` and displayed in `academy-watch-ios/AcademyWatch/Features/Showcase/ShowcaseSectionView.swift:52-99`. Private claims, verification evidence, reports, list/watchlist notes, and direct messages are still privacy/safety-relevant, but do not by themselves establish Apple's broad-distribution UGC descriptor.
- **Messaging and Chat: Yes** when the contact rail is enabled — composer/thread UI is `academy-watch-ios/AcademyWatch/Features/Contact/ContactThreadView.swift:31-246`.
- Intended questionnaire answers appear to be **Advertising: No**, **Social Media: No**, and **Unrestricted Web Access: No**, because no ad/social SDK exists in `academy-watch-ios/project.yml:14-62` and the only browser launch is a fixed YouTube destination in `academy-watch-ios/AcademyWatch/Features/Showcase/ShowcaseSectionView.swift:308-322`. The operator must validate the live questionnaire definitions and SFSafari navigation behavior.
- Football content intends no mature/violent/sexual/gambling descriptors, but free-text UGC makes “no objectionable content” an operational assertion, not something code proves. Answer from actual content, filtering, and moderation evidence.
- The backend's DOB-based denial already enforces adult player self-claims in `academy-watch-backend/src/routes/showcase.py:1040-1089` and may itself qualify as an age-assurance mechanism under the live questionnaire definition. The operator must assess that definition; an app-side acknowledgement improves story/UX completeness but does not alone determine the answer.

### 8. Export compliance

All app API traffic uses an HTTPS production URL in `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:118-120`; Keychain and CryptoKit usage is platform-provided, and CryptoKit SHA-256 is used only to name a cache file in `academy-watch-ios/AcademyWatch/Core/Performance/ScoutResponseCache.swift:118-129`. No custom encryption protocol was found.

Apple's [encryption export guidance](https://developer.apple.com/documentation/security/complying-with-encryption-export-regulations) suggests an OS-provided/HTTPS standard exemption is likely, but this is a legal/operator classification. `ITSAppUsesNonExemptEncryption` is absent from `academy-watch-ios/AcademyWatch/Info.plist:5-33`, so App Store Connect will ask. After confirming the exemption and all linked code, set the key consistently to `false` to streamline future uploads.

### 9. Build, signing, entitlements, and TestFlight

| Item | Finding |
|---|---|
| Bundle ID | `com.theacademywatch.app` in `academy-watch-ios/project.yml:34` and `academy-watch-ios/AcademyWatch.xcodeproj/project.pbxproj:920`. Operator must verify it matches the App Store Connect record. |
| Version/build | `1.0 (1)` in `academy-watch-ios/project.yml:11-12` and `academy-watch-ios/AcademyWatch/Info.plist:19-22`. Build 1 is valid only if not already uploaded; every subsequent upload needs a unique build. |
| Minimum OS/devices | iOS 17+, iPhone-only in `academy-watch-ios/project.yml:5-6,18,38`. This is a product reach decision, not a review defect. |
| Signing | Automatic signing with team `263YH9X3BU` in `academy-watch-ios/project.yml:32-33` and `academy-watch-ios/AcademyWatch.xcodeproj/project.pbxproj:910-925`. Certificate/profile validity is operator-only and unverified. |
| Entitlements/push | No entitlement file or push capability is present; `academy-watch-ios/project.yml:15-38` declares none. Push is **not implemented**, so incoming introductions are visible only on app load/refresh through `academy-watch-ios/AcademyWatch/Features/Contact/IncomingContactRequestsViewModel.swift:135-190`. Push is not a submission requirement. |
| Tests | The unit target is configured in `academy-watch-ios/project.yml:40-52`, with 23 test files and 108 test methods under `academy-watch-ios/AcademyWatchTests/`; no XCUITest target exists. Unit coverage is useful but does not prove archive/install/live-email/role-to-role behavior. |
| Build selection and TestFlight | No archive upload, processing result, TestFlight install, signing validation, crash-free launch, or two-role end-to-end run is evidenced in the repository. A valid signed build uploaded, processed, and selected for the App Store version is a formal submission requirement; TestFlight install/E2E/external beta review are strongly recommended internal readiness gates, not formal prerequisites to press Submit for Review. |

---

## Part C — ordered punch list

Sizes are relative implementation/coordination estimates: **S** = focused change, **M** = several coordinated surfaces or operator steps, **L** = cross-system workflow/policy work.

### Launch-readiness blockers — 10

B1, B2, B3, B6, the support/contact component of B5, and the required metadata/build portion of B10 are unequivocal Apple/App Store Connect submission gates. B4 and the ToS/community-rules component of B5 are high-risk UGC/contact controls and project prerequisites. B7 is user-story/UX completeness rather than an express Apple age-checkbox rule; B8 is a product-scope/timeline decision; B9 is a quality/Guideline 2.1 review risk. The TestFlight rehearsals in B10 are internal readiness gates, not formal prerequisites to press Submit for Review.

| Order | Work item | Owner | Size | Done when |
|---:|---|---|:---:|---|
| B1 | Add in-app account deletion using the live endpoint. | Code | S | Account exposes a clear destructive flow, calls `POST /api/account/delete`, handles failure, and clears the Keychain token on success; evidence gap is `academy-watch-ios/AcademyWatch/Features/Account/AccountView.swift:94-115,309-318` and `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:1-116,239-520`. |
| B2 | Provide secure, non-expiring App Review access with seeded scout/player states. | Code + operator | M | A Release reviewer login works without private inbox access, is restricted/audited/revocable, exposes both roles, and credentials/steps are in Review Notes; current random OTP is `academy-watch-backend/src/routes/auth_routes.py:53-125,138-220`. |
| B3 | Publish a privacy policy, link it in-app and in App Store Connect, and complete the App Privacy answers. | Policy + code + metadata | M | Live policy covers the audited data/processors/retention/deletion, Account links it, ASC has the URL, and labels match production handling; current Account gap is `academy-watch-ios/AcademyWatch/Features/Account/AccountView.swift:94-340`. |
| B4 | Close Guideline 1.2 safeguards: persistent user block, defensible objectionable-content filtering/containment, reachable reporting, and a staffed timely-response process. | Code + policy + operator decision | L | A user can block an abusive participant even after acceptance; public UGC has an appropriate report path; message handling has documented filtering/containment; moderator ownership and timely response are operational. Mute may supplement but not replace the literal block requirement. Current report-without-block behavior is explicit in `academy-watch-ios/AcademyWatch/Core/Models/FullCircleModels.swift:482-513`. |
| B5 | Publish ToS/community rules and support/contact pages, then link them in-app and metadata. | Policy + code + metadata | M | ToS and UGC rules are live, support reaches a staffed channel, Account/claim/contact surfaces link them, and App Store support URL works. Published contact is an explicit Guidelines 1.2/1.5 requirement; the ToS/community-rules publication is the project's contact-rail prerequisite and a review-risk control, not a separate literal 1.2 bullet. No such links exist at `academy-watch-ios/AcademyWatch/Features/Account/AccountView.swift:94-340`. |
| B6 | Add and validate the privacy manifest. | Code + privacy | S | `PrivacyInfo.xcprivacy` is bundled; it declares the accurate System Boot Time reason for release `systemUptime` use in `academy-watch-ios/AcademyWatch/Features/ScoutDesk/ScoutDeskViewModel.swift:89-99,342-355`, its collected-data/tracking fields align with the final label, and archive privacy diagnostics are clean. |
| B7 | Make the player-claim 18+ gate explicit in the app. | Code + policy copy | S | For story/UX completeness, claim UI explains the requirement before submission and handles unknown/minor DOB outcomes clearly while preserving backend enforcement at `academy-watch-backend/src/routes/showcase.py:1040-1089`; current sheet at `academy-watch-ios/AcademyWatch/Features/Showcase/PlayerClaimSectionView.swift:400-465` contains only contract/club fields. Apple does not expressly require a checkbox. |
| B8 | Decide the submitted product scope and make the contact rail reviewable. | Operator decision + code | L | Preferred path: B3–B5 are complete, production flag is on, club-consent dependency is operable, and scout/player/contact/report paths pass end-to-end. Current gating is `academy-watch-backend/src/services/contact.py:74-87`; iOS hides it at `academy-watch-ios/AcademyWatch/Core/FeatureAvailability/ContactFeatureAvailability.swift:10-16,27-43`. |
| B9 | Triage and fix the sampled production player-availability 500, then smoke-test representative player types. | Code + operator | M | As an internal quality gate, `/api/players/403064/availability` and representative goalkeeper/outfielder cases return expected responses from the route at `academy-watch-backend/src/routes/players.py:1097-1152`; no visible Player Detail section fails. |
| B10 | Complete submission metadata, upload/select a valid Release build, and pass the internal TestFlight rehearsal. | Metadata + operator | M | Formal submission gate: ASC record/bundle match; required description/keywords, screenshots, URLs, copyright, rating, privacy/export answers and Review Notes are complete; a signed build is uploaded, processed, and selected. Internal gate: install and two-role TestFlight smoke tests pass. Source configuration is `academy-watch-ios/project.yml:3-52`; no tracked `AppStore/metadata/` exists. |

### Should-fix before or immediately after v1

| Order | Work item | Owner | Size | Rationale / evidence |
|---:|---|---|:---:|---|
| S1 | Add native export and a takedown help/deep-link surface. | Code + policy | M | Backends are live at `academy-watch-backend/src/routes/account.py:20-30` and `academy-watch-backend/src/routes/player_suppression.py:71-131`; iOS has no wrappers in `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:239-520`. |
| S2 | Resolve the club-consent product path. | Code + operator | M | Backend requires a separate active-club-manager action at `academy-watch-backend/src/routes/contact.py:504-565`, while iOS only explains waiting at `academy-watch-ios/AcademyWatch/Features/Contact/IncomingContactRequestsView.swift:308-310,361-370`. Build or identify, document, and test the manager client/API operation; no web manager surface was verified. |
| S3 | Add an automated Release/XCUITest smoke path for launch, login, Scout Desk, player detail, and both contact roles. | Code | M | Only a unit-test target exists in `academy-watch-ios/project.yml:40-52`; debug fixture destinations in `academy-watch-ios/AcademyWatch/Core/Models/FullCircleFixtureDestination.swift:3-23` do not prove Release production behavior. |
| S4 | Add `ITSAppUsesNonExemptEncryption = false` after legal/operator confirmation. | Code + operator | S | The key is absent from `academy-watch-ios/AcademyWatch/Info.plist:5-33`; HTTPS/platform crypto evidence supports a likely exemption. |
| S5 | Clarify dormant watchlist/list capabilities or expose the intended controls. | Product + code | S | Note/digest APIs exist at `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:439-464`, while current UI mainly displays them at `academy-watch-ios/AcademyWatch/Features/Watchlist/WatchlistView.swift:169-203`; non-player follows are display-only at `academy-watch-ios/AcademyWatch/Features/Lists/ListsView.swift:270-279`. |

### Post-launch

| Order | Work item | Owner | Size | Rationale / evidence |
|---:|---|---|:---:|---|
| P1 | Add privacy-reviewed push notifications for incoming requests/messages. | Code + metadata + policy | L | Today there is no push entitlement/capability in `academy-watch-ios/project.yml:15-38`, and the player inbox is pull-only in `academy-watch-ios/AcademyWatch/Features/Contact/IncomingContactRequestsViewModel.swift:135-190`. |
| P2 | Expand safety controls with per-thread freeze, stronger moderator containment, and suppression coverage audits. | Code + trust operations | L | The runbook notes that reports do not auto-stop contact and containment is separate at `docs/runbooks/incident-response.md:919-971,1136-1148`. |
| P3 | Add privacy-aware production observability only after updating policy/labels. | Code + operator | M | Current timing diagnostics are mostly debug-only in `academy-watch-ios/AcademyWatch/Core/Networking/APIClient.swift:138-158,564-633`; no crash/analytics SDK is currently linked in `academy-watch-ios/project.yml:14-62`. |
| P4 | Reassess iPad support and minimum iOS reach using usage data. | Product + code | M | The first release is intentionally iPhone-only and iOS 17+ in `academy-watch-ios/project.yml:5-6,18,38`. |

## Recommended submission sequence

1. **Close the code/policy blockers while the rail stays dark:** B1–B7, including deletion, reviewer access, privacy manifest, explicit adult claim gate, privacy/ToS/community/support publication, and UGC controls.
2. **Stabilize production:** fix the sampled availability failure (B9), seed deterministic review identities/data, and verify moderation and club-consent operations.
3. **Internal TestFlight:** archive/upload with the production-equivalent configuration; test fresh install, email/reviewer login, both strict story matrices, account deletion, policy links, block/report, and error/offline behavior.
4. **Enable the contact rail after the ToS/support/privacy prerequisites are live:** turn on `CONTACT_RAIL_ENABLED`, then rerun scout, direct/free-agent, contracted/club-notified, and contracted/club-included consent flows in TestFlight against production-equivalent services.
5. **Finish App Store Connect:** upload current iPhone screenshots from the reviewable build; complete description/keywords, support/privacy URLs, copyright, rating, privacy labels, export answers, and exact Review Notes/account instructions.
6. **External TestFlight/review rehearsal:** confirm the reviewer account does not expire, no endpoint returns an unexpected 404/500, and the two-role flows work without operator improvisation.
7. **Submit with the rail on and use manual release:** disclose the server-controlled rail and consent model in Review Notes. Recheck Apple's live guidelines and ASC questionnaires immediately before submission.

Submitting before the flag flips is not recommended. If policy timing forces a Scout-Desk-only first version, treat that as a deliberate separate product scope: do not advertise or screenshot contact, explain the disabled capability, and accept the residual Guideline 2.3.1(a) dormant-feature risk.

## Validation record

- `ruff check academy-watch-backend` — **passed** (`All checks passed!`) on 2026-07-24.
- Repository validation before commit found only `docs/ios-app-store-readiness.md` newly added; no code or ledger file was modified.
- Markdown table-width, heading-spacing, cited-path existence, cited-line bounds, and whitespace checks passed.

## Items not verifiable from code

- Whether privacy, ToS, community-rules, and support pages already exist at unpublished/untracked URLs; the task states only that ToS is drafted and not published.
- The live App Store Connect record, bundle-ID reservation, agreements, tax/banking state, metadata, privacy answers, generated age rating, export-compliance response, review notes, or build history.
- Signing certificate/provisioning-profile validity for team `263YH9X3BU`, archive/signing/upload/processing, and actual TestFlight installation.
- Email-provider delivery/reputation and whether App Review can receive ordinary OTPs.
- Azure/application/CDN/YouTube log retention, derived location, downstream sharing, subprocessors, deletion propagation, and whether any vendor behavior changes the privacy labels or ATT conclusion.
- Moderator staffing, timely-response performance, legal/paging contacts, evidence-system access, and rights/copyright owner.
- The production identity/state required to exercise verified scout, approved adult player, and active club-manager consent paths safely; no authenticated production mutation was attempted.
- Whether the sampled `/api/players/403064/availability` 500 is player-specific or systemic.
- Final binary/archive privacy diagnostics and any required-reason APIs introduced by the build toolchain rather than visible source.
