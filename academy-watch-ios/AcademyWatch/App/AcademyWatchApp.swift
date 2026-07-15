import SwiftUI

@main
struct AcademyWatchApp: App {
    private let initialPhase = ScoutPhase.fromLaunchArguments(ProcessInfo.processInfo.arguments)
    private let initialPlayerID: Int? = {
        let arguments = ProcessInfo.processInfo.arguments
        guard let flagIndex = arguments.firstIndex(of: "-playerId"),
              arguments.indices.contains(flagIndex + 1)
        else { return nil }
        return Int(arguments[flagIndex + 1])
    }()
    private let initialComparePlayerIDs: [Int] = {
        let arguments = ProcessInfo.processInfo.arguments
        guard let flagIndex = arguments.firstIndex(of: "-comparePlayerIds"),
              arguments.indices.contains(flagIndex + 1)
        else { return [] }
        return Array(
            arguments[flagIndex + 1]
                .split(separator: ",")
                .compactMap { Int($0.trimmingCharacters(in: .whitespacesAndNewlines)) }
                .prefix(4)
        )
    }()
    private let initialTab = RootTab.fromLaunchArguments(ProcessInfo.processInfo.arguments)
    private let initiallyShowsSignIn = ProcessInfo.processInfo.arguments.contains("-showSignIn")

    init() {
        LaunchPerformance.markLaunchStarted()
        guard ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] == nil else {
            return
        }
        let warmUpClient = APIClient()
        Task.detached(priority: .utility) {
            await warmUpClient.warmUp()
        }
    }

    var body: some Scene {
        WindowGroup {
            RootTabView(
                initialPhase: initialPhase,
                initialPlayerID: initialPlayerID,
                initialComparePlayerIDs: initialComparePlayerIDs,
                initialTab: initialTab,
                initiallyShowsSignIn: initiallyShowsSignIn
            )
                .tint(AcademyColors.claretForeground)
        }
    }
}
