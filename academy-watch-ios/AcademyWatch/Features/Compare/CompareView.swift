import SwiftUI

@MainActor
struct CompareView: View {
    @StateObject private var viewModel: CompareViewModel
    @Environment(\.dismiss) private var dismiss

    private static let labelColumnWidth: CGFloat = 112
    private static let playerColumnWidth: CGFloat = 126

    init(
        playerIDs: [Int],
        apiClient: any CompareAPIClientProtocol = APIClient()
    ) {
        _viewModel = StateObject(
            wrappedValue: CompareViewModel(
                playerIDs: playerIDs,
                apiClient: apiClient
            )
        )
    }

    var body: some View {
        ZStack {
            AcademyColors.background.ignoresSafeArea()
            content
        }
        .navigationTitle("Player Comparison")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Done") {
                    dismiss()
                }
            }
        }
        .task {
            await viewModel.load()
        }
    }

    @ViewBuilder
    private var content: some View {
        if viewModel.isLoading, viewModel.players.isEmpty {
            ProgressView("Comparing players…")
                .tint(AcademyColors.claret)
        } else if let message = viewModel.errorMessage, viewModel.players.isEmpty {
            ContentUnavailableView {
                Label("Comparison unavailable", systemImage: "wifi.exclamationmark")
            } description: {
                Text(message)
            } actions: {
                Button("Try Again") {
                    Task { await viewModel.load() }
                }
                .buttonStyle(.borderedProminent)
                .tint(AcademyColors.claret)
            }
        } else if viewModel.players.isEmpty {
            ContentUnavailableView(
                "No players found",
                systemImage: "person.2.slash",
                description: Text("These players are not available for comparison.")
            )
        } else {
            comparisonTable
        }
    }

    private var comparisonTable: some View {
        ScrollView(.vertical) {
            ScrollView(.horizontal, showsIndicators: viewModel.players.count > 2) {
                LazyVStack(alignment: .leading, spacing: 0) {
                    playerHeaders

                    ForEach(visibleRows) { row in
                        if let section = row.section {
                            sectionHeader(section)
                        }
                        statRow(row)
                    }
                }
                .background(AcademyColors.surface)
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
                }
                .padding(16)
            }
        }
    }

    private var playerHeaders: some View {
        HStack(alignment: .bottom, spacing: 0) {
            Color.clear
                .frame(width: Self.labelColumnWidth, height: 182)

            ForEach(viewModel.players) { player in
                ComparePlayerHeader(player: player)
                    .frame(width: Self.playerColumnWidth, height: 182, alignment: .bottom)
            }
        }
        .background(Color(uiColor: .tertiarySystemGroupedBackground))
        .overlay(alignment: .bottom) {
            Divider()
        }
    }

    private func sectionHeader(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.caption2.weight(.bold))
            .tracking(1.1)
            .foregroundStyle(AcademyColors.claret)
            .padding(.horizontal, 12)
            .frame(
                width: tableWidth,
                height: 38,
                alignment: .leading
            )
            .background(Color(uiColor: .tertiarySystemGroupedBackground))
    }

    private func statRow(_ row: CompareRow) -> some View {
        let values = viewModel.players.map(row.value)
        let numericValues = values.map { $0?.numericValue }
        let highlightedIndices = row.highlightsBest
            ? CompareHighlighting.highlightedIndices(
                in: numericValues,
                lowerIsBetter: row.lowerIsBetter
            )
            : []

        return HStack(spacing: 0) {
            Text(row.label)
                .font(.caption.weight(.medium))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 10)
                .frame(width: Self.labelColumnWidth, alignment: .leading)
                .frame(minHeight: 44)

            ForEach(values.indices, id: \.self) { index in
                let isHighlighted = highlightedIndices.contains(index)
                Text(values[index]?.displayValue ?? "—")
                    .font(.subheadline.weight(isHighlighted ? .bold : .regular))
                    .foregroundStyle(isHighlighted ? AcademyColors.claret : Color.primary)
                    .monospacedDigit()
                    .lineLimit(2)
                    .minimumScaleFactor(0.72)
                    .multilineTextAlignment(.center)
                    .frame(width: Self.playerColumnWidth, alignment: .center)
                    .frame(minHeight: 44)
                    .background(isHighlighted ? AcademyColors.claretSoft : Color.clear)
            }
        }
        .overlay(alignment: .bottom) {
            Divider()
        }
        .accessibilityElement(children: .contain)
    }

    private var visibleRows: [CompareRow] {
        let includesGoalkeeper = viewModel.players.contains { $0.profile.isGoalkeeper }
        return Self.rows.filter { !$0.goalkeeperOnly || includesGoalkeeper }
    }

    private var tableWidth: CGFloat {
        Self.labelColumnWidth + Self.playerColumnWidth * CGFloat(viewModel.players.count)
    }
}

