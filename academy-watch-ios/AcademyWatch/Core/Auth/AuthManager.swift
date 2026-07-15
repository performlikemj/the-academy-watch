import Combine
import Foundation

@MainActor
final class AuthManager: ObservableObject, AuthSessionProtocol {
    @Published private(set) var state: AuthState
    @Published private(set) var signOutErrorMessage: String?

    private let authClient: any AuthAPIClientProtocol
    private let tokenStore: any TokenStoreProtocol
    private let protectedResponseCache: URLCache
    private var token: String?
    private var verificationGeneration: UInt = 0

    var isAuthenticated: Bool { state.isAuthenticated }
    var email: String? { state.email }

    convenience init() {
        self.init(authClient: APIClient(), tokenStore: KeychainTokenStore())
    }

    init(
        authClient: any AuthAPIClientProtocol,
        tokenStore: any TokenStoreProtocol,
        protectedResponseCache: URLCache = .shared
    ) {
        self.authClient = authClient
        self.tokenStore = tokenStore
        self.protectedResponseCache = protectedResponseCache

        let restoredToken = try? tokenStore.loadToken()
        token = restoredToken
        state = restoredToken == nil ? .signedOut : .signedIn(email: nil)
        signOutErrorMessage = nil
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

        verificationGeneration &+= 1
        let attemptGeneration = verificationGeneration
        let response = try await authClient.verifyLoginCode(
            email: normalizedEmail,
            code: normalizedCode
        )
        try Task.checkCancellation()
        guard attemptGeneration == verificationGeneration else {
            throw CancellationError()
        }
        try tokenStore.saveToken(response.token)
        token = response.token
        signOutErrorMessage = nil
        state = .signedIn(email: normalizedEmail)
        return response
    }

    func signOut() {
        cancelVerificationAttempts()
        signOutErrorMessage = nil

        do {
            try deletePersistedCredential()
        } catch {
            signOutErrorMessage = "Sign out failed. \(error.localizedDescription) Please try again."
            return
        }

        token = nil
        state = .signedOut
        protectedResponseCache.removeAllCachedResponses()
    }

    func cancelVerificationAttempts() {
        verificationGeneration &+= 1
    }

    func clearSignOutError() {
        signOutErrorMessage = nil
    }

    func accessToken() async -> String? {
        token
    }

    func invalidate() async {
        signOut()
    }

    func invalidate(credential: String) async {
        guard normalizedToken(token) == credential else { return }
        signOut()
    }

    private func deletePersistedCredential() throws {
        var lastError: Error = KeychainTokenStoreError.credentialStillPresent

        for _ in 0 ..< 2 {
            do {
                try tokenStore.deleteToken()
                guard try tokenStore.loadToken() == nil else {
                    lastError = KeychainTokenStoreError.credentialStillPresent
                    continue
                }
                return
            } catch {
                lastError = error
            }
        }

        throw lastError
    }

    private func normalizedToken(_ token: String?) -> String? {
        token.flatMap { value in
            let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? nil : trimmed
        }
    }
}
