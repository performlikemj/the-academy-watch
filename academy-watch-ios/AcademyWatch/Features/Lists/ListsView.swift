import SwiftUI

enum ListsRoute: Hashable {
    case list(Int)
    case player(Int)
}

@MainActor
struct ListsView: View {
    let onSignInRequested: () -> Void

    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var viewModel: FollowListsViewModel
    @State private var isCreatingList = false
    @State private var newListName = ""

    private let apiClient: any FollowListsAPIClientProtocol

    init(
        apiClient: any FollowListsAPIClientProtocol,
        onSignInRequested: @escaping () -> Void
    ) {
        self.apiClient = apiClient
        self.onSignInRequested = onSignInRequested
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
                        onSignInRequested: onSignInRequested
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
                Button("Cancel", role: .cancel) {}
                Button("Create") {
                    let name = newListName
                    Task { await viewModel.createList(name: name) }
                }
                .disabled(newListName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            } message: {
                Text("Give this group a clear scouting name.")
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if !authManager.isAuthenticated {
            signedOutState
        } else if viewModel.isLoading, viewModel.lists.isEmpty {
            ProgressView("Loading your lists…")
                .tint(AcademyColors.claret)
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
                .font(.system(size: 58))
                .foregroundStyle(AcademyColors.claret)
                .accessibilityHidden(true)

            VStack(spacing: 7) {
                Text("Sign in to organize your scouting")
                    .font(.title3.weight(.bold))
                Text("Group players into named lists and keep each live shortlist in one place.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            Button("Sign In", action: onSignInRequested)
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
        }
        .padding(28)
        .frame(maxWidth: 430)
    }

    private var emptyState: some View {
        ContentUnavailableView {
            Label("No lists yet", systemImage: "list.bullet.rectangle")
        } description: {
            Text("Create a list, then add players from any player profile.")
        } actions: {
            Button("Create List") {
                newListName = ""
                isCreatingList = true
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(24)
    }

    private func errorState(message: String) -> some View {
        ContentUnavailableView {
            Label("Lists unavailable", systemImage: "wifi.exclamationmark")
        } description: {
            Text(message)
        } actions: {
            Button("Try Again") {
                Task { await viewModel.loadLists() }
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(24)
    }

    private var lists: some View {
        List {
            if let message = viewModel.errorMessage {
                Section {
                    Label(message, systemImage: "exclamationmark.triangle.fill")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }

            ForEach(viewModel.lists) { list in
                NavigationLink(value: ListsRoute.list(list.id)) {
                    FollowListRow(list: list)
                }
                .listRowBackground(AcademyColors.surface)
                .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                    if !list.isDefault {
                        Button(role: .destructive) {
                            Task { await viewModel.deleteList(list) }
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                        .disabled(viewModel.pendingListIDs.contains(list.id))
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
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
                .font(.title2)
                .foregroundStyle(AcademyColors.claret)
                .frame(width: 32)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 7) {
                    Text(list.name)
                        .font(.headline)
                        .lineLimit(1)
                    if list.isDefault {
                        BadgeView(text: "Default")
                    }
                    if !list.isActive {
                        BadgeView(
                            text: "Paused",
                            foregroundColor: .secondary,
                            backgroundColor: Color(uiColor: .tertiarySystemFill)
                        )
                    }
                }
                Text("\(list.followCount) \(list.followCount == 1 ? "follow" : "follows")")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 5)
        .accessibilityElement(children: .combine)
    }
}

@MainActor
private struct FollowListDetailView: View {
    let listID: Int

    @EnvironmentObject private var listsViewModel: FollowListsViewModel
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
                ContentUnavailableView(
                    "List unavailable",
                    systemImage: "list.bullet.rectangle",
                    description: Text("This list may have been removed.")
                )
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
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(list.follows) { follow in
                        followRow(follow, list: list)
                    }
                }
            } header: {
                Text("Follows · \(list.followCount)")
            }

            Section {
                if let message = detailViewModel.errorMessage, detailViewModel.players.isEmpty {
                    VStack(spacing: 10) {
                        Label(message, systemImage: "exclamationmark.triangle.fill")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
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
                            .tint(AcademyColors.claret)
                        Spacer()
                    }
                    .padding(.vertical, 18)
                } else if detailViewModel.players.isEmpty {
                    Text("No players resolve from this list yet.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(detailViewModel.players) { player in
                        NavigationLink(value: ListsRoute.player(player.playerApiId)) {
                            ResolvedPlayerCard(player: player)
                        }
                        .buttonStyle(.plain)
                        .listRowInsets(EdgeInsets(top: 7, leading: 16, bottom: 7, trailing: 16))
                        .listRowSeparator(.hidden)
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
            }
        }
        .listStyle(.insetGrouped)
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
                        if await listsViewModel.removeFollow(follow, from: list.id) {
                            await detailViewModel.reload()
                        }
                    }
                } label: {
                    Label("Remove", systemImage: "trash")
                }
                .disabled(listsViewModel.pendingFollowIDs.contains(follow.id))
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
                .foregroundStyle(AcademyColors.claret)
                .frame(width: 22)
            VStack(alignment: .leading, spacing: 2) {
                Text(follow.label)
                    .font(.subheadline.weight(.medium))
                    .lineLimit(2)
                if let note = follow.note, !note.isEmpty {
                    Text(note)
                        .font(.caption)
                        .italic()
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                } else if follow.kind != .player {
                    Text(follow.kind.label)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 3)
    }
}

private struct ResolvedPlayerCard: View {
    let player: ResolvedFollowPlayer

    var body: some View {
        PlayerIdentityHeader(
            name: player.playerName ?? "Player #\(player.playerApiId)",
            photoURL: player.photoURL,
            position: nil,
            metadata: player.source == "shadow" ? "Worldwide player" : nil,
            club: player.teamName ?? "Club unavailable",
            status: player.status
        )
        .padding(14)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
        }
    }
}
