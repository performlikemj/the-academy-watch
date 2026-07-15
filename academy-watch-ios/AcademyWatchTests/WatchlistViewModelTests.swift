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

    @MainActor
    func testReadStartedBeforeSuccessfulAddCannotOverwriteNewerState() async throws {
        let fixture: WatchlistResponse = try decodeFixture(named: "watchlist_response")
        let addedEntry = try XCTUnwrap(fixture.entries.first)
        let client = DelayedWatchlistReadClient(
            staleResponse: WatchlistResponse(
                entries: [],
                digestOptIn: true,
                scoutTier: "free"
            ),
            addedEntry: addedEntry
        )
        let viewModel = WatchlistViewModel(apiClient: client)

        let loadTask = Task { @MainActor in
            await viewModel.loadWatchlist()
        }
        await client.waitUntilReadStarts()

        let didAdd = await viewModel.toggleWatchlist(playerID: addedEntry.playerApiId)
        XCTAssertTrue(didAdd)
        await client.releaseRead()
        await loadTask.value

        XCTAssertTrue(viewModel.isWatched(playerID: addedEntry.playerApiId))
        XCTAssertEqual(viewModel.entries, [addedEntry])
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

private actor DelayedWatchlistReadClient: WatchlistAPIClientProtocol {
    let staleResponse: WatchlistResponse
    let addedEntry: WatchlistEntry

    private var readStarted = false
    private var readStartWaiters: [CheckedContinuation<Void, Never>] = []
    private var readContinuation: CheckedContinuation<Void, Never>?

    init(staleResponse: WatchlistResponse, addedEntry: WatchlistEntry) {
        self.staleResponse = staleResponse
        self.addedEntry = addedEntry
    }

    func fetchWatchlist() async throws -> WatchlistResponse {
        await withCheckedContinuation { continuation in
            readContinuation = continuation
            readStarted = true
            readStartWaiters.forEach { $0.resume() }
            readStartWaiters = []
        }
        return staleResponse
    }

    func fetchWatchlistIDs() async throws -> WatchlistIDsResponse {
        WatchlistIDsResponse(playerIds: [])
    }

    func addToWatchlist(playerID _: Int) async throws -> WatchlistEntryResponse {
        WatchlistEntryResponse(entry: addedEntry)
    }

    func removeFromWatchlist(playerID _: Int) async throws -> WatchlistRemoveResponse {
        WatchlistRemoveResponse(removed: true)
    }

    func updateWatchlistNote(playerID _: Int, note _: String) async throws -> WatchlistEntryResponse {
        WatchlistEntryResponse(entry: addedEntry)
    }

    func updateWatchlistSettings(digestOptIn: Bool) async throws -> WatchlistSettingsResponse {
        WatchlistSettingsResponse(digestOptIn: digestOptIn)
    }

    func waitUntilReadStarts() async {
        if readStarted { return }
        await withCheckedContinuation { continuation in
            readStartWaiters.append(continuation)
        }
    }

    func releaseRead() {
        readContinuation?.resume()
        readContinuation = nil
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
