import SwiftUI

struct IncomingContactRequestsView: View {
    @ObservedObject var viewModel: IncomingContactRequestsViewModel
    @ObservedObject var availability: ContactFeatureAvailability

    let apiClient: APIClient

    @Environment(\.dismiss) private var dismiss
    @State private var pendingDecision: IncomingContactDecision?
    @State private var reportSubject: ContentReportSubject?
    @State private var selectedThreadID: String?

    var body: some View {
        ZStack {
            AcademyColors.background.ignoresSafeArea()

            if viewModel.isLoading, !viewModel.hasLoaded {
                ProgressView("Checking your introductions…")
                    .tint(AcademyColors.claret)
            } else if let error = viewModel.errorMessage, viewModel.requests.isEmpty {
                ContentUnavailableView {
                    Label("Introductions unavailable", systemImage: "tray")
                } description: {
                    Text(error)
                } actions: {
                    Button("Try Again") {
                        Task { await viewModel.reload() }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(AcademyColors.claretFill)
                }
            } else if viewModel.hasLoaded, !viewModel.ownsApprovedPlayerClaim {
                ContentUnavailableView(
                    "No approved player claim",
                    systemImage: "person.crop.circle.badge.checkmark",
                    description: Text(
                        "Once your player-profile claim is approved, incoming scout introductions will appear here."
                    )
                )
            } else if viewModel.requests.isEmpty {
                ContentUnavailableView(
                    "Your inbox is clear",
                    systemImage: "tray",
                    description: Text(
                        "When a verified scout requests an introduction, you’ll be able to review it here."
                    )
                )
            } else {
                requestsList
            }
        }
        .navigationTitle("Introduction Inbox")
        .navigationBarTitleDisplayMode(.inline)
        .navigationDestination(item: $selectedThreadID) { requestID in
            if let request = viewModel.requests.first(where: { $0.id == requestID }) {
                ContactThreadView(
                    contactRequest: request,
                    apiClient: apiClient,
                    availability: availability,
                    viewerRole: .player
                )
            } else {
                ContentUnavailableView(
                    "Introduction unavailable",
                    systemImage: "bubble.left.and.bubble.right"
                )
            }
        }
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
            showFixtureConfirmationIfNeeded()
        }
        .onChange(of: availability.state) { _, state in
            if state == .unavailable {
                pendingDecision = nil
                reportSubject = nil
                dismiss()
            }
        }
        .confirmationDialog(
            pendingDecision?.action.title ?? "Respond to introduction",
            isPresented: Binding(
                get: { pendingDecision != nil },
                set: { if !$0 { pendingDecision = nil } }
            ),
            titleVisibility: .visible,
            presenting: pendingDecision
        ) { decision in
            Button(decision.action.confirmButtonTitle, role: decision.action.buttonRole) {
                pendingDecision = nil
                Task {
                    await perform(decision)
                }
            }
            Button("Cancel", role: .cancel) {
                pendingDecision = nil
            }
        } message: { decision in
            Text(decision.action.message(for: decision.request))
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
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .padding(.horizontal, 4)
                }

                ForEach(viewModel.requests) { request in
                    IncomingContactRequestCard(
                        request: request,
                        isResponding: viewModel.respondingRequestIDs.contains(request.id),
                        apiClient: apiClient,
                        availability: availability,
                        onAccept: {
                            pendingDecision = IncomingContactDecision(
                                request: request,
                                action: .accept
                            )
                        },
                        onDecline: {
                            pendingDecision = IncomingContactDecision(
                                request: request,
                                action: .decline
                            )
                        },
                        onReport: {
                            reportSubject = .request(request)
                        }
                    )
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

    private func showFixtureConfirmationIfNeeded() {
        #if DEBUG
        guard pendingDecision == nil,
              FullCircleFixtureDestination.fromLaunchArguments(
                  ProcessInfo.processInfo.arguments
              ) == .declineConfirmation,
              let pendingRequest = viewModel.requests.first(where: { $0.status == .pending })
        else { return }
        pendingDecision = IncomingContactDecision(request: pendingRequest, action: .decline)
        #endif
    }

    private func perform(_ decision: IncomingContactDecision) async {
        switch decision.action {
        case .accept:
            await viewModel.accept(decision.request)
            let requestID = decision.request.id
            guard let index = viewModel.requests.firstIndex(where: { $0.id == requestID })
            else { return }
            let acceptedRequest = viewModel.requests[index]
            if acceptedRequest.status == .accepted {
                selectedThreadID = acceptedRequest.id
            }
        case .decline:
            await viewModel.decline(decision.request)
        }
    }
}

private struct IncomingContactRequestCard: View {
    let request: ContactRequest
    let isResponding: Bool
    let apiClient: APIClient
    let availability: ContactFeatureAvailability
    let onAccept: () -> Void
    let onDecline: () -> Void
    let onReport: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(request.participants.scout.displayName ?? "Scout identity unavailable")
                        .font(.headline)
                        .lineLimit(1)
                    Text("Received \(formattedDate(request.createdAt))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer(minLength: 8)
                ContactStatusBadge(status: request.status)
            }

            Text(request.message)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            Divider()

            actionRow
        }
        .padding(15)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 17))
        .overlay {
            RoundedRectangle(cornerRadius: 17)
                .stroke(AcademyColors.separator.opacity(0.3), lineWidth: 0.6)
        }
    }

    @ViewBuilder
    private var actionRow: some View {
        HStack(spacing: 10) {
            if request.status == .pending, !isResponding {
                Button("Decline", role: .destructive, action: onDecline)
                    .buttonStyle(.bordered)
                    .accessibilityIdentifier("decline-contact-request")

                Button("Accept", action: onAccept)
                    .buttonStyle(.borderedProminent)
                    .tint(AcademyColors.claretFill)
                    .accessibilityIdentifier("accept-contact-request")
            } else if isResponding {
                ProgressView()
                    .controlSize(.small)
                Text(request.status == .accepted ? "Accepting…" : "Declining…")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
            } else if request.status == .accepted {
                NavigationLink {
                    ContactThreadView(
                        contactRequest: request,
                        apiClient: apiClient,
                        availability: availability,
                        viewerRole: .player
                    )
                } label: {
                    Label("Open thread", systemImage: "bubble.left.and.bubble.right.fill")
                }
                .buttonStyle(.borderedProminent)
                .tint(AcademyColors.claretFill)
                .accessibilityIdentifier("open-player-contact-thread")
            } else {
                Text(statusExplanation)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer(minLength: 0)

            Button(action: onReport) {
                Label("Report", systemImage: "exclamationmark.bubble")
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
            }
            .buttonStyle(.bordered)
            .tint(AcademyColors.claret)
            .layoutPriority(1)
            .accessibilityIdentifier("report-contact-request")
        }
    }

    private var statusExplanation: String {
        switch request.status {
        case .declined:
            "Request declined"
        case .withdrawn:
            "Withdrawn by scout"
        case .expired:
            "Request expired"
        case .pending, .accepted:
            request.status.displayName
        }
    }

    private func formattedDate(_ raw: String) -> String {
        let parser = ISO8601DateFormatter()
        let date = parser.date(from: raw + (raw.hasSuffix("Z") ? "" : "Z"))
        guard let date else { return String(raw.prefix(10)) }
        return date.formatted(date: .abbreviated, time: .omitted)
    }
}

private struct IncomingContactDecision: Identifiable {
    let request: ContactRequest
    let action: Action

    var id: String { "\(request.id):\(action.id)" }

    enum Action: String {
        case accept
        case decline

        var id: String { rawValue }

        var title: String {
            switch self {
            case .accept: "Accept this introduction?"
            case .decline: "Decline this introduction?"
            }
        }

        var confirmButtonTitle: String {
            switch self {
            case .accept: "Accept and Open Thread"
            case .decline: "Decline Request"
            }
        }

        var buttonRole: ButtonRole? {
            self == .decline ? .destructive : nil
        }

        func message(for request: ContactRequest) -> String {
            switch self {
            case .accept:
                let scoutName = request.participants.scout.displayName ?? "this scout"
                return "Accepting opens a private thread with \(scoutName). Either participant can message and report an outcome."
            case .decline:
                return "Declining closes this request and prevents the scout from requesting again during the cooldown window. To stop the request and flag a concern, decline it, then use Report—reporting alone does not block the scout."
            }
        }
    }
}
