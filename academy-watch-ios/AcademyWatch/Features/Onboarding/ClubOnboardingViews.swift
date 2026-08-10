import SwiftUI

@MainActor
struct ClubOnboardingView: View {
    @StateObject private var viewModel: ClubClaimViewModel
    @State private var showsForm: Bool
    private let loadsOnAppear: Bool

    init(
        apiClient: any OnboardingAPIClientProtocol = APIClient(),
        viewModel: ClubClaimViewModel? = nil,
        initiallyShowsForm: Bool = false,
        loadsOnAppear: Bool = true
    ) {
        _viewModel = StateObject(wrappedValue: viewModel ?? ClubClaimViewModel(apiClient: apiClient))
        _showsForm = State(initialValue: initiallyShowsForm)
        self.loadsOnAppear = loadsOnAppear
    }

    var body: some View {
        ZStack {
            AcademyColors.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    header
                    benefits
                    if showsForm || viewModel.claims.isEmpty {
                        claimForm
                    } else {
                        Button {
                            showsForm = true
                        } label: {
                            Label("Claim another club", systemImage: "plus")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(AcademyColors.claretFill)
                    }
                    claimsSection
                }
                .padding(18)
            }
        }
        .navigationTitle("Represent a club")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            guard loadsOnAppear else { return }
            await viewModel.load()
        }
        .accessibilityIdentifier("club-onboarding")
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("CLUB IDENTITY", systemImage: "shield.lefthalf.filled")
                .font(.caption.weight(.bold))
                .tracking(1.1)
                .foregroundStyle(AcademyColors.claret)
            Text("Represent a club or academy?")
                .font(.title2.weight(.bold))
            Text("Claims are reviewed. Use your real role and select the exact club you represent; pending claims do not grant club access.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding(18)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 19))
    }

    private var benefits: some View {
        VStack(alignment: .leading, spacing: 9) {
            Label("What verified clubs get", systemImage: "checkmark.shield.fill")
                .font(.headline)
                .foregroundStyle(AcademyColors.positiveGreen)
            Text("Roster vouching is available now: approved club officials can confirm player affiliations and help review player claims connected to their club. Roster, match video and player reports live in the web console.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(16)
        .background(AcademyColors.positiveGreen.opacity(0.09), in: RoundedRectangle(cornerRadius: 16))
    }

    @ViewBuilder
    private var claimForm: some View {
        if let submitted = viewModel.submittedClaim {
            submittedClaimCard(submitted)
        } else {
        VStack(alignment: .leading, spacing: 15) {
            Text("CLAIM A CLUB")
                .font(.caption.weight(.bold))
                .tracking(1.1)
                .foregroundStyle(AcademyColors.claret)

            HStack(spacing: 8) {
                TextField("Search club or academy", text: $viewModel.searchQuery)
                    .submitLabel(.search)
                    .onSubmit { Task { await viewModel.searchClubs() } }
                    .padding(12)
                    .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 11))
                    .accessibilityIdentifier("club-search")
                Button {
                    Task { await viewModel.searchClubs() }
                } label: {
                    if viewModel.isSearching { ProgressView().controlSize(.small) }
                    else { Image(systemName: "magnifyingglass") }
                }
                .buttonStyle(.bordered)
                .disabled(viewModel.isSearching)
            }

            if let error = viewModel.error(for: .club) {
                Text(error).font(.caption).foregroundStyle(Color(uiColor: .systemRed))
            }

            if !viewModel.searchResults.apiTeams.isEmpty || !viewModel.searchResults.localClubs.isEmpty {
                clubResults
            }

            if let selected = viewModel.selectedClub {
                Label(selected.name, systemImage: "checkmark.circle.fill")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(AcademyColors.positiveGreen)
            }

            OnboardingTextField(
                title: "Your role title",
                placeholder: "e.g. Academy director",
                text: $viewModel.roleTitle,
                error: viewModel.error(for: .roleTitle),
                identifier: "club-role-title"
            )

            VStack(alignment: .leading, spacing: 6) {
                Text("Evidence or context (optional)").font(.subheadline.weight(.semibold))
                TextEditor(text: $viewModel.message)
                    .frame(minHeight: 86)
                    .padding(8)
                    .scrollContentBackground(.hidden)
                    .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 11))
                    .accessibilityIdentifier("club-claim-message")
                if let error = viewModel.error(for: .message) {
                    Text(error).font(.caption).foregroundStyle(Color(uiColor: .systemRed))
                }
            }

            if let error = viewModel.errorMessage {
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
                    Text(viewModel.isSubmitting ? "Submitting…" : "Submit club claim")
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .tint(AcademyColors.claretFill)
            .disabled(viewModel.isSubmitting)
            .accessibilityIdentifier("club-claim-submit")
        }
        .padding(17)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 18))
        .accessibilityIdentifier("club-claim-form")
        }
    }

    private func submittedClaimCard(_ claim: ClubClaim) -> some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack {
                Image(systemName: "clock.badge.checkmark.fill")
                    .font(.title)
                    .foregroundStyle(AcademyColors.loanAmber)
                Spacer()
                BadgeView(
                    text: "PENDING",
                    foregroundColor: AcademyColors.loanAmber,
                    backgroundColor: AcademyColors.loanAmber.opacity(0.12)
                )
            }
            Text("Club claim pending review").font(.title3.weight(.bold))
            Text("Your claim for \(claim.clubName ?? "this club") was submitted. Pending claims grant no club permissions.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            if let code = claim.verificationCode {
                Text("Verification code").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                Text(code).font(.title3.monospaced().weight(.bold)).textSelection(.enabled)
            }
            Text("Open the claim below to add a public HTTPS proof URL. Proof checking helps review but does not approve the claim automatically.")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(18)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 18))
        .accessibilityIdentifier("club-claim-pending")
    }

    private var clubResults: some View {
        VStack(spacing: 7) {
            ForEach(viewModel.searchResults.apiTeams) { club in
                ClubSearchResultButton(
                    name: club.name,
                    detail: [club.country, "Official database"].compactMap { $0 }.joined(separator: " · "),
                    isSelected: viewModel.selectedClub == .apiTeam(club)
                ) {
                    viewModel.select(.apiTeam(club))
                }
            }
            ForEach(viewModel.searchResults.localClubs) { club in
                ClubSearchResultButton(
                    name: club.name,
                    detail: [club.city, club.country, "Community club · \(club.status)"].compactMap { $0 }.joined(separator: " · "),
                    isSelected: viewModel.selectedClub == .localClub(club)
                ) {
                    viewModel.select(.localClub(club))
                }
            }
        }
    }

    @ViewBuilder
    private var claimsSection: some View {
        if viewModel.isLoading, viewModel.claims.isEmpty {
            ProgressView("Loading your club claims…")
                .frame(maxWidth: .infinity)
        } else if !viewModel.claims.isEmpty {
            VStack(alignment: .leading, spacing: 11) {
                Text("MY CLUB CLAIMS")
                    .font(.caption.weight(.bold))
                    .tracking(1.1)
                    .foregroundStyle(AcademyColors.claret)
                ForEach(viewModel.claims) { claim in
                    NavigationLink {
                        ClubClaimDetailView(claimID: claim.id, viewModel: viewModel)
                    } label: {
                        HStack(spacing: 12) {
                            Image(systemName: "shield.fill")
                                .font(.title2)
                                .foregroundStyle(AcademyColors.claret)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(claim.clubName ?? "Club #\(claim.teamApiId ?? claim.localClubId ?? 0)")
                                    .font(.headline)
                                Text(claim.roleTitle).font(.subheadline).foregroundStyle(.secondary)
                            }
                            Spacer()
                            BadgeView(text: claim.status.uppercased())
                            Image(systemName: "chevron.right").foregroundStyle(.tertiary)
                        }
                        .padding(15)
                        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 16))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

private struct ClubSearchResultButton: View {
    let name: String
    let detail: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(name).font(.subheadline.weight(.semibold))
                    Text(detail).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(isSelected ? AcademyColors.positiveGreen : Color.secondary.opacity(0.55))
            }
            .padding(11)
            .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 11))
        }
        .buttonStyle(.plain)
    }
}

