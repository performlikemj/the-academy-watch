import Foundation

protocol ScoutAPIClientProtocol: Sendable {
    func fetchScoutPlayers(_ request: ScoutPlayersRequest) async throws -> ScoutPlayersResponse
    func fetchScoutLeaderboards(_ request: ScoutLeaderboardsRequest) async throws -> ScoutLeaderboardsResponse
}

protocol SeasonDirectoryAPIClientProtocol: Sendable {
    func fetchSeasons() async throws -> SeasonDirectory
}

protocol PlayerDetailAPIClientProtocol: Sendable {
    func fetchPlayerProfile(playerID: Int) async throws -> PlayerProfile
    func fetchPlayerSeasonStats(playerID: Int) async throws -> PlayerSeasonStats
    func fetchPlayerRecentFixtures(playerID: Int) async throws -> [PlayerRecentFixture]
    func fetchPlayerJourney(playerID: Int) async throws -> PlayerJourneyResponse
    func fetchPlayerAvailability(playerID: Int) async throws -> PlayerAvailability
    func fetchPlayerSeasonStats(playerID: Int, season: Int?) async throws -> PlayerSeasonStats
    func fetchPlayerRecentFixtures(playerID: Int, season: Int?) async throws -> [PlayerRecentFixture]
    func fetchPlayerAvailability(playerID: Int, season: Int?) async throws -> PlayerAvailability
}

extension PlayerDetailAPIClientProtocol {
    func fetchPlayerSeasonStats(playerID: Int, season _: Int?) async throws -> PlayerSeasonStats {
        try await fetchPlayerSeasonStats(playerID: playerID)
    }

    func fetchPlayerRecentFixtures(playerID: Int, season _: Int?) async throws -> [PlayerRecentFixture] {
        try await fetchPlayerRecentFixtures(playerID: playerID)
    }

    func fetchPlayerAvailability(playerID: Int, season _: Int?) async throws -> PlayerAvailability {
        try await fetchPlayerAvailability(playerID: playerID)
    }
}

protocol ShowcaseAPIClientProtocol: Sendable {
    func fetchPlayerShowcase(playerID: Int) async throws -> PlayerShowcaseResponse
    func updateOwnerShowcaseProfile(
        playerID: Int,
        profile: ShowcaseProfile?,
        attestation: PlayerContractAttestation
    ) async throws -> ShowcaseProfileResponse
}

protocol PlayerClaimAPIClientProtocol: Sendable {
    func fetchMyProfileClaims() async throws -> PlayerClaimsResponse
    func submitPlayerClaim(
        playerID: Int,
        attestation: PlayerContractAttestation
    ) async throws -> PlayerClaimResponse
}

protocol PlayerTakedownAPIClientProtocol: Sendable {
    func submitPlayerTakedownRequest(
        playerID: Int,
        requesterRole: TakedownRequesterRole,
        contactEmail: String,
        statement: String
    ) async throws
}

protocol AccountDataExportAPIClientProtocol: Sendable {
    func exportAccountData() async throws -> Data
}

protocol ScoutVerificationAPIClientProtocol: Sendable {
    func fetchScoutVerification() async throws -> ScoutVerificationResponse
    func submitScoutVerification(_ submission: ScoutVerificationSubmission) async throws -> ScoutVerificationResponse
}

protocol ContactAPIClientProtocol: Sendable {
    func createContactRequest(
        playerID: Int,
        message: String,
        permissionAttestation: Bool
    ) async throws -> ContactRequestResponse
}

protocol SentContactRequestsAPIClientProtocol: Sendable {
    func fetchSentContactRequests(limit: Int, offset: Int) async throws -> ContactRequestsResponse
    func withdrawContactRequest(requestID: String) async throws -> ContactRequestResponse
}

protocol IncomingContactRequestsAPIClientProtocol: Sendable {
    func fetchMyProfileClaims() async throws -> PlayerClaimsResponse
    func fetchIncomingContactRequests(limit: Int, offset: Int) async throws -> ContactRequestsResponse
    func acceptContactRequest(requestID: String) async throws -> ContactRequestResponse
    func declineContactRequest(requestID: String) async throws -> ContactRequestResponse
}

protocol ContactThreadAPIClientProtocol: Sendable {
    func fetchContactMessages(requestID: String, limit: Int, offset: Int) async throws -> ContactMessagesResponse
    func sendContactMessage(requestID: String, body: String) async throws -> ContactMessageResponse
    func reportContactOutcome(
        requestID: String,
        stage: ContactOutcomeStage,
        notes: String?,
        occurredAt: String?
    ) async throws -> ContactOutcomeResponse
}

