import Combine
import Foundation

@MainActor
final class SentContactRequestsViewModel: ObservableObject {
    @Published private(set) var requests: [ContactRequest] = []
    @Published private(set) var isLoading = false
    @Published private(set) var isLoadingMore = false
    @Published private(set) var hasLoaded = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var withdrawingRequestIDs: Set<String> = []
    @Published private(set) var isFixturePreview = false

    private let apiClient: any SentContactRequestsAPIClientProtocol
    private let availability: ContactFeatureAvailability
    private let pageSize: Int
    private var total = 0
    private var loadRevision = 0
    private var mutationRevision = 0
    private var activeLoadTask: Task<Void, Never>?
    private var activePaginationTask: Task<Void, Never>?
    private var withdrawalRevisions: [String: Int] = [:]

    init(
        apiClient: any SentContactRequestsAPIClientProtocol,
        availability: ContactFeatureAvailability,
        pageSize: Int = 30
    ) {
        self.apiClient = apiClient
        self.availability = availability
        self.pageSize = pageSize

        #if DEBUG
        let fixture = FullCircleFixtureDestination.fromLaunchArguments(ProcessInfo.processInfo.arguments)
        if fixture == .inbox || fixture == .thread || fixture == .messageReport,
           let response = Self.decodeFixture() {
            requests = response.requests
            total = response.total
            hasLoaded = true
            isFixturePreview = true
            availability.recordSuccess()
        }
        #endif
    }

    var canLoadMore: Bool {
        requests.count < total && !isLoading && !isLoadingMore
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

    func withdraw(_ request: ContactRequest) async {
        guard request.status == .pending,
              !withdrawingRequestIDs.contains(request.id),
              let index = requests.firstIndex(where: { $0.id == request.id })
        else { return }

        mutationRevision += 1
        let revision = mutationRevision
        withdrawalRevisions[request.id] = revision
        let original = requests[index]
        requests[index] = original.replacing(status: .withdrawn)
        withdrawingRequestIDs.insert(request.id)
        errorMessage = nil

        defer {
            finishWithdrawal(requestID: request.id, revision: revision)
        }

        do {
            let response = try await apiClient.withdrawContactRequest(requestID: request.id)
            guard withdrawalRevisions[request.id] == revision else { return }
            availability.recordSuccess()
            if let currentIndex = requests.firstIndex(where: { $0.id == request.id }) {
                requests[currentIndex] = response.contactRequest
            }
        } catch {
            guard withdrawalRevisions[request.id] == revision else { return }
            if Self.isCancellation(error) {
                if let currentIndex = requests.firstIndex(where: { $0.id == request.id }),
                   requests[currentIndex].status == .withdrawn {
                    requests[currentIndex] = original
                }
                errorMessage = nil
            } else if availability.recordFailure(error) {
                requests = []
                errorMessage = nil
            } else if let currentIndex = requests.firstIndex(where: { $0.id == request.id }),
                      requests[currentIndex].status == .withdrawn {
                requests[currentIndex] = original
                errorMessage = Self.displayMessage(for: error)
            }
        }
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
        withdrawingRequestIDs = []
        withdrawalRevisions = [:]
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
            let response = try await apiClient.fetchSentContactRequests(limit: pageSize, offset: 0)
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
            let response = try await apiClient.fetchSentContactRequests(limit: pageSize, offset: offset)
            guard revision == loadRevision, offset == requests.count, !Task.isCancelled else { return }
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

    private func finishWithdrawal(requestID: String, revision: Int) {
        guard withdrawalRevisions[requestID] == revision else { return }
        withdrawalRevisions[requestID] = nil
        withdrawingRequestIDs.remove(requestID)
    }

    private static func isCancellation(_ error: Error) -> Bool {
        error is CancellationError || (error as? URLError)?.code == .cancelled
    }

    private static func displayMessage(for error: Error) -> String {
        if let apiError = error as? APIClientError, apiError.statusCode == 429 {
            return "You’ve reached the current request limit. Please try again later."
        }
        return error.localizedDescription
    }

    #if DEBUG
    private static func decodeFixture() -> ContactRequestsResponse? {
        let payload = #"""
        {
          "requests": [
            {
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
            {
              "id": "451f1c56-a815-4cb3-9f9b-f5978480ef04",
              "player_api_id": 700002,
              "message": "Could we arrange an introductory call about our U23 programme?",
              "status": "pending",
              "created_at": "2026-07-16T14:05:00",
              "responded_at": null,
              "expires_at": "2026-07-30T14:05:00",
              "participants": {
                "scout": {"display_name": "Alex Scout"},
                "player": {"display_name": "Mateo Silva"}
              },
              "latest_outcome": null
            },
            {
              "id": "b7ac28b0-4189-4471-8fd5-7d4851358947",
              "player_api_id": 700003,
              "message": "Our recruitment team would value a confidential conversation.",
              "status": "declined",
              "created_at": "2026-07-08T09:00:00",
              "responded_at": "2026-07-09T17:45:00",
              "expires_at": "2026-07-22T09:00:00",
              "participants": {
                "scout": {"display_name": "Alex Scout"},
                "player": {"display_name": "Noah Williams"}
              },
              "latest_outcome": null
            },
            {
              "id": "cfe124af-87c0-4b6f-8e27-cb58a6d5e80d",
              "player_api_id": 700004,
              "message": "Introduction request for our academy transition programme.",
              "status": "expired",
              "created_at": "2026-06-20T10:00:00",
              "responded_at": null,
              "expires_at": "2026-07-04T10:00:00",
              "participants": {
                "scout": {"display_name": "Alex Scout"},
                "player": {"display_name": "Ethan Cole"}
              },
              "latest_outcome": null
            }
          ],
          "box": "sent",
          "total": 4,
          "limit": 30,
          "offset": 0
        }
        """#
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(ContactRequestsResponse.self, from: Data(payload.utf8))
    }
    #endif
}
