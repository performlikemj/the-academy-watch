import SwiftUI

enum RootTab: String, Hashable {
    case scoutDesk
    case watchlist
    case lists
    case account

    static func fromLaunchArguments(_ arguments: [String]) -> RootTab {
        guard let flagIndex = arguments.firstIndex(of: "-initialTab"),
              arguments.indices.contains(flagIndex + 1)
        else { return .scoutDesk }

        switch arguments[flagIndex + 1].lowercased() {
        case "watchlist": return .watchlist
        case "lists": return .lists
        case "account": return .account
        default: return .scoutDesk
        }
    }
}

@MainActor
struct RootTabView: View {
    @StateObject private var authManager: AuthManager
    @StateObject private var watchlistViewModel: WatchlistViewModel
    @StateObject private var followListsViewModel: FollowListsViewModel
    @StateObject private var contactAvailability: ContactFeatureAvailability
    @StateObject private var sentRequestsViewModel: SentContactRequestsViewModel
    @StateObject private var incomingRequestsViewModel: IncomingContactRequestsViewModel
    @State private var selectedTab: RootTab
    @State private var isSignInPresented: Bool
    @State private var isPlayerPromptPresented = false
    @State private var accountDestination: AccountDestination?

    private let apiClient: APIClient
    private let initialPhase: ScoutPhase
    private let initialPlayerID: Int?
    private let initialComparePlayerIDs: [Int]
    private let fixtureDestination: FullCircleFixtureDestination?

    init(
        initialPhase: ScoutPhase = .all,
        initialPlayerID: Int? = nil,
        initialComparePlayerIDs: [Int] = [],
        initialTab: RootTab = .scoutDesk,
        initiallyShowsSignIn: Bool = false
    ) {
        let fixtureDestination = FullCircleFixtureDestination.fromLaunchArguments(
            ProcessInfo.processInfo.arguments
        )
        let fixtureState: AuthState?
        #if DEBUG
        if fixtureDestination != nil {
            switch fixtureDestination {
            case .fanRow:
                fixtureState = nil
            case .playerInbox, .declineConfirmation, .watchingYou, .messageReport, .claimGate, .takedown:
                fixtureState = .signedIn(
                    email: "habeeb.player@fixture.example",
                    accountRole: .player,
                    displayName: "Habeeb Amass",
                    isVerifiedScout: false
                )
            case .verification, .introduction, .attestationWarning, .inbox, .clubConsent, .thread,
                 .deleteAccount, .blockedUsers, .watchlistNullStats, .exportData:
                fixtureState = .signedIn(
                    email: "alex.scout@fixture.example",
                    accountRole: .scout,
                    displayName: "Alex Scout",
                    isVerifiedScout: true
                )
            case nil:
                fixtureState = nil
            }
        } else {
            fixtureState = nil
        }
        #else
        fixtureState = nil
        #endif

        let authManager = AuthManager(
            authClient: APIClient(),
            tokenStore: KeychainTokenStore(),
            fixtureState: fixtureState
        )
        let apiClient = APIClient(authSession: authManager)
        let contactAvailability = ContactFeatureAvailability.shared
        if fixtureDestination != nil {
            contactAvailability.recordSuccess()
        }

        _authManager = StateObject(wrappedValue: authManager)
        _watchlistViewModel = StateObject(
            wrappedValue: WatchlistViewModel(apiClient: apiClient)
        )
        _followListsViewModel = StateObject(
            wrappedValue: FollowListsViewModel(apiClient: apiClient)
        )
        _contactAvailability = StateObject(wrappedValue: contactAvailability)
        _sentRequestsViewModel = StateObject(
            wrappedValue: SentContactRequestsViewModel(
                apiClient: apiClient,
                availability: contactAvailability
            )
        )
        _incomingRequestsViewModel = StateObject(
            wrappedValue: IncomingContactRequestsViewModel(
                apiClient: apiClient,
                availability: contactAvailability
            )
        )
        let resolvedTab: RootTab = {
            switch fixtureDestination {
            case .verification, .inbox, .clubConsent, .thread, .playerInbox, .declineConfirmation,
                 .messageReport, .deleteAccount, .blockedUsers, .exportData:
                return .account
            case .watchlistNullStats:
                return .watchlist
            case .introduction, .attestationWarning, .watchingYou, .claimGate, .takedown, .fanRow, nil:
                return initialTab
            }
        }()
        _selectedTab = State(initialValue: resolvedTab)
        _isSignInPresented = State(initialValue: initiallyShowsSignIn)
        _accountDestination = State(initialValue: nil)
        self.apiClient = apiClient
        self.initialPhase = initialPhase
        self.initialPlayerID = fixtureDestination == .introduction
            || fixtureDestination == .attestationWarning
            || fixtureDestination == .watchingYou
            || fixtureDestination == .claimGate
            || fixtureDestination == .takedown
            || fixtureDestination == .fanRow
            ? 403_064
            : initialPlayerID
        self.initialComparePlayerIDs = initialComparePlayerIDs
        self.fixtureDestination = fixtureDestination
    }