protocol InterestSignalsAPIClientProtocol: Sendable {
    func fetchMyInterestSignals() async throws -> InterestSignalsResponse
}

protocol ContentReportAPIClientProtocol: Sendable {
    func submitContentReport(
        subjectType: ContentReportSubjectType,
        subjectID: String,
        reasonCode: String,
        details: String?
    ) async throws -> ContentReportResponse
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

protocol OnboardingAPIClientProtocol: Sendable {
    func createLocalPlayer(_ submission: LocalPlayerSubmission) async throws -> LocalPlayerCreateResponse
    func fetchLocalPlayer(id: Int) async throws -> LocalPlayerResponse
    func searchWorldwidePlayers(query: String) async throws -> WorldwidePlayerSearchResponse
    func addWorldwidePlayerFollow(
        listID: Int,
        player: WorldwidePlayer
    ) async throws -> FollowResponse
    func searchClubs(query: String) async throws -> ClubSearchResponse
    func fetchMyClubClaims() async throws -> ClubClaimsResponse
    func submitClubClaim(_ submission: ClubClaimSubmission) async throws -> ClubClaimResponse
    func verifyClubClaim(id: Int, proofURL: String) async throws -> ClubClaimResponse
}

struct APIClient: ScoutAPIClientProtocol,
    SeasonDirectoryAPIClientProtocol,
    PlayerDetailAPIClientProtocol,
    ShowcaseAPIClientProtocol,
    PlayerClaimAPIClientProtocol,
    PlayerTakedownAPIClientProtocol,
    AuthAPIClientProtocol,
    AccountAPIClientProtocol,
    AccountDataExportAPIClientProtocol,
    AccountDeletionAPIClientProtocol,
    BlocksAPIClientProtocol,
    ScoutVerificationAPIClientProtocol,
    ContactAPIClientProtocol,
    SentContactRequestsAPIClientProtocol,
    IncomingContactRequestsAPIClientProtocol,
    ContactThreadAPIClientProtocol,
    InterestSignalsAPIClientProtocol,
    ContentReportAPIClientProtocol,
    WatchlistAPIClientProtocol,
    FollowListsAPIClientProtocol,
    OnboardingAPIClientProtocol,
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

    func warmUp() async {
        #if DEBUG
        let startedAt = ProcessInfo.processInfo.systemUptime
        #endif

        do {
            let url = try makeURL(path: "health", queryItems: [])
            var request = URLRequest(url: url)
            request.httpMethod = "GET"
            request.cachePolicy = .reloadIgnoringLocalCacheData
            request.timeoutInterval = 60
            request.setValue("application/json", forHTTPHeaderField: "Accept")

            let (_, response) = try await session.data(for: request)
            #if DEBUG
            let elapsed = ProcessInfo.processInfo.systemUptime - startedAt
            let formattedElapsed = String(format: "%.3f", elapsed)
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? -1
            print("[LaunchPerformance] warm-up=/health elapsed=\(formattedElapsed)s status=\(statusCode)")
            #endif
        } catch {
            #if DEBUG
            let elapsed = ProcessInfo.processInfo.systemUptime - startedAt
            let formattedElapsed = String(format: "%.3f", elapsed)
            print("[LaunchPerformance] warm-up=/health elapsed=\(formattedElapsed)s failed=\(error.localizedDescription)")
            #endif
        }
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
        queryItems.appendIfPresent(name: "season", value: request.season.map(String.init))

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
        queryItems.appendIfPresent(name: "season", value: request.season.map(String.init))

        return try await get(
            path: "scout/leaderboards",
            queryItems: queryItems
        )
    }

    func fetchPlayerProfile(playerID: Int) async throws -> PlayerProfile {
        try await get(path: "players/\(playerID)/profile", queryItems: [])
    }

    func fetchSeasons() async throws -> SeasonDirectory {
        #if DEBUG
        let arguments = ProcessInfo.processInfo.arguments
        if let flagIndex = arguments.firstIndex(of: "-scoutDeskSeasonDelaySeconds"),
           arguments.indices.contains(flagIndex + 1),
           let delay = Double(arguments[flagIndex + 1]),
           delay > 0 {
            try await Task.sleep(
                nanoseconds: UInt64(min(delay, 120) * 1_000_000_000)
            )
        }
        #endif

        if let cached = await SeasonDirectoryMemoryCache.shared.value() {
            return cached
        }

        let directory: SeasonDirectory = try await get(path: "seasons", queryItems: [])
        await SeasonDirectoryMemoryCache.shared.store(directory)
        return directory
    }

