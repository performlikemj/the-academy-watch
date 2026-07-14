import SwiftUI

@main
struct AcademyWatchApp: App {
    var body: some Scene {
        WindowGroup {
            ScoutDeskView()
                .tint(AcademyColors.claret)
        }
    }
}
