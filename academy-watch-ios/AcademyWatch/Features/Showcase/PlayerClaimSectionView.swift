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
                    .font(AcademyType.caption)
                    .foregroundStyle(AcademyColors.danger)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(14)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10))
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.75)
        }
        .sheet(item: $attestationSheet) { mode in
            PlayerContractAttestationSheet(viewModel: viewModel, mode: mode)
        }
        .task {
            #if DEBUG
            if isAuthenticated,
               FullCircleFixtureDestination.fromLaunchArguments(
                   ProcessInfo.processInfo.arguments
               ) == .claimGate {
                attestationSheet = .claim
            }
            #endif
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
            .font(AcademyType.caption.weight(.medium))
            .tracking(1.05)
            .foregroundStyle(AcademyColors.accent)

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
                    .tint(AcademyColors.accent)
                Text("Checking your claim status…")
                    .font(AcademyType.subheadline)
                    .foregroundStyle(AcademyColors.secondaryText)
            }
        } else if let claim = viewModel.claim {
            claimContent(claim)
        } else if isAuthenticated, viewModel.errorMessage != nil, viewModel.hasLoaded {
            Button("Try again") {
                Task { await viewModel.load(isAuthenticated: true) }
            }
            .buttonStyle(FloodlightPillStyle(variant: .outline))
            .tint(AcademyColors.accent)
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
                        .font(AcademyType.headline)
                    Text("We’ll show this as your profile after an Academy Watch admin approves the claim.")
                        .font(AcademyType.subheadline)
                        .foregroundStyle(AcademyColors.secondaryText)
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
                        .font(AcademyType.headline)
                        .foregroundStyle(AcademyColors.accent)
                    Text("This profile is linked to your \(approvedRoleLabel.lowercased()) account.")
                        .font(AcademyType.subheadline)
                        .foregroundStyle(AcademyColors.secondaryText)

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
                        .font(AcademyType.subheadline)
                        .foregroundStyle(AcademyColors.secondaryText)
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
                        .font(AcademyType.caption2.weight(.medium))
                        .tracking(0.85)
                        .foregroundStyle(AcademyColors.secondaryText)

                    Spacer()

                    if viewModel.currentAttestationReviewStatus == .pending {
                        BadgeView(
                            text: "Pending review",
                            foregroundColor: AcademyColors.warnText,
                            backgroundColor: AcademyColors.warnText.opacity(0.12)
                        )
                    }
                }

                Label(attestation.contractStatus.displayName, systemImage: "doc.text.magnifyingglass")
                    .font(AcademyType.subheadline.weight(.semibold))

                if let clubName = clean(attestation.currentClubName) {
                    Text("Current club: \(clubName)")
                        .font(AcademyType.subheadline)
                }

                Text(attestation.contractStatus.routingExplanation)
                    .font(AcademyType.caption)
                    .foregroundStyle(AcademyColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)

                if viewModel.isLoadingOwnerProfile {
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.small)
                        Text("Loading the moderated profile…")
                            .font(AcademyType.caption)
                            .foregroundStyle(AcademyColors.secondaryText)
                    }
                } else {
                    Button("Edit contract attestation") {
                        viewModel.clearOwnerProfileError()
                        attestationSheet = .edit(attestation)
                    }
                    .buttonStyle(FloodlightPillStyle(variant: .outline))
                    .tint(AcademyColors.accent)
                    .disabled(!viewModel.canEditOwnerAttestation)
                    .accessibilityIdentifier("player-contract-attestation-edit")
                }

                if let ownerError = viewModel.ownerProfileErrorMessage {
                    Label(ownerError, systemImage: "exclamationmark.triangle.fill")
                        .font(AcademyType.caption)
                        .foregroundStyle(AcademyColors.danger)
                        .fixedSize(horizontal: false, vertical: true)
                    Button("Try loading profile again") {
                        Task { await viewModel.reloadOwnerProfile() }
                    }
                    .font(AcademyType.caption.weight(.medium))
                }

                Text("Only you and Academy Watch moderators can see this attestation. Changes are reviewed before they affect new contact routing.")
                    .font(AcademyType.caption2)
                    .foregroundStyle(AcademyColors.secondaryText)
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
                    .foregroundStyle(AcademyColors.accent)
                Text(attestation.contractStatus.displayName)
                    .font(AcademyType.subheadline.weight(.semibold))
                Spacer()
                Text(reviewLabel)
                    .font(AcademyType.caption2)
                    .foregroundStyle(AcademyColors.secondaryText)
            }
            if let clubName = clean(attestation.currentClubName) {
                Text("Current club: \(clubName)")
                    .font(AcademyType.caption)
                    .foregroundStyle(AcademyColors.secondaryText)
            }
            Text("This attestation is not shown on your public profile.")
                .font(AcademyType.caption2)
                .foregroundStyle(AcademyColors.secondaryText)
        }
        .padding(10)
        .background(AcademyColors.background.opacity(0.7), in: RoundedRectangle(cornerRadius: 10))
    }

    private func representativeClaimContent(_ claim: PlayerProfileClaim) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(representativeTitle(for: claim.status))
                .font(AcademyType.headline)
            Text(
                "Your \(relationshipLabel(claim.relationshipType).lowercased()) claim does not identify you as the player."
            )
            .font(AcademyType.subheadline)
            .foregroundStyle(AcademyColors.secondaryText)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("player-representative-claim")
    }

    private var claimCallToAction: some View {
        VStack(alignment: .leading, spacing: 9) {
            Text("Are you this player?")
                .font(AcademyType.headline)
            Text(
                isAuthenticated
                    ? "Submit a claim and attest your current contract status to link this profile to your player account."
                    : "Sign in, then submit a claim to link this profile to your player account."
            )
            .font(AcademyType.subheadline)
            .foregroundStyle(AcademyColors.secondaryText)

            if isAuthenticated {
                submitButton(title: "This is me")
            } else {
                Button("This is me", action: onSignInRequested)
                    .buttonStyle(FloodlightPillStyle())
                    .tint(AcademyColors.primaryFill)
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
                    ProgressView().tint(AcademyColors.onPrimary)
                    Text("Submitting…")
                }
            } else {
                Text(title)
            }
        }
        .buttonStyle(FloodlightPillStyle())
        .tint(AcademyColors.primaryFill)
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
            return AcademyColors.warnText
        case .approved:
            return AcademyColors.good
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
        case .claim: "Claim This Profile"
        case .edit: "Edit contract status"
        }
    }

    var introduction: String {
        switch self {
        case .claim:
            return "Player claims are for adults aged 18 or older. The player must have a known date of birth before a claim can be submitted. Choose the contract status that is true today; an Academy Watch admin reviews it with your claim."
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
                    if case .claim = mode {
                        Label(mode.introduction, systemImage: "18.circle.fill")
                            .font(AcademyType.subheadline.weight(.semibold))
                            .foregroundStyle(AcademyColors.accent)
                            .fixedSize(horizontal: false, vertical: true)
                            .accessibilityIdentifier("player-claim-adults-only-copy")

                        LegalSafariLink(destination: .communityRules) {
                            Label("Community Rules", systemImage: "arrow.up.right.square")
                                .font(AcademyType.footnote.weight(.semibold))
                                .foregroundStyle(AcademyColors.accent)
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("player-claim-community-rules")
                    } else {
                        Text(mode.introduction)
                            .font(AcademyType.subheadline)
                            .foregroundStyle(AcademyColors.secondaryText)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }.listRowBackground(AcademyColors.background)

                Section("Contract status") {
                    ForEach(PlayerContractStatus.allCases) { status in
                        statusChoice(status)
                    }
                }.listRowBackground(AcademyColors.background)

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
                        .font(AcademyType.caption)
                        .foregroundStyle(clubNameIsTooLong ? AcademyColors.danger : AcademyColors.secondaryText)
                    }.listRowBackground(AcademyColors.background)
                }

                if let selectedStatus {
                    Section("How requests are routed") {
                        Text(selectedStatus.routingExplanation)
                            .font(AcademyType.subheadline)
                            .fixedSize(horizontal: false, vertical: true)
                    }.listRowBackground(AcademyColors.background)
                }

                Section {
                    Label(
                        "Your attestation is visible only to you and Academy Watch moderators. It is not added to the public player profile.",
                        systemImage: "lock.shield.fill"
                    )
                    .font(AcademyType.caption)
                    .foregroundStyle(AcademyColors.secondaryText)
                }.listRowBackground(AcademyColors.background)

                if let errorMessage = submissionErrorMessage {
                    Section {
                        Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                            .font(AcademyType.caption)
                            .foregroundStyle(AcademyColors.danger)
                    }.listRowBackground(AcademyColors.background)
                }
            }
        .scrollContentBackground(.hidden)
        .background(AcademyColors.background)
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
                    .font(AcademyType.title3)
                    .foregroundStyle(selectedStatus == status ? AcademyColors.accent : AcademyColors.secondaryText)

                VStack(alignment: .leading, spacing: 3) {
                    Text(status.displayName)
                        .font(AcademyType.subheadline.weight(.semibold))
                        .foregroundStyle(AcademyColors.text)
                    Text(status.formExplanation)
                        .font(AcademyType.caption)
                        .foregroundStyle(AcademyColors.secondaryText)
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
