import Combine
import Foundation

@MainActor
final class ContactThreadViewModel: ObservableObject {
    @Published private(set) var contactRequest: ContactRequest
    @Published private(set) var messages: [ContactMessage] = []
    @Published var draft = ""
    @Published var selectedOutcomeStage: ContactOutcomeStage = .contacted
    @Published var outcomeNotes = ""
    @Published private(set) var isLoading = false
    @Published private(set) var isLoadingMore = false
    @Published private(set) var isSending = false
    @Published private(set) var isReportingOutcome = false
    @Published private(set) var hasLoaded = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var isFixturePreview = false

    private let apiClient: any ContactThreadAPIClientProtocol
    private let availability: ContactFeatureAvailability
    private let pageSize: Int
    private var total = 0
    private var nextMessageOffset = 0
    private var locallyCommittedMessageIDs: Set<String> = []
    private var loadRevision = 0
    private var messageMutationRevision = 0
    private var outcomeMutationRevision = 0
    private var activeLoadTask: Task<Void, Never>?
    private var activePaginationTask: Task<Void, Never>?

    init(
        contactRequest: ContactRequest,
        apiClient: any ContactThreadAPIClientProtocol,
        availability: ContactFeatureAvailability,
        pageSize: Int = 50
    ) {
        self.contactRequest = contactRequest
        self.apiClient = apiClient
        self.availability = availability
        self.pageSize = pageSize

        #if DEBUG
        if FullCircleFixtureDestination.fromLaunchArguments(ProcessInfo.processInfo.arguments) == .thread,
           let fixture = Self.decodeFixture() {
            self.contactRequest = fixture.contactRequest
            messages = fixture.messages
            total = fixture.total
            nextMessageOffset = fixture.offset + fixture.messages.count
            hasLoaded = true
            isFixturePreview = true
            availability.recordSuccess()
        }
        #endif

        selectedOutcomeStage = self.contactRequest.latestOutcome?.stage ?? .contacted
    }

    var canSend: Bool {
        let clean = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        return !clean.isEmpty && clean.count <= 2_000 && !isSending
    }

    var canReportOutcome: Bool {
        outcomeNotes.trimmingCharacters(in: .whitespacesAndNewlines).count <= 2_000
            && !isReportingOutcome
    }

    var canLoadMore: Bool {
        nextMessageOffset < total && !isLoading && !isLoadingMore
    }

    func loadIfNeeded() async {
        guard !hasLoaded, !isFixturePreview else { return }
        await reload()
    }

    func reload() async {
        guard !isFixturePreview else { return }
        loadRevision += 1
        let revision = loadRevision
        activeLoadTask?.cancel()
        activePaginationTask?.cancel()
        activePaginationTask = nil
        isLoadingMore = false

        let task = Task { [weak self] in
            guard let self else { return }
            await self.performFullLoad(revision: revision)
        }
        activeLoadTask = task
        await withTaskCancellationHandler {
            await task.value
        } onCancel: {
            task.cancel()
        }
        if revision == loadRevision { activeLoadTask = nil }
    }

    func loadNextPage() async {
        guard canLoadMore, activePaginationTask == nil, !isFixturePreview else { return }
        let revision = loadRevision
        let offset = nextMessageOffset
        isLoadingMore = true
        let task = Task { [weak self] in
            guard let self else { return }
            await self.performPagination(revision: revision, offset: offset)
        }
        activePaginationTask = task
        await withTaskCancellationHandler {
            await task.value
        } onCancel: {
            task.cancel()
        }
        if revision == loadRevision {
            activePaginationTask = nil
            isLoadingMore = false
        }
    }

