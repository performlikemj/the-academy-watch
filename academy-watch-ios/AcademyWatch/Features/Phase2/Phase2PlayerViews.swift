import CoreLocation
import SwiftUI

struct Phase2Page<Content: View>: View {
    let title: String
    let eyebrow: String
    @ViewBuilder let content: () -> Content
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if !eyebrow.isEmpty {
                    Text(eyebrow.uppercased()).font(AcademyType.caption).tracking(1.5).foregroundStyle(
                        AcademyColors.accent)
                }
                Text(title).font(AcademyType.largeTitle).fixedSize(horizontal: false, vertical: true)
                content()
            }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
        }.background(AcademyColors.background).foregroundStyle(AcademyColors.text)
            .navigationBarTitleDisplayMode(.inline)
    }
}
struct Phase2ErrorView: View {
    let message: String?
    var retry: (() -> Void)? = nil
    var body: some View {
        if let message {
            VStack(alignment: .leading, spacing: 12) {
                Label(message, systemImage: "exclamationmark.circle").font(AcademyType.subheadline).foregroundStyle(
                    AcademyColors.danger)
                if let retry { Button("Try again", action: retry).buttonStyle(FloodlightPillStyle(variant: .outline)) }
            }.accessibilityIdentifier("phase2-error")
        }
    }
}
struct Phase2Pagination: View {
    let page: Int
    let hasMore: Bool
    let busy: Bool
    let load: (Int) -> Void
    var body: some View {
        if page > 1 || hasMore {
            HStack {
                Button("Previous") { load(page - 1) }.disabled(page <= 1 || busy)
                Spacer()
                Text("Page \(page)").font(AcademyType.caption)
                Spacer()
                Button("Next") { load(page + 1) }.disabled(!hasMore || busy)
            }.frame(minHeight: 44)
        }
    }
}
struct Phase2Row: View {
    let eyebrow: String
    let title: String
    let detail: String
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(eyebrow.uppercased()).font(AcademyType.caption).tracking(1).foregroundStyle(AcademyColors.accent)
            HStack(alignment: .firstTextBaseline) {
                Text(title).font(AcademyType.title2)
                Spacer(minLength: 8)
                Image(systemName: "arrow.up.right").font(AcademyType.footnote)
            }
            Text(detail).font(AcademyType.subheadline).foregroundStyle(AcademyColors.secondaryText)
            Divider().overlay(AcademyColors.hairline).padding(.top, 8)
        }.frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
    }
}

@MainActor
final class DirectoryLocation: NSObject, ObservableObject, @preconcurrency CLLocationManagerDelegate {
    @Published private(set) var coordinate: CLLocationCoordinate2D?
    @Published private(set) var message: String?
    @Published private(set) var isWaiting = false
    private let manager = CLLocationManager()
    private var requested = false
    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyKilometer
    }
    func request() {
        requested = true
        coordinate = nil
        message = nil
        isWaiting = true
        if manager.authorizationStatus == .notDetermined { manager.requestWhenInUseAuthorization() } else { locate() }
    }
    func clear() {
        requested = false
        manager.stopUpdatingLocation()
        coordinate = nil
        message = nil
        isWaiting = false
    }
    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) { if requested { locate() } }
    private func locate() {
        guard requested else { return }
        if manager.authorizationStatus == .authorizedWhenInUse || manager.authorizationStatus == .authorizedAlways {
            manager.requestLocation()
        } else if manager.authorizationStatus != .notDetermined {
            message = "Location is off or unavailable, so there are no distances."
            isWaiting = false
        }
    }
    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard requested, let location = locations.last else { return }
        coordinate = location.coordinate
        isWaiting = false
    }
    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        coordinate = nil
        message = "Location is unavailable. You can still search by club, town or postcode."
        isWaiting = false
    }
}

