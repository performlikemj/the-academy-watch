import Foundation

struct FollowListsResponse: Decodable, Equatable, Sendable {
    let lists: [FollowList]
}

struct FollowListResponse: Decodable, Equatable, Sendable {
    let list: FollowList
}

struct FollowListDeleteResponse: Decodable, Equatable, Sendable {
    let deleted: Bool
}

struct FollowResponse: Decodable, Equatable, Sendable {
    let follow: Follow
    let shadowCreated: Bool
}

struct FollowRemoveResponse: Decodable, Equatable, Sendable {
    let removed: Bool
}

struct FollowList: Decodable, Equatable, Identifiable, Sendable {
    let id: Int
    let name: String
    let cadence: String
    let isActive: Bool
    let isDefault: Bool
    let playerCap: Int
    let followCount: Int
    let follows: [Follow]
    let createdAt: String?
    let updatedAt: String?

    func containsPlayer(_ playerID: Int) -> Bool {
        follows.contains {
            $0.kind == .player && $0.selector.playerApiId == playerID
        }
    }
}

struct Follow: Decodable, Equatable, Identifiable, Sendable {
    let id: Int
    let kind: FollowKind
    let selector: FollowSelector
    let label: String
    let note: String?
    let createdAt: String?
}

enum FollowKind: String, Decodable, Equatable, Sendable {
    case player
    case academyClub = "academy_club"
    case geo
    case query
    case unknown

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        self = FollowKind(rawValue: try container.decode(String.self)) ?? .unknown
    }

    var label: String {
        switch self {
        case .player: "Player"
        case .academyClub: "Academy"
        case .geo: "Location"
        case .query: "Saved filter"
        case .unknown: "Follow"
        }
    }

    var iconName: String {
        switch self {
        case .player: "person.fill"
        case .academyClub: "shield.fill"
        case .geo: "globe.europe.africa.fill"
        case .query: "line.3.horizontal.decrease.circle.fill"
        case .unknown: "bookmark.fill"
        }
    }
}

struct FollowSelector: Decodable, Equatable, Sendable {
    let playerApiId: Int?
    let teamId: Int?
    let countries: [String]?
    let match: String?
}

struct ResolvedFollowListResponse: Decodable, Equatable, Sendable {
    let players: [ResolvedFollowPlayer]
    let total: Int
}

struct ResolvedFollowPlayer: Decodable, Equatable, Identifiable, Sendable {
    let playerApiId: Int
    let playerName: String?
    let source: String
    let teamName: String?
    let status: String?
    let photo: String?

    var id: Int { playerApiId }

    var photoURL: URL? {
        photo.flatMap(URL.init(string:))
    }
}
