import SwiftUI

/// Same side-profile paths and 1.2-second club phases as web lib/cleat-loader.js.
enum CleatPalette {
  static let strokes = ["0F3D2E", "7A1426", "1F3E73", "0B0E0D", "E35D18", "6CACE4"]
  static let accents = ["0F3D2E", "7A1426", "1F3E73", "CFAE62", "E35D18", "6CACE4"]
  static let phaseDuration = 1.2
  static let easeDuration = 0.2
  static func phase(elapsed: TimeInterval, reduceMotion: Bool) -> Int {
    reduceMotion ? 0 : Int(max(0, elapsed) / phaseDuration) % strokes.count
  }
}

struct CleatDrawing: Shape {
  var part = 0
  func path(in rect: CGRect) -> Path {
    let p = Path(CleatGeometry.paths[part])
    return p.applying(CGAffineTransform(scaleX: rect.width / 144, y: rect.height / 96))
      .applying(CGAffineTransform(translationX: rect.minX, y: rect.minY))
  }
}

struct CleatLoader: View {
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @Environment(\.controlSize) private var controlSize
  private var caption: String?
  private var feedback: ScoutInitialLoadFeedback?
  private var reduceMotionOverride: Bool?
  private var phaseOverride: Int?
  @State private var phase = 0
  init(_ caption: String? = nil) { self.caption = caption }
  init(feedback: ScoutInitialLoadFeedback, reduceMotionOverride: Bool? = nil) {
    self.feedback = feedback
    self.caption = "LOADING"
    self.reduceMotionOverride = reduceMotionOverride
  }
  init(phase: Int, reduceMotionOverride: Bool = false) {
    caption = "LOADING"
    phaseOverride = phase
    self.reduceMotionOverride = reduceMotionOverride
  }
  private var still: Bool { reduceMotion || (reduceMotionOverride ?? false) }
  private var displayedPhase: Int {
    still ? 0 : (phaseOverride ?? phase) % CleatPalette.strokes.count
  }
  private var width: CGFloat {
    if feedback != nil || caption != nil { return 144 }
    return controlSize == .mini ? 24 : controlSize == .small ? 30 : 36
  }
  var body: some View {
    VStack(spacing: 12) {
      ZStack {
        CleatDrawing().fill(Color(hex: UInt32(CleatPalette.strokes[displayedPhase], radix: 16)!))
        CleatDrawing(part: 2).fill(
          Color(hex: UInt32(CleatPalette.accents[displayedPhase], radix: 16)!))
        CleatDrawing(part: 3).stroke(
          displayedPhase >= 4 ? AcademyColors.ink : AcademyColors.chalk,
          style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
        // Inherit ink/chalk or button foreground, just as the SVG inherits currentColor.
        CleatDrawing(part: 1).stroke(
          .foreground,
          style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
      }.frame(width: width, height: width * 96 / 144)
      if let caption {
        Text(caption).font(AcademyType.mono(11)).tracking(1.8)
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
    .frame(
      maxWidth: feedback == nil ? nil : .infinity, maxHeight: feedback == nil ? nil : .infinity
    )
    .padding(feedback == nil ? 0 : 30)
    .background(feedback == nil ? Color.clear : AcademyColors.background)
    .multilineTextAlignment(.center)
    .accessibilityElement(children: .ignore).accessibilityLabel("Loading")
    .accessibilityIdentifier(feedback == nil ? "cleat-loader" : "initial-load-feedback")
    .task(id: still) {
      guard !still, phaseOverride == nil else {
        phase = 0
        return
      }
      let started = Date()
      do {
        try await Task.sleep(for: .seconds(CleatPalette.phaseDuration - CleatPalette.easeDuration))
      } catch { return }
      while !Task.isCancelled {
        withAnimation(.timingCurve(0.25, 0.1, 0.25, 1, duration: CleatPalette.easeDuration)) {
          phase = CleatPalette.phase(
            elapsed: Date().timeIntervalSince(started) + CleatPalette.easeDuration,
            reduceMotion: still)
        }
        do { try await Task.sleep(for: .seconds(CleatPalette.phaseDuration)) } catch { return }
      }
    }
  }
  #if DEBUG
    static func fixtureElapsedSeconds(from arguments: [String]) -> Int? {
      guard let i = arguments.firstIndex(of: "-cleatFixtureSeconds"),
        arguments.indices.contains(i + 1),
        let seconds = Int(arguments[i + 1])
      else { return nil }
      return max(0, seconds)
    }
  #endif
}
