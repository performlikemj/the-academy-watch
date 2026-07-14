import Foundation

enum ScoutPhase: String, CaseIterable, Decodable, Equatable, Identifiable, Sendable {
    case all
    case attack
    case midfield
    case defense
    case goalkeepers = "gk"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .all: "All"
        case .attack: "Attack"
        case .midfield: "Midfield"
        case .defense: "Defense"
        case .goalkeepers: "Goalkeepers"
        }
    }

    var position: String? {
        switch self {
        case .all: nil
        case .attack: "Attacker"
        case .midfield: "Midfielder"
        case .defense: "Defender"
        case .goalkeepers: "Goalkeeper"
        }
    }

    var description: String? {
        switch self {
        case .all:
            nil
        case .attack:
            "Attacking output across goals, shots and dribbles."
        case .midfield:
            "Creative output across key passes, passing and duels."
        case .defense:
            "Defensive output across tackles, duels and discipline."
        case .goalkeepers:
            "Goalkeeping output across saves, goals against and clean sheets."
        }
    }

    var defaultSortKey: String {
        switch self {
        case .all: "contributions"
        case .attack: "goals"
        case .midfield: "key_passes"
        case .defense: "tackles"
        case .goalkeepers: "clean_sheets"
        }
    }

    var compactStats: [ScoutCompactStat] {
        switch self {
        case .all:
            [.appearances, .goals, .assists, .minutes, .rating]
        case .attack:
            [.goals, .assists, .shots, .dribbles, .rating]
        case .midfield:
            [.keyPasses, .passes, .assists, .duelWinPercentage, .rating]
        case .defense:
            [.tackles, .tacklesPer90, .duelsWon, .duelWinPercentage, .cards]
        case .goalkeepers:
            [.saves, .savePercentage, .goalsConceded, .concededPer90, .cleanSheets]
        }
    }

    var sortOptions: [ScoutSortOption] {
        let base = [
            ScoutSortOption(key: "minutes", label: "Minutes played"),
            ScoutSortOption(key: "appearances", label: "Appearances"),
            ScoutSortOption(key: "rating", label: "Avg rating"),
            ScoutSortOption(key: "age", label: "Age"),
            ScoutSortOption(key: "name", label: "Name"),
        ]

        switch self {
        case .all:
            return [
                ScoutSortOption(key: "contributions", label: "Goal contributions"),
                ScoutSortOption(key: "goals", label: "Goals"),
                ScoutSortOption(key: "assists", label: "Assists"),
                ScoutSortOption(key: "per90", label: "G+A per 90"),
            ] + base
        case .attack:
            return [
                ScoutSortOption(key: "goals", label: "Goals"),
                ScoutSortOption(key: "assists", label: "Assists"),
                ScoutSortOption(key: "contributions", label: "Goal contributions"),
                ScoutSortOption(key: "per90", label: "G+A per 90"),
                ScoutSortOption(key: "shots", label: "Shots"),
                ScoutSortOption(key: "dribbles", label: "Dribbles won"),
                ScoutSortOption(key: "fouls_won", label: "Fouls won"),
            ] + base
        case .midfield:
            return [
                ScoutSortOption(key: "key_passes", label: "Key passes"),
                ScoutSortOption(key: "key_passes_per90", label: "Key passes per 90"),
                ScoutSortOption(key: "assists", label: "Assists"),
                ScoutSortOption(key: "passes", label: "Passes"),
                ScoutSortOption(key: "goals", label: "Goals"),
                ScoutSortOption(key: "duels_won", label: "Duels won"),
            ] + base
        case .defense:
            return [
                ScoutSortOption(key: "tackles", label: "Tackles"),
                ScoutSortOption(key: "tackles_per90", label: "Tackles per 90"),
                ScoutSortOption(key: "duels_won", label: "Duels won"),
            ] + base
        case .goalkeepers:
            return [
                ScoutSortOption(key: "clean_sheets", label: "Clean sheets"),
                ScoutSortOption(key: "saves", label: "Saves"),
                ScoutSortOption(key: "save_pct", label: "Save %"),
                ScoutSortOption(key: "conceded_per90", label: "Goals against per 90"),
                ScoutSortOption(key: "goals_conceded", label: "Goals against"),
            ] + base
        }
    }

    var leaderboards: [ScoutLeaderboardDefinition] {
        switch self {
        case .all:
            [
                ScoutLeaderboardDefinition(key: "top_scorers", title: "Top Scorers", iconName: "trophy.fill", metric: .goals, suffix: "goals"),
                ScoutLeaderboardDefinition(key: "top_assists", title: "Top Assists", iconName: "bolt.fill", metric: .assists, suffix: "assists"),
                ScoutLeaderboardDefinition(key: "most_minutes", title: "Most Minutes", iconName: "clock.fill", metric: .minutes, suffix: "mins"),
                ScoutLeaderboardDefinition(key: "best_per90", title: "Best G+A / 90", iconName: "speedometer", metric: .contributionsPer90, suffix: "/90"),
            ]
        case .attack:
            [
                ScoutLeaderboardDefinition(key: "top_scorers", title: "Top Scorers", iconName: "trophy.fill", metric: .goals, suffix: "goals"),
                ScoutLeaderboardDefinition(key: "top_assists", title: "Top Assists", iconName: "bolt.fill", metric: .assists, suffix: "assists"),
                ScoutLeaderboardDefinition(key: "best_per90", title: "Best G+A / 90", iconName: "speedometer", metric: .contributionsPer90, suffix: "/90"),
                ScoutLeaderboardDefinition(key: "most_shots", title: "Most Shots", iconName: "scope", metric: .shots, suffix: "shots"),
            ]
        case .midfield:
            [
                ScoutLeaderboardDefinition(key: "most_key_passes", title: "Most Key Passes", iconName: "sparkles", metric: .keyPasses, suffix: "key passes"),
                ScoutLeaderboardDefinition(key: "top_assists", title: "Top Assists", iconName: "bolt.fill", metric: .assists, suffix: "assists"),
                ScoutLeaderboardDefinition(key: "most_passes", title: "Most Passes", iconName: "paperplane.fill", metric: .passes, suffix: "passes"),
                ScoutLeaderboardDefinition(key: "best_kp_per90", title: "Best KP / 90", iconName: "speedometer", metric: .keyPassesPer90, suffix: "/90"),
            ]
        case .defense:
            [
                ScoutLeaderboardDefinition(key: "most_tackles", title: "Most Tackles", iconName: "figure.martial.arts", metric: .tackles, suffix: "tackles"),
                ScoutLeaderboardDefinition(key: "most_duels_won", title: "Most Duels Won", iconName: "shield.fill", metric: .duelsWon, suffix: "duels"),
                ScoutLeaderboardDefinition(key: "best_tackles_per90", title: "Best Tkl / 90", iconName: "speedometer", metric: .tacklesPer90, suffix: "/90"),
                ScoutLeaderboardDefinition(key: "most_minutes", title: "Most Minutes", iconName: "clock.fill", metric: .minutes, suffix: "mins"),
            ]
        case .goalkeepers:
            [
                ScoutLeaderboardDefinition(key: "most_clean_sheets", title: "Most Clean Sheets", iconName: "checkmark.shield.fill", metric: .cleanSheets, suffix: "CS"),
                ScoutLeaderboardDefinition(key: "most_saves", title: "Most Saves", iconName: "hand.raised.fill", metric: .saves, suffix: "saves"),
                ScoutLeaderboardDefinition(key: "best_conceded_per90", title: "Best GA / 90", iconName: "speedometer", metric: .concededPer90, suffix: "/90"),
                ScoutLeaderboardDefinition(key: "most_minutes", title: "Most Minutes", iconName: "clock.fill", metric: .minutes, suffix: "mins"),
            ]
        }
    }

    static func fromLaunchArguments(_ arguments: [String]) -> ScoutPhase {
        guard let flagIndex = arguments.firstIndex(of: "-initialPhase"),
              arguments.indices.contains(flagIndex + 1),
              let phase = ScoutPhase(rawValue: arguments[flagIndex + 1])
        else {
            return .all
        }
        return phase
    }
}

