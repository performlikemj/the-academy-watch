import SafariServices
import SwiftUI

@MainActor
final class MyProfilesViewModel: ObservableObject {
    @Published private(set) var claims: [PlayerProfileClaim] = []
    @Published private(set) var isLoading = false
    @Published private(set) var error: String?
    private let client: any PlayerClubAPIClientProtocol
    private var generation = 0
    init(client: any PlayerClubAPIClientProtocol) { self.client = client }

    func load() async {
        generation += 1
        let request = generation
        isLoading = true
        error = nil
        do {
            let response = try await client.fetchMyProfileClaims()
            guard request == generation, !Task.isCancelled else { return }
            claims = response.claims
        } catch {
            guard request == generation, !Task.isCancelled else { return }
            claims = []
            self.error = playerClubError(error)
        }
        if request == generation { isLoading = false }
    }
}

struct PlayerHomeView: View {
    @EnvironmentObject private var auth: AuthManager
    @AppStorage(ExperienceRole.storageKey) private var roleValue = ""
    let apiClient: APIClient
    let onSignIn: () -> Void
    let onNavigate: (RootTab) -> Void
    let onRoleSelected: (ExperienceRole?) -> Void
    var onGolRequested: () -> Void = {}
    @ObservedObject var incoming: IncomingContactRequestsViewModel
    @ObservedObject var availability: ContactFeatureAvailability
    private var role: ExperienceRole? { ExperienceRole(rawValue: roleValue) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    #if DEBUG && targetEnvironment(simulator)
                        if PlayerClubExperienceFixtures.mode != nil {
                            Label("OFFLINE FIXTURE", systemImage: "testtube.2").font(AcademyType.caption).foregroundStyle(AcademyColors.secondaryText)
                        }
                    #endif
                    VStack(alignment: .leading, spacing: 10) {
                        Label("YOUR NEXT CHAPTER", systemImage: "soccerball")
                            .font(AcademyType.caption.weight(.medium)).tracking(1.4)
                            .foregroundStyle(AcademyColors.gold)
                        Text(headline).font(AcademyType.largeTitle).foregroundStyle(AcademyColors.chalk)
                        Text(subtitle).font(AcademyType.subheadline).foregroundStyle(AcademyColors.mutedDark)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(24)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(role == .club ? AcademyColors.club : AcademyColors.night)
                    .padding(.horizontal, -16)
                    if role == nil {
                        ForEach(ExperienceRole.allCases) { choice in
                            Button {
                                roleValue = choice.rawValue
                                onRoleSelected(choice)
                            } label: {
                                OnboardingActionRow(icon: choice.icon, title: choice.title, detail: roleDetail(choice))
                            }.buttonStyle(.plain)
                                .accessibilityIdentifier(choice.homeChoiceAccessibilityIdentifier)
                        }
                        Button("Explore players first") { onNavigate(.scoutDesk) }
                            .accessibilityIdentifier("home-skip")
                    } else {
                        Phase2HomeCards(client: apiClient, role: role, incoming: incoming, availability: availability)
                        if role == .scout {
                            scoutingLink(
                                tab: .scoutDesk,
                                icon: "binoculars.fill",
                                title: "Scout Desk",
                                detail: "Discover players and compare their progress."
                            )
                            scoutingLink(
                                tab: .watchlist,
                                icon: "star.fill",
                                title: "Watchlist",
                                detail: "Keep the players you are tracking close at hand."
                            )
                            scoutingLink(
                                tab: .lists,
                                icon: "list.bullet.rectangle.fill",
                                title: "Lists",
                                detail: "Organise players into scouting shortlists."
                            )
                        } else {
                            if auth.isAuthenticated {
                                if role == .club {
                                    clubLink
                                    profilesLink
                                } else {
                                    profilesLink
                                }
                                NavigationLink {
                                    ClubInboxView(apiClient: apiClient)
                                } label: {
                                    OnboardingActionRow(
                                        icon: "envelope.badge", title: "Club invitations",
                                        detail: "Review invitations and choose who you join.")
                                }.buttonStyle(.plain).accessibilityIdentifier("home-club-invitations")
                            } else {
                                VStack(alignment: .leading, spacing: 12) {
                                    Text(role == .club ? "Bring your team together" : "Make your next step count")
                                        .font(AcademyType.title3)
                                    Text("Sign in with an email code. We'll keep your place here.").foregroundStyle(AcademyColors.secondaryText)
                                    Button("Sign in to get started", action: onSignIn)
                                        .buttonStyle(FloodlightPillStyle()).controlSize(.large)
                                        .tint(AcademyColors.primaryFill).foregroundStyle(AcademyColors.onPrimary)
                                        .accessibilityIdentifier("home-sign-in")
                                }.homeCard()
                            }
                            NavigationLink {
                                ScoutDeskView(apiClient: apiClient, playerDetailAPIClient: apiClient, onSignInRequested: onSignIn)
                            } label: {
                                OnboardingActionRow(
                                    icon: "binoculars.fill", title: "Explore players",
                                    detail: "Discover profiles, follow players, and build your watchlist.")
                            }.buttonStyle(.plain)
                        }
                        Menu {
                            ForEach(ExperienceRole.allCases) { choice in
                                Button(choice.title) {
                                    roleValue = choice.rawValue
                                    onRoleSelected(choice)
                                }
                            }
                        } label: {
                            Label("Change my home", systemImage: "slider.horizontal.3").font(AcademyType.footnote.weight(.semibold))
                        }
                        .accessibilityIdentifier("home-change-role")
                    }
                }.padding(16)
            }.background(AcademyColors.background)
            .background(AcademyColors.background)
            .navigationTitle("Home").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    GolEntryButton(action: onGolRequested)
                }
            }
            .accessibilityIdentifier("player-club-home")
        }
    }

    private var headline: String {
        switch role {
        case .player: "Your football.\nYour story."
        case .club: "A home for\nyour team."
        case .scout: "Find the next\nchapter."
        case nil: "Where will\nyou go next?"
        }
    }
    private var subtitle: String {
        switch role {
        case .player: "Build your profile, connect with your club, and keep your development moving."
        case .club: "Bring players onboard and turn each match into a chance to develop."
        case .scout: "Discover players and follow their progress."
        case nil: "Choose what brings you here. You can change this any time."
        }
    }
    private func roleDetail(_ role: ExperienceRole) -> String {
        switch role {
        case .player: "Create your profile and connect with your club."
        case .club: "Onboard players and manage your team."
        case .scout: "Discover players and follow their progress."
        }
    }
    private var profilesLink: some View {
        NavigationLink {
            MyProfilesView(apiClient: apiClient)
        } label: {
            OnboardingActionRow(
                icon: "person.crop.rectangle", title: "My profiles",
                detail: "Find your profile, check your claim, or update your story.")
        }.buttonStyle(.plain).accessibilityIdentifier("home-my-profiles")
    }
    private var clubLink: some View {
        NavigationLink {
            MyClubHomeView(apiClient: apiClient)
        } label: {
            OnboardingActionRow(
                icon: "shield.fill", title: "My club", detail: "Check club verification and open your team's workspace."
            )
        }.buttonStyle(.plain).accessibilityIdentifier("home-my-club")
    }
    private func scoutingLink(tab: RootTab, icon: String, title: String, detail: String) -> some View {
        Button { onNavigate(tab) } label: {
            OnboardingActionRow(icon: icon, title: title, detail: detail)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("home-scout-\(tab.rawValue)")
    }
}

