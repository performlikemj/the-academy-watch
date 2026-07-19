import XCTest
@testable import AcademyWatch

final class ContactFeatureAvailabilityTests: XCTestCase {
    @MainActor
    func testSuccessMarksAvailableAndResetReturnsToUnknown() {
        let availability = ContactFeatureAvailability()

        XCTAssertEqual(availability.state, .unknown)

        availability.recordSuccess()
        XCTAssertEqual(availability.state, .available)

        availability.reset()
        XCTAssertEqual(availability.state, .unknown)
    }

    @MainActor
    func testAnyHTTP404MarksContactRailUnavailable() {
        let availability = ContactFeatureAvailability()

        availability.recordFailure(APIClientError.httpStatus(404))

        XCTAssertEqual(availability.state, .unavailable)
        XCTAssertTrue(availability.isUnavailable)
    }

    @MainActor
    func testNon404FailureDoesNotChangeKnownState() {
        let unknownAvailability = ContactFeatureAvailability()
        unknownAvailability.recordFailure(
            APIClientError.codedServer(
                statusCode: 403,
                message: "Scout verification is required",
                code: "scout_not_verified",
                cooldownDays: nil
            )
        )
        XCTAssertEqual(unknownAvailability.state, .unknown)

        let available = ContactFeatureAvailability(state: .available)
        available.recordFailure(APIClientError.httpStatus(500))
        XCTAssertEqual(available.state, .available)
    }

    @MainActor
    func testOlderSuccessCannotOverrideAContactRail404() {
        let availability = ContactFeatureAvailability()
        availability.recordFailure(APIClientError.httpStatus(404))

        availability.recordSuccess()

        XCTAssertEqual(availability.state, .unavailable)
    }
}