enum ScoutAgePreset: String, CaseIterable, Equatable, Identifiable, Sendable {
    case all
    case under18 = "u18"
    case under21 = "u21"
    case under23 = "u23"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .all: "All"
        case .under18: "U18"
        case .under21: "U21"
        case .under23: "U23"
        }
    }

    var maximumAge: Int? {
        switch self {
        case .all: nil
        case .under18: 18
        case .under21: 21
        case .under23: 23
        }
    }
}

enum ScoutStatusFilter: String, CaseIterable, Equatable, Identifiable, Sendable {
    case all
    case academy
    case onLoan = "on_loan"
    case firstTeam = "first_team"
    case sold
    case released
    case left

    var id: String { rawValue }

    var label: String {
        switch self {
        case .all: "All statuses"
        case .academy: "Academy"
        case .onLoan: "On loan"
        case .firstTeam: "First team"
        case .sold: "Sold"
        case .released: "Released"
        case .left: "Left"
        }
    }

    var queryValue: String? {
        self == .all ? nil : rawValue
    }
}

enum ScoutSortOrder: String, Equatable, Sendable {
    case ascending = "asc"
    case descending = "desc"

    static func defaultOrder(for sortKey: String) -> ScoutSortOrder {
        switch sortKey {
        case "name", "age", "goals_conceded", "conceded_per90":
            .ascending
        default:
            .descending
        }
    }
}

