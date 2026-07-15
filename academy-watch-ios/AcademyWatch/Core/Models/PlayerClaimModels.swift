import Foundation

enum PlayerProfileClaimStatus: String, Decodable, Equatable, Sendable {
    case pending
    case approved
    case rejected
    case revoked
}

struct PlayerProfileClaim: Decodable, Equatable, Identifiable, Sendable {
    let id: Int
    let playerApiId: Int
    let userAccountId: Int
    let relationshipType: String
    let status: PlayerProfileClaimStatus
    let message: String?
    let reviewedBy: String?
    let reviewedAt: String?
    let createdAt: String?
    let playerName: String?
}

struct PlayerClaimsResponse: Decodable, Equatable, Sendable {
    let claims: [PlayerProfileClaim]
}

struct PlayerClaimResponse: Decodable, Equatable, Sendable {
    let claim: PlayerProfileClaim
}
