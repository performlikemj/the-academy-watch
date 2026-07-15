import XCTest
@testable import AcademyWatch

final class PlayerClaimFlowTests: XCTestCase {
    func testDecodesMyClaimsAndSubmitClaimSerializerShapes() throws {
        let fixtureURL = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: "player_claims", withExtension: "json")
        )
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let claims = try decoder.decode(
            PlayerClaimsResponse.self,
            from: Data(contentsOf: fixtureURL)
        )
        XCTAssertEqual(claims.claims.map(\.status), [.approved, .pending])
        XCTAssertEqual(claims.claims.first?.playerApiId, 700_001)
        XCTAssertEqual(claims.claims.first?.relationshipType, "player")
        XCTAssertEqual(claims.claims.first?.playerName, "Test Player")

        let submitPayload = #"""
        {
          "claim": {
            "id": 14,
            "player_api_id": 700003,
            "user_account_id": 44,
            "relationship_type": "player",
            "status": "pending",
            "message": null,
            "reviewed_by": null,
            "reviewed_at": null,
            "created_at": "2026-07-15T03:00:00+00:00"
          }
        }
        """#
        let submitted = try decoder.decode(
            PlayerClaimResponse.self,
            from: Data(submitPayload.utf8)
        )
        XCTAssertEqual(submitted.claim.playerApiId, 700_003)
        XCTAssertEqual(submitted.claim.status, .pending)
        XCTAssertNil(submitted.claim.playerName)
    }

    @MainActor
    func testHappyPathLoadsEmptyStateThenSubmitsThisIsMeClaim() async {
        let client = SuccessfulPlayerClaimClient()
        let viewModel = PlayerClaimViewModel(playerID: 700_003, apiClient: client)

        await viewModel.load(isAuthenticated: true)
        XCTAssertTrue(viewModel.hasLoaded)
        XCTAssertNil(viewModel.claim)
        XCTAssertNil(viewModel.errorMessage)

        await viewModel.submitThisIsMe()

        XCTAssertEqual(viewModel.claim?.playerApiId, 700_003)
        XCTAssertEqual(viewModel.claim?.relationshipType, "player")
        XCTAssertEqual(viewModel.claim?.status, .pending)
        XCTAssertFalse(viewModel.isSubmitting)
        XCTAssertNil(viewModel.errorMessage)
        let submittedPlayerIDs = await client.submittedPlayerIDs()
        XCTAssertEqual(submittedPlayerIDs, [700_003])
    }
}

private actor SuccessfulPlayerClaimClient: PlayerClaimAPIClientProtocol {
    private var submissions: [Int] = []

    func fetchMyProfileClaims() async throws -> PlayerClaimsResponse {
        PlayerClaimsResponse(claims: [])
    }

    func submitPlayerClaim(playerID: Int) async throws -> PlayerClaimResponse {
        submissions.append(playerID)
        return PlayerClaimResponse(
            claim: PlayerProfileClaim(
                id: 14,
                playerApiId: playerID,
                userAccountId: 44,
                relationshipType: "player",
                status: .pending,
                message: nil,
                reviewedBy: nil,
                reviewedAt: nil,
                createdAt: "2026-07-15T03:00:00+00:00",
                playerName: nil
            )
        )
    }

    func submittedPlayerIDs() -> [Int] {
        submissions
    }
}
