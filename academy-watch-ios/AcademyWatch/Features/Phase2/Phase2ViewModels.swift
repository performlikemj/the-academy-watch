import Combine
import Foundation

@MainActor
final class Phase2Workspace: ObservableObject {
    private struct Snapshot {
        var flags = Phase2Flags()
        var clubs: [ClubMembership] = []
    }
    @Published private var snapshot = Snapshot()
    var flags: Phase2Flags { snapshot.flags }
    var clubs: [ClubMembership] { snapshot.clubs }
    @Published var selectedClubId: Int?
    @Published private(set) var error: String?
    @Published private(set) var isLoading = false
    private let client: any Phase2API
    private var generation = 0
    init(client: any Phase2API) { self.client = client }
    var selected: ClubMembership? { clubs.first { $0.id == selectedClubId } ?? clubs.first }
    var hasClubSurface: Bool { flags.staff || flags.opportunities || !clubs.isEmpty }
    func load(authenticated: Bool) async {
        generation += 1
        let request = generation
        isLoading = true
        error = nil
        // Revalidate in memory; keep the last confirmed tree and drafts while fetching.
        var next = snapshot
        var failure: String?
        do {
            async let features: Phase2FeatureResponse = client.read("features")
            async let opportunities: OpportunityFeatures = opportunityFlags()
            let (base, posts) = try await (features, opportunities)
            next.flags = Phase2Flags(
                directory: base.clubDirectory == true, opportunities: posts.opportunities,
                applications: posts.opportunities && posts.applications,
                staff: base.clubStaffAccess == true, contact: base.contactRail == true)
            guard request == generation, !Task.isCancelled else { return }
            snapshot = next
        } catch {
            failure = phase2ReadError(error)
        }
        // Public flags and private access are independent decisions. A refused
        // club never turns successfully fetched public features off.
        if failure == nil {
            if authenticated && (next.flags.staff || next.flags.opportunities) {
                do {
                    async let grants: ClubMembershipsResponse = next.flags.staff
                        ? client.read("me/club-access") : ClubMembershipsResponse(programs: [])
                    async let claims: Phase2ClubClaimsResponse = client.read("funding/claims/me")
                    let (memberships, ownClaims) = try await (grants, claims)
                    var resolved = memberships.programs
                    for claim in ownClaims.claims
                    where claim.status == "approved" && !resolved.contains(where: { $0.id == claim.program.id }) {
                        do {
                            let result: ClubAccessResponse = try await client.read("club/\(claim.program.id)/access/me")
                            resolved.append(ClubMembership(program: claim.program, access: result.access))
                        } catch {
                            if [403, 404].contains(phase2Status(error) ?? 0) {
                                next.clubs.removeAll { $0.id == claim.program.id }
                                continue
                            }
                            throw error
                        }
                    }
                    next.clubs = resolved
                } catch {
                    failure = phase2ReadError(error)
                    if [401, 403, 404].contains(phase2Status(error) ?? 0) { next.clubs = [] }
                }
            } else { next.clubs = [] }
        }
        guard request == generation, !Task.isCancelled else { return }
        if !authenticated { next.clubs = [] }
        snapshot = next
        if !clubs.contains(where: { $0.id == selectedClubId }) { selectedClubId = clubs.first?.id }
        error = failure
        isLoading = false
    }
    private func opportunityFlags() async throws -> OpportunityFeatures {
        do { return try await client.read("opportunities/features") } catch {
            if phase2Status(error) == 404 {
                return OpportunityFeatures(opportunities: false, applications: false)
            }
            throw error
        }
    }
    func reset(preservePublicFlags: Bool = false) {
        generation += 1
        snapshot = Snapshot(flags: preservePublicFlags ? snapshot.flags : Phase2Flags())
        selectedClubId = nil
        error = nil
        isLoading = false
    }
}

