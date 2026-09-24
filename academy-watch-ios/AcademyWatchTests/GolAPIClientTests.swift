import XCTest

@testable import AcademyWatch

@MainActor
final class GolAPIClientTests: XCTestCase {
    func testHTTPStatusMappingThroughTransportAndCredentialInvalidation() async throws {
        for (status, code) in [
            (402, "credits_exhausted"), (403, "scout_pro_required"), (409, "in_flight"),
            (409, "client_msg_id_reused"), (409, "recovery_exhausted"), (401, "unauthorized"),
        ] {
            GolURLProtocol.status = status
            GolURLProtocol.body = Data("{\"error\":\"\(code)\",\"top_up_path\":\"/account/billing\"}".utf8)
            let session = makeSession()
            defer { session.invalidateAndCancel() }
            let auth = GolAuthSpy()
            let client = APIClient(
                baseURL: URL(string: "https://example.test/api")!, session: session, authSession: auth)
            do {
                try await client.streamGol(.init(message: "Question", messages: [], sessionID: "session")) {
                    _ in
                    XCTFail("An HTTP error must not become chat content")
                }
                XCTFail("Expected rejection")
            } catch let error as GolFailure {
                XCTAssertEqual(error, .http(status, code: code))
            }
            let invalidated = await auth.invalidated
            XCTAssertEqual(invalidated, status == 401)
            XCTAssertEqual(
                GolURLProtocol.request?.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
        }
    }

    func testRealAsyncBytesTransportStreamsEvents() async throws {
        GolURLProtocol.status = 200
        GolURLProtocol.body = Data(
            "event: token\ndata: {\"content\":\"Hello ⚽\"}\n\nevent: done\ndata: {}\n\n".utf8)
        let session = makeSession()
        defer { session.invalidateAndCancel() }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api")!, session: session, authSession: GolAuthSpy())
        let model = GolChatViewModel(client: client)
        model.send("Hello")
        for _ in 0..<200 where model.isStreaming { try await Task.sleep(for: .milliseconds(5)) }
        XCTAssertFalse(model.isStreaming)
        XCTAssertEqual(model.messages.last?.content, "Hello ⚽")
        XCTAssertNil(model.failure)
    }

    private func makeSession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [GolURLProtocol.self]
        return URLSession(configuration: configuration)
    }
}

private actor GolAuthSpy: AuthSessionProtocol {
    var invalidated = false
    func accessToken() async -> String? { "test-token" }
    func invalidate() async { invalidated = true }
}

private final class GolURLProtocol: URLProtocol {
    static var status = 200
    static var body = Data()
    static var request: URLRequest?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.request = request
        let response = HTTPURLResponse(
            url: request.url!, statusCode: Self.status, httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": Self.status == 200 ? "text/event-stream" : "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        for byte in Self.body { client?.urlProtocol(self, didLoad: Data([byte])) }
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
