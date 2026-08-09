import Foundation
import XCTest
@testable import AcademyWatch

final class PlayerTakedownRequestViewModelTests: XCTestCase {
    @MainActor
    func testSubmitTransitionsThroughSubmittingToNeutralConfirmation() async {
        let client = DelayedTakedownClient()
        let viewModel = PlayerTakedownRequestViewModel(playerID: 403_064, apiClient: client)
        viewModel.requesterRole = .player
        viewModel.contactEmail = "  player@example.test  "
        viewModel.statement = "  Please remove my profile.  "

        let submission = Task { await viewModel.submit() }
        await client.waitUntilStarted()

        XCTAssertEqual(viewModel.state, .submitting)
        await client.release()
        await submission.value

        XCTAssertEqual(viewModel.state, .received)
        XCTAssertEqual(
            PlayerTakedownRequestViewModel.confirmationMessage,
            "Request received. We review every removal request."
        )
        let captured = await client.capturedSubmission()
        XCTAssertEqual(captured?.playerID, 403_064)
        XCTAssertEqual(captured?.requesterRole, .player)
        XCTAssertEqual(captured?.contactEmail, "player@example.test")
        XCTAssertEqual(captured?.statement, "Please remove my profile.")
    }

    @MainActor
    func testFailureUsesGenericRetryStateAndCanThenSucceed() async {
        let client = RetryTakedownClient()
        let viewModel = PlayerTakedownRequestViewModel(playerID: 700_003, apiClient: client)
        viewModel.requesterRole = .club
        viewModel.contactEmail = "club@example.test"
        viewModel.statement = "Authorized club removal request."

        await viewModel.submit()

        XCTAssertEqual(viewModel.state, .failed)
        XCTAssertEqual(
            PlayerTakedownRequestViewModel.genericErrorMessage,
            "We couldn’t send your request. Please check your connection and try again."
        )
        XCTAssertTrue(viewModel.canSubmit)

        await viewModel.submit()

        XCTAssertEqual(viewModel.state, .received)
        let attempts = await client.attemptCount()
        XCTAssertEqual(attempts, 2)
    }
}

private actor DelayedTakedownClient: PlayerTakedownAPIClientProtocol {
    private var submission: TakedownSubmission?
    private var didStart = false
    private var startWaiters: [CheckedContinuation<Void, Never>] = []
    private var releaseContinuation: CheckedContinuation<Void, Never>?

    func submitPlayerTakedownRequest(
        playerID: Int,
        requesterRole: TakedownRequesterRole,
        contactEmail: String,
        statement: String
    ) async throws {
        submission = TakedownSubmission(
            playerID: playerID,
            requesterRole: requesterRole,
            contactEmail: contactEmail,
            statement: statement
        )
        didStart = true
        startWaiters.forEach { $0.resume() }
        startWaiters = []
        await withCheckedContinuation { continuation in
            releaseContinuation = continuation
        }
    }

    func waitUntilStarted() async {
        guard !didStart else { return }
        await withCheckedContinuation { continuation in
            startWaiters.append(continuation)
        }
    }

    func release() {
        releaseContinuation?.resume()
        releaseContinuation = nil
    }

    func capturedSubmission() -> TakedownSubmission? { submission }
}

private actor RetryTakedownClient: PlayerTakedownAPIClientProtocol {
    private var attempts = 0

    func submitPlayerTakedownRequest(
        playerID _: Int,
        requesterRole _: TakedownRequesterRole,
        contactEmail _: String,
        statement _: String
    ) async throws {
        attempts += 1
        if attempts == 1 {
            throw URLError(.cannotConnectToHost)
        }
    }

    func attemptCount() -> Int { attempts }
}

private struct TakedownSubmission: Sendable {
    let playerID: Int
    let requesterRole: TakedownRequesterRole
    let contactEmail: String
    let statement: String
}
