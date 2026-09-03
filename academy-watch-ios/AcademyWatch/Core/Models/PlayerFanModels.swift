import Foundation

/// GET `/players/<signed id>/followers/count` — anonymous OK, optional Bearer.
/// `following` is `null` for anonymous callers and a bool for signed-in ones.
struct PlayerFollowerCountResponse: Decodable, Equatable, Sendable {
    let playerApiId: Int
    let fans: Int
    let following: Bool?
    let shareUrl: String?
}

/// POST `/players/<signed id>/follow` — 201 on first follow (`created: true`),
/// 200 on the idempotent repeat (`created: false`).
struct PlayerFollowResponse: Decodable, Equatable, Sendable {
    let playerApiId: Int
    let following: Bool
    let fans: Int
    let created: Bool?

    private enum CodingKeys: String, CodingKey {
        case playerApiId
        case following
        case fans
        case created
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        playerApiId = try container.decode(Int.self, forKey: .playerApiId)
        following = try container.decode(Bool.self, forKey: .following)
        fans = try container.decode(Int.self, forKey: .fans)
        created = try container.decodeIfPresent(Bool.self, forKey: .created)
    }

    init(playerApiId: Int, following: Bool, fans: Int, created: Bool?) {
        self.playerApiId = playerApiId
        self.following = following
        self.fans = fans
        self.created = created
    }
}

/// DELETE `/players/<signed id>/follow` — removes only the caller's fan row.
struct PlayerUnfollowResponse: Decodable, Equatable, Sendable {
    let playerApiId: Int
    let following: Bool
    let deleted: Bool?

    private enum CodingKeys: String, CodingKey {
        case playerApiId
        case following
        case deleted
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        playerApiId = try container.decode(Int.self, forKey: .playerApiId)
        following = try container.decode(Bool.self, forKey: .following)
        deleted = try container.decodeIfPresent(Bool.self, forKey: .deleted)
    }
}

/// What the PlayerDetail fan row needs after auth resolution. `nil` means the
/// surface is hidden: non-public subjects (minor/suppressed/unknown) answer 404.
struct PlayerFanSummary: Equatable, Sendable {
    let fans: Int
    let following: Bool?

    init(fans: Int, following: Bool?) {
        self.fans = fans
        self.following = following
    }

    init(response: PlayerFollowerCountResponse) {
        fans = response.fans
        following = response.following
    }
}