private extension CompareView {
    static let rows: [CompareRow] = [
        CompareRow(
            id: "season-appearances",
            section: "Season",
            label: "Appearances",
            value: { $0.totals.appearances.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "season-minutes",
            label: "Minutes",
            value: { $0.totals.minutesPlayed.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "season-goals",
            label: "Goals",
            value: { $0.totals.goals.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "season-assists",
            label: "Assists",
            value: { $0.totals.assists.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "season-rating",
            label: "Avg rating",
            value: { $0.totals.avgRating.map(CompareCellValue.decimal) }
        ),
        CompareRow(
            id: "season-shots",
            label: "Shots",
            value: { $0.totals.shotsTotal.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "season-key-passes",
            label: "Key passes",
            value: { $0.totals.keyPasses.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "season-dribbles",
            label: "Dribbles won",
            value: { $0.totals.dribblesSuccess.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "season-tackles",
            label: "Tackles",
            value: { $0.totals.tackles.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "season-interceptions",
            label: "Interceptions",
            value: { $0.totals.interceptions.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "season-duels-won",
            label: "Duels won",
            value: { $0.totals.duelsWon.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "season-saves",
            label: "Saves",
            goalkeeperOnly: true,
            value: { $0.totals.saves.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "season-goals-conceded",
            label: "Goals conceded",
            goalkeeperOnly: true,
            lowerIsBetter: true,
            value: { $0.totals.goalsConceded.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "season-clean-sheets",
            label: "Clean sheets",
            goalkeeperOnly: true,
            value: { $0.totals.cleanSheets.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "season-penalties-saved",
            label: "Penalties saved",
            goalkeeperOnly: true,
            value: { $0.totals.penaltySaved.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "per90-contributions",
            section: "Per 90",
            label: "G+A / 90",
            value: { $0.per90.goalContributions.map(CompareCellValue.decimal) }
        ),
        CompareRow(
            id: "per90-goals",
            label: "Goals / 90",
            value: { $0.per90.goals.map(CompareCellValue.decimal) }
        ),
        CompareRow(
            id: "per90-assists",
            label: "Assists / 90",
            value: { $0.per90.assists.map(CompareCellValue.decimal) }
        ),
        CompareRow(
            id: "per90-key-passes",
            label: "Key passes / 90",
            value: { $0.per90.keyPasses.map(CompareCellValue.decimal) }
        ),
        CompareRow(
            id: "per90-shots",
            label: "Shots / 90",
            value: { $0.per90.shotsTotal.map(CompareCellValue.decimal) }
        ),
        CompareRow(
            id: "per90-dribbles",
            label: "Dribbles / 90",
            value: { $0.per90.dribblesSuccess.map(CompareCellValue.decimal) }
        ),
        CompareRow(
            id: "per90-tackles",
            label: "Tackles / 90",
            value: { $0.per90.tackles.map(CompareCellValue.decimal) }
        ),
        CompareRow(
            id: "per90-duels-won",
            label: "Duels won / 90",
            value: { $0.per90.duelsWon.map(CompareCellValue.decimal) }
        ),
        CompareRow(
            id: "availability-missed",
            section: "Availability",
            label: "Fixtures missed",
            highlightsBest: false,
            value: { $0.availability?.totalAbsences.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "availability-reason",
            label: "Last absence",
            highlightsBest: false,
            value: { $0.availability?.lastReason.map(CompareCellValue.text) }
        ),
        CompareRow(
            id: "career-academy-apps",
            section: "Career",
            label: "Academy apps",
            value: { $0.career?.youthApps.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "career-loan-apps",
            label: "Loan apps",
            value: { $0.career?.loanApps.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "career-first-team-apps",
            label: "First-team apps",
            value: { $0.career?.firstTeamApps.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "career-goals",
            label: "Career goals",
            value: { $0.career?.goals.map(CompareCellValue.integer) }
        ),
        CompareRow(
            id: "career-assists",
            label: "Career assists",
            value: { $0.career?.assists.map(CompareCellValue.integer) }
        ),
    ]
}

private struct CompareRow: Identifiable {
    let id: String
    var section: String?
    let label: String
    var goalkeeperOnly = false
    var lowerIsBetter = false
    var highlightsBest = true
    let value: (ComparePlayer) -> CompareCellValue?
}

private enum CompareCellValue {
    case integer(Int)
    case decimal(Double)
    case text(String)

    var numericValue: Double? {
        switch self {
        case let .integer(value): Double(value)
        case let .decimal(value): value
        case .text: nil
        }
    }

    var displayValue: String {
        switch self {
        case let .integer(value):
            value.formatted()
        case let .decimal(value):
            value.formatted(
                .number
                    .grouping(.automatic)
                    .precision(.fractionLength(0 ... 2))
            )
        case let .text(value):
            value
        }
    }
}

private struct ComparePlayerHeader: View {
    let player: ComparePlayer

    var body: some View {
        VStack(spacing: 6) {
            playerPhoto

            Text(player.profile.playerName)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.primary)
                .lineLimit(2)
                .multilineTextAlignment(.center)

            Text(metadata)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)

            if let status = player.profile.status, !status.isEmpty {
                BadgeView(text: displayStatus(status))
            }

            Text(player.profile.clubName ?? "Club unavailable")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(2)
                .multilineTextAlignment(.center)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var playerPhoto: some View {
        Group {
            if let photoURL = player.profile.photoURL {
                AsyncImage(url: photoURL) { phase in
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
        .frame(width: 54, height: 54)
        .background(Color(uiColor: .tertiarySystemFill))
        .clipShape(Circle())
        .overlay {
            Circle().stroke(AcademyColors.claret.opacity(0.18), lineWidth: 1)
        }
    }

    private var photoPlaceholder: some View {
        Image(systemName: "person.crop.circle.fill")
            .resizable()
            .scaledToFit()
            .foregroundStyle(.tertiary)
    }

    private var metadata: String {
        [
            player.profile.position,
            player.profile.age.map { "\($0) yrs" },
        ]
        .compactMap { $0 }
        .filter { !$0.isEmpty }
        .joined(separator: " · ")
    }

    private func displayStatus(_ status: String) -> String {
        status
            .split(separator: "_")
            .map { $0.capitalized }
            .joined(separator: " ")
    }
}