struct ClubsNearYouView: View {
    let client: APIClient
    @StateObject private var model: DirectoryViewModel
    @StateObject private var location = DirectoryLocation()
    @State private var query = ""
    @State private var level = ""
    @State private var programme = ""
    @State private var radius = 50.0
    @State private var locationOn = false
    init(client: APIClient) {
        self.client = client
        _model = StateObject(wrappedValue: DirectoryViewModel(client: client))
    }
    private var filter: DirectorySearch {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return DirectorySearch(
            q: q.isEmpty ? nil : q, lat: locationOn ? location.coordinate?.latitude : nil,
            lng: locationOn ? location.coordinate?.longitude : nil,
            radiusKm: locationOn && location.coordinate != nil ? radius : nil, level: level.isEmpty ? nil : level,
            programme: programme.isEmpty ? nil : programme)
    }
    var body: some View {
        Phase2Page(title: "Clubs near you", eyebrow: "Find your next chapter") {
            TextField("Club, town or postcode", text: $query).textFieldStyle(.roundedBorder).submitLabel(.search)
                .onSubmit { search() }.accessibilityIdentifier("clubs-search")
            Toggle("Use my location", isOn: $locationOn).onChange(of: locationOn) { _, value in
                if value {
                    location.request()
                } else {
                    location.clear()
                    search()
                }
            }
            if location.isWaiting { ProgressView("Finding your location…") }
            if locationOn, location.coordinate != nil {
                Picker("Within", selection: $radius) {
                    ForEach([10.0, 25, 50, 100, 250], id: \.self) { Text("\(Int($0)) km").tag($0) }
                }.pickerStyle(.menu)
            } else {
                Text(location.message ?? "Location is off, so there are no distances.").font(AcademyType.footnote)
                    .foregroundStyle(AcademyColors.secondaryText)
            }
            HStack {
                Picker("Level", selection: $level) {
                    Text("All levels").tag("")
                    Text("Grassroots").tag("grassroots")
                    Text("Amateur").tag("amateur")
                    Text("Semi-pro").tag("semi_pro")
                    Text("Professional").tag("professional")
                }
                Picker("Programme", selection: $programme) {
                    Text("Anyone").tag("")
                    ForEach(["men", "women", "boys", "girls"], id: \.self) { Text($0.capitalized).tag($0) }
                }
            }.pickerStyle(.menu)
            Button("Search clubs", action: search).buttonStyle(FloodlightPillStyle()).accessibilityIdentifier(
                "clubs-search-submit")
            if model.isLoading { ProgressView("Finding clubs…") }
            Phase2ErrorView(message: model.error, retry: search)
            ForEach(model.clubs) { club in
                NavigationLink {
                    PublicClubView(slug: club.slug, searchDistance: club.distanceKm, client: client)
                } label: {
                    Phase2Row(
                        eyebrow: club.verified == true ? "Verified club · \(club.location)" : club.location,
                        title: club.name,
                        detail: [
                            club.clubLevel?.replacingOccurrences(of: "_", with: " ").capitalized,
                            club.genderPrograms?.map { $0.capitalized }.joined(separator: ", "),
                            locationOn ? club.distance : "Distance unavailable",
                            club.openOpportunities.map { "\($0) open opportunities" },
                        ].compactMap { $0 }.joined(separator: " · "))
                }.buttonStyle(.plain).accessibilityIdentifier("club-\(club.id)")
            }
            if !model.isLoading, model.error == nil, model.clubs.isEmpty {
                FloodlightEmptyState(
                    title: "Nobody this close, yet.", systemImage: "shield",
                    description: location.coordinate != nil && locationOn
                        ? "No approved club matches within \(Int(radius)) km. Widen the circle or clear your filters."
                        : "No approved club matches this search. Try another club, town or postcode.")
                Button("Clear filters") {
                    query = ""
                    level = ""
                    programme = ""
                    radius = 50
                    search()
                }.buttonStyle(FloodlightPillStyle(variant: .outline))
            }
            Phase2Pagination(page: model.page, hasMore: model.hasMore, busy: model.isLoading) { page in
                Task { await model.search(filter, page: page) }
            }
            Text("Only approved clubs are listed. Distances run from your location to the ground pin the club set.")
                .font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
        }.navigationTitle("Clubs").accessibilityIdentifier("phase2-clubs")
            .task { await model.search(filter) }.refreshable { await model.search(filter) }
            .onChange(of: location.coordinate?.latitude) { _, _ in search() }
            .onChange(of: radius) { _, _ in search() }
            .onDisappear { location.clear() }
    }
    private func search() { Task { await model.search(filter) } }
}

