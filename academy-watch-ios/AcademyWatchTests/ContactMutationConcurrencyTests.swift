import XCTest
@testable import AcademyWatch

final class ContactMutationConcurrencyTests: XCTestCase {
    @MainActor
    func testPaginationOffsetIgnoresOptimisticAndLocallyCommittedMessages() async {
        let request = makeRequest()
        let messages = (1 ... 5).map(makeMessage)
        let client = PagingContactThreadClient(
            request: request,
            pages: [
                0: Array(messages[0 ... 1]),
                2: Array(messages[2 ... 3]),
                4: [messages[4]],
            ],
            total: messages.count,
            sentMessage: messages[4]
        )
        let viewModel = ContactThreadViewModel(
            contactRequest: request,
            apiClient: client,
            availability: ContactFeatureAvailability(),
            pageSize: 2
        )

        await viewModel.reload()
        viewModel.draft = messages[4].body
        await viewModel.sendMessage()
        await viewModel.loadNextPage()
        await viewModel.loadNextPage()

        let offsets = await client.recordedOffsets()
        XCTAssertEqual(offsets, [0, 2, 4])
        XCTAssertEqual(Set(viewModel.messages.map(\.id)), Set(messages.map(\.id)))
        XCTAssertEqual(viewModel.messages.count, messages.count)
        XCTAssertFalse(viewModel.canLoadMore)
    }

    @MainActor
    func testStaleConcurrentReloadCannotEraseCommittedSend() async {
        let request = makeRequest()
        let firstMessage = makeMessage(1)
        let committedMessage = makeMessage(2)
        let client = DelayedReloadContactThreadClient(
            request: request,
            staleMessages: [firstMessage],
            committedMessage: committedMessage
        )
        let viewModel = ContactThreadViewModel(
            contactRequest: request,
            apiClient: client,
            availability: ContactFeatureAvailability(),
            pageSize: 50
        )

        await viewModel.reload()
        let staleReload = Task { @MainActor in
            await viewModel.reload()
        }
        await client.waitUntilDelayedReloadStarts()

        viewModel.draft = committedMessage.body
        await viewModel.sendMessage()
        await client.releaseDelayedReload()
        await staleReload.value

        XCTAssertEqual(
            Set(viewModel.messages.map(\.id)),
            Set([firstMessage.id, committedMessage.id])
        )
        XCTAssertFalse(viewModel.isSending)
        XCTAssertFalse(viewModel.isLoading)
    }

    @MainActor
    func testCancelledCallersStillCommitReturnedMessageAndOutcomeResponses() async {
        let existingOutcome = makeOutcome(stage: .trialScheduled, suffix: "existing")
        let request = makeRequest(latestOutcome: existingOutcome)
        let committedMessage = makeMessage(1)
        let committedOutcome = makeOutcome(stage: .signed, suffix: "committed")
        let client = SuspendingContactMutationClient(
            request: request,
            committedMessage: committedMessage,
            committedOutcome: committedOutcome
        )
        let viewModel = ContactThreadViewModel(
            contactRequest: request,
            apiClient: client,
            availability: ContactFeatureAvailability()
        )

        XCTAssertEqual(viewModel.selectedOutcomeStage, .trialScheduled)

        viewModel.draft = committedMessage.body
        let send = Task { @MainActor in
            await viewModel.sendMessage()
        }
        await client.waitUntilSendStarts()
        send.cancel()
        await client.releaseSend()
        await send.value

        XCTAssertEqual(viewModel.messages, [committedMessage])
        XCTAssertFalse(viewModel.isSending)

        viewModel.selectedOutcomeStage = .signed
        let report = Task { @MainActor in
            await viewModel.reportOutcome()
        }
        await client.waitUntilOutcomeStarts()
        report.cancel()
        await client.releaseOutcome()
        let didReport = await report.value

        XCTAssertTrue(didReport)
        XCTAssertEqual(viewModel.contactRequest.latestOutcome, committedOutcome)
        XCTAssertEqual(viewModel.selectedOutcomeStage, .signed)
        XCTAssertFalse(viewModel.isReportingOutcome)
    }

