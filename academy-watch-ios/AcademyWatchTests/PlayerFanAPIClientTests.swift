import Foundation
import XCTest
@testable import AcademyWatch

/// Covers the PlayerDetail fan surface: follower-count decode (following null
/// vs bool), follow 201/200 idempotency, unfollow, and the neutral-404 "no fan
/// surface" rule, plus the optimistic-toggle rollback behaviour.
final class PlayerFanAPIClientTests: XCTestCase {
    override func setUp() {
        super.setUp()
        PlayerFanURLProtocol.reset()
    }

    override func tearDown() {
        PlayerFanURLProtocol.reset()
        super.tearDown()
    }

    // MARK: - Count decode

    func testFollowerCountDecodesAnonymousAndSignedInShapes() async throws {
        let client = makeClient { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.path, "/api/players/403064/followers/count")
            return (
                200,
                #"{"player_api_id":403064,"fans":12,"following":null,"share_url":"https://theacademywatch.com/p/403064"}"#
            )
        }

        let anonymous = try await client.fetchFollowerCount(playerID: 403_064)

        XCTAssertEqual(anonymous.fans, 12)
        XCTAssertNil(anonymous.following)
        XCTAssertEqual(anonymous.shareUrl, "https://theacademywatch.com/p/403064")

        PlayerFanURLProtocol.setHandler { request in
            (
                Self.response(request, status: 200),
                Data(#"{"player_api_id":403064,"fans":12,"following":true,"share_url":"https://theacademywatch.com/p/403064"}"#.utf8)
            )
        }

        let following = try await client.fetchFollowerCount(playerID: 403_064)

        XCTAssertEqual(following.following, true)
    }