struct PublicClubView: View {
    let slug: String
    let searchDistance: Double?
    let client: APIClient
    @EnvironmentObject private var workspace: Phase2Workspace
    @State private var club: Phase2Club?
    @State private var error: String?
    @StateObject private var posts: OpportunitiesViewModel
    init(slug: String, searchDistance: Double? = nil, client: APIClient) {
        self.slug = slug
        self.searchDistance = searchDistance
        self.client = client
        _posts = StateObject(wrappedValue: OpportunitiesViewModel(client: client))
    }
    var body: some View {
        Phase2Page(title: club?.name ?? "Club", eyebrow: club?.location ?? "Your next club") {
            Phase2ErrorView(message: error, retry: { Task { await load() } })
            if let club {
                VStack(alignment: .leading, spacing: 12) {
                    if club.isVerifiedProgram == true {
                        Label("Verified club", systemImage: "checkmark.shield").font(AcademyType.caption)
                    }
                    Text(club.league?.name ?? "Local club").font(AcademyType.headline)
                    Text(club.location).font(AcademyType.subheadline)
                }.foregroundStyle(heroForeground(club.brand?.primaryColor)).padding(22).frame(
                    maxWidth: .infinity, alignment: .leading
                ).background(primaryColor(club.brand?.primaryColor), in: RoundedRectangle(cornerRadius: 10))
                if let facts = club.directory {
                    Text(
                        [
                            facts.clubLevel?.replacingOccurrences(of: "_", with: " ").capitalized,
                            facts.genderPrograms?.map { $0.capitalized }.joined(separator: ", "),
                            facts.squadCount.map { "\($0) squads" },
                        ].compactMap { $0 }.joined(separator: " · ")
                    ).font(AcademyType.headline)
                    if let venue = facts.venue {
                        Label(
                            [venue.name, venue.postcode].compactMap { $0 }.joined(separator: ", "),
                            systemImage: "mappin"
                        ).font(AcademyType.subheadline)
                    }
                }
                Text(searchDistance.map { String(format: "%.1f km · from your search", $0) } ?? "Distance unavailable")
                    .font(AcademyType.caption).foregroundStyle(AcademyColors.secondaryText)
                if let description = club.programProvided?.summary ?? club.description {
                    Text(description).font(AcademyType.body)
                }
                if workspace.flags.opportunities {
                    Text("Open now").font(AcademyType.title2)
                    Divider()
                    Phase2ErrorView(message: posts.error, retry: { Task { await posts.load(programId: club.id) } })
                    ForEach(posts.posts) { post in
                        NavigationLink {
                            TrialDetailView(id: post.id, client: client)
                        } label: {
                            OpportunityRow(post: post)
                        }.buttonStyle(.plain)
                    }
                    if posts.posts.isEmpty, !posts.isLoading, posts.error == nil {
                        Text("No open opportunities right now.").foregroundStyle(AcademyColors.secondaryText)
                    }
                    Phase2Pagination(page: posts.page, hasMore: posts.hasMore, busy: posts.isLoading) { page in
                        Task { await posts.load(programId: club.id, page: page) }
                    }
                }
            } else if error == nil {
                ProgressView("Loading club…")
            }
        }.navigationTitle("Club page").task { await load() }.refreshable { await load() }.accessibilityIdentifier(
            "phase2-club-page")
    }
    private func load() async {
        club = nil
        error = nil
        do {
            let response: PublicClubResponse = try await client.read("programs/\(slug)")
            guard !Task.isCancelled else { return }
            club = response.program
            if workspace.flags.opportunities { await posts.load(programId: response.program.id) }
        } catch { self.error = phase2Error(error) }
    }
    private func heroForeground(_ raw: String?) -> Color {
        guard let raw, raw.count == 7, let hex = UInt32(raw.dropFirst(), radix: 16) else { return AcademyColors.chalk }
        func luminance(_ value: UInt32) -> Double {
            let channel = Double(value) / 255
            return channel <= 0.04045 ? channel / 12.92 : pow((channel + 0.055) / 1.055, 2.4)
        }
        let light =
            0.2126 * luminance((hex >> 16) & 255) + 0.7152 * luminance((hex >> 8) & 255) + 0.0722 * luminance(hex & 255)
        return light > 0.35 ? AcademyColors.ink : AcademyColors.chalk
    }
    private func primaryColor(_ raw: String?) -> Color {
        guard let raw, raw.hasPrefix("#"), raw.count == 7, let hex = UInt32(raw.dropFirst(), radix: 16) else {
            return AcademyColors.club
        }
        // Hero text always sits on the token night layer for readable contrast.
        return Color(hex: hex)
    }
}

