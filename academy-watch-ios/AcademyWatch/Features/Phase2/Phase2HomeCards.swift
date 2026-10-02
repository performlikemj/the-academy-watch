import SwiftUI

struct Phase2HomeCards: View {
    let client: APIClient
    let role: ExperienceRole?
    @EnvironmentObject private var workspace: Phase2Workspace
    @EnvironmentObject private var auth: AuthManager
    @ObservedObject var incoming: IncomingContactRequestsViewModel
    @ObservedObject var availability: ContactFeatureAvailability
    @StateObject private var applications: ApplicationsViewModel
    init(
        client: APIClient, role: ExperienceRole?, incoming: IncomingContactRequestsViewModel,
        availability: ContactFeatureAvailability
    ) {
        self.client = client
        self.role = role
        self.incoming = incoming
        self.availability = availability
        _applications = StateObject(wrappedValue: ApplicationsViewModel(client: client))
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if role == .club, workspace.flags.staff || workspace.flags.opportunities {
                Phase2ClubSelector()
                if let membership = workspace.selected {
                    Text(membership.program.name).font(AcademyType.title2)
                    Text(
                        "\(membership.access.role.capitalized) · \(membership.access.wholeClub ? "Whole club" : "Your assigned squads")"
                    ).font(AcademyType.caption).foregroundStyle(AcademyColors.secondaryText)
                    if workspace.flags.staff && membership.access.can("players.view") {
                        NavigationLink {
                            SquadQuickView(membership: membership, client: client)
                        } label: {
                            Phase2Row(
                                eyebrow: "Your team", title: "Squads",
                                detail: "Players and match footage in your scope.")
                        }.buttonStyle(.plain)
                    }
                    if membership.access.canRecruit, workspace.flags.opportunities {
                        NavigationLink {
                            RecruitingView(client: client, membership: membership)
                        } label: {
                            Phase2Row(
                                eyebrow: "Needs your club", title: "Recruiting",
                                detail: "Review your posts and adult applicants.")
                        }.buttonStyle(.plain).accessibilityIdentifier("home-recruiting")
                    }
                    if workspace.flags.staff && membership.access.canManageAccess {
                        NavigationLink {
                            StaffAccessView(programId: membership.id, client: client)
                        } label: {
                            Phase2Row(
                                eyebrow: "Owner", title: "Staff & access",
                                detail: "Manage who can sign in and which squads they see.")
                        }.buttonStyle(.plain).accessibilityIdentifier("home-staff-access")
                    }
                }
            }
            if role == .club, workspace.hasClubSurface {
                Phase2ErrorView(
                    message: workspace.error,
                    retry: { Task { await workspace.load(authenticated: auth.isAuthenticated) } })
            }
            if role == .player {
                if workspace.flags.applications, auth.isAuthenticated {
                    NavigationLink {
                        MyApplicationsView(client: client)
                    } label: {
                        Phase2Row(
                            eyebrow: "Needs you", title: "Applications",
                            detail: applications.applications.first(where: { $0.canRespond() }).map {
                                "Trial invite · reply needed\n\($0.opportunityTitle)"
                            } ?? "See every step in your applications.")
                    }.buttonStyle(.plain).accessibilityIdentifier("home-applications")
                }
                if workspace.flags.contact, auth.isAuthenticated, !availability.isUnavailable {
                    NavigationLink {
                        IncomingContactRequestsView(
                            viewModel: incoming, availability: availability, apiClient: client)
                    } label: {
                        Phase2Row(
                            eyebrow: "Introductions",
                            title: incoming.actionableRequests.isEmpty ? "Your conversations" : "Introductions need your reply",
                            detail: "Review introductions and decide who you talk to.")
                    }.buttonStyle(.plain).accessibilityIdentifier("home-introductions")
                }
                if workspace.flags.directory {
                    NavigationLink {
                        ClubsNearYouView(client: client)
                    } label: {
                        Phase2Row(
                            eyebrow: "Find your next club", title: "Clubs near you",
                            detail: "Approved clubs, at your own pace.")
                    }.buttonStyle(.plain).accessibilityIdentifier("home-clubs")
                }
                if workspace.flags.opportunities {
                    NavigationLink {
                        TrialsView(client: client)
                    } label: {
                        Phase2Row(
                            eyebrow: "Open doors", title: "All trials",
                            detail: "Trials, open sessions and positions.")
                    }.buttonStyle(.plain).accessibilityIdentifier("home-trials")
                }
            }
        }.task(id: workspace.flags.applications) {
            if workspace.flags.applications && auth.isAuthenticated && role == .player {
                await applications.load()
            }
        }
    }
}

