import Combine
import Foundation

enum LocalPlayerFormContext: Equatable, Sendable {
    case claimant
    case scoutAdd
}

enum LocalPlayerFormField: Hashable, Sendable {
    case displayName
    case birthYear
    case position
    case clubName
    case country
    case city
}

@MainActor
final class LocalPlayerFormViewModel: ObservableObject {
    @Published var displayName = ""
    @Published var relationship: LocalPlayerRelationship = .player
    @Published var position = ""
    @Published var clubName = ""
    @Published var country = ""
    @Published var city = ""
    @Published var birthYear = ""
    @Published private(set) var fieldErrors: [LocalPlayerFormField: String] = [:]
    @Published private(set) var requestError: String?
    @Published private(set) var isSubmitting = false
    @Published private(set) var created: LocalPlayerCreateResponse?

    let context: LocalPlayerFormContext
    private let apiClient: any OnboardingAPIClientProtocol

    init(
        context: LocalPlayerFormContext,
        apiClient: any OnboardingAPIClientProtocol = APIClient(),
        fixtureCreated: LocalPlayerCreateResponse? = nil
    ) {
        self.context = context
        self.apiClient = apiClient
        created = fixtureCreated
    }

    @discardableResult
    func validate() -> Bool {
        var errors: [LocalPlayerFormField: String] = [:]
        let name = trimmed(displayName)
        if name.count < 2 {
            errors[.displayName] = "Enter at least 2 characters."
        } else if name.count > 200 {
            errors[.displayName] = "Use 200 characters or fewer."
        }
        validateMaximum(position, maximum: 50, field: .position, errors: &errors)
        validateMaximum(clubName, maximum: 200, field: .clubName, errors: &errors)
        validateMaximum(country, maximum: 100, field: .country, errors: &errors)
        validateMaximum(city, maximum: 120, field: .city, errors: &errors)

        let yearText = trimmed(birthYear)
        if !yearText.isEmpty {
            if yearText.allSatisfy(\.isNumber), let year = Int(yearText) {
                if !(1950 ... 2020).contains(year) {
                    errors[.birthYear] = "Birth year must be between 1950 and 2020."
                }
            } else {
                errors[.birthYear] = "Enter a whole year, for example 2008."
            }
        }
        fieldErrors = errors
        return errors.isEmpty
    }

    func submit() async {
        guard !isSubmitting, validate() else { return }
        isSubmitting = true
        requestError = nil
        defer { isSubmitting = false }

        do {
            created = try await apiClient.createLocalPlayer(submission)
        } catch {
            requestError = displayMessage(for: error)
        }
    }

    var submission: LocalPlayerSubmission {
        LocalPlayerSubmission(
            displayName: trimmed(displayName),
            relationshipType: context == .claimant ? relationship : nil,
            position: optional(position),
            clubName: optional(clubName),
            country: optional(country),
            city: optional(city),
            birthYear: Int(trimmed(birthYear))
        )
    }

    func error(for field: LocalPlayerFormField) -> String? {
        fieldErrors[field]
    }

    private func validateMaximum(
        _ value: String,
        maximum: Int,
        field: LocalPlayerFormField,
        errors: inout [LocalPlayerFormField: String]
    ) {
        if trimmed(value).count > maximum {
            errors[field] = "Use \(maximum) characters or fewer."
        }
    }

    private func optional(_ value: String) -> String? {
        let value = trimmed(value)
        return value.isEmpty ? nil : value
    }

    private func trimmed(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func displayMessage(for error: Error) -> String {
        (error as? LocalizedError)?.errorDescription
            ?? "We couldn't submit this profile. Check your connection and try again."
    }
}

@MainActor
final class PlayerSelfSearchViewModel: ObservableObject {
    @Published var query = ""
    @Published private(set) var players: [ScoutPlayerSummary]
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var hasSearched: Bool

    private let apiClient: any ScoutAPIClientProtocol

