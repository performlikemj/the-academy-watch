import Combine
import Foundation

/// The match lines read for one player and one account.
///
/// A failed read is never an empty season: `failed` is set, the last good
/// answer for the SAME account stays on screen, and `retry()` asks again.
/// `resetAccount()` drops everything the moment the account changes, and a
/// late answer for the previous account is discarded.
@MainActor
final class PlayerMatchLinesViewModel: ObservableObject {
    let playerID: Int

    @Published private(set) var seasons: [PlayerMatchLineSeason] = []
    @Published private(set) var truncated = false
    /// A good answer for the current account is held (it may be empty).
    @Published private(set) var hasLines = false
    @Published private(set) var isLoading = false
    /// The latest read failed. With `hasLines` the last good data is still shown.
    @Published private(set) var failed = false

    private let apiClient: any PlayerMatchLinesAPIClientProtocol
    private var revision = 0

    init(playerID: Int, apiClient: any PlayerMatchLinesAPIClientProtocol = APIClient()) {
        self.playerID = playerID
        self.apiClient = apiClient
    }

    /// Nothing to show yet and no answer yet.
    var isAwaitingFirstAnswer: Bool { !hasLines && !failed }

    func resetAccount() {
        revision += 1
        seasons = []
        truncated = false
        hasLines = false
        isLoading = false
        failed = false
    }

    func retry() async {
        await load()
    }

    func load() async {
        revision += 1
        let request = revision
        isLoading = true
        failed = false
        do {
            let response = try await apiClient.fetchPlayerMatchLines(playerID: playerID)
            guard request == revision else { return }
            accept(response)
        } catch {
            guard request == revision else { return }
            isLoading = false
            if error is CancellationError || (error as? URLError)?.code == .cancelled { return }
            // 404 is the route's answer for "no match entries to show for this
            // identity": an empty result, not a failure.
            if Self.statusCode(of: error) == 404 {
                accept(.empty)
            } else {
                failed = true
            }
        }
    }

    private func accept(_ response: PlayerMatchLinesResponse) {
        seasons = response.seasons
        truncated = response.truncated
        hasLines = true
        isLoading = false
        failed = false
    }

    nonisolated static func statusCode(of error: Error) -> Int? {
        switch error as? APIClientError {
        case let .httpStatus(code): code
        case let .server(code, _): code
        case let .codedServer(code, _, _, _): code
        default: nil
        }
    }
}
