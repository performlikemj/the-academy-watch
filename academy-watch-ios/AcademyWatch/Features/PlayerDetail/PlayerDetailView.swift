import SwiftUI

@MainActor
struct PlayerDetailView: View {
    @StateObject private var viewModel: PlayerDetailViewModel
    @StateObject private var showcaseViewModel: ShowcaseViewModel
    private let onSignInRequested: () -> Void

    init(
        playerID: Int,
        onSignInRequested: @escaping () -> Void = {}
    ) {
        _viewModel = StateObject(wrappedValue: PlayerDetailViewModel(playerID: playerID))
        _showcaseViewModel = StateObject(wrappedValue: ShowcaseViewModel(playerID: playerID))
        self.onSignInRequested = onSignInRequested
    }

    init(
        viewModel: PlayerDetailViewModel,
        onSignInRequested: @escaping () -> Void = {}
    ) {
        _viewModel = StateObject(wrappedValue: viewModel)
        _showcaseViewModel = StateObject(
            wrappedValue: ShowcaseViewModel(playerID: viewModel.playerID)
        )
        self.onSignInRequested = onSignInRequested
    }

    var body: some View {
        ZStack {
            AcademyColors.background.ignoresSafeArea()

            if viewModel.isLoading(.profile), viewModel.profile == nil {
                ProgressView("Loading player…")
                    .tint(AcademyColors.claret)
            } else if let message = viewModel.errorMessage(for: .profile), viewModel.profile == nil {
                PlayerDetailPageError(message: message) {
                    Task { await viewModel.reload() }
                }
                .padding(20)
            } else if let profile = viewModel.profile {
                detailContent(profile: profile)
            } else if viewModel.hasAttemptedLoad {
                ContentUnavailableView(
                    "Player unavailable",
                    systemImage: "person.crop.circle.badge.questionmark",
                    description: Text("No profile was returned for player #\(viewModel.playerID).")
                )
            }
        }
        .navigationTitle(viewModel.profile?.name ?? "Player Detail")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                WatchlistStarButton(
                    playerID: viewModel.playerID,
                    playerName: viewModel.profile?.name ?? "this player",
                    onSignInRequested: onSignInRequested,
                    showsBackground: false
                )
            }
        }
        .task {
            async let detailLoad: Void = viewModel.loadIfNeeded()
            async let showcaseLoad: Void = showcaseViewModel.loadIfNeeded()
            _ = await (detailLoad, showcaseLoad)
        }
    }

    private func detailContent(profile: PlayerProfile) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 22) {
                PlayerProfileHeader(profile: profile)
                AddPlayerToListButton(
                    playerID: viewModel.playerID,
                    playerName: profile.name,
                    onSignInRequested: onSignInRequested
                )
                ShowcaseSectionView(viewModel: showcaseViewModel)
                seasonSection(profile: profile)
                recentFormSection
                journeySection(profile: profile)
                availabilitySection
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
        }
        .refreshable {
            async let detailReload: Void = viewModel.reload()
            async let showcaseReload: Void = showcaseViewModel.reload()
            _ = await (detailReload, showcaseReload)
        }
    }

    @ViewBuilder
    private func seasonSection(profile: PlayerProfile) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            DetailSectionHeader(
                title: "SEASON STATS",
                iconName: "chart.xyaxis.line",
                detail: viewModel.seasonStats?.season
            )

            if viewModel.isLoading(.seasonStats) {
                PlayerDetailLoadingCard(label: "Loading season totals…")
            } else if let message = viewModel.errorMessage(for: .seasonStats) {
                PlayerDetailInlineError(message: message) {
                    Task { await viewModel.reload() }
                }
            } else if let stats = viewModel.seasonStats, stats.hasAnyData {
                SeasonOverviewCard(stats: stats, isGoalkeeper: profile.isGoalkeeper)

                if stats.clubs.isEmpty {
                    Text("Club-level totals are not available for this season.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 2)
                } else {
                    ForEach(Array(stats.clubs.enumerated()), id: \.offset) { _, club in
                        SeasonClubCard(
                            club: club,
                            sourceLabel: stats.clubSourceLabel,
                            competitionCount: viewModel.competitionCount(
                                for: club.teamName,
                                season: stats.seasonStartYear
                            ),
                            averageRating: viewModel.averageRating(for: club.teamName),
                            cleanSheets: viewModel.cleanSheets(for: club.teamName),
                            isCurrent: club.matchesCurrentClub(named: profile.currentClubName),
                            isGoalkeeper: profile.isGoalkeeper
                        )
                    }
                }
            } else {
                PlayerDetailEmptyCard(
                    iconName: "chart.bar",
                    title: "No season data",
                    message: "Season totals have not been recorded for this player yet."
                )
            }
        }
    }

    private var recentFormSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            DetailSectionHeader(title: "RECENT FORM", iconName: "clock.arrow.circlepath")

            if viewModel.isLoading(.recentForm) {
                PlayerDetailLoadingCard(label: "Loading recent matches…")
            } else if let message = viewModel.errorMessage(for: .recentForm) {
                PlayerDetailInlineError(message: message) {
                    Task { await viewModel.reload() }
                }
            } else if viewModel.recentMatches.isEmpty {
                PlayerDetailEmptyCard(
                    iconName: "calendar.badge.minus",
                    title: "No recent matches",
                    message: "Match-level form is not available for this season."
                )
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    LazyHStack(spacing: 10) {
                        ForEach(viewModel.recentMatches, id: \.id) { fixture in
                            RecentMatchCard(fixture: fixture)
                        }
                    }
                    .padding(.vertical, 1)
                }
            }
        }
    }

    private func journeySection(profile: PlayerProfile) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            DetailSectionHeader(
                title: "DEVELOPMENT JOURNEY",
                iconName: "point.topleft.down.to.point.bottomright.curvepath"
            )

            if viewModel.isLoading(.journey) {
                PlayerDetailLoadingCard(label: "Loading career journey…")
            } else if let message = viewModel.errorMessage(for: .journey) {
                PlayerDetailInlineError(message: message) {
                    Task { await viewModel.reload() }
                }
            } else if viewModel.timelineEntries.isEmpty {
                PlayerDetailEmptyCard(
                    iconName: "point.topleft.down.to.point.bottomright.curvepath",
                    title: "No journey yet",
                    message: "A season-by-season career record is not available."
                )
            } else {
                JourneyTimeline(
                    entries: viewModel.timelineEntries,
                    currentClubName: profile.currentClubName
                )

                if viewModel.timelineEntries.allSatisfy({ $0.minutes == nil }) {
                    Label("Journey minutes are not exposed by the current public feed.", systemImage: "info.circle")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .padding(.leading, 30)
                }
            }
        }
    }

    @ViewBuilder
    private var availabilitySection: some View {
        if viewModel.isLoading(.availability) {
            VStack(alignment: .leading, spacing: 10) {
                DetailSectionHeader(title: "AVAILABILITY", iconName: "cross.case")
                PlayerDetailLoadingCard(label: "Checking availability…")
            }
        } else if let message = viewModel.errorMessage(for: .availability) {
            VStack(alignment: .leading, spacing: 10) {
                DetailSectionHeader(title: "AVAILABILITY", iconName: "cross.case")
                PlayerDetailInlineError(message: message) {
                    Task { await viewModel.reload() }
                }
            }
        } else if let availability = viewModel.visibleAvailability {
            VStack(alignment: .leading, spacing: 10) {
                DetailSectionHeader(title: "AVAILABILITY", iconName: "cross.case.fill")
                AvailabilityCard(availability: availability)
            }
        }
    }
}

