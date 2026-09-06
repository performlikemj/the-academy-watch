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

    private func tap(_ element: XCUIElement) {
        XCTAssertTrue(element.waitForExistence(timeout: 10), "Missing \(element)")
        if !element.isHittable { app.swipeUp() }
        element.tap()
    }
    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
