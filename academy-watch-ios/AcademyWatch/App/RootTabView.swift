import SwiftUI

enum RootTab: String, Hashable {
    case home
    case scoutDesk
    case watchlist
    case lists
    case account

    static func available(for role: ExperienceRole?) -> [RootTab] {
        if role == .scout {
            return [.scoutDesk, .watchlist, .lists, .account]
        }
        return [.home, .scoutDesk, .watchlist, .lists, .account]
    }

    static func initial(
        role: ExperienceRole?,
        launchArguments: [String],
        fixtureDestination: FullCircleFixtureDestination? = nil
    ) -> RootTab {
        let fallback: RootTab = role == .scout ? .scoutDesk : .home
        let requested = tab(for: fixtureDestination) ?? launchOverride(from: launchArguments)
        guard let requested else { return fallback }
        return available(for: role).contains(requested) ? requested : fallback
    }

    static func fromLaunchArguments(_ arguments: [String]) -> RootTab {
        launchOverride(from: arguments) ?? .home
    }

    private static func launchOverride(from arguments: [String]) -> RootTab? {
        guard let flagIndex = arguments.firstIndex(of: "-initialTab"),
              arguments.indices.contains(flagIndex + 1)
        else {
            return arguments.contains("-playerId")
                || arguments.contains("-comparePlayerIds")
                || arguments.contains("-showSignIn") ? .scoutDesk : nil
        }

        switch arguments[flagIndex + 1].lowercased() {
        case "home": return .home
        case "watchlist": return .watchlist
        case "lists": return .lists
        case "account": return .account
        default: return .scoutDesk
        }
    }

    private static func tab(for fixtureDestination: FullCircleFixtureDestination?) -> RootTab? {
        switch fixtureDestination {
        case .verification, .inbox, .clubConsent, .thread, .playerInbox, .declineConfirmation,
             .messageReport, .deleteAccount, .blockedUsers, .exportData:
            return .account
        case .watchlistNullStats:
            return .watchlist
        case .introduction, .attestationWarning, .watchingYou, .claimGate, .takedown, .fanRow:
            return .scoutDesk
        case nil:
            return nil
        }
    }
}

@MainActor
struct RootTabView: View {
    @AppStorage(ExperienceRole.storageKey) private var roleValue = ""
    @StateObject private var authManager: AuthManager
    @StateObject private var watchlistViewModel: WatchlistViewModel
    @StateObject private var followListsViewModel: FollowListsViewModel
    @StateObject private var contactAvailability: ContactFeatureAvailability
    @StateObject private var sentRequestsViewModel: SentContactRequestsViewModel
    @StateObject private var incomingRequestsViewModel: IncomingContactRequestsViewModel
    @State private var selectedTab: RootTab
    @State private var isSignInPresented: Bool
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
        launchArguments: [String] = ProcessInfo.processInfo.arguments,
        initiallyShowsSignIn: Bool = false
    ) {
        let fixtureDestination = FullCircleFixtureDestination.fromLaunchArguments(
            launchArguments
        )
        let fixtureState: AuthState?
        #if DEBUG && targetEnvironment(simulator)
        if PlayerClubExperienceFixtures.mode != nil {
            fixtureState = .signedIn(email: "maya@fixture.example", accountRole: .player, displayName: "Maya Okafor", isVerifiedScout: false)
        } else if fixtureDestination != nil {
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

        let tokenStore: any TokenStoreProtocol
        #if DEBUG && targetEnvironment(simulator)
        tokenStore = PlayerClubExperienceFixtures.mode == nil ? KeychainTokenStore() : ExperienceTokenStore()
        #else
        tokenStore = KeychainTokenStore()
        #endif
        let authManager = AuthManager(
            authClient: APIClient(),
            tokenStore: tokenStore,
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
        let storedRole = ExperienceRole(
            rawValue: UserDefaults.standard.string(forKey: ExperienceRole.storageKey) ?? ""
        )
        let resolvedTab = RootTab.initial(
            role: storedRole,
            launchArguments: launchArguments,
            fixtureDestination: fixtureDestination
        )
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
        TabView(selection: tabSelection) {
            if RootTab.available(for: role).contains(.home) {
                PlayerHomeView(
                    apiClient: apiClient,
                    onSignIn: presentSignIn,
                    onNavigate: select,
                    onRoleSelected: selectInitialTab
                )
                    .id(authManager.email ?? "signed-out")
                    .tabItem {
                        Label("Home", systemImage: "house.fill")
                            .accessibilityIdentifier("tab-bar-home")
                    }
                    .tag(RootTab.home)
            }

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
                    .accessibilityIdentifier("tab-bar-scout-desk")
            }
            .tag(RootTab.scoutDesk)

            WatchlistView(
                playerDetailAPIClient: apiClient,
                onSignInRequested: presentSignIn,
                onVerificationRequested: presentVerification
            )
                .tabItem {
                    Label("Watchlist", systemImage: "star.fill")
                        .accessibilityIdentifier("tab-bar-watchlist")
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
                        .accessibilityIdentifier("tab-bar-lists")
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
                        .accessibilityIdentifier("tab-bar-account")
                }
                .tag(RootTab.account)
        }
        .id(roleValue)
        .environmentObject(authManager)
        .environmentObject(watchlistViewModel)
        .environmentObject(followListsViewModel)
        .onChange(of: roleValue) { _, newValue in
            selectInitialTab(ExperienceRole(rawValue: newValue))
        }
        .sheet(isPresented: $isSignInPresented) {
            SignInView(authManager: authManager)
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
                _ = await (account, watchlist, lists, sentRequests, incomingRequests)
            } else {
                accountDestination = nil
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
        select(.account)
        accountDestination = .verification
    }

    private var role: ExperienceRole? {
        ExperienceRole(rawValue: roleValue)
    }

    private var tabSelection: Binding<RootTab> {
        Binding(
            get: {
                RootTab.available(for: role).contains(selectedTab)
                    ? selectedTab
                    : RootTab.initial(role: role, launchArguments: [])
            },
            set: select
        )
    }

    private func select(_ tab: RootTab) {
        selectedTab = RootTab.available(for: role).contains(tab)
            ? tab
            : RootTab.initial(role: role, launchArguments: [])
    }

    private func selectInitialTab(_ role: ExperienceRole?) {
        selectedTab = RootTab.initial(role: role, launchArguments: [])
    }

}
