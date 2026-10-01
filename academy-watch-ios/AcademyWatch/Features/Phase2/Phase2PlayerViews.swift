import CoreLocation
import SwiftUI

struct Phase2Page<Content: View>: View {
    let title: String
    let eyebrow: String
    @ViewBuilder let content: () -> Content
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if !eyebrow.isEmpty {
                    Text(eyebrow.uppercased()).font(AcademyType.mono(10)).tracking(1.5).foregroundStyle(
                        AcademyColors.accent)
                }
                if !title.isEmpty {
                    Text(title).font(AcademyType.serif(32)).fixedSize(horizontal: false, vertical: true)
                }
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
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    if !eyebrow.isEmpty { Phase2Eyebrow(text: eyebrow, gold: true) }
                    Text(title).font(AcademyType.serif(22)).fixedSize(horizontal: false, vertical: true)
                    if !detail.isEmpty {
                        Text(detail).font(AcademyType.subheadline).foregroundStyle(AcademyColors.secondaryText)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right").font(.system(size: 14, weight: .light)).foregroundStyle(
                    AcademyColors.secondaryText)
            }.padding(.vertical, 13).frame(minHeight: 44)
            Divider().overlay(AcademyColors.hairline)
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
        #if DEBUG && targetEnvironment(simulator)
            if Phase2Fixtures.active && ProcessInfo.processInfo.arguments.contains("-reviewLocation") {
                coordinate = CLLocationCoordinate2D(latitude: 51.50, longitude: -0.12)
                isWaiting = false
                return
            }
        #endif
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
        #if DEBUG && targetEnvironment(simulator)
            _locationOn = State(
                initialValue: Phase2Fixtures.screen != nil
                    && ProcessInfo.processInfo.arguments.contains("-reviewLocation"))
            _radius = State(initialValue: Phase2Fixtures.screen == "N02b" ? 10 : 50)
        #endif
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
        Phase2Page(title: "", eyebrow: "") {
            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass").foregroundStyle(AcademyColors.secondaryText)
                TextField("Search clubs, town or postcode", text: $query).textFieldStyle(.plain).font(AcademyType.body)
                    .submitLabel(.search)
                    .onSubmit { search() }.accessibilityIdentifier("clubs-search")
                Button(action: search) { Image(systemName: "arrow.right").frame(width: 44, height: 44) }
                    .accessibilityLabel("Search clubs").accessibilityIdentifier("clubs-search-submit")
            }.padding(.leading, 14).background(AcademyColors.elevatedSurface, in: RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(AcademyColors.hairline, lineWidth: 1))
            HStack(spacing: 8) {
                Toggle(isOn: $locationOn) {
                    Label(locationOn ? "Using my location" : "Use my location", systemImage: "location")
                }
                .toggleStyle(Phase2LocationToggleStyle()).onChange(of: locationOn) { _, value in
                    if value {
                        location.request()
                    } else {
                        location.clear()
                        search()
                    }
                }
                if locationOn && location.coordinate != nil {
                    Picker("Within", selection: $radius) {
                        ForEach([10.0, 25, 50, 100, 250], id: \.self) { Text("Within \(Int($0)) km").tag($0) }
                    }.pickerStyle(.menu).font(AcademyType.ui(13)).tint(AcademyColors.text).padding(.horizontal, 12)
                        .frame(minHeight: 44).overlay(Capsule().stroke(AcademyColors.hairline, lineWidth: 1))
                }
            }
            if location.isWaiting { ProgressView("Finding your location…") }
            if !locationOn || location.coordinate == nil {
                Text(location.message ?? "Location is off, so there are no distances.").font(AcademyType.footnote)
                    .foregroundStyle(AcademyColors.secondaryText)
            }
            Phase2Chips(
                choices: [
                    ("", "All levels"), ("grassroots", "Grassroots"), ("amateur", "Amateur"), ("semi_pro", "Semi-pro"),
                    ("professional", "Professional"),
                ], selection: $level)
            Phase2Chips(
                choices: [("", "Anyone"), ("men", "Men"), ("women", "Women"), ("boys", "Boys"), ("girls", "Girls")],
                selection: $programme)
            if !model.clubs.isEmpty { Phase2Section(title: "Near you", trailing: phase2Count(model.total, "club")) }
            if model.isLoading { ProgressView("Finding clubs…") }
            Phase2ErrorView(message: model.error, retry: search)
            ForEach(model.clubs) { club in
                NavigationLink {
                    PublicClubView(slug: club.slug, searchDistance: club.distanceKm, client: client)
                } label: {
                    VStack(spacing: 0) {
                        HStack(spacing: 16) {
                            Phase2ClubCrest(name: club.name, brand: club.brand)
                            VStack(alignment: .leading, spacing: 5) {
                                HStack(spacing: 7) {
                                    Text(club.name).font(AcademyType.serif(25))
                                    if club.verified == true {
                                        Image(systemName: "checkmark.shield").font(.system(size: 14)).foregroundStyle(
                                            AcademyColors.good)
                                    }
                                }
                                Text(
                                    [
                                        club.city, club.clubLevel?.replacingOccurrences(of: "_", with: "-").capitalized,
                                        club.genderPrograms?.map { $0.capitalized }.joined(separator: ", "),
                                    ].compactMap { $0 }.joined(separator: " · ")
                                )
                                .font(AcademyType.subheadline).foregroundStyle(AcademyColors.secondaryText)
                                Phase2Eyebrow(
                                    text: [
                                        club.squadCount.map { phase2Count($0, "squad") },
                                        club.openOpportunities.map { "\($0) open now" },
                                    ].compactMap { $0 }.joined(separator: " · "), gold: true)
                            }.frame(maxWidth: .infinity, alignment: .leading)
                            if locationOn, let distance = club.distanceKm {
                                VStack(spacing: 0) {
                                    Text(
                                        distance >= 10
                                            ? String(format: "%.0f", distance) : String(format: "%.1f", distance)
                                    ).font(AcademyType.serif(32))
                                    Phase2Eyebrow(text: "km")
                                }
                            } else {
                                Text("Distance unavailable").font(AcademyType.mono(9)).foregroundStyle(
                                    AcademyColors.secondaryText
                                ).frame(width: 70)
                            }
                        }.padding(.vertical, 15).frame(minHeight: 44)
                        Divider()
                    }
                }.buttonStyle(.plain).accessibilityIdentifier("club-\(club.id)")
            }
            if !model.isLoading, model.error == nil, model.clubs.isEmpty {
                Phase2EmptyState(
                    title: "Nobody this close, yet.",
                    detail: location.coordinate != nil && locationOn
                        ? "No approved club matches within \(Int(radius)) km. Widen the circle or clear your filters."
                        : "No approved club matches this search. Try another club, town or postcode.",
                    icon: "mappin.and.ellipse",
                    eyebrow: locationOn && location.coordinate != nil
                        ? "0 clubs within \(Int(radius)) km of you" : "0 clubs")
                HStack {
                    if locationOn && location.coordinate != nil && radius < 25 {
                        Button("Widen to 25 km") { radius = 25 }.buttonStyle(FloodlightPillStyle())
                    }
                    Button("Clear filters") {
                        query = ""
                        level = ""
                        programme = ""
                        radius = 50
                        search()
                    }.buttonStyle(FloodlightPillStyle(variant: .outline))
                }
            }
            Phase2Pagination(page: model.page, hasMore: model.hasMore, busy: model.isLoading) { page in
                Task { await model.search(filter, page: page) }
            }
            Text("Only approved clubs are listed. Distances run from your location to the ground pin the club set.")
                .font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
        }.navigationTitle("Clubs").accessibilityIdentifier("phase2-clubs")
            .task {
                if locationOn { location.request() }
                await model.search(filter)
            }.refreshable { await model.search(filter) }
            .onChange(of: location.coordinate?.latitude) { _, _ in search() }
            .onChange(of: radius) { _, _ in search() }
            .onChange(of: level) { _, _ in search() }
            .onChange(of: programme) { _, _ in search() }
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
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                if let club {
                    VStack(alignment: .leading, spacing: 16) {
                        HStack(spacing: 20) {
                            Phase2ClubCrest(name: club.name, brand: club.brand, size: 54)
                            VStack(alignment: .leading, spacing: 7) {
                                Text(club.location.uppercased()).font(AcademyType.mono(10)).tracking(1.8)
                                    .foregroundStyle(
                                        phase2BrandColor(club.brand?.accentColor, fallback: AcademyColors.gold))
                                if club.isVerifiedProgram == true {
                                    Label("Verified club", systemImage: "checkmark.shield").font(
                                        AcademyType.subheadline)
                                }
                            }
                        }
                        Text(club.name).font(AcademyType.serif(42))
                        Text(club.league?.name ?? "Local club").font(AcademyType.subheadline)
                    }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
                        .foregroundStyle(heroForeground(club.brand?.primaryColor)).background(
                            primaryColor(club.brand?.primaryColor))
                    Rectangle().fill(phase2BrandColor(club.brand?.accentColor, fallback: AcademyColors.gold)).frame(
                        height: 4)
                    VStack(alignment: .leading, spacing: 20) {
                        if let facts = club.directory {
                            HStack(alignment: .top, spacing: 20) {
                                clubStat(
                                    facts.clubLevel?.replacingOccurrences(of: "_", with: "-").capitalized ?? "—",
                                    "Level")
                                clubStat(
                                    facts.genderPrograms?.map { $0.capitalized }.joined(separator: ", ") ?? "—",
                                    "Programmes")
                                clubStat(facts.squadCount.map(String.init) ?? "—", "Squads")
                            }
                            Divider()
                            HStack(spacing: 12) {
                                Image(systemName: "mappin.and.ellipse").foregroundStyle(AcademyColors.accent)
                                Text(
                                    [facts.venue?.name, facts.venue?.postcode].compactMap { $0 }.joined(separator: ", ")
                                ).font(AcademyType.subheadline)
                                Spacer()
                                VStack(alignment: .trailing, spacing: 5) {
                                    Phase2Eyebrow(
                                        text: searchDistance.map { String(format: "%.1f km", $0) }
                                            ?? "Distance unavailable")
                                    if searchDistance != nil { Phase2Eyebrow(text: "From your search") }
                                }
                            }.padding(.vertical, 5)
                            Divider()
                        }
                        if let description = club.programProvided?.summary ?? club.description {
                            Text(description).font(AcademyType.body).lineSpacing(5)
                        }
                        if workspace.flags.opportunities {
                            VStack(spacing: 0) {
                                Phase2Section(title: "Open now", trailing: "\(posts.posts.count) open")
                                Phase2ErrorView(
                                    message: posts.error, retry: { Task { await posts.load(programId: club.id) } })
                                ForEach(posts.posts) { post in
                                    NavigationLink {
                                        TrialDetailView(id: post.id, client: client)
                                    } label: {
                                        Phase2Row(
                                            eyebrow: post.typeLabel, title: post.title,
                                            detail: (post.startsAt == nil
                                                ? "No fixed date"
                                                : Phase2Time.display(post.startsAt, zone: post.timezone)) + " · closes "
                                                + Phase2Time.shortDate(post.closesAt, zone: post.timezone))
                                    }.buttonStyle(.plain)
                                }
                                if posts.posts.isEmpty && !posts.isLoading && posts.error == nil {
                                    Text("No open opportunities right now.").font(AcademyType.subheadline).padding(
                                        .vertical, 16)
                                }
                            }
                            if let post = posts.posts.first {
                                Phase2Eyebrow(
                                    text: "Times in "
                                        + Phase2Time.zoneLabel(post.timezone, at: post.startsAt ?? post.closesAt))
                            }
                            Phase2Pagination(page: posts.page, hasMore: posts.hasMore, busy: posts.isLoading) { page in
                                Task { await posts.load(programId: club.id, page: page) }
                            }
                        }
                        Phase2Section(
                            title: "Who can play here", trailing: club.squadCount.map { phase2Count($0, "squad") } ?? ""
                        )
                        Label("Squad lists and under-18 players are never shown on public pages.", systemImage: "lock")
                            .font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
                    }.padding(16)
                } else if error == nil {
                    ProgressView("Loading club…").padding(20)
                }
                Phase2ErrorView(message: error, retry: { Task { await load() } }).padding(.horizontal, 16)
            }
        }.background(AcademyColors.background).foregroundStyle(AcademyColors.text)
            .navigationTitle("").navigationBarTitleDisplayMode(.inline).task { await load() }.refreshable {
                await load()
            }
            .accessibilityIdentifier("phase2-club-page")
            .toolbarBackground(
                phase2BrandColor(club?.brand?.primaryColor, fallback: AcademyColors.club), for: .navigationBar
            )
            .toolbarBackground(.visible, for: .navigationBar).toolbarColorScheme(.dark, for: .navigationBar)
    }
    private func clubStat(_ value: String, _ label: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(value).font(AcademyType.serif(25))
            Phase2Eyebrow(text: label)
        }.frame(maxWidth: .infinity, alignment: .leading)
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
        VStack(spacing: 0) {
            HStack(alignment: .top, spacing: 16) {
                VStack(spacing: 2) {
                    Text(
                        post.startsAt == nil
                            ? "—" : Phase2Time.shortDate(post.startsAt, zone: post.timezone, format: "d")
                    ).font(AcademyType.serif(36))
                    Phase2Eyebrow(
                        text: post.startsAt == nil
                            ? "Open" : Phase2Time.shortDate(post.startsAt, zone: post.timezone, format: "MMM"))
                }.frame(width: 44)
                VStack(alignment: .leading, spacing: 5) {
                    Phase2Eyebrow(text: "\(post.typeLabel) · \(post.clubName)", gold: true)
                    Text(post.title).font(AcademyType.serif(23)).fixedSize(horizontal: false, vertical: true)
                    Text(
                        (post.startsAt == nil
                            ? "No fixed date" : Phase2Time.display(post.startsAt, zone: post.timezone)) + " · "
                            + post.venue
                    ).font(AcademyType.subheadline).foregroundStyle(AcademyColors.secondaryText)
                    Phase2Eyebrow(
                        text: "\(post.genderProgram) · Closes "
                            + Phase2Time.shortDate(post.closesAt, zone: post.timezone, format: "d MMM"))
                }.frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right").font(.system(size: 14, weight: .light)).foregroundStyle(
                    AcademyColors.secondaryText
                ).padding(.top, 24)
            }.padding(.vertical, 16).frame(minHeight: 44)
            Divider()
        }
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
        Phase2Page(title: "", eyebrow: "") {
            Phase2Chips(
                choices: [
                    ("", "All"), ("trial", "Trials"), ("open_session", "Open sessions"), ("position", "Positions"),
                ], selection: $type
            ).accessibilityIdentifier("trials-type")
            HStack {
                Phase2Eyebrow(text: "Open opportunities")
                Spacer()
                Phase2Eyebrow(text: "\(model.posts.count) open")
            }
            if let post = model.posts.first {
                Phase2Eyebrow(
                    text: "Times in " + Phase2Time.zoneLabel(post.timezone, at: post.startsAt ?? post.closesAt))
            }
            Rectangle().fill(AcademyColors.text).frame(height: 1)
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
            Text("PARENTS & GUARDIANS · COMING SOON").font(AcademyType.mono(10)).tracking(1.4)
                .accessibilityLabel("Parents & guardians · coming soon")
            Text("Applying for someone under 18 is not open yet. Leave your own email to hear when it opens.").font(
                AcademyType.subheadline
            ).foregroundStyle(AcademyColors.secondaryText)
            WebDestinationLink(
                url: URL(
                    string: "https://theacademywatch.com/opportunities" + (opportunityId.map { "/\($0)" } ?? "")
                        + "#parent-interest")!, title: "Tell me when")
        }.padding(16).frame(maxWidth: .infinity, alignment: .leading).background(
            AcademyColors.elevatedSurface, in: RoundedRectangle(cornerRadius: 14)
        ).accessibilityIdentifier("applications-parent-coming-soon")
    }
}
struct TrialDetailView: View {
    let client: APIClient
    @EnvironmentObject private var auth: AuthManager
    @EnvironmentObject private var workspace: Phase2Workspace
    @StateObject private var model: TrialDetailViewModel
    @State private var club: Phase2Club?
    init(id: String, client: APIClient) {
        self.client = client
        _model = StateObject(wrappedValue: TrialDetailViewModel(id: id, client: client))
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                if let post = model.post {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("\(post.typeLabel) · \(post.clubName)".uppercased()).font(AcademyType.mono(10)).tracking(
                            1.5
                        ).foregroundStyle(AcademyColors.gold)
                        Text(post.title).font(AcademyType.serif(28)).foregroundStyle(AcademyColors.chalk)
                    }.padding(20).frame(maxWidth: .infinity, alignment: .leading).background(
                        phase2BrandColor(club?.brand?.primaryColor, fallback: AcademyColors.club))
                    Rectangle().fill(phase2BrandColor(club?.brand?.accentColor, fallback: AcademyColors.gold)).frame(
                        height: 4)
                    VStack(alignment: .leading, spacing: 12) {
                        VStack(spacing: 0) {
                            Phase2Fact(
                                label: "When",
                                value: Phase2Time.interval(post.startsAt, post.endsAt, zone: post.timezone),
                                zone: Phase2Time.zoneLabel(post.timezone, at: post.startsAt ?? post.closesAt))
                            Phase2Fact(
                                label: "Where",
                                value: [post.venue, post.address].filter { !$0.isEmpty }.joined(separator: ", "))
                            Phase2Fact(
                                label: "Who",
                                value: "\(post.genderProgram.capitalized) · \(post.positionRequirements)"
                                    + (post.birthYearMin.map {
                                        " · born \($0)–\(post.birthYearMax.map(String.init) ?? "any")"
                                    } ?? ""))
                            Phase2Fact(
                                label: "Closes", value: Phase2Time.display(post.closesAt, zone: post.timezone),
                                zone: Phase2Time.zoneLabel(post.timezone, at: post.closesAt))
                        }
                        Text(post.description).font(AcademyType.body).lineSpacing(4)
                        if !post.instructions.isEmpty {
                            Text(post.instructions).font(AcademyType.subheadline).foregroundStyle(
                                AcademyColors.secondaryText)
                        }
                        if let sent = model.sent {
                            Text("Application sent").font(AcademyType.title2).accessibilityIdentifier(
                                "application-sent")
                            Phase2Status(application: sent)
                            Text(
                                "Deleted by \(Phase2Time.shortDate(sent.retentionExpiresAt, zone: sent.timezone, format: "EEE d MMM yyyy"))"
                            ).font(AcademyType.footnote)
                            NavigationLink("See my application") { ApplicationDetailView(id: sent.id, client: client) }
                                .buttonStyle(FloodlightPillStyle())
                        } else if workspace.flags.applications {
                            Phase2FormCard {
                                Text("Apply").font(AcademyType.serif(28))
                                if !auth.isAuthenticated {
                                    Text("Sign in from Account to apply with your approved adult profile.").font(
                                        AcademyType.subheadline)
                                } else if model.claims.isEmpty && !model.isLoading {
                                    Text(
                                        "Applications require your own approved adult self-profile. Guardian and agent profiles cannot apply."
                                    ).font(AcademyType.subheadline)
                                    NavigationLink("Find or claim your profile") { MyProfilesView(apiClient: client) }
                                } else {
                                    if let claim = model.claims.first(where: { $0.id == model.selectedClaimId }) {
                                        HStack(spacing: 12) {
                                            Phase2Avatar(name: claim.name, size: 40)
                                            VStack(alignment: .leading, spacing: 4) {
                                                Text(claim.name).font(AcademyType.headline)
                                                Phase2Eyebrow(text: "Your approved profile")
                                            }
                                        }
                                    }
                                    if model.claims.count > 1 {
                                        Picker("Your approved profile", selection: $model.selectedClaimId) {
                                            ForEach(model.claims) { claim in Text(claim.name).tag(Optional(claim.id)) }
                                        }
                                    }
                                    Phase2Eyebrow(text: "Position")
                                    TextField("Position", text: $model.position).textFieldStyle(Phase2InputStyle())
                                        .accessibilityIdentifier("apply-position")
                                    HStack {
                                        Phase2Eyebrow(text: "Current club")
                                        Spacer()
                                        Text("Optional").font(AcademyType.footnote).foregroundStyle(
                                            AcademyColors.secondaryText)
                                    }
                                    TextField("Current club", text: $model.currentClub).textFieldStyle(
                                        Phase2InputStyle()
                                    ).accessibilityIdentifier("apply-current-club")
                                    Toggle(
                                        "\(post.clubName) can contact me about this application.",
                                        isOn: $model.contactConsent
                                    ).toggleStyle(Phase2CheckboxStyle()).accessibilityIdentifier(
                                        "apply-contact-consent")
                                    Button(
                                        model.isSending
                                            ? "Sending…"
                                            : model.contactConsent ? "Send application" : "Tick the box to send"
                                    ) { Task { await model.apply() } }
                                    .buttonStyle(FloodlightPillStyle()).disabled(!model.canSend)
                                    .accessibilityIdentifier("apply-send")
                                    Text("The club sees your public profile and what you type here.").font(
                                        AcademyType.footnote
                                    ).foregroundStyle(AcademyColors.secondaryText)
                                }
                                Text(applicationRetentionCopy).font(AcademyType.footnote).foregroundStyle(
                                    AcademyColors.secondaryText)
                            }
                        }
                        ParentsComingSoon(opportunityId: post.id)
                        Phase2ErrorView(message: model.error, retry: reload)
                    }.padding(16)
                } else {
                    ProgressView("Loading opportunity…").padding(20)
                    Phase2ErrorView(message: model.error, retry: reload).padding(16)
                }
            }
        }.background(AcademyColors.background).foregroundStyle(AcademyColors.text)
            .navigationTitle("").navigationBarTitleDisplayMode(.inline).task {
                await model.load(authenticated: auth.isAuthenticated, applications: workspace.flags.applications)
                if let post = model.post {
                    let response: PublicClubResponse? = try? await client.read("programs/\(post.clubSlug)")
                    club = response?.program
                }
                #if DEBUG && targetEnvironment(simulator)
                    if Phase2Fixtures.screen == "N05" {
                        model.position = "Central midfield"
                        model.currentClub = "Quillmere Athletic"
                    }
                #endif
            }.accessibilityIdentifier("phase2-trial-detail")
            .toolbarBackground(
                phase2BrandColor(club?.brand?.primaryColor, fallback: AcademyColors.club), for: .navigationBar
            )
            .toolbarBackground(.visible, for: .navigationBar).toolbarColorScheme(.dark, for: .navigationBar)
    }
    private func reload() {
        Task { await model.load(authenticated: auth.isAuthenticated, applications: workspace.flags.applications) }
    }
}

