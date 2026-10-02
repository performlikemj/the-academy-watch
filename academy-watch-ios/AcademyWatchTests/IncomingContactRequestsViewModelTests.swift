import XCTest
@testable import AcademyWatch

final class IncomingContactRequestsViewModelTests: XCTestCase {
    func testDecodesInboxSerializerShape() throws {
        let fixtureURL = try XCTUnwrap(
            Bundle(for: Self.self).url(
                forResource: "contact_requests_inbox",
                withExtension: "json"
            )
        )
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let response = try decoder.decode(
            ContactRequestsResponse.self,
            from: Data(contentsOf: fixtureURL)
        )

        XCTAssertEqual(response.box, .inbox)
        XCTAssertEqual(response.total, 2)
        XCTAssertEqual(response.requests.first?.participants.scout.displayName, "Alex Morgan")
        XCTAssertEqual(response.requests.first?.status, .pending)
    }

    @MainActor
    func testApprovedPlayerOwnershipLoadsCompleteInbox() async {
        let first = makeRequest(id: "request-1")
        let second = makeRequest(id: "request-2", status: .accepted)
        let client = PagingIncomingContactClient(
            claims: PlayerClaimsResponse(claims: [makeClaim(status: .approved)]),
            pages: [0: [first], 1: [second]],
            total: 2
        )
        let viewModel = IncomingContactRequestsViewModel(
            apiClient: client,
            availability: ContactFeatureAvailability(),
            pageSize: 1
        )

        await viewModel.reload()

        XCTAssertTrue(viewModel.hasLoaded)
        XCTAssertTrue(viewModel.ownsApprovedPlayerClaim)
        XCTAssertTrue(viewModel.isComplete)
        XCTAssertEqual(viewModel.requests, [first, second])
        XCTAssertFalse(viewModel.canLoadMore)
        let offsets = await client.recordedOffsets()
        XCTAssertEqual(offsets, [0, 1])
    }

    @MainActor
    func testHomeCountsDirectNotifiedAndGrantedIntroductionsBeyondPageOne() async {
        let direct = makeRequest(id: "direct")
        let notified = makeRequest(id: "notified", routing: .clubNotified)
        let granted = makeRequest(id: "older-granted", routing: .clubIncluded, consent: .granted)
        let pending = makeRequest(id: "awaiting-club", routing: .clubIncluded, consent: .pending)
        let declined = makeRequest(id: "club-declined", routing: .clubIncluded, consent: .declined)
        let firstPage = (0..<30).map { makeRequest(id: "terminal-\($0)", status: .declined) }
        let client = PagingIncomingContactClient(
            claims: PlayerClaimsResponse(claims: [makeClaim(status: .approved)]),
            pages: [0: firstPage, 30: [direct, notified, granted, pending, declined]], total: 35)
        let model = IncomingContactRequestsViewModel(apiClient: client, availability: ContactFeatureAvailability())
        await model.reload()
        XCTAssertTrue(model.isComplete)
        XCTAssertEqual(model.actionableRequests.map(\.id), ["direct", "notified", "older-granted"])
        XCTAssertFalse(direct.playerActionDetail.contains("club"))
        XCTAssertTrue(notified.playerActionDetail.contains("notified"))
        XCTAssertTrue(granted.playerActionDetail.contains("agreed"))
        XCTAssertEqual(direct.playerActionEyebrow, "Introduction · reply needed")
        let offsets = await client.recordedOffsets()
        XCTAssertEqual(offsets, [0, 30])
    }

    @MainActor
    func testFailedLaterIntroductionPageCannotConfirmCaughtUp() async {
        let client = PagingIncomingContactClient(
            claims: PlayerClaimsResponse(claims: [makeClaim(status: .approved)]),
            pages: [0: [makeRequest(status: .declined)]], total: 2, failingOffset: 1)
        let model = IncomingContactRequestsViewModel(apiClient: client, availability: ContactFeatureAvailability(), pageSize: 1)
        await model.reload()
        XCTAssertFalse(model.isLoading)
        XCTAssertFalse(model.isComplete)
        XCTAssertNotNil(model.errorMessage)
        XCTAssertTrue(model.requests.isEmpty)
    }

    @MainActor
    func testNonOwnerDoesNotRequestInbox() async {
        let client = PagingIncomingContactClient(
            claims: PlayerClaimsResponse(
                claims: [
                    makeClaim(status: .pending),
                    makeClaim(status: .approved, relationshipType: "guardian"),
                ]
            ),
            pages: [:],
            total: 0
        )
        let viewModel = IncomingContactRequestsViewModel(
            apiClient: client,
            availability: ContactFeatureAvailability()
        )

        await viewModel.reload()

        XCTAssertTrue(viewModel.hasLoaded)
        XCTAssertFalse(viewModel.ownsApprovedPlayerClaim)
        XCTAssertTrue(viewModel.requests.isEmpty)
        let offsets = await client.recordedOffsets()
        XCTAssertTrue(offsets.isEmpty)
    }

