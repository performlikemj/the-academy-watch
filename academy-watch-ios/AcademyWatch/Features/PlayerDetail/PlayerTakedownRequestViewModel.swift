import Combine
import Foundation

enum TakedownRequesterRole: String, CaseIterable, Encodable, Identifiable, Sendable {
    case player
    case guardian
    case club
    case other

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .player: return "The player"
        case .guardian: return "Parent or guardian"
        case .club: return "Club representative"
        case .other: return "Other authorized representative"
        }
    }
}

enum PlayerTakedownSubmissionState: Equatable, Sendable {
    case idle
    case submitting
    case received
    case failed
}

@MainActor
final class PlayerTakedownRequestViewModel: ObservableObject {
    static let confirmationMessage = "Request received. We review every removal request."
    static let genericErrorMessage = "We couldn’t send your request. Please check your connection and try again."

    @Published var requesterRole: TakedownRequesterRole = .player
    @Published var contactEmail = ""
    @Published var statement = ""
    @Published private(set) var state: PlayerTakedownSubmissionState = .idle

    private let playerID: Int
    private let apiClient: any PlayerTakedownAPIClientProtocol

    init(playerID: Int, apiClient: any PlayerTakedownAPIClientProtocol) {
        self.playerID = playerID
        self.apiClient = apiClient
    }

    var canSubmit: Bool {
        state != .submitting
            && !contactEmail.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !statement.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    func submit() async {
        guard canSubmit else { return }

        state = .submitting
        do {
            try await apiClient.submitPlayerTakedownRequest(
                playerID: playerID,
                requesterRole: requesterRole,
                contactEmail: contactEmail.trimmingCharacters(in: .whitespacesAndNewlines),
                statement: statement.trimmingCharacters(in: .whitespacesAndNewlines)
            )
            guard !Task.isCancelled else { return }
            state = .received
        } catch {
            guard !Task.isCancelled else { return }
            state = .failed
        }
    }
}
