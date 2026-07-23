import XCTest
@testable import AcademyWatch

final class CompareModelsTests: XCTestCase {
    func testDecodesCapturedGoalkeeperAndOutfielderComparison() throws {
        let response: CompareResponse = try decodeFixture(named: "scout_compare_gk_outfielder")

        XCTAssertEqual(response.missingIds, [])
        XCTAssertEqual(response.players.map(\.profile.playerId), [145_060, 403_064])

        let goalkeeper = try XCTUnwrap(response.players.first)
        XCTAssertEqual(goalkeeper.profile.playerName, "S. Ngapandouetnbu")
        XCTAssertTrue(goalkeeper.profile.isGoalkeeper)
        XCTAssertEqual(goalkeeper.profile.clubName, "Montpellier")
        XCTAssertEqual(goalkeeper.totals.saves, 101)
        XCTAssertEqual(goalkeeper.totals.goalsConceded, 26)
        XCTAssertEqual(goalkeeper.totals.cleanSheets, 12)
        XCTAssertEqual(goalkeeper.totals.penaltySaved, 0)
        XCTAssertEqual(goalkeeper.per90.duelsWon, 0.71)
        XCTAssertEqual(goalkeeper.career?.firstTeamApps, 55)
        XCTAssertEqual(goalkeeper.availability?.totalAbsences, 0)
        XCTAssertNil(goalkeeper.availability?.lastReason)

        let outfielder = try XCTUnwrap(response.players.last)
        XCTAssertEqual(outfielder.profile.playerName, "H. Amass")
        XCTAssertFalse(outfielder.profile.isGoalkeeper)
        XCTAssertEqual(outfielder.profile.ownerTeamName, "Manchester United")
        XCTAssertNil(outfielder.totals.saves)
        XCTAssertNil(outfielder.totals.goalsConceded)
        XCTAssertNil(outfielder.totals.cleanSheets)
        XCTAssertNil(outfielder.totals.penaltySaved)
        XCTAssertEqual(outfielder.per90.goalContributions, 0.09)
        XCTAssertEqual(outfielder.career?.youthApps, 56)
        XCTAssertEqual(outfielder.availability?.lastReason, "Hamstring Injury")
    }

    func testBestValueHighlightingUsesMinimumForLowerIsBetterIncludingZero() {
        XCTAssertEqual(
            CompareHighlighting.highlightedIndices(
                in: [26, nil, 0, 0],
                lowerIsBetter: true
            ),
            Set([2, 3])
        )
        XCTAssertEqual(
            CompareHighlighting.highlightedIndices(
                in: [0, 0, nil],
                lowerIsBetter: false
            ),
            []
        )
        XCTAssertEqual(
            CompareHighlighting.highlightedIndices(
                in: [1, 3, 3],
                lowerIsBetter: false
            ),
            Set([1, 2])
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