    var body: some View {
        TabView(selection: $selectedTab) {
            ScoutDeskView(
                apiClient: apiClient,
                playerDetailAPIClient: apiClient,
                initialPhase: initialPhase,
                initialPlayerID: initialPlayerID,
                initialComparePlayerIDs: initialComparePlayerIDs,
                onSignInRequested: presentSignIn,
                onVerificationRequested: presentVerification
            )
            .tabItem {
                Label("Scout Desk", systemImage: "binoculars.fill")
            }
            .tag(RootTab.scoutDesk)

            WatchlistView(
                playerDetailAPIClient: apiClient,
                onSignInRequested: presentSignIn,
                onVerificationRequested: presentVerification
            )
                .tabItem {
                    Label("Watchlist", systemImage: "star.fill")
                }
            .tag(RootTab.watchlist)

            ListsView(
                apiClient: apiClient,
                playerDetailAPIClient: apiClient,
                onSignInRequested: presentSignIn,
                onVerificationRequested: presentVerification
            )
                .tabItem {
                    Label("Lists", systemImage: "list.bullet.rectangle.fill")
                }
                .tag(RootTab.lists)

            AccountView(
                sentRequestsViewModel: sentRequestsViewModel,
                incomingRequestsViewModel: incomingRequestsViewModel,
                contactAvailability: contactAvailability,
                destination: $accountDestination,
                apiClient: apiClient,
                fixtureDestination: fixtureDestination,
                onSignInRequested: presentSignIn
            )
                // Protected destinations own verification and thread state.
                // Rebuild their navigation tree whenever auth crosses the
                // signed-in boundary so one account cannot retain another
                // account's private form or conversation data.
                .id(authManager.isAuthenticated)
                .tabItem {
                    Label("Account", systemImage: "person.crop.circle.fill")
                }
                .tag(RootTab.account)
        }
        .environmentObject(authManager)
        .environmentObject(watchlistViewModel)
        .environmentObject(followListsViewModel)
        .sheet(isPresented: $isSignInPresented) {
            SignInView(authManager: authManager)
        }
        .sheet(isPresented: $isPlayerPromptPresented) {
            PlayerFirstSignInPrompt(
                onStart: {
                    markPlayerPromptDismissed()
                    isPlayerPromptPresented = false
                    selectedTab = .account
                    accountDestination = .playerOnboarding
                },
                onDismiss: {
                    markPlayerPromptDismissed()
                    isPlayerPromptPresented = false
                }
            )
            .presentationDetents([.medium])
            .presentationDragIndicator(.visible)
        }
        .alert(
            "Unable to Sign Out",
            isPresented: Binding(
                get: { authManager.signOutErrorMessage != nil },
                set: { isPresented in
                    if !isPresented {
                        authManager.clearSignOutError()
                    }
                }
            )
        ) {
            Button("Try Again") {
                authManager.signOut()
            }
            Button("Cancel", role: .cancel) {
                authManager.clearSignOutError()
            }
        } message: {
            Text(authManager.signOutErrorMessage ?? "Your credential is still stored on this device.")
        }
        .task(id: authManager.isAuthenticated) {
            guard fixtureDestination == nil else { return }
            if authManager.isAuthenticated {
                async let account: Void = authManager.refreshAccount(using: apiClient)
                async let watchlist: Void = watchlistViewModel.loadWatchlist()
                async let lists: Void = followListsViewModel.loadLists()
                async let sentRequests: Void = sentRequestsViewModel.reload()
                async let incomingRequests: Void = incomingRequestsViewModel.reload()
                async let playerPrompt: Void = evaluatePlayerPrompt()
                _ = await (account, watchlist, lists, sentRequests, incomingRequests, playerPrompt)
            } else {
                accountDestination = nil
                isPlayerPromptPresented = false
                watchlistViewModel.resetForSignOut()
                followListsViewModel.resetForSignOut()
                sentRequestsViewModel.resetForSignOut()
                incomingRequestsViewModel.resetForSignOut()
            }
        }
    }

    private func presentSignIn() {
        isSignInPresented = true
    }

    private func presentVerification() {
        isSignInPresented = false
        selectedTab = .account
        accountDestination = .verification
    }

    private func evaluatePlayerPrompt() async {
        guard !UserDefaults.standard.bool(forKey: playerPromptDefaultsKey) else { return }
        do {
            let response = try await apiClient.fetchMyProfileClaims()
            guard authManager.isAuthenticated, response.claims.isEmpty else { return }
            isPlayerPromptPresented = true
        } catch {
            // The Account entry remains available. A transient read failure
            // must not turn a one-time prompt into a false claim-status statement.
        }
    }

    private func markPlayerPromptDismissed() {
        UserDefaults.standard.set(true, forKey: playerPromptDefaultsKey)
    }

    private var playerPromptDefaultsKey: String {
        "academyWatch.playerOnboardingPromptDismissed.v1"
    }
}

private struct PlayerFirstSignInPrompt: View {
    let onStart: () -> Void
    let onDismiss: () -> Void

    var body: some View {
        VStack(spacing: 18) {
            ZStack {
                Circle().fill(AcademyColors.claretSoft).frame(width: 70, height: 70)
                Image(systemName: "figure.soccer")
                    .font(.system(size: 34))
                    .foregroundStyle(AcademyColors.claret)
            }
            VStack(spacing: 7) {
                Text("Are you a player?").font(.title2.weight(.bold))
                Text("Find an existing profile to claim, search worldwide, or create a private community profile for review.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            Button("Find my profile", action: onStart)
                .buttonStyle(.borderedProminent)
                .tint(AcademyColors.claretFill)
                .controlSize(.large)
                .frame(maxWidth: .infinity)
            Button("Not now", action: onDismiss)
                .font(.subheadline.weight(.semibold))
        }
        .padding(24)
        .accessibilityIdentifier("first-sign-in-player-prompt")
    }
}
