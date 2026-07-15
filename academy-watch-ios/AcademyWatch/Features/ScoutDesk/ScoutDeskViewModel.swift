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
    @Published private(set) var isShowingCachedPlayers = false
    @Published private(set) var isShowingCachedLeaderboards = false

    @Published private(set) var selectedPhase: ScoutPhase
    @Published private(set) var selectedAgePreset: ScoutAgePreset = .all
    @Published private(set) var selectedStatus: ScoutStatusFilter = .all
    @Published private(set) var selectedSortKey: String
    @Published private(set) var selectedSortOrder: ScoutSortOrder
    @Published private(set) var searchText = ""

    private let apiClient: any ScoutAPIClientProtocol
    private let responseCache: any ScoutResponseCaching
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
    private(set) var firstRowDataSource = "network"

    init(
        apiClient: any ScoutAPIClientProtocol = APIClient(),
        responseCache: any ScoutResponseCaching = ScoutResponseCache.shared,
        pageSize: Int = 25,
        initialPhase: ScoutPhase = .all
    ) {
        self.apiClient = apiClient
        self.responseCache = responseCache
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

    var isUpdatingCachedData: Bool {
        isUpdatingCachedPlayers || isUpdatingCachedLeaderboards
    }

    var isUpdatingCachedPlayers: Bool {
        isShowingCachedPlayers && isLoadingInitial
    }

    var isUpdatingCachedLeaderboards: Bool {
        isShowingCachedLeaderboards && isLoadingLeaderboards
    }

    func loadInitialIfNeeded() async {
        guard !hasAttemptedInitialLoad else { return }
        hasAttemptedInitialLoad = true
        await reloadFullUsingCache()
    }

    func reload() async {
        let work = scheduleFullReload(
            preservingPlayers: !players.isEmpty,
            preservingLeaderboards: !leaderboards.isEmpty
        )
        await finishFullReload(work)
    }

    func selectPhase(_ phase: ScoutPhase) async {
        guard selectedPhase != phase else { return }
        selectedPhase = phase
        selectedSortKey = phase.defaultSortKey
        selectedSortOrder = ScoutSortOrder.defaultOrder(for: phase.defaultSortKey)
        await reloadFullUsingCache()
    }

    func selectAgePreset(_ preset: ScoutAgePreset) async {
        guard selectedAgePreset != preset else { return }
        selectedAgePreset = preset
        await reloadFullUsingCache()
    }

    func selectStatus(_ status: ScoutStatusFilter) async {
        guard selectedStatus != status else { return }
        selectedStatus = status
        await reloadFullUsingCache()
    }

    func selectSort(_ option: ScoutSortOption) async {
        guard selectedPhase.sortOptions.contains(option), selectedSortKey != option.key else { return }
        selectedSortKey = option.key
        selectedSortOrder = ScoutSortOrder.defaultOrder(for: option.key)
        await reloadPlayersUsingCache()
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
        let work = scheduleLeaderboardsReload(preservingCurrentData: !leaderboards.isEmpty)
        await work.task.value
        if work.revision == leaderboardsRevision {
            leaderboardsTask = nil
        }
    }

    private func applySearch(_ search: String) async {
        guard appliedSearch != search else { return }
        appliedSearch = search
        await reloadPlayersUsingCache()
    }

    private func reloadFullUsingCache() async {
        let playersRequest = makePlayersRequest(page: 1)
        let leaderboardsRequest = makeLeaderboardsRequest()
        let playersKey = ScoutPlayersCacheKey(phase: selectedPhase, request: playersRequest)
        let leaderboardsKey = ScoutLeaderboardsCacheKey(
            phase: selectedPhase,
            request: leaderboardsRequest
        )

        prepareForCacheLookup(includingLeaderboards: true)
        let playersLookupRevision = listRevision
        let leaderboardsLookupRevision = leaderboardsRevision
        async let cachedPlayers = responseCache.loadPlayers(for: playersKey)
        async let cachedLeaderboards = responseCache.loadLeaderboards(for: leaderboardsKey)
        var playersWork: RequestWork?
        var leaderboardsWork: RequestWork?

        let playersResponse = await cachedPlayers
        if playersLookupRevision == listRevision,
           playersKey == ScoutPlayersCacheKey(
            phase: selectedPhase,
            request: makePlayersRequest(page: 1)
        ) {
            if let playersResponse {
                applyCachedPlayers(playersResponse)
            }
            playersWork = schedulePlayersReload(preservingCurrentData: playersResponse != nil)
        }

        let leaderboardsResponse = await cachedLeaderboards
        if leaderboardsLookupRevision == leaderboardsRevision,
           leaderboardsKey == ScoutLeaderboardsCacheKey(
            phase: selectedPhase,
            request: makeLeaderboardsRequest()
        ) {
            if let leaderboardsResponse {
                applyCachedLeaderboards(leaderboardsResponse)
            }
            leaderboardsWork = scheduleLeaderboardsReload(
                preservingCurrentData: leaderboardsResponse != nil
            )
        }

        switch (playersWork, leaderboardsWork) {
        case let (playersWork?, leaderboardsWork?):
            await finishFullReload(FullReloadWork(list: playersWork, boards: leaderboardsWork))
        case let (playersWork?, nil):
            await finishPlayersReload(playersWork)
        case let (nil, leaderboardsWork?):
            await finishLeaderboardsReload(leaderboardsWork)
        case (nil, nil):
            return
        }
    }

    private func reloadPlayersUsingCache() async {
        let request = makePlayersRequest(page: 1)
        let key = ScoutPlayersCacheKey(phase: selectedPhase, request: request)

        prepareForCacheLookup(includingLeaderboards: false)
        let lookupRevision = listRevision
        let cachedResponse = await responseCache.loadPlayers(for: key)

        guard lookupRevision == listRevision,
              key == ScoutPlayersCacheKey(
            phase: selectedPhase,
            request: makePlayersRequest(page: 1)
        ) else { return }

        if let cachedResponse {
            applyCachedPlayers(cachedResponse)
        }

        let work = schedulePlayersReload(preservingCurrentData: cachedResponse != nil)
        await finishPlayersReload(work)
    }

    private func prepareForCacheLookup(includingLeaderboards: Bool) {
        playersReloadTask?.cancel()
        paginationTask?.cancel()
        listRevision += 1
        currentPage = 0
        totalPages = 0
        totalPlayers = 0
        players = []
        isShowingCachedPlayers = false
        firstRowDataSource = "network"
        isLoadingInitial = true
        isLoadingNextPage = false
        errorMessage = nil
        paginationErrorMessage = nil

        guard includingLeaderboards else { return }
        leaderboardsTask?.cancel()
        leaderboardsRevision += 1
        leaderboards = [:]
        isShowingCachedLeaderboards = false
        leaderboardsErrorMessage = nil
        isLoadingLeaderboards = true
    }

    private func applyCachedPlayers(_ response: ScoutPlayersResponse) {
        players = response.players
        totalPlayers = response.total
        currentPage = response.page
        totalPages = response.totalPages
        isShowingCachedPlayers = true
        firstRowDataSource = "disk-cache"
    }

    private func applyCachedLeaderboards(_ response: ScoutLeaderboardsResponse) {
        leaderboards = response.leaderboards
        isShowingCachedLeaderboards = true
    }

    private func scheduleFullReload(
        preservingPlayers: Bool = false,
        preservingLeaderboards: Bool = false
    ) -> FullReloadWork {
        let list = schedulePlayersReload(preservingCurrentData: preservingPlayers)
        let boards = scheduleLeaderboardsReload(preservingCurrentData: preservingLeaderboards)
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

    private func finishPlayersReload(_ work: RequestWork) async {
        await work.task.value
        if work.revision == listRevision {
            playersReloadTask = nil
        }
    }

    private func finishLeaderboardsReload(_ work: RequestWork) async {
        await work.task.value
        if work.revision == leaderboardsRevision {
            leaderboardsTask = nil
        }
    }

    private func schedulePlayersReload(preservingCurrentData: Bool = false) -> RequestWork {
        playersReloadTask?.cancel()
        paginationTask?.cancel()
        listRevision += 1
        let revision = listRevision

        if !preservingCurrentData {
            currentPage = 0
            totalPages = 0
            totalPlayers = 0
            players = []
            isShowingCachedPlayers = false
            firstRowDataSource = "network"
        }
        isLoadingInitial = true
        isLoadingNextPage = false
        errorMessage = nil
        paginationErrorMessage = nil

        let request = makePlayersRequest(page: 1)
        let context = PlayersReloadContext(
            revision: revision,
            request: request,
            cacheKey: ScoutPlayersCacheKey(phase: selectedPhase, request: request)
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
            isShowingCachedPlayers = false
            firstRowDataSource = "network"
            await responseCache.savePlayers(response, for: context.cacheKey)
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

    private func scheduleLeaderboardsReload(preservingCurrentData: Bool = false) -> RequestWork {
        leaderboardsTask?.cancel()
        leaderboardsRevision += 1
        let revision = leaderboardsRevision

        if !preservingCurrentData {
            leaderboards = [:]
            isShowingCachedLeaderboards = false
        }
        leaderboardsErrorMessage = nil
        isLoadingLeaderboards = true

        let request = makeLeaderboardsRequest()
        let context = LeaderboardsReloadContext(
            revision: revision,
            request: request,
            cacheKey: ScoutLeaderboardsCacheKey(phase: selectedPhase, request: request)
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
            isShowingCachedLeaderboards = false
            await responseCache.saveLeaderboards(response, for: context.cacheKey)
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
    let cacheKey: ScoutPlayersCacheKey
}

private struct LeaderboardsReloadContext: Sendable {
    let revision: Int
    let request: ScoutLeaderboardsRequest
    let cacheKey: ScoutLeaderboardsCacheKey
}

private struct PageLoadContext: Sendable {
    let revision: Int
    let request: ScoutPlayersRequest
}
