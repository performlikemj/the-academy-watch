import Combine
import Foundation

@MainActor
final class ScoutDeskViewModel: ObservableObject {
    @Published private(set) var players: [ScoutPlayerSummary] = []
    @Published private(set) var leaderboards: [String: [ScoutPlayerSummary]] = [:]
    @Published private(set) var totalPlayers = 0
    @Published private(set) var isLoadingInitial = false
    @Published private(set) var isLoadingNextPage = false
    @Published private(set) var isLoadingLeaderboards = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var paginationErrorMessage: String?
    @Published private(set) var leaderboardsErrorMessage: String?
    @Published private(set) var hasAttemptedInitialLoad = false

    @Published private(set) var selectedPhase: ScoutPhase
    @Published private(set) var selectedAgePreset: ScoutAgePreset = .all
    @Published private(set) var selectedStatus: ScoutStatusFilter = .all
    @Published private(set) var selectedSortKey: String
    @Published private(set) var selectedSortOrder: ScoutSortOrder
    @Published private(set) var searchText = ""

    private let apiClient: any ScoutAPIClientProtocol
    private let pageSize: Int
    private var appliedSearch = ""
    private var listRevision = 0
    private var leaderboardsRevision = 0
    private var searchDebounceTask: Task<Void, Never>?
    private var playersReloadTask: Task<Void, Never>?
    private var paginationTask: Task<Void, Never>?
    private var leaderboardsTask: Task<Void, Never>?

    private(set) var currentPage = 0
    private(set) var totalPages = 0

    init(
        apiClient: any ScoutAPIClientProtocol = APIClient(),
        pageSize: Int = 25,
        initialPhase: ScoutPhase = .all
    ) {
        self.apiClient = apiClient
        self.pageSize = pageSize
        selectedPhase = initialPhase
        selectedSortKey = initialPhase.defaultSortKey
        selectedSortOrder = ScoutSortOrder.defaultOrder(for: initialPhase.defaultSortKey)
    }

    deinit {
        searchDebounceTask?.cancel()
        playersReloadTask?.cancel()
        paginationTask?.cancel()
        leaderboardsTask?.cancel()
    }

    var selectedSortLabel: String {
        selectedPhase.sortOptions.first(where: { $0.key == selectedSortKey })?.label
            ?? "Sort"
    }

    func loadInitialIfNeeded() async {
        guard !hasAttemptedInitialLoad else { return }
        let work = scheduleFullReload()
        await finishFullReload(work)
    }

    func reload() async {
        let work = scheduleFullReload()
        await finishFullReload(work)
    }

    func selectPhase(_ phase: ScoutPhase) async {
        guard selectedPhase != phase else { return }
        selectedPhase = phase
        selectedSortKey = phase.defaultSortKey
        selectedSortOrder = ScoutSortOrder.defaultOrder(for: phase.defaultSortKey)
        let work = scheduleFullReload()
        await finishFullReload(work)
    }

    func selectAgePreset(_ preset: ScoutAgePreset) async {
        guard selectedAgePreset != preset else { return }
        selectedAgePreset = preset
        let work = scheduleFullReload()
        await finishFullReload(work)
    }

    func selectStatus(_ status: ScoutStatusFilter) async {
        guard selectedStatus != status else { return }
        selectedStatus = status
        let work = scheduleFullReload()
        await finishFullReload(work)
    }

    func selectSort(_ option: ScoutSortOption) async {
        guard selectedPhase.sortOptions.contains(option), selectedSortKey != option.key else { return }
        selectedSortKey = option.key
        selectedSortOrder = ScoutSortOrder.defaultOrder(for: option.key)
        let work = scheduleFullReload()
        await finishFullReload(work)
    }

    func setSearchText(_ value: String) {
        searchText = value
        searchDebounceTask?.cancel()

        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalized != appliedSearch else { return }

        searchDebounceTask = Task { [weak self] in
            do {
                try await Task.sleep(nanoseconds: 300_000_000)
            } catch {
                return
            }
            guard !Task.isCancelled, let self else { return }
            await self.applySearch(normalized)
        }
    }

    func loadNextPageIfNeeded(currentPlayer: ScoutPlayerSummary) async {
        guard currentPlayer.playerId == players.last?.playerId else { return }
        await loadNextPage()
    }

    func retryNextPage() async {
        await loadNextPage()
    }

    func retryLeaderboards() async {
        let work = scheduleLeaderboardsReload()
        await work.task.value
        if work.revision == leaderboardsRevision {
            leaderboardsTask = nil
        }
    }

    private func applySearch(_ search: String) async {
        guard appliedSearch != search else { return }
        appliedSearch = search
        let work = scheduleFullReload()
        await finishFullReload(work)
    }

    private func scheduleFullReload() -> FullReloadWork {
        let list = schedulePlayersReload()
        let boards = scheduleLeaderboardsReload()
        return FullReloadWork(list: list, boards: boards)
    }

    private func finishFullReload(_ work: FullReloadWork) async {
        // Both tasks are already scheduled, so these awaits preserve parallel
        // list/board loading while the synchronous setup above stays atomic.
        await work.list.task.value
        await work.boards.task.value

        if work.list.revision == listRevision {
            playersReloadTask = nil
        }
        if work.boards.revision == leaderboardsRevision {
            leaderboardsTask = nil
        }
    }

