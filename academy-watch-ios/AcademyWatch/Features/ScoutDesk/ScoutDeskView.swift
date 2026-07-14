import Foundation
import SwiftUI

@MainActor
struct ScoutDeskView: View {
    @StateObject private var viewModel: ScoutDeskViewModel

    init() {
        _viewModel = StateObject(wrappedValue: ScoutDeskViewModel())
    }

    init(viewModel: ScoutDeskViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                AcademyColors.background.ignoresSafeArea()
                content
            }
            .navigationTitle("Scout Desk")
            .navigationBarTitleDisplayMode(.large)
        }
        .task {
            await viewModel.loadInitialIfNeeded()
        }
    }

    @ViewBuilder
    private var content: some View {
        if (!viewModel.hasAttemptedInitialLoad || viewModel.isLoadingInitial), viewModel.players.isEmpty {
            ProgressView("Scouting talent…")
                .tint(AcademyColors.claret)
        } else if let message = viewModel.errorMessage, viewModel.players.isEmpty {
            ScoutErrorView(message: message) {
                Task { await viewModel.reload() }
            }
        } else if viewModel.players.isEmpty {
            ContentUnavailableView(
                "No players found",
                systemImage: "person.3",
                description: Text("There are no prospects to show right now.")
            )
        } else {
            playerList
        }
    }

    private var playerList: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("GLOBAL TALENT")
                            .font(.caption.weight(.bold))
                            .tracking(1.2)
                            .foregroundStyle(AcademyColors.claret)
                        Text("\(viewModel.totalPlayers.formatted()) prospects ranked by goal contributions")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                .padding(.horizontal, 2)
                .padding(.bottom, 2)

                if let message = viewModel.errorMessage {
                    ScoutInlineErrorView(message: message) {
                        Task { await viewModel.reload() }
                    }
                }

                ForEach(viewModel.players, id: \.playerId) { player in
                    ScoutPlayerRow(player: player)
                        .onAppear {
                            Task {
                                await viewModel.loadNextPageIfNeeded(currentPlayer: player)
                            }
                        }
                }

                if viewModel.isLoadingNextPage {
                    ProgressView()
                        .tint(AcademyColors.claret)
                        .padding(.vertical, 16)
                } else if let message = viewModel.paginationErrorMessage {
                    VStack(spacing: 8) {
                        Text(message)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                        Button("Try loading more") {
                            Task { await viewModel.retryNextPage() }
                        }
                        .font(.footnote.weight(.semibold))
                    }
                    .padding(.vertical, 12)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
        }
        .refreshable {
            await viewModel.reload()
        }
    }
}

private struct ScoutPlayerRow: View {
    let player: ScoutPlayerSummary

    var body: some View {
        VStack(spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                playerPhoto

                VStack(alignment: .leading, spacing: 5) {
                    Text(player.playerName)
                        .font(.headline)
                        .foregroundStyle(.primary)
                        .lineLimit(1)

                    Text(metadataLine)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)

                    Label(clubLine, systemImage: "shield.fill")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)

                    HStack(spacing: 6) {
                        BadgeView(text: player.position ?? "Position TBD")
                        BadgeView(
                            text: displayStatus,
                            foregroundColor: statusColor,
                            backgroundColor: statusColor.opacity(0.12)
                        )
                    }
                }
                Spacer(minLength: 0)
            }

            Divider()

            HStack(spacing: 0) {
                StatCell(label: "Apps", spokenLabel: "Appearances", value: String(player.appearances))
                StatCell(label: "G", spokenLabel: "Goals", value: String(player.goals))
                StatCell(label: "A", spokenLabel: "Assists", value: String(player.assists))
                StatCell(label: "Mins", spokenLabel: "Minutes", value: compactMinutes)
                StatCell(label: "Rating", spokenLabel: "Rating", value: ratingText)
            }
        }
        .padding(14)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
        }
        .accessibilityElement(children: .contain)
    }

    @ViewBuilder
    private var playerPhoto: some View {
        Group {
            if let photoURL = player.photoURL {
                AsyncImage(url: photoURL, transaction: Transaction(animation: .easeInOut(duration: 0.2))) { phase in
                    switch phase {
                    case let .success(image):
                        image
                            .resizable()
                            .scaledToFill()
                    case .empty:
                        ProgressView()
                            .tint(AcademyColors.claret)
                    case .failure:
                        photoPlaceholder
                    @unknown default:
                        photoPlaceholder
                    }
                }
            } else {
                photoPlaceholder
            }
        }
        .frame(width: 60, height: 60)
        .background(Color(uiColor: .tertiarySystemFill))
        .clipShape(Circle())
        .overlay {
            Circle().stroke(AcademyColors.claret.opacity(0.18), lineWidth: 1)
        }
        .accessibilityLabel("Photo of \(player.playerName)")
    }

    private var photoPlaceholder: some View {
        Image(systemName: "person.crop.circle.fill")
            .resizable()
            .scaledToFit()
            .foregroundStyle(.tertiary)
    }

    private var metadataLine: String {
        var parts: [String] = []
        if let age = player.age {
            parts.append(String(age))
        }
        if let nationality = player.nationality, !nationality.isEmpty {
            parts.append(nationality)
        }
        return parts.isEmpty ? "Age and nationality unavailable" : parts.joined(separator: " · ")
    }

    private var clubLine: String {
        if player.status == "on_loan",
           let current = player.loanTeamName,
           let owner = player.ownerTeamName,
           current.caseInsensitiveCompare(owner) != .orderedSame {
            return "\(current) · from \(owner)"
        }

        if let current = player.loanTeamName,
           let academy = player.primaryTeamName,
           current.caseInsensitiveCompare(academy) != .orderedSame {
            return "\(current) · \(academy) academy"
        }

        return player.loanTeamName ?? player.primaryTeamName ?? "Club unavailable"
    }

    private var displayStatus: String {
        player.status
            .split(separator: "_")
            .map { $0.capitalized }
            .joined(separator: " ")
    }

    private var statusColor: Color {
        switch player.status {
        case "academy": .blue
        case "on_loan": Color(red: 0.66, green: 0.32, blue: 0.02)
        case "first_team": Color(red: 0.04, green: 0.45, blue: 0.20)
        case "sold": .purple
        case "released", "left": .secondary
        default: AcademyColors.claret
        }
    }

    private var compactMinutes: String {
        guard player.minutesPlayed >= 1_000 else { return String(player.minutesPlayed) }
        return String(format: "%.1fk", Double(player.minutesPlayed) / 1_000)
    }

    private var ratingText: String {
        player.avgRating.map { String(format: "%.1f", $0) } ?? "–"
    }
}

private struct StatCell: View {
    let label: String
    let spokenLabel: String
    let value: String

    var body: some View {
        VStack(spacing: 3) {
            Text(value)
                .font(.subheadline.weight(.semibold))
                .monospacedDigit()
                .foregroundStyle(.primary)
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(spokenLabel), \(value)")
    }
}

private struct ScoutInlineErrorView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(AcademyColors.claret)
            Text(message)
                .font(.footnote)
                .foregroundStyle(.secondary)
            Spacer(minLength: 4)
            Button("Retry", action: retry)
                .font(.footnote.weight(.semibold))
        }
        .padding(12)
        .background(AcademyColors.claretSoft, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

private struct ScoutErrorView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        ContentUnavailableView {
            Label("Scout Desk unavailable", systemImage: "wifi.exclamationmark")
        } description: {
            Text(message)
        } actions: {
            Button("Try Again", action: retry)
                .buttonStyle(.borderedProminent)
                .tint(AcademyColors.claret)
        }
    }
}
