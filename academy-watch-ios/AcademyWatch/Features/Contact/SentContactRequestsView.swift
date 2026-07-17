import SwiftUI

struct SentContactRequestsView: View {
    @ObservedObject var viewModel: SentContactRequestsViewModel
    @ObservedObject var availability: ContactFeatureAvailability

    let apiClient: APIClient

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            AcademyColors.background.ignoresSafeArea()

            if viewModel.isLoading, !viewModel.hasLoaded {
                ProgressView("Loading sent requests…")
                    .tint(AcademyColors.claret)
            } else if let error = viewModel.errorMessage, viewModel.requests.isEmpty {
                ContentUnavailableView {
                    Label("Requests unavailable", systemImage: "paperplane")
                } description: {
                    Text(error)
                } actions: {
                    Button("Try Again") {
                        Task { await viewModel.reload() }
                    }
                    .buttonStyle(.borderedProminent)
                }
            } else if viewModel.requests.isEmpty {
                ContentUnavailableView(
                    "No introduction requests",
                    systemImage: "paperplane",
                    description: Text("Requests you send from claimed player profiles will appear here.")
                )
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
                        foregroundColor: AcademyColors.loanAmber,
                        backgroundColor: AcademyColors.loanAmber.opacity(0.12)
                    )
                }
            }
        }
        .task {
            await viewModel.loadIfNeeded()
        }
        .onChange(of: availability.state) { _, state in
            if state == .unavailable { dismiss() }
        }
    }

    private var requestsList: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 12) {
                if let error = viewModel.errorMessage {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .font(.footnote)
                        .foregroundStyle(.red)
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
                    ProgressView("Loading more…")
                        .frame(maxWidth: .infinity)
                        .padding()
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
        }
        .refreshable {
            await viewModel.reload()
        }
    }

    @ViewBuilder
    private func requestDestination(_ request: ContactRequest) -> some View {
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
                        .font(.headline)
                        .lineLimit(1)
                    Text("Player #\(request.playerApiId)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 8)
                ContactStatusBadge(status: request.status)
            }

            ContactRoutingBadge(request: request)

            Text(request.message)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .lineLimit(2)

            if let outcome = request.latestOutcome {
                HStack(spacing: 7) {
                    Image(systemName: "flag.checkered")
                        .foregroundStyle(AcademyColors.transitionPurple)
                    Text("Latest: \(outcome.stage.displayName)")
                        .font(.caption.weight(.semibold))
                    Spacer()
                    if request.messagingOpen {
                        Image(systemName: "chevron.right")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.tertiary)
                    }
                }
                .padding(10)
                .background(
                    AcademyColors.transitionPurple.opacity(0.08),
                    in: RoundedRectangle(cornerRadius: 10)
                )
            } else {
                HStack {
                    Label(formattedDate(request.createdAt), systemImage: "calendar")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                    if request.messagingOpen {
                        Label("Open thread", systemImage: "bubble.left.and.bubble.right.fill")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(AcademyColors.claret)
                    }
                }
            }

            if let onWithdraw {
                Divider()
                Button(role: .destructive, action: onWithdraw) {
                    HStack(spacing: 7) {
                        if isWithdrawing { ProgressView().controlSize(.small) }
                        Text(isWithdrawing ? "Withdrawing…" : "Withdraw request")
                    }
                    .font(.subheadline.weight(.semibold))
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
                color: AcademyColors.loanAmber
            )
        case (.clubIncluded, .pending):
            EmptyView()
        case (.clubIncluded, .declined):
            badge(
                text: "Consent declined",
                systemImage: "xmark.shield.fill",
                color: Color(uiColor: .systemRed)
            )
        case (.clubIncluded, .granted):
            badge(
                text: "Club consent granted",
                systemImage: "checkmark.shield.fill",
                color: AcademyColors.positiveGreen
            )
        case (.clubNotified, _):
            badge(
                text: "Club notified",
                systemImage: "bell.badge.fill",
                color: AcademyColors.transitionPurple
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
        .font(.caption.weight(.semibold))
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
            return AcademyColors.loanAmber
        case .accepted:
            return AcademyColors.positiveGreen
        case .declined:
            return Color(uiColor: .systemRed)
        case .withdrawn, .expired:
            return .secondary
        }
    }
}
