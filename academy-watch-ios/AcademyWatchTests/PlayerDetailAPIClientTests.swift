import Foundation
import XCTest
@testable import AcademyWatch

final class PlayerDetailAPIClientTests: XCTestCase {
    override func tearDown() {
        PlayerDetailTestURLProtocol.reset()
        super.tearDown()
    }

    func testPlayerDetailRequestsUseExactPublicEndpointPaths() async throws {
        let playerID = 403_064
        let expectedPaths = [
            "/api/players/403064/profile",
            "/api/players/403064/season-stats",
            "/api/players/403064/stats",
            "/api/players/403064/journey",
            "/api/players/403064/availability",
        ]
        let fixturesByPath = [
            expectedPaths[0]: try fixtureData(named: "player_profile_outfielder"),
            expectedPaths[1]: try fixtureData(named: "player_season_stats_outfielder"),
            expectedPaths[2]: try fixtureData(named: "player_recent_fixtures_outfielder"),
            expectedPaths[3]: try fixtureData(named: "player_journey_outfielder"),
            expectedPaths[4]: try fixtureData(named: "player_availability_outfielder"),
        ]
        let recorder = PlayerDetailRequestRecorder()

        PlayerDetailTestURLProtocol.setRequestHandler { request in
            guard let url = request.url else {
                throw PlayerDetailAPIClientTestError.missingRequestURL
            }
            recorder.record(path: url.path)

            guard request.httpMethod == "GET" else {
                throw PlayerDetailAPIClientTestError.unexpectedMethod(request.httpMethod)
            }
            guard request.value(forHTTPHeaderField: "Accept") == "application/json" else {
                throw PlayerDetailAPIClientTestError.missingJSONAcceptHeader
            }
            guard let fixture = fixturesByPath[url.path] else {
                throw PlayerDetailAPIClientTestError.unexpectedPath(url.path)
            }
            return fixture
        }

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [PlayerDetailTestURLProtocol.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }

        let client = APIClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test/api")),
            session: session
        )

        let profile = try await client.fetchPlayerProfile(playerID: playerID)
        let seasonStats = try await client.fetchPlayerSeasonStats(playerID: playerID)
        let recentFixtures = try await client.fetchPlayerRecentFixtures(playerID: playerID)
        let journey = try await client.fetchPlayerJourney(playerID: playerID)
        let availability = try await client.fetchPlayerAvailability(playerID: playerID)

        XCTAssertEqual(profile.playerId, playerID)
        XCTAssertEqual(seasonStats.playerId, playerID)
        XCTAssertFalse(recentFixtures.isEmpty)
        XCTAssertEqual(journey.playerId, playerID)
        XCTAssertEqual(availability.playerId, playerID)
        XCTAssertEqual(recorder.paths, expectedPaths)
    }

    private func fixtureData(named name: String) throws -> Data {
        let fixtureURL = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: name, withExtension: "json")
        )
        return try Data(contentsOf: fixtureURL)
    }
}

private final class PlayerDetailTestURLProtocol: URLProtocol {
    typealias RequestHandler = (URLRequest) throws -> Data

    private static let lock = NSLock()
    private static var requestHandler: RequestHandler?

    static func setRequestHandler(_ requestHandler: @escaping RequestHandler) {
        lock.lock()
        self.requestHandler = requestHandler
        lock.unlock()
    }

    static func reset() {
        lock.lock()
        requestHandler = nil
        lock.unlock()
    }

    override class func canInit(with request: URLRequest) -> Bool {
        true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        Self.lock.lock()
        let requestHandler = Self.requestHandler
        Self.lock.unlock()

        guard let requestHandler else {
            client?.urlProtocol(
                self,
                didFailWithError: PlayerDetailAPIClientTestError.missingRequestHandler
            )
            return
        }

        do {
            let data = try requestHandler(request)
            guard let url = request.url,
                  let response = HTTPURLResponse(
                      url: url,
                      statusCode: 200,
                      httpVersion: "HTTP/1.1",
                      headerFields: ["Content-Type": "application/json"]
                  )
            else {
                throw PlayerDetailAPIClientTestError.missingRequestURL
            }

            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

private final class PlayerDetailRequestRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var recordedPaths: [String] = []

    var paths: [String] {
        lock.lock()
        defer { lock.unlock() }
        return recordedPaths
    }

    func record(path: String) {
        lock.lock()
        recordedPaths.append(path)
        lock.unlock()
    }
}

private enum PlayerDetailAPIClientTestError: Error {
    case missingRequestHandler
    case missingRequestURL
    case missingJSONAcceptHeader
    case unexpectedMethod(String?)
    case unexpectedPath(String)
}
