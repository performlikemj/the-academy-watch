import Foundation
import XCTest
@testable import AcademyWatch

/// Covers POST `/players/<signed id>/matches` for the add-a-game sheet: request
/// encoding, 201-created vs 200-updated handling, lenient season_stats decode,
/// and 400 message surfacing.
final class PlayerMatchAPIClientTests: XCTestCase {
    override func setUp() {
        super.setUp()
        PlayerMatchURLProtocol.reset()
    }

    override func tearDown() {
        PlayerMatchURLProtocol.reset()
        super.tearDown()
    }

    private static let matchBody = #"{"match":{"id":812,"player_api_id":-41,"season":2025,"match_date":"2026-08-30","competition":"U18 Premier League","opponent":"Coventry U18","home_away":"home","result_for":2,"result_against":1,"minutes":74,"goals":1,"assists":0,"yellows":0,"reds":0,"saves":null,"goals_conceded":null,"note":"Captain on the day","source":"self","status":"self_reported","editable":true,"provenance":{"source_category":"self","source_label":"Self-reported","primary_source":"user"},"created_at":"2026-08-30T19:00:00Z","updated_at":null},"season_stats":{"cells":3,"totals":2}}"#

    func testCreatePlayerMatchSendsSnakeCaseBodyWithOptionalOmission() async throws {
        var recordedBody: [String: Any] = [:]
        PlayerMatchURLProtocol.setHandler { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.path, "/api/players/-41/matches")
            let data = try XCTUnwrap(Self.bodyData(of: request))
            recordedBody = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
            return (
                Self.response(request, status: 201),
                Data(Self.matchBody.utf8)
            )
        }
        let client = makeClient()

        let response = try await client.createPlayerMatch(
            playerID: -41,
            submission: PlayerMatchSubmission(
                matchDate: "2026-08-30",
                competition: "U18 Premier League",
                opponent: "Coventry U18",
                homeAway: .home,
                resultFor: 2,
                resultAgainst: 1,
                minutes: 74,
                goals: 1,
                assists: 0,
                yellows: 0,
                reds: 0,
                saves: nil,
                goalsConceded: nil,
                note: "Captain on the day"
            )
        )

        XCTAssertEqual(recordedBody["match_date"] as? String, "2026-08-30")
        XCTAssertEqual(recordedBody["opponent"] as? String, "Coventry U18")
        XCTAssertEqual(recordedBody["competition"] as? String, "U18 Premier League")
        XCTAssertEqual(recordedBody["home_away"] as? String, "home")
        XCTAssertEqual(recordedBody["minutes"] as? Int, 74)
        XCTAssertEqual(recordedBody["goals"] as? Int, 1)
        XCTAssertEqual(recordedBody["result_for"] as? Int, 2)
        XCTAssertEqual(recordedBody["note"] as? String, "Captain on the day")
        XCTAssertNil(recordedBody["saves"], "unset goalkeeper counters must be omitted, not zeroed")
        XCTAssertNil(recordedBody["goals_conceded"])

        XCTAssertEqual(response.match.id, 812)
        XCTAssertEqual(response.match.season, 2025)
        XCTAssertEqual(response.match.editable, true)
        XCTAssertNil(response.seasonStats, "the rollup summary shape does not decode as season stats")
    }

    func testCreatedAndUpdatedBodiesBothDecode() async throws {
        PlayerMatchURLProtocol.setHandler { request in
            let call = PlayerMatchCallCounter.shared.increment()
            let status = call == 1 ? 201 : 200
            return (
                Self.response(request, status: status),
                Data(Self.matchBody.utf8)
            )
        }
        let client = makeClient()
        let submission = Self.stubSubmission()

        let created = try await client.createPlayerMatch(playerID: -41, submission: submission)
        let updated = try await client.createPlayerMatch(playerID: -41, submission: submission)

        XCTAssertEqual(created.match.opponent, "Coventry U18")
        XCTAssertEqual(updated.match.opponent, "Coventry U18")
    }

    func testSeasonStatsDecodeWhenPayloadCarriesFullTotals() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let payload = """
        {"match":{"id":813,"player_api_id":-41,"season":2025,"match_date":"2026-08-30","competition":null,"opponent":"Reading U18","home_away":"away","result_for":null,"result_against":null,"minutes":90,"goals":0,"assists":2,"yellows":0,"reds":0,"saves":null,"goals_conceded":null,"note":null,"source":"self","status":"self_reported","editable":true},"season_stats":{"player_id":-41,"season":"2025/26","appearances":4,"minutes":310,"goals":2,"assists":3,"saves":0,"goals_conceded":0,"clean_sheets":1,"source":"local-db","stats_coverage":null,"local_appearances":4,"clubs":[],"provenance":null}}
        """
        let response = try decoder.decode(PlayerMatchMutationResponse.self, from: Data(payload.utf8))

        XCTAssertEqual(response.match.assists, 2)
        XCTAssertEqual(response.seasonStats?.appearances, 4)
        XCTAssertEqual(response.seasonStats?.season, "2025/26")
    }

    func testBackend400MessageSurfaces() async {
        PlayerMatchURLProtocol.setHandler { request in
            (
                Self.response(request, status: 400),
                Data(#"{"error":"match_date cannot be more than one day in the future"}"#.utf8)
            )
        }
        let client = makeClient()

        do {
            _ = try await client.createPlayerMatch(playerID: -41, submission: Self.stubSubmission())
            XCTFail("expected a 400 server error")
        } catch let error as APIClientError {
            XCTAssertEqual(error.errorDescription, "match_date cannot be more than one day in the future")
            XCTAssertEqual(error.statusCode, 400)
        } catch {
            XCTFail("unexpected error type: \(error)")
        }
    }
}

