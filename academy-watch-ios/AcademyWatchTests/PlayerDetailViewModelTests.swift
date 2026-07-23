import XCTest
@testable import AcademyWatch

final class PlayerDetailViewModelTests: XCTestCase {
    @MainActor
    func testLoadsIndependentSectionsAndDerivesDisplayData() async throws {
        let client = try capturedClient()
        let viewModel = PlayerDetailViewModel(playerID: 403_064, apiClient: client)

        await viewModel.loadIfNeeded()

        XCTAssertTrue(viewModel.hasAttemptedLoad)
        XCTAssertTrue(viewModel.loadingSections.isEmpty)
        XCTAssertEqual(viewModel.profile?.name, "H. Amass")
        XCTAssertEqual(viewModel.recentMatches.count, 5)
        XCTAssertEqual(viewModel.recentMatches.first?.opponent, "Coventry")
        XCTAssertEqual(viewModel.timelineEntries.first?.clubName, "Norwich")
        XCTAssertEqual(viewModel.visibleAvailability?.summary.totalAbsences, 23)
        XCTAssertEqual(viewModel.competitionCount(for: "Norwich", season: 2025), 1)
        XCTAssertEqual(viewModel.averageRating(for: "Norwich"), 6.6)
        XCTAssertNil(viewModel.cleanSheets(for: "Norwich"))
        XCTAssertTrue(viewModel.errorMessages.isEmpty)
    }

    @MainActor
    func testSectionFailureDoesNotDiscardLoadedProfile() async throws {
        var client = try capturedClient()
        client.failedSection = .journey
        let viewModel = PlayerDetailViewModel(playerID: 403_064, apiClient: client)

        await viewModel.loadIfNeeded()

        XCTAssertEqual(viewModel.profile?.name, "H. Amass")
        XCTAssertEqual(viewModel.seasonStats?.minutes, 1_940)
        XCTAssertEqual(viewModel.recentMatches.count, 5)
        XCTAssertNil(viewModel.journey)
        XCTAssertTrue(viewModel.timelineEntries.isEmpty)
        XCTAssertEqual(viewModel.errorMessage(for: .journey), "Journey unavailable.")
        XCTAssertNil(viewModel.errorMessage(for: .profile))
    }

    @MainActor
    func testRecentFixtureHydrationCompletesBeforeSeasonStatsRequest() async throws {
        let captured = try capturedClient()
        let client = SequencedPlayerDetailClient(captured: captured)
        let viewModel = PlayerDetailViewModel(playerID: 403_064, apiClient: client)

        await viewModel.loadIfNeeded()

        let requestedTooEarly = await client.seasonRequestedBeforeRecentFinished()
        XCTAssertFalse(requestedTooEarly)
        XCTAssertEqual(viewModel.seasonStats?.minutes, 1_940)
    }

    @MainActor
    func testCancellationClearsLoadingStateForRetry() async throws {
        let viewModel = PlayerDetailViewModel(
            playerID: 403_064,
            apiClient: SuspendedPlayerDetailClient()
        )
        let loadTask = Task { await viewModel.loadIfNeeded() }

        try await Task.sleep(nanoseconds: 30_000_000)
        loadTask.cancel()
        await loadTask.value

        XCTAssertTrue(viewModel.loadingSections.isEmpty)
        XCTAssertFalse(viewModel.hasAttemptedLoad)
    }

    @MainActor
    func testReloadCancelsAndDrainsPriorHydrationBeforeRestarting() async throws {
        let captured = try capturedClient()
        let client = ReloadSupersessionPlayerDetailClient(captured: captured)
        let viewModel = PlayerDetailViewModel(playerID: 403_064, apiClient: client)
        let firstLoad = Task { await viewModel.loadIfNeeded() }

        var firstRecentStarted = false
        for _ in 0 ..< 100 {
            firstRecentStarted = await client.hasStartedFirstRecentRequest()
            if firstRecentStarted { break }
            try await Task.sleep(nanoseconds: 5_000_000)
        }
        XCTAssertTrue(firstRecentStarted)

        await viewModel.reload()
        await firstLoad.value

        let snapshot = await client.snapshot()
        XCTAssertEqual(snapshot.recentRequests, 2)
        XCTAssertTrue(snapshot.firstRecentCancelled)
        XCTAssertEqual(snapshot.maximumConcurrentRecentRequests, 1)
        XCTAssertEqual(snapshot.seasonRequests, 1)
        XCTAssertEqual(viewModel.seasonStats?.minutes, 1_940)
        XCTAssertTrue(viewModel.loadingSections.isEmpty)
    }

