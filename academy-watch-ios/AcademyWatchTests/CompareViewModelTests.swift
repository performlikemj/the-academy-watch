import XCTest
@testable import AcademyWatch

final class CompareViewModelTests: XCTestCase {
    @MainActor
    func testLoadsComparisonWithAvailability() async throws {
        let response: CompareResponse = try decodeFixture(named: "scout_compare_gk_outfielder")
        let client = StubCompareAPIClient(response: response)
        let viewModel = CompareViewModel(
            playerIDs: [145_060, 403_064],
            apiClient: client
        )

        await viewModel.load()

        XCTAssertEqual(viewModel.players, response.players)
        XCTAssertEqual(viewModel.missingPlayerIDs, response.missingIds)
        XCTAssertFalse(viewModel.isLoading)
        XCTAssertNil(viewModel.errorMessage)

        let request = await client.capturedRequest()
        XCTAssertEqual(request?.playerIDs, [145_060, 403_064])
        XCTAssertEqual(request?.includeAvailability, true)
    }

    private func decodeFixture<Response: Decodable>(named name: String) throws -> Response {
        let fixtureURL = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: name, withExtension: "json")
        )
        let data = try Data(contentsOf: fixtureURL)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Response.self, from: data)
    }
}

private actor StubCompareAPIClient: CompareAPIClientProtocol {
    private let response: CompareResponse
    private var request: (playerIDs: [Int], includeAvailability: Bool)?

    init(response: CompareResponse) {
        self.response = response
    }

    func fetchComparison(
        playerIDs: [Int],
        includeAvailability: Bool
    ) async throws -> CompareResponse {
        request = (playerIDs, includeAvailability)
        return response
    }

    func capturedRequest() -> (playerIDs: [Int], includeAvailability: Bool)? {
        request
    }
}