    func fetchPlayerSeasonStats(playerID: Int) async throws -> PlayerSeasonStats {
        try await fetchPlayerSeasonStats(playerID: playerID, season: nil)
    }

    func fetchPlayerSeasonStats(playerID: Int, season: Int?) async throws -> PlayerSeasonStats {
        try await get(
            path: "players/\(playerID)/season-stats",
            queryItems: season.map { [URLQueryItem(name: "season", value: String($0))] } ?? []
        )
    }

    func fetchPlayerRecentFixtures(playerID: Int) async throws -> [PlayerRecentFixture] {
        try await fetchPlayerRecentFixtures(playerID: playerID, season: nil)
    }

    func fetchPlayerRecentFixtures(playerID: Int, season: Int?) async throws -> [PlayerRecentFixture] {
        let response: PlayerRecentFixturesResponse = try await get(
            path: "players/\(playerID)/stats",
            queryItems: season.map { [URLQueryItem(name: "season", value: String($0))] } ?? []
        )
        return response.matches
    }

    func fetchPlayerJourney(playerID: Int) async throws -> PlayerJourneyResponse {
        try await get(path: "players/\(playerID)/journey", queryItems: [])
    }

    func fetchPlayerAvailability(playerID: Int) async throws -> PlayerAvailability {
        try await fetchPlayerAvailability(playerID: playerID, season: nil)
    }

    func fetchPlayerAvailability(playerID: Int, season: Int?) async throws -> PlayerAvailability {
        try await get(
            path: "players/\(playerID)/availability",
            queryItems: season.map { [URLQueryItem(name: "season", value: String($0))] } ?? []
        )
    }

    func fetchPlayerShowcase(playerID: Int) async throws -> PlayerShowcaseResponse {
        try await get(path: "players/\(playerID)/showcase", queryItems: [])
    }

    func updateOwnerShowcaseProfile(
        playerID: Int,
        profile: ShowcaseProfile?,
        attestation: PlayerContractAttestation
    ) async throws -> ShowcaseProfileResponse {
        try await send(
            path: "players/\(playerID)/showcase/profile",
            method: "PUT",
            body: OwnerShowcaseProfileUpdate(
                profile: profile,
                attestation: attestation
            )
        )
    }

    func fetchMyProfileClaims() async throws -> PlayerClaimsResponse {
        try await get(path: "me/claims", queryItems: [])
    }

    func submitPlayerClaim(
        playerID: Int,
        attestation: PlayerContractAttestation
    ) async throws -> PlayerClaimResponse {
        try await send(
            path: "players/\(playerID)/claim",
            method: "POST",
            body: PlayerClaimSubmission(attestation: attestation)
        )
    }

    func fetchScoutVerification() async throws -> ScoutVerificationResponse {
        try await get(path: "scout/verification", queryItems: [])
    }

