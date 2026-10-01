import XCTest

@testable import AcademyWatch

final class Phase2ContractTests: XCTestCase {
    private struct Manifest: Decodable {
        let source: String
        let fixtures: [Entry]
    }
    private struct Entry: Decodable {
        let file: String
        let dto: String
        let status: Int
        let path: String
    }
    private struct Refusal: Decodable {
        let error: String?
        let message: String?
    }
    private func fixture(_ name: String) throws -> Data {
        let bundle = Bundle(for: Self.self)
        let url = try XCTUnwrap(
            bundle.url(forResource: name, withExtension: "json", subdirectory: "Phase2"))
        return try Data(contentsOf: url)
    }
    func testEveryCapturedEndpointDecodesItsRealResponse() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let manifest = try decoder.decode(Manifest.self, from: fixture("manifest"))
        XCTAssertEqual(manifest.source, "https://basecamp.tail37b60.ts.net:15443/api/")
        XCTAssertGreaterThanOrEqual(manifest.fixtures.count, 40)
        for entry in manifest.fixtures {
            let data = try fixture(String(entry.file.dropLast(5)))
            func decode<T: Decodable>(_ type: T.Type) throws { _ = try decoder.decode(type, from: data) }
            do {
                switch entry.dto {
                case "Phase2FeatureResponse": try decode(Phase2FeatureResponse.self)
                case "OpportunityFeatures": try decode(OpportunityFeatures.self)
                case "ClubDirectoryResponse": try decode(ClubDirectoryResponse.self)
                case "PublicClubResponse": try decode(PublicClubResponse.self)
                case "OpportunitiesResponse": try decode(OpportunitiesResponse.self)
                case "OpportunityResponse": try decode(OpportunityResponse.self)
                case "ApplicationClaimsResponse": try decode(ApplicationClaimsResponse.self)
                case "ApplicationsResponse": try decode(ApplicationsResponse.self)
                case "ApplicationResponse": try decode(ApplicationResponse.self)
                case "NoteResponse": try decode(NoteResponse.self)
                case "ClubMembershipsResponse": try decode(ClubMembershipsResponse.self)
                case "Phase2ClubClaimsResponse": try decode(Phase2ClubClaimsResponse.self)
                case "ClubAccessResponse": try decode(ClubAccessResponse.self)
                case "SquadsResponse": try decode(SquadsResponse.self)
                case "RosterResponse": try decode(RosterResponse.self)
                case "MatchesResponse": try decode(MatchesResponse.self)
                case "StaffBoardResponse": try decode(StaffBoardResponse.self)
                case "StaffInviteResponse": try decode(StaffInviteResponse.self)
                case "ContactRequestsResponse": try decode(ContactRequestsResponse.self)
                case "ContactMessagesResponse": try decode(ContactMessagesResponse.self)
                case "Phase2Empty": try decode(Phase2Empty.self)
                case "Error":
                    XCTAssertGreaterThanOrEqual(entry.status, 400)
                    try decode(Refusal.self)
                default: XCTFail("Missing DTO assertion for \(entry.dto)")
                }
            } catch { XCTFail("\(entry.file) (\(entry.path)): \(error)") }
        }
    }
    func testVerifiedOwnerIsResolvedThroughClaimsNotInvitedMemberships() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let invited = try decoder.decode(
            ClubMembershipsResponse.self, from: fixture("club_owner-memberships"))
        let claims = try decoder.decode(Phase2ClubClaimsResponse.self, from: fixture("owner-claims"))
        let access = try decoder.decode(ClubAccessResponse.self, from: fixture("club_owner-access-me"))
        XCTAssertTrue(invited.programs.isEmpty)
        XCTAssertTrue(
            claims.claims.contains { $0.status == "approved" && $0.program.id == access.access.programId }
        )
        XCTAssertTrue(access.access.canRecruit)
        XCTAssertTrue(access.access.canManageAccess)
        let coach = try decoder.decode(
            ClubMembershipsResponse.self, from: fixture("coach_u18-memberships"))
        XCTAssertFalse(coach.programs.isEmpty)
        XCTAssertFalse(coach.programs[0].access.wholeClub)
    }
    func testActual422And429TravelThroughAPIClientErrorDecoder() async throws {
        for (file, status, expected) in [
            ("invalid-trial-422", 422, "invitation window"),
            ("invalid-email-422", 422, "valid email"),
            ("directory-rate-limit-429", 429, "Too many attempts"),
        ] {
            ContractProtocol.response = (status, try fixture(file))
            let configuration = URLSessionConfiguration.ephemeral
            configuration.protocolClasses = [ContractProtocol.self]
            let client = APIClient(
                baseURL: URL(string: "https://contract.test/api")!,
                session: URLSession(configuration: configuration))
            do {
                let _: Phase2Empty = try await client.read("contract-refusal")
                XCTFail("Expected refusal")
            } catch {
                XCTAssertEqual(phase2Status(error), status)
                XCTAssertTrue(phase2Error(error).contains(expected), phase2Error(error))
                XCTAssertFalse(phase2Error(error).contains("Could not connect"))
            }
        }
    }
    func testPhase2TransportCannotPersistPrivateResponsesEvenIfServerOmitsCacheHeaders() {
        let configuration = APIClient.phase2SessionConfiguration()
        XCTAssertNil(configuration.urlCache)
        XCTAssertNil(configuration.httpCookieStorage)
        XCTAssertNil(configuration.urlCredentialStorage)
        XCTAssertEqual(configuration.requestCachePolicy, .reloadIgnoringLocalCacheData)
    }
    func testConfirmationAndRescheduleEventsHaveDistinctLabels() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let confirmation = try decoder.decode(
            ApplicationResponse.self, from: fixture("confirm-application"))
        let reschedule = try decoder.decode(
            ApplicationResponse.self, from: fixture("reschedule-application"))
        XCTAssertEqual(confirmation.application.reservationState, "confirmed")
        XCTAssertEqual(
            reschedule.application.events?.first(where: { $0.reasonCode == "trial_confirmed" })?.label,
            "Trial place confirmed")
        XCTAssertEqual(reschedule.application.events?.last?.label, "Trial rescheduled")
    }
}
private final class ContractProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var response: (Int, Data) = (200, Data())
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}
    override func startLoading() {
        let (status, data) = Self.response
        let response = HTTPURLResponse(
            url: request.url!, statusCode: status, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .allowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
}
