import Foundation

enum FullCircleFixtureDestination: String, Sendable {
    case verification
    case introduction
    case attestationWarning = "attestationwarning"
    case inbox
    case clubConsent = "clubconsent"
    case thread
    case playerInbox = "playerinbox"
    case declineConfirmation = "declineconfirmation"
    case watchingYou = "watchingyou"
    case messageReport = "messagereport"
    case deleteAccount = "deleteaccount"
    case claimGate = "claimgate"
    case blockedUsers = "blockedusers"
    case watchlistNullStats = "watchlistnullstats"
    case exportData = "exportdata"
    case takedown
    case fanRow = "fanrow"

    static func fromLaunchArguments(_ arguments: [String]) -> FullCircleFixtureDestination? {
        #if DEBUG
        guard let flagIndex = arguments.firstIndex(of: "-fullCircleFixture"),
              arguments.indices.contains(flagIndex + 1)
        else { return nil }
        return FullCircleFixtureDestination(rawValue: arguments[flagIndex + 1].lowercased())
        #else
        return nil
        #endif
    }
}
