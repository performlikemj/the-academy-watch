import Foundation
import SwiftUI

@MainActor
struct ScoutDeskView: View {
    @StateObject private var viewModel: ScoutDeskViewModel
    @State private var navigationPath: [Int]

    init(initialPhase: ScoutPhase = .all, initialPlayerID: Int? = nil) {
        _viewModel = StateObject(wrappedValue: ScoutDeskViewModel(initialPhase: initialPhase))
        _navigationPath = State(initialValue: initialPlayerID.map { [$0] } ?? [])
    }

    init(viewModel: ScoutDeskViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
        _navigationPath = State(initialValue: [])
    }

    var body: some View {
        NavigationStack(path: $navigationPath) {
            ZStack {
                AcademyColors.background.ignoresSafeArea()

                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 14) {
                        phaseSwitcher

                        if let description = viewModel.selectedPhase.description {
                            Text(description + " Missing detailed coverage is shown as —.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .padding(.horizontal, 16)
                        }

                        leaderboardsSection
                        filtersSection
                        resultsHeader
                        resultsContent
                    }
                    .padding(.vertical, 12)
                }
                .refreshable {
                    await viewModel.reload()
                }
            }
            .navigationTitle("Scout Desk")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: Int.self) { playerID in
                PlayerDetailView(playerID: playerID)
            }
        }
        .task(id: navigationPath.isEmpty) {
            guard navigationPath.isEmpty else { return }
            await viewModel.loadInitialIfNeeded()
        }
    }

    private var phaseSwitcher: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(ScoutPhase.allCases) { phase in
                    let isSelected = viewModel.selectedPhase == phase
                    Button {
                        Task { await viewModel.selectPhase(phase) }
                    } label: {
                        Text(phase.label)
                            .font(.caption.weight(.semibold))
                            .padding(.horizontal, 14)
                            .padding(.vertical, 9)
                            .foregroundStyle(isSelected ? Color.white : Color.primary)
                            .background(
                                isSelected ? AcademyColors.claret : AcademyColors.surface,
                                in: Capsule()
                            )
                            .overlay {
                                if !isSelected {
                                    Capsule()
                                        .stroke(AcademyColors.separator.opacity(0.4), lineWidth: 0.5)
                                }
                            }
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("\(phase.label) view")
                    .accessibilityAddTraits(isSelected ? .isSelected : [])
                    .accessibilityIdentifier("phase-\(phase.rawValue)")
                }
            }
            .padding(.horizontal, 16)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Phase of play")
    }

    private var leaderboardsSection: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                Label("LEADERBOARDS", systemImage: "chart.bar.fill")
                    .font(.caption.weight(.bold))
                    .tracking(1.1)
                    .foregroundStyle(AcademyColors.claret)

                Spacer()

                if viewModel.isLoadingLeaderboards {
                    ProgressView()
                        .controlSize(.small)
                        .tint(AcademyColors.claret)
                }
            }
            .padding(.horizontal, 16)

            if let message = viewModel.leaderboardsErrorMessage {
                ScoutInlineErrorView(message: message) {
                    Task { await viewModel.retryLeaderboards() }
                }
                .padding(.horizontal, 16)
            }

            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(spacing: 12) {
                    ForEach(viewModel.selectedPhase.leaderboards) { board in
                        ScoutLeaderboardCard(
                            definition: board,
                            entries: viewModel.leaderboards[board.key] ?? [],
                            isLoading: viewModel.isLoadingLeaderboards
                        )
                    }
                }
                .padding(.horizontal, 16)
            }
        }
    }

    private var filtersSection: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                Text("FILTERS")
                    .font(.caption.weight(.bold))
                    .tracking(1.1)
                    .foregroundStyle(AcademyColors.claret)
                Spacer()
                Text(viewModel.isLoadingInitial ? "Loading…" : "\(viewModel.totalPlayers.formatted()) players")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 7) {
                    ForEach(ScoutAgePreset.allCases) { preset in
                        let isSelected = viewModel.selectedAgePreset == preset
                        Button {
                            Task { await viewModel.selectAgePreset(preset) }
                        } label: {
                            Text(preset.label)
                                .font(.caption.weight(.semibold))
                                .padding(.horizontal, 12)
                                .padding(.vertical, 7)
                                .foregroundStyle(isSelected ? Color.white : Color.primary)
                                .background(
                                    isSelected ? AcademyColors.claret : Color(uiColor: .tertiarySystemFill),
                                    in: Capsule()
                                )
                        }
                        .buttonStyle(.plain)
                        .accessibilityAddTraits(isSelected ? .isSelected : [])
                    }
                }
            }

            HStack(spacing: 9) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField("Search players by name…", text: searchBinding)
                    .textInputAutocapitalization(.words)
                    .autocorrectionDisabled()
                    .submitLabel(.search)
                    .accessibilityLabel("Search players")
                if !viewModel.searchText.isEmpty {
                    Button {
                        viewModel.setSearchText("")
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Clear search")
                }
            }
            .padding(.horizontal, 12)
            .frame(height: 42)
            .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 11, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
            }

            HStack(spacing: 9) {
                statusMenu
                sortMenu
            }
        }
        .padding(.horizontal, 16)
    }

    private var searchBinding: Binding<String> {
        Binding(
            get: { viewModel.searchText },
            set: { viewModel.setSearchText($0) }
        )
    }

    private var statusMenu: some View {
        Menu {
            ForEach(ScoutStatusFilter.allCases) { status in
                Button {
                    Task { await viewModel.selectStatus(status) }
                } label: {
                    if status == viewModel.selectedStatus {
                        Label(status.label, systemImage: "checkmark")
                    } else {
                        Text(status.label)
                    }
                }
            }
        } label: {
            FilterMenuLabel(
                iconName: "line.3.horizontal.decrease.circle",
                value: viewModel.selectedStatus.label
            )
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Status, \(viewModel.selectedStatus.label)")
    }

    private var sortMenu: some View {
        Menu {
            ForEach(viewModel.selectedPhase.sortOptions) { option in
                Button {
                    Task { await viewModel.selectSort(option) }
                } label: {
                    if option.key == viewModel.selectedSortKey {
                        Label(option.label, systemImage: "checkmark")
                    } else {
                        Text(option.label)
                    }
                }
            }
        } label: {
            FilterMenuLabel(iconName: "arrow.up.arrow.down", value: viewModel.selectedSortLabel)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Sort by \(viewModel.selectedSortLabel)")
    }

    private var resultsHeader: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 2) {
                Text("GLOBAL TALENT")
                    .font(.caption.weight(.bold))
                    .tracking(1.1)
                    .foregroundStyle(AcademyColors.claret)
                Text("Ranked by \(viewModel.selectedSortLabel.lowercased())")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if viewModel.selectedSortOrder == .ascending {
                Label("Low to high", systemImage: "arrow.up")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 16)
    }

    @ViewBuilder
    private var resultsContent: some View {
        if viewModel.isLoadingInitial, viewModel.players.isEmpty {
            HStack {
                Spacer()
                ProgressView("Scouting talent…")
                    .tint(AcademyColors.claret)
                    .padding(.vertical, 28)
                Spacer()
            }
        } else if let message = viewModel.errorMessage, viewModel.players.isEmpty {
            ScoutErrorView(message: message) {
                Task { await viewModel.reload() }
            }
            .padding(.horizontal, 16)
        } else if viewModel.players.isEmpty {
            ContentUnavailableView(
                "No players found",
                systemImage: "person.3",
                description: Text("Try a different name, age band or status.")
            )
            .padding(.horizontal, 16)
        } else {
            if let message = viewModel.errorMessage {
                ScoutInlineErrorView(message: message) {
                    Task { await viewModel.reload() }
                }
                .padding(.horizontal, 16)
            }

            ForEach(viewModel.players, id: \.playerId) { player in
                NavigationLink(value: player.playerId) {
                    ScoutPlayerRow(player: player, phase: viewModel.selectedPhase)
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 16)
                .accessibilityHint("Opens player detail")
                    .onAppear {
                        Task {
                            await viewModel.loadNextPageIfNeeded(currentPlayer: player)
                        }
                    }
            }

            if viewModel.isLoadingNextPage {
                HStack {
                    Spacer()
                    ProgressView()
                        .tint(AcademyColors.claret)
                        .padding(.vertical, 16)
                    Spacer()
                }
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
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
            }
        }
    }
}