struct Phase2PlayerHome: View {
    let client: APIClient
    @ObservedObject var incoming: IncomingContactRequestsViewModel
    @ObservedObject var availability: ContactFeatureAvailability
    @EnvironmentObject private var workspace: Phase2Workspace
    @EnvironmentObject private var auth: AuthManager
    @StateObject private var applications: ApplicationsViewModel
    @StateObject private var openings: OpportunitiesViewModel
    init(
        client: APIClient, incoming: IncomingContactRequestsViewModel,
        availability: ContactFeatureAvailability,
        onNavigate: @escaping (RootTab) -> Void,
        onSignIn: @escaping () -> Void
    ) {
        self.client = client
        self.onNavigate = onNavigate
        self.onSignIn = onSignIn
        self.incoming = incoming
        self.availability = availability
        _applications = StateObject(wrappedValue: ApplicationsViewModel(client: client))
        _openings = StateObject(wrappedValue: OpportunitiesViewModel(client: client))
    }
    let onNavigate: (RootTab) -> Void
    let onSignIn: () -> Void
    private var invitations: [Phase2Application] {
        workspace.flags.applications ? applications.applications.filter { $0.canRespond() } : []
    }
    private var introductions: [ContactRequest] {
        workspace.flags.contact && !availability.isUnavailable
            ? incoming.actionableRequests : []
    }
    private var waiting: Int { invitations.count + introductions.count }
    private var waitingCopy: String {
        guard auth.isAuthenticated else { return "Find your next step." }
        if workspace.flags.applications && !applications.isComplete {
            return applications.error == nil ? "Checking what needs you…" : "Applications could not be checked."
        }
        if workspace.flags.contact && !availability.isUnavailable && !incoming.isComplete {
            return incoming.errorMessage == nil ? "Checking what needs you…" : "Introductions could not be checked."
        }
        return waiting == 0 ? "You're all caught up." : "\(waiting) \(waiting == 1 ? "thing is" : "things are") waiting on you."
    }
    private var firstName: String {
        auth.displayName?.split(separator: " ").first.map(String.init) ?? "there"
    }
    private var heroDate: Date {
        #if DEBUG && targetEnvironment(simulator)
            if Phase2Fixtures.active { return Phase2Time.date("2026-10-01T18:00:00Z")! }
        #endif
        return Date()
    }
    private var greeting: String {
        var calendar = Calendar.current
        #if DEBUG && targetEnvironment(simulator)
            if Phase2Fixtures.active { calendar.timeZone = TimeZone(identifier: "Europe/London")! }
        #endif
        let hour = calendar.component(.hour, from: heroDate)
        return hour < 12 ? "Good morning," : hour < 17 ? "Good afternoon," : "Good evening,"
    }
    private var dateEyebrow: String {
        let formatter = DateFormatter()
        formatter.locale = .current
        formatter.setLocalizedDateFormatFromTemplate("EEEE d MMMM")
        #if DEBUG && targetEnvironment(simulator)
            if Phase2Fixtures.active { formatter.timeZone = TimeZone(identifier: "Europe/London")! }
        #endif
        return formatter.string(from: heroDate).uppercased()
    }
    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                VStack(alignment: .leading, spacing: 9) {
                        Text(dateEyebrow)
                            .font(AcademyType.mono(10)).tracking(2).foregroundStyle(AcademyColors.gold)
                        (Text(greeting + " ").font(AcademyType.serif(40)).foregroundColor(AcademyColors.chalk)
                            + Text(firstName + ".").font(AcademyType.serif(40, italic: true)).foregroundColor(
                                AcademyColors.gold))
                            .fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("home-greeting")
                        Text(
                            waitingCopy
                        )
                        .font(AcademyType.subheadline).foregroundStyle(AcademyColors.mutedDark)
                        .fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("home-waiting")
                    }.padding(.horizontal, 20).padding(.vertical, 18)
                    .frame(maxWidth: .infinity, minHeight: 174, alignment: .bottomLeading)
                    .background {
                        GeometryReader { geometry in
                            Image("FootballAtmosphere").resizable().scaledToFill()
                                .frame(width: geometry.size.width, height: geometry.size.height).clipped().opacity(0.42)
                        }
                        LinearGradient(
                            colors: [AcademyColors.night.opacity(0.15), AcademyColors.night.opacity(0.92)],
                            startPoint: .top, endPoint: .bottom)
                    }.background(AcademyColors.night)
                VStack(alignment: .leading, spacing: 20) {
                    if !auth.isAuthenticated {
                        Button(action: onSignIn) {
                            Phase2Row(eyebrow: "Your next step", title: "Sign in to get started",
                                      detail: "Sign in with an email code to use your approved profile.")
                        }.buttonStyle(.plain).accessibilityIdentifier("home-sign-in")
                    }
                    if workspace.flags.contact && auth.isAuthenticated && !availability.isUnavailable {
                        Phase2ErrorView(message: incoming.errorMessage, retry: { Task { await incoming.reload() } })
                    }
                    if waiting > 0 {
                        VStack(spacing: 0) {
                            Phase2Section(title: "Needs you", trailing: phase2Count(waiting, "thing"))
                            ForEach(invitations) { application in
                                NavigationLink {
                                    ApplicationDetailView(id: application.id, client: client)
                                } label: {
                                    homeNeed(
                                        icon: "calendar", eyebrow: "Trial invite · reply needed",
                                        title: application.opportunityTitle,
                                        detail: Phase2Time.display(
                                            application.trialAt, zone: application.timezone)
                                            + " · " + (application.trialVenue ?? ""),
                                        zone: Phase2Time.zoneLabel(
                                            application.timezone, at: application.trialAt))
                                }.buttonStyle(.plain).accessibilityIdentifier(
                                    "home-application-invite-\(application.id)")
                            }
                            ForEach(introductions) { request in
                                NavigationLink {
                                    IncomingContactRequestsView(
                                        viewModel: incoming, availability: availability, apiClient: client)
                                } label: {
                                    homeNeed(
                                        icon: "bubble.left", eyebrow: request.playerActionEyebrow,
                                        title: "A verified scout wants to talk",
                                        detail: request.playerActionDetail)
                                }.buttonStyle(.plain).accessibilityIdentifier("home-introductions")
                            }
                        }
                    }
                    if workspace.flags.applications && auth.isAuthenticated {
                        VStack(alignment: .leading, spacing: 0) {
                            Phase2ErrorView(message: applications.error, retry: { Task { await applications.load() } })
                            Phase2Section(
                                title: "Applications", trailing: applications.isComplete ? "\(applications.applications.count) sent" : "")
                            ForEach(applications.applications.prefix(3)) { application in
                                NavigationLink {
                                    ApplicationDetailView(id: application.id, client: client)
                                } label: {
                                    HStack(spacing: 12) {
                                        VStack(alignment: .leading, spacing: 5) {
                                            Text(application.opportunityTitle).font(AcademyType.serif(20))
                                            Phase2Eyebrow(
                                                text: application.clubName + " · "
                                                    + Phase2Time.shortDate(
                                                        application.submittedAt, zone: application.timezone,
                                                        format: "d MMM"))
                                        }.frame(maxWidth: .infinity, alignment: .leading)
                                        Phase2Status(application: application).frame(
                                            maxWidth: 118, alignment: .trailing)
                                    }.padding(.vertical, 13)
                                    Divider()
                                }.buttonStyle(.plain)
                            }
                            NavigationLink("See every step") { MyApplicationsView(client: client) }
                                .font(AcademyType.subheadline.weight(.medium)).underline().frame(
                                    minHeight: 44
                                )
                                .accessibilityIdentifier("home-applications")
                        }
                    }
                    if workspace.flags.opportunities {
                        VStack(alignment: .leading, spacing: 0) {
                            Phase2Eyebrow(text: "Open near you").padding(.bottom, 10)
                            Divider()
                            // The public endpoint has no distance: use its titles/dates without inventing proximity.
                            ForEach(
                                openings.posts.filter { post in
                                    !applications.applications.contains { $0.opportunityId == post.id }
                                }.prefix(2)
                            ) { post in
                                NavigationLink {
                                    TrialDetailView(id: post.id, client: client).phase2BrowseDestinations(client: client)
                                } label: {
                                    HStack {
                                        Text(post.title).font(AcademyType.serif(20))
                                        Spacer(minLength: 8)
                                        Phase2Eyebrow(
                                            text: Phase2Time.shortDate(post.startsAt, zone: post.timezone))
                                    }.padding(.vertical, 12)
                                    Divider()
                                }.buttonStyle(.plain)
                            }
                            Text("Open opportunities · distance unavailable").font(AcademyType.footnote)
                                .foregroundStyle(AcademyColors.secondaryText).padding(.top, 8)
                        }
                    }
                    VStack(spacing: 0) {
                        Phase2Section(title: "Your scouting", trailing: "")
                        ForEach([RootTab.scoutDesk, .watchlist, .lists]) { tab in
                            Button {
                                onNavigate(tab)
                            } label: {
                                Phase2Row(
                                    eyebrow: "",
                                    title: tab == .scoutDesk
                                        ? "Explore players" : tab == .watchlist ? "Watchlist" : "Lists",
                                    detail: tab == .scoutDesk
                                        ? "Discover profiles and compare players."
                                        : tab == .watchlist
                                            ? "The players you follow." : "Your scouting shortlists.")
                            }.buttonStyle(.plain).accessibilityIdentifier("home-scout-\(tab.rawValue)")
                        }
                    }
                    HStack(spacing: 10) {
                        if workspace.flags.directory {
                            NavigationLink {
                                ClubsNearYouView(client: client)
                            } label: {
                                Label("Clubs near you", systemImage: "mappin.and.ellipse")
                            }
                            .buttonStyle(FloodlightPillStyle(variant: .outline)).accessibilityIdentifier(
                                "home-clubs")
                        }
                        if workspace.flags.opportunities {
                            NavigationLink {
                                TrialsView(client: client)
                            } label: {
                                Label("All trials", systemImage: "flag")
                            }
                            .buttonStyle(FloodlightPillStyle(variant: .outline)).accessibilityIdentifier(
                                "home-trials")
                        }
                    }
                }.padding(16)
            }
        }.background(AcademyColors.background).foregroundStyle(AcademyColors.text)
            .task(id: workspace.flags) {
                if workspace.flags.applications && auth.isAuthenticated { await applications.load() }
                if workspace.flags.opportunities { await openings.load() }
            }
    }
    private func homeNeed(
        icon: String, eyebrow: String, title: String, detail: String, zone: String? = nil
    )
        -> some View
    {
        VStack(spacing: 0) {
            HStack(spacing: 14) {
                Image(systemName: icon).font(.system(size: 20, weight: .light)).foregroundStyle(
                    AcademyColors.accent
                )
                .frame(width: 44, height: 44).background(AcademyColors.elevatedSurface, in: Circle())
                VStack(alignment: .leading, spacing: 4) {
                    Phase2Eyebrow(text: eyebrow, gold: true)
                    Text(title).font(AcademyType.serif(21))
                    Text(detail).font(AcademyType.subheadline).foregroundStyle(AcademyColors.secondaryText)
                    if let zone { Phase2Eyebrow(text: zone) }
                }.frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right").font(.system(size: 14, weight: .light)).foregroundStyle(
                    AcademyColors.secondaryText)
            }.padding(.vertical, 13).frame(minHeight: 44)
            Divider()
        }
    }
}
