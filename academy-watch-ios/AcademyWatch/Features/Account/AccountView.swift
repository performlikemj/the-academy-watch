import SwiftUI
import UIKit

enum AccountDestination: String, Hashable, Identifiable {
    case myProfiles
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
    @AppStorage(ExperienceRole.storageKey) private var roleValue = ""
    @ObservedObject var sentRequestsViewModel: SentContactRequestsViewModel
    @ObservedObject var incomingRequestsViewModel: IncomingContactRequestsViewModel
    @ObservedObject var contactAvailability: ContactFeatureAvailability

    @Binding var destination: AccountDestination?

    let apiClient: APIClient
    let fixtureDestination: FullCircleFixtureDestination?
    let onSignInRequested: () -> Void
    let onGolRequested: () -> Void
    var phase2Membership: ClubMembership? = nil

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
                    case .myProfiles:
                        MyProfilesView(apiClient: apiClient)
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
             .watchlistNullStats, .exportData, .takedown, .fanRow, nil:
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
                    Button(action: onGolRequested) {
                        HStack(spacing: 14) {
                            Image(systemName: "bubble.left.and.bubble.right.fill").font(AcademyType.title2)
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Ask GOL").font(AcademyType.headline)
                                Text("Your football AI assistant").font(AcademyType.subheadline)
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                        }
                        .padding(18)
                        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10))
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(AcademyColors.accent)
                    .accessibilityLabel("Ask GOL, your football AI assistant")
                    .accessibilityIdentifier("gol-entry")
                    if displaysSignedInAccount {
                        signedInHeader
                        if let membership = phase2Membership, membership.access.canManageAccess {
                            NavigationLink { StaffAccessView(programId: membership.id, client: apiClient) } label: { Label("Staff & access", systemImage: "person.badge.key") }.accessibilityIdentifier("account-staff-access")
                        }
                        identityOnboardingSection
                        verificationSection
                        contactSection
                        accountActionsSection
                    } else {
                        signedOutContent
                    }
                    homeExperienceSection
                    legalSection
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 22)
            }.background(AcademyColors.background)
            .accessibilityIdentifier("account-scroll")
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

    private var homeExperienceSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("App experience")
                .font(AcademyType.title3)
                .padding(.horizontal, 4)

            Menu {
                Button("Not chosen") { roleValue = "" }
                    .accessibilityIdentifier("account-home-role-none")
                Divider()
                ForEach(ExperienceRole.allCases) { role in
                    Button(role.selectionTitle) { roleValue = role.rawValue }
                        .accessibilityIdentifier("account-home-role-\(role.rawValue)")
                }
            } label: {
                HStack(spacing: 13) {
                    Image(systemName: "rectangle.3.group.fill")
                        .font(AcademyType.title2)
                        .foregroundStyle(AcademyColors.accent)
                        .frame(width: 34)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Home experience").font(AcademyType.headline)
                        Text("Choose which part of Academy Watch opens first.")
                            .font(AcademyType.subheadline)
                            .foregroundStyle(AcademyColors.secondaryText)
                    }
                    Spacer(minLength: 6)
                    Text(ExperienceRole(rawValue: roleValue)?.selectionTitle ?? "Not chosen")
                        .font(AcademyType.subheadline.weight(.semibold))
                    Image(systemName: "chevron.up.chevron.down")
                        .font(AcademyType.caption.weight(.medium))
                        .foregroundStyle(AcademyColors.secondaryText)
                }
                .padding(16)
                .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 17))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("account-home-experience")
        }
    }

    private var signedInHeader: some View {
        VStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(AcademyColors.accentSoft)
                    .frame(width: 76, height: 76)
                Image(systemName: "person.crop.circle.fill")
                    .font(AcademyType.ui( 54))
                    .foregroundStyle(AcademyColors.accent)
            }

            VStack(spacing: 4) {
                Text(authManager.displayName ?? "Academy Watch member")
                    .font(AcademyType.title2)
                if let email = authManager.email {
                    Text(email)
                        .font(AcademyType.subheadline)
                        .foregroundStyle(AcademyColors.secondaryText)
                }
            }

            VStack(spacing: 9) {
                HStack {
                    Label("Identity", systemImage: "person.text.rectangle")
                        .font(AcademyType.subheadline.weight(.semibold))
                    Spacer()
                    BadgeView(text: identityName)
                }

                Divider()

                HStack {
                    Label("Scout verification", systemImage: "checkmark.shield")
                        .font(AcademyType.subheadline.weight(.semibold))
                    Spacer()
                    if authManager.isVerifiedScout {
                        BadgeView(
                            text: "Verified scout",
                            foregroundColor: AcademyColors.good,
                            backgroundColor: AcademyColors.good.opacity(0.12)
                        )
                    } else if authManager.accountRole == .scout {
                        BadgeView(
                            text: "Scout unverified",
                            foregroundColor: AcademyColors.warnText,
                            backgroundColor: AcademyColors.warnText.opacity(0.12)
                        )
                    } else {
                        BadgeView(
                            text: "Not scout-verified",
                            foregroundColor: AcademyColors.secondaryText,
                            backgroundColor: AcademyColors.secondaryText.opacity(0.1)
                        )
                    }
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(20)
        .background(AcademyColors.background, in: RoundedRectangle(cornerRadius: 10))
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .stroke(AcademyColors.hairline, lineWidth: 1)
        }
        .accessibilityIdentifier("account-signed-in")
    }

    private var identityName: String {
        if hasApprovedPlayerClaim || incomingRequestsViewModel.ownsApprovedPlayerClaim {
            return AccountRole.player.displayName
        }
        return authManager.accountRole?.displayName ?? "Member"
    }

    private var identityOnboardingSection: some View {
        VStack(spacing: 12) {
            Button { destination = .myProfiles } label: {
                OnboardingActionRow(icon: "person.crop.rectangle", title: "My profiles", detail: "Find your profile, check your claim, or update your story.")
            }.buttonStyle(.plain).accessibilityIdentifier("account-my-profiles")

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
                    .font(AcademyType.title2)
                    .foregroundStyle(authManager.isVerifiedScout ? AcademyColors.good : AcademyColors.accent)
                    .frame(width: 34)

                VStack(alignment: .leading, spacing: 4) {
                    Text("Scout Verification")
                        .font(AcademyType.headline)
                    Text(
                        authManager.isVerifiedScout
                            ? "Your professional scouting role is verified."
                            : "Apply or check your verification status."
                    )
                    .font(AcademyType.subheadline)
                    .foregroundStyle(AcademyColors.secondaryText)
                    .multilineTextAlignment(.leading)
                }

                Spacer(minLength: 6)
                Image(systemName: "chevron.right")
                    .font(AcademyType.subheadline.weight(.semibold))
                    .foregroundStyle(AcademyColors.secondaryText)
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
                                .font(AcademyType.title2)
                                .foregroundStyle(AcademyColors.accent)
                                .frame(width: 34)

                            VStack(alignment: .leading, spacing: 4) {
                                HStack(spacing: 8) {
                                    Text("Incoming Introductions")
                                        .font(AcademyType.headline)
                                    if incomingRequestsViewModel.hasLoaded,
                                       !incomingRequestsViewModel.requests.isEmpty {
                                        BadgeView(
                                            text: incomingRequestsViewModel.requests.count.formatted()
                                        )
                                    }
                                }
                                Text("Review scout introductions for your claimed player profile.")
                                    .font(AcademyType.subheadline)
                                    .foregroundStyle(AcademyColors.secondaryText)
                                    .multilineTextAlignment(.leading)
                            }

                            Spacer(minLength: 6)
                            if incomingRequestsViewModel.isLoading,
                               !incomingRequestsViewModel.hasLoaded {
                                WingLiftLoadingView().controlSize(.small)
                            } else {
                                Image(systemName: "chevron.right")
                                    .font(AcademyType.subheadline.weight(.semibold))
                                    .foregroundStyle(AcademyColors.secondaryText)
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
                            .font(AcademyType.title2)
                            .foregroundStyle(AcademyColors.accent)
                            .frame(width: 34)

                        VStack(alignment: .leading, spacing: 4) {
                            HStack(spacing: 8) {
                                Text("Sent Requests")
                                    .font(AcademyType.headline)
                                if sentRequestsViewModel.hasLoaded, !sentRequestsViewModel.requests.isEmpty {
                                    BadgeView(text: sentRequestsViewModel.requests.count.formatted())
                                }
                            }
                            Text("Track requests, accepted threads, and outcomes.")
                                .font(AcademyType.subheadline)
                                .foregroundStyle(AcademyColors.secondaryText)
                                .multilineTextAlignment(.leading)
                        }

                        Spacer(minLength: 6)
                        if sentRequestsViewModel.isLoading, !sentRequestsViewModel.hasLoaded {
                            WingLiftLoadingView().controlSize(.small)
                        } else {
                            Image(systemName: "chevron.right")
                                .font(AcademyType.subheadline.weight(.semibold))
                                .foregroundStyle(AcademyColors.secondaryText)
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
                        .font(AcademyType.title2)
                        .foregroundStyle(AcademyColors.accent)
                        .frame(width: 34)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Export my data").font(AcademyType.headline)
                        Text("Download a copy of everything we store about you")
                            .font(AcademyType.subheadline)
                            .foregroundStyle(AcademyColors.secondaryText)
                            .multilineTextAlignment(.leading)
                    }
                    Spacer(minLength: 6)
                    if exportState == .loading {
                        WingLiftLoadingView().controlSize(.small)
                    } else {
                        Image(systemName: "chevron.right")
                            .font(AcademyType.subheadline.weight(.semibold))
                            .foregroundStyle(AcademyColors.secondaryText)
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
                    .font(AcademyType.footnote)
                    .foregroundStyle(AcademyColors.danger)
                    .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 4)
                    Button("Retry") {
                        Task { await exportAccountData() }
                    }
                    .font(AcademyType.footnote.weight(.semibold))
                }
                .padding(.horizontal, 4)
            }

            Button {
                destination = .blockedUsers
            } label: {
                HStack(spacing: 13) {
                    Image(systemName: "person.crop.circle.badge.xmark")
                        .font(AcademyType.title2)
                        .foregroundStyle(AcademyColors.accent)
                        .frame(width: 34)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Blocked users").font(AcademyType.headline)
                        Text("Review people you’ve blocked or unblock them.")
                            .font(AcademyType.subheadline)
                            .foregroundStyle(AcademyColors.secondaryText)
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(AcademyType.subheadline.weight(.semibold))
                        .foregroundStyle(AcademyColors.secondaryText)
                }
                .padding(16)
                .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 17))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("account-blocked-users")

            #if DEBUG && targetEnvironment(simulator)
            if Phase2Fixtures.active && ProcessInfo.processInfo.arguments.contains("-reviewAccountSwitch") {
                Button("Switch fixture account") {
                    Task {
                        _ = try? await authManager.verifyCode(email: "second@fixture.invalid", code: "123456")
                    }
                }.accessibilityIdentifier("fixture-account-switch")
                Text(authManager.email ?? "signed-out").accessibilityIdentifier("fixture-account-identity")
            }
            #endif
            Button(role: .destructive) {
                authManager.signOut()
            } label: {
                Label("Sign Out", systemImage: "rectangle.portrait.and.arrow.right")
                    .frame(maxWidth: .infinity)
                    .frame(height: 44)
            }
            .buttonStyle(FloodlightPillStyle(variant: .outline))

            Button(role: .destructive) {
                isDeleteAccountPresented = true
            } label: {
                Label("Delete account", systemImage: "trash")
                    .frame(maxWidth: .infinity)
                    .frame(height: 44)
            }
            .buttonStyle(FloodlightPillStyle(variant: .outline))
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
                    .font(AcademyType.subheadline.weight(.semibold))
                    .foregroundStyle(AcademyColors.good)
                    .multilineTextAlignment(.center)
                    .accessibilityIdentifier("account-deletion-confirmation")
            }
            Image(systemName: "person.crop.circle.badge.checkmark")
                .font(AcademyType.ui( 62))
                .foregroundStyle(AcademyColors.accent)
            Text("Your scout account")
                .font(AcademyType.title2)
            Text("Sign in to apply for scout verification, manage introduction requests, and continue accepted conversations.")
                .font(AcademyType.subheadline)
                .foregroundStyle(AcademyColors.secondaryText)
                .multilineTextAlignment(.center)
            Button("Sign In", action: onSignInRequested)
                .buttonStyle(FloodlightPillStyle())
                .tint(AcademyColors.primaryFill)
                .frame(maxWidth: .infinity)
                .accessibilityIdentifier("account-sign-in")
        }
        .padding(24)
        .frame(maxWidth: .infinity)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10))
    }

    var legalSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Legal")
                .font(AcademyType.title3)
                .padding(.horizontal, 4)

            VStack(spacing: 0) {
                ForEach(LegalDestination.legalCases) { destination in
                    LegalSafariLink(destination: destination) {
                        HStack(spacing: 13) {
                            Image(systemName: destination.systemImage)
                                .font(AcademyType.body.weight(.semibold))
                                .foregroundStyle(AcademyColors.accent)
                                .frame(width: 28)

                            Text(destination.title)
                                .font(AcademyType.subheadline.weight(.semibold))
                                .foregroundStyle(AcademyColors.text)

                            Spacer(minLength: 6)

                            Image(systemName: "arrow.up.right.square")
                                .font(AcademyType.subheadline.weight(.semibold))
                                .foregroundStyle(AcademyColors.secondaryText)
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
                    .font(AcademyType.ui( 54))
                    .foregroundStyle(AcademyColors.danger)

                Text("Delete your account")
                    .font(AcademyType.title2)

                Text("Deletion is immediate and irreversible. Your sign-in account, profile claims, watchlist, lists, contact requests and messages, reports, and other content you submitted will be deleted or anonymized where records must be retained.")
                    .font(AcademyType.body)
                    .foregroundStyle(AcademyColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)

                Label("You will be signed out on this device.", systemImage: "key.slash")
                    .font(AcademyType.subheadline.weight(.semibold))

                if let errorMessage {
                    Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                        .font(AcademyType.footnote)
                        .foregroundStyle(AcademyColors.danger)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer()

                Button(role: .destructive) {
                    isConfirming = true
                } label: {
                    HStack {
                        Spacer()
                        if isDeleting { WingLiftLoadingView() }
                        Text(isDeleting ? "Deleting…" : "Continue to Delete")
                            .fontWeight(.semibold)
                        Spacer()
                    }
                    .frame(height: 44)
                }
                .buttonStyle(FloodlightPillStyle())
                .tint(AcademyColors.danger)
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
