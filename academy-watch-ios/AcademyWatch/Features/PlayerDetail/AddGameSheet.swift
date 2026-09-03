import SwiftUI

/// Mirrors the web "add a game" form semantics for POST
/// `/players/<signed id>/matches`: the same required fields, the same bounds,
/// and goalkeeper-only saves / goals-conceded.
@MainActor
final class AddGameViewModel: ObservableObject {
    @Published var matchDate: Date
    @Published var competition = ""
    @Published var opponent = ""
    @Published var homeAway: PlayerMatchVenue = .home
    @Published var useScore = false
    @Published var resultFor = 0
    @Published var resultAgainst = 0
    @Published var minutes = 0
    @Published var goals = 0
    @Published var assists = 0
    @Published var yellows = 0
    @Published var reds = 0
    @Published var useGoalkeeperEvents = false
    @Published var saves = 0
    @Published var goalsConceded = 0
    @Published var note = ""

    @Published private(set) var isSubmitting = false
    @Published private(set) var formError: String?
    @Published private(set) var requestError: String?
    @Published private(set) var didSave = false

    /// Backend bounds (player_matches.py `_entry_values`).
    static let maximumMinutes = 130
    static let maximumCount = 20

    let playerID: Int
    private let apiClient: any PlayerMatchAPIClientProtocol
    private let calendar: Calendar

    init(
        playerID: Int,
        apiClient: any PlayerMatchAPIClientProtocol = APIClient(),
        calendar: Calendar = .current
    ) {
        self.playerID = playerID
        self.apiClient = apiClient
        self.calendar = calendar
        // Yesterday: the backend rejects dates more than one day in the future.
        matchDate = calendar.date(byAdding: .day, value: -1, to: calendar.startOfDay(for: Date()))
            ?? calendar.startOfDay(for: Date())
    }

    var selectableDateRange: ClosedRange<Date> {
        let lower = calendar.date(from: DateComponents(year: 1970, month: 1, day: 1)) ?? .distantPast
        let upper = calendar.date(byAdding: .day, value: 1, to: calendar.startOfDay(for: Date())) ?? Date()
        return lower ... upper
    }

    @discardableResult
    func validate() -> Bool {
        let trimmedOpponent = opponent.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedCompetition = competition.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedNote = note.trimmingCharacters(in: .whitespacesAndNewlines)

        if trimmedOpponent.isEmpty {
            formError = "Enter the opponent."
            return false
        }
        if trimmedOpponent.count > 120 {
            formError = "Opponent must be 120 characters or fewer."
            return false
        }
        if trimmedCompetition.count > 120 {
            formError = "Competition must be 120 characters or fewer."
            return false
        }
        if trimmedNote.count > 500 {
            formError = "Note must be 500 characters or fewer."
            return false
        }
        formError = nil
        return true
    }

    var submission: PlayerMatchSubmission {
        PlayerMatchSubmission(
            matchDate: Self.matchDateString(from: matchDate, calendar: calendar),
            competition: optional(competition),
            opponent: opponent.trimmingCharacters(in: .whitespacesAndNewlines),
            homeAway: homeAway,
            resultFor: useScore ? resultFor : nil,
            resultAgainst: useScore ? resultAgainst : nil,
            minutes: minutes,
            goals: goals,
            assists: assists,
            yellows: yellows,
            reds: reds,
            saves: useGoalkeeperEvents ? saves : nil,
            goalsConceded: useGoalkeeperEvents ? goalsConceded : nil,
            note: optional(note)
        )
    }

    func submit() async -> PlayerMatchMutationResponse? {
        guard !isSubmitting, validate() else { return nil }
        isSubmitting = true
        requestError = nil
        defer { isSubmitting = false }

        do {
            let response = try await apiClient.createPlayerMatch(playerID: playerID, submission: submission)
            didSave = true
            return response
        } catch {
            requestError = (error as? LocalizedError)?.errorDescription
                ?? "We couldn't save this game. Check your connection and try again."
            return nil
        }
    }

    /// The exact `YYYY-MM-DD` form accepted by `_parse_match_date`, read in the
    /// user's calendar so the picked day never shifts across time zones.
    nonisolated static func matchDateString(from date: Date, calendar: Calendar = .current) -> String {
        let components = calendar.dateComponents([.year, .month, .day], from: date)
        return String(
            format: "%04ld-%02ld-%02ld",
            components.year ?? 0,
            components.month ?? 0,
            components.day ?? 0
        )
    }

    private func optional(_ value: String) -> String? {
        let value = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return value.isEmpty ? nil : value
    }
}

/// Sheet mirroring the web add-a-game form for owned local players.
@MainActor
struct AddGameSheet: View {
    @StateObject private var viewModel: AddGameViewModel
    @Environment(\.dismiss) private var dismiss
    let playerName: String
    let isGoalkeeper: Bool
    let onSaved: (PlayerMatchMutationResponse) -> Void

    init(
        playerID: Int,
        playerName: String,
        isGoalkeeper: Bool,
        apiClient: any PlayerMatchAPIClientProtocol = APIClient(),
        onSaved: @escaping (PlayerMatchMutationResponse) -> Void
    ) {
        _viewModel = StateObject(wrappedValue: AddGameViewModel(playerID: playerID, apiClient: apiClient))
        self.playerName = playerName
        self.isGoalkeeper = isGoalkeeper
        self.onSaved = onSaved
    }