    func testFollowerCountPathCarriesNegativeSignedLocalID() async throws {
        PlayerFanURLProtocol.setHandler { request in
            XCTAssertEqual(request.url?.path, "/api/players/-41/followers/count")
            return (
                Self.response(request, status: 200),
                Data(#"{"player_api_id":-41,"fans":0,"following":null,"share_url":"https://theacademywatch.com/p/-41"}"#.utf8)
            )
        }

        let response = try await makeClient().fetchFollowerCount(playerID: -41)

        XCTAssertEqual(response.fans, 0)
        XCTAssertNil(response.following)
    }

    // MARK: - Follow / unfollow

    func testFollowDecodesCreatedAndIdempotentResponses() async throws {
        let callCounter = CallCounter()
        PlayerFanURLProtocol.setHandler { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.path, "/api/players/403064/follow")
            let call = callCounter.increment()
            if call == 1 {
                return (
                    Self.response(request, status: 201),
                    Data(#"{"player_api_id":403064,"following":true,"fans":13,"created":true}"#.utf8)
                )
            }
            return (
                Self.response(request, status: 200),
                Data(#"{"player_api_id":403064,"following":true,"fans":13,"created":false}"#.utf8)
            )
        }
        let client = makeClient()

        let created = try await client.followPlayer(playerID: 403_064)
        let repeated = try await client.followPlayer(playerID: 403_064)

        XCTAssertEqual(created.fans, 13)
        XCTAssertEqual(created.following, true)
        XCTAssertEqual(created.created, true)
        XCTAssertEqual(repeated.created, false)
        XCTAssertEqual(repeated.fans, 13)
    }

    func testUnfollowDecodesRemovalResponse() async throws {
        PlayerFanURLProtocol.setHandler { request in
            XCTAssertEqual(request.httpMethod, "DELETE")
            XCTAssertEqual(request.url?.path, "/api/players/403064/follow")
            return (
                Self.response(request, status: 200),
                Data(#"{"player_api_id":403064,"following":false,"deleted":true}"#.utf8)
            )
        }

        let response = try await makeClient().unfollowPlayer(playerID: 403_064)

        XCTAssertEqual(response.following, false)
        XCTAssertEqual(response.deleted, true)
    }

    // MARK: - View model behaviour

    @MainActor
    func testLoadHidesSurfaceOnNeutral404() async {
        let client = FanStubClient(
            countResult: .failure(APIClientError.server(statusCode: 404, message: "Player not found"))
        )
        let viewModel = PlayerFanViewModel(playerID: 403_064, apiClient: client)

        await viewModel.loadIfNeeded()

        XCTAssertNil(viewModel.summary, "non-public subjects must render nothing")
        XCTAssertNil(viewModel.actionErrorMessage)
    }

    @MainActor
    func testLoadResolvesCountAndFollowStateForSignedInCaller() async {
        let client = FanStubClient(countResult: .success(
            PlayerFollowerCountResponse(playerApiId: 403_064, fans: 12, following: true, shareUrl: nil)
        ))
        let viewModel = PlayerFanViewModel(playerID: 403_064, apiClient: client)

        await viewModel.loadIfNeeded()

        XCTAssertEqual(viewModel.summary?.fans, 12)
        XCTAssertEqual(viewModel.summary?.following, true)
    }

    @MainActor
    func testFollowTogglesOptimisticallyAndAppliesServerFans() async {
        let client = FanStubClient(
            countResult: .success(
                PlayerFollowerCountResponse(playerApiId: 403_064, fans: 12, following: false, shareUrl: nil)
            ),
            followResult: .success(PlayerFollowResponse(playerApiId: 403_064, following: true, fans: 13, created: true))
        )
        let viewModel = PlayerFanViewModel(playerID: 403_064, apiClient: client)
        await viewModel.loadIfNeeded()

        var signInRequested = false
        await viewModel.toggleFollow(isAuthenticated: true, onSignInRequested: { signInRequested = true })

        XCTAssertFalse(signInRequested)
        XCTAssertEqual(viewModel.summary?.following, true)
        XCTAssertEqual(viewModel.summary?.fans, 13)
        XCTAssertNil(viewModel.actionErrorMessage)
    }

    @MainActor
    func testSelfFollow400RollsBackAndSurfacesInlineMessage() async {
        let client = FanStubClient(
            countResult: .success(
                PlayerFollowerCountResponse(playerApiId: 403_064, fans: 12, following: false, shareUrl: nil)
            ),
            followResult: .failure(
                APIClientError.server(statusCode: 400, message: "You cannot follow your own profile")
            )
        )
        let viewModel = PlayerFanViewModel(playerID: 403_064, apiClient: client)
        await viewModel.loadIfNeeded()

        await viewModel.toggleFollow(isAuthenticated: true, onSignInRequested: {})

        XCTAssertEqual(viewModel.summary, PlayerFanSummary(fans: 12, following: false), "optimistic state rolls back")
        XCTAssertEqual(viewModel.actionErrorMessage, "You cannot follow your own profile")
    }

    @MainActor
    func testUnfollowFailureRollsBackFollowingState() async {
        let client = FanStubClient(
            countResult: .success(
                PlayerFollowerCountResponse(playerApiId: 403_064, fans: 12, following: true, shareUrl: nil)
            ),
            unfollowResult: .failure(APIClientError.server(statusCode: 500, message: "Failed"))
        )
        let viewModel = PlayerFanViewModel(playerID: 403_064, apiClient: client)
        await viewModel.loadIfNeeded()

        await viewModel.toggleFollow(isAuthenticated: true, onSignInRequested: {})

        XCTAssertEqual(viewModel.summary, PlayerFanSummary(fans: 12, following: true))
        XCTAssertNotNil(viewModel.actionErrorMessage)
    }

    @MainActor
    func testUnfollowWithoutDeletedRowRestoresServerCount() async {
        let client = FanStubClient(
            countResult: .success(
                PlayerFollowerCountResponse(playerApiId: 403_064, fans: 12, following: true, shareUrl: nil)
            ),
            unfollowResult: .success(
                PlayerUnfollowResponse(playerApiId: 403_064, following: false, deleted: false)
            )
        )
        let viewModel = PlayerFanViewModel(playerID: 403_064, apiClient: client)
        await viewModel.loadIfNeeded()

        await viewModel.toggleFollow(isAuthenticated: true, onSignInRequested: {})

        XCTAssertEqual(viewModel.summary, PlayerFanSummary(fans: 12, following: false))
        XCTAssertNil(viewModel.actionErrorMessage)
    }

    @MainActor
    func testRefreshStartedBeforeFollowCannotOverwriteMutationResult() async {
        let client = FanRefreshRaceClient()
        let viewModel = PlayerFanViewModel(playerID: 403_064, apiClient: client)
        await viewModel.loadIfNeeded()

        let refreshTask = Task { await viewModel.refresh() }
        await client.waitForSecondFetchToStart()
        await viewModel.toggleFollow(isAuthenticated: true, onSignInRequested: {})
        await client.finishSecondFetch()
        await refreshTask.value

        XCTAssertEqual(viewModel.summary, PlayerFanSummary(fans: 13, following: true))
    }

    @MainActor
    func testSignedOutToggleRoutesToSignInWithoutTouchingState() async {
        let client = FanStubClient(countResult: .success(
            PlayerFollowerCountResponse(playerApiId: 403_064, fans: 12, following: nil, shareUrl: nil)
        ))
        let viewModel = PlayerFanViewModel(playerID: 403_064, apiClient: client)
        await viewModel.loadIfNeeded()

        var signInRequested = false
        await viewModel.toggleFollow(isAuthenticated: false, onSignInRequested: { signInRequested = true })

        XCTAssertTrue(signInRequested)
        XCTAssertNil(viewModel.summary?.following)
        XCTAssertEqual(client.followCallCount, 0)
    }
}

// MARK: - Helpers

private extension PlayerFanAPIClientTests {
    func makeClient() -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [PlayerFanURLProtocol.self]
        return APIClient(
            baseURL: URL(string: "https://example.test/api")!,
            session: URLSession(configuration: configuration)
        )
    }

    func makeClient(
        handler: @escaping @Sendable (URLRequest) -> (Int, String)
    ) -> APIClient {
        PlayerFanURLProtocol.setHandler { request in
            let (status, body) = handler(request)
            return (Self.response(request, status: status), Data(body.utf8))
        }
        return makeClient()
    }

    static func response(_ request: URLRequest, status: Int) -> HTTPURLResponse {
        HTTPURLResponse(
            url: request.url!,
            statusCode: status,
            httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
    }
}

private final class CallCounter: @unchecked Sendable {
    private let lock = NSLock()
    private var calls = 0

    func increment() -> Int {
        lock.lock()
        defer { lock.unlock() }
        calls += 1
        return calls
    }
}

private final class PlayerFanURLProtocol: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var handler: ((URLRequest) -> (HTTPURLResponse, Data))?

    static func setHandler(_ value: @escaping (URLRequest) -> (HTTPURLResponse, Data)) {
        lock.lock()
        handler = value
        lock.unlock()
    }

    static func reset() {
        lock.lock()
        handler = nil
        lock.unlock()
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.lock.lock()
        let handler = Self.handler
        Self.lock.unlock()
        guard let handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.unsupportedURL))
            return
        }
        let (response, data) = handler(request)
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        if !data.isEmpty { client?.urlProtocol(self, didLoad: data) }
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

private final class FanStubClient: PlayerFanAPIClientProtocol, @unchecked Sendable {
    private let lock = NSLock()
    private var countResult: Result<PlayerFollowerCountResponse, Error>
    private var followResult: Result<PlayerFollowResponse, Error>
    private var unfollowResult: Result<PlayerUnfollowResponse, Error>
    private var followCount = 0

