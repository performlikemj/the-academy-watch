import SwiftUI

struct ContactThreadView: View {
    @StateObject private var viewModel: ContactThreadViewModel
    @ObservedObject private var availability: ContactFeatureAvailability
    @State private var isOutcomePresented = false
    @State private var reportSubject: ContentReportSubject?

    private let apiClient: APIClient

    @Environment(\.dismiss) private var dismiss

    init(
        contactRequest: ContactRequest,
        apiClient: APIClient,
        availability: ContactFeatureAvailability,
        viewerRole: ContactSenderRole = .scout
    ) {
        _viewModel = StateObject(
            wrappedValue: ContactThreadViewModel(
                contactRequest: contactRequest,
                apiClient: apiClient,
                availability: availability,
                viewerRole: viewerRole
            )
        )
        _availability = ObservedObject(wrappedValue: availability)
        self.apiClient = apiClient
    }

    var body: some View {
        ZStack {
            AcademyColors.background.ignoresSafeArea()

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 14) {
                        requestSummary
                        outcomeCard

                        if viewModel.isLoading, !viewModel.hasLoaded {
                            ProgressView("Loading conversation…")
                                .padding(.vertical, 28)
                        } else if viewModel.messages.isEmpty {
                            ContentUnavailableView(
                                "Conversation ready",
                                systemImage: "bubble.left.and.bubble.right",
                                description: Text("Send the first message to continue the introduction.")
                            )
                            .padding(.vertical, 12)
                        } else {
                            if viewModel.canLoadMore {
                                Button("Load more messages") {
                                    Task { await viewModel.loadNextPage() }
                                }
                                .font(.subheadline.weight(.semibold))
                            }

                            ForEach(viewModel.messages) { message in
                                ContactMessageBubble(
                                    message: message,
                                    viewerRole: viewModel.viewerRole,
                                    clubDisplayName: viewModel.contactRequest.participants.club?.displayName,
                                    onReport: { reportSubject = .message(message) }
                                )
                                .id(message.id)
                            }
                        }

                        if let error = viewModel.errorMessage {
                            Label(error, systemImage: "exclamationmark.triangle.fill")
                                .font(.footnote)
                                .foregroundStyle(.red)
                                .fixedSize(horizontal: false, vertical: true)
                                .padding(12)
                                .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 12))
                        }
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 12)
                }
                .onChange(of: viewModel.messages.count) { _, _ in
                    if let lastID = viewModel.messages.last?.id {
                        withAnimation(.easeOut(duration: 0.2)) {
                            proxy.scrollTo(lastID, anchor: .bottom)
                        }
                    }
                }
                .onAppear {
                    guard viewModel.isFixturePreview,
                          let lastID = viewModel.messages.last?.id
                    else { return }
                    DispatchQueue.main.async {
                        proxy.scrollTo(lastID, anchor: .bottom)
                    }
                }
            }
        }
        .navigationTitle(
            viewModel.counterpartDisplayName
                ?? viewModel.counterpartRole.displayName
        )
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if viewModel.isFixturePreview {
                ToolbarItem(placement: .topBarTrailing) {
                    BadgeView(
                        text: "Fixture",
                        foregroundColor: AcademyColors.loanAmber,
                        backgroundColor: AcademyColors.loanAmber.opacity(0.12)
                    )
                }
            }
        }
        .safeAreaInset(edge: .bottom) {
            if viewModel.contactRequest.messagingOpen {
                messageComposer
            }
        }
        .sheet(isPresented: $isOutcomePresented) {
            OutcomeSheet(viewModel: viewModel)
        }
        .sheet(item: $reportSubject) { subject in
            ContentReportSheet(subject: subject, apiClient: apiClient)
        }
        .task {
            await viewModel.loadIfNeeded()
            presentMessageReportFixtureIfNeeded()
        }
        .onChange(of: availability.state) { _, state in
            if state == .unavailable {
                isOutcomePresented = false
                reportSubject = nil
                dismiss()
            }
        }
    }

    private var requestSummary: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                Label("INTRODUCTION ACCEPTED", systemImage: "checkmark.circle.fill")
                    .font(.caption.weight(.bold))
                    .tracking(0.8)
                    .foregroundStyle(AcademyColors.positiveGreen)
                Spacer()
                ContactStatusBadge(status: viewModel.contactRequest.status)
            }
            ContactRoutingBadge(request: viewModel.contactRequest)
            Text(viewModel.contactRequest.message)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(14)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 16))
        .overlay {
            RoundedRectangle(cornerRadius: 16)
                .stroke(AcademyColors.positiveGreen.opacity(0.22), lineWidth: 0.75)
        }
    }

    private var outcomeCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Label("OUTCOME", systemImage: "flag.checkered")
                    .font(.caption.weight(.bold))
                    .tracking(0.9)
                    .foregroundStyle(AcademyColors.transitionPurple)
                Spacer()
                Button(
                    viewModel.contactRequest.latestOutcome == nil
                        ? "Record outcome"
                        : "Update outcome"
                ) {
                    isOutcomePresented = true
                }
                .font(.subheadline.weight(.semibold))
                .accessibilityIdentifier("report-contact-outcome")
            }

            if let outcome = viewModel.contactRequest.latestOutcome {
                HStack(alignment: .top, spacing: 11) {
                    Image(systemName: outcome.stage.iconName)
                        .font(.title3)
                        .foregroundStyle(AcademyColors.transitionPurple)
                        .frame(width: 28)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(outcome.stage.displayName)
                            .font(.headline)
                        if let notes = outcome.notes, !notes.isEmpty {
                            Text(notes)
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            } else {
                Text("Record progress from first contact through trial and signing decisions.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .background(
            AcademyColors.transitionPurple.opacity(0.08),
            in: RoundedRectangle(cornerRadius: 16)
        )
        .overlay {
            RoundedRectangle(cornerRadius: 16)
                .stroke(AcademyColors.transitionPurple.opacity(0.24), lineWidth: 0.75)
        }
    }

    private var messageComposer: some View {
        HStack(alignment: .bottom, spacing: 10) {
            TextField("Message", text: $viewModel.draft, axis: .vertical)
                .lineLimit(1 ... 4)
                .padding(.horizontal, 13)
                .padding(.vertical, 11)
                .background(Color(uiColor: .tertiarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 18))
                .accessibilityIdentifier("contact-message-composer")

            Button {
                Task { await viewModel.sendMessage() }
            } label: {
                Group {
                    if viewModel.isSending {
                        ProgressView().tint(.white)
                    } else {
                        Image(systemName: "arrow.up")
                            .font(.body.weight(.bold))
                    }
                }
                .frame(width: 42, height: 42)
                .foregroundStyle(.white)
                .background(AcademyColors.claretFill, in: Circle())
            }
            .disabled(!viewModel.canSend)
            .opacity(viewModel.canSend ? 1 : 0.45)
            .accessibilityLabel("Send message")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .background(.bar)
    }

    private func presentMessageReportFixtureIfNeeded() {
        #if DEBUG
        guard FullCircleFixtureDestination.fromLaunchArguments(
            ProcessInfo.processInfo.arguments
        ) == .messageReport,
            reportSubject == nil,
            let counterpartMessage = viewModel.messages.first(where: {
                $0.senderRole != viewModel.viewerRole
            })
        else { return }

        reportSubject = .message(counterpartMessage)
        #endif
    }
}

enum ContactMessageRenderingKind: Equatable, Sendable {
    case viewer
    case counterpart
    case club
}

struct ContactMessageRenderingModel: Equatable, Sendable {
    let kind: ContactMessageRenderingKind
    let displayLabel: String

    init(
        message: ContactMessage,
        viewerRole: ContactSenderRole,
        clubDisplayName: String?
    ) {
        if message.senderRole == .club {
            kind = .club
            let normalizedClubName = clubDisplayName?
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if let normalizedClubName, !normalizedClubName.isEmpty {
                displayLabel = normalizedClubName
            } else {
                displayLabel = "Club"
            }
        } else {
            kind = message.senderRole == viewerRole ? .viewer : .counterpart
            displayLabel = message.senderDisplayName ?? message.senderRole.displayName
        }
    }
}

private struct ContactMessageBubble: View {
    let message: ContactMessage
    let viewerRole: ContactSenderRole
    let clubDisplayName: String?
    let onReport: () -> Void

    private var rendering: ContactMessageRenderingModel {
        ContactMessageRenderingModel(
            message: message,
            viewerRole: viewerRole,
            clubDisplayName: clubDisplayName
        )
    }

    var body: some View {
        HStack {
            if rendering.kind == .viewer { Spacer(minLength: 48) }

            VStack(
                alignment: rendering.kind == .viewer ? .trailing : .leading,
                spacing: 5
            ) {
                if rendering.kind == .club {
                    Label(rendering.displayLabel, systemImage: "building.2.fill")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(AcademyColors.transitionPurple)
                } else {
                    Text(rendering.displayLabel)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
                Text(message.body)
                    .font(.subheadline)
                    .foregroundStyle(
                        rendering.kind == .viewer ? AcademyColors.claretOnFill : .primary
                    )
                    .padding(.horizontal, 13)
                    .padding(.vertical, 10)
                    .background(
                        bubbleColor,
                        in: RoundedRectangle(cornerRadius: 16)
                    )
                    .overlay {
                        if rendering.kind == .club {
                            RoundedRectangle(cornerRadius: 16)
                                .stroke(AcademyColors.transitionPurple.opacity(0.4), lineWidth: 1)
                        }
                    }

                if rendering.kind != .viewer {
                    Button(action: onReport) {
                        Label("Report", systemImage: "exclamationmark.bubble")
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("report-contact-message-\(message.id)")
                }
            }

            if rendering.kind != .viewer {
                Spacer(minLength: rendering.kind == .club ? 24 : 48)
            }
        }
        .frame(maxWidth: .infinity)
    }

    private var bubbleColor: Color {
        switch rendering.kind {
        case .viewer:
            AcademyColors.claretFill
        case .counterpart:
            AcademyColors.surface
        case .club:
            AcademyColors.transitionPurple.opacity(0.1)
        }
    }
}

private struct OutcomeSheet: View {
    @ObservedObject var viewModel: ContactThreadViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var submissionError: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Progress stage") {
                    Picker("Stage", selection: $viewModel.selectedOutcomeStage) {
                        ForEach(ContactOutcomeStage.allCases, id: \.self) { stage in
                            Label(stage.displayName, systemImage: stage.iconName)
                                .tag(stage)
                        }
                    }
                    .pickerStyle(.inline)
                    .labelsHidden()
                }

                Section {
                    TextEditor(text: $viewModel.outcomeNotes)
                        .frame(minHeight: 110)
                        .accessibilityIdentifier("outcome-notes")
                } header: {
                    HStack {
                        Text("Notes (optional)")
                        Spacer()
                        Text("\(viewModel.outcomeNotes.count)/2,000")
                            .monospacedDigit()
                    }
                } footer: {
                    Text("Outcome updates are added to this introduction’s progress history.")
                }

                if let submissionError {
                    Section {
                        Label(submissionError, systemImage: "exclamationmark.triangle.fill")
                            .font(.footnote)
                            .foregroundStyle(Color(uiColor: .systemRed))
                            .fixedSize(horizontal: false, vertical: true)
                            .accessibilityIdentifier("contact-outcome-error")
                    }
                }

                Section {
                    Button {
                        Task {
                            submissionError = nil
                            if await viewModel.reportOutcome() {
                                dismiss()
                            } else {
                                submissionError = viewModel.errorMessage
                                    ?? "We couldn't save this outcome. Please try again."
                            }
                        }
                    } label: {
                        HStack {
                            Spacer()
                            if viewModel.isReportingOutcome { ProgressView() }
                            Text(viewModel.isReportingOutcome ? "Saving…" : "Save outcome")
                                .fontWeight(.semibold)
                            Spacer()
                        }
                    }
                    .disabled(!viewModel.canReportOutcome)
                    .accessibilityIdentifier("save-contact-outcome")
                }
            }
            .navigationTitle("Record Outcome")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                if viewModel.isFixturePreview {
                    ToolbarItem(placement: .topBarTrailing) {
                        BadgeView(
                            text: "Fixture",
                            foregroundColor: AcademyColors.loanAmber,
                            backgroundColor: AcademyColors.loanAmber.opacity(0.12)
                        )
                    }
                }
            }
        }
        .interactiveDismissDisabled(viewModel.isReportingOutcome)
        .onAppear {
            viewModel.selectedOutcomeStage = viewModel.contactRequest.latestOutcome?.stage ?? .contacted
        }
    }
}

private extension ContactOutcomeStage {
    var iconName: String {
        switch self {
        case .contacted: "phone.fill"
        case .trialScheduled: "calendar.badge.clock"
        case .trialCompleted: "figure.soccer"
        case .signed: "signature"
        case .noFit: "arrow.triangle.branch"
        }
    }
}

extension ContactSenderRole {
    var displayName: String {
        switch self {
        case .scout: "Scout"
        case .player: "Player"
        case .club: "Club"
        }
    }
}
