import Foundation
import XCTest
@testable import AcademyWatch

final class AuthenticationAPIClientTests: XCTestCase {
    func testProtectedRequestAttachesBearerAndInvalidatesSessionBeforeReturning401() async throws {
        let spy = AuthenticationSessionSpy.shared
        spy.reset()

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [AuthenticationStubURLProtocol.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }

        let client = APIClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test/api")),
            session: session,
            authSession: spy
        )

        do {
            let _: WatchlistIDsResponse = try await client.fetchWatchlistIDs()
            XCTFail("Expected the protected request to return HTTP 401")
        } catch {
            let snapshot = spy.snapshot()
            XCTAssertEqual(snapshot.authorizationHeader, "Bearer test-token")
            XCTAssertEqual(snapshot.cacheControlHeader, "no-store")
            XCTAssertEqual(snapshot.cachePolicy, .reloadIgnoringLocalCacheData)
            XCTAssertTrue(snapshot.didInvalidate, "Session invalidation must finish before the API error returns")

            guard case let APIClientError.server(statusCode, message) = error else {
                return XCTFail("Expected parsed APIClientError.server, got \(error)")
            }
            XCTAssertEqual(statusCode, 401)
            XCTAssertEqual(message, "invalid auth token")
        }
    }

    func test401ForOlderCredentialDoesNotInvalidateReplacementSession() async throws {
        let requestRecorder = AuthenticationSessionSpy.shared
        requestRecorder.reset()
        let authSession = ReplacingAuthenticationSession(
            requestCredential: "token-a",
            replacementCredential: "token-b"
        )

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [AuthenticationStubURLProtocol.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }

        let client = APIClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test/api")),
            session: session,
            authSession: authSession
        )

        do {
            let _: WatchlistIDsResponse = try await client.fetchWatchlistIDs()
            XCTFail("Expected the protected request to return HTTP 401")
        } catch {
            guard case APIClientError.server(statusCode: 401, message: "invalid auth token") = error else {
                return XCTFail("Expected parsed HTTP 401, got \(error)")
            }
        }

        let snapshot = await authSession.snapshot()
        XCTAssertEqual(requestRecorder.snapshot().authorizationHeader, "Bearer token-a")
        XCTAssertEqual(snapshot.credential, "token-b")
        XCTAssertFalse(snapshot.didInvalidate)
    }

    @MainActor
    func testStaleVerificationCannotReplaceNewerSession() async throws {
        let authClient = DelayedVerificationAuthClient()
        let tokenStore = InMemoryTokenStore()
        let manager = AuthManager(authClient: authClient, tokenStore: tokenStore)

        let olderAttempt = Task {
            try await manager.verifyCode(email: "a@example.com", code: "code-for-a")
        }
        await authClient.waitUntilOlderAttemptStarts()

        _ = try await manager.verifyCode(email: "b@example.com", code: "code-for-b")
        await authClient.releaseOlderAttempt()

        do {
            _ = try await olderAttempt.value
            XCTFail("Expected the superseded verification to be ignored")
        } catch is CancellationError {
            // Superseded verification attempts are intentionally cancellation-shaped.
        } catch {
            XCTFail("Expected CancellationError, got \(error)")
        }

        XCTAssertEqual(manager.email, "b@example.com")
        XCTAssertEqual(tokenStore.snapshot(), "token-b")
    }

    @MainActor
    func testAuthManagerIgnoresInvalidationForOlderCredential() async throws {
        let tokenStore = InMemoryTokenStore(initialToken: "token-a")
        let manager = AuthManager(
            authClient: ImmediateVerificationAuthClient(token: "token-b"),
            tokenStore: tokenStore
        )

        _ = try await manager.verifyCode(email: "b@example.com", code: "code-for-b")
        await manager.invalidate(credential: "token-a")
        let currentToken = await manager.accessToken()

        XCTAssertTrue(manager.isAuthenticated)
        XCTAssertEqual(manager.email, "b@example.com")
        XCTAssertEqual(currentToken, "token-b")
        XCTAssertEqual(tokenStore.snapshot(), "token-b")
    }

    @MainActor
    func testSignOutRetriesKeychainDeletionThenPurgesProtectedCache() throws {
        let tokenStore = InMemoryTokenStore(initialToken: "test-token", deletionFailures: 1)
        let (cache, request) = try protectedCacheFixture()
        let manager = AuthManager(
            authClient: ImmediateVerificationAuthClient(token: "unused"),
            tokenStore: tokenStore,
            protectedResponseCache: cache
        )

        manager.signOut()

        XCTAssertFalse(manager.isAuthenticated)
        XCTAssertNil(manager.signOutErrorMessage)
        XCTAssertEqual(tokenStore.deletionAttemptCount, 2)
        XCTAssertNil(tokenStore.snapshot())
        XCTAssertNil(cache.cachedResponse(for: request))
    }

    @MainActor
    func testSignOutSurfacesPersistentKeychainDeletionFailureWithoutFinalizingLogout() async throws {
        let tokenStore = InMemoryTokenStore(initialToken: "test-token", deletionFailures: 2)
        let (cache, request) = try protectedCacheFixture()
        let manager = AuthManager(
            authClient: ImmediateVerificationAuthClient(token: "unused"),
            tokenStore: tokenStore,
            protectedResponseCache: cache
        )

        manager.signOut()
        let currentToken = await manager.accessToken()

        XCTAssertTrue(manager.isAuthenticated)
        XCTAssertEqual(currentToken, "test-token")
        XCTAssertNotNil(manager.signOutErrorMessage)
        XCTAssertEqual(tokenStore.deletionAttemptCount, 2)
        XCTAssertEqual(tokenStore.snapshot(), "test-token")
        XCTAssertNotNil(cache.cachedResponse(for: request))
    }

    private func protectedCacheFixture() throws -> (URLCache, URLRequest) {
        let cache = URLCache(memoryCapacity: 1_024_000, diskCapacity: 0)
        let url = try XCTUnwrap(URL(string: "https://example.test/api/scout/watchlist"))
        let request = URLRequest(url: url)
        let response = try XCTUnwrap(
            URLResponse(
                url: url,
                mimeType: "application/json",
                expectedContentLength: 2,
                textEncodingName: "utf-8"
            )
        )
        cache.storeCachedResponse(
            CachedURLResponse(response: response, data: Data("{}".utf8)),
            for: request
        )
        XCTAssertNotNil(cache.cachedResponse(for: request))
        return (cache, request)
    }

}

