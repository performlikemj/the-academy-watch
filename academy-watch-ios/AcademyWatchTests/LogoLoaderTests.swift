import SwiftUI
import XCTest

@testable import AcademyWatch

@MainActor
final class LogoLoaderTests: XCTestCase {
    func testSixPhaseCycleAndEaseTiming() {
        XCTAssertEqual(LogoLoadingPalette.bodies, ["0F3D2E", "7A1426", "1F3E73", "0B0E0D", "E35D18", "6CACE4"])
        XCTAssertEqual(LogoLoadingPalette.accents, ["0F3D2E", "7A1426", "1F3E73", "CFAE62", "E35D18", "6CACE4"])
        XCTAssertEqual(LogoLoadingPalette.wing, "FFFFFF")
        XCTAssertEqual(LogoLoadingPalette.phaseDuration, 1.2)
        XCTAssertEqual(LogoLoadingPalette.easeDuration, 0.2)
        XCTAssertEqual(LogoLoadingPalette.phase(elapsed: -1, reduceMotion: false), 0)
        for cycle in 0..<3 {
            for phase in 0..<6 {
                let start = Double(cycle * 6 + phase) * 1.2
                XCTAssertEqual(LogoLoadingPalette.phase(elapsed: start + 0.001, reduceMotion: false), phase)
                XCTAssertEqual(LogoLoadingPalette.phase(elapsed: start + 1.199, reduceMotion: false), phase)
                XCTAssertEqual(LogoLoadingPalette.phase(elapsed: start + 1.2, reduceMotion: true), 0)
            }
        }
    }

    func testReduceMotionAlwaysWinsAndStopsEveryMotionComponent() {
        XCTAssertTrue(LogoLoadingPalette.shouldReduceMotion(system: true, preview: false))
        XCTAssertTrue(LogoLoadingPalette.shouldReduceMotion(system: true, preview: true))
        XCTAssertTrue(LogoLoadingPalette.shouldReduceMotion(system: false, preview: true))
        XCTAssertFalse(LogoLoadingPalette.shouldReduceMotion(system: false, preview: false))
        let still = LogoLoadingMotion(elapsed: 0, reduceMotion: true)
        XCTAssertEqual(still.scale, 1)
        XCTAssertEqual(still.lift, 0)
        XCTAssertEqual(still.upperBeat, 0)
        XCTAssertEqual(still.lowerBeat, 0)
        for elapsed in stride(from: 0.0, through: 20.0, by: 0.1) {
            XCTAssertEqual(LogoLoadingMotion(elapsed: elapsed, reduceMotion: true), still)
        }
        XCTAssertNotEqual(LogoLoadingMotion(elapsed: 0.6, reduceMotion: false), still)
    }

    func testReduceMotionSnapshotsStayGreenForAllPhasesAndAppearances() throws {
        for scheme in [ColorScheme.light, .dark] {
            let expected = try snapshot(phase: 0, scheme: scheme, reduceMotion: true)
            for phase in 1..<6 {
                XCTAssertEqual(try snapshot(phase: phase, scheme: scheme, reduceMotion: true), expected)
            }
            let image = XCTAttachment(data: expected, uniformTypeIdentifier: "public.png")
            image.name = "logo-reduce-motion-\(scheme)"
            image.lifetime = .keepAlways
            add(image)
        }
    }

    func testExistingTemplateLayersAndWhiteWingsAcrossEveryPhase() throws {
        let bundle = Bundle.main
        for layer in ["LaunchBootBody", "LaunchBootWingA", "LaunchBootWingB"] {
            XCTAssertNotNil(UIImage(named: layer, in: bundle, compatibleWith: nil), layer)
        }
        for scheme in [ColorScheme.light, .dark] {
            let baseline = try rgba(snapshot(phase: 0, scheme: scheme))
            // White interiors belong to the original wings (there is no other white content).
            let whitePixels = stride(from: 0, to: baseline.count, by: 4).filter {
                baseline[$0] > 240 && baseline[$0 + 1] > 240 && baseline[$0 + 2] > 240 && baseline[$0 + 3] == 255
            }
            XCTAssertGreaterThan(whitePixels.count, 3000, "The entire wing must stay white, including the wing pixels in the legacy Body layer")
            var phaseImages = Set<Data>()
            for phase in 0..<6 {
                let data = try snapshot(phase: phase, scheme: scheme)
                phaseImages.insert(data)
                let pixels = try rgba(data)
                XCTAssertEqual(pixels.count, baseline.count)
                for i in whitePixels {
                    let difference = zip(pixels[i..<i + 4], baseline[i..<i + 4]).map { abs(Int($0) - Int($1)) }.max() ?? 0
                    XCTAssertLessThanOrEqual(difference, 2, "wing phase \(phase), \(scheme)")
                }
            }
            XCTAssertEqual(phaseImages.count, 6, "All six body tints must differ")
        }
    }

