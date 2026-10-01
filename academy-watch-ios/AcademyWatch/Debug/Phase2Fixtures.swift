#if DEBUG && targetEnvironment(simulator)
    import Foundation

    /// Process-local fixture world. Unknown routes and writes fail closed, before URLSession.
    /// The same transport is used by offline journeys and the screenshot launcher.
    enum Phase2Fixtures {
        static var mode: String? {
            let args = ProcessInfo.processInfo.arguments
            guard let i = args.firstIndex(of: "-phase2Fixture"), args.indices.contains(i + 1) else {
                return nil
            }
            return args[i + 1]
        }
        static var screen: String? {
            let args = ProcessInfo.processInfo.arguments
            guard let i = args.firstIndex(of: "-phase2Preview"), args.indices.contains(i + 1) else {
                return nil
            }
            return args[i + 1]
        }
        static var active: Bool { mode != nil || screen != nil }
        static var resolvedMode: String {
            mode
                ?? ((["N09", "N09b", "N10", "N13"].contains(screen ?? "") || (screen ?? "").hasPrefix("post-"))
                    ? "owner" : screen == "N14" ? "coach" : "player")
        }
        static var isClubExperience: Bool {
            ["owner", "terminal", "editor", "coach", "recruiting", "signed", "draft", "full", "conflict", "nostaff", "membership-error", "pendingclub", "club-signed-out"].contains(resolvedMode)
        }
        static func contactFixture(_ data: Data, messages: Bool) throws -> Data {
            guard screen == "N17" || screen == "N01" else { return data }
            var dto = try JSONSerialization.jsonObject(with: data) as! [String: Any]
            func restyle(_ original: [String: Any]) -> [String: Any] {
                var request = original
                request["message"] = "A conversation about the next step."
                request["club_consent_note"] = "He is ready to be looked at. Speak to Sunil about dates."
                request["club_consent_at"] = "2026-08-25T10:45:00"
                request["responded_at"] = "2026-08-25T11:00:00"
                request["participants"] = [
                    "scout": ["display_name": "Corinne Shaw"],
                    "player": ["display_name": screen == "N01" ? "Reuben Castellane" : "Nabil Ferhane"],
                    "club": ["club_program_id": 101, "display_name": "Quillmere Athletic"],
                ]
                request["latest_outcome"] = [
                    "stage": "trial_scheduled", "notes": "Tue 6 Oct, 19:00 BST · Europe/London",
                    "occurred_at": "2026-08-26T09:00:00", "created_at": "2026-08-26T09:05:00",
                ]
                if screen == "N01" {
                    request["status"] = "pending"
                    request["club_consent_status"] = "granted"
                    request["messaging_open"] = false
                    request["responded_at"] = NSNull()
                    request["latest_outcome"] = NSNull()
                }
                return request
            }
            if messages {
                if let request = dto["contact_request"] as? [String: Any] {
                    dto["contact_request"] = restyle(request)
                }
                var rows = dto["messages"] as? [[String: Any]] ?? []
                let samples = [
                    (
                        "player", "Nabil Ferhane",
                        "Hi Corinne. Yes, definitely. Thank you for asking through the club. I have college until 4 most days, so evenings are best."
                    ),
                    (
                        "scout", "Corinne Shaw",
                        "Good. Our development group trains on a 3G pitch from 19:00. I will meet you at the gate at 18:40 so you are not walking in on your own."
                    ),
                    (
                        "club", "Idris Penhalow",
                        "All fine with us. Sunil has moved Nabil's individual session so he is fresh. Please let me know how he gets on, good or bad."
                    ),
                    (
                        "player", "Nabil Ferhane",
                        "My dad will drive me. Is it okay if he watches from the side?"
                    ),
                ]
                if rows.count == 3, var last = rows.first {
                    last["id"] = "50505050-1111-4111-8111-010101010104"
                    rows.append(last)
                }
                for i in rows.indices {
                    rows[i]["sender_role"] = samples[i % samples.count].0
                    rows[i]["sender_display_name"] = samples[i % samples.count].1
                    rows[i]["body"] = samples[i % samples.count].2
                    rows[i]["created_at"] =
                        "2026-08-\([25, 26, 26, 27][i % samples.count])T11:\(i == 2 ? "20" : "15"):00"
                }
                dto["messages"] = rows
                dto["total"] = rows.count
            } else if var rows = dto["requests"] as? [[String: Any]], !rows.isEmpty {
                rows[0] = restyle(rows[0])
                dto["requests"] = rows
            }
            return try JSONSerialization.data(withJSONObject: dto)
        }
        static let store = Phase2FixtureTransport(mode: resolvedMode)
        static func data(for request: URLRequest) throws -> Data { try store.data(for: request) }
    }

    final class Phase2FixtureTransport: @unchecked Sendable {
        static let postId = "10101010-1111-4111-8111-010101010101"
        static let applicationId = "20202020-1111-4111-8111-010101010101"
        let mode: String
        private let lock = NSLock()
        private var flagReads = 0
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
        private var editorPost: [String: Any]?
        init(mode: String) {
            self.mode = mode
            if mode == "recruiting" || mode == "owner" || mode == "full" || mode == "conflict" {
                status = "shortlisted"
                reservation = "none"
            }
            if Phase2Fixtures.screen == "N09" {
                status = "new"
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
                    URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems?.first(
                        where: {
                            $0.name == "page"
                        })?.value ?? "1") ?? 1
            let body =
                request.httpBody.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
                ?? [:]
            func json(_ value: Any) throws -> Data { try JSONSerialization.data(withJSONObject: value) }
            if path == "auth/me", method == "GET" {
                return try json([
                    "email": "phase2@fixture.invalid", "role": "user", "user_id": 7,
                    "display_name": "Reuben Castellane", "display_name_confirmed": true,
                    "is_journalist": false,
                    "is_curator": false, "is_verified_scout": false,
                ])
            }
            if path == "features" {
                flagReads += 1
                if mode == "foreground-failure" && flagReads > 1 { throw URLError(.timedOut) }
                return try json(
                    mode == "off"
                        ? ["contact_rail": false]
                        : [
                            "club_directory": true, "club_staff_access": mode != "nostaff",
                            "contact_rail": true,
                        ])
            }
            if path == "opportunities/features" {
                if mode == "off" { throw APIClientError.httpStatus(404) }
                return try json(["opportunities": true, "applications": true])
            }
            if method == "GET", path == "me/club-access" {
                if mode == "membership-error" { throw URLError(.timedOut) }
                return try json([
                    "programs": ["coach"].contains(mode)
                        ? [
                            [
                                "program": [
                                    "id": 101, "name": "Quillmere Athletic", "slug": "quillmere-athletic",
                                ],
                                "access": access,
                            ]
                        ] : []
                ])
            }
            if method == "GET", path == "funding/claims/me" {
                return try json([
                    "claims": ["owner", "terminal", "editor", "recruiting", "signed", "full", "conflict", "draft", "nostaff"]
                        .contains(mode)
                        ? [
                            [
                                "status": "approved",
                                "program": [
                                    "id": 101, "name": "Quillmere Athletic", "slug": "quillmere-athletic",
                                ],
                            ]
                        ] : []
                ])
            }
            if method == "GET", path == "club/101/access/me" { return try json(["access": access]) }
            if path == "club-directory/search", method == "POST" {
                if mode == "rate-limit" { throw APIClientError.httpStatus(429) }
                var card = club
                if let lat = body["lat"] as? Double, let lng = body["lng"] as? Double, lat.isFinite,
                    lng.isFinite
                {
                    card["distance_km"] = 0.8
                }
                let empty =
                    mode == "empty" || Phase2Fixtures.screen == "N02b"
                    || (body["q"] as? String)?.lowercased().contains("nobody") == true
                return try json([
                    "clubs": empty ? [] : directoryCards(card, body: body),
                    "total": empty ? 0 : directoryCards(card, body: body).count, "page": body["page"] ?? 1,
                    "has_more": false,
                ])
            }
            if path == "programs/thrandby-wrens", method == "GET",
                ["N02", "N04"].contains(Phase2Fixtures.screen ?? "")
            {
                var page = directoryCards(club, body: [:])[1]
                page["directory"] = [
                    "club_level": "amateur", "gender_programs": ["women", "girls"], "squad_count": 2,
                ]
                return try json(["program": page])
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
            if mode == "editor", path == "club/101/opportunities", method == "GET" {
                if var value = editorPost, value["status"] as? String == "published" {
                    // A retained application arrives between the publication response and the next read.
                    value["application_count"] = 1; editorPost = value
                }
                return try json(["opportunities": editorPost.map { [$0] } ?? [], "page": 1, "has_more": false])
            }
            if mode == "editor", path == "club/101/opportunities", method == "POST" {
                guard body["title"] is String, body["closes_at"] is String else {
                    throw APIClientError.server(statusCode: 422, message: "required_opportunity_details")
                }
                var value = body
                value["id"] = Self.postId; value["program_id"] = 101; value["club_name"] = "Quillmere Athletic"
                value["club_slug"] = "quillmere-athletic"; value["version"] = 1; value["application_count"] = 0
                value["created_at"] = "2026-10-01T10:00:00Z"; value["trial_invite_deadline"] = "2026-12-30T10:00:00Z"
                editorPost = value
                return try json(["opportunity": value])
            }
            if mode == "editor", path.hasPrefix("club/101/opportunities/"), method == "PATCH" || path.hasSuffix("/close") {
                guard var value = editorPost, body["expected_version"] as? Int == value["version"] as? Int else {
                    throw APIClientError.server(statusCode: 409, message: "version_conflict")
                }
                if (value["application_count"] as? Int ?? 0) > 0 && Set(body.keys).subtracting(["expected_version", "status"]).count > 0 {
                    throw APIClientError.server(statusCode: 409, message: "advertised_terms_locked")
                }
                value.merge(body) { _, new in new }; value.removeValue(forKey: "expected_version")
                value["version"] = (value["version"] as? Int ?? 0) + 1; editorPost = value
                return try json(["opportunity": value])
            }
            if path == "opportunities" || path == "club/101/opportunities", method == "GET" {
                return try json([
                    "opportunities": mode == "empty"
                        ? []
                        : reviewPosts(private: path.hasPrefix("club/")).filter { dto in
                            let type = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?
                                .queryItems?
                                .first(where: { $0.name == "type" })?.value
                            return type == nil || type == dto["type"] as? String
                        },
                    "page": requestedPage,
                    "has_more": false,
                ])
            }
            if method == "GET", path.hasPrefix("opportunities/"),
                let dto = reviewPosts(private: false).first(where: {
                    path == "opportunities/" + ($0["id"] as? String ?? "")
                })
            {
                return try json(["opportunity": dto])
            }
            if path == "opportunities/\(Self.postId)", method == "GET" {
                return try json(["opportunity": post(private: false)])
            }
            if path == "me/application-claims", method == "GET" {
                if mode == "claims-error" { throw URLError(.timedOut) }
                return try json([
                    "claims": mode == "parent" || mode == "ineligible"
                        ? [] : [["claim_id": 71, "signed_player_id": 900001, "name": "Reuben Castellane"]]
                ])
            }
            if path == "opportunities/\(Self.postId)/applications", method == "POST" {
                guard body["contact_consent"] as? Bool == true, body["client_request_id"] is String else {
                    throw APIClientError.server(statusCode: 400, message: "invalid_payload")
                }
                if mode == "closed" {
                    throw APIClientError.server(statusCode: 409, message: "opportunity_closed")
                }
                if mode == "ineligible" { throw APIClientError.httpStatus(403) }
                submitted = true
                status = "new"
                reservation = "none"
                return try json([
                    "application": application(private: false, position: body["position"] as? String)
                ])
            }
            if path == "me/applications" || path == "club/101/opportunities/\(Self.postId)/applications",
                method == "GET"
            {
                let empty =
                    mode == "empty" || Phase2Fixtures.screen == "N06b" || Phase2Fixtures.screen == "N09b"
                    || mode == "draft" || (mode == "apply" && !submitted)
                return try json([
                    "applications": empty ? [] : reviewApplications(private: path.hasPrefix("club/")),
                    "page": requestedPage,
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
            if method == "GET",
                path.hasPrefix("me/applications/") || path.hasPrefix("club/101/applications/"),
                let dto = reviewApplications(private: path.hasPrefix("club/")).first(where: {
                    path.hasSuffix("/" + ($0["id"] as? String ?? ""))
                })
            {
                return try json(["application": dto])
            }
            if path == "me/applications/\(Self.applicationId)"
                || path == "club/101/applications/\(Self.applicationId)",
                method == "GET"
            {
                return try json(["application": application(private: path.hasPrefix("club/"))])
            }
            if path.hasSuffix("/withdraw") || path.hasSuffix("/trial-response")
                || path.hasSuffix("/transition"),
                method == "POST"
            {
                guard path.contains("/applications/\(Self.applicationId)/") else {
                    throw ExperienceFixtureError.unmatchedRequest(method: method, path: path)
                }
                if mode == "conflict" || body["expected_version"] as? Int != version {
                    throw APIClientError.server(statusCode: 409, message: "version_conflict")
                }
                if mode == "full" { throw APIClientError.server(statusCode: 409, message: "trial_full") }
                if mode == "invalid-trial" {
                    throw APIClientError.server(statusCode: 422, message: "invalid_trial_at")
                }
                if path.hasSuffix("/withdraw") || body["response"] as? String == "decline" {
                    status = "withdrawn"
                    reservation = body["response"] as? String == "decline" ? "declined" : "released"
                } else if body["response"] as? String == "accept" {
                    reservation = "confirmed"
                } else if let target = body["status"] as? String {
                    if target == "signed", body["enrollment_confirmed"] as? Bool != true {
                        throw APIClientError.server(statusCode: 422, message: "separate_enrollment_required")
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
                        : [
                            squad(1, "First Team"), squad(2, "Reserves"), squad(3, "Under-18s"),
                            squad(4, "Under-16s"),
                            squad(5, "Under-21s"),
                        ]
                ])
            }
            if path == "club/101/roster", method == "GET" {
                return try json([
                    "members": Phase2Fixtures.screen == "N14"
                        ? reviewSquadMembers
                        : [
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
                            "id": 501, "squad_id": 3, "opponent_name": "Marrowby Colts U18",
                            "status": "finalized",
                            "match_date": "2026-09-26",
                        ]
                    ]
                ])
            }
            if path == "club/101/access", method == "GET" {
                guard mode != "coach" else { throw APIClientError.httpStatus(403) }
                return try json([
                    "me": access,
                    "people": Phase2Fixtures.screen == "N13"
                        ? reviewStaff
                        : revoked
                            ? []
                            : [
                                [
                                    "user_account_id": 22, "grant_id": 7, "display_name": "Niamh Byrne",
                                    "email": "niamh@fixture.invalid", "role": staffRole, "all_squads": false,
                                    "squad_ids": staffScope, "version": 1, "editable": true,
                                    "permissions": [true, true, false, false],
                                ]
                            ],
                    "invites": Phase2Fixtures.screen == "N13" ? reviewInvites : invited ? [invite] : [],
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
                return try Phase2Fixtures.contactFixture(
                    FloodlightPreview.fixture(
                        request.url?.query?.contains("box=inbox") == true
                            ? "contact_requests_inbox" : "contact_requests_sent"), messages: false)
            }
            if method == "GET", path.hasPrefix("contact/requests/"), path.hasSuffix("/messages") {
                return try Phase2Fixtures.contactFixture(
                    FloodlightPreview.fixture("contact_messages"), messages: true)
            }
            if method == "GET" {
                return try PlayerClubExperienceFixtures.data(for: request, mode: "development")
            }
            throw ExperienceFixtureError.unmatchedRequest(method: method, path: path)
        }
        private var access: [String: Any] {
            [
                "program_id": 101, "role": mode == "coach" ? "coach" : "owner", "verified": true,
                "whole_club": mode != "coach", "all_squads": Phase2Fixtures.screen != "N14",
                "squad_ids": mode == "coach" ? [3] : [],
                "capabilities": mode == "coach"
                    ? ["players.view", "matches.view", "feedback"]
                    : ["players.view", "matches.view", "recruiting", "access.view", "access.manage"],
            ]
        }
        private var club: [String: Any] {
            [
                "id": 101, "slug": "quillmere-athletic", "name": "Quillmere Athletic",
                "brand": ["primary_color": "#1F3A5F", "accent_color": "#E8B23A"], "city": "Quillmere",
                "region": "Wendleshire", "verified": true, "is_verified_program": true,
                "league": ["name": "Wendle & District Senior League"], "club_level": "semi_pro",
                "gender_programs": ["men", "boys"], "squad_count": 5,
                "open_opportunities": ["N02", "N03"].contains(Phase2Fixtures.screen ?? "") ? 3 : 1,
                "venue": ["name": "The Saltings 3G", "postcode": "XW4 2QA"], "distance_km": NSNull(),
                "program_provided": [
                    "summary":
                        "A community-owned club on the Wendle estuary. Most of our first team walked in off an open trial night."
                ],
            ]
        }
        private func post(private privateDTO: Bool) -> [String: Any] {
            var dto: [String: Any] = [
                "id": Self.postId, "program_id": 101, "club_name": "Quillmere Athletic",
                "club_slug": "quillmere-athletic", "title": "Open training night with the Reserves",
                "description":
                    "A training night, not a trial: no cuts. Bring 3G boots, shin pads and a drink.",
                "instructions": "Meet at 19:15. No metal studs.", "position_requirements": "All positions",
                "birth_year_min": 1980, "birth_year_max": 2008, "gender_program": "men",
                "timezone": "Europe/London",
                "starts_at": "2026-10-07T18:30:00Z", "ends_at": "2026-10-07T20:00:00Z",
                "closes_at": "2026-10-06T19:00:00Z", "venue": "The Saltings 3G",
                "address": "Quillmere XW4 2QA", "squad_id": 3,
                "status": (mode == "draft" || Phase2Fixtures.screen == "N09b") && !published
                    ? "draft" : "published",
                "type": "open_session", "version": published ? 2 : 1,
            ]
            if mode == "terminal" { dto["status"] = "closed" }
            if privateDTO {
                dto["created_at"] = "2026-10-01T10:00:00Z"
                dto["trial_invite_deadline"] = "2026-12-30T10:00:00Z"
                dto["capacity"] = 24
                dto["places_left"] = 22
                dto["application_count"] =
                    mode == "draft" || Phase2Fixtures.screen == "N09b"
                    ? 0 : Phase2Fixtures.screen == "N09" ? 14 : 1
            }
            if ["post-filled", "post-locked"].contains(Phase2Fixtures.screen ?? "") {
                dto["title"] = "Open trial — Reserves"; dto["type"] = "trial"
                dto["status"] = Phase2Fixtures.screen == "post-filled" ? "draft" : "published"
                if privateDTO { dto["application_count"] = Phase2Fixtures.screen == "post-filled" ? 0 : 1 }
            }
            if Phase2Fixtures.screen == "N09" {
                dto["title"] = "Open trial — First Team"
                dto["type"] = "trial"
                dto["starts_at"] = "2026-10-17T09:30:00Z"
                dto["ends_at"] = "2026-10-17T11:00:00Z"
                dto["closes_at"] = "2026-10-15T19:00:00Z"
            }
            if Phase2Fixtures.screen == "N09b" {
                dto["title"] = "Goalkeeper — First Team cover"
                dto["type"] = "position"
                dto["starts_at"] = NSNull()
                dto["ends_at"] = NSNull()
                dto["closes_at"] = "2026-10-31T20:00:00Z"
            }
            return dto
        }
        private func application(private privateDTO: Bool, position: String? = nil) -> [String: Any] {
            var dto: [String: Any] = [
                "id": Self.applicationId, "opportunity_id": Self.postId, "program_id": 101, "claim_id": 71,
                "signed_player_id": 900001, "status": status,
                "status_label": Phase2Application.label(status),
                "position": position ?? "Central midfield", "current_club": "Hallowfen Rovers",
                "version": version,
                "reservation_state": reservation, "submitted_at": "2026-09-23T10:00:00Z",
                "retention_expires_at": "2027-01-05T19:30:00Z",
                "opportunity_title": "Open training night with the Reserves",
                "club_name": "Quillmere Athletic",
                "timezone": "Europe/London",
            ]
            if status == "invited" {
                dto["trial_at"] = "2026-10-07T18:30:00Z"
                dto["trial_venue"] = "The Saltings 3G"
                dto["trial_instructions"] = "Meet at 19:15. No metal studs."
            }
            if privateDTO {
                dto["applicant_name"] = Phase2Fixtures.screen == "N09" ? "Declan Farrimond" : "Antoni Kurek"
                dto["transitions"] =
                    [
                        "new": ["shortlisted", "rejected"], "shortlisted": ["invited", "rejected"],
                        "invited": ["attended", "rejected"], "attended": ["offer", "rejected"],
                        "offer": ["signed", "rejected"],
                    ][status] ?? []
                dto["notes"] =
                    Phase2Fixtures.screen == "N10"
                    ? [
                        [
                            "id": "40404040-1111-4111-8111-010101010101",
                            "body":
                                "Saw him for Hallowfen reserves last season — tidy, good engine. Worth a look if Aaron’s suspension happens. Check he is not cup-tied.",
                            "created_at": "2026-09-25T20:30:00Z",
                        ]
                    ] + notes : notes
                dto["events"] = [
                    [
                        "from_state": NSNull(), "to_state": "new", "version": 1,
                        "created_at": "2026-09-23T10:00:00Z",
                    ]
                ]
                if reservation == "confirmed" {
                    dto["events"] =
                        (dto["events"] as! [[String: Any]]) + [
                            [
                                "from_state": "invited", "to_state": "invited",
                                "reason_code": "trial_confirmed",
                                "version": version, "created_at": "2026-10-01T10:00:00Z",
                            ]
                        ]
                }
            }
            return dto
        }
        private func directoryCards(_ base: [String: Any], body: [String: Any]) -> [[String: Any]] {
            guard ["N02", "N04"].contains(Phase2Fixtures.screen ?? "") else { return [base] }
            var wren = base
            wren["id"] = 102
            wren["slug"] = "thrandby-wrens"
            wren["name"] = "Thrandby Wrens"
            wren["city"] = "Thrandby"
            wren["club_level"] = "amateur"
            wren["gender_programs"] = ["women", "girls"]
            wren["squad_count"] = 2
            wren["open_opportunities"] = 1
            wren["brand"] = ["primary_color": "#6B1F3A", "accent_color": "#A8D8C8"]
            wren["distance_km"] = body["lat"] == nil ? NSNull() : 25.0
            return [base, wren].filter { card in
                let level = body["level"] as? String
                let programme = body["programme"] as? String
                return (level == nil || card["club_level"] as? String == level)
                    && (programme == nil || (card["gender_programs"] as? [String] ?? []).contains(programme!))
            }
        }
        private var reviewSquadMembers: [[String: Any]] {
            [
                ("Alfie Rowe", "Goalkeeper", 1), ("Kian Marsh", "Right-back", 2),
                ("Deji Adeyemi", "Centre-back", 4),
                ("Tomasz Ward", "Centre-back", 5), ("Rory Holt", "Central midfield", 6),
                ("Ibrahim Saleh", "Central midfield", 8), ("Jude Evans", "Striker", 9),
                ("Freddie Owen", "Winger", 11),
            ].enumerated().map { index, sample in
                [
                    "id": 401 + index, "squad_id": 3, "display_name": sample.0, "is_minor": true,
                    "position": sample.1,
                    "shirt_number": sample.2, "available": true,
                ]
            }
        }
        private var reviewStaff: [[String: Any]] {
            [
                ("Ruth Calloway", "owner", [Int]()), ("Idris Penhalow", "manager", [Int]()),
                ("Sunil Vadher", "coach", [5]), ("Niamh Garrity", "coach", [3]),
                ("Tobias Wrenfield", "analyst", [5, 3]), ("Gwen Ostler", "viewer", [4]),
            ].enumerated().map { index, sample in
                [
                    "user_account_id": index == 0 ? 7 : 20 + index,
                    "grant_id": index == 0 ? NSNull() : 5 + index,
                    "display_name": sample.0, "email": "staff\(index)@fixture.invalid", "role": sample.1,
                    "all_squads": false, "squad_ids": sample.2, "version": 1, "editable": index != 0,
                    "permissions": [
                        true, sample.1 != "viewer", sample.1 == "owner" || sample.1 == "manager",
                        sample.1 == "owner",
                    ],
                ]
            }
        }
        private func reviewApplications(private privateDTO: Bool) -> [[String: Any]] {
            let base = application(private: privateDTO)
            if Phase2Fixtures.screen == "N09" {
                let samples = [
                    ("Declan Farrimond", "Centre-back", "new"), ("Yaw Boadu-Sterling", "Winger", "new"),
                    ("Lewis Carmody", "Goalkeeper", "new"),
                    ("Antoni Kurek", "Central midfield", "shortlisted"),
                    ("Hugh Penhalow", "Striker", "shortlisted"), ("Alfie Rowe", "Full-back", "invited"),
                    ("Robin Wren", "Goalkeeper", "invited"), ("Kian Marsh", "Defender", "attended"),
                    ("Deji Adeyemi", "Midfield", "attended"), ("Rory Holt", "Winger", "offer"),
                    ("Ibrahim Saleh", "Midfield", "signed"), ("Freddie Owen", "Winger", "withdrawn"),
                    ("Tomasz Ward", "Centre-back", "rejected"), ("Jude Evans", "Striker", "rejected"),
                ]
                return samples.enumerated().map { index, sample in
                    var row = base
                    row["id"] =
                        index == 0
                        ? Self.applicationId : String(format: "20202020-1111-4111-8111-%012d", index)
                    row["applicant_name"] = sample.0
                    row["position"] = sample.1
                    row["status"] = index == 0 ? status : sample.2
                    row["status_label"] = Phase2Application.label(index == 0 ? status : sample.2)
                    row["current_club"] =
                        index == 0 ? "" : index == 1 ? "Pellowick Town" : index == 2 ? "" : "Hallowfen Rovers"
                    row["reservation_state"] = sample.2 == "invited" ? "pending" : "none"
                    row["submitted_at"] = index == 0 ? "2026-09-29T10:00:00Z" : "2026-09-30T10:00:00Z"
                    return row
                }
            }
            if ["N01", "N06"].contains(Phase2Fixtures.screen ?? "") {
                var signed = base
                signed["id"] = "20202020-1111-4111-8111-010101010102"
                signed["status"] = "signed"
                signed["status_label"] = "Signed"
                signed["opportunity_title"] = "Summer open trial"
                signed["submitted_at"] = "2026-07-23T10:00:00Z"
                signed["retention_expires_at"] = "2026-11-05T10:00:00Z"
                signed["trial_at"] = NSNull()
                signed["reservation_state"] = "none"
                var withdrawn = base
                withdrawn["id"] = "20202020-1111-4111-8111-010101010103"
                withdrawn["status"] = "withdrawn"
                withdrawn["status_label"] = "Withdrawn"
                withdrawn["opportunity_title"] = "Winter futsal squad"
                withdrawn["submitted_at"] = "2026-09-11T10:00:00Z"
                withdrawn["trial_at"] = NSNull()
                withdrawn["reservation_state"] = "released"
                return [base, signed, withdrawn]
            }
            return [base]
        }
        private func reviewPosts(private privateDTO: Bool) -> [[String: Any]] {
            let base = post(private: privateDTO)
            guard ["N01", "N03", "N04"].contains(Phase2Fixtures.screen ?? "") else { return [base] }
            var trial = base
            trial["id"] = "10101010-1111-4111-8111-010101010102"
            trial["type"] = "trial"
            trial["title"] = "Open trial — First Team"
            trial["starts_at"] = "2026-10-17T09:30:00Z"
            trial["ends_at"] = "2026-10-17T11:00:00Z"
            trial["closes_at"] = "2026-10-15T19:00:00Z"
            var position = base
            position["id"] = "10101010-1111-4111-8111-010101010103"
            position["type"] = "position"
            position["title"] = "Left-back wanted — Under-21s"
            position["starts_at"] = NSNull()
            position["ends_at"] = NSNull()
            position["closes_at"] = "2026-10-22T19:00:00Z"
            position["position_requirements"] = "Left-back"
            if Phase2Fixtures.screen == "N04" {
                var women = base
                women["id"] = "10101010-1111-4111-8111-010101010104"
                women["program_id"] = 102
                women["club_name"] = "Thrandby Wrens"
                women["club_slug"] = "thrandby-wrens"
                women["title"] = "Open training evening — Women's First Team"
                women["gender_program"] = "women"
                women["venue"] = "Coldharbour Rec"
                women["address"] = "Thrandby"
                women["starts_at"] = "2026-10-12T18:00:00Z"
                women["ends_at"] = "2026-10-12T19:30:00Z"
                women["closes_at"] = "2026-10-10T19:00:00Z"
                return [base, women, trial, position]
            }
            return [base, trial, position]
        }
        private var invite: [String: Any] {
            [
                "id": "30303030-1111-4111-8111-010101010101", "email": "new.coach@fixture.invalid",
                "role": "coach",
                "all_squads": false, "squad_ids": [3, 4], "status": "pending",
                "expires_at": "2026-10-08T10:00:00Z",
            ]
        }
        private func squad(_ id: Int, _ name: String) -> [String: Any] {
            ["id": id, "name": name, "kind": "youth", "age_limit": 18]
        }
        private var reviewInvites: [[String: Any]] {
            var pending = invite
            pending["email"] = "callum@saltings.example"
            pending["squad_ids"] = [2]
            pending["expires_at"] = "2026-10-06T10:00:00Z"
            var expired = invite
            expired["id"] = "30303030-1111-4111-8111-010101010102"
            expired["email"] = "bryn.h@saltings.example"
            expired["squad_ids"] = [4]
            expired["status"] = "expired"
            expired["expires_at"] = "2026-09-18T10:00:00Z"
            return [pending, expired]
        }
    }

    extension Phase2FixtureTransport: Phase2API {
        func phase2Data(path: String, method: String, query: [URLQueryItem], body: Data?) async throws
            -> Data
        {
            var components = URLComponents(string: "https://fixture.invalid/api/" + path)!
            components.queryItems = query.isEmpty ? nil : query
            var request = URLRequest(url: components.url!)
            request.httpMethod = method
            request.httpBody = body
            return try data(for: request)
        }
    }
#endif