    func sendMessage() async {
        let body = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !body.isEmpty, body.count <= 2_000, !isSending else { return }

        messageMutationRevision += 1
        let revision = messageMutationRevision
        let temporaryID = "local-\(UUID().uuidString)"
        let totalBeforeSend = total
        let optimistic = ContactMessage(
            id: temporaryID,
            contactRequestId: contactRequest.id,
            senderRole: .scout,
            senderDisplayName: contactRequest.participants.scout.displayName,
            body: body,
            createdAt: Self.nowString()
        )
        draft = ""
        messages.append(optimistic)
        isSending = true
        errorMessage = nil

        defer {
            if revision == messageMutationRevision {
                isSending = false
            }
        }

        do {
            let response = try await apiClient.sendContactMessage(
                requestID: contactRequest.id,
                body: body
            )
            guard revision == messageMutationRevision else { return }
            availability.recordSuccess()
            locallyCommittedMessageIDs.insert(response.message.id)
            reconcileCommittedMessage(response.message, replacingTemporaryID: temporaryID)
            total = max(total, totalBeforeSend + 1)
        } catch {
            guard revision == messageMutationRevision else { return }
            messages.removeAll { $0.id == temporaryID }
            if Self.isCancellation(error) {
                draft = body
                errorMessage = nil
            } else if availability.recordFailure(error) {
                errorMessage = nil
            } else {
                draft = body
                errorMessage = Self.displayMessage(for: error)
            }
        }
    }

    func reportOutcome() async -> Bool {
        let notes = outcomeNotes.trimmingCharacters(in: .whitespacesAndNewlines)
        guard notes.count <= 2_000, !isReportingOutcome else { return false }

        outcomeMutationRevision += 1
        let revision = outcomeMutationRevision
        let originalRequest = contactRequest
        let timestamp = Self.nowString()
        let optimistic = ContactOutcome(
            stage: selectedOutcomeStage,
            notes: notes.isEmpty ? nil : notes,
            occurredAt: timestamp,
            createdAt: timestamp
        )
        contactRequest = contactRequest.replacing(latestOutcome: optimistic)
        isReportingOutcome = true
        errorMessage = nil

        defer {
            if revision == outcomeMutationRevision {
                isReportingOutcome = false
            }
        }

        do {
            let response = try await apiClient.reportContactOutcome(
                requestID: contactRequest.id,
                stage: selectedOutcomeStage,
                notes: notes.isEmpty ? nil : notes,
                occurredAt: nil
            )
            guard revision == outcomeMutationRevision else { return false }
            availability.recordSuccess()
            contactRequest = response.contactRequest
            selectedOutcomeStage = response.contactRequest.latestOutcome?.stage ?? response.outcome.stage
            outcomeNotes = ""
            return true
        } catch {
            guard revision == outcomeMutationRevision else { return false }
            if contactRequest.latestOutcome?.createdAt == timestamp {
                contactRequest = originalRequest
            }
            if Self.isCancellation(error) {
                errorMessage = nil
            } else if availability.recordFailure(error) {
                errorMessage = nil
            } else {
                errorMessage = Self.displayMessage(for: error)
            }
            return false
        }
    }

    private func performFullLoad(revision: Int) async {
        isLoading = true
        errorMessage = nil
        defer {
            if revision == loadRevision {
                isLoading = false
            }
        }
        do {
            let response = try await apiClient.fetchContactMessages(
                requestID: contactRequest.id,
                limit: pageSize,
                offset: 0
            )
            guard revision == loadRevision, !Task.isCancelled else { return }
            availability.recordSuccess()
            contactRequest = response.contactRequest
            selectedOutcomeStage = response.contactRequest.latestOutcome?.stage ?? .contacted
            replaceServerPagePreservingLocalMessages(response.messages)
            nextMessageOffset = response.offset + response.messages.count
            total = max(total, response.total)
            hasLoaded = true
        } catch {
            guard revision == loadRevision else { return }
            guard !Self.isCancellation(error) else { return }
            hasLoaded = true
            if availability.recordFailure(error) {
                messages = []
                errorMessage = nil
            } else {
                errorMessage = Self.displayMessage(for: error)
            }
        }
    }

    private func performPagination(revision: Int, offset: Int) async {
        do {
            let response = try await apiClient.fetchContactMessages(
                requestID: contactRequest.id,
                limit: pageSize,
                offset: offset
            )
            guard revision == loadRevision, offset == nextMessageOffset, !Task.isCancelled else { return }
            availability.recordSuccess()
            contactRequest = response.contactRequest
            mergeMessages(response.messages)
            nextMessageOffset = response.offset + response.messages.count
            total = max(total, response.total)
        } catch {
            guard revision == loadRevision, !Self.isCancellation(error) else { return }
            if availability.recordFailure(error) {
                messages = []
                errorMessage = nil
            } else {
                errorMessage = Self.displayMessage(for: error)
            }
        }
    }

