import Combine
import Foundation

@MainActor
final class ScoutDeskViewModel: ObservableObject {
    @Published private(set) var players: [ScoutPlayerSummary] = []
    @Published private(set) var totalPlayers = 0
    @Published private(set) var isLoadingInitial = false
    @Published private(set) var isLoadingNextPage = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var paginationErrorMessage: String?
    @Published private(set) var hasAttemptedInitialLoad = false

    private let apiClient: APIClient
    private let pageSize: Int
    private var currentPage = 0
    private var totalPages = 0
    init(apiClient: APIClient = APIClient(), pageSize: Int = 25) {
        self.apiClient = apiClient
        self.pageSize = pageSize
    }

    func loadInitialIfNeeded() async {
        guard !hasAttemptedInitialLoad else { return }
        await reload()
    }

    func reload() async {
        guard !isLoadingInitial else { return }
        isLoadingInitial = true
        errorMessage = nil
        paginationErrorMessage = nil
        defer {
            isLoadingInitial = false
            hasAttemptedInitialLoad = true
        }

        do {
            let response = try await apiClient.fetchScoutPlayers(page: 1, perPage: pageSize)
            players = response.players
            totalPlayers = response.total
            currentPage = response.page
            totalPages = response.totalPages
        } catch {
            errorMessage = displayMessage(for: error)
        }
    }

    func loadNextPageIfNeeded(currentPlayer: ScoutPlayerSummary) async {
        guard currentPlayer.playerId == players.last?.playerId else { return }
        await loadNextPage()
    }

    func retryNextPage() async {
        await loadNextPage()
    }

    private func loadNextPage() async {
        guard !isLoadingInitial,
              !isLoadingNextPage,
              currentPage > 0,
              currentPage < totalPages
        else { return }

        isLoadingNextPage = true
        paginationErrorMessage = nil
        defer { isLoadingNextPage = false }

        do {
            let response = try await apiClient.fetchScoutPlayers(
                page: currentPage + 1,
                perPage: pageSize
            )
            let existingIds = Set(players.map(\.playerId))
            players.append(contentsOf: response.players.filter { !existingIds.contains($0.playerId) })
            currentPage = response.page
            totalPages = response.totalPages
            totalPlayers = response.total
        } catch {
            paginationErrorMessage = displayMessage(for: error)
        }
    }

    private func displayMessage(for error: Error) -> String {
        (error as? LocalizedError)?.errorDescription
            ?? "We couldn't load the Scout Desk. Check your connection and try again."
    }
}
