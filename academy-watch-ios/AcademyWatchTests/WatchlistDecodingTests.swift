import XCTest
@testable import AcademyWatch

final class WatchlistDecodingTests: XCTestCase {
    func testDecodesCapturedPlayerInsideWatchlistEnvelope() throws {
        let response: WatchlistResponse = try decodeFixture(named: "watchlist_response")

        XCTAssertEqual(response.entries.count, 2)
        XCTAssertTrue(response.digestOptIn)
        XCTAssertEqual(response.scoutTier, "free")

        let active = response.entries[0]
        XCTAssertEqual(active.playerApiId, 386_828)
        XCTAssertEqual(active.note, "Explosive in tight spaces; revisit after the next window.")
        XCTAssertEqual(active.createdAt, "2026-07-15T05:00:00+00:00")
        XCTAssertEqual(active.player?.playerId, 386_828)
        XCTAssertEqual(active.player?.playerName, "Lamine Yamal")
        XCTAssertEqual(active.player?.recentForm?.count, 5)
        XCTAssertNil(active.player?.saves)

        let inactive = response.entries[1]
        XCTAssertEqual(inactive.playerApiId, 999_999)
        XCTAssertNil(inactive.note)
        XCTAssertNil(inactive.player)
    }

    func testDecodesWatchlistIDsEnvelope() throws {
        let response: WatchlistIDsResponse = try decodeFixture(named: "watchlist_ids")

        XCTAssertEqual(response.playerIds, [386_828, 999_999])
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
