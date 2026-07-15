import SwiftUI

@MainActor
struct WatchlistView: View {
    let onSignInRequested: () -> Void

    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var viewModel: WatchlistViewModel
    @EnvironmentObject private var listsViewModel: FollowListsViewModel

    var body: some View {
        NavigationStack {
            ZStack {
                AcademyColors.background.ignoresSafeArea()
                content
            }
            .navigationTitle("Watchlist")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: Int.self) { playerID in
                PlayerDetailView(
                    playerID: playerID,
                    onSignInRequested: onSignInRequested
                )
            }
            .toolbar {
                if authManager.isAuthenticated {
                    ToolbarItem(placement: .topBarTrailing) {
                        Menu {
                            Button(role: .destructive) {
                                authManager.signOut()
                            } label: {
                                Label("Sign Out", systemImage: "rectangle.portrait.and.arrow.right")
                            }
                        } label: {
                            Image(systemName: "person.crop.circle")
                                .accessibilityLabel("Account")
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if !authManager.isAuthenticated {
            signedOutState
        } else if viewModel.isLoading, viewModel.entries.isEmpty {
            ProgressView("Loading your watchlist…")
                .tint(AcademyColors.claret)
        } else if let message = viewModel.errorMessage, viewModel.entries.isEmpty {
            errorState(message: message)
        } else if viewModel.entries.isEmpty {
            emptyState
        } else {
            watchlist
        }
    }

    private var signedOutState: some View {
        VStack(spacing: 16) {
            Image(systemName: "star.circle.fill")
                .font(.system(size: 58))
                .foregroundStyle(AcademyColors.claret)
                .accessibilityHidden(true)

            VStack(spacing: 7) {
                Text("Sign in to build your watchlist")
                    .font(.title3.weight(.bold))
                Text("Star players across the Scout Desk and keep their form, stats and availability close at hand.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            Button("Sign In", action: onSignInRequested)
                .buttonStyle(.borderedProminent)
                .tint(AcademyColors.claretFill)
                .controlSize(.large)
        }
        .padding(28)
        .frame(maxWidth: 430)
    }

    private var emptyState: some View {
        ContentUnavailableView {
            Label("No watched players", systemImage: "star")
        } description: {
            Text("Star a player from the Scout Desk or a player profile to start tracking them here.")
        }
        .padding(24)
    }

    private func errorState(message: String) -> some View {
        ContentUnavailableView {
            Label("Watchlist unavailable", systemImage: "wifi.exclamationmark")
        } description: {
            Text(message)
        } actions: {
            Button("Try Again") {
                Task { await viewModel.loadWatchlist() }
            }
            .buttonStyle(.borderedProminent)
            .tint(AcademyColors.claretFill)
        }
        .padding(24)
    }

    private var watchlist: some View {
        List {
            if let message = viewModel.errorMessage {
                Section {
                    Label(message, systemImage: "exclamationmark.triangle.fill")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }

            ForEach(viewModel.entries, id: \.playerApiId) { entry in
                Group {
                    if let player = entry.player {
                        NavigationLink(value: player.playerId) {
                            WatchlistPlayerCard(entry: entry, player: player)
                        }
                        .buttonStyle(.plain)
                    } else {
                        WatchlistUnavailablePlayerCard(entry: entry)
                    }
                }
                .listRowInsets(EdgeInsets(top: 7, leading: 16, bottom: 7, trailing: 16))
                .listRowSeparator(.hidden)
                .listRowBackground(Color.clear)
                .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                    Button(role: .destructive) {
                        Task {
                            if await viewModel.removeFromWatchlist(playerID: entry.playerApiId) {
                                await listsViewModel.synchronizeAfterWatchlistMutation()
                            }
                        }
                    } label: {
                        Label("Remove", systemImage: "trash")
                    }
                    .disabled(viewModel.pendingPlayerIDs.contains(entry.playerApiId))
                }
            }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .refreshable {
            await viewModel.loadWatchlist()
        }
    }
}

private struct WatchlistPlayerCard: View {
    let entry: WatchlistEntry
    let player: ScoutPlayerSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ScoutPlayerRow(player: player, phase: .all)

            if let note = entry.note, !note.isEmpty {
                Label(note, systemImage: "note.text")
                    .font(.caption)
                    .foregroundStyle(AcademyColors.claret)
                    .lineLimit(2)
                    .padding(.horizontal, 4)
            }
        }
    }
}

private struct WatchlistUnavailablePlayerCard: View {
    let entry: WatchlistEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("Player #\(entry.playerApiId)", systemImage: "person.crop.circle.badge.questionmark")
                .font(.headline)
            Text("This player is no longer in the active tracking feed.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            if let note = entry.note, !note.isEmpty {
                Text(note)
                    .font(.caption)
                    .foregroundStyle(AcademyColors.claret)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
        }
    }
}
