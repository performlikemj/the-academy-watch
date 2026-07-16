import XCTest
@testable import AcademyWatch

final class ShowcaseDecodingTests: XCTestCase {
    func testDecodesRouteSerializerFixtureWithoutMixingTrustTiers() throws {
        let showcase = try decodeFixture()

        XCTAssertEqual(showcase.playerApiId, 403_064)
        XCTAssertEqual(showcase.claimStatus, "claimed")
        XCTAssertTrue(showcase.isClaimedProfile)

        let profile = try XCTUnwrap(showcase.selfReportedProfile)
        XCTAssertTrue(profile.selfReported)
        XCTAssertEqual(profile.bio, "An attack-minded left-back who looks to progress play early and recover with pace.")
        XCTAssertEqual(profile.positions, "Left-back, wing-back")
        XCTAssertEqual(profile.preferredFoot, "left")
        XCTAssertEqual(profile.heightCm, 181)

        XCTAssertEqual(showcase.approvedReel.map(\.id), ["41", "yt-9"])
        XCTAssertEqual(showcase.approvedReel[0].videoID, "Ryt6tidyYaI")
        XCTAssertEqual(
            showcase.approvedReel[0].videoURL?.absoluteString,
            "https://www.youtube.com/watch?v=Ryt6tidyYaI"
        )
        XCTAssertEqual(
            showcase.approvedReel[0].thumbnailURL?.absoluteString,
            "https://img.youtube.com/vi/Ryt6tidyYaI/hqdefault.jpg"
        )
        XCTAssertEqual(showcase.approvedReel[1].videoID, "bcoAMvp9ez8")

        let evidence = try XCTUnwrap(showcase.clubVerifiedFootage.first)
        XCTAssertTrue(evidence.verified)
        XCTAssertEqual(evidence.identitySource, "human_confirmed")
        XCTAssertEqual(evidence.minutesOnCamera, 88)
        XCTAssertEqual(evidence.coveragePercent, 72)
        XCTAssertTrue(showcase.hasContent)
    }

    func testYouTubeParserRecognizesBackendSupportedHTTPSShapesOnly() {
        XCTAssertEqual(YouTubeVideoID.parse("https://youtu.be/abc123"), "abc123")
        XCTAssertEqual(YouTubeVideoID.parse("https://www.youtube.com/embed/abc123"), "abc123")
        XCTAssertEqual(YouTubeVideoID.parse("https://m.youtube.com/shorts/abc123"), "abc123")
        XCTAssertNil(YouTubeVideoID.parse("http://www.youtube.com/watch?v=abc123"))
        XCTAssertNil(YouTubeVideoID.parse("https://example.com/watch?v=abc123"))
    }

    private func decodeFixture() throws -> PlayerShowcaseResponse {
        let fixtureURL = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: "player_showcase", withExtension: "json")
        )
        let data = try Data(contentsOf: fixtureURL)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(PlayerShowcaseResponse.self, from: data)
    }
}
