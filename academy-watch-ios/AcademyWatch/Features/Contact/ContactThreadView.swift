import SwiftUI

struct ContactThreadView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

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
                VStack(spacing: 0) {
                    antiScamBanner

                    ScrollView {
                        LazyVStack(spacing: 14) {
                            requestSummary
                            outcomeCard

                            if viewModel.isLoading, !viewModel.hasLoaded {
                                ProgressView("Loading conversation…")
                                    .padding(.vertical, 28)
                            } else if viewModel.messages.isEmpty {
                                FloodlightEmptyState(title: "Conversation ready", systemImage: "bubble.left.and.bubble.right", description: "Send the first message to continue the introduction.")
                                .padding(.vertical, 12)
                            } else {
                                if viewModel.canLoadMore {
                                    Button("Load more messages") {
                                        Task { await viewModel.loadNextPage() }
                                    }
                                    .font(AcademyType.subheadline.weight(.semibold))
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
                                    .font(AcademyType.footnote)
                                    .foregroundStyle(AcademyColors.danger)
                                    .fixedSize(horizontal: false, vertical: true)
                                    .padding(12)
                                    .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10))
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)
                    }.background(AcademyColors.background)
                    .onChange(of: viewModel.messages.count) { _, _ in
                        if let lastID = viewModel.messages.last?.id {
                            withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) {
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
                        foregroundColor: AcademyColors.warnText,
                        backgroundColor: AcademyColors.warnText.opacity(0.12)
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

    private var antiScamBanner: some View {
        HStack(alignment: .top, spacing: 9) {
            Image(systemName: "shield.lefthalf.filled")
                .font(AcademyType.footnote.weight(.semibold))
                .accessibilityHidden(true)
            Text("Never pay to be scouted. Legitimate scouts and clubs never ask players for fees — report anyone who does.")
                .font(AcademyType.footnote)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .foregroundStyle(AcademyColors.warnText)
        .padding(.horizontal, 16)
        .padding(.vertical, 9)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AcademyColors.warnText.opacity(0.1))
        .overlay(alignment: .bottom) {
            Divider().overlay(AcademyColors.warnText.opacity(0.22))
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("contact-thread-anti-scam-banner")
    }

    private var requestSummary: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                Label(viewModel.contactRequest.messagingOpen ? "CONVERSATION OPEN" : viewModel.contactRequest.status.displayName.uppercased(), systemImage: "checkmark.circle.fill")
                    .font(AcademyType.caption.weight(.medium))
                    .tracking(0.8)
                    .foregroundStyle(AcademyColors.good)
                Spacer()
                ContactStatusBadge(status: viewModel.contactRequest.status)
            }
            ContactRoutingBadge(request: viewModel.contactRequest)
            if viewModel.contactRequest.routingMode == .clubIncluded {
                Label(viewModel.contactRequest.clubConsentStatus == .granted ? "Club agreed" : viewModel.contactRequest.clubConsentStatus == .declined ? "Club declined" : "Waiting on club", systemImage: viewModel.contactRequest.clubConsentStatus == .granted ? "checkmark.circle" : "clock")
                    .font(AcademyType.subheadline)
                Label(viewModel.contactRequest.status == .accepted ? "Player accepted" : viewModel.contactRequest.status.displayName, systemImage: viewModel.contactRequest.status == .accepted ? "checkmark.circle" : "clock")
                    .font(AcademyType.subheadline)
                Text("The club is in this thread and sees every message.").font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
            }
            Text(viewModel.contactRequest.message)
                .font(AcademyType.subheadline)
                .foregroundStyle(AcademyColors.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
            if let accountID = viewModel.counterpartAccountID {
                Divider()
                BlockUserButton(
                    accountID: accountID,
                    displayName: viewModel.counterpartDisplayName,
                    apiClient: apiClient
                )
                .font(AcademyType.caption.weight(.medium))
                .buttonStyle(.plain)
                .foregroundStyle(AcademyColors.danger)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(14)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10))
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .stroke(AcademyColors.good.opacity(0.22), lineWidth: 0.75)
        }
    }

    private var outcomeCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Label("OUTCOME", systemImage: "flag.checkered")
                    .font(AcademyType.caption.weight(.medium))
                    .tracking(0.9)
                    .foregroundStyle(AcademyColors.secondaryText)
                Spacer()
                Button(
                    viewModel.contactRequest.latestOutcome == nil
                        ? "Record outcome"
                        : "Update outcome"
                ) {
                    isOutcomePresented = true
                }
                .font(AcademyType.subheadline.weight(.semibold))
                .accessibilityIdentifier("report-contact-outcome")
            }

            if let outcome = viewModel.contactRequest.latestOutcome {
                HStack(alignment: .top, spacing: 11) {
                    Image(systemName: outcome.stage.iconName)
                        .font(AcademyType.title3)
                        .foregroundStyle(AcademyColors.secondaryText)
                        .frame(width: 28)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(outcome.stage.displayName)
                            .font(AcademyType.headline)
                        if let notes = outcome.notes, !notes.isEmpty {
                            Text(notes)
                                .font(AcademyType.subheadline)
                                .foregroundStyle(AcademyColors.secondaryText)
                        }
                    }
                }
            } else {
                Text("Record progress from first contact through trial and signing decisions.")
                    .font(AcademyType.subheadline)
                    .foregroundStyle(AcademyColors.secondaryText)
            }
        }
        .padding(14)
        .background(
            AcademyColors.secondaryText.opacity(0.08),
            in: RoundedRectangle(cornerRadius: 10)
        )
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .stroke(AcademyColors.secondaryText.opacity(0.24), lineWidth: 0.75)
        }
    }

    private var messageComposer: some View {
        HStack(alignment: .bottom, spacing: 10) {
            TextField("Message", text: $viewModel.draft, axis: .vertical)
                .lineLimit(1 ... 4)
                .padding(.horizontal, 13)
                .padding(.vertical, 11)
                .background(AcademyColors.elevatedSurface, in: RoundedRectangle(cornerRadius: 10))
                .accessibilityIdentifier("contact-message-composer")

            Button {
                Task { await viewModel.sendMessage() }
            } label: {
                Group {
                    if viewModel.isSending {
                        ProgressView().tint(AcademyColors.onPrimary)
                    } else {
                        Image(systemName: "arrow.up")
                            .font(AcademyType.body.weight(.semibold))
                    }
                }
                .frame(width: 42, height: 42)
                .foregroundStyle(AcademyColors.onPrimary)
                .background(AcademyColors.primaryFill, in: Circle())
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
                        .font(AcademyType.caption.weight(.medium))
                        .foregroundStyle(AcademyColors.secondaryText)
                } else {
                    Text(rendering.displayLabel)
                        .font(AcademyType.caption2.weight(.medium))
                        .foregroundStyle(AcademyColors.secondaryText)
                }
                Text(message.body)
                    .font(AcademyType.subheadline)
                    .foregroundStyle(
                        rendering.kind == .viewer ? AcademyColors.onPrimary : .primary
                    )
                    .padding(.horizontal, 13)
                    .padding(.vertical, 10)
                    .background(
                        bubbleColor,
                        in: RoundedRectangle(cornerRadius: 10)
                    )
                    .overlay {
                        if rendering.kind == .club {
                            RoundedRectangle(cornerRadius: 10)
                                .stroke(AcademyColors.secondaryText.opacity(0.4), lineWidth: 1)
                        }
                    }

                if rendering.kind != .viewer {
                    Button(action: onReport) {
                        Label("Report", systemImage: "exclamationmark.bubble")
                    }
                    .font(AcademyType.caption.weight(.medium))
                    .foregroundStyle(AcademyColors.secondaryText)
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
            AcademyColors.primaryFill
        case .counterpart:
            AcademyColors.surface
        case .club:
            AcademyColors.secondaryText.opacity(0.1)
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
                }.listRowBackground(AcademyColors.background)

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
                }.listRowBackground(AcademyColors.background)

                if let submissionError {
                    Section {
                        Label(submissionError, systemImage: "exclamationmark.triangle.fill")
                            .font(AcademyType.footnote)
                            .foregroundStyle(AcademyColors.danger)
                            .fixedSize(horizontal: false, vertical: true)
                            .accessibilityIdentifier("contact-outcome-error")
                    }.listRowBackground(AcademyColors.background)
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
                }.listRowBackground(AcademyColors.background)
            }
        .scrollContentBackground(.hidden)
        .background(AcademyColors.background)
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
                            foregroundColor: AcademyColors.warnText,
                            backgroundColor: AcademyColors.warnText.opacity(0.12)
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
