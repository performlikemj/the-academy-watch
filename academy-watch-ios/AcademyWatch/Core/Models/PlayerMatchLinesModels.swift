import Foundation

/// `GET /players/<signed id>/matches?view=lines` — the server's one line per
/// match (`services/match_lines.py`). The player's own entries and the club's
/// are paired and totalled there; nothing is merged or summed on the device.
struct PlayerMatchLinesResponse: Decodable, Equatable, Sendable {
    let seasons: [PlayerMatchLineSeason]
    /// The server left the oldest seasons out (very long records).
    let truncated: Bool

    static let empty = PlayerMatchLinesResponse(seasons: [], truncated: false)

    init(seasons: [PlayerMatchLineSeason], truncated: Bool) {
        self.seasons = seasons
        self.truncated = truncated
    }

    private enum CodingKeys: String, CodingKey {
        case seasons
        case truncated
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        seasons = try container.decodeIfPresent([PlayerMatchLineSeason].self, forKey: .seasons) ?? []
        truncated = try container.decodeIfPresent(Bool.self, forKey: .truncated) ?? false
    }
}

struct PlayerMatchLineSeason: Decodable, Equatable, Identifiable, Sendable {
    let season: Int
    let lines: [PlayerMatchLine]
    let totals: PlayerMatchLineTotals

    var id: Int { season }
}

struct PlayerMatchLine: Decodable, Equatable, Identifiable, Sendable {
    enum Confirmation: String, Decodable, Sendable {
        case clubConfirmed = "club_confirmed"
        case selfReported = "self_reported"
    }

    /// How the player's own report compares with the club line shown.
    enum SelfReport: String, Decodable, Sendable {
        case matches
        case differs
    }

    let key: String
    let season: Int?
    let matchDate: String?
    let opponent: String?
    let competition: String?
    let homeAway: String?
    let resultFor: Int?
    let resultAgainst: Int?
    let minutes: Int?
    let goals: Int?
    let assists: Int?
    let yellows: Int?
    let reds: Int?
    let saves: Int?
    let goalsConceded: Int?
    let confirmation: Confirmation
    let selfReport: SelfReport?
    /// Other entries share this date and opponent and could not be paired.
    let sharedSlot: Bool

    var id: String { key }

    var isClubConfirmed: Bool { confirmation == .clubConfirmed }

    private enum CodingKeys: String, CodingKey {
        case key, season, matchDate, opponent, competition, homeAway, resultFor, resultAgainst
        case minutes, goals, assists, yellows, reds, saves, goalsConceded
        case confirmation, selfReport, sharedSlot
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        key = try container.decode(String.self, forKey: .key)
        season = try container.decodeIfPresent(Int.self, forKey: .season)
        matchDate = try container.decodeIfPresent(String.self, forKey: .matchDate)
        opponent = try container.decodeIfPresent(String.self, forKey: .opponent)
        competition = try container.decodeIfPresent(String.self, forKey: .competition)
        homeAway = try container.decodeIfPresent(String.self, forKey: .homeAway)
        resultFor = try container.decodeIfPresent(Int.self, forKey: .resultFor)
        resultAgainst = try container.decodeIfPresent(Int.self, forKey: .resultAgainst)
        minutes = try container.decodeIfPresent(Int.self, forKey: .minutes)
        goals = try container.decodeIfPresent(Int.self, forKey: .goals)
        assists = try container.decodeIfPresent(Int.self, forKey: .assists)
        yellows = try container.decodeIfPresent(Int.self, forKey: .yellows)
        reds = try container.decodeIfPresent(Int.self, forKey: .reds)
        saves = try container.decodeIfPresent(Int.self, forKey: .saves)
        goalsConceded = try container.decodeIfPresent(Int.self, forKey: .goalsConceded)
        // Only a club row whose status is club_confirmed is ever sent as
        // confirmed; anything unrecognised is treated as the weaker claim.
        confirmation = (try? container.decode(Confirmation.self, forKey: .confirmation)) ?? .selfReported
        selfReport = try? container.decodeIfPresent(SelfReport.self, forKey: .selfReport)
        sharedSlot = try container.decodeIfPresent(Bool.self, forKey: .sharedSlot) ?? false
    }
}

/// `season_totals()` for exactly the lines of one season, each match once.
struct PlayerMatchLineTotals: Decodable, Equatable, Sendable {
    let matches: Int
    let appearances: Int
    let fullMatches: Int?
    let minutes: Int
    let goals: Int
    let assists: Int
    let yellows: Int?
    let reds: Int?
    /// Cards are only "known" when every line states them. Unknown is not clean.
    let cardsKnown: Bool
    let saves: Int?
    let goalsConceded: Int?
    let keeperMatches: Int
    let clubConfirmed: Int
    let selfReportedOnly: Int
    let differing: Int

    private enum CodingKeys: String, CodingKey {
        case matches, appearances, fullMatches, minutes, goals, assists, yellows, reds, cardsKnown
        case saves, goalsConceded, keeperMatches, clubConfirmed, selfReportedOnly, differing
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        matches = try container.decodeIfPresent(Int.self, forKey: .matches) ?? 0
        appearances = try container.decodeIfPresent(Int.self, forKey: .appearances) ?? 0
        fullMatches = try container.decodeIfPresent(Int.self, forKey: .fullMatches)
        minutes = try container.decodeIfPresent(Int.self, forKey: .minutes) ?? 0
        goals = try container.decodeIfPresent(Int.self, forKey: .goals) ?? 0
        assists = try container.decodeIfPresent(Int.self, forKey: .assists) ?? 0
        yellows = try container.decodeIfPresent(Int.self, forKey: .yellows)
        reds = try container.decodeIfPresent(Int.self, forKey: .reds)
        cardsKnown = try container.decodeIfPresent(Bool.self, forKey: .cardsKnown) ?? false
        saves = try container.decodeIfPresent(Int.self, forKey: .saves)
        goalsConceded = try container.decodeIfPresent(Int.self, forKey: .goalsConceded)
        keeperMatches = try container.decodeIfPresent(Int.self, forKey: .keeperMatches) ?? 0
        clubConfirmed = try container.decodeIfPresent(Int.self, forKey: .clubConfirmed) ?? 0
        selfReportedOnly = try container.decodeIfPresent(Int.self, forKey: .selfReportedOnly) ?? 0
        differing = try container.decodeIfPresent(Int.self, forKey: .differing) ?? 0
    }
}

/// An approved showcase photo row (`_media_dict`). Owners also receive
/// unapproved rows; only approved rows that carry a public URL are ever shown.
struct ShowcasePhoto: Decodable, Equatable, Identifiable, Sendable {
    let id: Int
    let status: String?
    let publicUrl: String?
    let isPrimary: Bool?
    let sortOrder: Int?

    var url: URL? { publicUrl.flatMap(URL.init(string:)) }
}

struct ShowcaseAffiliation: Decodable, Equatable, Sendable {
    let id: Int?
    let clubName: String?
    let season: String?
    let status: String?

    private enum CodingKeys: String, CodingKey {
        case id, clubName, season, status
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(Int.self, forKey: .id)
        clubName = try container.decodeIfPresent(String.self, forKey: .clubName)
        // The season is a label; older rows carry it as a number.
        if let text = try? container.decodeIfPresent(String.self, forKey: .season) {
            season = text
        } else if let number = try? container.decodeIfPresent(Int.self, forKey: .season) {
            season = String(number)
        } else {
            season = nil
        }
        status = try container.decodeIfPresent(String.self, forKey: .status)
    }
}
