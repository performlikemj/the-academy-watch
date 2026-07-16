import SwiftUI

enum AccountDestination: String, Hashable, Identifiable {
    case verification
    case sentRequests
    case incomingRequests

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

    var body: some View {
        NavigationStack {
            debugOrAccountContent
                .navigationDestination(item: $destination) { destination in
                    switch destination {
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
        case .inbox:
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
            if let request = sentRequestsViewModel.requests.first(where: { $0.status == .accepted }) {
                ContactThreadView(
                    contactRequest: request,
                    apiClient: apiClient,
                    availability: contactAvailability
                )
            } else {
                ContentUnavailableView("Fixture unavailable", systemImage: "exclamationmark.triangle")
            }
        case .messageReport:
            if let request = sentRequestsViewModel.requests.first(where: { $0.status == .accepted }) {
                ContactThreadView(
                    contactRequest: request,
                    apiClient: apiClient,
                    availability: contactAvailability,
                    viewerRole: .player
                )
            } else {
                ContentUnavailableView("Fixture unavailable", systemImage: "exclamationmark.triangle")
            }
        case .introduction, .watchingYou, nil:
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
                    if authManager.isAuthenticated {
                        signedInHeader
                        verificationSection
                        contactSection
                        signOutSection
                    } else {
                        signedOutContent
                    }
                }
                .padding(.horizontal, 18)
                .padding(.vertical, 22)
            }
        }
        .navigationTitle("Account")
        .navigationBarTitleDisplayMode(.inline)
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

            HStack(spacing: 7) {
                if let role = authManager.accountRole {
                    BadgeView(text: role.displayName)
                }
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

    private var signOutSection: some View {
        Button(role: .destructive) {
            authManager.signOut()
        } label: {
            Label("Sign Out", systemImage: "rectangle.portrait.and.arrow.right")
                .frame(maxWidth: .infinity)
                .frame(height: 44)
        }
        .buttonStyle(.bordered)
    }

    private var signedOutContent: some View {
        VStack(spacing: 18) {
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
}
