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
    @AppStorage("academyWatch.experienceRole.v1") private var roleValue = ""
    let apiClient: APIClient
    let onSignIn: () -> Void
    let onExplore: () -> Void
    private var role: ExperienceRole? { ExperienceRole(rawValue: roleValue) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    #if DEBUG
                        if PlayerClubExperienceFixtures.mode != nil {
                            Label("OFFLINE FIXTURE", systemImage: "testtube.2").font(.caption).foregroundStyle(
                                .secondary)
                        }
                    #endif
                    VStack(alignment: .leading, spacing: 10) {
                        Label("YOUR NEXT CHAPTER", systemImage: "soccerball")
                            .font(.caption.weight(.bold)).tracking(1.4)
                            .foregroundStyle(AcademyColors.claret)
                        Text(headline).font(.largeTitle.bold())
                        Text(subtitle).font(.subheadline).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if role == nil {
                        ForEach(ExperienceRole.allCases) { choice in
                            Button {
                                roleValue = choice.rawValue
                            } label: {
                                OnboardingActionRow(icon: choice.icon, title: choice.title, detail: roleDetail(choice))
                            }.buttonStyle(.plain)
                                .accessibilityIdentifier("home-role-\(choice.rawValue)")
                        }
                        Button("Explore players first", action: onExplore)
                            .accessibilityIdentifier("home-skip")
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
                                Text(role == .club ? "Bring your team together" : "Make your next step count").font(
                                    .title3.bold())
                                Text("Sign in with an email code. We'll keep your place here.").foregroundStyle(
                                    .secondary)
                                Button("Sign in to get started", action: onSignIn)
                                    .buttonStyle(.borderedProminent).controlSize(.large)
                                    .tint(AcademyColors.claretFill).foregroundStyle(AcademyColors.claretOnFill)
                                    .accessibilityIdentifier("home-sign-in")
                            }.homeCard()
                        }
                        Button(action: onExplore) {
                            OnboardingActionRow(
                                icon: "binoculars.fill", title: "Explore players",
                                detail: "Discover profiles, follow players, and build your watchlist.")
                        }.buttonStyle(.plain)
                        Menu {
                            ForEach(ExperienceRole.allCases) { choice in
                                Button(choice.title) { roleValue = choice.rawValue }
                            }
                        } label: {
                            Label("Change my home", systemImage: "slider.horizontal.3").font(
                                .footnote.weight(.semibold))
                        }
                        .accessibilityIdentifier("home-change-role")
                    }
                }.padding(20)
            }
            .background(AcademyColors.background)
            .navigationTitle("Home").navigationBarTitleDisplayMode(.inline)
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
                Text("Your place in the game").font(.title2.bold())
                Text("Your claims stay here while they're reviewed. Come back any time to see what's next.")
                    .foregroundStyle(.secondary)
                if model.isLoading { ProgressView("Checking your profiles…") }
                if let error = model.error {
                    Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.red)
                    Button("Try again") { Task { await model.load() } }
                }
                ForEach(model.claims) { claim in
                    NavigationLink {
                        MyPlayerProfileView(claim: claim, apiClient: apiClient)
                    } label: {
                        VStack(alignment: .leading, spacing: 10) {
                            HStack {
                                Text(claim.profileTitle).font(.headline)
                                Spacer()
                                BadgeView(text: claim.status.rawValue.capitalized)
                            }
                            Text(claim.nextStep).font(.subheadline).foregroundStyle(.secondary)
                            Label("Open profile", systemImage: "arrow.right").font(.footnote.weight(.semibold))
                        }.homeCard()
                    }.buttonStyle(.plain).accessibilityIdentifier("my-profile-\(claim.id)")
                }
                if !model.isLoading, model.error == nil, model.claims.isEmpty {
                    ContentUnavailableView(
                        "Let's find your profile", systemImage: "figure.soccer",
                        description: Text("Search your name, or create a profile if you're new here."))
                }
                NavigationLink {
                    PlayerOnboardingView(apiClient: apiClient)
                } label: {
                    Label("Find or create a profile", systemImage: "person.badge.plus")
                        .frame(maxWidth: .infinity)
                }.buttonStyle(.borderedProminent).controlSize(.large)
                    .tint(AcademyColors.claretFill).foregroundStyle(AcademyColors.claretOnFill)
                    .accessibilityIdentifier("my-profiles-add")
            }.padding(20)
        }
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
                    Text(claim.profileTitle).font(.largeTitle.bold())
                    Text(claim.nextStep).foregroundStyle(.secondary)
                    if claim.relationshipType != "player" {
                        Label("You represent this player", systemImage: "person.2").font(.footnote)
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
                    Text("Use the same email to sign in on the web.").font(.caption).foregroundStyle(.secondary)
                }
                LegalSafariLink(destination: .support) {
                    Label("Get help with this profile", systemImage: "questionmark.circle")
                }
                if claim.status == .pending {
                    Text(
                        "Next: we'll review your claim. Your private submissions are not shared publicly before approval."
                    )
                    .font(.footnote).foregroundStyle(.secondary)
                }
            }.padding(20)
        }
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
                Text("Bring your team together").font(.largeTitle.bold())
                Text(
                    "Start with club verification. Once approved, your club workspace brings your roster, player invitations, match reviews, and feedback together."
                )
                .foregroundStyle(.secondary)
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
                    .font(.footnote).foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 14) {
                    Text("Your first team session").font(.headline)
                    Label("Ask each adult player to claim or create their profile.", systemImage: "1.circle")
                    Label("Invite approved players from your club roster.", systemImage: "2.circle")
                    Label("Players accept in Home → Club invitations.", systemImage: "3.circle")
                    Label("Publish feedback, then review it together next week.", systemImage: "4.circle")
                }.homeCard()
                LegalSafariLink(destination: .support) {
                    Label("Get onboarding help", systemImage: "questionmark.circle")
                }
            }.padding(20)
        }.background(AcademyColors.background)
            .navigationTitle("My club").navigationBarTitleDisplayMode(.inline)
    }
}

extension View {
    func homeCard() -> some View {
        self.frame(maxWidth: .infinity, alignment: .leading).padding(18)
            .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 20))
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
    func makeUIViewController(context: Context) -> SFSafariViewController { SFSafariViewController(url: url) }
    func updateUIViewController(_ controller: SFSafariViewController, context: Context) {}
}