struct OpportunityRow: View {
    let post: Phase2Opportunity
    var body: some View {
        Phase2Row(
            eyebrow: "\(post.typeLabel) · \(post.clubName)", title: post.title,
            detail:
                "\(Phase2Time.display(post.startsAt ?? post.closesAt, zone: post.timezone))\n\(Phase2Time.zoneLabel(post.timezone, at: post.startsAt ?? post.closesAt))\n\(post.venue) · \(post.positionRequirements)"
        )
    }
}
struct TrialsView: View {
    let client: APIClient
    @StateObject private var model: OpportunitiesViewModel
    @State private var type = ""
    init(client: APIClient) {
        self.client = client
        _model = StateObject(wrappedValue: OpportunitiesViewModel(client: client))
    }
    var body: some View {
        Phase2Page(title: "An open door.", eyebrow: "Trials & opportunities") {
            Picker("Type", selection: $type) {
                Text("All").tag("")
                Text("Trials").tag("trial")
                Text("Open sessions").tag("open_session")
                Text("Positions").tag("position")
            }.pickerStyle(.menu).accessibilityIdentifier("trials-type")
            Text("Ordered by closing date. Every time is shown in the club's stated zone.").font(AcademyType.footnote)
                .foregroundStyle(AcademyColors.secondaryText)
            if model.isLoading { ProgressView("Finding opportunities…") }
            Phase2ErrorView(message: model.error, retry: reload)
            ForEach(model.posts) { post in
                NavigationLink {
                    TrialDetailView(id: post.id, client: client)
                } label: {
                    OpportunityRow(post: post)
                }.buttonStyle(.plain).accessibilityIdentifier("trial-\(post.id)")
            }
            if model.posts.isEmpty, !model.isLoading, model.error == nil {
                FloodlightEmptyState(
                    title: "More doors will open.", systemImage: "soccerball",
                    description: "There are no open opportunities matching this filter. Check back soon.")
            }
            Phase2Pagination(page: model.page, hasMore: model.hasMore, busy: model.isLoading) { page in
                Task { await model.load(type: type, page: page) }
            }
        }.navigationTitle("Trials").task { await model.load(type: type) }.refreshable { await model.load(type: type) }
            .onChange(of: type) { _, _ in reload() }.accessibilityIdentifier("phase2-trials")
    }
    private func reload() { Task { await model.load(type: type) } }
}

let applicationRetentionCopy =
    "Application data, including signed outcomes, is deleted by the earlier of 90 days after the session or closing date and 180 days after submission."
