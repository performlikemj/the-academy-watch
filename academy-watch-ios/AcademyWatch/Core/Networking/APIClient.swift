import Foundation

protocol ScoutAPIClientProtocol: Sendable {
    func fetchScoutPlayers(_ request: ScoutPlayersRequest) async throws -> ScoutPlayersResponse
    func fetchScoutLeaderboards(_ request: ScoutLeaderboardsRequest) async throws -> ScoutLeaderboardsResponse
}

protocol PlayerDetailAPIClientProtocol: Sendable {
    func fetchPlayerProfile(playerID: Int) async throws -> PlayerProfile
    func fetchPlayerSeasonStats(playerID: Int) async throws -> PlayerSeasonStats
    func fetchPlayerRecentFixtures(playerID: Int) async throws -> [PlayerRecentFixture]
    func fetchPlayerJourney(playerID: Int) async throws -> PlayerJourneyResponse
    func fetchPlayerAvailability(playerID: Int) async throws -> PlayerAvailability
}

protocol ShowcaseAPIClientProtocol: Sendable {
    func fetchPlayerShowcase(playerID: Int) async throws -> PlayerShowcaseResponse
}

protocol WatchlistAPIClientProtocol: Sendable {
    func fetchWatchlist() async throws -> WatchlistResponse
    func fetchWatchlistIDs() async throws -> WatchlistIDsResponse
    func addToWatchlist(playerID: Int) async throws -> WatchlistEntryResponse
    func removeFromWatchlist(playerID: Int) async throws -> WatchlistRemoveResponse
    func updateWatchlistNote(playerID: Int, note: String) async throws -> WatchlistEntryResponse
    func updateWatchlistSettings(digestOptIn: Bool) async throws -> WatchlistSettingsResponse
}

protocol FollowListsAPIClientProtocol: Sendable {
    func fetchFollowLists() async throws -> FollowListsResponse
    func createFollowList(name: String) async throws -> FollowListResponse
    func deleteFollowList(listID: Int) async throws -> FollowListDeleteResponse
    func addPlayerFollow(listID: Int, playerID: Int) async throws -> FollowResponse
    func removeFollow(listID: Int, followID: Int) async throws -> FollowRemoveResponse
    func resolveFollowList(listID: Int, limit: Int, offset: Int) async throws -> ResolvedFollowListResponse
}

