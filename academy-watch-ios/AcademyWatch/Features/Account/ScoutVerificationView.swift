import SwiftUI

@MainActor
struct ScoutVerificationView: View {
    @StateObject private var viewModel: ScoutVerificationViewModel
    @EnvironmentObject private var authManager: AuthManager
    @FocusState private var focusedField: Field?

    init(apiClient: any ScoutVerificationAPIClientProtocol = APIClient()) {
        _viewModel = StateObject(
            wrappedValue: ScoutVerificationViewModel(apiClient: apiClient)
        )
    }

    init(viewModel: ScoutVerificationViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
    }

    var body: some View {
        ZStack {
            AcademyColors.background.ignoresSafeArea()

            if viewModel.isLoading, !viewModel.hasLoaded {
                ProgressView("Loading verification status…")
                    .tint(AcademyColors.claret)
            } else if !viewModel.hasLoaded, let errorMessage = viewModel.errorMessage {
                initialErrorState(errorMessage)
            } else {
                content
            }
        }
        .navigationTitle("Scout Verification")
        .navigationBarTitleDisplayMode(.inline)
        .tint(AcademyColors.claret)
        .task {
            await viewModel.loadIfNeeded()
            syncVerifiedScoutState()
        }
        .onChange(of: viewModel.verification?.status) { _, _ in
            syncVerifiedScoutState()
        }
        .onDisappear {
            viewModel.cancel()
        }
    }

    private func syncVerifiedScoutState() {
        guard viewModel.hasLoaded else { return }
        authManager.updateScoutVerification(viewModel.verification?.status == .approved)
    }

    private var content: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                screenHeader

                if let verification = viewModel.verification {
                    statusCard(verification)
                } else {
                    firstApplicationCard
                }

                if viewModel.shouldShowApplicationForm {
                    applicationForm
                }

