import XCTest

final class Phase2UITests: XCTestCase {
    private var app: XCUIApplication!
    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
    }
    override func tearDownWithError() throws {
        app.terminate()
        app = nil
    }
    private func launch(_ mode: String, tab: String = "home") {
        app.launchArguments = ["-phase2Fixture", mode, "-initialTab", tab]
        app.launch()
        XCTAssertTrue(
            app.tabBars.buttons[
                ["owner", "coach", "signed", "draft", "full", "conflict"].contains(mode) ? "Today" : "Home"
            ].waitForExistence(timeout: 15))
    }
    private func tap(_ element: XCUIElement, file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertTrue(element.waitForExistence(timeout: 10), file: file, line: line)
        for _ in 0..<8 {
            if element.isHittable { break }
            app.swipeUp()
        }
        XCTAssertTrue(element.isHittable, file: file, line: line)
        element.tap()
    }
    private func capture(_ name: String) {
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "I1-" + name
        shot.lifetime = .keepAlways
        add(shot)
    }
    func testPlayerTabsDirectoryAndPublicClub() {
        launch("player", tab: "clubs")
        XCTAssertTrue(app.tabBars.buttons["Clubs"].waitForExistence(timeout: 15))
        XCTAssertEqual(app.tabBars.buttons.count, 5)
        tap(app.tabBars.buttons["Clubs"])
        XCTAssertTrue(
            app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Distance unavailable")).firstMatch
                .waitForExistence(timeout: 8))
        capture("clubs-location-off")
        tap(app.buttons["club-101"])
        XCTAssertTrue(app.staticTexts["Verified club"].waitForExistence(timeout: 8))
        capture("public-club")
    }
    func testApplicationNeedsConsentBeforeSending() {
        launch("apply", tab: "trials")
        tap(app.tabBars.buttons["Trials"])
        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'trial-'")).firstMatch)
        let position = app.textFields["apply-position"]
        tap(position)
        position.typeText("Central midfield\n")
        let send = app.buttons["apply-send"]
        for _ in 0..<3 {
            if send.isHittable { break }
            app.swipeUp()
        }
        XCTAssertFalse(send.isEnabled)
        tap(app.switches["apply-contact-consent"])
        XCTAssertTrue(send.isEnabled)
        tap(send)
        XCTAssertTrue(app.staticTexts["application-sent"].waitForExistence(timeout: 8))
        capture("applied")
    }
    func testConfirmTrialKeepsPlace() {
        launch("player", tab: "applied")
        tap(app.tabBars.buttons["Applied"])
        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'application-'")).firstMatch)
        tap(app.buttons["application-confirm"])
        tap(app.buttons["Confirm place"])
        XCTAssertTrue(app.staticTexts["application-confirmed"].waitForExistence(timeout: 8))
        capture("confirmed")
        XCTAssertFalse(app.buttons["application-decline"].exists)
    }
    func testDeclineIsWithdrawalAndRemovesActions() {
        launch("player", tab: "applied")
        tap(app.tabBars.buttons["Applied"])
        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'application-'")).firstMatch)
        tap(app.buttons["application-decline"])
        tap(app.buttons["Decline trial"])
        XCTAssertTrue(app.staticTexts["WITHDRAWN"].waitForExistence(timeout: 8))
        XCTAssertFalse(app.buttons["application-confirm"].exists)
        XCTAssertFalse(app.buttons["application-withdraw"].exists)
        capture("declined-withdrawn")
    }
    func testParentGetsInterestLinkAndNoApplyForm() {
        launch("parent", tab: "trials")
        tap(app.tabBars.buttons["Trials"])
        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'trial-'")).firstMatch)
        app.swipeUp()
        app.swipeUp()
        XCTAssertTrue(
            app.otherElements["applications-parent-coming-soon"].exists
                || app.staticTexts["Parents & guardians · coming soon"].exists)
        XCTAssertFalse(app.buttons["apply-send"].exists)
        XCTAssertTrue(app.buttons["Tell me when"].exists)
        capture("parent-coming-soon")
    }
    func testOwnerRecruitingInviteAndPrivateNote() {
        launch("owner", tab: "recruiting")
        tap(app.tabBars.buttons["Recruiting"])
        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'recruiting-post-'")).firstMatch)
        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'applicant-'")).firstMatch)
        let venue = app.textFields["invite-venue"]
        tap(venue)
        venue.typeText("The Saltings\n")
        tap(app.buttons["applicant-invite"])
        XCTAssertTrue(app.staticTexts["INVITED TO TRIAL"].waitForExistence(timeout: 8))
        capture("invited")
        let note = app.descendants(matching: .any)["applicant-note"]
        tap(note)
        note.typeText("Club-private fixture note\n")
        tap(app.buttons["Done"])
        tap(app.buttons["applicant-save-note"])
        XCTAssertTrue(app.staticTexts["Club-private fixture note"].waitForExistence(timeout: 8))
        capture("private-note")
    }
    func testSignedRequiresEnrollmentCheckbox() {
        launch("signed", tab: "recruiting")
        tap(app.tabBars.buttons["Recruiting"])
        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'recruiting-post-'")).firstMatch)
        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'applicant-'")).firstMatch)
        tap(app.buttons["applicant-signed"])
        let confirm = app.buttons["applicant-confirm-decision"]
        XCTAssertTrue(confirm.waitForExistence(timeout: 8))
        XCTAssertFalse(confirm.isEnabled)
        tap(app.switches["applicant-enrollment-confirmed"])
        XCTAssertTrue(confirm.isEnabled)
        tap(confirm)
        XCTAssertTrue(app.staticTexts["SIGNED"].waitForExistence(timeout: 8))
        capture("signed")
    }
    func testCoachAllSquadsHasNoRecruitingAndMinorNameIsPrivate() {
        launch("coach", tab: "squads")
        tap(app.tabBars.buttons["Squads"])
        XCTAssertFalse(app.tabBars.buttons["Recruiting"].exists)
        XCTAssertEqual(app.tabBars.buttons.count, 4)
        XCTAssertTrue(app.staticTexts["Nabil F."].waitForExistence(timeout: 8))
        XCTAssertFalse(app.staticTexts["Nabil Ferhane"].exists)
        capture("coach-private-squad")
        tap(app.tabBars.buttons["Account"])
        XCTAssertFalse(app.buttons["account-staff-access"].exists)
    }
    func testOwnerStaffEditKeepsBothSquads() {
        launch("owner")
        tap(app.tabBars.buttons["Account"])
        tap(app.buttons["account-staff-access"])
        tap(app.buttons["staff-edit-22"])
        XCTAssertEqual(app.switches["staff-edit-squad-3"].value as? String, "1")
        XCTAssertEqual(app.switches["staff-edit-squad-4"].value as? String, "1")
        capture("staff-multiple-squads")
        tap(app.buttons["staff-save-access"])
        XCTAssertTrue(app.buttons["staff-edit-22"].waitForExistence(timeout: 8))
    }
    func testDraftCanBePublishedAndEmptyApplicationsStayCalm() {
        launch("draft")
        tap(app.tabBars.buttons["Recruiting"])
        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'recruiting-post-'")).firstMatch)
        tap(app.buttons["recruiting-publish"])
        XCTAssertFalse(app.buttons["recruiting-publish"].exists)
        capture("published-empty-pipeline")
        launch("empty", tab: "applied")
        tap(app.tabBars.buttons["Applied"])
        XCTAssertTrue(app.staticTexts["Nothing sent, yet."].waitForExistence(timeout: 8))
        capture("empty-applications")
    }
    func testFlagsOffHaveNoPhase2Entries() {
        launch("off")
        XCTAssertFalse(app.tabBars.buttons["Clubs"].exists)
        XCTAssertFalse(app.tabBars.buttons["Trials"].exists)
        XCTAssertFalse(app.tabBars.buttons["Applied"].exists)
        XCTAssertFalse(app.buttons["home-clubs"].exists)
        XCTAssertFalse(app.buttons["home-applications"].exists)
        capture("flags-off")
    }
    func testReviewHomeUsesPersonalHeroWithoutFixtureBanner() {
        app.launchArguments = ["-phase2Preview", "N01", "-reviewCapture"]
        app.launch()
        XCTAssertTrue(app.staticTexts["Good evening, Reuben."].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["2 things are waiting on you."].exists)
        XCTAssertTrue(app.staticTexts["Needs you"].exists)
        XCTAssertFalse(
            app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'OFFLINE FIXTURE'")).firstMatch.exists)
        XCTAssertEqual(app.tabBars.buttons.count, 5)
        XCTAssertTrue(app.tabBars.buttons["Home"].isSelected)
        capture("fidelity-home")
    }
    func testRecruitingSwipeShortlistUpdatesStageCounts() {
        app.launchArguments = ["-phase2Preview", "N09", "-reviewCapture"]
        app.launch()
        let declan = app.buttons["applicant-20202020-1111-4111-8111-010101010101"]
        XCTAssertTrue(declan.waitForExistence(timeout: 15))
        declan.swipeLeft()
        capture("review-N09-swiped")
        tap(app.buttons["pipeline-shortlist-20202020-1111-4111-8111-010101010101"])
        XCTAssertTrue(app.buttons["New  2"].waitForExistence(timeout: 10))
        tap(app.buttons["Shortlisted  3"])
        XCTAssertTrue(declan.waitForExistence(timeout: 10))
        XCTAssertTrue(app.tabBars.buttons["Recruiting"].exists)
        capture("fidelity-shortlisted")
    }
    func testReviewBoardsAndScrolledContent() {
        let screens = [
            "N01", "N02", "N02b", "N03", "N04", "N05", "N06", "N06b", "N09", "N09b", "N10", "N13", "N14", "N17",
        ]
        let longBoards = ["N01", "N03", "N04", "N05", "N06", "N10", "N13", "N14", "N17"]
        for screen in screens {
            app.launchArguments = ["-phase2Preview", screen, "-reviewCapture", "-AppleInterfaceStyle", "Light"]
            if ["N02", "N02b"].contains(screen) { app.launchArguments.append("-reviewLocation") }
            app.launch()
            XCTAssertTrue(app.navigationBars.firstMatch.waitForExistence(timeout: 15), screen)
            // Fixture transport is synchronous; allow the role/flag tasks and native layout to settle.
            Thread.sleep(forTimeInterval: 2)
            XCTAssertFalse(
                app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'OFFLINE FIXTURE'")).firstMatch.exists,
                screen)
            XCTAssertFalse(app.otherElements["phase2-error"].exists, screen)
            capture("review-\(screen)-top")
            if longBoards.contains(screen) {
                app.swipeUp()
                app.swipeUp()
                capture("review-\(screen)-scrolled")
            }
            app.terminate()
        }
    }
}
