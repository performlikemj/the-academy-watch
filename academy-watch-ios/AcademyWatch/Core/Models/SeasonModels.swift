import Foundation

struct SeasonDirectory: Codable, Equatable, Sendable {
    let currentSeason: Int
    let bounds: SeasonBounds
    let seasons: [Season]
}

struct SeasonBounds: Codable, Equatable, Sendable {
    let min: Int
    let max: Int
}

struct Season: Codable, Equatable, Hashable, Identifiable, Sendable {
    let season: Int
    let label: String
    let hasRollup: Bool
    let isCurrent: Bool

    var id: Int { season }
}

struct SeasonProvenance: Codable, Equatable, Sendable {
    let source: String?
    let primarySource: String?
    let reconcileFlag: String?
    let fixturesMinutes: Int?
    let journeyMinutes: Int?
    let deltaPct: Double?
    let computedAt: String?

    var resolvedSource: String? {
        primarySource ?? source
    }

    var sourceLabel: String? {
        switch resolvedSource {
        case "fixtures": "match-level data"
        case "journey": "season totals"
        case "live-fallback": "live fallback"
        default: nil
        }
    }

    var badgeText: String? {
        guard let resolvedSource else { return nil }
        switch (resolvedSource, reconcileFlag) {
        case ("journey", "cup-gap"):
            return "journey · incl. cups"
        case ("journey", _):
            return "journey · season totals"
        case ("fixtures", _):
            return "fixtures · match log"
        case ("live-fallback", _):
            return "live fallback"
        default:
            return resolvedSource.replacingOccurrences(of: "-", with: " ")
        }
    }

    var detailText: String? {
        switch reconcileFlag {
        case "cup-gap":
            guard let fixturesMinutes, let journeyMinutes else { return nil }
            return "\(fixturesMinutes.formatted()) match mins · \(journeyMinutes.formatted()) incl. cups"
        case "fixtures-invisible":
            guard let journeyMinutes else { return nil }
            return "\(journeyMinutes.formatted()) season mins · no match log coverage"
        case "journey-under-sync":
            return "Season totals re-sync pending"
        default:
            return nil
        }
    }
}

enum SeasonLabelFormatter {
    static func label(for season: Int) -> String {
        "\(season)/\(String(format: "%02d", (season + 1) % 100))"
    }
}
