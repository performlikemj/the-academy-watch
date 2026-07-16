import XCTest
@testable import AcademyWatch

final class IntroductionRequestViewModelTests: XCTestCase {
    @MainActor
    func testSuccessfulSubmissionTrimsMessageAndMarksContactRailAvailable() async {
        let request = ContactRequest(
            id: "b3bd7fe9-05b4-4bb8-b8b1-298d5aa7ba71",
            playerApiId: 700_001,
            message: "Could we arrange a short conversation?",
            status: .pending,
            createdAt: "2026-07-17T08:00:00",
            respondedAt: nil,
            expiresAt: "2026-07-31T08:00:00",
            participants: ContactRequestParticipants(
                scout: ContactRequestParticipant(displayName: "Alex Scout"),
                player: ContactRequestParticipant(displayName: "Test Player")
            ),
            latestOutcome: nil
        )
        let recorder = IntroductionSubmissionRecorder(
            response: ContactRequestResponse(contactRequest: request)
        )
        let availability = ContactFeatureAvailability()
        let viewModel = IntroductionRequestViewModel(
            playerID: 700_001,
            availability: availability,
            initialMessage: "  Could we arrange a short conversation?\n",
            createRequest: { playerID, message in
                try await recorder.create(playerID: playerID, message: message)
            }
        )

        let didSubmit = await viewModel.submit()

        XCTAssertTrue(didSubmit)
        XCTAssertEqual(viewModel.createdRequest, request)
        XCTAssertEqual(availability.state, .available)
        let submission = await recorder.submission()
        XCTAssertEqual(submission?.playerID, 700_001)
        XCTAssertEqual(submission?.message, "Could we arrange a short conversation?")
    }

    @MainActor
    func testValidatesTrimmedMessageAtOneThroughTwoThousandCharacters() async {
        let availability = ContactFeatureAvailability()
        let viewModel = makeViewModel(
            availability: availability,
            initialMessage: "   \n"
        )

        XCTAssertEqual(viewModel.validationFailure, .messageRequired)
        XCTAssertFalse(viewModel.canSubmit)
        let didSubmitEmptyMessage = await viewModel.submit()
        XCTAssertFalse(didSubmitEmptyMessage)
        XCTAssertEqual(viewModel.failure, .messageRequired)

        viewModel.message = String(repeating: "a", count: 2_000)
        viewModel.clearFailure()
        XCTAssertNil(viewModel.validationFailure)
        XCTAssertTrue(viewModel.canSubmit)

        viewModel.message.append("a")
        XCTAssertEqual(viewModel.validationFailure, .messageTooLong)
        XCTAssertFalse(viewModel.canSubmit)
        let didSubmitLongMessage = await viewModel.submit()
        XCTAssertFalse(didSubmitLongMessage)
        XCTAssertEqual(viewModel.failure, .messageTooLong)
    }

    @MainActor
    func testMapsVerificationErrorToVerificationRoute() async {
        let viewModel = makeFailingViewModel(
            error: codedError(status: 403, code: "scout_not_verified")
        )

        let didSubmit = await viewModel.submit()
        XCTAssertFalse(didSubmit)

        XCTAssertEqual(viewModel.failure, .verificationRequired)
        XCTAssertTrue(viewModel.shouldRouteToVerification)
        XCTAssertEqual(
            viewModel.errorMessage,
            "Verify your scout profile before requesting an introduction."
        )
    }

    @MainActor
    func testMapsPlayerAndRequestStateErrorCodes() async {
        let cases: [(String, IntroductionRequestFailure)] = [
            ("player_not_claimable", .playerNotClaimable),
            ("active_request_exists", .activeRequestExists),
            ("request_expired", .requestExpired),
        ]

        for (code, expectedFailure) in cases {
            let viewModel = makeFailingViewModel(
                error: codedError(status: code == "player_not_claimable" ? 403 : 409, code: code)
            )

            let didSubmit = await viewModel.submit()
            XCTAssertFalse(didSubmit, "Expected \(code) to fail")
            XCTAssertEqual(viewModel.failure, expectedFailure, "Incorrect mapping for \(code)")
            XCTAssertFalse(viewModel.shouldRouteToVerification)
        }
    }

