#if DEBUG && targetEnvironment(simulator)
    import Foundation

    /// Process-local fixture world. Unknown routes and writes fail closed, before URLSession.
    /// The same transport is used by offline journeys and the screenshot launcher.
    enum Phase2Fixtures {
        static var mode: String? {
            let args = ProcessInfo.processInfo.arguments
            guard let i = args.firstIndex(of: "-phase2Fixture"), args.indices.contains(i + 1) else { return nil }
            return args[i + 1]
        }
        static var screen: String? {
            let args = ProcessInfo.processInfo.arguments
            guard let i = args.firstIndex(of: "-phase2Preview"), args.indices.contains(i + 1) else { return nil }
            return args[i + 1]
        }
        static var active: Bool { mode != nil || screen != nil }
        static var resolvedMode: String {
            mode
                ?? (["N09", "N09b", "N10", "N13"].contains(screen ?? "")
                    ? "owner" : screen == "N14" ? "coach" : "player")
        }
        static var isClubExperience: Bool {
            ["owner", "coach", "recruiting", "signed", "draft", "full", "conflict"].contains(resolvedMode)
        }
        static let store = Phase2FixtureTransport(mode: resolvedMode)
        static func data(for request: URLRequest) throws -> Data { try store.data(for: request) }
    }

    final class Phase2FixtureTransport: @unchecked Sendable {
        static let postId = "10101010-1111-4111-8111-010101010101"
        static let applicationId = "20202020-1111-4111-8111-010101010101"
        let mode: String
        private let lock = NSLock()
        private var submitted = false
        private var version = 1
        private var status = "invited"
        private var reservation = "pending"
        private var staffRole = "coach"
        private var staffScope = [3, 4]
        private var revoked = false
        private var invited = false
        private var published = false
        private var notes: [[String: Any]] = []
        init(mode: String) {
            self.mode = mode
            if mode == "recruiting" || mode == "owner" || mode == "full" || mode == "conflict" {
                status = "shortlisted"
                reservation = "none"
            }
            if mode == "signed" {
                status = "offer"
                reservation = "confirmed"
            }
        }
        func data(for request: URLRequest) throws -> Data {
            lock.lock()
            defer { lock.unlock() }
            let path = request.url?.path.replacingOccurrences(of: "/api/", with: "") ?? ""
            let method = request.httpMethod ?? "GET"
            let requestedPage =
                Int(
                    URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems?.first(where: {
                        $0.name == "page"
                    })?.value ?? "1") ?? 1
            let body = request.httpBody.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
            func json(_ value: Any) throws -> Data { try JSONSerialization.data(withJSONObject: value) }
            if path == "auth/me", method == "GET" {
                return try json([
                    "email": "phase2@fixture.invalid", "role": "user", "user_id": 7,
                    "display_name": "Reuben Castellane", "display_name_confirmed": true, "is_journalist": false,
                    "is_curator": false, "is_verified_scout": false,
                ])
            }
            if path == "features" {
                return try json(
                    mode == "off"
                        ? ["contact_rail": false]
                        : ["club_directory": true, "club_staff_access": true, "contact_rail": true])
            }
            if path == "opportunities/features" {
                if mode == "off" { throw APIClientError.httpStatus(404) }
                return try json(["opportunities": true, "applications": true])
            }
            if method == "GET", path == "me/club-access" {
                return try json([
                    "programs": ["owner", "coach", "recruiting", "signed", "full", "conflict", "draft"].contains(mode)
                        ? [
                            [
                                "program": ["id": 101, "name": "Quillmere Athletic", "slug": "quillmere-athletic"],
                                "access": access,
                            ]
                        ] : []
                ])
            }
            if method == "GET", path == "funding/claims/me" { return try json(["claims": []]) }
            if method == "GET", path == "club/101/access/me" { return try json(["access": access]) }
            if path == "club-directory/search", method == "POST" {
                var card = club
                if let lat = body["lat"] as? Double, let lng = body["lng"] as? Double, lat.isFinite, lng.isFinite {
                    card["distance_km"] = 0.8
                }
                let empty =
                    mode == "empty" || Phase2Fixtures.screen == "N02b"
                    || (body["q"] as? String)?.lowercased().contains("nobody") == true
                return try json([
                    "clubs": empty ? [] : [card], "total": empty ? 0 : 1, "page": body["page"] ?? 1, "has_more": false,
                ])
            }
            if path == "programs/quillmere-athletic", method == "GET" {
                var page = club
                page.removeValue(forKey: "distance_km")
                page["directory"] = [
                    "venue": ["name": "The Saltings 3G", "postcode": "XW4 2QA"], "club_level": "semi_pro",
                    "gender_programs": ["men", "boys"], "squad_count": 5,
                ]
                return try json(["program": page])
            }
            if path == "opportunities" || path == "club/101/opportunities", method == "GET" {
                return try json([
                    "opportunities": mode == "empty" ? [] : [post(private: path.hasPrefix("club/"))],
                    "page": requestedPage,
                    "has_more": false,
                ])
            }
            if path == "opportunities/\(Self.postId)", method == "GET" {
                return try json(["opportunity": post(private: false)])
            }
            if path == "me/application-claims", method == "GET" {
                return try json([
                    "claims": mode == "parent" || mode == "ineligible"
                        ? [] : [["claim_id": 71, "signed_player_id": 900001, "name": "Reuben Castellane"]]
                ])
            }
            if path == "opportunities/\(Self.postId)/applications", method == "POST" {
                guard body["contact_consent"] as? Bool == true, body["client_request_id"] is String else {
                    throw APIClientError.server(statusCode: 400, message: "invalid_payload")
                }
                if mode == "closed" { throw APIClientError.server(statusCode: 409, message: "opportunity_closed") }
                if mode == "ineligible" { throw APIClientError.httpStatus(403) }
                submitted = true
                status = "new"
                reservation = "none"
                return try json(["application": application(private: false, position: body["position"] as? String)])
            }
            if path == "me/applications" || path == "club/101/opportunities/\(Self.postId)/applications",
                method == "GET"
            {
                let empty =
                    mode == "empty" || Phase2Fixtures.screen == "N06b" || Phase2Fixtures.screen == "N09b"
                    || mode == "draft" || (mode == "apply" && !submitted)
                return try json([
                    "applications": empty ? [] : [application(private: path.hasPrefix("club/"))], "page": requestedPage,
                    "has_more": false,
                ])
            }
            if path == "club/101/opportunities/\(Self.postId)", method == "PATCH" {
                guard body["expected_version"] as? Int == 1 else {
                    throw APIClientError.server(statusCode: 409, message: "version_conflict")
                }
                published = true
                return try json(["opportunity": post(private: true)])
            }
            if path == "me/applications/\(Self.applicationId)" || path == "club/101/applications/\(Self.applicationId)",
                method == "GET"
            {
                return try json(["application": application(private: path.hasPrefix("club/"))])
            }
            if path.hasSuffix("/withdraw") || path.hasSuffix("/trial-response") || path.hasSuffix("/transition"),
                method == "POST"
            {
                if mode == "conflict" || body["expected_version"] as? Int != version {
                    throw APIClientError.server(statusCode: 409, message: "version_conflict")
                }
                if mode == "full" { throw APIClientError.server(statusCode: 409, message: "trial_full") }
                if path.hasSuffix("/withdraw") || body["response"] as? String == "decline" {
                    status = "withdrawn"
                    reservation = body["response"] as? String == "decline" ? "declined" : "released"
                } else if body["response"] as? String == "accept" {
                    reservation = "confirmed"
                } else if let target = body["status"] as? String {
                    if target == "signed", body["enrollment_confirmed"] as? Bool != true {
                        throw APIClientError.server(statusCode: 400, message: "separate_enrollment_required")
                    }
                    status = target
                    if status == "invited" { reservation = "pending" }
                }
                version += 1
                return try json(["application": application(private: path.hasPrefix("club/"))])
            }
            if path == "club/101/applications/\(Self.applicationId)/notes", method == "POST" {
                let note: [String: Any] = [
                    "id": UUID().uuidString,
                    "body": (body["body"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines),
                    "created_at": "2026-10-01T10:00:00Z",
                ]
                notes.append(note)
                return try json(["note": note])
            }
            if path == "club/101/squads", method == "GET" {
                return try json([
                    "squads": mode == "coach"
                        ? [squad(3, "Under-18s")]
                        : [squad(1, "First Team"), squad(2, "Reserves"), squad(3, "Under-18s"), squad(4, "Under-16s")]
                ])
            }
            if path == "club/101/roster", method == "GET" {
                return try json([
                    "members": [
                        [
                            "id": 401, "squad_id": 3, "display_name": "Nabil Ferhane", "is_minor": true,
                            "shirt_number": 8, "position": "Midfield", "available": true,
                        ]
                    ]
                ])
            }
            if path == "club/101/matches", method == "GET" {
                return try json([
                    "matches": [
                        [
                            "id": 501, "squad_id": 3, "opponent_name": "Marrowby Colts U18", "status": "finalized",
                            "match_date": "2026-09-26",
                        ]
                    ]
                ])
            }
            if path == "club/101/access", method == "GET" {
                guard mode != "coach" else { throw APIClientError.httpStatus(403) }
                return try json([
                    "me": access,
                    "people": revoked
                        ? []
                        : [
                            [
                                "user_account_id": 22, "grant_id": 7, "display_name": "Niamh Byrne",
                                "email": "niamh@fixture.invalid", "role": staffRole, "all_squads": false,
                                "squad_ids": staffScope, "version": 1, "editable": true,
                                "permissions": [true, true, false, false],
                            ]
                        ], "invites": invited ? [invite] : [],
                    "matrix": ["rows": ["Players", "Matches", "Recruiting", "Staff access"]],
                ])
            }
            if path == "club/101/staff-invites", method == "POST" {
                invited = true
                return try json(["invite": invite, "email_sent": true])
            }
            if path.hasPrefix("club/101/staff-invites/"), path.hasSuffix("/revoke"), method == "POST" {
                invited = false
                return try json(["invite": invite])
            }
            if path == "club/101/access/7", method == "PATCH" {
                staffRole = body["role"] as? String ?? staffRole
                staffScope = body["squad_ids"] as? [Int] ?? staffScope
                return try json(["grant": ["id": 7]])
            }
            if path == "club/101/access/7", method == "DELETE" {
                revoked = true
                return try json(["grant": ["id": 7]])
            }
            if method == "GET", path == "contact/requests" {
                return try FloodlightPreview.fixture(
                    request.url?.query?.contains("box=inbox") == true
                        ? "contact_requests_inbox" : "contact_requests_sent")
            }
            if method == "GET", path.hasPrefix("contact/requests/"), path.hasSuffix("/messages") {
                return try FloodlightPreview.fixture("contact_messages")
            }
            if method == "GET" { return try PlayerClubExperienceFixtures.data(for: request, mode: "development") }
            throw ExperienceFixtureError.unmatchedRequest(method: method, path: path)
        }
        private var access: [String: Any] {
            [
                "program_id": 101, "role": mode == "coach" ? "coach" : "owner", "verified": true,
                "whole_club": mode != "coach", "all_squads": true, "squad_ids": mode == "coach" ? [3] : [],
                "capabilities": mode == "coach"
                    ? ["players.view", "matches.view", "feedback"]
                    : ["players.view", "matches.view", "recruiting", "access.view", "access.manage"],
            ]
        }
        private var club: [String: Any] {
            [
                "id": 101, "slug": "quillmere-athletic", "name": "Quillmere Athletic",
                "brand": ["primary_color": "#0F3D2E", "accent_color": "#CFAE62"], "city": "Quillmere",
                "region": "Wendleshire", "verified": true, "is_verified_program": true,
                "league": ["name": "Wendle & District Senior League"], "club_level": "semi_pro",
                "gender_programs": ["men", "boys"], "squad_count": 5, "open_opportunities": 1,
                "venue": ["name": "The Saltings 3G", "postcode": "XW4 2QA"], "distance_km": NSNull(),
                "program_provided": ["summary": "A community-owned club on the Wendle estuary."],
            ]
        }
        private func post(private privateDTO: Bool) -> [String: Any] {
            var dto: [String: Any] = [
                "id": Self.postId, "program_id": 101, "club_name": "Quillmere Athletic",
                "club_slug": "quillmere-athletic", "title": "Open training night with the Reserves",
                "description": "A training night, not a trial: no cuts. Bring 3G boots, shin pads and a drink.",
                "instructions": "Meet at 19:15. No metal studs.", "position_requirements": "All positions",
                "birth_year_min": 1980, "birth_year_max": 2008, "gender_program": "men", "timezone": "Europe/London",
                "starts_at": "2026-10-07T18:30:00Z", "ends_at": "2026-10-07T20:00:00Z",
                "closes_at": "2026-10-06T19:00:00Z", "venue": "The Saltings 3G", "address": "Quillmere XW4 2QA",
                "status": (mode == "draft" || Phase2Fixtures.screen == "N09b") && !published ? "draft" : "published",
                "type": "open_session", "version": published ? 2 : 1,
            ]
            if privateDTO {
                dto["capacity"] = 24
                dto["places_left"] = 22
                dto["application_count"] = mode == "draft" || Phase2Fixtures.screen == "N09b" ? 0 : 1
            }
            return dto
        }
        private func application(private privateDTO: Bool, position: String? = nil) -> [String: Any] {
            var dto: [String: Any] = [
                "id": Self.applicationId, "opportunity_id": Self.postId, "program_id": 101, "claim_id": 71,
                "signed_player_id": 900001, "status": status, "status_label": Phase2Application.label(status),
                "position": position ?? "Central midfield", "current_club": "Hallowfen Rovers", "version": version,
                "reservation_state": reservation, "submitted_at": "2026-09-23T10:00:00Z",
                "retention_expires_at": "2027-01-05T19:30:00Z",
                "opportunity_title": "Open training night with the Reserves", "club_name": "Quillmere Athletic",
                "timezone": "Europe/London",
            ]
            if status == "invited" {
                dto["trial_at"] = "2026-10-07T18:30:00Z"
                dto["trial_venue"] = "The Saltings 3G"
                dto["trial_instructions"] = "Meet at 19:15. No metal studs."
            }
            if privateDTO {
                dto["applicant_name"] = "Antoni Kurek"
                dto["transitions"] =
                    [
                        "new": ["shortlisted", "rejected"], "shortlisted": ["invited", "rejected"],
                        "invited": ["attended", "rejected"], "offer": ["signed", "rejected"],
                    ][status] ?? []
                dto["notes"] = notes
                dto["events"] = [
                    ["from_state": NSNull(), "to_state": "new", "version": 1, "created_at": "2026-09-23T10:00:00Z"]
                ]
            }
            return dto
        }
        private var invite: [String: Any] {
            [
                "id": "30303030-1111-4111-8111-010101010101", "email": "new.coach@fixture.invalid", "role": "coach",
                "all_squads": false, "squad_ids": [3, 4], "status": "pending", "expires_at": "2026-10-08T10:00:00Z",
            ]
        }
        private func squad(_ id: Int, _ name: String) -> [String: Any] {
            ["id": id, "name": name, "kind": "youth", "age_limit": 18]
        }
    }

    extension Phase2FixtureTransport: Phase2API {
        func phase2Data(path: String, method: String, query: [URLQueryItem], body: Data?) async throws -> Data {
            var components = URLComponents(string: "https://fixture.invalid/api/" + path)!
            components.queryItems = query.isEmpty ? nil : query
            var request = URLRequest(url: components.url!)
            request.httpMethod = method
            request.httpBody = body
            return try data(for: request)
        }
    }
#endif
