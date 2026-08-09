import Foundation

enum LocalPlayerRelationship: String, Codable, CaseIterable, Identifiable, Sendable {
    case player
    case agent
    case guardian

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .player: "Player"
        case .agent: "Agent"
        case .guardian: "Parent / guardian"
        }
    }
}

/// Exact POST `/local-players` body. Nil optionals are omitted so the scout
/// path can deliberately rely on the server's documented relationship default.
struct LocalPlayerSubmission: Encodable, Equatable, Sendable {
    let displayName: String
    let relationshipType: LocalPlayerRelationship?
    let position: String?
    let clubName: String?
    let country: String?
    let city: String?
    let birthYear: Int?
}

struct LocalPlayer: Codable, Equatable, Identifiable, Sendable {
    let id: Int
    let displayName: String
    let birthYear: Int?
    let position: String?
    let country: String?
    let city: String?
    let clubName: String?
    let status: String
    let provenance: String?
    let createdAt: String?
}

struct LocalPlayerCreateResponse: Decodable, Equatable, Sendable {
    let player: LocalPlayer
    let claim: LocalPlayerClaim
}

struct LocalPlayerResponse: Decodable, Equatable, Sendable {
    let player: LocalPlayer
    let mergedInto: Int?
}

struct LocalPlayerClaim: Decodable, Equatable, Sendable {
    let id: Int
    let localPlayerId: Int?
    let relationshipType: String
    let status: String
    let verificationCode: String?
    let verificationStatus: String?
}

struct WorldwidePlayerSearchResponse: Decodable, Equatable, Sendable {
    let players: [WorldwidePlayer]
}

struct WorldwidePlayer: Codable, Equatable, Identifiable, Sendable {
    let playerApiId: Int
    let name: String
    let age: Int?
    let nationality: String?
    let photo: String?
    let clubName: String?
    let tracked: Bool
    let shadow: Bool

    var id: Int { playerApiId }
    var photoURL: URL? { photo.flatMap(URL.init(string:)) }
}

struct WorldwidePlayerSeed: Encodable, Equatable, Sendable {
    let name: String
    let age: Int?
    let nationality: String?
    let photo: String?
    let clubName: String?

    init(player: WorldwidePlayer) {
        name = player.name
        age = player.age
        nationality = player.nationality
        photo = player.photo
        clubName = player.clubName
    }
}

struct WorldwidePlayerFollowSubmission: Encodable, Equatable, Sendable {
    let kind = "player"
    let selector: WorldwidePlayerSelector
    let seed: WorldwidePlayerSeed

    init(player: WorldwidePlayer) {
        selector = WorldwidePlayerSelector(playerApiId: player.playerApiId)
        seed = WorldwidePlayerSeed(player: player)
    }
}

struct WorldwidePlayerSelector: Encodable, Equatable, Sendable {
    let playerApiId: Int
}

struct ClubSearchResponse: Decodable, Equatable, Sendable {
    let apiTeams: [APIClubSearchResult]
    let localClubs: [LocalClubSearchResult]
}

struct APIClubSearchResult: Decodable, Equatable, Identifiable, Sendable {
    let teamApiId: Int
    let name: String
    let country: String?

    var id: String { "api-\(teamApiId)" }
}

struct LocalClubSearchResult: Decodable, Equatable, Identifiable, Sendable {
    let id: Int
    let name: String
    let country: String?
    let city: String?
    let level: String?
    let status: String
}

enum ClubClaimSubject: Equatable, Sendable {
    case apiTeam(APIClubSearchResult)
    case localClub(LocalClubSearchResult)

    var name: String {
        switch self {
        case let .apiTeam(team): team.name
        case let .localClub(club): club.name
        }
    }
}

/// Exact POST `/clubs/claim` body. The custom encoder enforces the backend XOR.
struct ClubClaimSubmission: Encodable, Equatable, Sendable {
    let subject: ClubClaimSubject
    let roleTitle: String
    let message: String?

    private enum CodingKeys: String, CodingKey {
        case teamApiId
        case localClubId
        case roleTitle
        case message
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        switch subject {
        case let .apiTeam(team):
            try container.encode(team.teamApiId, forKey: .teamApiId)
        case let .localClub(club):
            try container.encode(club.id, forKey: .localClubId)
        }
        try container.encode(roleTitle, forKey: .roleTitle)
        try container.encodeIfPresent(message, forKey: .message)
    }
}

struct ClubClaimsResponse: Decodable, Equatable, Sendable {
    let claims: [ClubClaim]
}

struct ClubClaimResponse: Decodable, Equatable, Sendable {
    let claim: ClubClaim
}

struct ClubClaim: Decodable, Equatable, Identifiable, Sendable {
    let id: Int
    let teamApiId: Int?
    let localClubId: Int?
    let clubName: String?
    let roleTitle: String
    let message: String?
    let status: String
    let verificationCode: String?
    let verificationProofUrl: String?
    let verificationStatus: String
    let verificationNote: String?
    let createdAt: String?
}

struct ClubClaimProofSubmission: Encodable, Equatable, Sendable {
    let proofUrl: String
}
