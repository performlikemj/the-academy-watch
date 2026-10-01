import SwiftUI
import XCTest

@testable import AcademyWatch

@MainActor
final class CleatLoaderTests: XCTestCase {
  func testPaletteTimingAndReduceMotion() {
    XCTAssertEqual(
      CleatPalette.strokes, ["0F3D2E", "7A1426", "1F3E73", "0B0E0D", "E35D18", "6CACE4"])
    XCTAssertEqual(CleatPalette.accents[3], "CFAE62")
    XCTAssertEqual(CleatPalette.easeDuration, 0.2)
    for phase in 0..<6 {
      XCTAssertEqual(
        CleatPalette.phase(elapsed: Double(phase) * 1.2 + 0.001, reduceMotion: false), phase)
      XCTAssertEqual(CleatPalette.phase(elapsed: Double(phase) * 1.2, reduceMotion: true), 0)
    }
    XCTAssertEqual(CleatPalette.phase(elapsed: 7.201, reduceMotion: false), 0)
  }
  func testReduceMotionSnapshotsMatchStillGreenForEveryPhaseAndAppearance() throws {
    for scheme in [ColorScheme.light, .dark] {
      func snapshot(_ phase: Int) throws -> Data {
        let renderer = ImageRenderer(
          content: CleatLoader(phase: phase, reduceMotionOverride: true)
            .padding(24).background(AcademyColors.background).environment(\.colorScheme, scheme))
        renderer.scale = 2
        return try XCTUnwrap(renderer.uiImage?.pngData())
      }
      let expected = try snapshot(0)
      for phase in 1..<6 { XCTAssertEqual(try snapshot(phase), expected) }
      let image = XCTAttachment(data: expected, uniformTypeIdentifier: "public.png")
      image.name = "cleat-reduce-motion-\(scheme)"
      image.lifetime = .keepAlways
      add(image)
    }
  }
  func testLowCutPathsUseFiveBladesAndRemainValid() {
    XCTAssertTrue(CleatGeometry.upper.contains("M20 47"))
    XCTAssertEqual(CleatGeometry.outline.components(separatedBy: " L").count > 15, true)
    XCTAssertEqual(CleatGeometry.paths.count, 4)
    for path in CleatGeometry.paths { XCTAssertFalse(path.isEmpty) }
    XCTAssertEqual(CleatGeometry.paths[0].boundingBoxOfPath.maxY, 75, accuracy: 3)
  }
  func testOldLoaderTypeAndIndeterminateSpinnersAreAbsentFromAppSource() throws {
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
      .deletingLastPathComponent().appendingPathComponent("AcademyWatch")
    let files = try XCTUnwrap(
      FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil))
    let retired = ["Wing", "Lift", "Loading", "View"].joined()
    for case let file as URL in files where file.pathExtension == "swift" {
      let source = try String(contentsOf: file, encoding: .utf8)
      XCTAssertFalse(source.contains(retired), file.path)
      XCTAssertFalse(source.contains("Progress" + "View("), file.path)
    }
  }
}
