import Foundation

struct PlayerProfile: Decodable, Equatable, Sendable {
    let playerId: Int
    let name: String
    let photo: String?
    let position: String?
    let status: String?
    let age: Int?
    let nationality: String?
    let shadow: Bool?

    let loanTeamName: String?
    let loanTeamId: Int?
    let loanTeamLogo: String?
    let parentTeamName: String?
    let parentTeamId: Int?
    let parentTeamLogo: String?
    let ownerTeamName: String?
    let ownerTeamId: Int?
    let ownerTeamLogo: String?
    let saleFee: String?

    var photoURL: URL? {
        photo.flatMap(URL.init(string:))
    }

    var currentClubName: String? {
        loanTeamName ?? parentTeamName
    }

    var currentClubLogoURL: URL? {
        let logo = loanTeamName == nil ? parentTeamLogo : loanTeamLogo
        return logo.flatMap(URL.init(string:))
    }

    var clubOriginLine: String? {
        guard let currentClubName else { return nil }
        if status == "on_loan" {
            let origin = ownerTeamName ?? parentTeamName
            guard let origin,
                  !origin.isEmpty,
                  currentClubName.caseInsensitiveCompare(origin) != .orderedSame
            else { return nil }
            return "from \(origin)"
        }

        guard let parentTeamName,
              !parentTeamName.isEmpty,
              currentClubName.caseInsensitiveCompare(parentTeamName) != .orderedSame
        else { return nil }
        return "\(parentTeamName) academy"
    }

    var isGoalkeeper: Bool {
        guard let position else { return false }
        return position.caseInsensitiveCompare("Goalkeeper") == .orderedSame
            || position.caseInsensitiveCompare("G") == .orderedSame
    }

    var isShadow: Bool {
        shadow == true
    }
}

#if DEBUG
extension PlayerProfile {
    static let fullCircleFixture = PlayerProfile(
        playerId: 403_064,
        name: "Habeeb Amass",
        photo: nil,
        position: "Defender",
        status: "first_team",
        age: 19,
        nationality: "England",
        shadow: false,
        loanTeamName: "Manchester United",
        loanTeamId: 33,
        loanTeamLogo: nil,
        parentTeamName: "Manchester United",
        parentTeamId: 33,
        parentTeamLogo: nil,
        ownerTeamName: nil,
        ownerTeamId: nil,
        ownerTeamLogo: nil,
        saleFee: nil
    )
}
#endif

struct PlayerSeasonStats: Decodable, Equatable, Sendable {
    let playerId: Int
    let season: String
    let appearances: Int
    let minutes: Int
    let goals: Int
    let assists: Int
    let avgRating: Double?
    let saves: Int
    let goalsConceded: Int
    let cleanSheets: Int
    let source: String
    let statsCoverage: String?
    let localAppearances: Int?
    let clubs: [PlayerSeasonClub]
    let provenance: PlayerSeasonProvenance?

    var hasHeadlineData: Bool {
        appearances > 0
            || minutes > 0
            || goals > 0
            || assists > 0
            || saves > 0
            || goalsConceded > 0
            || cleanSheets > 0
            || !clubs.isEmpty
    }

    var hasAnyData: Bool {
        hasHeadlineData
            || (provenance?.fixturesMinutes ?? 0) > 0
            || (provenance?.journeyMinutes ?? 0) > 0
    }

    var seasonStartYear: Int? {
        season.split(separator: "/").first.flatMap { Int($0) }
    }

    var countingSourceLabel: String? {
        if statsCoverage == "limited" || source == "limited-coverage" {
            return "limited coverage"
        }
        return fallbackSourceLabel
    }

    var clubSourceLabel: String? {
        guard !clubs.isEmpty else { return nil }
        if statsCoverage == "limited" || source == "limited-coverage" {
            return "limited coverage"
        }
        return "season totals"
    }

    var matchDetailSourceLabel: String {
        if statsCoverage == "limited" || source == "limited-coverage" || source == "shadow" {
            return "limited coverage"
        }
        return hasDetailedGoalkeeperCoverage ? "match-level data" : "no match-level coverage"
    }

