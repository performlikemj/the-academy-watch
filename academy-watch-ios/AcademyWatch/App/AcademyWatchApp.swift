import SwiftUI

@main
struct AcademyWatchApp: App {
    #if DEBUG
    private let onboardingFixture = OnboardingFixtureDestination.fromLaunchArguments(
        ProcessInfo.processInfo.arguments
    )
    private let logoFixtureElapsedSeconds = WingLiftLoadingView.fixtureElapsedSeconds(
        from: ProcessInfo.processInfo.arguments
    )
    private let logoFixtureReducesMotion = ProcessInfo.processInfo.arguments.contains(
        "-logoFixtureReduceMotion"
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
        if FloodlightPreview.isActive || logoFixtureElapsedSeconds != nil { return }
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

    #if DEBUG && targetEnvironment(simulator)
    private var reviewColorScheme: ColorScheme? {
        guard Phase2Fixtures.active || FloodlightPreview.isActive || logoFixtureElapsedSeconds != nil else { return nil }
        let args = ProcessInfo.processInfo.arguments
        guard let i = args.firstIndex(of: "-reviewAppearance") ?? args.firstIndex(of: "-AppleInterfaceStyle"),
              args.indices.contains(i + 1) else { return nil }
        switch args[i + 1].lowercased() {
        case "light": return .light
        case "dark": return .dark
        default: return nil
        }
    }
    #endif

    var body: some Scene {
        WindowGroup {
            Group {
                if APIEndpointPolicy.Context.current.testHost {
                    Text("Offline unit-test host").accessibilityIdentifier("unit-test-host")
                } else if let error = APIClient.developerConfigurationError {
                    Text(error).padding().accessibilityIdentifier("developer-api-error")
                } else {
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
            }
            .floodlightAppearance()
            #if DEBUG && targetEnvironment(simulator)
            .preferredColorScheme(reviewColorScheme)
            #endif
        }
    }

    @ViewBuilder private var normalRoot: some View {
        #if DEBUG
        if let logoFixtureElapsedSeconds {
            WingLiftLoadingView(
                feedback: ScoutInitialLoadFeedback(elapsedSeconds: logoFixtureElapsedSeconds),
                reduceMotionOverride: logoFixtureReducesMotion
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
