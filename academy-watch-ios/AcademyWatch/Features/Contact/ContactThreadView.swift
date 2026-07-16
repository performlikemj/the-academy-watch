import SwiftUI

struct ContactThreadView: View {
    @StateObject private var viewModel: ContactThreadViewModel
    @ObservedObject private var availability: ContactFeatureAvailability
    @State private var isOutcomePresented = false

    @Environment(\.dismiss) private var dismiss

    init(
        contactRequest: ContactRequest,
        apiClient: APIClient,
        availability: ContactFeatureAvailability
    ) {
        _viewModel = StateObject(
            wrappedValue: ContactThreadViewModel(
                contactRequest: contactRequest,
                apiClient: apiClient,
                availability: availability
            )
        )
        _availability = ObservedObject(wrappedValue: availability)
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
                                ContactMessageBubble(message: message)
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
            }
        }
        .navigationTitle(viewModel.contactRequest.participants.player.displayName ?? "Introduction")
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
            messageComposer
        }
        .sheet(isPresented: $isOutcomePresented) {
            OutcomeReportSheet(viewModel: viewModel)
        }
        .task {
            await viewModel.loadIfNeeded()
        }
        .onChange(of: availability.state) { _, state in
            if state == .unavailable {
                isOutcomePresented = false
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
                Button(viewModel.contactRequest.latestOutcome == nil ? "Report" : "Update") {
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
}

private struct ContactMessageBubble: View {
    let message: ContactMessage

    var body: some View {
        HStack {
            if message.senderRole == .scout { Spacer(minLength: 48) }

            VStack(alignment: message.senderRole == .scout ? .trailing : .leading, spacing: 4) {
                Text(message.senderDisplayName ?? message.senderRole.displayName)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(message.body)
                    .font(.subheadline)
                    .foregroundStyle(message.senderRole == .scout ? AcademyColors.claretOnFill : .primary)
                    .padding(.horizontal, 13)
                    .padding(.vertical, 10)
                    .background(
                        message.senderRole == .scout ? AcademyColors.claretFill : AcademyColors.surface,
                        in: RoundedRectangle(cornerRadius: 16)
                    )
            }

            if message.senderRole == .player { Spacer(minLength: 48) }
        }
        .frame(maxWidth: .infinity)
    }
}

private struct OutcomeReportSheet: View {
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
                    Text("Outcome reports are appended to this introduction’s progress history.")
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
            .navigationTitle("Report Outcome")
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

private extension ContactSenderRole {
    var displayName: String {
        switch self {
        case .scout: "Scout"
        case .player: "Player"
        }
    }
}