private final class AuthenticationSessionSpy: AuthSessionProtocol, @unchecked Sendable {
    static let shared = AuthenticationSessionSpy()

    private let lock = NSLock()
    private var authorizationHeader: String?
    private var cacheControlHeader: String?
    private var cachePolicy: URLRequest.CachePolicy?
    private var didInvalidate = false

    func accessToken() async -> String? {
        "test-token"
    }

    func invalidate() async {
        setInvalidated()
    }

    func record(
        authorizationHeader: String?,
        cacheControlHeader: String?,
        cachePolicy: URLRequest.CachePolicy
    ) {
        lock.lock()
        self.authorizationHeader = authorizationHeader
        self.cacheControlHeader = cacheControlHeader
        self.cachePolicy = cachePolicy
        lock.unlock()
    }

    func snapshot() -> (
        authorizationHeader: String?,
        cacheControlHeader: String?,
        cachePolicy: URLRequest.CachePolicy?,
        didInvalidate: Bool
    ) {
        lock.lock()
        defer { lock.unlock() }
        return (authorizationHeader, cacheControlHeader, cachePolicy, didInvalidate)
    }

    func reset() {
        lock.lock()
        authorizationHeader = nil
        cacheControlHeader = nil
        cachePolicy = nil
        didInvalidate = false
        lock.unlock()
    }

    private func setInvalidated() {
        lock.lock()
        didInvalidate = true
        lock.unlock()
    }
}

private final class AuthenticationStubURLProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool {
        true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        AuthenticationSessionSpy.shared.record(
            authorizationHeader: request.value(forHTTPHeaderField: "Authorization"),
            cacheControlHeader: request.value(forHTTPHeaderField: "Cache-Control"),
            cachePolicy: request.cachePolicy
        )