struct MyProfilesView: View {
    @StateObject private var model: MyProfilesViewModel
    @Environment(\.scenePhase) private var scenePhase
    let apiClient: APIClient
    init(apiClient: APIClient) {
        self.apiClient = apiClient
        _model = StateObject(wrappedValue: MyProfilesViewModel(client: apiClient))
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Your place in the game").font(AcademyType.title2)
                Text("Your claims stay here while they're reviewed. Come back any time to see what's next.")
                    .foregroundStyle(AcademyColors.secondaryText)
                if model.isLoading { ProgressView("Checking your profiles…") }
                if let error = model.error {
                    Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(AcademyColors.danger)
                    Button("Try again") { Task { await model.load() } }
                }
                ForEach(model.claims) { claim in
                    NavigationLink {
                        MyPlayerProfileView(claim: claim, apiClient: apiClient)
                    } label: {
                        VStack(alignment: .leading, spacing: 10) {
                            HStack {
                                Text(claim.profileTitle).font(AcademyType.headline)
                                Spacer()
                                BadgeView(text: claim.status.rawValue.capitalized)
                            }
                            Text(claim.nextStep).font(AcademyType.subheadline).foregroundStyle(AcademyColors.secondaryText)
                            Label("Open profile", systemImage: "arrow.right").font(AcademyType.footnote.weight(.semibold))
                        }.homeCard()
                    }.buttonStyle(.plain).accessibilityIdentifier("my-profile-\(claim.id)")
                }
                if !model.isLoading, model.error == nil, model.claims.isEmpty {
                    FloodlightEmptyState(title: "Let's find your profile", systemImage: "figure.soccer", description: "Search your name, or create a profile if you're new here.")
                }
                NavigationLink {
                    PlayerOnboardingView(apiClient: apiClient)
                } label: {
                    Label("Find or create a profile", systemImage: "person.badge.plus")
                        .frame(maxWidth: .infinity)
                }.buttonStyle(FloodlightPillStyle()).controlSize(.large)
                    .tint(AcademyColors.primaryFill).foregroundStyle(AcademyColors.onPrimary)
                    .accessibilityIdentifier("my-profiles-add")
            }.padding(20)
        }.background(AcademyColors.background)
        .background(AcademyColors.background)
        .navigationTitle("My profiles").navigationBarTitleDisplayMode(.inline)
        .task { await model.load() }
        .refreshable { await model.load() }
        .onChange(of: scenePhase) { _, phase in if phase == .active { Task { await model.load() } } }
        .accessibilityIdentifier("my-profiles")
    }
}

