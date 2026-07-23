import Combine
import Foundation

@MainActor
final class FollowListsViewModel: ObservableObject {
    @Published private(set) var lists: [FollowList] = []
    @Published private(set) var isLoading = false
    @Published private(set) var isCreating = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var pendingListIDs: Set<Int> = []
    @Published private(set) var pendingPlayerIDs: Set<Int> = []
    @Published private(set) var pendingFollowIDs: Set<Int> = []

    private let apiClient: any FollowListsAPIClientProtocol
    private var sessionRevision = 0
    private var listDataRevision = 0
    private var loadRequestRevision = 0
    private var synchronizationRequestRevision = 0
    private var synchronizationTaskRevision = 0
    private var synchronizationTask: Task<Void, Never>?
    private var listMutationWaiters: [CheckedContinuation<Void, Never>] = []

    init(apiClient: any FollowListsAPIClientProtocol = APIClient()) {
        self.apiClient = apiClient
    }

    func list(id: Int) -> FollowList? {
        lists.first { $0.id == id }
    }

    func loadLists() async {
        loadRequestRevision += 1
        let session = sessionRevision
        let dataRevision = listDataRevision
        let requestRevision = loadRequestRevision
        isLoading = true
        errorMessage = nil
        defer {
            if session == sessionRevision, requestRevision == loadRequestRevision {
                isLoading = false
            }
        }

        do {
            let response = try await apiClient.fetchFollowLists()
            guard session == sessionRevision,
                  dataRevision == listDataRevision,
                  requestRevision == loadRequestRevision
            else { return }
            lists = response.lists
        } catch {
            guard session == sessionRevision,
                  dataRevision == listDataRevision,
                  requestRevision == loadRequestRevision
            else { return }
            errorMessage = displayMessage(for: error)
        }
    }

