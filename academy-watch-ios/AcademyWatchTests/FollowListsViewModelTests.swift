import XCTest
@testable import AcademyWatch

final class FollowListsViewModelTests: XCTestCase {
    @MainActor
    func testDefaultListRejectsGenericFollowMutations() async throws {
        let follow = Follow(
            id: 201,
            kind: .player,
            selector: FollowSelector(playerApiId: 2_001, teamId: nil, countries: nil, match: nil),
            label: "Watchlist player",
            note: nil,
            createdAt: nil
        )
        let defaultList = FollowList(
            id: 27,
            name: "My Watchlist",
            cadence: "weekly",
            isActive: true,
            isDefault: true,
            playerCap: 200,
            followCount: 1,
            follows: [follow],
            createdAt: nil,
            updatedAt: nil
        )
        let client = OverlappingFollowRemovalClient(list: defaultList, delayedFailureID: -1)
        let viewModel = FollowListsViewModel(apiClient: client)
        await viewModel.loadLists()

        let didAddGenerically = await viewModel.addPlayer(2_002, to: defaultList.id)
        let didRemoveGenerically = await viewModel.removeFollow(follow, from: defaultList.id)

        XCTAssertFalse(didAddGenerically)
        XCTAssertFalse(didRemoveGenerically)
        XCTAssertEqual(viewModel.list(id: defaultList.id), defaultList)
    }

    @MainActor
    func testFailedRemovalRestoresOnlyItsDeltaDuringOverlappingSuccessfulRemoval() async throws {
        let first = Follow(
            id: 101,
            kind: .player,
            selector: FollowSelector(playerApiId: 1_001, teamId: nil, countries: nil, match: nil),
            label: "First player",
            note: nil,
            createdAt: nil
        )
        let second = Follow(
            id: 102,
            kind: .player,
            selector: FollowSelector(playerApiId: 1_002, teamId: nil, countries: nil, match: nil),
            label: "Second player",
            note: nil,
            createdAt: nil
        )
        let list = FollowList(
            id: 17,
            name: "Shortlist",
            cadence: "weekly",
            isActive: true,
            isDefault: false,
            playerCap: 40,
            followCount: 2,
            follows: [first, second],
            createdAt: nil,
            updatedAt: nil
        )
        let client = OverlappingFollowRemovalClient(
            list: list,
            delayedFailureID: first.id
        )
        let viewModel = FollowListsViewModel(apiClient: client)
        await viewModel.loadLists()

        let failedRemoval = Task { @MainActor in
            await viewModel.removeFollow(first, from: list.id)
        }
        await client.waitUntilDelayedRemovalStarts()

        let secondRemovalSucceeded = await viewModel.removeFollow(second, from: list.id)
        XCTAssertTrue(secondRemovalSucceeded)
        await client.releaseDelayedFailure()
        let firstRemovalSucceeded = await failedRemoval.value
        XCTAssertFalse(firstRemovalSucceeded)

        let updated = try XCTUnwrap(viewModel.list(id: list.id))
        XCTAssertEqual(updated.follows, [first])
        XCTAssertEqual(updated.followCount, 1)
    }

    @MainActor
    func testWatchlistSynchronizationRetriesAfterConcurrentListCreation() async throws {
        let existing = makeList(id: 301, name: "Existing")
        let created = makeList(id: 302, name: "Created")
        let defaultList = FollowList(
            id: 300,
            name: "My Watchlist",
            cadence: "weekly",
            isActive: true,
            isDefault: true,
            playerCap: 200,
            followCount: 0,
            follows: [],
            createdAt: nil,
            updatedAt: nil
        )
        let client = SynchronizingFollowListsClient(
            initialLists: [existing],
            staleSynchronizationLists: [defaultList, existing],
            stableLists: [defaultList, existing, created],
            createdList: created
        )
        let viewModel = FollowListsViewModel(apiClient: client)
        await viewModel.loadLists()

        let synchronization = Task { @MainActor in
            await viewModel.synchronizeAfterWatchlistMutation()
        }
        await client.waitUntilSynchronizationReadStarts()

        let creation = Task { @MainActor in
            await viewModel.createList(name: created.name)
        }
        await client.waitUntilCreationStarts()

        await client.releaseCreation()
        let didCreate = await creation.value
        await client.releaseSynchronizationRead()
        await synchronization.value
        let fetchCount = await client.fetchCount()

        XCTAssertTrue(didCreate)
        XCTAssertEqual(viewModel.lists, [defaultList, existing, created])
        XCTAssertEqual(fetchCount, 3)
    }

    private func makeList(id: Int, name: String) -> FollowList {
        FollowList(
            id: id,
            name: name,
            cadence: "weekly",
            isActive: true,
            isDefault: false,
            playerCap: 40,
            followCount: 0,
            follows: [],
            createdAt: nil,
            updatedAt: nil
        )
    }
}

