import XCTest
@testable import AcademyWatch

final class PlayerClaimFlowTests: XCTestCase {
    // Fixture provenance: `player_claims.json` mirrors
    // `PlayerProfileClaim.to_dict()` in full-circle `src/models/showcase.py`
    // plus the `player_name` added by GET `/api/me/claims` in
    // `src/routes/showcase.py`.
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
        XCTAssertEqual(claims.claims.first?.contractStatus, .freeAgent)
        XCTAssertNil(claims.claims.first?.currentClubName)
        XCTAssertNil(claims.claims.first?.clubProgramId)
        XCTAssertEqual(claims.claims.last?.contractStatus, .contracted)
        XCTAssertEqual(claims.claims.last?.currentClubName, "Academy Town FC")
        XCTAssertEqual(claims.claims.last?.clubProgramId, 901)
        let pendingClaim = try XCTUnwrap(claims.claims.last)
        XCTAssertFalse(pendingClaim.statusContradiction)

        let submitPayload = #"""
        {
          "claim": {
            "id": 14,
            "player_api_id": 700003,
            "user_account_id": 44,
            "relationship_type": "player",
            "status": "pending",
            "message": null,
            "contract_status": "unknown",
            "current_club_name": null,
            "club_program_id": null,
            "status_contradiction": false,
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
        XCTAssertEqual(submitted.claim.contractStatus, .unknown)
        XCTAssertNil(submitted.claim.playerName)
    }

    func testClaimAttestationEncodesEveryBackendStatusAndOptionalClubFields() throws {
        XCTAssertEqual(
            PlayerContractStatus.allCases.map(\.rawValue),
            ["free_agent", "contracted", "unknown"]
        )

        let linkedClub = try encodeObject(
            PlayerClaimSubmission(
                attestation: PlayerContractAttestation(
                    contractStatus: .contracted,
                    currentClubName: "Registry FC",
                    clubProgramId: 901
                )
            )
        )
        XCTAssertEqual(linkedClub["relationship_type"] as? String, "player")
        XCTAssertEqual(linkedClub["contract_status"] as? String, "contracted")
        XCTAssertEqual(linkedClub["current_club_name"] as? String, "Registry FC")
        XCTAssertEqual(linkedClub["club_program_id"] as? Int, 901)

        let unknownClub = try encodeObject(
            PlayerClaimSubmission(
                attestation: PlayerContractAttestation(contractStatus: .unknown)
            )
        )
        XCTAssertEqual(unknownClub["contract_status"] as? String, "unknown")
        XCTAssertTrue(unknownClub["current_club_name"] is NSNull)
        XCTAssertTrue(unknownClub["club_program_id"] is NSNull)
    }

    func testOwnerUpdatePreservesOrdinaryProfileAndExplicitlyClearsClubFields() throws {
        let ownerShowcase: PlayerShowcaseResponse = try decodeFixture("player_showcase_owner")
        let profile = try XCTUnwrap(ownerShowcase.profile)
        let body = try encodeObject(
            OwnerShowcaseProfileUpdate(
                profile: profile,
                attestation: PlayerContractAttestation(contractStatus: .freeAgent)
            )
        )

        XCTAssertEqual(body["bio"] as? String, profile.bio)
        XCTAssertEqual(body["positions"] as? String, profile.positions)
        XCTAssertEqual(body["preferred_foot"] as? String, profile.preferredFoot)
        XCTAssertEqual(body["height_cm"] as? Int, profile.heightCm)
        XCTAssertEqual(body["contract_status"] as? String, "free_agent")
        XCTAssertTrue(body["current_club_name"] is NSNull)
        XCTAssertTrue(body["club_program_id"] is NSNull)
    }

    @MainActor
    func testHappyPathLoadsEmptyStateThenSubmitsThisIsMeClaim() async {
        let client = SuccessfulPlayerClaimClient()
        let viewModel = PlayerClaimViewModel(playerID: 700_003, apiClient: client)

        await viewModel.load(isAuthenticated: true)
        XCTAssertTrue(viewModel.hasLoaded)
        XCTAssertNil(viewModel.claim)
        XCTAssertNil(viewModel.errorMessage)

        let attestation = PlayerContractAttestation(
            contractStatus: .contracted,
            currentClubName: "Academy Town FC"
        )
        await viewModel.submitThisIsMe(attestation: attestation)

        XCTAssertEqual(viewModel.claim?.playerApiId, 700_003)
        XCTAssertEqual(viewModel.claim?.relationshipType, "player")
        XCTAssertEqual(viewModel.claim?.status, .pending)
        XCTAssertEqual(viewModel.claim?.contractStatus, .contracted)
        XCTAssertEqual(viewModel.claim?.currentClubName, "Academy Town FC")
        XCTAssertFalse(viewModel.isSubmitting)
        XCTAssertNil(viewModel.errorMessage)
        let submittedPlayerIDs = await client.submittedPlayerIDs()
        XCTAssertEqual(submittedPlayerIDs, [700_003])
        let submittedAttestations = await client.submittedAttestations()
        XCTAssertEqual(submittedAttestations, [attestation])
    }

    @MainActor
    func testApprovedPlayerOwnerLoadsPrivateAttestationAndUsesModeratedProfileUpdate() async throws {
        let ownerShowcase: PlayerShowcaseResponse = try decodeFixture("player_showcase_owner")
        let claim = PlayerProfileClaim(
            id: 77,
            playerApiId: 403_064,
            userAccountId: 44,
            relationshipType: "player",
            status: .approved,
            message: nil,
            contractStatus: .freeAgent,
            currentClubName: nil,
            clubProgramId: nil,
            statusContradiction: false,
            reviewedBy: "reviewer@example.test",
            reviewedAt: "2026-07-17T09:00:00+00:00",
            createdAt: "2026-07-16T09:00:00+00:00",
            playerName: "H. Amass"
        )
        let claimClient = ApprovedOwnerClaimClient(claim: claim)
        let showcaseClient = OwnerShowcaseClient(response: ownerShowcase)
        let viewModel = PlayerClaimViewModel(
            playerID: 403_064,
            apiClient: claimClient,
            showcaseAPIClient: showcaseClient
        )

        await viewModel.load(isAuthenticated: true)

        XCTAssertTrue(viewModel.isApprovedPlayerOwner)
        XCTAssertTrue(viewModel.hasLoadedOwnerProfile)
        XCTAssertEqual(viewModel.currentOwnerAttestation?.contractStatus, .contracted)
        XCTAssertEqual(viewModel.currentOwnerAttestation?.currentClubName, "Moderated FC")
        XCTAssertEqual(viewModel.currentAttestationReviewStatus, .pending)
        XCTAssertTrue(viewModel.canEditOwnerAttestation)

        let update = PlayerContractAttestation(contractStatus: .freeAgent)
        let didUpdate = await viewModel.updateOwnerAttestation(update)

        XCTAssertTrue(didUpdate)
        let captured = await showcaseClient.capturedUpdate()
        XCTAssertEqual(captured?.playerID, 403_064)
        XCTAssertEqual(captured?.profile, ownerShowcase.profile)
        XCTAssertEqual(captured?.attestation, update)
    }

    private func decodeFixture<Response: Decodable>(_ name: String) throws -> Response {
        let fixtureURL = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: name, withExtension: "json")
        )
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Response.self, from: Data(contentsOf: fixtureURL))
    }

    private func encodeObject<Body: Encodable>(_ body: Body) throws -> [String: Any] {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(body)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }
}