    init(
        apiClient: any ScoutAPIClientProtocol = APIClient(),
        fixtureQuery: String = "",
        fixturePlayers: [ScoutPlayerSummary] = []
    ) {
        self.apiClient = apiClient
        query = fixtureQuery
        players = fixturePlayers
        hasSearched = !fixturePlayers.isEmpty
    }

    func search() async {
        let query = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard query.count >= 2, !isLoading else {
            errorMessage = query.count < 2 ? "Enter at least 2 characters." : nil
            return
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let response = try await apiClient.fetchScoutPlayers(
                ScoutPlayersRequest(
                    page: 1,
                    perPage: 20,
                    search: query,
                    position: nil,
                    status: nil,
                    maximumAge: nil,
                    sort: "name",
                    order: .ascending
                )
            )
            players = response.players
            hasSearched = true
        } catch {
            players = []
            hasSearched = true
            errorMessage = (error as? LocalizedError)?.errorDescription
                ?? "We couldn't search tracked players."
        }
    }
}

struct WorldwideFollowConfirmation: Equatable, Sendable {
    let playerName: String
    let listName: String
    let shadowCreated: Bool
}

@MainActor
final class WorldwidePlayerSearchViewModel: ObservableObject {
    @Published var query = ""
    @Published private(set) var players: [WorldwidePlayer]
    @Published private(set) var isSearching = false
    @Published private(set) var pendingPlayerID: Int?
    @Published private(set) var errorMessage: String?
    @Published private(set) var confirmation: WorldwideFollowConfirmation?
    @Published private(set) var hasSearched: Bool

    private let apiClient: any OnboardingAPIClientProtocol

    init(
        apiClient: any OnboardingAPIClientProtocol = APIClient(),
        fixtureQuery: String = "",
        fixturePlayers: [WorldwidePlayer] = [],
        fixtureConfirmation: WorldwideFollowConfirmation? = nil
    ) {
        self.apiClient = apiClient
        query = fixtureQuery
        players = fixturePlayers
        confirmation = fixtureConfirmation
        hasSearched = !fixturePlayers.isEmpty
    }

    func search() async {
        let query = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard query.count >= 3, !isSearching else {
            errorMessage = query.count < 3 ? "Type at least 3 characters to search worldwide." : nil
            return
        }
        isSearching = true
        errorMessage = nil
        confirmation = nil
        defer { isSearching = false }
        do {
            players = try await apiClient.searchWorldwidePlayers(query: query).players
            hasSearched = true
        } catch {
            players = []
            hasSearched = true
            errorMessage = displayMessage(for: error)
        }
    }

    func add(_ player: WorldwidePlayer, to list: FollowList) async -> Bool {
        guard !list.isDefault, pendingPlayerID == nil else { return false }
        pendingPlayerID = player.playerApiId
        errorMessage = nil
        confirmation = nil
        defer { pendingPlayerID = nil }
        do {
            let response = try await apiClient.addWorldwidePlayerFollow(
                listID: list.id,
                player: player
            )
            confirmation = WorldwideFollowConfirmation(
                playerName: player.name,
                listName: list.name,
                shadowCreated: response.shadowCreated
            )
            return true
        } catch {
            errorMessage = displayMessage(for: error)
            return false
        }
    }

    func clearConfirmation() {
        confirmation = nil
    }

    private func displayMessage(for error: Error) -> String {
        (error as? LocalizedError)?.errorDescription
            ?? "We couldn't update this list. Check your connection and try again."
    }
}

enum ClubClaimFormField: Hashable, Sendable {
    case club
    case roleTitle
    case message
    case proofURL
}

@MainActor
final class ClubClaimViewModel: ObservableObject {
    @Published var searchQuery = ""
    @Published var roleTitle = ""
    @Published var message = ""
    @Published private(set) var selectedClub: ClubClaimSubject?
    @Published private(set) var searchResults = ClubSearchResponse(apiTeams: [], localClubs: [])
    @Published private(set) var claims: [ClubClaim]
    @Published private(set) var fieldErrors: [ClubClaimFormField: String] = [:]
    @Published private(set) var errorMessage: String?
    @Published private(set) var isLoading = false
    @Published private(set) var isSearching = false
    @Published private(set) var isSubmitting = false
    @Published private(set) var verifyingClaimID: Int?
    @Published private(set) var submittedClaim: ClubClaim?

