import Combine
import Foundation

@MainActor
final class WatchlistViewModel: ObservableObject {
    @Published private(set) var entries: [WatchlistEntry] = []
    @Published private(set) var watchedPlayerIDs: Set<Int> = []
    @Published private(set) var isLoadingWatchlist = false
    @Published private(set) var isLoadingWatchedPlayerIDs = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var pendingPlayerIDs: Set<Int> = []
    @Published private(set) var digestOptIn = true
    @Published private(set) var scoutTier = "free"

    private let apiClient: any WatchlistAPIClientProtocol
    private var sessionRevision = 0

    init(apiClient: any WatchlistAPIClientProtocol = APIClient()) {
        self.apiClient = apiClient
    }

    var isLoading: Bool {
        isLoadingWatchlist || isLoadingWatchedPlayerIDs
    }

    func isWatched(playerID: Int) -> Bool {
        watchedPlayerIDs.contains(playerID)
    }

    func isPending(playerID: Int) -> Bool {
        pendingPlayerIDs.contains(playerID)
    }

    func loadWatchedPlayerIDs() async {
        let revision = sessionRevision
        isLoadingWatchedPlayerIDs = true
        errorMessage = nil

        defer {
            if revision == sessionRevision {
                isLoadingWatchedPlayerIDs = false
            }
        }

        do {
            let response = try await apiClient.fetchWatchlistIDs()
            guard revision == sessionRevision else { return }
            watchedPlayerIDs = Set(response.playerIds)
        } catch {
            guard revision == sessionRevision else { return }
            errorMessage = displayMessage(for: error)
        }
    }

    func loadWatchlist() async {
        let revision = sessionRevision
        isLoadingWatchlist = true
        errorMessage = nil

        defer {
            if revision == sessionRevision {
                isLoadingWatchlist = false
            }
        }

        do {
            let response = try await apiClient.fetchWatchlist()
            guard revision == sessionRevision else { return }
            entries = response.entries
            watchedPlayerIDs = Set(response.entries.map(\.playerApiId))
            digestOptIn = response.digestOptIn
            scoutTier = response.scoutTier
        } catch {
            guard revision == sessionRevision else { return }
            errorMessage = displayMessage(for: error)
        }
    }

    func resetForSignOut() {
        sessionRevision += 1
        entries = []
        watchedPlayerIDs = []
        isLoadingWatchlist = false
        isLoadingWatchedPlayerIDs = false
        errorMessage = nil
        pendingPlayerIDs = []
        digestOptIn = true
        scoutTier = "free"
    }

    func toggleWatchlist(playerID: Int) async {
        guard !isPending(playerID: playerID) else { return }
        if isWatched(playerID: playerID) {
            await removeFromWatchlist(playerID: playerID)
        } else {
            await addToWatchlist(playerID: playerID)
        }
    }

    func removeFromWatchlist(playerID: Int) async {
        guard !isPending(playerID: playerID) else { return }

        let revision = sessionRevision
        let snapshot = captureState(for: playerID)
        pendingPlayerIDs.insert(playerID)
        errorMessage = nil
        watchedPlayerIDs.remove(playerID)
        entries.removeAll { $0.playerApiId == playerID }

        defer {
            if revision == sessionRevision {
                pendingPlayerIDs.remove(playerID)
            }
        }

        do {
            _ = try await apiClient.removeFromWatchlist(playerID: playerID)
        } catch {
            guard revision == sessionRevision else { return }
            restore(snapshot, for: playerID)
            errorMessage = displayMessage(for: error)
        }
    }

    func updateNote(playerID: Int, note: String) async {
        guard !isPending(playerID: playerID) else { return }

        let revision = sessionRevision
        pendingPlayerIDs.insert(playerID)
        errorMessage = nil

        defer {
            if revision == sessionRevision {
                pendingPlayerIDs.remove(playerID)
            }
        }

        do {
            let response = try await apiClient.updateWatchlistNote(playerID: playerID, note: note)
            guard revision == sessionRevision else { return }
            upsert(response.entry, preferBeginning: false)
            watchedPlayerIDs.insert(playerID)
        } catch {
            guard revision == sessionRevision else { return }
            errorMessage = displayMessage(for: error)
        }
    }

    func clearError() {
        errorMessage = nil
    }

    private func addToWatchlist(playerID: Int) async {
        let revision = sessionRevision
        let snapshot = captureState(for: playerID)
        pendingPlayerIDs.insert(playerID)
        errorMessage = nil
        watchedPlayerIDs.insert(playerID)

        defer {
            if revision == sessionRevision {
                pendingPlayerIDs.remove(playerID)
            }
        }

        do {
            let response = try await apiClient.addToWatchlist(playerID: playerID)
            guard revision == sessionRevision else { return }
            watchedPlayerIDs.insert(playerID)
            upsert(response.entry, preferBeginning: true)
        } catch {
            guard revision == sessionRevision else { return }
            restore(snapshot, for: playerID)
            errorMessage = displayMessage(for: error)
        }
    }

    private func captureState(for playerID: Int) -> PlayerStateSnapshot {
        let entryIndex = entries.firstIndex { $0.playerApiId == playerID }
        return PlayerStateSnapshot(
            wasWatched: watchedPlayerIDs.contains(playerID),
            entry: entryIndex.map { entries[$0] },
            entryIndex: entryIndex
        )
    }

    private func restore(_ snapshot: PlayerStateSnapshot, for playerID: Int) {
        if snapshot.wasWatched {
            watchedPlayerIDs.insert(playerID)
        } else {
            watchedPlayerIDs.remove(playerID)
        }

        entries.removeAll { $0.playerApiId == playerID }
        if let entry = snapshot.entry {
            let index = min(max(snapshot.entryIndex ?? entries.endIndex, 0), entries.endIndex)
            entries.insert(entry, at: index)
        }
    }

    private func upsert(_ entry: WatchlistEntry, preferBeginning: Bool) {
        if let index = entries.firstIndex(where: { $0.playerApiId == entry.playerApiId }) {
            entries[index] = entry
        } else if preferBeginning {
            entries.insert(entry, at: 0)
        } else {
            entries.append(entry)
        }
    }

    private func displayMessage(for error: Error) -> String {
        (error as? LocalizedError)?.errorDescription
            ?? "We couldn't update your watchlist. Check your connection and try again."
    }
}

private struct PlayerStateSnapshot {
    let wasWatched: Bool
    let entry: WatchlistEntry?
    let entryIndex: Int?
}
