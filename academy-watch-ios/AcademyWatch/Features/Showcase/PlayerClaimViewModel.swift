import Combine
import Foundation

@MainActor
final class PlayerClaimViewModel: ObservableObject {
    let playerID: Int

    @Published private(set) var claim: PlayerProfileClaim?
    @Published private(set) var isLoading = false
    @Published private(set) var isSubmitting = false
    @Published private(set) var hasLoaded = false
    @Published private(set) var errorMessage: String?

    private let apiClient: any PlayerClaimAPIClientProtocol
    private var revision = 0

    init(
        playerID: Int,
        apiClient: any PlayerClaimAPIClientProtocol = APIClient()
    ) {
        self.playerID = playerID
        self.apiClient = apiClient

        #if DEBUG
        if FullCircleFixtureDestination.fromLaunchArguments(
            ProcessInfo.processInfo.arguments
        ) == .watchingYou {
            claim = PlayerProfileClaim(
                id: 77,
                playerApiId: playerID,
                userAccountId: 91,
                relationshipType: "player",
                status: .approved,
                message: nil,
                reviewedBy: "fixture-admin",
                reviewedAt: "2026-07-15T11:00:00",
                createdAt: "2026-07-14T09:00:00",
                playerName: "Habeeb Amass"
            )
            hasLoaded = true
        }
        #endif
    }

    func load(isAuthenticated: Bool) async {
        guard isAuthenticated else {
            resetForSignOut()
            return
        }
        #if DEBUG
        if FullCircleFixtureDestination.fromLaunchArguments(
            ProcessInfo.processInfo.arguments
        ) == .watchingYou {
            return
        }
        #endif
        guard !isLoading, !isSubmitting else { return }

        revision += 1
        let requestRevision = revision
        isLoading = true
        errorMessage = nil

        do {
            let response = try await apiClient.fetchMyProfileClaims()
            guard requestRevision == revision else { return }
            guard !Task.isCancelled else {
                isLoading = false
                return
            }
            claim = response.claims.first { $0.playerApiId == playerID }
            hasLoaded = true
            isLoading = false
        } catch {
            guard requestRevision == revision else { return }
            isLoading = false
            if error is CancellationError || (error as? URLError)?.code == .cancelled {
                return
            }
            hasLoaded = true
            errorMessage = error.localizedDescription
        }
    }

    func submitThisIsMe() async {
        guard !isSubmitting, !isLoading else { return }

        revision += 1
        let requestRevision = revision
        isSubmitting = true
        errorMessage = nil

        do {
            let response = try await apiClient.submitPlayerClaim(playerID: playerID)
            guard requestRevision == revision else { return }
            guard !Task.isCancelled else {
                isSubmitting = false
                return
            }
            claim = response.claim
            hasLoaded = true
            isSubmitting = false
        } catch {
            guard requestRevision == revision else { return }
            isSubmitting = false
            if error is CancellationError || (error as? URLError)?.code == .cancelled {
                return
            }
            errorMessage = error.localizedDescription
        }
    }

    private func resetForSignOut() {
        revision += 1
        claim = nil
        isLoading = false
        isSubmitting = false
        hasLoaded = false
        errorMessage = nil
    }
}
