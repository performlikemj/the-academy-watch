import SwiftUI

struct PlayerTakedownRequestSheet: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel: PlayerTakedownRequestViewModel

    init(playerID: Int, apiClient: any PlayerTakedownAPIClientProtocol) {
        _viewModel = StateObject(
            wrappedValue: PlayerTakedownRequestViewModel(
                playerID: playerID,
                apiClient: apiClient
            )
        )
    }

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.state == .received {
                    confirmationContent
                } else {
                    requestForm
                }
            }
            .navigationTitle("Profile removal")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                        .disabled(viewModel.state == .submitting)
                }
            }
        }
        .interactiveDismissDisabled(viewModel.state == .submitting)
    }

    private var requestForm: some View {
        Form {
            Section {
                Label {
                    Text("This form is for the player shown or an authorized representative requesting removal of their profile.")
                        .fixedSize(horizontal: false, vertical: true)
                } icon: {
                    Image(systemName: "person.crop.circle.badge.minus")
                        .foregroundStyle(AcademyColors.claret)
                }
            }

            Section("Who are you?") {
                Picker("Requester", selection: $viewModel.requesterRole) {
                    ForEach(TakedownRequesterRole.allCases) { role in
                        Text(role.displayName).tag(role)
                    }
                }
                .pickerStyle(.menu)

                TextField("Contact email", text: $viewModel.contactEmail)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .accessibilityIdentifier("takedown-contact-email")
            }

            Section("Why should this profile be removed?") {
                TextEditor(text: $viewModel.statement)
                    .frame(minHeight: 120)
                    .accessibilityIdentifier("takedown-statement")
                    .onChange(of: viewModel.statement) { _, value in
                        if value.count > 2_000 {
                            viewModel.statement = String(value.prefix(2_000))
                        }
                    }
                Text("Include enough detail for us to verify that you are the player or are authorized to act for them. \(viewModel.statement.count)/2,000")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if viewModel.state == .failed {
                Section {
                    Label(
                        PlayerTakedownRequestViewModel.genericErrorMessage,
                        systemImage: "exclamationmark.triangle.fill"
                    )
                    .font(.footnote)
                    .foregroundStyle(Color(uiColor: .systemRed))
                }
            }

            Section {
                Button {
                    Task { await viewModel.submit() }
                } label: {
                    HStack {
                        Spacer()
                        if viewModel.state == .submitting {
                            ProgressView()
                        }
                        Text(submitButtonTitle)
                            .fontWeight(.semibold)
                        Spacer()
                    }
                }
                .disabled(!viewModel.canSubmit)
                .accessibilityIdentifier("submit-takedown-request")
            } footer: {
                Text("Submitting a request does not indicate whether a profile exists or what action will be taken.")
            }
        }
    }

    private var confirmationContent: some View {
        VStack(spacing: 18) {
            Image(systemName: "checkmark.shield.fill")
                .font(.system(size: 54))
                .foregroundStyle(AcademyColors.positiveGreen)
            Text(PlayerTakedownRequestViewModel.confirmationMessage)
                .font(.title3.weight(.semibold))
                .multilineTextAlignment(.center)
            Text("You may close this form now.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Button("Done") { dismiss() }
                .buttonStyle(.borderedProminent)
                .tint(AcademyColors.claretFill)
        }
        .padding(28)
    }

    private var submitButtonTitle: String {
        switch viewModel.state {
        case .submitting: return "Sending…"
        case .failed: return "Try Again"
        case .idle, .received: return "Submit Request"
        }
    }
}