struct ParentsComingSoon: View {
    let opportunityId: String?
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Parents & guardians · coming soon").font(AcademyType.headline)
            Text("Applying for someone under 18 is not open yet. Leave your own email to hear when it opens.").font(
                AcademyType.subheadline
            ).foregroundStyle(AcademyColors.secondaryText)
            WebDestinationLink(
                url: URL(
                    string: "https://theacademywatch.com/opportunities" + (opportunityId.map { "/\($0)" } ?? "")
                        + "#parent-interest")!, title: "Tell me when")
        }.homeCard().accessibilityIdentifier("applications-parent-coming-soon")
    }
}
struct TrialDetailView: View {
    let client: APIClient
    @EnvironmentObject private var auth: AuthManager
    @EnvironmentObject private var workspace: Phase2Workspace
    @StateObject private var model: TrialDetailViewModel
    init(id: String, client: APIClient) {
        self.client = client
        _model = StateObject(wrappedValue: TrialDetailViewModel(id: id, client: client))
    }
    var body: some View {
        Phase2Page(
            title: model.post?.title ?? "Opportunity",
            eyebrow: model.post.map { "\($0.typeLabel) · \($0.clubName)" } ?? "Your next step"
        ) {
            if model.isLoading { ProgressView("Loading opportunity…") }
            if let post = model.post {
                VStack(alignment: .leading, spacing: 12) {
                    Text(Phase2Time.display(post.startsAt ?? post.closesAt, zone: post.timezone)).font(
                        AcademyType.title2)
                    Text(Phase2Time.zoneLabel(post.timezone, at: post.startsAt ?? post.closesAt)).font(
                        AcademyType.caption)
                    Label(
                        [post.venue, post.address].filter { !$0.isEmpty }.joined(separator: ", "), systemImage: "mappin"
                    )
                    Text("\(post.genderProgram.capitalized) · \(post.positionRequirements)")
                    if post.birthYearMin != nil || post.birthYearMax != nil {
                        Text(
                            "Birth years: \(post.birthYearMin.map(String.init) ?? "any")–\(post.birthYearMax.map(String.init) ?? "any")"
                        )
                    }
                    Text("Closes \(Phase2Time.display(post.closesAt, zone: post.timezone))")
                    Text("Run by · Club coaching team").font(AcademyType.caption)
                }.font(AcademyType.subheadline)
                Divider()
                Text(post.description).font(AcademyType.body)
                if !post.instructions.isEmpty { Text(post.instructions).font(AcademyType.body) }
                if let sent = model.sent {
                    Text("Application sent.").font(AcademyType.title2).accessibilityIdentifier("application-sent")
                    Text("\(sent.clubName) has your profile. Every step shows in My applications.")
                    Text("Deleted by \(Phase2Time.display(sent.retentionExpiresAt, zone: sent.timezone))").font(
                        AcademyType.footnote)
                    NavigationLink("See my application") { ApplicationDetailView(id: sent.id, client: client) }
                        .buttonStyle(FloodlightPillStyle())
                } else if workspace.flags.applications {
                    Text("Apply").font(AcademyType.title2)
                    Divider()
                    if !auth.isAuthenticated {
                        Text("Sign in from Account to apply with your approved adult profile.").font(
                            AcademyType.subheadline)
                    } else if model.claims.isEmpty, !model.isLoading {
                        Text(
                            "Applications require your own approved adult self-profile. Guardian and agent profiles cannot apply."
                        ).font(AcademyType.subheadline)
                        NavigationLink("Find or claim your profile") { MyProfilesView(apiClient: client) }
                    } else {
                        Picker("Your approved profile", selection: $model.selectedClaimId) {
                            ForEach(model.claims) { claim in Text(claim.name).tag(Optional(claim.id)) }
                        }
                        TextField("Position", text: $model.position).textFieldStyle(.roundedBorder)
                            .accessibilityIdentifier("apply-position")
                        TextField("Current club (optional)", text: $model.currentClub).textFieldStyle(.roundedBorder)
                            .accessibilityIdentifier("apply-current-club")
                        Toggle("\(post.clubName) can contact me about this application.", isOn: $model.contactConsent)
                            .accessibilityIdentifier("apply-contact-consent")
                        Button(model.isSending ? "Sending…" : "Send application") { Task { await model.apply() } }
                            .buttonStyle(FloodlightPillStyle()).disabled(!model.canSend).accessibilityIdentifier(
                                "apply-send")
                    }
                    Text(applicationRetentionCopy).font(AcademyType.footnote).foregroundStyle(
                        AcademyColors.secondaryText)
                }
                ParentsComingSoon(opportunityId: post.id)
            }
            Phase2ErrorView(
                message: model.error,
                retry: {
                    Task {
                        await model.load(
                            authenticated: auth.isAuthenticated, applications: workspace.flags.applications)
                    }
                })
        }.navigationTitle("Trial detail").task {
            await model.load(authenticated: auth.isAuthenticated, applications: workspace.flags.applications)
        }.accessibilityIdentifier("phase2-trial-detail")
    }
}

struct MyApplicationsView: View {
    let client: APIClient
    @EnvironmentObject private var auth: AuthManager
    @StateObject private var model: ApplicationsViewModel
    init(client: APIClient) {
        self.client = client
        _model = StateObject(wrappedValue: ApplicationsViewModel(client: client))
    }
    var body: some View {
        Phase2Page(title: "Every step, here.", eyebrow: "My applications") {
            if !auth.isAuthenticated {
                Text("Sign in from Account to see your applications.")
            } else {
                if model.isLoading { ProgressView("Checking your applications…") }
                Phase2ErrorView(message: model.error, retry: reload)
                ForEach(model.applications) { application in
                    NavigationLink {
                        ApplicationDetailView(id: application.id, client: client)
                    } label: {
                        Phase2Row(
                            eyebrow: application.statusLabel, title: application.opportunityTitle,
                            detail:
                                "\(application.clubName) · \(application.position)\nDeleted by \(Phase2Time.display(application.retentionExpiresAt, zone: application.timezone))"
                        )
                    }.buttonStyle(.plain).accessibilityIdentifier("application-\(application.id)")
                }
                if model.applications.isEmpty, !model.isLoading, model.error == nil {
                    FloodlightEmptyState(
                        title: "Nothing sent, yet.", systemImage: "paperplane",
                        description: "When you apply for a trial or open session, every step shows here.")
                    NavigationLink("Browse trials") { TrialsView(client: client) }.buttonStyle(FloodlightPillStyle())
                    ParentsComingSoon(opportunityId: nil)
                }
                Phase2Pagination(page: model.page, hasMore: model.hasMore, busy: model.isLoading) { page in
                    Task { await model.load(page: page) }
                }
                Text(applicationRetentionCopy).font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
            }
        }.navigationTitle("Applications").task { if auth.isAuthenticated { await model.load() } }.refreshable {
            if auth.isAuthenticated { await model.load() }
        }.accessibilityIdentifier("phase2-applications")
    }
    private func reload() { Task { await model.load() } }
}

