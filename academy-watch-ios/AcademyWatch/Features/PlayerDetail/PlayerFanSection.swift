import SwiftUI

/// Drives the compact fan row on PlayerDetail. A 404 (minor, suppressed, or
/// unknown subject) means "no fan surface": the row simply never renders.
@MainActor
final class PlayerFanViewModel: ObservableObject {
    let playerID: Int

    @Published private(set) var summary: PlayerFanSummary?
    @Published private(set) var isPending = false
    @Published private(set) var actionErrorMessage: String?
    @Published private(set) var hasLoaded = false

    private let apiClient: any PlayerFanAPIClientProtocol
    private var loadRevision = 0

    init(
        playerID: Int,
        apiClient: any PlayerFanAPIClientProtocol = APIClient()
    ) {
        self.playerID = playerID
        self.apiClient = apiClient
    }

    func loadIfNeeded() async {
        guard !hasLoaded else { return }
        await refresh()
    }

    func refresh() async {
        loadRevision += 1
        let revision = loadRevision
        #if DEBUG
        // Evidence fixture: the CI sandbox has no network, so the signed-out
        // fan row is captured with a fixed preview value instead of live data.
        if FullCircleFixtureDestination.fromLaunchArguments(
            ProcessInfo.processInfo.arguments
        ) == .fanRow {
            summary = PlayerFanSummary(fans: 12, following: nil)
            hasLoaded = true
            return
        }
        #endif
        do {
            let response = try await apiClient.fetchFollowerCount(playerID: playerID)
            guard revision == loadRevision, !Task.isCancelled else { return }
            summary = PlayerFanSummary(response: response)
        } catch {
            // Count reads are decorative: any failure (including the neutral
            // 404 for non-public subjects) keeps the row hidden, never an error.
            guard revision == loadRevision, !Task.isCancelled else { return }
            summary = nil
        }
        hasLoaded = true
    }

    /// Optimistic follow/unfollow with rollback on failure. Signed-out callers
    /// are routed to sign-in instead.
    func toggleFollow(isAuthenticated: Bool, onSignInRequested: @escaping () -> Void) async {
        guard let summary else { return }
        guard isAuthenticated else {
            onSignInRequested()
            return
        }
        guard !isPending else { return }

        isPending = true
        actionErrorMessage = nil
        defer { isPending = false }

        if summary.following == true {
            let rollback = summary
            self.summary = PlayerFanSummary(fans: max(0, summary.fans - 1), following: false)
            do {
                // The unfollow body carries no fan count; keep the optimistic
                // count (it only decremented) and trust the response's flag.
                let response = try await apiClient.unfollowPlayer(playerID: playerID)
                self.summary = PlayerFanSummary(
                    fans: max(0, rollback.fans - 1),
                    following: response.following
                )
            } catch {
                self.summary = rollback
                actionErrorMessage = Self.actionMessage(for: error, fallback: "Could not unfollow. Try again.")
            }
        } else {
            let rollback = summary
            self.summary = PlayerFanSummary(fans: summary.fans + 1, following: true)
            do {
                let response = try await apiClient.followPlayer(playerID: playerID)
                self.summary = PlayerFanSummary(fans: response.fans, following: response.following)
            } catch {
                self.summary = rollback
                actionErrorMessage = Self.actionMessage(for: error, fallback: "Could not follow. Try again.")
            }
        }
    }

    func clearActionError() {
        actionErrorMessage = nil
    }

    nonisolated static func actionMessage(for error: Error, fallback: String) -> String {
        (error as? LocalizedError)?.errorDescription ?? fallback
    }
}

/// Compact "N fans" + follow toggle row. Renders nothing while the count is
/// unknown or the subject is non-public.
@MainActor
struct PlayerFanSectionView: View {
    @ObservedObject var viewModel: PlayerFanViewModel
    let isAuthenticated: Bool
    let onSignInRequested: () -> Void

    var body: some View {
        if let summary = viewModel.summary {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 12) {
                    Label {
                        Text("\(summary.fans) \(summary.fans == 1 ? "fan" : "fans")")
                            .font(.subheadline.weight(.semibold))
                            .monospacedDigit()
                    } icon: {
                        Image(systemName: "person.2.fill")
                            .foregroundStyle(AcademyColors.claret)
                    }
                    .accessibilityLabel("\(summary.fans) \(summary.fans == 1 ? "fan" : "fans")")

                    Spacer(minLength: 8)

                    if isAuthenticated {
                        followButton(isFollowing: summary.following == true)
                    } else {
                        Button("Sign in to follow", action: onSignInRequested)
                            .font(.subheadline.weight(.semibold))
                            .buttonStyle(.bordered)
                            .tint(AcademyColors.claret)
                            .accessibilityIdentifier("player-fan-sign-in")
                    }
                }

                if let message = viewModel.actionErrorMessage {
                    Label(message, systemImage: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(Color(uiColor: .systemRed))
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 16))
            .overlay {
                RoundedRectangle(cornerRadius: 16)
                    .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.75)
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("player-fan-row")
        }
    }

    private func followButton(isFollowing: Bool) -> some View {
        Button {
            Task {
                await viewModel.toggleFollow(isAuthenticated: isAuthenticated, onSignInRequested: onSignInRequested)
            }
        } label: {
            HStack(spacing: 6) {
                if viewModel.isPending {
                    ProgressView()
                        .controlSize(.small)
                        .tint(isFollowing ? AcademyColors.claret : AcademyColors.claretOnFill)
                }
                Text(isFollowing ? "Following" : "Follow")
                if isFollowing {
                    Image(systemName: "checkmark")
                }
            }
            .font(.subheadline.weight(.semibold))
        }
        .buttonStyle(.borderedProminent)
        .tint(isFollowing ? AcademyColors.claretSoft : AcademyColors.claretFill)
        .foregroundStyle(isFollowing ? AcademyColors.claret : AcademyColors.claretOnFill)
        .disabled(viewModel.isPending)
        .accessibilityIdentifier(isFollowing ? "player-fan-unfollow" : "player-fan-follow")
        .accessibilityLabel(isFollowing ? "Following, tap to unfollow" : "Follow this player")
    }
}
