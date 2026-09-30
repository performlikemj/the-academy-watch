import SwiftUI

enum WorldwideSearchPurpose: Equatable, Sendable {
    case claimSelf
    case addToList
}

@MainActor
struct WorldwidePlayerSearchView: View {
    @EnvironmentObject private var listsViewModel: FollowListsViewModel
    @StateObject private var viewModel: WorldwidePlayerSearchViewModel

    let purpose: WorldwideSearchPurpose
    private let playerDetailAPIClient: APIClient

    init(
        purpose: WorldwideSearchPurpose,
        apiClient: APIClient,
        viewModel: WorldwidePlayerSearchViewModel? = nil
    ) {
        self.purpose = purpose
        playerDetailAPIClient = apiClient
        _viewModel = StateObject(
            wrappedValue: viewModel ?? WorldwidePlayerSearchViewModel(apiClient: apiClient)
        )
    }

    var body: some View {
        ZStack {
            AcademyColors.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    header
                    searchField
                    if let confirmation = viewModel.confirmation {
                        confirmationCard(confirmation)
                    }
                    if let error = viewModel.errorMessage {
                        Label(error, systemImage: "exclamationmark.triangle.fill")
                            .font(AcademyType.footnote)
                            .foregroundStyle(AcademyColors.danger)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    results
                }
                .padding(18)
            }.background(AcademyColors.background)
        }
        .navigationTitle("Search worldwide")
        .navigationBarTitleDisplayMode(.inline)
        .accessibilityIdentifier("worldwide-player-search")
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 7) {
            Label("WORLDWIDE", systemImage: "globe.europe.africa.fill")
                .font(AcademyType.caption.weight(.medium))
                .tracking(1.1)
                .foregroundStyle(AcademyColors.accent)
            Text(purpose == .claimSelf ? "Check the global universe" : "Follow any player into a list")
                .font(AcademyType.title2)
            Text(
                purpose == .claimSelf
                    ? "Open the right profile, then use “This is me.” Player self-claims are reviewed and limited to adults aged 18 or older."
                    : "Players outside tracked coverage are clearly marked Worldwide. Adding one may create a shadow record so tracking can begin; no statistics are invented."
            )
            .font(AcademyType.subheadline)
            .foregroundStyle(AcademyColors.secondaryText)
            .fixedSize(horizontal: false, vertical: true)
        }
        .padding(18)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 19))
    }

    private var searchField: some View {
        HStack(spacing: 9) {
            TextField("Player name", text: $viewModel.query)
                .textContentType(.name)
                .textInputAutocapitalization(.words)
                .submitLabel(.search)
                .onSubmit { Task { await viewModel.search() } }
                .padding(13)
                .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10))
                .accessibilityIdentifier("worldwide-player-query")
            Button {
                Task { await viewModel.search() }
            } label: {
                if viewModel.isSearching {
                    ProgressView().controlSize(.small)
                } else {
                    Image(systemName: "magnifyingglass")
                }
            }
            .buttonStyle(FloodlightPillStyle())
            .tint(AcademyColors.primaryFill)
            .disabled(viewModel.isSearching)
            .accessibilityLabel("Search worldwide")
        }
    }

    @ViewBuilder
    private var results: some View {
        if viewModel.players.isEmpty, viewModel.hasSearched, !viewModel.isSearching,
           viewModel.errorMessage == nil {
            FloodlightEmptyState(title: "No worldwide players found", systemImage: "person.crop.circle.badge.questionmark", description: "Check the spelling or try a longer version of the name.")
        } else {
            LazyVStack(spacing: 11) {
                ForEach(viewModel.players) { player in
                    WorldwidePlayerRow(player: player) {
                        action(for: player)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func action(for player: WorldwidePlayer) -> some View {
        if purpose == .claimSelf {
            NavigationLink {
                PlayerDetailView(playerID: player.playerApiId, apiClient: playerDetailAPIClient)
            } label: {
                Label("Open", systemImage: "chevron.right")
            }
            .buttonStyle(FloodlightPillStyle(variant: .outline))
        } else {
            let availableLists = listsViewModel.lists.filter { !$0.isDefault }
            if availableLists.isEmpty {
                Text("Create a list first")
                    .font(AcademyType.caption)
                    .foregroundStyle(AcademyColors.secondaryText)
            } else {
                Menu {
                    ForEach(availableLists) { list in
                        Button(list.name) {
                            Task {
                                if await viewModel.add(player, to: list) {
                                    await listsViewModel.loadLists()
                                }
                            }
                        }
                        .disabled(list.containsPlayer(player.playerApiId))
                    }
                } label: {
                    if viewModel.pendingPlayerID == player.playerApiId {
                        ProgressView().controlSize(.small)
                    } else {
                        Label("Add", systemImage: "plus")
                    }
                }
                .buttonStyle(FloodlightPillStyle())
                .tint(AcademyColors.primaryFill)
                .disabled(viewModel.pendingPlayerID != nil)
            }
        }
    }

    private func confirmationCard(_ confirmation: WorldwideFollowConfirmation) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Label(
                confirmation.shadowCreated ? "Worldwide tracking started" : "Added to your list",
                systemImage: "checkmark.circle.fill"
            )
            .font(AcademyType.headline)
            .foregroundStyle(AcademyColors.good)
            Text("\(confirmation.playerName) was added to \(confirmation.listName).")
                .font(AcademyType.subheadline)
            if confirmation.shadowCreated {
                Text("A clearly badged shadow profile was created. Coverage may be limited while verified data is collected.")
                    .font(AcademyType.footnote)
                    .foregroundStyle(AcademyColors.secondaryText)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(AcademyColors.good.opacity(0.10), in: RoundedRectangle(cornerRadius: 10))
        .accessibilityIdentifier("worldwide-follow-confirmation")
    }
}

private struct WorldwidePlayerRow<Action: View>: View {
    let player: WorldwidePlayer
    @ViewBuilder let action: () -> Action

    var body: some View {
        HStack(spacing: 12) {
            AsyncImage(url: player.photoURL) { image in
                image.resizable().scaledToFill()
            } placeholder: {
                Image(systemName: "person.crop.circle.fill")
                    .resizable()
                    .foregroundStyle(AcademyColors.secondaryText)
            }
            .frame(width: 48, height: 48)
            .clipShape(Circle())

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(player.name).font(AcademyType.headline).lineLimit(1)
                    BadgeView(
                        text: player.tracked ? "TRACKED" : (player.shadow ? "WORLDWIDE SHADOW" : "WORLDWIDE"),
                        foregroundColor: player.tracked ? AcademyColors.good : AcademyColors.accent,
                        backgroundColor: player.tracked
                            ? AcademyColors.good.opacity(0.10)
                            : AcademyColors.accentSoft
                    )
                }
                Text(
                    [player.nationality, player.age.map { "\($0) yrs" }, player.clubName]
                        .compactMap { $0 }
                        .joined(separator: " · ")
                        .nonEmpty ?? "Details unavailable —"
                )
                .font(AcademyType.caption)
                .foregroundStyle(AcademyColors.secondaryText)
                .lineLimit(2)
            }
            Spacer(minLength: 4)
            action()
        }
        .padding(14)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10))
    }
}

private extension String {
    var nonEmpty: String? { isEmpty ? nil : self }
}
