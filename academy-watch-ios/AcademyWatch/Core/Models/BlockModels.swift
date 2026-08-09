import Foundation

protocol BlocksAPIClientProtocol: Sendable {
    func fetchBlockedUsers() async throws -> BlockedUsersResponse
    func blockUser(accountID: Int) async throws
    func unblockUser(accountID: Int) async throws
}

struct BlockedUsersResponse: Decodable, Equatable, Sendable {
    let blocks: [BlockedUser]
}

struct BlockedUser: Decodable, Equatable, Identifiable, Sendable {
    let accountId: Int
    let displayName: String?
    let createdAt: String?

    var id: Int { accountId }

    private enum CodingKeys: String, CodingKey {
        case accountId
        case blockedUserId
        case displayName
        case createdAt
    }

    init(accountId: Int, displayName: String?, createdAt: String?) {
        self.accountId = accountId
        self.displayName = displayName
        self.createdAt = createdAt
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        accountId = try container.decodeIfPresent(Int.self, forKey: .accountId)
            ?? container.decode(Int.self, forKey: .blockedUserId)
        displayName = try container.decodeIfPresent(String.self, forKey: .displayName)
        createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
    }
}

enum ContactPrivacyMessage {
    static let exchangeUnavailable = "You can’t exchange new requests or messages with this account."
    static let blockingUnavailable = "Blocking is temporarily unavailable. Please try again."

    static func message(for error: Error) -> String? {
        guard let apiError = error as? APIClientError else { return nil }
        if case let .codedServer(_, _, code, _) = apiError,
           code == "messaging_unavailable" {
            return exchangeUnavailable
        }
        return nil
    }

    static func blockActionMessage(for error: Error) -> String {
        if let apiError = error as? APIClientError, apiError.statusCode == 503 {
            return blockingUnavailable
        }
        if let urlError = error as? URLError,
           urlError.code == .notConnectedToInternet || urlError.code == .networkConnectionLost {
            return "You’re offline. Reconnect and try again."
        }
        return "We couldn’t update this block. Please try again."
    }
}