struct ApplicationDetailView: View {
    let client: APIClient
    @StateObject private var model: ApplicationDetailViewModel
    @State private var confirmation: String?
    init(id: String, client: APIClient) {
        self.client = client
        _model = StateObject(wrappedValue: ApplicationDetailViewModel(id: id, client: client))
    }
    var body: some View {
        Phase2Page(
            title: model.application?.opportunityTitle ?? "Your application",
            eyebrow: model.application?.statusLabel ?? "Applications"
        ) {
            if model.isBusy { ProgressView("Updating application…") }
            Phase2ErrorView(message: model.error, retry: { Task { await model.load() } })
            if let application = model.application {
                Text("\(application.clubName) · Applied as \(application.position)").font(AcademyType.subheadline)
                Text("Deleted by \(Phase2Time.display(application.retentionExpiresAt, zone: application.timezone))")
                    .font(AcademyType.caption).foregroundStyle(AcademyColors.secondaryText)
                ApplicationTimeline(application: application)
                if let trial = application.trialAt, !application.isTerminal {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(Phase2Time.display(trial, zone: application.timezone)).font(AcademyType.title2)
                        Text(Phase2Time.zoneLabel(application.timezone, at: trial)).font(AcademyType.caption)
                        Text(application.trialVenue ?? "")
                        Text(application.trialInstructions ?? "")
                        if application.canRespond() {
                            Button("Confirm my place") { confirmation = "accept" }.buttonStyle(FloodlightPillStyle())
                                .accessibilityIdentifier("application-confirm")
                            Button("Can't make it") { confirmation = "decline" }.buttonStyle(
                                FloodlightPillStyle(variant: .outline)
                            ).accessibilityIdentifier("application-decline")
                        }
                        if application.reservationState == "confirmed" {
                            Label("Place confirmed · it is yours", systemImage: "checkmark.circle")
                                .accessibilityIdentifier("application-confirmed")
                        }
                    }.homeCard()
                }
                if !application.isTerminal {
                    Button("Withdraw this application", role: .destructive) { confirmation = "withdraw" }
                        .accessibilityIdentifier("application-withdraw")
                }
                Text(applicationRetentionCopy).font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
            }
        }.navigationTitle("Application").task { await model.load() }.refreshable { await model.load() }
            .confirmationDialog(
                confirmation == "accept"
                    ? "Confirm your place?"
                    : confirmation == "decline" ? "Decline and withdraw?" : "Withdraw this application?",
                isPresented: Binding(get: { confirmation != nil }, set: { if !$0 { confirmation = nil } }),
                titleVisibility: .visible
            ) {
                let action = confirmation ?? "withdraw"
                Button(
                    action == "accept" ? "Confirm place" : action == "decline" ? "Decline trial" : "Withdraw",
                    role: action == "accept" ? nil : .destructive
                ) {
                    confirmation = nil
                    Task { await model.applicantAction(action) }
                }
            }.disabled(model.isBusy).accessibilityIdentifier("phase2-application-detail")
    }
}
struct ApplicationTimeline: View {
    let application: Phase2Application
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Your progress").font(AcademyType.title2)
            Divider()
            if let events = application.events {
                ForEach(events) { event in
                    Label(
                        Phase2Application.label(event.toState) + " · "
                            + Phase2Time.display(event.createdAt, zone: application.timezone),
                        systemImage: "circle.fill"
                    ).font(AcademyType.footnote)
                }
            } else {
                Label(
                    "Applied · " + Phase2Time.display(application.submittedAt, zone: application.timezone),
                    systemImage: "checkmark.circle")
                if application.status != "new" { Label(application.statusLabel, systemImage: "circle.fill") }
            }
        }
    }
}
