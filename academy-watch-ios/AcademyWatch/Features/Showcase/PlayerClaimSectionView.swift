import SwiftUI

struct PlayerClaimSectionView: View {
    @ObservedObject var viewModel: PlayerClaimViewModel

    let isAuthenticated: Bool
    let accountRole: AccountRole?
    let onSignInRequested: () -> Void

    @State private var attestationSheet: PlayerAttestationSheetMode?

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
        .sheet(item: $attestationSheet) { mode in
            PlayerContractAttestationSheet(viewModel: viewModel, mode: mode)
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
                VStack(alignment: .leading, spacing: 9) {
                    Text("Claim under review")
                        .font(.headline)
                    Text("We’ll show this as your profile after an Academy Watch admin approves the claim.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    compactAttestation(claim.contractAttestation, reviewLabel: "Reviewed with claim")
                }
                .accessibilityIdentifier("player-claim-pending")
            } else {
                representativeClaimContent(claim)
            }

        case .approved:
            if claim.relationshipType == "player" {
                VStack(alignment: .leading, spacing: 10) {
                    Label("Your profile", systemImage: "person.crop.circle.fill")
                        .font(.headline)
                        .foregroundStyle(AcademyColors.claret)
                    Text("This profile is linked to your \(approvedRoleLabel.lowercased()) account.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)

                    Divider()
                    ownerAttestationContent
                }
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

    @ViewBuilder
    private var ownerAttestationContent: some View {
        if let attestation = viewModel.currentOwnerAttestation {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 8) {
                    Text("PRIVATE CONTRACT ATTESTATION")
                        .font(.caption2.weight(.bold))
                        .tracking(0.85)
                        .foregroundStyle(.secondary)

                    Spacer()

                    if viewModel.currentAttestationReviewStatus == .pending {
                        BadgeView(
                            text: "Pending review",
                            foregroundColor: AcademyColors.loanAmber,
                            backgroundColor: AcademyColors.loanAmber.opacity(0.12)
                        )
                    }
                }

                Label(attestation.contractStatus.displayName, systemImage: "doc.text.magnifyingglass")
                    .font(.subheadline.weight(.semibold))

                if let clubName = clean(attestation.currentClubName) {
                    Text("Current club: \(clubName)")
                        .font(.subheadline)
                }

                Text(attestation.contractStatus.routingExplanation)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                if viewModel.isLoadingOwnerProfile {
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.small)
                        Text("Loading the moderated profile…")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                } else {
                    Button("Edit contract attestation") {
                        viewModel.clearOwnerProfileError()
                        attestationSheet = .edit(attestation)
                    }
                    .buttonStyle(.bordered)
                    .tint(AcademyColors.claret)
                    .disabled(!viewModel.canEditOwnerAttestation)
                    .accessibilityIdentifier("player-contract-attestation-edit")
                }

                if let ownerError = viewModel.ownerProfileErrorMessage {
                    Label(ownerError, systemImage: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(Color(uiColor: .systemRed))
                        .fixedSize(horizontal: false, vertical: true)
                    Button("Try loading profile again") {
                        Task { await viewModel.reloadOwnerProfile() }
                    }
                    .font(.caption.weight(.semibold))
                }

                Text("Only you and Academy Watch moderators can see this attestation. Changes are reviewed before they affect new contact routing.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("player-contract-attestation-owner")
        }
    }

    private func compactAttestation(
        _ attestation: PlayerContractAttestation,
        reviewLabel: String
    ) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 7) {
                Image(systemName: "doc.text.magnifyingglass")
                    .foregroundStyle(AcademyColors.claret)
                Text(attestation.contractStatus.displayName)
                    .font(.subheadline.weight(.semibold))
                Spacer()
                Text(reviewLabel)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            if let clubName = clean(attestation.currentClubName) {
                Text("Current club: \(clubName)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text("This attestation is not shown on your public profile.")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding(10)
        .background(AcademyColors.background.opacity(0.7), in: RoundedRectangle(cornerRadius: 11))
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
                    ? "Submit a claim and attest your current contract status to link this profile to your player account."
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
            // A new claim always starts with no selected status. The player
            // must make an explicit attestation for every submission.
            viewModel.clearClaimError()
            attestationSheet = .claim
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
        viewModel.isApprovedPlayerOwner
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

    private func clean(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              !value.isEmpty
        else { return nil }
        return value
    }
}

private enum PlayerAttestationSheetMode: Identifiable {
    case claim
    case edit(PlayerContractAttestation)

    var id: String {
        switch self {
        case .claim: "claim"
        case .edit: "edit"
        }
    }

    var initialAttestation: PlayerContractAttestation? {
        switch self {
        case .claim: nil
        case let .edit(attestation): attestation
        }
    }

    var title: String {
        switch self {
        case .claim: "Your contract status"
        case .edit: "Edit contract status"
        }
    }

    var introduction: String {
        switch self {
        case .claim:
            return "Choose the status that is true today. An Academy Watch admin reviews this with your profile claim."
        case .edit:
            return "Changes use the existing moderated profile-edit path and do not affect routing until approved."
        }
    }

    var actionTitle: String {
        switch self {
        case .claim: "Submit claim"
        case .edit: "Submit update"
        }
    }
}

private struct PlayerContractAttestationSheet: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var viewModel: PlayerClaimViewModel

    let mode: PlayerAttestationSheetMode

    @State private var selectedStatus: PlayerContractStatus?
    @State private var currentClubName: String

    init(viewModel: PlayerClaimViewModel, mode: PlayerAttestationSheetMode) {
        self.viewModel = viewModel
        self.mode = mode
        _selectedStatus = State(initialValue: mode.initialAttestation?.contractStatus)
        _currentClubName = State(initialValue: mode.initialAttestation?.currentClubName ?? "")
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(mode.introduction)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Section("Contract status") {
                    ForEach(PlayerContractStatus.allCases) { status in
                        statusChoice(status)
                    }
                }

                if selectedStatus != nil, selectedStatus != .freeAgent {
                    Section("Current club (optional)") {
                        TextField("Club name", text: $currentClubName)
                            .textInputAutocapitalization(.words)
                            .autocorrectionDisabled()
                            .accessibilityIdentifier("player-contract-current-club")

                        HStack {
                            Text("Used to help route introductions correctly.")
                            Spacer()
                            Text("\(currentClubName.count)/180")
                                .monospacedDigit()
                        }
                        .font(.caption)
                        .foregroundStyle(clubNameIsTooLong ? Color(uiColor: .systemRed) : .secondary)
                    }
                }

                if let selectedStatus {
                    Section("How requests are routed") {
                        Text(selectedStatus.routingExplanation)
                            .font(.subheadline)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                Section {
                    Label(
                        "Your attestation is visible only to you and Academy Watch moderators. It is not added to the public player profile.",
                        systemImage: "lock.shield.fill"
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }

                if let errorMessage = submissionErrorMessage {
                    Section {
                        Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                            .font(.caption)
                            .foregroundStyle(Color(uiColor: .systemRed))
                    }
                }
            }
            .navigationTitle(mode.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .disabled(isSubmitting)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(mode.actionTitle) {
                        submit()
                    }
                    .disabled(!canSubmit)
                }
            }
        }
        .interactiveDismissDisabled(isSubmitting)
        .presentationDetents([.medium, .large])
        .accessibilityIdentifier("player-contract-attestation-sheet")
    }

    private func statusChoice(_ status: PlayerContractStatus) -> some View {
        Button {
            selectedStatus = status
            if status == .freeAgent {
                currentClubName = ""
            }
        } label: {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: selectedStatus == status ? "checkmark.circle.fill" : "circle")
                    .font(.title3)
                    .foregroundStyle(selectedStatus == status ? AcademyColors.claret : Color.secondary)

                VStack(alignment: .leading, spacing: 3) {
                    Text(status.displayName)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.primary)
                    Text(status.formExplanation)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(status.displayName)
        .accessibilityValue(selectedStatus == status ? "Selected" : "Not selected")
        .accessibilityIdentifier("player-contract-status-\(status.rawValue)")
    }

    private var isSubmitting: Bool {
        switch mode {
        case .claim:
            return viewModel.isSubmitting
        case .edit:
            return viewModel.isSavingOwnerAttestation
        }
    }

    private var submissionErrorMessage: String? {
        switch mode {
        case .claim:
            return viewModel.errorMessage
        case .edit:
            return viewModel.ownerProfileErrorMessage
        }
    }

    private var clubNameIsTooLong: Bool {
        currentClubName.count > 180
    }

    private var canSubmit: Bool {
        selectedStatus != nil && !clubNameIsTooLong && !isSubmitting
    }

    private func submit() {
        guard let selectedStatus, canSubmit else { return }
        let cleanClubName = selectedStatus == .freeAgent ? nil : cleanedClubName
        let attestation = PlayerContractAttestation(
            contractStatus: selectedStatus,
            currentClubName: cleanClubName,
            clubProgramId: preservedProgramID(for: cleanClubName, status: selectedStatus)
        )

        Task {
            let didSubmit: Bool
            switch mode {
            case .claim:
                didSubmit = await viewModel.submitThisIsMe(attestation: attestation)
            case .edit:
                didSubmit = await viewModel.updateOwnerAttestation(attestation)
            }
            if didSubmit {
                dismiss()
            }
        }
    }

    private var cleanedClubName: String? {
        let cleaned = currentClubName.trimmingCharacters(in: .whitespacesAndNewlines)
        return cleaned.isEmpty ? nil : cleaned
    }

    private func preservedProgramID(
        for cleanClubName: String?,
        status: PlayerContractStatus
    ) -> Int? {
        guard status != .freeAgent,
              let initial = mode.initialAttestation,
              let initialName = initial.currentClubName?.trimmingCharacters(in: .whitespacesAndNewlines),
              let cleanClubName,
              initialName.caseInsensitiveCompare(cleanClubName) == .orderedSame
        else { return nil }
        return initial.clubProgramId
    }
}
