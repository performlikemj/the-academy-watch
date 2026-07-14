import SwiftUI

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
                    .padding(.horizontal, 20)
                    .padding(.vertical, 28)
                }
                .scrollDismissesKeyboard(.interactively)
            }
            .navigationTitle("Sign In")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Close", systemImage: "xmark") {
                        dismiss()
                    }
                    .labelStyle(.iconOnly)
                    .accessibilityLabel("Close sign in")
                }
            }
        }
        .tint(AcademyColors.claret)
        .onAppear {
            focusedField = step == .email ? .email : .code
        }
    }

    private var header: some View {
        VStack(spacing: 12) {
            Image(systemName: "star.circle.fill")
                .font(.system(size: 54, weight: .semibold))
                .foregroundStyle(AcademyColors.claret)
                .accessibilityHidden(true)

            Text("Build your watchlist")
                .font(.title2.weight(.bold))

            Text("We’ll email you a one-time code. No password needed.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
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
                    .font(.footnote)
                    .foregroundStyle(.green)
                    .accessibilityIdentifier("signin-confirmation")
            }

            if let errorMessage {
                Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .accessibilityIdentifier("signin-error")
            }
        }
        .padding(20)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
        }
    }

    private var emailStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 7) {
                Text("EMAIL")
                    .font(.caption.weight(.bold))
                    .tracking(1)
                    .foregroundStyle(AcademyColors.claret)

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
                    .background(Color(uiColor: .tertiarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 11))
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
                    .font(.caption.weight(.bold))
                    .tracking(1)
                    .foregroundStyle(AcademyColors.claret)
                Text("Enter the 11-character code sent to \(normalizedEmail). It expires in five minutes.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            TextField("11-character code", text: $code)
                .textContentType(.oneTimeCode)
                .keyboardType(.asciiCapable)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .font(.body.monospaced())
                .focused($focusedField, equals: .code)
                .submitLabel(.go)
                .onSubmit { verifyCode() }
                .onChange(of: code) { _, newValue in
                    let filtered = newValue.unicodeScalars
                        .filter { (33 ... 126).contains(Int($0.value)) }
                        .prefix(11)
                        .map { String($0) }
                        .joined()
                    if code != filtered {
                        code = filtered
                    }
                }
                .accessibilityIdentifier("signin-code")
                .padding(.horizontal, 12)
                .frame(height: 48)
                .background(Color(uiColor: .tertiarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 11))

            primaryButton(title: "Verify & sign in", identifier: "signin-verify") {
                verifyCode()
            }
            .disabled(isLoading || code.count != 11)

            HStack {
                Button("Back") {
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
            .font(.subheadline.weight(.semibold))
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
                    ProgressView()
                        .tint(.white)
                }
                Text(title)
                    .fontWeight(.semibold)
            }
            .frame(maxWidth: .infinity)
            .frame(height: 48)
        }
        .buttonStyle(.borderedProminent)
        .accessibilityIdentifier(identifier)
    }

    private var normalizedEmail: String {
        email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    private func requestCode(isResend: Bool = false) {
        guard !isLoading, !normalizedEmail.isEmpty else { return }
        clearMessages()
        isLoading = true
        Task {
            defer { isLoading = false }
            do {
                _ = try await authManager.requestCode(email: normalizedEmail)
                step = .code
                confirmationMessage = isResend ? "A new code is on its way." : "Code sent. Check your inbox."
                focusedField = .code
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    private func verifyCode() {
        guard !isLoading, code.count == 11 else { return }
        clearMessages()
        isLoading = true
        Task {
            defer { isLoading = false }
            do {
                _ = try await authManager.verifyCode(email: normalizedEmail, code: code)
                dismiss()
            } catch {
                errorMessage = error.localizedDescription
            }
        }
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
