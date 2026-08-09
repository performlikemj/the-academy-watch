import SwiftUI

@MainActor
struct PlayerOnboardingView: View {
    @StateObject private var viewModel: PlayerSelfSearchViewModel
    private let apiClient: APIClient

    init(
        apiClient: APIClient,
        viewModel: PlayerSelfSearchViewModel? = nil
    ) {
        self.apiClient = apiClient
        _viewModel = StateObject(wrappedValue: viewModel ?? PlayerSelfSearchViewModel(apiClient: apiClient))
    }

    var body: some View {
        ZStack {
            AcademyColors.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    onboardingHeader
                    trackedSearch
                    results
                    nextSteps
                }
                .padding(18)
            }
        }
        .navigationTitle("Are you a player?")
        .navigationBarTitleDisplayMode(.inline)
        .accessibilityIdentifier("player-onboarding-search")
    }

    private var onboardingHeader: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("FIND YOUR PROFILE", systemImage: "person.crop.circle.badge.magnifyingglass")
                .font(.caption.weight(.bold))
                .tracking(1.1)
                .foregroundStyle(AcademyColors.claret)
            Text("Search for yourself")
                .font(.title2.weight(.bold))
            Text("Start with players already tracked by Academy Watch. If you find your profile, open it and use “This is me.” Direct player claims are for adults aged 18 or older.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(18)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 19))
    }

    private var trackedSearch: some View {
        VStack(alignment: .leading, spacing: 9) {
            TextField("Full name", text: $viewModel.query)
                .textContentType(.name)
                .textInputAutocapitalization(.words)
                .submitLabel(.search)
                .onSubmit { Task { await viewModel.search() } }
                .padding(13)
                .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
                .accessibilityIdentifier("player-onboarding-name-search")

            if let error = viewModel.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.footnote)
                    .foregroundStyle(Color(uiColor: .systemRed))
            }

            Button {
                Task { await viewModel.search() }
            } label: {
                HStack {
                    if viewModel.isLoading { ProgressView().controlSize(.small) }
                    Label("Search tracked players", systemImage: "magnifyingglass")
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .tint(AcademyColors.claretFill)
            .disabled(viewModel.isLoading)
        }
    }

    @ViewBuilder
    private var results: some View {
        if !viewModel.players.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Text("TRACKED RESULTS")
                    .font(.caption.weight(.bold))
                    .tracking(1.1)
                    .foregroundStyle(AcademyColors.claret)
                ForEach(viewModel.players, id: \.playerId) { player in
                    NavigationLink {
                        PlayerDetailView(playerID: player.playerId, apiClient: apiClient)
                    } label: {
                        PlayerIdentityHeader(
                            name: player.playerName,
                            photoURL: player.photoURL,
                            position: player.position,
                            metadata: [player.nationality, player.age.map { "\($0) yrs" }]
                                .compactMap { $0 }
                                .joined(separator: " · "),
                            club: player.loanTeamName ?? player.primaryTeamName ?? "Club unavailable",
                            status: player.status
                        )
                        .padding(14)
                        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 16))
                    }
                    .buttonStyle(.plain)
                }
            }
        } else if viewModel.hasSearched, !viewModel.isLoading, viewModel.errorMessage == nil {
            Label("No tracked profile matched that name.", systemImage: "person.crop.circle.badge.questionmark")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(14)
                .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 14))
        }
    }

    private var nextSteps: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("CAN'T FIND YOURSELF?")
                .font(.caption.weight(.bold))
                .tracking(1.1)
                .foregroundStyle(AcademyColors.claret)

            NavigationLink {
                WorldwidePlayerSearchView(purpose: .claimSelf, apiClient: apiClient)
            } label: {
                OnboardingActionRow(
                    icon: "globe",
                    title: "Search worldwide",
                    detail: "Check the global player universe before creating a community profile."
                )
            }
            .buttonStyle(.plain)

            NavigationLink {
                LocalPlayerCreateView(context: .claimant, apiClient: apiClient)
            } label: {
                OnboardingActionRow(
                    icon: "person.badge.plus",
                    title: "Create your profile",
                    detail: "For players outside official coverage. Your profile stays private while it is reviewed."
                )
            }
            .buttonStyle(.plain)
        }
    }
}