    func synchronizeAfterWatchlistMutation() async {
        synchronizationRequestRevision += 1
        if let synchronizationTask {
            await synchronizationTask.value
            return
        }

        synchronizationTaskRevision += 1
        let taskRevision = synchronizationTaskRevision
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.performStableSynchronization()
            if self.synchronizationTaskRevision == taskRevision {
                self.synchronizationTask = nil
            }
        }
        synchronizationTask = task
        await task.value
    }

    @discardableResult
    func createList(name: String) async -> Bool {
        let trimmedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedName.isEmpty, !isCreating else { return false }

        let revision = sessionRevision
        invalidateListLoads()
        isCreating = true
        errorMessage = nil
        defer {
            if revision == sessionRevision {
                isCreating = false
                resumeListMutationWaitersIfSettled()
            }
        }

        do {
            let response = try await apiClient.createFollowList(name: trimmedName)
            guard revision == sessionRevision else { return false }
            invalidateListLoads()
            lists.append(response.list)
            return true
        } catch {
            guard revision == sessionRevision else { return false }
            invalidateListLoads()
            errorMessage = displayMessage(for: error)
            return false
        }
    }

    func deleteList(_ list: FollowList) async {
        guard !list.isDefault, !pendingListIDs.contains(list.id) else { return }

        let revision = sessionRevision
        let originalIndex = lists.firstIndex { $0.id == list.id }
        invalidateListLoads()
        pendingListIDs.insert(list.id)
        errorMessage = nil
        lists.removeAll { $0.id == list.id }

        defer {
            if revision == sessionRevision {
                pendingListIDs.remove(list.id)
                resumeListMutationWaitersIfSettled()
            }
        }

        do {
            _ = try await apiClient.deleteFollowList(listID: list.id)
            guard revision == sessionRevision else { return }
            invalidateListLoads()
        } catch {
            guard revision == sessionRevision else { return }
            invalidateListLoads()
            if !lists.contains(where: { $0.id == list.id }) {
                lists.insert(list, at: min(originalIndex ?? lists.endIndex, lists.endIndex))
            }
            errorMessage = displayMessage(for: error)
        }
    }

    @discardableResult
    func addPlayer(_ playerID: Int, to listID: Int) async -> Bool {
        guard !pendingPlayerIDs.contains(playerID),
              let listIndex = lists.firstIndex(where: { $0.id == listID }),
              !lists[listIndex].isDefault,
              !lists[listIndex].containsPlayer(playerID)
        else { return false }

        let revision = sessionRevision
        invalidateListLoads()
        pendingPlayerIDs.insert(playerID)
        errorMessage = nil
        defer {
            if revision == sessionRevision {
                pendingPlayerIDs.remove(playerID)
                resumeListMutationWaitersIfSettled()
            }
        }

        do {
            let response = try await apiClient.addPlayerFollow(listID: listID, playerID: playerID)
            guard revision == sessionRevision,
                  let currentIndex = lists.firstIndex(where: { $0.id == listID })
            else { return false }
            invalidateListLoads()
            let current = lists[currentIndex]
            lists[currentIndex] = current.replacing(
                follows: current.follows + [response.follow],
                followCount: current.followCount + 1
            )
            return true
        } catch {
            guard revision == sessionRevision else { return false }
            invalidateListLoads()
            errorMessage = displayMessage(for: error)
            return false
        }
    }

    @discardableResult
    func removeFollow(_ follow: Follow, from listID: Int) async -> Bool {
        guard follow.kind == .player,
              !pendingFollowIDs.contains(follow.id),
              let listIndex = lists.firstIndex(where: { $0.id == listID }),
              !lists[listIndex].isDefault
        else { return false }

        let revision = sessionRevision
        let snapshot = lists[listIndex]
        let originalFollowIndex = snapshot.follows.firstIndex { $0.id == follow.id }
        invalidateListLoads()
        pendingFollowIDs.insert(follow.id)
        errorMessage = nil
        lists[listIndex] = snapshot.replacing(
            follows: snapshot.follows.filter { $0.id != follow.id },
            followCount: max(0, snapshot.followCount - 1)
        )

        defer {
            if revision == sessionRevision {
                pendingFollowIDs.remove(follow.id)
                resumeListMutationWaitersIfSettled()
            }
        }

        do {
            _ = try await apiClient.removeFollow(listID: listID, followID: follow.id)
            guard revision == sessionRevision else { return false }
            invalidateListLoads()
            return true
        } catch {
            guard revision == sessionRevision else { return false }
            invalidateListLoads()
            if let currentIndex = lists.firstIndex(where: { $0.id == listID }) {
                let current = lists[currentIndex]
                if !current.follows.contains(where: { $0.id == follow.id }) {
                    var restoredFollows = current.follows
                    restoredFollows.insert(
                        follow,
                        at: min(originalFollowIndex ?? restoredFollows.endIndex, restoredFollows.endIndex)
                    )
                    lists[currentIndex] = current.replacing(
                        follows: restoredFollows,
                        followCount: current.followCount + 1
                    )
                }
            }
            errorMessage = displayMessage(for: error)
            return false
        }
    }

    func resetForSignOut() {
        sessionRevision += 1
        listDataRevision += 1
        synchronizationRequestRevision += 1
        synchronizationTaskRevision += 1
        synchronizationTask?.cancel()
        synchronizationTask = nil
        lists = []
        isLoading = false
        isCreating = false
        errorMessage = nil
        pendingListIDs = []
        pendingPlayerIDs = []
        pendingFollowIDs = []
        resumeListMutationWaitersIfSettled()
    }

    func clearError() {
        errorMessage = nil
    }

    private func displayMessage(for error: Error) -> String {
        (error as? LocalizedError)?.errorDescription
            ?? "We couldn't update your lists. Check your connection and try again."
    }

    private func invalidateListLoads() {
        listDataRevision += 1
    }

    private var hasActiveListMutation: Bool {
        isCreating
            || !pendingListIDs.isEmpty
            || !pendingPlayerIDs.isEmpty
            || !pendingFollowIDs.isEmpty
    }

    private func performStableSynchronization() async {
        let session = sessionRevision
        var latestRequestRevision: Int?
        isLoading = true
        errorMessage = nil
        defer {
            if session == sessionRevision,
               latestRequestRevision == loadRequestRevision {
                isLoading = false
            }
        }

        while session == sessionRevision, !Task.isCancelled {
            if hasActiveListMutation {
                await waitForListMutationsToSettle()
                continue
            }

            loadRequestRevision += 1
            let dataRevision = listDataRevision
            let requestRevision = loadRequestRevision
            latestRequestRevision = requestRevision
            let synchronizationRevision = synchronizationRequestRevision

            do {
                let response = try await apiClient.fetchFollowLists()
                guard session == sessionRevision, !Task.isCancelled else { return }
                guard dataRevision == listDataRevision,
                      requestRevision == loadRequestRevision,
                      synchronizationRevision == synchronizationRequestRevision,
                      !hasActiveListMutation
                else { continue }
                lists = response.lists
                return
            } catch {
                guard session == sessionRevision, !Task.isCancelled else { return }
                guard dataRevision == listDataRevision,
                      requestRevision == loadRequestRevision,
                      synchronizationRevision == synchronizationRequestRevision,
                      !hasActiveListMutation
                else { continue }
                errorMessage = displayMessage(for: error)
                return
            }
        }
    }

    private func waitForListMutationsToSettle() async {
        guard hasActiveListMutation else { return }
        await withCheckedContinuation { continuation in
            listMutationWaiters.append(continuation)
        }
    }

    private func resumeListMutationWaitersIfSettled() {
        guard !hasActiveListMutation, !listMutationWaiters.isEmpty else { return }
        let waiters = listMutationWaiters
        listMutationWaiters = []
        waiters.forEach { $0.resume() }
    }
}

