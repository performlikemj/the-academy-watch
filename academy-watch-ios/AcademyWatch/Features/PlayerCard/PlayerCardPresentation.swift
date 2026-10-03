import Foundation

// Wording for the player card and the read view of a player's season: the
// Swift twin of the web's `lib/player-card.js`, so both say the same thing
// about the same server answer.
//
// Match lines and their totals are NOT computed here. The server pairs the
// player's own entries with the club's and totals exactly those lines
// (`GET /players/<id>/matches?view=lines`); this file only decides what to say.

struct PlayerFact: Equatable, Identifiable, Sendable {
    let label: String
    let value: String
    var isEmail = false

    var id: String { label }
}

/// Provider totals kept whole. They are never added to the match lines.
struct ProviderSeasonTotals: Equatable, Sendable {
    var appearances: Int
    var minutes: Int
    var goals: Int
    var assists: Int
    var yellows: Int?
    var reds: Int?
    var saves: Int?
    var goalsConceded: Int?
    var avgRating: Double?
    var asOf: String?
    /// Rebuilt from the provider's own per-match rows (the totals read was empty or failed).
    var fromMatchRows = false
}

struct SeasonTile: Equatable, Identifiable, Sendable {
    let key: String
    let label: String
    let shortLabel: String
    let value: String
    /// A zero or an unknown: drawn muted, never as a fact.
    let quiet: Bool
    /// A word ("Clean", "2 cards") rather than a number.
    var word = false
    /// Share of the possible minutes (lead tile meter); nil = no meter.
    var share: Double?
    let note: String?

    var id: String { key }

    var spokenValue: String { value == "–" ? "not recorded" : value }
}

struct SeasonSummary: Equatable, Sendable {
    enum Source: String, Sendable {
        /// The provider has real totals; shown whole and labelled.
        case provider
        /// Totals are exactly the merged match lines.
        case grain
        /// Nothing recorded: an honest empty state, no zero tiles.
        case none
    }

    let source: Source
    let tiles: [SeasonTile]
    let sentence: String?
    /// At least one line is club-confirmed (the green tick on the sentence).
    let confirmed: Bool
    var avgRating: Double?
}

struct SeasonViewChoice: Equatable, Sendable {
    let season: Int?
    let provider: ProviderSeasonTotals?
    let statsMatchSeason: Bool
    let lines: [PlayerMatchLine]
    let totals: PlayerMatchLineTotals?
}

struct MatchLineSource: Equatable, Sendable {
    let mark: String
    let confirmed: Bool
    var lead: String?
    var note: String?

    var detail: String? {
        let parts = [lead, note].compactMap { $0 }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}

struct MatchResult: Equatable, Sendable {
    let outcome: String
    let score: String
    let label: String
}

struct MatchDateParts: Equatable, Sendable {
    let day: String
    let year: String
    let compact: String
}

struct CardCounter: Equatable, Identifiable, Sendable {
    let value: String
    let unit: String

    var id: String { unit }
}

enum PlayerCardText {
    static let matchLinesPreview = 10
    static let fullMatchMinutes = 90

    private static let grainSources: Set<String> = [
        "club", "club_confirmed", "club_verified", "user", "self", "self_reported",
    ]
    private static let providerSources: Set<String> = [
        "api", "api_football", "fixtures", "journey", "apss", "shadow",
    ]
    private static let months = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    private static let footLabels = ["left": "Left", "right": "Right", "both": "Both"]
    private static let contractLabels = [
        "under_contract": "Under contract", "expiring": "Contract expiring", "free_agent": "Free agent",
    ]
    private static let availabilityLabels = [
        "open_to_moves": "Open to moves", "not_looking": "Not looking",
        "trial_available": "Available for trials",
    ]
    private static let venueLabels = ["home": "home", "away": "away", "neutral": "neutral venue"]

    // MARK: Small helpers

    private static func count(_ value: Int?) -> Int {
        guard let value, value > 0 else { return 0 }
        return value
    }

    private static let grouping: NumberFormatter = {
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "en_GB")
        formatter.numberStyle = .decimal
        return formatter
    }()

