import XCTest
@testable import AcademyWatch

final class WatchlistViewModelTests: XCTestCase {
    @MainActor
    func testLoadsWatchlistAndCompletesOptimisticRemoval() async throws {
        let watchlist: WatchlistResponse = try decodeFixture(named: "watchlist_response")
        let ids: WatchlistIDsResponse = try decodeFixture(named: "watchlist_ids")
        let client = StubWatchlistAPIClient(watchlist: watchlist, ids: ids)
        let viewModel = WatchlistViewModel(apiClient: client)

        await viewModel.loadWatchedPlayerIDs()
        XCTAssertEqual(viewModel.watchedPlayerIDs, Set([386_828, 999_999]))

        await viewModel.loadWatchlist()
        XCTAssertEqual(viewModel.entries, watchlist.entries)
        XCTAssertEqual(viewModel.digestOptIn, watchlist.digestOptIn)
        XCTAssertEqual(viewModel.scoutTier, watchlist.scoutTier)

        await viewModel.toggleWatchlist(playerID: 386_828)

        XCTAssertFalse(viewModel.isWatched(playerID: 386_828))
        XCTAssertEqual(viewModel.entries.map(\.playerApiId), [999_999])
        XCTAssertTrue(viewModel.pendingPlayerIDs.isEmpty)
        XCTAssertFalse(viewModel.isLoading)
        XCTAssertNil(viewModel.errorMessage)

        viewModel.resetForSignOut()
        XCTAssertTrue(viewModel.entries.isEmpty)
        XCTAssertTrue(viewModel.watchedPlayerIDs.isEmpty)
    }

    private func decodeFixture<Response: Decodable>(named name: String) throws -> Response {
        let fixtureURL = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: name, withExtension: "json")
        )
        let data = try Data(contentsOf: fixtureURL)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Response.self, from: data)
    }
}

private struct StubWatchlistAPIClient: WatchlistAPIClientProtocol {
    let watchlist: WatchlistResponse
    let ids: WatchlistIDsResponse

    func fetchWatchlist() async throws -> WatchlistResponse {
        watchlist
    }

    func fetchWatchlistIDs() async throws -> WatchlistIDsResponse {
        ids
    }

    func addToWatchlist(playerID: Int) async throws -> WatchlistEntryResponse {
        WatchlistEntryResponse(entry: watchlist.entries[0])
    }

    func removeFromWatchlist(playerID: Int) async throws -> WatchlistRemoveResponse {
        WatchlistRemoveResponse(removed: true)
    }

    func updateWatchlistNote(playerID: Int, note: String) async throws -> WatchlistEntryResponse {
        WatchlistEntryResponse(entry: watchlist.entries[0])
    }

    func updateWatchlistSettings(digestOptIn: Bool) async throws -> WatchlistSettingsResponse {
        WatchlistSettingsResponse(digestOptIn: digestOptIn)
    }
}
