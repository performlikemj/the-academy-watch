import XCTest
import UIKit

@testable import AcademyWatch

private actor RecordingPhase2API: Phase2API {
    struct Call: Sendable {
        let path: String
        let method: String
        let query: [URLQueryItem]
        let body: Data?
    }
    private(set) var calls: [Call] = []
    let fixture: Phase2FixtureTransport
    private var delay = false
    func delayFlags() { delay = true }
    private var failure: Int?
    init(_ mode: String = "player") { fixture = Phase2FixtureTransport(mode: mode) }
    func fail(_ status: Int?) { failure = status }
    func phase2Data(path: String, method: String, query: [URLQueryItem], body: Data?) async throws
        -> Data
    {
        calls.append(Call(path: path, method: method, query: query, body: body))
        if delay && ["features", "opportunities/features"].contains(path) {
            try await Task.sleep(for: .milliseconds(100))
        }
        if let failure { throw APIClientError.httpStatus(failure) }
        if fixture.mode == "legacy", path == "funding/claims/me" {
            return Data(
                #"{"claims":[{"status":"approved","program":{"id":101,"name":"Quillmere Athletic","slug":"quillmere-athletic"}}]}"#
                    .utf8)
        }
        return try await fixture.phase2Data(path: path, method: method, query: query, body: body)
    }
    func snapshot() -> [Call] { calls }
}

