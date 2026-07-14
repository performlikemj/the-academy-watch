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
            XCTAssertTrue(snapshot.didInvalidate, "Session invalidation must finish before the API error returns")

            guard case let APIClientError.server(statusCode, message) = error else {
                return XCTFail("Expected parsed APIClientError.server, got \(error)")
            }
            XCTAssertEqual(statusCode, 401)
            XCTAssertEqual(message, "invalid auth token")
        }
    }
}

private final class AuthenticationSessionSpy: AuthSessionProtocol, @unchecked Sendable {
    static let shared = AuthenticationSessionSpy()

    private let lock = NSLock()
    private var authorizationHeader: String?
    private var didInvalidate = false

    func accessToken() async -> String? {
        "test-token"
    }

    func invalidate() async {
        setInvalidated()
    }

    func record(authorizationHeader: String?) {
        lock.lock()
        self.authorizationHeader = authorizationHeader
        lock.unlock()
    }

    func snapshot() -> (authorizationHeader: String?, didInvalidate: Bool) {
        lock.lock()
        defer { lock.unlock() }
        return (authorizationHeader, didInvalidate)
    }

    func reset() {
        lock.lock()
        authorizationHeader = nil
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
            authorizationHeader: request.value(forHTTPHeaderField: "Authorization")
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
