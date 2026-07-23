import Foundation

struct PlayerShowcaseResponse: Decodable, Equatable, Sendable {
    let playerApiId: Int
    let profile: ShowcaseProfile?
    let reel: [ShowcaseReelItem]
    let verifiedFootage: [ShowcaseVerifiedFootage]
    let claimStatus: String?

    private enum CodingKeys: String, CodingKey {
        case playerApiId
        case profile
        case reel
        case verifiedFootage
        case claimStatus
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        playerApiId = try container.decode(Int.self, forKey: .playerApiId)
        profile = try container.decodeIfPresent(ShowcaseProfile.self, forKey: .profile)
        reel = try container.decodeIfPresent([ShowcaseReelItem].self, forKey: .reel) ?? []
        verifiedFootage = try container.decodeIfPresent(
            [ShowcaseVerifiedFootage].self,
            forKey: .verifiedFootage
        ) ?? []
        claimStatus = try container.decodeIfPresent(String.self, forKey: .claimStatus)
    }

    var approvedReel: [ShowcaseReelItem] {
        reel.filter { item in
            item.status.caseInsensitiveCompare("approved") == .orderedSame
                && item.videoID != nil
        }
    }

    var selfReportedProfile: ShowcaseProfile? {
        guard let profile, profile.selfReported, profile.hasVisibleContent else { return nil }
        return profile
    }

    var clubVerifiedFootage: [ShowcaseVerifiedFootage] {
        verifiedFootage.filter(\.verified)
    }

    /// Public ownership signal emitted by the showcase route. The contact
    /// endpoint remains authoritative about whether the approved claim is a
    /// direct player self-claim.
    var isClaimedProfile: Bool {
        claimStatus?.caseInsensitiveCompare("claimed") == .orderedSame
    }

    var hasContent: Bool {
        !approvedReel.isEmpty
            || selfReportedProfile != nil
            || !clubVerifiedFootage.isEmpty
    }
}

enum ShowcaseProfileModerationStatus: String, Decodable, Equatable, Sendable {
    case pending
    case approved
}

enum PlayerContractAttestationReviewStatus: String, Decodable, Equatable, Sendable {
    case pending
    case approved
}

struct ShowcaseProfile: Decodable, Equatable, Sendable {
    let id: Int?
    let playerApiId: Int
    let bio: String?
    let positions: String?
    let preferredFoot: String?
    let heightCm: Int?
    let selfReported: Bool
    let status: ShowcaseProfileModerationStatus?
    let updatedAt: String?
    let contractStatus: PlayerContractStatus?
    let currentClubName: String?
    let clubProgramId: Int?
    let statusContradiction: Bool?
    let contractAttestationReviewStatus: PlayerContractAttestationReviewStatus?

    private enum CodingKeys: String, CodingKey {
        case id
        case playerApiId
        case bio
        case positions
        case preferredFoot
        case heightCm
        case selfReported
        case status
        case updatedAt
        case contractStatus
        case currentClubName
        case clubProgramId
        case statusContradiction
        case contractAttestationReviewStatus
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(Int.self, forKey: .id)
        playerApiId = try container.decode(Int.self, forKey: .playerApiId)
        bio = try container.decodeIfPresent(String.self, forKey: .bio)
        positions = try container.decodeIfPresent(String.self, forKey: .positions)
        preferredFoot = try container.decodeIfPresent(String.self, forKey: .preferredFoot)
        heightCm = try container.decodeIfPresent(Int.self, forKey: .heightCm)
        selfReported = try container.decodeIfPresent(Bool.self, forKey: .selfReported) ?? false
        status = try container.decodeIfPresent(ShowcaseProfileModerationStatus.self, forKey: .status)
        updatedAt = try container.decodeIfPresent(String.self, forKey: .updatedAt)
        contractStatus = try container.decodeIfPresent(PlayerContractStatus.self, forKey: .contractStatus)
        currentClubName = try container.decodeIfPresent(String.self, forKey: .currentClubName)
        clubProgramId = try container.decodeIfPresent(Int.self, forKey: .clubProgramId)
        statusContradiction = try container.decodeIfPresent(Bool.self, forKey: .statusContradiction)
        contractAttestationReviewStatus = try container.decodeIfPresent(
            PlayerContractAttestationReviewStatus.self,
            forKey: .contractAttestationReviewStatus
        )
    }

