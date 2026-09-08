import Foundation

enum ExperienceRole: String, CaseIterable, Identifiable {
    case player, club, scout
    static let storageKey = "academyWatch.experienceRole.v1"
    var id: String { rawValue }
    var title: String {
        switch self {
        case .player: "Player"
        case .club: "Coach / club"
        case .scout: "Scout / supporter"
        }
    }
    var icon: String {
        switch self {
        case .player: "figure.soccer"
        case .club: "person.3.fill"
        case .scout: "binoculars.fill"
        }
    }
    var selectionTitle: String {
        switch self {
        case .player: "Player"
        case .club: "Club"
        case .scout: "Scout"
        }
    }
}

extension PlayerProfileClaim {
    var signedPlayerID: Int? { playerApiId ?? localPlayerId.map { -$0 } }
    var profileTitle: String { playerName ?? "Player profile" }
    var nextStep: String {
        switch status {
        case .pending: "Your claim is under review. You can return here to check its progress."
        case .approved: "Add your story, update your highlights, and stay connected with your club."
        case .rejected: "Your claim was not approved. Review your details and contact support for help."
        case .revoked: "This claim is inactive. Contact support if you believe this is a mistake."
        }
    }
    var webURL: URL? {
        if let localPlayerId { return URL(string: "https://theacademywatch.com/local-players/\(localPlayerId)") }
        return playerApiId.flatMap { URL(string: "https://theacademywatch.com/players/\($0)") }
    }
}

struct OwnerShowcase: Decodable, Sendable {
    let profile: BasicPlayerProfile?
    let photos: [ProfilePhoto]
    let reel: [OwnerHighlight]
}

struct BasicPlayerProfile: Decodable, Sendable {
    let bio: String?
    let positions: String?
    let preferredFoot: String?
    let heightCm: Int?
    let status: String?
}

struct BasicProfileUpdate: Encodable, Equatable, Sendable {
    var bio: String
    var positions: String
    var preferredFoot: String?
    var heightCm: Int?

    enum CodingKeys: String, CodingKey { case bio, positions, preferredFoot, heightCm }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(bio, forKey: .bio)
        try c.encode(positions, forKey: .positions)
        try c.encode(preferredFoot, forKey: .preferredFoot)
        try c.encode(heightCm, forKey: .heightCm)
    }
}

struct ProfilePhoto: Decodable, Identifiable, Sendable {
    let id: Int
    let status: String
    let isPrimary: Bool
    let publicUrl: String?
    let reviewNote: String?
}
struct OwnerHighlight: Decodable, Identifiable, Sendable {
    let id: String
    let title: String?
    let url: String
    let status: String
    enum CodingKeys: String, CodingKey { case id, title, url, status }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        if let string = try? c.decode(String.self, forKey: .id) {
            id = string
        } else {
            id = String(try c.decode(Int.self, forKey: .id))
        }
        title = try c.decodeIfPresent(String.self, forKey: .title)
        url = try c.decode(String.self, forKey: .url)
        status = try c.decode(String.self, forKey: .status)
    }
}
struct ProfilePhotoResponse: Decodable { let media: ProfilePhoto }
struct ProfilePhotoUpload: Decodable {
    let media: ProfilePhoto
    let upload: Upload
    struct Upload: Decodable {
        let url: URL
        let method: String
        let headers: [String: String]
    }
}

struct ClubInvitation: Decodable, Identifiable, Sendable {
    let id: String
    let programId: Int
    let programName: String?
    let playerApiId: Int
    let status: String
    let expiresAt: String?
    var clubName: String { programName ?? "Your club" }
}
struct ClubInvitationsResponse: Decodable, Sendable {
    let invitations: [ClubInvitation]
    let nextBefore: String?
}
struct ClubInvitationResponse: Decodable { let invitation: ClubInvitation }
enum ClubInvitationDecision: String { case accept, decline, revoke }

struct PlayerFeedback: Decodable, Identifiable, Sendable {
    let id: String
    let threadId: String
    let revision: Int
    let playerApiId: Int
    let program: Program
    let author: Author
    let title: String
    let body: String?
    let publishedAt: String
    let acknowledgedAt: String?
    let canAcknowledge: Bool
    var developmentAction: PlayerDevelopmentAction? = nil
    var developmentProgress: PlayerDevelopmentProgress? = nil
    var canUpdateProgress: Bool? = nil
    struct Program: Decodable, Sendable {
        let id: Int
        let name: String
    }
    struct Author: Decodable, Sendable { let displayName: String? }
}
struct PlayerFeedbackPage: Decodable, Sendable {
    let feedback: [PlayerFeedback]
    let nextBefore: String?
}
struct PlayerFeedbackResponse: Decodable { let feedback: PlayerFeedback }

struct PlayerDevelopmentAction: Decodable, Sendable {
    let focus: String
    let practice: String
    let success: String
    let reviewOn: String?
}
struct PlayerDevelopmentProgress: Decodable, Sendable {
    let version: Int
    let status: String
    let reflection: String
    let coachNote: String?
    let updatedAt: String
    let history: [Event]
    struct Event: Decodable, Identifiable, Sendable {
        let version: Int
        let actor: String
        let status: String
        let note: String
        let at: String
        var id: Int { version }
    }
    static func label(_ status: String?) -> String {
        switch status {
        case "working_on_it": "Working on it"
        case "ready_for_review": "Ready for coach review"
        case "reviewed": "Reviewed by your coach"
        default: "Your next step"
        }
    }
}
struct PlayerDevelopmentUpdate: Encodable, Sendable {
    let expectedVersion: Int
    let status: String
    let note: String
}

protocol PlayerClubAPIClientProtocol: Sendable {
    func fetchMyProfileClaims() async throws -> PlayerClaimsResponse
    func fetchOwnerShowcase(playerID: Int) async throws -> OwnerShowcase
    func saveBasicProfile(playerID: Int, update: BasicProfileUpdate) async throws
    func addHighlight(playerID: Int, url: String, title: String) async throws
    func fetchClubInvitations(before: String?) async throws -> ClubInvitationsResponse
    func decideClubInvitation(id: String, decision: ClubInvitationDecision) async throws
    func fetchPlayerFeedback(playerID: Int, before: String?) async throws -> PlayerFeedbackPage
    func fetchFeedbackDetail(id: String) async throws -> PlayerFeedback
    func acknowledgeFeedback(id: String) async throws -> PlayerFeedback
    func updateDevelopmentProgress(id: String, update: PlayerDevelopmentUpdate) async throws
        -> PlayerFeedback
}

func playerClubError(_ error: Error) -> String {
    if (error as? APIClientError)?.statusCode == 401 { return "Please sign in again to continue." }
    if (error as? APIClientError)?.statusCode == 403 {
        return "Your access has changed. Refresh to check your current permissions."
    }
    if (error as? APIClientError)?.statusCode == 409 {
        return "This has changed since you opened it. Refresh and try again."
    }
    if (error as? APIClientError)?.statusCode == 429 {
        return "You've made several requests. Please wait a little before trying again."
    }
    return (error as? LocalizedError)?.errorDescription ?? "We couldn't complete that request. Please try again."
}
