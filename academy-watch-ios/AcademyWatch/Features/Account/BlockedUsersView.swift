import Combine
import SwiftUI

@MainActor
final class BlockedUsersViewModel: ObservableObject {
    @Published private(set) var users: [BlockedUser] = []
    @Published private(set) var isLoading = false
    @Published private(set) var unblockingAccountIDs: Set<Int> = []
    @Published private(set) var errorMessage: String?

    private let apiClient: any BlocksAPIClientProtocol

    init(apiClient: any BlocksAPIClientProtocol = APIClient()) {
        self.apiClient = apiClient

        #if DEBUG
        if FullCircleFixtureDestination.fromLaunchArguments(
            ProcessInfo.processInfo.arguments
        ) == .blockedUsers {
            users = [
                BlockedUser(accountId: 81, displayName: "Jordan Taylor", createdAt: "2026-08-08T10:00:00"),
                BlockedUser(accountId: 82, displayName: "Northbridge Scout", createdAt: "2026-08-07T09:00:00"),
            ]
        }
        #endif
    }

    func load() async {
        #if DEBUG
        if FullCircleFixtureDestination.fromLaunchArguments(
            ProcessInfo.processInfo.arguments
        ) == .blockedUsers { return }
        #endif

        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            users = try await apiClient.fetchBlockedUsers().blocks
        } catch is CancellationError {
            return
        } catch {
            errorMessage = ContactPrivacyMessage.blockActionMessage(for: error)
        }
    }

    func unblock(_ user: BlockedUser) async {
        guard !unblockingAccountIDs.contains(user.accountId) else { return }
        unblockingAccountIDs.insert(user.accountId)
        errorMessage = nil
        defer { unblockingAccountIDs.remove(user.accountId) }

        do {
            try await apiClient.unblockUser(accountID: user.accountId)
            users.removeAll { $0.accountId == user.accountId }
        } catch {
            errorMessage = ContactPrivacyMessage.blockActionMessage(for: error)
        }
    }
}

struct BlockedUsersView: View {
    @StateObject private var viewModel: BlockedUsersViewModel

    init(apiClient: any BlocksAPIClientProtocol = APIClient()) {
        _viewModel = StateObject(wrappedValue: BlockedUsersViewModel(apiClient: apiClient))
    }

    var body: some View {
        ZStack {
            AcademyColors.background.ignoresSafeArea()

            if viewModel.isLoading, viewModel.users.isEmpty {
                ProgressView("Loading blocked users…")
            } else if viewModel.users.isEmpty, let error = viewModel.errorMessage {
                ContentUnavailableView {
                    Label("Blocked users unavailable", systemImage: "person.crop.circle.badge.exclamationmark")
                } description: {
                    Text(error)
                } actions: {
                    Button("Try Again") { Task { await viewModel.load() } }
                        .buttonStyle(.borderedProminent)
                }
            } else if viewModel.users.isEmpty {
                ContentUnavailableView(
                    "No blocked users",
                    systemImage: "person.crop.circle.badge.checkmark",
                    description: Text("People you block from request or message screens will appear here.")
                )
            } else {
                List {
                    if let error = viewModel.errorMessage {
                        Section {
                            Label(error, systemImage: "exclamationmark.triangle.fill")
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                        }
                    }

                    Section {
                        ForEach(viewModel.users) { user in
                            HStack(spacing: 12) {
                                Image(systemName: "person.crop.circle.fill")
                                    .font(.title2)
                                    .foregroundStyle(.secondary)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(user.displayName ?? "Academy Watch user")
                                        .font(.headline)
                                    Text("New requests and messages are blocked")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Button("Unblock") {
                                    Task { await viewModel.unblock(user) }
                                }
                                .disabled(viewModel.unblockingAccountIDs.contains(user.accountId))
                                .accessibilityIdentifier("unblock-user-\(user.accountId)")
                            }
                        }
                    } footer: {
                        Text("Unblocking allows new introduction requests and messages again.")
                    }
                }
                .scrollContentBackground(.hidden)
                .refreshable { await viewModel.load() }
            }
        }
        .navigationTitle("Blocked Users")
        .navigationBarTitleDisplayMode(.inline)
        .task { await viewModel.load() }
    }
}