@MainActor
final class DirectoryViewModel: ObservableObject {
    @Published private(set) var clubs: [Phase2Club] = []
    @Published private(set) var error: String?
    @Published private(set) var isLoading = false
    @Published private(set) var total = 0
    @Published private(set) var hasMore = false
    @Published private(set) var page = 1
    private let client: any Phase2API
    private var generation = 0
    init(client: any Phase2API) { self.client = client }
    func search(_ filter: DirectorySearch, page: Int = 1) async {
        generation += 1
        let request = generation
        isLoading = true
        error = nil
        clubs = []
        hasMore = false
        var body = filter
        body.page = page
        if let q = body.q, q.trimmingCharacters(in: .whitespacesAndNewlines).count == 1 {
            error = "Enter at least two characters, or leave search empty."
            isLoading = false
            return
        }
        if body.lat == nil || body.lng == nil {
            body.lat = nil
            body.lng = nil
            body.radiusKm = nil
        }
        do {
            let response: ClubDirectoryResponse = try await client.write(
                "club-directory/search", body: body)
            guard request == generation, !Task.isCancelled else { return }
            clubs = response.clubs
            total = response.total
            hasMore = response.hasMore
            self.page = response.page
        } catch {
            guard request == generation, !Task.isCancelled else { return }
            self.error = phase2Error(error)
        }
        if request == generation { isLoading = false }
    }
}

@MainActor
final class OpportunitiesViewModel: ObservableObject {
    @Published private(set) var posts: [Phase2Opportunity] = []
    @Published private(set) var error: String?
    @Published private(set) var isLoading = false
    @Published private(set) var hasMore = false
    @Published private(set) var page = 1
    private let client: any Phase2API
    private var generation = 0
    init(client: any Phase2API) { self.client = client }
    func load(type: String = "", programId: Int? = nil, club: Bool = false, page: Int = 1) async {
        generation += 1
        let request = generation
        isLoading = true
        error = nil
        posts = []
        hasMore = false
        guard !club || programId != nil else {
            error = "Select a club to open recruiting."
            isLoading = false
            return
        }
        var query = [URLQueryItem(name: "page", value: String(page))]
        if !type.isEmpty { query.append(URLQueryItem(name: "type", value: type)) }
        if !club, let programId {
            query.append(URLQueryItem(name: "program_id", value: String(programId)))
        }
        do {
            let path = club ? "club/\(programId!)/opportunities" : "opportunities"
            let response: OpportunitiesResponse = try await client.read(path, query: query)
            guard request == generation, !Task.isCancelled else { return }
            posts = response.opportunities
            hasMore = response.hasMore
            self.page = response.page
        } catch {
            guard request == generation, !Task.isCancelled else { return }
            self.error = phase2Error(error)
        }
        if request == generation { isLoading = false }
    }
}

@MainActor
final class TrialDetailViewModel: ObservableObject {
    @Published private(set) var post: Phase2Opportunity?
    @Published private(set) var claims: [ApplicationClaim] = []
    @Published private(set) var sent: Phase2Application?
    @Published private(set) var isLoading = false
    @Published private(set) var isSending = false
    @Published private(set) var error: String?
    @Published var selectedClaimId: Int?
    @Published var position = ""
    @Published var currentClub = ""
    @Published var contactConsent = false
    private let client: any Phase2API
    private let clock: () -> Date
    private let id: String
    private var accountIdentity: String?
    private var accountGeneration = 0
    private var requestId = UUID().uuidString
    private var previousBody: ApplicationSubmission?
    private var generation = 0
    init(id: String, client: any Phase2API, now: @escaping () -> Date = { Phase2Time.now }) {
        self.id = id
        self.client = client
        self.clock = now
    }
    func setAccount(_ identity: String) {
        guard accountIdentity != identity else { return }
        accountIdentity = identity
        accountGeneration += 1
        generation += 1
        claims = []
        selectedClaimId = nil
        sent = nil
        position = ""
        currentClub = ""
        contactConsent = false
        previousBody = nil
        requestId = UUID().uuidString
        isSending = false
        error = nil
    }
    var canSend: Bool {
        !isSending && sent == nil && contactConsent
            && !position.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && claims.contains { $0.id == selectedClaimId } && post?.status == "published"
            && (Phase2Time.date(post?.closesAt).map { $0 > clock() } ?? false)
    }
    func load(authenticated: Bool, applications: Bool) async {
        generation += 1
        let request = generation
        isLoading = true
        error = nil
        claims = []
        post = nil
        do {
            let detail: OpportunityResponse = try await client.read("opportunities/\(id)")
            guard request == generation, !Task.isCancelled else { return }
            post = detail.opportunity
            if authenticated && applications {
                let result: ApplicationClaimsResponse = try await client.read("me/application-claims")
                guard request == generation, !Task.isCancelled else { return }
                claims = result.claims
                if !claims.contains(where: { $0.id == selectedClaimId }) {
                    selectedClaimId = claims.first?.id
                }
            }
        } catch {
            guard request == generation, !Task.isCancelled else { return }
            self.error = phase2ReadError(error)
        }
        if request == generation { isLoading = false }
    }
    func apply() async {
        guard canSend, let selectedClaimId else { return }
        // Keep the same key for a transport retry; edited terms get a fresh key.
        if let old = previousBody,
            old.claimId != selectedClaimId || old.position != position || old.currentClub != currentClub
        {
            requestId = UUID().uuidString
        }
        let body = ApplicationSubmission(
            claimId: selectedClaimId, position: position, currentClub: currentClub,
            contactConsent: contactConsent,
            clientRequestId: requestId)
        previousBody = body
        let account = accountGeneration
        isSending = true
        error = nil
        defer { if account == accountGeneration { isSending = false } }
        do {
            let response: ApplicationResponse = try await client.write(
                "opportunities/\(id)/applications", body: body)
            guard account == accountGeneration, !Task.isCancelled else { return }
            sent = response.application
        } catch { if account == accountGeneration { self.error = phase2Error(error) } }
    }
}

