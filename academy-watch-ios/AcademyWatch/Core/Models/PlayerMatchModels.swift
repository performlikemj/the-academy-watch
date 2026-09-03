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

/// 201 (created) / 200 (updated) body for the matches mutation. The backend's
/// `season_stats` value is a compact rollup summary, so the detail screen
/// re-fetches authoritative season stats instead of decoding that field here.
struct PlayerMatchMutationResponse: Decodable, Equatable, Sendable {
    let match: PlayerMatchEntry
}