struct ScoutSortOption: Equatable, Identifiable, Sendable {
    let key: String
    let label: String

    var id: String { key }
}

struct ScoutPlayersRequest: Equatable, Sendable {
    let page: Int
    let perPage: Int
    let search: String?
    let position: String?
    let status: String?
    let maximumAge: Int?
    let sort: String
    let order: ScoutSortOrder
}

struct ScoutLeaderboardsRequest: Equatable, Sendable {
    let phase: ScoutPhase
    let limit: Int
    let position: String?
    let status: String?
    let maximumAge: Int?
}

enum ScoutCompactStat: Sendable {
    case appearances
    case goals
    case assists
    case minutes
    case rating
    case shots
    case dribbles
    case keyPasses
    case passes
    case duelWinPercentage
    case tackles
    case tacklesPer90
    case duelsWon
    case cards
    case saves
    case savePercentage
    case goalsConceded
    case concededPer90
    case cleanSheets

    var label: String {
        switch self {
        case .appearances: "Apps"
        case .goals: "G"
        case .assists: "A"
        case .minutes: "Mins"
        case .rating: "Rating"
        case .shots: "Shots"
        case .dribbles: "Drb"
        case .keyPasses: "KP"
        case .passes: "Passes"
        case .duelWinPercentage: "Duel%"
        case .tackles: "Tkl"
        case .tacklesPer90: "Tkl90"
        case .duelsWon: "DuelsW"
        case .cards: "Cards"
        case .saves: "Saves"
        case .savePercentage: "Save%"
        case .goalsConceded: "GA"
        case .concededPer90: "GA90"
        case .cleanSheets: "CS"
        }
    }

    var spokenLabel: String {
        switch self {
        case .appearances: "Appearances"
        case .goals: "Goals"
        case .assists: "Assists"
        case .minutes: "Minutes"
        case .rating: "Rating"
        case .shots: "Shots"
        case .dribbles: "Successful dribbles"
        case .keyPasses: "Key passes"
        case .passes: "Passes"
        case .duelWinPercentage: "Duel win percentage"
        case .tackles: "Tackles"
        case .tacklesPer90: "Tackles per 90"
        case .duelsWon: "Duels won"
        case .cards: "Yellow and red cards"
        case .saves: "Saves"
        case .savePercentage: "Save percentage"
        case .goalsConceded: "Goals against"
        case .concededPer90: "Goals against per 90"
        case .cleanSheets: "Clean sheets"
        }
    }
}

