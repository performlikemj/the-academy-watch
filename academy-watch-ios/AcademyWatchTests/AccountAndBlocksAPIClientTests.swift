import Foundation
import XCTest
@testable import AcademyWatch

final class AccountAndBlocksAPIClientTests: XCTestCase {
    override func setUp() {
        super.setUp()
        ReviewBlockersURLProtocol.reset()
    }

    func testAccountDeletionAPISendsConfirmationBody() async throws {
        ReviewBlockersURLProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.path, "/api/account/delete")
            XCTAssertEqual(try jsonBody(request)["confirm"] as? String, "DELETE")
            return response(
                request,
                status: 200,
                body: #"{"deleted":true,"deletion_event_id":14,"completed_at":"2026-08-09T10:00:00Z"}"#
            )
        }
        let client = makeClient()

        let result = try await client.deleteAccount()

        XCTAssertTrue(result.deleted)
        XCTAssertEqual(result.deletionEventId, 14)
    }

    @MainActor
    func testSuccessfulDeleteClearsStoredTokenAndAuthState() async throws {
        let tokenStore = DeletionTestTokenStore(token: "fixture-token")
        let manager = AuthManager(
            authClient: DeletionTestAuthClient(),
            tokenStore: tokenStore
        )

        try await manager.deleteAccount(using: SuccessfulDeletionClient())
        let currentToken = await manager.accessToken()

        XCTAssertFalse(manager.isAuthenticated)
        XCTAssertNil(currentToken)
        XCTAssertNil(tokenStore.token)
        XCTAssertEqual(tokenStore.deleteCount, 1)
        XCTAssertEqual(
            manager.accountDeletionConfirmationMessage,
            "Your account and associated personal data were deleted."
        )
    }

    func testBlocksAPIMethodsUseLiveContractAndAcceptNoContent() async throws {
        let recorder = BlocksRequestRecorder()
        ReviewBlockersURLProtocol.handler = { request in
            let body = jsonBodyIfPresent(request) ?? [:]
            recorder.record(method: request.httpMethod ?? "", path: request.url?.path ?? "", body: body)

            if request.httpMethod == "GET" {
                return response(
                    request,
                    status: 200,
                    body: #"{"blocks":[{"blocked_user_id":81,"display_name":"Jordan Taylor","created_at":"2026-08-08T10:00:00Z"}]}"#
                )
            }
            return response(request, status: 204, body: "")
        }
        let client = makeClient()

        try await client.blockUser(accountID: 81)
        let blocks = try await client.fetchBlockedUsers()
        try await client.unblockUser(accountID: 81)

        XCTAssertEqual(blocks.blocks.first?.accountId, 81)
        XCTAssertEqual(blocks.blocks.first?.displayName, "Jordan Taylor")
        let snapshot = recorder.snapshot()
        XCTAssertEqual(snapshot.map(\.method), ["POST", "GET", "DELETE"])
        XCTAssertEqual(snapshot.map(\.path), ["/api/blocks", "/api/blocks", "/api/blocks/81"])
        XCTAssertEqual(snapshot[0].body["account_id"] as? Int, 81)
    }

    func testBlockedContactErrorsUseSameNeutralMessageRegardlessOfServerDetail() {
        let blockedByViewer = APIClientError.codedServer(
            statusCode: 403,
            message: "viewer blocked counterpart",
            code: "messaging_unavailable",
            cooldownDays: nil
        )
        let blockedByCounterpart = APIClientError.codedServer(
            statusCode: 403,
            message: "counterpart blocked viewer",
            code: "messaging_unavailable",
            cooldownDays: nil
        )

        XCTAssertEqual(
            ContactPrivacyMessage.message(for: blockedByViewer),
            ContactPrivacyMessage.exchangeUnavailable
        )
        XCTAssertEqual(
            ContactPrivacyMessage.message(for: blockedByCounterpart),
            ContactPrivacyMessage.exchangeUnavailable
        )
        XCTAssertEqual(
            ContactPrivacyMessage.blockActionMessage(
                for: APIClientError.codedServer(
                    statusCode: 503,
                    message: "table unavailable",
                    code: "blocks_unavailable",
                    cooldownDays: nil
                )
            ),
            ContactPrivacyMessage.blockingUnavailable
        )
    }

    private func makeClient() -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ReviewBlockersURLProtocol.self]
        return APIClient(
            baseURL: URL(string: "https://example.test/api")!,
            session: URLSession(configuration: configuration)
        )
    }
}

private final class BlocksRequestRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var requests: [(method: String, path: String, body: [String: Any])] = []

    func record(method: String, path: String, body: [String: Any]) {
        lock.lock()
        requests.append((method, path, body))
        lock.unlock()
    }

    func snapshot() -> [(method: String, path: String, body: [String: Any])] {
        lock.lock()
        defer { lock.unlock() }
        return requests
    }
}

private final class ReviewBlockersURLProtocol: URLProtocol, @unchecked Sendable {
    static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    static func reset() {
        handler = nil
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        do {
            let handler = try XCTUnwrap(Self.handler)
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            if !data.isEmpty { client?.urlProtocol(self, didLoad: data) }
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

private func jsonBody(_ request: URLRequest) throws -> [String: Any] {
    let data = try XCTUnwrap(requestBodyData(request))
    return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
}

private func jsonBodyIfPresent(_ request: URLRequest) -> [String: Any]? {
    guard let data = requestBodyData(request) else { return nil }
    return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
}

private func requestBodyData(_ request: URLRequest) -> Data? {
    if let body = request.httpBody { return body }
    guard let stream = request.httpBodyStream else { return nil }

    stream.open()
    defer { stream.close() }
    var data = Data()
    let bufferSize = 1_024
    var buffer = [UInt8](repeating: 0, count: bufferSize)
    while stream.hasBytesAvailable {
        let count = stream.read(&buffer, maxLength: bufferSize)
        guard count >= 0 else { return nil }
        if count == 0 { break }
        data.append(buffer, count: count)
    }
    return data.isEmpty ? nil : data
}

private func response(
    _ request: URLRequest,
    status: Int,
    body: String
) -> (HTTPURLResponse, Data) {
    let response = HTTPURLResponse(
        url: request.url!,
        statusCode: status,
        httpVersion: nil,
        headerFields: ["Content-Type": "application/json"]
    )!
    return (response, Data(body.utf8))
}

private final class DeletionTestTokenStore: TokenStoreProtocol, @unchecked Sendable {
    var token: String?
    var deleteCount = 0

    init(token: String?) {
        self.token = token
    }

    func loadToken() throws -> String? { token }
    func saveToken(_ token: String) throws { self.token = token }
    func deleteToken() throws {
        deleteCount += 1
        token = nil
    }
}

private struct DeletionTestAuthClient: AuthAPIClientProtocol {
    func requestLoginCode(email _: String) async throws -> LoginCodeResponse {
        LoginCodeResponse(message: "sent")
    }

    func verifyLoginCode(email _: String, code _: String) async throws -> AuthTokenResponse {
        throw URLError(.unsupportedURL)
    }
}

private struct SuccessfulDeletionClient: AccountDeletionAPIClientProtocol {
    func deleteAccount() async throws -> AccountDeletionResponse {
        AccountDeletionResponse(deleted: true, deletionEventId: 1, completedAt: "2026-08-09T10:00:00Z")
    }
}