    @MainActor
    func testCancelledRefreshPreservesLastKnownGoodDetail() async throws {
        let captured = try capturedClient()
        let client = RefreshCancellationPlayerDetailClient(captured: captured)
        let viewModel = PlayerDetailViewModel(playerID: 403_064, apiClient: client)

        await viewModel.loadIfNeeded()
        let originalProfile = viewModel.profile
        let originalSeasonStats = viewModel.seasonStats
        let originalRecentFixtures = viewModel.recentFixtures
        let originalJourney = viewModel.journey
        let originalAvailability = viewModel.availability

        await client.suspendRequests()
        let refreshTask = Task { await viewModel.reload() }
        try await Task.sleep(nanoseconds: 30_000_000)
        refreshTask.cancel()
        await refreshTask.value

        XCTAssertEqual(viewModel.profile, originalProfile)
        XCTAssertEqual(viewModel.seasonStats, originalSeasonStats)
        XCTAssertEqual(viewModel.recentFixtures, originalRecentFixtures)
        XCTAssertEqual(viewModel.journey, originalJourney)
        XCTAssertEqual(viewModel.availability, originalAvailability)
        XCTAssertTrue(viewModel.hasAttemptedLoad)
        XCTAssertTrue(viewModel.loadingSections.isEmpty)
    }

    private func capturedClient() throws -> StubPlayerDetailClient {
        try StubPlayerDetailClient(
            profile: decode(PlayerProfile.self, fixture: "player_profile_outfielder"),
            seasonStats: decode(PlayerSeasonStats.self, fixture: "player_season_stats_outfielder"),
            recentFixtures: decode(
                [PlayerRecentFixture].self,
                fixture: "player_recent_fixtures_outfielder"
            ),
            journey: decode(PlayerJourneyResponse.self, fixture: "player_journey_outfielder"),
            availability: decode(PlayerAvailability.self, fixture: "player_availability_outfielder")
        )
    }

    private func decode<Value: Decodable>(
        _ type: Value.Type,
        fixture: String
    ) throws -> Value {
        let fixtureURL = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: fixture, withExtension: "json")
        )
        let data = try Data(contentsOf: fixtureURL)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: data)
    }
}

private struct StubPlayerDetailClient: PlayerDetailAPIClientProtocol {
    let profile: PlayerProfile
    let seasonStats: PlayerSeasonStats
    let recentFixtures: [PlayerRecentFixture]
    let journey: PlayerJourneyResponse
    let availability: PlayerAvailability
    var failedSection: PlayerDetailSection?

    init(
        profile: PlayerProfile,
        seasonStats: PlayerSeasonStats,
        recentFixtures: [PlayerRecentFixture],
        journey: PlayerJourneyResponse,
        availability: PlayerAvailability,
        failedSection: PlayerDetailSection? = nil
    ) {
        self.profile = profile
        self.seasonStats = seasonStats
        self.recentFixtures = recentFixtures
        self.journey = journey
        self.availability = availability
        self.failedSection = failedSection
    }

    func fetchPlayerProfile(playerID _: Int) async throws -> PlayerProfile {
        try throwIfNeeded(.profile)
        return profile
    }

    func fetchPlayerSeasonStats(playerID _: Int) async throws -> PlayerSeasonStats {
        try throwIfNeeded(.seasonStats)
        return seasonStats
    }

    func fetchPlayerRecentFixtures(playerID _: Int) async throws -> [PlayerRecentFixture] {
        try throwIfNeeded(.recentForm)
        return recentFixtures
    }

    func fetchPlayerJourney(playerID _: Int) async throws -> PlayerJourneyResponse {
        try throwIfNeeded(.journey)
        return journey
    }

    func fetchPlayerAvailability(playerID _: Int) async throws -> PlayerAvailability {
        try throwIfNeeded(.availability)
        return availability
    }

    private func throwIfNeeded(_ section: PlayerDetailSection) throws {
        guard failedSection == section else { return }
        throw StubPlayerDetailError(section: section)
    }
}

private struct StubPlayerDetailError: LocalizedError {
    let section: PlayerDetailSection

    var errorDescription: String? {
        switch section {
        case .profile: "Profile unavailable."
        case .seasonStats: "Season stats unavailable."
        case .recentForm: "Recent form unavailable."
        case .journey: "Journey unavailable."
        case .availability: "Availability unavailable."
        }
    }
}

private actor SequencedPlayerDetailClient: PlayerDetailAPIClientProtocol {
    private let captured: StubPlayerDetailClient
    private var recentFinished = false
    private var seasonWasRequestedTooEarly = false

    init(captured: StubPlayerDetailClient) {
        self.captured = captured
    }

    func fetchPlayerProfile(playerID _: Int) async throws -> PlayerProfile {
        captured.profile
    }

    func fetchPlayerSeasonStats(playerID _: Int) async throws -> PlayerSeasonStats {
        if !recentFinished {
            seasonWasRequestedTooEarly = true
        }
        return captured.seasonStats
    }

    func fetchPlayerRecentFixtures(playerID _: Int) async throws -> [PlayerRecentFixture] {
        try await Task.sleep(nanoseconds: 30_000_000)
        recentFinished = true
        return captured.recentFixtures
    }

    func fetchPlayerJourney(playerID _: Int) async throws -> PlayerJourneyResponse {
        captured.journey
    }

    func fetchPlayerAvailability(playerID _: Int) async throws -> PlayerAvailability {
        captured.availability
    }

    func seasonRequestedBeforeRecentFinished() -> Bool {
        seasonWasRequestedTooEarly
    }
}