    static func grouped(_ number: Int) -> String {
        grouping.string(from: NSNumber(value: number)) ?? String(number)
    }

    static func plural(_ number: Int, _ one: String, _ many: String? = nil) -> String {
        "\(grouped(number)) \(number == 1 ? one : (many ?? one + "s"))"
    }

    private static func clean(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else {
            return nil
        }
        return value
    }

    // MARK: Identity

    static func initials(of name: String?) -> String {
        let words = (name ?? "").split(whereSeparator: { $0.isWhitespace })
        guard let first = words.first?.first else { return "·" }
        guard words.count > 1, let last = words.last?.first else { return String(first).uppercased() }
        return (String(first) + String(last)).uppercased()
    }

    /// Same rule as the edit form and the web: G, GK, Goalkeeper, Keeper as a word.
    static func isGoalkeeper(position: String?) -> Bool {
        let normalized = (position ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let words = normalized.split(whereSeparator: { !("a"..."z").contains($0) })
        return words.contains { ["g", "gk", "goalkeeper", "keeper"].contains(String($0)) }
    }

    /// Short role label for the chip on a photo: "RB, RWB" -> "RB · RWB".
    static func roleLabel(positions: String?, fallback: String?) -> String? {
        let stated = (positions ?? "")
            .split(whereSeparator: { ",/;".contains($0) })
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
            .prefix(3)
        if !stated.isEmpty { return stated.joined(separator: " · ") }
        return clean(fallback)
    }

    /// The line under the name on a list card: only fields that exist, never invented.
    static func cardLine(position: String?, clubName: String?, bio: String? = nil) -> String {
        let role = [clean(position), clean(clubName)].compactMap { $0 }
        let lead: String
        switch role.count {
        case 2: lead = "\(role[0]) at \(role[1])."
        case 1: lead = "\(role[0])."
        default: lead = ""
        }
        return [lead, firstSentence(of: bio)].filter { !$0.isEmpty }.joined(separator: " ")
    }

    private static func firstSentence(of text: String?) -> String {
        guard let text = clean(text) else { return "" }
        var sentence = ""
        var previousEndsSentence = false
        for character in text {
            if previousEndsSentence, character.isWhitespace { break }
            sentence.append(character)
            previousEndsSentence = ".!?".contains(character)
        }
        return sentence
    }

    static func cardCounters(appearances: Int?, minutes: Int?) -> [CardCounter] {
        var counters: [CardCounter] = []
        if count(appearances) > 0 {
            counters.append(CardCounter(
                value: grouped(count(appearances)),
                unit: count(appearances) == 1 ? "app" : "apps"
            ))
        }
        if count(minutes) > 0 {
            counters.append(CardCounter(value: grouped(count(minutes)), unit: "min"))
        }
        return counters
    }

    private static func normalizedSource(_ value: String?) -> String {
        (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            .replacingOccurrences(of: "-", with: "_")
    }

    /// True only when a list row's figures are known to come from the provider.
    /// Club- or player-entered figures are counted differently on the player's
    /// page (one line per match), so a list must not print them as counters.
    static func isProviderSourced(_ provenance: SeasonProvenance?) -> Bool {
        let raw = [provenance?.sourceCategory, provenance?.source, provenance?.primarySource]
            .compactMap { $0 }
            .first { !$0.isEmpty }
        return providerSources.contains(normalizedSource(raw))
    }

    /// The server's own merged-lines totals for a list row: the same numbers
    /// the player's page shows, so they may be printed as counters.
    static func isMatchLinesSourced(_ provenance: SeasonProvenance?) -> Bool {
        normalizedSource(provenance?.primarySource) == "matches"
    }

    // MARK: Facts strip

    private static func formatContractUntil(_ value: String?) -> String? {
        guard let parts = dateComponents(value), let month = monthName(parts.month) else { return nil }
        return "\(parts.day) \(month) \(parts.yearText)"
    }

    /// Facts strip: only fields that have a value, never a placeholder dash.
    static func profileFacts(_ profile: ShowcaseProfile?) -> [PlayerFact] {
        guard let profile else { return [] }
        let until = formatContractUntil(profile.contractUntil)
        let contractParts = [
            profile.rawContractStatus.flatMap { contractLabels[$0] },
            until.map { "until \($0)" },
        ].compactMap { $0 }
        var contract = contractParts.isEmpty ? nil : contractParts.joined(separator: " · ")
        if let text = contract, text.hasPrefix("until ") {
            contract = "Until " + text.dropFirst("until ".count)
        }
        let candidates: [(String, String?)] = [
            ("Positions", profile.positions),
            ("Foot", profile.preferredFoot.flatMap { footLabels[$0] }),
            ("Height", profile.heightCm.map { "\($0) cm" }),
            ("Contract", contract),
            ("Availability", profile.availability.flatMap { availabilityLabels[$0] }),
            ("Second nationality", profile.nationalitySecondary),
            ("Languages", profile.languages),
            ("Agent", profile.agentName),
        ]
        var facts = candidates.compactMap { label, value in
            clean(value).map { PlayerFact(label: label, value: $0) }
        }
        // The server only includes the agent's email for signed-in readers.
        if let email = clean(profile.agentContactEmail) {
            facts.append(PlayerFact(label: "Agent email", value: email, isEmail: true))
        }
        return facts
    }

    // MARK: Which totals, which season

    static func seasonStart(of value: String?) -> Int? {
        let digits = (value ?? "").trimmingCharacters(in: .whitespaces).prefix(4)
        guard digits.count == 4, digits.allSatisfy(\.isNumber) else { return nil }
        return Int(digits)
    }

    /// Provider totals count only when the provider really has play for the
    /// season. Totals whose headline source is the club or the player are the
    /// match grain, and those are read from the merged lines instead.
    static func providerTotals(_ stats: PlayerSeasonStats?) -> ProviderSeasonTotals? {
        guard let stats else { return nil }
        if let frozen = stats.publicMatchData {
            guard frozen.available == true, let totals = frozen.totals,
                  count(totals.appearances) > 0 || count(totals.minutes) > 0
            else { return nil }
            return ProviderSeasonTotals(
                appearances: count(totals.appearances), minutes: count(totals.minutes),
                goals: count(totals.goals), assists: count(totals.assists),
                yellows: totals.yellows, reds: totals.reds,
                saves: totals.saves, goalsConceded: totals.goalsConceded,
                avgRating: totals.avgRating, asOf: frozen.asOf
            )
        }
        let headline = [stats.provenance?.primarySource, stats.provenance?.source, stats.source]
            .compactMap { $0 }
            .first { !$0.isEmpty }
        if grainSources.contains(normalizedSource(headline)) || grainSources.contains(stats.source.lowercased()) {
            return nil
        }
        guard stats.appearances > 0 || stats.minutes > 0 else { return nil }
        return ProviderSeasonTotals(
            appearances: stats.appearances, minutes: stats.minutes,
            goals: stats.goals, assists: stats.assists,
            yellows: stats.yellows, reds: stats.reds,
            saves: stats.statedSaves, goalsConceded: stats.statedGoalsConceded,
            avgRating: stats.avgRating, asOf: nil
        )
    }

    /// Provider totals rebuilt from the provider's own per-match rows.
    static func providerTotals(fromMatchRows rows: [PlayerRecentFixture]) -> ProviderSeasonTotals? {
        guard !rows.isEmpty else { return nil }
        func sum(_ value: (PlayerRecentFixture) -> Int?) -> Int {
            rows.reduce(0) { $0 + count(value($1)) }
        }
        func knownSum(_ value: (PlayerRecentFixture) -> Int?) -> Int? {
            rows.contains { value($0) != nil } ? sum(value) : nil
        }
        let dates = rows.compactMap { $0.fixtureDate.map { String($0.prefix(10)) } }
            .filter { !$0.isEmpty }
            .sorted()
        return ProviderSeasonTotals(
            appearances: rows.count, minutes: sum(\.minutes), goals: sum(\.goals), assists: sum(\.assists),
            yellows: knownSum(\.yellows), reds: knownSum(\.reds),
            saves: knownSum(\.saves), goalsConceded: knownSum(\.goalsConceded),
            avgRating: nil, asOf: dates.last, fromMatchRows: true
        )
    }

    /// Which season the read view shows: an explicit pick wins; otherwise the
    /// season the provider totals describe; otherwise the newest with lines.
    static func resolveSeason(
        picked: Int?, statsSeason: Int?, hasProvider: Bool, seasons: [PlayerMatchLineSeason]
    ) -> Int? {
        if let picked { return picked }
        if hasProvider, let statsSeason { return statsSeason }
        if let newest = seasons.map(\.season).max() { return newest }
        return statsSeason
    }

    /// Everything the season block needs, decided in one place from ONE
    /// season. Provider totals are used only when they describe the season
    /// being shown — another season's response is never printed under it.
    static func seasonView(
        picked: Int?,
        stats: PlayerSeasonStats?,
        seasons: [PlayerMatchLineSeason],
        fallbackSeason: Int?,
        matchRows: [PlayerRecentFixture] = [],
        matchRowsSeason: Int? = nil
    ) -> SeasonViewChoice {
        let fromRows = matchRowsSeason != nil ? providerTotals(fromMatchRows: matchRows) : nil
        let fromStats = providerTotals(stats)
        let statsSeason = seasonStart(of: stats?.season)
        let providerSeason: Int? = (fromStats != nil && statsSeason != nil)
            ? statsSeason
            : (fromRows != nil ? matchRowsSeason : nil)
        let season = resolveSeason(
            picked: picked,
            statsSeason: providerSeason ?? statsSeason ?? fallbackSeason,
            hasProvider: providerSeason != nil,
            seasons: seasons
        )
        let entry = seasons.first { $0.season == season }
        let provider: ProviderSeasonTotals?
        if let fromStats, statsSeason != nil, statsSeason == season {
            provider = fromStats
        } else if let fromRows, matchRowsSeason == season {
            provider = fromRows
        } else {
            provider = nil
        }
        return SeasonViewChoice(
            season: season,
            provider: provider,
            statsMatchSeason: statsSeason != nil && statsSeason == season,
            lines: entry?.lines ?? [],
            totals: entry?.totals
        )
    }

    /// Football season that contains a date: August to July.
    static func calendarSeason(_ date: Date = Date(), calendar: Calendar = .current) -> Int {
        let parts = calendar.dateComponents([.year, .month], from: date)
        let year = parts.year ?? 0
        return (parts.month ?? 1) >= 8 ? year : year - 1
    }

    static func seasonKicker(season: Int?, currentSeason: Int) -> String {
        season == currentSeason ? "This season" : "Season"
    }

    // MARK: Failed reads

    /// The one sentence shown when a read behind the season block failed, or
    /// nil. `showing` = something is on screen for the season (tiles or lines).
    static func readProblem(
        linesError: Bool, linesStale: Bool, totalsError: Bool, totalsStale: Bool, showing: Bool
    ) -> String? {
        guard linesError || totalsError else { return nil }
        if (linesError && linesStale) || (totalsError && totalsStale) {
            return "The latest figures could not be loaded. Showing what was loaded before."
        }
        if !showing {
            return linesError && !totalsError
                ? "The matches could not be loaded. This is a loading problem — it does not mean nothing has been recorded."
                : "The season could not be loaded. This is a loading problem — it does not mean nothing has been recorded."
        }
        if totalsError {
            return "The season totals could not be loaded. What is shown comes from the matches that did load."
        }
        return "The matches entered by the club or the player could not be loaded."
    }

    // MARK: Season tiles

    private struct Figures {
        var minutes: Int
        var appearances: Int
        var fullMatches: Int?
        var goals: Int
        var assists: Int
        var yellows: Int?
        var reds: Int?
        var cardsKnown: Bool
        var saves: Int?
        var goalsConceded: Int?
        var keeperMatches: Int
    }

    private static func minutesTile(_ figures: Figures, matchCount: Int) -> SeasonTile {
        var note: String?
        if figures.appearances > 0 {
            if let full = figures.fullMatches, full == matchCount, matchCount > 0 {
                note = "Every minute of the \(plural(matchCount, "match", "matches")) recorded"
            } else {
                let average = Int((Double(figures.minutes) / Double(figures.appearances)).rounded())
                note = "\(average) minutes a game across \(plural(figures.appearances, "appearance"))"
            }
        }
        return SeasonTile(
            key: "minutes", label: "Minutes", shortLabel: "Minutes",
            value: grouped(figures.minutes), quiet: figures.minutes == 0,
            share: figures.appearances > 0
                ? min(1, Double(figures.minutes) / Double(figures.appearances * fullMatchMinutes))
                : 0,
            note: note
        )
    }

    private static func appearancesTile(_ figures: Figures, matchCount: Int, provider: Bool) -> SeasonTile {
        var note: String?
        if !provider {
            note = figures.appearances == matchCount
                ? "\(plural(matchCount, "match", "matches")) recorded so far"
                : "Played in \(figures.appearances) of \(plural(matchCount, "match", "matches")) recorded"
        }
        return SeasonTile(
            key: "appearances", label: "Appearances", shortLabel: "Apps",
            value: grouped(figures.appearances), quiet: figures.appearances == 0, note: note
        )
    }

    private static func contributionTile(_ figures: Figures) -> SeasonTile {
        let total = figures.goals + figures.assists
        let parts = [
            figures.goals > 0 ? plural(figures.goals, "goal") : nil,
            figures.assists > 0 ? plural(figures.assists, "assist") : nil,
        ].compactMap { $0 }
        return SeasonTile(
            key: "contribution", label: "Goals + assists", shortLabel: "G + A",
            value: String(total), quiet: total == 0,
            note: total == 0 ? "No goals or assists yet" : parts.joined(separator: " · ")
        )
    }

    /// Whatever keeper figures exist replace the goals + assists tile. Unknown is not zero.
    private static func keeperTile(_ figures: Figures) -> SeasonTile {
        let across = figures.keeperMatches > 0 ? " in \(plural(figures.keeperMatches, "match", "matches"))" : ""
        guard figures.saves != nil || figures.goalsConceded != nil else {
            return SeasonTile(
                key: "keeper", label: "Saves", shortLabel: "Saves", value: "–", quiet: true,
                note: "No keeper figures recorded yet"
            )
        }
        guard let saves = figures.saves else {
            return SeasonTile(
                key: "keeper", label: "Conceded", shortLabel: "Conceded",
                value: String(count(figures.goalsConceded)), quiet: false, note: "Goals conceded\(across)"
            )
        }
        return SeasonTile(
            key: "keeper", label: "Saves", shortLabel: "Saves",
            value: String(count(saves)), quiet: count(saves) == 0,
            note: figures.goalsConceded.map { "\(count($0)) conceded\(across)" } ?? "Goals conceded not recorded"
        )
    }

    /// "Clean" only when the source actually states card counts. Unknown shows nothing.
    private static func disciplineTile(_ figures: Figures) -> SeasonTile? {
        guard figures.cardsKnown else { return nil }
        let yellows = count(figures.yellows)
        let reds = count(figures.reds)
        if yellows + reds == 0 {
            return SeasonTile(
                key: "discipline", label: "Discipline", shortLabel: "Cards", value: "Clean",
                quiet: false, word: true, note: "No yellow or red cards"
            )
        }
        let parts = [yellows > 0 ? "\(yellows) yellow" : nil, reds > 0 ? "\(reds) red" : nil].compactMap { $0 }
        return SeasonTile(
            key: "discipline", label: "Discipline", shortLabel: "Cards",
            value: plural(yellows + reds, "card"), quiet: false, word: true,
            note: parts.joined(separator: " · ")
        )
    }

    private static func grainSentence(_ totals: PlayerMatchLineTotals, lines: [PlayerMatchLine]) -> String {
        var parts = [
            "Built from \(plural(totals.matches, "match", "matches")). \(count(totals.clubConfirmed)) confirmed by the club, \(count(totals.selfReportedOnly)) only reported by the player.",
        ]
        if totals.differing > 0 {
            parts.append("Where the two reports differ, the club's figures are used.")
        }
        if lines.contains(where: \.sharedSlot) {
            parts.append("Entries that share a date and opponent are listed separately and each is counted.")
        }
        return parts.joined(separator: " ")
    }

    private static func providerSentence(_ provider: ProviderSeasonTotals, frozen: Bool, lineCount: Int) -> String {
        let verb = lineCount == 1 ? "is" : "are"
        if provider.fromMatchRows {
            let built = "Totals are built from the \(plural(provider.appearances, "match", "matches")) in the public match log."
            guard lineCount > 0 else { return built }
            return "\(built) The \(plural(lineCount, "match", "matches")) entered by the club or the player \(verb) listed separately and \(verb) not added to these totals."
        }
        let asOf = provider.asOf.map { String($0.prefix(10)) }
        let lead = frozen
            ? "Public match data — last updated \(asOf ?? "unknown")."
            : "Totals come from public match data."
        guard lineCount > 0 else { return lead }
        return "\(lead) The \(plural(lineCount, "match", "matches")) entered by the club or the player \(verb) listed below and \(verb) not added to these totals."
    }

    /// One description of the season block. Provider totals and match-line
    /// totals are never added together.
    static func summarizeSeason(
        lines: [PlayerMatchLine] = [],
        totals: PlayerMatchLineTotals? = nil,
        provider: ProviderSeasonTotals? = nil,
        goalkeeper: Bool = false,
        frozen: Bool = false,
        minutesKnown: Bool = true
    ) -> SeasonSummary {
        if let provider {
            let figures = Figures(
                minutes: provider.minutes, appearances: provider.appearances, fullMatches: nil,
                goals: provider.goals, assists: provider.assists,
                yellows: provider.yellows, reds: provider.reds,
                cardsKnown: provider.yellows != nil && provider.reds != nil,
                saves: provider.saves, goalsConceded: provider.goalsConceded, keeperMatches: 0
            )
            let tiles: [SeasonTile?] = [
                // Limited-coverage provider totals carry no minutes: leave the
                // tile out rather than print a zero.
                minutesKnown ? minutesTile(figures, matchCount: provider.appearances) : nil,
                appearancesTile(figures, matchCount: provider.appearances, provider: true),
                goalkeeper ? keeperTile(figures) : contributionTile(figures),
                disciplineTile(figures),
            ]
            return SeasonSummary(
                source: .provider, tiles: tiles.compactMap { $0 },
                sentence: providerSentence(provider, frozen: frozen, lineCount: lines.count),
                confirmed: false, avgRating: provider.avgRating
            )
        }
        guard let totals, totals.matches > 0 else {
            return SeasonSummary(source: .none, tiles: [], sentence: nil, confirmed: false)
        }
        let figures = Figures(
            minutes: count(totals.minutes), appearances: count(totals.appearances),
            fullMatches: totals.fullMatches.map { count($0) },
            goals: count(totals.goals), assists: count(totals.assists),
            yellows: totals.yellows, reds: totals.reds, cardsKnown: totals.cardsKnown,
            saves: totals.saves, goalsConceded: totals.goalsConceded, keeperMatches: count(totals.keeperMatches)
        )
        let tiles: [SeasonTile?] = [
            minutesTile(figures, matchCount: totals.matches),
            appearancesTile(figures, matchCount: totals.matches, provider: false),
            goalkeeper ? keeperTile(figures) : contributionTile(figures),
            disciplineTile(figures),
        ]
        return SeasonSummary(
            source: .grain, tiles: tiles.compactMap { $0 },
            sentence: grainSentence(totals, lines: lines),
            confirmed: totals.clubConfirmed > 0
        )
    }

    // MARK: One match

    private static func dateComponents(_ value: String?) -> (yearText: String, month: Int, day: Int)? {
        let text = String((value ?? "").prefix(10))
        let parts = text.split(separator: "-", omittingEmptySubsequences: false)
        guard text.count == 10, parts.count == 3, parts[0].count == 4,
              parts.allSatisfy({ !$0.isEmpty && $0.allSatisfy(\.isNumber) }),
              let month = Int(parts[1]), let day = Int(parts[2])
        else { return nil }
        return (String(parts[0]), month, day)
    }

    private static func monthName(_ month: Int) -> String? {
        months.indices.contains(month - 1) ? months[month - 1] : nil
    }

    static func matchDateParts(_ value: String?) -> MatchDateParts {
        guard let parts = dateComponents(value), let month = monthName(parts.month) else {
            return MatchDateParts(day: "Date not recorded", year: "", compact: "DATE NOT RECORDED")
        }
        let day = "\(parts.day) \(month)"
        return MatchDateParts(day: day, year: parts.yearText, compact: "\(day) \(parts.yearText)".uppercased())
    }

    static func venueLabel(_ homeAway: String?) -> String? {
        homeAway.flatMap { venueLabels[$0] }
    }

    static func matchResult(_ line: PlayerMatchLine) -> MatchResult? {
        guard let goalsFor = line.resultFor, let against = line.resultAgainst else { return nil }
        let outcome = goalsFor > against ? "W" : goalsFor < against ? "L" : "D"
        let word = outcome == "W" ? "Won" : outcome == "L" ? "Lost" : "Drew"
        return MatchResult(outcome: outcome, score: "\(goalsFor)–\(against)", label: "\(word) \(goalsFor)–\(against)")
    }

    static func minutesShare(_ minutes: Int?) -> Double {
        max(0, min(1, Double(count(minutes)) / Double(fullMatchMinutes)))
    }

    /// One plain sentence for the match card.
    static func lineSummary(_ line: PlayerMatchLine, goalkeeper: Bool = false) -> String {
        var parts: [String] = []
        if goalkeeper {
            if let saves = line.saves { parts.append(plural(saves, "save")) }
            if let conceded = line.goalsConceded {
                parts.append(conceded == 0 ? "none conceded" : "\(conceded) conceded")
            }
        } else {
            if count(line.goals) > 0 { parts.append(plural(count(line.goals), "goal")) }
            if count(line.assists) > 0 { parts.append(plural(count(line.assists), "assist")) }
        }
        if count(line.yellows) > 0 { parts.append("\(count(line.yellows)) yellow") }
        if count(line.reds) > 0 { parts.append("\(count(line.reds)) red") }
        if !parts.isEmpty { return parts.joined(separator: " · ") }
        let cardsStated = line.yellows != nil && line.reds != nil
        if goalkeeper { return cardsStated ? "No cards" : "No keeper figures recorded" }
        return cardsStated ? "No goals, assists or cards" : "No goals or assists"
    }

    /// Source wording. Neutral by design: a difference is stated, never judged.
    static func lineSource(_ line: PlayerMatchLine) -> MatchLineSource {
        // Several entries share this date and opponent and could not be paired:
        // each is listed and counted, and the page says so rather than guessing.
        if line.sharedSlot {
            return MatchLineSource(
                mark: line.isClubConfirmed ? "Club-confirmed" : "Self-reported",
                confirmed: line.isClubConfirmed,
                note: "One of several entries for this date and opponent"
            )
        }
        guard line.isClubConfirmed else {
            return MatchLineSource(mark: "Self-reported", confirmed: false)
        }
        switch line.selfReport {
        case .matches:
            return MatchLineSource(mark: "Club-confirmed", confirmed: true, note: "Matches the player's own report")
        case .differs:
            return MatchLineSource(
                mark: "Club-confirmed", confirmed: true,
                lead: "Club figures shown", note: "Differs from the player's report"
            )
        case nil:
            return MatchLineSource(mark: "Club-confirmed", confirmed: true)
        }
    }

    /// Everything VoiceOver says for one match card, in reading order.
    static func spokenLine(_ line: PlayerMatchLine, goalkeeper: Bool) -> String {
        let date = matchDateParts(line.matchDate)
        let source = lineSource(line)
        let parts: [String?] = [
            date.year.isEmpty ? date.day : "\(date.day) \(date.year)",
            [clean(line.opponent), venueLabel(line.homeAway)].compactMap { $0 }.joined(separator: ", "),
            clean(line.competition),
            matchResult(line)?.label ?? "Result not recorded",
            "\(count(line.minutes)) minutes",
            lineSummary(line, goalkeeper: goalkeeper),
            source.mark,
            source.detail,
        ]
        return parts.compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: ". ")
    }
}
