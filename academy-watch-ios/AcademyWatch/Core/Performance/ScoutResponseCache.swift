import CryptoKit
import Foundation

protocol ScoutResponseCaching: Sendable {
    func loadPlayers(for key: ScoutPlayersCacheKey) async -> ScoutPlayersResponse?
    func savePlayers(_ response: ScoutPlayersResponse, for key: ScoutPlayersCacheKey) async
    func loadLeaderboards(for key: ScoutLeaderboardsCacheKey) async -> ScoutLeaderboardsResponse?
    func saveLeaderboards(_ response: ScoutLeaderboardsResponse, for key: ScoutLeaderboardsCacheKey) async
}

struct ScoutPlayersCacheKey: Codable, Equatable, Hashable, Sendable {
    let schemaVersion: Int
    let phase: ScoutPhase
    let request: ScoutPlayersRequest

    init(phase: ScoutPhase, request: ScoutPlayersRequest) {
        schemaVersion = ScoutResponseCache.modelSchemaVersion
        self.phase = phase
        self.request = request
    }
}

struct ScoutLeaderboardsCacheKey: Codable, Equatable, Hashable, Sendable {
    let schemaVersion: Int
    let phase: ScoutPhase
    let request: ScoutLeaderboardsRequest

    init(phase: ScoutPhase, request: ScoutLeaderboardsRequest) {
        schemaVersion = ScoutResponseCache.modelSchemaVersion
        self.phase = phase
        self.request = request
    }
}

actor ScoutResponseCache: ScoutResponseCaching {
    static let modelSchemaVersion = 1
    static let shared = ScoutResponseCache()

    private enum Resource: String {
        case players
        case leaderboards
    }

    private let directoryURL: URL
    private let fileManager: FileManager

    init(directoryURL: URL? = nil, fileManager: FileManager = .default) {
        self.fileManager = fileManager
        let cacheRoot = directoryURL
            ?? fileManager.urls(for: .cachesDirectory, in: .userDomainMask).first
            ?? fileManager.temporaryDirectory
        self.directoryURL = cacheRoot.appendingPathComponent(
            "ScoutResponseCache-v\(Self.modelSchemaVersion)",
            isDirectory: true
        )
    }

    func loadPlayers(for key: ScoutPlayersCacheKey) async -> ScoutPlayersResponse? {
        load(ScoutPlayersResponse.self, resource: .players, key: key)
    }

    func savePlayers(_ response: ScoutPlayersResponse, for key: ScoutPlayersCacheKey) async {
        save(response, resource: .players, key: key)
    }

    func loadLeaderboards(for key: ScoutLeaderboardsCacheKey) async -> ScoutLeaderboardsResponse? {
        load(ScoutLeaderboardsResponse.self, resource: .leaderboards, key: key)
    }

    func saveLeaderboards(_ response: ScoutLeaderboardsResponse, for key: ScoutLeaderboardsCacheKey) async {
        save(response, resource: .leaderboards, key: key)
    }

    private func load<Payload: Codable & Sendable, Key: Encodable>(
        _ type: Payload.Type,
        resource: Resource,
        key: Key
    ) -> Payload? {
        do {
            let fileURL = try fileURL(resource: resource, key: key)
            let data = try Data(contentsOf: fileURL)
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .millisecondsSince1970
            let envelope = try decoder.decode(ScoutCacheEnvelope<Payload>.self, from: data)
            guard envelope.schemaVersion == Self.modelSchemaVersion else { return nil }
            return envelope.payload
        } catch {
            return nil
        }
    }

    private func save<Payload: Codable & Sendable, Key: Encodable>(
        _ payload: Payload,
        resource: Resource,
        key: Key
    ) {
        do {
            try fileManager.createDirectory(
                at: directoryURL,
                withIntermediateDirectories: true
            )
            let envelope = ScoutCacheEnvelope(
                schemaVersion: Self.modelSchemaVersion,
                savedAt: Date(),
                payload: payload
            )
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .millisecondsSince1970
            encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
            let data = try encoder.encode(envelope)
            let destination = try fileURL(resource: resource, key: key)
            try data.write(to: destination, options: .atomic)
        } catch {
            // Cache writes are best-effort and must never turn a successful API response into an error.
        }
    }

    private func fileURL<Key: Encodable>(resource: Resource, key: Key) throws -> URL {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let keyData = try encoder.encode(key)
        let digest = SHA256.hash(data: keyData)
            .map { String(format: "%02x", $0) }
            .joined()
        return directoryURL.appendingPathComponent(
            "\(resource.rawValue)-\(digest).json",
            isDirectory: false
        )
    }
}

private struct ScoutCacheEnvelope<Payload: Codable & Sendable>: Codable, Sendable {
    let schemaVersion: Int
    let savedAt: Date
    let payload: Payload
}