                if let errorMessage = viewModel.errorMessage {
                    errorBanner(errorMessage)
                }
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 20)
            .frame(maxWidth: 640)
            .frame(maxWidth: .infinity)
        }
        .scrollDismissesKeyboard(.interactively)
        .refreshable {
            await viewModel.reload()
        }
    }

    private var screenHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 5) {
                Label("SCOUT TRUST", systemImage: "checkmark.shield.fill")
                    .font(.caption.weight(.bold))
                    .tracking(1.05)
                    .foregroundStyle(AcademyColors.claret)

                Text("Verify your scouting role")
                    .font(.title2.weight(.bold))

                Text("Verified scouts can request introductions to claimed player profiles.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 4)

            if viewModel.isFixturePreview {
                BadgeView(
                    text: "Fixture preview",
                    foregroundColor: AcademyColors.loanAmber,
                    backgroundColor: AcademyColors.loanAmber.opacity(0.12)
                )
            }
        }
    }

    private var firstApplicationCard: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "person.crop.circle.badge.checkmark")
                .font(.title2)
                .foregroundStyle(AcademyColors.claret)
                .frame(width: 34)

            VStack(alignment: .leading, spacing: 5) {
                Text("Apply for verification")
                    .font(.headline)
                Text("Share your professional role and at least one public link that helps us confirm it. Applications are reviewed by The Academy Watch team.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .cardStyle()
        .accessibilityElement(children: .combine)
    }

    private func statusCard(_ verification: ScoutVerification) -> some View {
        let presentation = statusPresentation(for: verification.status)

        return VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: presentation.icon)
                    .font(.title2)
                    .foregroundStyle(presentation.color)
                    .frame(width: 34)

                VStack(alignment: .leading, spacing: 5) {
                    HStack(spacing: 8) {
                        Text(presentation.title)
                            .font(.headline)
                        BadgeView(
                            text: presentation.badge,
                            foregroundColor: presentation.color,
                            backgroundColor: presentation.color.opacity(0.12)
                        )
                    }

                    Text(presentation.detail)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            if verification.status == .rejected,
               let notes = clean(verification.reviewNotes) {
                Divider()
                VStack(alignment: .leading, spacing: 5) {
                    Label("REVIEW NOTES", systemImage: "text.bubble.fill")
                        .font(.caption.weight(.bold))
                        .tracking(0.8)
                        .foregroundStyle(presentation.color)
                    Text(notes)
                        .font(.subheadline)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            if verification.status == .revoked,
               let reason = clean(verification.revocationReason) {
                Divider()
                VStack(alignment: .leading, spacing: 5) {
                    Text("REASON")
                        .font(.caption.weight(.bold))
                        .tracking(0.8)
                        .foregroundStyle(.secondary)
                    Text(reason)
                        .font(.subheadline)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .cardStyle(borderColor: presentation.color.opacity(0.35))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("scout-verification-status-\(verification.status.rawValue)")
    }

    private var applicationForm: some View {
        VStack(alignment: .leading, spacing: 20) {
            VStack(alignment: .leading, spacing: 5) {
                Text(viewModel.verification?.status == .rejected ? "Update your application" : "Your application")
                    .font(.headline)
                Text(viewModel.verification?.status == .rejected
                    ? "Address the review notes and resubmit when your evidence is ready."
                    : "All fields are required. Your evidence links must be public https URLs.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            boundedTextField(
                label: "FULL NAME",
                placeholder: "Alex Morgan",
                text: $viewModel.fullName,
                limit: ScoutVerificationViewModel.fullNameLimit,
                field: .fullName,
                identifier: "scout-verification-full-name",
                contentType: .name
            )

            boundedTextField(
                label: "ORGANIZATION",
                placeholder: "Club or scouting organization",
                text: $viewModel.organization,
                limit: ScoutVerificationViewModel.organizationLimit,
                field: .organization,
                identifier: "scout-verification-organization",
                contentType: .organizationName
            )

            boundedTextField(
                label: "ROLE OR TITLE",
                placeholder: "Academy scout",
                text: $viewModel.roleTitle,
                limit: ScoutVerificationViewModel.roleTitleLimit,
                field: .roleTitle,
                identifier: "scout-verification-role-title"
            )

            statementField
            evidenceFields

            if let validationMessage = viewModel.validationMessage,
               !allFieldsAreUntouched {
                Label(validationMessage, systemImage: "info.circle.fill")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("scout-verification-validation")
            }

            Button {
                focusedField = nil
                Task { await viewModel.submit() }
            } label: {
                HStack(spacing: 9) {
                    if viewModel.isSubmitting {
                        ProgressView()
                            .tint(AcademyColors.claretOnFill)
                    }
                    Text(viewModel.verification?.status == .rejected ? "Resubmit for review" : "Submit for review")
                        .fontWeight(.semibold)
                }
                .frame(maxWidth: .infinity)
                .frame(height: 48)
            }
            .buttonStyle(.borderedProminent)
            .tint(AcademyColors.claretFill)
            .disabled(!viewModel.isFormValid || viewModel.isSubmitting || viewModel.isLoading)
            .accessibilityIdentifier("scout-verification-submit")
        }
        .cardStyle()
    }

    private var statementField: some View {
        VStack(alignment: .leading, spacing: 7) {
            fieldLabel("SCOUTING STATEMENT", count: viewModel.statement.count, limit: ScoutVerificationViewModel.statementLimit)

            ZStack(alignment: .topLeading) {
                if viewModel.statement.isEmpty {
                    Text("Describe your scouting work and how you use The Academy Watch…")
                        .font(.body)
                        .foregroundStyle(Color(uiColor: .placeholderText))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 12)
                        .allowsHitTesting(false)
                }

                TextEditor(text: $viewModel.statement)
                    .focused($focusedField, equals: .statement)
                    .frame(minHeight: 128)
                    .scrollContentBackground(.hidden)
                    .padding(.horizontal, 4)
                    .background(Color.clear)
                    .onChange(of: viewModel.statement) { _, value in
                        if value.count > ScoutVerificationViewModel.statementLimit {
                            viewModel.statement = String(value.prefix(ScoutVerificationViewModel.statementLimit))
                        }
                    }
                    .accessibilityIdentifier("scout-verification-statement")
            }
            .background(Color(uiColor: .tertiarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 11))
        }
    }

    private var evidenceFields: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("EVIDENCE LINKS")
                        .font(.caption.weight(.bold))
                        .tracking(0.9)
                        .foregroundStyle(AcademyColors.claret)
                    Text("Professional profile, club directory, or other public proof")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                Text("\(viewModel.evidenceURLs.count)/\(ScoutVerificationViewModel.maximumEvidenceURLs)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }

            ForEach(viewModel.evidenceURLs.indices, id: \.self) { index in
                HStack(spacing: 8) {
                    TextField(
                        "https://example.com/profile",
                        text: evidenceBinding(at: index)
                    )
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .textContentType(.URL)
                    .focused($focusedField, equals: .evidence(index))
                    .padding(.horizontal, 12)
                    .frame(height: 48)
                    .background(Color(uiColor: .tertiarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 11))
                    .accessibilityLabel("Evidence URL \(index + 1)")
                    .accessibilityIdentifier("scout-verification-evidence-\(index)")

                    if viewModel.evidenceURLs.count > 1 {
                        Button(role: .destructive) {
                            viewModel.removeEvidenceURL(at: index)
                        } label: {
                            Image(systemName: "minus.circle.fill")
                                .font(.title3)
                        }
                        .accessibilityLabel("Remove evidence URL \(index + 1)")
                    }
                }
            }

            if viewModel.evidenceURLs.count < ScoutVerificationViewModel.maximumEvidenceURLs {
                Button {
                    viewModel.addEvidenceURL()
                } label: {
                    Label("Add another link", systemImage: "plus.circle.fill")
                        .font(.subheadline.weight(.semibold))
                }
                .accessibilityIdentifier("scout-verification-add-evidence")
            }
        }
    }

    private func boundedTextField(
        label: String,
        placeholder: String,
        text: Binding<String>,
        limit: Int,
        field: Field,
        identifier: String,
        contentType: UITextContentType? = nil
    ) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            fieldLabel(label, count: text.wrappedValue.count, limit: limit)
            TextField(placeholder, text: text)
                .textContentType(contentType)
                .focused($focusedField, equals: field)
                .padding(.horizontal, 12)
                .frame(height: 48)
                .background(Color(uiColor: .tertiarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 11))
                .onChange(of: text.wrappedValue) { _, value in
                    if value.count > limit {
                        text.wrappedValue = String(value.prefix(limit))
                    }
                }
                .accessibilityIdentifier(identifier)
        }
    }

    private func fieldLabel(_ title: String, count: Int, limit: Int) -> some View {
        HStack {
            Text(title)
                .font(.caption.weight(.bold))
                .tracking(0.9)
                .foregroundStyle(AcademyColors.claret)
            Spacer()
            Text("\(count)/\(limit)")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
        }
    }

    private func evidenceBinding(at index: Int) -> Binding<String> {
        Binding(
            get: {
                guard viewModel.evidenceURLs.indices.contains(index) else { return "" }
                return viewModel.evidenceURLs[index]
            },
            set: { value in
                viewModel.updateEvidenceURL(at: index, value: value)
            }
        )
    }

    private func initialErrorState(_ message: String) -> some View {
        ContentUnavailableView {
            Label("Verification unavailable", systemImage: "wifi.exclamationmark")
        } description: {
            Text(message)
        } actions: {
            Button("Try Again") {
                Task { await viewModel.reload() }
            }
            .buttonStyle(.borderedProminent)
            .tint(AcademyColors.claretFill)
        }
        .padding(24)
    }

    private func errorBanner(_ message: String) -> some View {
        Label(message, systemImage: "exclamationmark.triangle.fill")
            .font(.footnote)
            .foregroundStyle(Color(uiColor: .systemRed))
            .fixedSize(horizontal: false, vertical: true)
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(uiColor: .systemRed).opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
            .accessibilityIdentifier("scout-verification-error")
    }

    private var allFieldsAreUntouched: Bool {
        viewModel.fullName.isEmpty
            && viewModel.organization.isEmpty
            && viewModel.roleTitle.isEmpty
            && viewModel.statement.isEmpty
            && viewModel.evidenceURLs.allSatisfy(\.isEmpty)
    }

    private func clean(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private func statusPresentation(for status: ScoutVerificationStatus) -> StatusPresentation {
        switch status {
        case .pending:
            return StatusPresentation(
                title: "Application under review",
                detail: "Your evidence is with our review team. You’ll see your updated status here when a decision is made.",
                badge: "Pending",
                icon: "clock.fill",
                color: AcademyColors.loanAmber
            )
        case .approved:
            return StatusPresentation(
                title: "Verified scout",
                detail: "Your professional scouting role is verified. You can request introductions to players with claimed profiles.",
                badge: "Approved",
                icon: "checkmark.seal.fill",
                color: AcademyColors.positiveGreen
            )
        case .rejected:
            return StatusPresentation(
                title: "Changes needed",
                detail: "We couldn’t verify this application yet. Review the notes below, update your evidence, and resubmit.",
                badge: "Not approved",
                icon: "exclamationmark.bubble.fill",
                color: AcademyColors.loanAmber
            )
        case .revoked:
            return StatusPresentation(
                title: "Verification revoked",
                detail: "This verification is no longer active. Contact The Academy Watch if you believe this is a mistake.",
                badge: "Inactive",
                icon: "shield.slash.fill",
                color: .secondary
            )
        }
    }
}

private extension ScoutVerificationView {
    enum Field: Hashable {
        case fullName
        case organization
        case roleTitle
        case statement
        case evidence(Int)
    }

    struct StatusPresentation {
        let title: String
        let detail: String
        let badge: String
        let icon: String
        let color: Color
    }
}

private extension View {
    func cardStyle(borderColor: Color = AcademyColors.separator.opacity(0.35)) -> some View {
        padding(16)
            .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 17, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 17, style: .continuous)
                    .stroke(borderColor, lineWidth: 0.75)
            }
    }
}
