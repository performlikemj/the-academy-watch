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
                ["owner", "terminal", "editor", "coach", "analyst", "viewer", "signed", "draft", "full", "conflict"].contains(mode) ? "Today" : "Home"
            ].waitForExistence(timeout: 15))
    }
    private func tap(_ element: XCUIElement, file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertTrue(element.waitForExistence(timeout: 10), file: file, line: line)
        for _ in 0..<8 {
            let isField = element.elementType == .textField || element.elementType == .textView
            let scrollTarget = isField || element.identifier.hasPrefix("home-scout-")
            let visibleBottom =
                app.keyboards.firstMatch.exists ? app.keyboards.firstMatch.frame.minY : app.frame.maxY - 90
            if element.isHittable && (!scrollTarget || element.frame.maxY < visibleBottom) { break }
            app.swipeUp()
        }
        XCTAssertTrue(element.isHittable, file: file, line: line)
        element.tap()
    }
    private enum ScrollDirection { case up, down }
    private func scrollTo(_ element: XCUIElement, direction: ScrollDirection = .up) {
        XCTAssertTrue(element.waitForExistence(timeout: 10))
        for _ in 0..<12 {
            if element.isHittable && element.frame.minY > app.frame.minY + 70 && element.frame.maxY < app.frame.maxY - 90 { return }
            let scroll = app.scrollViews.firstMatch
            if direction == .up { scroll.swipeUp() } else { scroll.swipeDown() }
        }
        XCTAssertTrue(element.isHittable)
    }
    func testFirstEditorPresentationEditsExistingAndTerminalPosts() {
        for mode in ["owner", "terminal"] {
            launch(mode, tab: "recruiting")
            tap(app.tabBars.buttons["Recruiting"])
            tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'recruiting-edit-'")).firstMatch)
            let title = app.textFields["post-title"]
            XCTAssertTrue(title.waitForExistence(timeout: 10))
            XCTAssertTrue(app.navigationBars["Edit opportunity"].exists)
            XCTAssertEqual(title.value as? String, "Open training night with the Reserves")
            XCTAssertFalse(title.isEnabled)
            if mode == "terminal" { XCTAssertFalse(app.buttons["post-publish"].exists) }
            capture("first-edit-" + mode)
            app.terminate()
        }
    }
    func testFlagsOffSignOutKeepsAccountSelected() {
        app.launchArguments = ["-phase2Fixture", "off"]
        app.launch()
        tap(app.tabBars.buttons["Account"])
        tap(app.buttons["Sign Out"])
        if app.alerts.buttons["Sign Out"].waitForExistence(timeout: 2) { app.alerts.buttons["Sign Out"].tap() }
        XCTAssertTrue(app.buttons["Sign In"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.tabBars.buttons["Account"].isSelected)
        capture("flags-off-sign-out-account")
    }
    func testLateFlagsOffBootstrapDoesNotPullScoutDeskBackHome() {
        app.launchArguments = ["-phase2Fixture", "late-off"]
        app.launch()
        tap(app.tabBars.buttons["Scout Desk"])
        XCTAssertTrue(app.navigationBars["Scout Desk"].waitForExistence(timeout: 10))
        // The fixture delays only feature responses, without blocking the UI.
        Thread.sleep(forTimeInterval: 5)
        XCTAssertTrue(app.tabBars.buttons["Scout Desk"].isSelected)
        XCTAssertTrue(app.navigationBars["Scout Desk"].exists)
        capture("late-bootstrap-scout-desk")
    }
    func testDirtyEditorRequiresDiscardAndSwipeKeepsDraft() {
        launch("editor", tab: "recruiting")
        tap(app.buttons["recruiting-create"])
        let title = app.textFields["post-title"]
        tap(title); title.typeText("Retained draft\n")
        app.navigationBars.firstMatch.swipeDown()
        XCTAssertEqual(title.value as? String, "Retained draft")
        app.navigationBars.buttons["Done"].tap()
        XCTAssertTrue(app.buttons["Keep editing"].waitForExistence(timeout: 5))
        tap(app.buttons["Keep editing"])
        XCTAssertEqual(title.value as? String, "Retained draft")
        capture("dirty-editor-kept")
        app.navigationBars.buttons["Done"].tap()
        tap(app.buttons["Discard changes"])
        XCTAssertTrue(app.buttons["recruiting-create"].waitForExistence(timeout: 5))
    }
    func testHomeHeroGrowsAtLargestTextWithoutOverlappingNeedsYou() {
        for longName in [false, true] {
            app.launchArguments = ["-phase2Preview", "N01", "-reviewCapture", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
            if longName { app.launchArguments.append("-reviewLongName") }
            app.launch()
            let greeting = app.staticTexts["home-greeting"]
            let waiting = app.staticTexts["home-waiting"]
            XCTAssertTrue(greeting.waitForExistence(timeout: 10))
            XCTAssertTrue(waiting.waitForExistence(timeout: 10))
            let needs = app.staticTexts["Needs you"]
            XCTAssertTrue(needs.waitForExistence(timeout: 10))
            XCTAssertTrue(greeting.label.contains(longName ? "Alexanderthegreat" : "Reuben"))
            XCTAssertGreaterThan(greeting.frame.height, 100)
            XCTAssertLessThanOrEqual(greeting.frame.maxY, waiting.frame.minY)
            XCTAssertLessThanOrEqual(waiting.frame.maxY, needs.frame.minY)
            capture("home-390-largest-" + (longName ? "long-name" : "default-name"))
            app.terminate()
        }
    }
    func testClubDetailReturnKeepsSearchAndLocation() {
        app.launchArguments = ["-phase2Fixture", "player", "-initialTab", "clubs", "-reviewLocation"]
        app.launch()
        tap(app.tabBars.buttons["Clubs"])
        let query = app.textFields["clubs-search"]
        tap(query); query.typeText("Quillmere\n")
        tap(app.switches["clubs-location"])
        XCTAssertTrue(app.staticTexts["0.8"].waitForExistence(timeout: 5))
        tap(app.buttons["club-101"])
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "The Saltings 3G")).firstMatch.waitForExistence(timeout: 5))
        app.navigationBars.buttons.firstMatch.tap()
        XCTAssertTrue(query.waitForExistence(timeout: 5))
        XCTAssertEqual(query.value as? String, "Quillmere")
        XCTAssertTrue(app.staticTexts["0.8"].exists)
        capture("clubs-return-location")
    }
    private func capture(_ name: String) {
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "I1-" + name
        shot.lifetime = .keepAlways
        add(shot)
    }
    func testNativePostCreatePublishAndAdvertisedTermsLock() {
        launch("editor", tab: "recruiting")
        tap(app.buttons["recruiting-create"])
        XCTAssertTrue(app.textFields["post-title"].waitForExistence(timeout: 10))
        capture("post-empty")
        for (key, value) in [("title", "Open trial — Reserves"), ("description", "A training session for adult players."),
                             ("instructions", "Bring boots and shin pads."), ("venue", "The Saltings 3G")] {
            let field = app.descendants(matching: .any).matching(identifier: "post-" + key).firstMatch
            tap(field); field.typeText(value)
            if app.toolbars.buttons["Done"].exists { app.toolbars.buttons["Done"].tap() }
        }
        capture("post-filled")
        tap(app.buttons["post-save-draft"])
        XCTAssertTrue(app.staticTexts["post-notice"].waitForExistence(timeout: 10))
        capture("post-draft-saved")
        tap(app.buttons["post-publish"])
        XCTAssertTrue(app.staticTexts["Published. Adult players can now apply."].waitForExistence(timeout: 10))
        capture("post-published")
        app.navigationBars.buttons["Done"].tap()
        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'recruiting-edit-'")).firstMatch)
        XCTAssertTrue(app.staticTexts["post-terms-locked"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.textFields["post-title"].isEnabled)
        capture("post-locked-after-application")
        XCTAssertFalse(app.buttons["post-timezone"].isEnabled)
    }
    func testPostValidationAndAllowedZonePicker() {
        launch("editor", tab: "recruiting")
        tap(app.buttons["recruiting-create"])
        tap(app.buttons["post-timezone"])
        XCTAssertTrue(app.navigationBars["Time zone"].waitForExistence(timeout: 10))
        let search = app.searchFields.firstMatch
        tap(search); search.typeText("Kolkata")
        tap(app.buttons["post-zone-Asia/Kolkata"])
        XCTAssertTrue(app.buttons["post-timezone"].label.contains("Kolkata"))
        tap(app.buttons["post-save-draft"])
        XCTAssertTrue(app.staticTexts["post-error-title"].exists)
        scrollTo(app.staticTexts["post-error-title"], direction: .down)
        capture("post-field-validation")
        XCTAssertTrue(app.staticTexts["post-error-title"].isHittable)
    }
    func testTrialsDraftSurvivesSettingsAndFailedForegroundRefresh() {
        for mode in ["apply", "foreground-failure"] {
            launch(mode, tab: "trials")
            tap(app.tabBars.buttons["Trials"])
            tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'trial-'")).firstMatch)
            let position = app.textFields["apply-position"]
            tap(position)
            position.typeText("Draft central midfield\n")
            let settings = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
            settings.launch()
            XCTAssertTrue(settings.wait(for: .runningForeground, timeout: 10))
            app.activate()
            XCTAssertTrue(position.waitForExistence(timeout: 10))
            XCTAssertEqual(position.value as? String, "Draft central midfield")
            XCTAssertTrue(app.tabBars.buttons["Trials"].isSelected)
            capture("foreground-draft-" + mode)
            app.terminate()
        }
    }
    func testFlaggedPlayerStillReachesWatchlistAndLists() {
        launch("player")
        app.swipeUp()
        app.swipeUp()
        tap(app.buttons["home-scout-watchlist"])
        capture("legacy-watchlist-destination")
        XCTAssertTrue(app.navigationBars["Watchlist"].waitForExistence(timeout: 10))
        app.terminate()
        launch("player")
        app.swipeUp()
        app.swipeUp()
        tap(app.buttons["home-scout-lists"])
        XCTAssertTrue(app.navigationBars["Lists"].waitForExistence(timeout: 10))
    }
    func testFlagsOffExplorePlayersSwitchesExistingTab() {
        launch("off")
        tap(app.buttons["home-scout-scoutDesk"])
        XCTAssertTrue(app.tabBars.buttons["Scout Desk"].isSelected)
        XCTAssertTrue(app.navigationBars["Scout Desk"].waitForExistence(timeout: 10))
    }
    func testFirstLocationPermissionKeepsClubsAndSearchDraft() {
        launch("player", tab: "clubs")
        tap(app.tabBars.buttons["Clubs"])
        let query = app.textFields["clubs-search"]
        tap(query)
        query.typeText("Quillmere\n")
        tap(app.switches["clubs-location"])
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let alert = springboard.alerts.firstMatch
        XCTAssertTrue(alert.waitForExistence(timeout: 10))
        let deny = alert.buttons.matching(
            NSPredicate(format: "label CONTAINS[c] 'allow' AND label CONTAINS[c] 'don'")
        ).firstMatch
        XCTAssertTrue(deny.exists)
        deny.tap()
        XCTAssertTrue(query.waitForExistence(timeout: 10))
        XCTAssertEqual(query.value as? String, "Quillmere")
        XCTAssertTrue(app.tabBars.buttons["Clubs"].isSelected)
        capture("location-permission-draft")
    }
    func testInviteAndPrivateNoteDraftsSurviveSettings() {
        launch("owner", tab: "recruiting")
        tap(app.tabBars.buttons["Recruiting"])
        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'recruiting-post-'")).firstMatch)
        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'applicant-'")).firstMatch)
        let venue = app.textFields["invite-venue"]
        tap(venue)
        venue.typeText("Draft pitch\n")
        let note = app.descendants(matching: .any)["applicant-note"]
        tap(note)
        note.typeText("Draft private note")
        tap(app.buttons["Done"])
        let settings = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        settings.launch()
        app.activate()
        XCTAssertTrue(note.waitForExistence(timeout: 10))
        XCTAssertEqual(note.value as? String, "Draft private note")
        XCTAssertEqual(venue.value as? String, "Draft pitch")
        XCTAssertTrue(app.tabBars.buttons["Recruiting"].isSelected)
        capture("foreground-club-drafts")
    }
    func testStaffInviteDraftSurvivesSettingsAndClearsOnlyOnSuccess() {
        launch("owner")
        tap(app.buttons["home-staff-access"])
        let email = app.textFields["staff-invite-email"]
        tap(email)
        email.typeText("newcoach@fixture.example\n")
        let settings = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        settings.launch()
        app.activate()
        XCTAssertEqual(email.value as? String, "newcoach@fixture.example")
        tap(app.switches["staff-all-squads"])
        tap(app.buttons["staff-invite-send"])
        XCTAssertTrue(app.staticTexts["staff-notice"].waitForExistence(timeout: 10))
        XCTAssertNotEqual(email.value as? String, "newcoach@fixture.example")
        capture("staff-invite-cleared")
    }
    func testClaimsFailureNeverShowsMissingAdultProfileCopy() {
        launch("claims-error", tab: "trials")
        tap(app.tabBars.buttons["Trials"])
        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'trial-'")).firstMatch)
        app.swipeUp()
        XCTAssertTrue(
            app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Could not connect")).firstMatch
                .waitForExistence(timeout: 10))
        XCTAssertFalse(
            app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'approved adult self-profile'"))
                .firstMatch.exists)
        XCTAssertFalse(app.textFields["apply-position"].exists)
        XCTAssertFalse(app.textFields["apply-current-club"].exists)
        XCTAssertFalse(app.switches["apply-contact-consent"].exists)
        XCTAssertFalse(app.buttons["apply-send"].exists)
        capture("claims-failure-retry-only")
    }
    func testFlaggedExplorePlayersCanOpenGol() {
        launch("player")
        app.swipeUp()
        app.swipeUp()
        tap(app.buttons["home-scout-scoutDesk"])
        XCTAssertTrue(app.navigationBars["Scout Desk"].waitForExistence(timeout: 10))
        capture("legacy-explore-destination")
        tap(app.navigationBars["Scout Desk"].buttons["gol-landing-entry"])
        capture("legacy-gol-destination")
        XCTAssertTrue(app.navigationBars["GOL"].waitForExistence(timeout: 10))
    }
    func testUnconfirmedClubUsersKeepLegacyTabsAndFailureOffersRetry() {
        for mode in ["pendingclub", "membership-error", "club-signed-out"] {
            launch(mode)
            XCTAssertEqual(app.tabBars.buttons.count, 5)
            XCTAssertTrue(app.tabBars.buttons["Scout Desk"].exists)
            XCTAssertTrue(app.tabBars.buttons["Watchlist"].exists)
            XCTAssertTrue(app.tabBars.buttons["Lists"].exists)
            if mode == "membership-error" { XCTAssertTrue(app.buttons["Try again"].exists) }
            capture("legacy-club-" + mode)
            app.terminate()
        }
    }
    func testPlayerTabsDirectoryAndPublicClub() {
        launch("player", tab: "clubs")
        XCTAssertTrue(app.tabBars.buttons["Clubs"].waitForExistence(timeout: 15))
        XCTAssertEqual(app.tabBars.buttons.count, 5)
        tap(app.tabBars.buttons["Clubs"])
        XCTAssertTrue(
            app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Distance unavailable"))
                .firstMatch
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
        tap(
            app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'application-'")).firstMatch)
        tap(app.buttons["application-confirm"])
        tap(app.buttons["Confirm place"])
        XCTAssertTrue(app.staticTexts["application-confirmed"].waitForExistence(timeout: 8))
        capture("confirmed")
        XCTAssertFalse(app.buttons["application-decline"].exists)
    }
    func testDeclineIsWithdrawalAndRemovesActions() {
        launch("player", tab: "applied")
        tap(app.tabBars.buttons["Applied"])
        tap(
            app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'application-'")).firstMatch)
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
        tap(
            app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'recruiting-post-'"))
                .firstMatch)
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
        tap(
            app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'recruiting-post-'"))
                .firstMatch)
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
    func testAllSquadsAnalystAndViewerCopyAndCapabilities() {
        for role in ["analyst", "viewer"] {
            launch(role, tab: "squads")
            XCTAssertFalse(app.tabBars.buttons["Recruiting"].exists)
            XCTAssertTrue(app.staticTexts["Your access covers all squads. Recruiting and staff administration remain outside your staff access."].waitForExistence(timeout: 8))
            XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "coach's access")).firstMatch.exists)
            capture("all-squads-" + role)
            app.terminate()
        }
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
        tap(
            app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'recruiting-post-'"))
                .firstMatch)
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
            app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'OFFLINE FIXTURE'")).firstMatch
                .exists)
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
    func testRound2FormAndLoaderReviewEvidence() {
        for style in ["Light", "Dark"] {
            for screen in ["post-empty", "post-filled", "post-error", "post-locked"] {
                app.launchArguments = ["-phase2Preview", screen, "-reviewCapture", "-AppleInterfaceStyle", style]
                app.launch()
                XCTAssertTrue(app.textFields["post-title"].waitForExistence(timeout: 15))
                Thread.sleep(forTimeInterval: 2)
                if screen == "post-error" { XCTAssertTrue(app.staticTexts["post-error-title"].exists) }
                if screen == "post-locked" { XCTAssertFalse(app.textFields["post-title"].isEnabled) }
                capture("round2-\(screen)-\(style.lowercased())-top")
                app.swipeUp(); app.swipeUp()
                capture("round2-\(screen)-\(style.lowercased())-schedule")
                app.swipeUp(); app.swipeUp()
                capture("round2-\(screen)-\(style.lowercased())-publication")
                app.terminate()
            }
            for screen in ["loader-green", "loader-claret", "loader-navy", "loader-gold", "loader-still"] {
                app.launchArguments = ["-phase2Preview", screen, "-reviewCapture", "-AppleInterfaceStyle", style]
                app.launch()
                XCTAssertTrue(app.otherElements["cleat-loader"].waitForExistence(timeout: 15))
                XCTAssertEqual(app.otherElements["cleat-loader"].label, "Loading")
                capture("round2-\(screen)-\(style.lowercased())")
                app.terminate()
            }
        }
    }
    func testReviewBoardsAndScrolledContent() {
        let screens = [
            "N01", "N02", "N02b", "N03", "N04", "N05", "N06", "N06b", "N09", "N09b", "N10", "N13", "N14",
            "N17",
        ]
        let longBoards = ["N01", "N03", "N04", "N05", "N06", "N10", "N13", "N14", "N17"]
        for screen in screens {
            app.launchArguments = [
                "-phase2Preview", screen, "-reviewCapture", "-AppleInterfaceStyle", "Light",
            ]
            if ["N02", "N02b"].contains(screen) { app.launchArguments.append("-reviewLocation") }
            app.launch()
            XCTAssertTrue(app.navigationBars.firstMatch.waitForExistence(timeout: 15), screen)
            // Fixture transport is synchronous; allow the role/flag tasks and native layout to settle.
            Thread.sleep(forTimeInterval: 2)
            XCTAssertFalse(
                app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'OFFLINE FIXTURE'")).firstMatch
                    .exists,
                screen)
            XCTAssertFalse(app.otherElements["phase2-error"].exists, screen)
            if screen == "N17" {
                XCTAssertTrue(app.staticTexts["contact-original-introduction"].exists)
                XCTAssertEqual(app.staticTexts["contact-original-introduction"].label, "A conversation about the next step.")
            }
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