@MainActor
final class ApplicationsViewModel: ObservableObject {
    @Published private(set) var applications: [Phase2Application] = []
    @Published private(set) var error: String?
    @Published private(set) var isLoading = false
    @Published private(set) var page = 1
    @Published private(set) var hasMore = false
    @Published private(set) var isComplete = false
    var current: Phase2Application? {
        applications.first(where: { $0.canRespond() }) ?? applications.first(where: { !$0.isTerminal })
    }
    private let client: any Phase2API
    private var generation = 0
    init(client: any Phase2API) { self.client = client }
    func load(programId: Int? = nil, opportunityId: String? = nil, page: Int = 1) async {
        generation += 1
        let request = generation
        isLoading = true
        error = nil
        applications = []
        hasMore = false
        isComplete = false
        let path =
            programId.flatMap { pid in
                opportunityId.map { "club/\(pid)/opportunities/\($0)/applications" }
            }
            ?? "me/applications"
        do {
            var nextPage = 1
            var rows: [Phase2Application] = []
            var result: ApplicationsResponse
            repeat {
                result = try await client.read(
                    path, query: [URLQueryItem(name: "page", value: String(nextPage))])
                guard request == generation, !Task.isCancelled else { return }
                var known = Set(rows.map(\.id))
                rows.append(contentsOf: result.applications.filter { known.insert($0.id).inserted })
                nextPage += 1
            } while result.hasMore
            applications = rows
            self.page = 1
            hasMore = false
            isComplete = true
        } catch {
            guard request == generation, !Task.isCancelled else { return }
            self.error = phase2Error(error)
        }
        if request == generation { isLoading = false }
    }
}

@MainActor
final class ApplicationDetailViewModel: ObservableObject {
    @Published private(set) var application: Phase2Application?
    @Published private(set) var error: String?
    @Published private(set) var isBusy = false
    @Published var note = ""
    @Published var venue = ""
    @Published var instructions = ""
    @Published var trialDate = Phase2Time.now.addingTimeInterval(86400)
    @Published var enrollmentConfirmed = false
    private let clock: () -> Date
    private let client: any Phase2API
    let id: String
    let programId: Int?
    private var generation = 0
    init(
        id: String, programId: Int? = nil, client: any Phase2API,
        now: @escaping () -> Date = { Phase2Time.now }
    ) {
        self.id = id
        self.programId = programId
        self.client = client
        self.clock = now
        self.trialDate = now().addingTimeInterval(86400)
    }
    private var initializedInvite = false
    private var path: String {
        programId.map { "club/\($0)/applications/\(id)" } ?? "me/applications/\(id)"
    }
    private var accountSubscription: AnyCancellable?
    func observeAccount(_ auth: AuthManager) {
        guard accountSubscription == nil else { return }
        accountSubscription = auth.$state
            .map { $0.isAuthenticated ? ($0.email ?? "restoring-account") : "signed-out" }
            .removeDuplicates().dropFirst()
            .sink { [weak self] _ in self?.resetAccount() }
    }

