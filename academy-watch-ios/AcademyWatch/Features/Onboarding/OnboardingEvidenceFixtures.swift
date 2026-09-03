import SwiftUI

#if DEBUG
enum OnboardingFixtureDestination: String {
    case playerSearch = "player-search"
    case createProfile = "create-profile"
    case pendingProfile = "pending-profile"
    case clubClaim = "club-claim"
    case approvedClubClaim = "approved-club-claim"
    case worldwideConfirmation = "worldwide-confirmation"
    case addGameSheet = "add-game-sheet"

    static func fromLaunchArguments(_ arguments: [String]) -> Self? {
        guard let index = arguments.firstIndex(of: "-onboardingFixture"),
              arguments.indices.contains(index + 1)
        else { return nil }
        return Self(rawValue: arguments[index + 1])
    }
}

@MainActor
struct OnboardingEvidenceRoot: View {
    let destination: OnboardingFixtureDestination
    @StateObject private var listsViewModel = FollowListsViewModel(apiClient: APIClient())
    @StateObject private var clubClaimViewModel: ClubClaimViewModel

    init(destination: OnboardingFixtureDestination) {
        self.destination = destination
        _clubClaimViewModel = StateObject(
            wrappedValue: ClubClaimViewModel(
                apiClient: APIClient(),
                fixtureClaims: [Self.approvedClubClaim]
            )
        )
    }

    var body: some View {
        NavigationStack {
            switch destination {
            case .playerSearch:
                PlayerOnboardingView(apiClient: APIClient())
            case .createProfile:
                LocalPlayerCreateView(context: .claimant, apiClient: APIClient())
            case .pendingProfile:
                LocalPlayerCreateView(
                    context: .claimant,
                    apiClient: APIClient(),
                    fixtureCreated: Self.pendingResponse
                )
            case .clubClaim:
                ClubOnboardingView(
                    apiClient: APIClient(),
                    initiallyShowsForm: true,
                    loadsOnAppear: false
                )
            case .approvedClubClaim:
                ClubClaimDetailView(claimID: Self.approvedClubClaim.id, viewModel: clubClaimViewModel)
            case .worldwideConfirmation:
                WorldwidePlayerSearchView(
                    purpose: .addToList,
                    apiClient: APIClient(),
                    viewModel: WorldwidePlayerSearchViewModel(
                        fixtureQuery: "Lamine Yamal",
                        fixturePlayers: [],
                        fixtureConfirmation: WorldwideFollowConfirmation(
                            playerName: "Lamine Yamal",
                            listName: "Summer shortlist",
                            shadowCreated: true
                        )
                    )
                )
            case .addGameSheet:
                AddGameSheet(
                    playerID: -481,
                    playerName: "Maya Okafor",
                    isGoalkeeper: false,
                    apiClient: APIClient(),
                    onSaved: { _ in }
                )
            }
        }
        .environmentObject(listsViewModel)
        .tint(AcademyColors.claretForeground)
    }

    private static let pendingResponse = LocalPlayerCreateResponse(
        player: LocalPlayer(
            id: 481,
            displayName: "Maya Okafor",
            birthYear: 2004,
            position: "Central midfielder",
            country: "England",
            city: "Birmingham",
            clubName: "Northside Academy",
            status: "pending",
            provenance: "user",
            createdAt: "2026-08-09T08:00:00+00:00"
        ),
        claim: LocalPlayerClaim(
            id: 891,
            localPlayerId: 481,
            relationshipType: "player",
            status: "pending",
            verificationCode: "MAYA-7QK9",
            verificationStatus: "unverified"
        )
    )

    private static let approvedClubClaim = ClubClaim(
        id: 973,
        teamApiId: 4401,
        localClubId: nil,
        clubName: "Northbridge United Academy",
        roleTitle: "Academy Director",
        message: "I manage the academy programme.",
        status: "approved",
        verificationCode: nil,
        verificationProofUrl: "https://northbridge.example/academy",
        verificationStatus: "code_found",
        verificationNote: nil,
        createdAt: "2026-08-10T08:00:00+00:00"
    )

}
#endif
