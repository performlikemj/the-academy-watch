import CryptoKit
import CoreGraphics
import Foundation
import XCTest

@MainActor
final class JourneyRunnerUITests: XCTestCase {
    private struct EvidenceClaim: Codable {
        let claim: String
        let source: String
    }

    private struct Preflight: Codable {
        let kind: String
        let note: String
    }

    private struct FixtureEvidence: Codable {
        let offeredInputs: [EvidenceClaim]
        let serverState: [EvidenceClaim]
        let serverStateReason: String?
        let layout: [EvidenceClaim]
        let preflight: Preflight

        private enum CodingKeys: String, CodingKey {
            case offeredInputs = "offered_inputs"
            case serverState = "server_state"
            case serverStateReason = "server_state_reason"
            case layout, preflight
        }
    }

    private struct Journey: Decodable {
        let version: String
        let name: String
        let journeyHash: String?
        let checkpointOnly: Bool
        let fixtureEvidence: FixtureEvidence
        let settleMS: Int
        let settleTimeoutMS: Int
        let settleQuietRatio: Double
        let steps: [Step]

        private enum CodingKeys: String, CodingKey {
            case version, name, steps
            case journeyHash = "journey_hash"
            case checkpointOnly = "checkpoint_only"
            case fixtureEvidence = "fixture_evidence"
            case settleMS = "settle_ms"
            case settleTimeoutMS = "settle_timeout_ms"
            case settleQuietRatio = "settle_quiet_ratio"
        }

        init(from decoder: Decoder) throws {
            let values = try decoder.container(keyedBy: CodingKeys.self)
            if let stringVersion = try? values.decode(String.self, forKey: .version) {
                version = stringVersion
            } else {
                version = String(try values.decode(Int.self, forKey: .version))
            }
            name = try values.decode(String.self, forKey: .name)
            journeyHash = try values.decodeIfPresent(String.self, forKey: .journeyHash)
            checkpointOnly = try values.decodeIfPresent(Bool.self, forKey: .checkpointOnly) ?? false
            guard let evidence = try values.decodeIfPresent(FixtureEvidence.self, forKey: .fixtureEvidence) else {
                throw DecodingError.dataCorruptedError(
                    forKey: .fixtureEvidence,
                    in: values,
                    debugDescription: "fixture_evidence is required for every journey."
                )
            }
            fixtureEvidence = evidence
            settleMS = try values.decodeIfPresent(Int.self, forKey: .settleMS) ?? 400
            settleTimeoutMS = try values.decodeIfPresent(Int.self, forKey: .settleTimeoutMS) ?? 4_000
            settleQuietRatio = try values.decodeIfPresent(Double.self, forKey: .settleQuietRatio) ?? 0.005
            steps = try values.decode([Step].self, forKey: .steps)
        }
    }

    private struct Step: Decodable {
        let id: String
        let expectation: String
        let action: Action
        let continueOnFailure: Bool
        let checkpoint: Bool
        let settle: SettleAction?
        let settleMS: Int?
        let settleTimeoutMS: Int?
        let settleQuietRatio: Double?

        private enum CodingKeys: String, CodingKey {
            case id, expectation, action, continueOnFailure, checkpoint, settle
            case settleMS = "settle_ms"
            case settleTimeoutMS = "settle_timeout_ms"
            case settleQuietRatio = "settle_quiet_ratio"
        }

        init(from decoder: Decoder) throws {
            let values = try decoder.container(keyedBy: CodingKeys.self)
            id = try values.decode(String.self, forKey: .id)
            expectation = try values.decode(String.self, forKey: .expectation)
            action = try values.decode(Action.self, forKey: .action)
            continueOnFailure = try values.decodeIfPresent(Bool.self, forKey: .continueOnFailure) ?? false
            checkpoint = try values.decodeIfPresent(Bool.self, forKey: .checkpoint) ?? false
            settle = try values.decodeIfPresent(SettleAction.self, forKey: .settle)
            settleMS = try values.decodeIfPresent(Int.self, forKey: .settleMS)
            settleTimeoutMS = try values.decodeIfPresent(Int.self, forKey: .settleTimeoutMS)
            settleQuietRatio = try values.decodeIfPresent(Double.self, forKey: .settleQuietRatio)
        }
    }

