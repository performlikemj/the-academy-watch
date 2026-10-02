import SwiftUI

enum SignInCodeInput {
    static let maximumLength = 64

    static func acceptedValue(_ value: String) -> String {
        String(value.filter { !$0.isWhitespace }.prefix(maximumLength))
    }

    static func submissionValue(_ value: String) -> String? {
        let acceptedValue = acceptedValue(value)
        guard !acceptedValue.isEmpty else {
            return nil
        }
        return acceptedValue
    }
}

@MainActor
struct SignInView: View {
    @ObservedObject private var authManager: AuthManager
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focusedField: Field?

    @State private var step = Step.email
    @State private var email = ""
    @State private var code = ""
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var confirmationMessage: String?
    @State private var authenticationTask: Task<Void, Never>?
    @State private var authenticationGeneration: UInt = 0

    init(authManager: AuthManager) {
        self.authManager = authManager
    }

    var body: some View {
        NavigationStack {
            ZStack {
                AcademyColors.background.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 24) {
                        header
                        signInCard
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 28)
                }.background(AcademyColors.background)
                .scrollDismissesKeyboard(.interactively)
            }
            .navigationTitle("Sign In")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Close", systemImage: "xmark") {
                        cancelAuthenticationAttempt()
                        dismiss()
                    }
                    .labelStyle(.iconOnly)
                    .accessibilityLabel("Close sign in")
                }
            }
        }
        .tint(AcademyColors.accent)
        .onAppear {
            focusedField = step == .email ? .email : .code
        }
        .onDisappear {
            cancelAuthenticationAttempt()
        }
    }

    private var header: some View {
        VStack(spacing: 12) {
            Image(systemName: "star.circle.fill")
                .font(AcademyType.ui( 54, weight: .semibold))
                .foregroundStyle(AcademyColors.accent)
                .accessibilityHidden(true)

            Text("Build your watchlist")
                .font(AcademyType.title2)

            Text("We’ll email you a one-time code. No password needed.")
                .font(AcademyType.subheadline)
                .foregroundStyle(AcademyColors.secondaryText)
                .multilineTextAlignment(.center)
        }
    }

    private var signInCard: some View {
        VStack(alignment: .leading, spacing: 18) {
            if step == .email {
                emailStep
            } else {
                codeStep
            }

            if let confirmationMessage {
                Label(confirmationMessage, systemImage: "checkmark.circle.fill")
                    .font(AcademyType.footnote)
                    .foregroundStyle(AcademyColors.good)
                    .accessibilityIdentifier("signin-confirmation")
            }

            if let errorMessage {
                Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                    .font(AcademyType.footnote)
                    .foregroundStyle(AcademyColors.danger)
                    .accessibilityIdentifier("signin-error")
            }
        }
        .padding(20)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
        }
    }

    private var emailStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 7) {
                Text("EMAIL")
                    .font(AcademyType.caption.weight(.medium))
                    .tracking(1)
                    .foregroundStyle(AcademyColors.accent)

                TextField("you@example.com", text: $email)
                    .textContentType(.emailAddress)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .focused($focusedField, equals: .email)
                    .submitLabel(.continue)
                    .onSubmit { requestCode() }
                    .accessibilityIdentifier("signin-email")
                    .padding(.horizontal, 12)
                    .frame(height: 48)
                    .background(AcademyColors.elevatedSurface, in: RoundedRectangle(cornerRadius: 10))
            }

            primaryButton(title: "Send login code", identifier: "signin-send-code") {
                requestCode()
            }
            .disabled(isLoading || normalizedEmail.isEmpty)
        }
    }

    private var codeStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 5) {
                Text("CHECK YOUR EMAIL")
                    .font(AcademyType.caption.weight(.medium))
                    .tracking(1)
                    .foregroundStyle(AcademyColors.accent)
                Text("Enter the code we emailed to \(normalizedEmail). It expires in five minutes.")
                    .font(AcademyType.subheadline)
                    .foregroundStyle(AcademyColors.secondaryText)
            }

            TextField("Sign-in code", text: $code)
                .textContentType(.oneTimeCode)
                .keyboardType(.asciiCapable)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .font(AcademyType.body.monospaced())
                .focused($focusedField, equals: .code)
                .submitLabel(.go)
                .onSubmit { verifyCode() }
                .onChange(of: code) { _, newValue in
                    let acceptedValue = SignInCodeInput.acceptedValue(newValue)
                    if code != acceptedValue {
                        code = acceptedValue
                    }
                }
                .accessibilityIdentifier("signin-code")
                .padding(.horizontal, 12)
                .frame(height: 48)
                .background(AcademyColors.elevatedSurface, in: RoundedRectangle(cornerRadius: 10))

            primaryButton(title: "Verify & sign in", identifier: "signin-verify") {
                verifyCode()
            }
            .disabled(isLoading || SignInCodeInput.submissionValue(code) == nil)

            HStack {
                Button("Back") {
                    cancelAuthenticationAttempt()
                    step = .email
                    code = ""
                    clearMessages()
                    focusedField = .email
                }

                Spacer()

                Button("Resend code") {
                    requestCode(isResend: true)
                }
                .disabled(isLoading)
            }
            .font(AcademyType.subheadline.weight(.semibold))
        }
    }

    private func primaryButton(
        title: String,
        identifier: String,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 9) {
                if isLoading {
                    WingLiftLoadingView()
                        .tint(AcademyColors.onPrimary)
                }
                Text(title)
                    .fontWeight(.semibold)
            }
            .frame(maxWidth: .infinity)
            .frame(height: 48)
        }
        .buttonStyle(FloodlightPillStyle())
        .tint(AcademyColors.primaryFill)
        .accessibilityIdentifier(identifier)
    }

    private var normalizedEmail: String {
        email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    private func requestCode(isResend: Bool = false) {
        guard !isLoading, !normalizedEmail.isEmpty else { return }
        clearMessages()
        isLoading = true
        authenticationGeneration &+= 1
        let attemptGeneration = authenticationGeneration
        authenticationTask = Task { @MainActor in
            defer { finishAuthenticationAttempt(generation: attemptGeneration) }
            do {
                _ = try await authManager.requestCode(email: normalizedEmail)
                guard isCurrentAuthenticationAttempt(attemptGeneration) else { return }
                step = .code
                confirmationMessage = isResend ? "A new code is on its way." : "Code sent. Check your inbox."
                focusedField = .code
            } catch is CancellationError {
                return
            } catch {
                guard isCurrentAuthenticationAttempt(attemptGeneration) else { return }
                errorMessage = error.localizedDescription
            }
        }
    }

    private func verifyCode() {
        guard !isLoading, let submittedCode = SignInCodeInput.submissionValue(code) else { return }
        clearMessages()
        isLoading = true
        authenticationGeneration &+= 1
        let attemptGeneration = authenticationGeneration
        authenticationTask = Task { @MainActor in
            defer { finishAuthenticationAttempt(generation: attemptGeneration) }
            do {
                _ = try await authManager.verifyCode(email: normalizedEmail, code: submittedCode)
                guard isCurrentAuthenticationAttempt(attemptGeneration) else { return }
                dismiss()
            } catch is CancellationError {
                return
            } catch {
                guard isCurrentAuthenticationAttempt(attemptGeneration) else { return }
                errorMessage = error.localizedDescription
            }
        }
    }

    private func cancelAuthenticationAttempt() {
        authenticationGeneration &+= 1
        authenticationTask?.cancel()
        authenticationTask = nil
        isLoading = false
        authManager.cancelVerificationAttempts()
    }

    private func isCurrentAuthenticationAttempt(_ generation: UInt) -> Bool {
        generation == authenticationGeneration && !Task.isCancelled
    }

    private func finishAuthenticationAttempt(generation: UInt) {
        guard generation == authenticationGeneration else { return }
        authenticationTask = nil
        isLoading = false
    }

    private func clearMessages() {
        errorMessage = nil
        confirmationMessage = nil
    }
}

private extension SignInView {
    enum Step {
        case email
        case code
    }

    enum Field {
        case email
        case code
    }
}
