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
            if role == .club, workspace.flags.staff {
                Phase2ClubSelector()
                if let membership = workspace.selected {
                    Text(membership.program.name).font(AcademyType.title2)
                    Text(
                        "\(membership.access.role.capitalized) · \(membership.access.wholeClub ? "Whole club" : "Your assigned squads")"
                    ).font(AcademyType.caption).foregroundStyle(AcademyColors.secondaryText)
                    if membership.access.can("players.view") {
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
                    if membership.access.canManageAccess {
                        NavigationLink {
                            StaffAccessView(programId: membership.id, client: client)
                        } label: {
                            Phase2Row(
                                eyebrow: "Owner", title: "Staff & access",
                                detail: "Manage who can sign in and which squads they see.")
                        }.buttonStyle(.plain).accessibilityIdentifier("home-staff-access")
                    }
                }
                Phase2ErrorView(message: workspace.error)
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
                        IncomingContactRequestsView(viewModel: incoming, availability: availability, apiClient: client)
                    } label: {
                        Phase2Row(
                            eyebrow: "Introductions",
                            title: incoming.requests.contains {
                                $0.clubConsentStatus == .granted && $0.status == .pending
                            } ? "Your club said yes." : "Your conversations",
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
                            eyebrow: "Open doors", title: "All trials", detail: "Trials, open sessions and positions.")
                    }.buttonStyle(.plain).accessibilityIdentifier("home-trials")
                }
            }
        }.task(id: workspace.flags.applications) {
            if workspace.flags.applications && auth.isAuthenticated && role == .player { await applications.load() }
        }
    }
}
