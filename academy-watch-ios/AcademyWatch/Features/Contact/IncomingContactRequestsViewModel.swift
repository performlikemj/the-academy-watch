import Combine
import Foundation

@MainActor
final class IncomingContactRequestsViewModel: ObservableObject {
    @Published private(set) var requests: [ContactRequest] = []
    @Published private(set) var isLoading = false
    @Published private(set) var isLoadingMore = false
    @Published private(set) var hasLoaded = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var respondingRequestIDs: Set<String> = []
    @Published private(set) var ownsApprovedPlayerClaim = false
    @Published private(set) var isFixturePreview = false

    private let apiClient: any IncomingContactRequestsAPIClientProtocol
    private let availability: ContactFeatureAvailability
    private let pageSize: Int
    private var total = 0
    private var loadRevision = 0
    private var mutationRevision = 0
    private var activeLoadTask: Task<Void, Never>?
    private var activePaginationTask: Task<Void, Never>?
    private var responseRevisions: [String: Int] = [:]

    init(
        apiClient: any IncomingContactRequestsAPIClientProtocol,
        availability: ContactFeatureAvailability,
        pageSize: Int = 30
    ) {
        self.apiClient = apiClient
        self.availability = availability
        self.pageSize = pageSize

        #if DEBUG
        let destination = FullCircleFixtureDestination.fromLaunchArguments(
            ProcessInfo.processInfo.arguments
        )
        if destination == .playerInbox || destination == .declineConfirmation,
           let response = Self.decodeFixture() {
            requests = response.requests
            total = response.total
            ownsApprovedPlayerClaim = true
            hasLoaded = true
            isFixturePreview = true
            availability.recordSuccess()
        }
        #endif
    }

    var canLoadMore: Bool {
        ownsApprovedPlayerClaim
            && requests.count < total
            && !isLoading
            && !isLoadingMore
            && !availability.isUnavailable
    }

    func loadIfNeeded() async {
        guard !hasLoaded, !isFixturePreview, !availability.isUnavailable else { return }
        await reload()
    }

    func reload() async {
        guard !isFixturePreview, !availability.isUnavailable else { return }

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
        if revision == loadRevision {
            activeLoadTask = nil
        }
    }

