import XCTest
@testable import AcademyWatch

final class ScoutDeskViewModelTests: XCTestCase {
    @MainActor
    func testPhaseSwitchResetsPaginationAndAppliesDefaultSort() async throws {
        let fixture = try capturedPlayersResponse()
        let client = RecordingScoutAPIClient(players: Array(fixture.players.prefix(2)))
        let viewModel = ScoutDeskViewModel(
            apiClient: client,
            responseCache: EmptyScoutResponseCache(),
            pageSize: 1
        )

        await viewModel.loadInitialIfNeeded()
        let firstPagePlayer = try XCTUnwrap(viewModel.players.last)
        await viewModel.loadNextPageIfNeeded(currentPlayer: firstPagePlayer)

        XCTAssertEqual(viewModel.currentPage, 2)

        await viewModel.selectPhase(.goalkeepers)

        XCTAssertEqual(viewModel.selectedPhase, .goalkeepers)
        XCTAssertEqual(viewModel.selectedSortKey, "clean_sheets")
        XCTAssertEqual(viewModel.selectedSortOrder, .descending)
        XCTAssertEqual(viewModel.currentPage, 1)

        let playerRequests = await client.recordedPlayerRequests()
        let phaseRequest = try XCTUnwrap(playerRequests.last)
        XCTAssertEqual(phaseRequest.page, 1)
        XCTAssertEqual(phaseRequest.position, "Goalkeeper")
        XCTAssertEqual(phaseRequest.sort, "clean_sheets")
        XCTAssertEqual(phaseRequest.order, .descending)

        let boardRequests = await client.recordedLeaderboardRequests()
        let boardRequest = try XCTUnwrap(boardRequests.last)
        XCTAssertEqual(boardRequest.phase, .goalkeepers)
        XCTAssertEqual(boardRequest.position, "Goalkeeper")
        XCTAssertEqual(boardRequest.limit, 5)
    }

    @MainActor
    func testLatePageFromPreviousPhaseIsDiscarded() async throws {
        let fixture = try capturedPlayersResponse()
        let firstTwoPlayers = Array(fixture.players.prefix(2))
        let client = RecordingScoutAPIClient(players: firstTwoPlayers, delaySecondPage: true)
        let viewModel = ScoutDeskViewModel(
            apiClient: client,
            responseCache: EmptyScoutResponseCache(),
            pageSize: 1
        )

        await viewModel.loadInitialIfNeeded()
        let firstPagePlayer = try XCTUnwrap(viewModel.players.last)
        let oldPagination = Task {
            await viewModel.loadNextPageIfNeeded(currentPlayer: firstPagePlayer)
        }
        await client.waitUntilSecondPageStarts()

        await viewModel.selectPhase(.goalkeepers)
        await client.releaseSecondPage()
        await oldPagination.value

        XCTAssertEqual(viewModel.selectedPhase, .goalkeepers)
        XCTAssertEqual(viewModel.currentPage, 1)
        XCTAssertEqual(viewModel.players.map(\.playerId), [firstTwoPlayers[0].playerId])
        XCTAssertFalse(viewModel.isLoadingInitial)
        XCTAssertFalse(viewModel.isLoadingNextPage)
        XCTAssertNil(viewModel.paginationErrorMessage)
    }

    @MainActor
    func testSortChangeDoesNotReloadUnchangedLeaderboards() async throws {
        let fixture = try capturedPlayersResponse()
        let client = RecordingScoutAPIClient(players: Array(fixture.players.prefix(2)))
        let viewModel = ScoutDeskViewModel(
            apiClient: client,
            responseCache: EmptyScoutResponseCache(),
            pageSize: 1
        )

        await viewModel.loadInitialIfNeeded()
        let boardCountBeforeSort = await client.recordedLeaderboardRequests().count
        let goalsSort = try XCTUnwrap(
            viewModel.selectedPhase.sortOptions.first(where: { $0.key == "goals" })
        )

        await viewModel.selectSort(goalsSort)
        let boardCountAfterSort = await client.recordedLeaderboardRequests().count
        let lastPlayerRequest = await client.recordedPlayerRequests().last

        XCTAssertEqual(boardCountAfterSort, boardCountBeforeSort)
        XCTAssertEqual(lastPlayerRequest?.sort, "goals")
    }

