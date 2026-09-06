#if DEBUG
    import Foundation

    /// Explicit offline UI-test mode. Every API request is intercepted; unknown
    /// paths fail locally and can never fall through to a production server.
    enum PlayerClubExperienceFixtures {
        static var mode: String? {
            let args = ProcessInfo.processInfo.arguments
            guard let i = args.firstIndex(of: "-experienceFixture"), args.indices.contains(i + 1),
                ["player", "club", "pending"].contains(args[i + 1])
            else { return nil }
            return args[i + 1]
        }
        static func session() -> URLSession {
            let config = URLSessionConfiguration.ephemeral
            config.protocolClasses = [ExperienceURLProtocol.self]
            return URLSession(configuration: config)
        }
    }
    struct ExperienceTokenStore: TokenStoreProtocol {
        func loadToken() throws -> String? { nil }
        func saveToken(_ token: String) throws {}
        func deleteToken() throws {}
    }
    private final class ExperienceURLProtocol: URLProtocol, @unchecked Sendable {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var accepted = false
        nonisolated(unsafe) private static var acknowledged = false
        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func stopLoading() {}
        override func startLoading() {
            Self.lock.lock()
            defer { Self.lock.unlock() }
            let path = request.url?.path ?? ""
            let isPending = PlayerClubExperienceFixtures.mode == "pending"
            let claim = """
                {"id":71,"player_api_id":null,"local_player_id":481,"user_account_id":7,"relationship_type":"player","status":"\(isPending ? "pending" : "approved")","player_name":"Maya Okafor","contract_status":"unknown"}
                """
            let feedback = """
                {"id":"feedback-fixture","thread_id":"thread-fixture","revision":1,"player_api_id":-481,"program":{"id":44,"name":"Community FC"},"author":{"display_name":"Coach Alex"},"title":"Building your next pass","body":"Check your shoulder before receiving. In our next session, focus on finding the forward pass early.","published_at":"2026-09-05T10:00:00Z","acknowledged_at":\(Self.acknowledged ? "\"2026-09-06T10:00:00Z\"" : "null"),"can_acknowledge":\(!Self.acknowledged)}
                """
            var status = 200
            let body: String
            switch path {
            case "/api/auth/me":
                body = #"{"email":"maya@fixture.example","display_name":"Maya Okafor","is_verified_scout":false}"#
            case "/api/me/claims": body = "{\"claims\":[\(claim)]}"
            case "/api/local-players/481/showcase":
                body =
                    #"{"profile":{"bio":"Central midfielder, always looking for the next pass.","positions":"CM","preferred_foot":"right","height_cm":172,"status":"approved"},"photos":[],"reel":[]}"#
            case "/api/local-players/481/showcase/profile": body = "{}"
            case "/api/local-players/481/showcase/reel": body = "{}"
            case "/api/me/club-invitations":
                body = """
                    {"invitations":[{"id":"club-fixture","program_id":44,"program_name":"Community FC","player_api_id":-481,"status":"\(Self.accepted ? "accepted" : "pending")","expires_at":"2027-01-01T00:00:00Z"}],"next_before":null}
                    """
            case "/api/me/club-invitations/club-fixture/accept":
                Self.accepted = true
                body = "{}"
            case "/api/me/player-feedback": body = "{\"feedback\":[\(feedback)],\"next_before\":null}"
            case "/api/me/player-feedback/feedback-fixture": body = "{\"feedback\":\(feedback)}"
            case "/api/me/player-feedback/feedback-fixture/acknowledge":
                Self.acknowledged = true
                body =
                    "{\"feedback\":\(feedback.replacingOccurrences(of: "\"can_acknowledge\":true", with: "\"can_acknowledge\":false").replacingOccurrences(of: "\"acknowledged_at\":null", with: "\"acknowledged_at\":\"2026-09-06T10:00:00Z\""))}"
            case "/api/players/-481/followers/count":
                body =
                    #"{"player_api_id":-481,"fans":2,"following":false,"share_url":"https://theacademywatch.com/p/-481"}"#
            case "/api/me/club-claims": body = #"{"claims":[]}"#
            case "/api/scout/players": body = #"{"players":[],"total":0,"page":1,"per_page":20,"total_pages":0}"#
            case "/api/scout/player-search": body = #"{"players":[]}"#
            default:
                status = 404
                body = #"{"error":"Offline fixture endpoint unavailable"}"#
            }
            let response = HTTPURLResponse(
                url: request.url!, statusCode: status, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(body.utf8))
            client?.urlProtocolDidFinishLoading(self)
        }
    }
#endif
