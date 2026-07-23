import Foundation

struct CompareResponse: Decodable, Equatable, Sendable {
    let players: [ComparePlayer]
    let missingIds: [Int]
}

struct ComparePlayer: Decodable, Equatable, Identifiable, Sendable {
    let profile: ComparePlayerProfile
    let totals: CompareTotals
    let per90: ComparePer90
    let career: CompareCareer?
    let availability: CompareAvailability?

    var id: Int { profile.playerId }
}

struct ComparePlayerProfile: Decodable, Equatable, Sendable {
    let playerId: Int
    let playerName: String
    let playerPhoto: String?
    let position: String?
    let age: Int?
    let status: String?
    let nationality: String?
    let primaryTeamName: String?
    let loanTeamName: String?
    let ownerTeamName: String?

    var photoURL: URL? {
        playerPhoto.flatMap(URL.init(string:))
    }

    var clubName: String? {
        loanTeamName ?? primaryTeamName
    }

    var isGoalkeeper: Bool {
        guard let position else { return false }
        return position.caseInsensitiveCompare("Goalkeeper") == .orderedSame
            || position.caseInsensitiveCompare("G") == .orderedSame
    }
}

/// Compare totals intentionally decode every statistic as optional. Full-coverage
/// players include the complete bucket, while limited-coverage fallback payloads
/// can omit detailed match statistics entirely.
struct CompareTotals: Decodable, Equatable, Sendable {
    let appearances: Int?
    let goals: Int?
    let assists: Int?
    let minutesPlayed: Int?
    let avgRating: Double?
    let shotsTotal: Int?
    let shotsOn: Int?
    let passesTotal: Int?
    let keyPasses: Int?
    let dribblesAttempts: Int?
    let dribblesSuccess: Int?
    let tackles: Int?
    let interceptions: Int?
    let duelsTotal: Int?
    let duelsWon: Int?
    let foulsDrawn: Int?
    let yellows: Int?
    let reds: Int?
    let saves: Int?
    let goalsConceded: Int?
    let penaltySaved: Int?
    let cleanSheets: Int?
    let statsCoverage: String?
}

struct ComparePer90: Decodable, Equatable, Sendable {
    let goals: Double?
    let assists: Double?
    let goalContributions: Double?
    let keyPasses: Double?
    let shotsTotal: Double?
    let dribblesSuccess: Double?
    let tackles: Double?
    let interceptions: Double?
    let duelsWon: Double?
}

struct CompareCareer: Decodable, Equatable, Sendable {
    let firstTeamApps: Int?
    let youthApps: Int?
    let loanApps: Int?
    let goals: Int?
    let assists: Int?
    let firstTeamDebutSeason: Int?
    let firstTeamDebutClub: String?
}

struct CompareAvailability: Decodable, Equatable, Sendable {
    let totalAbsences: Int?
    let lastReason: String?
}

enum CompareHighlighting {
    /// Mirrors the web comparison table: null values do not compete, normal
    /// rows highlight the maximum only when it is positive, lower-is-better
    /// rows highlight the minimum (including a real best value of zero), and
    /// every tied winner is highlighted when at least two players are shown.
    static func highlightedIndices(
        in values: [Double?],
        lowerIsBetter: Bool
    ) -> Set<Int> {
        guard values.count > 1 else { return [] }

        let candidates = values.compactMap { $0 }
        guard let best = lowerIsBetter ? candidates.min() : candidates.max() else {
            return []
        }
        guard lowerIsBetter || best > 0 else { return [] }

        return Set(values.indices.filter { values[$0] == best })
    }
}
