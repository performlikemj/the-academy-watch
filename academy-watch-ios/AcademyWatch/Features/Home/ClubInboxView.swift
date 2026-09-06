import SwiftUI

@MainActor
final class ClubInboxViewModel: ObservableObject {
    @Published private(set) var invitations: [ClubInvitation] = []
    @Published private(set) var nextBefore: String?
    @Published private(set) var busy = false
    @Published private(set) var error: String?
    @Published private(set) var unavailable = false
    private let client: any PlayerClubAPIClientProtocol
    init(client: any PlayerClubAPIClientProtocol) { self.client = client }

    func load(more: Bool = false) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        error = nil
        do {
            let page = try await client.fetchClubInvitations(before: more ? nextBefore : nil)
            guard !Task.isCancelled else { return }
            let existing = more ? invitations : []
            invitations = existing + page.invitations.filter { row in !existing.contains { $0.id == row.id } }
            nextBefore = page.nextBefore
            unavailable = false
        } catch {
            guard !Task.isCancelled else { return }
            invitations = []
            nextBefore = nil
            unavailable = (error as? APIClientError)?.statusCode == 404
            self.error = unavailable ? nil : playerClubError(error)
        }
    }

    func decide(_ row: ClubInvitation, decision: ClubInvitationDecision) async {
        guard !busy else { return }
        busy = true
        error = nil
        do {
            try await client.decideClubInvitation(id: row.id, decision: decision)
            let page = try await client.fetchClubInvitations(before: nil)
            guard !Task.isCancelled else {
                busy = false
                return
            }
            invitations = page.invitations
            nextBefore = page.nextBefore
        } catch {
            invitations = []
            nextBefore = nil
            self.error = playerClubError(error)
        }
        busy = false
    }
}

struct ClubInboxView: View {
    @StateObject private var model: ClubInboxViewModel
    @Environment(\.scenePhase) private var scenePhase
    @State private var confirmation: InvitationConfirmation?
    init(apiClient: any PlayerClubAPIClientProtocol) {
        _model = StateObject(wrappedValue: ClubInboxViewModel(client: apiClient))
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Your club connections").font(.title2.bold())
                Text(
                    "You choose which invitations to accept. Joining connects your profile to the club's roster and lets the club send you private feedback. It doesn't change your contract status."
                )
                .font(.subheadline).foregroundStyle(.secondary)
                if model.busy { ProgressView("Updating invitations…") }
                if model.unavailable {
                    ContentUnavailableView(
                        "Club connections aren't available yet", systemImage: "envelope",
                        description: Text(
                            "Your profile is still available. Ask your coach when your club is ready to connect."))
                } else if !model.busy, model.error == nil, model.invitations.isEmpty {
                    ContentUnavailableView(
                        "No invitations yet", systemImage: "envelope",
                        description: Text(
                            "After your player claim is approved, ask your coach to invite your profile from the club roster."
                        ))
                }
                if let error = model.error {
                    Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.red)
                    Button("Refresh invitations") { Task { await model.load() } }
                }
                ForEach(model.invitations) { row in
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text(row.clubName).font(.headline)
                            Spacer()
                            BadgeView(text: row.status.capitalized)
                        }
                        if row.status == "pending" {
                            Text("This club would like to add your player profile to its roster.").font(.subheadline)
                            if let expiry = row.expiresAt {
                                Text("Expires \(displayClubDate(expiry))").font(.caption).foregroundStyle(.secondary)
                            }
                            HStack {
                                Button("Accept invitation") { confirmation = .init(row: row, decision: .accept) }
                                    .buttonStyle(.borderedProminent)
                                    .tint(AcademyColors.claretFill).foregroundStyle(AcademyColors.claretOnFill)
                                Button("Decline") { confirmation = .init(row: row, decision: .decline) }.buttonStyle(
                                    .bordered)
                            }.disabled(model.busy)
                        } else if row.status == "accepted" {
                            Text("You're connected. Find private coach feedback in My profiles.").font(.subheadline)
                            Button("Leave club connection", role: .destructive) {
                                confirmation = .init(row: row, decision: .revoke)
                            }.disabled(model.busy)
                        }
                    }.homeCard()
                }
                if model.nextBefore != nil {
                    Button("Load more invitations") { Task { await model.load(more: true) } }.disabled(model.busy)
                }
            }.padding(20)
        }.background(AcademyColors.background)
            .navigationTitle("Club invitations").navigationBarTitleDisplayMode(.inline)
            .task { await model.load() }
            .refreshable { await model.load() }
            .onChange(of: scenePhase) { _, phase in if phase == .active { Task { await model.load() } } }
            .confirmationDialog(
                confirmation?.title ?? "Club invitation",
                isPresented: Binding(get: { confirmation != nil }, set: { if !$0 { confirmation = nil } }),
                titleVisibility: .visible, presenting: confirmation
            ) { action in
                Button(
                    action.decision == .accept
                        ? "Accept invitation" : action.decision == .decline ? "Decline invitation" : "Leave connection",
                    role: action.decision == .accept ? nil : .destructive
                ) {
                    Task { await model.decide(action.row, decision: action.decision) }
                }
                Button("Cancel", role: .cancel) {}
            } message: { action in
                Text(
                    action.decision == .revoke
                        ? "Leaving removes this club connection and access to its private feedback. Your public profile remains yours."
                        : "Only accept if you recognize \(action.row.clubName) and want to connect your profile to its roster."
                )
            }
            .accessibilityIdentifier("club-inbox")
    }
}
private struct InvitationConfirmation: Identifiable {
    let row: ClubInvitation
    let decision: ClubInvitationDecision
    var id: String { row.id + decision.rawValue }
    var title: String {
        decision == .accept
            ? "Join \(row.clubName)?" : decision == .decline ? "Decline \(row.clubName)?" : "Leave \(row.clubName)?"
    }
}

