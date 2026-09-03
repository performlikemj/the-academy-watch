import Foundation
import XCTest
@testable import AcademyWatch

/// Covers the `birth_date` debt on POST `/local-players`: the body must carry
/// the optional ISO date as `birth_date` while `birth_year` keeps working when
/// no date is set, and backend 400 messages surface inline.
final class OnboardingBirthDateTests: XCTestCase {
    override func setUp() {
        super.setUp()
        BirthDateURLProtocol.reset()
    }

    override func tearDown() {
        BirthDateURLProtocol.reset()
        super.tearDown()
    }

    // MARK: - Encoding

    func testSubmissionEncodesBirthDateAndOmitsBirthYearWhenDateIsSet() throws {
        let submission = LocalPlayerSubmission(
            displayName: "Maya Okafor",
            relationshipType: .player,
            position: nil,
            clubName: nil,
            country: nil,
            city: nil,
            birthYear: nil,
            birthDate: "2008-05-04"
        )

        let object = try snakeCaseObject(submission)

        XCTAssertEqual(object["birth_date"] as? String, "2008-05-04")
        XCTAssertNil(object["birth_year"], "the backend derives birth_year from birth_date")
        XCTAssertEqual(object["display_name"] as? String, "Maya Okafor")
        XCTAssertEqual(object["relationship_type"] as? String, "player")
    }

    func testSubmissionKeepsBirthYearAndOmitsBirthDateWhenNoDateIsSet() throws {
        let submission = LocalPlayerSubmission(
            displayName: "Community Player",
            relationshipType: nil,
            position: nil,
            clubName: nil,
            country: nil,
            city: nil,
            birthYear: 2004
        )

        let object = try snakeCaseObject(submission)

        XCTAssertEqual(object["birth_year"] as? Int, 2004)
        XCTAssertNil(object["birth_date"], "nil birth_date must be omitted so the year-only path is unchanged")
    }

    func testBirthDateStringUsesCalendarComponentsWithoutTimezoneShift() {
        var calendar = Calendar(identifier: .gregorian)
        guard let fixedUTC = TimeZone(secondsFromGMT: 0) else { return XCTFail("missing UTC timezone") }
        calendar.timeZone = fixedUTC
        guard let date = calendar.date(from: DateComponents(year: 2008, month: 5, day: 4)) else {
            return XCTFail("missing fixture date")
        }

        XCTAssertEqual(
            LocalPlayerFormViewModel.birthDateString(from: date, calendar: calendar),
            "2008-05-04"
        )
    }

    func testLocalPlayerDecodesBirthDateWhenResponseCarriesIt() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let payload = #"{"id":41,"display_name":"Maya Okafor","birth_year":2008,"birth_date":"2008-05-04","position":null,"country":null,"city":null,"club_name":null,"status":"pending","provenance":"user","created_at":null}"#
        let player = try decoder.decode(LocalPlayer.self, from: Data(payload.utf8))

