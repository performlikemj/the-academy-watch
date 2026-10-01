import SwiftUI

struct Phase2ClubSelector: View {
    @EnvironmentObject private var workspace: Phase2Workspace
    var body: some View {
        if workspace.clubs.count > 1 {
            Picker("Club", selection: $workspace.selectedClubId) {
                ForEach(workspace.clubs) { club in Text(club.program.name).tag(Optional(club.id)) }
            }.pickerStyle(.menu).accessibilityIdentifier("phase2-club-selector")
        }
    }
}
struct RecruitingView: View {
    let client: APIClient
    let membership: ClubMembership
    @EnvironmentObject private var workspace: Phase2Workspace
    @StateObject private var model: OpportunitiesViewModel
    init(client: APIClient, membership: ClubMembership) {
        self.client = client
        self.membership = membership
        _model = StateObject(wrappedValue: OpportunitiesViewModel(client: client))
    }
    var body: some View {
        Phase2Page(title: "Build the next team.", eyebrow: "\(membership.program.name) · Recruiting") {
            Phase2ClubSelector()
            if membership.access.canRecruit && workspace.flags.opportunities {
                if model.isLoading { ProgressView("Loading recruiting…") }
                Phase2ErrorView(message: model.error, retry: reload)
                ForEach(model.posts) { post in
                    if workspace.flags.applications {
                        NavigationLink {
                            RecruitingPipelineView(post: post, client: client)
                        } label: {
                            Phase2Row(
                                eyebrow: post.status.capitalized, title: post.title,
                                detail:
                                    "\(phase2Count(post.applicationCount ?? 0, "applicant")) · \(post.placesLeft.map { phase2Count($0, "place") + " available" } ?? "No capacity limit")"
                            )
                        }.buttonStyle(.plain).accessibilityIdentifier("recruiting-post-\(post.id)")
                    } else {
                        OpportunityRow(post: post)
                    }
                }
                if !model.isLoading, model.posts.isEmpty, model.error == nil {
                    FloodlightEmptyState(
                        title: "Your next opening.", systemImage: "person.badge.plus",
                        description:
                            "Create a trial, open session or position in the club workspace. Your posts and applicants will appear here."
                    )
                }
                Phase2Pagination(page: model.page, hasMore: model.hasMore, busy: model.isLoading) { page in
                    Task { await model.load(programId: membership.id, club: true, page: page) }
                }
            }
        }.navigationTitle("Recruiting").task { await model.load(programId: membership.id, club: true) }.refreshable {
            await model.load(programId: membership.id, club: true)
        }.accessibilityIdentifier("phase2-recruiting")
    }
    private func reload() { Task { await model.load(programId: membership.id, club: true) } }
}