struct APIClient: ScoutAPIClientProtocol,
    PlayerDetailAPIClientProtocol,
    ShowcaseAPIClientProtocol,
    AuthAPIClientProtocol,
    WatchlistAPIClientProtocol,
    FollowListsAPIClientProtocol,
    CompareAPIClientProtocol,
    Sendable
{
    static let productionBaseURL = URL(
        string: "https://ca-loan-army-backend.lemonmoss-23c9ec03.westus2.azurecontainerapps.io/api"
    )!

    private let baseURL: URL
    private let session: URLSession
    private let authSession: (any AuthSessionProtocol)?

    init(
        baseURL: URL = APIClient.productionBaseURL,
        session: URLSession = .shared,
        authSession: (any AuthSessionProtocol)? = nil
    ) {
        self.baseURL = baseURL
        self.session = session
        self.authSession = authSession
    }

    func fetchScoutPlayers(_ request: ScoutPlayersRequest) async throws -> ScoutPlayersResponse {
        var queryItems = [
            URLQueryItem(name: "sort", value: request.sort),
            URLQueryItem(name: "order", value: request.order.rawValue),
            URLQueryItem(name: "per_page", value: String(request.perPage)),
            URLQueryItem(name: "page", value: String(request.page)),
        ]
        queryItems.appendIfPresent(name: "search", value: request.search)
        queryItems.appendIfPresent(name: "position", value: request.position)
        queryItems.appendIfPresent(name: "status", value: request.status)
        queryItems.appendIfPresent(name: "max_age", value: request.maximumAge.map(String.init))

        return try await get(
            path: "scout/players",
            queryItems: queryItems
        )
    }

    func fetchScoutLeaderboards(_ request: ScoutLeaderboardsRequest) async throws -> ScoutLeaderboardsResponse {
        var queryItems = [
            URLQueryItem(name: "limit", value: String(request.limit)),
            URLQueryItem(name: "phase", value: request.phase.rawValue),
        ]
        // `phase` selects the board set server-side. Attack, midfield and
        // defense still need their explicit position filter (GK is clamped).
        queryItems.appendIfPresent(name: "position", value: request.position)
        queryItems.appendIfPresent(name: "status", value: request.status)
        queryItems.appendIfPresent(name: "max_age", value: request.maximumAge.map(String.init))

        return try await get(
            path: "scout/leaderboards",
            queryItems: queryItems
        )
    }

    func fetchPlayerProfile(playerID: Int) async throws -> PlayerProfile {
        try await get(path: "players/\(playerID)/profile", queryItems: [])
    }

    func fetchPlayerSeasonStats(playerID: Int) async throws -> PlayerSeasonStats {
        try await get(path: "players/\(playerID)/season-stats", queryItems: [])
    }

    func fetchPlayerRecentFixtures(playerID: Int) async throws -> [PlayerRecentFixture] {
        try await get(path: "players/\(playerID)/stats", queryItems: [])
    }

    func fetchPlayerJourney(playerID: Int) async throws -> PlayerJourneyResponse {
        try await get(path: "players/\(playerID)/journey", queryItems: [])
    }

    func fetchPlayerAvailability(playerID: Int) async throws -> PlayerAvailability {
        try await get(path: "players/\(playerID)/availability", queryItems: [])
    }

    func fetchPlayerShowcase(playerID: Int) async throws -> PlayerShowcaseResponse {
        try await get(path: "players/\(playerID)/showcase", queryItems: [])
    }

    func requestLoginCode(email: String) async throws -> LoginCodeResponse {
        try await send(
            path: "auth/request-code",
            method: "POST",
            body: LoginCodeRequest(email: email)
        )
    }

    func verifyLoginCode(email: String, code: String) async throws -> AuthTokenResponse {
        try await send(
            path: "auth/verify-code",
            method: "POST",
            body: VerifyLoginCodeRequest(email: email, code: code)
        )
    }

    func fetchWatchlist() async throws -> WatchlistResponse {
        try await get(path: "scout/watchlist", queryItems: [])
    }

    func fetchWatchlistIDs() async throws -> WatchlistIDsResponse {
        try await get(path: "scout/watchlist/ids", queryItems: [])
    }

    func addToWatchlist(playerID: Int) async throws -> WatchlistEntryResponse {
        try await send(
            path: "scout/watchlist",
            method: "POST",
            body: WatchlistPlayerRequest(playerApiId: playerID)
        )
    }

    func removeFromWatchlist(playerID: Int) async throws -> WatchlistRemoveResponse {
        try await perform(
            path: "scout/watchlist/\(playerID)",
            method: "DELETE",
            queryItems: [],
            body: nil
        )
    }

    func updateWatchlistNote(playerID: Int, note: String) async throws -> WatchlistEntryResponse {
        try await send(
            path: "scout/watchlist/\(playerID)",
            method: "PATCH",
            body: WatchlistNoteRequest(note: note)
        )
    }

    func updateWatchlistSettings(digestOptIn: Bool) async throws -> WatchlistSettingsResponse {
        try await send(
            path: "scout/watchlist/settings",
            method: "PATCH",
            body: WatchlistSettingsRequest(digestOptIn: digestOptIn)
        )
    }

    func fetchFollowLists() async throws -> FollowListsResponse {
        try await get(path: "scout/lists", queryItems: [])
    }

    func createFollowList(name: String) async throws -> FollowListResponse {
        try await send(
            path: "scout/lists",
            method: "POST",
            body: FollowListCreateRequest(name: name)
        )
    }

    func deleteFollowList(listID: Int) async throws -> FollowListDeleteResponse {
        try await perform(
            path: "scout/lists/\(listID)",
            method: "DELETE",
            queryItems: [],
            body: nil
        )
    }

    func addPlayerFollow(listID: Int, playerID: Int) async throws -> FollowResponse {
        try await send(
            path: "scout/lists/\(listID)/follows",
            method: "POST",
            body: PlayerFollowRequest(
                kind: "player",
                selector: PlayerFollowSelectorRequest(playerApiId: playerID)
            )
        )
    }

    func removeFollow(listID: Int, followID: Int) async throws -> FollowRemoveResponse {
        try await perform(
            path: "scout/lists/\(listID)/follows/\(followID)",
            method: "DELETE",
            queryItems: [],
            body: nil
        )
    }

    func resolveFollowList(
        listID: Int,
        limit: Int,
        offset: Int
    ) async throws -> ResolvedFollowListResponse {
        try await get(
            path: "scout/lists/\(listID)/resolve",
            queryItems: [
                URLQueryItem(name: "limit", value: String(limit)),
                URLQueryItem(name: "offset", value: String(offset)),
            ]
        )
    }

    func fetchComparison(
        playerIDs: [Int],
        includeAvailability: Bool
    ) async throws -> CompareResponse {
        try await get(
            path: "scout/compare",
            queryItems: [
                URLQueryItem(name: "ids", value: playerIDs.map(String.init).joined(separator: ",")),
                URLQueryItem(name: "include_availability", value: includeAvailability ? "true" : "false"),
            ]
        )
    }

    private func get<Response: Decodable>(
        path: String,
        queryItems: [URLQueryItem]
    ) async throws -> Response {
        try await perform(
            path: path,
            method: "GET",
            queryItems: queryItems,
            body: nil
        )
    }

    private func send<Body: Encodable, Response: Decodable>(
        path: String,
        method: String,
        body: Body
    ) async throws -> Response {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let bodyData: Data
        do {
            bodyData = try encoder.encode(body)
        } catch {
            throw APIClientError.encoding(error)
        }

        return try await perform(
            path: path,
            method: method,
            queryItems: [],
            body: bodyData
        )
    }

    private func perform<Response: Decodable>(
        path: String,
        method: String,
        queryItems: [URLQueryItem],
        body: Data?
    ) async throws -> Response {
        let url = try makeURL(path: path, queryItems: queryItems)
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        let token = await authSession?.accessToken()
            .flatMap { value in
                let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
                return trimmed.isEmpty ? nil : trimmed
            }
        if let token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
            request.cachePolicy = .reloadIgnoringLocalCacheData
        }

        // Scout aggregation can approach 30 seconds during an Azure cold start.
        request.timeoutInterval = 60
        if method == "GET", token == nil {
            request.cachePolicy = .reloadRevalidatingCacheData
        }

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIClientError.invalidResponse
        }
        guard (200 ... 299).contains(httpResponse.statusCode) else {
            if httpResponse.statusCode == 401, let token {
                await authSession?.invalidate(credential: token)
            }
            if let message = Self.errorMessage(from: data) {
                throw APIClientError.server(statusCode: httpResponse.statusCode, message: message)
            }
            throw APIClientError.httpStatus(httpResponse.statusCode)
        }

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        do {
            return try decoder.decode(Response.self, from: data)
        } catch {
            throw APIClientError.decoding(error)
        }
    }

    private static func errorMessage(from data: Data) -> String? {
        guard let payload = try? JSONDecoder().decode(APIErrorPayload.self, from: data) else {
            return nil
        }
        return [payload.error, payload.message]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .first { !$0.isEmpty }
    }

    private func makeURL(path: String, queryItems: [URLQueryItem]) throws -> URL {
        guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
            throw APIClientError.invalidURL
        }

        let basePath = components.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let endpointPath = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        components.path = "/" + [basePath, endpointPath]
            .filter { !$0.isEmpty }
            .joined(separator: "/")
        components.queryItems = queryItems.isEmpty ? nil : queryItems

        guard let url = components.url else {
            throw APIClientError.invalidURL
        }
        return url
    }
}

