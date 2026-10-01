import SwiftUI

@main
struct AcademyWatchApp: App {
    #if DEBUG
    private let onboardingFixture = OnboardingFixtureDestination.fromLaunchArguments(
        ProcessInfo.processInfo.arguments
    )
    private let wingLiftFixtureElapsedSeconds = WingLiftLoadingView.fixtureElapsedSeconds(
        from: ProcessInfo.processInfo.arguments
    )
    private let wingLiftFixtureReducesMotion = ProcessInfo.processInfo.arguments.contains(
        "-wingLiftFixtureReduceMotion"
    )
    #endif
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
    private let initiallyShowsSignIn = ProcessInfo.processInfo.arguments.contains("-showSignIn")

    init() {
        FloodlightNativeAppearance.configure()
        LaunchPerformance.markLaunchStarted()
        #if DEBUG && targetEnvironment(simulator)
        if Phase2Fixtures.active {
            UserDefaults.standard.set(Phase2Fixtures.isClubExperience ? "club" : "player", forKey: ExperienceRole.storageKey)
            return
        }
        if FloodlightPreview.isActive { return }
        do {
            try ExperienceRole.applySimulatorLaunchArguments(ProcessInfo.processInfo.arguments)
            _ = try PlayerClubExperienceFixtures.mode(from: ProcessInfo.processInfo.arguments)
        } catch {
            fatalError("Invalid simulator launch configuration: \(error.localizedDescription)")
        }
        #endif
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
            Group {
                #if DEBUG && targetEnvironment(simulator)
                if let screen = Phase2Fixtures.screen {
                    Phase2PreviewRoot(screen: screen)
                } else if let screen = FloodlightPreview.screen {
                    FloodlightPreviewRoot(screen: screen)
                } else {
                    normalRoot
                }
                #else
                normalRoot
                #endif
            }
            .floodlightAppearance()
        }
    }

    @ViewBuilder private var normalRoot: some View {
        #if DEBUG
        if let wingLiftFixtureElapsedSeconds {
            WingLiftLoadingView(
                feedback: ScoutInitialLoadFeedback(elapsedSeconds: wingLiftFixtureElapsedSeconds),
                reduceMotionOverride: wingLiftFixtureReducesMotion
            )
        } else if let onboardingFixture {
            OnboardingEvidenceRoot(destination: onboardingFixture)
        } else {
            appRoot
        }
        #else
        appRoot
        #endif
    }

    private var appRoot: some View {
        RootTabView(
            initialPhase: initialPhase,
            initialPlayerID: initialPlayerID,
            initialComparePlayerIDs: initialComparePlayerIDs,
            launchArguments: ProcessInfo.processInfo.arguments,
            initiallyShowsSignIn: initiallyShowsSignIn
        )
        .tint(AcademyColors.accent)
    }
}
