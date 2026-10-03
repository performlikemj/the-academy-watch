import Foundation

struct Phase2Flags: Equatable, Sendable {
    var directory = false
    var opportunities = false
    var applications = false
    var staff = false
    var contact = false
}
struct Phase2FeatureResponse: Decodable {
    let clubDirectory: Bool?
    let clubStaffAccess: Bool?
    let contactRail: Bool?
}
struct OpportunityFeatures: Decodable {
    let opportunities: Bool
    let applications: Bool
}
struct ClubBrand: Decodable, Sendable {
    let primaryColor: String?
    let accentColor: String?
}
struct ClubVenue: Decodable, Sendable {
    let name: String?
    let postcode: String?
}
struct DirectoryFacts: Decodable, Sendable {
    let venue: ClubVenue?
    let clubLevel: String?
    let genderPrograms: [String]?
    let squadCount: Int?
}
struct Phase2Club: Decodable, Identifiable, Sendable {
    let id: Int
    let slug: String
    let name: String
    let crestUrl: String?
    let brand: ClubBrand?
    let city: String?
    let region: String?
    let country: String?
    let verified: Bool?
    let isVerifiedProgram: Bool?
    let league: ClubLeague?
    let venue: ClubVenue?
    let clubLevel: String?
    let genderPrograms: [String]?
    let squadCount: Int?
    let distanceKm: Double?
    let openOpportunities: Int?
    let directory: DirectoryFacts?
    let programProvided: ProgramProvided?
    var location: String {
        [city, region].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
    }
    var distance: String {
        distanceKm.map { String(format: "%.1f km", $0) } ?? "Distance unavailable"
    }
}
struct ClubLeague: Decodable, Sendable { let name: String }
struct ClubDirectoryResponse: Decodable {
    let clubs: [Phase2Club]
    let page: Int
    let hasMore: Bool
    let total: Int
}
struct PublicClubResponse: Decodable { let program: Phase2Club }
struct DirectorySearch: Encodable, Equatable, Sendable {
    var q: String? = nil
    var lat: Double? = nil
    var lng: Double? = nil
    var radiusKm: Double? = nil
    var level: String? = nil
    var programme: String? = nil
    var page = 1
    var perPage = 20
}
struct Phase2Opportunity: Decodable, Identifiable, Sendable {
    let id: String
    let programId: Int
    let clubName: String
    let clubSlug: String
    let title: String
    let description: String
    let instructions: String
    let type: String
    let positionRequirements: String
    let birthYearMin: Int?
    let birthYearMax: Int?
    let genderProgram: String
    let timezone: String
    let startsAt: String?
    let endsAt: String?
    let closesAt: String
    let venue: String
    let address: String
    let status: String
    let version: Int
    // These fields exist only on the club DTO. Public views never render them.
    var squadId: Int? = nil
    var createdAt: String? = nil
    let trialInviteDeadline: String?
    let capacity: Int?
    let placesLeft: Int?
    let applicationCount: Int?
    var typeLabel: String { type.replacingOccurrences(of: "_", with: " ").capitalized }
}
struct OpportunityResponse: Decodable { let opportunity: Phase2Opportunity }
struct OpportunitiesResponse: Decodable {
    let opportunities: [Phase2Opportunity]
    let page: Int
    let hasMore: Bool
}
struct ApplicationClaim: Decodable, Identifiable, Sendable {
    let claimId: Int
    let signedPlayerId: Int
    let name: String
    var id: Int { claimId }
}
struct ApplicationClaimsResponse: Decodable { let claims: [ApplicationClaim] }
struct ApplicationSubmission: Encodable, Sendable {
    let claimId: Int
    let position: String
    let currentClub: String
    let contactConsent: Bool
    let clientRequestId: String
}
struct Phase2Application: Decodable, Identifiable, Sendable {
    let id: String
    let opportunityId: String
    let programId: Int
    let signedPlayerId: Int
    let status: String
    let statusLabel: String
    let position: String
    let currentClub: String
    let version: Int
    let reservationState: String
    let trialAt: String?
    let trialVenue: String?
    let trialInstructions: String?
    let submittedAt: String
    let retentionExpiresAt: String
    let opportunityTitle: String
    let clubName: String
    let timezone: String
    let applicantName: String?
    let transitions: [String]?
    let notes: [ApplicationNote]?
    let events: [ApplicationEvent]?
    var isTerminal: Bool { ["signed", "rejected", "withdrawn"].contains(status) }
    func canRespond(now: Date = Phase2Time.now) -> Bool {
        status == "invited" && reservationState == "pending"
            && (Phase2Time.date(trialAt).map { $0 > now } ?? false)
    }
    func canTransition(to target: String, now: Date = Phase2Time.now) -> Bool {
        guard
            transitions?.contains(target) == true
                || (target == "invited" && status == "invited" && transitions != nil)
        else { return false }
        if target == "attended" {
            return reservationState == "confirmed"
                && (Phase2Time.date(trialAt).map { $0 <= now } ?? false)
        }
        return true
    }
    static func label(_ status: String) -> String {
        [
            "new": "Applied", "shortlisted": "With the club", "invited": "Invited to trial",
            "attended": "Trial attended", "offer": "Offer received", "signed": "Signed",
            "rejected": "Not selected",
            "withdrawn": "Withdrawn",
        ][status] ?? status.capitalized
    }
}
struct ApplicationNote: Decodable, Identifiable, Sendable {
    let id: String
    let body: String
    let createdAt: String
}
struct ApplicationEvent: Decodable, Identifiable, Sendable {
    let fromState: String?
    let toState: String
    let version: Int
    let createdAt: String
    let reasonCode: String?
    var label: String {
        switch reasonCode {
        case "trial_confirmed": "Trial place confirmed"
        case "rescheduled": "Trial rescheduled"
        default: Phase2Application.label(toState)
        }
    }
    var id: Int { version }
}
struct ApplicationResponse: Decodable { let application: Phase2Application }
struct ApplicationsResponse: Decodable {
    let applications: [Phase2Application]
    let page: Int
    let hasMore: Bool
}
struct VersionAction: Encodable {
    let expectedVersion: Int
    var response: String? = nil
    var status: String? = nil
}
struct RecruitingTransition: Encodable {
    let expectedVersion: Int
    let status: String
    var trialAt: String? = nil
    var trialVenue: String? = nil
    var trialInstructions: String? = nil
    var enrollmentConfirmed: Bool? = nil
}
struct NoteSubmission: Encodable { let body: String }
struct NoteResponse: Decodable { let note: ApplicationNote }

