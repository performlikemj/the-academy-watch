import Foundation

enum PlayerContractStatus: String, Codable, CaseIterable, Equatable, Identifiable, Sendable {
    case freeAgent = "free_agent"
    case contracted
    case unknown

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .freeAgent:
            return "Free agent"
        case .contracted:
            return "Contracted"
        case .unknown:
            return "Not sure"
        }
    }

    var formExplanation: String {
        switch self {
        case .freeAgent:
            return "I am not currently under contract with a club."
        case .contracted:
            return "I am currently under contract with a club."
        case .unknown:
            return "I am not sure of my current contract status."
        }
    }

    var routingExplanation: String {
        switch self {
        case .freeAgent:
            return "Verified scout requests can be routed directly to you."
        case .contracted:
            return "Requests may include your club or require the scout to confirm permission before approaching you."
        case .unknown:
            return "For safety, requests are routed as though you are contracted. Your club may be included, or the scout may need to confirm permission before approaching you."
        }
    }
}

struct PlayerContractAttestation: Encodable, Equatable, Sendable {
    let contractStatus: PlayerContractStatus
    let currentClubName: String?
    let clubProgramId: Int?

    init(
        contractStatus: PlayerContractStatus,
        currentClubName: String? = nil,
        clubProgramId: Int? = nil
    ) {
        self.contractStatus = contractStatus
        self.currentClubName = currentClubName
        self.clubProgramId = clubProgramId
    }
}

/// The exact body accepted by POST `/players/<id>/claim` for a direct player
/// self-claim. Keeping this model outside APIClient makes the serializer shape
/// independently testable.
struct PlayerClaimSubmission: Encodable, Equatable, Sendable {
    let relationshipType: String
    let contractStatus: PlayerContractStatus
    let currentClubName: String?
    let clubProgramId: Int?

    init(attestation: PlayerContractAttestation) {
        relationshipType = "player"
        contractStatus = attestation.contractStatus
        currentClubName = attestation.currentClubName
        clubProgramId = attestation.clubProgramId
    }

    private enum CodingKeys: String, CodingKey {
        case relationshipType
        case contractStatus
        case currentClubName
        case clubProgramId
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(relationshipType, forKey: .relationshipType)
        try container.encode(contractStatus, forKey: .contractStatus)
        if let currentClubName {
            try container.encode(currentClubName, forKey: .currentClubName)
        } else {
            try container.encodeNil(forKey: .currentClubName)
        }
        if let clubProgramId {
            try container.encode(clubProgramId, forKey: .clubProgramId)
        } else {
            try container.encodeNil(forKey: .clubProgramId)
        }
    }
}

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
    let contractStatus: PlayerContractStatus
    let currentClubName: String?
    let clubProgramId: Int?
    let statusContradiction: Bool
    let reviewedBy: String?
    let reviewedAt: String?
    let createdAt: String?
    let playerName: String?

    init(
        id: Int,
        playerApiId: Int,
        userAccountId: Int,
        relationshipType: String,
        status: PlayerProfileClaimStatus,
        message: String?,
        contractStatus: PlayerContractStatus = .unknown,
        currentClubName: String? = nil,
        clubProgramId: Int? = nil,
        statusContradiction: Bool = false,
        reviewedBy: String?,
        reviewedAt: String?,
        createdAt: String?,
        playerName: String?
    ) {
        self.id = id
        self.playerApiId = playerApiId
        self.userAccountId = userAccountId
        self.relationshipType = relationshipType
        self.status = status
        self.message = message
        self.contractStatus = contractStatus
        self.currentClubName = currentClubName
        self.clubProgramId = clubProgramId
        self.statusContradiction = statusContradiction
        self.reviewedBy = reviewedBy
        self.reviewedAt = reviewedAt
        self.createdAt = createdAt
        self.playerName = playerName
    }

    private enum CodingKeys: String, CodingKey {
        case id
        case playerApiId
        case userAccountId
        case relationshipType
        case status
        case message
        case contractStatus
        case currentClubName
        case clubProgramId
        case statusContradiction
        case reviewedBy
        case reviewedAt
        case createdAt
        case playerName
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(Int.self, forKey: .id)
        playerApiId = try container.decode(Int.self, forKey: .playerApiId)
        userAccountId = try container.decode(Int.self, forKey: .userAccountId)
        relationshipType = try container.decode(String.self, forKey: .relationshipType)
        status = try container.decode(PlayerProfileClaimStatus.self, forKey: .status)
        message = try container.decodeIfPresent(String.self, forKey: .message)
        // Older, pre-routing servers do not emit these fields. Conservatively
        // decode those responses as unknown without changing the public UI.
        contractStatus = try container.decodeIfPresent(
            PlayerContractStatus.self,
            forKey: .contractStatus
        ) ?? .unknown
        currentClubName = try container.decodeIfPresent(String.self, forKey: .currentClubName)
        clubProgramId = try container.decodeIfPresent(Int.self, forKey: .clubProgramId)
        statusContradiction = try container.decodeIfPresent(
            Bool.self,
            forKey: .statusContradiction
        ) ?? false
        reviewedBy = try container.decodeIfPresent(String.self, forKey: .reviewedBy)
        reviewedAt = try container.decodeIfPresent(String.self, forKey: .reviewedAt)
        createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
        playerName = try container.decodeIfPresent(String.self, forKey: .playerName)
    }

    var contractAttestation: PlayerContractAttestation {
        PlayerContractAttestation(
            contractStatus: contractStatus,
            currentClubName: currentClubName,
            clubProgramId: clubProgramId
        )
    }
}

struct PlayerClaimsResponse: Decodable, Equatable, Sendable {
    let claims: [PlayerProfileClaim]
}

struct PlayerClaimResponse: Decodable, Equatable, Sendable {
    let claim: PlayerProfileClaim
}