    @MainActor
    func testPlayerOwnerUsesPlayerIdentityWhenSendingAndCanRecordOutcome() async throws {
        let request = makeRequest()
        let committedMessage = ContactMessage(
            id: "owner-message",
            contactRequestId: request.id,
            senderRole: .player,
            senderDisplayName: "Test Player",
            body: "My representative can join the call.",
            createdAt: "2026-07-17T10:00:00"
        )
        let committedOutcome = makeOutcome(stage: .trialScheduled, suffix: "owner")
        let client = SuspendingContactMutationClient(
            request: request,
            committedMessage: committedMessage,
            committedOutcome: committedOutcome
        )
        let viewModel = ContactThreadViewModel(
            contactRequest: request,
            apiClient: client,
            availability: ContactFeatureAvailability(),
            viewerRole: .player
        )

        XCTAssertEqual(viewModel.viewerRole, .player)
        XCTAssertEqual(viewModel.viewerDisplayName, "Test Player")
        XCTAssertEqual(viewModel.counterpartDisplayName, "Alex Scout")

        viewModel.draft = committedMessage.body
        let send = Task { @MainActor in
            await viewModel.sendMessage()
        }
        await client.waitUntilSendStarts()

        let optimisticMessage = try XCTUnwrap(viewModel.messages.first)
        XCTAssertTrue(optimisticMessage.id.hasPrefix("local-"))
        XCTAssertEqual(optimisticMessage.senderRole, .player)
        XCTAssertEqual(optimisticMessage.senderDisplayName, "Test Player")
        XCTAssertEqual(optimisticMessage.body, committedMessage.body)
        XCTAssertTrue(viewModel.isSending)
        XCTAssertEqual(viewModel.draft, "")

        await client.releaseSend()
        await send.value

        XCTAssertEqual(viewModel.messages, [committedMessage])
        XCTAssertFalse(viewModel.isSending)

        viewModel.selectedOutcomeStage = .trialScheduled
        viewModel.outcomeNotes = "Owner confirmed the visit."
        let outcome = Task { @MainActor in
            await viewModel.reportOutcome()
        }
        await client.waitUntilOutcomeStarts()

        XCTAssertEqual(viewModel.contactRequest.latestOutcome?.stage, .trialScheduled)
        XCTAssertEqual(viewModel.contactRequest.latestOutcome?.notes, "Owner confirmed the visit.")
        XCTAssertTrue(viewModel.isReportingOutcome)

        await client.releaseOutcome()
        let didRecordOutcome = await outcome.value

        XCTAssertTrue(didRecordOutcome)
        XCTAssertEqual(viewModel.contactRequest.latestOutcome, committedOutcome)
        XCTAssertEqual(viewModel.selectedOutcomeStage, .trialScheduled)
        XCTAssertEqual(viewModel.outcomeNotes, "")
        XCTAssertFalse(viewModel.isReportingOutcome)
    }

    @MainActor
    func testCancelledCallerStillCommitsReturnedWithdrawalAndSettlesBusyState() async {
        let pending = makeRequest(status: .pending)
        let withdrawn = pending.replacing(status: .withdrawn)
        let client = SuspendingWithdrawalClient(pending: pending, withdrawn: withdrawn)
        let viewModel = SentContactRequestsViewModel(
            apiClient: client,
            availability: ContactFeatureAvailability()
        )

        await viewModel.reload()
        let withdrawal = Task { @MainActor in
            await viewModel.withdraw(pending)
        }
        await client.waitUntilWithdrawalStarts()
        withdrawal.cancel()
        await client.releaseWithdrawal()
        await withdrawal.value

        XCTAssertEqual(viewModel.requests, [withdrawn])
        XCTAssertTrue(viewModel.withdrawingRequestIDs.isEmpty)
    }