private struct SuspendedPlayerDetailClient: PlayerDetailAPIClientProtocol {
    func fetchPlayerProfile(playerID _: Int) async throws -> PlayerProfile {
        try await suspendForever()
    }

    func fetchPlayerSeasonStats(playerID _: Int) async throws -> PlayerSeasonStats {
        try await suspendForever()
    }

    func fetchPlayerRecentFixtures(playerID _: Int) async throws -> [PlayerRecentFixture] {
        try await suspendForever()
    }

    func fetchPlayerJourney(playerID _: Int) async throws -> PlayerJourneyResponse {
        try await suspendForever()
    }

    func fetchPlayerAvailability(playerID _: Int) async throws -> PlayerAvailability {
        try await suspendForever()
    }

    private func suspendForever<Value>() async throws -> Value {
        try await Task.sleep(nanoseconds: 5_000_000_000)
        throw CancellationError()
    }
}

private actor ReloadSupersessionPlayerDetailClient: PlayerDetailAPIClientProtocol {
    private let captured: StubPlayerDetailClient
    private var recentRequests = 0
    private var activeRecentRequests = 0
    private var maximumConcurrentRecentRequests = 0
    private var firstRecentStarted = false
    private var firstRecentCancelled = false
    private var seasonRequests = 0

    init(captured: StubPlayerDetailClient) {
        self.captured = captured
    }

    func fetchPlayerProfile(playerID _: Int) async throws -> PlayerProfile {
        captured.profile
    }

    func fetchPlayerSeasonStats(playerID _: Int) async throws -> PlayerSeasonStats {
        seasonRequests += 1
        return captured.seasonStats
    }

    func fetchPlayerRecentFixtures(playerID _: Int) async throws -> [PlayerRecentFixture] {
        recentRequests += 1
        let requestNumber = recentRequests
        activeRecentRequests += 1
        maximumConcurrentRecentRequests = max(
            maximumConcurrentRecentRequests,
            activeRecentRequests
        )
        defer { activeRecentRequests -= 1 }

        if requestNumber == 1 {
            firstRecentStarted = true
            do {
                try await Task.sleep(nanoseconds: 5_000_000_000)
            } catch {
                firstRecentCancelled = true
                throw error
            }
        }

        return captured.recentFixtures
    }

    func fetchPlayerJourney(playerID _: Int) async throws -> PlayerJourneyResponse {
        captured.journey
    }

    func fetchPlayerAvailability(playerID _: Int) async throws -> PlayerAvailability {
        captured.availability
    }

    func hasStartedFirstRecentRequest() -> Bool {
        firstRecentStarted
    }

    func snapshot() -> (
        recentRequests: Int,
        firstRecentCancelled: Bool,
        maximumConcurrentRecentRequests: Int,
        seasonRequests: Int
    ) {
        (
            recentRequests,
            firstRecentCancelled,
            maximumConcurrentRecentRequests,
            seasonRequests
        )
    }
}

private actor RefreshCancellationPlayerDetailClient: PlayerDetailAPIClientProtocol {
    private let captured: StubPlayerDetailClient
    private var shouldSuspend = false

    init(captured: StubPlayerDetailClient) {
        self.captured = captured
    }

    func suspendRequests() {
        shouldSuspend = true
    }

    func fetchPlayerProfile(playerID _: Int) async throws -> PlayerProfile {
        try await waitIfSuspended()
        return captured.profile
    }

    func fetchPlayerSeasonStats(playerID _: Int) async throws -> PlayerSeasonStats {
        try await waitIfSuspended()
        return captured.seasonStats
    }

    func fetchPlayerRecentFixtures(playerID _: Int) async throws -> [PlayerRecentFixture] {
        try await waitIfSuspended()
        return captured.recentFixtures
    }

    func fetchPlayerJourney(playerID _: Int) async throws -> PlayerJourneyResponse {
        try await waitIfSuspended()
        return captured.journey
    }

    func fetchPlayerAvailability(playerID _: Int) async throws -> PlayerAvailability {
        try await waitIfSuspended()
        return captured.availability
    }

    private func waitIfSuspended() async throws {
        guard shouldSuspend else { return }
        try await Task.sleep(nanoseconds: 5_000_000_000)
    }
}