@MainActor
final class PlayerFeedbackViewModel: ObservableObject {
    @Published private(set) var progressConflict = false
    @Published private(set) var rows: [PlayerFeedback] = []
    @Published private(set) var detail: PlayerFeedback?
    @Published private(set) var nextBefore: String?
    @Published private(set) var busy = false
    @Published private(set) var error: String?
    private let client: any PlayerClubAPIClientProtocol
    init(client: any PlayerClubAPIClientProtocol) { self.client = client }

    func load(playerID: Int, more: Bool = false) async {
        guard !busy else { return }
        busy = true
        error = nil
        defer { busy = false }
        do {
            let result = try await client.fetchPlayerFeedback(playerID: playerID, before: more ? nextBefore : nil)
            guard !Task.isCancelled else { return }
            let previous = more ? rows : []
            rows = previous + result.feedback.filter { row in !previous.contains { $0.id == row.id } }
            nextBefore = result.nextBefore
        } catch {
            rows = []
            nextBefore = nil
            self.error =
                (error as? APIClientError)?.statusCode == 404
                ? "Feedback isn't available for this profile right now. Your club connection may not be active yet."
                : playerClubError(error)
        }
    }
    func open(id: String) async {
        guard !busy else { return }
        busy = true
        error = nil
        detail = nil
        progressConflict = false
        defer { busy = false }
        do {
            let value = try await client.fetchFeedbackDetail(id: id)
            guard !Task.isCancelled else { return }
            detail = value
        } catch { self.error = unavailableMessage(error) }
    }
    func acknowledge() async {
        guard !busy, let value = detail, value.canAcknowledge else { return }
        busy = true
        error = nil
        defer { busy = false }
        do {
            let result = try await client.acknowledgeFeedback(id: value.id)
            guard !Task.isCancelled else { return }
            detail = result
        } catch {
            detail = nil
            self.error = unavailableMessage(error)
        }
    }
    private func unavailableMessage(_ error: Error) -> String {
        (error as? APIClientError)?.statusCode == 404
            ? "This feedback is no longer available. Return to your profile and refresh for current updates."
            : playerClubError(error)
    }

    func updateProgress(status: String, note: String) async {
        guard !busy, !progressConflict, let value = detail, value.canUpdateProgress == true else {
            return
        }
        busy = true
        error = nil
        defer { busy = false }
        do {
            let result = try await client.updateDevelopmentProgress(
                id: value.id,
                update: .init(
                    expectedVersion: value.developmentProgress?.version ?? 0, status: status, note: note))
            guard !Task.isCancelled else { return }
            detail = result
        } catch {
            let code = (error as? APIClientError)?.statusCode
            if code == 401 || code == 403 || code == 404 { detail = nil }
            if code == 409 { progressConflict = true }
            self.error =
                code == 409
                ? "This action has changed. Refresh the feedback before updating it again."
                : playerClubError(error)
        }
    }
}

