import XCTest
@testable import AcademyWatch

final class PlayerInterestSignalsViewModelTests: XCTestCase {
    @MainActor
    func testLoadsOnlyExactPlayerAndKeepsPositiveMetricsSeparate() async throws {
        let requestedPlayerID = 700_002
        let exactSignal = makeSignal(
            playerID: requestedPlayerID,
            watchlistTotal: 7,
            watchlistAdds: 2,
            followTotal: 3,
            followAdds: 1
        )
        let client = InterestSignalsClientStub(
            response: makeResponse(
                signals: [
                    makeSignal(
                        playerID: 700_001,
                        watchlistTotal: 99,
                        watchlistAdds: 20,
                        followTotal: 88,
                        followAdds: 10
                    ),
                    exactSignal,
                ]
            )
        )
        let availability = ContactFeatureAvailability()
        let viewModel = PlayerInterestSignalsViewModel(
            playerID: requestedPlayerID,
            apiClient: client,
            availability: availability
        )

        await viewModel.reload()

        XCTAssertEqual(viewModel.signal, exactSignal)
        XCTAssertEqual(availability.state, .available)
        let presentation = try XCTUnwrap(viewModel.presentation)
        XCTAssertEqual(presentation.metrics.map(\.kind), [.watchlists, .follows])
        XCTAssertEqual(presentation.metrics.map(\.total), [7, 3])
        XCTAssertEqual(presentation.metrics.map(\.addedThisWeek), [2, 1])
        XCTAssertEqual(presentation.metrics.map(\.weeklyActivityText), ["+2 this week", "+1 this week"])
        XCTAssertTrue(presentation.hasNewInterestThisWeek)
        XCTAssertFalse(presentation.isZeroState)
        XCTAssertEqual(presentation.title, "Scouts are watching you")
    }

    @MainActor
    func testPartialSignalKeepsBothCategoriesWithWarmZeroCopy() async throws {
        let client = InterestSignalsClientStub(
            response: makeResponse(
                signals: [
                    makeSignal(
                        playerID: 700_001,
                        watchlistTotal: 4,
                        watchlistAdds: 0,
                        followTotal: 0,
                        followAdds: 0
                    )
                ]
            )
        )
        let viewModel = PlayerInterestSignalsViewModel(
            playerID: 700_001,
            apiClient: client,
            availability: ContactFeatureAvailability()
        )

        await viewModel.reload()

        let presentation = try XCTUnwrap(viewModel.presentation)
        XCTAssertEqual(presentation.metrics.map(\.kind), [.watchlists, .follows])
        XCTAssertEqual(presentation.metrics.map(\.total), [4, 0])
        XCTAssertEqual(presentation.metrics.map(\.weeklyActivityText), ["No new this week", "No new this week"])
        XCTAssertEqual(presentation.metrics.last?.emptyTotalText, "No follows yet")
        XCTAssertFalse(presentation.hasNewInterestThisWeek)
        XCTAssertEqual(
            presentation.message,
            "No new saves this week, but scouts still have you on their radar."
        )
    }

    @MainActor
    func testZeroSignalUsesWarmCopyWithoutDeadNumericMetrics() async throws {
        let client = InterestSignalsClientStub(
            response: makeResponse(
                signals: [
                    makeSignal(
                        playerID: 700_001,
                        watchlistTotal: 0,
                        watchlistAdds: 0,
                        followTotal: 0,
                        followAdds: 0
                    )
                ]
            )
        )
        let viewModel = PlayerInterestSignalsViewModel(
            playerID: 700_001,
            apiClient: client,
            availability: ContactFeatureAvailability()
        )

        await viewModel.reload()

        let presentation = try XCTUnwrap(viewModel.presentation)
        XCTAssertTrue(presentation.isZeroState)
        XCTAssertTrue(presentation.metrics.isEmpty)
        XCTAssertEqual(presentation.title, "Your profile is ready to be seen")
        XCTAssertFalse(presentation.title.contains("0"))
        XCTAssertFalse(presentation.message.contains("0"))
    }

    @MainActor
    func test404MakesFeatureUnavailableAndPreventsFurtherRefreshes() async {
        let client = InterestSignalsClientStub(statusCode: 404)
        let availability = ContactFeatureAvailability()
        let viewModel = PlayerInterestSignalsViewModel(
            playerID: 700_001,
            apiClient: client,
            availability: availability
        )

        await viewModel.reload()

        XCTAssertEqual(availability.state, .unavailable)
        XCTAssertFalse(viewModel.isCardVisible)
        XCTAssertNil(viewModel.signal)
        XCTAssertNil(viewModel.errorMessage)

        availability.recordSuccess()
        await viewModel.refresh()

        XCTAssertEqual(availability.state, .unavailable)
        let requestCount = await client.requestCount()
        XCTAssertEqual(requestCount, 1)
    }

    private func makeResponse(signals: [PlayerInterestSignal]) -> InterestSignalsResponse {
        InterestSignalsResponse(
            weekStart: "2026-07-13T00:00:00+00:00",
            interestSignals: signals
        )
    }

    private func makeSignal(
        playerID: Int,
        watchlistTotal: Int,
        watchlistAdds: Int,
        followTotal: Int,
        followAdds: Int
    ) -> PlayerInterestSignal {
        PlayerInterestSignal(
            playerApiId: playerID,
            watchlists: InterestSignalMetric(total: watchlistTotal, addedThisWeek: watchlistAdds),
            follows: InterestSignalMetric(total: followTotal, addedThisWeek: followAdds)
        )
    }
}

private actor InterestSignalsClientStub: InterestSignalsAPIClientProtocol {
    private let response: InterestSignalsResponse?
    private let statusCode: Int?
    private var requests = 0

    init(response: InterestSignalsResponse) {
        self.response = response
        statusCode = nil
    }

    init(statusCode: Int) {
        response = nil
        self.statusCode = statusCode
    }

    func fetchMyInterestSignals() async throws -> InterestSignalsResponse {
        requests += 1
        if let statusCode {
            throw APIClientError.httpStatus(statusCode)
        }
        guard let response else {
            throw APIClientError.invalidResponse
        }
        return response
    }

    func requestCount() -> Int {
        requests
    }
}