    @MainActor
    func testCachedResponsesRenderWhileNetworkRefreshes() async throws {
        let playersResponse = try capturedPlayersResponse()
        let leaderboardsResponse = ScoutLeaderboardsResponse(
            leaderboards: ["top_scorers": Array(playersResponse.players.prefix(1))],
            limit: 5,
            phase: .all
        )
        let client = SuspendedScoutAPIClient(
            playersResponse: playersResponse,
            leaderboardsResponse: leaderboardsResponse
        )
        let cache = SeededScoutResponseCache(
            playersResponse: playersResponse,
            leaderboardsResponse: leaderboardsResponse
        )
        let viewModel = ScoutDeskViewModel(apiClient: client, responseCache: cache)

        let loadTask = Task {
            await viewModel.loadInitialIfNeeded()
        }
        await client.waitUntilBothRequestsStart()

        XCTAssertEqual(viewModel.players, playersResponse.players)
        XCTAssertEqual(viewModel.leaderboards, leaderboardsResponse.leaderboards)
        XCTAssertTrue(viewModel.isShowingCachedPlayers)
        XCTAssertTrue(viewModel.isShowingCachedLeaderboards)
        XCTAssertTrue(viewModel.isUpdatingCachedData)
        XCTAssertEqual(viewModel.firstRowDataSource, "disk-cache")
        XCTAssertNil(viewModel.initialLoadStartedAt)
        XCTAssertNil(viewModel.initialLoadFeedback())

        await client.releaseRequests()
        await loadTask.value

        XCTAssertFalse(viewModel.isShowingCachedPlayers)
        XCTAssertFalse(viewModel.isShowingCachedLeaderboards)
        XCTAssertFalse(viewModel.isUpdatingCachedData)
    }

    @MainActor
    func testColdStartFeedbackAppearsAfterThreeSecondsAndClearsWhenPlayersArrive() async throws {
        let playersResponse = try capturedPlayersResponse()
        let client = SuspendedScoutAPIClient(
            playersResponse: playersResponse,
            leaderboardsResponse: ScoutLeaderboardsResponse(
                leaderboards: [:],
                limit: 5,
                phase: .all
            )
        )
        let viewModel = ScoutDeskViewModel(
            apiClient: client,
            responseCache: EmptyScoutResponseCache()
        )

        let loadTask = Task {
            await viewModel.loadInitialIfNeeded()
        }
        await client.waitUntilBothRequestsStart()

        let startedAt = try XCTUnwrap(viewModel.initialLoadStartedAt)
        XCTAssertNil(viewModel.initialLoadFeedback(atUptime: startedAt + 2.999))
        XCTAssertEqual(
            viewModel.initialLoadFeedback(atUptime: startedAt + 3),
            ScoutInitialLoadFeedback(elapsedSeconds: 3)
        )
        XCTAssertEqual(
            viewModel.initialLoadFeedback(atUptime: startedAt + 8.9)?.title,
            "Waking up the match server…"
        )
        XCTAssertEqual(
            viewModel.initialLoadFeedback(atUptime: startedAt + 8.9)?.detail,
            "Still working — 8s elapsed"
        )

        await client.releaseRequests()
        await loadTask.value

        XCTAssertNil(viewModel.initialLoadStartedAt)
        XCTAssertNil(viewModel.initialLoadFeedback(atUptime: startedAt + 30))
    }

    @MainActor
    func testEmptyCachedResponseStillShowsColdStartFeedbackDuringRefresh() async throws {
        let networkResponse = try capturedPlayersResponse()
        let emptyCachedResponse = ScoutPlayersResponse(
            players: [],
            total: 0,
            page: 1,
            perPage: 25,
            totalPages: 0
        )
        let leaderboardsResponse = ScoutLeaderboardsResponse(
            leaderboards: [:],
            limit: 5,
            phase: .all
        )
        let client = SuspendedScoutAPIClient(
            playersResponse: networkResponse,
            leaderboardsResponse: leaderboardsResponse
        )
        let cache = SeededScoutResponseCache(
            playersResponse: emptyCachedResponse,
            leaderboardsResponse: leaderboardsResponse
        )
        let viewModel = ScoutDeskViewModel(apiClient: client, responseCache: cache)

        let loadTask = Task {
            await viewModel.loadInitialIfNeeded()
        }
        await client.waitUntilBothRequestsStart()

        let startedAt = try XCTUnwrap(viewModel.initialLoadStartedAt)
        XCTAssertTrue(viewModel.players.isEmpty)
        XCTAssertFalse(viewModel.isShowingCachedPlayers)
        XCTAssertEqual(
            viewModel.initialLoadFeedback(atUptime: startedAt + 3),
            ScoutInitialLoadFeedback(elapsedSeconds: 3)
        )

        await client.releaseRequests()
        await loadTask.value

        XCTAssertEqual(viewModel.players, networkResponse.players)
        XCTAssertNil(viewModel.initialLoadStartedAt)
    }

