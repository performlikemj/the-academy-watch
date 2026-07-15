import Foundation

@MainActor
enum LaunchPerformance {
    #if DEBUG
    private static var launchStartedAt = ProcessInfo.processInfo.systemUptime
    private static var didLogFirstRow = false

    static func markLaunchStarted() {
        launchStartedAt = ProcessInfo.processInfo.systemUptime
        didLogFirstRow = false
    }

    static func markFirstRowRendered(source: String) {
        guard !didLogFirstRow else { return }
        didLogFirstRow = true
        let elapsed = ProcessInfo.processInfo.systemUptime - launchStartedAt
        let formattedElapsed = String(format: "%.3f", elapsed)
        print("[LaunchPerformance] time-to-first-row=\(formattedElapsed)s source=\(source)")
    }
    #else
    static func markLaunchStarted() {}
    static func markFirstRowRendered(source _: String) {}
    #endif
}
