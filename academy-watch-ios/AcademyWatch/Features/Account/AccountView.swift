import SwiftUI
import UIKit

enum AccountDestination: String, Hashable, Identifiable {
    case playerOnboarding
    case clubOnboarding
    case verification
    case sentRequests
    case incomingRequests
    case blockedUsers

    var id: String { rawValue }
}

struct AccountView: View {
    @EnvironmentObject private var authManager: AuthManager
    @ObservedObject var sentRequestsViewModel: SentContactRequestsViewModel
    @ObservedObject var incomingRequestsViewModel: IncomingContactRequestsViewModel
    @ObservedObject var contactAvailability: ContactFeatureAvailability

    @Binding var destination: AccountDestination?

    let apiClient: APIClient
    let fixtureDestination: FullCircleFixtureDestination?
    let onSignInRequested: () -> Void

    @State private var isDeleteAccountPresented = false
    @State private var hasApprovedPlayerClaim = false
    @State private var hasAnyPlayerClaim = false
    @State private var exportState: AccountExportState = .idle
    @State private var exportFile: AccountExportFile?
    @State private var exportedFileURL: URL?

    var body: some View {
        NavigationStack {
            debugOrAccountContent
                .navigationDestination(item: $destination) { destination in
                    switch destination {
                    case .playerOnboarding:
                        PlayerOnboardingView(apiClient: apiClient)
                    case .clubOnboarding:
                        ClubOnboardingView(apiClient: apiClient)
                    case .verification:
                        ScoutVerificationView(apiClient: apiClient)
                    case .sentRequests:
                        SentContactRequestsView(
                            viewModel: sentRequestsViewModel,
                            availability: contactAvailability,
                            apiClient: apiClient
                        )
                    case .incomingRequests:
                        IncomingContactRequestsView(
                            viewModel: incomingRequestsViewModel,
                            availability: contactAvailability,
                            apiClient: apiClient
                        )
                    case .blockedUsers:
                        BlockedUsersView(apiClient: apiClient)
                    }
                }
        }
    }

    @ViewBuilder
    private var debugOrAccountContent: some View {
        #if DEBUG
        switch fixtureDestination {
        case .verification:
            ScoutVerificationView(apiClient: apiClient)
        case .inbox, .clubConsent:
            SentContactRequestsView(
                viewModel: sentRequestsViewModel,
                availability: contactAvailability,
                apiClient: apiClient
            )
        case .playerInbox, .declineConfirmation:
            IncomingContactRequestsView(
                viewModel: incomingRequestsViewModel,
                availability: contactAvailability,
                apiClient: apiClient
            )
        case .thread:
            if let request = sentRequestsViewModel.requests.first(where: \.messagingOpen) {
                ContactThreadView(
                    contactRequest: request,
                    apiClient: apiClient,
                    availability: contactAvailability
                )
            } else {
                ContentUnavailableView("Fixture unavailable", systemImage: "exclamationmark.triangle")
            }
        case .messageReport:
            if let request = sentRequestsViewModel.requests.first(where: \.messagingOpen) {
                ContactThreadView(
                    contactRequest: request,
                    apiClient: apiClient,
                    availability: contactAvailability,
                    viewerRole: .player
                )
            } else {
                ContentUnavailableView("Fixture unavailable", systemImage: "exclamationmark.triangle")
            }
        case .blockedUsers:
            BlockedUsersView(apiClient: apiClient)
        case .deleteAccount, .introduction, .attestationWarning, .watchingYou, .claimGate,
             .watchlistNullStats, .exportData, .takedown, nil:
            accountHome
        }
        #else
        accountHome
        #endif
    }

