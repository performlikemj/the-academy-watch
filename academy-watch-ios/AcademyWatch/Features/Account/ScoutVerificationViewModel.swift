import Combine
import Foundation

@MainActor
final class ScoutVerificationViewModel: ObservableObject {
    static let fullNameLimit = 200
    static let organizationLimit = 200
    static let roleTitleLimit = 120
    static let statementLimit = 2_000
    static let evidenceURLLimit = 500
    static let maximumEvidenceURLs = 10

    @Published private(set) var verification: ScoutVerification?
    @Published private(set) var isLoading = false
    @Published private(set) var isSubmitting = false
    @Published private(set) var hasLoaded = false
    @Published private(set) var isFixturePreview = false
    @Published private(set) var errorMessage: String?

    @Published var fullName = ""
    @Published var organization = ""
    @Published var roleTitle = ""
    @Published var statement = ""
    @Published var evidenceURLs = [""]

    private let apiClient: any ScoutVerificationAPIClientProtocol
    private var loadTask: Task<ScoutVerificationResponse, Error>?
    private var submissionTask: Task<ScoutVerificationResponse, Error>?
    private var loadRevision = 0
    private var submissionRevision = 0

    init(
        apiClient: any ScoutVerificationAPIClientProtocol = APIClient(),
        launchArguments: [String] = ProcessInfo.processInfo.arguments
    ) {
        self.apiClient = apiClient

        #if DEBUG
        if Self.usesVerificationFixture(launchArguments) {
            let response = Self.debugFixture
            verification = response.verification
            hasLoaded = true
            isFixturePreview = true
            if let verification = response.verification {
                populateForm(from: verification)
            }
        }
        #endif
    }

    var shouldShowApplicationForm: Bool {
        verification == nil || verification?.status == .rejected
    }

    var isFormValid: Bool {
        validationMessage == nil
    }

    var validationMessage: String? {
        if normalized(fullName).isEmpty {
            return "Enter your full name."
        }
        if fullName.count > Self.fullNameLimit {
            return "Full name must be \(Self.fullNameLimit) characters or fewer."
        }
        if normalized(organization).isEmpty {
            return "Enter your organization."
        }
        if organization.count > Self.organizationLimit {
            return "Organization must be \(Self.organizationLimit) characters or fewer."
        }
        if normalized(roleTitle).isEmpty {
            return "Enter your role or title."
        }
        if roleTitle.count > Self.roleTitleLimit {
            return "Role or title must be \(Self.roleTitleLimit) characters or fewer."
        }
        if normalized(statement).isEmpty {
            return "Tell us about your scouting work."
        }
        if statement.count > Self.statementLimit {
            return "Statement must be \(Self.statementLimit) characters or fewer."
        }

        let urls = normalizedEvidenceURLs
        if urls.isEmpty {
            return "Add at least one evidence URL."
        }
        if urls.count > Self.maximumEvidenceURLs {
            return "Add no more than \(Self.maximumEvidenceURLs) evidence URLs."
        }
        if urls.contains(where: { $0.count > Self.evidenceURLLimit }) {
            return "Evidence URLs must be \(Self.evidenceURLLimit) characters or fewer."
        }
        if urls.contains(where: { !Self.isAbsoluteHTTPSURL($0) }) {
            return "Evidence URLs must be complete https links, including https://."
        }
        return nil
    }

    func loadIfNeeded() async {
        guard !hasLoaded, !isLoading else { return }
        await load()
    }

    func reload() async {
        guard !isFixturePreview else { return }
        await load()
    }

    @discardableResult
    func submit() async -> Bool {
        guard shouldShowApplicationForm, !isSubmitting else { return false }
        guard let submission = makeSubmission() else {
            errorMessage = validationMessage
            return false
        }

        cancelLoad()
        submissionRevision += 1
        let requestRevision = submissionRevision
        errorMessage = nil
        isSubmitting = true

        let task = Task {
            try await apiClient.submitScoutVerification(submission)
        }
        submissionTask = task

        do {
            let response = try await task.value
            guard requestRevision == submissionRevision else { return false }

            verification = response.verification
            hasLoaded = true
            finishSubmission(revision: requestRevision)
            return true
        } catch {
            guard requestRevision == submissionRevision else { return false }
            finishSubmission(revision: requestRevision)
            if Self.isCancellation(error) {
                return false
            }
            errorMessage = error.localizedDescription
            return false
        }
    }

    func addEvidenceURL() {
        guard evidenceURLs.count < Self.maximumEvidenceURLs else { return }
        evidenceURLs.append("")
    }

