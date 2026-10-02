import SwiftUI

@MainActor
struct PlayerDetailView: View {
    @StateObject private var viewModel: PlayerDetailViewModel
    @StateObject private var showcaseViewModel: ShowcaseViewModel
    @StateObject private var claimViewModel: PlayerClaimViewModel
    @StateObject private var interestSignalsViewModel: PlayerInterestSignalsViewModel
    @StateObject private var fanViewModel: PlayerFanViewModel
    @ObservedObject private var contactAvailability: ContactFeatureAvailability
    @EnvironmentObject private var authManager: AuthManager
    @State private var isTakedownRequestPresented = false
    @State private var isAddGamePresented = false
    @State private var reportSubject: ContentReportSubject?
    private let onSignInRequested: () -> Void
    private let onVerificationRequested: () -> Void
    private let contactAPIClient: any ContactAPIClientProtocol
    private let reportAPIClient: any ContentReportAPIClientProtocol
    private let takedownAPIClient: any PlayerTakedownAPIClientProtocol
    private let matchAPIClient: any PlayerMatchAPIClientProtocol

    init(
        playerID: Int,
        apiClient: APIClient = APIClient(),
        initialSeason: Int? = nil,
        onSignInRequested: @escaping () -> Void = {},
        onVerificationRequested: @escaping () -> Void = {}
    ) {
        _viewModel = StateObject(
            wrappedValue: PlayerDetailViewModel(
                playerID: playerID,
                initialSeason: initialSeason,
                apiClient: apiClient
            )
        )
        _showcaseViewModel = StateObject(
            wrappedValue: ShowcaseViewModel(playerID: playerID, apiClient: apiClient)
        )
        _claimViewModel = StateObject(
            wrappedValue: PlayerClaimViewModel(playerID: playerID, apiClient: apiClient)
        )
        let contactAvailability = ContactFeatureAvailability.shared
        _interestSignalsViewModel = StateObject(
            wrappedValue: PlayerInterestSignalsViewModel(
                playerID: playerID,
                apiClient: apiClient,
                availability: contactAvailability
            )
        )
        _fanViewModel = StateObject(
            wrappedValue: PlayerFanViewModel(playerID: playerID, apiClient: apiClient)
        )
        _contactAvailability = ObservedObject(wrappedValue: contactAvailability)
        self.onSignInRequested = onSignInRequested
        self.onVerificationRequested = onVerificationRequested
        contactAPIClient = apiClient
        reportAPIClient = apiClient
        takedownAPIClient = apiClient
        matchAPIClient = apiClient
    }

    init(
        viewModel: PlayerDetailViewModel,
        showcaseAPIClient: any ShowcaseAPIClientProtocol = APIClient(),
        claimAPIClient: any PlayerClaimAPIClientProtocol = APIClient(),
        contactAPIClient: any ContactAPIClientProtocol = APIClient(),
        reportAPIClient: any ContentReportAPIClientProtocol = APIClient(),
        takedownAPIClient: any PlayerTakedownAPIClientProtocol = APIClient(),
        interestSignalsAPIClient: any InterestSignalsAPIClientProtocol = APIClient(),
        fanAPIClient: any PlayerFanAPIClientProtocol = APIClient(),
        matchAPIClient: any PlayerMatchAPIClientProtocol = APIClient(),
        contactAvailability: ContactFeatureAvailability? = nil,
        onSignInRequested: @escaping () -> Void = {},
        onVerificationRequested: @escaping () -> Void = {}
    ) {
        _viewModel = StateObject(wrappedValue: viewModel)
        _showcaseViewModel = StateObject(
            wrappedValue: ShowcaseViewModel(
                playerID: viewModel.playerID,
                apiClient: showcaseAPIClient
            )
        )
        _claimViewModel = StateObject(
            wrappedValue: PlayerClaimViewModel(
                playerID: viewModel.playerID,
                apiClient: claimAPIClient
            )
        )
        let resolvedContactAvailability = contactAvailability ?? .shared
        _interestSignalsViewModel = StateObject(
            wrappedValue: PlayerInterestSignalsViewModel(
                playerID: viewModel.playerID,
                apiClient: interestSignalsAPIClient,
                availability: resolvedContactAvailability
            )
        )
        _fanViewModel = StateObject(
            wrappedValue: PlayerFanViewModel(playerID: viewModel.playerID, apiClient: fanAPIClient)
        )
        _contactAvailability = ObservedObject(wrappedValue: resolvedContactAvailability)
        self.onSignInRequested = onSignInRequested
        self.onVerificationRequested = onVerificationRequested
        self.contactAPIClient = contactAPIClient
        self.reportAPIClient = reportAPIClient
        self.takedownAPIClient = takedownAPIClient
        self.matchAPIClient = matchAPIClient
    }