        XCTAssertEqual(player.birthDate, "2008-05-04")
    }

    func testLocalPlayerDecodesWithoutBirthDateKey() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let payload = #"{"id":41,"display_name":"Maya Okafor","birth_year":2008,"position":null,"country":null,"city":null,"club_name":null,"status":"pending","provenance":"user","created_at":null}"#
        let player = try decoder.decode(LocalPlayer.self, from: Data(payload.utf8))

        XCTAssertNil(player.birthDate)
        XCTAssertEqual(player.birthYear, 2008)
    }

    // MARK: - View model wiring

    @MainActor
    func testFormViewModelSendsBirthDateAndDropsYearWhenDateIsSet() {
        let viewModel = LocalPlayerFormViewModel(
            context: .claimant,
            apiClient: BirthDateStubClient(),
            calendar: fixedGregorianUTC()
        )
        viewModel.displayName = "Maya Okafor"
        guard let date = fixedGregorianUTC().date(from: DateComponents(year: 2008, month: 5, day: 4)) else {
            return XCTFail("missing fixture date")
        }
        viewModel.birthDate = date
        viewModel.birthYear = "2004"

        let submission = viewModel.submission
        XCTAssertEqual(submission.birthDate, "2008-05-04")
        XCTAssertNil(submission.birthYear, "the date takes precedence, mirroring the backend")
    }

    @MainActor
    func testFormViewModelValidatesBirthDateYearAgainstBackendBounds() {
        let viewModel = LocalPlayerFormViewModel(
            context: .claimant,
            apiClient: BirthDateStubClient(),
            calendar: fixedGregorianUTC()
        )
        viewModel.displayName = "Maya Okafor"
        guard let early = fixedGregorianUTC().date(from: DateComponents(year: 1935, month: 1, day: 2)),
              let inRange = fixedGregorianUTC().date(from: DateComponents(year: 2008, month: 6, day: 3))
        else { return XCTFail("missing fixture dates") }

        viewModel.birthDate = early
        XCTAssertFalse(viewModel.validate())
        XCTAssertEqual(
            viewModel.error(for: .birthDate),
            "Birth date must fall between 1950 and 2020."
        )

        viewModel.birthDate = inRange
        XCTAssertTrue(viewModel.validate())
        XCTAssertNil(viewModel.error(for: .birthDate))
    }

    @MainActor
    func testValidBirthDateIgnoresInvalidYearAndClearsStaleYearError() async {
        let client = BirthDateSubmissionSpy()
        let viewModel = LocalPlayerFormViewModel(
            context: .claimant,
            apiClient: client,
            calendar: fixedGregorianUTC()
        )
        viewModel.displayName = "Maya Okafor"
        viewModel.birthYear = "2021"

        XCTAssertFalse(viewModel.validate())
        XCTAssertNotNil(viewModel.error(for: .birthYear))

        guard let date = fixedGregorianUTC().date(from: DateComponents(year: 2008, month: 5, day: 4)) else {
            return XCTFail("missing fixture date")
        }
        viewModel.birthDate = date

        XCTAssertNil(viewModel.error(for: .birthYear))
        XCTAssertTrue(viewModel.validate())
        await viewModel.submit()
        let submissionCount = await client.submissionCount()
        XCTAssertEqual(submissionCount, 1)
        XCTAssertNil(viewModel.submission.birthYear)
    }

    @MainActor
    func testInvalidBirthYearStillFailsWithoutExactDate() {
        let viewModel = LocalPlayerFormViewModel(
            context: .claimant,
            apiClient: BirthDateStubClient(),
            calendar: fixedGregorianUTC()
        )
        viewModel.displayName = "Maya Okafor"
        viewModel.birthYear = "2021"

        XCTAssertFalse(viewModel.validate())
        XCTAssertEqual(
            viewModel.error(for: .birthYear),
            "Birth year must be between 1950 and 2020."
        )
    }

    // MARK: - 400 surfacing

    @MainActor
    func testBackend400MessageSurfacesFromCreateRequest() async throws {
        BirthDateURLProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.path, "/api/local-players")
            return (
                Self.response(request, status: 400),
                Data(#"{"error":"The platform is 18+ for self-managed profiles"}"#.utf8)
            )
        }
        let client = makeClient()
        let viewModel = LocalPlayerFormViewModel(context: .claimant, apiClient: client)
        viewModel.displayName = "Underage Self Claim"

        await viewModel.submit()

        XCTAssertNil(viewModel.created)
        XCTAssertEqual(viewModel.requestError, "The platform is 18+ for self-managed profiles")
    }

    func testCreateClientThrowsServer400WithBackendMessage() async {
        BirthDateURLProtocol.handler = { request in
            (
                Self.response(request, status: 400),
                Data(#"{"error":"birth_date must be an ISO date in YYYY-MM-DD format"}"#.utf8)
            )
        }

        do {
            _ = try await makeClient().createLocalPlayer(
                LocalPlayerSubmission(
                    displayName: "Maya Okafor",
                    relationshipType: .player,
                    position: nil,
                    clubName: nil,
                    country: nil,
                    city: nil,
                    birthYear: nil,
                    birthDate: "not-a-date"
                )
            )
            XCTFail("expected a 400 server error")
        } catch let error as APIClientError {
            guard case let .server(statusCode, message) = error else {
                return XCTFail("unexpected error: \(error)")
            }
            XCTAssertEqual(statusCode, 400)
            XCTAssertEqual(message, "birth_date must be an ISO date in YYYY-MM-DD format")
        } catch {
            XCTFail("unexpected error type: \(error)")
        }
    }

    // MARK: - Helpers

    private func fixedGregorianUTC() -> Calendar {
        var calendar = Calendar(identifier: .gregorian)
        guard let fixedUTC = TimeZone(secondsFromGMT: 0) else { fatalError("missing UTC") }
        calendar.timeZone = fixedUTC
        return calendar
    }

    private func snakeCaseObject(_ value: some Encodable) throws -> [String: Any] {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return try XCTUnwrap(
            JSONSerialization.jsonObject(with: encoder.encode(value)) as? [String: Any]
        )
    }

    private func makeClient() -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [BirthDateURLProtocol.self]
        return APIClient(
            baseURL: URL(string: "https://example.test/api")!,
            session: URLSession(configuration: configuration)
        )
    }

    private static func response(_ request: URLRequest, status: Int) -> HTTPURLResponse {
        HTTPURLResponse(
            url: request.url!,
            statusCode: status,
            httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
    }
}

