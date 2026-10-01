import SwiftUI

enum RootTab: String, Hashable {
    case home
    case scoutDesk
    case watchlist
    case lists
    case account
    case clubs, trials, applied, squads, matches, recruiting

    static func available(for role: ExperienceRole?, flags: Phase2Flags? = nil, access: ClubAccess? = nil) -> [RootTab]
    {
        if let flags, role == .player, flags.directory || flags.opportunities || flags.applications {
            return [.home] + (flags.directory ? [.clubs] : []) + (flags.opportunities ? [.trials] : [])
                + (flags.applications ? [.applied] : []) + [.account]
        }
        if let flags, role == .club, flags.staff {
            return [.home] + (access?.can("players.view") == true ? [.squads] : [])
                + (access?.can("matches.view") == true ? [.matches] : [])
                + (access?.canRecruit == true && flags.opportunities ? [.recruiting] : []) + [.account]
        }
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
        case "clubs": return .clubs
        case "trials": return .trials
        case "applied": return .applied
        case "squads": return .squads
        case "matches": return .matches
        case "recruiting": return .recruiting
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
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var workspace: Phase2Workspace
    @StateObject private var authManager: AuthManager
    @StateObject private var watchlistViewModel: WatchlistViewModel
    @StateObject private var followListsViewModel: FollowListsViewModel
    @StateObject private var contactAvailability: ContactFeatureAvailability
    @StateObject private var sentRequestsViewModel: SentContactRequestsViewModel
    @StateObject private var incomingRequestsViewModel: IncomingContactRequestsViewModel
    @State private var hasLoadedWorkspace = false
    @State private var selectedTab: RootTab
    @State private var isSignInPresented: Bool
    @State private var accountDestination: AccountDestination?
    @State private var isGolPresented = false
    @StateObject private var golChatViewModel: GolChatViewModel

    private let launchArguments: [String]
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
            if Phase2Fixtures.active {
                fixtureState = .signedIn(
                    email: "phase2@fixture.invalid", accountRole: .player, displayName: "Reuben Castellane",
                    isVerifiedScout: false)
            } else if FloodlightPreview.isActive {
                fixtureState =
                    ["auth", "chooser", "account-signed-out"].contains(FloodlightPreview.screen ?? "")
                    ? .signedOut
                    : .signedIn(
                        email: "review@example.invalid", accountRole: .scout, displayName: "Sample Reviewer",
                        isVerifiedScout: true)
            } else if PlayerClubExperienceFixtures.mode != nil {
                fixtureState = .signedIn(
                    email: "maya@fixture.example", accountRole: .player, displayName: "Maya Okafor",
                    isVerifiedScout: false)
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
            tokenStore =
                PlayerClubExperienceFixtures.mode == nil && !FloodlightPreview.isActive && !Phase2Fixtures.active
                ? KeychainTokenStore() : ExperienceTokenStore()
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

        _workspace = StateObject(wrappedValue: Phase2Workspace(client: apiClient))
        _authManager = StateObject(wrappedValue: authManager)
        _golChatViewModel = StateObject(wrappedValue: GolChatViewModel(client: apiClient))
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
        self.launchArguments = launchArguments
        self.apiClient = apiClient
        self.initialPhase = initialPhase
        self.initialPlayerID =
            fixtureDestination == .introduction
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
            homeTab
            phase2Tabs
            legacyTabs
            accountTab
        }
        .id(tabTreeIdentity)
        .toolbar(usesEditorialTabs ? .hidden : .visible, for: .tabBar)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if usesEditorialTabs {
                Phase2TabBar(tabs: availableTabs, role: role, selection: tabSelection)
                    .frame(height: 64).padding(.horizontal, 14).padding(.top, 8).padding(.bottom, 4)
                    .background(AcademyColors.background)
            }
        }
        .environmentObject(workspace)
        .environmentObject(authManager)
        .environmentObject(watchlistViewModel)
        .environmentObject(followListsViewModel)
        .onChange(of: availableTabs) { _, tabs in
            if !tabs.contains(selectedTab) { selectedTab = role == .scout ? .scoutDesk : .home }
        }
        .task(id: authManager.email) {
            await workspace.load(authenticated: authManager.isAuthenticated)
            guard !Task.isCancelled else { return }
            hasLoadedWorkspace = true
            let requested = RootTab.fromLaunchArguments(launchArguments)
            if availableTabs.contains(requested) { selectedTab = requested }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active && hasLoadedWorkspace {
                Task { await workspace.load(authenticated: authManager.isAuthenticated) }
            }
        }
        .onChange(of: roleValue) { _, newValue in
            selectInitialTab(ExperienceRole(rawValue: newValue))
        }
        .onChange(of: authManager.isAuthenticated) { _, authenticated in
            if !authenticated { golChatViewModel.resetAccount() }
        }
        .onChange(of: authManager.email) { old, new in
            if old != nil && old != new {
                golChatViewModel.resetAccount()
                watchlistViewModel.resetForSignOut()
                followListsViewModel.resetForSignOut()
                sentRequestsViewModel.resetForSignOut()
                incomingRequestsViewModel.resetForSignOut()
            }
        }
        .sheet(isPresented: $isGolPresented) {
            GolChatView(model: golChatViewModel)
                .environmentObject(authManager)
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
        .task(id: authManager.email) {
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

    private var tabTreeIdentity: String {
        roleValue + "|" + (authManager.email ?? "signed-out") + "|"
            + availableTabs.map(\.rawValue).joined(separator: ",") + "|" + String(workspace.selected?.id ?? 0)
    }

    @ViewBuilder private var homeTab: some View {

        if availableTabs.contains(.home) {
            PlayerHomeView(
                apiClient: apiClient,
                onSignIn: presentSignIn,
                onNavigate: select,
                onRoleSelected: selectInitialTab,
                onGolRequested: { isGolPresented = true },
                incoming: incomingRequestsViewModel,
                availability: contactAvailability
            )
            .id(authManager.email ?? "signed-out")
            .tabItem {
                Label(role == .club && workspace.flags.staff ? "Today" : "Home", systemImage: "house")
                    .accessibilityIdentifier("tab-bar-home")
            }
            .tag(RootTab.home)
        }

    }

    @ViewBuilder private var phase2Tabs: some View {
        if availableTabs.contains(.clubs) {
            NavigationStack { ClubsNearYouView(client: apiClient) }.tabItem {
                Label("Clubs", systemImage: "mappin.and.ellipse")
            }
            .tag(RootTab.clubs)
        }
        if availableTabs.contains(.trials) {
            NavigationStack { TrialsView(client: apiClient) }.tabItem { Label("Trials", systemImage: "flag") }
                .tag(RootTab.trials)
        }
        if availableTabs.contains(.applied) {
            NavigationStack { MyApplicationsView(client: apiClient) }.tabItem {
                Label("Applied", systemImage: "tray")
            }.tag(RootTab.applied)
        }
        if let membership = workspace.selected {
            if availableTabs.contains(.squads) {
                NavigationStack { SquadQuickView(membership: membership, client: apiClient) }.tabItem {
                    Label("Squads", systemImage: "person.3")
                }.tag(RootTab.squads)
            }
            if availableTabs.contains(.matches) {
                NavigationStack { SquadQuickView(membership: membership, client: apiClient, matchesOnly: true) }.tabItem
                { Label("Matches", systemImage: "play.rectangle") }.tag(RootTab.matches)
            }
            if availableTabs.contains(.recruiting) {
                NavigationStack { RecruitingView(client: apiClient, membership: membership) }.tabItem {
                    Label("Recruiting", systemImage: "person.badge.plus")
                }.tag(RootTab.recruiting)
            }
        }

    }

    @ViewBuilder private var legacyTabs: some View {
        if availableTabs.contains(.scoutDesk) {
            ScoutDeskView(
                apiClient: apiClient,
                playerDetailAPIClient: apiClient,
                initialPhase: initialPhase,
                initialPlayerID: initialPlayerID,
                initialComparePlayerIDs: initialComparePlayerIDs,
                onSignInRequested: presentSignIn,
                onVerificationRequested: presentVerification,
                onGolRequested: { isGolPresented = true }
            )
            .tabItem {
                Label("Scout Desk", systemImage: "binoculars.fill")
                    .accessibilityIdentifier("tab-bar-scout-desk")
            }
            .tag(RootTab.scoutDesk)
        }

        if availableTabs.contains(.watchlist) {
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
        }

        if availableTabs.contains(.lists) {
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
        }

    }

    @ViewBuilder private var accountTab: some View {
        AccountView(
            sentRequestsViewModel: sentRequestsViewModel,
            incomingRequestsViewModel: incomingRequestsViewModel,
            contactAvailability: contactAvailability,
            destination: $accountDestination,
            apiClient: apiClient,
            fixtureDestination: fixtureDestination,
            onSignInRequested: presentSignIn,
            onGolRequested: { isGolPresented = true },
            phase2Membership: workspace.flags.staff ? workspace.selected : nil
        )
        // Protected destinations own verification and thread state.
        // Rebuild their navigation tree whenever auth crosses the
        // signed-in boundary so one account cannot retain another
        // account's private form or conversation data.
        .id(authManager.isAuthenticated)
        .tabItem {
            Label("Account", systemImage: "person")
                .accessibilityIdentifier("tab-bar-account")
        }
        .tag(RootTab.account)

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

    private var usesEditorialTabs: Bool {
        (role == .player
            && (workspace.flags.directory || workspace.flags.opportunities || workspace.flags.applications))
            || (role == .club && workspace.flags.staff)
    }

    private var availableTabs: [RootTab] {
        RootTab.available(for: role, flags: workspace.flags, access: workspace.selected?.access)
    }

    private var tabSelection: Binding<RootTab> {
        Binding(
            get: {
                availableTabs.contains(selectedTab)
                    ? selectedTab
                    : RootTab.initial(role: role, launchArguments: [])
            },
            set: { select($0) }
        )
    }

    private func select(_ tab: RootTab) {
        selectedTab =
            availableTabs.contains(tab)
            ? tab
            : RootTab.initial(role: role, launchArguments: [])
    }

    private func selectInitialTab(_ role: ExperienceRole?) {
        selectedTab = RootTab.initial(role: role, launchArguments: [])
    }

}
