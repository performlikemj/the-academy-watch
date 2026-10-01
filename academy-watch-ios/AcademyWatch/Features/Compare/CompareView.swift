import SwiftUI

@MainActor
struct CompareView: View {
    @StateObject private var viewModel: CompareViewModel
    @Environment(\.dismiss) private var dismiss

    @ScaledMetric(relativeTo: .caption) private var scaledLabelWidth: CGFloat = 112
    @ScaledMetric(relativeTo: .caption) private var scaledPlayerWidth: CGFloat = 120
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    private var labelColumnWidth: CGFloat { min(scaledLabelWidth, 140) }
    private var playerColumnWidth: CGFloat { min(scaledPlayerWidth, 220) }

    init(
        playerIDs: [Int],
        season: Int? = nil,
        apiClient: any CompareAPIClientProtocol = APIClient()
    ) {
        _viewModel = StateObject(
            wrappedValue: CompareViewModel(
                playerIDs: playerIDs,
                season: season,
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
            CleatLoader("Comparing players…")
                .tint(AcademyColors.accent)
        } else if let message = viewModel.errorMessage, viewModel.players.isEmpty {
            ContentUnavailableView {
                Label("Comparison unavailable", systemImage: "wifi.exclamationmark")
                .font(AcademyType.title2)
                .foregroundStyle(AcademyColors.text)
            } description: {
                Text(message)
            } actions: {
                Button("Try Again") {
                    Task { await viewModel.load() }
                }
                .buttonStyle(FloodlightPillStyle())
                .tint(AcademyColors.primaryFill)
            }
        } else if viewModel.players.isEmpty {
            FloodlightEmptyState(title: "No players found", systemImage: "person.2.slash", description: "These players are not available for comparison.")
        } else {
            comparisonTable
        }
    }

    private var comparisonTable: some View {
        VStack(spacing: 0) {
            Toggle(
                "Include availability",
                isOn: Binding(
                    get: { viewModel.includeAvailability },
                    set: { include in
                        Task { await viewModel.setIncludeAvailability(include) }
                    }
                )
            )
            .font(AcademyType.subheadline.weight(.semibold))
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(AcademyColors.surface)
            .accessibilityIdentifier("compare-include-availability")

            ScrollView(.vertical) {
                ScrollView(.horizontal, showsIndicators: viewModel.players.count > 2 || dynamicTypeSize.isAccessibilitySize) {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        playerHeaders

                        ForEach(visibleRows) { row in
                            if let section = row.section {
                                sectionHeader(section == "Season" ? viewModel.resolvedSeasonLabel : section)
                            }
                            statRow(row)
                        }
                    }
                    .background(AcademyColors.surface)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
                    }
                    .padding(16)
                }.background(AcademyColors.background)
            }.background(AcademyColors.background)
        }
    }

    private var playerHeaders: some View {
        HStack(alignment: .top, spacing: 0) {
            Color.clear
                .frame(width: labelColumnWidth, height: 1)

            ForEach(viewModel.players) { player in
                ComparePlayerHeader(player: player)
                    .frame(width: playerColumnWidth, alignment: .top)
            }
        }
        .frame(minHeight: 232, alignment: .top)
        .background(AcademyColors.elevatedSurface)
        .overlay(alignment: .bottom) {
            Divider()
        }
    }

    private func sectionHeader(_ title: String) -> some View {
        Text(title.uppercased())
            .font(AcademyType.caption2.weight(.medium))
            .tracking(1.1)
            .foregroundStyle(AcademyColors.secondaryText)
            .padding(.horizontal, 12)
            .frame(
                width: tableWidth,
                height: 38,
                alignment: .leading
            )
            .background(AcademyColors.elevatedSurface)
    }

    private func statRow(_ row: CompareRow) -> some View {
        let values: [CompareCellValue?] = viewModel.players.map { player in
            if player.totals.rollupMissing == true,
               (row.id.hasPrefix("season-") || row.id.hasPrefix("per90-")) {
                return CompareCellValue.text("No data this season")
            }
            return row.value(player)
        }
        let numericValues = values.map { $0?.numericValue }
        let highlightedIndices = row.highlightsBest
            ? CompareHighlighting.highlightedIndices(
                in: numericValues,
                lowerIsBetter: row.lowerIsBetter
            )
            : []

        return HStack(spacing: 0) {
            Text(row.label)
                .font(AcademyType.caption.weight(.medium))
                .foregroundStyle(AcademyColors.secondaryText)
                .padding(.horizontal, 10)
                .frame(width: labelColumnWidth, alignment: .leading)
                .frame(minHeight: 44)

            ForEach(values.indices, id: \.self) { index in
                let isHighlighted = highlightedIndices.contains(index)
                Text(values[index]?.displayValue ?? "—")
                    .font(AcademyType.serif(24, relativeTo: .title3))
                    .foregroundStyle(isHighlighted ? AcademyColors.accent : AcademyColors.text)
                    .monospacedDigit()
                    .lineLimit(2)
                    .minimumScaleFactor(0.72)
                    .multilineTextAlignment(.center)
                    .frame(width: playerColumnWidth, alignment: .center)
                    .frame(minHeight: 44)
                    .background(isHighlighted ? AcademyColors.accentSoft : Color.clear)
            }
        }
        .overlay(alignment: .bottom) {
            Divider()
        }
        .accessibilityElement(children: .contain)
    }

    private var visibleRows: [CompareRow] {
        let includesGoalkeeper = viewModel.players.contains { $0.profile.isGoalkeeper }
        return Self.rows.filter {
            (!$0.goalkeeperOnly || includesGoalkeeper)
                && (viewModel.includeAvailability || !$0.id.hasPrefix("availability-"))
        }
    }

    private var tableWidth: CGFloat {
        labelColumnWidth + playerColumnWidth * CGFloat(viewModel.players.count)
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
                .font(AcademyType.serif(22, relativeTo: .headline))
                .foregroundStyle(AcademyColors.text)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
                .multilineTextAlignment(.center)

            Text(metadata)
                .font(AcademyType.caption2)
                .foregroundStyle(AcademyColors.secondaryText)
                .lineLimit(2)
                .multilineTextAlignment(.center)

            if let status = player.profile.status, !status.isEmpty {
                BadgeView(text: displayStatus(status))
            }

            Text(player.profile.clubName ?? "Club unavailable")
                .font(AcademyType.caption2)
                .foregroundStyle(AcademyColors.secondaryText)
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
                        CleatLoader()
                            .tint(AcademyColors.accent)
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
        .background(AcademyColors.elevatedSurface)
        .clipShape(Circle())
        .overlay {
            Circle().stroke(AcademyColors.accent.opacity(0.18), lineWidth: 1)
        }
    }

    private var photoPlaceholder: some View {
        Image(systemName: "person.crop.circle.fill")
            .resizable()
            .scaledToFit()
            .foregroundStyle(AcademyColors.secondaryText)
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
