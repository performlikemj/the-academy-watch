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

    var body: some Scene {
        WindowGroup {
            ScoutDeskView(initialPhase: initialPhase, initialPlayerID: initialPlayerID)
                .tint(AcademyColors.claret)
        }
    }
}