private final class BirthDateURLProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var handler: ((URLRequest) -> (HTTPURLResponse, Data))?

    static func reset() { handler = nil }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = Self.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.unsupportedURL))
            return
        }
        let (response, data) = handler(request)
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        if !data.isEmpty { client?.urlProtocol(self, didLoad: data) }
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

private struct BirthDateStubClient: OnboardingAPIClientProtocol {
    func createLocalPlayer(_ submission: LocalPlayerSubmission) async throws -> LocalPlayerCreateResponse {
        throw URLError(.unsupportedURL)
    }

    func fetchLocalPlayer(id _: Int) async throws -> LocalPlayerResponse { throw URLError(.unsupportedURL) }
    func searchWorldwidePlayers(query _: String) async throws -> WorldwidePlayerSearchResponse {
        WorldwidePlayerSearchResponse(players: [])
    }

    func addWorldwidePlayerFollow(listID _: Int, player _: WorldwidePlayer) async throws -> FollowResponse {
        throw URLError(.unsupportedURL)
    }

    func searchClubs(query _: String) async throws -> ClubSearchResponse {
        ClubSearchResponse(apiTeams: [], localClubs: [])
    }

    func fetchMyClubClaims() async throws -> ClubClaimsResponse { ClubClaimsResponse(claims: []) }
    func submitClubClaim(_ submission: ClubClaimSubmission) async throws -> ClubClaimResponse {
        throw URLError(.unsupportedURL)
    }

    func verifyClubClaim(id _: Int, proofURL _: String) async throws -> ClubClaimResponse {
        throw URLError(.unsupportedURL)
    }
}

private actor BirthDateSubmissionSpy: OnboardingAPIClientProtocol {
    private var submissions: [LocalPlayerSubmission] = []

    func submissionCount() -> Int { submissions.count }

    func createLocalPlayer(_ submission: LocalPlayerSubmission) async throws -> LocalPlayerCreateResponse {
        submissions.append(submission)
        throw URLError(.unsupportedURL)
    }

    func fetchLocalPlayer(id _: Int) async throws -> LocalPlayerResponse { throw URLError(.unsupportedURL) }
    func searchWorldwidePlayers(query _: String) async throws -> WorldwidePlayerSearchResponse {
        WorldwidePlayerSearchResponse(players: [])
    }

    func addWorldwidePlayerFollow(listID _: Int, player _: WorldwidePlayer) async throws -> FollowResponse {
        throw URLError(.unsupportedURL)
    }

    func searchClubs(query _: String) async throws -> ClubSearchResponse {
        ClubSearchResponse(apiTeams: [], localClubs: [])
    }

    func fetchMyClubClaims() async throws -> ClubClaimsResponse { ClubClaimsResponse(claims: []) }
    func submitClubClaim(_ submission: ClubClaimSubmission) async throws -> ClubClaimResponse {
        throw URLError(.unsupportedURL)
    }

    func verifyClubClaim(id _: Int, proofURL _: String) async throws -> ClubClaimResponse {
        throw URLError(.unsupportedURL)
    }
}
