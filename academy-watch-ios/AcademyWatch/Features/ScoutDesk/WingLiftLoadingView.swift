import SwiftUI

/// Club colours tint the existing brand layers; no logo geometry is drawn here.
enum LogoLoadingPalette {
    static let bodies = ["0F3D2E", "7A1426", "1F3E73", "0B0E0D", "E35D18", "6CACE4"]
    static let accents = ["0F3D2E", "7A1426", "1F3E73", "CFAE62", "E35D18", "6CACE4"]
    static let wing = "FFFFFF"
    static let phaseDuration = 1.2
    static let easeDuration = 0.2

    static func phase(elapsed: TimeInterval, reduceMotion: Bool) -> Int {
        reduceMotion ? 0 : Int(max(0, elapsed) / phaseDuration) % bodies.count
    }

    static func shouldReduceMotion(system: Bool, preview: Bool = false) -> Bool {
        system || preview
    }
}

/// The original WingLiftLoadingView's lift, wing beats and breathing scale.
struct LogoLoadingMotion: Equatable {
    let upperBeat: Double
    let lowerBeat: Double
    let scale: Double
    let lift: Double

    init(elapsed: TimeInterval, reduceMotion: Bool) {
        let time = reduceMotion ? 0 : max(0, elapsed)
        let ramp = min(1, time / 0.3)
        let breath = (1 - cos((time / 2.4) * 2 * .pi)) / 2
        upperBeat = sin((time / 1.7) * 2 * .pi) * ramp * 5.4
        lowerBeat = sin((time / 1.85) * 2 * .pi - 0.28) * ramp * 3.1
        scale = 1 + breath * 0.018
        lift = sin((time / 2.4) * 2 * .pi) * 5
    }
}

enum LogoLoadingSurface {
    case page, primaryButton, chalk
    func isDark(in scheme: ColorScheme) -> Bool {
        switch self {
        case .page: scheme == .dark
        case .primaryButton: scheme == .light
        case .chalk: false
        }
    }
}
private struct LogoLoadingSurfaceKey: EnvironmentKey {
    static let defaultValue = LogoLoadingSurface.page
}
extension EnvironmentValues {
    var logoLoadingSurface: LogoLoadingSurface {
        get { self[LogoLoadingSurfaceKey.self] }
        set { self[LogoLoadingSurfaceKey.self] = newValue }
    }
}

/// Crisp, asset-derived chalk edge on dark surfaces; the bitmap silhouette is unchanged.
private struct LogoBootEdge: ViewModifier {
    let dark: Bool
    func body(content: Content) -> some View {
        let edge = AcademyColors.chalk.opacity(dark ? 0.9 : 0)
        content
            .shadow(color: edge, radius: 0.2, x: 0.35)
            .shadow(color: edge, radius: 0.2, x: -0.35)
            .shadow(color: edge, radius: 0.2, y: 0.35)
            .shadow(color: edge, radius: 0.2, y: -0.35)
    }
}

