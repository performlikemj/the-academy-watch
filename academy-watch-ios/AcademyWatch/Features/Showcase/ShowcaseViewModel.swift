import Combine
import Foundation

@MainActor
final class ShowcaseViewModel: ObservableObject {
    let playerID: Int

    @Published private(set) var showcase: PlayerShowcaseResponse?
    @Published private(set) var isLoading = false
    @Published private(set) var hasAttemptedLoad = false
    @Published private(set) var isFixturePreview = false

    private let apiClient: any ShowcaseAPIClientProtocol
    private var loadRevision = 0

    init(
        playerID: Int,
        apiClient: any ShowcaseAPIClientProtocol = APIClient()
    ) {
        self.playerID = playerID
        self.apiClient = apiClient

        #if DEBUG
        let fixtureDestination = FullCircleFixtureDestination.fromLaunchArguments(
            ProcessInfo.processInfo.arguments
        )
        if ProcessInfo.processInfo.arguments.contains("-showcaseFixture")
            || fixtureDestination == .introduction
            || fixtureDestination == .attestationWarning
            || fixtureDestination == .watchingYou
            || fixtureDestination == .claimGate
            || fixtureDestination == .takedown {
            showcase = .debugFixture
            hasAttemptedLoad = true
            isFixturePreview = true
        }
        #endif
    }

    var visibleShowcase: PlayerShowcaseResponse? {
        guard let showcase, showcase.hasContent else { return nil }
        return showcase
    }

    /// The showcase differs by reader (the server adds the agent's email only
    /// for signed-in readers; owners get more), so nothing loaded for one
    /// account is kept for the next, and a late answer for it is discarded.
    func resetAccount() {
        guard !isFixturePreview else { return }
        loadRevision += 1
        showcase = nil
        hasAttemptedLoad = false
        isLoading = false
    }

    func loadIfNeeded() async {
        guard !hasAttemptedLoad, !isLoading else { return }
        await load()
    }

    func reload() async {
        guard !isFixturePreview else { return }
        await load()
    }

    private func load() async {
        loadRevision += 1
        let revision = loadRevision
        isLoading = true

        do {
            let response = try await apiClient.fetchPlayerShowcase(playerID: playerID)
            guard revision == loadRevision else { return }
            guard !Task.isCancelled else {
                isLoading = false
                return
            }
            // Keep the full serializer even when there is no visible reel or
            // profile copy: `claim_status` independently gates the contact CTA.
            showcase = response
            hasAttemptedLoad = true
            isLoading = false
        } catch {
            guard revision == loadRevision else { return }
            isLoading = false
            if error is CancellationError || (error as? URLError)?.code == .cancelled {
                return
            }
            // Showcase is additive. A failure must never break player detail,
            // and a refresh failure preserves the last known public content.
            hasAttemptedLoad = true
        }
    }
}