    func resetAccount() {
        generation += 1
        application = nil
        error = nil
        isBusy = false
        note = ""
        venue = ""
        instructions = ""
        trialDate = clock().addingTimeInterval(86400)
        enrollmentConfirmed = false
        initializedInvite = false
    }
    func load() async {
        guard !isBusy else { return }
        generation += 1
        let request = generation
        isBusy = true
        error = nil
        defer { if request == generation { isBusy = false } }
        do {
            let result: ApplicationResponse = try await client.read(path)
            guard request == generation, !Task.isCancelled else { return }
            application = result.application
            if !initializedInvite {
                initializedInvite = true
                trialDate = Phase2Time.date(result.application.trialAt) ?? trialDate
                venue = result.application.trialVenue ?? venue
                instructions = result.application.trialInstructions ?? instructions
            }
        } catch {
            if request == generation {
                self.error = phase2Error(error)
                if [403, 404].contains(phase2Status(error) ?? 0) { application = nil }
            }
        }
    }
    func applicantAction(_ action: String) async {
        guard !isBusy, programId == nil, let application, !application.isTerminal else { return }
        if action != "withdraw", !application.canRespond(now: clock()) { return }
        await mutate(
            suffix: action == "withdraw" ? "withdraw" : "trial-response",
            body: VersionAction(
                expectedVersion: application.version, response: action == "withdraw" ? nil : action))
    }
    func transition(_ status: String) async {
        guard !isBusy, programId != nil, let application,
            application.canTransition(to: status, now: clock())
        else {
            return
        }
        if status == "signed", !enrollmentConfirmed { return }
        if status == "invited", venue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return }
        await mutate(
            suffix: "transition",
            body: RecruitingTransition(
                expectedVersion: application.version, status: status,
                trialAt: status == "invited"
                    ? Phase2Time.submission(trialDate, zone: application.timezone) : nil,
                trialVenue: status == "invited" ? venue : nil,
                trialInstructions: status == "invited" ? instructions : nil,
                enrollmentConfirmed: status == "signed" ? true : nil))
    }
    private func mutate<Body: Encodable>(suffix: String, body: Body) async {
        isBusy = true
        error = nil
        generation += 1
        let request = generation
        defer { if request == generation { isBusy = false } }
        do {
            let response: ApplicationResponse = try await client.write(path + "/" + suffix, body: body)
            guard request == generation, !Task.isCancelled else { return }
            application = response.application
        } catch {
            guard request == generation, !Task.isCancelled else { return }
            self.error = phase2Error(error)
            // Private records can be withdrawn from the board after a hold or
            // scope change; never keep stale profile/notes visible after denial.
            if [403, 404].contains(phase2Status(error) ?? 0) { application = nil }
            if phase2Status(error) == 409 { await revalidateConflict(request: request) }
        }
    }
    private func revalidateConflict(request: Int) async {
        do {
            let response: ApplicationResponse = try await client.read(path)
            guard request == generation, !Task.isCancelled else { return }
            application = response.application
        } catch {
            guard request == generation, !Task.isCancelled else { return }
            if [403, 404].contains(phase2Status(error) ?? 0) { application = nil }
        }
    }
    func addNote() async {
        guard !isBusy, programId != nil, application != nil,
            !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else { return }
        isBusy = true
        error = nil
        generation += 1
        let request = generation
        do {
            let _: NoteResponse = try await client.write(
                path + "/notes", body: NoteSubmission(body: note))
            guard request == generation, !Task.isCancelled else { return }
            note = ""
            isBusy = false
            await load()
        } catch {
            guard request == generation, !Task.isCancelled else { return }
            self.error = phase2Error(error)
            isBusy = false
            if [403, 404].contains(phase2Status(error) ?? 0) { application = nil }
            if phase2Status(error) == 409 { await revalidateConflict(request: request) }
        }
    }
}

@MainActor
final class SquadViewModel: ObservableObject {
    @Published private(set) var squads: [Phase2Squad] = []
    @Published private(set) var members: [SquadMember] = []
    @Published private(set) var matches: [Phase2Match] = []
    @Published private(set) var error: String?
    @Published private(set) var isLoading = false
    private let client: any Phase2API
    private var generation = 0
    init(client: any Phase2API) { self.client = client }
    func load(programId: Int) async {
        generation += 1
        let request = generation
        squads = []
        members = []
        matches = []
        error = nil
        isLoading = true
        defer { if request == generation { isLoading = false } }
        do {
            let access: ClubAccessResponse = try await client.read("club/\(programId)/access/me")
            async let roster: RosterResponse = client.read("club/\(programId)/roster")
            async let teams: SquadsResponse = client.read("club/\(programId)/squads")
            let (players, groups) = try await (roster, teams)
            var games: [Phase2Match] = []
            if access.access.can("matches.view") {
                let response: MatchesResponse = try await client.read("club/\(programId)/matches")
                games = response.matches
            }
            guard request == generation, !Task.isCancelled else { return }
            let scope = access.access
            squads = groups.squads.filter { scope.wholeClub || scope.squadIds.contains($0.id) }
            members = players.members.filter { member in
                member.available
                    && (scope.wholeClub || member.squadId.map { scope.squadIds.contains($0) } == true)
            }
            matches = games.filter {
                scope.wholeClub || $0.squadId.map { scope.squadIds.contains($0) } == true
            }
        } catch { if request == generation { self.error = phase2Error(error) } }
    }
}

