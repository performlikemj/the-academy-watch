import Foundation
import XCTest
@testable import AcademyWatch

final class ScoutResponseCacheTests: XCTestCase {
    func testPlayersRoundTripOnDiskAndFiltersProduceDistinctKeys() async throws {
        let cacheRoot = makeTemporaryCacheRoot()
        defer { try? FileManager.default.removeItem(at: cacheRoot) }

        let expected: ScoutPlayersResponse = try decodeFixture(named: "scout_players")
        let request = ScoutPlayersRequest(
            page: 1,
            perPage: 25,
            search: nil,
            position: nil,
            status: nil,
            maximumAge: nil,
            sort: "contributions",
            order: .descending
        )
        let key = ScoutPlayersCacheKey(phase: .all, request: request)

        let writer = ScoutResponseCache(directoryURL: cacheRoot)
        await writer.savePlayers(expected, for: key)

        let reader = ScoutResponseCache(directoryURL: cacheRoot)
        let restored = await reader.loadPlayers(for: key)
        XCTAssertEqual(restored, expected)

        let filteredRequest = ScoutPlayersRequest(
            page: request.page,
            perPage: request.perPage,
            search: request.search,
            position: request.position,
            status: request.status,
            maximumAge: 21,
            sort: request.sort,
            order: request.order
        )
        let filteredKey = ScoutPlayersCacheKey(phase: .all, request: filteredRequest)
        XCTAssertNotEqual(filteredKey, key)
        let filteredMiss = await reader.loadPlayers(for: filteredKey)
        XCTAssertNil(filteredMiss)
    }

    func testLeaderboardsRoundTripOnDiskAndPhasesProduceDistinctKeys() async throws {
        let cacheRoot = makeTemporaryCacheRoot()
        defer { try? FileManager.default.removeItem(at: cacheRoot) }

        let expected: ScoutLeaderboardsResponse = try decodeFixture(named: "scout_leaderboards_gk")
        let request = ScoutLeaderboardsRequest(
            phase: .goalkeepers,
            limit: 5,
            position: "Goalkeeper",
            status: nil,
            maximumAge: nil
        )
        let key = ScoutLeaderboardsCacheKey(phase: .goalkeepers, request: request)

        let writer = ScoutResponseCache(directoryURL: cacheRoot)
        await writer.saveLeaderboards(expected, for: key)

        let reader = ScoutResponseCache(directoryURL: cacheRoot)
        let restored = await reader.loadLeaderboards(for: key)
        XCTAssertEqual(restored, expected)

        let differentPhaseKey = ScoutLeaderboardsCacheKey(phase: .defense, request: request)
        XCTAssertNotEqual(differentPhaseKey, key)
        let differentPhaseMiss = await reader.loadLeaderboards(for: differentPhaseKey)
        XCTAssertNil(differentPhaseMiss)
    }

    func testOldOrIncompatibleCachePayloadIsDiscardedWithoutThrowing() async throws {
        let cacheRoot = makeTemporaryCacheRoot()
        defer { try? FileManager.default.removeItem(at: cacheRoot) }

        let expected: ScoutPlayersResponse = try decodeFixture(named: "scout_players")
        let request = ScoutPlayersRequest(
            page: 1,
            perPage: 25,
            search: nil,
            position: nil,
            status: nil,
            maximumAge: nil,
            sort: "contributions",
            order: .descending
        )
        let key = ScoutPlayersCacheKey(phase: .all, request: request)
        let writer = ScoutResponseCache(directoryURL: cacheRoot)
        await writer.savePlayers(expected, for: key)

        let cacheDirectory = cacheRoot.appendingPathComponent(
            "ScoutResponseCache-v\(ScoutResponseCache.modelSchemaVersion)",
            isDirectory: true
        )
        let cacheFile = try XCTUnwrap(
            FileManager.default.contentsOfDirectory(
                at: cacheDirectory,
                includingPropertiesForKeys: nil
            ).first
        )
        let originalData = try Data(contentsOf: cacheFile)
        var envelope = try XCTUnwrap(
            JSONSerialization.jsonObject(with: originalData) as? [String: Any]
        )

        envelope["schemaVersion"] = ScoutResponseCache.modelSchemaVersion - 1
        try JSONSerialization.data(withJSONObject: envelope).write(to: cacheFile, options: .atomic)
        let oldSchemaResult = await ScoutResponseCache(directoryURL: cacheRoot).loadPlayers(for: key)
        XCTAssertNil(oldSchemaResult)

        envelope["schemaVersion"] = ScoutResponseCache.modelSchemaVersion
        envelope["payload"] = ["players": "P4b-incompatible-shape"]
        try JSONSerialization.data(withJSONObject: envelope).write(to: cacheFile, options: .atomic)
        let incompatibleResult = await ScoutResponseCache(directoryURL: cacheRoot).loadPlayers(for: key)
        XCTAssertNil(incompatibleResult)
    }

    private func makeTemporaryCacheRoot() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent(
            "ScoutResponseCacheTests-\(UUID().uuidString)",
            isDirectory: true
        )
    }

    private func decodeFixture<Response: Decodable>(named name: String) throws -> Response {
        let fixtureURL = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: name, withExtension: "json")
        )
        let data = try Data(contentsOf: fixtureURL)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Response.self, from: data)
    }
}
