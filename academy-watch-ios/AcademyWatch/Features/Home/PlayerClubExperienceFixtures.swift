#if DEBUG && targetEnvironment(simulator)
    import Foundation

    /// Explicit offline UI-test transport. APIClient asks this seam for bytes
    /// before creating a URLSession task, so an unknown route cannot open a socket.
    enum PlayerClubExperienceFixtures {
        static let supportedModes = [
            "player", "club", "scout", "pending", "development", "reviewed",
        ]

        static var mode: String? {
            do {
                return try mode(from: ProcessInfo.processInfo.arguments)
            } catch {
                fatalError("Invalid simulator fixture configuration: \(error.localizedDescription)")
            }
        }

        static func mode(from arguments: [String]) throws -> String? {
            guard let index = arguments.firstIndex(of: "-experienceFixture") else { return nil }
            guard arguments.indices.contains(index + 1) else {
                throw ExperienceFixtureError.missingMode
            }
            let value = arguments[index + 1].lowercased()
            guard supportedModes.contains(value) else {
                throw ExperienceFixtureError.unknownMode(value)
            }
            return value
        }

        static func data(for request: URLRequest, mode: String) throws -> Data {
            guard supportedModes.contains(mode) else {
                throw ExperienceFixtureError.unknownMode(mode)
            }
            return try ExperienceFixtureStore.data(for: request, mode: mode)
        }
    }

    enum ExperienceFixtureError: LocalizedError, Equatable {
        case missingMode
        case unknownMode(String)
        case unmatchedRequest(method: String, path: String)

        var errorDescription: String? {
            switch self {
            case .missingMode:
                "-experienceFixture requires a fixture mode."
            case let .unknownMode(value):
                "Unknown -experienceFixture value: \(value)."
            case let .unmatchedRequest(method, path):
                "Offline fixture has no response for \(method) \(path)."
            }
        }
    }

    struct ExperienceTokenStore: TokenStoreProtocol {
        func loadToken() throws -> String? { nil }
        func saveToken(_ token: String) throws {}
        func deleteToken() throws {}
    }

    private enum ExperienceFixtureStore {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var accepted = false
        nonisolated(unsafe) private static var acknowledged = false
        nonisolated(unsafe) private static var progress: [String: Any]?

        static func data(for request: URLRequest, mode: String) throws -> Data {
            lock.lock()
            defer { lock.unlock() }

            let method = request.httpMethod ?? "GET"
            let path = request.url?.path ?? ""
            let body = try responseBody(method: method, path: path, request: request, mode: mode)
            return Data(body.utf8)
        }

        private static func responseBody(
            method: String,
            path: String,
            request: URLRequest,
            mode: String
        ) throws -> String {
            let isPending = mode == "pending"
            let claim = """
                {"id":71,"player_api_id":null,"local_player_id":481,"user_account_id":7,"relationship_type":"player","status":"\(isPending ? "pending" : "approved")","player_name":"Maya Okafor","contract_status":"unknown"}
                """
            var feedback = """
                {"id":"feedback-fixture","thread_id":"thread-fixture","revision":1,"player_api_id":-481,"program":{"id":44,"name":"Community FC"},"author":{"display_name":"Coach Alex"},"title":"Building your next pass","body":"Check your shoulder before receiving. In our next session, focus on finding the forward pass early.","published_at":"2026-09-05T10:00:00Z","acknowledged_at":\(acknowledged ? "\"2026-09-06T10:00:00Z\"" : "null"),"can_acknowledge":\(!acknowledged)}
                """
            let isDevelopment = ["development", "reviewed"].contains(mode)
            if isDevelopment {
                if path.hasSuffix("/progress") {
                    let update = requestJSON(request)
                    let version = (progress?["version"] as? Int ?? 0) + 1
                    let note = update["note"] as? String ?? ""
                    let nextStatus = update["status"] as? String ?? "working_on_it"
                    var history = progress?["history"] as? [[String: Any]] ?? []
                    history.append([
                        "version": version, "actor": "player", "status": nextStatus, "note": note,
                        "at": "2026-09-06T10:00:00Z",
                    ])
                    progress = [
                        "version": version, "status": nextStatus, "reflection": note,
                        "updated_at": "2026-09-06T10:00:00Z", "history": history,
                    ]
                }
                if mode == "reviewed", progress == nil {
                    progress = [
                        "version": 2, "status": "reviewed",
                        "reflection": "Scanning early helped me find the forward pass.",
                        "coach_note":
                            "Good progress, Maya. Keep the early scan when we add pressure next session.",
                        "updated_at": "2026-09-06T10:00:00Z", "history": [],
                    ]
                }
                var object =
                    (try? JSONSerialization.jsonObject(with: Data(feedback.utf8))) as? [String: Any] ?? [:]
                object["development_action"] = [
                    "focus": "See the next pass before receiving",
                    "practice":
                        "In the next small-sided game, check both shoulders before five receptions. Call out the forward option before the ball arrives.",
                    "success":
                        "Find the forward option early, then choose whether to turn or set the ball back.",
                    "review_on": "2026-09-12",
                ]
                object["development_progress"] = progress ?? NSNull()
                object["can_update_progress"] = true
                if let data = try? JSONSerialization.data(withJSONObject: object),
                    let value = String(data: data, encoding: .utf8)
                {
                    feedback = value
                }
            }

            switch (method, path) {
            case ("GET", "/api/health"):
                return #"{"status":"ok","fixture":true}"#
            case ("GET", "/api/auth/me"):
                return #"{"email":"sim.member@example.invalid","role":"user","user_id":7,"display_name":"Sim Member","display_name_confirmed":true,"is_journalist":false,"is_curator":false,"is_verified_scout":true}"#
            case ("GET", "/api/me/claims"):
                return "{\"claims\":[\(claim)]}"
            case ("GET", "/api/local-players/481/showcase"):
                return #"{"profile":{"bio":"Central midfielder, always looking for the next pass.","positions":"CM","preferred_foot":"right","height_cm":172,"status":"approved"},"photos":[],"reel":[]}"#
            case ("PATCH", "/api/local-players/481/showcase/profile"),
                 ("POST", "/api/local-players/481/showcase/reel"):
                return "{}"
            case ("GET", "/api/me/club-invitations"):
                return """
                    {"invitations":[{"id":"club-fixture","program_id":44,"program_name":"Community FC","player_api_id":-481,"status":"\(accepted ? "accepted" : "pending")","expires_at":"2027-01-01T00:00:00Z"}],"next_before":null}
                    """
            case ("POST", "/api/me/club-invitations/club-fixture/accept"):
                accepted = true
                return "{}"
            case ("GET", "/api/me/player-feedback"):
                return "{\"feedback\":[\(feedback)],\"next_before\":null}"
            case ("GET", "/api/me/player-feedback/feedback-fixture"),
                 ("POST", "/api/me/player-feedback/feedback-fixture/progress"):
                return "{\"feedback\":\(feedback)}"
            case ("POST", "/api/me/player-feedback/feedback-fixture/acknowledge"):
                acknowledged = true
                let acknowledgedFeedback = feedback
                    .replacingOccurrences(
                        of: "\"can_acknowledge\":true",
                        with: "\"can_acknowledge\":false"
                    )
                    .replacingOccurrences(
                        of: "\"acknowledged_at\":null",
                        with: "\"acknowledged_at\":\"2026-09-06T10:00:00Z\""
                    )
                return "{\"feedback\":\(acknowledgedFeedback)}"
            case ("GET", "/api/players/-481/followers/count"):
                return #"{"player_api_id":-481,"fans":2,"following":false,"share_url":"https://theacademywatch.com/p/-481"}"#
            case ("GET", "/api/me/club-claims"):
                return #"{"claims":[]}"#
            case ("GET", "/api/scout/watchlist"):
                return #"{"entries":[],"digest_opt_in":false,"scout_tier":"fixture"}"#
            case ("GET", "/api/scout/watchlist/ids"):
                return #"{"player_ids":[]}"#
            case ("GET", "/api/scout/lists"):
                return #"{"lists":[]}"#
            case ("GET", "/api/contact/requests"):
                let box = request.url?.query?.contains("box=inbox") == true ? "inbox" : "sent"
                return "{\"requests\":[],\"box\":\"\(box)\",\"total\":0,\"limit\":20,\"offset\":0}"
            case ("GET", "/api/seasons"):
                return #"{"current_season":2026,"bounds":{"min":2026,"max":2026},"seasons":[{"season":2026,"label":"2026/27","has_rollup":true,"is_current":true}]}"#
            case ("GET", "/api/scout/leaderboards"):
                return #"{"leaderboards":{},"limit":3,"phase":"all","season":2026}"#
            case ("GET", "/api/scout/players"):
                return """
                    {"players":[{"id":900001,"player_id":900001,"player_name":"Sim Player One","player_photo":null,"position":"Midfielder","age":19,"nationality":"Fixtureland","primary_team_id":9001,"primary_team_name":"Sim Academy","primary_team_api_id":9001,"loan_team_name":null,"loan_team_api_id":null,"loan_team_db_id":null,"loan_team_logo":null,"owner_team_id":null,"owner_team_name":null,"is_active":true,"status":"academy","pathway_status":"academy","current_level":"U21","data_source":"sim-fixture","data_depth":"fixture","sale_fee":null,"created_at":null,"updated_at":null,"appearances":3,"goals":1,"assists":2,"minutes_played":180,"avg_rating":7.2,"goal_contributions":3,"contributions_per90":1.5,"has_detailed_stats":false,"recent_form":[]}],"total":1,"page":1,"per_page":20,"total_pages":1,"season":2026}
                    """
            case ("GET", "/api/scout/player-search"):
                return #"{"players":[{"player_id":900001,"name":"Sim Player One","photo":null,"nationality":"Fixtureland","position":"Midfielder","age":19,"team":{"id":9001,"name":"Sim Academy","logo":null},"source":"api"}]}"#
            case ("GET", "/api/players/900001/profile"):
                return #"{"player_id":900001,"name":"Sim Player One","photo":null,"position":"Midfielder","status":"academy","age":19,"nationality":"Fixtureland","shadow":false,"loan_team_name":null,"loan_team_id":null,"loan_team_logo":null,"parent_team_name":"Sim Academy","parent_team_id":9001,"parent_team_logo":null,"owner_team_name":null,"owner_team_id":null,"owner_team_logo":null,"sale_fee":null}"#
            case ("GET", "/api/players/900001/stats"):
                return #"{"matches":[],"season":2026}"#
            case ("GET", "/api/players/900001/season-stats"):
                return #"{"player_id":900001,"season":"2026/2027","appearances":3,"minutes":180,"goals":1,"assists":2,"avg_rating":7.2,"saves":0,"goals_conceded":0,"clean_sheets":0,"source":"local-db","stats_coverage":"fixture","local_appearances":3,"clubs":[{"team_api_id":9001,"team_name":"Sim Academy","team_logo":null,"window_type":"Academy","is_current":true,"appearances":3,"minutes":180,"goals":1,"assists":2,"saves":0,"goals_conceded":0}],"provenance":null}"#
            case ("GET", "/api/players/900001/journey"):
                return #"{"player_id":900001,"source":"sim-fixture","birth_date":"2007-01-01","entries":[],"stints":[],"total_stints":0}"#
            case ("GET", "/api/players/900001/availability"):
                return #"{"player_id":900001,"season":2026,"degraded":false,"reason":null,"absences":[],"summary":{"total_absences":0,"by_reason":{},"last_absence":null}}"#
            case ("GET", "/api/players/900001/showcase"):
                return #"{"player_api_id":900001,"profile":{"id":900001,"player_api_id":900001,"bio":"Synthetic simulator profile.","positions":"CM","preferred_foot":"right","height_cm":175,"self_reported":true,"status":"approved","updated_at":"2026-09-08T00:00:00Z","contract_status":"academy","current_club_name":"Sim Academy","club_program_id":null,"status_contradiction":false,"contract_attestation_review_status":"approved"},"reel":[],"verified_footage":[],"claim_status":"unclaimed"}"#
            case ("GET", "/api/players/900001/followers/count"):
                return #"{"player_api_id":900001,"fans":0,"following":false,"share_url":"https://theacademywatch.com/p/900001"}"#
            default:
                throw ExperienceFixtureError.unmatchedRequest(method: method, path: path)
            }
        }

        private static func requestJSON(_ request: URLRequest) -> [String: Any] {
            var bytes = request.httpBody ?? Data()
            if bytes.isEmpty, let stream = request.httpBodyStream {
                stream.open()
                defer { stream.close() }
                var buffer = [UInt8](repeating: 0, count: 1024)
                while stream.hasBytesAvailable {
                    let count = stream.read(&buffer, maxLength: buffer.count)
                    if count <= 0 { break }
                    bytes.append(buffer, count: count)
                }
            }
            return (try? JSONSerialization.jsonObject(with: bytes)) as? [String: Any] ?? [:]
        }
    }
#endif