    func removeEvidenceURL(at index: Int) {
        guard evidenceURLs.indices.contains(index) else { return }
        evidenceURLs.remove(at: index)
        if evidenceURLs.isEmpty {
            evidenceURLs = [""]
        }
    }

    func updateEvidenceURL(at index: Int, value: String) {
        guard evidenceURLs.indices.contains(index) else { return }
        evidenceURLs[index] = String(value.prefix(Self.evidenceURLLimit))
    }

    func cancel() {
        cancelLoad()
        submissionRevision += 1
        submissionTask?.cancel()
        submissionTask = nil
        isSubmitting = false
    }

    private func load() async {
        guard !isSubmitting else { return }

        loadRevision += 1
        let requestRevision = loadRevision
        loadTask?.cancel()
        errorMessage = nil
        isLoading = true

        let task = Task {
            try await apiClient.fetchScoutVerification()
        }
        loadTask = task

        do {
            let response = try await task.value
            guard requestRevision == loadRevision else { return }
            guard !Task.isCancelled else {
                finishLoad(revision: requestRevision)
                return
            }

            verification = response.verification
            if let verification = response.verification, verification.status == .rejected {
                populateForm(from: verification)
            }
            hasLoaded = true
            finishLoad(revision: requestRevision)
        } catch {
            guard requestRevision == loadRevision else { return }
            finishLoad(revision: requestRevision)
            if Self.isCancellation(error) {
                return
            }
            errorMessage = error.localizedDescription
        }
    }

    private func cancelLoad() {
        loadRevision += 1
        loadTask?.cancel()
        loadTask = nil
        isLoading = false
    }

    private func finishLoad(revision: Int) {
        guard revision == loadRevision else { return }
        loadTask = nil
        isLoading = false
    }

    private func finishSubmission(revision: Int) {
        guard revision == submissionRevision else { return }
        submissionTask = nil
        isSubmitting = false
    }

    private func makeSubmission() -> ScoutVerificationSubmission? {
        guard validationMessage == nil else { return nil }
        return ScoutVerificationSubmission(
            fullName: normalized(fullName),
            organization: normalized(organization),
            roleTitle: normalized(roleTitle),
            statement: normalized(statement),
            evidenceUrls: normalizedEvidenceURLs
        )
    }

    private var normalizedEvidenceURLs: [String] {
        evidenceURLs
            .map(normalized)
            .filter { !$0.isEmpty }
    }

    private func populateForm(from verification: ScoutVerification) {
        fullName = verification.fullName
        organization = verification.organization
        roleTitle = verification.roleTitle
        statement = verification.statement
        evidenceURLs = verification.evidenceUrls.isEmpty ? [""] : verification.evidenceUrls
    }

    private func normalized(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func isAbsoluteHTTPSURL(_ value: String) -> Bool {
        guard let components = URLComponents(string: value),
              components.scheme?.lowercased() == "https",
              let host = components.host,
              !host.isEmpty
        else { return false }
        return true
    }

    private static func isCancellation(_ error: Error) -> Bool {
        error is CancellationError || (error as? URLError)?.code == .cancelled
    }
}

#if DEBUG
private extension ScoutVerificationViewModel {
    static func usesVerificationFixture(_ arguments: [String]) -> Bool {
        arguments.indices.contains { index in
            arguments[index] == "-fullCircleFixture"
                && arguments.indices.contains(index + 1)
                && arguments[index + 1].lowercased() == "verification"
        }
    }

    static let debugFixture: ScoutVerificationResponse = {
        // Route-serializer-shaped preview data from ScoutVerification.to_dict().
        let payload = #"""
        {
          "verification": {
            "id": 17,
            "full_name": "Alex Scout",
            "organization": "Fixture Scouting Network",
            "role_title": "First-team scout",
            "statement": "I scout academy players for our recruitment team and report directly to our head of recruitment.",
            "evidence_urls": [
              "https://example.com/scouting-profile",
              "https://example.com/club-directory/alex-scout"
            ],
            "status": "rejected",
            "submitted_at": "2026-07-12T09:30:00+00:00",
            "reviewed_at": "2026-07-14T16:45:00+00:00",
            "review_notes": "Please add an official club directory or professional profile that confirms your current role.",
            "revocation_reason": null
          }
        }
        """#
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let response = try? decoder.decode(
            ScoutVerificationResponse.self,
            from: Data(payload.utf8)
        ) else {
            preconditionFailure("Invalid debug scout verification fixture")
        }
        return response
    }()
}
#endif