private struct FilterMenuLabel: View {
    let iconName: String
    let value: String

    var body: some View {
        HStack(spacing: 7) {
            Image(systemName: iconName)
                .foregroundStyle(AcademyColors.claret)
            Text(value)
                .lineLimit(1)
            Spacer(minLength: 2)
            Image(systemName: "chevron.down")
                .font(.caption2.weight(.bold))
                .foregroundStyle(.secondary)
        }
        .font(.caption.weight(.semibold))
        .padding(.horizontal, 11)
        .frame(maxWidth: .infinity, minHeight: 42)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 11, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
        }
    }
}

private struct ScoutLeaderboardCard: View {
    let definition: ScoutLeaderboardDefinition
    let entries: [ScoutPlayerSummary]
    let isLoading: Bool

    private var topEntries: [ScoutPlayerSummary] {
        Array(entries.prefix(3))
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 7) {
                Image(systemName: definition.iconName)
                    .foregroundStyle(AcademyColors.claret)
                Text(definition.title.uppercased())
                    .font(.caption2.weight(.bold))
                    .tracking(0.7)
                    .lineLimit(1)
                Spacer()
            }
            .padding(.horizontal, 12)
            .frame(height: 36)
            .background(Color(uiColor: .tertiarySystemGroupedBackground))

