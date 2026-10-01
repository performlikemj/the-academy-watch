import SwiftUI

@MainActor
struct WatchlistStarButton: View {
    let playerID: Int
    let playerName: String
    let onSignInRequested: () -> Void
    var showsBackground = true

    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var watchlistViewModel: WatchlistViewModel
    @EnvironmentObject private var followListsViewModel: FollowListsViewModel

    private var isWatched: Bool {
        watchlistViewModel.isWatched(playerID: playerID)
    }

    private var isPending: Bool {
        watchlistViewModel.isPending(playerID: playerID)
    }

    var body: some View {
        Button(action: toggleWatchlist) {
            Group {
                if isPending {
                    CleatLoader()
                        .controlSize(.small)
                        .tint(AcademyColors.accent)
                } else {
                    Image(systemName: isWatched ? "star.fill" : "star")
                        .font(AcademyType.ui( 16, weight: .semibold))
                        .foregroundStyle(isWatched ? AcademyColors.warnText : AcademyColors.accent)
                }
            }
            .frame(width: 44, height: 44)
            .background(
                showsBackground ? AcademyColors.surface.opacity(0.96) : Color.clear,
                in: Circle()
            )
            .overlay {
                if showsBackground {
                    Circle()
                        .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
                }
            }
            .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .disabled(isPending)
        .accessibilityLabel(
            isWatched ? "Remove \(playerName) from watchlist" : "Add \(playerName) to watchlist"
        )
        .accessibilityIdentifier(isWatched ? "watchlist-remove-\(playerID)" : "watchlist-add-\(playerID)")
    }

    private func toggleWatchlist() {
        guard authManager.isAuthenticated else {
            onSignInRequested()
            return
        }

        Task {
            if await watchlistViewModel.toggleWatchlist(playerID: playerID) {
                await followListsViewModel.synchronizeAfterWatchlistMutation()
            }
        }
    }
}