        guard let url = request.url,
              let response = HTTPURLResponse(
                  url: url,
                  statusCode: 401,
                  httpVersion: "HTTP/1.1",
                  headerFields: ["Content-Type": "application/json"]
              )
        else {
            client?.urlProtocol(self, didFailWithError: URLError(.badURL))
            return
        }

        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(#"{"error":"invalid auth token"}"#.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

private actor ReplacingAuthenticationSession: AuthSessionProtocol {
    private var credential: String?
    private let replacementCredential: String
    private var didReplaceCredential = false
    private var didInvalidate = false

    init(requestCredential: String, replacementCredential: String) {
        credential = requestCredential
        self.replacementCredential = replacementCredential
    }

    func accessToken() async -> String? {
        let requestCredential = credential
        if !didReplaceCredential {
            credential = replacementCredential
            didReplaceCredential = true
        }
        return requestCredential
    }

    func invalidate() async {
        credential = nil
        didInvalidate = true
    }

    func invalidate(credential failingCredential: String) async {
        guard credential == failingCredential else { return }
        await invalidate()
    }

    func snapshot() -> (credential: String?, didInvalidate: Bool) {
        (credential, didInvalidate)
    }
}

private actor DelayedVerificationAuthClient: AuthAPIClientProtocol {
    private var olderAttemptContinuation: CheckedContinuation<AuthTokenResponse, Error>?
    private var didStartOlderAttempt = false
    private var startWaiters: [CheckedContinuation<Void, Never>] = []

    func requestLoginCode(email _: String) async throws -> LoginCodeResponse {
        LoginCodeResponse(message: "sent")
    }

    func verifyLoginCode(email: String, code _: String) async throws -> AuthTokenResponse {
        if email == "a@example.com" {
            return try await withCheckedThrowingContinuation { continuation in
                olderAttemptContinuation = continuation
                didStartOlderAttempt = true
                startWaiters.forEach { $0.resume() }
                startWaiters = []
            }
        }

        return Self.response(token: "token-b")
    }

    func waitUntilOlderAttemptStarts() async {
        if didStartOlderAttempt { return }
        await withCheckedContinuation { continuation in
            startWaiters.append(continuation)
        }
    }

    func releaseOlderAttempt() {
        olderAttemptContinuation?.resume(returning: Self.response(token: "token-a"))
        olderAttemptContinuation = nil
    }

    private static func response(token: String) -> AuthTokenResponse {
        AuthTokenResponse(
            message: "signed in",
            role: "user",
            displayName: nil,
            displayNameConfirmed: false,
            token: token,
            expiresIn: 3600
        )
    }
}

private struct ImmediateVerificationAuthClient: AuthAPIClientProtocol {
    let token: String

    func requestLoginCode(email _: String) async throws -> LoginCodeResponse {
        LoginCodeResponse(message: "sent")
    }

    func verifyLoginCode(email _: String, code _: String) async throws -> AuthTokenResponse {
        AuthTokenResponse(
            message: "signed in",
            role: "user",
            displayName: nil,
            displayNameConfirmed: false,
            token: token,
            expiresIn: 3600
        )
    }
}

private final class InMemoryTokenStore: TokenStoreProtocol, @unchecked Sendable {
    private let lock = NSLock()
    private var token: String?
    private var remainingDeletionFailures: Int
    private var deletionAttempts = 0

    init(initialToken: String? = nil, deletionFailures: Int = 0) {
        token = initialToken
        remainingDeletionFailures = deletionFailures
    }

    func loadToken() throws -> String? {
        snapshot()
    }

    func saveToken(_ token: String) throws {
        lock.lock()
        self.token = token
        lock.unlock()
    }

    func deleteToken() throws {
        lock.lock()
        defer { lock.unlock() }
        deletionAttempts += 1
        if remainingDeletionFailures > 0 {
            remainingDeletionFailures -= 1
            throw StubTokenStoreError.deletionFailed
        }
        token = nil
    }

    func snapshot() -> String? {
        lock.lock()
        defer { lock.unlock() }
        return token
    }

    var deletionAttemptCount: Int {
        lock.lock()
        defer { lock.unlock() }
        return deletionAttempts
    }
}

private enum StubTokenStoreError: LocalizedError {
    case deletionFailed

    var errorDescription: String? {
        "The test credential could not be deleted."
    }
}
