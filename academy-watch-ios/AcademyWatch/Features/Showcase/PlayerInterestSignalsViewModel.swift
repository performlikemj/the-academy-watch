import Combine
import Foundation

struct PlayerInterestSignalsPresentation: Equatable, Sendable {
    struct Metric: Equatable, Identifiable, Sendable {
        enum Kind: String, Equatable, Sendable {
            case watchlists
            case follows

            var title: String {
                switch self {
                case .watchlists:
                    return "Watchlists"
                case .follows:
                    return "Follows"
                }
            }

            var systemImage: String {
                switch self {
                case .watchlists:
                    return "star.fill"
                case .follows:
                    return "person.2.fill"
                }
            }

            func unit(for count: Int) -> String {
                switch self {
                case .watchlists:
                    return count == 1 ? "watchlist" : "watchlists"
                case .follows:
                    return count == 1 ? "follow" : "follows"
                }
            }
        }

        let kind: Kind
        let total: Int
        let addedThisWeek: Int

        var id: Kind { kind }
        var title: String { kind.title }
        var systemImage: String { kind.systemImage }
        var totalUnit: String { kind.unit(for: total) }

        var emptyTotalText: String {
            switch kind {
            case .watchlists:
                return "No watchlist saves yet"
            case .follows:
                return "No follows yet"
            }
        }

        var weeklyActivityText: String {
            guard addedThisWeek > 0 else { return "No new this week" }
            return "+\(addedThisWeek) this week"
        }
    }

    let metrics: [Metric]
    let title: String
    let message: String

    var isZeroState: Bool {
        metrics.isEmpty
    }

    var hasNewInterestThisWeek: Bool {
        metrics.contains { $0.addedThisWeek > 0 }
    }

    init(signal: PlayerInterestSignal) {
        if signal.watchlists.total == 0, signal.follows.total == 0 {
            metrics = []
        } else {
            metrics = [
                Metric(
                    kind: .watchlists,
                    total: signal.watchlists.total,
                    addedThisWeek: signal.watchlists.addedThisWeek
                ),
                Metric(
                    kind: .follows,
                    total: signal.follows.total,
                    addedThisWeek: signal.follows.addedThisWeek
                ),
            ]
        }

        if metrics.isEmpty {
            title = "Your profile is ready to be seen"
            message = "No scout saves yet. Keep your profile fresh — the first one can arrive any time."
        } else if metrics.contains(where: { $0.addedThisWeek > 0 }) {
            title = "Scouts are watching you"
            message = "Your profile picked up new interest this week."
        } else {
            title = "Scouts are watching you"
            message = "No new saves this week, but scouts still have you on their radar."
        }
    }
}

@MainActor
final class PlayerInterestSignalsViewModel: ObservableObject {
    let playerID: Int
    let availability: ContactFeatureAvailability

    @Published private(set) var signal: PlayerInterestSignal?
    @Published private(set) var isLoading = false
    @Published private(set) var hasLoaded = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var isFixturePreview = false

    private let apiClient: any InterestSignalsAPIClientProtocol
    private var loadRevision = 0
    private var activeLoadTask: Task<Void, Never>?

    init(
        playerID: Int,
        apiClient: any InterestSignalsAPIClientProtocol = APIClient(),
        availability: ContactFeatureAvailability? = nil
    ) {
        self.playerID = playerID
        self.apiClient = apiClient
        self.availability = availability ?? .shared

        #if DEBUG
        if FullCircleFixtureDestination.fromLaunchArguments(ProcessInfo.processInfo.arguments) == .watchingYou {
            signal = Self.watchingYouFixture(playerID: playerID)
            hasLoaded = true
            isFixturePreview = true
            self.availability.recordSuccess()
        }
        #endif
    }

    var presentation: PlayerInterestSignalsPresentation? {
        signal.map(PlayerInterestSignalsPresentation.init(signal:))
    }

    var isCardVisible: Bool {
        guard !availability.isUnavailable else { return false }
        return !hasLoaded || signal != nil || errorMessage != nil
    }

    func loadIfNeeded() async {
        guard !hasLoaded, !isFixturePreview else { return }
        await reload()
    }

    func refresh() async {
        await reload()
    }

    func retry() async {
        await reload()
    }

    func reload() async {
        guard !isFixturePreview, !availability.isUnavailable else { return }

        loadRevision += 1
        let revision = loadRevision
        activeLoadTask?.cancel()

        let task = Task { [weak self] in
            guard let self else { return }
            await self.performLoad(revision: revision)
        }
        activeLoadTask = task
        await withTaskCancellationHandler {
            await task.value
        } onCancel: {
            task.cancel()
        }
        if revision == loadRevision {
            activeLoadTask = nil
        }
    }

    private func performLoad(revision: Int) async {
        isLoading = true
        errorMessage = nil
        defer {
            if revision == loadRevision {
                isLoading = false
            }
        }

        do {
            let response = try await apiClient.fetchMyInterestSignals()
            guard revision == loadRevision, !Task.isCancelled else { return }
            availability.recordSuccess()
            signal = response.interestSignals.first { $0.playerApiId == playerID }
            hasLoaded = true
        } catch {
            guard revision == loadRevision, !Self.isCancellation(error) else { return }
            hasLoaded = true
            if availability.recordFailure(error) {
                signal = nil
                errorMessage = nil
            } else {
                errorMessage = Self.displayMessage(for: error)
            }
        }
    }

    private static func isCancellation(_ error: Error) -> Bool {
        error is CancellationError || (error as? URLError)?.code == .cancelled
    }

    private static func displayMessage(for error: Error) -> String {
        if let urlError = error as? URLError,
           urlError.code == .notConnectedToInternet || urlError.code == .networkConnectionLost {
            return "You’re offline. Reconnect and try again."
        }
        return "We couldn’t refresh your scout interest. Please try again."
    }

    #if DEBUG
    private static func watchingYouFixture(playerID: Int) -> PlayerInterestSignal {
        PlayerInterestSignal(
            playerApiId: playerID,
            watchlists: InterestSignalMetric(total: 12, addedThisWeek: 3),
            follows: InterestSignalMetric(total: 5, addedThisWeek: 1)
        )
    }
    #endif
}
