import Foundation

/// Exact POST `/players/<signed id>/matches` body. Required scalar counters
/// (`minutes`, `goals`, `assists`, `yellows`, `reds`) are always sent because
/// the backend defaults them to 0; optional ones are omitted when unset so the
/// backend treats them as "not provided" rather than zero.
struct PlayerMatchSubmission: Encodable, Equatable, Sendable {
    var matchDate: String
    var competition: String?
    var opponent: String
    var homeAway: PlayerMatchVenue
    var resultFor: Int?
    var resultAgainst: Int?
    var minutes: Int
    var goals: Int
    var assists: Int
    var yellows: Int
    var reds: Int
    var saves: Int?
    var goalsConceded: Int?
    var note: String?
}

enum PlayerMatchVenue: String, CaseIterable, Identifiable, Codable, Sendable {
    case home
    case away
    case neutral

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .home: "Home"
        case .away: "Away"
        case .neutral: "Neutral venue"
        }
    }
}

/// One `PlayerMatchEntry.to_dict()` row from the matches route.
struct PlayerMatchEntry: Decodable, Equatable, Identifiable, Sendable {
    let id: Int
    let playerApiId: Int
    let season: Int
    let matchDate: String?
    let competition: String?
    let opponent: String?
    let homeAway: String?
    let resultFor: Int?
    let resultAgainst: Int?
    let minutes: Int?
    let goals: Int?
    let assists: Int?
    let yellows: Int?
    let reds: Int?
    let saves: Int?
    let goalsConceded: Int?
    let note: String?
    let source: String?
    let status: String?
    let editable: Bool?
}

/// 201 (created) / 200 (updated) body for the matches mutation. `season_stats`
/// is the rollup service's refresh payload; it is a compact `{cells, totals}`
/// summary today, but was a fuller stats object in earlier releases, so it is
/// decoded leniently and the detail screen re-fetches authoritative totals
/// unless the payload decodes as real season stats.
struct PlayerMatchMutationResponse: Decodable, Equatable, Sendable {
    let match: PlayerMatchEntry
    let seasonStats: PlayerSeasonStats?

    private enum CodingKeys: String, CodingKey {
        case match
        case seasonStats
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        match = try container.decode(PlayerMatchEntry.self, forKey: .match)
        seasonStats = try? container.decodeIfPresent(PlayerSeasonStats.self, forKey: .seasonStats)
    }

    init(match: PlayerMatchEntry, seasonStats: PlayerSeasonStats?) {
        self.match = match
        self.seasonStats = seasonStats
    }
}
