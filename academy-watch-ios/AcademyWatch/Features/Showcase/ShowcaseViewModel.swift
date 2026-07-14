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
        if ProcessInfo.processInfo.arguments.contains("-showcaseFixture") {
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
            showcase = response.hasContent ? response : nil
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
