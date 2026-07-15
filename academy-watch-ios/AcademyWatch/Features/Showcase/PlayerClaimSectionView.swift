import SwiftUI

struct PlayerClaimSectionView: View {
    @ObservedObject var viewModel: PlayerClaimViewModel

    let isAuthenticated: Bool
    let accountRole: AccountRole?
    let onSignInRequested: () -> Void

    @State private var isConfirmationPresented = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionHeader
            content

            if let errorMessage = viewModel.errorMessage {
                Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(Color(uiColor: .systemRed))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(14)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 16))
        .overlay {
            RoundedRectangle(cornerRadius: 16)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.75)
        }
        .confirmationDialog(
            "Claim this player profile?",
            isPresented: $isConfirmationPresented,
            titleVisibility: .visible
        ) {
            Button("Submit player claim") {
                Task { await viewModel.submitThisIsMe() }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("The Academy Watch will review the claim before linking this profile to your player account.")
        }
    }

    private var sectionHeader: some View {
        HStack(spacing: 8) {
            Label(
                isApprovedPlayerClaim ? "YOUR PROFILE" : "PROFILE CLAIM",
                systemImage: isApprovedPlayerClaim
                    ? "person.crop.circle.badge.checkmark"
                    : "person.crop.circle.badge.questionmark"
            )
            .font(.caption.weight(.bold))
            .tracking(1.05)
            .foregroundStyle(AcademyColors.claret)

            Spacer()

            if let claim = viewModel.claim {
                BadgeView(
                    text: badgeText(for: claim.status),
                    foregroundColor: badgeColor(for: claim.status),
                    backgroundColor: badgeColor(for: claim.status).opacity(0.12)
                )
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if isAuthenticated, viewModel.isLoading, !viewModel.hasLoaded {
            HStack(spacing: 10) {
                ProgressView()
                    .tint(AcademyColors.claret)
                Text("Checking your claim status…")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        } else if let claim = viewModel.claim {
            claimContent(claim)
        } else if isAuthenticated, viewModel.errorMessage != nil, viewModel.hasLoaded {
            Button("Try again") {
                Task { await viewModel.load(isAuthenticated: true) }
            }
            .buttonStyle(.bordered)
            .tint(AcademyColors.claret)
        } else {
            claimCallToAction
        }
    }

    @ViewBuilder
    private func claimContent(_ claim: PlayerProfileClaim) -> some View {
        switch claim.status {
        case .pending:
            if claim.relationshipType == "player" {
                VStack(alignment: .leading, spacing: 5) {
                    Text("Claim under review")
                        .font(.headline)
                    Text("We’ll show this as your profile after an Academy Watch admin approves the claim.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .accessibilityIdentifier("player-claim-pending")
            } else {
                representativeClaimContent(claim)
            }

        case .approved:
            if claim.relationshipType == "player" {
                VStack(alignment: .leading, spacing: 7) {
                    Label("Your profile", systemImage: "person.crop.circle.fill")
                        .font(.headline)
                        .foregroundStyle(AcademyColors.claret)
                    Text("This profile is linked to your \(approvedRoleLabel.lowercased()) account.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("player-own-profile")
            } else {
                representativeClaimContent(claim)
            }

        case .rejected, .revoked:
            if claim.relationshipType == "player" {
                VStack(alignment: .leading, spacing: 9) {
                    Text("This claim is not active. You can submit it for another review.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    submitButton(title: "Resubmit claim")
                }
            } else {
                representativeClaimContent(claim)
            }
        }
    }

    private func representativeClaimContent(_ claim: PlayerProfileClaim) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(representativeTitle(for: claim.status))
                .font(.headline)
            Text(
                "Your \(relationshipLabel(claim.relationshipType).lowercased()) claim does not identify you as the player."
            )
            .font(.subheadline)
            .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("player-representative-claim")
    }

    private var claimCallToAction: some View {
        VStack(alignment: .leading, spacing: 9) {
            Text("Are you this player?")
                .font(.headline)
            Text(
                isAuthenticated
                    ? "Submit a claim to link this profile to your player account."
                    : "Sign in, then submit a claim to link this profile to your player account."
            )
            .font(.subheadline)
            .foregroundStyle(.secondary)

            if isAuthenticated {
                submitButton(title: "This is me")
            } else {
                Button("This is me", action: onSignInRequested)
                    .buttonStyle(.borderedProminent)
                    .tint(AcademyColors.claretFill)
                    .accessibilityHint("Opens sign in before submitting a player claim")
                    .accessibilityIdentifier("player-claim-this-is-me")
            }
        }
    }

    private func submitButton(title: String) -> some View {
        Button {
            isConfirmationPresented = true
        } label: {
            if viewModel.isSubmitting {
                HStack(spacing: 8) {
                    ProgressView().tint(AcademyColors.claretOnFill)
                    Text("Submitting…")
                }
            } else {
                Text(title)
            }
        }
        .buttonStyle(.borderedProminent)
        .tint(AcademyColors.claretFill)
        .disabled(viewModel.isSubmitting || viewModel.isLoading)
        .accessibilityIdentifier("player-claim-this-is-me")
    }

    private var isApprovedPlayerClaim: Bool {
        viewModel.claim?.status == .approved && viewModel.claim?.relationshipType == "player"
    }

    private var approvedRoleLabel: String {
        guard accountRole == .player else { return AccountRole.player.displayName }
        return accountRole?.displayName ?? AccountRole.player.displayName
    }

    private func badgeText(for status: PlayerProfileClaimStatus) -> String {
        switch status {
        case .pending:
            return "Pending"
        case .approved:
            return viewModel.claim?.relationshipType == "player" ? approvedRoleLabel : "Approved"
        case .rejected:
            return "Not approved"
        case .revoked:
            return "Inactive"
        }
    }

    private func representativeTitle(for status: PlayerProfileClaimStatus) -> String {
        switch status {
        case .pending:
            return "Representative claim under review"
        case .approved:
            return "Approved profile representative"
        case .rejected, .revoked:
            return "Representative claim inactive"
        }
    }

    private func relationshipLabel(_ value: String) -> String {
        switch value {
        case "agent":
            return "Agent"
        case "guardian":
            return "Guardian"
        case "club_official":
            return "Club official"
        default:
            return "Representative"
        }
    }

    private func badgeColor(for status: PlayerProfileClaimStatus) -> Color {
        switch status {
        case .pending:
            return AcademyColors.loanAmber
        case .approved:
            return AcademyColors.positiveGreen
        case .rejected, .revoked:
            return .secondary
        }
    }
}
