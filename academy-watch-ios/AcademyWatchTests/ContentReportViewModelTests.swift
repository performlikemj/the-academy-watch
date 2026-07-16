import XCTest
@testable import AcademyWatch

final class ContentReportViewModelTests: XCTestCase {
    @MainActor
    func testSuccessfulSubmissionTrimsDetailsAndUsesExactSubject() async throws {
        let client = SuccessfulContentReportClient()
        let subject = ContentReportSubject(
            subjectType: .contactMessage,
            subjectID: "message-42",
            title: "Report Message",
            explanation: "Review this message.",
            defaultReason: .participantSafety
        )
        let viewModel = ContentReportViewModel(subject: subject, apiClient: client)
        viewModel.details = "  Please review this message.\n"

        let submitted = await viewModel.submit()
        XCTAssertTrue(submitted)

        let submission = await client.recordedSubmission()
        XCTAssertEqual(submission?.subjectType, .contactMessage)
        XCTAssertEqual(submission?.subjectID, "message-42")
        XCTAssertEqual(submission?.reasonCode, "participant_safety")
        XCTAssertEqual(submission?.details, "Please review this message.")
        XCTAssertEqual(viewModel.submittedReport?.status, .open)
        XCTAssertNil(viewModel.errorMessage)
    }

    @MainActor
    func testRateLimitedSubmissionMapsToReportSpecificMessage() async {
        let viewModel = ContentReportViewModel(
            subject: reportSubject,
            apiClient: RateLimitedContentReportClient()
        )

        let submitted = await viewModel.submit()
        XCTAssertFalse(submitted)
        XCTAssertEqual(
            viewModel.errorMessage,
            "You’ve submitted several reports recently. Please wait before trying again."
        )
        XCTAssertFalse(viewModel.isSubmitting)
    }

    func testMapsOfflineTimeoutValidationAndUnknownFailures() {
        XCTAssertEqual(
            ContentReportViewModel.displayMessage(
                for: URLError(.notConnectedToInternet)
            ),
            "You’re offline. Reconnect and try submitting the report again."
        )
        XCTAssertEqual(
            ContentReportViewModel.displayMessage(for: URLError(.timedOut)),
            "The report timed out. Please try again."
        )
        XCTAssertEqual(
            ContentReportViewModel.displayMessage(
                for: APIClientError.server(statusCode: 400, message: "details must be at most 2000 characters")
            ),
            "details must be at most 2000 characters"
        )
        XCTAssertEqual(
            ContentReportViewModel.displayMessage(for: URLError(.badServerResponse)),
            "We couldn’t submit this report. Please try again."
        )
    }

    @MainActor
    private var reportSubject: ContentReportSubject {
        ContentReportSubject(
            subjectType: .other,
            subjectID: "request-42",
            title: "Report Introduction",
            explanation: "Review this introduction.",
            defaultReason: .participantSafety
        )
    }
}

private struct RecordedContentReportSubmission: Equatable, Sendable {
    let subjectType: ContentReportSubjectType
    let subjectID: String
    let reasonCode: String
    let details: String?
}

private actor SuccessfulContentReportClient: ContentReportAPIClientProtocol {
    private var submission: RecordedContentReportSubmission?

    func submitContentReport(
        subjectType: ContentReportSubjectType,
        subjectID: String,
        reasonCode: String,
        details: String?
    ) async throws -> ContentReportResponse {
        submission = RecordedContentReportSubmission(
            subjectType: subjectType,
            subjectID: subjectID,
            reasonCode: reasonCode,
            details: details
        )
        return ContentReportResponse(
            report: ContentReport(
                id: 41,
                subjectType: subjectType,
                subjectId: subjectID,
                reasonCode: reasonCode,
                details: details,
                status: .open,
                resolutionNotes: nil,
                createdAt: "2026-07-17T09:30:00+00:00",
                resolvedAt: nil
            )
        )
    }

    func recordedSubmission() -> RecordedContentReportSubmission? {
        submission
    }
}

private actor RateLimitedContentReportClient: ContentReportAPIClientProtocol {
    func submitContentReport(
        subjectType _: ContentReportSubjectType,
        subjectID _: String,
        reasonCode _: String,
        details _: String?
    ) async throws -> ContentReportResponse {
        throw APIClientError.server(statusCode: 429, message: "rate limited")
    }
}