@MainActor
struct LocalPlayerCreateView: View {
    @StateObject private var viewModel: LocalPlayerFormViewModel

    init(
        context: LocalPlayerFormContext,
        apiClient: any OnboardingAPIClientProtocol = APIClient(),
        fixtureCreated: LocalPlayerCreateResponse? = nil
    ) {
        _viewModel = StateObject(
            wrappedValue: LocalPlayerFormViewModel(
                context: context,
                apiClient: apiClient,
                fixtureCreated: fixtureCreated
            )
        )
    }

    var body: some View {
        ZStack {
            AcademyColors.background.ignoresSafeArea()
            if let created = viewModel.created {
                LocalPlayerPendingDetailView(response: created)
            } else {
                form
            }
        }
        .navigationTitle(viewModel.context == .claimant ? "Create your profile" : "Add a player")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var form: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 7) {
                    Label("COMMUNITY PROFILE", systemImage: "person.crop.rectangle.badge.plus")
                        .font(.caption.weight(.bold))
                        .tracking(1.1)
                        .foregroundStyle(AcademyColors.claret)
                    Text(viewModel.context == .claimant ? "Tell us who you are" : "Add someone outside coverage")
                        .font(.title2.weight(.bold))
                    Text(formIntro)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                VStack(spacing: 15) {
                    OnboardingTextField(
                        title: "Full name",
                        placeholder: "Player name",
                        text: $viewModel.displayName,
                        error: viewModel.error(for: .displayName),
                        identifier: "local-player-name"
                    )

                    if viewModel.context == .claimant {
                        VStack(alignment: .leading, spacing: 7) {
                            Text("Your relationship to the player").font(.subheadline.weight(.semibold))
                            Picker("Relationship", selection: $viewModel.relationship) {
                                ForEach(LocalPlayerRelationship.allCases) { relationship in
                                    Text(relationship.displayName).tag(relationship)
                                }
                            }
                            .pickerStyle(.segmented)
                        }
                    }

                    OnboardingTextField(
                        title: "Position (optional)",
                        placeholder: "e.g. Centre-forward",
                        text: $viewModel.position,
                        error: viewModel.error(for: .position),
                        identifier: "local-player-position"
                    )
                    OnboardingTextField(
                        title: "Current club (optional)",
                        placeholder: "Club or academy",
                        text: $viewModel.clubName,
                        error: viewModel.error(for: .clubName),
                        identifier: "local-player-club"
                    )
                    OnboardingTextField(
                        title: "Country (optional)",
                        placeholder: "Country",
                        text: $viewModel.country,
                        error: viewModel.error(for: .country),
                        identifier: "local-player-country"
                    )
                    OnboardingTextField(
                        title: "City (optional)",
                        placeholder: "City",
                        text: $viewModel.city,
                        error: viewModel.error(for: .city),
                        identifier: "local-player-city"
                    )
                    OnboardingTextField(
                        title: "Birth year (optional)",
                        placeholder: "e.g. 2008",
                        text: $viewModel.birthYear,
                        error: viewModel.error(for: .birthYear),
                        keyboardType: .numberPad,
                        identifier: "local-player-birth-year"
                    )
                }
                .padding(17)
                .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 18))

                Label(
                    "Community profiles contain self-reported details, show no fabricated statistics, and remain private until review. Adults should manage their own claims; parents, guardians and agents must follow the community rules.",
                    systemImage: "checkmark.shield"
                )
                .font(.footnote)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

                if let error = viewModel.requestError {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .font(.footnote)
                        .foregroundStyle(Color(uiColor: .systemRed))
                        .fixedSize(horizontal: false, vertical: true)
                }

                Button {
                    Task { await viewModel.submit() }
                } label: {
                    HStack {
                        if viewModel.isSubmitting { ProgressView().controlSize(.small) }
                        Text(viewModel.isSubmitting ? "Submitting…" : "Submit for review")
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(AcademyColors.claretFill)
                .disabled(viewModel.isSubmitting)
                .accessibilityIdentifier("local-player-submit")
            }
            .padding(18)
        }
        .accessibilityIdentifier("local-player-create-form")
    }

    private var formIntro: String {
        if viewModel.context == .claimant {
            return "Use this only after checking tracked and worldwide search. Full name is required; everything else helps reviewers distinguish the right player."
        }
        return "This creates a pending local identity under the service's review claim. The app omits an invented scout relationship and sends only the player details."
    }
}

