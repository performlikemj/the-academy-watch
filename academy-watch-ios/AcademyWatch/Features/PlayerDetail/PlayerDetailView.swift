import SwiftUI

@MainActor
struct PlayerDetailView: View {
    @StateObject private var viewModel: PlayerDetailViewModel
    @StateObject private var showcaseViewModel: ShowcaseViewModel
    @StateObject private var claimViewModel: PlayerClaimViewModel
    @StateObject private var interestSignalsViewModel: PlayerInterestSignalsViewModel
    @StateObject private var fanViewModel: PlayerFanViewModel
    @StateObject private var linesViewModel: PlayerMatchLinesViewModel
    @ObservedObject private var contactAvailability: ContactFeatureAvailability
    @EnvironmentObject private var authManager: AuthManager
    @State private var isTakedownRequestPresented = false
    @State private var isAddGamePresented = false
    @State private var reportSubject: ContentReportSubject?
    @State private var pickedPhotoID: Int?
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
        _linesViewModel = StateObject(
            wrappedValue: PlayerMatchLinesViewModel(playerID: playerID, apiClient: apiClient)
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
        matchLinesAPIClient: any PlayerMatchLinesAPIClientProtocol = APIClient(),
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
        _linesViewModel = StateObject(
            wrappedValue: PlayerMatchLinesViewModel(playerID: viewModel.playerID, apiClient: matchLinesAPIClient)
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
                Task {
                    async let totals: Void = viewModel.refreshAfterMatchAdd(response)
                    async let lines: Void = linesViewModel.load()
                    _ = await (totals, lines)
                }
            }
        }
        .task {
            await viewModel.loadIfNeeded()
        }
        .task(id: authManager.accountIdentity) {
            // The showcase and the match lines differ by reader: nothing read
            // for one account is kept for the next.
            showcaseViewModel.resetAccount()
            linesViewModel.resetAccount()
            pickedPhotoID = nil
            async let showcaseLoad: Void = showcaseViewModel.loadIfNeeded()
            async let linesLoad: Void = linesViewModel.load()
            _ = await (showcaseLoad, linesLoad)
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
                    heroSection(profile: profile)
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
                    ShowcaseSectionView(viewModel: showcaseViewModel, showsProfile: false)
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
                async let linesReload: Void = linesViewModel.load()
                _ = await (detailReload, showcaseReload, claimReload, linesReload)
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
                if let anchor = PlayerCardReviewFixtures.anchor {
                    try? await Task.sleep(for: .milliseconds(1500))
                    proxy.scrollTo(anchor == "facts" ? "review-facts" : "review-season", anchor: .top)
                    if anchor == "matches" || anchor == "end" {
                        try? await Task.sleep(for: .milliseconds(400))
                        proxy.scrollTo("review-matches", anchor: anchor == "end" ? .bottom : .top)
                    }
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

    /// Card C: the approved photo (or the initials tile) with the name over a
    /// night scrim, the player's own words, then the facts strip.
    @ViewBuilder
    private func heroSection(profile: PlayerProfile) -> some View {
        let showcase = showcaseViewModel.showcase
        let photos = showcase?.publicPhotos ?? []
        let photo = photos.first { $0.id == pickedPhotoID } ?? photos.first
        let confirmedBy = showcase?.confirmedClubName
        let clubName = confirmedBy ?? profile.currentClubName
        let age = PlayerAgeCalculator.age(from: viewModel.journey?.birthDate) ?? profile.age
        let line = [
            profile.position.map(expandedPosition),
            clubName,
            age.map { "\($0) yrs" },
            profile.nationality,
        ]
        .compactMap { $0 }
        .filter { !$0.isEmpty }
        .joined(separator: " · ")

        VStack(alignment: .leading, spacing: 20) {
            PlayerHeroCard(
                name: profile.name,
                photoURL: photo?.url,
                faceURL: profile.photoURL,
                clubName: clubName,
                role: PlayerCardText.roleLabel(
                    positions: showcase?.profile?.positions,
                    fallback: profile.position.map(expandedPosition)
                ),
                confirmedBy: confirmedBy,
                eyebrow: heroEyebrow(profile: profile),
                line: line.isEmpty ? nil : line
            )

            if photos.count > 1 {
                photoThumbnails(photos, selected: photo, name: profile.name)
            }

            if let bio = showcase?.profile?.bio?.trimmingCharacters(in: .whitespacesAndNewlines), !bio.isEmpty {
                PlayerQuote(text: bio)
            }

            if let clubName = profile.currentClubName {
                PlayerClubRow(profile: profile, clubName: clubName)
            }

            PlayerFactsStrip(facts: PlayerCardText.profileFacts(showcase?.profile))
                .id("review-facts")
        }
    }

    private func heroEyebrow(profile: PlayerProfile) -> String? {
        guard let status = profile.status, !status.isEmpty else { return nil }
        var parts = [status.replacingOccurrences(of: "_", with: " ")]
        if status == "on_loan", let owner = profile.ownerTeamName, !owner.isEmpty {
            parts.append("from \(owner)")
        }
        if let fee = profile.saleFee, !fee.isEmpty { parts.append(fee) }
        return parts.joined(separator: " · ")
    }

    private func photoThumbnails(_ photos: [ShowcasePhoto], selected: ShowcasePhoto?, name: String) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(Array(photos.enumerated()), id: \.element.id) { index, photo in
                    Button {
                        pickedPhotoID = photo.id
                    } label: {
                        AsyncImage(url: photo.url) { image in
                            image.resizable().scaledToFill()
                        } placeholder: {
                            AcademyColors.photoPlaceholder
                        }
                        .frame(width: 56, height: 56)
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .overlay {
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .stroke(photo.id == selected?.id ? AcademyColors.text : .clear, lineWidth: 2)
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Show photo \(index + 1) of \(photos.count)")
                    .accessibilityAddTraits(photo.id == selected?.id ? .isSelected : [])
                }
            }
            .padding(2)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Photos of \(name)")
        .accessibilityIdentifier("player-photo-thumbnails")
    }

    /// Totals are the provider's when it really has them, otherwise exactly
    /// the server's merged match lines for the season shown. The two are never
    /// added together, and nothing is merged or totalled here.
    @ViewBuilder
    private func seasonSection(profile: PlayerProfile) -> some View {
        let goalkeeper = profile.isGoalkeeper || PlayerCardText.isGoalkeeper(position: profile.position)
        let totalsLoading = viewModel.isLoading(.seasonStats)
        let totalsError = viewModel.errorMessage(for: .seasonStats) != nil
        // The provider's per-match rows count only once they have settled for
        // the season asked for.
        let rowsSettled = !viewModel.isLoading(.recentForm) && viewModel.errorMessage(for: .recentForm) == nil
        let choice = PlayerCardText.seasonView(
            picked: viewModel.hasExplicitSeason ? viewModel.selectedSeason : nil,
            stats: viewModel.seasonStats,
            seasons: linesViewModel.seasons,
            fallbackSeason: viewModel.selectedSeason,
            matchRows: rowsSettled ? viewModel.recentFixtures : [],
            matchRowsSeason: rowsSettled ? viewModel.selectedSeason : nil
        )
        let stats = choice.statsMatchSeason ? viewModel.seasonStats : nil
        let summary = PlayerCardText.summarizeSeason(
            lines: choice.lines,
            totals: choice.totals,
            provider: choice.provider,
            goalkeeper: goalkeeper,
            frozen: stats?.publicMatchData != nil,
            minutesKnown: stats?.statsCoverage != "limited"
        )
        let problem = PlayerCardText.readProblem(
            linesError: linesViewModel.failed,
            linesStale: linesViewModel.hasLines,
            totalsError: totalsError,
            totalsStale: stats != nil,
            showing: choice.provider != nil || !choice.lines.isEmpty
        )
        let currentSeason = viewModel.seasons.first(where: \.isCurrent)?.season ?? PlayerCardText.calendarSeason()

        VStack(alignment: .leading, spacing: 28) {
            PlayerSeasonBlock(
                seasonLabel: seasonLabel(choice.season),
                kicker: PlayerCardText.seasonKicker(season: choice.season, currentSeason: currentSeason),
                summary: summary,
                playerName: profile.name,
                loading: linesViewModel.isAwaitingFirstAnswer || totalsLoading,
                problem: problem,
                onRetry: {
                    Task {
                        if linesViewModel.failed { await linesViewModel.retry() }
                        if totalsError { await viewModel.reload() }
                    }
                },
                truncated: linesViewModel.truncated
            ) {
                SeasonPicker(
                    seasons: pickerSeasons,
                    selectedSeason: choice.season
                ) { season in
                    Task { await viewModel.selectSeason(season) }
                }
            }

            PlayerMatchLinesSection(lines: choice.lines, goalkeeper: goalkeeper)
                .id(choice.season)
                .id("review-matches")

            if summary.source == .provider, let stats, !stats.clubs.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Text("BY CLUB")
                        .font(AcademyType.mono(11, relativeTo: .caption))
                        .tracking(1.9)
                        .foregroundStyle(AcademyColors.secondaryText)
                        .accessibilityLabel("By club")
                        .accessibilityAddTraits(.isHeader)
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
            }
        }
    }

    private func seasonLabel(_ season: Int?) -> String {
        guard let season else { return "Season" }
        return viewModel.seasons.first { $0.season == season }?.label ?? SeasonLabelFormatter.label(for: season)
    }

    /// The directory's seasons plus any season the match lines cover.
    private var pickerSeasons: [Season] {
        var seasons = viewModel.seasons
        for entry in linesViewModel.seasons where !seasons.contains(where: { $0.season == entry.season }) {
            seasons.append(Season(
                season: entry.season,
                label: SeasonLabelFormatter.label(for: entry.season),
                hasRollup: true,
                isCurrent: false
            ))
        }
        return seasons.sorted { $0.season > $1.season }
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

private struct PlayerClubRow: View {
    let profile: PlayerProfile
    let clubName: String

    var body: some View {
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
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .combine)
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