    private struct SettleAction: Decodable {
        let waitFor: LocatorAction
        let timeout: TimeInterval
    }

    private struct Action: Decodable {
        let launch: LaunchAction?
        let tap: LocatorAction?
        let type: TypeAction?
        let clearAndType: TypeAction?
        let swipe: SwipeAction?
        let waitFor: WaitAction?
        let assertVisible: LocatorAction?
        let screenshot: EmptyAction?
        let dismissKeyboard: EmptyAction?
        let systemAlert: SystemAlertAction?

        var populatedCount: Int {
            [launch != nil, tap != nil, type != nil, clearAndType != nil, swipe != nil,
             waitFor != nil, assertVisible != nil, screenshot != nil,
             dismissKeyboard != nil, systemAlert != nil].filter { $0 }.count
        }
    }

    private struct LaunchAction: Decodable {
        let args: [String]
        let env: [String: String]

        private enum CodingKeys: String, CodingKey { case args, env }

        init(from decoder: Decoder) throws {
            let values = try decoder.container(keyedBy: CodingKeys.self)
            args = try values.decodeIfPresent([String].self, forKey: .args) ?? []
            env = try values.decodeIfPresent([String: String].self, forKey: .env) ?? [:]
        }
    }

    private struct LocatorAction: Decodable {
        let id: String?
        let text: String?
        let why: String?
    }

    private struct TypeAction: Decodable {
        let id: String
        let text: String
    }

    private struct SwipeAction: Decodable {
        let dir: String
        let id: String?
    }

    private struct WaitAction: Decodable {
        let id: String?
        let text: String?
        let why: String?
        let timeout: TimeInterval
    }

    private struct SystemAlertAction: Decodable {
        let action: String
        let timeout: TimeInterval
    }

    private struct EmptyAction: Decodable {}

    private struct StepResult: Codable {
        let id: String
        let expectation: String
        let ok: Bool
        let note: String
        let shot: String
        let settleMSUsed: Int
        let settleReason: String
        let settleDiffRatio: Double?

        private enum CodingKeys: String, CodingKey {
            case id, expectation, ok, note, shot
            case settleMSUsed = "settle_ms_used"
            case settleReason = "settle_reason"
            case settleDiffRatio = "settle_diff_ratio"
        }
    }

    private struct SettleResult {
        let png: Data?
        let reason: String
        let diffRatio: Double?
    }

    private struct AttachmentRecord: Codable {
        let name: String
        let bytes: Int
        let kind: String
    }

    private struct JourneyResult: Codable {
        let name: String
        let journeyHash: String
        let fixtureEvidence: FixtureEvidence
        let checkpointOnly: Bool
        let checkpointReached: Bool
        let steps: [StepResult]
        let attachments: [AttachmentRecord]

        private enum CodingKeys: String, CodingKey {
            case name, steps, attachments
            case journeyHash = "journey_hash"
            case fixtureEvidence = "fixture_evidence"
            case checkpointOnly = "checkpoint_only"
            case checkpointReached = "checkpoint_reached"
        }
    }

    private struct LoadedJourney {
        let journey: Journey
        let digest: String
    }

    private enum RunnerError: LocalizedError {
        case invalidJourney(String)
        case missingElement(String)
        case notHittable(String)
        case unsupportedAction(String)

        var errorDescription: String? {
            switch self {
            case .invalidJourney(let message), .missingElement(let message),
                 .notHittable(let message), .unsupportedAction(let message):
                return message
            }
        }
    }