    @MainActor
    func testAcceptIsOptimisticThenCommitsServerResponse() async {
        let pending = makeRequest()
        let committed = makeRequest(
            status: .accepted,
            respondedAt: "2026-07-17T10:30:00"
        )
        let client = SuspendingIncomingMutationClient(
            initialRequest: pending,
            action: .accept,
            serverRequest: committed,
            shouldFail: false
        )
        let viewModel = IncomingContactRequestsViewModel(
            apiClient: client,
            availability: ContactFeatureAvailability()
        )
        await viewModel.reload()

        let mutation = Task { @MainActor in
            await viewModel.accept(pending)
        }
        await client.waitUntilMutationStarts()

        XCTAssertEqual(viewModel.requests.first?.status, .accepted)
        XCTAssertTrue(viewModel.respondingRequestIDs.contains(pending.id))

        await client.releaseMutation()
        await mutation.value

        XCTAssertEqual(viewModel.requests, [committed])
        XCTAssertTrue(viewModel.respondingRequestIDs.isEmpty)
        XCTAssertNil(viewModel.errorMessage)
    }

    @MainActor
    func testDeclineIsOptimisticThenRollsBackOnlyItsStatusOnFailure() async {
        let pending = makeRequest()
        let client = SuspendingIncomingMutationClient(
            initialRequest: pending,
            action: .decline,
            serverRequest: pending.replacing(status: .declined),
            shouldFail: true
        )
        let viewModel = IncomingContactRequestsViewModel(
            apiClient: client,
            availability: ContactFeatureAvailability()
        )
        await viewModel.reload()

        let mutation = Task { @MainActor in
            await viewModel.decline(pending)
        }
        await client.waitUntilMutationStarts()

        XCTAssertEqual(viewModel.requests.first?.status, .declined)
        XCTAssertTrue(viewModel.respondingRequestIDs.contains(pending.id))

        await client.releaseMutation()
        await mutation.value

        XCTAssertEqual(viewModel.requests, [pending])
        XCTAssertTrue(viewModel.respondingRequestIDs.isEmpty)
        XCTAssertEqual(viewModel.errorMessage, "The response could not be saved.")
    }

    @MainActor
    func testInbox404SetsStickyContactAvailability() async {
        let availability = ContactFeatureAvailability()
        let client = FailingIncomingLoadClient(
            claims: PlayerClaimsResponse(claims: [makeClaim(status: .approved)]),
            error: APIClientError.httpStatus(404)
        )
        let viewModel = IncomingContactRequestsViewModel(
            apiClient: client,
            availability: availability
        )

        await viewModel.reload()

        XCTAssertEqual(availability.state, .unavailable)
        XCTAssertTrue(viewModel.hasLoaded)
        XCTAssertTrue(viewModel.requests.isEmpty)
        XCTAssertNil(viewModel.errorMessage)
    }
}

private enum IncomingMutationAction: Sendable {
    case accept
    case decline
}

private actor PagingIncomingContactClient: IncomingContactRequestsAPIClientProtocol {
    let claims: PlayerClaimsResponse
    let pages: [Int: [ContactRequest]]
    let total: Int
    let failingOffset: Int?
    private var offsets: [Int] = []

    init(
        claims: PlayerClaimsResponse,
        pages: [Int: [ContactRequest]],
        total: Int, failingOffset: Int? = nil
    ) {
        self.claims = claims
        self.pages = pages
        self.total = total
        self.failingOffset = failingOffset
    }

    func fetchMyProfileClaims() async throws -> PlayerClaimsResponse {
        claims
    }

    func fetchIncomingContactRequests(
        limit: Int,
        offset: Int
    ) async throws -> ContactRequestsResponse {
        offsets.append(offset)
        if offset == failingOffset { throw URLError(.timedOut) }
        return ContactRequestsResponse(
            requests: pages[offset] ?? [],
            box: .inbox,
            total: total,
            limit: limit,
            offset: offset
        )
    }

    func acceptContactRequest(requestID _: String) async throws -> ContactRequestResponse {
        throw IncomingContactTestError.unexpectedCall
    }

    func declineContactRequest(requestID _: String) async throws -> ContactRequestResponse {
        throw IncomingContactTestError.unexpectedCall
    }

    func recordedOffsets() -> [Int] {
        offsets
    }
}