    private let apiClient: any OnboardingAPIClientProtocol

    init(
        apiClient: any OnboardingAPIClientProtocol = APIClient(),
        fixtureClaims: [ClubClaim] = [],
        fixtureSelection: ClubClaimSubject? = nil
    ) {
        self.apiClient = apiClient
        claims = fixtureClaims
        selectedClub = fixtureSelection
    }

    func load() async {
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            claims = try await apiClient.fetchMyClubClaims().claims
        } catch {
            errorMessage = displayMessage(for: error)
        }
    }

    func searchClubs() async {
        let query = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard query.count >= 2, !isSearching else {
            fieldErrors[.club] = query.count < 2 ? "Enter at least 2 characters." : nil
            return
        }
        isSearching = true
        errorMessage = nil
        fieldErrors[.club] = nil
        defer { isSearching = false }
        do {
            searchResults = try await apiClient.searchClubs(query: query)
        } catch {
            searchResults = ClubSearchResponse(apiTeams: [], localClubs: [])
            errorMessage = displayMessage(for: error)
        }
    }

    func select(_ club: ClubClaimSubject) {
        selectedClub = club
        fieldErrors[.club] = nil
    }

    @discardableResult
    func validateClaim() -> Bool {
        var errors: [ClubClaimFormField: String] = [:]
        if selectedClub == nil { errors[.club] = "Select a club from the search results." }
        let role = roleTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        if role.count < 2 {
            errors[.roleTitle] = "Enter a role title of at least 2 characters."
        } else if role.count > 100 {
            errors[.roleTitle] = "Use 100 characters or fewer."
        }
        if message.trimmingCharacters(in: .whitespacesAndNewlines).count > 1_000 {
            errors[.message] = "Use 1,000 characters or fewer."
        }
        fieldErrors = errors
        return errors.isEmpty
    }

    func submit() async {
        guard !isSubmitting, validateClaim(), let selectedClub else { return }
        isSubmitting = true
        errorMessage = nil
        defer { isSubmitting = false }
        do {
            let trimmedMessage = message.trimmingCharacters(in: .whitespacesAndNewlines)
            let response = try await apiClient.submitClubClaim(
                ClubClaimSubmission(
                    subject: selectedClub,
                    roleTitle: roleTitle.trimmingCharacters(in: .whitespacesAndNewlines),
                    message: trimmedMessage.isEmpty ? nil : trimmedMessage
                )
            )
            submittedClaim = response.claim
            claims.insert(response.claim, at: 0)
        } catch {
            errorMessage = displayMessage(for: error)
        }
    }

    func verify(_ claim: ClubClaim, proofURL: String) async -> Bool {
        let proofURL = proofURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard verifyingClaimID == nil else { return false }
        guard let url = URL(string: proofURL), url.scheme?.lowercased() == "https" else {
            fieldErrors[.proofURL] = "Enter a public HTTPS proof URL."
            return false
        }
        guard proofURL.count <= 500 else {
            fieldErrors[.proofURL] = "Use 500 characters or fewer."
            return false
        }
        verifyingClaimID = claim.id
        fieldErrors[.proofURL] = nil
        errorMessage = nil
        defer { verifyingClaimID = nil }
        do {
            let updated = try await apiClient.verifyClubClaim(id: claim.id, proofURL: proofURL).claim
            if let index = claims.firstIndex(where: { $0.id == claim.id }) {
                claims[index] = updated
            }
            return true
        } catch {
            errorMessage = displayMessage(for: error)
            return false
        }
    }

    func error(for field: ClubClaimFormField) -> String? {
        fieldErrors[field]
    }

    private func displayMessage(for error: Error) -> String {
        (error as? LocalizedError)?.errorDescription
            ?? "We couldn't update your club claim. Check your connection and try again."
    }
}
