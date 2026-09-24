import XCTest

/// Opt-in local integration test. Never runs against the production API.
final class GolChatUITests: XCTestCase {
    func testLocalSignInSuggestionStreamingAndExhaustedQuestions() throws {
        let environment = ProcessInfo.processInfo.environment
        guard let raw = environment["GOL_LOCAL_API_URL"],
            let url = URL(string: raw), url.host == "127.0.0.1", url.scheme == "http"
        else {
            throw XCTSkip("Start sim/fixtures/gol_local_server.py and set TEST_RUNNER_GOL_LOCAL_API_URL.")
        }
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-resetExperienceRole", "-experienceRole", "scout", "-initialTab", "account"]
        app.launchEnvironment["ACADEMY_LOCAL_API_URL"] = raw
        app.launch()
        defer { app.terminate() }
        tap(app.buttons["gol-entry"])
        XCTAssertTrue(app.buttons["gol-sign-in"].waitForExistence(timeout: 10))
        capture("01-gol-sign-in", app)
        tap(app.buttons["gol-sign-in"])
        let email = app.textFields["signin-email"]
        XCTAssertTrue(email.waitForExistence(timeout: 10))
        email.tap()
        email.typeText("gol-ios-local@example.test")
        tap(app.buttons["signin-send-code"])
        let code = app.textFields["signin-code"]
        XCTAssertTrue(code.waitForExistence(timeout: 15))
        code.tap()
        code.typeText("24680246802")
        tap(app.buttons["signin-verify"])
        let suggestion = app.buttons["gol-suggestion-0"]
        XCTAssertTrue(suggestion.waitForExistence(timeout: 15))
        capture("02-gol-suggestions", app)
        suggestion.tap()
        XCTAssertTrue(app.buttons["gol-stop"].waitForExistence(timeout: 15))
        capture("03-gol-streaming", app)
        XCTAssertTrue(app.staticTexts["gol-answer"].firstMatch.waitForExistence(timeout: 90))
        let finished = NSPredicate(format: "exists == false")
        expectation(for: finished, evaluatedWith: app.buttons["gol-stop"])
        waitForExpectations(timeout: 150)
        XCTAssertFalse(app.staticTexts["gol-error"].exists)
        XCTAssertFalse(app.staticTexts["gol-answer"].firstMatch.label.isEmpty)
        capture("04-gol-answer", app)
        tap(app.buttons["gol-new-chat"])
        tap(app.buttons["gol-suggestion-0"])
        XCTAssertTrue(app.staticTexts["You've used all your GOL questions."].waitForExistence(timeout: 20))
        XCTAssertFalse(app.buttons["gol-retry"].exists)
        XCTAssertFalse(app.buttons["gol-send"].isEnabled)
        for forbidden in ["buy", "top up", "billing", "purchase", "$", "website"] {
            let query = NSPredicate(format: "label CONTAINS[c] %@", forbidden)
            XCTAssertEqual(app.buttons.matching(query).count, 0)
            XCTAssertEqual(app.staticTexts.matching(query).count, 0)
            XCTAssertEqual(app.links.matching(query).count, 0)
        }
        capture("05-gol-exhausted", app)
    }

    func testOfflineEntrySupportsAccessibilityTextSize() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = [
            "-resetExperienceRole", "-experienceRole", "scout", "-experienceFixture", "scout",
            "-initialTab", "account", "-UIPreferredContentSizeCategoryName",
            "UICTContentSizeCategoryAccessibilityXXXL",
        ]
        app.launch()
        defer { app.terminate() }
        tap(app.buttons["gol-entry"])
        XCTAssertTrue(app.textFields["gol-composer"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.textFields["gol-composer"].isHittable)
        XCTAssertTrue(app.buttons["gol-close"].isHittable)
        capture("06-gol-accessibility-text", app)
    }

    private func tap(_ element: XCUIElement) {
        XCTAssertTrue(element.waitForExistence(timeout: 10))
        element.tap()
    }

    private func capture(_ name: String, _ app: XCUIApplication) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