    var hasDetailedGoalkeeperCoverage: Bool {
        localAppearances != nil
            && statsCoverage != "limited"
            && source != "limited-coverage"
            && source != "shadow"
    }

    private var fallbackSourceLabel: String? {
        switch source {
        case "api-football": "season totals"
        case "local-db": "match-level data"
        case "limited-coverage": "limited coverage"
        case "shadow": "season totals"
        default: nil
        }
    }
}

struct PlayerSeasonClub: Decodable, Equatable, Sendable {
    let teamName: String
    let teamLogo: String?
    let windowType: String?
    let isCurrent: Bool?
    let appearances: Int?
    let minutes: Int?
    let goals: Int?
    let assists: Int?
    let saves: Int?
    let goalsConceded: Int?

    var logoURL: URL? {
        teamLogo.flatMap(URL.init(string:))
    }

    func matchesCurrentClub(named currentClubName: String?) -> Bool {
        guard let currentClubName else { return false }
        return teamName.caseInsensitiveCompare(currentClubName) == .orderedSame
    }
}

struct PlayerSeasonProvenance: Decodable, Equatable, Sendable {
    let source: String
    let fixturesMinutes: Int
    let journeyMinutes: Int
    let deltaPct: Double
    let reconcileFlag: String?

    var sourceLabel: String? {
        switch source {
        case "fixtures": "match-level data"
        case "journey": "season totals"
        default: nil
        }
    }

    var detailText: String? {
        switch reconcileFlag {
        case "cup-gap":
            return "\(fixturesMinutes.formatted()) match mins · \(journeyMinutes.formatted()) incl. cups"
        case "fixtures-invisible":
            return "\(journeyMinutes.formatted()) season mins · no match log coverage"
        case "journey-under-sync":
            return "Season totals re-sync pending"
        default:
            return nil
        }
    }
}

struct PlayerRecentFixture: Decodable, Equatable, Sendable {
    let id: Int
    let fixtureId: Int
    let playerApiId: Int
    let fixtureDate: String?
    let opponent: String?
    let competition: String?
    let loanTeamName: String?
    let isHome: Bool?
    let minutes: Int?
    let goals: Int?
    let assists: Int?
    let rating: Double?
    let saves: Int?
    let goalsConceded: Int?
}

struct PlayerAvailability: Decodable, Equatable, Sendable {
    let playerId: Int
    let season: Int
    let absences: [PlayerAbsence]
    let summary: PlayerAvailabilitySummary
}

struct PlayerAvailabilitySummary: Decodable, Equatable, Sendable {
    let totalAbsences: Int
    let byReason: [String: Int]
    let lastAbsence: PlayerAbsence?
}

struct PlayerAbsence: Decodable, Equatable, Sendable {
    let date: String?
    let fixtureId: Int?
    let type: String?
    let reason: String?
    let teamId: Int?
    let teamName: String?
    let teamLogo: String?
    let leagueName: String?
}

struct PlayerJourneyResponse: Decodable, Equatable, Sendable {
    let playerId: Int
    let source: String
    let entries: [PlayerJourneyEntry]?
    let stints: [PlayerJourneyStint]
    let totalStints: Int

    private enum CodingKeys: String, CodingKey {
        case playerId
        case source
        case entries
        case stints
        case totalStints
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        playerId = try container.decode(Int.self, forKey: .playerId)
        source = try container.decode(String.self, forKey: .source)
        entries = try container.decodeIfPresent([PlayerJourneyEntry].self, forKey: .entries)
        stints = try container.decodeIfPresent([PlayerJourneyStint].self, forKey: .stints) ?? []
        totalStints = try container.decodeIfPresent(Int.self, forKey: .totalStints) ?? stints.count
    }

    var timelineEntries: [PlayerJourneyTimelineEntry] {
        if let entries, !entries.isEmpty {
            return Self.timelineEntries(from: entries)
        }
        return Self.timelineEntries(from: stints)
    }