    var hasVisibleContent: Bool {
        [bio, positions, preferredFoot]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .contains { !$0.isEmpty }
            || heightCm != nil
    }

    var contractAttestation: PlayerContractAttestation? {
        guard let contractStatus else { return nil }
        return PlayerContractAttestation(
            contractStatus: contractStatus,
            currentClubName: currentClubName,
            clubProgramId: clubProgramId
        )
    }
}

struct ShowcaseProfileResponse: Decodable, Equatable, Sendable {
    let profile: ShowcaseProfile
}

/// Exact owner-facing PUT `/players/<id>/showcase/profile` body. Every ordinary
/// profile field is carried forward because the route replaces, rather than
/// patches, those values. Nullable club fields are deliberately encoded as
/// JSON null so an owner can clear an earlier attestation.
struct OwnerShowcaseProfileUpdate: Encodable, Equatable, Sendable {
    let bio: String?
    let positions: String?
    let preferredFoot: String?
    let heightCm: Int?
    let contractStatus: PlayerContractStatus
    let currentClubName: String?
    let clubProgramId: Int?

    init(profile: ShowcaseProfile?, attestation: PlayerContractAttestation) {
        bio = profile?.bio
        positions = profile?.positions
        preferredFoot = profile?.preferredFoot
        heightCm = profile?.heightCm
        contractStatus = attestation.contractStatus
        currentClubName = attestation.currentClubName
        clubProgramId = attestation.clubProgramId
    }

    private enum CodingKeys: String, CodingKey {
        case bio
        case positions
        case preferredFoot
        case heightCm
        case contractStatus
        case currentClubName
        case clubProgramId
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try Self.encodeNullable(bio, forKey: .bio, into: &container)
        try Self.encodeNullable(positions, forKey: .positions, into: &container)
        try Self.encodeNullable(preferredFoot, forKey: .preferredFoot, into: &container)
        try Self.encodeNullable(heightCm, forKey: .heightCm, into: &container)
        try container.encode(contractStatus, forKey: .contractStatus)
        try Self.encodeNullable(currentClubName, forKey: .currentClubName, into: &container)
        try Self.encodeNullable(clubProgramId, forKey: .clubProgramId, into: &container)
    }

    private static func encodeNullable<Value: Encodable>(
        _ value: Value?,
        forKey key: CodingKeys,
        into container: inout KeyedEncodingContainer<CodingKeys>
    ) throws {
        if let value {
            try container.encode(value, forKey: key)
        } else {
            try container.encodeNil(forKey: key)
        }
    }
}

struct ShowcaseReelItem: Decodable, Equatable, Identifiable, Sendable {
    let id: String
    let playerId: Int
    let url: String
    let title: String?
    let linkType: String
    let status: String
    let upvotes: Int
    let sortOrder: Int?
    let source: String?
    let createdAt: String?

    private enum CodingKeys: String, CodingKey {
        case id
        case playerId
        case url
        case title
        case linkType
        case status
        case upvotes
        case sortOrder
        case source
        case createdAt
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        if let stringID = try? container.decode(String.self, forKey: .id) {
            id = stringID
        } else {
            id = String(try container.decode(Int.self, forKey: .id))
        }
        playerId = try container.decode(Int.self, forKey: .playerId)
        url = try container.decode(String.self, forKey: .url)
        title = try container.decodeIfPresent(String.self, forKey: .title)
        linkType = try container.decodeIfPresent(String.self, forKey: .linkType) ?? "highlight"
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? ""
        upvotes = try container.decodeIfPresent(Int.self, forKey: .upvotes) ?? 0
        sortOrder = try container.decodeIfPresent(Int.self, forKey: .sortOrder)
        source = try container.decodeIfPresent(String.self, forKey: .source)
        createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
    }

    var videoID: String? {
        YouTubeVideoID.parse(url)
    }

