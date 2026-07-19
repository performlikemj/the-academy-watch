import XCTest
@testable import AcademyWatch

final class FollowListDecodingTests: XCTestCase {
    func testDecodesCapturedListsWithEveryFollowKind() throws {
        let response: FollowListsResponse = try decodeFixture(named: "scout_follow_lists")

        let list = try XCTUnwrap(response.lists.first)
        XCTAssertEqual(response.lists.count, 1)
        XCTAssertEqual(list.id, 17)
        XCTAssertEqual(list.name, "South America shortlist")
        XCTAssertEqual(list.cadence, "weekly")
        XCTAssertTrue(list.isActive)
        XCTAssertFalse(list.isDefault)
        XCTAssertEqual(list.playerCap, 40)
        XCTAssertEqual(list.followCount, 5)
        XCTAssertEqual(
            list.follows.map(\.kind),
            [.player, .academyClub, .geo, .geo, .query]
        )

        let player = list.follows[0]
        XCTAssertEqual(player.selector.playerApiId, 1_001)
        XCTAssertEqual(player.label, "Alfie Striker")
        XCTAssertEqual(player.note, "Review after the next international window")
        XCTAssertTrue(list.containsPlayer(1_001))

        let academy = list.follows[1]
        XCTAssertEqual(academy.selector.teamId, 1)
        XCTAssertEqual(academy.label, "Club academy: Manchester United")

        let playingIn = list.follows[2]
        XCTAssertEqual(playingIn.selector.countries, ["Brazil", "Argentina"])
        XCTAssertEqual(playingIn.selector.match, "playing_in")

        let nationality = list.follows[3]
        XCTAssertEqual(nationality.selector.countries, ["Japan"])
        XCTAssertEqual(nationality.selector.match, "nationality")

        let query = list.follows[4]
        XCTAssertEqual(query.label, "Filter: Attacker, age -19, 270+ mins")
        XCTAssertNil(query.selector.playerApiId)
        XCTAssertNil(query.selector.teamId)
        XCTAssertNil(query.selector.countries)
        XCTAssertNil(query.selector.match)
    }

    func testDecodesResolvedTrackedAndShadowPlayersWithNulls() throws {
        let response: ResolvedFollowListResponse = try decodeFixture(
            named: "scout_follow_list_resolve"
        )

        XCTAssertEqual(response.total, 2)
        XCTAssertEqual(response.players.map(\.playerApiId), [1_001, 2_001])

        let tracked = response.players[0]
        XCTAssertEqual(tracked.playerName, "Alfie Striker")
        XCTAssertEqual(tracked.source, "tracked")
        XCTAssertEqual(tracked.teamName, "Rio FC")
        XCTAssertEqual(tracked.status, "on_loan")
        XCTAssertEqual(
            tracked.photoURL?.absoluteString,
            "https://media.api-sports.io/football/players/1001.png"
        )

        let shadow = response.players[1]
        XCTAssertEqual(shadow.playerName, "Shadow Prospect")
        XCTAssertEqual(shadow.source, "shadow")
        XCTAssertEqual(shadow.teamName, "Boca")
        XCTAssertNil(shadow.status)
        XCTAssertNil(shadow.photo)
        XCTAssertNil(shadow.photoURL)
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
