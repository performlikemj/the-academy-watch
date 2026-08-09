import SwiftUI

struct BlockUserButton: View {
    let accountID: Int
    let displayName: String?
    let apiClient: any BlocksAPIClientProtocol

    @State private var isConfirming = false
    @State private var isBlocking = false
    @State private var isBlocked = false
    @State private var errorMessage: String?

    init(
        accountID: Int,
        displayName: String?,
        apiClient: any BlocksAPIClientProtocol = APIClient()
    ) {
        self.accountID = accountID
        self.displayName = displayName
        self.apiClient = apiClient
    }

    var body: some View {
        Button(role: .destructive) {
            isConfirming = true
        } label: {
            Label(isBlocked ? "Blocked" : "Block user", systemImage: "person.crop.circle.badge.xmark")
        }
        .disabled(isBlocking || isBlocked)
        .accessibilityIdentifier("block-user-\(accountID)")
        .confirmationDialog(
            "Block this user?",
            isPresented: $isConfirming,
            titleVisibility: .visible
        ) {
            Button("Block user", role: .destructive) {
                Task { await block() }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("You won’t be able to exchange new requests or messages. You can unblock them later in Account.")
        }
        .alert("Unable to Block User", isPresented: Binding(
            get: { errorMessage != nil },
            set: { if !$0 { errorMessage = nil } }
        )) {
            Button("Try Again") { isConfirming = true }
            Button("Cancel", role: .cancel) { errorMessage = nil }
        } message: {
            Text(errorMessage ?? ContactPrivacyMessage.blockingUnavailable)
        }
    }

    private func block() async {
        guard !isBlocking else { return }
        isBlocking = true
        defer { isBlocking = false }
        do {
            try await apiClient.blockUser(accountID: accountID)
            isBlocked = true
        } catch {
            errorMessage = ContactPrivacyMessage.blockActionMessage(for: error)
        }
    }
}