    @MainActor
    func testPlayerRefreshStartsBeforeDelayedLeaderboardCacheReturns() async throws {
        let playersResponse = try capturedPlayersResponse()
        let leaderboardsResponse = ScoutLeaderboardsResponse(
            leaderboards: [:],
            limit: 5,
            phase: .all
        )
        let client = SuspendedScoutAPIClient(
            playersResponse: playersResponse,
            leaderboardsResponse: leaderboardsResponse
        )
        let cache = DelayedLeaderboardsScoutResponseCache(playersResponse: playersResponse)
        let viewModel = ScoutDeskViewModel(apiClient: client, responseCache: cache)

        let loadTask = Task {
            await viewModel.loadInitialIfNeeded()
        }
        await cache.waitUntilLeaderboardsLoadStarts()
        await client.waitUntilPlayerRequestStarts()

        XCTAssertEqual(viewModel.players, playersResponse.players)
        XCTAssertTrue(viewModel.isShowingCachedPlayers)
        let didStartLeaderboards = await client.hasStartedLeaderboardRequest()
        XCTAssertFalse(didStartLeaderboards)

        await cache.releaseLeaderboardsLoad()
        await client.waitUntilBothRequestsStart()
        await client.releaseRequests()
        await loadTask.value
    }

    @MainActor
    func testOlderSameKeyCacheLookupCannotReplaceNewerReload() async throws {
        let playersResponse = try capturedPlayersResponse()
        let leaderboardsResponse = ScoutLeaderboardsResponse(
            leaderboards: [:],
            limit: 5,
            phase: .all
        )
        let client = SuspendedScoutAPIClient(
            playersResponse: playersResponse,
            leaderboardsResponse: leaderboardsResponse
        )
        let cache = BlockingPlayersScoutResponseCache(playersResponse: playersResponse)
        let viewModel = ScoutDeskViewModel(apiClient: client, responseCache: cache)

        let initialLoad = Task {
            await viewModel.loadInitialIfNeeded()
        }
        await cache.waitUntilPlayersLoadStarts()

        let newerReload = Task {
            await viewModel.reload()
        }
        await client.waitUntilBothRequestsStart()
        await cache.releasePlayersLoad()
        await initialLoad.value

        let counts = await client.requestCounts()
        XCTAssertEqual(counts.players, 1)
        XCTAssertEqual(counts.leaderboards, 1)

        await client.releaseRequests()
        await newerReload.value
    }

    private func capturedPlayersResponse() throws -> ScoutPlayersResponse {
        let fixtureURL = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: "scout_players", withExtension: "json")
        )
        let data = try Data(contentsOf: fixtureURL)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(ScoutPlayersResponse.self, from: data)
    }
}

private actor EmptyScoutResponseCache: ScoutResponseCaching {
    func loadPlayers(for _: ScoutPlayersCacheKey) async -> ScoutPlayersResponse? { nil }
    func savePlayers(_: ScoutPlayersResponse, for _: ScoutPlayersCacheKey) async {}
    func loadLeaderboards(for _: ScoutLeaderboardsCacheKey) async -> ScoutLeaderboardsResponse? { nil }
    func saveLeaderboards(_: ScoutLeaderboardsResponse, for _: ScoutLeaderboardsCacheKey) async {}
}