    private static func timelineEntries(from entries: [PlayerJourneyEntry]) -> [PlayerJourneyTimelineEntry] {
        var grouped: [RawJourneyGroupKey: PlayerJourneyTimelineEntry] = [:]

        for entry in entries {
            let key = RawJourneyGroupKey(
                season: entry.season,
                clubId: entry.club.id,
                level: entry.level,
                entryType: entry.entryType
            )
            let current = grouped[key]
            grouped[key] = PlayerJourneyTimelineEntry(
                id: "entry-\(entry.season)-\(entry.club.id)-\(entry.level ?? "level")-\(entry.entryType ?? "type")",
                season: entry.season,
                clubId: entry.club.id,
                clubName: entry.club.name,
                clubLogo: entry.club.logo,
                level: entry.level,
                entryType: entry.entryType,
                appearances: combinedOptionalTotal(current?.appearances, entry.stats.appearances),
                goals: combinedOptionalTotal(current?.goals, entry.stats.goals),
                assists: combinedOptionalTotal(current?.assists, entry.stats.assists),
                minutes: combinedOptionalTotal(current?.minutes, entry.stats.minutes),
                competitionCount: (current?.competitionCount ?? 0) + 1,
                sequence: current?.sequence ?? 0,
                isCurrent: current?.isCurrent ?? false
            )
        }

        return grouped.values.sorted(by: timelineSort)
    }

    private static func timelineEntries(from stints: [PlayerJourneyStint]) -> [PlayerJourneyTimelineEntry] {
        var grouped: [StintJourneyGroupKey: PlayerJourneyTimelineEntry] = [:]

        for stint in stints {
            let honestLevel = stint.levels.count == 1 ? stint.levels.first : nil
            // Public stints reduce entry types at club level, so the value is
            // not trustworthy for an individual season (international teams
            // can otherwise be mislabeled "Academy").
            let honestType: String? = nil

            for competition in stint.competitions {
                let key = StintJourneyGroupKey(season: competition.season, clubId: stint.teamApiId)
                let current = grouped[key]
                grouped[key] = PlayerJourneyTimelineEntry(
                    id: "stint-\(competition.season)-\(stint.teamApiId)",
                    season: competition.season,
                    clubId: stint.teamApiId,
                    clubName: stint.teamName,
                    clubLogo: stint.teamLogo,
                    level: honestLevel,
                    entryType: honestType,
                    appearances: combinedOptionalTotal(current?.appearances, competition.apps),
                    goals: combinedOptionalTotal(current?.goals, competition.goals),
                    assists: combinedOptionalTotal(current?.assists, competition.assists),
                    minutes: nil,
                    competitionCount: (current?.competitionCount ?? 0) + 1,
                    sequence: stint.sequence ?? 0,
                    isCurrent: stint.isCurrent ?? false
                )
            }
        }

        return grouped.values.sorted(by: timelineSort)
    }

    private static func timelineSort(
        _ lhs: PlayerJourneyTimelineEntry,
        _ rhs: PlayerJourneyTimelineEntry
    ) -> Bool {
        if lhs.season != rhs.season { return lhs.season > rhs.season }
        if lhs.isCurrent != rhs.isCurrent { return lhs.isCurrent }
        if lhs.sequence != rhs.sequence { return lhs.sequence > rhs.sequence }
        return lhs.clubName.localizedCaseInsensitiveCompare(rhs.clubName) == .orderedAscending
    }

    private static func combinedOptionalTotal(_ lhs: Int?, _ rhs: Int?) -> Int? {
        guard lhs != nil || rhs != nil else { return nil }
        return (lhs ?? 0) + (rhs ?? 0)
    }
}

struct PlayerJourneyEntry: Decodable, Equatable, Sendable {
    let id: Int
    let season: Int
    let club: PlayerJourneyClub
    let league: PlayerJourneyLeague?
    let level: String?
    let entryType: String?
    let isYouth: Bool?
    let isInternational: Bool?
    let stats: PlayerJourneyEntryStats
}