struct ScoutLeaderboardDefinition: Equatable, Identifiable, Sendable {
    let key: String
    let title: String
    let iconName: String
    let metric: ScoutLeaderboardMetric
    let suffix: String

    var id: String { key }
}

enum ScoutLeaderboardMetric: Equatable, Sendable {
    case goals
    case assists
    case minutes
    case contributionsPer90
    case shots
    case keyPasses
    case passes
    case keyPassesPer90
    case tackles
    case duelsWon
    case tacklesPer90
    case cleanSheets
    case saves
    case concededPer90
}

extension ScoutPlayerSummary {
    func displayValue(for stat: ScoutCompactStat) -> String {
        switch stat {
        case .appearances:
            return String(appearances)
        case .goals:
            return String(goals)
        case .assists:
            return String(assists)
        case .minutes:
            return compactNumber(minutesPlayed)
        case .rating:
            return avgRating.map { String(format: "%.1f", $0) } ?? Self.emDash
        case .shots:
            return detailedInteger(shotsTotal)
        case .dribbles:
            return detailedInteger(dribblesSuccess)
        case .keyPasses:
            return detailedInteger(keyPasses)
        case .passes:
            return detailedInteger(passesTotal, compact: true)
        case .duelWinPercentage:
            return detailedDecimal(duelWinPct, suffix: "%", maximumFractionDigits: 1)
        case .tackles:
            return detailedInteger(tackles)
        case .tacklesPer90:
            return detailedDecimal(tacklesPer90)
        case .duelsWon:
            return detailedInteger(duelsWon)
        case .cards:
            guard hasDetailedStats, let yellows, let reds else { return Self.emDash }
            return "\(yellows)/\(reds)"
        case .saves:
            return detailedInteger(saves)
        case .savePercentage:
            return detailedDecimal(savePct, suffix: "%", maximumFractionDigits: 1)
        case .goalsConceded:
            return detailedInteger(goalsConceded)
        case .concededPer90:
            return detailedDecimal(concededPer90)
        case .cleanSheets:
            return detailedInteger(cleanSheets)
        }
    }

    func leaderboardValue(for metric: ScoutLeaderboardMetric) -> String {
        switch metric {
        case .goals: return String(goals)
        case .assists: return String(assists)
        case .minutes: return minutesPlayed.formatted()
        case .contributionsPer90: return formattedDecimal(contributionsPer90)
        case .shots: return detailedInteger(shotsTotal)
        case .keyPasses: return detailedInteger(keyPasses)
        case .passes: return hasDetailedStats ? passesTotal?.formatted() ?? Self.emDash : Self.emDash
        case .keyPassesPer90: return detailedDecimal(keyPassesPer90)
        case .tackles: return detailedInteger(tackles)
        case .duelsWon: return detailedInteger(duelsWon)
        case .tacklesPer90: return detailedDecimal(tacklesPer90)
        case .cleanSheets: return detailedInteger(cleanSheets)
        case .saves: return detailedInteger(saves)
        case .concededPer90: return detailedDecimal(concededPer90)
        }
    }

    private static let emDash = "—"

    private func detailedInteger(_ value: Int?, compact: Bool = false) -> String {
        guard hasDetailedStats, let value else { return Self.emDash }
        return compact ? compactNumber(value) : String(value)
    }

    private func detailedDecimal(
        _ value: Double?,
        suffix: String = "",
        maximumFractionDigits: Int = 2
    ) -> String {
        guard hasDetailedStats, let value else { return Self.emDash }
        return formattedDecimal(value, maximumFractionDigits: maximumFractionDigits) + suffix
    }
}

private func compactNumber(_ value: Int) -> String {
    guard abs(value) >= 1_000 else { return String(value) }
    return formattedDecimal(Double(value) / 1_000, maximumFractionDigits: 1) + "k"
}

private func formattedDecimal(_ value: Double?, maximumFractionDigits: Int = 2) -> String {
    guard let value else { return "—" }
    var result = String(format: "%.\(maximumFractionDigits)f", value)
    while result.contains("."), result.last == "0" {
        result.removeLast()
    }
    if result.last == "." {
        result.removeLast()
    }
    return result
}