    @MainActor
    func testCancelledFullLoadsSettleCurrentRevisionLoadingFlags() async {
        let request = makeRequest()
        let threadClient = SuspendingThreadLoadClient(request: request)
        let thread = ContactThreadViewModel(
            contactRequest: request,
            apiClient: threadClient,
            availability: ContactFeatureAvailability()
        )

        let threadLoad = Task { @MainActor in
            await thread.reload()
        }
        await threadClient.waitUntilLoadStarts()
        threadLoad.cancel()
        await threadClient.releaseLoad()
        await threadLoad.value

        XCTAssertFalse(thread.isLoading)

        let sentClient = SuspendingSentLoadClient()
        let sent = SentContactRequestsViewModel(
            apiClient: sentClient,
            availability: ContactFeatureAvailability()
        )
        let sentLoad = Task { @MainActor in
            await sent.reload()
        }
        await sentClient.waitUntilLoadStarts()
        sentLoad.cancel()
        await sentClient.releaseLoad()
        await sentLoad.value

        XCTAssertFalse(sent.isLoading)
    }

    private func makeRequest(
        status: ContactRequestStatus = .accepted,
        latestOutcome: ContactOutcome? = nil
    ) -> ContactRequest {
        ContactRequest(
            id: "b3bd7fe9-05b4-4bb8-b8b1-298d5aa7ba71",
            playerApiId: 403_064,
            message: "Introduction request",
            status: status,
            createdAt: "2026-07-12T10:15:00",
            respondedAt: status == .accepted ? "2026-07-13T08:30:00" : nil,
            expiresAt: "2026-07-26T10:15:00",
            participants: ContactRequestParticipants(
                scout: ContactRequestParticipant(displayName: "Alex Scout"),
                player: ContactRequestParticipant(displayName: "Test Player")
            ),
            latestOutcome: latestOutcome
        )
    }

    private func makeMessage(_ index: Int) -> ContactMessage {
        ContactMessage(
            id: "message-\(index)",
            contactRequestId: "b3bd7fe9-05b4-4bb8-b8b1-298d5aa7ba71",
            senderRole: index.isMultiple(of: 2) ? .player : .scout,
            senderDisplayName: index.isMultiple(of: 2) ? "Test Player" : "Alex Scout",
            body: "Message \(index)",
            createdAt: String(format: "2026-07-13T09:%02d:00", index)
        )
    }

    private func makeOutcome(stage: ContactOutcomeStage, suffix: String) -> ContactOutcome {
        ContactOutcome(
            stage: stage,
            notes: suffix,
            occurredAt: "2026-07-17T10:00:00",
            createdAt: "2026-07-17T10:00:00-\(suffix)"
        )
    }
}

private actor PagingContactThreadClient: ContactThreadAPIClientProtocol {
    let request: ContactRequest
    let pages: [Int: [ContactMessage]]
    let total: Int
    let sentMessage: ContactMessage
    private var offsets: [Int] = []
    private var didSend = false

    init(
        request: ContactRequest,
        pages: [Int: [ContactMessage]],
        total: Int,
        sentMessage: ContactMessage
    ) {
        self.request = request
        self.pages = pages
        self.total = total
        self.sentMessage = sentMessage
    }

    func fetchContactMessages(
        requestID _: String,
        limit: Int,
        offset: Int
    ) async throws -> ContactMessagesResponse {
        offsets.append(offset)
        return ContactMessagesResponse(
            messages: pages[offset] ?? [],
            contactRequest: request,
            total: didSend ? total : max(0, total - 1),
            limit: limit,
            offset: offset
        )
    }

    func sendContactMessage(requestID _: String, body _: String) async throws -> ContactMessageResponse {
        didSend = true
        return ContactMessageResponse(message: sentMessage)
    }

    func reportContactOutcome(
        requestID _: String,
        stage: ContactOutcomeStage,
        notes: String?,
        occurredAt _: String?
    ) async throws -> ContactOutcomeResponse {
        let outcome = ContactOutcome(
            stage: stage,
            notes: notes,
            occurredAt: "2026-07-17T10:00:00",
            createdAt: "2026-07-17T10:00:00"
        )
        return ContactOutcomeResponse(
            outcome: outcome,
            contactRequest: request.replacing(latestOutcome: outcome)
        )
    }

    func recordedOffsets() -> [Int] {
        offsets
    }
}