    var videoURL: URL? {
        guard let videoID else { return nil }
        var components = URLComponents()
        components.scheme = "https"
        components.host = "www.youtube.com"
        components.path = "/watch"
        components.queryItems = [URLQueryItem(name: "v", value: videoID)]
        return components.url
    }

    var thumbnailURL: URL? {
        guard let videoID else { return nil }
        return URL(string: "https://img.youtube.com/vi/\(videoID)/hqdefault.jpg")
    }

    var displayTitle: String {
        let cleanTitle = title?.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let cleanTitle, !cleanTitle.isEmpty else { return "Match highlights" }
        return cleanTitle
    }

    var sourceLabel: String {
        source?.caseInsensitiveCompare("newsletter") == .orderedSame
            ? "Newsletter highlight"
            : "Showcase reel"
    }
}

struct ShowcaseVerifiedFootage: Decodable, Equatable, Identifiable, Sendable {
    let matchId: Int
    let matchDate: String?
    let opponentName: String?
    let teamName: String?
    let minutesOnCamera: Double?
    let pctOfMatch: Double?
    let identitySource: String?
    let verified: Bool

    var id: Int { matchId }

    var coveragePercent: Int? {
        guard let pctOfMatch, pctOfMatch >= 0 else { return nil }
        let percent = pctOfMatch <= 1 ? pctOfMatch * 100 : pctOfMatch
        return Int(min(percent, 100).rounded())
    }
}

enum YouTubeVideoID {
    static func parse(_ value: String) -> String? {
        guard let components = URLComponents(string: value),
              components.scheme?.lowercased() == "https",
              let rawHost = components.host?.lowercased()
        else { return nil }

        let host = rawHost.hasPrefix("www.") ? String(rawHost.dropFirst(4)) : rawHost
        let pathParts = components.path.split(separator: "/").map(String.init)

        if host == "youtu.be" {
            return clean(pathParts.first)
        }

        guard host == "youtube.com" || host == "m.youtube.com" else { return nil }
        if let queryID = components.queryItems?.first(where: { $0.name == "v" })?.value,
           let cleanID = clean(queryID) {
            return cleanID
        }
        guard pathParts.count >= 2,
              pathParts[0] == "embed" || pathParts[0] == "shorts"
        else { return nil }
        return clean(pathParts[1])
    }

    private static func clean(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              !value.isEmpty,
              value.rangeOfCharacter(from: CharacterSet(charactersIn: "/?&#")) == nil
        else { return nil }
        return value
    }
}

#if DEBUG
extension PlayerShowcaseResponse {
    static let debugFixture: PlayerShowcaseResponse = {
        let payload = #"""
        {
          "claim_status": "claimed",
          "player_api_id": 403064,
          "profile": {
            "player_api_id": 403064,
            "bio": "An attack-minded left-back who looks to progress play early and recover with pace.",
            "positions": "Left-back, wing-back",
            "preferred_foot": "left",
            "height_cm": 181,
            "self_reported": true
          },
          "reel": [
            {
              "id": 41,
              "player_id": 403064,
              "url": "https://www.youtube.com/watch?v=Ryt6tidyYaI",
              "title": "Development match highlights",
              "link_type": "highlight",
              "status": "approved",
              "upvotes": 0,
              "sort_order": 0,
              "source": "user",
              "created_at": "2026-07-02T10:00:00+00:00"
            },
            {
              "id": "yt-9",
              "player_id": 403064,
              "url": "https://youtu.be/bcoAMvp9ez8",
              "title": "Matchday reel",
              "link_type": "highlight",
              "status": "approved",
              "upvotes": 0,
              "sort_order": null,
              "source": "newsletter",
              "created_at": null
            }
          ],
          "verified_footage": [
            {
              "match_id": 4,
              "match_date": "2025-09-10",
              "opponent_name": "Rivals FC",
              "team_name": "Manchester United",
              "minutes_on_camera": 88.0,
              "pct_of_match": 0.72,
              "identity_source": "human_confirmed",
              "verified": true
            }
          ]
        }
        """#
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let fixture = try? decoder.decode(
            PlayerShowcaseResponse.self,
            from: Data(payload.utf8)
        ) else {
            preconditionFailure("Invalid debug showcase fixture")
        }
        return fixture
    }()
}
#endif