// MARK: - View model

@MainActor
final class AddGameViewModelTests: XCTestCase {
    func testValidationMirrorsWebFormRules() {
        let viewModel = AddGameViewModel(playerID: -41, apiClient: MatchStubClient())

        viewModel.opponent = "   "
        XCTAssertFalse(viewModel.validate())
        XCTAssertEqual(viewModel.formError, "Enter the opponent.")

        viewModel.opponent = String(repeating: "x", count: 121)
        XCTAssertFalse(viewModel.validate())

        viewModel.opponent = "Coventry U18"
        viewModel.competition = String(repeating: "c", count: 121)
        XCTAssertFalse(viewModel.validate())

        viewModel.competition = "U18 Premier League"
        viewModel.note = String(repeating: "n", count: 501)
        XCTAssertFalse(viewModel.validate())

        viewModel.note = "Captain on the day"
        XCTAssertTrue(viewModel.validate())
        XCTAssertNil(viewModel.formError)
    }

    func testSubmissionOmitsOptionalFieldsAndFormatsDateForBackend() {
        var calendar = Calendar(identifier: .gregorian)
        guard let fixedUTC = TimeZone(secondsFromGMT: 0) else { return XCTFail("missing UTC") }
        calendar.timeZone = fixedUTC
        let viewModel = AddGameViewModel(playerID: -41, apiClient: MatchStubClient(), calendar: calendar)
        guard let date = calendar.date(from: DateComponents(year: 2026, month: 8, day: 30)) else {
            return XCTFail("missing fixture date")
        }
        viewModel.matchDate = date
        viewModel.competition = "  U18 Premier League "
        viewModel.opponent = "  Coventry U18 "
        viewModel.homeAway = .neutral
        viewModel.useScore = true
        viewModel.resultFor = 2
        viewModel.resultAgainst = 1
        viewModel.minutes = 74
        viewModel.goals = 1
        viewModel.saves = 5
        viewModel.note = "  "

        let submission = viewModel.submission

        XCTAssertEqual(submission.matchDate, "2026-08-30")
        XCTAssertEqual(submission.competition, "U18 Premier League")
        XCTAssertEqual(submission.opponent, "Coventry U18")
        XCTAssertEqual(submission.homeAway, .neutral)
        XCTAssertEqual(submission.resultFor, 2)
        XCTAssertEqual(submission.resultAgainst, 1)
        XCTAssertEqual(submission.saves, 5)
        XCTAssertNil(submission.goalsConceded, "goalkeeper counters stay off for outfield players")
        XCTAssertNil(submission.note, "blank notes are omitted like the web payload")
    }

    func testSuccessfulSubmitReturnsResponseAndRequest400SurfacesInline() async {
        let failingClient = MatchStubClient(result: .failure(
            APIClientError.server(statusCode: 400, message: "You do not have an approved claim for this player")
        ))
        let viewModel = AddGameViewModel(playerID: -41, apiClient: failingClient)
        viewModel.opponent = "Coventry U18"

        let failedResponse = await viewModel.submit()

        XCTAssertNil(failedResponse)
        XCTAssertEqual(viewModel.requestError, "You do not have an approved claim for this player")
        XCTAssertFalse(viewModel.didSave)

        let successClient = MatchStubClient(result: .success(
            PlayerMatchMutationResponse(
                match: Self.stubEntry(),
                seasonStats: nil
            )
        ))
        let successViewModel = AddGameViewModel(playerID: -41, apiClient: successClient)
        successViewModel.opponent = "Coventry U18"

        let saved = await successViewModel.submit()

        XCTAssertEqual(saved?.match.id, 812)
        XCTAssertTrue(successViewModel.didSave)
        XCTAssertNil(successViewModel.requestError)
    }

