import Foundation

struct LoginCodeResponse: Decodable, Equatable, Sendable {
    let message: String
}

enum AccountRole: String, Decodable, Equatable, Sendable {
    case scout
    case player
    case clubManager = "club_manager"

    var displayName: String {
        switch self {
        case .scout:
            return "Scout"
        case .player:
            return "Player"
        case .clubManager:
            return "Club manager"
        }
    }
}

struct AuthTokenResponse: Decodable, Equatable, Sendable {
    let message: String
    let role: String
    let accountRole: AccountRole?
    let displayName: String?
    let displayNameConfirmed: Bool
    let isVerifiedScout: Bool
    let token: String
    let expiresIn: Int

    init(
        message: String,
        role: String,
        accountRole: AccountRole? = nil,
        displayName: String?,
        displayNameConfirmed: Bool,
        isVerifiedScout: Bool = false,
        token: String,
        expiresIn: Int
    ) {
        self.message = message
        self.role = role
        self.accountRole = accountRole
        self.displayName = displayName
        self.displayNameConfirmed = displayNameConfirmed
        self.isVerifiedScout = isVerifiedScout
        self.token = token
        self.expiresIn = expiresIn
    }

    private enum CodingKeys: String, CodingKey {
        case message
        case role
        case accountRole
        case displayName
        case displayNameConfirmed
        case isVerifiedScout
        case token
        case expiresIn
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        message = try container.decode(String.self, forKey: .message)
        role = try container.decode(String.self, forKey: .role)
        accountRole = try container.decodeIfPresent(AccountRole.self, forKey: .accountRole)
        displayName = try container.decodeIfPresent(String.self, forKey: .displayName)
        displayNameConfirmed = try container.decodeIfPresent(Bool.self, forKey: .displayNameConfirmed) ?? false
        isVerifiedScout = try container.decodeIfPresent(Bool.self, forKey: .isVerifiedScout) ?? false
        token = try container.decode(String.self, forKey: .token)
        expiresIn = try container.decode(Int.self, forKey: .expiresIn)
    }
}

/// Exact public `/api/auth/me` serializer shape observed in `routes/auth_routes.py`.
struct AuthProfileResponse: Decodable, Equatable, Sendable {
    let email: String?
    let role: String
    let userId: Int?
    let displayName: String?
    let displayNameConfirmed: Bool
    let isJournalist: Bool
    let isCurator: Bool
    let isVerifiedScout: Bool
}

enum AuthState: Equatable, Sendable {
    case signedOut
    case signedIn(
        email: String?,
        accountRole: AccountRole?,
        displayName: String?,
        isVerifiedScout: Bool
    )

    var isAuthenticated: Bool {
        if case .signedIn = self {
            return true
        }
        return false
    }

    var email: String? {
        guard case let .signedIn(email, _, _, _) = self else { return nil }
        return email
    }

    var accountRole: AccountRole? {
        guard case let .signedIn(_, accountRole, _, _) = self else { return nil }
        return accountRole
    }

    var displayName: String? {
        guard case let .signedIn(_, _, displayName, _) = self else { return nil }
        return displayName
    }

    var isVerifiedScout: Bool {
        guard case let .signedIn(_, _, _, isVerifiedScout) = self else { return false }
        return isVerifiedScout
    }
}

protocol AuthSessionProtocol: Sendable {
    func accessToken() async -> String?
    func invalidate() async
    func invalidate(credential: String) async
}

extension AuthSessionProtocol {
    func invalidate(credential: String) async {
        guard await accessToken() == credential else { return }
        await invalidate()
    }
}

protocol AuthAPIClientProtocol: Sendable {
    func requestLoginCode(email: String) async throws -> LoginCodeResponse
    func verifyLoginCode(email: String, code: String) async throws -> AuthTokenResponse
}

protocol AccountAPIClientProtocol: Sendable {
    func fetchCurrentAccount() async throws -> AuthProfileResponse
}

enum AuthInputError: LocalizedError {
    case emailRequired
    case codeRequired

    var errorDescription: String? {
        switch self {
        case .emailRequired:
            return "Enter the email you use for The Academy Watch."
        case .codeRequired:
            return "Enter the code from your email."
        }
    }
}