private actor SeededScoutResponseCache: ScoutResponseCaching {
    private let playersResponse: ScoutPlayersResponse
    private let leaderboardsResponse: ScoutLeaderboardsResponse

    init(
        playersResponse: ScoutPlayersResponse,
        leaderboardsResponse: ScoutLeaderboardsResponse
    ) {
        self.playersResponse = playersResponse
        self.leaderboardsResponse = leaderboardsResponse
    }

    func loadPlayers(for _: ScoutPlayersCacheKey) async -> ScoutPlayersResponse? {
        playersResponse
    }

    func savePlayers(_: ScoutPlayersResponse, for _: ScoutPlayersCacheKey) async {}

    func loadLeaderboards(for _: ScoutLeaderboardsCacheKey) async -> ScoutLeaderboardsResponse? {
        leaderboardsResponse
    }

    func saveLeaderboards(_: ScoutLeaderboardsResponse, for _: ScoutLeaderboardsCacheKey) async {}
}

private actor DelayedLeaderboardsScoutResponseCache: ScoutResponseCaching {
    private let playersResponse: ScoutPlayersResponse
    private var leaderboardsLoadStarted = false
    private var leaderboardsStartWaiters: [CheckedContinuation<Void, Never>] = []
    private var leaderboardsContinuation: CheckedContinuation<Void, Never>?

    init(playersResponse: ScoutPlayersResponse) {
        self.playersResponse = playersResponse
    }

    func loadPlayers(for _: ScoutPlayersCacheKey) async -> ScoutPlayersResponse? {
        playersResponse
    }

    func savePlayers(_: ScoutPlayersResponse, for _: ScoutPlayersCacheKey) async {}

    func loadLeaderboards(for _: ScoutLeaderboardsCacheKey) async -> ScoutLeaderboardsResponse? {
        leaderboardsLoadStarted = true
        leaderboardsStartWaiters.forEach { $0.resume() }
        leaderboardsStartWaiters = []
        await withCheckedContinuation { continuation in
            leaderboardsContinuation = continuation
        }
        return nil
    }

    func saveLeaderboards(_: ScoutLeaderboardsResponse, for _: ScoutLeaderboardsCacheKey) async {}

    func waitUntilLeaderboardsLoadStarts() async {
        guard !leaderboardsLoadStarted else { return }
        await withCheckedContinuation { continuation in
            leaderboardsStartWaiters.append(continuation)
        }
    }

    func releaseLeaderboardsLoad() {
        leaderboardsContinuation?.resume()
        leaderboardsContinuation = nil
    }
}

private actor BlockingPlayersScoutResponseCache: ScoutResponseCaching {
    private let playersResponse: ScoutPlayersResponse
    private var playersLoadStarted = false
    private var playersStartWaiters: [CheckedContinuation<Void, Never>] = []
    private var playersContinuation: CheckedContinuation<Void, Never>?

    init(playersResponse: ScoutPlayersResponse) {
        self.playersResponse = playersResponse
    }

    func loadPlayers(for _: ScoutPlayersCacheKey) async -> ScoutPlayersResponse? {
        playersLoadStarted = true
        playersStartWaiters.forEach { $0.resume() }
        playersStartWaiters = []
        await withCheckedContinuation { continuation in
            playersContinuation = continuation
        }
        return playersResponse
    }

    func savePlayers(_: ScoutPlayersResponse, for _: ScoutPlayersCacheKey) async {}
    func loadLeaderboards(for _: ScoutLeaderboardsCacheKey) async -> ScoutLeaderboardsResponse? { nil }
    func saveLeaderboards(_: ScoutLeaderboardsResponse, for _: ScoutLeaderboardsCacheKey) async {}

    func waitUntilPlayersLoadStarts() async {
        guard !playersLoadStarted else { return }
        await withCheckedContinuation { continuation in
            playersStartWaiters.append(continuation)
        }
    }

    func releasePlayersLoad() {
        playersContinuation?.resume()
        playersContinuation = nil
    }
}