private extension Array where Element == URLQueryItem {
    mutating func appendIfPresent(name: String, value: String?) {
        guard let value, !value.isEmpty else { return }
        append(URLQueryItem(name: name, value: value))
    }
}

enum APIClientError: LocalizedError {
    case invalidURL
    case invalidResponse
    case httpStatus(Int)
    case server(statusCode: Int, message: String)
    case encoding(Error)
    case decoding(Error)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "The Academy Watch service address is invalid."
        case .invalidResponse:
            return "The service returned an unreadable response."
        case let .httpStatus(statusCode):
            return "The service returned an error (HTTP \(statusCode))."
        case let .server(_, message):
            return message
        case .encoding:
            return "The request could not be prepared."
        case .decoding:
            return "The service response format was not recognized."
        }
    }
}

private struct LoginCodeRequest: Encodable {
    let email: String
}

private struct VerifyLoginCodeRequest: Encodable {
    let email: String
    let code: String
}

private struct WatchlistPlayerRequest: Encodable {
    let playerApiId: Int
}

private struct WatchlistNoteRequest: Encodable {
    let note: String
}

private struct WatchlistSettingsRequest: Encodable {
    let digestOptIn: Bool
}

private struct FollowListCreateRequest: Encodable {
    let name: String
}

private struct PlayerFollowRequest: Encodable {
    let kind: String
    let selector: PlayerFollowSelectorRequest
}

private struct PlayerFollowSelectorRequest: Encodable {
    let playerApiId: Int
}

private struct APIErrorPayload: Decodable {
    let error: String?
    let message: String?
}