    func testRetiredArtworkAbsentAndEveryFormerCallSiteUsesLogoLoader() throws {
        let ios = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        let root = ios.appendingPathComponent("AcademyWatch")
        let files = try XCTUnwrap(FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil))
        for case let file as URL in files where file.pathExtension == "swift" {
            let source = try String(contentsOf: file, encoding: .utf8)
            for retired in ["CleatLoader", "CleatDrawing", "CleatGeometry", "LaunchCleat", "ProgressView("] {
                XCTAssertFalse(source.contains(retired), "\(retired) in \(file.path)")
            }
        }
        let manifestURL = ios.appendingPathComponent("AcademyWatchTests/Fixtures/LogoLoaderCallSites.json")
        let manifest = try JSONDecoder().decode([String: Int].self, from: Data(contentsOf: manifestURL))
        XCTAssertGreaterThan(manifest.count, 30)
        for (path, count) in manifest {
            let source = try String(contentsOf: root.appendingPathComponent(path), encoding: .utf8)
            XCTAssertEqual(source.components(separatedBy: "WingLiftLoadingView(").count - 1, count, path)
        }
        for path in ["AcademyWatch/DesignSystem/CleatLoader.swift", "AcademyWatch/DesignSystem/CleatGeometry.swift",
                     "AcademyWatch/Assets.xcassets/LaunchCleat.imageset", "scripts/generate_cleat_launch.swift"] {
            XCTAssertFalse(FileManager.default.fileExists(atPath: ios.appendingPathComponent(path).path), path)
        }
        for path in ["project.yml", "AcademyWatch/Info.plist", "AcademyWatch.xcodeproj/project.pbxproj"] {
            XCTAssertFalse(try String(contentsOf: ios.appendingPathComponent(path)).contains("LaunchCleat"), path)
            XCTAssertFalse(try String(contentsOf: ios.appendingPathComponent(path)).contains("CleatLoader"), path)
        }
        let plist = try XCTUnwrap(PropertyListSerialization.propertyList(
            from: Data(contentsOf: root.appendingPathComponent("Info.plist")), format: nil) as? [String: Any])
        let launch = try XCTUnwrap(plist["UILaunchScreen"] as? [String: Any])
        XCTAssertEqual(launch["UIImageName"] as? String, "LaunchBoot")
        XCTAssertEqual(launch["UIColorName"] as? String, "LaunchBackground")
        XCTAssertEqual(launch["UIImageRespectsSafeAreaInsets"] as? Bool, false)
    }

    private func snapshot(phase: Int, scheme: ColorScheme, reduceMotion: Bool = false) throws -> Data {
        let renderer = ImageRenderer(content:
            WingLiftLoadingView(phase: phase, reduceMotionOverride: reduceMotion)
                .padding(24).background(AcademyColors.background)
                .environment(\.colorScheme, scheme))
        renderer.scale = 2
        return try XCTUnwrap(renderer.uiImage?.pngData())
    }

    private func rgba(_ png: Data) throws -> [UInt8] {
        let image = try XCTUnwrap(UIImage(data: png)?.cgImage)
        let bytesPerRow = image.width * 4
        var pixels = [UInt8](repeating: 0, count: bytesPerRow * image.height)
        try pixels.withUnsafeMutableBytes { storage in
            let context = try XCTUnwrap(CGContext(data: storage.baseAddress, width: image.width, height: image.height,
                bitsPerComponent: 8, bytesPerRow: bytesPerRow, space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue))
            context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        }
        return pixels
    }
}
