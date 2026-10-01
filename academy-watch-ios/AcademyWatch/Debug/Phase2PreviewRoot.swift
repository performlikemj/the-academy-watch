#if DEBUG && targetEnvironment(simulator)
    import SwiftUI

    struct Phase2PreviewRoot: View {
        let screen: String
        @StateObject private var workspace: Phase2Workspace
        @StateObject private var auth: AuthManager
        @StateObject private var watchlist: WatchlistViewModel
        @State private var post: Phase2Opportunity?
        @State private var request: ContactRequest?
        private let client: APIClient
        init(screen: String) {
            self.screen = screen
            let auth = AuthManager(
                authClient: APIClient(), tokenStore: ExperienceTokenStore(),
                fixtureState: .signedIn(
                    email: "phase2@fixture.invalid", accountRole: .player, displayName: "Reuben Castellane",
                    isVerifiedScout: false))
            let client = APIClient(authSession: auth)
            self.client = client
            _auth = StateObject(wrappedValue: auth)
            _workspace = StateObject(wrappedValue: Phase2Workspace(client: client))
            _watchlist = StateObject(wrappedValue: WatchlistViewModel(apiClient: client))
        }
        var body: some View {
            content.environmentObject(workspace).environmentObject(auth).environmentObject(watchlist)
                .overlay(alignment: .top) {
                    Text("OFFLINE FIXTURE · WENDLESHIRE").font(.system(size: 9, design: .monospaced)).foregroundStyle(
                        AcademyColors.secondaryText
                    ).allowsHitTesting(false).offset(y: -10)
                }
                .task {
                    await workspace.load(authenticated: true)
                    let response: OpportunitiesResponse? = try? await client.read("club/101/opportunities")
                    post = response?.opportunities.first
                    let data = try? FloodlightPreview.fixture("contact_requests_sent")
                    let decoder = JSONDecoder()
                    decoder.keyDecodingStrategy = .convertFromSnakeCase
                    if let data {
                        request = try? decoder.decode(ContactRequestsResponse.self, from: data).requests.first
                    }
                }
        }
        @ViewBuilder private var content: some View {
            switch screen {
            case "N01": RootTabView(launchArguments: ["-initialTab", "home"])
            case "N02", "N02b": RootTabView(launchArguments: ["-initialTab", "clubs"])
            case "N03":
                NavigationStack { PublicClubView(slug: "quillmere-athletic", searchDistance: 0.8, client: client) }
            case "N04": RootTabView(launchArguments: ["-initialTab", "trials"])
            case "N05":
                NavigationStack {
                    if workspace.flags.opportunities {
                        TrialDetailView(id: Phase2FixtureTransport.postId, client: client)
                    }
                }
            case "N06", "N06b": RootTabView(launchArguments: ["-initialTab", "applied"])
            case "N09", "N09b": NavigationStack { if let post { RecruitingPipelineView(post: post, client: client) } }
            case "N10":
                NavigationStack {
                    if let post {
                        RecruitingApplicantView(id: Phase2FixtureTransport.applicationId, post: post, client: client)
                    }
                }
            case "N13": NavigationStack { StaffAccessView(programId: 101, client: client) }
            case "N14": RootTabView(launchArguments: ["-initialTab", "squads"])
            case "N17":
                NavigationStack {
                    if let request {
                        ContactThreadView(contactRequest: request, apiClient: client, availability: .shared)
                    }
                }
            default: RootTabView()
            }
        }
    }
#endif
