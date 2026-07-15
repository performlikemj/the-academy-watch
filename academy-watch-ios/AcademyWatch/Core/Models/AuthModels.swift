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
    let token: String
    let expiresIn: Int

    init(
        message: String,
        role: String,
        accountRole: AccountRole? = nil,
        displayName: String?,
        displayNameConfirmed: Bool,
        token: String,
        expiresIn: Int
    ) {
        self.message = message
        self.role = role
        self.accountRole = accountRole
        self.displayName = displayName
        self.displayNameConfirmed = displayNameConfirmed
        self.token = token
        self.expiresIn = expiresIn
    }
}

enum AuthState: Equatable, Sendable {
    case signedOut
    case signedIn(email: String?, accountRole: AccountRole?)

    var isAuthenticated: Bool {
        if case .signedIn = self {
            return true
        }
        return false
    }

    var email: String? {
        guard case let .signedIn(email, _) = self else { return nil }
        return email
    }

    var accountRole: AccountRole? {
        guard case let .signedIn(_, accountRole) = self else { return nil }
        return accountRole
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
