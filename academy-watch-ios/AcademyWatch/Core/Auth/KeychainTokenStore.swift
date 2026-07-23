import Foundation
import Security

protocol TokenStoreProtocol: Sendable {
    func loadToken() throws -> String?
    func saveToken(_ token: String) throws
    func deleteToken() throws
}

struct KeychainTokenStore: TokenStoreProtocol, Sendable {
    private let service: String
    private let account: String

    init(
        service: String = "com.theacademywatch.app.auth",
        account: String = "user-token"
    ) {
        self.service = service
        self.account = account
    }

    func loadToken() throws -> String? {
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound {
            return nil
        }
        guard status == errSecSuccess else {
            throw KeychainTokenStoreError.unhandledStatus(status)
        }
        guard let data = result as? Data,
              let token = String(data: data, encoding: .utf8),
              !token.isEmpty
        else {
            throw KeychainTokenStoreError.invalidTokenData
        }
        return token
    }

    func saveToken(_ token: String) throws {
        guard let data = token.data(using: .utf8), !token.isEmpty else {
            throw KeychainTokenStoreError.invalidTokenData
        }

        let updateStatus = SecItemUpdate(
            baseQuery as CFDictionary,
            [kSecValueData as String: data] as CFDictionary
        )
        if updateStatus == errSecSuccess {
            return
        }
        guard updateStatus == errSecItemNotFound else {
            throw KeychainTokenStoreError.unhandledStatus(updateStatus)
        }

        var addQuery = baseQuery
        addQuery[kSecValueData as String] = data
        addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
        guard addStatus == errSecSuccess else {
            throw KeychainTokenStoreError.unhandledStatus(addStatus)
        }
    }

    func deleteToken() throws {
        let status = SecItemDelete(baseQuery as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainTokenStoreError.unhandledStatus(status)
        }
    }

    private var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }
}

enum KeychainTokenStoreError: LocalizedError {
    case invalidTokenData
    case credentialStillPresent
    case unhandledStatus(OSStatus)

    var errorDescription: String? {
        switch self {
        case .invalidTokenData:
            return "The sign-in token could not be stored securely."
        case .credentialStillPresent:
            return "The sign-in credential is still stored securely on this device."
        case let .unhandledStatus(status):
            let detail = SecCopyErrorMessageString(status, nil) as String?
            return detail ?? "The Keychain returned error \(status)."
        }
    }
}