struct RecruitingPipelineView: View {
    let client: APIClient
    @State private var post: Phase2Opportunity
    @StateObject private var model: ApplicationsViewModel
    @State private var stage = "all"
    @State private var error: String?
    @State private var isPublishing = false
    @ScaledMetric(relativeTo: .body) private var applicantRowHeight: CGFloat = 98
    init(post: Phase2Opportunity, client: APIClient) {
        self.client = client
        _post = State(initialValue: post)
        _model = StateObject(wrappedValue: ApplicationsViewModel(client: client))
    }
    private var filtered: [Phase2Application] {
        model.applications.filter { stage == "all" || (stage == "closed" ? $0.isTerminal : $0.status == stage) }
    }
    private var stageChoices: [(String, String)] {
        [
            ("new", "New"), ("shortlisted", "Shortlisted"), ("invited", "Invited"), ("attended", "Attended"),
            ("offer", "Offer"), ("closed", "Closed"),
        ].map { key, name in
            let count = model.applications.filter { key == "closed" ? $0.isTerminal : $0.status == key }.count
            return (key, "\(name)  \(count)")
        }
    }
    var body: some View {
        Phase2Page(
            title: post.title,
            eyebrow:
                "\(post.typeLabel) · \(post.status == "draft" ? "Draft" : "Closes " + Phase2Time.shortDate(post.closesAt, zone: post.timezone))"
        ) {
            Phase2Eyebrow(
                text: phase2Count(post.applicationCount ?? model.applications.count, "applicant") + " · "
                    + (post.status == "draft"
                        ? "Not published" : post.capacity.map { phase2Count($0, "place") } ?? "No capacity limit")
                    + (post.status == "draft" ? "" : post.placesLeft.map { " · \($0) available" } ?? ""))
            if post.status != "draft" {
                Phase2Eyebrow(
                    text: "Trial times in " + Phase2Time.zoneLabel(post.timezone, at: post.startsAt ?? post.closesAt))
                Phase2Chips(choices: stageChoices, selection: $stage).accessibilityIdentifier("pipeline-stage")
                if model.hasMore || model.page > 1 { Phase2Eyebrow(text: "Stage counts on this page") }
            }
            Rectangle().fill(AcademyColors.text).frame(height: 1)
            if model.isLoading { ProgressView("Loading applicants…") }
            Phase2ErrorView(message: model.error, retry: reload)
            Phase2ErrorView(message: error)
            List {
                ForEach(filtered) { application in
                    ApplicantSwipeRow(
                        application: application, post: post, client: client,
                        changed: {
                            await model.load(programId: post.programId, opportunityId: post.id, page: model.page)
                        }
                    ) {
                        NavigationLink {
                            RecruitingApplicantView(id: application.id, post: post, client: client)
                        } label: {
                            VStack(spacing: 0) {
                                HStack(spacing: 16) {
                                    Phase2Avatar(name: application.applicantName ?? "Adult applicant", size: 48)
                                    VStack(alignment: .leading, spacing: 5) {
                                        Text(application.applicantName ?? "Adult applicant").font(AcademyType.serif(22))
                                            .lineLimit(1)
                                        Text(
                                            [
                                                application.position,
                                                application.currentClub.isEmpty
                                                    ? "no current club" : application.currentClub,
                                            ].joined(separator: " · ")
                                        ).font(AcademyType.subheadline).foregroundStyle(AcademyColors.secondaryText)
                                        Phase2Eyebrow(
                                            text: "Applied "
                                                + Phase2Time.shortDate(
                                                    application.submittedAt, zone: application.timezone))
                                        if application.isTerminal { Phase2Status(application: application) }
                                    }.frame(maxWidth: .infinity, alignment: .leading)
                                }.padding(.vertical, 14).frame(minHeight: 44)
                                Divider()
                            }
                        }.buttonStyle(.plain).accessibilityIdentifier("applicant-\(application.id)")
                    }.frame(minHeight: applicantRowHeight).listRowInsets(EdgeInsets())
                        .listRowBackground(AcademyColors.background)
                        .listRowSeparator(.hidden)
                }
            }.listStyle(.plain).scrollDisabled(true).scrollContentBackground(.hidden)
                .frame(height: CGFloat(filtered.count) * applicantRowHeight)
            if filtered.contains(where: { $0.canTransition(to: "shortlisted") }) {
                Phase2Eyebrow(text: "← Swipe a name left to move it on")
            }
            if filtered.isEmpty && !model.isLoading && model.error == nil {
                Phase2EmptyState(
                    title: post.status == "draft" ? "Nobody can see this yet." : "A place for someone new.",
                    detail: post.status == "draft"
                        ? "It is a draft, visible only to the owner and manager. Publish it and adult players can apply with their profile. Applicants appear here, newest first."
                        : "No applicants in this stage on this page. Applications will appear here as they arrive.",
                    icon: "eye")
                if post.status == "draft" {
                    HStack {
                        Button(isPublishing ? "Publishing…" : "Publish") { Task { await publish() } }.buttonStyle(
                            FloodlightPillStyle()
                        ).disabled(isPublishing).accessibilityIdentifier("recruiting-publish")
                        LegalSafariLink(destination: .clubConsole) { Text("Edit the post") }.buttonStyle(
                            FloodlightPillStyle(variant: .outline))
                    }
                    Divider().padding(.top, 14)
                    Text(
                        "Closes " + Phase2Time.shortDate(post.closesAt, zone: post.timezone)
                            + ". You can close it sooner once you have who you need."
                    ).font(AcademyType.subheadline).foregroundStyle(AcademyColors.secondaryText)
                }
            }
            Phase2Pagination(page: model.page, hasMore: model.hasMore, busy: model.isLoading) { page in
                Task { await model.load(programId: post.programId, opportunityId: post.id, page: page) }
            }
        }.navigationTitle("Applicants").task {
            await model.load(programId: post.programId, opportunityId: post.id)
            if stage == "all" { stage = model.applications.first?.status ?? "new" }
        }.refreshable { await model.load(programId: post.programId, opportunityId: post.id) }.accessibilityIdentifier(
            "phase2-pipeline")
    }
    private func reload() { Task { await model.load(programId: post.programId, opportunityId: post.id) } }
    private func publish() async {
        guard !isPublishing else { return }
        isPublishing = true
        error = nil
        defer { isPublishing = false }
        do {
            let result: OpportunityResponse = try await client.write(
                "club/\(post.programId)/opportunities/\(post.id)", method: "PATCH",
                body: VersionAction(expectedVersion: post.version, status: "published"))
            post = result.opportunity
            reload()
        } catch { self.error = phase2Error(error) }
    }
}