    func loadNextPage() async {
        guard canLoadMore, activePaginationTask == nil, !isFixturePreview else { return }
        let revision = loadRevision
        let offset = requests.count
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

    func accept(_ request: ContactRequest) async {
        await respond(to: request, with: .accepted)
    }

    func decline(_ request: ContactRequest) async {
        await respond(to: request, with: .declined)
    }

    func resetForSignOut() {
        loadRevision += 1
        activeLoadTask?.cancel()
        activePaginationTask?.cancel()
        activeLoadTask = nil
        activePaginationTask = nil
        requests = []
        total = 0
        isLoading = false
        isLoadingMore = false
        hasLoaded = false
        errorMessage = nil
        respondingRequestIDs = []
        responseRevisions = [:]
        ownsApprovedPlayerClaim = false
    }

    private func performFullLoad(revision: Int) async {
        isLoading = true
        errorMessage = nil
        defer {
            if revision == loadRevision {
                isLoading = false
            }
        }

        let claims: PlayerClaimsResponse
        do {
            claims = try await apiClient.fetchMyProfileClaims()
        } catch {
            guard revision == loadRevision, !Self.isCancellation(error) else { return }
            // `/me/claims` predates and is independent of the contact feature
            // flag. Its failures must never poison the sticky rail signal.
            hasLoaded = true
            errorMessage = Self.displayMessage(for: error)
            return
        }

        guard revision == loadRevision, !Task.isCancelled else { return }
        let isOwner = claims.claims.contains {
            $0.relationshipType == "player" && $0.status == .approved
        }
        ownsApprovedPlayerClaim = isOwner

        guard isOwner else {
            requests = []
            total = 0
            hasLoaded = true
            return
        }

        do {
            let response = try await apiClient.fetchIncomingContactRequests(
                limit: pageSize,
                offset: 0
            )
            guard revision == loadRevision, !Task.isCancelled else { return }
            availability.recordSuccess()
            requests = response.requests
            total = response.total
            hasLoaded = true
        } catch {
            guard revision == loadRevision else { return }
            guard !Self.isCancellation(error) else { return }
            hasLoaded = true
            if availability.recordFailure(error) {
                requests = []
                total = 0
                errorMessage = nil
            } else {
                errorMessage = Self.displayMessage(for: error)
            }
        }
    }

    private func performPagination(revision: Int, offset: Int) async {
        do {
            let response = try await apiClient.fetchIncomingContactRequests(
                limit: pageSize,
                offset: offset
            )
            guard revision == loadRevision,
                  offset == requests.count,
                  !Task.isCancelled
            else { return }

            availability.recordSuccess()
            let knownIDs = Set(requests.map(\.id))
            requests.append(contentsOf: response.requests.filter { !knownIDs.contains($0.id) })
            total = response.total
        } catch {
            guard revision == loadRevision, !Self.isCancellation(error) else { return }
            if availability.recordFailure(error) {
                requests = []
                total = 0
                errorMessage = nil
            } else {
                errorMessage = Self.displayMessage(for: error)
            }
        }
    }

    private func respond(
        to request: ContactRequest,
        with optimisticStatus: ContactRequestStatus
    ) async {
        guard request.status == .pending,
              optimisticStatus == .accepted || optimisticStatus == .declined,
              !respondingRequestIDs.contains(request.id),
              let index = requests.firstIndex(where: { $0.id == request.id })
        else { return }

        mutationRevision += 1
        let revision = mutationRevision
        responseRevisions[request.id] = revision
        let original = requests[index]
        requests[index] = original.replacing(status: optimisticStatus)
        respondingRequestIDs.insert(request.id)
        errorMessage = nil

        defer {
            finishResponse(requestID: request.id, revision: revision)
        }

        #if DEBUG
        if isFixturePreview {
            availability.recordSuccess()
            return
        }
        #endif

        do {
            let response: ContactRequestResponse
            switch optimisticStatus {
            case .accepted:
                response = try await apiClient.acceptContactRequest(requestID: request.id)
            case .declined:
                response = try await apiClient.declineContactRequest(requestID: request.id)
            case .pending, .withdrawn, .expired:
                return
            }

            guard responseRevisions[request.id] == revision else { return }
            availability.recordSuccess()
            if let currentIndex = requests.firstIndex(where: { $0.id == request.id }) {
                requests[currentIndex] = response.contactRequest
            }
        } catch {
            guard responseRevisions[request.id] == revision else { return }
            if Self.isCancellation(error) {
                rollback(
                    requestID: request.id,
                    optimisticStatus: optimisticStatus,
                    original: original
                )
                errorMessage = nil
            } else if availability.recordFailure(error) {
                requests = []
                total = 0
                errorMessage = nil
            } else {
                rollback(
                    requestID: request.id,
                    optimisticStatus: optimisticStatus,
                    original: original
                )
                errorMessage = Self.displayMessage(for: error)
            }
        }
    }

    private func rollback(
        requestID: String,
        optimisticStatus: ContactRequestStatus,
        original: ContactRequest
    ) {
        guard let currentIndex = requests.firstIndex(where: { $0.id == requestID }),
              requests[currentIndex].status == optimisticStatus
        else { return }
        requests[currentIndex] = original
    }

    private func finishResponse(requestID: String, revision: Int) {
        guard responseRevisions[requestID] == revision else { return }
        responseRevisions[requestID] = nil
        respondingRequestIDs.remove(requestID)
    }

    private static func isCancellation(_ error: Error) -> Bool {
        error is CancellationError || (error as? URLError)?.code == .cancelled
    }

    private static func displayMessage(for error: Error) -> String {
        if let apiError = error as? APIClientError {
            switch apiError {
            case let .codedServer(_, _, code, _) where code == ContactRequestErrorCode.requestExpired.rawValue:
                return "This introduction has expired. Refresh to see its latest status."
            case .server(statusCode: 403, _), .codedServer(statusCode: 403, _, _, _):
                return "You no longer have permission to respond to this introduction."
            case .httpStatus(429), .server(statusCode: 429, _), .codedServer(statusCode: 429, _, _, _):
                return "Too many requests. Please wait and try again."
            default:
                break
            }
        }
        return error.localizedDescription
    }

    #if DEBUG
    private static func decodeFixture() -> ContactRequestsResponse? {
        // Shape copied from ContactRequest.to_dict() and the inbox list route.
        let payload = #"""
        {
          "requests": [
            {
              "id": "02020202-2222-4222-8222-020202020202",
              "player_api_id": 403064,
              "message": "Would you be open to a confidential conversation about next season?",
              "status": "pending",
              "created_at": "2026-07-16T14:00:00",
              "responded_at": null,
              "expires_at": "2026-07-30T14:00:00",
              "participants": {
                "scout": {"display_name": "Alex Morgan"},
                "player": {"display_name": "Habeeb Amass"}
              },
              "latest_outcome": null
            },
            {
              "id": "01010101-1111-4111-8111-010101010101",
              "player_api_id": 403064,
              "message": "I would value an introduction to discuss your development pathway.",
              "status": "accepted",
              "created_at": "2026-07-15T08:00:00",
              "responded_at": "2026-07-15T11:00:00",
              "expires_at": "2026-07-29T08:00:00",
              "participants": {
                "scout": {"display_name": "Northbank Scout"},
                "player": {"display_name": "Habeeb Amass"}
              },
              "latest_outcome": {
                "stage": "contacted",
                "notes": "Introduction accepted and first call arranged.",
                "occurred_at": "2026-07-15T11:45:00",
                "created_at": "2026-07-15T11:46:00"
              }
            }
          ],
          "box": "inbox",
          "total": 2,
          "limit": 50,
          "offset": 0
        }
        """#
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(ContactRequestsResponse.self, from: Data(payload.utf8))
    }
    #endif
}