struct PlayerFeedbackListView: View {
    let playerID: Int
    let apiClient: any PlayerClubAPIClientProtocol
    @StateObject private var model: PlayerFeedbackViewModel
    init(playerID: Int, apiClient: any PlayerClubAPIClientProtocol) {
        self.playerID = playerID
        self.apiClient = apiClient
        _model = StateObject(wrappedValue: PlayerFeedbackViewModel(client: apiClient))
    }
    var body: some View {
        List {
            Section {
                Text("Private notes from your club. Your acknowledgment lets your coach know you've read them.")
                    .foregroundStyle(.secondary)
            }
            if model.busy { ProgressView("Loading feedback…") }
            if let error = model.error {
                Text(error).foregroundStyle(.secondary)
                Button("Refresh") { Task { await model.load(playerID: playerID) } }
            }
            ForEach(model.rows) { row in
                NavigationLink {
                    PlayerFeedbackDetailView(id: row.id, apiClient: apiClient)
                } label: {
                    VStack(alignment: .leading, spacing: 7) {
                        Text(row.title).font(.headline)
                        Text(row.program.name).font(.subheadline).foregroundStyle(.secondary)
                        if let action = row.developmentAction {
                            Text(action.focus).font(.subheadline)
                            Label(
                                PlayerDevelopmentProgress.label(row.developmentProgress?.status),
                                systemImage: "flag.fill"
                            )
                            .font(.caption.weight(.semibold)).foregroundStyle(AcademyColors.claret)
                        }
                        Text(row.acknowledgedAt == nil ? "Awaiting acknowledgment" : "Acknowledged").font(
                            .caption)
                    }.padding(.vertical, 6)
                }
            }
            if !model.busy, model.error == nil, model.rows.isEmpty {
                ContentUnavailableView(
                    "Your next step starts here", systemImage: "text.bubble",
                    description: Text("When your coach publishes feedback for you, it will appear here."))
            }
            if model.nextBefore != nil {
                Button("Load more") { Task { await model.load(playerID: playerID, more: true) } }.disabled(model.busy)
            }
        }.navigationTitle("Coach feedback").navigationBarTitleDisplayMode(.inline)
            .task { await model.load(playerID: playerID) }
            .refreshable { await model.load(playerID: playerID) }
            .accessibilityIdentifier("player-feedback-list")
    }
}

struct PlayerFeedbackDetailView: View {
    let id: String
    @StateObject private var model: PlayerFeedbackViewModel
    @Environment(\.scenePhase) private var scenePhase
    init(id: String, apiClient: any PlayerClubAPIClientProtocol) {
        self.id = id
        _model = StateObject(wrappedValue: PlayerFeedbackViewModel(client: apiClient))
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if model.busy { ProgressView("Updating feedback…") }
                if let row = model.detail {
                    Label("PRIVATE CLUB FEEDBACK", systemImage: "lock.fill").font(.caption.bold()).foregroundStyle(
                        AcademyColors.claret)
                    Text(row.title).font(.largeTitle.bold())
                    Text("\(row.program.name) · \(row.author.displayName ?? "Club staff")").foregroundStyle(.secondary)
                    Text("\(displayClubDate(row.publishedAt)) · Revision \(row.revision)").font(.caption)
                        .foregroundStyle(.secondary)
                    Text(row.body ?? "").textSelection(.enabled).frame(
                        maxWidth: .infinity, alignment: .leading)
                    if row.developmentAction != nil {
                        PlayerDevelopmentCard(feedback: row, busy: model.busy || model.progressConflict) {
                            status, note in
                            Task { await model.updateProgress(status: status, note: note) }
                        }
                        .id("\(row.id):\(row.developmentProgress?.version ?? 0)")
                    }
                    if row.canAcknowledge {
                        Button("I've read this feedback") { Task { await model.acknowledge() } }
                            .buttonStyle(.borderedProminent).controlSize(.large).disabled(model.busy)
                            .tint(AcademyColors.claretFill).foregroundStyle(AcademyColors.claretOnFill)
                            .accessibilityIdentifier("feedback-acknowledge")
                        Text(
                            "This tells your coach you've read this revision. It doesn't mean you agree with every point."
                        ).font(.caption).foregroundStyle(.secondary)
                    } else if row.acknowledgedAt != nil {
                        Label(
                            "Acknowledged — your coach can see you've read this.", systemImage: "checkmark.circle.fill"
                        ).foregroundStyle(AcademyColors.positiveGreen)
                    }
                }
                if let error = model.error {
                    Text(error).foregroundStyle(.secondary)
                    Button("Refresh feedback") { Task { await model.open(id: id) } }
                }
            }.padding(20)
        }.navigationTitle("Feedback").navigationBarTitleDisplayMode(.inline)
            .task { await model.open(id: id) }
            .onChange(of: scenePhase) { _, phase in if phase == .active { Task { await model.open(id: id) } } }
    }
}

