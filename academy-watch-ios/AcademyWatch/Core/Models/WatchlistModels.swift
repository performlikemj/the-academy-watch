import Foundation

struct WatchlistResponse: Decodable, Equatable, Sendable {
    let entries: [WatchlistEntry]
    let digestOptIn: Bool
    let scoutTier: String
}

struct WatchlistEntry: Decodable, Equatable, Identifiable, Sendable {
    let playerApiId: Int
    let note: String?
    let createdAt: String?
    let player: ScoutPlayerSummary?

    var id: Int { playerApiId }
}

struct WatchlistIDsResponse: Decodable, Equatable, Sendable {
    let playerIds: [Int]
}

struct WatchlistEntryResponse: Decodable, Equatable, Sendable {
    let entry: WatchlistEntry
}

struct WatchlistRemoveResponse: Decodable, Equatable, Sendable {
    let removed: Bool
}

struct WatchlistSettingsResponse: Decodable, Equatable, Sendable {
    let digestOptIn: Bool
}