            Divider()

            if isLoading, entries.isEmpty {
                VStack(spacing: 0) {
                    ForEach(0 ..< 3, id: \.self) { index in
                        HStack(spacing: 9) {
                            Circle()
                                .fill(Color(uiColor: .tertiarySystemFill))
                                .frame(width: 24, height: 24)
                            RoundedRectangle(cornerRadius: 4)
                                .fill(Color(uiColor: .tertiarySystemFill))
                                .frame(width: 120, height: 11)
                            Spacer()
                            RoundedRectangle(cornerRadius: 4)
                                .fill(Color(uiColor: .tertiarySystemFill))
                                .frame(width: 34, height: 18)
                        }
                        .padding(.horizontal, 12)
                        .frame(height: 43)
                        if index < 2 { Divider().padding(.leading, 45) }
                    }
                }
                .accessibilityLabel("Loading \(definition.title)")
            } else if topEntries.isEmpty {
                Text("No data yet")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 129)
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(topEntries.enumerated()), id: \.element.playerId) { index, player in
                        NavigationLink(value: player.playerId) {
                            HStack(spacing: 9) {
                                RankChip(rank: index + 1)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(player.playerName)
                                        .font(.caption.weight(.semibold))
                                        .lineLimit(1)
                                    Text(player.loanTeamName ?? player.primaryTeamName ?? "Club unavailable")
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                }
                                Spacer(minLength: 5)
                                VStack(alignment: .trailing, spacing: 0) {
                                    Text(player.leaderboardValue(for: definition.metric))
                                        .font(.caption.weight(.bold))
                                        .foregroundStyle(AcademyColors.claret)
                                        .monospacedDigit()
                                    Text(definition.suffix.uppercased())
                                        .font(.system(size: 8, weight: .medium))
                                        .foregroundStyle(.secondary)
                                }
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityHint("Opens player detail")
                        .padding(.horizontal, 12)
                        .frame(height: 43)
                        if index < topEntries.count - 1 {
                            Divider().padding(.leading, 45)
                        }
                    }

                    if topEntries.count < 3 {
                        Spacer(minLength: CGFloat(3 - topEntries.count) * 43)
                    }
                }
            }
        }
        .frame(width: 286, height: 166, alignment: .top)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
        }
    }
}

private struct RankChip: View {
    let rank: Int

    var body: some View {
        Text(String(rank))
            .font(.caption2.weight(.bold))
            .foregroundStyle(foregroundColor)
            .frame(width: 24, height: 24)
            .background(backgroundColor, in: Circle())
            .overlay {
                if rank > 1 {
                    Circle().stroke(AcademyColors.separator.opacity(0.45), lineWidth: 0.5)
                }
            }
            .accessibilityLabel("Rank \(rank)")
    }

    private var foregroundColor: Color {
        rank == 1 ? .white : .primary
    }

    private var backgroundColor: Color {
        switch rank {
        case 1: AcademyColors.claret
        case 2: Color(red: 0.94, green: 0.80, blue: 0.36).opacity(0.45)
        default: Color(uiColor: .tertiarySystemFill)
        }
    }
}

private struct ScoutPlayerRow: View {
    let player: ScoutPlayerSummary
    let phase: ScoutPhase

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
                ForEach(Array(phase.compactStats.enumerated()), id: \.offset) { _, stat in
                    StatCell(
                        label: stat.label,
                        spokenLabel: stat.spokenLabel,
                        value: player.displayValue(for: stat)
                    )
                }
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
                .lineLimit(1)
                .minimumScaleFactor(0.72)
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.72)
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