    func testJourneys() throws {
        let environment = ProcessInfo.processInfo.environment
        guard environment["SIM_JOURNEYS_JSON"] != nil || environment["SIM_JOURNEYS"] != nil else {
            throw XCTSkip("No simulator journey was injected.")
        }
        let loadedJourneys = try loadJourneys()
        guard !loadedJourneys.isEmpty else {
            throw RunnerError.invalidJourney("SIM_JOURNEYS_JSON or SIM_JOURNEYS must select at least one journey.")
        }

        for loaded in loadedJourneys {
            try run(loaded)
        }
    }

    private func run(_ loaded: LoadedJourney) throws {
        let journey = loaded.journey
        guard ["1.1", "1.2"].contains(journey.version) else {
            throw RunnerError.invalidJourney("Unsupported journey version \(journey.version); expected 1.1 or 1.2.")
        }
        guard !journey.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !journey.steps.isEmpty else {
            throw RunnerError.invalidJourney("Journey name and steps must not be empty.")
        }
        guard journey.settleMS > 0, journey.settleTimeoutMS > 0,
              validQuietRatio(journey.settleQuietRatio) else {
            throw RunnerError.invalidJourney("settle_ms and settle_timeout_ms must be greater than zero; settle_quiet_ratio must be between zero and one.")
        }
        try validateFixtureEvidence(journey.fixtureEvidence, journey: journey.name)
        if journey.checkpointOnly && !journey.steps.contains(where: { $0.checkpoint }) {
            throw RunnerError.invalidJourney("Journey \(journey.name) has no checkpoint:true step.")
        }

        let app = XCUIApplication()
        var results: [StepResult] = []
        var attachmentRecords: [AttachmentRecord] = []
        var checkpointReached = false

        for (index, step) in journey.steps.enumerated() {
            let base = "\(safeFilePart(journey.name))__\(String(format: "%03d", index + 1))-\(safeFilePart(step.id))"
            let fileName = "\(base).png"
            var ok = true
            var note = "Action completed."
            var settledPNG: Data?
            var settleMSUsed = 0
            var settleReason = "quiet"
            var settleDiffRatio: Double?

            do {
                guard !step.id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                    throw RunnerError.invalidJourney("Step id must not be empty.")
                }
                guard step.action.populatedCount == 1 else {
                    throw RunnerError.invalidJourney("Step \(step.id) must contain exactly one action.")
                }
                let settleMS = step.settleMS ?? journey.settleMS
                let settleTimeoutMS = step.settleTimeoutMS ?? journey.settleTimeoutMS
                let settleQuietRatio = step.settleQuietRatio ?? journey.settleQuietRatio
                guard settleMS > 0, settleTimeoutMS > 0, validQuietRatio(settleQuietRatio) else {
                    throw RunnerError.invalidJourney("Step \(step.id) settle timing must be greater than zero and settle_quiet_ratio must be between zero and one.")
                }
                if let predicate = step.settle, predicate.timeout <= 0 {
                    throw RunnerError.invalidJourney("Step \(step.id) settle timeout must be greater than zero.")
                }
                if let why = try perform(step.action, app: app) {
                    note = "Action completed. Text selector rationale: \(why)"
                }
                settleMSUsed = settleMS
                let settled = try settle(
                    step: step,
                    app: app,
                    settleMS: settleMS,
                    settleTimeoutMS: settleTimeoutMS,
                    settleQuietRatio: settleQuietRatio
                )
                settledPNG = settled.png
                settleReason = settled.reason
                settleDiffRatio = settled.diffRatio
                if settled.reason == "timeout" { note = "settle timeout" }
            } catch {
                ok = false
                note = bounded(error.localizedDescription, limit: 2_000)
                let dump = attachLabelDump(app: app, journey: journey.name, index: index, stepID: step.id)
                attachmentRecords.append(dump)
            }

            let png = settledPNG ?? XCUIScreen.main.screenshot().pngRepresentation
            let attachment = XCTAttachment(data: png, uniformTypeIdentifier: "public.png")
            attachment.name = fileName
            attachment.lifetime = .keepAlways
            add(attachment)
            attachmentRecords.append(AttachmentRecord(name: fileName, bytes: png.count, kind: "shot"))

            results.append(StepResult(
                id: step.id,
                expectation: step.expectation,
                ok: ok,
                note: note,
                shot: "shots/\(fileName)",
                settleMSUsed: settleMSUsed,
                settleReason: settleReason,
                settleDiffRatio: settleDiffRatio
            ))

            if step.checkpoint {
                checkpointReached = ok
                if journey.checkpointOnly { break }
            }
            if !ok && !step.continueOnFailure { break }
        }

