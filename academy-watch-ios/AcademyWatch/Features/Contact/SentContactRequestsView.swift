import SwiftUI

struct SentContactRequestsView: View {
    @ObservedObject var viewModel: SentContactRequestsViewModel
    @ObservedObject var availability: ContactFeatureAvailability

    let apiClient: APIClient

    @Environment(\.dismiss) private var dismiss
    @State private var reportSubject: ContentReportSubject?

    var body: some View {
        ZStack {
            AcademyColors.background.ignoresSafeArea()

            if viewModel.isLoading, !viewModel.hasLoaded {
                WingLiftLoadingView("Loading sent requests…")
            } else if let error = viewModel.errorMessage, viewModel.requests.isEmpty {
                ContentUnavailableView {
                    Label("Requests unavailable", systemImage: "paperplane")
                .font(AcademyType.title2)
                .foregroundStyle(AcademyColors.text)
                } description: {
                    Text(error)
                } actions: {
                    Button("Try Again") {
                        Task { await viewModel.reload() }
                    }
                    .buttonStyle(FloodlightPillStyle())
                }
            } else if viewModel.requests.isEmpty {
                FloodlightEmptyState(title: "No introduction requests", systemImage: "paperplane", description: "Requests you send from claimed player profiles will appear here.")
            } else {
                requestsList
            }
        }
        .navigationTitle("Sent Requests")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if viewModel.isFixturePreview {
                ToolbarItem(placement: .topBarTrailing) {
                    BadgeView(
                        text: "Fixture preview",
                        foregroundColor: AcademyColors.warnText,
                        backgroundColor: AcademyColors.warnText.opacity(0.12)
                    )
                }
            }
        }
        .task {
            await viewModel.reload()
        }
        .onChange(of: availability.state) { _, state in
            if state == .unavailable { dismiss() }
        }
        .sheet(item: $reportSubject) { subject in
            ContentReportSheet(subject: subject, apiClient: apiClient)
        }
    }

    private var requestsList: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 12) {
                if let error = viewModel.errorMessage {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .font(AcademyType.footnote)
                        .foregroundStyle(AcademyColors.danger)
                        .padding(.horizontal, 4)
                }

                ForEach(viewModel.requests) { request in
                    requestDestination(request)
                        .onAppear {
                            if request.id == viewModel.requests.last?.id, viewModel.canLoadMore {
                                Task { await viewModel.loadNextPage() }
                            }
                        }
                }

                if viewModel.isLoadingMore {
                    WingLiftLoadingView("Loading more…")
                        .frame(maxWidth: .infinity)
                        .padding()
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
        }.background(AcademyColors.background)
        .refreshable {
            await viewModel.reload()
        }
    }

    @ViewBuilder
    private func requestDestination(_ request: ContactRequest) -> some View {
        VStack(spacing: 8) {
            if request.messagingOpen {
                NavigationLink {
                    ContactThreadView(
                        contactRequest: request,
                        apiClient: apiClient,
                        availability: availability,
                        viewerRole: .scout
                    )
                } label: {
                    ContactRequestCard(
                        request: request,
                        isWithdrawing: false,
                        onWithdraw: nil
                    )
                }
                .buttonStyle(.plain)
                .accessibilityHint("Opens the accepted introduction thread")
            } else {
                ContactRequestCard(
                    request: request,
                    isWithdrawing: viewModel.withdrawingRequestIDs.contains(request.id),
                    onWithdraw: request.status == .pending
                        ? { Task { await viewModel.withdraw(request) } }
                        : nil
                )
            }

            HStack(spacing: 14) {
                Button {
                    reportSubject = .request(request)
                } label: {
                    Label("Report", systemImage: "exclamationmark.bubble")
                }
                .accessibilityIdentifier("report-sent-contact-request")

                if let accountID = request.participants.player.userId {
                    BlockUserButton(
                        accountID: accountID,
                        displayName: request.participants.player.displayName,
                        apiClient: apiClient
                    )
                }

                Spacer()
            }
            .font(AcademyType.caption.weight(.medium))
            .buttonStyle(.plain)
            .foregroundStyle(AcademyColors.accent)
            .padding(.horizontal, 14)
        }
    }
}

