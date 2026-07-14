import Combine
import Foundation

@MainActor
final class AuthManager: ObservableObject, AuthSessionProtocol {
    @Published private(set) var state: AuthState

    private let authClient: any AuthAPIClientProtocol
    private let tokenStore: any TokenStoreProtocol
    private var token: String?

    var isAuthenticated: Bool { state.isAuthenticated }
    var email: String? { state.email }

    convenience init() {
        self.init(authClient: APIClient(), tokenStore: KeychainTokenStore())
    }

    init(
        authClient: any AuthAPIClientProtocol,
        tokenStore: any TokenStoreProtocol
    ) {
        self.authClient = authClient
        self.tokenStore = tokenStore

        let restoredToken = try? tokenStore.loadToken()
        token = restoredToken
        state = restoredToken == nil ? .signedOut : .signedIn(email: nil)
    }

    @discardableResult
    func requestCode(email: String) async throws -> LoginCodeResponse {
        let normalizedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !normalizedEmail.isEmpty else {
            throw AuthInputError.emailRequired
        }
        return try await authClient.requestLoginCode(email: normalizedEmail)
    }

    @discardableResult
    func verifyCode(email: String, code: String) async throws -> AuthTokenResponse {
        let normalizedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let normalizedCode = code.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalizedEmail.isEmpty else {
            throw AuthInputError.emailRequired
        }
        guard !normalizedCode.isEmpty else {
            throw AuthInputError.codeRequired
        }

        let response = try await authClient.verifyLoginCode(
            email: normalizedEmail,
            code: normalizedCode
        )
        try tokenStore.saveToken(response.token)
        token = response.token
        state = .signedIn(email: normalizedEmail)
        return response
    }

    func signOut() {
        token = nil
        state = .signedOut
        try? tokenStore.deleteToken()
    }

    func accessToken() async -> String? {
        token
    }

    func invalidate() async {
        signOut()
    }
}