struct ClubAccess: Decodable, Sendable {
    let programId: Int
    let role: String
    let verified: Bool
    let wholeClub: Bool
    let allSquads: Bool
    let squadIds: [Int]
    let capabilities: [String]
    var canRecruit: Bool {
        ["owner", "manager"].contains(role) && capabilities.contains("recruiting")
    }
    var canManageAccess: Bool { role == "owner" && capabilities.contains("access.manage") }
    func can(_ capability: String) -> Bool { capabilities.contains(capability) }
}
struct ClubAccessResponse: Decodable { let access: ClubAccess }
struct MembershipProgram: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let slug: String?
}
struct ClubMembership: Decodable, Identifiable, Sendable {
    let program: MembershipProgram
    let access: ClubAccess
    var id: Int { program.id }
}
struct ClubMembershipsResponse: Decodable { let programs: [ClubMembership] }
struct Phase2ClubClaimsResponse: Decodable { let claims: [Phase2ClubClaim] }
struct Phase2ClubClaim: Decodable {
    let status: String
    let program: MembershipProgram
}
struct Phase2Squad: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
}
struct SquadsResponse: Decodable { let squads: [Phase2Squad] }
struct SquadMember: Decodable, Identifiable, Sendable {
    let id: Int
    let squadId: Int?
    let displayName: String?
    let name: String?
    let isMinor: Bool?
    let position: String?
    let shirtNumber: Int?
    let available: Bool
    var privateName: String {
        let value = displayName ?? name ?? "Player"
        guard isMinor != false else { return value }
        let words = value.split(separator: " ")
        return words.first.map(String.init).map { first in
            words.count > 1 ? first + " " + String(words.last!.prefix(1)) + "." : first
        } ?? "Player"
    }
}
struct RosterResponse: Decodable { let members: [SquadMember] }
struct Phase2Match: Decodable, Identifiable, Sendable {
    let id: Int
    let squadId: Int?
    let opponentName: String?
    let title: String?
    let status: String
    let matchDate: String?
}
struct MatchesResponse: Decodable { let matches: [Phase2Match] }
struct StaffPerson: Decodable, Identifiable, Sendable {
    let userAccountId: Int
    let grantId: Int?
    let displayName: String?
    let email: String?
    let role: String
    let allSquads: Bool
    let squadIds: [Int]
    let version: Int?
    let editable: Bool
    let permissions: [Bool]
    var id: Int { userAccountId }
}
struct StaffInvite: Decodable, Identifiable, Sendable {
    let id: String
    let email: String
    let role: String
    let allSquads: Bool
    let squadIds: [Int]
    let status: String
    let expiresAt: String
}
struct StaffBoardResponse: Decodable {
    let me: ClubAccess
    let people: [StaffPerson]
    let invites: [StaffInvite]
    let matrix: StaffMatrix
}
struct StaffMatrix: Decodable { let rows: [String] }
struct StaffScopeSubmission: Encodable {
    let role: String
    let allSquads: Bool
    let squadIds: [Int]
    var expectedVersion: Int? = nil
}
struct StaffInviteSubmission: Encodable {
    let email: String
    let role: String
    let allSquads: Bool
    let squadIds: [Int]
}
struct StaffInviteResponse: Decodable {
    let invite: StaffInvite
    let emailSent: Bool?
}
struct Phase2Empty: Decodable {}