private actor SynchronizingFollowListsClient: FollowListsAPIClientProtocol {
    let initialLists: [FollowList]
    let staleSynchronizationLists: [FollowList]
    let stableLists: [FollowList]
    let createdList: FollowList

    private var fetchCallCount = 0
    private var synchronizationReadStarted = false
    private var synchronizationReadStartWaiters: [CheckedContinuation<Void, Never>] = []
    private var synchronizationReadContinuation: CheckedContinuation<Void, Never>?
    private var creationStarted = false
    private var creationStartWaiters: [CheckedContinuation<Void, Never>] = []
    private var creationContinuation: CheckedContinuation<Void, Never>?

    init(
        initialLists: [FollowList],
        staleSynchronizationLists: [FollowList],
        stableLists: [FollowList],
        createdList: FollowList
    ) {
        self.initialLists = initialLists
        self.staleSynchronizationLists = staleSynchronizationLists
        self.stableLists = stableLists
        self.createdList = createdList
    }

    func fetchFollowLists() async throws -> FollowListsResponse {
        fetchCallCount += 1
        switch fetchCallCount {
        case 1:
            return FollowListsResponse(lists: initialLists)
        case 2:
            await withCheckedContinuation { continuation in
                synchronizationReadContinuation = continuation
                synchronizationReadStarted = true
                synchronizationReadStartWaiters.forEach { $0.resume() }
                synchronizationReadStartWaiters = []
            }
            return FollowListsResponse(lists: staleSynchronizationLists)
        default:
            return FollowListsResponse(lists: stableLists)
        }
    }

    func createFollowList(name _: String) async throws -> FollowListResponse {
        await withCheckedContinuation { continuation in
            creationContinuation = continuation
            creationStarted = true
            creationStartWaiters.forEach { $0.resume() }
            creationStartWaiters = []
        }
        return FollowListResponse(list: createdList)
    }

    func deleteFollowList(listID _: Int) async throws -> FollowListDeleteResponse {
        FollowListDeleteResponse(deleted: true)
    }

    func addPlayerFollow(listID _: Int, playerID _: Int) async throws -> FollowResponse {
        throw URLError(.unsupportedURL)
    }

    func removeFollow(listID _: Int, followID _: Int) async throws -> FollowRemoveResponse {
        FollowRemoveResponse(removed: true)
    }

    func resolveFollowList(
        listID _: Int,
        limit _: Int,
        offset _: Int
    ) async throws -> ResolvedFollowListResponse {
        ResolvedFollowListResponse(players: [], total: 0)
    }

    func waitUntilSynchronizationReadStarts() async {
        if synchronizationReadStarted { return }
        await withCheckedContinuation { continuation in
            synchronizationReadStartWaiters.append(continuation)
        }
    }

    func waitUntilCreationStarts() async {
        if creationStarted { return }
        await withCheckedContinuation { continuation in
            creationStartWaiters.append(continuation)
        }
    }

    func releaseSynchronizationRead() {
        synchronizationReadContinuation?.resume()
        synchronizationReadContinuation = nil
    }

    func releaseCreation() {
        creationContinuation?.resume()
        creationContinuation = nil
    }

    func fetchCount() -> Int {
        fetchCallCount
    }
}

private actor OverlappingFollowRemovalClient: FollowListsAPIClientProtocol {
    let list: FollowList
    let delayedFailureID: Int

    private var delayedRemovalStarted = false
    private var startWaiters: [CheckedContinuation<Void, Never>] = []
    private var failureContinuation: CheckedContinuation<Void, Never>?

    init(list: FollowList, delayedFailureID: Int) {
        self.list = list
        self.delayedFailureID = delayedFailureID
    }

    func fetchFollowLists() async throws -> FollowListsResponse {
        FollowListsResponse(lists: [list])
    }

    func createFollowList(name _: String) async throws -> FollowListResponse {
        FollowListResponse(list: list)
    }

    func deleteFollowList(listID _: Int) async throws -> FollowListDeleteResponse {
        FollowListDeleteResponse(deleted: true)
    }

    func addPlayerFollow(listID _: Int, playerID _: Int) async throws -> FollowResponse {
        FollowResponse(follow: list.follows[0], shadowCreated: false)
    }

    func removeFollow(listID _: Int, followID: Int) async throws -> FollowRemoveResponse {
        if followID == delayedFailureID {
            await withCheckedContinuation { continuation in
                failureContinuation = continuation
                delayedRemovalStarted = true
                startWaiters.forEach { $0.resume() }
                startWaiters = []
            }
            throw URLError(.timedOut)
        }
        return FollowRemoveResponse(removed: true)
    }

    func resolveFollowList(
        listID _: Int,
        limit _: Int,
        offset _: Int
    ) async throws -> ResolvedFollowListResponse {
        ResolvedFollowListResponse(players: [], total: 0)
    }

    func waitUntilDelayedRemovalStarts() async {
        if delayedRemovalStarted { return }
        await withCheckedContinuation { continuation in
            startWaiters.append(continuation)
        }
    }

    func releaseDelayedFailure() {
        failureContinuation?.resume()
        failureContinuation = nil
    }
}
