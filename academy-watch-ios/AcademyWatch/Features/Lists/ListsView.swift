import SwiftUI

enum ListsRoute: Hashable {
    case list(Int)
    case player(Int)
}

@MainActor
struct ListsView: View {
    let onSignInRequested: () -> Void
    let onVerificationRequested: () -> Void

    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var viewModel: FollowListsViewModel
    @State private var isCreatingList = false
    @State private var newListName = ""
    @State private var isWorldwideSearchPresented = false

    private let apiClient: any FollowListsAPIClientProtocol
    private let playerDetailAPIClient: APIClient

    init(
        apiClient: any FollowListsAPIClientProtocol,
        playerDetailAPIClient: APIClient = APIClient(),
        onSignInRequested: @escaping () -> Void,
        onVerificationRequested: @escaping () -> Void = {}
    ) {
        self.apiClient = apiClient
        self.playerDetailAPIClient = playerDetailAPIClient
        self.onSignInRequested = onSignInRequested
        self.onVerificationRequested = onVerificationRequested
    }

    var body: some View {
        NavigationStack {
            ZStack {
                AcademyColors.background.ignoresSafeArea()
                content
            }
            .navigationTitle("Lists")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: ListsRoute.self) { route in
                switch route {
                case let .list(listID):
                    FollowListDetailView(listID: listID, apiClient: apiClient)
                case let .player(playerID):
                    PlayerDetailView(
                        playerID: playerID,
                        apiClient: playerDetailAPIClient,
                        onSignInRequested: onSignInRequested,
                        onVerificationRequested: onVerificationRequested
                    )
                }
            }
            .toolbar {
                if authManager.isAuthenticated {
                    ToolbarItemGroup(placement: .topBarTrailing) {
                        Button {
                            newListName = ""
                            isCreatingList = true
                        } label: {
                            Image(systemName: "plus")
                        }
                        .accessibilityLabel("Create list")
                        .accessibilityIdentifier("lists-create")

                        Button {
                            isWorldwideSearchPresented = true
                        } label: {
                            Image(systemName: "globe.badge.chevron.backward")
                        }
                        .accessibilityLabel("Search worldwide players")

                        Menu {
                            Button(role: .destructive) {
                                authManager.signOut()
                            } label: {
                                Label("Sign Out", systemImage: "rectangle.portrait.and.arrow.right")
                            }
                        } label: {
                            Image(systemName: "person.crop.circle")
                                .accessibilityLabel("Account")
                        }
                    }
                }
            }
            .alert("New List", isPresented: $isCreatingList) {
                TextField("List name", text: $newListName)
                    .accessibilityIdentifier("lists-name")
                Button("Cancel", role: .cancel) {}
                Button("Create") {
                    let name = newListName
                    Task { await viewModel.createList(name: name) }
                }
                .disabled(newListName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .accessibilityIdentifier("lists-create-submit")
            } message: {
                Text("Give this group a clear scouting name.")
            }
            .sheet(isPresented: $isWorldwideSearchPresented) {
                NavigationStack {
                    WorldwidePlayerSearchView(
                        purpose: .addToList,
                        apiClient: playerDetailAPIClient
                    )
                }
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if !authManager.isAuthenticated {
            signedOutState
        } else if viewModel.isLoading, viewModel.lists.isEmpty {
            ProgressView("Loading your lists…")
                .tint(AcademyColors.accent)
        } else if let message = viewModel.errorMessage, viewModel.lists.isEmpty {
            errorState(message: message)
        } else if viewModel.lists.isEmpty {
            emptyState
        } else {
            lists
        }
    }

    private var signedOutState: some View {
        VStack(spacing: 16) {
            Image(systemName: "list.bullet.rectangle.portrait.fill")
                .font(AcademyType.ui( 58))
                .foregroundStyle(AcademyColors.accent)
                .accessibilityHidden(true)

            VStack(spacing: 7) {
                Text("Sign in to organize your scouting")
                    .font(AcademyType.title3)
                Text("Group players into named lists and keep each live shortlist in one place.")
                    .font(AcademyType.subheadline)
                    .foregroundStyle(AcademyColors.secondaryText)
                    .multilineTextAlignment(.center)
            }

            Button("Sign In", action: onSignInRequested)
                .buttonStyle(FloodlightPillStyle())
                .tint(AcademyColors.primaryFill)
                .controlSize(.large)
        }
        .padding(28)
        .frame(maxWidth: 430)
    }

    private var emptyState: some View {
        VStack(spacing: 14) {
            FloodlightEmptyState(title: "No lists yet", systemImage: "list.bullet.rectangle", description: "Create a list, then add a tracked player or search worldwide.")
            Button("Create List") {
                newListName = ""
                isCreatingList = true
            }
            .accessibilityIdentifier("lists-create")
            .buttonStyle(FloodlightPillStyle())
            .tint(AcademyColors.primaryFill)

            Button("Search worldwide") {
                isWorldwideSearchPresented = true
            }
            .buttonStyle(FloodlightPillStyle(variant: .outline))
        }
        .padding(24)
    }

    private func errorState(message: String) -> some View {
        ContentUnavailableView {
            Label("Lists unavailable", systemImage: "wifi.exclamationmark")
                .font(AcademyType.title2)
                .foregroundStyle(AcademyColors.text)
        } description: {
            Text(message)
        } actions: {
            Button("Try Again") {
                Task { await viewModel.loadLists() }
            }
            .buttonStyle(FloodlightPillStyle())
            .tint(AcademyColors.primaryFill)
        }
        .padding(24)
    }

    private var lists: some View {
        List {
            if let message = viewModel.errorMessage {
                Section {
                    Label(message, systemImage: "exclamationmark.triangle.fill")
                        .font(AcademyType.footnote)
                        .foregroundStyle(AcademyColors.secondaryText)
                }.listRowBackground(AcademyColors.background)
            }

            ForEach(viewModel.lists) { list in
                NavigationLink(value: ListsRoute.list(list.id)) {
                    FollowListRow(list: list)
                }
                .accessibilityIdentifier("list-\(list.id)")
                .listRowBackground(AcademyColors.surface)
                .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                    if !list.isDefault {
                        Button(role: .destructive) {
                            Task { await viewModel.deleteList(list) }
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                        .accessibilityIdentifier("list-delete-\(list.id)")
                        .disabled(viewModel.pendingListIDs.contains(list.id))
                    }
                }
            }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .refreshable {
            await viewModel.loadLists()
        }
    }
}

private struct FollowListRow: View {
    let list: FollowList

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: list.isDefault ? "star.square.fill" : "list.bullet.rectangle.fill")
                .font(AcademyType.title2)
                .foregroundStyle(AcademyColors.accent)
                .frame(width: 32)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 7) {
                    Text(list.name)
                        .font(AcademyType.headline)
                        .lineLimit(1)
                    if list.isDefault {
                        BadgeView(text: "Default")
                    }
                    if !list.isActive {
                        BadgeView(
                            text: "Paused",
                            foregroundColor: AcademyColors.secondaryText,
                            backgroundColor: AcademyColors.elevatedSurface
                        )
                    }
                }
                Text("\(list.followCount) \(list.followCount == 1 ? "follow" : "follows")")
                    .font(AcademyType.subheadline)
                    .foregroundStyle(AcademyColors.secondaryText)
            }
        }
        .padding(.vertical, 5)
        .accessibilityElement(children: .combine)
    }
}