private actor SuspendedScoutAPIClient: ScoutAPIClientProtocol {
    private let playersResponse: ScoutPlayersResponse
    private let leaderboardsResponse: ScoutLeaderboardsResponse
    private var playerRequestCount = 0
    private var leaderboardRequestCount = 0
    private var startWaiters: [CheckedContinuation<Void, Never>] = []
    private var playerStartWaiters: [CheckedContinuation<Void, Never>] = []
    private var releaseContinuations: [CheckedContinuation<Void, Never>] = []

    init(
        playersResponse: ScoutPlayersResponse,
        leaderboardsResponse: ScoutLeaderboardsResponse
    ) {
        self.playersResponse = playersResponse
        self.leaderboardsResponse = leaderboardsResponse
    }

    func fetchScoutPlayers(_: ScoutPlayersRequest) async throws -> ScoutPlayersResponse {
        playerRequestCount += 1
        playerStartWaiters.forEach { $0.resume() }
        playerStartWaiters = []
        signalBothRequestsIfNeeded()
        await suspendUntilReleased()
        return playersResponse
    }

    func fetchScoutLeaderboards(_: ScoutLeaderboardsRequest) async throws -> ScoutLeaderboardsResponse {
        leaderboardRequestCount += 1
        signalBothRequestsIfNeeded()
        await suspendUntilReleased()
        return leaderboardsResponse
    }

    func waitUntilBothRequestsStart() async {
        guard playerRequestCount == 0 || leaderboardRequestCount == 0 else { return }
        await withCheckedContinuation { continuation in
            startWaiters.append(continuation)
        }
    }

    func waitUntilPlayerRequestStarts() async {
        guard playerRequestCount == 0 else { return }
        await withCheckedContinuation { continuation in
            playerStartWaiters.append(continuation)
        }
    }

    func hasStartedLeaderboardRequest() -> Bool {
        leaderboardRequestCount > 0
    }

    func requestCounts() -> (players: Int, leaderboards: Int) {
        (playerRequestCount, leaderboardRequestCount)
    }

    func releaseRequests() {
        releaseContinuations.forEach { $0.resume() }
        releaseContinuations = []
    }

    private func suspendUntilReleased() async {
        await withCheckedContinuation { continuation in
            releaseContinuations.append(continuation)
        }
    }

    private func signalBothRequestsIfNeeded() {
        if playerRequestCount > 0, leaderboardRequestCount > 0 {
            startWaiters.forEach { $0.resume() }
            startWaiters = []
        }
    }
}

private actor RecordingScoutAPIClient: ScoutAPIClientProtocol {
    private let players: [ScoutPlayerSummary]
    private let delaySecondPage: Bool
    private var playerRequests: [ScoutPlayersRequest] = []
    private var leaderboardRequests: [ScoutLeaderboardsRequest] = []
    private var secondPageStarted = false
    private var secondPageStartWaiters: [CheckedContinuation<Void, Never>] = []
    private var secondPageResponseContinuation: CheckedContinuation<Void, Never>?

    init(players: [ScoutPlayerSummary], delaySecondPage: Bool = false) {
        self.players = players
        self.delaySecondPage = delaySecondPage
    }

    func fetchScoutPlayers(_ request: ScoutPlayersRequest) async throws -> ScoutPlayersResponse {
        playerRequests.append(request)
        if delaySecondPage, request.page == 2 {
            secondPageStarted = true
            secondPageStartWaiters.forEach { $0.resume() }
            secondPageStartWaiters = []
            await withCheckedContinuation { continuation in
                secondPageResponseContinuation = continuation
            }
        }

        let index = min(max(request.page - 1, 0), max(players.count - 1, 0))
        let pagePlayers = players.isEmpty ? [] : [players[index]]
        return ScoutPlayersResponse(
            players: pagePlayers,
            total: players.count,
            page: request.page,
            perPage: request.perPage,
            totalPages: players.count
        )
    }

    func fetchScoutLeaderboards(_ request: ScoutLeaderboardsRequest) async throws -> ScoutLeaderboardsResponse {
        leaderboardRequests.append(request)
        return ScoutLeaderboardsResponse(leaderboards: [:], limit: request.limit, phase: request.phase)
    }

    func recordedPlayerRequests() -> [ScoutPlayersRequest] {
        playerRequests
    }

    func recordedLeaderboardRequests() -> [ScoutLeaderboardsRequest] {
        leaderboardRequests
    }

    func waitUntilSecondPageStarts() async {
        guard !secondPageStarted else { return }
        await withCheckedContinuation { continuation in
            secondPageStartWaiters.append(continuation)
        }
    }

    func releaseSecondPage() {
        secondPageResponseContinuation?.resume()
        secondPageResponseContinuation = nil
    }
}
