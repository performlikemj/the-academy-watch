#if DEBUG && targetEnvironment(simulator)
    import SwiftUI

    struct Phase2PreviewRoot: View {
        let screen: String
        @StateObject private var workspace: Phase2Workspace
        @StateObject private var auth: AuthManager
        @StateObject private var watchlist: WatchlistViewModel
        @State private var post: Phase2Opportunity?
        @State private var request: ContactRequest?
        @State private var chosenTab: RootTab?
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
                    if !Phase2ReviewCapture.isActive {
                        Text("OFFLINE FIXTURE · WENDLESHIRE").font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(
                                AcademyColors.secondaryText
                            ).allowsHitTesting(false).offset(y: -10)
                    }
                }
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    if chosenTab == nil && ["N03", "N05", "N09", "N09b", "N10", "N13"].contains(screen) {
                        let role: ExperienceRole = Phase2Fixtures.isClubExperience ? .club : .player
                        Phase2TabBar(
                            tabs: RootTab.available(
                                for: role, flags: workspace.flags, access: workspace.selected?.access), role: role,
                            selection: Binding(
                                get: {
                                    screen == "N03"
                                        ? .clubs : screen == "N05" ? .trials : screen == "N13" ? .account : .recruiting
                                }, set: { chosenTab = $0 })
                        )
                        .frame(height: 64).padding(.horizontal, 14).padding(.top, 8).padding(.bottom, 4).background(
                            AcademyColors.background)
                    }
                }
                .task {
                    await workspace.load(authenticated: true)
                    let response: OpportunitiesResponse? = try? await client.read("club/101/opportunities")
                    post = response?.opportunities.first
                    let data = try? FloodlightPreview.fixture("contact_requests_sent")
                    let decoder = JSONDecoder()
                    decoder.keyDecodingStrategy = .convertFromSnakeCase
                    if let data {
                        request = try? decoder.decode(
                            ContactRequestsResponse.self, from: Phase2Fixtures.contactFixture(data, messages: false)
                        ).requests.first
                    }
                }
        }
        @ViewBuilder private var content: some View {
            if let chosenTab {
                RootTabView(launchArguments: ["-initialTab", chosenTab.rawValue])
            } else {
                switch screen {
                case "loader-green", "loader-claret", "loader-navy", "loader-gold", "loader-still":
                    CleatLoader(phase: screen == "loader-claret" ? 1 : screen == "loader-navy" ? 2 : screen == "loader-gold" ? 3 : 0,
                                reduceMotionOverride: screen == "loader-still")
                        .frame(maxWidth: .infinity, maxHeight: .infinity).background(AcademyColors.background)
                case "post-empty", "post-error":
                    NavigationStack {
                        if workspace.flags.opportunities {
                            OpportunityEditorView(programId: 101, flags: workspace.flags, client: client)
                        }
                    }
                case "post-filled", "post-locked":
                    NavigationStack {
                        if let post {
                            OpportunityEditorView(programId: 101, post: post, flags: workspace.flags, client: client)
                        }
                    }
                case "N01": RootTabView(launchArguments: ["-initialTab", "home"])
                case "N02", "N02b": RootTabView(launchArguments: ["-initialTab", "clubs"])
                case "N03":
                    NavigationStack {
                        PublicClubView(slug: "quillmere-athletic", searchDistance: 0.8, client: client)
                            .toolbar { ToolbarItem(placement: .topBarLeading) { reviewBack("Clubs", tab: .clubs) } }
                    }
                case "N04": RootTabView(launchArguments: ["-initialTab", "trials"])
                case "N05":
                    NavigationStack {
                        if workspace.flags.opportunities {
                            TrialDetailView(id: Phase2FixtureTransport.postId, client: client)
                                .toolbar {
                                    ToolbarItem(placement: .topBarLeading) { reviewBack("Trials", tab: .trials) }
                                }
                        }
                    }
                case "N06", "N06b": RootTabView(launchArguments: ["-initialTab", "applied"])
                case "N09", "N09b":
                    NavigationStack { if let post { RecruitingPipelineView(post: post, client: client) } }
                case "N10":
                    NavigationStack {
                        if let post {
                            RecruitingApplicantView(
                                id: Phase2FixtureTransport.applicationId, post: post, client: client)
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
        private func reviewBack(_ title: String, tab: RootTab) -> some View {
            Button {
                chosenTab = tab
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: "chevron.left")
                    Text(title)
                }
                .font(AcademyType.ui(15)).foregroundStyle(AcademyColors.chalk)
                .frame(minWidth: 74, minHeight: 44).fixedSize(horizontal: true, vertical: false)
            }.buttonStyle(.plain)
        }
    }
#endif
