import Combine
import Foundation

@MainActor
final class PlayerClaimViewModel: ObservableObject {
    let playerID: Int

    @Published private(set) var claim: PlayerProfileClaim?
    @Published private(set) var ownerShowcaseProfile: ShowcaseProfile?
    @Published private(set) var isLoading = false
    @Published private(set) var isSubmitting = false
    @Published private(set) var isLoadingOwnerProfile = false
    @Published private(set) var isSavingOwnerAttestation = false
    @Published private(set) var hasLoaded = false
    @Published private(set) var hasLoadedOwnerProfile = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var ownerProfileErrorMessage: String?

    private let apiClient: any PlayerClaimAPIClientProtocol
    private let showcaseAPIClient: (any ShowcaseAPIClientProtocol)?
    private var revision = 0

    init(
        playerID: Int,
        apiClient: any PlayerClaimAPIClientProtocol = APIClient(),
        showcaseAPIClient: (any ShowcaseAPIClientProtocol)? = nil
    ) {
        self.playerID = playerID
        self.apiClient = apiClient
        self.showcaseAPIClient = showcaseAPIClient
            ?? (apiClient as? any ShowcaseAPIClientProtocol)

        #if DEBUG
        if FullCircleFixtureDestination.fromLaunchArguments(
            ProcessInfo.processInfo.arguments
        ) == .watchingYou {
            claim = PlayerProfileClaim(
                id: 77,
                playerApiId: playerID,
                userAccountId: 91,
                relationshipType: "player",
                status: .approved,
                message: nil,
                contractStatus: .contracted,
                currentClubName: "Manchester United",
                clubProgramId: nil,
                statusContradiction: false,
                reviewedBy: "fixture-admin",
                reviewedAt: "2026-07-15T11:00:00",
                createdAt: "2026-07-14T09:00:00",
                playerName: "Habeeb Amass"
            )
            hasLoaded = true
        }
        #endif
    }

    var isApprovedPlayerOwner: Bool {
        claim?.status == .approved && claim?.relationshipType == "player"
    }

    var currentOwnerAttestation: PlayerContractAttestation? {
        guard isApprovedPlayerOwner, let claim else { return nil }
        return ownerShowcaseProfile?.contractAttestation ?? claim.contractAttestation
    }

    var currentAttestationReviewStatus: PlayerContractAttestationReviewStatus? {
        guard isApprovedPlayerOwner else { return nil }
        if ownerShowcaseProfile?.contractAttestation != nil {
            return ownerShowcaseProfile?.contractAttestationReviewStatus ?? .approved
        }
        return .approved
    }

    var canEditOwnerAttestation: Bool {
        isApprovedPlayerOwner
            && showcaseAPIClient != nil
            && hasLoadedOwnerProfile
            && !isLoadingOwnerProfile
            && !isSavingOwnerAttestation
    }

    func load(isAuthenticated: Bool) async {
        guard isAuthenticated else {
            resetForSignOut()
            return
        }
        #if DEBUG
        if FullCircleFixtureDestination.fromLaunchArguments(
            ProcessInfo.processInfo.arguments
        ) == .watchingYou {
            return
        }
        #endif
        guard !isLoading,
              !isSubmitting,
              !isLoadingOwnerProfile,
              !isSavingOwnerAttestation
        else { return }

        revision += 1
        let requestRevision = revision
        isLoading = true
        errorMessage = nil

        do {
            let response = try await apiClient.fetchMyProfileClaims()
            guard requestRevision == revision else { return }
            guard !Task.isCancelled else {
                isLoading = false
                return
            }
            claim = response.claims.first { $0.playerApiId == playerID }
            hasLoaded = true
            isLoading = false

            if isApprovedPlayerOwner {
                await loadOwnerProfile(revision: requestRevision)
            } else {
                clearOwnerProfile()
            }
        } catch {
            guard requestRevision == revision else { return }
            isLoading = false
            if error is CancellationError || (error as? URLError)?.code == .cancelled {
                return
            }
            hasLoaded = true
            errorMessage = error.localizedDescription
        }
    }