    init(
        countResult: Result<PlayerFollowerCountResponse, Error>,
        followResult: Result<PlayerFollowResponse, Error> = .failure(URLError(.unsupportedURL)),
        unfollowResult: Result<PlayerUnfollowResponse, Error> = .failure(URLError(.unsupportedURL))
    ) {
        self.countResult = countResult
        self.followResult = followResult
        self.unfollowResult = unfollowResult
    }

    var followCallCount: Int {
        lock.lock()
        defer { lock.unlock() }
        return followCount
    }

    func fetchFollowerCount(playerID _: Int) async throws -> PlayerFollowerCountResponse {
        try countResult.get()
    }

    func followPlayer(playerID _: Int) async throws -> PlayerFollowResponse {
        lock.lock()
        followCount += 1
        lock.unlock()
        return try followResult.get()
    }

    func unfollowPlayer(playerID _: Int) async throws -> PlayerUnfollowResponse {
        try unfollowResult.get()
    }
}

private actor FanRefreshRaceClient: PlayerFanAPIClientProtocol {
    private var fetchCount = 0
    private var didStartSecondFetch = false
    private var secondFetchContinuation: CheckedContinuation<PlayerFollowerCountResponse, Never>?
    private var secondFetchStartedContinuation: CheckedContinuation<Void, Never>?

    func fetchFollowerCount(playerID: Int) async throws -> PlayerFollowerCountResponse {
        fetchCount += 1
        if fetchCount == 1 {
            return PlayerFollowerCountResponse(
                playerApiId: playerID,
                fans: 12,
                following: false,
                shareUrl: nil
            )
        }

        didStartSecondFetch = true
        secondFetchStartedContinuation?.resume()
        secondFetchStartedContinuation = nil
        return await withCheckedContinuation { continuation in
            secondFetchContinuation = continuation
        }
    }

    func waitForSecondFetchToStart() async {
        guard !didStartSecondFetch else { return }
        await withCheckedContinuation { continuation in
            secondFetchStartedContinuation = continuation
        }
    }

    func finishSecondFetch() {
        secondFetchContinuation?.resume(returning: PlayerFollowerCountResponse(
            playerApiId: 403_064,
            fans: 12,
            following: false,
            shareUrl: nil
        ))
        secondFetchContinuation = nil
    }

    func followPlayer(playerID: Int) async throws -> PlayerFollowResponse {
        PlayerFollowResponse(
            playerApiId: playerID,
            following: true,
            fans: 13,
            created: true
        )
    }

    func unfollowPlayer(playerID _: Int) async throws -> PlayerUnfollowResponse {
        throw URLError(.unsupportedURL)
    }
}
