import XCTest
@testable import AcademyWatch

final class ShowcaseDecodingTests: XCTestCase {
    // Fixture provenance: `player_showcase.json` mirrors the anonymous public
    // dictionary assembled by GET `/api/players/<id>/showcase` in full-circle
    // `src/routes/showcase.py`. `player_showcase_owner.json` mirrors that same
    // route for an approved direct player owner, including `owner_dict()` and
    // `_claim_contract_payload()`; those fields are deliberately absent from
    // the public fixture.
    func testDecodesRouteSerializerFixtureWithoutMixingTrustTiers() throws {
        let showcase: PlayerShowcaseResponse = try decodeFixture("player_showcase")

        XCTAssertEqual(showcase.playerApiId, 403_064)
        XCTAssertEqual(showcase.claimStatus, "claimed")
        XCTAssertTrue(showcase.isClaimedProfile)

        let profile = try XCTUnwrap(showcase.selfReportedProfile)
        XCTAssertTrue(profile.selfReported)
        XCTAssertEqual(profile.bio, "An attack-minded left-back who looks to progress play early and recover with pace.")
        XCTAssertEqual(profile.positions, "Left-back, wing-back")
        XCTAssertEqual(profile.preferredFoot, "left")
        XCTAssertEqual(profile.heightCm, 181)
        XCTAssertNil(profile.id)
        XCTAssertNil(profile.status)
        XCTAssertNil(profile.updatedAt)
        XCTAssertNil(profile.contractStatus)
        XCTAssertNil(profile.currentClubName)
        XCTAssertNil(profile.clubProgramId)
        XCTAssertNil(profile.statusContradiction)
        XCTAssertNil(profile.contractAttestationReviewStatus)

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

    func testDecodesOwnerOnlyContractAttestationAndPendingReviewState() throws {
        let showcase: PlayerShowcaseResponse = try decodeFixture("player_showcase_owner")
        let profile = try XCTUnwrap(showcase.profile)

        XCTAssertEqual(profile.id, 33)
        XCTAssertEqual(profile.status, .pending)
        XCTAssertEqual(profile.updatedAt, "2026-07-17T10:30:00+00:00")
        XCTAssertEqual(profile.contractStatus, .contracted)
        XCTAssertEqual(profile.currentClubName, "Moderated FC")
        XCTAssertEqual(profile.clubProgramId, 901)
        XCTAssertEqual(profile.statusContradiction, false)
        XCTAssertEqual(profile.contractAttestationReviewStatus, .pending)
        XCTAssertEqual(
            profile.contractAttestation,
            PlayerContractAttestation(
                contractStatus: .contracted,
                currentClubName: "Moderated FC",
                clubProgramId: 901
            )
        )
    }

    func testYouTubeParserRecognizesBackendSupportedHTTPSShapesOnly() {
        XCTAssertEqual(YouTubeVideoID.parse("https://youtu.be/abc123"), "abc123")
        XCTAssertEqual(YouTubeVideoID.parse("https://www.youtube.com/embed/abc123"), "abc123")
        XCTAssertEqual(YouTubeVideoID.parse("https://m.youtube.com/shorts/abc123"), "abc123")
        XCTAssertNil(YouTubeVideoID.parse("http://www.youtube.com/watch?v=abc123"))
        XCTAssertNil(YouTubeVideoID.parse("https://example.com/watch?v=abc123"))
    }

    private func decodeFixture<Response: Decodable>(_ name: String) throws -> Response {
        let fixtureURL = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: name, withExtension: "json")
        )
        let data = try Data(contentsOf: fixtureURL)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Response.self, from: data)
    }
}