    func testRequestEncodingMatchesContract() throws {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(AddGameViewModelTests.stubSubmission())
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertEqual(object["match_date"] as? String, "2026-08-30")
        XCTAssertEqual(object["home_away"] as? String, "away")
        XCTAssertEqual(object["minutes"] as? Int, 90)
        XCTAssertEqual(object["assists"] as? Int, 2)
        XCTAssertNil(object["saves"])
        XCTAssertNil(object["result_for"])
    }

    private static func stubSubmission() -> PlayerMatchSubmission {
        PlayerMatchSubmission(
            matchDate: "2026-08-30",
            competition: nil,
            opponent: "Reading U18",
            homeAway: .away,
            resultFor: nil,
            resultAgainst: nil,
            minutes: 90,
            goals: 0,
            assists: 2,
            yellows: 0,
            reds: 0,
            saves: nil,
            goalsConceded: nil,
            note: nil
        )
    }

    private static func stubEntry() -> PlayerMatchEntry {
        PlayerMatchEntry(
            id: 812,
            playerApiId: -41,
            season: 2025,
            matchDate: "2026-08-30",
            competition: nil,
            opponent: "Reading U18",
            homeAway: "away",
            resultFor: nil,
            resultAgainst: nil,
            minutes: 90,
            goals: 0,
            assists: 2,
            yellows: 0,
            reds: 0,
            saves: nil,
            goalsConceded: nil,
            note: nil,
            source: "self",
            status: "self_reported",
            editable: true
        )
    }
}

// MARK: - Helpers

private extension PlayerMatchAPIClientTests {
    static func stubSubmission() -> PlayerMatchSubmission {
        PlayerMatchSubmission(
            matchDate: "2026-08-30",
            competition: "U18 Premier League",
            opponent: "Coventry U18",
            homeAway: .home,
            resultFor: 2,
            resultAgainst: 1,
            minutes: 74,
            goals: 1,
            assists: 0,
            yellows: 0,
            reds: 0,
            saves: nil,
            goalsConceded: nil,
            note: "Captain on the day"
        )
    }

    func makeClient() -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [PlayerMatchURLProtocol.self]
        return APIClient(
            baseURL: URL(string: "https://example.test/api")!,
            session: URLSession(configuration: configuration)
        )
    }

    static func bodyData(of request: URLRequest) -> Data? {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return nil }
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 1_024)
        while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            guard count >= 0 else { return nil }
            if count == 0 { break }
            data.append(buffer, count: count)
        }
        return data.isEmpty ? nil : data
    }

    static func response(_ request: URLRequest, status: Int) -> HTTPURLResponse {
        HTTPURLResponse(
            url: request.url!,
            statusCode: status,
            httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
    }
}

private final class PlayerMatchCallCounter: @unchecked Sendable {
    static let shared = PlayerMatchCallCounter()
    private let lock = NSLock()
    private var calls = 0

    var callCount: Int {
        lock.lock()
        defer { lock.unlock() }
        return calls
    }

    func increment() -> Int {
        lock.lock()
        defer { lock.unlock() }
        calls += 1
        return calls
    }

    func reset() {
        lock.lock()
        calls = 0
        lock.unlock()
    }
}

private final class PlayerMatchURLProtocol: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    static func setHandler(_ value: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)) {
        lock.lock()
        handler = value
        lock.unlock()
    }

    static func reset() {
        lock.lock()
        handler = nil
        PlayerMatchCallCounter.shared.reset()
        lock.unlock()
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.lock.lock()
        let handler = Self.handler
        Self.lock.unlock()
        do {
            guard let handler else { throw URLError(.unsupportedURL) }
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            if !data.isEmpty { client?.urlProtocol(self, didLoad: data) }
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

private struct MatchStubClient: PlayerMatchAPIClientProtocol {
    let result: Result<PlayerMatchMutationResponse, Error>

    init(result: Result<PlayerMatchMutationResponse, Error> = .failure(URLError(.unsupportedURL))) {
        self.result = result
    }

    func createPlayerMatch(
        playerID _: Int,
        submission _: PlayerMatchSubmission
    ) async throws -> PlayerMatchMutationResponse {
        try result.get()
    }
}
