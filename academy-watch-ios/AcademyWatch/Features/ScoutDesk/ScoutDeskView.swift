import Foundation
import SwiftUI

@MainActor
struct ScoutDeskView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @EnvironmentObject private var authManager: AuthManager
    @StateObject private var viewModel: ScoutDeskViewModel
    @State private var navigationPath: [Int]
    @State private var selectedPlayerIDs: [Int]
    @State private var isComparePresented: Bool
    @State private var isWorldwideAddPresented = false
    @State private var isLocalAddPresented = false
    @State private var revealsTabBarDuringInitialLoad = false
    private let onSignInRequested: () -> Void
    private let onVerificationRequested: () -> Void
    private let onGolRequested: () -> Void
    private let playerDetailAPIClient: APIClient

    init(
        apiClient: any ScoutAPIClientProtocol = APIClient(),
        playerDetailAPIClient: APIClient = APIClient(),
        initialPhase: ScoutPhase = .all,
        initialPlayerID: Int? = nil,
        initialComparePlayerIDs: [Int] = [],
        onSignInRequested: @escaping () -> Void = {},
        onVerificationRequested: @escaping () -> Void = {},
        onGolRequested: @escaping () -> Void = {}
    ) {
        var seenPlayerIDs = Set<Int>()
        let comparePlayerIDs = initialComparePlayerIDs
            .filter { $0 > 0 && seenPlayerIDs.insert($0).inserted }
            .prefix(4)
        _viewModel = StateObject(
            wrappedValue: ScoutDeskViewModel(
                apiClient: apiClient,
                initialPhase: initialPhase
            )
        )
        _navigationPath = State(initialValue: initialPlayerID.map { [$0] } ?? [])
        _selectedPlayerIDs = State(initialValue: Array(comparePlayerIDs))
        _isComparePresented = State(initialValue: comparePlayerIDs.count >= 2)
        self.playerDetailAPIClient = playerDetailAPIClient
        self.onSignInRequested = onSignInRequested
        self.onVerificationRequested = onVerificationRequested
        self.onGolRequested = onGolRequested
    }

    init(
        viewModel: ScoutDeskViewModel,
        onSignInRequested: @escaping () -> Void = {},
        onVerificationRequested: @escaping () -> Void = {},
        onGolRequested: @escaping () -> Void = {}
    ) {
        _viewModel = StateObject(wrappedValue: viewModel)
        _navigationPath = State(initialValue: [])
        _selectedPlayerIDs = State(initialValue: [])
        _isComparePresented = State(initialValue: false)
        playerDetailAPIClient = APIClient()
        self.onSignInRequested = onSignInRequested
        self.onVerificationRequested = onVerificationRequested
        self.onGolRequested = onGolRequested
    }

    var body: some View {
        NavigationStack(path: $navigationPath) {
            ZStack {
                AcademyColors.background.ignoresSafeArea()

                ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 14) {
                        VStack(alignment: .leading, spacing: 10) {
                            FloodlightEyebrow(text: "THE SCOUT DESK")
                            (Text("Who are you\n").font(AcademyType.serif(44, relativeTo: .largeTitle))
                             + Text("looking for?").font(AcademyType.serif(44, italic: true, relativeTo: .largeTitle)).foregroundColor(AcademyColors.displayAccent))
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 16)
                        phaseSwitcher

                        if let description = viewModel.selectedPhase.description {
                            Text(description + " Missing detailed coverage is shown as —.")
                                .font(AcademyType.caption)
                                .foregroundStyle(AcademyColors.secondaryText)
                                .padding(.horizontal, 16)
                        }

                        filtersSection
                        resultsHeader.id("review-results")
                        resultsContent
                        leaderboardsSection.padding(.top, 20)
                    }
                    .padding(.vertical, 12)
                }.background(AcademyColors.background)
                .refreshable {
                    await viewModel.reload()
                }
                .accessibilityIdentifier("scout-desk-scroll")
                .allowsHitTesting(!isShowingInitialLoadingCard)
                .accessibilityHidden(isShowingInitialLoadingCard)
                #if DEBUG && targetEnvironment(simulator)
                .task(id: viewModel.isLoadingInitial) {
                    if !viewModel.isLoadingInitial, ["scout-empty", "scout-error"].contains(FloodlightPreview.screen ?? "") {
                        try? await Task.sleep(for: .milliseconds(800))
                        proxy.scrollTo("review-results", anchor: .top)
                    }
                }
                #endif
                }

                if isShowingInitialLoadingCard {
                    TimelineView(.periodic(from: .now, by: 1)) { _ in
                        WingLiftLoadingView(
                            feedback: viewModel.initialLoadFeedback()
                                ?? ScoutInitialLoadFeedback(elapsedSeconds: 0)
                        )
                    }
                    .transition(.opacity)
                    .zIndex(1)
                }
            }
            .animation(
                reduceMotion ? nil : .easeInOut(duration: 0.2),
                value: isShowingInitialLoadingCard
            )
            .navigationTitle("Scout Desk")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar(isShowingInitialLoadingCard ? .hidden : .automatic, for: .navigationBar)
            .toolbar(hidesTabBarForInitialGrace ? .hidden : .automatic, for: .tabBar)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    GolEntryButton(action: onGolRequested)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button {
                            presentAuthenticatedAdd { isWorldwideAddPresented = true }
                        } label: {
                            Label("Search worldwide", systemImage: "globe")
                        }
                        Button {
                            presentAuthenticatedAdd { isLocalAddPresented = true }
                        } label: {
                            Label("Add a local player", systemImage: "person.badge.plus")
                        }
                    } label: {
                        Image(systemName: "person.badge.plus")
                    }
                    .accessibilityLabel("Add a player")
                }
            }
            .navigationDestination(for: Int.self) { playerID in
                PlayerDetailView(
                    playerID: playerID,
                    apiClient: playerDetailAPIClient,
                    initialSeason: viewModel.selectedSeason,
                    onSignInRequested: onSignInRequested,
                    onVerificationRequested: onVerificationRequested
                )
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if !isShowingInitialLoadingCard, !selectedPlayerIDs.isEmpty {
                compareTray
                    .padding(.horizontal, 16)
                    .padding(.bottom, 6)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .sheet(isPresented: $isComparePresented) {
            NavigationStack {
                CompareView(
                    playerIDs: selectedPlayerIDs,
                    season: viewModel.selectedSeason
                )
            }
        }
        .sheet(isPresented: $isWorldwideAddPresented) {
            NavigationStack {
                WorldwidePlayerSearchView(
                    purpose: .addToList,
                    apiClient: playerDetailAPIClient
                )
            }
        }
        .sheet(isPresented: $isLocalAddPresented) {
            NavigationStack {
                LocalPlayerCreateView(
                    context: .scoutAdd,
                    apiClient: playerDetailAPIClient
                )
            }
        }
        .task(id: navigationPath.isEmpty) {
            guard navigationPath.isEmpty else { return }
            await viewModel.loadInitialIfNeeded()
        }
        .task(id: isShowingInitialLoadingCard) {
            guard isShowingInitialLoadingCard else {
                revealsTabBarDuringInitialLoad = false
                return
            }

            revealsTabBarDuringInitialLoad = false
            do {
                try await Task.sleep(nanoseconds: 2_500_000_000)
            } catch {
                return
            }
            guard !Task.isCancelled, isShowingInitialLoadingCard else { return }
            withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) {
                revealsTabBarDuringInitialLoad = true
            }
        }
    }

    private var isShowingInitialLoadingCard: Bool {
        navigationPath.isEmpty && viewModel.shouldShowWingLiftLoadingCard
    }

    private var hidesTabBarForInitialGrace: Bool {
        isShowingInitialLoadingCard && !revealsTabBarDuringInitialLoad
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
                            .font(AcademyType.caption.weight(.medium))
                            .padding(.horizontal, 14)
                            .padding(.vertical, 9)
                            .foregroundStyle(isSelected ? AcademyColors.onPrimary : AcademyColors.text)
                            .background(
                                isSelected ? AcademyColors.primaryFill : AcademyColors.surface,
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
        }.background(AcademyColors.background)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Phase of play")
    }

    private var leaderboardsSection: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                Label("LEADERBOARDS", systemImage: "chart.bar.fill")
                    .font(AcademyType.caption.weight(.medium))
                    .tracking(1.1)
                    .foregroundStyle(AcademyColors.accent)

                Spacer()

                Text(viewModel.leaderboardsSeasonLabel)
                    .font(AcademyType.caption2.weight(.medium))
                    .foregroundStyle(AcademyColors.secondaryText)
                    .monospacedDigit()

                if viewModel.isUpdatingCachedLeaderboards {
                    Label("Updating…", systemImage: "arrow.triangle.2.circlepath")
                        .font(AcademyType.caption2.weight(.medium))
                        .foregroundStyle(AcademyColors.secondaryText)
                } else if viewModel.isLoadingLeaderboards {
                    ProgressView()
                        .controlSize(.small)
                        .tint(AcademyColors.accent)
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
            }.background(AcademyColors.background)

        }
    }

    private var filtersSection: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                Text("FILTERS")
                    .font(AcademyType.caption.weight(.medium))
                    .tracking(1.1)
                    .foregroundStyle(AcademyColors.accent)
                Spacer()
                Text(
                    viewModel.isLoadingInitial && viewModel.players.isEmpty
                        ? "Loading…"
                        : "\(viewModel.totalPlayers.formatted()) \(viewModel.totalPlayers == 1 ? "player" : "players")"
                )
                    .font(AcademyType.caption)
                    .foregroundStyle(AcademyColors.secondaryText)
                    .monospacedDigit()
            }

            SeasonPicker(
                seasons: viewModel.seasons,
                selectedSeason: viewModel.selectedSeason
            ) { season in
                Task { await viewModel.selectSeason(season) }
            }

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 7) {
                    ForEach(ScoutAgePreset.allCases) { preset in
                        let isSelected = viewModel.selectedAgePreset == preset
                        Button {
                            Task { await viewModel.selectAgePreset(preset) }
                        } label: {
                            Text(preset.label)
                                .font(AcademyType.caption.weight(.medium))
                                .padding(.horizontal, 12)
                                .padding(.vertical, 7)
                                .foregroundStyle(isSelected ? AcademyColors.onPrimary : AcademyColors.text)
                                .background(
                                    isSelected ? AcademyColors.primaryFill : AcademyColors.elevatedSurface,
                                    in: Capsule()
                                )
                        }
                        .buttonStyle(.plain)
                        .accessibilityAddTraits(isSelected ? .isSelected : [])
                    }
                }
            }.background(AcademyColors.background)

            HStack(spacing: 9) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(AcademyColors.secondaryText)
                TextField("Search players by name…", text: searchBinding)
                    .textFieldStyle(.plain)
                    .textInputAutocapitalization(.words)
                    .autocorrectionDisabled()
                    .submitLabel(.search)
                    .accessibilityLabel("Search players")
                    .accessibilityIdentifier("scout-search")
                if !viewModel.searchText.isEmpty {
                    Button {
                        viewModel.setSearchText("")
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(AcademyColors.secondaryText)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Clear search")
                }
            }
            .padding(.horizontal, 12)
            .frame(minHeight: 46)
            .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
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
                FloodlightSectionHeader(title: "Players", counter: "\(viewModel.totalPlayers.formatted()) FOUND")
                Text("Ranked by \(viewModel.selectedSortLabel.lowercased())")
                    .font(AcademyType.caption)
                    .foregroundStyle(AcademyColors.secondaryText)
                Text(viewModel.playersSeasonLabel)
                    .font(AcademyType.caption2.weight(.medium))
                    .foregroundStyle(AcademyColors.secondaryText)
                    .monospacedDigit()
            }
            Spacer()
            if viewModel.isUpdatingCachedPlayers {
                Label("Updating…", systemImage: "arrow.triangle.2.circlepath")
                    .font(AcademyType.caption2.weight(.medium))
                    .foregroundStyle(AcademyColors.secondaryText)
            } else if viewModel.selectedSortOrder == .ascending {
                Label("Low to high", systemImage: "arrow.up")
                    .font(AcademyType.caption2)
                    .foregroundStyle(AcademyColors.secondaryText)
            }
        }
        .padding(.horizontal, 16)
    }

    @ViewBuilder
    private var resultsContent: some View {
        if viewModel.shouldShowInlineInitialLoader {
            TimelineView(.periodic(from: .now, by: 1)) { _ in
                VStack(spacing: 7) {
                    if let feedback = viewModel.initialLoadFeedback() {
                        ProgressView()
                            .tint(AcademyColors.accent)
                        Text(feedback.title)
                            .font(AcademyType.subheadline.weight(.semibold))
                        Text(feedback.detail)
                            .font(AcademyType.caption)
                            .foregroundStyle(AcademyColors.secondaryText)
                            .monospacedDigit()
                        Text("First visits can take about 30 seconds.")
                            .font(AcademyType.caption2)
                            .foregroundStyle(AcademyColors.secondaryText)
                    } else {
                        ProgressView("Scouting talent…")
                            .tint(AcademyColors.accent)
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 28)
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("initial-load-feedback")
            }
        } else if let message = viewModel.errorMessage, viewModel.players.isEmpty {
            ScoutErrorView(message: message) {
                Task { await viewModel.reload() }
            }
            .padding(.horizontal, 16)
        } else if viewModel.players.isEmpty {
            ContentUnavailableView {
                Label("No players found", systemImage: "person.3")
                .font(AcademyType.title2)
                .foregroundStyle(AcademyColors.text)
            } description: {
                Text("Try another filter, search worldwide, or add a pending local player profile.")
            } actions: {
                Button("Search worldwide") {
                    presentAuthenticatedAdd { isWorldwideAddPresented = true }
                }
                .buttonStyle(FloodlightPillStyle())
                .tint(AcademyColors.primaryFill)

                Button("Add a player") {
                    presentAuthenticatedAdd { isLocalAddPresented = true }
                }
                .buttonStyle(FloodlightPillStyle(variant: .outline))
            }
            .padding(.horizontal, 16)
        } else {
            if let message = viewModel.errorMessage {
                ScoutInlineErrorView(message: message) {
                    Task { await viewModel.reload() }
                }
                .padding(.horizontal, 16)
            }

            ForEach(viewModel.players, id: \.playerId) { player in
                ZStack(alignment: .topTrailing) {
                    NavigationLink(value: player.playerId) {
                        ScoutPlayerRow(player: player, phase: viewModel.selectedPhase)
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint("Opens player detail")
                    .accessibilityIdentifier("scout-player-\(player.playerId)")

                    VStack(spacing: 4) {
                        WatchlistStarButton(
                            playerID: player.playerId,
                            playerName: player.playerName,
                            onSignInRequested: onSignInRequested
                        )
                        compareSelectionButton(for: player)
                    }
                    .padding(.top, 9)
                    .padding(.trailing, 9)
                    .zIndex(1)
                }
                .padding(.horizontal, 16)
                .onAppear {
                    if player.playerId == viewModel.players.first?.playerId {
                        LaunchPerformance.markFirstRowRendered(source: viewModel.firstRowDataSource)
                    }
                    Task {
                        await viewModel.loadNextPageIfNeeded(currentPlayer: player)
                    }
                }
            }

            if viewModel.isLoadingNextPage {
                HStack {
                    Spacer()
                    ProgressView()
                        .tint(AcademyColors.accent)
                        .padding(.vertical, 16)
                    Spacer()
                }
            } else if let message = viewModel.paginationErrorMessage {
                VStack(spacing: 8) {
                    Text(message)
                        .font(AcademyType.footnote)
                        .foregroundStyle(AcademyColors.secondaryText)
                        .multilineTextAlignment(.center)
                    Button("Try loading more") {
                        Task { await viewModel.retryNextPage() }
                    }
                    .font(AcademyType.footnote.weight(.semibold))
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
            }
        }
    }

    private func presentAuthenticatedAdd(_ action: () -> Void) {
        if authManager.isAuthenticated {
            action()
        } else {
            onSignInRequested()
        }
    }

    private var compareTray: some View {
        HStack(spacing: 12) {
            Label(
                "\(selectedPlayerIDs.count) of 4 selected",
                systemImage: "rectangle.on.rectangle.angled"
            )
            .font(AcademyType.subheadline.weight(.semibold))
            .foregroundStyle(AcademyColors.text)

            Spacer(minLength: 0)

            Button("Compare") {
                isComparePresented = true
            }
            .buttonStyle(FloodlightPillStyle())
            .tint(AcademyColors.primaryFill)
            .controlSize(.small)
            .disabled(selectedPlayerIDs.count < 2)

            Button {
                withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) {
                    selectedPlayerIDs = []
                }
            } label: {
                Image(systemName: "xmark")
                    .font(AcademyType.caption.weight(.medium))
                    .frame(width: 28, height: 28)
            }
            .buttonStyle(.plain)
            .foregroundStyle(AcademyColors.secondaryText)
            .accessibilityLabel("Clear comparison selection")
        }
        .padding(.leading, 15)
        .padding(.trailing, 9)
        .padding(.vertical, 9)
        .background(.regularMaterial, in: Capsule())
        .overlay {
            Capsule()
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
        }

        .accessibilityElement(children: .contain)
    }

    private func compareSelectionButton(for player: ScoutPlayerSummary) -> some View {
        let isSelected = selectedPlayerIDs.contains(player.playerId)
        let hasReachedLimit = selectedPlayerIDs.count >= 4

        return Button {
            withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.18)) {
                if isSelected {
                    selectedPlayerIDs.removeAll { $0 == player.playerId }
                } else if !hasReachedLimit {
                    selectedPlayerIDs.append(player.playerId)
                }
            }
        } label: {
            Image(systemName: isSelected ? "checkmark.square.fill" : "square")
                .font(AcademyType.ui( 16, weight: .semibold))
                .foregroundStyle(isSelected ? AcademyColors.accent : AcademyColors.secondaryText)
                .frame(width: 44, height: 44)
                .background(AcademyColors.surface.opacity(0.96), in: Circle())
                .overlay {
                    Circle()
                        .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
                }
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .disabled(!isSelected && hasReachedLimit)
        .opacity(!isSelected && hasReachedLimit ? 0.45 : 1)
        .accessibilityLabel(
            isSelected
                ? "Remove \(player.playerName) from comparison"
                : "Add \(player.playerName) to comparison"
        )
        .accessibilityHint(hasReachedLimit && !isSelected ? "Four players are already selected" : "")
    }
}

