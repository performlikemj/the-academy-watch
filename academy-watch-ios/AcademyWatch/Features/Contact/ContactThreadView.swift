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
                    ScrollView {
                        LazyVStack(spacing: 14) {
                            requestSummary
                            outcomeCard

                            if viewModel.isLoading, !viewModel.hasLoaded {
                                CleatLoader("Loading conversation…")
                                    .padding(.vertical, 28)
                            } else if viewModel.messages.isEmpty {
                                FloodlightEmptyState(
                                    title: "Conversation ready", systemImage: "bubble.left.and.bubble.right",
                                    description: "Send the first message to continue the introduction."
                                )
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

                            antiScamBanner
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
                            guard !Phase2ReviewCapture.isActive else { return }
                            if let lastID = viewModel.messages.last?.id {
                                withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) {
                                    proxy.scrollTo(lastID, anchor: .bottom)
                                }
                            }
                        }
                        .onAppear {
                            guard !Phase2ReviewCapture.isActive, viewModel.isFixturePreview,
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
            Text(
                "Never pay to be scouted. Legitimate scouts and clubs never ask players for fees — report anyone who does."
            )
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
        VStack(alignment: .leading, spacing: 16) {
            Phase2Eyebrow(
                text: viewModel.contactRequest.routingMode == .clubIncluded ? "Club and player consent" : "Introduction"
            )
            if viewModel.contactRequest.routingMode == .clubIncluded {
                consentRow(
                    done: viewModel.contactRequest.clubConsentStatus == .granted,
                    title: viewModel.contactRequest.clubConsentStatus == .granted
                        ? (viewModel.contactRequest.participants.club?.displayName ?? "Club") + " said yes"
                        : viewModel.contactRequest.clubConsentStatus == .declined ? "Club declined" : "Waiting on club",
                    detail: [
                        viewModel.contactRequest.clubConsentAt.map { Phase2Time.shortDate($0, zone: TimeZone.current.identifier) },
                        viewModel.contactRequest.clubConsentNote,
                    ].compactMap { $0 }.joined(separator: " · "))
            }
            consentRow(
                done: viewModel.contactRequest.status == .accepted,
                title: viewModel.contactRequest.status == .accepted
                    ? (viewModel.contactRequest.participants.player.displayName?.split(separator: " ").first.map(
                        String.init) ?? "Player") + " accepted" : viewModel.contactRequest.status.displayName,
                detail: viewModel.contactRequest.respondedAt.map { Phase2Time.shortDate($0, zone: TimeZone.current.identifier) }
                    ?? "The player decides who they talk to.")
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "bubble.left").font(.system(size: 15, weight: .light)).foregroundStyle(
                    AcademyColors.accent
                )
                .frame(width: 28, height: 28).overlay(Circle().stroke(AcademyColors.accent, lineWidth: 1))
                VStack(alignment: .leading, spacing: 4) {
                    Text(viewModel.contactRequest.messagingOpen ? "Conversation open" : "Conversation not open").font(
                        AcademyType.headline)
                    Text(viewModel.contactRequest.message)
                        .font(AcademyType.subheadline).foregroundStyle(AcademyColors.secondaryText)
                        .accessibilityIdentifier("contact-original-introduction")
                    if viewModel.contactRequest.routingMode == .clubIncluded {
                        Text("The club is in the thread and sees every message.")
                            .font(AcademyType.subheadline).foregroundStyle(AcademyColors.secondaryText)
                    }
                }
            }
            if let accountID = viewModel.counterpartAccountID {
                Divider()
                BlockUserButton(
                    accountID: accountID, displayName: viewModel.counterpartDisplayName, apiClient: apiClient
                )
                .font(AcademyType.footnote).buttonStyle(.plain).foregroundStyle(AcademyColors.danger).frame(
                    minHeight: 44)
            }
            Divider()
            Phase2Eyebrow(text: "Other states you will see")
            Phase2Flow {
                ForEach(["Waiting on club", "Waiting on player", "Declined", "Expired", "Withdrawn"], id: \.self) {
                    state in
                    Text(state.uppercased()).font(AcademyType.mono(9)).tracking(1)
                        .foregroundStyle(AcademyColors.secondaryText).padding(.horizontal, 9).padding(.vertical, 5)
                        .overlay(Capsule().stroke(AcademyColors.hairline, lineWidth: 1))
                }
            }
        }.padding(16).frame(maxWidth: .infinity, alignment: .leading).background(
            AcademyColors.elevatedSurface, in: RoundedRectangle(cornerRadius: 14))
    }
    private func consentRow(done: Bool, title: String, detail: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: done ? "checkmark" : "clock").font(.system(size: 14))
                .foregroundStyle(done ? AcademyColors.background : AcademyColors.accent).frame(width: 28, height: 28)
                .background(done ? AcademyColors.good : .clear, in: Circle())
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(AcademyType.headline)
                if !detail.isEmpty {
                    Text(detail).font(AcademyType.subheadline).foregroundStyle(AcademyColors.secondaryText).fixedSize(
                        horizontal: false, vertical: true)
                }
            }
        }
    }
    private var outcomeCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Rectangle().fill(AcademyColors.text).frame(height: 1)
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 7) {
                    if let outcome = viewModel.contactRequest.latestOutcome {
                        HStack(spacing: 6) {
                            Circle().fill(AcademyColors.good).frame(width: 6, height: 6)
                            Phase2Eyebrow(text: outcome.stage.displayName)
                        }
                        if let notes = outcome.notes, !notes.isEmpty {
                            Text(notes).font(AcademyType.subheadline).foregroundStyle(AcademyColors.secondaryText)
                        }
                    } else {
                        Phase2Eyebrow(text: "Introduction progress")
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
                Button(viewModel.contactRequest.latestOutcome == nil ? "Record outcome" : "Update outcome") {
                    isOutcomePresented = true
                }
                .font(AcademyType.footnote).underline().frame(minHeight: 44).accessibilityIdentifier(
                    "report-contact-outcome")
            }
            Divider()
        }
    }

    private var messageComposer: some View {
        HStack(alignment: .bottom, spacing: 10) {
            TextField("Message", text: $viewModel.draft, axis: .vertical)
                .textFieldStyle(.plain)
                .lineLimit(1...4)
                .padding(.horizontal, 13)
                .padding(.vertical, 11)
                .background(AcademyColors.elevatedSurface, in: Capsule())
                .overlay(Capsule().stroke(AcademyColors.hairline, lineWidth: 1))
                .accessibilityIdentifier("contact-message-composer")

            Button {
                Task { await viewModel.sendMessage() }
            } label: {
                Group {
                    if viewModel.isSending {
                        CleatLoader().tint(AcademyColors.onPrimary)
                    } else {
                        Image(systemName: "arrow.right")
                            .font(AcademyType.body.weight(.semibold))
                    }
                }
                .frame(width: 44, height: 44)
                .foregroundStyle(AcademyColors.onPrimary)
                .background(AcademyColors.primaryFill, in: Circle())
            }
            .disabled(!viewModel.canSend)
            .opacity(viewModel.canSend ? 1 : 0.45)
            .accessibilityLabel("Send message")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .background(AcademyColors.background)
    }

    private func presentMessageReportFixtureIfNeeded() {
        #if DEBUG
            guard
                FullCircleFixtureDestination.fromLaunchArguments(
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
                HStack(spacing: 8) {
                    Text(
                        (rendering.kind == .viewer
                            ? "You"
                            : (message.senderDisplayName?.split(separator: " ").first.map(String.init)
                                ?? rendering.displayLabel) + " · "
                                + (rendering.kind == .club ? clubDisplayName ?? "Club" : message.senderRole.rawValue))
                            .uppercased() + " · "
                            + Phase2Time.shortDate(message.createdAt, zone: TimeZone.current.identifier, format: "d MMM").uppercased()
                    )
                    .font(AcademyType.mono(9)).tracking(1.2).foregroundStyle(
                        rendering.kind == .club ? AcademyColors.accent : AcademyColors.secondaryText)
                    if rendering.kind != .viewer {
                        Button(action: onReport) { Image(systemName: "ellipsis").frame(width: 44, height: 44) }
                            .font(AcademyType.footnote).buttonStyle(.plain).foregroundStyle(AcademyColors.secondaryText)
                            .accessibilityLabel("Report message").accessibilityIdentifier(
                                "report-contact-message-\(message.id)")
                    }
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
                        in: RoundedRectangle(cornerRadius: 14)
                    )
                    .overlay {
                        if rendering.kind != .viewer {
                            RoundedRectangle(cornerRadius: 14).stroke(
                                rendering.kind == .club ? AcademyColors.accent : AcademyColors.hairline, lineWidth: 1)
                        }
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
            AcademyColors.surface
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
                                submissionError =
                                    viewModel.errorMessage
                                    ?? "We couldn't save this outcome. Please try again."
                            }
                        }
                    } label: {
                        HStack {
                            Spacer()
                            if viewModel.isReportingOutcome { CleatLoader() }
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

extension ContactOutcomeStage {
    fileprivate var iconName: String {
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