private struct ApplicantSwipeRow<Content: View>: View {
    let application: Phase2Application
    let changed: () async -> Void
    @ViewBuilder let content: () -> Content
    @StateObject private var detail: ApplicationDetailViewModel
    @State private var reject = false
    init(
        application: Phase2Application, post: Phase2Opportunity, client: APIClient,
        changed: @escaping () async -> Void, @ViewBuilder content: @escaping () -> Content
    ) {
        self.application = application
        self.changed = changed
        self.content = content
        _detail = StateObject(
            wrappedValue: ApplicationDetailViewModel(id: application.id, programId: post.programId, client: client))
    }
    var body: some View {
        VStack(spacing: 0) {
            content().frame(maxWidth: .infinity).disabled(detail.isBusy)
                .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                    if application.canTransition(to: "rejected") {
                        Button {
                            reject = true
                        } label: {
                            Label("Not selected", systemImage: "xmark")
                        }
                        .tint(AcademyColors.danger).accessibilityIdentifier("pipeline-reject-" + application.id)
                    }
                    if application.canTransition(to: "shortlisted") {
                        Button {
                            Task { await move("shortlisted") }
                        } label: {
                            Label("Shortlist", systemImage: "arrow.right")
                        }
                        .tint(AcademyColors.good).accessibilityIdentifier("pipeline-shortlist-" + application.id)
                    }
                }
            Phase2ErrorView(message: detail.error)
        }.confirmationDialog("Not select this applicant?", isPresented: $reject, titleVisibility: .visible) {
            Button("Not selected", role: .destructive) { Task { await move("rejected") } }
        }
    }
    private func move(_ status: String) async {
        await detail.load()
        guard detail.application?.canTransition(to: status) == true else { return }
        await detail.transition(status)
        if detail.error == nil {
            await changed()
        }
    }
}

