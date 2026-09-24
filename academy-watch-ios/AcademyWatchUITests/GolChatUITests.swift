import XCTest

/// Offline UI coverage plus an opt-in local integration test. Never uses the production API.
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
        assertMoneyFence(app)
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

    func testOfflineLandingRoles() {
        continueAfterFailure = false
        for role in ["scout", "player", "club"] {
            let app = offlineApp(role)
            app.launch()
            let tab = role == "scout" ? "Scout Desk" : "Home"
            XCTAssertTrue(app.tabBars.buttons[tab].waitForExistence(timeout: 10))
            XCTAssertTrue(app.tabBars.buttons[tab].isSelected)
            XCTAssertTrue(app.buttons["gol-landing-entry"].waitForExistence(timeout: 10))
            XCTAssertTrue(app.buttons["gol-landing-entry"].isHittable)
            capture("fix1-landing-\(role)", app)
            tap(app.buttons["gol-landing-entry"])
            XCTAssertTrue(app.textFields["gol-composer"].waitForExistence(timeout: 10))
            assertMoneyFence(app)
            tap(app.buttons["gol-close"])
            tap(app.tabBars.buttons["Account"])
            tap(app.buttons["gol-entry"])
            XCTAssertTrue(app.textFields["gol-composer"].waitForExistence(timeout: 10))
            app.terminate()
        }
    }

    func testOfflineScoutLoadingCardHidesNavigationUntilLoaded() {
        continueAfterFailure = false
        let app = offlineApp("scout")
        app.launchArguments += ["-scoutDeskSeasonDelaySeconds", "15"]
        app.launch()
        defer { app.terminate() }
        XCTAssertTrue(app.otherElements["initial-load-feedback"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.navigationBars["Scout Desk"].exists)
        XCTAssertFalse(app.buttons["gol-landing-entry"].exists)
        XCTAssertFalse(app.buttons["Add a player"].exists)
        capture("fix2-scout-initial-loading", app)
        XCTAssertTrue(app.buttons["gol-landing-entry"].waitForExistence(timeout: 25))
        XCTAssertTrue(app.navigationBars["Scout Desk"].exists)
        XCTAssertTrue(app.buttons["gol-landing-entry"].isHittable)
        capture("fix2-scout-loaded", app)
    }

    func testOfflineStopButtonRetainsCutShortAnswerOnReopen() {
        continueAfterFailure = false
        let app = offlineApp("scout")
        app.launch()
        defer { app.terminate() }
        tap(app.buttons["gol-landing-entry"])
        tap(app.buttons["gol-suggestion-0"])
        let answer = app.staticTexts["gol-answer"].firstMatch
        XCTAssertTrue(answer.waitForExistence(timeout: 10))
        tap(app.buttons["gol-stop"])
        XCTAssertTrue(app.staticTexts["gol-cut-short"].waitForExistence(timeout: 10))
        let partial = answer.label
        XCTAssertFalse(partial.contains("Synthetic offline football guidance."))
        tap(app.buttons["gol-close"])
        tap(app.buttons["gol-landing-entry"])
        XCTAssertTrue(app.staticTexts["gol-cut-short"].waitForExistence(timeout: 10))
        XCTAssertEqual(answer.label, partial)
        XCTAssertFalse(app.buttons["gol-stop"].exists)
        assertMoneyFence(app)
    }

    func testOfflineStreamingCloseReopenMarkdownAndExhaustionMoneyFence() {
        continueAfterFailure = false
        let app = offlineApp("scout")
        app.launch()
        defer { app.terminate() }
        tap(app.buttons["gol-landing-entry"])
        assertMoneyFence(app)
        tap(app.buttons["gol-suggestion-0"])
        let answer = app.staticTexts["gol-answer"].firstMatch
        XCTAssertTrue(answer.waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["gol-stop"].exists)
        // Pull down the sheet from its top edge: it must stay presented during the stream.
        app.navigationBars["GOL"].swipeDown()
        XCTAssertTrue(app.buttons["gol-close"].exists)
        XCTAssertTrue(app.buttons["gol-stop"].exists)
        XCTAssertFalse(answer.label.contains("Synthetic offline football guidance."))
        tap(app.buttons["gol-close"])
        XCTAssertTrue(app.buttons["gol-landing-entry"].waitForExistence(timeout: 10))
        // Let the nine-second fixture stream finish while the actual sheet is dismissed.
        Thread.sleep(forTimeInterval: 10)
        tap(app.buttons["gol-landing-entry"])
        XCTAssertTrue(answer.waitForExistence(timeout: 10))
        XCTAssertEqual(answer.label, "Academy progress\n\n- Watch playing time.\n- Track development.\n\nSynthetic offline football guidance.")
        XCTAssertFalse(app.buttons["gol-stop"].exists)
        XCTAssertFalse(app.staticTexts["gol-cut-short"].exists)
        capture("fix2-reopened-after-close-complete-answer", app)
        assertMoneyFence(app)
        tap(app.buttons["gol-new-chat"])
        tap(app.buttons["gol-suggestion-0"])
        XCTAssertTrue(answer.waitForExistence(timeout: 10))
        let finished = NSPredicate(format: "exists == false")
        expectation(for: finished, evaluatedWith: app.buttons["gol-stop"])
        waitForExpectations(timeout: 20)
        XCTAssertTrue(answer.label.contains("- Watch playing time."))
        XCTAssertTrue(answer.label.contains("Track development."))
        XCTAssertFalse(answer.label.contains("**"))
        XCTAssertEqual(app.staticTexts["gol-usage"].label, "Questions left: 0")
        let completed = answer.label
        capture("fix1-markdown-answer", app)
        assertMoneyFence(app)
        // Completed answers can be dismissed interactively and remain in the root-owned model.
        app.navigationBars["GOL"].swipeDown()
        XCTAssertTrue(app.buttons["gol-landing-entry"].waitForExistence(timeout: 10))
        tap(app.buttons["gol-landing-entry"])
        XCTAssertEqual(answer.label, completed)
        capture("fix1-reopened-complete-answer", app)
        let composer = app.textFields["gol-composer"]
        tap(composer)
        composer.typeText("One more question")
        tap(app.buttons["gol-send"])
        XCTAssertTrue(app.staticTexts["You've used all your GOL questions."].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts.matching(identifier: "gol-question").count, 1)
        XCTAssertEqual(app.staticTexts.matching(identifier: "gol-answer").count, 1)
        XCTAssertFalse(app.buttons["gol-retry"].exists)
        XCTAssertFalse(app.buttons["gol-send"].isEnabled)
        XCTAssertEqual(app.staticTexts["gol-usage"].label, "Questions left: 0")
        assertMoneyFence(app)
        capture("fix1-out-of-questions", app)
        // A rejected first question leaves no bubbles, but New chat must still work.
        tap(app.buttons["gol-new-chat"])
        XCTAssertFalse(app.staticTexts["gol-error"].exists)
        XCTAssertFalse(app.staticTexts["gol-usage"].exists)
        tap(app.buttons["gol-suggestion-0"])
        XCTAssertTrue(app.staticTexts["You've used all your GOL questions."].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts.matching(identifier: "gol-question").count, 0)
        XCTAssertTrue(app.buttons["gol-new-chat"].isEnabled)
        tap(app.buttons["gol-new-chat"])
        XCTAssertFalse(app.staticTexts["gol-error"].exists)
        tap(app.buttons["gol-suggestion-0"])
        XCTAssertTrue(app.staticTexts["You've used all your GOL questions."].waitForExistence(timeout: 10))
        tap(app.buttons["gol-close"])
        tap(app.buttons["gol-landing-entry"])
        XCTAssertFalse(app.staticTexts["gol-error"].exists)
        XCTAssertFalse(app.staticTexts["gol-usage"].exists)
        XCTAssertTrue(app.buttons["gol-suggestion-0"].isEnabled)
        // Reopening permits a fresh request; the server still decides access.
        tap(app.buttons["gol-suggestion-0"])
        XCTAssertTrue(app.staticTexts["You've used all your GOL questions."].waitForExistence(timeout: 10))
        assertMoneyFence(app)
        capture("fix3-first-question-block-retry", app)
    }

    private func offlineApp(_ role: String) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-resetExperienceRole", "-experienceRole", role, "-experienceFixture", role]
        return app
    }

    private func assertMoneyFence(_ app: XCUIApplication) {
        for forbidden in ["credit", "buy", "purchase", "price", "top up", "billing", "subscribe", "$", "website", "/account/billing"] {
            let query = NSPredicate(format: "label CONTAINS[c] %@", forbidden)
            XCTAssertEqual(app.buttons.matching(query).count, 0, forbidden)
            XCTAssertEqual(app.staticTexts.matching(query).count, 0, forbidden)
            XCTAssertEqual(app.links.matching(query).count, 0, forbidden)
        }
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
