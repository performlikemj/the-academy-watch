import Foundation

struct APIClient: Sendable {
    static let productionBaseURL = URL(
        string: "https://ca-loan-army-backend.lemonmoss-23c9ec03.westus2.azurecontainerapps.io/api"
    )!

    private let baseURL: URL
    private let session: URLSession

    init(baseURL: URL = APIClient.productionBaseURL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    func fetchScoutPlayers(
        page: Int,
        perPage: Int = 25,
        sort: String = "contributions"
    ) async throws -> ScoutPlayersResponse {
        try await get(
            path: "scout/players",
            queryItems: [
                URLQueryItem(name: "sort", value: sort),
                URLQueryItem(name: "per_page", value: String(perPage)),
                URLQueryItem(name: "page", value: String(page)),
            ]
        )
    }

    func fetchScoutLeaderboards(limit: Int = 10, phase: String = "all") async throws -> ScoutLeaderboardsResponse {
        try await get(
            path: "scout/leaderboards",
            queryItems: [
                URLQueryItem(name: "limit", value: String(limit)),
                URLQueryItem(name: "phase", value: phase),
            ]
        )
    }

    private func get<Response: Decodable>(
        path: String,
        queryItems: [URLQueryItem]
    ) async throws -> Response {
        let url = try makeURL(path: path, queryItems: queryItems)
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        // Scout aggregation can approach 30 seconds during an Azure cold start.
        request.timeoutInterval = 60
        request.cachePolicy = .reloadRevalidatingCacheData

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIClientError.invalidResponse
        }
        guard (200 ... 299).contains(httpResponse.statusCode) else {
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

enum APIClientError: LocalizedError {
    case invalidURL
    case invalidResponse
    case httpStatus(Int)
    case decoding(Error)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "The Academy Watch service address is invalid."
        case .invalidResponse:
            return "The service returned an unreadable response."
        case let .httpStatus(statusCode):
            return "The service returned an error (HTTP \(statusCode))."
        case .decoding:
            return "The player data format was not recognized."
        }
    }
}