private struct PlayerProfileHeader: View {
    let profile: PlayerProfile

    var body: some View {
        VStack(spacing: 15) {
            profilePhoto

            VStack(spacing: 7) {
                Text(profile.name)
                    .font(.system(.largeTitle, design: .rounded, weight: .bold))
                    .multilineTextAlignment(.center)
                    .minimumScaleFactor(0.75)

                HStack(spacing: 6) {
                    if let position = profile.position, !position.isEmpty {
                        BadgeView(text: expandedPosition(position))
                    }
                    if let status = profile.status, !status.isEmpty {
                        BadgeView(
                            text: displayStatus(status),
                            foregroundColor: statusColor(status),
                            backgroundColor: statusColor(status).opacity(0.12)
                        )
                    }
                }

                if !metadataLine.isEmpty {
                    Text(metadataLine)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }

            if let clubName = profile.currentClubName {
                Divider()

                HStack(spacing: 11) {
                    clubLogo

                    VStack(alignment: .leading, spacing: 2) {
                        Text(clubName)
                            .font(.headline)
                        if let clubOriginLine = profile.clubOriginLine {
                            Text(clubOriginLine)
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                }
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity)
        .background(
            LinearGradient(
                colors: [AcademyColors.surface, AcademyColors.claretSoft.opacity(0.45)],
                startPoint: .top,
                endPoint: .bottomTrailing
            ),
            in: RoundedRectangle(cornerRadius: 22, style: .continuous)
        )
        .overlay {
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(AcademyColors.claret.opacity(0.16), lineWidth: 0.75)
        }
    }

    @ViewBuilder
    private var profilePhoto: some View {
        Group {
            if let photoURL = profile.photoURL {
                AsyncImage(url: photoURL, transaction: Transaction(animation: .easeInOut(duration: 0.2))) { phase in
                    switch phase {
                    case let .success(image):
                        image.resizable().scaledToFill()
                    case .empty:
                        ProgressView().tint(AcademyColors.claret)
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
        .frame(width: 132, height: 132)
        .background(Color(uiColor: .tertiarySystemFill))
        .clipShape(Circle())
        .overlay {
            Circle().stroke(Color.white.opacity(0.9), lineWidth: 4)
            Circle().stroke(AcademyColors.claret.opacity(0.28), lineWidth: 1)
        }
        .shadow(color: AcademyColors.claret.opacity(0.16), radius: 12, y: 5)
        .accessibilityLabel("Photo of \(profile.name)")
    }

    private var photoPlaceholder: some View {
        Image(systemName: "person.crop.circle.fill")
            .resizable()
            .scaledToFit()
            .foregroundStyle(.tertiary)
    }

    private var clubLogo: some View {
        Group {
            if let logoURL = profile.currentClubLogoURL {
                AsyncImage(url: logoURL) { image in
                    image.resizable().scaledToFit()
                } placeholder: {
                    ProgressView().controlSize(.small)
                }
            } else {
                Image(systemName: "shield.fill")
                    .resizable()
                    .scaledToFit()
                    .foregroundStyle(AcademyColors.claret)
                    .padding(7)
            }
        }
        .frame(width: 42, height: 42)
        .background(Color(uiColor: .tertiarySystemFill), in: RoundedRectangle(cornerRadius: 10))
        .accessibilityHidden(true)
    }

    private var metadataLine: String {
        var parts: [String] = []
        if let age = profile.age { parts.append(age.formatted()) }
        if let nationality = profile.nationality, !nationality.isEmpty { parts.append(nationality) }
        return parts.joined(separator: " · ")
    }
}

private struct SeasonOverviewCard: View {
    let stats: PlayerSeasonStats
    let isGoalkeeper: Bool

    private var countingMetrics: [DetailMetric] {
        if isGoalkeeper {
            return [
                DetailMetric(label: "Apps", value: stats.appearances.formatted()),
                DetailMetric(label: "Goals", value: stats.goals.formatted()),
                DetailMetric(label: "Assists", value: stats.assists.formatted()),
                DetailMetric(label: "Minutes", value: stats.minutes.formatted()),
            ]
        }
        return [
            DetailMetric(label: "Apps", value: stats.appearances.formatted()),
            DetailMetric(label: "Goals", value: stats.goals.formatted()),
            DetailMetric(label: "Assists", value: stats.assists.formatted()),
            DetailMetric(label: "Minutes", value: stats.minutes.formatted()),
        ]
    }

    private var matchMetrics: [DetailMetric] {
        guard isGoalkeeper else {
            return [DetailMetric(label: "Rating", value: formatRating(stats.avgRating))]
        }

        let hasDetail = stats.hasDetailedGoalkeeperCoverage
        return [
            DetailMetric(label: "Saves", value: hasDetail ? stats.saves.formatted() : "—"),
            DetailMetric(label: "GA", value: hasDetail ? stats.goalsConceded.formatted() : "—"),
            DetailMetric(label: "Clean sheets", value: hasDetail ? stats.cleanSheets.formatted() : "—"),
            DetailMetric(label: "Rating", value: hasDetail ? formatRating(stats.avgRating) : "—"),
        ]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Overall")
                .font(.headline)

            if stats.hasHeadlineData {
                SeasonMetricGroup(
                    title: "Counting stats",
                    sourceLabel: stats.countingSourceLabel,
                    metrics: countingMetrics
                )

                SeasonMetricGroup(
                    title: isGoalkeeper ? "Goalkeeper events" : "Match detail",
                    sourceLabel: stats.matchDetailSourceLabel,
                    metrics: matchMetrics
                )
            } else {
                Label("Counting totals unavailable for this coverage snapshot.", systemImage: "info.circle")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            if let comparisonSource = stats.provenance?.sourceLabel {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text("Minutes coverage comparison")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer(minLength: 4)
                    SourceBadge(text: comparisonSource)
                }
            }

            if let detailText = stats.provenance?.detailText {
                Text(detailText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if !stats.hasDetailedGoalkeeperCoverage, isGoalkeeper {
                Text("Goalkeeper event detail is unavailable at this coverage level.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .detailCardStyle()
    }
}

private struct SeasonClubCard: View {
    let club: PlayerSeasonClub
    let sourceLabel: String?
    let competitionCount: Int?
    let averageRating: Double?
    let cleanSheets: Int?
    let isCurrent: Bool
    let isGoalkeeper: Bool

    private var countingMetrics: [DetailMetric] {
        if isGoalkeeper {
            return [
                DetailMetric(label: "Apps", value: formatOptional(club.appearances)),
                DetailMetric(label: "Goals", value: formatOptional(club.goals)),
                DetailMetric(label: "Assists", value: formatOptional(club.assists)),
                DetailMetric(label: "Minutes", value: formatOptional(club.minutes)),
                DetailMetric(label: "Saves", value: formatOptional(club.saves)),
                DetailMetric(label: "GA", value: formatOptional(club.goalsConceded)),
            ]
        }
        return [
            DetailMetric(label: "Apps", value: formatOptional(club.appearances)),
            DetailMetric(label: "Goals", value: formatOptional(club.goals)),
            DetailMetric(label: "Assists", value: formatOptional(club.assists)),
            DetailMetric(label: "Minutes", value: formatOptional(club.minutes)),
        ]
    }

    private var matchMetrics: [DetailMetric] {
        if isGoalkeeper {
            return [
                DetailMetric(label: "Clean sheets", value: cleanSheets.map(String.init) ?? "—"),
                DetailMetric(label: "Rating", value: formatRating(averageRating)),
            ]
        }
        return [DetailMetric(label: "Rating", value: formatRating(averageRating))]
    }

    private var hasMatchDetail: Bool {
        averageRating != nil || (isGoalkeeper && cleanSheets != nil)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                clubLogo

                VStack(alignment: .leading, spacing: 2) {
                    Text(club.teamName)
                        .font(.headline)
                    if let competitionCount {
                        HStack(spacing: 6) {
                            Text("\(competitionCount) competition\(competitionCount == 1 ? "" : "s")")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            SourceBadge(text: "career season data")
                        }
                    }
                }

                Spacer(minLength: 4)

                if isCurrent {
                    BadgeView(
                        text: "Current",
                        foregroundColor: Color(red: 0.04, green: 0.45, blue: 0.20),
                        backgroundColor: Color(red: 0.04, green: 0.45, blue: 0.20).opacity(0.12)
                    )
                }
            }

            SeasonMetricGroup(
                title: "Counting stats",
                sourceLabel: sourceLabel,
                metrics: countingMetrics
            )

            if hasMatchDetail {
                SeasonMetricGroup(
                    title: "Match detail",
                    sourceLabel: "match-level data",
                    metrics: matchMetrics
                )
            }
        }
        .detailCardStyle()
    }

    private var clubLogo: some View {
        Group {
            if let logoURL = club.logoURL {
                AsyncImage(url: logoURL) { image in
                    image.resizable().scaledToFit()
                } placeholder: {
                    ProgressView().controlSize(.small)
                }
            } else {
                Image(systemName: "shield.fill")
                    .resizable()
                    .scaledToFit()
                    .foregroundStyle(.tertiary)
                    .padding(7)
            }
        }
        .frame(width: 40, height: 40)
        .background(Color(uiColor: .tertiarySystemFill), in: RoundedRectangle(cornerRadius: 9))
        .accessibilityHidden(true)
    }
}

private struct SeasonMetricGroup: View {
    let title: String
    let sourceLabel: String?
    let metrics: [DetailMetric]

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(title.uppercased())
                    .font(.caption2.weight(.bold))
                    .tracking(0.35)
                    .foregroundStyle(.secondary)
                Spacer(minLength: 4)
                if let sourceLabel {
                    SourceBadge(text: sourceLabel)
                }
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 82), spacing: 8)], spacing: 8) {
                ForEach(metrics) { metric in
                    DetailMetricCell(metric: metric)
                }
            }
        }
    }
}

private struct DetailMetric: Identifiable {
    let label: String
    let value: String

    var id: String { label }
}

private struct DetailMetricCell: View {
    let metric: DetailMetric

    var body: some View {
        VStack(spacing: 2) {
            Text(metric.value)
                .font(.subheadline.weight(.bold))
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.72)
            Text(metric.label.uppercased())
                .font(.caption2.weight(.semibold))
                .tracking(0.25)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.72)
        }
        .frame(maxWidth: .infinity, minHeight: 48)
        .background(Color(uiColor: .tertiarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 9))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(metric.label), \(metric.value)")
    }
}

private struct RecentMatchCard: View {
    let fixture: PlayerRecentFixture

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            Text(compactDate(fixture.fixtureDate))
                .font(.caption.weight(.bold))
                .foregroundStyle(AcademyColors.claret)

            Text(fixture.opponent ?? "Opponent unavailable")
                .font(.subheadline.weight(.semibold))
                .lineLimit(2)
                .frame(minHeight: 38, alignment: .topLeading)

            Divider()

            HStack {
                matchValue(label: "MIN", value: formatOptional(fixture.minutes))
                matchValue(label: "G/A", value: formatGoalAssist(fixture.goals, fixture.assists))
                matchValue(label: "RATING", value: formatRating(fixture.rating))
            }
        }
        .padding(12)
        .frame(width: 174, alignment: .topLeading)
        .frame(minHeight: 142, alignment: .topLeading)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
        }
    }

    private func matchValue(label: String, value: String) -> some View {
        VStack(spacing: 1) {
            Text(value)
                .font(.caption.weight(.bold))
                .monospacedDigit()
            Text(label)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}

private struct JourneyTimeline: View {
    let entries: [PlayerJourneyTimelineEntry]
    let currentClubName: String?

    var body: some View {
        VStack(spacing: 0) {
            ForEach(Array(entries.enumerated()), id: \.element.id) { index, entry in
                HStack(alignment: .top, spacing: 11) {
                    VStack(spacing: 0) {
                        Circle()
                            .fill(isCurrent(entry) ? AcademyColors.claret : Color(uiColor: .tertiarySystemFill))
                            .frame(width: 15, height: 15)
                            .overlay {
                                Circle().stroke(AcademyColors.claret.opacity(0.42), lineWidth: 1)
                            }
                        if index < entries.count - 1 {
                            Rectangle()
                                .fill(AcademyColors.separator.opacity(0.45))
                                .frame(width: 2)
                                .frame(maxHeight: .infinity)
                        }
                    }
                    .frame(width: 18)

                    JourneyTimelineCard(entry: entry, isCurrent: isCurrent(entry))
                        .padding(.bottom, index < entries.count - 1 ? 10 : 0)
                }
                .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func isCurrent(_ entry: PlayerJourneyTimelineEntry) -> Bool {
        guard let currentClubName else { return false }
        return entry.clubName.caseInsensitiveCompare(currentClubName) == .orderedSame
            && entry.season == entries.first?.season
    }
}

private struct JourneyTimelineCard: View {
    let entry: PlayerJourneyTimelineEntry
    let isCurrent: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(alignment: .top, spacing: 9) {
                clubLogo

                VStack(alignment: .leading, spacing: 2) {
                    Text(entry.seasonLabel)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(AcademyColors.claret)
                    Text(entry.clubName)
                        .font(.headline)
                        .lineLimit(2)
                }

                Spacer(minLength: 4)

                if isCurrent {
                    BadgeView(
                        text: "Current",
                        foregroundColor: Color(red: 0.04, green: 0.45, blue: 0.20),
                        backgroundColor: Color(red: 0.04, green: 0.45, blue: 0.20).opacity(0.12)
                    )
                }
            }

            HStack(spacing: 5) {
                if let level = entry.level {
                    BadgeView(text: level)
                }
                if let entryType = entry.entryType {
                    BadgeView(
                        text: displayStatus(entryType),
                        foregroundColor: .secondary,
                        backgroundColor: Color(uiColor: .tertiarySystemFill)
                    )
                }
                if entry.competitionCount > 0 {
                    Text("\(entry.competitionCount) comp\(entry.competitionCount == 1 ? "" : "s")")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            HStack(spacing: 14) {
                if let appearances = entry.appearances {
                    timelineStat("Apps", appearances.formatted())
                }
                if let goals = entry.goals {
                    timelineStat("Goals", goals.formatted())
                }
                if let assists = entry.assists {
                    timelineStat("Assists", assists.formatted())
                }
                if let minutes = entry.minutes {
                    timelineStat("Minutes", minutes.formatted())
                }
            }

            if entry.appearances == nil,
               entry.goals == nil,
               entry.assists == nil,
               entry.minutes == nil {
                Text("Season totals unavailable")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .detailCardStyle()
    }

    private var clubLogo: some View {
        Group {
            if let logoURL = entry.logoURL {
                AsyncImage(url: logoURL) { image in
                    image.resizable().scaledToFit()
                } placeholder: {
                    ProgressView().controlSize(.mini)
                }
            } else {
                Image(systemName: "shield.fill")
                    .resizable()
                    .scaledToFit()
                    .foregroundStyle(.tertiary)
                    .padding(5)
            }
        }
        .frame(width: 34, height: 34)
        .accessibilityHidden(true)
    }

    private func timelineStat(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(value)
                .font(.subheadline.weight(.bold))
                .monospacedDigit()
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }
}

private struct AvailabilityCard: View {
    let availability: PlayerAvailability

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            VStack(spacing: 1) {
                Text(availability.summary.totalAbsences.formatted())
                    .font(.system(.title, design: .rounded, weight: .bold))
                    .foregroundStyle(AcademyColors.claret)
                    .monospacedDigit()
                Text("ABSENCES")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.secondary)
            }
            .frame(width: 72)

            Divider()

            VStack(alignment: .leading, spacing: 4) {
                Text("Latest reason")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(availability.summary.lastAbsence?.reason ?? "Unavailable")
                    .font(.headline)
                if let date = availability.summary.lastAbsence?.date {
                    Text(compactDate(date))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 0)
        }
        .detailCardStyle()
    }
}

private struct DetailSectionHeader: View {
    let title: String
    let iconName: String
    var detail: String?

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Label(title, systemImage: iconName)
                .font(.caption.weight(.bold))
                .tracking(1.05)
                .foregroundStyle(AcademyColors.claret)
            Spacer()
            if let detail {
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }
        }
        .padding(.horizontal, 2)
    }
}

private struct SourceBadge: View {
    let text: String

    var body: some View {
        Label(text, systemImage: "checkmark.seal")
            .font(.caption2.weight(.semibold))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 7)
            .padding(.vertical, 4)
            .background(Color(uiColor: .tertiarySystemFill), in: Capsule())
            .accessibilityLabel("Data source: \(text)")
    }
}

private struct PlayerDetailLoadingCard: View {
    let label: String

    var body: some View {
        HStack(spacing: 10) {
            ProgressView().tint(AcademyColors.claret)
            Text(label)
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, minHeight: 76)
        .detailCardStyle()
    }
}

private struct PlayerDetailEmptyCard: View {
    let iconName: String
    let title: String
    let message: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: iconName)
                .font(.title3)
                .foregroundStyle(AcademyColors.claret)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.subheadline.weight(.semibold))
                Text(message).font(.footnote).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .detailCardStyle()
    }
}