private actor DelayedReloadContactThreadClient: ContactThreadAPIClientProtocol {
    let request: ContactRequest
    let staleMessages: [ContactMessage]
    let committedMessage: ContactMessage

    private var loadCount = 0
    private var delayedReloadStarted = false
    private var delayedReloadWaiters: [CheckedContinuation<Void, Never>] = []
    private var delayedReloadContinuation: CheckedContinuation<Void, Never>?

    init(
        request: ContactRequest,
        staleMessages: [ContactMessage],
        committedMessage: ContactMessage
    ) {
        self.request = request
        self.staleMessages = staleMessages
        self.committedMessage = committedMessage
    }

    func fetchContactMessages(
        requestID _: String,
        limit: Int,
        offset: Int
    ) async throws -> ContactMessagesResponse {
        loadCount += 1
        if loadCount > 1 {
            await withCheckedContinuation { continuation in
                delayedReloadContinuation = continuation
                delayedReloadStarted = true
                delayedReloadWaiters.forEach { $0.resume() }
                delayedReloadWaiters = []
            }
        }
        return ContactMessagesResponse(
            messages: staleMessages,
            contactRequest: request,
            total: staleMessages.count,
            limit: limit,
            offset: offset
        )
    }

    func sendContactMessage(requestID _: String, body _: String) async throws -> ContactMessageResponse {
        ContactMessageResponse(message: committedMessage)
    }

    func reportContactOutcome(
        requestID _: String,
        stage _: ContactOutcomeStage,
        notes _: String?,
        occurredAt _: String?
    ) async throws -> ContactOutcomeResponse {
        fatalError("Outcome reporting is not used in this test")
    }

    func waitUntilDelayedReloadStarts() async {
        if delayedReloadStarted { return }
        await withCheckedContinuation { continuation in
            delayedReloadWaiters.append(continuation)
        }
    }

    func releaseDelayedReload() {
        delayedReloadContinuation?.resume()
        delayedReloadContinuation = nil
    }
}

private actor SuspendingContactMutationClient: ContactThreadAPIClientProtocol {
    let request: ContactRequest
    let committedMessage: ContactMessage
    let committedOutcome: ContactOutcome

    private var sendStarted = false
    private var sendWaiters: [CheckedContinuation<Void, Never>] = []
    private var sendContinuation: CheckedContinuation<Void, Never>?
    private var outcomeStarted = false
    private var outcomeWaiters: [CheckedContinuation<Void, Never>] = []
    private var outcomeContinuation: CheckedContinuation<Void, Never>?

    init(
        request: ContactRequest,
        committedMessage: ContactMessage,
        committedOutcome: ContactOutcome
    ) {
        self.request = request
        self.committedMessage = committedMessage
        self.committedOutcome = committedOutcome
    }

    func fetchContactMessages(
        requestID _: String,
        limit: Int,
        offset: Int
    ) async throws -> ContactMessagesResponse {
        ContactMessagesResponse(
            messages: [],
            contactRequest: request,
            total: 0,
            limit: limit,
            offset: offset
        )
    }

    func sendContactMessage(requestID _: String, body _: String) async throws -> ContactMessageResponse {
        await withCheckedContinuation { continuation in
            sendContinuation = continuation
            sendStarted = true
            sendWaiters.forEach { $0.resume() }
            sendWaiters = []
        }
        return ContactMessageResponse(message: committedMessage)
    }

    func reportContactOutcome(
        requestID _: String,
        stage _: ContactOutcomeStage,
        notes _: String?,
        occurredAt _: String?
    ) async throws -> ContactOutcomeResponse {
        await withCheckedContinuation { continuation in
            outcomeContinuation = continuation
            outcomeStarted = true
            outcomeWaiters.forEach { $0.resume() }
            outcomeWaiters = []
        }
        return ContactOutcomeResponse(
            outcome: committedOutcome,
            contactRequest: request.replacing(latestOutcome: committedOutcome)
        )
    }

    func waitUntilSendStarts() async {
        if sendStarted { return }
        await withCheckedContinuation { continuation in
            sendWaiters.append(continuation)
        }
    }

    func releaseSend() {
        sendContinuation?.resume()
        sendContinuation = nil
    }

    func waitUntilOutcomeStarts() async {
        if outcomeStarted { return }
        await withCheckedContinuation { continuation in
            outcomeWaiters.append(continuation)
        }
    }

    func releaseOutcome() {
        outcomeContinuation?.resume()
        outcomeContinuation = nil
    }
}

