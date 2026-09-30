import SwiftUI

struct WingLiftLoadingView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    let feedback: ScoutInitialLoadFeedback
    #if DEBUG
    let reduceMotionOverride: Bool?
    #endif

    @State private var animationStartedAt = Date()

    private let markWidth: CGFloat = 162
    private let markHeight: CGFloat = 105
    private let wingAnchor = UnitPoint(x: 0.39, y: 0.41)

    #if DEBUG
    init(feedback: ScoutInitialLoadFeedback, reduceMotionOverride: Bool? = nil) {
        self.feedback = feedback
        self.reduceMotionOverride = reduceMotionOverride
    }
    #else
    init(feedback: ScoutInitialLoadFeedback) {
        self.feedback = feedback
    }
    #endif

    var body: some View {
        GeometryReader { proxy in
            TimelineView(.animation(minimumInterval: 1 / 60, paused: shouldReduceMotion)) { context in
                let elapsed = max(0, context.date.timeIntervalSince(animationStartedAt))

                ZStack {
                    AcademyColors.night

                    wingedBoot(elapsed: elapsed)
                        .position(x: proxy.size.width / 2, y: proxy.size.height / 2)

                    loadingCopy
                        .frame(width: max(0, proxy.size.width - 60), alignment: .top)
                        .position(
                            x: proxy.size.width / 2,
                            y: proxy.size.height / 2 + copyCenterOffset
                        )

                    Text("THE ACADEMY WATCH")
                        .font(AcademyType.ui( 10, weight: .semibold))
                        .tracking(2.8)
                        .foregroundStyle(cardMuted.opacity(0.55))
                        .position(x: proxy.size.width / 2, y: proxy.size.height - 30)
                }
            }
        }
        .ignoresSafeArea()
        .preferredColorScheme(.dark)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityStatus)
        .accessibilityAddTraits(.updatesFrequently)
        .accessibilityIdentifier("initial-load-feedback")
        .onAppear {
            animationStartedAt = Date()
        }
    }

    private var loadingCopy: some View {
        VStack(spacing: 0) {
            Text(feedback.title)
                .font(AcademyType.ui( 21, weight: .semibold))
                .tracking(-0.3)
                .foregroundStyle(cardInk)
                .multilineTextAlignment(.center)

            Text(feedback.detail)
                .font(AcademyType.ui( 14))
                .foregroundStyle(cardMuted)
                .multilineTextAlignment(.center)
                .lineSpacing(1.5)
                .frame(maxWidth: 290)
                .padding(.top, 9)

            if feedback.showsFirstVisitDuration {
                Text("First visits can take about 30 seconds.")
                    .font(AcademyType.caption2)
                    .foregroundStyle(cardMuted.opacity(0.72))
                    .multilineTextAlignment(.center)
                    .padding(.top, 9)
            }
        }
    }

    private var copyCenterOffset: CGFloat {
        feedback.showsFirstVisitDuration ? 118 : 103
    }

    private var accessibilityStatus: String {
        let duration = feedback.showsFirstVisitDuration
            ? " First visits can take about 30 seconds."
            : ""
        return "\(feedback.title) \(feedback.detail)\(duration)"
    }

    private var shouldReduceMotion: Bool {
        #if DEBUG
        if let reduceMotionOverride {
            return reduceMotionOverride
        }
        #endif
        return reduceMotion
    }

    private func wingedBoot(elapsed: TimeInterval) -> some View {
        let ramp = min(1, elapsed / 0.3)
        let hoverWave = sin((elapsed / 2.4) * 2 * .pi)
        let breath = (1 - cos((elapsed / 2.4) * 2 * .pi)) / 2
        let upperBeat = sin((elapsed / 1.7) * 2 * .pi) * ramp
        let lowerBeat = sin((elapsed / 1.85) * 2 * .pi - 0.28) * ramp

        return ZStack {
            markLayer("LaunchBootBody")
            markLayer("LaunchBootWingA")
                .rotationEffect(
                    .degrees(shouldReduceMotion ? 0 : upperBeat * 5.4),
                    anchor: wingAnchor
                )
            markLayer("LaunchBootWingB")
                .rotationEffect(
                    .degrees(shouldReduceMotion ? 0 : lowerBeat * 3.1),
                    anchor: wingAnchor
                )
        }
        .frame(width: markWidth, height: markHeight)
        .scaleEffect(shouldReduceMotion ? 1 : 1 + breath * 0.018)
        .opacity(1)
        .offset(y: shouldReduceMotion ? 0 : hoverWave * 5)
        .shadow(
            color: .black.opacity(
                ramp * (shouldReduceMotion ? 0.42 : 0.42 + breath * 0.13)
            ),
            radius: shouldReduceMotion ? 14 : 14 + breath * 6,
            y: shouldReduceMotion ? 9 : 9 + breath * 3
        )
    }

    private func markLayer(_ name: String) -> some View {
        Image(name)
            .resizable()
            .interpolation(.high)
            .frame(width: markWidth, height: markHeight)
    }

    private var cardInk: Color {
        AcademyColors.chalk
    }

    private var cardMuted: Color {
        AcademyColors.mutedDark
    }
}

#if DEBUG
extension WingLiftLoadingView {
    static func fixtureElapsedSeconds(from arguments: [String]) -> Int? {
        guard let flagIndex = arguments.firstIndex(of: "-wingLiftFixtureSeconds"),
              arguments.indices.contains(flagIndex + 1),
              let elapsedSeconds = Int(arguments[flagIndex + 1])
        else { return nil }
        return max(0, elapsedSeconds)
    }
}
#endif
