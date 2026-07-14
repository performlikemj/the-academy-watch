import SwiftUI

enum RootTab: String, Hashable {
    case scoutDesk
    case watchlist

    static func fromLaunchArguments(_ arguments: [String]) -> RootTab {
        guard let flagIndex = arguments.firstIndex(of: "-initialTab"),
              arguments.indices.contains(flagIndex + 1),
              arguments[flagIndex + 1].lowercased() == "watchlist"
        else { return .scoutDesk }
        return .watchlist
    }
}

@MainActor
struct RootTabView: View {
    @StateObject private var authManager: AuthManager
    @StateObject private var watchlistViewModel: WatchlistViewModel
    @State private var selectedTab: RootTab
    @State private var isSignInPresented: Bool

    private let apiClient: APIClient
    private let initialPhase: ScoutPhase
    private let initialPlayerID: Int?

    init(
        initialPhase: ScoutPhase = .all,
        initialPlayerID: Int? = nil,
        initialTab: RootTab = .scoutDesk,
        initiallyShowsSignIn: Bool = false
    ) {
        let authManager = AuthManager()
        let apiClient = APIClient(authSession: authManager)

        _authManager = StateObject(wrappedValue: authManager)
        _watchlistViewModel = StateObject(
            wrappedValue: WatchlistViewModel(apiClient: apiClient)
        )
        _selectedTab = State(initialValue: initialTab)
        _isSignInPresented = State(initialValue: initiallyShowsSignIn)
        self.apiClient = apiClient
        self.initialPhase = initialPhase
        self.initialPlayerID = initialPlayerID
    }

    var body: some View {
        TabView(selection: $selectedTab) {
            ScoutDeskView(
                apiClient: apiClient,
                initialPhase: initialPhase,
                initialPlayerID: initialPlayerID,
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
        }
        .environmentObject(authManager)
        .environmentObject(watchlistViewModel)
        .sheet(isPresented: $isSignInPresented) {
            SignInView(authManager: authManager)
        }
        .task(id: authManager.state) {
            if authManager.isAuthenticated {
                await watchlistViewModel.loadWatchlist()
            } else {
                watchlistViewModel.resetForSignOut()
            }
        }
    }

    private func presentSignIn() {
        isSignInPresented = true
    }
}