    private var accountHome: some View {
        ZStack {
            AcademyColors.background.ignoresSafeArea()

            ScrollView {
                VStack(spacing: 18) {
                    if displaysSignedInAccount {
                        signedInHeader
                        identityOnboardingSection
                        verificationSection
                        contactSection
                        accountActionsSection
                    } else {
                        signedOutContent
                    }
                    legalSection
                }
                .padding(.horizontal, 18)
                .padding(.vertical, 22)
            }
        }
        .navigationTitle("Account")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $isDeleteAccountPresented) {
            DeleteAccountSheet(apiClient: apiClient)
                .environmentObject(authManager)
        }
        .sheet(item: $exportFile, onDismiss: removeExportFile) { file in
            ActivityView(activityItems: [file.url])
        }
        .task(id: authManager.isAuthenticated) {
            guard authManager.isAuthenticated else {
                hasApprovedPlayerClaim = false
                hasAnyPlayerClaim = false
                return
            }
            #if DEBUG
            if fixtureDestination == .deleteAccount {
                isDeleteAccountPresented = true
                return
            }
            #endif
            do {
                let response = try await apiClient.fetchMyProfileClaims()
                hasApprovedPlayerClaim = response.claims.contains {
                    $0.relationshipType == "player" && $0.status == .approved
                }
                hasAnyPlayerClaim = !response.claims.isEmpty
            } catch {
                hasApprovedPlayerClaim = incomingRequestsViewModel.ownsApprovedPlayerClaim
            }
        }
    }

    private var displaysSignedInAccount: Bool {
        authManager.isAuthenticated || fixtureDestination == .exportData
    }

    private var signedInHeader: some View {
        VStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(AcademyColors.claretSoft)
                    .frame(width: 76, height: 76)
                Image(systemName: "person.crop.circle.fill")
                    .font(.system(size: 54))
                    .foregroundStyle(AcademyColors.claret)
            }

            VStack(spacing: 4) {
                Text(authManager.displayName ?? "Academy Watch member")
                    .font(.title2.weight(.bold))
                if let email = authManager.email {
                    Text(email)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }

            VStack(spacing: 9) {
                HStack {
                    Label("Identity", systemImage: "person.text.rectangle")
                        .font(.subheadline.weight(.semibold))
                    Spacer()
                    BadgeView(text: identityName)
                }

                Divider()

                HStack {
                    Label("Scout verification", systemImage: "checkmark.shield")
                        .font(.subheadline.weight(.semibold))
                    Spacer()
                    if authManager.isVerifiedScout {
                        BadgeView(
                            text: "Verified scout",
                            foregroundColor: AcademyColors.positiveGreen,
                            backgroundColor: AcademyColors.positiveGreen.opacity(0.12)
                        )
                    } else if authManager.accountRole == .scout {
                        BadgeView(
                            text: "Scout unverified",
                            foregroundColor: AcademyColors.loanAmber,
                            backgroundColor: AcademyColors.loanAmber.opacity(0.12)
                        )
                    } else {
                        BadgeView(
                            text: "Not scout-verified",
                            foregroundColor: .secondary,
                            backgroundColor: Color.secondary.opacity(0.1)
                        )
                    }
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(20)
        .background(
            LinearGradient(
                colors: [AcademyColors.surface, AcademyColors.claretSoft.opacity(0.5)],
                startPoint: .top,
                endPoint: .bottomTrailing
            ),
            in: RoundedRectangle(cornerRadius: 21)
        )
        .overlay {
            RoundedRectangle(cornerRadius: 21)
                .stroke(AcademyColors.claret.opacity(0.14), lineWidth: 0.75)
        }
    }

    private var identityName: String {
        if hasApprovedPlayerClaim || incomingRequestsViewModel.ownsApprovedPlayerClaim {
            return AccountRole.player.displayName
        }
        return authManager.accountRole?.displayName ?? "Member"
    }

    private var identityOnboardingSection: some View {
        VStack(spacing: 12) {
            if !hasAnyPlayerClaim {
                Button {
                    destination = .playerOnboarding
                } label: {
                    OnboardingActionRow(
                        icon: "figure.soccer",
                        title: "Are you a player?",
                        detail: "Find and claim your profile, or create a pending community profile."
                    )
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("account-player-onboarding")
            }

            Button {
                destination = .clubOnboarding
            } label: {
                OnboardingActionRow(
                    icon: "shield.fill",
                    title: "Represent a club or academy?",
                    detail: "Submit a reviewed official claim and complete the public proof step."
                )
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("account-club-onboarding")
        }
    }

    private var verificationSection: some View {
        Button {
            destination = .verification
        } label: {
            HStack(spacing: 13) {
                Image(systemName: authManager.isVerifiedScout ? "checkmark.shield.fill" : "checkmark.shield")
                    .font(.title2)
                    .foregroundStyle(authManager.isVerifiedScout ? AcademyColors.positiveGreen : AcademyColors.claret)
                    .frame(width: 34)

                VStack(alignment: .leading, spacing: 4) {
                    Text("Scout Verification")
                        .font(.headline)
                    Text(
                        authManager.isVerifiedScout
                            ? "Your professional scouting role is verified."
                            : "Apply or check your verification status."
                    )
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.leading)
                }

                Spacer(minLength: 6)
                Image(systemName: "chevron.right")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.tertiary)
            }
            .padding(16)
            .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 17))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("account-scout-verification")
    }

    @ViewBuilder
    private var contactSection: some View {
        if contactAvailability.state == .available {
            VStack(spacing: 12) {
                if shouldShowIncomingEntryPoint {
                    Button {
                        destination = .incomingRequests
                    } label: {
                        HStack(spacing: 13) {
                            Image(systemName: "tray.full.fill")
                                .font(.title2)
                                .foregroundStyle(AcademyColors.claret)
                                .frame(width: 34)

                            VStack(alignment: .leading, spacing: 4) {
                                HStack(spacing: 8) {
                                    Text("Incoming Introductions")
                                        .font(.headline)
                                    if incomingRequestsViewModel.hasLoaded,
                                       !incomingRequestsViewModel.requests.isEmpty {
                                        BadgeView(
                                            text: incomingRequestsViewModel.requests.count.formatted()
                                        )
                                    }
                                }
                                Text("Review scout introductions for your claimed player profile.")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                    .multilineTextAlignment(.leading)
                            }

                            Spacer(minLength: 6)
                            if incomingRequestsViewModel.isLoading,
                               !incomingRequestsViewModel.hasLoaded {
                                ProgressView().controlSize(.small)
                            } else {
                                Image(systemName: "chevron.right")
                                    .font(.subheadline.weight(.bold))
                                    .foregroundStyle(.tertiary)
                            }
                        }
                        .padding(16)
                        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 17))
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("account-incoming-contact-requests")
                }

                Button {
                    destination = .sentRequests
                } label: {
                    HStack(spacing: 13) {
                        Image(systemName: "paperplane.fill")
                            .font(.title2)
                            .foregroundStyle(AcademyColors.claret)
                            .frame(width: 34)

                        VStack(alignment: .leading, spacing: 4) {
                            HStack(spacing: 8) {
                                Text("Sent Requests")
                                    .font(.headline)
                                if sentRequestsViewModel.hasLoaded, !sentRequestsViewModel.requests.isEmpty {
                                    BadgeView(text: sentRequestsViewModel.requests.count.formatted())
                                }
                            }
                            Text("Track requests, accepted threads, and outcomes.")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                                .multilineTextAlignment(.leading)
                        }

                        Spacer(minLength: 6)
                        if sentRequestsViewModel.isLoading, !sentRequestsViewModel.hasLoaded {
                            ProgressView().controlSize(.small)
                        } else {
                            Image(systemName: "chevron.right")
                                .font(.subheadline.weight(.bold))
                                .foregroundStyle(.tertiary)
                        }
                    }
                    .padding(16)
                    .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 17))
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("account-sent-contact-requests")
            }
        }
    }

    private var shouldShowIncomingEntryPoint: Bool {
        incomingRequestsViewModel.ownsApprovedPlayerClaim
            || incomingRequestsViewModel.isLoading
            || (incomingRequestsViewModel.hasLoaded && incomingRequestsViewModel.errorMessage != nil)
    }

    private var accountActionsSection: some View {
        VStack(spacing: 12) {
            Button {
                Task { await exportAccountData() }
            } label: {
                HStack(spacing: 13) {
                    Image(systemName: "square.and.arrow.down")
                        .font(.title2)
                        .foregroundStyle(AcademyColors.claret)
                        .frame(width: 34)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Export my data").font(.headline)
                        Text("Download a copy of everything we store about you")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.leading)
                    }
                    Spacer(minLength: 6)
                    if exportState == .loading {
                        ProgressView().controlSize(.small)
                    } else {
                        Image(systemName: "chevron.right")
                            .font(.subheadline.weight(.bold))
                            .foregroundStyle(.tertiary)
                    }
                }
                .padding(16)
                .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 17))
            }
            .buttonStyle(.plain)
            .disabled(exportState == .loading)
            .accessibilityIdentifier("account-export-data")

            if exportState == .failed {
                HStack(alignment: .top, spacing: 10) {
                    Label(
                        "We couldn’t prepare your export. Check your connection and try again.",
                        systemImage: "exclamationmark.triangle.fill"
                    )
                    .font(.footnote)
                    .foregroundStyle(Color(uiColor: .systemRed))
                    .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 4)
                    Button("Retry") {
                        Task { await exportAccountData() }
                    }
                    .font(.footnote.weight(.semibold))
                }
                .padding(.horizontal, 4)
            }

            Button {
                destination = .blockedUsers
            } label: {
                HStack(spacing: 13) {
                    Image(systemName: "person.crop.circle.badge.xmark")
                        .font(.title2)
                        .foregroundStyle(AcademyColors.claret)
                        .frame(width: 34)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Blocked users").font(.headline)
                        Text("Review people you’ve blocked or unblock them.")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(.tertiary)
                }
                .padding(16)
                .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 17))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("account-blocked-users")

            Button(role: .destructive) {
                authManager.signOut()
            } label: {
                Label("Sign Out", systemImage: "rectangle.portrait.and.arrow.right")
                    .frame(maxWidth: .infinity)
                    .frame(height: 44)
            }
            .buttonStyle(.bordered)

            Button(role: .destructive) {
                isDeleteAccountPresented = true
            } label: {
                Label("Delete account", systemImage: "trash")
                    .frame(maxWidth: .infinity)
                    .frame(height: 44)
            }
            .buttonStyle(.bordered)
            .accessibilityIdentifier("account-delete-account")
        }
    }

    private func exportAccountData() async {
        guard exportState != .loading else { return }
        exportState = .loading

        do {
            let data = try await apiClient.exportAccountData()
            let formatter = DateFormatter()
            formatter.calendar = Calendar(identifier: .gregorian)
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.timeZone = TimeZone(secondsFromGMT: 0)
            formatter.dateFormat = "yyyy-MM-dd"
            let fileName = "academy-watch-export-\(formatter.string(from: Date())).json"
            let url = FileManager.default.temporaryDirectory.appendingPathComponent(fileName)
            try data.write(to: url, options: .atomic)
            exportState = .ready
            exportedFileURL = url
            exportFile = AccountExportFile(url: url)
        } catch {
            exportState = .failed
        }
    }

    private func removeExportFile() {
        if let exportedFileURL {
            try? FileManager.default.removeItem(at: exportedFileURL)
        }
        exportedFileURL = nil
        exportFile = nil
        exportState = .idle
    }

    private var signedOutContent: some View {
        VStack(spacing: 18) {
            if let confirmation = authManager.accountDeletionConfirmationMessage {
                Label(confirmation, systemImage: "checkmark.circle.fill")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(AcademyColors.positiveGreen)
                    .multilineTextAlignment(.center)
                    .accessibilityIdentifier("account-deletion-confirmation")
            }
            Image(systemName: "person.crop.circle.badge.checkmark")
                .font(.system(size: 62))
                .foregroundStyle(AcademyColors.claret)
            Text("Your scout account")
                .font(.title2.weight(.bold))
            Text("Sign in to apply for scout verification, manage introduction requests, and continue accepted conversations.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button("Sign In", action: onSignInRequested)
                .buttonStyle(.borderedProminent)
                .tint(AcademyColors.claretFill)
                .frame(maxWidth: .infinity)
                .accessibilityIdentifier("account-sign-in")
        }
        .padding(24)
        .frame(maxWidth: .infinity)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 20))
    }

    private var legalSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Legal")
                .font(.title3.weight(.bold))
                .padding(.horizontal, 4)

            VStack(spacing: 0) {
                ForEach(LegalDestination.legalCases) { destination in
                    LegalSafariLink(destination: destination) {
                        HStack(spacing: 13) {
                            Image(systemName: destination.systemImage)
                                .font(.body.weight(.semibold))
                                .foregroundStyle(AcademyColors.claret)
                                .frame(width: 28)

                            Text(destination.title)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(.primary)

                            Spacer(minLength: 6)

                            Image(systemName: "arrow.up.right.square")
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(.tertiary)
                        }
                        .padding(.horizontal, 16)
                        .frame(minHeight: 50)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("account-legal-\(destination.rawValue)")

                    if destination != LegalDestination.legalCases.last {
                        Divider().padding(.leading, 57)
                    }
                }
            }
            .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 17))
        }
        .accessibilityIdentifier("account-legal-section")
    }
}