struct MyPlayerProfileView: View {
    let claim: PlayerProfileClaim
    let apiClient: APIClient
    @State private var shareURL: URL?
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 10) {
                    BadgeView(text: claim.status.rawValue.capitalized)
                    Text(claim.profileTitle).font(AcademyType.largeTitle)
                    Text(claim.nextStep).foregroundStyle(AcademyColors.secondaryText)
                    if claim.relationshipType != "player" {
                        Label("You represent this player", systemImage: "person.2").font(AcademyType.footnote)
                    }
                }.homeCard()
                if let id = claim.signedPlayerID, claim.status == .approved {
                    NavigationLink {
                        ProfileEditorView(playerID: id, apiClient: apiClient)
                    } label: {
                        OnboardingActionRow(
                            icon: "pencil", title: "Edit profile", detail: "Your photo, bio, position, and highlights.")
                    }.buttonStyle(.plain).accessibilityIdentifier("my-profile-edit")
                    if claim.relationshipType == "player" {
                        NavigationLink {
                            PlayerFeedbackListView(playerID: id, apiClient: apiClient)
                        } label: {
                            OnboardingActionRow(
                                icon: "text.bubble", title: "Coach feedback",
                                detail: "Read your club's private feedback and acknowledge it.")
                        }.buttonStyle(.plain).accessibilityIdentifier("my-profile-feedback")
                        NavigationLink {
                            ClubInboxView(apiClient: apiClient)
                        } label: {
                            OnboardingActionRow(
                                icon: "envelope", title: "Club invitations",
                                detail: "Review the clubs you connect with.")
                        }.buttonStyle(.plain)
                    }
                    NavigationLink {
                        PlayerDetailView(playerID: id, apiClient: apiClient)
                    } label: {
                        Label("View player profile", systemImage: "person.crop.rectangle")
                    }
                    if let shareURL {
                        ShareLink(item: shareURL) { Label("Share public profile", systemImage: "square.and.arrow.up") }
                            .accessibilityIdentifier("my-profile-share")
                    }
                }
                if let url = claim.webURL {
                    WebDestinationLink(
                        url: url,
                        title: claim.status == .approved
                            ? "More profile tools on the web" : "Review claim and verification on the web")
                    Text("Use the same email to sign in on the web.").font(AcademyType.caption).foregroundStyle(AcademyColors.secondaryText)
                }
                LegalSafariLink(destination: .support) {
                    Label("Get help with this profile", systemImage: "questionmark.circle")
                }
                if claim.status == .pending {
                    Text(
                        "Next: we'll review your claim. Your private submissions are not shared publicly before approval."
                    )
                    .font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
                }
            }.padding(20)
        }.background(AcademyColors.background)
        .background(AcademyColors.background)
        .navigationTitle("My profile").navigationBarTitleDisplayMode(.inline)
        .task {
            shareURL = nil
            guard claim.status == .approved, let id = claim.signedPlayerID else { return }
            if let result = try? await apiClient.fetchFollowerCount(playerID: id), !Task.isCancelled {
                shareURL = PublicProfileLink.validated(result.shareUrl)
            }
        }
    }
}