struct PlayerJourneyClub: Decodable, Equatable, Sendable {
    let id: Int
    let name: String
    let logo: String?

    private enum CodingKeys: String, CodingKey {
        case id
        case name
        case logo
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(Int.self, forKey: .id)
        name = try container.decodeIfPresent(String.self, forKey: .name) ?? "Unknown club"
        logo = try container.decodeIfPresent(String.self, forKey: .logo)
    }
}

struct PlayerJourneyLeague: Decodable, Equatable, Sendable {
    let id: Int?
    let name: String?
    let country: String?
    let logo: String?
}

struct PlayerJourneyEntryStats: Decodable, Equatable, Sendable {
    let appearances: Int?
    let goals: Int?
    let assists: Int?
    let minutes: Int?
}

struct PlayerJourneyStint: Decodable, Equatable, Sendable {
    let id: String
    let teamApiId: Int
    let teamName: String
    let teamLogo: String?
    let stintType: String?
    let level: String?
    let levels: [String]
    let years: String?
    let isCurrent: Bool?
    let sequence: Int?
    let stats: PlayerJourneyStintStats?
    let competitions: [PlayerJourneyCompetition]

    private enum CodingKeys: String, CodingKey {
        case id
        case teamApiId
        case teamName
        case teamLogo
        case stintType
        case level
        case levels
        case years
        case isCurrent
        case sequence
        case stats
        case competitions
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        teamApiId = try container.decode(Int.self, forKey: .teamApiId)
        teamName = try container.decodeIfPresent(String.self, forKey: .teamName) ?? "Unknown club"
        teamLogo = try container.decodeIfPresent(String.self, forKey: .teamLogo)
        stintType = try container.decodeIfPresent(String.self, forKey: .stintType)
        level = try container.decodeIfPresent(String.self, forKey: .level)

        let decodedLevels = try container.decodeIfPresent([String?].self, forKey: .levels)?
            .compactMap { $0 } ?? []
        levels = decodedLevels.isEmpty ? [level].compactMap { $0 } : decodedLevels

        years = try container.decodeIfPresent(String.self, forKey: .years)
        isCurrent = try container.decodeIfPresent(Bool.self, forKey: .isCurrent)
        sequence = try container.decodeIfPresent(Int.self, forKey: .sequence)
        stats = try container.decodeIfPresent(PlayerJourneyStintStats.self, forKey: .stats)
        competitions = try container.decodeIfPresent(
            [PlayerJourneyCompetition].self,
            forKey: .competitions
        ) ?? []
    }
}

struct PlayerJourneyStintStats: Decodable, Equatable, Sendable {
    let apps: Int?
    let goals: Int?
    let assists: Int?
}

struct PlayerJourneyCompetition: Decodable, Equatable, Sendable {
    let season: Int
    let league: String?
    let apps: Int?
    let goals: Int?
    let assists: Int?
}

struct PlayerJourneyTimelineEntry: Identifiable, Equatable, Sendable {
    let id: String
    let season: Int
    let clubId: Int
    let clubName: String
    let clubLogo: String?
    let level: String?
    let entryType: String?
    let appearances: Int?
    let goals: Int?
    let assists: Int?
    let minutes: Int?
    let competitionCount: Int
    let sequence: Int
    let isCurrent: Bool

    var logoURL: URL? {
        clubLogo.flatMap(URL.init(string:))
    }

    var seasonLabel: String {
        "\(season)/\(String((season + 1) % 100).leftPadded(to: 2))"
    }
}

private struct RawJourneyGroupKey: Hashable {
    let season: Int
    let clubId: Int
    let level: String?
    let entryType: String?
}

private struct StintJourneyGroupKey: Hashable {
    let season: Int
    let clubId: Int
}

private extension String {
    func leftPadded(to length: Int) -> String {
        String(repeating: "0", count: max(0, length - count)) + self
    }
}
