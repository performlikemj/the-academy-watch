import SwiftUI

struct IntroductionRequestSectionView: View {
    @StateObject private var viewModel: IntroductionRequestViewModel
    @ObservedObject private var availability: ContactFeatureAvailability
    @State private var isSheetPresented = false

    private let playerName: String
    private let onVerificationRequested: () -> Void
    private let isFixturePreview: Bool

    init(
        playerID: Int,
        playerName: String,
        apiClient: any ContactAPIClientProtocol,
        availability: ContactFeatureAvailability,
        onVerificationRequested: @escaping () -> Void
    ) {
        let fixtureDestination = FullCircleFixtureDestination.fromLaunchArguments(
            ProcessInfo.processInfo.arguments
        )
        let isFixture = fixtureDestination == .introduction
            || fixtureDestination == .attestationWarning
        #if DEBUG
        let initialMessage = isFixture ? IntroductionRequestViewModel.debugFixtureMessage : ""
        #else
        let initialMessage = ""
        #endif
        _viewModel = StateObject(
            wrappedValue: IntroductionRequestViewModel(
                playerID: playerID,
                apiClient: apiClient,
                availability: availability,
                initialMessage: initialMessage,
                initialFailure: fixtureDestination == .attestationWarning
                    ? .attestationRequired
                    : nil
            )
        )
        _availability = ObservedObject(wrappedValue: availability)
        self.playerName = playerName
        self.onVerificationRequested = onVerificationRequested
        isFixturePreview = isFixture
    }

    var body: some View {
        if !availability.isUnavailable {
            VStack(alignment: .leading, spacing: 11) {
                HStack(spacing: 8) {
                    Label("SCOUT INTRODUCTION", systemImage: "paperplane.fill")
                        .font(.caption.weight(.bold))
                        .tracking(1.05)
                        .foregroundStyle(AcademyColors.claret)

                    Spacer()

                    if isFixturePreview {
                        fixtureBadge
                    }
                }

                Text("Start a private introduction")
                    .font(.headline)
                Text("Send a considered request to the player profile owner and, where required, their club. A thread opens after every required approval.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                Button {
                    viewModel.clearFailure()
                    isSheetPresented = true
                } label: {
                    Label("Request Introduction", systemImage: "person.crop.circle.badge.plus")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(AcademyColors.claretFill)
                .accessibilityIdentifier("request-introduction")
            }
            .padding(14)
            .background(
                LinearGradient(
                    colors: [AcademyColors.claretSoft.opacity(0.8), AcademyColors.surface],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                ),
                in: RoundedRectangle(cornerRadius: 16)
            )
            .overlay {
                RoundedRectangle(cornerRadius: 16)
                    .stroke(AcademyColors.claret.opacity(0.2), lineWidth: 0.75)
            }
            .sheet(isPresented: $isSheetPresented) {
                IntroductionRequestSheet(
                    viewModel: viewModel,
                    availability: availability,
                    playerName: playerName,
                    isFixturePreview: isFixturePreview,
                    onVerificationRequested: {
                        isSheetPresented = false
                        onVerificationRequested()
                    }
                )
            }
            .onAppear {
                if isFixturePreview {
                    isSheetPresented = true
                }
            }
            .onChange(of: availability.state) { _, newState in
                if newState == .unavailable {
                    isSheetPresented = false
                }
            }
        }
    }

    private var fixtureBadge: some View {
        BadgeView(
            text: "Fixture preview",
            foregroundColor: AcademyColors.loanAmber,
            backgroundColor: AcademyColors.loanAmber.opacity(0.12)
        )
    }
}

private struct IntroductionRequestSheet: View {
    @ObservedObject var viewModel: IntroductionRequestViewModel
    @ObservedObject var availability: ContactFeatureAvailability
    let playerName: String
    let isFixturePreview: Bool
    let onVerificationRequested: () -> Void

    @Environment(\.dismiss) private var dismiss
    @FocusState private var isMessageFocused: Bool
    @State private var permissionAttestationConfirmed = false