        let result = JourneyResult(
            name: journey.name,
            journeyHash: journey.journeyHash ?? loaded.digest,
            fixtureEvidence: journey.fixtureEvidence,
            checkpointOnly: journey.checkpointOnly,
            checkpointReached: checkpointReached,
            steps: results,
            attachments: attachmentRecords
        )
        let data = try JSONEncoder().encode(result)
        let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
        attachment.name = "sim-steps__\(safeFilePart(journey.name)).json"
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func perform(_ action: Action, app: XCUIApplication) throws -> String? {
        if let launch = action.launch {
            let secretName = try launch.env.keys.first { key in
                try NSRegularExpression(pattern: "password|token|secret|bearer", options: .caseInsensitive)
                    .firstMatch(in: key, range: NSRange(key.startIndex..., in: key)) != nil
            }
            if let secretName {
                throw RunnerError.invalidJourney("Launch environment key is forbidden: \(secretName)")
            }
            if app.state != .notRunning { app.terminate() }
            app.launchArguments = launch.args
            app.launchEnvironment = launch.env
            app.launch()
            guard app.wait(for: .runningForeground, timeout: 10) else {
                throw RunnerError.missingElement("The app did not reach the foreground within 10 seconds.")
            }
            return nil
        }
        if let tap = action.tap {
            let (target, why) = try located(tap, app: app)
            guard target.waitForExistence(timeout: 8) else {
                throw RunnerError.missingElement("Tap target \(locatorDescription(tap)) did not exist within 8 seconds.")
            }
            guard waitForHittable(target, timeout: 8) else {
                throw RunnerError.notHittable("Tap target \(locatorDescription(tap)) was not hittable within 8 seconds.")
            }
            target.tap()
            return why
        }
        if let type = action.type {
            try typeText(type, app: app, clear: false)
            return nil
        }
        if let type = action.clearAndType {
            try typeText(type, app: app, clear: true)
            return nil
        }
        if let swipe = action.swipe {
            let target: XCUIElement = swipe.id.map { app.descendants(matching: .any)[$0] } ?? app
            if let id = swipe.id, !target.waitForExistence(timeout: 8) {
                throw RunnerError.missingElement("Swipe target id=\(id) did not exist within 8 seconds.")
            }
            switch swipe.dir {
            case "up": target.swipeUp()
            case "down": target.swipeDown()
            case "left": target.swipeLeft()
            case "right": target.swipeRight()
            default: throw RunnerError.unsupportedAction("Unsupported swipe direction \(swipe.dir).")
            }
            return nil
        }
        if let wait = action.waitFor {
            guard wait.timeout > 0 else {
                throw RunnerError.invalidJourney("waitFor timeout must be greater than zero.")
            }
            let locator = LocatorAction(id: wait.id, text: wait.text, why: wait.why)
            let (target, why) = try located(locator, app: app)
            guard target.waitForExistence(timeout: wait.timeout) else {
                throw RunnerError.missingElement("Wait target \(locatorDescription(locator)) did not exist within \(wait.timeout) seconds.")
            }
            return why
        }
        if let assertion = action.assertVisible {
            let (target, why) = try located(assertion, app: app)
            guard target.waitForExistence(timeout: 8) else {
                throw RunnerError.missingElement("Visible target \(locatorDescription(assertion)) did not exist within 8 seconds.")
            }
            return why
        }
        if action.dismissKeyboard != nil {
            if !app.keyboards.element.exists { return nil }
            for label in ["Done", "Return"] {
                let button = app.keyboards.buttons[label]
                if button.exists && button.isHittable { button.tap(); return nil }
            }
            app.swipeDown()
            return nil
        }
        if let alert = action.systemAlert {
            try handleSystemAlert(alert)
            return nil
        }
        if action.screenshot != nil { return nil }
        throw RunnerError.unsupportedAction("No supported action was supplied.")
    }

