import XCTest

@testable import AcademyWatch

final class PlayerClubExperienceTests: XCTestCase {
    @MainActor
    func testSelfClaimRequiresAgeEvidenceBeforeSending() async {
        let model = LocalPlayerFormViewModel(context: .claimant, today: { Self.day(2026, 9, 6) })
        model.displayName = "Maya Okafor"
        await model.submit()
        XCTAssertNotNil(model.error(for: .birthDate))
        XCTAssertNil(model.created)
        XCTAssertNil(model.requestError, "Invalid form must not make an API request")
    }
    @MainActor
    func testSelfClaimBirthdayAndYearOnlyBoundaries() {
        let model = LocalPlayerFormViewModel(
            context: .claimant, calendar: Self.calendar, today: { Self.day(2026, 9, 6) })
        model.displayName = "Maya Okafor"
        model.birthDate = Self.day(2008, 9, 7)
        XCTAssertFalse(model.validate())
        model.birthDate = Self.day(2008, 9, 6)
        XCTAssertTrue(model.validate())
        model.birthDate = nil
        model.birthYear = "2008"
        XCTAssertFalse(model.validate(), "Year alone cannot establish which side of the birthday a player is on")
        model.birthYear = "2007"
        XCTAssertTrue(model.validate())
    }
    @MainActor
    func testGuardianDoesNotBecomeAdultPlayerSelfClaim() {
        let model = LocalPlayerFormViewModel(context: .claimant)
        model.displayName = "Represented Player"
        model.relationship = .guardian
        XCTAssertTrue(model.validate())
        XCTAssertFalse(model.requiresAdultEvidence)
        XCTAssertEqual(model.submission.relationshipType, .guardian)
    }
    func testDefaultHomeAndExplicitScoutLaunchArePreserved() {
        XCTAssertEqual(RootTab.fromLaunchArguments([]), .home)
        XCTAssertEqual(RootTab.fromLaunchArguments(["-initialTab", "scout"]), .scoutDesk)
        XCTAssertEqual(RootTab.fromLaunchArguments(["-playerId", "403064"]), .scoutDesk)
    }
    func testLocalOwnerPathsNeverUseNegativeIDsInLegacyRoutes() {
        XCTAssertEqual(APIClient.ownerShowcasePath(playerID: -481), "local-players/481/showcase")
        XCTAssertEqual(APIClient.ownerShowcasePath(playerID: 403064), "players/403064/showcase")
    }
    func testBasicProfileUpdateExplicitlyClearsNullableFieldsWithoutContractFields() throws {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(
            BasicProfileUpdate(bio: "My story", positions: "CM", preferredFoot: nil, heightCm: nil))
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertTrue(body["preferred_foot"] is NSNull)
        XCTAssertTrue(body["height_cm"] is NSNull)
        XCTAssertEqual(Set(body.keys), ["bio", "positions", "preferred_foot", "height_cm"])
    }
    func testPublicShareLinkRejectsUntrustedPrivateAndCredentialedURLs() {
        XCTAssertNotNil(PublicProfileLink.validated("https://theacademywatch.com/p/-481"))
        for url in [
            "https://evil.test/p/481", "http://theacademywatch.com/p/481", "https://user@theacademywatch.com/p/481",
            "https://theacademywatch.com/p/481?token=secret", "https://theacademywatch.com/my-club",
            "https://theacademywatch.com/p/0",
        ] {
            XCTAssertNil(PublicProfileLink.validated(url))
        }
    }
    func testPhotoUploadNeverForwardsAccountAuthorizationOrCookies() throws {
        let target = ProfilePhotoUpload.Upload(
            url: URL(string: "https://fixture.blob.core.windows.net/pending/photo.jpg?sig=test")!, method: "PUT",
            headers: [
                "x-ms-blob-type": "BlockBlob", "Content-Type": "image/jpeg", "Authorization": "do-not-forward",
                "Cookie": "do-not-forward",
            ])
        let request = try ProfilePhotoTransfer.request(destination: target)
        XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
        XCTAssertNil(request.value(forHTTPHeaderField: "Cookie"))
        XCTAssertEqual(request.value(forHTTPHeaderField: "x-ms-blob-type"), "BlockBlob")
        XCTAssertThrowsError(
            try ProfilePhotoTransfer.request(
                destination: .init(url: URL(string: "https://evil.test/upload")!, method: "PUT", headers: [:])))
        XCTAssertThrowsError(try ProfilePhotoPreparation.jpeg(Data("not an image".utf8)))
    }
    @MainActor
    func testProfilesClearWhenOwnershipCanNoLongerBeLoaded() async throws {
        let client = ExperienceStub()
        let model = MyProfilesViewModel(client: client)
        await model.load()
        XCTAssertEqual(model.claims.count, 1)
        await client.denyAccess()
        await model.load()
        XCTAssertTrue(model.claims.isEmpty)
        XCTAssertNotNil(model.error)
    }
    @MainActor
    func testFeedbackAcknowledgmentOnlyHappensAfterExplicitAction() async {
        let client = ExperienceStub()
        let model = PlayerFeedbackViewModel(client: client)
        await model.open(id: "f1")
        let before = await client.acknowledgmentCount
        XCTAssertEqual(before, 0)
        await model.acknowledge()
        let after = await client.acknowledgmentCount
        XCTAssertEqual(after, 1)
        XCTAssertFalse(model.detail?.canAcknowledge ?? true)
    }
    @MainActor
    func testFeedbackIsClearedWhenAccessIsWithdrawn() async {
        let client = ExperienceStub()
        let model = PlayerFeedbackViewModel(client: client)
        await model.open(id: "f1")
        XCTAssertNotNil(model.detail)
        await client.denyAccess()
        await model.acknowledge()
        XCTAssertNil(model.detail)
        XCTAssertNotNil(model.error)
    }
    @MainActor
    func testDisabledClubFeatureDoesNotLookLikeAnEmptySuccessfulInbox() async {
        let client = ExperienceStub()
        await client.denyAccess()
        let model = ClubInboxViewModel(client: client)
        await model.load()
        XCTAssertTrue(model.unavailable)
        XCTAssertTrue(model.invitations.isEmpty)
    }
    @MainActor
    func testPracticeUsesCurrentVersionAndNeverAcknowledges() async {
        let client = ExperienceStub()
        let model = PlayerFeedbackViewModel(client: client)
        await model.open(id: "f1")
        await model.updateProgress(status: "working_on_it", note: "Practised scanning")
        XCTAssertEqual(model.detail?.developmentProgress?.version, 1)
        await model.updateProgress(status: "ready_for_review", note: "Found the forward pass")
        XCTAssertEqual(model.detail?.developmentProgress?.version, 2)
        XCTAssertEqual(model.detail?.developmentProgress?.reflection, "Found the forward pass")
        let count = await client.acknowledgmentCount
        XCTAssertEqual(count, 0)
    }
    @MainActor
    func testProgressConflictKeepsDetailAndRequiresRefresh() async {
        let client = ExperienceStub()
        let model = PlayerFeedbackViewModel(client: client)
        await model.open(id: "f1")
        await client.conflictProgress()
        await model.updateProgress(status: "ready_for_review", note: "My reflection")
        XCTAssertTrue(model.progressConflict)
        XCTAssertNotNil(model.detail)
        await model.updateProgress(status: "ready_for_review", note: "Retry")
        let count = await client.progressCalls
        XCTAssertEqual(count, 1)
        await model.open(id: "f1")
        XCTAssertFalse(model.progressConflict)
    }
    @MainActor
    func testProgressLosesPrivateDetailAfterAccessRemoval() async {
        let client = ExperienceStub()
        let model = PlayerFeedbackViewModel(client: client)
        await model.open(id: "f1")
        await client.denyAccess()
        await model.updateProgress(status: "working_on_it", note: "My reflection")
        XCTAssertNil(model.detail)
        XCTAssertNotNil(model.error)
    }
    private static var calendar: Calendar {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(secondsFromGMT: 0)!
        return c
    }
    private static func day(_ year: Int, _ month: Int, _ day: Int) -> Date {
        calendar.date(from: DateComponents(year: year, month: month, day: day))!
    }
}