@MainActor
struct FollowListDetailView: View {
    let listID: Int

    @EnvironmentObject private var listsViewModel: FollowListsViewModel
    @EnvironmentObject private var watchlistViewModel: WatchlistViewModel
    @StateObject private var detailViewModel: FollowListDetailViewModel

    init(listID: Int, apiClient: any FollowListsAPIClientProtocol) {
        self.listID = listID
        _detailViewModel = StateObject(
            wrappedValue: FollowListDetailViewModel(listID: listID, apiClient: apiClient)
        )
    }

    var body: some View {
        ZStack {
            AcademyColors.background.ignoresSafeArea()
            if let list = listsViewModel.list(id: listID) {
                detailList(list)
            } else {
                FloodlightEmptyState(title: "List unavailable", systemImage: "list.bullet.rectangle", description: "This list may have been removed.")
            }
        }
        .navigationTitle(listsViewModel.list(id: listID)?.name ?? "List")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await detailViewModel.loadIfNeeded()
        }
    }

    private func detailList(_ list: FollowList) -> some View {
        List {
            Section {
                if list.follows.isEmpty {
                    Text("Add a player from a player profile. Club, location and saved-filter follows created on the web will also appear here.")
                        .font(AcademyType.subheadline)
                        .foregroundStyle(AcademyColors.secondaryText)
                } else {
                    ForEach(list.follows) { follow in
                        followRow(follow, list: list)
                    }
                }
            } header: {
                Text("Follows · \(list.followCount)")
            }.listRowBackground(AcademyColors.background)

            Section {
                if let message = detailViewModel.errorMessage, detailViewModel.players.isEmpty {
                    VStack(spacing: 10) {
                        Label(message, systemImage: "exclamationmark.triangle.fill")
                            .font(AcademyType.footnote)
                            .foregroundStyle(AcademyColors.secondaryText)
                        Button("Try Again") {
                            Task { await detailViewModel.reload() }
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                } else if detailViewModel.players.isEmpty, detailViewModel.isLoading {
                    HStack {
                        Spacer()
                        ProgressView("Resolving players…")
                            .tint(AcademyColors.accent)
                        Spacer()
                    }
                    .padding(.vertical, 18)
                } else if detailViewModel.players.isEmpty {
                    Text("No players resolve from this list yet.")
                        .font(AcademyType.subheadline)
                        .foregroundStyle(AcademyColors.secondaryText)
                } else {
                    ForEach(detailViewModel.players) { player in
                        NavigationLink(value: ListsRoute.player(player.playerApiId)) {
                            ResolvedPlayerCard(player: player)
                        }
                        .buttonStyle(.plain)
                        .listRowInsets(EdgeInsets(top: 7, leading: 16, bottom: 7, trailing: 16))
                        .listRowSeparator(.visible)
                        .listRowBackground(Color.clear)
                    }

                    if detailViewModel.canLoadMore {
                        Button {
                            Task { await detailViewModel.loadMore() }
                        } label: {
                            HStack {
                                Spacer()
                                if detailViewModel.isLoading {
                                    ProgressView()
                                        .controlSize(.small)
                                }
                                Text(detailViewModel.isLoading ? "Loading…" : "Load more")
                                Spacer()
                            }
                        }
                        .disabled(detailViewModel.isLoading)
                    }
                }
            } header: {
                Text("Resolved players · \(detailViewModel.players.count) of \(detailViewModel.total)")
            }.listRowBackground(AcademyColors.background)
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .refreshable {
            async let lists: Void = listsViewModel.loadLists()
            async let resolved: Void = detailViewModel.reload()
            _ = await (lists, resolved)
        }
    }

    @ViewBuilder
    private func followRow(_ follow: Follow, list: FollowList) -> some View {
        if follow.kind == .player, let playerID = follow.selector.playerApiId {
            NavigationLink(value: ListsRoute.player(playerID)) {
                FollowLabelRow(follow: follow)
            }
            .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                Button(role: .destructive) {
                    Task {
                        let didRemove: Bool
                        if list.isDefault {
                            didRemove = await watchlistViewModel.removeFromWatchlist(playerID: playerID)
                            if didRemove {
                                await listsViewModel.synchronizeAfterWatchlistMutation()
                            }
                        } else {
                            didRemove = await listsViewModel.removeFollow(follow, from: list.id)
                        }
                        if didRemove {
                            await detailViewModel.reload()
                        }
                    }
                } label: {
                    Label("Remove", systemImage: "trash")
                }
                .disabled(
                    list.isDefault
                        ? watchlistViewModel.isPending(playerID: playerID)
                        : listsViewModel.pendingFollowIDs.contains(follow.id)
                )
            }
        } else {
            FollowLabelRow(follow: follow)
        }
    }
}

private struct FollowLabelRow: View {
    let follow: Follow

    var body: some View {
        HStack(spacing: 11) {
            Image(systemName: follow.kind.iconName)
                .foregroundStyle(AcademyColors.accent)
                .frame(width: 22)
            VStack(alignment: .leading, spacing: 2) {
                Text(follow.label)
                    .font(AcademyType.subheadline.weight(.medium))
                    .lineLimit(2)
                if let note = follow.note, !note.isEmpty {
                    Text(note)
                        .font(AcademyType.caption)
                        .italic()
                        .foregroundStyle(AcademyColors.secondaryText)
                        .lineLimit(2)
                } else if follow.kind != .player {
                    Text(follow.kind.label)
                        .font(AcademyType.caption)
                        .foregroundStyle(AcademyColors.secondaryText)
                }
            }
        }
        .padding(.vertical, 3)
    }
}

private struct ResolvedPlayerCard: View {
    let player: ResolvedFollowPlayer

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if player.source == "shadow" {
                BadgeView(
                    text: "WORLDWIDE SHADOW",
                    foregroundColor: AcademyColors.accent,
                    backgroundColor: AcademyColors.accentSoft
                )
            }
            PlayerIdentityHeader(
                name: player.playerName ?? "Player #\(player.playerApiId)",
                photoURL: player.photoURL,
                position: nil,
                metadata: player.source == "shadow" ? "Worldwide player · limited coverage" : nil,
                club: player.teamName ?? "Club unavailable",
                status: player.status
            )
        }
        .padding(14)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
        }
    }
}