    private func typeText(_ action: TypeAction, app: XCUIApplication, clear: Bool) throws {
        guard !action.id.isEmpty else { throw RunnerError.invalidJourney("Type actions require id.") }
        let target = app.descendants(matching: .any)[action.id]
        guard target.waitForExistence(timeout: 8) else {
            throw RunnerError.missingElement("Type target id=\(action.id) did not exist within 8 seconds.")
        }
        guard waitForHittable(target, timeout: 8) else {
            throw RunnerError.notHittable("Type target id=\(action.id) was not hittable within 8 seconds.")
        }
        target.tap()
        if clear {
            target.press(forDuration: 1.0)
            let selectAll = app.menuItems["Select All"]
            if selectAll.waitForExistence(timeout: 2) {
                selectAll.tap()
                target.typeText(XCUIKeyboardKey.delete.rawValue)
            } else if let value = target.value as? String, !value.isEmpty {
                target.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: value.count))
            }
        }
        target.typeText(action.text)
    }

    private func handleSystemAlert(_ alert: SystemAlertAction) throws {
        guard alert.timeout > 0 else { throw RunnerError.invalidJourney("systemAlert timeout must be greater than zero.") }
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let candidates: [String]
        switch alert.action {
        case "allow": candidates = ["Allow", "Allow While Using App", "OK"]
        case "deny": candidates = ["Don’t Allow", "Don't Allow", "Deny"]
        case "dismiss": candidates = ["Cancel", "Not Now", "Close", "OK"]
        default: throw RunnerError.unsupportedAction("systemAlert action must be allow, deny, or dismiss.")
        }
        let deadline = Date().addingTimeInterval(alert.timeout)
        for name in candidates {
            let button = springboard.buttons[name]
            let remaining = max(0.1, deadline.timeIntervalSinceNow)
            if button.waitForExistence(timeout: remaining) && button.isHittable {
                button.tap()
                return
            }
        }
        throw RunnerError.missingElement("No matching SpringBoard \(alert.action) button appeared within \(alert.timeout) seconds.")
    }

    private func located(_ locator: LocatorAction, app: XCUIApplication) throws -> (XCUIElement, String?) {
        let hasID = !(locator.id ?? "").isEmpty
        let hasText = !(locator.text ?? "").isEmpty
        guard hasID != hasText else {
            throw RunnerError.invalidJourney("A locator must contain exactly one of id or text.")
        }
        if let id = locator.id { return (app.descendants(matching: .any)[id], nil) }
        guard let why = locator.why, !why.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw RunnerError.invalidJourney("A text locator requires a non-empty why string.")
        }
        let text = locator.text ?? ""
        let predicate = NSPredicate(format: "label == %@ OR value == %@", text, text)
        return (app.descendants(matching: .any).matching(predicate).firstMatch, why)
    }

    private func waitForHittable(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == true AND hittable == true"),
            object: element
        )
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }

    private func settle(
        step: Step,
        app: XCUIApplication,
        settleMS: Int,
        settleTimeoutMS: Int,
        settleQuietRatio: Double
    ) throws -> SettleResult {
        let deadline = Date().addingTimeInterval(TimeInterval(settleTimeoutMS) / 1_000)
        var reason = "quiet"

        if let predicate = step.settle {
            reason = "predicate"
            let target = try settleElement(predicate.waitFor, app: app)
            let available = min(predicate.timeout, max(0, deadline.timeIntervalSinceNow))
            if available <= 0 || !waitForHittable(target, timeout: available) {
                return SettleResult(png: nil, reason: "timeout", diffRatio: nil)
            }
        } else if let id = step.action.tap?.id, id.hasPrefix("tab-bar-") {
            reason = "selected"
            let target = app.descendants(matching: .any)[id]
            let available = min(3, max(0, deadline.timeIntervalSinceNow))
            if available <= 0 || !waitForSelected(target, timeout: available) {
                return SettleResult(png: nil, reason: "timeout", diffRatio: nil)
            }
        }

        var previous = XCUIScreen.main.screenshot()
        var previousPNG = previous.pngRepresentation
        var lastDiffRatio: Double?
        let quietSeconds = TimeInterval(settleMS) / 1_000
        while deadline.timeIntervalSinceNow >= quietSeconds {
            waitForInterval(quietSeconds)
            let current = XCUIScreen.main.screenshot()
            let currentPNG = current.pngRepresentation
            let diffRatio = currentPNG == previousPNG ? 0 : try pixelDiffRatio(previous, current)
            lastDiffRatio = diffRatio
            if diffRatio <= settleQuietRatio {
                return SettleResult(png: currentPNG, reason: reason, diffRatio: diffRatio)
            }
            previous = current
            previousPNG = currentPNG
        }
        return SettleResult(png: previousPNG, reason: "timeout", diffRatio: lastDiffRatio)
    }

    private func pixelDiffRatio(_ previous: XCUIScreenshot, _ current: XCUIScreenshot) throws -> Double {
        guard let previousImage = previous.image.cgImage,
              let currentImage = current.image.cgImage,
              let previousPixels = sampledPixels(previousImage),
              let currentPixels = sampledPixels(currentImage),
              previousPixels.count == currentPixels.count else {
            throw RunnerError.unsupportedAction("Could not decode simulator screenshots for quiet-frame comparison.")
        }

        let channelTolerance = 8
        var changedPixels = 0
        for offset in stride(from: 0, to: previousPixels.count, by: 4) {
            let changed = (0..<4).contains { channel in
                abs(Int(previousPixels[offset + channel]) - Int(currentPixels[offset + channel])) > channelTolerance
            }
            if changed { changedPixels += 1 }
        }
        return Double(changedPixels) / Double(previousPixels.count / 4)
    }

    private func sampledPixels(_ image: CGImage) -> [UInt8]? {
        let width = 120
        let height = 260
        let bytesPerRow = width * 4
        var pixels = [UInt8](repeating: 0, count: bytesPerRow * height)
        let rendered = pixels.withUnsafeMutableBytes { buffer -> Bool in
            guard let address = buffer.baseAddress,
                  let context = CGContext(
                    data: address,
                    width: width,
                    height: height,
                    bitsPerComponent: 8,
                    bytesPerRow: bytesPerRow,
                    space: CGColorSpaceCreateDeviceRGB(),
                    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue
                  ) else { return false }
            context.interpolationQuality = .low
            context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        return rendered ? pixels : nil
    }

    private func validQuietRatio(_ value: Double) -> Bool {
        value.isFinite && value >= 0 && value <= 1
    }

    private func settleElement(_ locator: LocatorAction, app: XCUIApplication) throws -> XCUIElement {
        let hasID = !(locator.id ?? "").isEmpty
        let hasText = !(locator.text ?? "").isEmpty
        guard hasID != hasText else {
            throw RunnerError.invalidJourney("A settle waitFor locator must contain exactly one of id or text.")
        }
        if let id = locator.id { return app.descendants(matching: .any)[id] }
        let text = locator.text ?? ""
        let predicate = NSPredicate(format: "label == %@ OR value == %@", text, text)
        return app.descendants(matching: .any).matching(predicate).firstMatch
    }

    private func waitForSelected(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        repeat {
            if element.exists && element.isSelected { return true }
            waitForInterval(min(0.05, max(0, deadline.timeIntervalSinceNow)))
        } while deadline.timeIntervalSinceNow > 0
        return element.exists && element.isSelected
    }

    private func waitForInterval(_ seconds: TimeInterval) {
        guard seconds > 0 else { return }
        RunLoop.current.run(until: Date().addingTimeInterval(seconds))
    }

    private func attachLabelDump(app: XCUIApplication, journey: String, index: Int, stepID: String) -> AttachmentRecord {
        let elements = app.staticTexts.allElementsBoundByIndex + app.buttons.allElementsBoundByIndex
        let rows = elements.prefix(200).enumerated().map { offset, element in
            let identifier = element.identifier.replacingOccurrences(of: "\n", with: " ")
            let label = element.label.replacingOccurrences(of: "\n", with: " ")
            return "\(offset + 1)\tidentifier=\(identifier)\tlabel=\(label)"
        }
        let body = (["visible staticTexts/buttons (first 200)"] + rows).joined(separator: "\n") + "\n"
        let data = Data(body.utf8)
        let name = "sim-labels__\(safeFilePart(journey))__\(String(format: "%03d", index + 1))-\(safeFilePart(stepID)).txt"
        let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.plain-text")
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        return AttachmentRecord(name: name, bytes: data.count, kind: "diagnostic")
    }

    private func loadJourneys() throws -> [LoadedJourney] {
        let environment = ProcessInfo.processInfo.environment
        if let inline = environment["SIM_JOURNEYS_JSON"] {
            let data = Data(inline.utf8)
            let journeys = try JSONDecoder().decode([Journey].self, from: data)
            return journeys.map { LoadedJourney(journey: $0, digest: $0.journeyHash ?? sha256(data)) }
        }
        if let names = environment["SIM_JOURNEYS"] {
            return try names.split(separator: ",").map { rawName in
                let name = String(rawName)
                guard name.range(of: "^[a-z0-9-]+$", options: .regularExpression) != nil else {
                    throw RunnerError.invalidJourney("Invalid bundled journey resource name: \(name)")
                }
                let url = try XCTUnwrap(
                    Bundle(for: Self.self).url(forResource: name, withExtension: "json"),
                    "Bundled journey resource was not found: \(name).json"
                )
                let data = try Data(contentsOf: url)
                return LoadedJourney(journey: try JSONDecoder().decode(Journey.self, from: data), digest: sha256(data))
            }
        }
        throw RunnerError.invalidJourney("Set SIM_JOURNEYS_JSON content or validated SIM_JOURNEYS resource names.")
    }

    private func validateFixtureEvidence(_ evidence: FixtureEvidence, journey: String) throws {
        let claims = evidence.offeredInputs + evidence.serverState + evidence.layout
        guard !evidence.offeredInputs.isEmpty, !evidence.layout.isEmpty else {
            throw RunnerError.invalidJourney("Journey \(journey) fixture_evidence requires offered_inputs and layout.")
        }
        if evidence.serverState.isEmpty && (evidence.serverStateReason ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            throw RunnerError.invalidJourney("Journey \(journey) with empty server_state requires server_state_reason.")
        }
        for claim in claims {
            guard !claim.claim.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  claim.source.range(of: "^.+:[0-9]+(?:-[0-9]+)?$", options: .regularExpression) != nil else {
                throw RunnerError.invalidJourney("Journey \(journey) has invalid fixture evidence claim/source.")
            }
        }
        guard ["none", "api"].contains(evidence.preflight.kind),
              !evidence.preflight.note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw RunnerError.invalidJourney("Journey \(journey) preflight requires kind none|api and a note.")
        }
    }

    private func locatorDescription(_ locator: LocatorAction) -> String {
        if let id = locator.id { return "id=\(id)" }
        return "text=\(locator.text ?? "") why=\(locator.why ?? "")"
    }

    private func safeFilePart(_ value: String) -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "._-"))
        let mapped = value.unicodeScalars.map { allowed.contains($0) ? Character(String($0)) : "-" }
        let result = String(mapped).trimmingCharacters(in: CharacterSet(charactersIn: "-"))
        return result.isEmpty ? "step" : result
    }

    private func bounded(_ value: String, limit: Int) -> String {
        guard value.count > limit else { return value }
        return String(value.prefix(limit))
    }

    private func sha256(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
}