private actor ExperienceStub: PlayerClubAPIClientProtocol {
    private var denied = false
    private var conflict = false
    private var progress: PlayerDevelopmentProgress?
    private(set) var progressCalls = 0
    func conflictProgress() { conflict = true }
    private(set) var acknowledgmentCount = 0
    func denyAccess() { denied = true }
    private func check() throws { if denied { throw APIClientError.httpStatus(404) } }
    private func feedback(acknowledged: Bool = false) throws -> PlayerFeedback {
        try check()
        return PlayerFeedback(
            id: "f1", threadId: "t1", revision: 1, playerApiId: -481, program: .init(id: 44, name: "Club"),
            author: .init(displayName: "Coach"), title: "Next step", body: "Private feedback",
            publishedAt: "2026-09-06T00:00:00Z", acknowledgedAt: acknowledged ? "2026-09-06T01:00:00Z" : nil,
            canAcknowledge: !acknowledged,
            developmentAction: .init(focus: "Scan", practice: "Check shoulders", success: "Find the pass", reviewOn: nil),
            developmentProgress: progress, canUpdateProgress: true)
    }
    func fetchMyProfileClaims() async throws -> PlayerClaimsResponse {
        try check()
        return PlayerClaimsResponse(claims: [
            PlayerProfileClaim(
                id: 1, playerApiId: nil, localPlayerId: 481, userAccountId: 1, relationshipType: "player",
                status: .approved, message: nil, reviewedBy: nil, reviewedAt: nil, createdAt: nil, playerName: "Maya")
        ])
    }
    func fetchOwnerShowcase(playerID: Int) async throws -> OwnerShowcase { throw URLError(.unsupportedURL) }
    func saveBasicProfile(playerID: Int, update: BasicProfileUpdate) async throws { try check() }
    func addHighlight(playerID: Int, url: String, title: String) async throws { try check() }
    func fetchClubInvitations(before: String?) async throws -> ClubInvitationsResponse {
        try check()
        return .init(invitations: [], nextBefore: nil)
    }
    func decideClubInvitation(id: String, decision: ClubInvitationDecision) async throws { try check() }
    func fetchPlayerFeedback(playerID: Int, before: String?) async throws -> PlayerFeedbackPage {
        .init(feedback: [try feedback()], nextBefore: nil)
    }
    func fetchFeedbackDetail(id: String) async throws -> PlayerFeedback { try feedback() }
    func updateDevelopmentProgress(id: String, update: PlayerDevelopmentUpdate) async throws -> PlayerFeedback {
        try check()
        progressCalls += 1
        if conflict || update.expectedVersion != (progress?.version ?? 0) { throw APIClientError.httpStatus(409) }
        progress = .init(version: update.expectedVersion + 1, status: update.status, reflection: update.note,
            coachNote: nil, updatedAt: "2026-09-06T00:00:00Z", history: [])
        return try feedback()
    }
    func acknowledgeFeedback(id: String) async throws -> PlayerFeedback {
        try check()
        acknowledgmentCount += 1
        return try feedback(acknowledged: true)
    }
}