private actor SuccessfulPlayerClaimClient: PlayerClaimAPIClientProtocol {
    private var submissions: [Int] = []
    private var attestations: [PlayerContractAttestation] = []

    func fetchMyProfileClaims() async throws -> PlayerClaimsResponse {
        PlayerClaimsResponse(claims: [])
    }

    func submitPlayerClaim(
        playerID: Int,
        attestation: PlayerContractAttestation
    ) async throws -> PlayerClaimResponse {
        submissions.append(playerID)
        attestations.append(attestation)
        return PlayerClaimResponse(
            claim: PlayerProfileClaim(
                id: 14,
                playerApiId: playerID,
                userAccountId: 44,
                relationshipType: "player",
                status: .pending,
                message: nil,
                contractStatus: attestation.contractStatus,
                currentClubName: attestation.currentClubName,
                clubProgramId: attestation.clubProgramId,
                statusContradiction: false,
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

    func submittedAttestations() -> [PlayerContractAttestation] {
        attestations
    }
}

private actor ApprovedOwnerClaimClient: PlayerClaimAPIClientProtocol {
    let claim: PlayerProfileClaim

    init(claim: PlayerProfileClaim) {
        self.claim = claim
    }

    func fetchMyProfileClaims() async throws -> PlayerClaimsResponse {
        PlayerClaimsResponse(claims: [claim])
    }

    func submitPlayerClaim(
        playerID: Int,
        attestation: PlayerContractAttestation
    ) async throws -> PlayerClaimResponse {
        PlayerClaimResponse(claim: claim)
    }
}

private actor OwnerShowcaseClient: ShowcaseAPIClientProtocol {
    struct CapturedUpdate: Equatable, Sendable {
        let playerID: Int
        let profile: ShowcaseProfile?
        let attestation: PlayerContractAttestation
    }

    let response: PlayerShowcaseResponse
    private var update: CapturedUpdate?

    init(response: PlayerShowcaseResponse) {
        self.response = response
    }

    func fetchPlayerShowcase(playerID: Int) async throws -> PlayerShowcaseResponse {
        response
    }

    func updateOwnerShowcaseProfile(
        playerID: Int,
        profile: ShowcaseProfile?,
        attestation: PlayerContractAttestation
    ) async throws -> ShowcaseProfileResponse {
        update = CapturedUpdate(
            playerID: playerID,
            profile: profile,
            attestation: attestation
        )
        guard let responseProfile = response.profile else {
            throw OwnerShowcaseClientError.missingProfile
        }
        return ShowcaseProfileResponse(profile: responseProfile)
    }

    func capturedUpdate() -> CapturedUpdate? {
        update
    }
}

private enum OwnerShowcaseClientError: Error {
    case missingProfile
}
