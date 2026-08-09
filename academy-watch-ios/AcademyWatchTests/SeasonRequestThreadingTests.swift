import Foundation
import XCTest
@testable import AcademyWatch

final class SeasonRequestThreadingTests: XCTestCase {
    override func tearDown() {
        SeasonRequestURLProtocol.handler = nil
        super.tearDown()
    }

    func testSeasonQueryThreadsThroughScoutAndPlayerReads() async throws {
        let recorder = SeasonRequestRecorder()
        let seasonStats = try fixtureData(named: "player_season_stats_outfielder")
        let recentFixtures = try fixtureData(named: "player_recent_fixtures_envelope")
        let availability = try fixtureData(named: "player_availability_outfielder")

        SeasonRequestURLProtocol.handler = { request in
            let url = try XCTUnwrap(request.url)
            recorder.record(url)
            switch url.path {
            case "/api/scout/players":
                return Data(#"{"players":[],"total":0,"page":1,"per_page":25,"total_pages":0,"season":2024}"#.utf8)
            case "/api/scout/leaderboards":
                return Data(#"{"leaderboards":{},"limit":5,"phase":"all","season":2024}"#.utf8)
            case "/api/scout/compare":
                return Data(#"{"players":[],"missing_ids":[],"season":2024}"#.utf8)
            case "/api/players/403064/season-stats":
                return seasonStats
            case "/api/players/403064/stats":
                return recentFixtures
            case "/api/players/403064/availability":
                return availability
            default:
                throw SeasonRequestTestError.unexpectedPath(url.path)
            }
        }

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [SeasonRequestURLProtocol.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }
        let client = APIClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test/api")),
            session: session
        )

        _ = try await client.fetchScoutPlayers(
            ScoutPlayersRequest(
                page: 1,
                perPage: 25,
                search: nil,
                position: nil,
                status: nil,
                maximumAge: nil,
                sort: "minutes",
                order: .descending,
                season: 2024
            )
        )
        _ = try await client.fetchScoutLeaderboards(
            ScoutLeaderboardsRequest(
                phase: .all,
                limit: 5,
                position: nil,
                status: nil,
                maximumAge: nil,
                season: 2024
            )
        )
        _ = try await client.fetchComparison(
            playerIDs: [403_064, 386_828],
            includeAvailability: true,
            season: 2024
        )
        _ = try await client.fetchPlayerSeasonStats(playerID: 403_064, season: 2024)
        _ = try await client.fetchPlayerRecentFixtures(playerID: 403_064, season: 2024)
        _ = try await client.fetchPlayerAvailability(playerID: 403_064, season: 2024)

        let urls = recorder.urls
        XCTAssertEqual(urls.count, 6)
        for url in urls {
            let seasonValue = URLComponents(url: url, resolvingAgainstBaseURL: false)?
                .queryItems?.first { $0.name == "season" }?.value
            XCTAssertEqual(seasonValue, "2024", "Missing season on \(url.path)")
        }
    }

    private func fixtureData(named name: String) throws -> Data {
        let fixtureURL = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: name, withExtension: "json")
        )
        return try Data(contentsOf: fixtureURL)
    }
}

private final class SeasonRequestURLProtocol: URLProtocol, @unchecked Sendable {
    static var handler: (@Sendable (URLRequest) throws -> Data)?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        do {
            guard let handler = Self.handler else { throw SeasonRequestTestError.missingHandler }
            let data = try handler(request)
            let response = try XCTUnwrap(
                HTTPURLResponse(
                    url: try XCTUnwrap(request.url),
                    statusCode: 200,
                    httpVersion: "HTTP/1.1",
                    headerFields: ["Content-Type": "application/json"]
                )
            )
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

private final class SeasonRequestRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var recordedURLs: [URL] = []

    var urls: [URL] {
        lock.withLock { recordedURLs }
    }

    func record(_ url: URL) {
        lock.withLock { recordedURLs.append(url) }
    }
}

private enum SeasonRequestTestError: Error {
    case missingHandler
    case unexpectedPath(String)
}