struct LocalPlayerPendingDetailView: View {
    let response: LocalPlayerCreateResponse

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Image(systemName: "clock.badge.checkmark.fill")
                            .font(.largeTitle)
                            .foregroundStyle(AcademyColors.loanAmber)
                        Spacer()
                        BadgeView(
                            text: "LOCAL · PENDING",
                            foregroundColor: AcademyColors.loanAmber,
                            backgroundColor: AcademyColors.loanAmber.opacity(0.12)
                        )
                    }
                    Text("Your profile is pending review")
                        .font(.title2.weight(.bold))
                    Text("Only you can see this pending community profile. It will not appear publicly until Academy Watch review is complete.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(19)
                .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 20))

                VStack(alignment: .leading, spacing: 12) {
                    Text(response.player.displayName).font(.title3.weight(.bold))
                    pendingRow("Position", response.player.position)
                    pendingRow("Current club", response.player.clubName)
                    pendingRow("Location", [response.player.city, response.player.country].compactMap { $0 }.joined(separator: ", "))
                    pendingRow("Birth year", response.player.birthYear.map(String.init))
                    Divider()
                    Text("No stats are shown for local profiles unless verified evidence is added later.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                .padding(18)
                .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 18))

                if let code = response.claim.verificationCode {
                    VStack(alignment: .leading, spacing: 7) {
                        Text("Claim verification code").font(.subheadline.weight(.semibold))
                        Text(code)
                            .font(.title3.monospaced().weight(.bold))
                            .textSelection(.enabled)
                        Text("Keep this code private until you are ready to place it on a public social profile for proof verification.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    .padding(17)
                    .background(AcademyColors.claretSoft, in: RoundedRectangle(cornerRadius: 16))
                }
            }
            .padding(18)
        }
        .accessibilityIdentifier("local-player-pending")
    }

    @ViewBuilder
    private func pendingRow(_ label: String, _ value: String?) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label).foregroundStyle(.secondary)
            Spacer()
            if let value, !value.isEmpty {
                Text(value).multilineTextAlignment(.trailing)
            } else {
                Text("—")
            }
        }
        .font(.subheadline)
    }
}

struct OnboardingActionRow: View {
    let icon: String
    let title: String
    let detail: String

    var body: some View {
        HStack(spacing: 13) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundStyle(AcademyColors.claret)
                .frame(width: 34)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.headline)
                Text(detail)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.leading)
            }
            Spacer(minLength: 5)
            Image(systemName: "chevron.right")
                .font(.subheadline.weight(.bold))
                .foregroundStyle(.tertiary)
        }
        .padding(16)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 17))
    }
}

struct OnboardingTextField: View {
    let title: String
    let placeholder: String
    @Binding var text: String
    let error: String?
    var keyboardType: UIKeyboardType = .default
    let identifier: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.subheadline.weight(.semibold))
            TextField(placeholder, text: $text)
                .keyboardType(keyboardType)
                .padding(12)
                .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 11))
                .accessibilityIdentifier(identifier)
            if let error {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(Color(uiColor: .systemRed))
            }
        }
    }
}