struct MyApplicationsView: View {
    let client: APIClient
    @EnvironmentObject private var auth: AuthManager
    @EnvironmentObject private var workspace: Phase2Workspace
    @StateObject private var model: ApplicationsViewModel
    init(client: APIClient) {
        self.client = client
        _model = StateObject(wrappedValue: ApplicationsViewModel(client: client))
    }
    private var current: Phase2Application? { model.applications.first(where: { !$0.isTerminal }) }
    var body: some View {
        Phase2Page(title: "", eyebrow: "") {
            if !auth.isAuthenticated {
                Text("Sign in from Account to see your applications.")
            } else {
                if model.isLoading { ProgressView("Checking your applications…") }
                Phase2ErrorView(message: model.error, retry: reload)
                if let current {
                    NavigationLink {
                        ApplicationDetailView(id: current.id, client: client)
                    } label: {
                        VStack(alignment: .leading, spacing: 8) {
                            Phase2Eyebrow(text: current.clubName, gold: true)
                            Text(current.opportunityTitle).font(AcademyType.serif(30)).fixedSize(
                                horizontal: false, vertical: true)
                            Text(
                                "Applied as \(current.position.lowercased()) · deleted by "
                                    + Phase2Time.shortDate(
                                        current.retentionExpiresAt, zone: current.timezone, format: "EEE d MMM yyyy")
                            )
                            .font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }.buttonStyle(.plain).accessibilityIdentifier("application-\(current.id)")
                    ApplicationProgressCard(id: current.id, client: client).id(current.id)
                }
                let earlier = model.applications.filter { $0.id != current?.id }
                if !earlier.isEmpty {
                    Phase2Section(title: current == nil ? "Applications" : "Earlier", trailing: String(earlier.count))
                    ForEach(earlier) { application in
                        NavigationLink {
                            ApplicationDetailView(id: application.id, client: client)
                        } label: {
                            VStack(spacing: 0) {
                                HStack {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(application.opportunityTitle).font(AcademyType.serif(22))
                                        Text(
                                            "Applied "
                                                + Phase2Time.shortDate(
                                                    application.submittedAt, zone: application.timezone)
                                        ).font(AcademyType.subheadline).foregroundStyle(AcademyColors.secondaryText)
                                    }
                                    Spacer()
                                    Phase2Status(application: application)
                                }.padding(.vertical, 12)
                                Divider()
                            }
                        }.buttonStyle(.plain).accessibilityIdentifier("application-\(application.id)")
                    }
                }
                if model.applications.isEmpty && !model.isLoading && model.error == nil {
                    Phase2EmptyState(
                        title: "Nothing sent, yet.",
                        detail:
                            "When you apply for a trial or an open session, every step shows here: applied, invited, decided. Nobody is left guessing.",
                        icon: "tray", eyebrow: "0 applications")
                    HStack {
                        if workspace.flags.opportunities {
                            NavigationLink("Browse trials") { TrialsView(client: client) }.buttonStyle(
                                FloodlightPillStyle())
                        }
                        if workspace.flags.directory {
                            NavigationLink("Clubs near you") { ClubsNearYouView(client: client) }.buttonStyle(
                                FloodlightPillStyle(variant: .outline))
                        }
                    }
                    Divider().padding(.vertical, 10)
                    Label(
                        "You apply with your own approved profile. Applications are for adults; applying for a child is coming soon.",
                        systemImage: "checkmark.shield"
                    )
                    .font(AcademyType.subheadline).foregroundStyle(AcademyColors.secondaryText)
                    ParentsComingSoon(opportunityId: nil)
                }
                Phase2Pagination(page: model.page, hasMore: model.hasMore, busy: model.isLoading) { page in
                    Task { await model.load(page: page) }
                }
                if !model.applications.isEmpty {
                    Text(applicationRetentionCopy + " Signing does not change that.").font(AcademyType.footnote)
                        .foregroundStyle(AcademyColors.secondaryText)
                    if workspace.flags.opportunities {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("STILL LOOKING").font(AcademyType.mono(10)).tracking(1.5).foregroundStyle(
                                AcademyColors.gold)
                            Text("Another door is open.").font(AcademyType.serif(28))
                            Text("You can have more than one application running. Each club only sees its own.").font(
                                AcademyType.subheadline
                            ).foregroundStyle(AcademyColors.mutedDark)
                            NavigationLink("Browse trials") { TrialsView(client: client) }.font(AcademyType.subheadline)
                                .underline().frame(minHeight: 44)
                        }.padding(18).frame(maxWidth: .infinity, alignment: .leading).foregroundStyle(
                            AcademyColors.chalk
                        ).background(AcademyColors.night, in: RoundedRectangle(cornerRadius: 14))
                    }
                }
            }
        }.navigationTitle("Applications").task { if auth.isAuthenticated { await model.load() } }.refreshable {
            if auth.isAuthenticated { await model.load() }
        }.accessibilityIdentifier("phase2-applications")
    }
    private func reload() { Task { await model.load() } }
}
struct ApplicationProgressCard: View {
    @StateObject private var model: ApplicationDetailViewModel
    init(id: String, client: APIClient) {
        _model = StateObject(wrappedValue: ApplicationDetailViewModel(id: id, client: client))
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Phase2ErrorView(message: model.error, retry: { Task { await model.load() } })
            if let application = model.application {
                ApplicationProgressContent(application: application, model: model)
            }
        }.task { await model.load() }
    }
}
struct ApplicationDetailView: View {
    let client: APIClient
    @StateObject private var model: ApplicationDetailViewModel
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
                Text(
                    "Deleted by "
                        + Phase2Time.shortDate(
                            application.retentionExpiresAt, zone: application.timezone, format: "EEE d MMM yyyy")
                ).font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
                ApplicationProgressContent(application: application, model: model)
                Text(applicationRetentionCopy).font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
            }
        }.navigationTitle("Application").task { await model.load() }.refreshable { await model.load() }
            .accessibilityIdentifier("phase2-application-detail")
    }
}
struct ApplicationProgressContent: View {
    let application: Phase2Application
    @ObservedObject var model: ApplicationDetailViewModel
    @State private var confirmation: String?
    private let stages = ["new", "shortlisted", "invited", "attended", "offer", "signed"]
    private var visibleStages: [String] {
        if application.status == "withdrawn" || application.status == "rejected" {
            return (application.events ?? []).map(\.toState).filter { stages.contains($0) } + [application.status]
        }
        return stages
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(visibleStages.enumerated()), id: \.offset) { index, stage in
                let reached =
                    application.isTerminal
                    || (stages.firstIndex(of: stage) ?? 99) <= (stages.firstIndex(of: application.status) ?? -1)
                HStack(alignment: .top, spacing: 15) {
                    VStack(spacing: 4) {
                        Circle().fill(
                            reached
                                ? (stage == application.status ? AcademyColors.accent : AcademyColors.text)
                                : AcademyColors.background
                        )
                        .frame(width: 12, height: 12).overlay(
                            Circle().stroke(reached ? .clear : AcademyColors.hairline, lineWidth: 2))
                        if index != visibleStages.count - 1 {
                            Rectangle().fill(reached ? AcademyColors.text : AcademyColors.hairline).frame(
                                width: 1, height: 15)
                        }
                    }.padding(.top, 5)
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(alignment: .firstTextBaseline) {
                            Text(Phase2Application.label(stage)).font(AcademyType.headline).foregroundStyle(
                                reached ? AcademyColors.text : AcademyColors.secondaryText)
                            Spacer()
                            if let date = application.events?.last(where: { $0.toState == stage })?.createdAt
                                ?? (stage == "new" ? application.submittedAt : nil)
                            {
                                Phase2Eyebrow(text: Phase2Time.shortDate(date, zone: application.timezone))
                            }
                        }.frame(minHeight: 28)
                        if stage == "invited", let trial = application.trialAt, !application.isTerminal {
                            VStack(alignment: .leading, spacing: 10) {
                                Label(
                                    Phase2Time.display(trial, zone: application.timezone) + " · "
                                        + (application.trialVenue ?? ""), systemImage: "calendar"
                                ).font(AcademyType.subheadline.weight(.medium))
                                Text(application.trialInstructions ?? "").font(AcademyType.subheadline).foregroundStyle(
                                    AcademyColors.secondaryText)
                                Phase2Eyebrow(text: Phase2Time.zoneLabel(application.timezone, at: trial))
                                if application.canRespond() {
                                    HStack(spacing: 8) {
                                        Button("Can't make it") { confirmation = "decline" }.buttonStyle(
                                            FloodlightPillStyle(variant: .outline)
                                        ).accessibilityIdentifier("application-decline")
                                        Button("Confirm my place") { confirmation = "accept" }.buttonStyle(
                                            FloodlightPillStyle()
                                        ).accessibilityIdentifier("application-confirm")
                                    }
                                }
                                if application.reservationState == "confirmed" {
                                    Label("Place confirmed · it is yours", systemImage: "checkmark.circle")
                                        .accessibilityIdentifier("application-confirmed")
                                }
                            }.padding(14).frame(maxWidth: .infinity, alignment: .leading).background(
                                AcademyColors.elevatedSurface, in: RoundedRectangle(cornerRadius: 14)
                            ).padding(.bottom, 12)
                        }
                    }
                }.padding(.bottom, 6)
            }
            if !application.isTerminal {
                Button("Withdraw this application", role: .destructive) { confirmation = "withdraw" }
                    .font(AcademyType.subheadline).underline().foregroundStyle(AcademyColors.danger).frame(
                        minHeight: 44
                    ).padding(.leading, 27).accessibilityIdentifier("application-withdraw")
            }
        }.disabled(model.isBusy).confirmationDialog(
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
        }
    }
}
struct ApplicationTimeline: View {
    let application: Phase2Application
    var body: some View {
        HStack(spacing: 4) {
            ForEach(Array(["new", "shortlisted", "invited", "attended", "offer", "signed"].enumerated()), id: \.offset)
            { index, stage in
                Capsule().fill(
                    stage == application.status
                        ? AcademyColors.accent : (index == 0 ? AcademyColors.text : AcademyColors.hairline)
                ).frame(height: 4)
            }
        }.padding(.vertical, 4)
    }
}
