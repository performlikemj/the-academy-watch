import XCTest
@testable import AcademyWatch

final class ScoutDeskViewModelTests: XCTestCase {
    @MainActor
    func testPhaseSwitchResetsPaginationAndAppliesDefaultSort() async throws {
        let fixture = try capturedPlayersResponse()
        let client = RecordingScoutAPIClient(players: Array(fixture.players.prefix(2)))
        let viewModel = ScoutDeskViewModel(apiClient: client, pageSize: 1)

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
        let viewModel = ScoutDeskViewModel(apiClient: client, pageSize: 1)

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