struct MyClubHomeView: View {
    let apiClient: APIClient
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Bring your team together").font(AcademyType.largeTitle)
                Text(
                    "Start with club verification. Once approved, your club workspace brings your roster, player invitations, match reviews, and feedback together."
                )
                .foregroundStyle(AcademyColors.secondaryText)
                NavigationLink {
                    ClubOnboardingView(apiClient: apiClient)
                } label: {
                    OnboardingActionRow(
                        icon: "checkmark.shield", title: "Club verification",
                        detail: "Claim your club or check an existing application.")
                }.buttonStyle(.plain).accessibilityIdentifier("my-club-verification")
                LegalSafariLink(destination: .clubConsole) {
                    OnboardingActionRow(
                        icon: "person.3", title: "Open club workspace",
                        detail: "Manage your players, invitations, match footage, and feedback on the web.")
                }.buttonStyle(.plain).accessibilityIdentifier("my-club-workspace")
                Text("Sign in with the same email. Club access is available after your official claim is approved.")
                    .font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
                VStack(alignment: .leading, spacing: 14) {
                    Text("Your first team session").font(AcademyType.headline)
                    Label("Ask each adult player to claim or create their profile.", systemImage: "1.circle")
                    Label("Invite approved players from your club roster.", systemImage: "2.circle")
                    Label("Players accept in Home → Club invitations.", systemImage: "3.circle")
                    Label("Publish feedback, then review it together next week.", systemImage: "4.circle")
                }.homeCard()
                LegalSafariLink(destination: .support) {
                    Label("Get onboarding help", systemImage: "questionmark.circle")
                }
            }.padding(20)
        }.background(AcademyColors.background).background(AcademyColors.background)
            .navigationTitle("My club").navigationBarTitleDisplayMode(.inline)
    }
}

private extension ExperienceRole {
    var homeChoiceAccessibilityIdentifier: String {
        switch self {
        case .player: "home-role-player"
        case .club: "home-role-club"
        case .scout: "home-role-scout"
        }
    }
}

extension View {
    func homeCard() -> some View {
        self.frame(maxWidth: .infinity, alignment: .leading).padding(18)
            .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10))
    }
}

struct WebDestinationLink: View {
    let url: URL
    let title: String
    @State private var presented = false
    var body: some View {
        Button {
            presented = true
        } label: {
            Label(title, systemImage: "arrow.up.right.square")
        }
        .sheet(isPresented: $presented) { SafariView(url: url).ignoresSafeArea() }
    }
}

enum PublicProfileLink {
    static func validated(_ value: String?) -> URL? {
        guard let value, let url = URL(string: value), url.scheme == "https",
            ["theacademywatch.com", "www.theacademywatch.com"].contains(url.host?.lowercased() ?? ""),
            url.user == nil, url.password == nil, url.port == nil,
            url.query == nil, url.fragment == nil,
            url.pathComponents.count == 3, url.pathComponents[1] == "p",
            Int(url.lastPathComponent).map({ $0 != 0 }) == true
        else { return nil }
        return url
    }
}

private struct SafariView: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> SFSafariViewController {
        let controller = SFSafariViewController(url: url)
        controller.preferredBarTintColor = UIColor(AcademyColors.background)
        controller.preferredControlTintColor = UIColor(AcademyColors.accent)
        return controller
    }
    func updateUIViewController(_ controller: SFSafariViewController, context: Context) {}
}