    @MainActor
    func testMapsDeclineCooldownIncludingPolicyDays() async {
        let viewModel = makeFailingViewModel(
            error: APIClientError.codedServer(
                statusCode: 409,
                message: "Please wait",
                code: "decline_cooldown_active",
                cooldownDays: 30
            )
        )

        let didSubmit = await viewModel.submit()
        XCTAssertFalse(didSubmit)

        XCTAssertEqual(viewModel.failure, .declineCooldownActive(days: 30))
        XCTAssertEqual(
            viewModel.errorMessage,
            "This player recently declined a request. You can ask again after the 30-day cooling-off period."
        )
    }

    @MainActor
    func testMaps429ToClearRateLimitMessage() async {
        let viewModel = makeFailingViewModel(error: APIClientError.httpStatus(429))

        let didSubmit = await viewModel.submit()
        XCTAssertFalse(didSubmit)

        XCTAssertEqual(viewModel.failure, .rateLimited)
        XCTAssertEqual(
            viewModel.errorMessage,
            "You've reached the introduction request limit. Please try again later."
        )
    }

    @MainActor
    func testContact404DisablesRailWithoutPresentingAnError() async {
        let availability = ContactFeatureAvailability()
        let viewModel = makeFailingViewModel(
            availability: availability,
            error: APIClientError.codedServer(
                statusCode: 404,
                message: "Not found",
                code: "not_found",
                cooldownDays: nil
            )
        )

        let didSubmit = await viewModel.submit()
        XCTAssertFalse(didSubmit)

        XCTAssertEqual(availability.state, .unavailable)
        XCTAssertNil(viewModel.failure)
        XCTAssertNil(viewModel.errorMessage)
        XCTAssertFalse(viewModel.canSubmit)
    }

    @MainActor
    func testMapsNetworkAndUnknownFailuresToHelpfulGenericMessages() async {
        let offline = makeFailingViewModel(
            error: URLError(.notConnectedToInternet)
        )
        let didSubmitOffline = await offline.submit()
        XCTAssertFalse(didSubmitOffline)
        XCTAssertEqual(
            offline.failure,
            .generic(message: "You're offline. Reconnect and try sending again.")
        )

        let unknown = makeFailingViewModel(error: IntroductionTestError.failed)
        let didSubmitUnknown = await unknown.submit()
        XCTAssertFalse(didSubmitUnknown)
        XCTAssertEqual(
            unknown.failure,
            .generic(
                message: "We couldn't send your introduction request. Check your connection and try again."
            )
        )
    }

    @MainActor
    private func makeViewModel(
        availability: ContactFeatureAvailability? = nil,
        initialMessage: String = "A concise introduction"
    ) -> IntroductionRequestViewModel {
        let availability = availability ?? ContactFeatureAvailability()
        return IntroductionRequestViewModel(
            playerID: 700_001,
            availability: availability,
            initialMessage: initialMessage,
            createRequest: { _, _ in
                throw IntroductionTestError.shouldNotReachNetwork
            }
        )
    }

    @MainActor
    private func makeFailingViewModel(
        availability: ContactFeatureAvailability? = nil,
        error: Error
    ) -> IntroductionRequestViewModel {
        let availability = availability ?? ContactFeatureAvailability()
        return IntroductionRequestViewModel(
            playerID: 700_001,
            availability: availability,
            initialMessage: "Could we arrange a short conversation?",
            createRequest: { _, _ in throw error }
        )
    }

    private func codedError(status: Int, code: String) -> APIClientError {
        APIClientError.codedServer(
            statusCode: status,
            message: "Server message",
            code: code,
            cooldownDays: nil
        )
    }
}

private enum IntroductionTestError: Error {
    case failed
    case shouldNotReachNetwork
}

private actor IntroductionSubmissionRecorder {
    let response: ContactRequestResponse
    private var receivedSubmission: (playerID: Int, message: String)?

    init(response: ContactRequestResponse) {
        self.response = response
    }

    func create(playerID: Int, message: String) throws -> ContactRequestResponse {
        receivedSubmission = (playerID, message)
        return response
    }

    func submission() -> (playerID: Int, message: String)? {
        receivedSubmission
    }
}
