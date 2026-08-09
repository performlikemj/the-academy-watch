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