@MainActor
final class StaffViewModel: ObservableObject {
    @Published private(set) var board: StaffBoardResponse?
    @Published private(set) var squads: [Phase2Squad] = []
    @Published private(set) var error: String?
    @Published private(set) var notice: String?
    @Published private(set) var isBusy = false
    private let client: any Phase2API
    let programId: Int
    init(programId: Int, client: any Phase2API) {
        self.programId = programId
        self.client = client
    }
    func load() async {
        guard !isBusy else { return }
        isBusy = true
        error = nil
        defer { isBusy = false }
        do {
            let result: StaffBoardResponse = try await client.read("club/\(programId)/access")
            guard result.me.canManageAccess else {
                board = nil
                squads = []
                return
            }
            let groups: SquadsResponse = try await client.read("club/\(programId)/squads")
            guard !Task.isCancelled else { return }
            board = result
            squads = groups.squads
        } catch {
            self.error = phase2Error(error)
            if [403, 404].contains(phase2Status(error) ?? 0) {
                board = nil
                squads = []
            }
        }
    }
    @discardableResult
    func invite(email: String, role: String, allSquads: Bool, squadIds: [Int]) async -> Bool {
        guard board?.me.canManageAccess == true, !isBusy,
            role == "manager" || allSquads || !squadIds.isEmpty
        else {
            return false
        }
        isBusy = true
        error = nil
        notice = nil
        do {
            let response: StaffInviteResponse = try await client.write(
                "club/\(programId)/staff-invites",
                body: StaffInviteSubmission(
                    email: email, role: role, allSquads: role == "manager" || allSquads,
                    squadIds: role == "manager" || allSquads ? [] : squadIds.sorted()))
            notice =
                response.emailSent == true
                ? "Invite sent. It expires in 7 days."
                : "Invite created, but email delivery failed. Revoke it and try again."
            isBusy = false
            await load()
            return true
        } catch {
            await fail(error)
            return false
        }
    }
    func update(_ person: StaffPerson, role: String, allSquads: Bool, squadIds: [Int]) async {
        guard board?.me.canManageAccess == true, !isBusy, person.editable, let grant = person.grantId,
            role == "manager" || allSquads || !squadIds.isEmpty
        else { return }
        isBusy = true
        error = nil
        do {
            let _: Phase2Empty = try await client.write(
                "club/\(programId)/access/\(grant)", method: "PATCH",
                body: StaffScopeSubmission(
                    role: role, allSquads: role == "manager" || allSquads,
                    squadIds: role == "manager" || allSquads ? [] : squadIds.sorted(),
                    expectedVersion: person.version))
            isBusy = false
            await load()
        } catch { await fail(error) }
    }
    func revoke(invite: StaffInvite? = nil, person: StaffPerson? = nil) async {
        guard board?.me.canManageAccess == true, !isBusy else { return }
        let path: String
        let method: String
        if let invite {
            path = "club/\(programId)/staff-invites/\(invite.id)/revoke"
            method = "POST"
        } else if let person, person.editable, let grant = person.grantId {
            path = "club/\(programId)/access/\(grant)"
            method = "DELETE"
        } else {
            return
        }
        isBusy = true
        error = nil
        do {
            let _: Phase2Empty = try await client.write(path, method: method, body: [String: String]())
            isBusy = false
            await load()
        } catch { await fail(error) }
    }
    private func fail(_ error: Error) async {
        self.error = phase2Error(error)
        defer { isBusy = false }
        if phase2Status(error) == 409 {
            do {
                let current: StaffBoardResponse = try await client.read("club/\(programId)/access")
                if current.me.canManageAccess {
                    board = current
                } else {
                    board = nil
                    squads = []
                }
            } catch {
                if [403, 404].contains(phase2Status(error) ?? 0) {
                    board = nil
                    squads = []
                }
            }
        }
        if [403, 404].contains(phase2Status(error) ?? 0) {
            board = nil
            squads = []
        }
    }
}