private struct ContactRequestCard: View {
    let request: ContactRequest
    let isWithdrawing: Bool
    let onWithdraw: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(request.participants.player.displayName ?? "Player #\(request.playerApiId)")
                        .font(AcademyType.headline)
                        .lineLimit(1)
                    Text("Player #\(request.playerApiId)")
                        .font(AcademyType.caption)
                        .foregroundStyle(AcademyColors.secondaryText)
                }
                Spacer(minLength: 8)
                ContactStatusBadge(status: request.status)
            }

            ContactRoutingBadge(request: request)

            Text(request.message)
                .font(AcademyType.subheadline)
                .foregroundStyle(AcademyColors.secondaryText)
                .lineLimit(2)

            if let outcome = request.latestOutcome {
                HStack(spacing: 7) {
                    Image(systemName: "flag.checkered")
                        .foregroundStyle(AcademyColors.secondaryText)
                    Text("Latest: \(outcome.stage.displayName)")
                        .font(AcademyType.caption.weight(.medium))
                    Spacer()
                    if request.messagingOpen {
                        Image(systemName: "chevron.right")
                            .font(AcademyType.caption.weight(.medium))
                            .foregroundStyle(AcademyColors.secondaryText)
                    }
                }
                .padding(10)
                .background(
                    AcademyColors.secondaryText.opacity(0.08),
                    in: RoundedRectangle(cornerRadius: 10)
                )
            } else {
                HStack {
                    Label(formattedDate(request.createdAt), systemImage: "calendar")
                        .font(AcademyType.caption)
                        .foregroundStyle(AcademyColors.secondaryText)
                    Spacer()
                    if request.messagingOpen {
                        Label("Open thread", systemImage: "bubble.left.and.bubble.right.fill")
                            .font(AcademyType.caption.weight(.medium))
                            .foregroundStyle(AcademyColors.accent)
                    }
                }
            }

            if let onWithdraw {
                Divider()
                Button(role: .destructive, action: onWithdraw) {
                    HStack(spacing: 7) {
                        if isWithdrawing { WingLiftLoadingView().controlSize(.small) }
                        Text(isWithdrawing ? "Withdrawing…" : "Withdraw request")
                    }
                    .font(AcademyType.subheadline.weight(.semibold))
                }
                .disabled(isWithdrawing)
                .accessibilityIdentifier("withdraw-contact-request")
            }
        }
        .padding(15)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 17))
        .overlay {
            RoundedRectangle(cornerRadius: 17)
                .stroke(AcademyColors.separator.opacity(0.3), lineWidth: 0.6)
        }
    }

    private func formattedDate(_ raw: String?) -> String {
        guard let raw else { return "Date unavailable" }
        let parser = ISO8601DateFormatter()
        let date = parser.date(from: raw + (raw.hasSuffix("Z") ? "" : "Z"))
        guard let date else { return String(raw.prefix(10)) }
        return date.formatted(date: .abbreviated, time: .omitted)
    }
}

struct ContactRoutingBadge: View {
    let request: ContactRequest

    @ViewBuilder
    var body: some View {
        switch (request.routingMode, request.clubConsentStatus) {
        case (.clubIncluded, .pending)
            where request.status == .pending || request.status == .accepted:
            badge(
                text: "Club reviewing",
                systemImage: "building.2.crop.circle",
                color: AcademyColors.warnText
            )
        case (.clubIncluded, .pending):
            EmptyView()
        case (.clubIncluded, .declined):
            badge(
                text: "Consent declined",
                systemImage: "xmark.shield.fill",
                color: AcademyColors.danger
            )
        case (.clubIncluded, .granted):
            badge(
                text: "Club consent granted",
                systemImage: "checkmark.shield.fill",
                color: AcademyColors.good
            )
        case (.clubNotified, _):
            badge(
                text: "Club notified",
                systemImage: "bell.badge.fill",
                color: AcademyColors.secondaryText
            )
        case (.direct, _), (.clubIncluded, nil):
            EmptyView()
        }
    }

    private func badge(text: String, systemImage: String, color: Color) -> some View {
        HStack(spacing: 6) {
            Image(systemName: systemImage)
            Text(text)
        }
        .font(AcademyType.caption.weight(.medium))
        .foregroundStyle(color)
        .padding(.horizontal, 9)
        .padding(.vertical, 6)
        .background(color.opacity(0.1), in: Capsule())
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("contact-routing-\(request.routingMode.rawValue)")
    }
}

struct ContactStatusBadge: View {
    let status: ContactRequestStatus

    var body: some View {
        BadgeView(
            text: status.displayName,
            foregroundColor: color,
            backgroundColor: color.opacity(0.12)
        )
    }

    private var color: Color {
        switch status {
        case .pending:
            return AcademyColors.warnText
        case .accepted:
            return AcademyColors.good
        case .declined:
            return AcademyColors.danger
        case .withdrawn, .expired:
            return .secondary
        }
    }
}