    @discardableResult
    func submitThisIsMe(attestation: PlayerContractAttestation) async -> Bool {
        guard !isSubmitting, !isLoading else { return false }

        revision += 1
        let requestRevision = revision
        isSubmitting = true
        errorMessage = nil

        do {
            let response = try await apiClient.submitPlayerClaim(
                playerID: playerID,
                attestation: attestation
            )
            guard requestRevision == revision else { return false }
            guard !Task.isCancelled else {
                isSubmitting = false
                return false
            }
            claim = response.claim
            hasLoaded = true
            isSubmitting = false

            if isApprovedPlayerOwner {
                await loadOwnerProfile(revision: requestRevision)
            } else {
                clearOwnerProfile()
            }
            return true
        } catch {
            guard requestRevision == revision else { return false }
            isSubmitting = false
            if error is CancellationError || (error as? URLError)?.code == .cancelled {
                return false
            }
            errorMessage = error.localizedDescription
            return false
        }
    }

    @discardableResult
    func updateOwnerAttestation(_ attestation: PlayerContractAttestation) async -> Bool {
        guard isApprovedPlayerOwner else {
            ownerProfileErrorMessage = "Only an approved player owner can update this attestation."
            return false
        }
        guard let showcaseAPIClient else {
            ownerProfileErrorMessage = "Profile editing is not available right now."
            return false
        }
        guard hasLoadedOwnerProfile else {
            ownerProfileErrorMessage = "Load the current owner profile before editing its attestation."
            return false
        }
        guard !isSavingOwnerAttestation, !isLoadingOwnerProfile else { return false }

        revision += 1
        let requestRevision = revision
        isSavingOwnerAttestation = true
        ownerProfileErrorMessage = nil

        do {
            let response = try await showcaseAPIClient.updateOwnerShowcaseProfile(
                playerID: playerID,
                profile: ownerShowcaseProfile,
                attestation: attestation
            )
            guard requestRevision == revision else { return false }
            guard !Task.isCancelled else {
                isSavingOwnerAttestation = false
                return false
            }
            ownerShowcaseProfile = response.profile
            hasLoadedOwnerProfile = true
            isSavingOwnerAttestation = false
            return true
        } catch {
            guard requestRevision == revision else { return false }
            isSavingOwnerAttestation = false
            if error is CancellationError || (error as? URLError)?.code == .cancelled {
                return false
            }
            ownerProfileErrorMessage = error.localizedDescription
            return false
        }
    }

    func reloadOwnerProfile() async {
        guard isApprovedPlayerOwner, !isLoadingOwnerProfile, !isSavingOwnerAttestation else { return }
        revision += 1
        await loadOwnerProfile(revision: revision)
    }

    func clearClaimError() {
        errorMessage = nil
    }

    func clearOwnerProfileError() {
        ownerProfileErrorMessage = nil
    }

    private func loadOwnerProfile(revision requestRevision: Int) async {
        guard let showcaseAPIClient else {
            hasLoadedOwnerProfile = false
            return
        }

        isLoadingOwnerProfile = true
        ownerProfileErrorMessage = nil
        do {
            let response = try await showcaseAPIClient.fetchPlayerShowcase(playerID: playerID)
            guard requestRevision == revision else { return }
            guard !Task.isCancelled else {
                isLoadingOwnerProfile = false
                return
            }
            ownerShowcaseProfile = response.profile
            hasLoadedOwnerProfile = true
            isLoadingOwnerProfile = false
        } catch {
            guard requestRevision == revision else { return }
            isLoadingOwnerProfile = false
            if error is CancellationError || (error as? URLError)?.code == .cancelled {
                return
            }
            hasLoadedOwnerProfile = false
            ownerProfileErrorMessage = error.localizedDescription
        }
    }

    private func clearOwnerProfile() {
        ownerShowcaseProfile = nil
        isLoadingOwnerProfile = false
        isSavingOwnerAttestation = false
        hasLoadedOwnerProfile = false
        ownerProfileErrorMessage = nil
    }

    private func resetForSignOut() {
        revision += 1
        claim = nil
        isLoading = false
        isSubmitting = false
        hasLoaded = false
        errorMessage = nil
        clearOwnerProfile()
    }
}