/// One shared logo loader for initial cards, inline reads and busy controls.
struct WingLiftLoadingView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.controlSize) private var controlSize
    @Environment(\.logoLoadingSurface) private var surface
    @Environment(\.colorScheme) private var colorScheme
    private var caption: String?
    private var feedback: ScoutInitialLoadFeedback?
    #if DEBUG
    private var reduceMotionOverride: Bool?
    private var phaseOverride: Int?
    #endif
    @State private var phase = 0
    @State private var animationStartedAt = Date()
    private let wingAnchor = UnitPoint(x: 0.39, y: 0.41)

    init(_ caption: String? = nil) { self.caption = caption }
    #if DEBUG
    init(feedback: ScoutInitialLoadFeedback, reduceMotionOverride: Bool? = nil) {
        self.feedback = feedback
        caption = "LOADING"
        self.reduceMotionOverride = reduceMotionOverride
    }
    init(phase: Int, reduceMotionOverride: Bool = false, caption: String? = "LOADING") {
        self.caption = caption
        phaseOverride = max(0, phase) % LogoLoadingPalette.bodies.count
        self.reduceMotionOverride = reduceMotionOverride
    }
    #else
    init(feedback: ScoutInitialLoadFeedback) {
        self.feedback = feedback
        caption = "LOADING"
    }
    #endif

    private var still: Bool {
        #if DEBUG
        return LogoLoadingPalette.shouldReduceMotion(system: reduceMotion, preview: reduceMotionOverride ?? false)
        #else
        return reduceMotion
        #endif
    }
    private var fixedPhase: Int? {
        #if DEBUG
        return phaseOverride
        #else
        return nil
        #endif
    }
    private var displayedPhase: Int { still ? 0 : fixedPhase ?? phase }
    private var width: CGFloat {
        if feedback != nil || caption != nil { return 162 }
        return controlSize == .mini ? 24 : controlSize == .small ? 30 : 36
    }
    private var height: CGFloat { width * 105 / 162 }

    var body: some View {
        VStack(spacing: 12) {
            TimelineView(.animation(minimumInterval: 1 / 60, paused: still || fixedPhase != nil)) { context in
                let elapsed = fixedPhase == nil ? max(0, context.date.timeIntervalSince(animationStartedAt)) : 0
                wingedBoot(elapsed: elapsed)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Loading")
            .accessibilityIdentifier("logo-loader")
            if let caption {
                Text(caption).accessibilityHidden(true).font(AcademyType.mono(11)).tracking(1.8)
                    .foregroundStyle(AcademyColors.text).multilineTextAlignment(.center)
            }
            if let feedback {
                Text(feedback.title).font(AcademyType.ui(21, weight: .semibold))
                Text(feedback.detail).font(AcademyType.body).foregroundStyle(AcademyColors.secondaryText)
                if feedback.showsFirstVisitDuration {
                    Text("First visits can take about 30 seconds.").font(AcademyType.caption2)
                        .foregroundStyle(AcademyColors.secondaryText)
                }
            }
        }
        .frame(maxWidth: feedback == nil ? nil : .infinity, maxHeight: feedback == nil ? nil : .infinity)
        .padding(feedback == nil ? 0 : 30)
        .background(feedback == nil ? Color.clear : AcademyColors.background)
        .multilineTextAlignment(.center)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(feedback == nil ? "logo-loading-container" : "initial-load-feedback")
        .task(id: still) {
            phase = 0
            animationStartedAt = Date()
            guard !still, fixedPhase == nil else { return }
            let started = animationStartedAt
            do {
                try await Task.sleep(for: .seconds(LogoLoadingPalette.phaseDuration - LogoLoadingPalette.easeDuration))
            } catch { return }
            while !Task.isCancelled {
                withAnimation(.timingCurve(0.25, 0.1, 0.25, 1, duration: LogoLoadingPalette.easeDuration)) {
                    phase = LogoLoadingPalette.phase(
                        elapsed: Date().timeIntervalSince(started) + LogoLoadingPalette.easeDuration,
                        reduceMotion: still)
                }
                do { try await Task.sleep(for: .seconds(LogoLoadingPalette.phaseDuration)) } catch { return }
            }
        }
    }

    private func wingedBoot(elapsed: TimeInterval) -> some View {
        let motion = LogoLoadingMotion(elapsed: elapsed, reduceMotion: still)
        let body = Color(hex: UInt32(LogoLoadingPalette.bodies[displayedPhase], radix: 16)!)
        let accent = Color(hex: UInt32(LogoLoadingPalette.accents[displayedPhase], radix: 16)!)
        let bodyTint = LinearGradient(stops: [
            .init(color: body, location: 0), .init(color: body, location: 0.72),
            .init(color: accent, location: 0.72), .init(color: accent, location: 1)
        ], startPoint: .top, endPoint: .bottom)
        return ZStack {
            // The legacy Body bitmap also contains the main wing. Two rectangles
            // select the boot pixels across the empty gap, without drawing a silhouette.
            markLayer("LaunchBootBody")
                .foregroundStyle(bodyTint)
                .mask {
                    ZStack(alignment: .bottomTrailing) {
                        Rectangle().frame(width: width * 310 / 486)
                            .frame(maxWidth: .infinity, alignment: .trailing)
                        Rectangle().frame(height: height * 135 / 315)
                            .frame(maxHeight: .infinity, alignment: .bottom)
                    }
                }
                .modifier(LogoBootEdge(dark: surface.isDark(in: colorScheme)))
            // WingB is actually a detached boot tongue in the original extraction.
            // It keeps its existing subtle beat, but takes the boot colour.
            markLayer("LaunchBootWingB").foregroundStyle(bodyTint)
                .modifier(LogoBootEdge(dark: surface.isDark(in: colorScheme)))
                .rotationEffect(.degrees(motion.lowerBeat), anchor: wingAnchor)
            ZStack {
                markLayer("LaunchBootBody")
                    .mask {
                        Rectangle().frame(width: width * 176 / 486, height: height * 180 / 315)
                            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                    }
                markLayer("LaunchBootWingA")
            }
            .foregroundStyle(Color.white)
            // A small ink edge keeps white wings legible on chalk without changing their fill.
            .shadow(color: AcademyColors.ink.opacity(surface.isDark(in: colorScheme) ? 0 : 0.85), radius: 0.5)
            .rotationEffect(.degrees(motion.upperBeat), anchor: wingAnchor)
        }
        .frame(width: width, height: height)
        .scaleEffect(motion.scale)
        .offset(y: motion.lift * width / 162)
    }

    private func markLayer(_ name: String) -> some View {
        Image(name).renderingMode(.template).resizable().interpolation(.high)
            .frame(width: width, height: height)
    }

    #if DEBUG
    static func fixtureElapsedSeconds(from arguments: [String]) -> Int? {
        guard let i = arguments.firstIndex(of: "-logoFixtureSeconds"),
              arguments.indices.contains(i + 1), let seconds = Int(arguments[i + 1])
        else { return nil }
        return max(0, seconds)
    }
    #endif
}
