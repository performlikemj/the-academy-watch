import XCTest
@testable import AcademyWatch

final class ScoutPlayerDecodingTests: XCTestCase {
    func testDecodesCapturedScoutPlayersResponse() throws {
        let fixtureURL = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: "scout_players", withExtension: "json")
        )
        let data = try Data(contentsOf: fixtureURL)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let response = try decoder.decode(ScoutPlayersResponse.self, from: data)

        XCTAssertEqual(response.page, 1)
        XCTAssertEqual(response.perPage, 25)
        XCTAssertEqual(response.players.count, 25)
        XCTAssertEqual(response.total, 3_544)
        XCTAssertEqual(response.totalPages, 142)

        let first = try XCTUnwrap(response.players.first)
        XCTAssertEqual(first.playerId, 386_828)
        XCTAssertEqual(first.playerName, "Lamine Yamal")
        XCTAssertTrue(first.hasDetailedStats)
        XCTAssertEqual(first.recentForm?.count, 5)
        XCTAssertEqual(first.displayValue(for: .shots), "119")
        XCTAssertEqual(first.displayValue(for: .saves), "—")

        XCTAssertNil(response.players.first(where: { $0.playerId == 283_058 })?.position)

        let effectiveStatusPlayer = try XCTUnwrap(
            response.players.first(where: { $0.playerId == 335_335 })
        )
        XCTAssertNotEqual(effectiveStatusPlayer.status, effectiveStatusPlayer.pathwayStatus)
        XCTAssertNotNil(effectiveStatusPlayer.ownerTeamName)
    }
}
