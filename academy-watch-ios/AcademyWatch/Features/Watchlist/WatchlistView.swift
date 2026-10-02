import SwiftUI

@MainActor
struct WatchlistView: View {
    let onSignInRequested: () -> Void
    let onVerificationRequested: () -> Void

    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var viewModel: WatchlistViewModel
    @EnvironmentObject private var listsViewModel: FollowListsViewModel
    private let playerDetailAPIClient: APIClient

    init(
        playerDetailAPIClient: APIClient = APIClient(),
        onSignInRequested: @escaping () -> Void,
        onVerificationRequested: @escaping () -> Void = {}
    ) {
        self.playerDetailAPIClient = playerDetailAPIClient
        self.onSignInRequested = onSignInRequested
        self.onVerificationRequested = onVerificationRequested
    }

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
                    apiClient: playerDetailAPIClient,
                    onSignInRequested: onSignInRequested,
                    onVerificationRequested: onVerificationRequested
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
            WingLiftLoadingView("Loading your watchlist…")
                .tint(AcademyColors.accent)
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
                .font(AcademyType.ui( 58))
                .foregroundStyle(AcademyColors.accent)
                .accessibilityHidden(true)

            VStack(spacing: 7) {
                Text("Sign in to build your watchlist")
                    .font(AcademyType.title3)
                Text("Star players across the Scout Desk and keep their form, stats and availability close at hand.")
                    .font(AcademyType.subheadline)
                    .foregroundStyle(AcademyColors.secondaryText)
                    .multilineTextAlignment(.center)
            }

            Button("Sign In", action: onSignInRequested)
                .buttonStyle(FloodlightPillStyle())
                .tint(AcademyColors.primaryFill)
                .controlSize(.large)
        }
        .padding(28)
        .frame(maxWidth: 430)
    }

    private var emptyState: some View {
        FloodlightEmptyState(title: "No watched players", systemImage: "star", description: "Star a player from the Scout Desk or a player profile to start tracking them here.")
        .padding(24)
    }

    private func errorState(message: String) -> some View {
        ContentUnavailableView {
            Label("Watchlist unavailable", systemImage: "wifi.exclamationmark")
                .font(AcademyType.title2)
                .foregroundStyle(AcademyColors.text)
        } description: {
            Text(message)
        } actions: {
            Button("Try Again") {
                Task { await viewModel.loadWatchlist() }
            }
            .buttonStyle(FloodlightPillStyle())
            .tint(AcademyColors.primaryFill)
        }
        .padding(24)
    }

    private var watchlist: some View {
        List {
            if let message = viewModel.errorMessage {
                Section {
                    Label(message, systemImage: "exclamationmark.triangle.fill")
                        .font(AcademyType.footnote)
                        .foregroundStyle(AcademyColors.secondaryText)
                }.listRowBackground(AcademyColors.background)
            }

            ForEach(viewModel.entries, id: \.playerApiId) { entry in
                Group {
                    if let player = entry.player {
                        NavigationLink(value: player.playerId) {
                            WatchlistPlayerCard(
                                entry: entry,
                                player: player,
                                season: viewModel.resolvedSeason
                            )
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("watchlist-player-\(entry.playerApiId)")
                    } else {
                        WatchlistUnavailablePlayerCard(entry: entry)
                    }
                }
                .listRowInsets(EdgeInsets(top: 7, leading: 16, bottom: 7, trailing: 16))
                .listRowSeparator(.visible)
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
                    .accessibilityIdentifier("watchlist-swipe-remove-\(entry.playerApiId)")
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
    let season: Int?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ScoutPlayerRow(player: player, phase: .all)

            if let season {
                Label(SeasonLabelFormatter.label(for: season), systemImage: "calendar")
                    .font(AcademyType.caption2.weight(.medium))
                    .foregroundStyle(AcademyColors.secondaryText)
                    .padding(.horizontal, 4)
            }

            if let note = entry.note, !note.isEmpty {
                Label(note, systemImage: "note.text")
                    .font(AcademyType.caption)
                    .foregroundStyle(AcademyColors.accent)
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
                .font(AcademyType.headline)
            Text("This player is no longer in the active tracking feed.")
                .font(AcademyType.subheadline)
                .foregroundStyle(AcademyColors.secondaryText)
            if let note = entry.note, !note.isEmpty {
                Text(note)
                    .font(AcademyType.caption)
                    .foregroundStyle(AcademyColors.accent)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
        }
    }
}
