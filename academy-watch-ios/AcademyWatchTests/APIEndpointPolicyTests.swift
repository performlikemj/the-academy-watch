import XCTest
@testable import AcademyWatch

@MainActor
final class APIEndpointPolicyTests: XCTestCase {
    func testResolverBuildAndHostMatrix() throws {
        let contexts: [(String, APIEndpointPolicy.Context)] = [
            ("Debug simulator", .init(debug: true, simulator: true, testHost: false)),
            ("Debug device", .init(debug: true, simulator: false, testHost: false)),
            ("Debug test host", .init(debug: true, simulator: true, testHost: true)),
            ("Release test host", .init(debug: false, simulator: false, testHost: true)),
            ("Release simulator", .init(debug: false, simulator: true, testHost: false)),
            ("Release device", .init(debug: false, simulator: false, testHost: false)),
        ]
        for (label, context) in contexts {
            if context.permitsProduction {
                XCTAssertEqual(try APIEndpointPolicy.resolve(override: nil, context: context, offlineFixture: false), .init(string: "https://api.theacademywatch.com/api"), label)
            } else {
                XCTAssertThrowsError(try APIEndpointPolicy.resolve(override: nil, context: context, offlineFixture: false), label)
                XCTAssertThrowsError(try APIEndpointPolicy.resolve(override: APIEndpointPolicy.production.absoluteString, context: context, offlineFixture: true), label)
            }
            for allowed in [APIEndpointPolicy.staging.absoluteString, "http://127.0.0.1:5011/api", "http://localhost/api", "http://[::1]:5011/api"] {
                XCTAssertEqual(try APIEndpointPolicy.resolve(override: allowed, context: context, offlineFixture: false).absoluteString, allowed, label)
            }
            for rejected in ["", "not a URL", "http://127.0.0.1:5011/wrong", "http://127.0.0.1/api?x=1", "http://127.0.0.1/api#x", "http://user:pass@127.0.0.1/api", "https://basecamp.tail37b60.ts.net/api", "http://basecamp.tail37b60.ts.net:15443/api", "https://example.com/api", "https://api.theacademywatch.com.evil.test/api"] {
                XCTAssertThrowsError(try APIEndpointPolicy.resolve(override: rejected, context: context, offlineFixture: true), "\(label): \(rejected)")
            }
            if context.debug && context.simulator {
                XCTAssertEqual(try APIEndpointPolicy.resolve(override: nil, context: context, offlineFixture: true), APIEndpointPolicy.offline)
            } else if !context.permitsProduction {
                XCTAssertThrowsError(try APIEndpointPolicy.resolve(override: nil, context: context, offlineFixture: true))
            }
        }
    }

    func testRejectedClientsNeverStartReadWarmupOrStreamingTransport() async {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [EndpointRequestSpy.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }
        EndpointRequestSpy.count = 0
        for raw in [APIEndpointPolicy.production.absoluteString, "http://localhost/wrong", "https://example.com/api"] {
            let client = APIClient(baseURL: URL(string: raw)!, session: session)
            do { _ = try await client.golSuggestions(); XCTFail("Read accepted \(raw)") }
            catch { XCTAssertTrue(error is APIEndpointPolicy.ConfigurationError) }
            await client.warmUp()
            do {
                try await client.streamGol(.init(message: "Hello", messages: [], sessionID: "session")) { _ in XCTFail() }
                XCTFail("Stream accepted \(raw)")
            } catch { XCTAssertTrue(error is APIEndpointPolicy.ConfigurationError) }
            XCTAssertThrowsError(try APIClient.golRequest(baseURL: URL(string: raw)!, token: "secret", question: .init(message: "Hello", messages: [], sessionID: "session")))
        }
        XCTAssertEqual(EndpointRequestSpy.count, 0)
        XCTAssertNotEqual(APIClient.defaultBaseURL.host, APIEndpointPolicy.production.host)
        print("I1F10 production guard: Debug/test host inert; rejected read, warm-up and stream requests=0")
    }

    func testStubAndOfflineExceptionsCannotAllowProduction() throws {
        let context = APIEndpointPolicy.Context(debug: true, simulator: true, testHost: true)
        XCTAssertThrowsError(try APIEndpointPolicy.validate(APIEndpointPolicy.production, context: context, stubTransport: true, offlineFixture: true))
        try APIEndpointPolicy.validate(URL(string: "https://example.test/api")!, context: context, stubTransport: true)
        XCTAssertThrowsError(try APIEndpointPolicy.validate(URL(string: "https://example.test/api")!, context: context))
    }

    func testRedirectCannotChangeOriginToProduction() {
        let session = URLSession(configuration: .ephemeral)
        defer { session.invalidateAndCancel() }
        let task = session.dataTask(with: APIEndpointPolicy.staging.appendingPathComponent("features"))
        let response = HTTPURLResponse(url: task.originalRequest!.url!, statusCode: 302, httpVersion: nil, headerFields: nil)!
        APIOriginRedirectGuard().urlSession(session, task: task, willPerformHTTPRedirection: response,
            newRequest: URLRequest(url: APIEndpointPolicy.production)) { request in XCTAssertNil(request) }
    }
}

private final class EndpointRequestSpy: URLProtocol {
    static var count = 0
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.count += 1
        client?.urlProtocol(self, didFailWithError: URLError(.cannotConnectToHost))
    }
    override func stopLoading() {}
}