private struct FilterMenuLabel: View {
    let iconName: String
    let value: String

    var body: some View {
        HStack(spacing: 7) {
            Image(systemName: iconName)
                .foregroundStyle(AcademyColors.accent)
            Text(value)
                .lineLimit(1)
                .minimumScaleFactor(0.6)
            Spacer(minLength: 2)
            Image(systemName: "chevron.down")
                .font(AcademyType.caption2.weight(.medium))
                .foregroundStyle(AcademyColors.secondaryText)
        }
        .font(AcademyType.caption.weight(.medium))
        .padding(.horizontal, 11)
        .frame(maxWidth: .infinity, minHeight: 42)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
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
                    .foregroundStyle(AcademyColors.accent)
                Text(definition.title.uppercased())
                    .font(AcademyType.caption2.weight(.medium))
                    .tracking(0.7)
                    .lineLimit(1)
                Spacer()
            }
            .padding(.horizontal, 12)
            .frame(height: 36)
            .background(AcademyColors.elevatedSurface)

            Divider()

            if isLoading, entries.isEmpty {
                VStack(spacing: 0) {
                    ForEach(0 ..< 3, id: \.self) { index in
                        HStack(spacing: 9) {
                            Circle()
                                .fill(AcademyColors.elevatedSurface)
                                .frame(width: 24, height: 24)
                            RoundedRectangle(cornerRadius: 4)
                                .fill(AcademyColors.elevatedSurface)
                                .frame(width: 120, height: 11)
                            Spacer()
                            RoundedRectangle(cornerRadius: 4)
                                .fill(AcademyColors.elevatedSurface)
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
                    .font(AcademyType.footnote)
                    .foregroundStyle(AcademyColors.secondaryText)
                    .frame(maxWidth: .infinity, minHeight: 129)
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(topEntries.enumerated()), id: \.element.playerId) { index, player in
                        NavigationLink(value: player.playerId) {
                            HStack(spacing: 9) {
                                RankChip(rank: index + 1)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(player.playerName)
                                        .font(AcademyType.caption.weight(.medium))
                                        .lineLimit(1)
                                    Text(player.loanTeamName ?? player.primaryTeamName ?? "Club unavailable")
                                        .font(AcademyType.caption2)
                                        .foregroundStyle(AcademyColors.secondaryText)
                                        .lineLimit(1)
                                }
                                Spacer(minLength: 5)
                                VStack(alignment: .trailing, spacing: 0) {
                                    Text(player.leaderboardValue(for: definition.metric))
                                        .font(AcademyType.caption.weight(.medium))
                                        .foregroundStyle(AcademyColors.accent)
                                        .monospacedDigit()
                                    Text(definition.suffix.uppercased())
                                        .font(AcademyType.ui( 8, weight: .medium))
                                        .foregroundStyle(AcademyColors.secondaryText)
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
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
        }
    }
}

private struct RankChip: View {
    let rank: Int

    var body: some View {
        Text(String(rank))
            .font(AcademyType.caption2.weight(.medium))
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
        rank == 1 ? AcademyColors.onPrimary : AcademyColors.text
    }

    private var backgroundColor: Color {
        switch rank {
        case 1: AcademyColors.primaryFill
        case 2: AcademyColors.accentSoft
        default: AcademyColors.elevatedSurface
        }
    }
}

struct ScoutPlayerRow: View {
    let player: ScoutPlayerSummary
    let phase: ScoutPhase

    var body: some View {
        VStack(spacing: 12) {
            PlayerIdentityHeader(
                name: player.playerName,
                photoURL: player.photoURL,
                position: player.position ?? "Position TBD",
                metadata: metadataLine,
                club: clubLine,
                status: player.status,
                reservesTrailingControlSpace: true
            )

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
        .floodlightRow()
        .accessibilityElement(children: .contain)
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

}

private struct StatCell: View {
    let label: String
    let spokenLabel: String
    let value: String

    var body: some View {
        VStack(spacing: 3) {
            Text(value)
                .font(AcademyType.serif(28, relativeTo: .title3))
                .monospacedDigit()
                .foregroundStyle(AcademyColors.text)
                .lineLimit(1)
                .minimumScaleFactor(0.72)
            Text(label)
                .font(AcademyType.caption2)
                .foregroundStyle(AcademyColors.secondaryText)
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

private struct ScoutErrorView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        ContentUnavailableView {
            Label("Scout Desk unavailable", systemImage: "wifi.exclamationmark")
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