enum Phase2Time {
    static var now: Date {
        #if DEBUG && targetEnvironment(simulator)
            if Phase2Fixtures.active { return date("2026-10-01T10:00:00Z")! }
        #endif
        return Date()
    }
    static func date(_ raw: String?) -> Date? {
        guard let raw else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let value = formatter.date(from: raw) ?? ISO8601DateFormatter().date(from: raw) {
            return value
        }
        // Contact DTOs serialize naive UTC timestamps; never interpret these in the device zone.
        guard
            raw.range(
                of: #"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?$"#, options: .regularExpression)
                != nil
        else { return nil }
        return formatter.date(from: raw + "Z") ?? ISO8601DateFormatter().date(from: raw + "Z")
    }
    static func zone(_ value: String) -> TimeZone {
        TimeZone(identifier: value) ?? TimeZone(secondsFromGMT: 0)!
    }
    static func display(_ raw: String?, zone value: String, locale: Locale = .current) -> String {
        guard let date = date(raw) else { return "Date unavailable" }
        let formatter = DateFormatter()
        formatter.locale = locale
        formatter.timeZone = zone(value)
        formatter.setLocalizedDateFormatFromTemplate("EEE d MMM jmm z")
        return formatter.string(from: date)
    }
    static func interval(
        _ start: String?, _ end: String?, zone value: String, locale: Locale = .current
    ) -> String {
        guard let startDate = date(start) else {
            return start == nil ? "No fixed date" : "Date unavailable"
        }
        guard let endDate = date(end), endDate > startDate else {
            return display(start, zone: value, locale: locale)
        }
        let timeZone = zone(value)
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        // Keep both zone labels across midnight or a daylight-saving change.
        guard calendar.isDate(startDate, inSameDayAs: endDate),
            timeZone.secondsFromGMT(for: startDate) == timeZone.secondsFromGMT(for: endDate)
        else {
            return display(start, zone: value, locale: locale) + " — "
                + display(end, zone: value, locale: locale)
        }
        let formatter = DateFormatter()
        formatter.locale = locale
        formatter.timeZone = timeZone
        formatter.setLocalizedDateFormatFromTemplate("EEE d MMM jmm")
        let leading = formatter.string(from: startDate)
        formatter.setLocalizedDateFormatFromTemplate("jmm z")
        return leading + "–" + formatter.string(from: endDate)
    }
    static func zoneLabel(_ value: String, at raw: String?) -> String {
        let zone = zone(value)
        let date = date(raw) ?? Date()
        let offset = zone.secondsFromGMT(for: date)
        let label = String(
            format: "UTC%@%02d:%02d", offset < 0 ? "−" : "+", abs(offset) / 3600, abs(offset) % 3600 / 60)
        let formatter = DateFormatter()
        formatter.locale = .current
        formatter.timeZone = zone
        formatter.dateFormat = "z"
        return
            "\(formatter.string(from: date)) (\(label)) · \(TimeZone(identifier: value) == nil ? "UTC fallback" : value)"
    }
    static func submission(_ date: Date, zone value: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.timeZone = zone(value)
        return formatter.string(from: date)
    }
}

struct ProgramProvided: Decodable, Sendable { let summary: String? }
