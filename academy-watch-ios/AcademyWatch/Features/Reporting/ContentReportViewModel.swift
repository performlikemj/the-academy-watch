import Combine
import Foundation

@MainActor
final class ContentReportViewModel: ObservableObject {
    let subject: ContentReportSubject

    @Published var selectedReason: ContentReportReason
    @Published var details = ""
    @Published private(set) var isSubmitting = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var submittedReport: ContentReport?

    private let apiClient: any ContentReportAPIClientProtocol
    private var submissionRevision = 0

    init(
        subject: ContentReportSubject,
        apiClient: any ContentReportAPIClientProtocol = APIClient()
    ) {
        self.subject = subject
        self.apiClient = apiClient
        selectedReason = subject.defaultReason
    }

    var normalizedDetails: String? {
        let clean = details.trimmingCharacters(in: .whitespacesAndNewlines)
        return clean.isEmpty ? nil : clean
    }

    var canSubmit: Bool {
        !isSubmitting
            && subject.subjectID.count <= ContentReportLimits.maximumSubjectIDLength
            && selectedReason.rawValue.count <= ContentReportLimits.maximumReasonCodeLength
            && (normalizedDetails?.count ?? 0) <= ContentReportLimits.maximumDetailsLength
    }

    @discardableResult
    func submit() async -> Bool {
        guard canSubmit else { return false }

        submissionRevision += 1
        let revision = submissionRevision
        isSubmitting = true
        errorMessage = nil

        defer {
            if revision == submissionRevision {
                isSubmitting = false
            }
        }

        do {
            let response = try await apiClient.submitContentReport(
                subjectType: subject.subjectType,
                subjectID: subject.subjectID,
                reasonCode: selectedReason.rawValue,
                details: normalizedDetails
            )
            guard revision == submissionRevision else { return false }
            // A server response is authoritative even if the presenting task
            // was cancelled immediately after the request completed.
            submittedReport = response.report
            return true
        } catch {
            guard revision == submissionRevision else { return false }
            if Self.isCancellation(error) {
                errorMessage = nil
            } else {
                errorMessage = Self.displayMessage(for: error)
            }
            return false
        }
    }

    func clearError() {
        errorMessage = nil
    }

    nonisolated static func displayMessage(for error: Error) -> String {
        if let apiError = error as? APIClientError {
            if apiError.statusCode == 429 {
                return "You’ve submitted several reports recently. Please wait before trying again."
            }
            if apiError.statusCode == 400 {
                return apiError.localizedDescription
            }
        }

        if let urlError = error as? URLError {
            switch urlError.code {
            case .notConnectedToInternet, .networkConnectionLost:
                return "You’re offline. Reconnect and try submitting the report again."
            case .timedOut:
                return "The report timed out. Please try again."
            default:
                break
            }
        }

        return "We couldn’t submit this report. Please try again."
    }

    private static func isCancellation(_ error: Error) -> Bool {
        error is CancellationError || (error as? URLError)?.code == .cancelled
    }
}
