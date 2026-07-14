import XCTest
@testable import AcademyWatch

final class ScoutLeaderboardDecodingTests: XCTestCase {
    func testDecodesCapturedGoalkeeperLeaderboardsByBoardKey() throws {
        let fixtureURL = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: "scout_leaderboards_gk", withExtension: "json")
        )
        let data = try Data(contentsOf: fixtureURL)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let response = try decoder.decode(ScoutLeaderboardsResponse.self, from: data)

        XCTAssertEqual(response.phase, .goalkeepers)
        XCTAssertEqual(response.limit, 5)
        XCTAssertEqual(
            Set(response.leaderboards.keys),
            Set(["most_clean_sheets", "most_saves", "best_conceded_per90", "most_minutes"])
        )
        XCTAssertTrue(response.leaderboards.values.allSatisfy { $0.count == 5 })

        let bestConceded = try XCTUnwrap(response.leaderboards["best_conceded_per90"]?.first)
        XCTAssertEqual(bestConceded.playerName, "S. Ngapandouetnbu")
        XCTAssertEqual(bestConceded.position, "Goalkeeper")
        XCTAssertEqual(bestConceded.concededPer90, 0.8)
        XCTAssertEqual(bestConceded.cleanSheets, 10)
        XCTAssertNil(bestConceded.recentForm)

        let mostSaves = try XCTUnwrap(response.leaderboards["most_saves"]?.first)
        XCTAssertEqual(mostSaves.playerName, "C. Kelleher")
        XCTAssertEqual(mostSaves.saves, 84)
        XCTAssertEqual(mostSaves.savePct, 67.2)

        let zeroTackles = try XCTUnwrap(response.leaderboards["most_clean_sheets"]?[1])
        XCTAssertEqual(zeroTackles.tackles, 0)
        XCTAssertEqual(zeroTackles.displayValue(for: .tackles), "0")
    }
}
