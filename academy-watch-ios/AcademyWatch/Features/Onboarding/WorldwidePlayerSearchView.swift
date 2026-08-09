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
                            .font(.footnote)
                            .foregroundStyle(Color(uiColor: .systemRed))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    results
                }
                .padding(18)
            }
        }
        .navigationTitle("Search worldwide")
        .navigationBarTitleDisplayMode(.inline)
        .accessibilityIdentifier("worldwide-player-search")
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 7) {
            Label("WORLDWIDE", systemImage: "globe.europe.africa.fill")
                .font(.caption.weight(.bold))
                .tracking(1.1)
                .foregroundStyle(AcademyColors.claret)
            Text(purpose == .claimSelf ? "Check the global universe" : "Follow any player into a list")
                .font(.title2.weight(.bold))
            Text(
                purpose == .claimSelf
                    ? "Open the right profile, then use “This is me.” Player self-claims are reviewed and limited to adults aged 18 or older."
                    : "Players outside tracked coverage are clearly marked Worldwide. Adding one may create a shadow record so tracking can begin; no statistics are invented."
            )
            .font(.subheadline)
            .foregroundStyle(.secondary)
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
                .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 12))
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
            .buttonStyle(.borderedProminent)
            .tint(AcademyColors.claretFill)
            .disabled(viewModel.isSearching)
            .accessibilityLabel("Search worldwide")
        }
    }

    @ViewBuilder
    private var results: some View {
        if viewModel.players.isEmpty, viewModel.hasSearched, !viewModel.isSearching,
           viewModel.errorMessage == nil {
            ContentUnavailableView(
                "No worldwide players found",
                systemImage: "person.crop.circle.badge.questionmark",
                description: Text("Check the spelling or try a longer version of the name.")
            )
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
            .buttonStyle(.bordered)
        } else {
            let availableLists = listsViewModel.lists.filter { !$0.isDefault }
            if availableLists.isEmpty {
                Text("Create a list first")
                    .font(.caption)
                    .foregroundStyle(.secondary)
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
                .buttonStyle(.borderedProminent)
                .tint(AcademyColors.claretFill)
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
            .font(.headline)
            .foregroundStyle(AcademyColors.positiveGreen)
            Text("\(confirmation.playerName) was added to \(confirmation.listName).")
                .font(.subheadline)
            if confirmation.shadowCreated {
                Text("A clearly badged shadow profile was created. Coverage may be limited while verified data is collected.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(AcademyColors.positiveGreen.opacity(0.10), in: RoundedRectangle(cornerRadius: 16))
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
                    .foregroundStyle(.tertiary)
            }
            .frame(width: 48, height: 48)
            .clipShape(Circle())

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(player.name).font(.headline).lineLimit(1)
                    BadgeView(
                        text: player.tracked ? "TRACKED" : (player.shadow ? "WORLDWIDE SHADOW" : "WORLDWIDE"),
                        foregroundColor: player.tracked ? AcademyColors.positiveGreen : AcademyColors.claret,
                        backgroundColor: player.tracked
                            ? AcademyColors.positiveGreen.opacity(0.10)
                            : AcademyColors.claretSoft
                    )
                }
                Text(
                    [player.nationality, player.age.map { "\($0) yrs" }, player.clubName]
                        .compactMap { $0 }
                        .joined(separator: " · ")
                        .nonEmpty ?? "Details unavailable —"
                )
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
            }
            Spacer(minLength: 4)
            action()
        }
        .padding(14)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 16))
    }
}

private extension String {
    var nonEmpty: String? { isEmpty ? nil : self }
}