    var body: some View {
        ZStack {
            AcademyColors.background.ignoresSafeArea()

            if viewModel.isLoading(.profile), viewModel.profile == nil {
                WingLiftLoadingView("Loading player…")
            } else if let message = viewModel.errorMessage(for: .profile), viewModel.profile == nil {
                PlayerDetailPageError(message: message) {
                    Task { await viewModel.reload() }
                }
                .padding(20)
            } else if let profile = viewModel.profile {
                detailContent(profile: profile)
            } else if viewModel.hasAttemptedLoad {
                FloodlightEmptyState(title: "Player unavailable", systemImage: "person.crop.circle.badge.questionmark", description: "No profile was returned for player #\(viewModel.playerID).")
            }
        }
        .navigationTitle(viewModel.profile?.name ?? "Player Detail")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if let profile = viewModel.profile {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    if !profile.isShadow {
                        WatchlistStarButton(
                            playerID: viewModel.playerID,
                            playerName: profile.name,
                            onSignInRequested: onSignInRequested,
                            showsBackground: false
                        )
                    }
                    Menu {
                        Button("Request profile removal…", systemImage: "person.crop.circle.badge.minus") {
                            isTakedownRequestPresented = true
                        }
                        Button("Report profile…", systemImage: "exclamationmark.bubble") {
                            guard authManager.isAuthenticated else {
                                onSignInRequested()
                                return
                            }
                            reportSubject = .playerProfile(
                                playerID: viewModel.playerID,
                                name: profile.name
                            )
                        }
                        .accessibilityIdentifier("player-report-profile")
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                    .accessibilityLabel("More player actions")
                }
            }
        }
        .sheet(isPresented: $isTakedownRequestPresented) {
            PlayerTakedownRequestSheet(
                playerID: viewModel.playerID,
                apiClient: takedownAPIClient
            )
        }
        .sheet(item: $reportSubject) { subject in
            ContentReportSheet(subject: subject, apiClient: reportAPIClient)
        }
        .sheet(isPresented: $isAddGamePresented) {
            AddGameSheet(
                playerID: viewModel.playerID,
                playerName: viewModel.profile?.name ?? "this player",
                isGoalkeeper: viewModel.profile?.isGoalkeeper ?? false,
                apiClient: matchAPIClient
            ) { response in
                Task { await viewModel.refreshAfterMatchAdd(response) }
            }
        }
        .task {
            async let detailLoad: Void = viewModel.loadIfNeeded()
            async let showcaseLoad: Void = showcaseViewModel.loadIfNeeded()
            _ = await (detailLoad, showcaseLoad)
        }
        .task(id: authManager.accountIdentity) {
            claimViewModel.resetAccount()
            guard !prioritizesIntroductionFixture else { return }
            await claimViewModel.load(isAuthenticated: authManager.isAuthenticated)
        }
        .task(id: authManager.accountIdentity) {
            fanViewModel.resetAccount()
            // The count endpoint is anonymous-OK; auth only changes the
            // caller's own `following` flag, so re-resolve on auth changes.
            await fanViewModel.refresh()
        }
        .task {
            #if DEBUG
            guard FullCircleFixtureDestination.fromLaunchArguments(
                ProcessInfo.processInfo.arguments
            ) == .takedown else { return }
            try? await Task.sleep(for: .milliseconds(400))
            isTakedownRequestPresented = true
            #endif
        }
    }

    private func detailContent(profile: PlayerProfile) -> some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 22) {
                    PlayerProfileHeader(
                        profile: profile,
                        birthDate: viewModel.journey?.birthDate
                    )
                    PlayerFanSectionView(
                        viewModel: fanViewModel,
                        isAuthenticated: authManager.isAuthenticated,
                        onSignInRequested: onSignInRequested
                    )
                    if prioritizesIntroductionFixture {
                        introductionSection(profile: profile)
                    }
                    PlayerClaimSectionView(
                        viewModel: claimViewModel,
                        isAuthenticated: authManager.isAuthenticated,
                        accountRole: authManager.accountRole,
                        onSignInRequested: onSignInRequested
                    )
                    if ownsCurrentPlayerProfile {
                        PlayerInterestSignalsCard(viewModel: interestSignalsViewModel)
                            .id("player-interest-signals-card")
                    }
                    AddPlayerToListButton(
                        playerID: viewModel.playerID,
                        playerName: profile.name,
                        allowsWatchlist: !profile.isShadow,
                        onSignInRequested: onSignInRequested
                    )
                    if canManageGames {
                        Button {
                            isAddGamePresented = true
                        } label: {
                            Label("Add a game", systemImage: "figure.soccer")
                                .font(AcademyType.subheadline.weight(.semibold))
                        }
                        .buttonStyle(FloodlightPillStyle(variant: .outline))
                        .tint(AcademyColors.accent)
                        .accessibilityIdentifier("add-game-open")
                    }
                    ShowcaseSectionView(viewModel: showcaseViewModel)
                    if !prioritizesIntroductionFixture {
                        introductionSection(profile: profile)
                    }
                    seasonSection(profile: profile).id("review-season")
                    recentFormSection
                    journeySection(profile: profile)
                    availabilitySection
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
            }.background(AcademyColors.background)
            .refreshable {
                async let detailReload: Void = viewModel.reload()
                async let showcaseReload: Void = showcaseViewModel.reload()
                async let claimReload: Void = claimViewModel.load(
                    isAuthenticated: authManager.isAuthenticated
                )
                _ = await (detailReload, showcaseReload, claimReload)
                if ownsCurrentPlayerProfile {
                    await interestSignalsViewModel.refresh()
                }
            }
            .accessibilityIdentifier("player-detail-scroll")
            #if DEBUG && targetEnvironment(simulator)
            .task {
                if FloodlightPreview.screen == "season" {
                    try? await Task.sleep(for: .milliseconds(800))
                    proxy.scrollTo("review-season", anchor: .top)
                }
            }
            #endif
            .task {
                guard prioritizesInterestSignalsFixture else { return }
                try? await Task.sleep(for: .milliseconds(300))
                proxy.scrollTo("player-interest-signals-card", anchor: .center)
            }
        }
    }

    private var ownsCurrentPlayerProfile: Bool {
        claimViewModel.claim?.status == .approved
            && claimViewModel.claim?.relationshipType == "player"
    }

    /// The matches write route allows only approved claimants (player,
    /// guardian, or agent). Local players carry negative signed ids; positive
    /// ids are platform subjects whose games are club-managed, so the sheet is
    /// reachable for owned local players only.
    private var canManageGames: Bool {
        guard viewModel.playerID < 0, let claim = claimViewModel.claim, claim.status == .approved else {
            return false
        }
        return ["player", "guardian", "agent"].contains(claim.relationshipType)
    }

    private var prioritizesIntroductionFixture: Bool {
        let destination = FullCircleFixtureDestination.fromLaunchArguments(
            ProcessInfo.processInfo.arguments
        )
        return destination == .introduction || destination == .attestationWarning
    }

    private var prioritizesInterestSignalsFixture: Bool {
        FullCircleFixtureDestination.fromLaunchArguments(
            ProcessInfo.processInfo.arguments
        ) == .watchingYou
    }

    @ViewBuilder
    private func introductionSection(profile: PlayerProfile) -> some View {
        if authManager.isVerifiedScout,
           showcaseViewModel.showcase?.isClaimedProfile == true,
           contactAvailability.state == .available {
            IntroductionRequestSectionView(
                playerID: viewModel.playerID,
                playerName: profile.name,
                apiClient: contactAPIClient,
                availability: contactAvailability,
                onVerificationRequested: onVerificationRequested
            )
        }
    }

    @ViewBuilder
    private func seasonSection(profile: PlayerProfile) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            DetailSectionHeader(
                title: "SEASON STATS",
                iconName: "chart.xyaxis.line",
                detail: viewModel.seasonStats?.season,
                badge: viewModel.seasonStats?.provenance?.badgeText
            )

            SeasonPicker(
                seasons: viewModel.seasons,
                selectedSeason: viewModel.selectedSeason
            ) { season in
                Task { await viewModel.selectSeason(season) }
            }

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
                        .font(AcademyType.footnote)
                        .foregroundStyle(AcademyColors.secondaryText)
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
                }.background(AcademyColors.background)
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
                        .font(AcademyType.caption)
                        .foregroundStyle(AcademyColors.secondaryText)
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
        } else if viewModel.isAvailabilityDegraded {
            VStack(alignment: .leading, spacing: 10) {
                DetailSectionHeader(title: "AVAILABILITY", iconName: "cross.case")
                PlayerDetailEmptyCard(
                    iconName: "wifi.exclamationmark",
                    title: "Availability unavailable right now",
                    message: "We can’t confirm this player’s availability."
                )
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
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    let profile: PlayerProfile
    let birthDate: String?

    var body: some View {
        VStack(spacing: 15) {
            profilePhoto

            VStack(spacing: 7) {
                Text(profile.name)
                    .font(AcademyType.largeTitle)
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
                        .font(AcademyType.subheadline)
                        .foregroundStyle(AcademyColors.secondaryText)
                }
            }

            if let clubName = profile.currentClubName {
                Divider()

                HStack(spacing: 11) {
                    clubLogo

                    VStack(alignment: .leading, spacing: 2) {
                        Text(clubName)
                            .font(AcademyType.headline)
                        if let clubOriginLine = profile.clubOriginLine {
                            Text(clubOriginLine)
                                .font(AcademyType.subheadline)
                                .foregroundStyle(AcademyColors.secondaryText)
                        }
                    }
                    Spacer()
                }
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity)
        .overlay(alignment: .bottom) { Rectangle().fill(AcademyColors.hairline).frame(height: 1) }
    }

    @ViewBuilder
    private var profilePhoto: some View {
        Group {
            if let photoURL = profile.photoURL {
                AsyncImage(url: photoURL, transaction: Transaction(animation: reduceMotion ? nil : .easeInOut(duration: 0.2))) { phase in
                    switch phase {
                    case let .success(image):
                        image.resizable().scaledToFill()
                    case .empty:
                        WingLiftLoadingView()
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
        .background(AcademyColors.elevatedSurface)
        .clipShape(Circle())
        .overlay {
            Circle().stroke(AcademyColors.chalk.opacity(0.9), lineWidth: 4)
            Circle().stroke(AcademyColors.accent.opacity(0.28), lineWidth: 1)
        }
        .accessibilityLabel("Photo of \(profile.name)")
    }

    private var photoPlaceholder: some View {
        Image(systemName: "person.crop.circle.fill")
            .resizable()
            .scaledToFit()
            .foregroundStyle(AcademyColors.secondaryText)
    }

    private var clubLogo: some View {
        Group {
            if let logoURL = profile.currentClubLogoURL {
                AsyncImage(url: logoURL) { image in
                    image.resizable().scaledToFit()
                } placeholder: {
                    WingLiftLoadingView().controlSize(.small)
                }
            } else {
                Image(systemName: "shield.fill")
                    .resizable()
                    .scaledToFit()
                    .foregroundStyle(AcademyColors.accent)
                    .padding(7)
            }
        }
        .frame(width: 42, height: 42)
        .background(AcademyColors.elevatedSurface, in: RoundedRectangle(cornerRadius: 10))
        .accessibilityHidden(true)
    }

    private var metadataLine: String {
        var parts: [String] = []
        if let age = PlayerAgeCalculator.age(from: birthDate) ?? profile.age {
            parts.append(age.formatted())
        }
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
                .font(AcademyType.headline)

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
                    .font(AcademyType.footnote)
                    .foregroundStyle(AcademyColors.secondaryText)
            }

            if let comparisonSource = stats.provenance?.sourceLabel {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text("Minutes coverage comparison")
                        .font(AcademyType.caption)
                        .foregroundStyle(AcademyColors.secondaryText)
                    Spacer(minLength: 4)
                    SourceBadge(text: comparisonSource)
                }
            }

            if let detailText = stats.provenance?.detailText {
                Text(detailText)
                    .font(AcademyType.caption)
                    .foregroundStyle(AcademyColors.secondaryText)
            }

            if !stats.hasDetailedGoalkeeperCoverage, isGoalkeeper {
                Text("Goalkeeper event detail is unavailable at this coverage level.")
                    .font(AcademyType.caption2)
                    .foregroundStyle(AcademyColors.secondaryText)
            }
        }
        .detailCardStyle()
        .accessibilityIdentifier("season-overview-row")
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
                        .font(AcademyType.headline)
                    if let competitionCount {
                        HStack(spacing: 6) {
                            Text("\(competitionCount) competition\(competitionCount == 1 ? "" : "s")")
                                .font(AcademyType.caption)
                                .foregroundStyle(AcademyColors.secondaryText)
                            SourceBadge(text: "career season data")
                        }
                    }
                }

                Spacer(minLength: 4)

                if isCurrent {
                    BadgeView(
                        text: "Current",
                        foregroundColor: AcademyColors.good,
                        backgroundColor: AcademyColors.good.opacity(0.12)
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
        .accessibilityIdentifier("season-club-row")
    }

    private var clubLogo: some View {
        Group {
            if let logoURL = club.logoURL {
                AsyncImage(url: logoURL) { image in
                    image.resizable().scaledToFit()
                } placeholder: {
                    WingLiftLoadingView().controlSize(.small)
                }
            } else {
                Image(systemName: "shield.fill")
                    .resizable()
                    .scaledToFit()
                    .foregroundStyle(AcademyColors.secondaryText)
                    .padding(7)
            }
        }
        .frame(width: 40, height: 40)
        .background(AcademyColors.elevatedSurface, in: RoundedRectangle(cornerRadius: 9))
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
                    .font(AcademyType.caption2.weight(.medium))
                    .tracking(0.35)
                    .foregroundStyle(AcademyColors.secondaryText)
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
                .font(AcademyType.serif(36, relativeTo: .title2))
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.72)
            Text(metric.label.uppercased())
                .font(AcademyType.caption2.weight(.medium))
                .tracking(0.25)
                .foregroundStyle(AcademyColors.secondaryText)
                .lineLimit(1)
                .minimumScaleFactor(0.72)
        }
        .frame(maxWidth: .infinity, minHeight: 72)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(metric.label), \(metric.value)")
    }
}

private struct RecentMatchCard: View {
    let fixture: PlayerRecentFixture

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            Text(compactDate(fixture.fixtureDate))
                .font(AcademyType.caption.weight(.medium))
                .foregroundStyle(AcademyColors.accent)

            Text(fixture.opponent ?? "Opponent unavailable")
                .font(AcademyType.subheadline.weight(.semibold))
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
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
        }
    }

    private func matchValue(label: String, value: String) -> some View {
        VStack(spacing: 1) {
            Text(value)
                .font(AcademyType.caption.weight(.medium))
                .monospacedDigit()
            Text(label)
                .font(AcademyType.caption2.weight(.medium))
                .foregroundStyle(AcademyColors.secondaryText)
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
                            .fill(isCurrent(entry) ? AcademyColors.accent : AcademyColors.elevatedSurface)
                            .frame(width: 15, height: 15)
                            .overlay {
                                Circle().stroke(AcademyColors.accent.opacity(0.42), lineWidth: 1)
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
                        .font(AcademyType.caption.weight(.medium))
                        .foregroundStyle(AcademyColors.accent)
                    Text(entry.clubName)
                        .font(AcademyType.headline)
                        .lineLimit(2)
                }

                Spacer(minLength: 4)

                if isCurrent {
                    BadgeView(
                        text: "Current",
                        foregroundColor: AcademyColors.good,
                        backgroundColor: AcademyColors.good.opacity(0.12)
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
                        foregroundColor: AcademyColors.secondaryText,
                        backgroundColor: AcademyColors.elevatedSurface
                    )
                }
                if entry.competitionCount > 0 {
                    Text("\(entry.competitionCount) comp\(entry.competitionCount == 1 ? "" : "s")")
                        .font(AcademyType.caption2)
                        .foregroundStyle(AcademyColors.secondaryText)
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
                    .font(AcademyType.caption)
                    .foregroundStyle(AcademyColors.secondaryText)
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
                    WingLiftLoadingView().controlSize(.mini)
                }
            } else {
                Image(systemName: "shield.fill")
                    .resizable()
                    .scaledToFit()
                    .foregroundStyle(AcademyColors.secondaryText)
                    .padding(5)
            }
        }
        .frame(width: 34, height: 34)
        .accessibilityHidden(true)
    }

    private func timelineStat(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(value)
                .font(AcademyType.subheadline.weight(.semibold))
                .monospacedDigit()
            Text(label)
                .font(AcademyType.caption2)
                .foregroundStyle(AcademyColors.secondaryText)
        }
    }
}

