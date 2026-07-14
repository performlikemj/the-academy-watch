import Foundation

struct ScoutPlayersResponse: Decodable, Equatable, Sendable {
    let players: [ScoutPlayerSummary]
    let total: Int
    let page: Int
    let perPage: Int
    let totalPages: Int
}

struct ScoutLeaderboardsResponse: Decodable, Equatable, Sendable {
    let leaderboards: [String: [ScoutPlayerSummary]]
    let limit: Int
    let phase: String
}

struct ScoutPlayerSummary: Decodable, Equatable, Sendable {
    // `id` is the tracked-player row. `playerId` is the canonical player identity.
    let id: Int
    let playerId: Int
    let playerName: String
    let playerPhoto: String?
    let position: String?
    let age: Int?
    let nationality: String?

    let primaryTeamId: Int
    let primaryTeamName: String?
    let primaryTeamApiId: Int?
    let loanTeamName: String?
    let loanTeamApiId: Int?
    let loanTeamDbId: Int?
    let loanTeamLogo: String?
    let ownerTeamId: Int?
    let ownerTeamName: String?

    let isActive: Bool
    let status: String
    let pathwayStatus: String
    let currentLevel: String?
    let dataSource: String
    let dataDepth: String
    let saleFee: String?
    let createdAt: String?
    let updatedAt: String?

    let appearances: Int
    let goals: Int
    let assists: Int
    let minutesPlayed: Int
    let avgRating: Double?
    let goalContributions: Int
    let contributionsPer90: Double?

    let hasDetailedStats: Bool
    let shotsTotal: Int?
    let shotsOn: Int?
    let passesTotal: Int?
    let keyPasses: Int?
    let dribblesAttempts: Int?
    let dribblesSuccess: Int?
    let tackles: Int?
    let duelsTotal: Int?
    let duelsWon: Int?
    let duelWinPct: Double?
    let foulsDrawn: Int?
    let foulsCommitted: Int?
    let yellows: Int?
    let reds: Int?
    let saves: Int?
    let goalsConceded: Int?
    let penaltySaved: Int?
    let cleanSheets: Int?
    let tacklesPer90: Double?
    let keyPassesPer90: Double?
    let concededPer90: Double?
    let savePct: Double?

    // Present on `/scout/players`, intentionally absent on leaderboard rows.
    let recentForm: [ScoutRecentForm]?

    var photoURL: URL? {
        playerPhoto.flatMap(URL.init(string:))
    }
}

struct ScoutRecentForm: Decodable, Equatable, Sendable {
    let date: String?
    let minutes: Int
    let goals: Int
    let assists: Int
    let rating: Double?
}
