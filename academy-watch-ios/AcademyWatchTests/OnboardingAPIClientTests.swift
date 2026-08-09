import Foundation
import XCTest
@testable import AcademyWatch

final class OnboardingAPIClientTests: XCTestCase {
    override func tearDown() {
        OnboardingTestURLProtocol.reset()
        super.tearDown()
    }

    func testOnboardingRequestsMatchLiveBackendContracts() async throws {
        let recorder = OnboardingRequestRecorder()
        OnboardingTestURLProtocol.setHandler { request in
            recorder.record(request)
            switch request.url?.path {
            case "/api/local-players":
                return Self.json(#"{"player":{"id":41,"display_name":"Maya Okafor","birth_year":2004,"position":"Midfielder","country":"England","city":"Birmingham","club_name":"Northside Academy","status":"pending","provenance":"user","created_at":null},"claim":{"id":91,"local_player_id":41,"relationship_type":"player","status":"pending","verification_code":"VERIFY-1","verification_status":"unverified"}}"#)
            case "/api/clubs/claim":
                return Self.json(#"{"claim":{"id":22,"team_api_id":55,"local_club_id":null,"club_name":"Northside FC","role_title":"Academy director","message":"Official account","status":"pending","verification_code":"CLUB-1","verification_proof_url":null,"verification_status":"unverified","verification_note":null,"created_at":null}}"#)
            case "/api/scout/player-search":
                return Self.json(#"{"players":[{"player_api_id":900001,"name":"Global Player","age":20,"nationality":"Japan","photo":null,"club_name":"Tokyo Academy","tracked":false,"shadow":false}]}"#)
            case "/api/scout/lists/73/follows":
                return Self.json(#"{"follow":{"id":301,"kind":"player","selector":{"player_api_id":900001},"label":"Global Player","note":null,"created_at":null},"shadow_created":true}"#)
            default:
                throw OnboardingRequestTestError.unexpectedPath(request.url?.path)
            }
        }

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [OnboardingTestURLProtocol.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }
        let client = APIClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test/api")),
            session: session
        )

        _ = try await client.createLocalPlayer(
            LocalPlayerSubmission(
                displayName: "Maya Okafor",
                relationshipType: .player,
                position: "Midfielder",
                clubName: "Northside Academy",
                country: "England",
                city: "Birmingham",
                birthYear: 2004
            )
        )
        _ = try await client.submitClubClaim(
            ClubClaimSubmission(
                subject: .apiTeam(APIClubSearchResult(teamApiId: 55, name: "Northside FC", country: "England")),
                roleTitle: "Academy director",
                message: "Official account"
            )
        )
        let worldwide = try await client.searchWorldwidePlayers(query: "Global Player")
        _ = try await client.addWorldwidePlayerFollow(listID: 73, player: try XCTUnwrap(worldwide.players.first))

        let requests = recorder.requests
        XCTAssertEqual(requests.map(\.method), ["POST", "POST", "GET", "POST"])
        XCTAssertEqual(requests.map(\.path), [
            "/api/local-players",
            "/api/clubs/claim",
            "/api/scout/player-search",
            "/api/scout/lists/73/follows",
        ])

        let local = try XCTUnwrap(requests[0].json)
        XCTAssertEqual(local["display_name"] as? String, "Maya Okafor")
        XCTAssertEqual(local["relationship_type"] as? String, "player")
        XCTAssertEqual(local["club_name"] as? String, "Northside Academy")
        XCTAssertEqual(local["birth_year"] as? Int, 2004)

        let club = try XCTUnwrap(requests[1].json)
        XCTAssertEqual(club["team_api_id"] as? Int, 55)
        XCTAssertNil(club["local_club_id"])
        XCTAssertEqual(club["role_title"] as? String, "Academy director")
        XCTAssertEqual(club["message"] as? String, "Official account")

        XCTAssertEqual(requests[2].queryItems, [URLQueryItem(name: "q", value: "Global Player")])

        let follow = try XCTUnwrap(requests[3].json)
        XCTAssertEqual(follow["kind"] as? String, "player")
        XCTAssertEqual((follow["selector"] as? [String: Any])?["player_api_id"] as? Int, 900_001)
        let seed = try XCTUnwrap(follow["seed"] as? [String: Any])
        XCTAssertEqual(seed["name"] as? String, "Global Player")
        XCTAssertEqual(seed["club_name"] as? String, "Tokyo Academy")
        XCTAssertEqual(seed["nationality"] as? String, "Japan")
    }

    func testScoutLocalAddOmitsClaimantRelationshipKey() throws {
        let submission = LocalPlayerSubmission(
            displayName: "Community Player",
            relationshipType: nil,
            position: nil,
            clubName: "Community FC",
            country: nil,
            city: nil,
            birthYear: nil
        )
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: encoder.encode(submission)) as? [String: Any]
        )

        XCTAssertNil(object["relationship_type"])
        XCTAssertEqual(object["display_name"] as? String, "Community Player")
        XCTAssertEqual(object["club_name"] as? String, "Community FC")
    }

    private static func json(_ value: String) -> Data { Data(value.utf8) }
}

private struct RecordedOnboardingRequest {
    let method: String
    let path: String
    let queryItems: [URLQueryItem]
    let json: [String: Any]?

    init(_ request: URLRequest) {
        method = request.httpMethod ?? ""
        path = request.url?.path ?? ""
        queryItems = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems ?? []
        if let body = onboardingRequestBodyData(request) {
            json = try? JSONSerialization.jsonObject(with: body) as? [String: Any]
        } else {
            json = nil
        }
    }
}

private func onboardingRequestBodyData(_ request: URLRequest) -> Data? {
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

private final class OnboardingRequestRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [RecordedOnboardingRequest] = []

    var requests: [RecordedOnboardingRequest] {
        lock.lock()
        defer { lock.unlock() }
        return storage
    }

    func record(_ request: URLRequest) {
        lock.lock()
        storage.append(RecordedOnboardingRequest(request))
        lock.unlock()
    }
}

private final class OnboardingTestURLProtocol: URLProtocol {
    typealias Handler = @Sendable (URLRequest) throws -> Data
    private static let lock = NSLock()
    nonisolated(unsafe) private static var handler: Handler?

    static func setHandler(_ value: @escaping Handler) {
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
        do {
            guard let handler else { throw OnboardingRequestTestError.missingHandler }
            let data = try handler(request)
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: "HTTP/1.1",
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

private enum OnboardingRequestTestError: Error {
    case missingHandler
    case unexpectedPath(String?)
}