private struct AvailabilityCard: View {
    let availability: PlayerAvailability

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            VStack(spacing: 1) {
                Text(availability.summary.totalAbsences?.formatted() ?? "—")
                    .font(AcademyType.title)
                    .foregroundStyle(AcademyColors.accent)
                    .monospacedDigit()
                Text("ABSENCES")
                    .font(AcademyType.caption2.weight(.medium))
                    .foregroundStyle(AcademyColors.secondaryText)
            }
            .frame(width: 72)

            Divider()

            VStack(alignment: .leading, spacing: 4) {
                Text("Latest reason")
                    .font(AcademyType.caption)
                    .foregroundStyle(AcademyColors.secondaryText)
                Text(availability.summary.lastAbsence?.reason ?? "Unavailable")
                    .font(AcademyType.headline)
                if let date = availability.summary.lastAbsence?.date {
                    Text(compactDate(date))
                        .font(AcademyType.caption)
                        .foregroundStyle(AcademyColors.secondaryText)
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
    var badge: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            FloodlightSectionHeader(title: title.capitalized, counter: detail)
            if let badge { SourceBadge(text: badge) }
        }
    }
}

private struct SourceBadge: View {
    let text: String

    var body: some View {
        Label(text, systemImage: "checkmark.seal")
            .font(AcademyType.caption2.weight(.medium))
            .foregroundStyle(AcademyColors.secondaryText)
            .padding(.horizontal, 7)
            .padding(.vertical, 4)
            .background(AcademyColors.elevatedSurface, in: Capsule())
            .accessibilityLabel("Data source: \(text)")
    }
}

