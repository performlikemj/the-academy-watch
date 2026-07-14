import Foundation

struct LoginCodeResponse: Decodable, Equatable, Sendable {
    let message: String
}

struct AuthTokenResponse: Decodable, Equatable, Sendable {
    let message: String
    let role: String
    let displayName: String?
    let displayNameConfirmed: Bool
    let token: String
    let expiresIn: Int
}

enum AuthState: Equatable, Sendable {
    case signedOut
    case signedIn(email: String?)

    var isAuthenticated: Bool {
        if case .signedIn = self {
            return true
        }
        return false
    }

    var email: String? {
        guard case let .signedIn(email) = self else { return nil }
        return email
    }
}

protocol AuthSessionProtocol: Sendable {
    func accessToken() async -> String?
    func invalidate() async
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