struct RecruitingApplicantView: View {
    let post: Phase2Opportunity
    let client: APIClient
    @StateObject private var model: ApplicationDetailViewModel
    @State private var transitionConfirmation: String?
    @FocusState private var noteIsFocused: Bool
    init(id: String, post: Phase2Opportunity, client: APIClient) {
        self.post = post
        self.client = client
        _model = StateObject(
            wrappedValue: ApplicationDetailViewModel(id: id, programId: post.programId, client: client))
    }
    var body: some View {
        Phase2Page(title: "", eyebrow: "") {
            if model.isBusy { ProgressView("Updating applicant…") }
            Phase2ErrorView(message: model.error, retry: { Task { await model.load() } })
            if let application = model.application {
                HStack(spacing: 14) {
                    Phase2Avatar(name: application.applicantName ?? "Applicant", size: 54)
                    VStack(alignment: .leading, spacing: 5) {
                        Text(application.applicantName ?? "Applicant").font(AcademyType.serif(34))
                        Text(
                            [application.position, application.currentClub].filter { !$0.isEmpty }.joined(
                                separator: " · ")
                        ).font(AcademyType.subheadline).foregroundStyle(AcademyColors.secondaryText)
                    }
                }
                ApplicationTimeline(application: application)
                HStack {
                    Phase2Eyebrow(text: application.statusLabel)
                    Spacer()
                    Phase2Eyebrow(text: application.canTransition(to: "invited") ? "Next · Invite" : "Recruiting")
                }
                Divider()
                NavigationLink {
                    PlayerDetailView(playerID: application.signedPlayerId, apiClient: client)
                } label: {
                    HStack {
                        Label("Their public profile", systemImage: "eye")
                        Spacer()
                        Image(systemName: "chevron.right").font(.system(size: 14, weight: .light))
                    }.font(AcademyType.subheadline).frame(minHeight: 44)
                }.accessibilityIdentifier("applicant-profile")
                Divider()
                if application.canTransition(to: "invited") {
                    Phase2FormCard {
                        Text("Invite to a trial").font(AcademyType.serif(28))
                        HStack(alignment: .top, spacing: 12) {
                            VStack(alignment: .leading, spacing: 8) {
                                Phase2Eyebrow(text: "Date")
                                Phase2DateControl(date: $model.trialDate, zone: Phase2Time.zone(application.timezone))
                                    .accessibilityIdentifier("invite-trial-date")
                            }
                            VStack(alignment: .leading, spacing: 8) {
                                Phase2Eyebrow(
                                    text: "Time ("
                                        + Phase2Time.shortDate(
                                            Phase2Time.submission(model.trialDate, zone: application.timezone),
                                            zone: application.timezone, format: "z") + ")")
                                Phase2DateControl(
                                    date: $model.trialDate, zone: Phase2Time.zone(application.timezone), timeOnly: true
                                ).accessibilityIdentifier("invite-trial-time")
                            }
                        }.environment(\.timeZone, Phase2Time.zone(application.timezone))
                        Phase2Eyebrow(
                            text: Phase2Time.zoneLabel(
                                application.timezone,
                                at: Phase2Time.submission(model.trialDate, zone: application.timezone)))
                        Phase2Eyebrow(text: "Where")
                        TextField("Where", text: $model.venue).textFieldStyle(Phase2InputStyle())
                            .accessibilityIdentifier("invite-venue")
                        Phase2Eyebrow(text: "What to tell them")
                        TextField("What to tell them", text: $model.instructions, axis: .vertical).textFieldStyle(
                            Phase2InputStyle()
                        ).accessibilityIdentifier("invite-instructions")
                        if let available = post.placesLeft {
                            Phase2Eyebrow(text: phase2Count(available, "place") + " available · Club only")
                        }
                        Text("Reserves one place; confirmation keeps it, decline or withdrawal releases it.").font(
                            AcademyType.footnote
                        ).foregroundStyle(AcademyColors.secondaryText)
                        HStack(spacing: 10) {
                            if application.canTransition(to: "rejected") {
                                Button("Not selected") { transitionConfirmation = "rejected" }.buttonStyle(
                                    FloodlightPillStyle(variant: .outline)
                                ).accessibilityIdentifier("applicant-rejected")
                            }
                            Button("Send invite") { Task { await model.transition("invited") } }.buttonStyle(
                                FloodlightPillStyle()
                            ).disabled(model.venue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                                .accessibilityIdentifier("applicant-invite")
                        }
                    }
                }
                if let trial = application.trialAt, !application.isTerminal {
                    Text(Phase2Time.display(trial, zone: application.timezone)).font(AcademyType.serif(24))
                    Phase2Eyebrow(text: Phase2Time.zoneLabel(application.timezone, at: trial))
                    Text(
                        "\(application.trialVenue ?? "") · \(application.reservationState == "confirmed" ? "Place confirmed" : "Waiting for player to confirm")"
                    ).font(AcademyType.subheadline)
                }
                ForEach(
                    (application.transitions ?? []).filter {
                        $0 != "invited" && ($0 != "rejected" || !application.canTransition(to: "invited"))
                    }, id: \.self
                ) { target in
                    Button(
                        target == "rejected" ? "Not selected" : "Mark \(Phase2Application.label(target).lowercased())"
                    ) { transitionConfirmation = target }
                    .buttonStyle(FloodlightPillStyle(variant: target == "rejected" ? .outline : .primary)).disabled(
                        !application.canTransition(to: target)
                    ).accessibilityIdentifier("applicant-\(target)")
                }
                if application.transitions?.contains("attended") == true && !application.canTransition(to: "attended") {
                    Text("Attendance unlocks after the player confirms and the trial has passed.").font(
                        AcademyType.footnote)
                }
                Phase2Section(title: "Private notes", trailing: "Only your club")
                ForEach(application.notes ?? []) { note in
                    VStack(alignment: .leading, spacing: 10) {
                        Phase2Eyebrow(text: Phase2Time.display(note.createdAt, zone: application.timezone))
                        Text(note.body).font(AcademyType.body).lineSpacing(4)
                        Divider()
                    }
                }
                HStack(alignment: .bottom, spacing: 8) {
                    TextField("Add a note for the club…", text: $model.note, axis: .vertical).textFieldStyle(
                        Phase2InputStyle()
                    ).lineLimit(1...4).focused($noteIsFocused).accessibilityIdentifier("applicant-note")
                    Button {
                        Task { await model.addNote() }
                    } label: {
                        Image(systemName: "plus").font(.system(size: 22, weight: .light)).frame(width: 44, height: 44)
                            .foregroundStyle(AcademyColors.onPrimary).background(
                                AcademyColors.primaryFill, in: Circle())
                    }.disabled(model.note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty).accessibilityLabel(
                        "Save note"
                    ).accessibilityIdentifier("applicant-save-note")
                }
                Text(
                    "The applicant never sees notes. Deleted by \(Phase2Time.shortDate(application.retentionExpiresAt, zone: application.timezone, format: "EEE d MMM yyyy")), signed or not. \(applicationRetentionCopy)"
                ).font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
            }
        }.navigationTitle("Applicant").task {
            await model.load()
            #if DEBUG && targetEnvironment(simulator)
                if Phase2Fixtures.screen == "N10" {
                    model.trialDate = Phase2Time.date("2026-10-06T18:15:00Z")!
                    model.venue = "The Saltings — main pitch"
                    model.instructions = "Report to the clubhouse at 18:45. Grass boots. You train with the full squad."
                }
            #endif
        }.refreshable { await model.load() }.disabled(model.isBusy)
            .toolbar {
                if noteIsFocused {
                    ToolbarItemGroup(placement: .keyboard) {
                        Spacer()
                        Button("Done") { noteIsFocused = false }
                    }
                }
            }
            .sheet(
                isPresented: Binding(
                    get: { transitionConfirmation != nil },
                    set: {
                        if !$0 {
                            transitionConfirmation = nil
                            model.enrollmentConfirmed = false
                        }
                    })
            ) {
                NavigationStack {
                    Phase2Page(
                        title: transitionConfirmation == "signed" ? "Mark as signed?" : "Record this decision?",
                        eyebrow: "Recruiting"
                    ) {
                        if transitionConfirmation == "signed" {
                            Text(
                                "Signing happens outside Academy Watch. Confirm only once the club's own registration is complete."
                            )
                            Toggle("Enrollment completed separately", isOn: $model.enrollmentConfirmed)
                                .accessibilityIdentifier("applicant-enrollment-confirmed")
                        } else {
                            Text("The player will see the updated status. Your private notes stay private.")
                        }
                        Button("Confirm decision") {
                            let target = transitionConfirmation!
                            transitionConfirmation = nil
                            Task { await model.transition(target) }
                        }.buttonStyle(FloodlightPillStyle()).disabled(
                            transitionConfirmation == "signed" && !model.enrollmentConfirmed
                        ).accessibilityIdentifier("applicant-confirm-decision")
                        Button("Cancel") {
                            transitionConfirmation = nil
                            model.enrollmentConfirmed = false
                        }
                    }
                }.presentationDetents([.medium, .large])
            }.accessibilityIdentifier("phase2-applicant-detail")
    }
}

struct SquadQuickView: View {
    let membership: ClubMembership
    let client: APIClient
    var matchesOnly = false
    @StateObject private var model: SquadViewModel
    @State private var selectedSquadId: Int?
    init(membership: ClubMembership, client: APIClient, matchesOnly: Bool = false) {
        self.membership = membership
        self.client = client
        self.matchesOnly = matchesOnly
        _model = StateObject(wrappedValue: SquadViewModel(client: client))
    }
    private var members: [SquadMember] {
        model.members.filter { selectedSquadId == nil || $0.squadId == selectedSquadId }
    }
    private var matches: [Phase2Match] {
        model.matches.filter { selectedSquadId == nil || $0.squadId == selectedSquadId }
    }
    var body: some View {
        Phase2Page(title: "", eyebrow: "") {
            Phase2ClubSelector()
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "lock").foregroundStyle(AcademyColors.accent)
                Text(
                    membership.access.wholeClub
                        ? "Your access covers the whole club."
                        : membership.access.allSquads
                            ? "Your access covers all squads. Recruiting and staff administration remain outside a coach's access."
                            : "Your access covers " + model.squads.map(\.name).joined(separator: ", ")
                                + ". These are the squads you see here."
                )
                .font(AcademyType.subheadline)
            }.padding(14).frame(maxWidth: .infinity, alignment: .leading).background(
                AcademyColors.elevatedSurface, in: RoundedRectangle(cornerRadius: 14))
            Phase2Eyebrow(text: membership.program.name, gold: true)
            Text(
                matchesOnly ? "Film Room" : model.squads.first(where: { $0.id == selectedSquadId })?.name ?? "My squads"
            ).font(AcademyType.serif(42))
            Label("CLUB-PRIVATE · NEVER ON A PUBLIC PAGE", systemImage: "checkmark.shield").font(AcademyType.mono(9))
                .tracking(1).foregroundStyle(AcademyColors.secondaryText)
            if model.squads.count > 1 {
                Picker("Squad", selection: $selectedSquadId) {
                    Text("My squads").tag(Optional<Int>.none)
                    ForEach(model.squads) { squad in Text(squad.name).tag(Optional(squad.id)) }
                }.pickerStyle(.menu).accessibilityIdentifier("squad-picker")
            }
            if model.isLoading { ProgressView("Loading your squads…") }
            Phase2ErrorView(message: model.error, retry: { Task { await model.load(programId: membership.id) } })
            Rectangle().fill(AcademyColors.text).frame(height: 1)
            HStack(spacing: 20) {
                if !matchesOnly { squadStat(members.count, "Player") }
                squadStat(matches.count, "Match filmed", plural: "Matches filmed")
            }
            Divider()
            if !matchesOnly {
                VStack(spacing: 0) {
                    ForEach(members) { member in
                        HStack(spacing: 18) {
                            Text(member.shirtNumber.map(String.init) ?? "—").font(AcademyType.serif(26))
                                .foregroundStyle(AcademyColors.accent).frame(width: 28, alignment: .leading)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(member.privateName).font(AcademyType.headline)
                                Text(member.position ?? "Position unavailable").font(AcademyType.subheadline)
                                    .foregroundStyle(AcademyColors.secondaryText)
                            }.frame(maxWidth: .infinity, alignment: .leading)
                        }.padding(.vertical, 12).frame(minHeight: 44).accessibilityIdentifier(
                            "squad-player-\(member.id)")
                        Divider()
                    }
                }
                if members.isEmpty && !model.isLoading && model.error == nil {
                    Text("No players in this squad yet.").font(AcademyType.subheadline)
                }
            }
            ForEach(matches) { match in
                VStack(alignment: .leading, spacing: 8) {
                    Text("FILM ROOM · " + match.status.replacingOccurrences(of: "_", with: " ").uppercased()).font(
                        AcademyType.mono(10)
                    ).tracking(1.5).foregroundStyle(AcademyColors.gold)
                    Text(match.opponentName.map { "v \($0)" } ?? match.title ?? "Club match").font(
                        AcademyType.serif(24)
                    ).foregroundStyle(AcademyColors.chalk)
                    if let date = match.matchDate {
                        Text(date).font(AcademyType.footnote).foregroundStyle(AcademyColors.mutedDark)
                    }
                }.padding(18).frame(maxWidth: .infinity, alignment: .leading).background(
                    AcademyColors.night, in: RoundedRectangle(cornerRadius: 14))
            }
            if matches.isEmpty && !model.isLoading && model.error == nil {
                Text("No filmed matches in your scope yet.").font(AcademyType.subheadline)
            }
            Text("Check Film Room for analysis. Your access includes only the squads assigned by the club owner.").font(
                AcademyType.footnote
            ).foregroundStyle(AcademyColors.secondaryText)
        }.navigationTitle(matchesOnly ? "Matches" : "Squads").toolbar {
            ToolbarItem(placement: .topBarTrailing) { Phase2Eyebrow(text: membership.access.role) }
        }
        .task {
            await model.load(programId: membership.id)
            if selectedSquadId == nil && model.squads.count == 1 { selectedSquadId = model.squads.first?.id }
        }
        .refreshable { await model.load(programId: membership.id) }.accessibilityIdentifier(
            matchesOnly ? "phase2-matches" : "phase2-squads")
    }
    private func squadStat(_ count: Int, _ label: String, plural: String? = nil) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(String(count)).font(AcademyType.serif(32))
            Phase2Eyebrow(text: count == 1 ? label : plural ?? label + "s")
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct StaffAccessView: View {
    @StateObject private var model: StaffViewModel
    @State private var email = ""
    @State private var role = "coach"
    @State private var allSquads = false
    @State private var squadIds = Set<Int>()
    @State private var editing: StaffPerson?
    @State private var revokePerson: StaffPerson?
    @State private var revokeInvite: StaffInvite?
    @FocusState private var inviteEmailFocused: Bool
    init(programId: Int, client: APIClient) {
        _model = StateObject(wrappedValue: StaffViewModel(programId: programId, client: client))
    }
    var body: some View {
        Phase2Page(title: "", eyebrow: "") {
            Text("Who can sign in, and which squads they see. Owner only.").font(AcademyType.subheadline)
                .foregroundStyle(
                    AcademyColors.secondaryText)
            if model.isBusy { ProgressView("Updating access…") }
            Phase2ErrorView(message: model.error, retry: { Task { await model.load() } })
            if let notice = model.notice {
                Text(notice).font(AcademyType.subheadline).accessibilityIdentifier("staff-notice")
            }
            if let board = model.board {
                Phase2Section(title: "People", trailing: "\(board.people.count) with access")
                VStack(spacing: 0) {
                    ForEach(board.people) { person in
                        VStack(alignment: .leading, spacing: 0) {
                            HStack(spacing: 12) {
                                Phase2Avatar(name: person.displayName ?? person.email ?? "Staff", size: 38)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(person.displayName ?? person.email ?? "Club staff").font(AcademyType.headline)
                                    Text(
                                        person.role == "owner"
                                            ? "Everything, including billing and staff"
                                            : person.role == "manager"
                                                ? "Whole club · no billing or staff"
                                                : scopeLabel(all: person.allSquads, ids: person.squadIds)
                                    ).font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
                                }.frame(maxWidth: .infinity, alignment: .leading)
                                if person.editable {
                                    Button {
                                        editing = person
                                    } label: {
                                        Text(person.role.uppercased()).font(AcademyType.mono(9)).tracking(1).padding(
                                            .horizontal, 10
                                        ).padding(.vertical, 5).overlay(
                                            Capsule().stroke(AcademyColors.hairline, lineWidth: 1)
                                        ).frame(minHeight: 44)
                                    }.accessibilityLabel("Edit " + (person.displayName ?? "staff") + " access")
                                        .accessibilityIdentifier("staff-edit-\(person.id)")
                                } else {
                                    Phase2Eyebrow(text: person.role, gold: person.role == "owner")
                                        .padding(.horizontal, 10).padding(.vertical, 5)
                                        .overlay(Capsule().stroke(AcademyColors.hairline, lineWidth: 1)).frame(
                                            minHeight: 44)
                                }
                            }.padding(.vertical, 8)
                            Divider()
                        }.contextMenu {
                            if person.editable {
                                Button("Edit access") { editing = person }
                                Button("Remove access", role: .destructive) { revokePerson = person }
                                    .accessibilityIdentifier("staff-remove-\(person.id)")
                            }
                        }
                    }
                }
                Phase2Section(
                    title: "Invites", trailing: "\(board.invites.filter { $0.status == "pending" }.count) open")
                ForEach(board.invites) { invite in
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(invite.email).font(AcademyType.headline)
                                Text(
                                    "\(invite.role.capitalized) · \(scopeLabel(all: invite.allSquads, ids: invite.squadIds))"
                                ).font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
                            }.frame(maxWidth: .infinity, alignment: .leading)
                            if invite.status == "expired" {
                                Button("Invite again") {
                                    email = invite.email
                                    role = invite.role
                                    allSquads = invite.allSquads
                                    squadIds = Set(invite.squadIds)
                                    inviteEmailFocused = true
                                }.buttonStyle(FloodlightPillStyle(variant: .outline)).accessibilityIdentifier(
                                    "staff-reinvite-\(invite.id)")
                            } else if invite.status == "pending" {
                                Button("Revoke") { revokeInvite = invite }.buttonStyle(
                                    FloodlightPillStyle(variant: .outline)
                                )
                                .accessibilityIdentifier("staff-revoke-\(invite.id)")
                            }
                        }
                        Phase2Eyebrow(
                            text:
                                "\(invite.status) · Expires \(Phase2Time.shortDate(invite.expiresAt, zone: "UTC")) · UTC"
                        )
                        Divider()
                    }
                }
                Phase2FormCard {
                    Text("Invite someone").font(AcademyType.serif(28))
                    Phase2Eyebrow(text: "Their email")
                    TextField("name@club.example", text: $email).keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never).autocorrectionDisabled().textFieldStyle(Phase2InputStyle())
                        .accessibilityIdentifier("staff-invite-email")
                        .focused($inviteEmailFocused)
                        .submitLabel(.done).onSubmit { inviteEmailFocused = false }
                    StaffScopeForm(role: $role, allSquads: $allSquads, squadIds: $squadIds, squads: model.squads)
                    Button("Send invite") {
                        Task {
                            await model.invite(
                                email: email, role: role, allSquads: allSquads, squadIds: Array(squadIds))
                        }
                    }
                    .buttonStyle(FloodlightPillStyle()).disabled(
                        !email.contains("@") || (role != "manager" && !allSquads && squadIds.isEmpty)
                    ).accessibilityIdentifier("staff-invite-send")
                }
            }
        }.navigationTitle("Staff & access").task {
            await model.load()
            #if DEBUG && targetEnvironment(simulator)
                if Phase2Fixtures.screen == "N13" { squadIds = [4] }
            #endif
        }.refreshable { await model.load() }.disabled(
            model.isBusy
        )
        .sheet(item: $editing) { person in StaffEditSheet(person: person, model: model) }
        .confirmationDialog(
            "Remove access?",
            isPresented: Binding(
                get: { revokePerson != nil || revokeInvite != nil },
                set: {
                    if !$0 {
                        revokePerson = nil
                        revokeInvite = nil
                    }
                }), titleVisibility: .visible
        ) {
            Button("Remove", role: .destructive) {
                let person = revokePerson
                let invite = revokeInvite
                revokePerson = nil
                revokeInvite = nil
                Task { await model.revoke(invite: invite, person: person) }
            }
        }.accessibilityIdentifier("phase2-staff")
    }
    private func scopeLabel(all: Bool, ids: [Int]) -> String {
        all ? "All squads" : model.squads.filter { ids.contains($0.id) }.map(\.name).joined(separator: ", ")
    }
}
struct StaffScopeForm: View {
    @Binding var role: String
    @Binding var allSquads: Bool
    @Binding var squadIds: Set<Int>
    let squads: [Phase2Squad]
    var identifierPrefix = "staff"
    private var roleDescription: String {
        switch role {
        case "manager": "Manager: the whole club, including recruiting. No billing or staff administration."
        case "analyst": "Analyst: players and matches in their squads. No recruiting, billing or staff."
        case "viewer": "Viewer: read-only access to their squads. No recruiting, billing or staff."
        default:
            "Coach: their squads' players, matches and feedback. No recruiting, billing or staff, even with all squads."
        }
    }
    var body: some View {
        Phase2Eyebrow(text: "Role")
        HStack(spacing: 0) {
            ForEach(["manager", "coach", "analyst", "viewer"], id: \.self) { choice in
                Button {
                    role = choice
                } label: {
                    Text(choice.capitalized).font(AcademyType.ui(13)).frame(maxWidth: .infinity).frame(height: 44)
                        .foregroundStyle(role == choice ? AcademyColors.background : AcademyColors.text)
                        .background(role == choice ? AcademyColors.text : .clear, in: Capsule())
                }.buttonStyle(.plain).accessibilityAddTraits(role == choice ? .isSelected : [])
            }
        }.accessibilityIdentifier(identifierPrefix + "-role")
        Text(roleDescription + " Invites last 7 days.").font(AcademyType.footnote).foregroundStyle(
            AcademyColors.secondaryText)
        if role != "manager" {
            Phase2Eyebrow(text: "Squads they can see")
            Phase2Flow {
                Toggle("All squads", isOn: $allSquads).toggleStyle(Phase2ChipToggleStyle()).accessibilityIdentifier(
                    identifierPrefix + "-all-squads")
                if !allSquads {
                    ForEach(squads) { squad in
                        Toggle(
                            squad.name,
                            isOn: Binding(
                                get: { squadIds.contains(squad.id) },
                                set: { value in
                                    if value { squadIds.insert(squad.id) } else { squadIds.remove(squad.id) }
                                })
                        ).toggleStyle(Phase2ChipToggleStyle()).accessibilityIdentifier(
                            identifierPrefix + "-squad-\(squad.id)")
                    }
                }
            }
        } else {
            Text("Managers have access to the whole club.").font(AcademyType.footnote)
        }
    }
}
struct StaffEditSheet: View {
    let person: StaffPerson
    @ObservedObject var model: StaffViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var role: String
    @State private var allSquads: Bool
    @State private var squadIds: Set<Int>
    init(person: StaffPerson, model: StaffViewModel) {
        self.person = person
        self.model = model
        _role = State(initialValue: person.role)
        _allSquads = State(initialValue: person.allSquads)
        _squadIds = State(initialValue: Set(person.squadIds))
    }
    var body: some View {
        NavigationStack {
            Phase2Page(title: "Update access", eyebrow: person.displayName ?? person.email ?? "Staff") {
                StaffScopeForm(
                    role: $role, allSquads: $allSquads, squadIds: $squadIds, squads: model.squads,
                    identifierPrefix: "staff-edit")
                Phase2ErrorView(message: model.error)
                DisclosureGroup("Permissions") {
                    ForEach(Array((model.board?.matrix.rows ?? []).enumerated()), id: \.offset) { index, label in
                        Label(
                            label,
                            systemImage: index < person.permissions.count && person.permissions[index]
                                ? "checkmark" : "minus"
                        ).font(AcademyType.footnote).frame(maxWidth: .infinity, alignment: .leading).padding(
                            .vertical, 3)
                    }
                }.font(AcademyType.footnote)
                Button("Save access") {
                    Task {
                        await model.update(person, role: role, allSquads: allSquads, squadIds: Array(squadIds))
                        if model.error == nil { dismiss() }
                    }
                }.buttonStyle(FloodlightPillStyle()).disabled(
                    model.isBusy || (role != "manager" && !allSquads && squadIds.isEmpty)
                ).accessibilityIdentifier("staff-save-access")
                Button("Cancel") { dismiss() }
            }
        }
    }
}