private struct PlayerDetailLoadingCard: View {
    let label: String

    var body: some View {
        HStack(spacing: 10) {
            WingLiftLoadingView()
            Text(label)
                .font(AcademyType.footnote)
                .foregroundStyle(AcademyColors.secondaryText)
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
                .font(AcademyType.title3)
                .foregroundStyle(AcademyColors.accent)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(AcademyType.subheadline.weight(.semibold))
                Text(message).font(AcademyType.footnote).foregroundStyle(AcademyColors.secondaryText)
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
                .foregroundStyle(AcademyColors.accent)
            Text(message)
                .font(AcademyType.footnote)
                .foregroundStyle(AcademyColors.secondaryText)
            Spacer(minLength: 4)
            Button("Retry", action: retry)
                .font(AcademyType.footnote.weight(.semibold))
        }
        .padding(12)
        .background(AcademyColors.accentSoft, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .tint(AcademyColors.secondaryText)
    }
}

private struct PlayerDetailPageError: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        ContentUnavailableView {
            Label("Player unavailable", systemImage: "wifi.exclamationmark")
                .font(AcademyType.title2)
                .foregroundStyle(AcademyColors.text)
        } description: {
            Text(message)
        } actions: {
            Button("Try Again", action: retry)
                .buttonStyle(FloodlightPillStyle())
                .tint(AcademyColors.primaryFill)
        }
    }
}

private extension View {
    func detailCardStyle() -> some View {
        padding(.vertical, 14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .overlay(alignment: .bottom) { Rectangle().fill(AcademyColors.hairline).frame(height: 1) }
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
    case "academy": AcademyColors.secondaryText
    case "on_loan": AcademyColors.warnText
    case "first_team": AcademyColors.good
    case "sold": AcademyColors.secondaryText
    case "released", "left": .secondary
    default: AcademyColors.accent
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