private actor SlowDirectoryAPI: Phase2API {
    let fixture = Phase2FixtureTransport(mode: "player")
    func phase2Data(path: String, method: String, query: [URLQueryItem], body: Data?) async throws
        -> Data
    {
        if let body, let text = String(data: body, encoding: .utf8), text.contains("slow") {
            try await Task.sleep(for: .milliseconds(120))
            return Data(#"{"clubs":[],"page":1,"has_more":false,"total":999}"#.utf8)
        }
        return try await fixture.phase2Data(path: path, method: method, query: query, body: body)
    }
}

@MainActor
final class Phase2ViewModelTests: XCTestCase {
    private static var fixtureNow: Date { Phase2Time.date("2026-10-01T10:00:00Z")! }
    func testRetainedPrivateModelsObserveAccountBoundaryWithoutDisappearing() async {
        let auth = AuthManager(authClient: APIClient(), tokenStore: ExperienceTokenStore(),
                               fixtureState: .signedIn(email: "a@fixture.invalid", accountRole: .player,
                                                       displayName: "A", isVerifiedScout: false))
        let application = ApplicationDetailViewModel(id: Phase2FixtureTransport.applicationId,
                                                      client: RecordingPhase2API())
        let profiles = MyProfilesViewModel(client: APIClient(fixtureMode: "development"))
        application.observeAccount(auth); profiles.observeAccount(auth)
        await application.load(); await profiles.load()
        XCTAssertNotNil(application.application); XCTAssertFalse(profiles.claims.isEmpty)
        auth.updateScoutVerification(true)
        XCTAssertNotNil(application.application); XCTAssertFalse(profiles.claims.isEmpty)
        auth.signOut()
        XCTAssertNil(application.application); XCTAssertTrue(profiles.claims.isEmpty)
    }
    func testAccountBoundaryKeepsOnlyPublicNavigationPrefix() {
        let club = Phase2BrowseRoute.club(slug: "quillmere", distance: 0.8)
        let trial = Phase2BrowseRoute.trial("trial")
        for entry in [Phase2BrowseRoute.application(id: "private", account: "a"), .profiles(account: "a")] {
            XCTAssertEqual(Phase2BrowseRoute.publicPrefix([trial, entry]), [trial])
            XCTAssertEqual(Phase2BrowseRoute.publicPrefix([club, trial, entry, trial]), [club, trial])
        }
        XCTAssertEqual(Phase2BrowseRoute.publicPrefix([club, trial]), [club, trial])
    }
    func testApplicationResetClearsDataAndDiscardsLateWithdrawal() async {
        let api = SuspendedTrialSendAPI()
        let model = ApplicationDetailViewModel(id: Phase2FixtureTransport.applicationId, client: api,
                                               now: { Self.fixtureNow })
        await model.load()
        XCTAssertNotNil(model.application)
        model.note = "Private note"; model.venue = "Private venue"; model.instructions = "Private instructions"
        model.enrollmentConfirmed = true
        let pending = Task { await model.applicantAction("withdraw") }
        await api.waitForSend()
        model.resetAccount()
        XCTAssertNil(model.application)
        XCTAssertEqual(model.note, ""); XCTAssertEqual(model.venue, ""); XCTAssertEqual(model.instructions, "")
        XCTAssertFalse(model.enrollmentConfirmed)
        XCTAssertFalse(model.isBusy)
        await api.release()
        await pending.value
        XCTAssertNil(model.application)
        XCTAssertNil(model.error)
    }
    func testApplicationResetDiscardsLateRead() async {
        let api = SuspendedPrivateReadAPI()
        let model = ApplicationDetailViewModel(id: Phase2FixtureTransport.applicationId, client: api)
        let pending = Task { await model.load() }
        await api.waitForRead()
        model.resetAccount()
        await api.release()
        await pending.value
        XCTAssertNil(model.application)
        XCTAssertNil(model.error)
        XCTAssertFalse(model.isBusy)
    }
    func testShiftedApplicationPagesKeepOneRowPerStableID() async {
        let model = ApplicationsViewModel(client: ShiftedApplicationsAPI())
        await model.load()
        XCTAssertTrue(model.isComplete)
        XCTAssertEqual(model.applications.count, 31)
        XCTAssertEqual(Set(model.applications.map(\.id)).count, 31)
        XCTAssertEqual(model.applications.first(where: { $0.id == "newer-29" })?.status, "signed")
        XCTAssertEqual(model.current?.id, "older-invitation")
    }
    func testReadFailureHasNoDraftAndLegacyClubHasNoWorkspaceErrorSurface() async {
        let workspace = Phase2Workspace(client: RecordingPhase2API("club-offline"))
        await workspace.load(authenticated: true)
        XCTAssertNotNil(workspace.error)
        XCTAssertFalse(workspace.hasClubSurface)
        XCTAssertFalse(workspace.error?.contains("draft") ?? true)
        XCTAssertFalse(phase2ReadError(APIClientError.decoding(NSError(domain: "fixture", code: 1))).contains("draft"))
        let enabled = Phase2Workspace(client: RecordingPhase2API("membership-error"))
        await enabled.load(authenticated: true)
        XCTAssertTrue(enabled.hasClubSurface)
        XCTAssertFalse(enabled.error?.contains("draft") ?? true)
    }
    func testLegacyAccountSymbolMatchesFlagsOffApp() {
        XCTAssertEqual(RootTab.accountSymbol(editorial: false), "person.crop.circle.fill")
        XCTAssertEqual(RootTab.accountSymbol(editorial: true), "person")
    }
    func testFailedTrialReadEndsLoading() async {
        let model = TrialDetailViewModel(id: Phase2FixtureTransport.postId, client: RecordingPhase2API("detail-error"))
        await model.load(authenticated: false, applications: true)
        XCTAssertNil(model.post)
        XCTAssertNotNil(model.error)
        XCTAssertFalse(model.isLoading)
    }
    func testPublicTrialRevalidatesClaimsAndClearsEveryAccountBoundField() async {
        let client = RecordingPhase2API("player")
        let model = TrialDetailViewModel(id: Phase2FixtureTransport.postId, client: client)
        model.setAccount("signed-out")
        await model.load(authenticated: false, applications: true)
        XCTAssertNotNil(model.post)
        XCTAssertTrue(model.claims.isEmpty)
        model.setAccount("signed-in|first")
        await model.load(authenticated: true, applications: true)
        XCTAssertEqual(model.selectedClaimId, 71)
        model.position = "Midfield"; model.currentClub = "Club"; model.contactConsent = true
        await model.apply()
        XCTAssertNotNil(model.sent)
        model.setAccount("signed-in|second")
        XCTAssertNotNil(model.post)
        XCTAssertTrue(model.claims.isEmpty)
        XCTAssertNil(model.selectedClaimId)
        XCTAssertNil(model.sent)
        XCTAssertEqual(model.position, "")
        XCTAssertEqual(model.currentClub, "")
        XCTAssertFalse(model.contactConsent)
        XCTAssertFalse(model.canSend)
        await model.load(authenticated: true, applications: true)
        XCTAssertEqual(model.claims.count, 1)
    }
    func testOldAccountApplicationSendCannotPopulateNewAccountDetail() async {
        let client = SuspendedTrialSendAPI()
        let model = TrialDetailViewModel(id: Phase2FixtureTransport.postId, client: client)
        model.setAccount("first")
        await model.load(authenticated: true, applications: true)
        model.position = "Midfield"; model.contactConsent = true
        let send = Task { await model.apply() }
        await client.waitForSend()
        model.setAccount("second")
        await model.load(authenticated: true, applications: true)
        await client.release()
        await send.value
        XCTAssertNil(model.sent)
        XCTAssertFalse(model.isSending)
        XCTAssertEqual(model.position, "")
        XCTAssertFalse(model.contactConsent)
    }

    func testBrandHeroSmallTextMeetsAAForPermittedPrimariesInBothAppearances() {
        func luminance(_ color: UIColor, _ traits: UITraitCollection) -> Double {
            var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
            color.resolvedColor(with: traits).getRed(&r, green: &g, blue: &b, alpha: &a)
            func linear(_ c: CGFloat) -> Double { c <= 0.04045 ? Double(c / 12.92) : pow(Double((c + 0.055) / 1.055), 2.4) }
            return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)
        }
        var colours: [UInt32] = [0x767676, 0x757575, 0x747474, 0x0F3D2E]
        for value in 0...4095 {
            let red = UInt32((value >> 8) * 17)
            let green = UInt32(((value >> 4) & 15) * 17)
            let blue = UInt32((value & 15) * 17)
            colours.append((red << 16) | (green << 8) | blue)
        }
        for style in [UIUserInterfaceStyle.light, .dark] {
            let traits = UITraitCollection(userInterfaceStyle: style)
            for primary in colours {
                let background = luminance(UIColor(hex: primary), traits)
                guard 1.05 / (background + 0.05) >= 4.5 else { continue } // Server-permitted primary.
                let raw = String(format: "#%06X", primary)
                let text = luminance(UIColor(phase2HeroForeground(raw)), traits)
                XCTAssertGreaterThanOrEqual((max(text, background) + 0.05) / (min(text, background) + 0.05), 4.5, raw)
            }
        }
    }

    func testClubResolutionRefusalPreservesPublicFlagsAndRemovesDeniedClub() async {
        for status in [403, 404] {
            let api = ClubResolutionAPI()
            let workspace = Phase2Workspace(client: api)
            await workspace.load(authenticated: true)
            XCTAssertEqual(workspace.clubs.count, 1)
            await api.refuse(access: status)
            await workspace.load(authenticated: true)
            XCTAssertTrue(workspace.flags.directory)
            XCTAssertTrue(workspace.flags.applications)
            XCTAssertTrue(workspace.clubs.isEmpty)
            XCTAssertNil(workspace.error)
            XCTAssertTrue(RootTab.available(for: .player, flags: workspace.flags).contains(.trials))
        }
    }
    func testAccountResetClearsPrivateAccessWithoutRemovingPublicTabs() async {
        let workspace = Phase2Workspace(client: ClubResolutionAPI())
        await workspace.load(authenticated: true)
        let publicTabs = RootTab.available(for: .player, flags: workspace.flags)
        workspace.reset(preservePublicFlags: true)
        XCTAssertTrue(workspace.clubs.isEmpty)
        XCTAssertNil(workspace.selectedClubId)
        XCTAssertEqual(RootTab.available(for: .player, flags: workspace.flags), publicTabs)
    }
    func testClaimsTransientFailureKeepsFlagsAndLastConfirmedClub() async {
        let api = ClubResolutionAPI(claimsStatus: 500)
        let workspace = Phase2Workspace(client: api)
        await workspace.load(authenticated: true)
        XCTAssertTrue(workspace.flags.directory)
        XCTAssertTrue(workspace.flags.opportunities)
        XCTAssertTrue(workspace.clubs.isEmpty)
        XCTAssertNotNil(workspace.error)
        await api.refuse()
        await workspace.load(authenticated: true)
        await api.refuse(claims: 500)
        await workspace.load(authenticated: true)
        XCTAssertEqual(workspace.selected?.id, 101)
        await api.refuse(claims: 401)
        await workspace.load(authenticated: true)
        XCTAssertTrue(workspace.clubs.isEmpty)
        XCTAssertTrue(workspace.flags.directory)
    }
    func testConversationDatesUseReaderZoneAcrossMidnight() {
        let date = "2026-10-07T00:30:00Z"
        XCTAssertEqual(Phase2Time.conversationDate(date, zone: TimeZone(identifier: "America/New_York")!, format: "d"), "6")
        XCTAssertEqual(Phase2Time.conversationDate(date, zone: TimeZone(secondsFromGMT: 0)!, format: "d"), "7")
        XCTAssertEqual(Phase2Time.conversationDate(date), Phase2Time.conversationDate(date, zone: .current))
    }
    func testSelectedSmallTabTitleMeetsAAOnActualLightPill() throws {
        let bar = EditorialTabBar()
        bar.overrideUserInterfaceStyle = .light
        bar.configure(tabs: [.home, .account], role: .player, selected: .home) { _ in }
        let button = try XCTUnwrap(bar.subviews.compactMap { $0 as? UIButton }.first)
        let foreground = try XCTUnwrap(button.configuration?.attributedTitle?.uiKit.foregroundColor)
        let traits = UITraitCollection(userInterfaceStyle: .light)
        func luminance(_ color: UIColor) -> Double {
            var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
            color.resolvedColor(with: traits).getRed(&r, green: &g, blue: &b, alpha: &a)
            func linear(_ c: CGFloat) -> Double { c <= 0.04045 ? Double(c / 12.92) : pow(Double((c + 0.055) / 1.055), 2.4) }
            return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)
        }
        let text = luminance(foreground)
        let pill = luminance(UIColor(AcademyColors.elevatedSurface))
        XCTAssertGreaterThanOrEqual((max(text, pill) + 0.05) / (min(text, pill) + 0.05), 4.5)
    }
    func testHomeAndAppliedReadOlderInvitationAndTrueTotalBeyondFirstPage() async {
        let client = PagedPlayerAPI()
        let model = ApplicationsViewModel(client: client)
        await model.load()
        XCTAssertTrue(model.isComplete)
        XCTAssertEqual(model.applications.count, 31)
        XCTAssertEqual(model.applications.filter { $0.canRespond(now: Self.fixtureNow) }.count, 1)
        XCTAssertEqual(model.current?.id, "older-invitation")
        XCTAssertFalse(model.hasMore)
        let pages = await client.pages
        XCTAssertEqual(pages, [1, 2])
    }
    func testRevalidationNeverTemporarilyDropsKnownTabsOrMembership() async {
        let client = RecordingPhase2API("owner")
        let model = Phase2Workspace(client: client)
        await model.load(authenticated: true)
        let flags = model.flags
        let id = model.selected?.id
        await client.delayFlags()
        let refresh = Task { await model.load(authenticated: true) }
        try? await Task.sleep(for: .milliseconds(20))
        XCTAssertTrue(model.isLoading)
        XCTAssertEqual(model.flags, flags)
        XCTAssertEqual(model.selected?.id, id)
        await refresh.value
        XCTAssertEqual(model.flags, flags)
        XCTAssertEqual(model.selected?.id, id)
    }
    func testClaimsFetchFailureIsNotAnAdultEligibilityDecision() async {
        let model = TrialDetailViewModel(
            id: Phase2FixtureTransport.postId, client: RecordingPhase2API("claims-error"))
        await model.load(authenticated: true, applications: true)
        XCTAssertNotNil(model.post)
        XCTAssertNotNil(model.error)
        XCTAssertTrue(model.claims.isEmpty)
        XCTAssertFalse(model.canSend)
    }
    func testDeniedPrivateRecordStillClearsButKeepsUnsentDraft() async {
        let client = RecordingPhase2API("owner")
        let model = ApplicationDetailViewModel(
            id: Phase2FixtureTransport.applicationId, programId: 101, client: client)
        await model.load()
        model.note = "Unsent draft"
        await client.fail(403)
        await model.addNote()
        XCTAssertNil(model.application)
        XCTAssertEqual(model.note, "Unsent draft")
    }
    func testFidelitySingularCountsRemainCorrect() {
        XCTAssertEqual(phase2Count(1, "applicant"), "1 applicant")
        XCTAssertEqual(phase2Count(1, "open opportunity", plural: "open opportunities"), "1 open opportunity")
        XCTAssertEqual(phase2Count(1, "squad"), "1 squad")
    }
    func testUnconfirmedClubMembershipAlwaysKeepsLegacyTabs() async {
        let flags = Phase2Flags(directory: true, opportunities: true, applications: true, staff: true)
        XCTAssertEqual(
            RootTab.available(for: .club, flags: flags),
            [.home, .scoutDesk, .watchlist, .lists, .account])
        let workspace = Phase2Workspace(client: RecordingPhase2API("membership-error"))
        await workspace.load(authenticated: true)
        XCTAssertNil(workspace.selected)
        XCTAssertNotNil(workspace.error)
        XCTAssertEqual(
            RootTab.available(for: .club, flags: workspace.flags),
            [.home, .scoutDesk, .watchlist, .lists, .account])
        let signedOut = Phase2Workspace(client: RecordingPhase2API("owner"))
        await signedOut.load(authenticated: false)
        XCTAssertNil(signedOut.selected)
    }
    func testRecruitingWorksWithoutStaffAdministrationFlag() async {
        let workspace = Phase2Workspace(client: RecordingPhase2API("nostaff"))
        await workspace.load(authenticated: true)
        XCTAssertFalse(workspace.flags.staff)
        XCTAssertTrue(workspace.selected?.access.canRecruit == true)
        XCTAssertEqual(
            RootTab.available(for: .club, flags: workspace.flags, access: workspace.selected?.access),
            [.home, .recruiting, .account])
    }
    func testInitialFailedFlagsStayClosed() async {
        let client = RecordingPhase2API("owner")
        await client.fail(503)
        let model = Phase2Workspace(client: client)
        await model.load(authenticated: true)
        XCTAssertEqual(model.flags, Phase2Flags())
        XCTAssertNil(model.selected)
    }
    func testRefusalsNeverSuggestTransportRetry() {
        for status in [400, 401, 403, 404, 409, 413, 422, 429, 500, 503] {
            XCTAssertFalse(phase2Error(APIClientError.httpStatus(status)).contains("Could not connect"))
        }
        XCTAssertTrue(phase2Error(URLError(.notConnectedToInternet)).contains("Could not connect"))
        XCTAssertTrue(
            phase2Error(APIClientError.server(statusCode: 409, message: "already_has_access")).contains(
                "already has club access"))
    }
    func testStageFilterCanSeeApplicantsBeyondFirstPage() async {
        let client = PagedPipelineAPI()
        let model = ApplicationsViewModel(client: client)
        await model.load(programId: 101, opportunityId: Phase2FixtureTransport.postId)
        XCTAssertEqual(model.applications.count, 2)
        XCTAssertTrue(model.applications.contains { $0.status == "offer" })
        XCTAssertFalse(model.hasMore)
        let pages = await client.pages
        XCTAssertEqual(pages, [1, 2])
    }
    func testValidationRefusalKeepsTrialInviteForm() async {
        let model = ApplicationDetailViewModel(
            id: Phase2FixtureTransport.applicationId, programId: 101,
            client: RecordingPhase2API("invalid-trial"), now: { Self.fixtureNow })
        await model.load()
        model.venue = "Draft venue"
        await model.transition("invited")
        XCTAssertNotNil(model.application)
        XCTAssertEqual(model.venue, "Draft venue")
        XCTAssertTrue(model.error?.contains("invitation window") == true)
    }
    func testSuccessfulInviteReturnsSuccessAndConflictKeepsStaffBoard() async {
        let client = RecordingPhase2API("owner")
        let model = StaffViewModel(programId: 101, client: client)
        await model.load()
        let sent = await model.invite(
            email: "fixture@example.test", role: "coach", allSquads: true, squadIds: [])
        XCTAssertTrue(sent)
        await client.fail(409)
        let refused = await model.invite(
            email: "fixture@example.test", role: "coach", allSquads: true, squadIds: [])
        XCTAssertFalse(refused)
        XCTAssertNotNil(model.board)
    }
    func testDirectorySearchNeverPutsSearchOrCoordinatesInURL() async throws {
        let client = RecordingPhase2API()
        let model = DirectoryViewModel(client: client)
        await model.search(DirectorySearch(q: "Quillmere", lat: 51, lng: -1, radiusKm: 50))
        let snapshot = await client.snapshot()
        let call = try XCTUnwrap(snapshot.first)
        XCTAssertEqual(call.path, "club-directory/search")
        XCTAssertEqual(call.method, "POST")
        XCTAssertTrue(call.query.isEmpty)
        let body = try XCTUnwrap(
            JSONSerialization.jsonObject(with: try XCTUnwrap(call.body)) as? [String: Any])
        XCTAssertEqual(body["q"] as? String, "Quillmere")
        XCTAssertEqual(body["lat"] as? Double, 51)
        XCTAssertEqual(model.clubs.count, 1)
        XCTAssertEqual(model.clubs.first?.distanceKm, 0.8)
    }
    func testLatestDirectorySearchWinsOverSlowOldResponse() async {
        let model = DirectoryViewModel(client: SlowDirectoryAPI())
        let old = Task { await model.search(DirectorySearch(q: "slow")) }
        try? await Task.sleep(for: .milliseconds(20))
        await model.search(DirectorySearch(q: "Quillmere"))
        await old.value
        XCTAssertEqual(model.total, 1)
        XCTAssertEqual(model.clubs.count, 1)
        XCTAssertFalse(model.isLoading)
    }
    func testVerifiedManagersAreResolvedFromApprovedFundingClaims() async {
        let client = RecordingPhase2API("legacy")
        let model = Phase2Workspace(client: client)
        await model.load(authenticated: true)
        XCTAssertEqual(model.selected?.id, 101)
        XCTAssertTrue(model.selected?.access.canRecruit == true)
        let calls = await client.snapshot()
        XCTAssertTrue(calls.contains { $0.path == "club/101/access/me" })
    }
    func testPostingAndApplicationPaginationUseCorrectPrivateEndpoints() async {
        let client = RecordingPhase2API("owner")
        let posts = OpportunitiesViewModel(client: client)
        let applications = ApplicationsViewModel(client: client)
        await posts.load(programId: 101, club: true, page: 2)
        await applications.load(programId: 101, opportunityId: Phase2FixtureTransport.postId, page: 3)
        let calls = await client.snapshot()
        XCTAssertEqual(calls.first?.path, "club/101/opportunities")
        XCTAssertEqual(calls.first?.query.first?.value, "2")
        XCTAssertEqual(
            calls.last?.path, "club/101/opportunities/\(Phase2FixtureTransport.postId)/applications")
        XCTAssertEqual(calls.last?.query.first?.value, "1")
        XCTAssertEqual(posts.page, 2)
        XCTAssertEqual(applications.page, 1)
    }
    func testMissingClubFailsWithoutConstructingInvalidRoute() async {
        let client = RecordingPhase2API()
        let model = OpportunitiesViewModel(client: client)
        await model.load(club: true)
        let calls = await client.snapshot()
        XCTAssertTrue(calls.isEmpty)
        XCTAssertNotNil(model.error)
    }
    func testLocationOffOmitsRadiusAndDistance() async throws {
        let client = RecordingPhase2API()
        let model = DirectoryViewModel(client: client)
        await model.search(DirectorySearch(q: "Quillmere", radiusKm: 50))
        let calls = await client.snapshot()
        let body =
            try JSONSerialization.jsonObject(with: try XCTUnwrap(calls.first?.body)) as! [String: Any]
        XCTAssertNil(body["lat"])
        XCTAssertNil(body["radius_km"])
        XCTAssertNil(model.clubs.first?.distanceKm)
    }
    func testOneCharacterSearchDoesNotSend() async {
        let client = RecordingPhase2API()
        let model = DirectoryViewModel(client: client)
        await model.search(DirectorySearch(q: "Q"))
        let calls = await client.snapshot()
        XCTAssertTrue(calls.isEmpty)
        XCTAssertNotNil(model.error)
    }
    func testFlagsOffClearAllPhase2Capabilities() async {
        let model = Phase2Workspace(client: RecordingPhase2API("off"))
        await model.load(authenticated: true)
        XCTAssertEqual(model.flags, Phase2Flags())
        XCTAssertTrue(model.clubs.isEmpty)
    }
    func testFeatureFailureKeepsLastConfirmedFlagsAndAuthResetClearsScope() async {
        let client = RecordingPhase2API("owner")
        let model = Phase2Workspace(client: client)
        await model.load(authenticated: true)
        XCTAssertTrue(model.selected?.access.canRecruit == true)
        await client.fail(503)
        await model.load(authenticated: true)
        XCTAssertTrue(model.flags.opportunities)
        XCTAssertTrue(model.selected?.access.canRecruit == true)
        XCTAssertNotNil(model.error)
        model.reset()
        XCTAssertEqual(model.flags, Phase2Flags())
        XCTAssertTrue(model.clubs.isEmpty)
        XCTAssertNil(model.selectedClubId)
    }
    func testCoachWithAllSquadsNeverGetsRecruitingOrStaff() async throws {
        let client = RecordingPhase2API("coach")
        let model = Phase2Workspace(client: client)
        await model.load(authenticated: true)
        let access = try XCTUnwrap(model.selected?.access)
        XCTAssertTrue(access.allSquads)
        XCTAssertFalse(access.wholeClub)
        XCTAssertFalse(access.canRecruit)
        XCTAssertFalse(access.canManageAccess)
        let tabs = RootTab.available(for: .club, flags: model.flags, access: access)
        XCTAssertEqual(tabs, [.home, .squads, .matches, .account])
    }
    func testPlayerAndOwnerHaveDedicatedTabsScoutKeepsItsTabs() async throws {
        let flags = Phase2Flags(directory: true, opportunities: true, applications: true, staff: true)
        XCTAssertEqual(
            RootTab.available(for: .player, flags: flags), [.home, .clubs, .trials, .applied, .account])
        XCTAssertEqual(
            RootTab.available(for: .scout, flags: flags), [.scoutDesk, .watchlist, .lists, .account])
        let result: ClubAccessResponse = try await RecordingPhase2API("owner").read(
            "club/101/access/me")
        XCTAssertEqual(
            RootTab.available(for: .club, flags: flags, access: result.access),
            [.home, .squads, .matches, .recruiting, .account])
        let partial = Phase2Flags(directory: true)
        XCTAssertEqual(RootTab.available(for: .player, flags: partial), [.home, .clubs, .account])
    }
    func testSignedOutTrialReadNeverFetchesClaims() async {
        let client = RecordingPhase2API()
        let model = TrialDetailViewModel(
            id: Phase2FixtureTransport.postId, client: client, now: { Self.fixtureNow })
        await model.load(authenticated: false, applications: true)
        let calls = await client.snapshot()
        XCTAssertEqual(calls.map(\.path), ["opportunities/\(Phase2FixtureTransport.postId)"])
        XCTAssertTrue(model.claims.isEmpty)
        XCTAssertFalse(model.canSend)
    }
    func testApplicationRequiresConsentAndUsesStableRetryKey() async throws {
        let client = RecordingPhase2API("apply")
        let model = TrialDetailViewModel(
            id: Phase2FixtureTransport.postId, client: client, now: { Self.fixtureNow })
        await model.load(authenticated: true, applications: true)
        model.position = "Midfield"
        XCTAssertFalse(model.canSend)
        await model.apply()
        var calls = await client.snapshot()
        XCTAssertFalse(calls.contains { $0.method == "POST" })
        model.contactConsent = true
        await client.fail(503)
        await model.apply()
        XCTAssertEqual(model.position, "Midfield")
        XCTAssertTrue(model.contactConsent)
        XCTAssertNotNil(model.error)
        await client.fail(nil)
        await model.apply()
        XCTAssertNotNil(model.sent)
        calls = await client.snapshot()
        let writes = calls.filter { $0.method == "POST" }
        let bodies = try writes.map {
            try JSONSerialization.jsonObject(with: XCTUnwrap($0.body)) as! [String: Any]
        }
        XCTAssertEqual(bodies.count, 2)
        XCTAssertEqual(
            bodies[0]["client_request_id"] as? String, bodies[1]["client_request_id"] as? String)
        XCTAssertEqual(bodies[0]["contact_consent"] as? Bool, true)
    }
    func testGuardianCannotApplyWithoutEligibleSelfClaim() async {
        let client = RecordingPhase2API("parent")
        let model = TrialDetailViewModel(
            id: Phase2FixtureTransport.postId, client: client, now: { Self.fixtureNow })
        await model.load(authenticated: true, applications: true)
        model.position = "Forward"
        model.contactConsent = true
        await model.apply()
        XCTAssertFalse(model.canSend)
        let calls = await client.snapshot()
        XCTAssertFalse(calls.contains { $0.method == "POST" })
    }
    func testConfirmAndDeclineUseVersionAndDeclineIsTerminal() async {
        let client = RecordingPhase2API()
        let model = ApplicationDetailViewModel(
            id: Phase2FixtureTransport.applicationId, client: client, now: { Self.fixtureNow })
        await model.load()
        await model.applicantAction("decline")
        XCTAssertEqual(model.application?.status, "withdrawn")
        XCTAssertEqual(model.application?.reservationState, "declined")
        XCTAssertTrue(model.application?.isTerminal == true)
        await model.applicantAction("accept")
        let calls = await client.snapshot()
        XCTAssertEqual(calls.filter { $0.method == "POST" }.count, 1)
    }
    func testConfirmKeepsPlaceAndWithdrawalRemovesActions() async {
        let model = ApplicationDetailViewModel(
            id: Phase2FixtureTransport.applicationId, client: RecordingPhase2API(),
            now: { Self.fixtureNow })
        await model.load()
        await model.applicantAction("accept")
        XCTAssertEqual(model.application?.reservationState, "confirmed")
        XCTAssertFalse(model.application?.canRespond() == true)
        await model.applicantAction("withdraw")
        XCTAssertTrue(model.application?.isTerminal == true)
    }
    func testPrivateConflictRevalidatesApplicantAndPreservesDraft() async {
        let client = RecordingPhase2API("conflict")
        let model = ApplicationDetailViewModel(
            id: Phase2FixtureTransport.applicationId, programId: 101, client: client,
            now: { Self.fixtureNow })
        await model.load()
        model.venue = "Saltings"
        model.instructions = "Bring boots"
        model.note = "Draft note"
        await model.transition("invited")
        XCTAssertNotNil(model.application)
        XCTAssertEqual(model.venue, "Saltings")
        XCTAssertEqual(model.note, "Draft note")
        XCTAssertNotNil(model.error)
    }
    func testTrialFullPreservesInviteDraft() async {
        let model = ApplicationDetailViewModel(
            id: Phase2FixtureTransport.applicationId, programId: 101, client: RecordingPhase2API("full"),
            now: { Self.fixtureNow })
        await model.load()
        model.venue = "Saltings"
        await model.transition("invited")
        XCTAssertEqual(model.venue, "Saltings")
        XCTAssertNotNil(model.application)
        XCTAssertTrue(model.error?.contains("full") == true)
    }
    func testSignedRequiresSeparateEnrollment() async {
        let client = RecordingPhase2API("signed")
        let model = ApplicationDetailViewModel(
            id: Phase2FixtureTransport.applicationId, programId: 101, client: client,
            now: { Self.fixtureNow })
        await model.load()
        await model.transition("signed")
        var calls = await client.snapshot()
        XCTAssertFalse(calls.contains { $0.method == "POST" })
        model.enrollmentConfirmed = true
        await model.transition("signed")
        XCTAssertEqual(model.application?.status, "signed")
        calls = await client.snapshot()
        XCTAssertEqual(calls.filter { $0.method == "POST" }.count, 1)
    }
    func testAttendanceLockedUntilConfirmedPastTrial() async throws {
        let response: ApplicationResponse = try await RecordingPhase2API().read(
            "club/101/applications/\(Phase2FixtureTransport.applicationId)")
        XCTAssertFalse(response.application.canTransition(to: "attended"))
        XCTAssertFalse(response.application.canTransition(to: "attended", now: Date.distantFuture))
    }
    func testPrivateNoteIsClearedOnlyAfterSuccess() async {
        let client = RecordingPhase2API("owner")
        let model = ApplicationDetailViewModel(
            id: Phase2FixtureTransport.applicationId, programId: 101, client: client,
            now: { Self.fixtureNow })
        await model.load()
        model.note = "Club-private observation"
        await client.fail(503)
        await model.addNote()
        XCTAssertEqual(model.note, "Club-private observation")
        await client.fail(nil)
        await model.addNote()
        XCTAssertEqual(model.note, "")
        XCTAssertEqual(model.application?.notes?.first?.body, "Club-private observation")
    }
    func testCoachSquadScopeAndMinorName() async {
        let model = SquadViewModel(client: RecordingPhase2API("coach"))
        await model.load(programId: 101)
        XCTAssertEqual(model.squads.map(\.id), [3])
        XCTAssertEqual(model.members.first?.privateName, "Nabil F.")
    }
    func testStaffRoleOnlyEditPreservesEntireSquadSet() async throws {
        let client = RecordingPhase2API("owner")
        let model = StaffViewModel(programId: 101, client: client)
        await model.load()
        let person = try XCTUnwrap(model.board?.people.first)
        await model.update(
            person, role: "analyst", allSquads: person.allSquads, squadIds: person.squadIds)
        let calls = await client.snapshot()
        let call = try XCTUnwrap(calls.first { $0.method == "PATCH" })
        let body = try JSONSerialization.jsonObject(with: XCTUnwrap(call.body)) as! [String: Any]
        XCTAssertEqual(body["squad_ids"] as? [Int], [3, 4])
        XCTAssertEqual(body["expected_version"] as? Int, 1)
        XCTAssertEqual(model.board?.people.first?.squadIds, [3, 4])
    }
    func testEmptyScopeIsNeverBroadenedToAllSquads() async throws {
        let client = RecordingPhase2API("owner")
        let model = StaffViewModel(programId: 101, client: client)
        await model.load()
        let person = try XCTUnwrap(model.board?.people.first)
        await model.update(person, role: "coach", allSquads: false, squadIds: [])
        let calls = await client.snapshot()
        XCTAssertFalse(calls.contains { $0.method == "PATCH" })
    }
    func testTimeUsesPostingZoneAcrossDSTAndLabelledFallback() {
        XCTAssertTrue(
            Phase2Time.zoneLabel("Europe/London", at: "2026-10-07T18:30:00Z").contains("UTC+01:00"))
        XCTAssertTrue(
            Phase2Time.display("2026-10-07T18:30:00Z", zone: "Europe/London").contains("19:30"))
        XCTAssertTrue(
            Phase2Time.zoneLabel("Europe/London", at: "2026-10-27T18:30:00Z").contains("UTC+00:00"))
        XCTAssertTrue(Phase2Time.zoneLabel("Unknown/Zone", at: nil).contains("UTC fallback"))
        XCTAssertEqual(Phase2Time.display("bad", zone: "Europe/London"), "Date unavailable")
    }
    func testContactNaiveUTCTimestampsMatchExplicitUTCAndPreserveOffsets() throws {
        let naive = try XCTUnwrap(Phase2Time.date("2026-08-26T11:15:00"))
        XCTAssertEqual(naive, Phase2Time.date("2026-08-26T11:15:00Z"))
        XCTAssertEqual(naive, Phase2Time.date("2026-08-26T12:15:00+01:00"))
        XCTAssertEqual(
            Phase2Time.date("2026-08-26T11:15:00.123456"), Phase2Time.date("2026-08-26T11:15:00.123456Z"))
        XCTAssertTrue(
            Phase2Time.display(
                "2026-08-26T11:15:00", zone: "Europe/London", locale: Locale(identifier: "en_GB")
            ).contains("12:15 BST"))
        XCTAssertNil(Phase2Time.date("2026-08-26"))
        XCTAssertNil(Phase2Time.date("2026-08-26T11:15:00junk"))
    }
    func testTimeRangePreservesEndTimeAndBothZonesAcrossDST() {
        let locale = Locale(identifier: "en_GB")
        let range = Phase2Time.interval(
            "2026-10-07T18:30:00Z", "2026-10-07T20:00:00Z", zone: "Europe/London", locale: locale)
        XCTAssertTrue(range.contains("19:30–21:00 BST"), range)
        let change = Phase2Time.interval(
            "2026-10-25T00:30:00Z", "2026-10-25T01:30:00Z", zone: "Europe/London", locale: locale)
        XCTAssertTrue(change.contains("BST"))
        XCTAssertTrue(change.contains("GMT"))
        let midnight = Phase2Time.interval(
            "2026-10-07T22:30:00Z", "2026-10-08T01:00:00Z", zone: "Europe/London", locale: locale)
        XCTAssertTrue(midnight.contains("7 Oct"), midnight)
        XCTAssertTrue(midnight.contains("8 Oct"), midnight)
        XCTAssertNotEqual(
            Phase2Time.display("2026-10-07T18:30:00Z", zone: "Europe/London", locale: locale),
            Phase2Time.display(
                "2026-10-07T18:30:00Z", zone: "Europe/London", locale: Locale(identifier: "ja_JP")))
        XCTAssertEqual(Phase2Time.interval(nil, nil, zone: "Europe/London"), "No fixed date")
    }
}