    var body: some View {
        NavigationStack {
            ZStack {
                AcademyColors.background.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        header
                        formCard
                        if let requestError = viewModel.requestError {
                            Label(requestError, systemImage: "exclamationmark.triangle.fill")
                                .font(.footnote)
                                .foregroundStyle(Color(uiColor: .systemRed))
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        saveButton
                    }
                    .padding(18)
                }
            }
            .navigationTitle("Add a game")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
            .accessibilityIdentifier("add-game-sheet")
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 7) {
            Label("ADD A GAME", systemImage: "figure.soccer")
                .font(.caption.weight(.bold))
                .tracking(1.1)
                .foregroundStyle(AcademyColors.claret)
            Text("Record a game for \(playerName)")
                .font(.title2.weight(.bold))
            Text("Self-reported games stay attached to this profile and refresh the season totals on save.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var formCard: some View {
        VStack(alignment: .leading, spacing: 15) {
            DatePicker(
                "Match date",
                selection: $viewModel.matchDate,
                in: viewModel.selectableDateRange,
                displayedComponents: .date
            )
            .accessibilityIdentifier("add-game-date")

            Picker("Venue", selection: $viewModel.homeAway) {
                ForEach(PlayerMatchVenue.allCases) { venue in
                    Text(venue.displayName).tag(venue)
                }
            }
            .pickerStyle(.segmented)
            .accessibilityIdentifier("add-game-venue")

            OnboardingTextField(
                title: "Opponent",
                placeholder: "Opponent name",
                text: $viewModel.opponent,
                error: nil,
                identifier: "add-game-opponent"
            )
            OnboardingTextField(
                title: "Competition (optional)",
                placeholder: "e.g. U18 Premier League",
                text: $viewModel.competition,
                error: nil,
                identifier: "add-game-competition"
            )

            Toggle(isOn: $viewModel.useScore) {
                Text("Record a score").font(.subheadline.weight(.semibold))
            }
            .accessibilityIdentifier("add-game-use-score")
            if viewModel.useScore {
                Stepper(value: $viewModel.resultFor, in: 0 ... Self.countBound) {
                    scoreRow(label: "Score for", value: viewModel.resultFor)
                }
                Stepper(value: $viewModel.resultAgainst, in: 0 ... Self.countBound) {
                    scoreRow(label: "Score against", value: viewModel.resultAgainst)
                }
            }

            Stepper(value: $viewModel.minutes, in: 0 ... AddGameViewModel.maximumMinutes) {
                scoreRow(label: "Minutes", value: viewModel.minutes)
            }

            Stepper(value: $viewModel.goals, in: 0 ... Self.countBound) {
                scoreRow(label: "Goals", value: viewModel.goals)
            }
            Stepper(value: $viewModel.assists, in: 0 ... Self.countBound) {
                scoreRow(label: "Assists", value: viewModel.assists)
            }
            Stepper(value: $viewModel.yellows, in: 0 ... Self.countBound) {
                scoreRow(label: "Yellow cards", value: viewModel.yellows)
            }
            Stepper(value: $viewModel.reds, in: 0 ... Self.countBound) {
                scoreRow(label: "Red cards", value: viewModel.reds)
            }

            if isGoalkeeper {
                Toggle(isOn: $viewModel.useGoalkeeperEvents) {
                    Text("Record saves and goals conceded").font(.subheadline.weight(.semibold))
                }
                .accessibilityIdentifier("add-game-use-goalkeeper-events")
                if viewModel.useGoalkeeperEvents {
                    Stepper(value: $viewModel.saves, in: 0 ... Self.countBound) {
                        scoreRow(label: "Saves", value: viewModel.saves)
                    }
                    Stepper(value: $viewModel.goalsConceded, in: 0 ... Self.countBound) {
                        scoreRow(label: "Goals conceded", value: viewModel.goalsConceded)
                    }
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("Note (optional)").font(.subheadline.weight(.semibold))
                TextField("Anything worth remembering", text: $viewModel.note, axis: .vertical)
                    .lineLimit(3 ... 5)
                    .padding(12)
                    .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 11))
                    .accessibilityIdentifier("add-game-note")
            }

            if let formError = viewModel.formError {
                Label(formError, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(Color(uiColor: .systemRed))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(17)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 18))
    }

    private static let countBound = AddGameViewModel.maximumCount

    private func scoreRow(label: String, value: Int) -> some View {
        HStack {
            Text(label)
            Spacer()
            Text(value.formatted())
                .font(.subheadline.weight(.bold))
                .monospacedDigit()
                .foregroundStyle(AcademyColors.claret)
        }
    }

    private var saveButton: some View {
        Button {
            Task {
                if let response = await viewModel.submit() {
                    onSaved(response)
                    dismiss()
                }
            }
        } label: {
            HStack {
                if viewModel.isSubmitting { ProgressView().controlSize(.small) }
                Text(viewModel.isSubmitting ? "Saving…" : "Save game")
            }
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderedProminent)
        .tint(AcademyColors.claretFill)
        .disabled(viewModel.isSubmitting)
        .accessibilityIdentifier("add-game-save")
    }
}
