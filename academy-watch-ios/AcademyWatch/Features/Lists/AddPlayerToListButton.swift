import SwiftUI

@MainActor
struct AddPlayerToListButton: View {
    let playerID: Int
    let playerName: String
    let onSignInRequested: () -> Void

    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var listsViewModel: FollowListsViewModel
    @State private var isListPickerPresented = false

    var body: some View {
        Button {
            if authManager.isAuthenticated {
                isListPickerPresented = true
            } else {
                onSignInRequested()
            }
        } label: {
            Label("Add to list", systemImage: "text.badge.plus")
                .font(.subheadline.weight(.semibold))
        }
        .buttonStyle(.bordered)
        .tint(AcademyColors.claret)
        .sheet(isPresented: $isListPickerPresented) {
            PlayerListPicker(
                playerID: playerID,
                playerName: playerName,
                isPresented: $isListPickerPresented
            )
        }
    }
}

@MainActor
private struct PlayerListPicker: View {
    let playerID: Int
    let playerName: String
    @Binding var isPresented: Bool

    @EnvironmentObject private var viewModel: FollowListsViewModel

    var body: some View {
        NavigationStack {
            ZStack {
                AcademyColors.background.ignoresSafeArea()
                content
            }
            .navigationTitle("Add to list")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { isPresented = false }
                }
            }
        }
        .presentationDetents([.medium, .large])
        .task {
            if viewModel.lists.isEmpty, !viewModel.isLoading {
                await viewModel.loadLists()
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if viewModel.isLoading, viewModel.lists.isEmpty {
            ProgressView("Loading lists…")
                .tint(AcademyColors.claret)
        } else if viewModel.lists.isEmpty {
            ContentUnavailableView {
                Label("No lists yet", systemImage: "list.bullet.rectangle")
            } description: {
                Text("Create your first list from the Lists tab, then add \(playerName).")
            }
            .padding(24)
        } else {
            List {
                if let message = viewModel.errorMessage {
                    Label(message, systemImage: "exclamationmark.triangle.fill")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                ForEach(viewModel.lists) { list in
                    let isAdded = list.containsPlayer(playerID)
                    Button {
                        Task {
                            if await viewModel.addPlayer(playerID, to: list.id) {
                                isPresented = false
                            }
                        }
                    } label: {
                        HStack(spacing: 12) {
                            Image(systemName: list.isDefault ? "star.square.fill" : "list.bullet.rectangle.fill")
                                .foregroundStyle(AcademyColors.claret)
                                .frame(width: 26)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(list.name)
                                    .font(.headline)
                                    .foregroundStyle(.primary)
                                Text("\(list.followCount) \(list.followCount == 1 ? "follow" : "follows")")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            if isAdded {
                                Label("Added", systemImage: "checkmark.circle.fill")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.green)
                                    .labelStyle(.titleAndIcon)
                            } else if viewModel.pendingPlayerIDs.contains(playerID) {
                                ProgressView()
                                    .controlSize(.small)
                            } else {
                                Image(systemName: "plus.circle")
                                    .foregroundStyle(AcademyColors.claret)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                    .disabled(isAdded || viewModel.pendingPlayerIDs.contains(playerID))
                }
            }
            .scrollContentBackground(.hidden)
        }
    }
}
