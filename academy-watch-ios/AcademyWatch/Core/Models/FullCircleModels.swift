import Foundation

enum ScoutVerificationLimits {
    static let maximumFullNameLength = 200
    static let maximumOrganizationLength = 200
    static let maximumRoleTitleLength = 120
    static let maximumStatementLength = 2_000
    static let maximumEvidenceURLLength = 500
    static let maximumEvidenceURLCount = 10
}

enum ContactLimits {
    static let maximumRequestMessageLength = 2_000
    static let maximumThreadMessageLength = 2_000
    static let maximumOutcomeNotesLength = 2_000
}

enum ContentReportLimits {
    static let maximumSubjectIDLength = 200
    static let maximumReasonCodeLength = 80
    static let maximumDetailsLength = 2_000
}

enum ScoutVerificationStatus: String, Codable, Equatable, Sendable {
    case pending
    case approved
    case rejected
    case revoked

    var displayName: String {
        switch self {
        case .pending: "Pending review"
        case .approved: "Verified scout"
        case .rejected: "Not approved"
        case .revoked: "Verification revoked"
        }
    }
}

struct ScoutVerification: Decodable, Equatable, Identifiable, Sendable {
    let id: Int
    let fullName: String
    let organization: String
    let roleTitle: String
    let statement: String
    let evidenceUrls: [String]
    let status: ScoutVerificationStatus
    let submittedAt: String
    let reviewedAt: String?
    let reviewNotes: String?
    let revocationReason: String?
}

struct ScoutVerificationSubmission: Encodable, Equatable, Sendable {
    let fullName: String
    let organization: String
    let roleTitle: String
    let statement: String
    let evidenceUrls: [String]
}

struct ScoutVerificationResponse: Decodable, Equatable, Sendable {
    let verification: ScoutVerification?
}

enum ContactRequestStatus: String, Codable, Equatable, Sendable {
    case pending
    case accepted
    case declined
    case withdrawn
    case expired

    var displayName: String {
        switch self {
        case .pending: "Pending"
        case .accepted: "Accepted"
        case .declined: "Declined"
        case .withdrawn: "Withdrawn"
        case .expired: "Expired"
        }
    }
}

enum ContactRequestBox: String, Codable, Equatable, Sendable {
    case sent
    case inbox
}

enum ContactRequestErrorCode: String, Equatable, Sendable {
    case scoutNotVerified = "scout_not_verified"
    case playerNotClaimable = "player_not_claimable"
    case activeRequestExists = "active_request_exists"
    case declineCooldownActive = "decline_cooldown_active"
    case requestExpired = "request_expired"
    case unknown
}

struct ContactRequestParticipant: Decodable, Equatable, Sendable {
    let displayName: String?
}

struct ContactRequestParticipants: Decodable, Equatable, Sendable {
    let scout: ContactRequestParticipant
    let player: ContactRequestParticipant
}

struct ContactRequest: Decodable, Equatable, Identifiable, Sendable {
    let id: String
    let playerApiId: Int
    let message: String
    let status: ContactRequestStatus
    let createdAt: String
    let respondedAt: String?
    let expiresAt: String
    let participants: ContactRequestParticipants
    let latestOutcome: ContactOutcome?

    func replacing(status: ContactRequestStatus) -> ContactRequest {
        ContactRequest(
            id: id,
            playerApiId: playerApiId,
            message: message,
            status: status,
            createdAt: createdAt,
            respondedAt: respondedAt,
            expiresAt: expiresAt,
            participants: participants,
            latestOutcome: latestOutcome
        )
    }

    func replacing(latestOutcome: ContactOutcome?) -> ContactRequest {
        ContactRequest(
            id: id,
            playerApiId: playerApiId,
            message: message,
            status: status,
            createdAt: createdAt,
            respondedAt: respondedAt,
            expiresAt: expiresAt,
            participants: participants,
            latestOutcome: latestOutcome
        )
    }
}

struct CreateContactRequestBody: Encodable, Equatable, Sendable {
    let playerApiId: Int
    let message: String
}

struct ContactRequestResponse: Decodable, Equatable, Sendable {
    let contactRequest: ContactRequest
}

struct ContactRequestsResponse: Decodable, Equatable, Sendable {
    let requests: [ContactRequest]
    let box: ContactRequestBox
    let total: Int
    let limit: Int
    let offset: Int
}

enum ContactSenderRole: String, Codable, Equatable, Sendable {
    case scout
    case player
}

struct ContactMessage: Decodable, Equatable, Identifiable, Sendable {
    let id: String
    let contactRequestId: String
    let senderRole: ContactSenderRole
    let senderDisplayName: String?
    let body: String
    let createdAt: String
}

struct CreateContactMessageBody: Encodable, Equatable, Sendable {
    let body: String
}

struct ContactMessageResponse: Decodable, Equatable, Sendable {
    let message: ContactMessage
}