private actor SuspendingWithdrawalClient: SentContactRequestsAPIClientProtocol {
    let pending: ContactRequest
    let withdrawn: ContactRequest

    private var withdrawalStarted = false
    private var withdrawalWaiters: [CheckedContinuation<Void, Never>] = []
    private var withdrawalContinuation: CheckedContinuation<Void, Never>?

    init(pending: ContactRequest, withdrawn: ContactRequest) {
        self.pending = pending
        self.withdrawn = withdrawn
    }

    func fetchSentContactRequests(limit: Int, offset: Int) async throws -> ContactRequestsResponse {
        ContactRequestsResponse(
            requests: [pending],
            box: .sent,
            total: 1,
            limit: limit,
            offset: offset
        )
    }

    func withdrawContactRequest(requestID _: String) async throws -> ContactRequestResponse {
        await withCheckedContinuation { continuation in
            withdrawalContinuation = continuation
            withdrawalStarted = true
            withdrawalWaiters.forEach { $0.resume() }
            withdrawalWaiters = []
        }
        return ContactRequestResponse(contactRequest: withdrawn)
    }

    func waitUntilWithdrawalStarts() async {
        if withdrawalStarted { return }
        await withCheckedContinuation { continuation in
            withdrawalWaiters.append(continuation)
        }
    }

    func releaseWithdrawal() {
        withdrawalContinuation?.resume()
        withdrawalContinuation = nil
    }
}

private actor SuspendingThreadLoadClient: ContactThreadAPIClientProtocol {
    let request: ContactRequest
    private var loadStarted = false
    private var loadWaiters: [CheckedContinuation<Void, Never>] = []
    private var loadContinuation: CheckedContinuation<Void, Never>?

    init(request: ContactRequest) {
        self.request = request
    }

    func fetchContactMessages(
        requestID _: String,
        limit: Int,
        offset: Int
    ) async throws -> ContactMessagesResponse {
        await withCheckedContinuation { continuation in
            loadContinuation = continuation
            loadStarted = true
            loadWaiters.forEach { $0.resume() }
            loadWaiters = []
        }
        return ContactMessagesResponse(
            messages: [],
            contactRequest: request,
            total: 0,
            limit: limit,
            offset: offset
        )
    }

    func sendContactMessage(requestID _: String, body _: String) async throws -> ContactMessageResponse {
        fatalError("Message sending is not used in this test")
    }

    func reportContactOutcome(
        requestID _: String,
        stage _: ContactOutcomeStage,
        notes _: String?,
        occurredAt _: String?
    ) async throws -> ContactOutcomeResponse {
        fatalError("Outcome reporting is not used in this test")
    }

    func waitUntilLoadStarts() async {
        if loadStarted { return }
        await withCheckedContinuation { continuation in
            loadWaiters.append(continuation)
        }
    }

    func releaseLoad() {
        loadContinuation?.resume()
        loadContinuation = nil
    }
}

private actor SuspendingSentLoadClient: SentContactRequestsAPIClientProtocol {
    private var loadStarted = false
    private var loadWaiters: [CheckedContinuation<Void, Never>] = []
    private var loadContinuation: CheckedContinuation<Void, Never>?

    func fetchSentContactRequests(limit: Int, offset: Int) async throws -> ContactRequestsResponse {
        await withCheckedContinuation { continuation in
            loadContinuation = continuation
            loadStarted = true
            loadWaiters.forEach { $0.resume() }
            loadWaiters = []
        }
        return ContactRequestsResponse(
            requests: [],
            box: .sent,
            total: 0,
            limit: limit,
            offset: offset
        )
    }

    func withdrawContactRequest(requestID _: String) async throws -> ContactRequestResponse {
        fatalError("Withdrawal is not used in this test")
    }

    func waitUntilLoadStarts() async {
        if loadStarted { return }
        await withCheckedContinuation { continuation in
            loadWaiters.append(continuation)
        }
    }

    func releaseLoad() {
        loadContinuation?.resume()
        loadContinuation = nil
    }
}
