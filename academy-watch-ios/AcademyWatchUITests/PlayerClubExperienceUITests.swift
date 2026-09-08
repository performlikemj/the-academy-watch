import XCTest

/// These walks use explicit offline API fixtures. They never request login
/// emails, upload media, or change production player/club records.
final class PlayerClubExperienceUITests: XCTestCase {
    private var app: XCUIApplication!
    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
    }
    override func tearDownWithError() throws {
        app.terminate()
        app = nil
    }
    private func launch(_ mode: String) {
        app.launchArguments = ["-experienceFixture", mode, "-initialTab", "home"]
        app.launch()
    }
    func testScoutExperienceUsesScoutingTabsAndCanChangeFromAccount() {
        launch("player")
        tap(app.buttons["home-role-scout"])
        assertScoutTabs()
        capture("scout-home-scout-desk")

        tap(app.tabBars.buttons["Account"])
        chooseHomeExperience("Player")
        XCTAssertTrue(app.tabBars.buttons["Home"].waitForExistence(timeout: 8))
        XCTAssertTrue(app.tabBars.buttons["Home"].isSelected)
        XCTAssertEqual(app.tabBars.buttons.count, 5)
        capture("scout-home-player-home")

        tap(app.tabBars.buttons["Account"])
        chooseHomeExperience("Scout")
        assertScoutTabs()
        capture("scout-home-scout-restored")
    }
    func testPlayerCanReturnToProfileEditAndReadFeedback() {
        launch("player")
        tap(app.buttons["home-role-player"])
        capture("player-home")
        tap(app.buttons["home-my-profiles"])
        tap(app.buttons["my-profile-71"])
        tap(app.buttons["my-profile-edit"])
        XCTAssertTrue(app.textFields["profile-editor-position"].waitForExistence(timeout: 8))
        tap(app.buttons["profile-editor-save"])
        XCTAssertTrue(
            app.staticTexts["Profile saved. Changes appear publicly when approved."].waitForExistence(timeout: 8))
        capture("profile-editor")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        tap(app.buttons["my-profile-feedback"])
        tap(app.buttons.containing(.staticText, identifier: "Building your next pass").firstMatch)
        tap(app.buttons["feedback-acknowledge"])
        XCTAssertTrue(
            app.staticTexts["Acknowledged — your coach can see you've read this."].waitForExistence(timeout: 8))
        capture("feedback-acknowledged")
    }
    func testPlayerMustExplicitlyAcceptClubInvitation() {
        launch("player")
        tap(app.buttons["home-role-player"])
        tap(app.buttons["home-club-invitations"])
        tap(app.buttons["Accept invitation"])
        tap(app.sheets.buttons["Accept invitation"])
        XCTAssertTrue(
            app.staticTexts["You're connected. Find private coach feedback in My profiles."].waitForExistence(
                timeout: 8))
        capture("club-connection")
    }
    func testCancellingInvitationKeepsPlayerUnconnected() {
        launch("player")
        tap(app.buttons["home-role-player"])
        tap(app.buttons["home-club-invitations"])
        tap(app.buttons["Accept invitation"])
        XCTAssertTrue(app.sheets.firstMatch.waitForExistence(timeout: 8))
        capture("invitation-confirmation")
        if app.buttons["Cancel"].exists {
            tap(app.buttons["Cancel"])
        } else {
            // iOS 26 can present a popover with an outside-dismiss region
            // instead of rendering the confirmation dialog's cancel button.
            let dismissRegion = app.otherElements["PopoverDismissRegion"]
            XCTAssertTrue(dismissRegion.waitForExistence(timeout: 8))
            dismissRegion.coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.75)).tap()
        }
        let dismissed = NSPredicate(format: "exists == false")
        expectation(for: dismissed, evaluatedWith: app.sheets.firstMatch)
        waitForExpectations(timeout: 8)
        XCTAssertTrue(app.buttons["Accept invitation"].exists)
        XCTAssertFalse(app.buttons["Leave club connection"].exists)
        capture("invitation-cancelled")
    }
    func testOpeningFeedbackDoesNotAcknowledgeIt() {
        launch("player")
        tap(app.buttons["home-role-player"])
        tap(app.buttons["home-my-profiles"])
        tap(app.buttons["my-profile-71"])
        tap(app.buttons["my-profile-feedback"])
        tap(app.buttons.containing(.staticText, identifier: "Building your next pass").firstMatch)
        XCTAssertTrue(app.buttons["feedback-acknowledge"].waitForExistence(timeout: 8))
        capture("feedback-unacknowledged")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertTrue(app.staticTexts["Awaiting acknowledgment"].waitForExistence(timeout: 8))
    }
    func testApprovedProfileOffersPublicSharing() {
        launch("player")
        tap(app.buttons["home-role-player"])
        tap(app.buttons["home-my-profiles"])
        tap(app.buttons["my-profile-71"])
        XCTAssertTrue(app.buttons["my-profile-share"].waitForExistence(timeout: 8))
        capture("approved-profile")
    }
    func testPendingProfileHasReturnPathWithoutOwnerActions() {
        launch("pending")
        tap(app.buttons["home-role-player"])
        tap(app.buttons["home-my-profiles"])
        tap(app.buttons["my-profile-71"])
        XCTAssertTrue(app.staticTexts["Pending"].waitForExistence(timeout: 8))
        XCTAssertFalse(app.buttons["my-profile-edit"].exists)
        XCTAssertFalse(app.buttons["my-profile-share"].exists)
        capture("pending-profile")
    }
    func testCoachCanFindWorkspaceAndVerification() {
        launch("club")
        tap(app.buttons["home-role-club"])
        tap(app.buttons["home-my-club"])
        XCTAssertTrue(app.buttons["my-club-workspace"].waitForExistence(timeout: 8))
        capture("club-home")
        tap(app.buttons["my-club-verification"])
        XCTAssertTrue(app.staticTexts["Represent a club or academy?"].waitForExistence(timeout: 8))
    }
    func testFindOrCreateExplainsRequiredAgeBeforeSubmission() {
        launch("player")
        tap(app.buttons["home-role-player"])
        tap(app.buttons["home-my-profiles"])
        tap(app.buttons["my-profiles-add"])
        let search = app.textFields["player-onboarding-name-search"]
        tap(search)
        search.typeText("Maya New\n")
        tap(app.buttons["player-create-after-search"])
        tap(app.textFields["local-player-name"])
        app.textFields["local-player-name"].typeText("Maya New")
        app.swipeUp()
        app.swipeUp()
        tap(app.buttons["local-player-submit"])
        let ageError = app.staticTexts["Add your birth date or birth year to confirm you are 18 or older."]
        XCTAssertTrue(ageError.waitForExistence(timeout: 8))
        XCTAssertTrue(ageError.isHittable, "Validation must bring the age requirement into view")
        XCTAssertFalse(app.otherElements["local-player-pending"].exists)
        capture("age-verification")
    }

    func testPlayerCanPractiseAndRequestCoachReview() {
        openDevelopment("development")
        capture("development-action")
        let reflection = app.textViews["development-reflection"]
        tap(reflection)
        reflection.typeText("Scanning early helped me find the forward pass.")
        tap(app.buttons["development-ready"])
        XCTAssertTrue(app.staticTexts["Ready for coach review"].waitForExistence(timeout: 8))
        capture("development-ready-for-review")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        tap(app.buttons.containing(.staticText, identifier: "Building your next pass").firstMatch)
        XCTAssertTrue(app.staticTexts["Ready for coach review"].waitForExistence(timeout: 8))
        XCTAssertEqual(
            app.textViews["development-reflection"].value as? String,
            "Scanning early helped me find the forward pass.")
        XCTAssertTrue(
            app.buttons["feedback-acknowledge"].exists, "Practice does not acknowledge feedback")
    }
    func testPlayerCanReadCoachDevelopmentReview() {
        openDevelopment("reviewed")
        let review = app.staticTexts[
            "Good progress, Maya. Keep the early scan when we add pressure next session."]
        XCTAssertTrue(review.waitForExistence(timeout: 8))
        for _ in 0..<5 {
            if review.isHittable { break }
            app.swipeUp()
        }
        capture("development-coach-review")
    }
    private func openDevelopment(_ mode: String) {
        launch(mode)
        tap(app.buttons["home-role-player"])
        tap(app.buttons["home-my-profiles"])
        tap(app.buttons["my-profile-71"])
        tap(app.buttons["my-profile-feedback"])
        tap(app.buttons.containing(.staticText, identifier: "Building your next pass").firstMatch)
        XCTAssertTrue(app.staticTexts["development-focus"].waitForExistence(timeout: 8))
    }

    private func chooseHomeExperience(_ role: String) {
        tap(app.buttons["account-home-experience"])
        tap(app.buttons[role])
    }

    private func assertScoutTabs() {
        XCTAssertTrue(app.tabBars.buttons["Scout Desk"].waitForExistence(timeout: 8))
        XCTAssertTrue(app.tabBars.buttons["Scout Desk"].isSelected)
        XCTAssertFalse(app.tabBars.buttons["Home"].exists)
        XCTAssertEqual(app.tabBars.buttons.count, 4)
    }

    private func tap(_ element: XCUIElement) {
        XCTAssertTrue(element.waitForExistence(timeout: 10), "Missing \(element)")
        for _ in 0..<6 {
            if element.isHittable { break }
            app.swipeUp()
        }
        element.tap()
    }
    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
