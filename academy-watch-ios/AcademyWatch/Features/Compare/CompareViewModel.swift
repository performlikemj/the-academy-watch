import Combine
import Foundation

protocol CompareAPIClientProtocol: Sendable {
    func fetchComparison(
        playerIDs: [Int],
        includeAvailability: Bool
    ) async throws -> CompareResponse
}

@MainActor
final class CompareViewModel: ObservableObject {
    let playerIDs: [Int]

    @Published private(set) var players: [ComparePlayer] = []
    @Published private(set) var missingPlayerIDs: [Int] = []
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?

    private let apiClient: any CompareAPIClientProtocol

    init(
        playerIDs: [Int],
        apiClient: any CompareAPIClientProtocol = APIClient()
    ) {
        self.playerIDs = playerIDs
        self.apiClient = apiClient
    }

    func load() async {
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let response = try await apiClient.fetchComparison(
                playerIDs: playerIDs,
                includeAvailability: true
            )
            players = response.players
            missingPlayerIDs = response.missingIds
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription
                ?? "We couldn't compare these players. Check your connection and try again."
        }
    }
}
