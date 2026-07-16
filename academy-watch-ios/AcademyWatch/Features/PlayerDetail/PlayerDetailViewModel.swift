import Combine
import Foundation

enum PlayerDetailSection: CaseIterable, Hashable, Sendable {
    case profile
    case seasonStats
    case recentForm
    case journey
    case availability
}

@MainActor
final class PlayerDetailViewModel: ObservableObject {
    let playerID: Int

    @Published private(set) var profile: PlayerProfile?
    @Published private(set) var seasonStats: PlayerSeasonStats?
    @Published private(set) var recentFixtures: [PlayerRecentFixture] = []
    @Published private(set) var journey: PlayerJourneyResponse?
    @Published private(set) var availability: PlayerAvailability?
    @Published private(set) var loadingSections: Set<PlayerDetailSection> = []
    @Published private(set) var errorMessages: [PlayerDetailSection: String] = [:]
    @Published private(set) var hasAttemptedLoad = false

    private let apiClient: any PlayerDetailAPIClientProtocol
    private var loadRevision = 0
    private var activeLoadRevision: Int?
    private var activeLoadTask: Task<Void, Never>?

    init(
        playerID: Int,
        apiClient: any PlayerDetailAPIClientProtocol = APIClient()
    ) {
        self.playerID = playerID
        self.apiClient = apiClient

        #if DEBUG
        if FullCircleFixtureDestination.fromLaunchArguments(ProcessInfo.processInfo.arguments) == .introduction {
            profile = .fullCircleFixture
            hasAttemptedLoad = true
        }
        #endif
    }

    var recentMatches: [PlayerRecentFixture] {
        Array(recentFixtures.suffix(5).reversed())
    }

    var timelineEntries: [PlayerJourneyTimelineEntry] {
        journey?.timelineEntries ?? []
    }

    var visibleAvailability: PlayerAvailability? {
        guard let availability, availability.summary.totalAbsences > 0 else { return nil }
        return availability
    }

    func loadIfNeeded() async {
        guard !hasAttemptedLoad, loadingSections.isEmpty, activeLoadTask == nil else { return }
        await beginLoad(replacingExisting: false)
    }

    func reload() async {
        await beginLoad(replacingExisting: true)
    }

    func errorMessage(for section: PlayerDetailSection) -> String? {
        errorMessages[section]
    }

    func isLoading(_ section: PlayerDetailSection) -> Bool {
        loadingSections.contains(section)
    }

    func averageRating(for clubName: String) -> Double? {
        let ratings = fixtures(for: clubName).compactMap(\.rating)
        guard !ratings.isEmpty else { return nil }
        return ratings.reduce(0, +) / Double(ratings.count)
    }

    func cleanSheets(for clubName: String) -> Int? {
        guard profile?.isGoalkeeper == true else { return nil }
        let clubFixtures = fixtures(for: clubName)
        guard !clubFixtures.isEmpty else { return nil }
        return clubFixtures.filter {
            ($0.minutes ?? 0) >= 45 && $0.goalsConceded == 0
        }.count
    }

    func competitionCount(for clubName: String, season: Int?) -> Int? {
        guard let season else { return nil }
        let matching = timelineEntries.filter {
            $0.season == season
                && $0.clubName.caseInsensitiveCompare(clubName) == .orderedSame
        }
        let count = matching.reduce(0) { $0 + $1.competitionCount }
        return count > 0 ? count : nil
    }

    private func fixtures(for clubName: String) -> [PlayerRecentFixture] {
        let matching = recentFixtures.filter {
            $0.loanTeamName?.caseInsensitiveCompare(clubName) == .orderedSame
        }
        if matching.isEmpty, seasonStats?.clubs.count == 1 {
            return recentFixtures
        }
        return matching
    }