    var body: some View {
        NavigationStack {
            ZStack {
                AcademyColors.background.ignoresSafeArea()

                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 20) {
                            playerHeader

                            if let request = viewModel.createdRequest {
                                successCard(request)
                            } else {
                                composer
                                privacyNote
                                failureContent
                                    .id("introduction-request-failure")
                            }
                        }
                        .padding(20)
                    }
                    .scrollDismissesKeyboard(.interactively)
                    .onAppear {
                        scrollToAttestationIfNeeded(using: proxy, animated: false)
                    }
                    .onChange(of: viewModel.failure) { _, _ in
                        scrollToAttestationIfNeeded(using: proxy, animated: true)
                    }
                }
            }
            .navigationTitle("Request Introduction")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(viewModel.createdRequest == nil ? "Close" : "Done") {
                        dismiss()
                    }
                }
            }
        }
        .tint(AcademyColors.claret)
        .presentationDetents([.large])
        .interactiveDismissDisabled(viewModel.isSubmitting)
        .onAppear {
            if !isFixturePreview, viewModel.createdRequest == nil {
                isMessageFocused = true
            }
        }
        .onChange(of: availability.state) { _, state in
            if state == .unavailable { dismiss() }
        }
    }

    private var playerHeader: some View {
        HStack(spacing: 14) {
            Image(systemName: "person.crop.circle.fill")
                .font(.system(size: 42))
                .foregroundStyle(AcademyColors.claret)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 3) {
                Text(playerName)
                    .font(.title3.weight(.bold))
                Text("Claimed player profile")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            if isFixturePreview {
                BadgeView(
                    text: "Fixture preview",
                    foregroundColor: AcademyColors.loanAmber,
                    backgroundColor: AcademyColors.loanAmber.opacity(0.12)
                )
                .fixedSize(horizontal: true, vertical: false)
            }
        }
        .padding(16)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 18))
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                Text("YOUR MESSAGE")
                    .font(.caption.weight(.bold))
                    .tracking(1)
                    .foregroundStyle(AcademyColors.claret)
                Spacer()
                Text("\(viewModel.characterCount)/\(IntroductionRequestViewModel.maximumMessageLength)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(
                        viewModel.characterCount > IntroductionRequestViewModel.maximumMessageLength
                            ? Color.red
                            : Color.secondary
                    )
            }

            TextEditor(text: $viewModel.message)
                .focused($isMessageFocused)
                .frame(minHeight: 180)
                .padding(10)
                .scrollContentBackground(.hidden)
                .background(Color(uiColor: .tertiarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 13))
                .accessibilityIdentifier("introduction-message")

            Button {
                Task { await viewModel.submit() }
            } label: {
                HStack(spacing: 9) {
                    if viewModel.isSubmitting {
                        ProgressView().tint(AcademyColors.claretOnFill)
                    }
                    Label(
                        viewModel.isSubmitting ? "Sending…" : "Send Introduction Request",
                        systemImage: "paperplane.fill"
                    )
                }
                .frame(maxWidth: .infinity)
                .frame(height: 48)
            }
            .buttonStyle(.borderedProminent)
            .tint(AcademyColors.claretFill)
            .disabled(!viewModel.canSubmit)
            .accessibilityIdentifier("send-introduction")
        }
    }

    private var privacyNote: some View {
        Label(
            "Your account identity and this message are shared with the player profile owner and, where required, their club. Messaging opens only after the player accepts and any required club consent is granted.",
            systemImage: "lock.shield"
        )
        .font(.footnote)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private var failureContent: some View {
        if let failure = viewModel.failure {
            VStack(alignment: .leading, spacing: 11) {
                Label(failure.message, systemImage: failure.routesToVerification ? "checkmark.shield" : "info.circle")
                    .font(.subheadline)
                    .foregroundStyle(failure.routesToVerification ? AcademyColors.claret : .secondary)
                    .fixedSize(horizontal: false, vertical: true)

                if failure.routesToVerification {
                    Button("Open Scout Verification", action: onVerificationRequested)
                        .buttonStyle(.bordered)
                }

                if failure.requiresPermissionAttestation {
                    VStack(alignment: .leading, spacing: 12) {
                        Toggle(isOn: $permissionAttestationConfirmed) {
                            Text(
                                "I confirm my club has, or will obtain, the required permission before any approach to this player if they are contracted."
                            )
                            .font(.subheadline.weight(.semibold))
                            .fixedSize(horizontal: false, vertical: true)
                        }
                        .toggleStyle(.switch)
                        .accessibilityIdentifier("permission-attestation-confirmation")

                        Button {
                            Task {
                                await viewModel.retryWithPermissionAttestation()
                                permissionAttestationConfirmed = false
                            }
                        } label: {
                            HStack(spacing: 9) {
                                if viewModel.isSubmitting {
                                    ProgressView().tint(AcademyColors.claretOnFill)
                                }
                                Text(viewModel.isSubmitting ? "Sending…" : "Confirm and Send Request")
                                    .fontWeight(.semibold)
                            }
                            .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(AcademyColors.claretFill)
                        .disabled(!permissionAttestationConfirmed || viewModel.isSubmitting)
                        .accessibilityIdentifier("send-attested-introduction")
                    }
                    .onDisappear {
                        // A permission attestation is an explicit act for this
                        // attempt. Never carry it into another presentation.
                        permissionAttestationConfirmed = false
                    }
                }
            }
            .padding(14)
            .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 14))
        }
    }

    private func successCard(_ request: ContactRequest) -> some View {
        VStack(spacing: 14) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 48))
                .foregroundStyle(AcademyColors.positiveGreen)
            Text("Request sent")
                .font(.title2.weight(.bold))
            Text(successMessage(for: request))
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            BadgeView(
                text: request.status.displayName,
                foregroundColor: AcademyColors.loanAmber,
                backgroundColor: AcademyColors.loanAmber.opacity(0.12)
            )
            ContactRoutingBadge(request: request)
        }
        .frame(maxWidth: .infinity)
        .padding(24)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 20))
    }

    private func successMessage(for request: ContactRequest) -> String {
        if request.routingMode == .clubIncluded {
            let clubName = request.participants.club?.displayName ?? "their club"
            return "The player profile owner and \(clubName) can now review it. You can withdraw it or follow its status from Sent Requests."
        }
        return "The player profile owner can now review it. You can withdraw it or follow its status from Sent Requests."
    }

    private func scrollToAttestationIfNeeded(
        using proxy: ScrollViewProxy,
        animated: Bool
    ) {
        guard viewModel.failure?.requiresPermissionAttestation == true else { return }
        DispatchQueue.main.async {
            if animated {
                withAnimation {
                    proxy.scrollTo("introduction-request-failure", anchor: .bottom)
                }
            } else {
                proxy.scrollTo("introduction-request-failure", anchor: .bottom)
            }
        }
    }
}