@MainActor
final class FollowListDetailViewModel: ObservableObject {
    @Published private(set) var players: [ResolvedFollowPlayer] = []
    @Published private(set) var total = 0
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?

    let listID: Int
    private let pageSize: Int
    private let apiClient: any FollowListsAPIClientProtocol
    private var hasAttemptedLoad = false
    private var needsReloadAfterCurrentLoad = false

    init(
        listID: Int,
        apiClient: any FollowListsAPIClientProtocol = APIClient(),
        pageSize: Int = 20
    ) {
        self.listID = listID
        self.apiClient = apiClient
        self.pageSize = pageSize
    }

    var canLoadMore: Bool {
        players.count < total
    }

    func loadIfNeeded() async {
        guard !hasAttemptedLoad else { return }
        await reload()
    }

    func reload() async {
        guard !isLoading else {
            needsReloadAfterCurrentLoad = true
            return
        }
        hasAttemptedLoad = true
        players = []
        total = 0
        await loadPage(offset: 0)
    }

    func loadMore() async {
        guard canLoadMore, !isLoading else { return }
        await loadPage(offset: players.count)
    }

    private func loadPage(offset: Int) async {
        isLoading = true
        errorMessage = nil

        do {
            let response = try await apiClient.resolveFollowList(
                listID: listID,
                limit: pageSize,
                offset: offset
            )
            if offset == 0 {
                players = response.players
            } else {
                let existingIDs = Set(players.map(\.playerApiId))
                players.append(contentsOf: response.players.filter { !existingIDs.contains($0.playerApiId) })
            }
            total = response.total
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription
                ?? "We couldn't resolve this list. Check your connection and try again."
        }

        isLoading = false
        if needsReloadAfterCurrentLoad {
            needsReloadAfterCurrentLoad = false
            players = []
            total = 0
            await loadPage(offset: 0)
        }
    }
}

private extension FollowList {
    func replacing(follows: [Follow], followCount: Int) -> FollowList {
        FollowList(
            id: id,
            name: name,
            cadence: cadence,
            isActive: isActive,
            isDefault: isDefault,
            playerCap: playerCap,
            followCount: followCount,
            follows: follows,
            createdAt: createdAt,
            updatedAt: updatedAt
        )
    }
}