    private func schedulePlayersReload() -> RequestWork {
        playersReloadTask?.cancel()
        paginationTask?.cancel()
        listRevision += 1
        let revision = listRevision

        currentPage = 0
        totalPages = 0
        totalPlayers = 0
        players = []
        isLoadingInitial = true
        isLoadingNextPage = false
        errorMessage = nil
        paginationErrorMessage = nil

        let context = PlayersReloadContext(
            revision: revision,
            request: makePlayersRequest(page: 1)
        )
        let task = Task { [weak self] in
            guard let self else { return }
            await self.performPlayersReload(context)
        }
        playersReloadTask = task
        return RequestWork(revision: revision, task: task)
    }

    private func performPlayersReload(_ context: PlayersReloadContext) async {
        do {
            let response = try await apiClient.fetchScoutPlayers(context.request)
            guard context.revision == listRevision else { return }
            players = response.players
            totalPlayers = response.total
            currentPage = response.page
            totalPages = response.totalPages
        } catch {
            guard context.revision == listRevision else { return }
            if isCancellation(error) {
                isLoadingInitial = false
                return
            }
            errorMessage = displayMessage(for: error)
        }

        guard context.revision == listRevision else { return }
        isLoadingInitial = false
        hasAttemptedInitialLoad = true
    }

    private func scheduleLeaderboardsReload() -> RequestWork {
        leaderboardsTask?.cancel()
        leaderboardsRevision += 1
        let revision = leaderboardsRevision

        leaderboards = [:]
        leaderboardsErrorMessage = nil
        isLoadingLeaderboards = true

        let context = LeaderboardsReloadContext(
            revision: revision,
            request: makeLeaderboardsRequest()
        )
        let task = Task { [weak self] in
            guard let self else { return }
            await self.performLeaderboardsReload(context)
        }
        leaderboardsTask = task
        return RequestWork(revision: revision, task: task)
    }

    private func performLeaderboardsReload(_ context: LeaderboardsReloadContext) async {
        do {
            let response = try await apiClient.fetchScoutLeaderboards(context.request)
            guard context.revision == leaderboardsRevision else { return }
            leaderboards = response.leaderboards
        } catch {
            guard context.revision == leaderboardsRevision else { return }
            if isCancellation(error) {
                isLoadingLeaderboards = false
                return
            }
            leaderboardsErrorMessage = displayMessage(for: error)
        }

        guard context.revision == leaderboardsRevision else { return }
        isLoadingLeaderboards = false
    }

    private func loadNextPage() async {
        guard !isLoadingInitial,
              !isLoadingNextPage,
              currentPage > 0,
              currentPage < totalPages
        else { return }

        paginationTask?.cancel()
        let context = PageLoadContext(
            revision: listRevision,
            request: makePlayersRequest(page: currentPage + 1)
        )
        isLoadingNextPage = true
        paginationErrorMessage = nil

        let task = Task { [weak self] in
            guard let self else { return }
            await self.performNextPageLoad(context)
        }
        paginationTask = task
        await task.value

        if context.revision == listRevision {
            paginationTask = nil
        }
    }

    private func performNextPageLoad(_ context: PageLoadContext) async {
        do {
            let response = try await apiClient.fetchScoutPlayers(context.request)
            guard context.revision == listRevision else { return }
            let existingIds = Set(players.map(\.playerId))
            players.append(contentsOf: response.players.filter { !existingIds.contains($0.playerId) })
            currentPage = response.page
            totalPages = response.totalPages
            totalPlayers = response.total
        } catch {
            guard context.revision == listRevision else { return }
            if isCancellation(error) {
                isLoadingNextPage = false
                return
            }
            paginationErrorMessage = displayMessage(for: error)
        }

        guard context.revision == listRevision else { return }
        isLoadingNextPage = false
    }

    private func makePlayersRequest(page: Int) -> ScoutPlayersRequest {
        ScoutPlayersRequest(
            page: page,
            perPage: pageSize,
            search: appliedSearch.isEmpty ? nil : appliedSearch,
            position: selectedPhase.position,
            status: selectedStatus.queryValue,
            maximumAge: selectedAgePreset.maximumAge,
            sort: selectedSortKey,
            order: selectedSortOrder
        )
    }

    private func makeLeaderboardsRequest() -> ScoutLeaderboardsRequest {
        ScoutLeaderboardsRequest(
            phase: selectedPhase,
            limit: 5,
            position: selectedPhase.position,
            status: selectedStatus.queryValue,
            maximumAge: selectedAgePreset.maximumAge
        )
    }

    private func isCancellation(_ error: Error) -> Bool {
        error is CancellationError || (error as? URLError)?.code == .cancelled
    }

    private func displayMessage(for error: Error) -> String {
        (error as? LocalizedError)?.errorDescription
            ?? "We couldn't load the Scout Desk. Check your connection and try again."
    }
}

private struct RequestWork {
    let revision: Int
    let task: Task<Void, Never>
}

private struct FullReloadWork {
    let list: RequestWork
    let boards: RequestWork
}

private struct PlayersReloadContext: Sendable {
    let revision: Int
    let request: ScoutPlayersRequest
}

private struct LeaderboardsReloadContext: Sendable {
    let revision: Int
    let request: ScoutLeaderboardsRequest
}

private struct PageLoadContext: Sendable {
    let revision: Int
    let request: ScoutPlayersRequest
}
