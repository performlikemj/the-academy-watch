#if DEBUG && targetEnvironment(simulator)
import SwiftUI

/// Review-only transport: every request is resolved locally or fails closed.
/// Unknown routes and all mutations cannot open a network connection.
enum FloodlightPreview {
    static var screen: String? {
        let args = ProcessInfo.processInfo.arguments
        guard let index = args.firstIndex(of: "-floodlightPreview"), args.indices.contains(index + 1) else { return nil }
        return args[index + 1]
    }
    static var isActive: Bool { screen != nil }

    static func fixture(_ name: String) throws -> Data {
        guard let url = Bundle.main.url(forResource: name, withExtension: "json") else {
            throw APIClientError.invalidResponse
        }
        return try Data(contentsOf: url)
    }

    static func data(for request: URLRequest) throws -> Data {
        let path = request.url?.path ?? ""
        guard request.httpMethod == "GET" else {
            throw ExperienceFixtureError.unmatchedRequest(method: request.httpMethod ?? "", path: path)
        }
        if screen?.hasSuffix("-error") == true, !path.hasSuffix("/health") {
            throw APIClientError.server(statusCode: 503, message: "Synthetic review error. Please try again.")
        }
        let empty = screen?.hasSuffix("-empty") == true
        var name: String?
        if path.hasSuffix("/scout/compare") { name = "scout_compare_gk_outfielder" }
        if path.hasSuffix("/scout/lists") && !empty { name = "scout_follow_lists" }
        if path.contains("/scout/lists/17") { name = path.hasSuffix("/resolve") ? "scout_follow_list_resolve" : "scout_follow_lists" }
        if path.hasSuffix("/contact/requests") && !empty { name = request.url?.query?.contains("box=inbox") == true ? "contact_requests_inbox" : "contact_requests_sent" }
        if path.hasSuffix("/messages") { name = "contact_messages" }
        if path.contains("verification") { name = "scout_verification" }
        if let name { return try fixture(name) }
        if path.hasSuffix("/gol/suggestions") { return Data(#"{"suggestions":["How should I assess a player's progress?","Explain academy pathways"]}"#.utf8) }
        if path.hasSuffix("/blocks") { return Data(#"{"blocks":[]}"#.utf8) }
        if path.hasSuffix("/claims") && path.contains("/players/") { return Data(#"{"claims":[],"claim":null}"#.utf8) }
        if path.hasSuffix("/interest-signals") { return Data(#"{"week_start":"2026-09-28","interest_signals":[]}"#.utf8) }
        if path.hasSuffix("/scout/watchlist") && !empty {
            let playerRequest = URLRequest(url: URL(string: "https://example.invalid/api/scout/players")!)
            let data = try self.data(for: playerRequest)
            let obj = try JSONSerialization.jsonObject(with: data) as! [String: Any]
            let players = obj["players"] as! [[String: Any]]
            return try JSONSerialization.data(withJSONObject: ["entries": [["player_api_id":900001,"player":players[0],"note":"Synthetic review shortlist","added_at":"2026-09-28T10:00:00Z"]], "digest_opt_in":false,"scout_tier":"fixture","season":2026])
        }
        if path.hasSuffix("/scout/watchlist/ids") { return Data(#"{"player_ids":[900001]}"#.utf8) }
        if path.hasSuffix("/scout/players") && empty { return Data(#"{"players":[],"total":0,"page":1,"per_page":20,"total_pages":0,"season":2026}"#.utf8) }
        // The existing experience fixture supplies synthetic profiles, season data,
        // invitations and coach feedback. Replace its fictional personal names
        // so every review image is unmistakably generic.
        let data = try PlayerClubExperienceFixtures.data(for: request, mode: "development")
        let text = String(decoding: data, as: UTF8.self)
            .replacingOccurrences(of: "Maya Okafor", with: "Sample Player")
            .replacingOccurrences(of: "Maya", with: "Sample Player")
            .replacingOccurrences(of: "Community FC", with: "Sample Club")
            .replacingOccurrences(of: "Coach Alex", with: "Sample Coach")
            .replacingOccurrences(of: "Sim Player One", with: "Sample Player One")
            .replacingOccurrences(of: "Sim Academy", with: "Sample Academy")
            .replacingOccurrences(of: "Sim Member", with: "Sample Member")
        return Data(text.utf8)
    }
}

struct FloodlightPreviewCache: ScoutResponseCaching {
    func loadPlayers(for key: ScoutPlayersCacheKey) async -> ScoutPlayersResponse? { nil }
    func savePlayers(_ response: ScoutPlayersResponse, for key: ScoutPlayersCacheKey) async {}
    func loadLeaderboards(for key: ScoutLeaderboardsCacheKey) async -> ScoutLeaderboardsResponse? { nil }
    func saveLeaderboards(_ response: ScoutLeaderboardsResponse, for key: ScoutLeaderboardsCacheKey) async {}
}

@MainActor
struct FloodlightPreviewRoot: View {
    let screen: String
    @StateObject private var auth: AuthManager
    @StateObject private var watchlist: WatchlistViewModel
    @StateObject private var lists: FollowListsViewModel
    @StateObject private var sent: SentContactRequestsViewModel
    @StateObject private var incoming: IncomingContactRequestsViewModel
    @StateObject private var gol: GolChatViewModel
    @StateObject private var showcase: ShowcaseViewModel
    private let client: APIClient
    private let availability = ContactFeatureAvailability()
    @StateObject private var introduction = IntroductionRequestViewModel(playerID: 900001, apiClient: APIClient(), availability: .shared)
    @State private var destination: AccountDestination?

    init(screen: String) {
        self.screen = screen
        let signedOut = ["auth", "chooser", "account-signed-out"].contains(screen)
        let auth = AuthManager(authClient: APIClient(), tokenStore: ExperienceTokenStore(), fixtureState: signedOut ? .signedOut : .signedIn(email: "review@example.invalid", accountRole: .scout, displayName: "Sample Reviewer", isVerifiedScout: true))
        let client = APIClient(authSession: auth)
        self.client = client
        _auth = StateObject(wrappedValue: auth)
        _watchlist = StateObject(wrappedValue: WatchlistViewModel(apiClient: client))
        _lists = StateObject(wrappedValue: FollowListsViewModel(apiClient: client))
        _sent = StateObject(wrappedValue: SentContactRequestsViewModel(apiClient: client, availability: ContactFeatureAvailability.shared))
        _incoming = StateObject(wrappedValue: IncomingContactRequestsViewModel(apiClient: client, availability: ContactFeatureAvailability.shared))
        _gol = StateObject(wrappedValue: GolChatViewModel(client: PreviewGolClient()))
        _showcase = StateObject(wrappedValue: ShowcaseViewModel(playerID: 900001, apiClient: client))
        UserDefaults.standard.set(screen == "chooser" ? "" : screen == "club-home" ? "club" : ["scout", "scout-empty", "scout-error", "watchlist", "watchlist-empty", "watchlist-error", "lists", "lists-empty", "account", "account-signed-out"].contains(screen) ? "scout" : "player", forKey: ExperienceRole.storageKey)
        ContactFeatureAvailability.shared.recordSuccess()
    }

    var body: some View {
        content
            .environmentObject(auth)
            .environmentObject(watchlist)
            .environmentObject(lists)
            .tint(AcademyColors.claretForeground)
            .overlay(alignment: .top) {
                Text("OFFLINE REVIEW · GENERIC FIXTURE")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(AcademyColors.secondaryText)
                    .offset(y: -12)
                    .allowsHitTesting(false)
            }
            .task {
                await watchlist.loadWatchlist()
                await lists.loadLists()
                if screen == "showcase" { await showcase.loadIfNeeded() }
                if screen == "gol-answer" { gol.send("How should I assess a player's progress?") }
            }
    }

    @ViewBuilder private var content: some View {
        switch screen {
        case "scout", "scout-empty", "scout-error": RootTabView(launchArguments: ["-initialTab", "scoutDesk"])
        case "loading": WingLiftLoadingView(feedback: ScoutInitialLoadFeedback(elapsedSeconds: 10), reduceMotionOverride: true)
        case "player", "player-error", "season": NavigationStack { PlayerDetailView(playerID: 900001, apiClient: client) }
        case "compare": NavigationStack { CompareView(playerIDs: [900001,900002], apiClient: client) }
        case "watchlist", "watchlist-empty", "watchlist-error": RootTabView(launchArguments: ["-initialTab", "watchlist"])
        case "lists", "lists-empty": RootTabView(launchArguments: ["-initialTab", "lists"])
        case "list-detail": NavigationStack { FollowListDetailView(listID: 17, apiClient: client) }
        case "auth": SignInView(authManager: auth)
        case "home", "chooser", "club-home": RootTabView(launchArguments: ["-initialTab", "home"])
        case "profiles": NavigationStack { MyProfilesView(apiClient: client) }
        case "profile-editor": NavigationStack { ProfileEditorView(playerID: -481, apiClient: client) }
        case "invitations": NavigationStack { ClubInboxView(apiClient: client) }
        case "feedback": NavigationStack { PlayerFeedbackListView(playerID: -481, apiClient: client) }
        case "development": NavigationStack { PlayerFeedbackDetailView(id: "feedback-fixture", apiClient: client) }
        case "player-onboarding": NavigationStack { PlayerOnboardingView(apiClient: client) }
        case "create-profile": NavigationStack { LocalPlayerCreateView(context: .claimant, apiClient: client) }
        case "club-onboarding": NavigationStack { ClubOnboardingView(apiClient: client, initiallyShowsForm: true, loadsOnAppear: false) }
        case "worldwide": NavigationStack { WorldwidePlayerSearchView(purpose: .addToList, apiClient: client) }
        case "introduction": IntroductionRequestSheet(viewModel: introduction, availability: .shared, playerName: "Sample Player One", isFixturePreview: true, onVerificationRequested: {})
        case "legal": NavigationStack { ScrollView { account.legalSection.padding(16) }.background(AcademyColors.background).navigationTitle("Legal & support") }
        case "verification": NavigationStack { ScoutVerificationView(apiClient: client) }
        case "introductions", "introductions-empty": NavigationStack { SentContactRequestsView(viewModel: sent, availability: .shared, apiClient: client) }
        case "incoming": NavigationStack { IncomingContactRequestsView(viewModel: incoming, availability: .shared, apiClient: client) }
        case "thread": NavigationStack { if let request = previewRequest { ContactThreadView(contactRequest: request, apiClient: client, availability: .shared) } }
        case "report": ContentReportSheet(subject: .playerProfile(playerID: 900001, name: "Sample Player One"), apiClient: client)
        case "removal": PlayerTakedownRequestSheet(playerID: 900001, apiClient: client)
        case "add-game": AddGameSheet(playerID: -481, playerName: "Sample Player", isGoalkeeper: false, apiClient: client, onSaved: {_ in})
        case "blocked": NavigationStack { BlockedUsersView(apiClient: client) }
        case "gol", "gol-answer": GolChatView(model: gol)
        case "showcase": NavigationStack { ScrollView { ShowcaseSectionView(viewModel: showcase).padding(16) }.background(AcademyColors.background).navigationTitle("Talent Showcase") }
        case "my-club": NavigationStack { MyClubHomeView(apiClient: client) }
        default: RootTabView(launchArguments: ["-initialTab", "account"])
        }
    }

    private var account: AccountView { AccountView(sentRequestsViewModel: sent, incomingRequestsViewModel: incoming, contactAvailability: .shared, destination: $destination, apiClient: client, fixtureDestination: nil, onSignInRequested: {}, onGolRequested: {}) }

    private var previewRequest: ContactRequest? {
        guard let data = try? FloodlightPreview.fixture("contact_requests_sent") else { return nil }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(ContactRequestsResponse.self, from: data).requests.first
    }
}

struct PreviewGolClient: GolAPIClientProtocol {
    func golSuggestions() async throws -> [String] { ["How should I assess a player's progress?", "Explain academy pathways"] }
    func streamGol(_ question: GolQuestion, onEvent: @escaping @MainActor @Sendable (GolSSEEvent) -> Void) async throws {
        await onEvent(.init(type: "usage", data: #"{"free_questions_remaining":2,"credit_balance":0}"#))
        await onEvent(.init(type: "token", data: #"{"content":"**Look for progress over time.**\n\nTrack playing time, read coach feedback, and compare performances in context.\n\nThis is synthetic guidance for an offline review."}"#))
        await onEvent(.init(type: "done", data: "{}"))
    }
}
#endif
