import SwiftUI

@MainActor
struct AddPlayerToListButton: View {
    let playerID: Int
    let playerName: String
    let allowsWatchlist: Bool
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
                allowsWatchlist: allowsWatchlist,
                isPresented: $isListPickerPresented
            )
        }
    }
}

@MainActor
private struct PlayerListPicker: View {
    let playerID: Int
    let playerName: String
    let allowsWatchlist: Bool
    @Binding var isPresented: Bool

    @EnvironmentObject private var viewModel: FollowListsViewModel
    @EnvironmentObject private var watchlistViewModel: WatchlistViewModel

    private var availableLists: [FollowList] {
        viewModel.lists.filter { allowsWatchlist || !$0.isDefault }
    }

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
        } else if availableLists.isEmpty {
            ContentUnavailableView {
                Label("No lists available", systemImage: "list.bullet.rectangle")
            } description: {
                Text("Create a named list from the Lists tab, then add \(playerName).")
            }
            .padding(24)
        } else {
            List {
                if let message = viewModel.errorMessage {
                    Label(message, systemImage: "exclamationmark.triangle.fill")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                ForEach(availableLists) { list in
                    let isAdded = list.isDefault
                        ? watchlistViewModel.isWatched(playerID: playerID) || list.containsPlayer(playerID)
                        : list.containsPlayer(playerID)
                    let isPending = list.isDefault
                        ? watchlistViewModel.isPending(playerID: playerID)
                        : viewModel.pendingPlayerIDs.contains(playerID)
                    Button {
                        Task {
                            let didAdd: Bool
                            if list.isDefault {
                                didAdd = await watchlistViewModel.addToWatchlist(playerID: playerID)
                                if didAdd {
                                    await viewModel.synchronizeAfterWatchlistMutation()
                                }
                            } else {
                                didAdd = await viewModel.addPlayer(playerID, to: list.id)
                            }
                            if didAdd {
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
                            } else if isPending {
                                ProgressView()
                                    .controlSize(.small)
                            } else {
                                Image(systemName: "plus.circle")
                                    .foregroundStyle(AcademyColors.claret)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                    .disabled(isAdded || isPending)
                }
            }
            .scrollContentBackground(.hidden)
        }
    }
}