func displayClubDate(_ raw: String) -> String {
    let parser = ISO8601DateFormatter()
    parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let date = parser.date(from: raw) ?? ISO8601DateFormatter().date(from: raw)
    return date?.formatted(date: .abbreviated, time: .omitted) ?? "Date unavailable"
}

private struct PlayerDevelopmentCard: View {
    let feedback: PlayerFeedback
    let busy: Bool
    let onSave: (String, String) -> Void
    @State private var reflection: String
    @FocusState private var writing: Bool

    init(feedback: PlayerFeedback, busy: Bool, onSave: @escaping (String, String) -> Void) {
        self.feedback = feedback
        self.busy = busy
        self.onSave = onSave
        _reflection = State(initialValue: feedback.developmentProgress?.reflection ?? "")
    }

    var body: some View {
        if let action = feedback.developmentAction {
            VStack(alignment: .leading, spacing: 18) {
                Label("YOUR NEXT STEP", systemImage: "flag.fill")
                    .font(.caption.bold()).foregroundStyle(AcademyColors.claretForeground)
                Text(action.focus).font(.title2.bold()).accessibilityIdentifier("development-focus")
                actionText("What to practise", action.practice)
                actionText("What progress looks like", action.success)
                if let day = action.reviewOn {
                    Label("Review together: \(day)", systemImage: "calendar").font(.subheadline)
                }
                Divider()
                Label(
                    PlayerDevelopmentProgress.label(feedback.developmentProgress?.status),
                    systemImage: "checklist"
                )
                .font(.headline).accessibilityIdentifier("development-status")
                if let review = feedback.developmentProgress?.coachNote, !review.isEmpty {
                    actionText("Coach review", review)
                }
                if feedback.canUpdateProgress == true {
                    Text("How did practice go?").font(.headline)
                    Text("What did you try? What felt different? Where do you need help?")
                        .font(.subheadline).foregroundStyle(.secondary)
                    TextEditor(text: $reflection)
                        .frame(minHeight: 110).padding(8)
                        .background(AcademyColors.background, in: RoundedRectangle(cornerRadius: 12))
                        .focused($writing).accessibilityLabel("Practice reflection")
                        .accessibilityIdentifier("development-reflection")
                        .onChange(of: reflection) { _, value in
                            if value.count > 1000 { reflection = String(value.prefix(1000)) }
                        }
                    Text("Only you and your club can see this reflection.").font(.caption).foregroundStyle(
                        .secondary)
                    Button("Save practice update") { save("working_on_it") }
                        .buttonStyle(.bordered).disabled(busy)
                        .accessibilityIdentifier("development-save")
                    Button("Ready for coach review") { save("ready_for_review") }
                        .buttonStyle(.borderedProminent).controlSize(.large)
                        .tint(AcademyColors.claretFill).foregroundStyle(AcademyColors.claretOnFill)
                        .disabled(busy || reflection.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        .accessibilityIdentifier("development-ready")
                } else {
                    Text("Open the latest feedback revision to update your progress.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if let history = feedback.developmentProgress?.history, !history.isEmpty {
                    DisclosureGroup("Development history") {
                        VStack(alignment: .leading, spacing: 14) {
                            ForEach(history.reversed()) { event in
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(
                                        "\(event.actor == "coach" ? "Coach" : "Player") · \(PlayerDevelopmentProgress.label(event.status))"
                                    )
                                    .font(.subheadline.bold())
                                    Text(displayClubDate(event.at)).font(.caption).foregroundStyle(.secondary)
                                    if !event.note.isEmpty { Text(event.note).font(.subheadline) }
                                }
                            }
                        }.padding(.top, 10)
                    }
                }
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 18))
        }
    }

    private func actionText(_ title: String, _ text: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.subheadline.bold())
            Text(text).fixedSize(horizontal: false, vertical: true)
        }
    }
    private func save(_ status: String) {
        writing = false
        onSave(status, reflection.trimmingCharacters(in: .whitespacesAndNewlines))
    }
}