private enum AccountExportState: Equatable {
    case idle
    case loading
    case ready
    case failed
}

private struct AccountExportFile: Identifiable {
    let url: URL
    var id: URL { url }
}

private struct ActivityView: UIViewControllerRepresentable {
    let activityItems: [Any]

    func makeUIViewController(context _: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: activityItems, applicationActivities: nil)
    }

    func updateUIViewController(_: UIActivityViewController, context _: Context) {}
}

private struct DeleteAccountSheet: View {
    @EnvironmentObject private var authManager: AuthManager
    @Environment(\.dismiss) private var dismiss

    let apiClient: any AccountDeletionAPIClientProtocol

    @State private var isConfirming = false
    @State private var isDeleting = false
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 20) {
                Image(systemName: "trash.circle.fill")
                    .font(.system(size: 54))
                    .foregroundStyle(Color(uiColor: .systemRed))

                Text("Delete your account")
                    .font(.title2.weight(.bold))

                Text("Deletion is immediate and irreversible. Your sign-in account, profile claims, watchlist, lists, contact requests and messages, reports, and other content you submitted will be deleted or anonymized where records must be retained.")
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                Label("You will be signed out on this device.", systemImage: "key.slash")
                    .font(.subheadline.weight(.semibold))

                if let errorMessage {
                    Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                        .font(.footnote)
                        .foregroundStyle(Color(uiColor: .systemRed))
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer()

                Button(role: .destructive) {
                    isConfirming = true
                } label: {
                    HStack {
                        Spacer()
                        if isDeleting { ProgressView() }
                        Text(isDeleting ? "Deleting…" : "Continue to Delete")
                            .fontWeight(.semibold)
                        Spacer()
                    }
                    .frame(height: 44)
                }
                .buttonStyle(.borderedProminent)
                .tint(Color(uiColor: .systemRed))
                .disabled(isDeleting)
                .accessibilityIdentifier("confirm-account-deletion-step-one")
            }
            .padding(24)
            .navigationTitle("Account Deletion")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .disabled(isDeleting)
                }
            }
        }
        .interactiveDismissDisabled(isDeleting)
        .confirmationDialog(
            "Permanently delete account?",
            isPresented: $isConfirming,
            titleVisibility: .visible
        ) {
            Button("Delete Account Now", role: .destructive) {
                Task { await deleteAccount() }
            }
            Button("Keep Account", role: .cancel) {}
        } message: {
            Text("This cannot be undone. Your account and associated data will be deleted immediately.")
        }
        .task {
            #if DEBUG
            if FullCircleFixtureDestination.fromLaunchArguments(
                ProcessInfo.processInfo.arguments
            ) == .deleteAccount {
                try? await Task.sleep(for: .milliseconds(500))
                isConfirming = true
            }
            #endif
        }
    }

    private func deleteAccount() async {
        guard !isDeleting else { return }
        isDeleting = true
        errorMessage = nil
        defer { isDeleting = false }

        do {
            try await authManager.deleteAccount(using: apiClient)
            dismiss()
        } catch {
            errorMessage = "We couldn’t delete your account. Please check your connection and try again."
        }
    }
}
