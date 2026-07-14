import SwiftUI

@MainActor
struct WatchlistStarButton: View {
    let playerID: Int
    let playerName: String
    let onSignInRequested: () -> Void
    var showsBackground = true

    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var watchlistViewModel: WatchlistViewModel

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
                    ProgressView()
                        .controlSize(.small)
                        .tint(AcademyColors.claret)
                } else {
                    Image(systemName: isWatched ? "star.fill" : "star")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(isWatched ? Color.orange : AcademyColors.claret)
                }
            }
            .frame(width: 34, height: 34)
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
    }

    private func toggleWatchlist() {
        guard authManager.isAuthenticated else {
            onSignInRequested()
            return
        }

        Task {
            await watchlistViewModel.toggleWatchlist(playerID: playerID)
        }
    }
}