@MainActor
struct ClubClaimDetailView: View {
    let claimID: Int
    @ObservedObject var viewModel: ClubClaimViewModel
    @State private var proofURL = ""
    @State private var verified = false

    private var claim: ClubClaim? { viewModel.claims.first { $0.id == claimID } }

    var body: some View {
        ZStack {
            AcademyColors.background.ignoresSafeArea()
            ScrollView {
                if let claim {
                    VStack(alignment: .leading, spacing: 17) {
                        VStack(alignment: .leading, spacing: 9) {
                            HStack {
                                Text(claim.clubName ?? "Club claim").font(.title2.weight(.bold))
                                Spacer()
                                BadgeView(text: claim.status.uppercased())
                            }
                            Text(claim.roleTitle).font(.subheadline).foregroundStyle(.secondary)
                            Text("Verification: \(claim.verificationStatus.replacingOccurrences(of: "_", with: " "))")
                                .font(.footnote.weight(.semibold))
                        }
                        .padding(18)
                        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 18))

                        if claim.status == "pending" {
                            proofStep(claim)
                        } else if claim.status == "approved" {
                            VStack(alignment: .leading, spacing: 11) {
                                LegalSafariLink(destination: .clubConsole) {
                                    Label("Manage your club on the web", systemImage: "arrow.up.right.square")
                                        .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.borderedProminent)
                                .tint(AcademyColors.claretFill)
                                .accessibilityIdentifier("club-console-link")

                                Text("Roster, match video and player reports live in the web console.")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            .padding(17)
                            .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 18))
                        }

                        Text(claimStatusCopy(claim.status))
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(18)
                }
            }
        }
        .navigationTitle("Club claim")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { proofURL = claim?.verificationProofUrl ?? "" }
    }

    private func claimStatusCopy(_ status: String) -> String {
        if status == "pending" {
            return "Pending claims grant no club permissions. Once approved, club officials can vouch for roster affiliations and manage roster, match video and player reports in the web console."
        }
        if status == "approved" {
            return "Your approved claim also lets you vouch for roster affiliations connected to your club."
        }
        return "This claim does not grant club permissions. You can review its status here and submit a new claim if appropriate."
    }

    private func proofStep(_ claim: ClubClaim) -> some View {
        VStack(alignment: .leading, spacing: 11) {
            Label("Proof verification", systemImage: "link.badge.plus")
                .font(.headline)
            if let code = claim.verificationCode {
                Text("Place this code on a public club-controlled social profile:")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Text(code).font(.title3.monospaced().weight(.bold)).textSelection(.enabled)
            }
            TextField("https://public-proof-url", text: $proofURL)
                .keyboardType(.URL)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .padding(12)
                .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 11))
            if let error = viewModel.error(for: .proofURL) {
                Text(error).font(.caption).foregroundStyle(Color(uiColor: .systemRed))
            }
            if verified {
                Label("Proof check completed. Review is still required.", systemImage: "checkmark.circle.fill")
                    .font(.footnote)
                    .foregroundStyle(AcademyColors.positiveGreen)
            }
            Button("Check public proof") {
                Task { verified = await viewModel.verify(claim, proofURL: proofURL) }
            }
            .buttonStyle(.borderedProminent)
            .tint(AcademyColors.claretFill)
            .disabled(viewModel.verifyingClaimID != nil || proofURL.isEmpty)
        }
        .padding(17)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 18))
    }
}