private actor PagedPipelineAPI: Phase2API {
    private(set) var pages: [Int] = []
    let fixture = Phase2FixtureTransport(mode: "owner")
    func phase2Data(path: String, method: String, query: [URLQueryItem], body: Data?) async throws
        -> Data
    {
        let page = Int(query.first?.value ?? "1") ?? 1
        pages.append(page)
        let raw = try await fixture.phase2Data(path: path, method: method, query: query, body: body)
        var response = try JSONSerialization.jsonObject(with: raw) as! [String: Any]
        var rows = response["applications"] as! [[String: Any]]
        if page == 2 {
            rows[0]["id"] = "second-page"
            rows[0]["status"] = "offer"
        }
        response["applications"] = rows
        response["has_more"] = page == 1
        return try JSONSerialization.data(withJSONObject: response)
    }
}

private actor ClubResolutionAPI: Phase2API {
    var accessStatus: Int?
    var claimsStatus: Int?
    init(accessStatus: Int? = nil, claimsStatus: Int? = nil) {
        self.accessStatus = accessStatus
        self.claimsStatus = claimsStatus
    }
    func refuse(access: Int? = nil, claims: Int? = nil) { accessStatus = access; claimsStatus = claims }
    func phase2Data(path: String, method: String, query: [URLQueryItem], body: Data?) async throws
        -> Data
    {
        switch path {
        case "features":
            return Data(#"{"club_directory":true,"club_staff_access":true,"contact_rail":true}"#.utf8)
        case "opportunities/features":
            return Data(#"{"opportunities":true,"applications":true}"#.utf8)
        case "me/club-access": return Data(#"{"programs":[]}"#.utf8)
        case "funding/claims/me":
            if let claimsStatus { throw APIClientError.httpStatus(claimsStatus) }
            return Data(
                #"{"claims":[{"status":"approved","program":{"id":101,"name":"Quillmere Athletic","slug":"quillmere-athletic"}}]}"#
                    .utf8)
        case "club/101/access/me":
            if let accessStatus { throw APIClientError.httpStatus(accessStatus) }
            return Data(
                #"{"access":{"program_id":101,"role":"owner","verified":true,"whole_club":true,"all_squads":true,"squad_ids":[],"capabilities":["recruiting","players.view"]}}"#
                    .utf8)
        default: throw APIClientError.httpStatus(404)
        }
    }
}


private actor PagedPlayerAPI: Phase2API {
    private(set) var pages: [Int] = []
    let fixture = Phase2FixtureTransport(mode: "player")
    func phase2Data(path: String, method: String, query: [URLQueryItem], body: Data?) async throws -> Data {
        let page = Int(query.first?.value ?? "1") ?? 1
        pages.append(page)
        let raw = try await fixture.phase2Data(path: path, method: method, query: query, body: body)
        var response = try JSONSerialization.jsonObject(with: raw) as! [String: Any]
        let base = (response["applications"] as! [[String: Any]])[0]
        response["applications"] = page == 1 ? (0..<30).map { index -> [String: Any] in
            var row = base
            row["id"] = "newer-\(index)"
            row["status"] = "signed"
            row["reservation_state"] = "none"
            return row
        } : [{ () -> [String: Any] in
            var row = base
            row["id"] = "older-invitation"
            return row
        }()]
        response["page"] = page
        response["has_more"] = page == 1
        return try JSONSerialization.data(withJSONObject: response)
    }
}

private actor ShiftedApplicationsAPI: Phase2API {
    let base = PagedPlayerAPI()
    func phase2Data(path: String, method: String, query: [URLQueryItem], body: Data?) async throws -> Data {
        let raw = try await base.phase2Data(path: path, method: method, query: query, body: body)
        guard query.first?.value == "2" else { return raw }
        var dto = try JSONSerialization.jsonObject(with: raw) as! [String: Any]
        var rows = dto["applications"] as! [[String: Any]]
        var duplicate = rows[0]
        duplicate["id"] = "newer-29"
        duplicate["status"] = "shortlisted"
        rows.insert(duplicate, at: 0)
        dto["applications"] = rows
        return try JSONSerialization.data(withJSONObject: dto)
    }
}

private actor SuspendedTrialSendAPI: Phase2API {
    let fixture = Phase2FixtureTransport(mode: "player")
    private var started = false
    private var startWaiter: CheckedContinuation<Void, Never>?
    private var sendWaiter: CheckedContinuation<Void, Never>?
    func waitForSend() async {
        if started { return }
        await withCheckedContinuation { startWaiter = $0 }
    }
    func release() { sendWaiter?.resume(); sendWaiter = nil }
    func phase2Data(path: String, method: String, query: [URLQueryItem], body: Data?) async throws -> Data {
        if method == "POST" {
            await withCheckedContinuation { continuation in
                sendWaiter = continuation
                started = true
                startWaiter?.resume(); startWaiter = nil
            }
        }
        return try await fixture.phase2Data(path: path, method: method, query: query, body: body)
    }
}

private actor SuspendedPrivateReadAPI: Phase2API {
    let fixture = Phase2FixtureTransport(mode: "player")
    private var started = false
    private var startWaiter: CheckedContinuation<Void, Never>?
    private var readWaiter: CheckedContinuation<Void, Never>?
    func waitForRead() async {
        if started { return }
        await withCheckedContinuation { startWaiter = $0 }
    }
    func release() { readWaiter?.resume(); readWaiter = nil }
    func phase2Data(path: String, method: String, query: [URLQueryItem], body: Data?) async throws -> Data {
        await withCheckedContinuation { continuation in
            readWaiter = continuation
            started = true
            startWaiter?.resume(); startWaiter = nil
        }
        return try await fixture.phase2Data(path: path, method: method, query: query, body: body)
    }
}
