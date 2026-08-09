import Combine
import Foundation

protocol CompareAPIClientProtocol: Sendable {
    func fetchComparison(
        playerIDs: [Int],
        includeAvailability: Bool
    ) async throws -> CompareResponse
    func fetchComparison(
        playerIDs: [Int],
        includeAvailability: Bool,
        season: Int?
    ) async throws -> CompareResponse
}

extension CompareAPIClientProtocol {
    func fetchComparison(
        playerIDs: [Int],
        includeAvailability: Bool,
        season _: Int?
    ) async throws -> CompareResponse {
        try await fetchComparison(
            playerIDs: playerIDs,
            includeAvailability: includeAvailability
        )
    }
}

@MainActor
final class CompareViewModel: ObservableObject {
    let playerIDs: [Int]
    let selectedSeason: Int?

    @Published private(set) var players: [ComparePlayer] = []
    @Published private(set) var missingPlayerIDs: [Int] = []
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var resolvedSeason: Int?

    private let apiClient: any CompareAPIClientProtocol

    init(
        playerIDs: [Int],
        season: Int? = nil,
        apiClient: any CompareAPIClientProtocol = APIClient()
    ) {
        self.playerIDs = playerIDs
        selectedSeason = season
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
                includeAvailability: true,
                season: selectedSeason
            )
            players = response.players
            missingPlayerIDs = response.missingIds
            resolvedSeason = response.season ?? selectedSeason
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription
                ?? "We couldn't compare these players. Check your connection and try again."
        }
    }

    var resolvedSeasonLabel: String {
        resolvedSeason.map(SeasonLabelFormatter.label(for:)) ?? "Season"
    }
}