private actor SuspendingIncomingMutationClient: IncomingContactRequestsAPIClientProtocol {
    let initialRequest: ContactRequest
    let action: IncomingMutationAction
    let serverRequest: ContactRequest
    let shouldFail: Bool

    private var mutationStarted = false
    private var mutationWaiters: [CheckedContinuation<Void, Never>] = []
    private var mutationContinuation: CheckedContinuation<Void, Never>?

    init(
        initialRequest: ContactRequest,
        action: IncomingMutationAction,
        serverRequest: ContactRequest,
        shouldFail: Bool
    ) {
        self.initialRequest = initialRequest
        self.action = action
        self.serverRequest = serverRequest
        self.shouldFail = shouldFail
    }

    func fetchMyProfileClaims() async throws -> PlayerClaimsResponse {
        PlayerClaimsResponse(claims: [makeClaim(status: .approved)])
    }

    func fetchIncomingContactRequests(
        limit: Int,
        offset: Int
    ) async throws -> ContactRequestsResponse {
        ContactRequestsResponse(
            requests: offset == 0 ? [initialRequest] : [],
            box: .inbox,
            total: 1,
            limit: limit,
            offset: offset
        )
    }

    func acceptContactRequest(requestID _: String) async throws -> ContactRequestResponse {
        guard action == .accept else { throw IncomingContactTestError.unexpectedCall }
        return try await completeMutation()
    }

    func declineContactRequest(requestID _: String) async throws -> ContactRequestResponse {
        guard action == .decline else { throw IncomingContactTestError.unexpectedCall }
        return try await completeMutation()
    }

    func waitUntilMutationStarts() async {
        if mutationStarted { return }
        await withCheckedContinuation { continuation in
            mutationWaiters.append(continuation)
        }
    }

    func releaseMutation() {
        mutationContinuation?.resume()
        mutationContinuation = nil
    }

    private func completeMutation() async throws -> ContactRequestResponse {
        await withCheckedContinuation { continuation in
            mutationContinuation = continuation
            mutationStarted = true
            mutationWaiters.forEach { $0.resume() }
            mutationWaiters = []
        }
        if shouldFail {
            throw APIClientError.server(
                statusCode: 500,
                message: "The response could not be saved."
            )
        }
        return ContactRequestResponse(contactRequest: serverRequest)
    }
}

private actor FailingIncomingLoadClient: IncomingContactRequestsAPIClientProtocol {
    let claims: PlayerClaimsResponse
    let error: APIClientError

    init(claims: PlayerClaimsResponse, error: APIClientError) {
        self.claims = claims
        self.error = error
    }

    func fetchMyProfileClaims() async throws -> PlayerClaimsResponse {
        claims
    }

    func fetchIncomingContactRequests(
        limit _: Int,
        offset _: Int
    ) async throws -> ContactRequestsResponse {
        throw error
    }

    func acceptContactRequest(requestID _: String) async throws -> ContactRequestResponse {
        throw IncomingContactTestError.unexpectedCall
    }

    func declineContactRequest(requestID _: String) async throws -> ContactRequestResponse {
        throw IncomingContactTestError.unexpectedCall
    }
}

private enum IncomingContactTestError: Error {
    case unexpectedCall
}

private func makeRequest(
    id: String = "451f1c56-a815-4cb3-9f9b-f5978480ef04",
    status: ContactRequestStatus = .pending,
    respondedAt: String? = nil,
    routing: ContactRoutingMode = .direct, consent: ClubConsentStatus? = nil
) -> ContactRequest {
    ContactRequest(
        id: id,
        playerApiId: 403_064,
        message: "I’d like to discuss your development pathway.",
        status: status,
        routingMode: routing, clubConsentStatus: consent,
        createdAt: "2026-07-16T14:05:00",
        respondedAt: respondedAt,
        expiresAt: "2026-07-30T14:05:00",
        participants: ContactRequestParticipants(
            scout: ContactRequestParticipant(displayName: "Alex Scout"),
            player: ContactRequestParticipant(displayName: "Test Player")
        ),
        latestOutcome: nil
    )
}

private func makeClaim(
    status: PlayerProfileClaimStatus,
    relationshipType: String = "player"
) -> PlayerProfileClaim {
    PlayerProfileClaim(
        id: status == .approved ? 1 : 2,
        playerApiId: 403_064,
        userAccountId: 44,
        relationshipType: relationshipType,
        status: status,
        message: nil,
        reviewedBy: status == .approved ? "admin@example.com" : nil,
        reviewedAt: status == .approved ? "2026-07-15T03:00:00+00:00" : nil,
        createdAt: "2026-07-14T03:00:00+00:00",
        playerName: "Test Player"
    )
}