    func submitScoutVerification(
        _ submission: ScoutVerificationSubmission
    ) async throws -> ScoutVerificationResponse {
        try await send(
            path: "scout/verification",
            method: "POST",
            body: submission
        )
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

    func fetchCurrentAccount() async throws -> AuthProfileResponse {
        try await get(path: "auth/me", queryItems: [])
    }

    func exportAccountData() async throws -> Data {
        try await requestData(
            path: "account/export",
            method: "GET",
            queryItems: [],
            body: nil
        ).data
    }

    func deleteAccount() async throws -> AccountDeletionResponse {
        try await send(
            path: "account/delete",
            method: "POST",
            body: AccountDeletionRequest(confirm: "DELETE")
        )
    }

    func fetchBlockedUsers() async throws -> BlockedUsersResponse {
        try await get(path: "blocks", queryItems: [])
    }

    func blockUser(accountID: Int) async throws {
        let _: EmptyResponse = try await send(
            path: "blocks",
            method: "POST",
            body: BlockUserRequest(accountId: accountID)
        )
    }

    func unblockUser(accountID: Int) async throws {
        let _: EmptyResponse = try await perform(
            path: "blocks/\(accountID)",
            method: "DELETE",
            queryItems: [],
            body: nil
        )
    }

    func createContactRequest(
        playerID: Int,
        message: String,
        permissionAttestation: Bool
    ) async throws -> ContactRequestResponse {
        try await send(
            path: "contact/requests",
            method: "POST",
            body: CreateContactRequestBody(
                playerApiId: playerID,
                message: message,
                permissionAttestation: permissionAttestation
            )
        )
    }

    func submitPlayerTakedownRequest(
        playerID: Int,
        requesterRole: TakedownRequesterRole,
        contactEmail: String,
        statement: String
    ) async throws {
        let _: EmptyResponse = try await send(
            path: "players/\(playerID)/takedown-request",
            method: "POST",
            body: PlayerTakedownRequestBody(
                requesterRole: requesterRole,
                contactEmail: contactEmail,
                statement: statement
            )
        )
    }

    func fetchSentContactRequests(limit: Int, offset: Int) async throws -> ContactRequestsResponse {
        try await get(
            path: "contact/requests",
            queryItems: [
                URLQueryItem(name: "box", value: "sent"),
                URLQueryItem(name: "limit", value: String(limit)),
                URLQueryItem(name: "offset", value: String(offset)),
            ]
        )
    }

    func withdrawContactRequest(requestID: String) async throws -> ContactRequestResponse {
        try await perform(
            path: "contact/requests/\(requestID)/withdraw",
            method: "POST",
            queryItems: [],
            body: nil
        )
    }

    func fetchIncomingContactRequests(limit: Int, offset: Int) async throws -> ContactRequestsResponse {
        try await get(
            path: "contact/requests",
            queryItems: [
                URLQueryItem(name: "box", value: "inbox"),
                URLQueryItem(name: "limit", value: String(limit)),
                URLQueryItem(name: "offset", value: String(offset)),
            ]
        )
    }

    func acceptContactRequest(requestID: String) async throws -> ContactRequestResponse {
        try await perform(
            path: "contact/requests/\(requestID)/accept",
            method: "POST",
            queryItems: [],
            body: nil
        )
    }

    func declineContactRequest(requestID: String) async throws -> ContactRequestResponse {
        try await perform(
            path: "contact/requests/\(requestID)/decline",
            method: "POST",
            queryItems: [],
            body: nil
        )
    }

    func fetchContactMessages(
        requestID: String,
        limit: Int,
        offset: Int
    ) async throws -> ContactMessagesResponse {
        try await get(
            path: "contact/requests/\(requestID)/messages",
            queryItems: [
                URLQueryItem(name: "limit", value: String(limit)),
                URLQueryItem(name: "offset", value: String(offset)),
            ]
        )
    }

    func sendContactMessage(requestID: String, body: String) async throws -> ContactMessageResponse {
        try await send(
            path: "contact/requests/\(requestID)/messages",
            method: "POST",
            body: CreateContactMessageBody(body: body)
        )
    }

    func reportContactOutcome(
        requestID: String,
        stage: ContactOutcomeStage,
        notes: String?,
        occurredAt: String?
    ) async throws -> ContactOutcomeResponse {
        try await send(
            path: "contact/requests/\(requestID)/outcome",
            method: "POST",
            body: ReportContactOutcomeBody(
                stage: stage,
                notes: notes,
                occurredAt: occurredAt
            )
        )
    }

    func fetchMyInterestSignals() async throws -> InterestSignalsResponse {
        try await get(path: "showcase/mine/interest-signals", queryItems: [])
    }

    func submitContentReport(
        subjectType: ContentReportSubjectType,
        subjectID: String,
        reasonCode: String,
        details: String?
    ) async throws -> ContentReportResponse {
        try await send(
            path: "reports",
            method: "POST",
            body: SubmitContentReportBody(
                subjectType: subjectType,
                subjectId: subjectID,
                reasonCode: reasonCode,
                details: details
            )
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

    func createLocalPlayer(_ submission: LocalPlayerSubmission) async throws -> LocalPlayerCreateResponse {
        try await send(path: "local-players", method: "POST", body: submission)
    }

    func fetchLocalPlayer(id: Int) async throws -> LocalPlayerResponse {
        try await get(path: "local-players/\(id)", queryItems: [])
    }

    func searchWorldwidePlayers(query: String) async throws -> WorldwidePlayerSearchResponse {
        try await get(
            path: "scout/player-search",
            queryItems: [URLQueryItem(name: "q", value: query)]
        )
    }

    func addWorldwidePlayerFollow(
        listID: Int,
        player: WorldwidePlayer
    ) async throws -> FollowResponse {
        try await send(
            path: "scout/lists/\(listID)/follows",
            method: "POST",
            body: WorldwidePlayerFollowSubmission(player: player)
        )
    }

    func searchClubs(query: String) async throws -> ClubSearchResponse {
        try await get(
            path: "clubs/search",
            queryItems: [URLQueryItem(name: "q", value: query)]
        )
    }

    func fetchMyClubClaims() async throws -> ClubClaimsResponse {
        try await get(path: "me/club-claims", queryItems: [])
    }

    func submitClubClaim(_ submission: ClubClaimSubmission) async throws -> ClubClaimResponse {
        try await send(path: "clubs/claim", method: "POST", body: submission)
    }

    func verifyClubClaim(id: Int, proofURL: String) async throws -> ClubClaimResponse {
        try await send(
            path: "me/club-claims/\(id)/verify",
            method: "POST",
            body: ClubClaimProofSubmission(proofUrl: proofURL)
        )
    }

    func fetchComparison(
        playerIDs: [Int],
        includeAvailability: Bool
    ) async throws -> CompareResponse {
        try await fetchComparison(
            playerIDs: playerIDs,
            includeAvailability: includeAvailability,
            season: nil
        )
    }

    func fetchComparison(
        playerIDs: [Int],
        includeAvailability: Bool,
        season: Int?
    ) async throws -> CompareResponse {
        var queryItems = [
            URLQueryItem(name: "ids", value: playerIDs.map(String.init).joined(separator: ",")),
            URLQueryItem(name: "include_availability", value: includeAvailability ? "true" : "false"),
        ]
        queryItems.appendIfPresent(name: "season", value: season.map(String.init))
        return try await get(
            path: "scout/compare",
            queryItems: queryItems
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
        #if DEBUG
        let requestStartedAt = ProcessInfo.processInfo.systemUptime
        #endif
        let result = try await requestData(
            path: path,
            method: method,
            queryItems: queryItems,
            body: body
        )
        let data = result.data

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        do {
            if data.isEmpty, let empty = EmptyResponse() as? Response {
                return empty
            }
            let decoded = try decoder.decode(Response.self, from: data)
            #if DEBUG
            let decodedAt = ProcessInfo.processInfo.systemUptime
            let networkDuration = String(format: "%.3f", result.receivedAt - requestStartedAt)
            let decodeDuration = String(format: "%.3f", decodedAt - result.receivedAt)
            print(
                "[LaunchPerformance] endpoint=/\(path) network=\(networkDuration)s decode=\(decodeDuration)s bytes=\(data.count)"
            )
            #endif
            return decoded
        } catch {
            throw APIClientError.decoding(error)
        }
    }

    private func requestData(
        path: String,
        method: String,
        queryItems: [URLQueryItem],
        body: Data?
    ) async throws -> (data: Data, receivedAt: TimeInterval) {
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
        let responseReceivedAt = ProcessInfo.processInfo.systemUptime
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIClientError.invalidResponse
        }
        guard (200 ... 299).contains(httpResponse.statusCode) else {
            if httpResponse.statusCode == 401, let token {
                await authSession?.invalidate(credential: token)
            }
            if let payload = Self.errorPayload(from: data) {
                let message = [payload.error, payload.message]
                    .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
                    .first { !$0.isEmpty }
                    ?? "The service returned an error (HTTP \(httpResponse.statusCode))."
                if let code = payload.code?.trimmingCharacters(in: .whitespacesAndNewlines),
                   !code.isEmpty {
                    throw APIClientError.codedServer(
                        statusCode: httpResponse.statusCode,
                        message: message,
                        code: code,
                        cooldownDays: payload.cooldownDays
                    )
                }
                throw APIClientError.server(statusCode: httpResponse.statusCode, message: message)
            }
            throw APIClientError.httpStatus(httpResponse.statusCode)
        }
        return (data, responseReceivedAt)
    }

    private static func errorPayload(from data: Data) -> APIErrorPayload? {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(APIErrorPayload.self, from: data)
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

private actor SeasonDirectoryMemoryCache {
    static let shared = SeasonDirectoryMemoryCache()

    private var directory: SeasonDirectory?

    func value() -> SeasonDirectory? {
        directory
    }

    func store(_ directory: SeasonDirectory) {
        self.directory = directory
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
    case codedServer(statusCode: Int, message: String, code: String, cooldownDays: Int?)
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
        case let .codedServer(_, message, _, _):
            return message
        case .encoding:
            return "The request could not be prepared."
        case .decoding:
            return "The service response format was not recognized."
        }
    }

    var statusCode: Int? {
        switch self {
        case let .httpStatus(statusCode),
             let .server(statusCode, _),
             let .codedServer(statusCode, _, _, _):
            return statusCode
        case .invalidURL, .invalidResponse, .encoding, .decoding:
            return nil
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

private struct AccountDeletionRequest: Encodable {
    let confirm: String
}

private struct BlockUserRequest: Encodable {
    let accountId: Int
}

private struct PlayerTakedownRequestBody: Encodable {
    let requesterRole: TakedownRequesterRole
    let contactEmail: String
    let statement: String
}

private struct EmptyResponse: Decodable {}

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
    let code: String?
    let cooldownDays: Int?
}