    private func beginLoad(replacingExisting: Bool) async {
        loadRevision += 1
        let revision = loadRevision

        if replacingExisting, let previousTask = activeLoadTask {
            previousTask.cancel()
            await previousTask.value
        }

        guard revision == loadRevision, !Task.isCancelled else { return }

        let task = Task { [weak self] in
            guard let self else { return }
            await self.load(revision: revision)
        }
        activeLoadRevision = revision
        activeLoadTask = task

        await withTaskCancellationHandler {
            await task.value
        } onCancel: {
            task.cancel()
        }

        if activeLoadRevision == revision {
            activeLoadRevision = nil
            activeLoadTask = nil
        }
    }

    private func load(revision: Int) async {
        let client = apiClient
        let playerID = playerID

        if !hasAttemptedLoad {
            profile = nil
            seasonStats = nil
            recentFixtures = []
            journey = nil
            availability = nil
        }
        errorMessages = [:]
        loadingSections = Set(PlayerDetailSection.allCases)

        await withTaskGroup(of: PlayerDetailLoadResult.self) { group in
            var seasonStatsScheduled = false

            group.addTask {
                do {
                    return .profile(try await client.fetchPlayerProfile(playerID: playerID))
                } catch {
                    return .failure(.profile, Self.displayMessage(for: error))
                }
            }
            group.addTask {
                do {
                    return .recentForm(try await client.fetchPlayerRecentFixtures(playerID: playerID))
                } catch {
                    return .failure(.recentForm, Self.displayMessage(for: error))
                }
            }
            group.addTask {
                do {
                    return .journey(try await client.fetchPlayerJourney(playerID: playerID))
                } catch {
                    return .failure(.journey, Self.displayMessage(for: error))
                }
            }
            group.addTask {
                do {
                    return .availability(try await client.fetchPlayerAvailability(playerID: playerID))
                } catch {
                    return .failure(.availability, Self.displayMessage(for: error))
                }
            }

            for await result in group {
                guard revision == loadRevision, !Task.isCancelled else {
                    group.cancelAll()
                    if revision == loadRevision {
                        loadingSections = []
                    }
                    return
                }
                apply(result)

                // `/stats` can hydrate fixture rows as part of its read. Fetch
                // season totals only after that request finishes so both
                // sections reflect the same match-level snapshot.
                if result.section == .recentForm, !seasonStatsScheduled {
                    seasonStatsScheduled = true
                    group.addTask {
                        do {
                            return .seasonStats(
                                try await client.fetchPlayerSeasonStats(playerID: playerID)
                            )
                        } catch {
                            return .failure(.seasonStats, Self.displayMessage(for: error))
                        }
                    }
                }
            }
        }

        guard revision == loadRevision, !Task.isCancelled else {
            if revision == loadRevision {
                loadingSections = []
            }
            return
        }
        hasAttemptedLoad = true
    }

    private func apply(_ result: PlayerDetailLoadResult) {
        switch result {
        case let .profile(value):
            profile = value
            loadingSections.remove(.profile)
        case let .seasonStats(value):
            seasonStats = value
            loadingSections.remove(.seasonStats)
        case let .recentForm(value):
            recentFixtures = value
            loadingSections.remove(.recentForm)
        case let .journey(value):
            journey = value
            loadingSections.remove(.journey)
        case let .availability(value):
            availability = value
            loadingSections.remove(.availability)
        case let .failure(section, message):
            loadingSections.remove(section)
            if let message {
                errorMessages[section] = message
            }
        }
    }

    nonisolated private static func displayMessage(for error: Error) -> String? {
        if error is CancellationError || (error as? URLError)?.code == .cancelled {
            return nil
        }
        return (error as? LocalizedError)?.errorDescription
            ?? "We couldn't load this player data. Check your connection and try again."
    }
}

private enum PlayerDetailLoadResult: Sendable {
    case profile(PlayerProfile)
    case seasonStats(PlayerSeasonStats)
    case recentForm([PlayerRecentFixture])
    case journey(PlayerJourneyResponse)
    case availability(PlayerAvailability)
    case failure(PlayerDetailSection, String?)

    var section: PlayerDetailSection {
        switch self {
        case .profile: .profile
        case .seasonStats: .seasonStats
        case .recentForm: .recentForm
        case .journey: .journey
        case .availability: .availability
        case let .failure(section, _): section
        }
    }
}
