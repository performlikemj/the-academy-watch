import XCTest
@testable import AcademyWatch

final class SeasonDecodingTests: XCTestCase {
    func testDecodesCapturedSeasonDirectory() throws {
        let directory: SeasonDirectory = try decodeFixture(named: "seasons_directory")

        XCTAssertEqual(directory.currentSeason, 2025)
        XCTAssertEqual(directory.bounds, SeasonBounds(min: 2007, max: 2026))
        XCTAssertEqual(directory.seasons.map(\.season), [2026, 2025, 2024])
        XCTAssertEqual(directory.seasons[1].label, "2025/26")
        XCTAssertTrue(directory.seasons[1].isCurrent)
        XCTAssertFalse(directory.seasons[0].hasRollup)
    }

    func testDecodesRecentFixturesEnvelope() throws {
        let response: PlayerRecentFixturesResponse = try decodeFixture(
            named: "player_recent_fixtures_envelope"
        )

        XCTAssertEqual(response.season, 2024)
        XCTAssertEqual(response.matches.count, 1)
        XCTAssertEqual(response.matches.first?.fixtureId, 51)
    }

    func testDecodesRecentFixturesBareArrayFallback() throws {
        let response: PlayerRecentFixturesResponse = try decodeFixture(
            named: "player_recent_fixtures_outfielder"
        )

        XCTAssertNil(response.season)
        XCTAssertEqual(response.matches.count, 23)
        XCTAssertEqual(response.matches.first?.fixtureId, 51)
    }

    func testHistoricalRollupKeepsTotalsVisibleWithoutMatchRows() throws {
        let stats: PlayerSeasonStats = try decodeFixture(named: "player_season_stats_rollup")
        let fixtures: PlayerRecentFixturesResponse = try decodeFixture(
            named: "player_recent_fixtures_empty_envelope"
        )

        XCTAssertTrue(stats.hasHeadlineData)
        XCTAssertEqual(stats.appearances, 52)
        XCTAssertEqual(stats.minutes, 4_281)
        XCTAssertEqual(stats.saves, 0)
        XCTAssertEqual(stats.cleanSheets, 0)
        XCTAssertEqual(stats.provenance?.badgeText, "journey · season totals")
        XCTAssertTrue(fixtures.matches.isEmpty)
    }

    func testDecodesLiveLankshearSeasonRollupWithNullClubName() throws {
        let stats: PlayerSeasonStats = try decodeFixture(
            named: "player_season_stats_lankshear_live"
        )

        XCTAssertEqual(stats.playerId, 393_195)
        XCTAssertEqual(stats.source, "season-rollup")
        XCTAssertEqual(stats.clubs.count, 1)
        XCTAssertEqual(stats.clubs.first?.teamName, "Club 70")
        XCTAssertFalse(stats.clubs[0].matchesCurrentClub(named: "Middlesbrough"))
    }

    func testDecodesLiveLankshearPlayerDetailEndpoints() throws {
        let profile: PlayerProfile = try decodeFixture(named: "player_profile_lankshear_live")
        let recentFixtures: PlayerRecentFixturesResponse = try decodeFixture(
            named: "player_recent_fixtures_lankshear_live"
        )

        XCTAssertEqual(profile.playerId, 393_195)
        XCTAssertEqual(profile.currentClubName, "Middlesbrough")
        XCTAssertEqual(recentFixtures.matches.count, 6)
        XCTAssertEqual(recentFixtures.matches.first?.playerApiId, 393_195)
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
