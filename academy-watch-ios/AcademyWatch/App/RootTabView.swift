import SwiftUI

enum RootTab: String, Hashable {
    case scoutDesk
    case watchlist
    case lists

    static func fromLaunchArguments(_ arguments: [String]) -> RootTab {
        guard let flagIndex = arguments.firstIndex(of: "-initialTab"),
              arguments.indices.contains(flagIndex + 1)
        else { return .scoutDesk }

        switch arguments[flagIndex + 1].lowercased() {
        case "watchlist": return .watchlist
        case "lists": return .lists
        default: return .scoutDesk
        }
    }
}

@MainActor
struct RootTabView: View {
    @StateObject private var authManager: AuthManager
    @StateObject private var watchlistViewModel: WatchlistViewModel
    @StateObject private var followListsViewModel: FollowListsViewModel
    @State private var selectedTab: RootTab
    @State private var isSignInPresented: Bool

    private let apiClient: APIClient
    private let initialPhase: ScoutPhase
    private let initialPlayerID: Int?
    private let initialComparePlayerIDs: [Int]

    init(
        initialPhase: ScoutPhase = .all,
        initialPlayerID: Int? = nil,
        initialComparePlayerIDs: [Int] = [],
        initialTab: RootTab = .scoutDesk,
        initiallyShowsSignIn: Bool = false
    ) {
        let authManager = AuthManager()
        let apiClient = APIClient(authSession: authManager)

        _authManager = StateObject(wrappedValue: authManager)
        _watchlistViewModel = StateObject(
            wrappedValue: WatchlistViewModel(apiClient: apiClient)
        )
        _followListsViewModel = StateObject(
            wrappedValue: FollowListsViewModel(apiClient: apiClient)
        )
        _selectedTab = State(initialValue: initialTab)
        _isSignInPresented = State(initialValue: initiallyShowsSignIn)
        self.apiClient = apiClient
        self.initialPhase = initialPhase
        self.initialPlayerID = initialPlayerID
        self.initialComparePlayerIDs = initialComparePlayerIDs
    }

    var body: some View {
        TabView(selection: $selectedTab) {
            ScoutDeskView(
                apiClient: apiClient,
                initialPhase: initialPhase,
                initialPlayerID: initialPlayerID,
                initialComparePlayerIDs: initialComparePlayerIDs,
                onSignInRequested: presentSignIn
            )
            .tabItem {
                Label("Scout Desk", systemImage: "binoculars.fill")
            }
            .tag(RootTab.scoutDesk)

            WatchlistView(onSignInRequested: presentSignIn)
                .tabItem {
                    Label("Watchlist", systemImage: "star.fill")
                }
            .tag(RootTab.watchlist)

            ListsView(apiClient: apiClient, onSignInRequested: presentSignIn)
                .tabItem {
                    Label("Lists", systemImage: "list.bullet.rectangle.fill")
                }
                .tag(RootTab.lists)
        }
        .environmentObject(authManager)
        .environmentObject(watchlistViewModel)
        .environmentObject(followListsViewModel)
        .sheet(isPresented: $isSignInPresented) {
            SignInView(authManager: authManager)
        }
        .task(id: authManager.state) {
            if authManager.isAuthenticated {
                async let watchlist: Void = watchlistViewModel.loadWatchlist()
                async let lists: Void = followListsViewModel.loadLists()
                _ = await (watchlist, lists)
            } else {
                watchlistViewModel.resetForSignOut()
                followListsViewModel.resetForSignOut()
            }
        }
    }

    private func presentSignIn() {
        isSignInPresented = true
    }
}
