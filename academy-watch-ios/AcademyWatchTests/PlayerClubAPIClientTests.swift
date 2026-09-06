import XCTest

@testable import AcademyWatch

final class PlayerClubAPIClientTests: XCTestCase {
    override func tearDown() {
        ClubContractURLProtocol.handler = nil
        super.tearDown()
    }
    func testLocalBasicProfileUsesPatchAndOnlyPresentationFields() async throws {
        ClubContractURLProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/api/local-players/481/showcase/profile")
            XCTAssertEqual(request.httpMethod, "PATCH")
            let body = try Self.body(request)
            XCTAssertEqual(Set(body.keys), ["bio", "positions", "preferred_foot", "height_cm"])
            XCTAssertTrue(body["height_cm"] is NSNull)
            return #"{"profile":{"bio":"My story"}}"#
        }
        try await client().saveBasicProfile(
            playerID: -481, update: .init(bio: "My story", positions: "CM", preferredFoot: nil, heightCm: nil))
    }
    func testInvitationDecisionSendsEmptyObject() async throws {
        ClubContractURLProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/api/me/club-invitations/invite-id/accept")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertTrue(try Self.body(request).isEmpty)
            return #"{"invitation":{"status":"accepted"}}"#
        }
        try await client().decideClubInvitation(id: "invite-id", decision: .accept)
    }
    func testFeedbackPagePreservesSignedPlayerAndCursorAndAcceptsSummaryWithoutBody() async throws {
        ClubContractURLProtocol.handler = { request in
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.queryItems!
            XCTAssertTrue(query.contains(.init(name: "player_api_id", value: "-481")))
            XCTAssertTrue(query.contains(.init(name: "before", value: "cursor")))
            return
                #"{"feedback":[{"id":"f1","thread_id":"t1","revision":2,"player_api_id":-481,"program":{"id":44,"name":"Club"},"author":{"display_name":null},"title":"Next step","published_at":"2026-09-06T00:00:00Z","acknowledged_at":null,"can_acknowledge":true}],"next_before":"f1"}"#
        }
        let result = try await client().fetchPlayerFeedback(playerID: -481, before: "cursor")
        XCTAssertNil(result.feedback.first?.body)
        XCTAssertEqual(result.nextBefore, "f1")
    }
    func testPhotoCompletionUsesLocalPathAndNoUploadCredential() async throws {
        ClubContractURLProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/api/local-players/481/showcase/photos/9/complete")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertNil(request.url?.query)
            return #"{"media":{"id":9,"status":"pending","is_primary":false,"public_url":null,"review_note":null}}"#
        }
        let media = try await client().completeProfilePhoto(playerID: -481, mediaID: 9)
        XCTAssertEqual(media.status, "pending")
    }
    func testAccountSwitchStopsSubsequentUploadStepsBeforeNetwork() async throws {
        let session = ClubContractAuthSession()
        let bound = try await client(auth: session).boundToCurrentAccount()
        await session.switchAccount()
        ClubContractURLProtocol.handler = { _ in
            XCTFail("Must not send the prior account's photo completion under the new account")
            return "{}"
        }
        do {
            _ = try await bound.completeProfilePhoto(playerID: -481, mediaID: 9)
            XCTFail("Expected expired operation")
        } catch { XCTAssertEqual((error as? APIClientError)?.statusCode, 401) }
        let token = await session.accessToken()
        XCTAssertEqual(token, "new-account", "An obsolete operation must not sign out the new account")
    }
    private func client(auth: (any AuthSessionProtocol)? = nil) -> APIClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [ClubContractURLProtocol.self]
        return APIClient(
            baseURL: URL(string: "https://example.test/api")!, session: URLSession(configuration: config),
            authSession: auth)
    }
    private static func body(_ request: URLRequest) throws -> [String: Any] {
        let data: Data
        if let body = request.httpBody {
            data = body
        } else if let stream = request.httpBodyStream {
            stream.open()
            defer { stream.close() }
            var collected = Data()
            var buffer = [UInt8](repeating: 0, count: 1024)
            while stream.hasBytesAvailable {
                let count = stream.read(&buffer, maxLength: buffer.count)
                if count <= 0 { break }
                collected.append(buffer, count: count)
            }
            data = collected
        } else {
            data = Data()
        }
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }
}
private final class ClubContractURLProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var handler: ((URLRequest) throws -> String)?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}
    override func startLoading() {
        do {
            let body = try Self.handler?(request) ?? "{}"
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"]
            )!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(body.utf8))
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
}
private actor ClubContractAuthSession: AuthSessionProtocol {
    private var token: String? = "original-account"
    func accessToken() async -> String? { token }
    func invalidate() async { token = nil }
    func switchAccount() { token = "new-account" }
}