struct ContactMessagesResponse: Decodable, Equatable, Sendable {
    let messages: [ContactMessage]
    let contactRequest: ContactRequest
    let total: Int
    let limit: Int
    let offset: Int
}

enum ContactOutcomeStage: String, Codable, CaseIterable, Equatable, Sendable {
    case contacted
    case trialScheduled = "trial_scheduled"
    case trialCompleted = "trial_completed"
    case signed
    case noFit = "no_fit"

    var displayName: String {
        switch self {
        case .contacted: "Contacted"
        case .trialScheduled: "Trial scheduled"
        case .trialCompleted: "Trial completed"
        case .signed: "Signed"
        case .noFit: "No fit"
        }
    }
}

struct ContactOutcome: Decodable, Equatable, Sendable {
    let stage: ContactOutcomeStage
    let notes: String?
    let occurredAt: String
    let createdAt: String
}

struct ReportContactOutcomeBody: Encodable, Equatable, Sendable {
    let stage: ContactOutcomeStage
    let notes: String?
    let occurredAt: String?
}

struct ContactOutcomeResponse: Decodable, Equatable, Sendable {
    let outcome: ContactOutcome
    let contactRequest: ContactRequest
}

struct InterestSignalMetric: Decodable, Equatable, Sendable {
    let total: Int
    let addedThisWeek: Int
}

struct PlayerInterestSignal: Decodable, Equatable, Identifiable, Sendable {
    let playerApiId: Int
    let watchlists: InterestSignalMetric
    let follows: InterestSignalMetric

    var id: Int { playerApiId }

    static func zero(playerID: Int) -> PlayerInterestSignal {
        PlayerInterestSignal(
            playerApiId: playerID,
            watchlists: InterestSignalMetric(total: 0, addedThisWeek: 0),
            follows: InterestSignalMetric(total: 0, addedThisWeek: 0)
        )
    }
}

struct InterestSignalsResponse: Decodable, Equatable, Sendable {
    let weekStart: String
    let interestSignals: [PlayerInterestSignal]
}

enum ContentReportSubjectType: String, Codable, Equatable, Sendable {
    case contactMessage = "contact_message"
    case other
}

enum ContentReportStatus: String, Decodable, Equatable, Sendable {
    case open
    case reviewing
    case resolved
    case dismissed
}

struct SubmitContentReportBody: Encodable, Equatable, Sendable {
    let subjectType: ContentReportSubjectType
    let subjectId: String
    let reasonCode: String
    let details: String?
}

struct ContentReport: Decodable, Equatable, Identifiable, Sendable {
    let id: Int
    let subjectType: ContentReportSubjectType
    let subjectId: String
    let reasonCode: String
    let details: String?
    let status: ContentReportStatus
    let resolutionNotes: String?
    let createdAt: String
    let resolvedAt: String?
}

struct ContentReportResponse: Decodable, Equatable, Sendable {
    let report: ContentReport
}

enum ContentReportReason: String, CaseIterable, Equatable, Sendable {
    case participantSafety = "participant_safety"
    case harassment
    case spam
    case misrepresentation
    case inappropriateContent = "inappropriate_content"
    case other

    var displayName: String {
        switch self {
        case .participantSafety: "Safety concern"
        case .harassment: "Harassment"
        case .spam: "Spam or repeated contact"
        case .misrepresentation: "Misrepresentation"
        case .inappropriateContent: "Inappropriate content"
        case .other: "Something else"
        }
    }
}

struct ContentReportSubject: Identifiable, Equatable, Sendable {
    let subjectType: ContentReportSubjectType
    let subjectID: String
    let title: String
    let explanation: String
    let defaultReason: ContentReportReason

    var id: String { "\(subjectType.rawValue):\(subjectID)" }

    static func request(_ request: ContactRequest) -> ContentReportSubject {
        let explanation: String
        switch request.status {
        case .pending:
            explanation = "Reporting asks Academy Watch to review this introduction. It does not block the scout; decline the request separately to close it and start the cooldown window."
        case .accepted:
            explanation = "Reporting asks Academy Watch to review this introduction. It does not block the scout, and an accepted introduction can no longer be declined."
        case .declined:
            explanation = "Reporting asks Academy Watch to review this introduction. It does not block the scout. This request is already closed as declined."
        case .withdrawn:
            explanation = "Reporting asks Academy Watch to review this introduction. It does not block the scout. This request was withdrawn and can no longer be declined."
        case .expired:
            explanation = "Reporting asks Academy Watch to review this introduction. It does not block the scout. This request expired and can no longer be declined."
        }

        return ContentReportSubject(
            subjectType: .other,
            subjectID: request.id,
            title: "Report Introduction",
            explanation: explanation,
            defaultReason: .participantSafety
        )
    }

    static func message(_ message: ContactMessage) -> ContentReportSubject {
        ContentReportSubject(
            subjectType: .contactMessage,
            subjectID: message.id,
            title: "Report Message",
            explanation: "Reporting sends this message to Academy Watch for review. It does not block the other participant.",
            defaultReason: .participantSafety
        )
    }
}
