import Combine
import Foundation

enum IntroductionRequestFailure: Equatable, Sendable {
    case messageRequired
    case messageTooLong
    case verificationRequired
    case playerNotClaimable
    case attestationRequired
    case activeRequestExists
    case declineCooldownActive(days: Int?)
    case requestExpired
    case rateLimited
    case generic(message: String)

    var message: String {
        switch self {
        case .messageRequired:
            return "Write a short introduction before sending."
        case .messageTooLong:
            return "Keep your introduction to 2,000 characters or fewer."
        case .verificationRequired:
            return "Verify your scout profile before requesting an introduction."
        case .playerNotClaimable:
            return "This player is not currently available for introduction requests."
        case .attestationRequired:
            return "Football approach rules may prohibit contacting this player without their current club’s consent. Confirm that your club has, or will obtain, the required permission before any approach."
        case .activeRequestExists:
            return "You already have an active request for this player. Check Sent Requests for its latest status."
        case let .declineCooldownActive(days):
            if let days, days > 0 {
                return "This player recently declined a request. You can ask again after the \(days)-day cooling-off period."
            }
            return "This player recently declined a request. Please wait before asking again."
        case .requestExpired:
            return "This request has expired. Refresh Sent Requests before trying again."
        case .rateLimited:
            return "You've reached the introduction request limit. Please try again later."
        case let .generic(message):
            return message
        }
    }

    var routesToVerification: Bool {
        self == .verificationRequired
    }

    var requiresPermissionAttestation: Bool {
        self == .attestationRequired
    }
}

@MainActor
final class IntroductionRequestViewModel: ObservableObject {
    static let maximumMessageLength = ContactLimits.maximumRequestMessageLength

    #if DEBUG
    static let debugFixtureMessage =
        "I’m tracking this player’s progress and would value a short conversation about their development and next steps."
    #endif

    let playerID: Int

    @Published var message: String
    @Published private(set) var isSubmitting = false
    @Published private(set) var createdRequest: ContactRequest?
    @Published private(set) var failure: IntroductionRequestFailure?

    private let availability: ContactFeatureAvailability
    private let createRequest: @Sendable (Int, String, Bool) async throws -> ContactRequestResponse

    convenience init(
        playerID: Int,
        apiClient: any ContactAPIClientProtocol = APIClient(),
        initialMessage: String = "",
        initialFailure: IntroductionRequestFailure? = nil
    ) {
        self.init(
            playerID: playerID,
            apiClient: apiClient,
            availability: .shared,
            initialMessage: initialMessage,
            initialFailure: initialFailure
        )
    }

    convenience init(
        playerID: Int,
        apiClient: any ContactAPIClientProtocol = APIClient(),
        availability: ContactFeatureAvailability,
        initialMessage: String = "",
        initialFailure: IntroductionRequestFailure? = nil
    ) {
        self.init(
            playerID: playerID,
            availability: availability,
            initialMessage: initialMessage,
            initialFailure: initialFailure,
            createRequest: { requestedPlayerID, message, permissionAttestation in
                try await apiClient.createContactRequest(
                    playerID: requestedPlayerID,
                    message: message,
                    permissionAttestation: permissionAttestation
                )
            }
        )
    }

    init(
        playerID: Int,
        availability: ContactFeatureAvailability,
        initialMessage: String = "",
        initialFailure: IntroductionRequestFailure? = nil,
        createRequest: @escaping @Sendable (Int, String, Bool) async throws -> ContactRequestResponse
    ) {
        self.playerID = playerID
        self.availability = availability
        message = initialMessage
        failure = initialFailure
        self.createRequest = createRequest
    }

    var characterCount: Int {
        message.count
    }

    var validationFailure: IntroductionRequestFailure? {
        let normalized = normalizedMessage
        if normalized.isEmpty {
            return .messageRequired
        }
        if normalized.count > Self.maximumMessageLength {
            return .messageTooLong
        }
        return nil
    }

    var canSubmit: Bool {
        createdRequest == nil
            && !isSubmitting
            && validationFailure == nil
            && failure?.requiresPermissionAttestation != true
            && !availability.isUnavailable
    }

    var errorMessage: String? {
        failure?.message
    }

    var shouldRouteToVerification: Bool {
        failure?.routesToVerification == true
    }

    @discardableResult
    func submit() async -> Bool {
        await submit(permissionAttestation: false)
    }

    @discardableResult
    func retryWithPermissionAttestation() async -> Bool {
        guard failure?.requiresPermissionAttestation == true else { return false }
        return await submit(permissionAttestation: true)
    }

    @discardableResult
    private func submit(permissionAttestation: Bool) async -> Bool {
        guard createdRequest == nil,
              !isSubmitting,
              !availability.isUnavailable
        else { return false }
        if let validationFailure {
            failure = validationFailure
            return false
        }

        isSubmitting = true
        failure = nil
        defer { isSubmitting = false }

        do {
            let response = try await createRequest(
                playerID,
                normalizedMessage,
                permissionAttestation
            )
            // The POST has succeeded at this point. Commit its server result
            // even if the presenting task was cancelled as the response won
            // the race, so a retry cannot create a duplicate request.
            createdRequest = response.contactRequest
            availability.recordSuccess()
            return true
        } catch is CancellationError {
            return false
        } catch {
            availability.recordFailure(error)
            guard !availability.isUnavailable else {
                // A contact-route 404 means the rollout is disabled. The
                // observing surfaces disappear instead of presenting an error.
                failure = nil
                return false
            }
            failure = Self.mapFailure(error)
            return false
        }
    }

    func clearFailure() {
        failure = nil
    }

    private var normalizedMessage: String {
        message.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func mapFailure(_ error: Error) -> IntroductionRequestFailure {
        if let apiError = error as? APIClientError {
            if case let .codedServer(_, _, code, cooldownDays) = apiError {
                switch code {
                case "scout_not_verified":
                    return .verificationRequired
                case "player_not_claimable":
                    return .playerNotClaimable
                case "attestation_required":
                    return .attestationRequired
                case "active_request_exists":
                    return .activeRequestExists
                case "decline_cooldown_active":
                    return .declineCooldownActive(days: cooldownDays)
                case "request_expired":
                    return .requestExpired
                default:
                    break
                }
            }

            if apiError.statusCode == 429 {
                return .rateLimited
            }
        }

        if let urlError = error as? URLError {
            switch urlError.code {
            case .notConnectedToInternet, .networkConnectionLost:
                return .generic(message: "You're offline. Reconnect and try sending again.")
            case .timedOut:
                return .generic(message: "The request timed out. Please try again.")
            default:
                break
            }
        }

        return .generic(
            message: "We couldn't send your introduction request. Check your connection and try again."
        )
    }
}
