import SwiftUI
import UIKit
import XCTest
@testable import AcademyWatch

final class FloodlightDesignTests: XCTestCase {
    func testBundledFontsRegisterByTheirPostScriptNames() throws {
        for name in ["InstrumentSerif-Regular", "InstrumentSerif-Italic", "Geist-Regular", "GeistMono-Regular"] {
            let font = try XCTUnwrap(UIFont(name: name, size: 16), "Missing bundled font: \(name)")
            XCTAssertEqual(font.fontName, name)
        }
        let fonts = try XCTUnwrap(Bundle.main.object(forInfoDictionaryKey: "UIAppFonts") as? [String])
        XCTAssertEqual(fonts.count, 4)
        for file in fonts { XCTAssertNotNil(Bundle.main.url(forResource: file, withExtension: nil)) }
    }

    func testTextAndPrimaryControlsHaveAAContrastInBothAppearances() {
        for style in [UIUserInterfaceStyle.light, .dark] {
            let traits = UITraitCollection(userInterfaceStyle: style)
            let background = UIColor(AcademyColors.background).resolvedColor(with: traits)
            for token in [AcademyColors.text, AcademyColors.secondaryText, AcademyColors.accent, AcademyColors.good, AcademyColors.warnText, AcademyColors.danger] {
                XCTAssertGreaterThanOrEqual(contrast(UIColor(token).resolvedColor(with: traits), background), 4.5)
            }
            XCTAssertGreaterThanOrEqual(contrast(UIColor(AcademyColors.primaryFill).resolvedColor(with: traits), UIColor(AcademyColors.onPrimary).resolvedColor(with: traits)), 4.5)
        }
    }

    private func contrast(_ first: UIColor, _ second: UIColor) -> Double {
        let a = luminance(first), b = luminance(second)
        return (max(a, b) + 0.05) / (min(a, b) + 0.05)
    }
    private func luminance(_ color: UIColor) -> Double {
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        color.getRed(&r, green: &g, blue: &b, alpha: &a)
        let linear = [r, g, b].map { Double($0) <= 0.04045 ? Double($0) / 12.92 : Foundation.pow((Double($0) + 0.055) / 1.055, 2.4) }
        return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722
    }

    #if DEBUG && targetEnvironment(simulator)
    func testReviewTransportRejectsMutationsAndUnknownRoutes() {
        var request = URLRequest(url: URL(string: "https://example.invalid/api/auth/request-code")!)
        request.httpMethod = "POST"
        XCTAssertThrowsError(try FloodlightPreview.data(for: request))
        request.httpMethod = "GET"
        request.url = URL(string: "https://example.invalid/api/unmatched-review-route")!
        XCTAssertThrowsError(try FloodlightPreview.data(for: request))
    }

    func testReviewContactAndCompareFixturesDecodeWithoutPersonalMedia() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let contacts = try decoder.decode(ContactRequestsResponse.self, from: FloodlightPreview.fixture("contact_requests_sent"))
        XCTAssertFalse(contacts.requests.isEmpty)
        XCTAssertTrue(contacts.requests.allSatisfy { $0.participants.player.displayName?.hasPrefix("Sample") != false })
        let comparison = try decoder.decode(CompareResponse.self, from: FloodlightPreview.fixture("scout_compare_gk_outfielder"))
        XCTAssertEqual(comparison.players.count, 2)
        XCTAssertTrue(comparison.players.allSatisfy { $0.profile.playerName.hasPrefix("Sample") && $0.profile.photoURL == nil })
    }
    #endif
}
