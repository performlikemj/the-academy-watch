import SwiftUI

#if DEBUG
enum OnboardingFixtureDestination: String {
    case playerSearch = "player-search"
    case createProfile = "create-profile"
    case pendingProfile = "pending-profile"
    case clubClaim = "club-claim"
    case worldwideConfirmation = "worldwide-confirmation"

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

}
#endif
