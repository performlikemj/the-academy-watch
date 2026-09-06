import Foundation
import XCTest
@testable import AcademyWatch

final class PlayerStoryAPIClientTests: XCTestCase {
    override func tearDown() {
        PlayerStoryURLProtocol.reset()
        super.tearDown()
    }

    func testAccountExportUsesAuthenticatedGETAndReturnsResponseDataUnchanged() async throws {
        let expected = Data(#"{"account":{"email":"player@example.test"},"lists":[]}"#.utf8)
        PlayerStoryURLProtocol.setHandler { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.path, "/api/account/export")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer export-token")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "application/json")
            XCTAssertNil(request.httpBody)
            return (200, expected)
        }
        let client = makeClient(authSession: PlayerStoryAuthSession(token: "export-token"))

        let result = try await client.exportAccountData()

        XCTAssertEqual(result, expected, "The export must remain passthrough JSON Data")
    }

    func testTakedownRequestUsesPublicEndpointAndExactBackendPayload() async throws {
        PlayerStoryURLProtocol.setHandler { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.path, "/api/players/403064/takedown-request")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
            XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))

            let body = try XCTUnwrap(requestBodyData(request))
            let object = try XCTUnwrap(
                JSONSerialization.jsonObject(with: body) as? [String: String]
            )
            XCTAssertEqual(
                object,
                [
                    "requester_role": "guardian",
                    "contact_email": "guardian@example.test",
                    "statement": "I am authorized to act for this player.",
                ]
            )
            return (
                202,
                Data(#"{"message":"Your takedown request has been received and will be reviewed."}"#.utf8)
            )
        }
        let client = makeClient()

        try await client.submitPlayerTakedownRequest(
            playerID: 403_064,
            requesterRole: .guardian,
            contactEmail: "guardian@example.test",
            statement: "I am authorized to act for this player."
        )
    }

    func testDevelopmentUpdateUsesAuthenticatedRevisionRouteAndDecodesReview() async throws {
        PlayerStoryURLProtocol.setHandler { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.path, "/api/me/player-feedback/f1/progress")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer player-token")
            let bytes = try XCTUnwrap(requestBodyData(request))
            let object = try XCTUnwrap(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
            XCTAssertEqual(Set(object.keys), ["expected_version", "status", "note"])
            XCTAssertEqual(object["expected_version"] as? Int, 2)
            XCTAssertEqual(object["status"] as? String, "ready_for_review")
            XCTAssertEqual(object["note"] as? String, "Found the pass")
            return (200, Data(#"{"feedback":{"id":"f1","thread_id":"t1","revision":1,"player_api_id":-481,"program":{"id":44,"name":"Club"},"author":{"display_name":"Coach"},"title":"Scan","body":"Private","published_at":"2026-09-06T00:00:00Z","can_acknowledge":true,"development_action":{"focus":"Scan","practice":"Check shoulders","success":"Find the pass","review_on":null},"development_progress":{"version":3,"status":"ready_for_review","reflection":"Found the pass","coach_note":null,"updated_at":"2026-09-06T00:00:00Z","history":[]},"can_update_progress":true}}"#.utf8))
        }
        let client = makeClient(authSession: PlayerStoryAuthSession(token: "player-token"))
        let feedback = try await client.updateDevelopmentProgress(id: "f1", update: .init(expectedVersion: 2, status: "ready_for_review", note: "Found the pass"))
        XCTAssertEqual(feedback.developmentAction?.focus, "Scan")
        XCTAssertEqual(feedback.developmentProgress?.version, 3)
        XCTAssertEqual(feedback.canUpdateProgress, true)
    }

    private func makeClient(authSession: (any AuthSessionProtocol)? = nil) -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [PlayerStoryURLProtocol.self]
        return APIClient(
            baseURL: URL(string: "https://example.test/api")!,
            session: URLSession(configuration: configuration),
            authSession: authSession
        )
    }
}

private actor PlayerStoryAuthSession: AuthSessionProtocol {
    private var token: String?

    init(token: String) {
        self.token = token
    }

    func accessToken() -> String? { token }
    func invalidate() { token = nil }
}

private final class PlayerStoryURLProtocol: URLProtocol, @unchecked Sendable {
    typealias Handler = @Sendable (URLRequest) throws -> (Int, Data)

    private static let lock = NSLock()
    private static var handler: Handler?

    static func setHandler(_ handler: @escaping Handler) {
        lock.lock()
        self.handler = handler
        lock.unlock()
    }

    static func reset() {
        lock.lock()
        handler = nil
        lock.unlock()
    }

    override class func canInit(with _: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.lock.lock()
        let handler = Self.handler
        Self.lock.unlock()

        do {
            let handler = try XCTUnwrap(handler)
            let (status, data) = try handler(request)
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: status,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

private func requestBodyData(_ request: URLRequest) -> Data? {
    if let body = request.httpBody { return body }
    guard let stream = request.httpBodyStream else { return nil }

    stream.open()
    defer { stream.close() }
    var data = Data()
    var buffer = [UInt8](repeating: 0, count: 1_024)
    while stream.hasBytesAvailable {
        let count = stream.read(&buffer, maxLength: buffer.count)
        guard count >= 0 else { return nil }
        if count == 0 { break }
        data.append(buffer, count: count)
    }
    return data.isEmpty ? nil : data
}
