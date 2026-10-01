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
                                    "\(post.applicationCount ?? 0) applicants · \(post.placesLeft.map { "\($0) places available" } ?? "No capacity limit")"
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
    init(post: Phase2Opportunity, client: APIClient) {
        self.client = client
        _post = State(initialValue: post)
        _model = StateObject(wrappedValue: ApplicationsViewModel(client: client))
    }
    private var filtered: [Phase2Application] {
        model.applications.filter {
            stage == "all" || (stage == "closed" ? ["rejected", "withdrawn"].contains($0.status) : $0.status == stage)
        }
    }
    var body: some View {
        Phase2Page(title: post.title, eyebrow: "Applicants · \(post.status)") {
            Text(
                "\(post.applicationCount ?? model.applications.count) applicants · \(post.capacity.map { "\($0) places" } ?? "No capacity limit") · \(post.placesLeft.map { "\($0) available" } ?? "")"
            ).font(AcademyType.caption)
            Text(Phase2Time.zoneLabel(post.timezone, at: post.startsAt ?? post.closesAt)).font(AcademyType.footnote)
                .foregroundStyle(AcademyColors.secondaryText)
            Picker("Stage", selection: $stage) {
                Text("All stages").tag("all")
                ForEach(["new", "shortlisted", "invited", "attended", "offer", "signed"], id: \.self) {
                    Text(Phase2Application.label($0)).tag($0)
                }
                Text("Closed").tag("closed")
            }.pickerStyle(.menu).accessibilityIdentifier("pipeline-stage")
            if model.isLoading { ProgressView("Loading applicants…") }
            Phase2ErrorView(message: model.error, retry: reload)
            Phase2ErrorView(message: error)
            ForEach(filtered) { application in
                NavigationLink {
                    RecruitingApplicantView(id: application.id, post: post, client: client)
                } label: {
                    Phase2Row(
                        eyebrow: application.statusLabel, title: application.applicantName ?? "Adult applicant",
                        detail: [application.position, application.currentClub].filter { !$0.isEmpty }.joined(
                            separator: " · "))
                }.buttonStyle(.plain).accessibilityIdentifier("applicant-\(application.id)")
            }
            if filtered.isEmpty, !model.isLoading, model.error == nil {
                FloodlightEmptyState(
                    title: post.status == "draft" ? "Nobody can see this yet." : "A place for someone new.",
                    systemImage: "person.2",
                    description: post.status == "draft"
                        ? "This draft is visible only to the owner and manager. Publish it so adult players can apply with their profile."
                        : "No applicants in this stage on this page. Applications will appear here as they arrive.")
                if post.status == "draft" {
                    Button(isPublishing ? "Publishing…" : "Publish") { Task { await publish() } }.buttonStyle(
                        FloodlightPillStyle()
                    ).disabled(isPublishing).accessibilityIdentifier("recruiting-publish")
                }
            }
            Phase2Pagination(page: model.page, hasMore: model.hasMore, busy: model.isLoading) { page in
                Task { await model.load(programId: post.programId, opportunityId: post.id, page: page) }
            }
        }.navigationTitle("Applicants").task { await model.load(programId: post.programId, opportunityId: post.id) }
            .refreshable { await model.load(programId: post.programId, opportunityId: post.id) }
            .accessibilityIdentifier("phase2-pipeline")
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

struct RecruitingApplicantView: View {
    let post: Phase2Opportunity
    let client: APIClient
    @StateObject private var model: ApplicationDetailViewModel
    @State private var transitionConfirmation: String?
    init(id: String, post: Phase2Opportunity, client: APIClient) {
        self.post = post
        self.client = client
        _model = StateObject(
            wrappedValue: ApplicationDetailViewModel(id: id, programId: post.programId, client: client))
    }
    var body: some View {
        Phase2Page(
            title: model.application?.applicantName ?? "Applicant",
            eyebrow: model.application?.statusLabel ?? "Recruiting"
        ) {
            if model.isBusy { ProgressView("Updating applicant…") }
            Phase2ErrorView(message: model.error, retry: { Task { await model.load() } })
            if let application = model.application {
                Text([application.position, application.currentClub].filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(AcademyType.subheadline)
                NavigationLink("Their public profile") {
                    PlayerDetailView(playerID: application.signedPlayerId, apiClient: client)
                }.accessibilityIdentifier("applicant-profile")
                ApplicationTimeline(application: application)
                if application.canTransition(to: "invited") {
                    Text("Invite to a trial").font(AcademyType.title2)
                    Divider()
                    DatePicker(
                        "Trial date & time", selection: $model.trialDate, in: Phase2Time.now...,
                        displayedComponents: [.date, .hourAndMinute]
                    ).environment(\.timeZone, Phase2Time.zone(application.timezone)).accessibilityIdentifier(
                        "invite-trial-date")
                    Text(
                        Phase2Time.zoneLabel(
                            application.timezone, at: Phase2Time.submission(model.trialDate, zone: application.timezone)
                        )
                    ).font(AcademyType.caption)
                    TextField("Where", text: $model.venue).textFieldStyle(.roundedBorder).accessibilityIdentifier(
                        "invite-venue")
                    TextField("What to tell them", text: $model.instructions, axis: .vertical).textFieldStyle(
                        .roundedBorder
                    ).accessibilityIdentifier("invite-instructions")
                    Text("Reserves one place. Confirmation keeps it; decline or withdrawal releases it.").font(
                        AcademyType.footnote
                    ).foregroundStyle(AcademyColors.secondaryText)
                    Button("Send invite") { Task { await model.transition("invited") } }.buttonStyle(
                        FloodlightPillStyle()
                    ).disabled(model.venue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        .accessibilityIdentifier("applicant-invite")
                }
                if let trial = application.trialAt, !application.isTerminal {
                    Text(Phase2Time.display(trial, zone: application.timezone)).font(AcademyType.title2)
                    Text(Phase2Time.zoneLabel(application.timezone, at: trial)).font(AcademyType.caption)
                    Text(
                        "\(application.trialVenue ?? "") · \(application.reservationState == "confirmed" ? "Place confirmed" : "Waiting for player to confirm")"
                    ).font(AcademyType.subheadline)
                }
                ForEach((application.transitions ?? []).filter { $0 != "invited" }, id: \.self) { target in
                    Button(
                        target == "rejected" ? "Not selected" : "Mark \(Phase2Application.label(target).lowercased())"
                    ) { transitionConfirmation = target }.buttonStyle(
                        FloodlightPillStyle(variant: target == "rejected" ? .outline : .primary)
                    ).disabled(!application.canTransition(to: target)).accessibilityIdentifier("applicant-\(target)")
                }
                if application.transitions?.contains("attended") == true, !application.canTransition(to: "attended") {
                    Text("Attendance unlocks after the player confirms and the trial has passed.").font(
                        AcademyType.footnote)
                }
                Text("Private notes").font(AcademyType.title2)
                Divider()
                Text("Only your club. The applicant never sees these notes.").font(AcademyType.caption).foregroundStyle(
                    AcademyColors.secondaryText)
                ForEach(application.notes ?? []) { note in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(note.body).font(AcademyType.body)
                        Text(Phase2Time.display(note.createdAt, zone: application.timezone)).font(AcademyType.caption)
                            .foregroundStyle(AcademyColors.secondaryText)
                        Divider()
                    }
                }
                TextField("Add a private note", text: $model.note, axis: .vertical).textFieldStyle(.roundedBorder)
                    .accessibilityIdentifier("applicant-note")
                Button("Save note") { Task { await model.addNote() } }.buttonStyle(
                    FloodlightPillStyle(variant: .outline)
                ).disabled(model.note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty).accessibilityIdentifier(
                    "applicant-save-note")
                Text(
                    "Deleted by \(Phase2Time.display(application.retentionExpiresAt, zone: application.timezone)), signed or not. \(applicationRetentionCopy)"
                ).font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
            }
        }.navigationTitle("Applicant").task { await model.load() }.refreshable { await model.load() }.disabled(
            model.isBusy
        )
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
        Phase2Page(
            title: matchesOnly ? "The work on film." : "Your squad, together.",
            eyebrow: "\(membership.access.role) · \(membership.program.name)"
        ) {
            Phase2ClubSelector()
            Text("Club-private · never on a public page").font(AcademyType.caption).foregroundStyle(
                AcademyColors.accent)
            Picker("Squad", selection: $selectedSquadId) {
                Text("My squads").tag(Optional<Int>.none)
                ForEach(model.squads) { squad in Text(squad.name).tag(Optional(squad.id)) }
            }.pickerStyle(.menu).accessibilityIdentifier("squad-picker")
            if model.isLoading { ProgressView("Loading your squads…") }
            Phase2ErrorView(message: model.error, retry: { Task { await model.load(programId: membership.id) } })
            if !matchesOnly {
                Text("\(members.count)").font(AcademyType.largeTitle) + Text(members.count == 1 ? " player" : " players").font(AcademyType.caption)
                ForEach(members) { member in
                    HStack(spacing: 16) {
                        Text(member.shirtNumber.map(String.init) ?? "—").font(AcademyType.title2).frame(width: 32)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(member.privateName).font(AcademyType.headline)
                            Text(member.position ?? "Position unavailable").font(AcademyType.caption).foregroundStyle(
                                AcademyColors.secondaryText)
                        }
                        Spacer()
                    }.padding(.vertical, 8).accessibilityIdentifier("squad-player-\(member.id)")
                    Divider()
                }
                if members.isEmpty, !model.isLoading, model.error == nil {
                    Text("No players in this squad yet.").foregroundStyle(AcademyColors.secondaryText)
                }
            }
            Text("Film Room").font(AcademyType.title2)
            Divider()
            ForEach(matches) { match in
                VStack(alignment: .leading, spacing: 8) {
                    Text(match.opponentName.map { "v \($0)" } ?? match.title ?? "Club match").font(AcademyType.headline)
                    Text(match.status.replacingOccurrences(of: "_", with: " ").capitalized).font(AcademyType.caption)
                        .foregroundStyle(AcademyColors.secondaryText)
                    if let date = match.matchDate { Text(date).font(AcademyType.footnote) }
                }.padding(.vertical, 6)
                Divider()
            }
            if matches.isEmpty, !model.isLoading, model.error == nil {
                Text("No filmed matches in your scope yet.").foregroundStyle(AcademyColors.secondaryText)
            }
            Text("Check Film Room for analysis. Your access includes only the squads assigned by the club owner.").font(
                AcademyType.footnote
            ).foregroundStyle(AcademyColors.secondaryText)
        }.navigationTitle(matchesOnly ? "Matches" : "Squads").task { await model.load(programId: membership.id) }
            .refreshable { await model.load(programId: membership.id) }.accessibilityIdentifier(
                matchesOnly ? "phase2-matches" : "phase2-squads")
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
    init(programId: Int, client: APIClient) {
        _model = StateObject(wrappedValue: StaffViewModel(programId: programId, client: client))
    }
    var body: some View {
        Phase2Page(title: "Staff & access", eyebrow: "Owner only") {
            Text("Who can sign in, and which squads they see.").font(AcademyType.subheadline).foregroundStyle(
                AcademyColors.secondaryText)
            if model.isBusy { ProgressView("Updating access…") }
            Phase2ErrorView(message: model.error, retry: { Task { await model.load() } })
            if let notice = model.notice {
                Text(notice).font(AcademyType.subheadline).accessibilityIdentifier("staff-notice")
            }
            if let board = model.board {
                Text("People · \(board.people.count)").font(AcademyType.title2)
                Divider()
                ForEach(board.people) { person in
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            VStack(alignment: .leading) {
                                Text(person.displayName ?? person.email ?? "Club staff").font(AcademyType.headline)
                                Text(
                                    person.role.capitalized + " · "
                                        + scopeLabel(all: person.allSquads, ids: person.squadIds)
                                ).font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
                            }
                            Spacer()
                            if person.editable {
                                Button("Edit") { editing = person }.accessibilityIdentifier("staff-edit-\(person.id)")
                            }
                        }
                        DisclosureGroup("Permissions") {
                            ForEach(Array(board.matrix.rows.enumerated()), id: \.offset) { index, label in
                                Label(
                                    label,
                                    systemImage: index < person.permissions.count && person.permissions[index]
                                        ? "checkmark" : "minus"
                                ).font(AcademyType.footnote).frame(maxWidth: .infinity, alignment: .leading).padding(
                                    .vertical, 3)
                            }
                        }
                        if person.editable {
                            Button("Remove access", role: .destructive) { revokePerson = person }
                                .accessibilityIdentifier("staff-remove-\(person.id)")
                        }
                        Divider()
                    }
                }
                Text("Invites · \(board.invites.count)").font(AcademyType.title2)
                Divider()
                ForEach(board.invites) { invite in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(invite.email).font(AcademyType.headline)
                        Text(
                            "\(invite.role.capitalized) · \(invite.status.capitalized) · \(scopeLabel(all: invite.allSquads, ids: invite.squadIds))"
                        ).font(AcademyType.footnote)
                        Text("Expires \(Phase2Time.display(invite.expiresAt, zone: "UTC"))").font(AcademyType.caption)
                        Button("Revoke invite", role: .destructive) { revokeInvite = invite }.accessibilityIdentifier(
                            "staff-revoke-\(invite.id)")
                        Divider()
                    }
                }
                Text("Invite someone").font(AcademyType.title2)
                TextField("Their email", text: $email).keyboardType(.emailAddress).textInputAutocapitalization(.never)
                    .autocorrectionDisabled().textFieldStyle(.roundedBorder).accessibilityIdentifier(
                        "staff-invite-email")
                StaffScopeForm(role: $role, allSquads: $allSquads, squadIds: $squadIds, squads: model.squads)
                Button("Send invite") {
                    Task {
                        await model.invite(email: email, role: role, allSquads: allSquads, squadIds: Array(squadIds))
                    }
                }.buttonStyle(FloodlightPillStyle()).disabled(
                    !email.contains("@") || (role != "manager" && !allSquads && squadIds.isEmpty)
                ).accessibilityIdentifier("staff-invite-send")
            }
        }.navigationTitle("Staff & access").task { await model.load() }.refreshable { await model.load() }.disabled(
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
    var body: some View {
        Picker("Role", selection: $role) {
            ForEach(["manager", "coach", "analyst", "viewer"], id: \.self) { Text($0.capitalized).tag($0) }
        }.pickerStyle(.menu).accessibilityIdentifier(identifierPrefix + "-role")
        Text(
            "Coach: their squads' players, matches and feedback. No recruiting, billing or staff, even with all squads. Invites last 7 days."
        ).font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
        if role != "manager" {
            Toggle("All squads", isOn: $allSquads).accessibilityIdentifier(identifierPrefix + "-all-squads")
            if !allSquads {
                ForEach(squads) { squad in
                    Toggle(
                        squad.name,
                        isOn: Binding(
                            get: { squadIds.contains(squad.id) },
                            set: { value in if value { squadIds.insert(squad.id) } else { squadIds.remove(squad.id) } })
                    ).accessibilityIdentifier(identifierPrefix + "-squad-\(squad.id)")
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
