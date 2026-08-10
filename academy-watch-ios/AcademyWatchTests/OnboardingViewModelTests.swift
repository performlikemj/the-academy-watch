import XCTest
@testable import AcademyWatch

final class OnboardingViewModelTests: XCTestCase {
    func testClubConsoleDestinationUsesCanonicalWebURL() {
        XCTAssertEqual(LegalDestination.clubConsole.url.absoluteString, "https://theacademywatch.com/my-club")
        XCTAssertFalse(LegalDestination.legalCases.contains(.clubConsole))
    }

    @MainActor
    func testLocalPlayerValidationMirrorsBackendBoundsAndCarriesClubName() {
        let viewModel = LocalPlayerFormViewModel(context: .claimant, apiClient: OnboardingStubClient())
        viewModel.displayName = "M"
        viewModel.birthYear = "2021"
        viewModel.position = String(repeating: "P", count: 51)
        viewModel.clubName = String(repeating: "C", count: 201)
        viewModel.country = String(repeating: "N", count: 101)
        viewModel.city = String(repeating: "Y", count: 121)

        XCTAssertFalse(viewModel.validate())
        XCTAssertNotNil(viewModel.error(for: .displayName))
        XCTAssertNotNil(viewModel.error(for: .birthYear))
        XCTAssertNotNil(viewModel.error(for: .position))
        XCTAssertNotNil(viewModel.error(for: .clubName))
        XCTAssertNotNil(viewModel.error(for: .country))
        XCTAssertNotNil(viewModel.error(for: .city))

        viewModel.displayName = "Maya Okafor"
        viewModel.birthYear = "2004"
        viewModel.position = "Midfielder"
        viewModel.clubName = "Northside Academy"
        viewModel.country = "England"
        viewModel.city = "Birmingham"
        viewModel.relationship = .guardian

        XCTAssertTrue(viewModel.validate())
        XCTAssertEqual(viewModel.submission.clubName, "Northside Academy")
        XCTAssertEqual(viewModel.submission.relationshipType, .guardian)
        XCTAssertEqual(viewModel.submission.birthYear, 2004)
    }

    @MainActor
    func testScoutLocalAddUsesServerDefaultInsteadOfInventingRelationship() {
        let viewModel = LocalPlayerFormViewModel(context: .scoutAdd, apiClient: OnboardingStubClient())
        viewModel.displayName = "Community Player"
        viewModel.clubName = "Community FC"

        XCTAssertTrue(viewModel.validate())
        XCTAssertNil(viewModel.submission.relationshipType)
        XCTAssertEqual(viewModel.submission.clubName, "Community FC")
    }

    @MainActor
    func testClubClaimValidationEnforcesSelectionRoleAndEvidenceLimits() {
        let viewModel = ClubClaimViewModel(apiClient: OnboardingStubClient())
        viewModel.roleTitle = "A"
        viewModel.message = String(repeating: "x", count: 1_001)

        XCTAssertFalse(viewModel.validateClaim())
        XCTAssertNotNil(viewModel.error(for: .club))
        XCTAssertNotNil(viewModel.error(for: .roleTitle))
        XCTAssertNotNil(viewModel.error(for: .message))

        viewModel.select(.localClub(LocalClubSearchResult(
            id: 44,
            name: "Community FC",
            country: "Japan",
            city: "Tokyo",
            level: "academy",
            status: "verified"
        )))
        viewModel.roleTitle = "Academy director"
        viewModel.message = "Roster lead"

        XCTAssertTrue(viewModel.validateClaim())
    }

    @MainActor
    func testWorldwideSearchRequiresThreeCharacters() async {
        let viewModel = WorldwidePlayerSearchViewModel(apiClient: OnboardingStubClient())
        viewModel.query = "Li"

        await viewModel.search()

        XCTAssertEqual(viewModel.errorMessage, "Type at least 3 characters to search worldwide.")
        XCTAssertFalse(viewModel.hasSearched)
    }
}

private actor OnboardingStubClient: OnboardingAPIClientProtocol {
    func createLocalPlayer(_ submission: LocalPlayerSubmission) async throws -> LocalPlayerCreateResponse {
        throw URLError(.unsupportedURL)
    }

    func fetchLocalPlayer(id: Int) async throws -> LocalPlayerResponse { throw URLError(.unsupportedURL) }
    func searchWorldwidePlayers(query: String) async throws -> WorldwidePlayerSearchResponse {
        WorldwidePlayerSearchResponse(players: [])
    }
    func addWorldwidePlayerFollow(listID: Int, player: WorldwidePlayer) async throws -> FollowResponse {
        throw URLError(.unsupportedURL)
    }
    func searchClubs(query: String) async throws -> ClubSearchResponse {
        ClubSearchResponse(apiTeams: [], localClubs: [])
    }
    func fetchMyClubClaims() async throws -> ClubClaimsResponse { ClubClaimsResponse(claims: []) }
    func submitClubClaim(_ submission: ClubClaimSubmission) async throws -> ClubClaimResponse {
        throw URLError(.unsupportedURL)
    }
    func verifyClubClaim(id: Int, proofURL: String) async throws -> ClubClaimResponse {
        throw URLError(.unsupportedURL)
    }
}
