import SwiftUI
import XCTest
@testable import AcademyWatch

/// The match-lines read (`GET /players/<id>/matches?view=lines`): decoding the
/// server's answer as-is, the failed-read and account rules, the scout desk
/// card, and the hero's contrast over a bright photo.
final class PlayerMatchLinesTests: XCTestCase {
    override func setUp() {
        super.setUp()
        MatchLinesURLProtocol.reset()
    }

    override func tearDown() {
        MatchLinesURLProtocol.reset()
        super.tearDown()
    }

    private func makeClient() -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MatchLinesURLProtocol.self]
        return APIClient(baseURL: URL(string: "https://example.test/api")!, session: URLSession(configuration: configuration))
    }

    private static let serverBody = #"""
    {"view":"lines","truncated":false,"seasons":[{"season":2026,"lines":[
      {"key":"2026-09-27|durnsea juniors","season":2026,"match_date":"2026-09-27","opponent":"Durnsea Juniors","competition":"Wendle & District Senior League, Premier Division","home_away":"away","result_for":1,"result_against":1,"minutes":74,"goals":0,"assists":0,"yellows":1,"reds":0,"saves":null,"goals_conceded":null,"confirmation":"club_confirmed","self_report":"differs","shared_slot":false},
      {"key":"2026-09-13|pellowick town","season":2026,"match_date":"2026-09-13","opponent":"Pellowick Town","competition":null,"home_away":"away","result_for":null,"result_against":null,"minutes":90,"goals":0,"assists":1,"yellows":0,"reds":0,"saves":null,"goals_conceded":null,"confirmation":"self_reported","self_report":null,"shared_slot":false}],
      "totals":{"matches":2,"appearances":2,"full_matches":1,"minutes":164,"goals":0,"assists":1,"yellows":1,"reds":0,"cards_known":true,"saves":null,"goals_conceded":null,"keeper_matches":0,"club_confirmed":1,"self_reported_only":1,"differing":1}}]}
    """#

    // MARK: The request and the answer

    func testTheLinesReadAsksTheSameRouteTheWebUsesAndDecodesItUnchanged() async throws {
        MatchLinesURLProtocol.setHandler { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.path, "/api/players/-41/matches")
            XCTAssertEqual(request.url?.query, "view=lines")
            return (200, Data(Self.serverBody.utf8))
        }

        let response = try await makeClient().fetchPlayerMatchLines(playerID: -41)

        XCTAssertFalse(response.truncated)
        let season = try XCTUnwrap(response.seasons.first)
        XCTAssertEqual(season.season, 2026)
        XCTAssertEqual(season.lines.map(\.key), ["2026-09-27|durnsea juniors", "2026-09-13|pellowick town"])
        XCTAssertEqual(season.lines[0].confirmation, .clubConfirmed)
        XCTAssertEqual(season.lines[0].selfReport, .differs)
        XCTAssertEqual(season.lines[0].minutes, 74)
        XCTAssertEqual(season.lines[1].confirmation, .selfReported)
        XCTAssertNil(season.lines[1].selfReport)
        XCTAssertNil(season.lines[1].resultFor)
        XCTAssertNil(season.lines[1].competition)
        // Totals are the server's; the device adds nothing up.
        XCTAssertEqual(season.totals.matches, 2)
        XCTAssertEqual(season.totals.minutes, 164)
        XCTAssertEqual(season.totals.clubConfirmed, 1)
        XCTAssertEqual(season.totals.selfReportedOnly, 1)
        XCTAssertEqual(season.totals.differing, 1)
        XCTAssertTrue(season.totals.cardsKnown)
        XCTAssertNil(season.totals.saves)
    }

    func testEveryReviewStateIsTheServerMergeOutputAndDecodes() throws {
        let url = try XCTUnwrap(Bundle.main.url(forResource: "player_card_states", withExtension: "json"))
        let root = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        let states = try XCTUnwrap(root["states"] as? [String: Any])
        XCTAssertEqual(
            Set(states.keys),
            ["photo", "no-photo", "no-matches", "full-season", "mismatch", "long-names", "several-photos",
             "keeper", "white-photo", "read-failed", "provider", "totals-failed"]
        )
        for (name, value) in states {
            let entry = try XCTUnwrap(value as? [String: Any])
            let lines = try PlayerCardPresentationTests.decode(PlayerMatchLinesResponse.self, try XCTUnwrap(entry["matches"]))
            for season in lines.seasons {
                XCTAssertEqual(season.totals.matches, season.lines.count, name)
                XCTAssertEqual(season.totals.minutes, season.lines.reduce(0) { $0 + ($1.minutes ?? 0) }, name)
                XCTAssertEqual(season.totals.clubConfirmed, season.lines.filter(\.isClubConfirmed).count, name)
                XCTAssertEqual(Set(season.lines.map(\.key)).count, season.lines.count, "one line per match: \(name)")
            }
            _ = try PlayerCardPresentationTests.decode(PlayerProfile.self, try XCTUnwrap(entry["profile"]))
            _ = try PlayerCardPresentationTests.decode(PlayerShowcaseResponse.self, try XCTUnwrap(entry["showcase"]))
            _ = try PlayerCardPresentationTests.decode(PlayerSeasonStats.self, try XCTUnwrap(entry["season-stats"]))
        }
        let mismatch = try PlayerCardPresentationTests.serverSeason("mismatch")
        XCTAssertEqual(mismatch.lines.map(\.selfReport), [.differs, .matches, nil])
        XCTAssertEqual(mismatch.lines.first?.minutes, 74, "the club's figures are the line when the reports differ")
        XCTAssertEqual(mismatch.totals.minutes, 254)
    }

    // MARK: Failed reads and the account boundary

    @MainActor
    func testNotFoundIsAnEmptyAnswerNotAFailure() async {
        let model = PlayerMatchLinesViewModel(playerID: 7, apiClient: StubLinesClient { throw APIClientError.httpStatus(404) })
        XCTAssertTrue(model.isAwaitingFirstAnswer)
        await model.load()
        XCTAssertTrue(model.hasLines)
        XCTAssertFalse(model.failed)
        XCTAssertTrue(model.seasons.isEmpty)
        XCTAssertFalse(model.isAwaitingFirstAnswer)
    }

    @MainActor
    func testAFailedReadIsNeverAnEmptySeasonAndRetryRecovers() async throws {
        let answers = AnswerQueue([
            .failure(APIClientError.server(statusCode: 503, message: "down")),
            .success(try Self.response()),
            .failure(URLError(.timedOut)),
        ])
        let model = PlayerMatchLinesViewModel(playerID: 7, apiClient: StubLinesClient { try await answers.next() })

        await model.load()
        XCTAssertTrue(model.failed)
        XCTAssertFalse(model.hasLines, "a failed first read holds no answer — the page must not call the season empty")
        XCTAssertFalse(model.isAwaitingFirstAnswer)

        await model.retry()
        XCTAssertFalse(model.failed)
        XCTAssertTrue(model.hasLines)
        XCTAssertEqual(model.seasons.first?.totals.matches, 2)

        await model.load()
        XCTAssertTrue(model.failed)
        XCTAssertTrue(model.hasLines, "the last good lines stay on screen behind the error")
        XCTAssertEqual(model.seasons.first?.lines.count, 2)
    }

    @MainActor
    func testNothingOfThePreviousAccountSurvivesASwitchAndALateAnswerIsDiscarded() async throws {
        let gate = AnswerGate()
        let first = try Self.response()
        let model = PlayerMatchLinesViewModel(playerID: 7, apiClient: StubLinesClient {
            await gate.wait()
            return first
        })

        let pending = Task { await model.load() }
        await gate.waitUntilEntered()
        model.resetAccount()
        XCTAssertTrue(model.seasons.isEmpty)
        XCTAssertFalse(model.hasLines)
        await gate.open()
        await pending.value

        XCTAssertTrue(model.seasons.isEmpty, "the previous account's answer arrived after the switch and is dropped")
        XCTAssertFalse(model.hasLines)
        XCTAssertFalse(model.failed)

        let loaded = PlayerMatchLinesViewModel(playerID: 7, apiClient: StubLinesClient { first })
        await loaded.load()
        XCTAssertTrue(loaded.hasLines)
        loaded.resetAccount()
        XCTAssertTrue(loaded.seasons.isEmpty)
        XCTAssertFalse(loaded.truncated)
        XCTAssertTrue(loaded.isAwaitingFirstAnswer)
    }

    @MainActor
    func testTheShowcaseOfThePreviousAccountIsDroppedOnASwitch() async throws {
        let signedIn = try PlayerCardPresentationTests.decode(PlayerShowcaseResponse.self, [
            "player_api_id": 7,
            "profile": ["player_api_id": 7, "agent_name": "A. Mensah", "agent_contact_email": "agent@example.invalid"],
        ] as [String: Any])
        let signedOut = try PlayerCardPresentationTests.decode(PlayerShowcaseResponse.self, [
            "player_api_id": 7, "profile": ["player_api_id": 7, "agent_name": "A. Mensah"],
        ] as [String: Any])
        let answers = AnswerQueue([.success(signedIn), .success(signedOut)])
        let model = ShowcaseViewModel(playerID: 7, apiClient: StubShowcaseClient { try await answers.next() })

        await model.loadIfNeeded()
        XCTAssertEqual(PlayerCardText.profileFacts(model.showcase?.profile).last?.label, "Agent email")

        model.resetAccount()
        XCTAssertNil(model.showcase, "the signed-in reader's agent email must not stay on screen after sign-out")
        await model.loadIfNeeded()
        XCTAssertEqual(PlayerCardText.profileFacts(model.showcase?.profile).map(\.label), ["Agent"])
    }

    func testAPublicProfileContractStatusNeverBreaksTheShowcase() throws {
        for status in ["under_contract", "expiring", "free_agent", "something_new"] {
            let showcase = try PlayerCardPresentationTests.decode(PlayerShowcaseResponse.self, [
                "player_api_id": 7, "claim_status": "claimed",
                "profile": ["player_api_id": 7, "positions": "RB", "self_reported": true, "contract_status": status],
            ] as [String: Any])
            XCTAssertTrue(showcase.isClaimedProfile, status)
            XCTAssertEqual(showcase.profile?.rawContractStatus, status)
        }
        // An owner's response: the claim attestation plus the profile's own status.
        let owner = try PlayerCardPresentationTests.decode(ShowcaseProfile.self, [
            "player_api_id": 7, "contract_status": "contracted", "profile_contract_status": "expiring",
        ])
        XCTAssertEqual(owner.contractStatus, .contracted)
        XCTAssertEqual(PlayerCardText.profileFacts(owner).first?.value, "Contract expiring")
    }

    @MainActor
    func testASeasonTotalsNotFoundIsAnAnswerAndTheSeasonPickIsTracked() async {
        let model = PlayerDetailViewModel(playerID: -41, apiClient: StubDetailClient())
        XCTAssertFalse(model.hasExplicitSeason)
        await model.loadIfNeeded()
        XCTAssertNil(model.errorMessage(for: .seasonStats), "404 means no totals for this identity, not a failed read")
        XCTAssertNil(model.seasonStats)
        XCTAssertFalse(model.isLoading(.seasonStats))

        await model.selectSeason(2025)
        XCTAssertTrue(model.hasExplicitSeason)
        XCTAssertEqual(model.selectedSeason, 2025)
        XCTAssertTrue(PlayerDetailViewModel(playerID: 1, initialSeason: 2024, apiClient: StubDetailClient()).hasExplicitSeason)
    }

    // MARK: Scout desk card

    func testDeskCardShowsNoCountersForClubOrPlayerEnteredSeasons() throws {
        let rows = try deskRows("desk")
        XCTAssertEqual(rows.count, 6)
        for row in rows.prefix(5) {
            XCTAssertTrue(ScoutPlayerCard.counters(for: row).isEmpty, "\(row.playerName): club/player-entered figures stay off the card")
            XCTAssertNil(row.approvedPhotoURL)
            XCTAssertNotEqual(row.clubConfirmed, true)
        }
        XCTAssertEqual(rows[0].appearances, 1, "the row does carry figures — the card withholds them")
        let provider = try XCTUnwrap(rows.last)
        XCTAssertEqual(ScoutPlayerCard.counters(for: provider).map { "\($0.value) \($0.unit)" }, ["30 apps", "2,412 min"])
        XCTAssertEqual(ScoutPlayerCard.line(for: rows[0]), "Right-back at Quillmere Athletic.")
        XCTAssertEqual(ScoutPlayerCard.line(for: rows[2]), "Winger.")
        XCTAssertNotNil(rows[1].photoURL, "a provider headshot is a face inside the initials tile, never the portrait")
    }

    func testDeskCardLightsUpFromTheServerCardFieldsWhenTheyArrive() throws {
        let rows = try deskRows("desk-next")
        let kofi = rows[0]
        XCTAssertNotNil(kofi.approvedPhotoURL)
        XCTAssertEqual(kofi.clubConfirmed, true)
        XCTAssertEqual(ScoutPlayerCard.line(for: kofi), "Right-back at Quillmere Athletic. Five seasons in the first team.")
        XCTAssertEqual(ScoutPlayerCard.counters(for: kofi).map { "\($0.value) \($0.unit)" }, ["1 app", "90 min"])
        // The same numbers the player's page shows for the same season.
        let page = try PlayerCardPresentationTests.serverSeason("full-season").totals
        XCTAssertEqual(rows[1].appearances, page.appearances)
        XCTAssertEqual(rows[1].minutesPlayed, page.minutes)
    }

    func testPositionChipUsesTheWebCodes() {
        XCTAssertEqual(ScoutPlayerCard.role(for: "Right-back"), "RB")
        XCTAssertEqual(ScoutPlayerCard.role(for: "Goalkeeper"), "GK")
        XCTAssertEqual(ScoutPlayerCard.role(for: "Attacking midfielder"), "AM")
        XCTAssertEqual(ScoutPlayerCard.role(for: "Winger"), "W")
        XCTAssertEqual(ScoutPlayerCard.role(for: "Midfielder"), "MID")
        XCTAssertEqual(ScoutPlayerCard.role(for: "left_wing_back, CB"), "LWB")
        XCTAssertEqual(ScoutPlayerCard.role(for: "Libero"), "LIB")
        XCTAssertNil(ScoutPlayerCard.role(for: "  "))
        XCTAssertNil(ScoutPlayerCard.role(for: nil))
    }

    func testScoutRowsWithoutTheCardFieldsStillDecodeAndRoundTripTheCache() throws {
        let row = try deskRows("desk")[5]
        let cached = try JSONDecoder().decode(ScoutPlayerSummary.self, from: JSONEncoder().encode(row))
        XCTAssertEqual(cached, row)
        XCTAssertNil(cached.bioLine)
    }

    private func deskRows(_ key: String) throws -> [ScoutPlayerSummary] {
        let url = try XCTUnwrap(Bundle.main.url(forResource: "player_card_states", withExtension: "json"))
        let root = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        return try PlayerCardPresentationTests.decode(ScoutPlayersResponse.self, try XCTUnwrap(root[key])).players
    }

    // MARK: Design rules

    func testClubColoursFallBackToGreenAndGold() {
        XCTAssertEqual(PlayerClubColors(), .standard)
        XCTAssertEqual(PlayerClubColors(primaryHex: nil, accentHex: "not a colour"), .standard)
        XCTAssertEqual(PlayerClubColors.hexValue("#1B2A4A"), 0x1B2A4A)
        XCTAssertNil(PlayerClubColors.hexValue("1B2A4A"))
        XCTAssertNil(PlayerClubColors.hexValue("#FFF"))
        XCTAssertNotEqual(PlayerClubColors(primaryHex: "#1B2A4A", accentHex: "#FFFFFF"), .standard)
    }

    /// The hero text starts below the point where the scrim reaches 90% night,
    /// so even over a pure white photo every line clears 4.5:1.
    func testHeroTextOverAWhitePhotoMeetsContrast() {
        XCTAssertGreaterThanOrEqual(PlayerHeroCard.Scrim.textInset, PlayerHeroCard.Scrim.ninety)
        let night = UIColor(AcademyColors.night)
        let opacity = PlayerHeroCard.Scrim.ninetyOpacity
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        night.getRed(&r, green: &g, blue: &b, alpha: &a)
        // Worst case: the lightest the backdrop can be behind any text = white under 90% night.
        let worst = UIColor(
            red: r * opacity + (1 - opacity), green: g * opacity + (1 - opacity),
            blue: b * opacity + (1 - opacity), alpha: 1
        )
        for text in [AcademyColors.chalk, AcademyColors.onNight] {
            XCTAssertGreaterThanOrEqual(contrast(UIColor(text), worst), 4.5)
        }
    }

    func testCardAndTileTextMeetsContrastInBothAppearances() {
        let paper = UIColor(AcademyColors.paper)
        for text in [AcademyColors.ink, AcademyColors.cardBody, AcademyColors.muted, AcademyColors.goodOnPaper] {
            XCTAssertGreaterThanOrEqual(contrast(UIColor(text), paper), 4.5)
        }
        let club = UIColor(AcademyColors.club)
        for text in [AcademyColors.chalk, AcademyColors.onClub, AcademyColors.gold] {
            XCTAssertGreaterThanOrEqual(contrast(UIColor(text), club), 4.5)
        }
        for style in [UIUserInterfaceStyle.light, .dark] {
            let traits = UITraitCollection(userInterfaceStyle: style)
            let surface = UIColor(AcademyColors.cardSurface).resolvedColor(with: traits)
            for text in [AcademyColors.text, AcademyColors.secondaryText, AcademyColors.good, AcademyColors.strongSecondary] {
                XCTAssertGreaterThanOrEqual(contrast(UIColor(text).resolvedColor(with: traits), surface), 4.5)
            }
            let page = UIColor(AcademyColors.background).resolvedColor(with: traits)
            XCTAssertGreaterThanOrEqual(contrast(UIColor(AcademyColors.strongSecondary).resolvedColor(with: traits), page), 4.5)
        }
    }

    private func contrast(_ first: UIColor, _ second: UIColor) -> Double {
        let a = luminance(first), b = luminance(second)
        return (max(a, b) + 0.05) / (min(a, b) + 0.05)
    }

    private func luminance(_ color: UIColor) -> Double {
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        color.getRed(&r, green: &g, blue: &b, alpha: &a)
        let linear = [r, g, b].map { Double($0) <= 0.04045 ? Double($0) / 12.92 : Foundation.pow((Double($0) + 0.055) / 1.055, 2.4) }
        return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722
    }

    // MARK: Offline review transport

    #if DEBUG && targetEnvironment(simulator)
    func testReviewStatesAnswerOfflineAndAFailedReadIsARealFailure() throws {
        func request(_ path: String) -> URLRequest {
            URLRequest(url: URL(string: "http://offline.invalid/api/\(path)")!)
        }
        let lines = try XCTUnwrap(PlayerCardReviewFixtures.data(for: request("players/900001/matches?view=lines"), state: "mismatch"))
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        XCTAssertEqual(try decoder.decode(PlayerMatchLinesResponse.self, from: lines).seasons.first?.totals.differing, 1)

        XCTAssertThrowsError(try PlayerCardReviewFixtures.data(for: request("players/900001/matches"), state: "read-failed"))
        XCTAssertThrowsError(try PlayerCardReviewFixtures.data(for: request("players/900001/season-stats"), state: "totals-failed"))
        XCTAssertThrowsError(try PlayerCardReviewFixtures.data(for: request("players/900001/profile"), state: "no-such-state"))
        XCTAssertNil(try PlayerCardReviewFixtures.data(for: request("players/900001/availability"), state: "photo"))
        XCTAssertNil(try PlayerCardReviewFixtures.data(for: request("scout/leaderboards"), state: "desk"))

        // Review photos are bundled files: no review image is fetched from a network.
        let showcase = try decoder.decode(
            PlayerShowcaseResponse.self,
            from: try XCTUnwrap(PlayerCardReviewFixtures.data(for: request("players/900001/showcase"), state: "several-photos"))
        )
        XCTAssertEqual(showcase.publicPhotos.count, 3)
        XCTAssertTrue(showcase.publicPhotos.allSatisfy { $0.url?.isFileURL == true })
    }
    #endif

    private static func response() throws -> PlayerMatchLinesResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(PlayerMatchLinesResponse.self, from: Data(serverBody.utf8))
    }
}

// MARK: - Test doubles

private struct StubLinesClient: PlayerMatchLinesAPIClientProtocol {
    let answer: @Sendable () async throws -> PlayerMatchLinesResponse
    func fetchPlayerMatchLines(playerID _: Int) async throws -> PlayerMatchLinesResponse { try await answer() }
}

private struct StubShowcaseClient: ShowcaseAPIClientProtocol {
    let answer: @Sendable () async throws -> PlayerShowcaseResponse
    func fetchPlayerShowcase(playerID _: Int) async throws -> PlayerShowcaseResponse { try await answer() }
    func updateOwnerShowcaseProfile(
        playerID _: Int, profile _: ShowcaseProfile?, attestation _: PlayerContractAttestation
    ) async throws -> ShowcaseProfileResponse {
        throw APIClientError.invalidResponse
    }
}

/// Profile loads; season totals answer 404 (no totals for this identity).
private struct StubDetailClient: PlayerDetailAPIClientProtocol {
    func fetchPlayerProfile(playerID: Int) async throws -> PlayerProfile {
        try PlayerCardPresentationTests.decode(PlayerProfile.self, ["player_id": playerID, "name": "Kofi Asante-Reid"])
    }
    func fetchPlayerSeasonStats(playerID _: Int) async throws -> PlayerSeasonStats { throw APIClientError.httpStatus(404) }
    func fetchPlayerSeasonStats(playerID _: Int, season _: Int?) async throws -> PlayerSeasonStats {
        throw APIClientError.server(statusCode: 404, message: "Player not found")
    }
    func fetchPlayerRecentFixtures(playerID _: Int) async throws -> [PlayerRecentFixture] { [] }
    func fetchPlayerRecentFixtures(playerID _: Int, season _: Int?) async throws -> [PlayerRecentFixture] { [] }
    func fetchPlayerJourney(playerID _: Int) async throws -> PlayerJourneyResponse { throw APIClientError.httpStatus(404) }
    func fetchPlayerAvailability(playerID _: Int) async throws -> PlayerAvailability { throw APIClientError.httpStatus(404) }
    func fetchPlayerAvailability(playerID _: Int, season _: Int?) async throws -> PlayerAvailability {
        throw APIClientError.httpStatus(404)
    }
}

private actor AnswerQueue<Value: Sendable> {
    private var answers: [Result<Value, Error>]
    init(_ answers: [Result<Value, Error>]) { self.answers = answers }
    func next() throws -> Value {
        guard !answers.isEmpty else { throw APIClientError.invalidResponse }
        return try answers.removeFirst().get()
    }
}

private actor AnswerGate {
    private var entered = false
    private var isOpen = false
    private var waiters: [CheckedContinuation<Void, Never>] = []
    private var entryWaiters: [CheckedContinuation<Void, Never>] = []

    func wait() async {
        entered = true
        entryWaiters.forEach { $0.resume() }
        entryWaiters = []
        if isOpen { return }
        await withCheckedContinuation { waiters.append($0) }
    }

    func waitUntilEntered() async {
        if entered { return }
        await withCheckedContinuation { entryWaiters.append($0) }
    }

    func open() {
        isOpen = true
        waiters.forEach { $0.resume() }
        waiters = []
    }
}

private final class MatchLinesURLProtocol: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var handler: ((URLRequest) throws -> (Int, Data))?

    static func setHandler(_ value: @escaping (URLRequest) throws -> (Int, Data)) {
        lock.lock()
        handler = value
        lock.unlock()
    }

    static func reset() {
        lock.lock()
        handler = nil
        lock.unlock()
    }

    override class func canInit(with _: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.lock.lock()
        let handler = Self.handler
        Self.lock.unlock()
        do {
            guard let handler, let url = request.url else { throw URLError(.badServerResponse) }
            let (status, data) = try handler(request)
            let response = HTTPURLResponse(
                url: url, statusCode: status, httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"]
            )!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}