private struct PlayerDetailInlineError: View {
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

private struct PlayerDetailPageError: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        ContentUnavailableView {
            Label("Player unavailable", systemImage: "wifi.exclamationmark")
        } description: {
            Text(message)
        } actions: {
            Button("Try Again", action: retry)
                .buttonStyle(.borderedProminent)
                .tint(AcademyColors.claret)
        }
    }
}

private extension View {
    func detailCardStyle() -> some View {
        padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 15, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 15, style: .continuous)
                    .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
            }
    }
}

private func expandedPosition(_ position: String) -> String {
    switch position.uppercased() {
    case "G": "Goalkeeper"
    case "D": "Defender"
    case "M": "Midfielder"
    case "F": "Attacker"
    default: position
    }
}

private func displayStatus(_ status: String) -> String {
    status
        .split(separator: "_")
        .map { $0.capitalized }
        .joined(separator: " ")
}

private func statusColor(_ status: String) -> Color {
    switch status {
    case "academy": .blue
    case "on_loan": Color(red: 0.66, green: 0.32, blue: 0.02)
    case "first_team": Color(red: 0.04, green: 0.45, blue: 0.20)
    case "sold": .purple
    case "released", "left": .secondary
    default: AcademyColors.claret
    }
}

private func formatOptional(_ value: Int?) -> String {
    value?.formatted() ?? "—"
}

private func formatRating(_ value: Double?) -> String {
    guard let value else { return "—" }
    return value.formatted(.number.precision(.fractionLength(1)))
}

private func formatGoalAssist(_ goals: Int?, _ assists: Int?) -> String {
    guard goals != nil || assists != nil else { return "—" }
    return "\(goals?.formatted() ?? "—")/\(assists?.formatted() ?? "—")"
}

private func compactDate(_ value: String?) -> String {
    guard let value else { return "Date unavailable" }
    let components = value.prefix(10).split(separator: "-").compactMap { Int($0) }
    guard components.count == 3,
          let date = Calendar(identifier: .gregorian).date(
              from: DateComponents(year: components[0], month: components[1], day: components[2])
          )
    else { return String(value.prefix(10)) }
    return date.formatted(.dateTime.day().month(.abbreviated))
}
