import SwiftUI

@main
struct AcademyWatchApp: App {
    private let initialPhase = ScoutPhase.fromLaunchArguments(ProcessInfo.processInfo.arguments)

    var body: some Scene {
        WindowGroup {
            ScoutDeskView(initialPhase: initialPhase)
                .tint(AcademyColors.claret)
        }
    }
}