    private static func nowString() -> String {
        ISO8601DateFormatter().string(from: Date())
    }

    private func reconcileCommittedMessage(
        _ committed: ContactMessage,
        replacingTemporaryID temporaryID: String
    ) {
        if let committedIndex = messages.firstIndex(where: { $0.id == committed.id }) {
            messages[committedIndex] = committed
            messages.removeAll { $0.id == temporaryID }
        } else if let temporaryIndex = messages.firstIndex(where: { $0.id == temporaryID }) {
            messages[temporaryIndex] = committed
        } else {
            messages.append(committed)
        }
        messages = Self.sortedDeduplicated(messages)
    }

    private func replaceServerPagePreservingLocalMessages(_ serverMessages: [ContactMessage]) {
        let preserved = messages.filter { message in
            message.id.hasPrefix("local-") || locallyCommittedMessageIDs.contains(message.id)
        }
        messages = Self.sortedDeduplicated(serverMessages + preserved)
    }

    private func mergeMessages(_ serverMessages: [ContactMessage]) {
        messages = Self.sortedDeduplicated(messages + serverMessages)
    }

    private static func sortedDeduplicated(_ candidates: [ContactMessage]) -> [ContactMessage] {
        var seen: Set<String> = []
        return candidates
            .filter { seen.insert($0.id).inserted }
            .sorted { lhs, rhs in
                if lhs.createdAt == rhs.createdAt {
                    return lhs.id < rhs.id
                }
                return lhs.createdAt < rhs.createdAt
            }
    }

    private static func isCancellation(_ error: Error) -> Bool {
        error is CancellationError || (error as? URLError)?.code == .cancelled
    }

    private static func displayMessage(for error: Error) -> String {
        if let apiError = error as? APIClientError, apiError.statusCode == 429 {
            return "You’ve reached the current messaging limit. Please try again later."
        }
        return error.localizedDescription
    }

    #if DEBUG
    private static func decodeFixture() -> ContactMessagesResponse? {
        let payload = #"""
        {
          "messages": [
            {
              "id": "d5d9622d-02cb-45f1-a06f-04e57bd9d693",
              "contact_request_id": "b3bd7fe9-05b4-4bb8-b8b1-298d5aa7ba71",
              "sender_role": "scout",
              "sender_display_name": "Alex Scout",
              "body": "Thanks for accepting. Would Tuesday suit for an introductory call?",
              "created_at": "2026-07-13T09:00:00"
            },
            {
              "id": "98e4be7d-2537-449f-a662-cb253e43dadb",
              "contact_request_id": "b3bd7fe9-05b4-4bb8-b8b1-298d5aa7ba71",
              "sender_role": "player",
              "sender_display_name": "Habeeb Amass",
              "body": "Tuesday works. My representative can join at 14:00.",
              "created_at": "2026-07-13T09:18:00"
            },
            {
              "id": "8a49c4ba-035d-4e8e-b823-ddd43699d64b",
              "contact_request_id": "b3bd7fe9-05b4-4bb8-b8b1-298d5aa7ba71",
              "sender_role": "scout",
              "sender_display_name": "Alex Scout",
              "body": "Perfect — invitation sent. Looking forward to speaking.",
              "created_at": "2026-07-13T09:25:00"
            }
          ],
          "contact_request": {
            "id": "b3bd7fe9-05b4-4bb8-b8b1-298d5aa7ba71",
            "player_api_id": 403064,
            "message": "I’d like to discuss your development pathway and a potential first-team opportunity.",
            "status": "accepted",
            "created_at": "2026-07-12T10:15:00",
            "responded_at": "2026-07-13T08:30:00",
            "expires_at": "2026-07-26T10:15:00",
            "participants": {
              "scout": {"display_name": "Alex Scout"},
              "player": {"display_name": "Habeeb Amass"}
            },
            "latest_outcome": {
              "stage": "trial_scheduled",
              "notes": "Training-ground visit arranged.",
              "occurred_at": "2026-07-18T09:00:00",
              "created_at": "2026-07-15T11:20:00"
            }
          },
          "total": 3,
          "limit": 50,
          "offset": 0
        }
        """#
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(ContactMessagesResponse.self, from: Data(payload.utf8))
    }
    #endif
}
