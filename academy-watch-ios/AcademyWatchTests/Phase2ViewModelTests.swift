import XCTest

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
    private var failure: Int?
    init(_ mode: String = "player") { fixture = Phase2FixtureTransport(mode: mode) }
    func fail(_ status: Int?) { failure = status }
    func phase2Data(path: String, method: String, query: [URLQueryItem], body: Data?) async throws -> Data {
        calls.append(Call(path: path, method: method, query: query, body: body))
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
    func phase2Data(path: String, method: String, query: [URLQueryItem], body: Data?) async throws -> Data {
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
    func testDirectorySearchNeverPutsSearchOrCoordinatesInURL() async throws {
        let client = RecordingPhase2API()
        let model = DirectoryViewModel(client: client)
        await model.search(DirectorySearch(q: "Quillmere", lat: 51, lng: -1, radiusKm: 50))
        let snapshot = await client.snapshot()
        let call = try XCTUnwrap(snapshot.first)
        XCTAssertEqual(call.path, "club-directory/search")
        XCTAssertEqual(call.method, "POST")
        XCTAssertTrue(call.query.isEmpty)
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: try XCTUnwrap(call.body)) as? [String: Any])
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
        XCTAssertEqual(calls.last?.path, "club/101/opportunities/\(Phase2FixtureTransport.postId)/applications")
        XCTAssertEqual(calls.last?.query.first?.value, "3")
        XCTAssertEqual(posts.page, 2)
        XCTAssertEqual(applications.page, 3)
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
        let body = try JSONSerialization.jsonObject(with: try XCTUnwrap(calls.first?.body)) as! [String: Any]
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
    func testFeatureFailureFailsClosedAndAuthResetClearsScope() async {
        let client = RecordingPhase2API("owner")
        let model = Phase2Workspace(client: client)
        await model.load(authenticated: true)
        XCTAssertTrue(model.selected?.access.canRecruit == true)
        await client.fail(503)
        await model.load(authenticated: true)
        XCTAssertEqual(model.flags, Phase2Flags())
        XCTAssertTrue(model.clubs.isEmpty)
        model.reset()
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
        XCTAssertEqual(RootTab.available(for: .player, flags: flags), [.home, .clubs, .trials, .applied, .account])
        XCTAssertEqual(RootTab.available(for: .scout, flags: flags), [.scoutDesk, .watchlist, .lists, .account])
        let result: ClubAccessResponse = try await RecordingPhase2API("owner").read("club/101/access/me")
        XCTAssertEqual(
            RootTab.available(for: .club, flags: flags, access: result.access),
            [.home, .squads, .matches, .recruiting, .account])
        let partial = Phase2Flags(directory: true)
        XCTAssertEqual(RootTab.available(for: .player, flags: partial), [.home, .clubs, .account])
    }
    func testSignedOutTrialReadNeverFetchesClaims() async {
        let client = RecordingPhase2API()
        let model = TrialDetailViewModel(id: Phase2FixtureTransport.postId, client: client, now: { Self.fixtureNow })
        await model.load(authenticated: false, applications: true)
        let calls = await client.snapshot()
        XCTAssertEqual(calls.map(\.path), ["opportunities/\(Phase2FixtureTransport.postId)"])
        XCTAssertTrue(model.claims.isEmpty)
        XCTAssertFalse(model.canSend)
    }
    func testApplicationRequiresConsentAndUsesStableRetryKey() async throws {
        let client = RecordingPhase2API("apply")
        let model = TrialDetailViewModel(id: Phase2FixtureTransport.postId, client: client, now: { Self.fixtureNow })
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
        let bodies = try writes.map { try JSONSerialization.jsonObject(with: XCTUnwrap($0.body)) as! [String: Any] }
        XCTAssertEqual(bodies.count, 2)
        XCTAssertEqual(bodies[0]["client_request_id"] as? String, bodies[1]["client_request_id"] as? String)
        XCTAssertEqual(bodies[0]["contact_consent"] as? Bool, true)
    }
    func testGuardianCannotApplyWithoutEligibleSelfClaim() async {
        let client = RecordingPhase2API("parent")
        let model = TrialDetailViewModel(id: Phase2FixtureTransport.postId, client: client, now: { Self.fixtureNow })
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
            id: Phase2FixtureTransport.applicationId, client: RecordingPhase2API(), now: { Self.fixtureNow })
        await model.load()
        await model.applicantAction("accept")
        XCTAssertEqual(model.application?.reservationState, "confirmed")
        XCTAssertFalse(model.application?.canRespond() == true)
        await model.applicantAction("withdraw")
        XCTAssertTrue(model.application?.isTerminal == true)
    }
    func testPrivateConflictDropsStaleApplicantButPreservesDraft() async {
        let client = RecordingPhase2API("conflict")
        let model = ApplicationDetailViewModel(
            id: Phase2FixtureTransport.applicationId, programId: 101, client: client, now: { Self.fixtureNow })
        await model.load()
        model.venue = "Saltings"
        model.instructions = "Bring boots"
        model.note = "Draft note"
        await model.transition("invited")
        XCTAssertNil(model.application)
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
        XCTAssertNil(model.application)
        XCTAssertTrue(model.error?.contains("full") == true)
    }
    func testSignedRequiresSeparateEnrollment() async {
        let client = RecordingPhase2API("signed")
        let model = ApplicationDetailViewModel(
            id: Phase2FixtureTransport.applicationId, programId: 101, client: client, now: { Self.fixtureNow })
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
            id: Phase2FixtureTransport.applicationId, programId: 101, client: client, now: { Self.fixtureNow })
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
        await model.update(person, role: "analyst", allSquads: person.allSquads, squadIds: person.squadIds)
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
        XCTAssertTrue(Phase2Time.zoneLabel("Europe/London", at: "2026-10-07T18:30:00Z").contains("UTC+01:00"))
        XCTAssertTrue(Phase2Time.display("2026-10-07T18:30:00Z", zone: "Europe/London").contains("19:30"))
        XCTAssertTrue(Phase2Time.zoneLabel("Europe/London", at: "2026-10-27T18:30:00Z").contains("UTC+00:00"))
        XCTAssertTrue(Phase2Time.zoneLabel("Unknown/Zone", at: nil).contains("UTC fallback"))
        XCTAssertEqual(Phase2Time.display("bad", zone: "Europe/London"), "Date unavailable")
    }
    func testContactNaiveUTCTimestampsMatchExplicitUTCAndPreserveOffsets() throws {
        let naive = try XCTUnwrap(Phase2Time.date("2026-08-26T11:15:00"))
        XCTAssertEqual(naive, Phase2Time.date("2026-08-26T11:15:00Z"))
        XCTAssertEqual(naive, Phase2Time.date("2026-08-26T12:15:00+01:00"))
        XCTAssertEqual(
            Phase2Time.date("2026-08-26T11:15:00.123456"), Phase2Time.date("2026-08-26T11:15:00.123456Z"))
        XCTAssertTrue(Phase2Time.display("2026-08-26T11:15:00", zone: "Europe/London").contains("12:15 BST"))
        XCTAssertNil(Phase2Time.date("2026-08-26"))
        XCTAssertNil(Phase2Time.date("2026-08-26T11:15:00junk"))
    }
    func testTimeRangePreservesEndTimeAndBothZonesAcrossDST() {
        XCTAssertEqual(
            Phase2Time.interval("2026-10-07T18:30:00Z", "2026-10-07T20:00:00Z", zone: "Europe/London"),
            "Wed 7 Oct, 19:30–21:00 BST")
        let change = Phase2Time.interval("2026-10-25T00:30:00Z", "2026-10-25T01:30:00Z", zone: "Europe/London")
        XCTAssertTrue(change.contains("BST"))
        XCTAssertTrue(change.contains("GMT"))
        let midnight = Phase2Time.interval("2026-10-07T22:30:00Z", "2026-10-08T01:00:00Z", zone: "Europe/London")
        XCTAssertTrue(midnight.contains("Wed 7 Oct"))
        XCTAssertTrue(midnight.contains("Thu 8 Oct"))
        XCTAssertEqual(Phase2Time.interval(nil, nil, zone: "Europe/London"), "No fixed date")
    }
}
