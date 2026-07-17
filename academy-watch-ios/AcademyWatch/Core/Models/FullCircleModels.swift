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

enum ContactRoutingMode: String, Codable, Equatable, Sendable {
    case direct
    case clubIncluded = "club_included"
    case clubNotified = "club_notified"
}

enum ClubConsentStatus: String, Codable, Equatable, Sendable {
    case pending
    case granted
    case declined
}

enum ContactRequestErrorCode: String, Equatable, Sendable {
    case scoutNotVerified = "scout_not_verified"
    case playerNotClaimable = "player_not_claimable"
    case activeRequestExists = "active_request_exists"
    case declineCooldownActive = "decline_cooldown_active"
    case requestExpired = "request_expired"
    case attestationRequired = "attestation_required"
    case clubConsentRequired = "club_consent_required"
    case clubConsentDeclined = "club_consent_declined"
    case unknown
}

struct ContactRequestParticipant: Decodable, Equatable, Sendable {
    let displayName: String?
    let clubProgramId: Int?

    init(displayName: String?, clubProgramId: Int? = nil) {
        self.displayName = displayName
        self.clubProgramId = clubProgramId
    }

    private enum CodingKeys: String, CodingKey {
        case displayName
        case clubProgramId
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        displayName = try container.decodeIfPresent(String.self, forKey: .displayName)
        clubProgramId = try container.decodeIfPresent(Int.self, forKey: .clubProgramId)
    }
}

struct ContactRequestParticipants: Decodable, Equatable, Sendable {
    let scout: ContactRequestParticipant
    let player: ContactRequestParticipant
    let club: ContactRequestParticipant?

    init(
        scout: ContactRequestParticipant,
        player: ContactRequestParticipant,
        club: ContactRequestParticipant? = nil
    ) {
        self.scout = scout
        self.player = player
        self.club = club
    }
}

struct ContactRequest: Decodable, Equatable, Identifiable, Sendable {
    let id: String
    let playerApiId: Int
    let message: String
    let status: ContactRequestStatus
    let routingMode: ContactRoutingMode
    let clubProgramId: Int?
    let clubConsentStatus: ClubConsentStatus?
    let clubConsentAt: String?
    let clubConsentNote: String?
    let permissionAttestation: Bool
    let permissionAttestedAt: String?
    let messagingOpen: Bool
    let createdAt: String
    let respondedAt: String?
    let expiresAt: String
    let participants: ContactRequestParticipants
    let latestOutcome: ContactOutcome?

    init(
        id: String,
        playerApiId: Int,
        message: String,
        status: ContactRequestStatus,
        routingMode: ContactRoutingMode = .direct,
        clubProgramId: Int? = nil,
        clubConsentStatus: ClubConsentStatus? = nil,
        clubConsentAt: String? = nil,
        clubConsentNote: String? = nil,
        permissionAttestation: Bool = false,
        permissionAttestedAt: String? = nil,
        messagingOpen: Bool? = nil,
        createdAt: String,
        respondedAt: String?,
        expiresAt: String,
        participants: ContactRequestParticipants,
        latestOutcome: ContactOutcome?
    ) {
        self.id = id
        self.playerApiId = playerApiId
        self.message = message
        self.status = status
        self.routingMode = routingMode
        self.clubProgramId = clubProgramId
        self.clubConsentStatus = clubConsentStatus
        self.clubConsentAt = clubConsentAt
        self.clubConsentNote = clubConsentNote
        self.permissionAttestation = permissionAttestation
        self.permissionAttestedAt = permissionAttestedAt
        self.messagingOpen = messagingOpen
            ?? (status == .accepted && (routingMode != .clubIncluded || clubConsentStatus == .granted))
        self.createdAt = createdAt
        self.respondedAt = respondedAt
        self.expiresAt = expiresAt
        self.participants = participants
        self.latestOutcome = latestOutcome
    }

    private enum CodingKeys: String, CodingKey {
        case id
        case playerApiId
        case message
        case status
        case routingMode
        case clubProgramId
        case clubConsentStatus
        case clubConsentAt
        case clubConsentNote
        case permissionAttestation
        case permissionAttestedAt
        case messagingOpen
        case createdAt
        case respondedAt
        case expiresAt
        case participants
        case latestOutcome
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        playerApiId = try container.decode(Int.self, forKey: .playerApiId)
        message = try container.decode(String.self, forKey: .message)
        status = try container.decode(ContactRequestStatus.self, forKey: .status)
        routingMode = try container.decodeIfPresent(ContactRoutingMode.self, forKey: .routingMode) ?? .direct
        clubProgramId = try container.decodeIfPresent(Int.self, forKey: .clubProgramId)
        clubConsentStatus = try container.decodeIfPresent(ClubConsentStatus.self, forKey: .clubConsentStatus)
        clubConsentAt = try container.decodeIfPresent(String.self, forKey: .clubConsentAt)
        clubConsentNote = try container.decodeIfPresent(String.self, forKey: .clubConsentNote)
        permissionAttestation = try container.decodeIfPresent(Bool.self, forKey: .permissionAttestation) ?? false
        permissionAttestedAt = try container.decodeIfPresent(String.self, forKey: .permissionAttestedAt)
        let decodedMessagingOpen = try container.decodeIfPresent(Bool.self, forKey: .messagingOpen)
        createdAt = try container.decode(String.self, forKey: .createdAt)
        respondedAt = try container.decodeIfPresent(String.self, forKey: .respondedAt)
        expiresAt = try container.decode(String.self, forKey: .expiresAt)
        participants = try container.decode(ContactRequestParticipants.self, forKey: .participants)
        latestOutcome = try container.decodeIfPresent(ContactOutcome.self, forKey: .latestOutcome)
        messagingOpen = decodedMessagingOpen
            ?? (status == .accepted && (routingMode != .clubIncluded || clubConsentStatus == .granted))
    }

    func replacing(status: ContactRequestStatus) -> ContactRequest {
        ContactRequest(
            id: id,
            playerApiId: playerApiId,
            message: message,
            status: status,
            routingMode: routingMode,
            clubProgramId: clubProgramId,
            clubConsentStatus: clubConsentStatus,
            clubConsentAt: clubConsentAt,
            clubConsentNote: clubConsentNote,
            permissionAttestation: permissionAttestation,
            permissionAttestedAt: permissionAttestedAt,
            messagingOpen: status == .accepted
                && (routingMode != .clubIncluded || clubConsentStatus == .granted),
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
            routingMode: routingMode,
            clubProgramId: clubProgramId,
            clubConsentStatus: clubConsentStatus,
            clubConsentAt: clubConsentAt,
            clubConsentNote: clubConsentNote,
            permissionAttestation: permissionAttestation,
            permissionAttestedAt: permissionAttestedAt,
            messagingOpen: messagingOpen,
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
    let permissionAttestation: Bool

    init(
        playerApiId: Int,
        message: String,
        permissionAttestation: Bool = false
    ) {
        self.playerApiId = playerApiId
        self.message = message
        self.permissionAttestation = permissionAttestation
    }
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
    case club
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
            explanation: "Reporting sends this message to Academy Watch for review. It does not block the other participants.",
            defaultReason: .participantSafety
        )
    }
}
