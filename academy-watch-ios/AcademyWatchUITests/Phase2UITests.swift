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
    private func fixtureSignIn() {
        tap(app.buttons["Sign In"])
        let email = app.textFields["signin-email"]
        tap(email); email.typeText("phase2@fixture.invalid")
        tap(app.buttons["signin-send-code"])
        let code = app.textFields["signin-code"]
        tap(code); code.typeText("123456")
        tap(app.buttons["signin-verify"])
    }
    func testClubSignInLoadsAccessAndClaimsOnceAndShowsStaffTabs() {
        app.launchArguments = ["-phase2Fixture", "club-signed-out", "-reviewAccountCounters", "-initialTab", "account"]
        app.launch()
        fixtureSignIn()
        waitForLabel("fixture-root-state", containing: "clubs=1")
        for title in ["Squads", "Matches", "Recruiting"] {
            XCTAssertTrue(app.tabBars.buttons[title].waitForExistence(timeout: 10))
        }
        // Read fresh diagnostics via a control update after async bootstrap has settled.
        tap(app.buttons["fixture-hydrate"])
        for path in ["me/club-access", "funding/claims/me"] {
            waitForLabel("fixture-bootstrap-counts", containing: path + "=1")
        }
        capture("I1F10-club-sign-in-tabs-and-single-access-load")
        tap(app.buttons["fixture-switch"])
        waitForLabel("fixture-hydration-email", containing: "second@fixture.invalid")
        waitForLabel("fixture-root-state", containing: "clubs=0")
        tap(app.buttons["fixture-hydrate"])
        for path in ["me/club-access", "funding/claims/me"] {
            waitForLabel("fixture-bootstrap-counts", containing: path + "=2")
        }
        XCTAssertFalse(app.tabBars.buttons["Recruiting"].exists)
        capture("I1F10-account-switch-reloads-new-access")
    }
    func testPlayerSignInFillsWatchlistAndSentRequests() {
        app.launchArguments = ["-phase2Fixture", "player-signed-out", "-reviewAccountCounters", "-initialTab", "account"]
        app.launch()
        fixtureSignIn()
        waitForLabel("fixture-root-state", containing: "watch=1")
        waitForLabel("fixture-root-state", containing: "lists=1;sent=5;inbox=2")
        tap(app.buttons["fixture-hydrate"])
        for path in ["scout/watchlist", "scout/lists", "contact/requests/sent", "contact/requests/inbox"] {
            waitForLabel("fixture-bootstrap-counts", containing: path + "=1")
        }
        capture("I1F10-player-sign-in-private-loads")
    }
    func testSwitchWhileAccountLookupPendingLoadsNewClubAccessOnce() {
        launchSavedSession("owner")
        waitForLabel("fixture-root-state", containing: "clubs=1")
        tap(app.buttons["fixture-switch"])
        waitForLabel("fixture-hydration-email", containing: "second@fixture.invalid")
        waitForLabel("fixture-root-state", containing: "clubs=0;watch=0;ids=0;lists=0;sent=0;inbox=0")
        // Release A's actual held auth/me only after B's private bootstrap finishes.
        tap(app.buttons["fixture-hydrate"])
        waitForLabel("fixture-hydration-email", containing: "second@fixture.invalid")
        for path in ["me/club-access", "funding/claims/me"] {
            waitForLabel("fixture-bootstrap-counts", containing: path + "=2")
        }
        capture("I1F10-switch-during-held-account-lookup-new-access-loaded")
    }

    func testInvalidOverrideShowsDeveloperErrorBeforeFixtureBootstrap() {
        app.launchArguments = ["-phase2Fixture", "owner"]
        app.launchEnvironment["ACADEMY_LOCAL_API_URL"] = "https://api.theacademywatch.com/api"
        app.launch()
        XCTAssertTrue(app.staticTexts["developer-api-error"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.tabBars.firstMatch.exists)
        capture("I1F10-production-override-refused")
    }

    private func launchSavedSession(_ mode: String, tab: String = "home") {
        app.launchArguments = ["-phase2Fixture", mode, "-initialTab", tab,
                               "-reviewSavedSession", "-reviewAppearance", "light"]
        app.launch()
        XCTAssertTrue(app.staticTexts["fixture-root-state"].waitForExistence(timeout: 15))
        waitForLabel("fixture-hydration-email", containing: "unhydrated")
        waitForLabel("fixture-root-state", containing: "lists=1")
        waitForLabel("fixture-root-state", containing: "watch=1")
        waitForLabel("fixture-root-state", containing: "sent=5")
        waitForLabel("fixture-root-state", containing: "inbox=2")
    }
    private func waitForLabel(_ identifier: String, containing value: String,
                              file: StaticString = #filePath, line: UInt = #line) {
        let element = app.staticTexts[identifier]
        let predicate = NSPredicate(format: "label CONTAINS %@", value)
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: predicate, object: element)], timeout: 15),
                       .completed, "\(identifier): expected \(value), got \(element.exists ? element.label : "absent")", file: file, line: line)
    }
    private func hydrateSavedSession() {
        let prefix = app.buttons["editor-fixture-hydrate"].exists ? "editor-" : ""
        tap(app.buttons[prefix + "fixture-hydrate"])
        waitForLabel(prefix + "fixture-hydration-email", containing: "phase2@fixture.invalid")
    }
    private func assertSingleBootstrap(club: Bool = false) {
        let prefix = app.staticTexts["editor-fixture-bootstrap-counts"].exists ? "editor-" : ""
        let counts = app.staticTexts[prefix + "fixture-bootstrap-counts"].label
        for path in ["auth/me", "features", "opportunities/features", "scout/watchlist", "scout/lists",
                     "contact/requests/sent", "contact/requests/inbox"] {
            XCTAssertTrue(counts.split(separator: ";").contains(Substring(path + "=1")), counts)
        }
        if club {
            for path in ["me/club-access", "funding/claims/me"] {
                XCTAssertTrue(counts.split(separator: ";").contains(Substring(path + "=1")), counts)
            }
            // Workspace resolves the owner once; editor/squad model independently
            // rechecks access once on entry. Hydration must trigger neither again.
            XCTAssertTrue(counts.split(separator: ";").contains("club/101/access/me=2"), counts)
        }
    }
    func testSavedSessionHydrationRetainsRecruitingDraftAndSelectedTab() {
        launchSavedSession("owner", tab: "recruiting")
        waitForLabel("fixture-root-state", containing: "clubs=1")
        tap(app.tabBars.buttons["Recruiting"])
        tap(app.buttons["recruiting-create"])
        let title = app.textFields["post-title"]
        tap(title); title.typeText("Unsaved restored-session trial")
        if app.toolbars.buttons["Done"].exists { tap(app.toolbars.buttons["Done"]) }
        capture("I1F9-owner-draft-before-hydration")
        hydrateSavedSession()
        XCTAssertEqual(title.value as? String, "Unsaved restored-session trial")
        XCTAssertTrue(app.navigationBars["Post a trial"].exists)
        assertSingleBootstrap(club: true)
        capture("I1F9-owner-draft-after-hydration")
        tap(app.navigationBars.buttons["Done"])
        XCTAssertTrue(app.tabBars.buttons["Recruiting"].isSelected)
        waitForLabel("fixture-root-state", containing: "tab=recruiting;clubs=1")
        capture("I1F9-owner-recruiting-retained")
    }
    func testSavedSessionClubBoundariesDisposeOpenDraft() {
        for action in ["signout", "switch"] {
            launchSavedSession("owner", tab: "recruiting")
            tap(app.tabBars.buttons["Recruiting"])
            tap(app.buttons["recruiting-create"])
            let title = app.textFields["post-title"]
            tap(title); title.typeText("Previous account private trial")
            if app.toolbars.buttons["Done"].exists { tap(app.toolbars.buttons["Done"]) }
            capture("I1F9-club-before-\(action)")
            tap(app.buttons["editor-fixture-" + action])
            waitForLabel("fixture-root-state", containing: "clubs=0;watch=0;ids=0;lists=0;sent=0;inbox=0")
            XCTAssertFalse(title.exists)
            XCTAssertFalse(app.tabBars.buttons["Recruiting"].exists)
            XCTAssertFalse(app.tabBars.buttons["Squads"].exists)
            XCTAssertFalse(app.tabBars.buttons["Matches"].exists)
            capture("I1F9-club-after-\(action)")
            app.terminate()
        }
    }
    func testSavedSessionHydrationRetainsSquadsAndMatchesSelection() {
        for tab in ["Squads", "Matches"] {
            launchSavedSession("owner", tab: tab.lowercased())
            tap(app.tabBars.buttons[tab])
            let picker = app.buttons["squad-picker"]
            tap(picker); tap(app.buttons["Reserves"])
            XCTAssertTrue(picker.label.contains("Reserves"))
            capture("I1F9-\(tab)-before-hydration")
            hydrateSavedSession()
            XCTAssertTrue(app.tabBars.buttons[tab].isSelected)
            XCTAssertTrue(app.navigationBars[tab].exists)
            XCTAssertTrue(picker.label.contains("Reserves"))
            waitForLabel("fixture-root-state", containing: "clubs=1")
            assertSingleBootstrap(club: true)
            capture("I1F9-\(tab)-after-hydration")
            app.terminate()
        }
    }
    func testSavedSessionHydrationRetainsProfilesAndDeepDraft() {
        launchSavedSession("off")
        tap(app.buttons["home-my-profiles"])
        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'my-profile-'")).firstMatch)
        tap(app.buttons["my-profile-edit"])
        let field = app.textFields["profile-editor-position"]
        tap(field); field.typeText(" Kept through hydration\n")
        if app.buttons["Done"].exists { tap(app.buttons["Done"]) }
        let before = field.value as? String
        capture("I1F9-profiles-before-hydration")
        hydrateSavedSession()
        XCTAssertEqual(field.value as? String, before)
        XCTAssertTrue(app.tabBars.buttons["Home"].isSelected)
        assertSingleBootstrap()
        capture("I1F9-profiles-after-hydration")
    }
    func testSavedSessionHydrationRetainsApplicationDetail() {
        launchSavedSession("player", tab: "applied")
        tap(app.tabBars.buttons["Applied"])
        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'application-'")).firstMatch)
        XCTAssertTrue(app.buttons["Withdraw this application"].waitForExistence(timeout: 10))
        capture("I1F9-application-before-hydration")
        hydrateSavedSession()
        XCTAssertTrue(app.buttons["Withdraw this application"].exists)
        XCTAssertTrue(app.descendants(matching: .any)["phase2-application-detail"].exists)
        XCTAssertTrue(app.tabBars.buttons["Applied"].isSelected)
        assertSingleBootstrap()
        capture("I1F9-application-after-hydration")
    }
    func testSavedSessionHydrationFlagsOffKeepsListsAndAccountDestination() {
        launchSavedSession("off", tab: "lists")
        tap(app.tabBars.buttons["Lists"])
        XCTAssertTrue(app.navigationBars["Lists"].waitForExistence(timeout: 10))
        tap(app.tabBars.buttons["Account"])
        tap(app.buttons["account-my-profiles"])
        XCTAssertTrue(app.staticTexts["Your place in the game"].waitForExistence(timeout: 10))
        capture("I1F9-flags-off-account-before-hydration")
        hydrateSavedSession()
        XCTAssertTrue(app.staticTexts["Your place in the game"].exists)
        XCTAssertTrue(app.tabBars.buttons["Account"].isSelected)
        waitForLabel("fixture-root-state", containing: "destination=Optional")
        assertSingleBootstrap()
        capture("I1F9-flags-off-account-after-hydration")
        tap(app.tabBars.buttons["Lists"])
        XCTAssertTrue(app.navigationBars["Lists"].exists)
        waitForLabel("fixture-root-state", containing: "tab=lists;clubs=0;watch=1")
    }
    func testUnhydratedSignOutAndFailedNextAccountClearsAllRootData() {
        for mode in ["owner", "off"] {
            launchSavedSession(mode)
            if mode == "owner" { waitForLabel("fixture-root-state", containing: "clubs=1") }
            capture("I1F9-\(mode)-unhydrated-data-before-signout")
            // Sign out before /auth/me answers: email remains nil -> nil.
            tap(app.buttons["fixture-signout"])
            waitForLabel("fixture-hydration-email", containing: "signed-out")
            waitForLabel("fixture-root-state", containing: "clubs=0;watch=0;ids=0;lists=0;sent=0;inbox=0;destination=nil")
            capture("I1F9-\(mode)-unhydrated-data-after-signout")
            tap(app.buttons["fixture-switch"])
            waitForLabel("fixture-hydration-email", containing: "second@fixture.invalid")
            tap(app.buttons["fixture-hydrate-fail"])
            waitForLabel("fixture-root-state", containing: "watch=0;ids=0;lists=0;sent=0;inbox=0;destination=nil")
            // B's private reloads are refused; A's data must still be absent.
            tap(app.tabBars.buttons["Account"])
            XCTAssertFalse(app.buttons["account-staff-access"].exists)
            capture("I1F9-\(mode)-next-account-failed-loads-empty")
            app.terminate()
        }
    }
    func testFailedSavedSessionHydrationThenSwitchClearsAllRootData() {
        launchSavedSession("owner")
        waitForLabel("fixture-root-state", containing: "clubs=1")
        tap(app.buttons["fixture-hydrate-fail"])
        waitForLabel("fixture-hydration-email", containing: "unhydrated")
        tap(app.buttons["fixture-switch"])
        waitForLabel("fixture-hydration-email", containing: "second@fixture.invalid")
        waitForLabel("fixture-root-state", containing: "watch=0;ids=0;lists=0;sent=0;inbox=0;destination=nil")
        capture("I1F9-failed-hydration-direct-switch-empty")
    }
    func testVisitorHomePublicTrialAndClubSurviveSignIn() {
        for entry in ["home-trials", "home-clubs", "home-club-page"] {
            launchBrowseFixture("player-signed-out", host: "Home")
            if entry == "home-club-page" {
                let clubs = app.buttons["home-clubs"]
                scrollBrowseTo(clubs); tap(clubs); tap(app.buttons["club-101"])
                XCTAssertTrue(app.descendants(matching: .any)["phase2-club-page"].waitForExistence(timeout: 10))
            } else { openBrowseList(entry) }
            capture("I1F9-\(entry)-visitor-before-sign-in")
            tap(app.tabBars.buttons["Account"]); tap(app.buttons["Sign In"])
            let email = app.textFields["signin-email"]
            tap(email); email.typeText("phase2@fixture.invalid")
            tap(app.buttons["signin-send-code"])
            let code = app.textFields["signin-code"]
            tap(code); code.typeText("123456")
            tap(app.buttons["signin-verify"])
            XCTAssertTrue(app.buttons["Sign Out"].waitForExistence(timeout: 10))
            tap(app.tabBars.buttons["Home"])
            if entry == "home-club-page" {
                XCTAssertTrue(app.descendants(matching: .any)["phase2-club-page"].waitForExistence(timeout: 10))
                XCTAssertTrue(app.staticTexts["The Saltings 3G, XW4 2QA"].exists)
            } else {
                XCTAssertTrue(app.scrollViews["phase2-trial-detail"].waitForExistence(timeout: 10))
                XCTAssertTrue(app.textFields["apply-position"].waitForExistence(timeout: 10))
            }
            capture("I1F9-\(entry)-visitor-after-sign-in")
            app.terminate()
        }
    }
    func testHomeAllTrialsRowsOpen() { checkBrowseEntry("home-trials") }
    func testHomeClubsRowsAndClubTrialOpen() { checkBrowseEntry("home-clubs") }
    func testHubHomeAllTrialsRowsOpen() { checkBrowseEntry("home-trials", mode: "player-hub") }
    func testHubHomeClubsRowsAndClubTrialOpen() { checkBrowseEntry("home-clubs", mode: "player-hub") }
    func testAppliedEmptyBrowseTrialsRowsOpen() { checkBrowseEntry("Browse trials", mode: "apply", host: "Applied") }
    func testAppliedEmptyClubsRowsAndClubTrialOpen() { checkBrowseEntry("Clubs near you", mode: "apply", host: "Applied") }
    func testAppliedStillLookingRowsOpen() { checkBrowseEntry("Browse trials", host: "Applied") }
    func testHomeSeeEveryStepStillLookingRowsOpen() { checkBrowseEntry("Browse trials", throughApplications: true) }
    func testHubHomeApplicationsStillLookingRowsOpen() {
        checkBrowseEntry("Browse trials", mode: "player-hub", throughApplications: true)
    }
    func testHomeSeeEveryStepEmptyBrowseTrialsRowsOpen() {
        checkBrowseEntry("Browse trials", mode: "apply", throughApplications: true)
    }
    func testHomeSeeEveryStepEmptyClubsRowsOpen() {
        checkBrowseEntry("Clubs near you", mode: "apply", throughApplications: true)
    }
    func testHubHomeApplicationsEmptyBrowseTrialsRowsOpen() {
        checkBrowseEntry("Browse trials", mode: "player-hub-empty", throughApplications: true)
    }
    func testHubHomeApplicationsEmptyClubsRowsOpen() {
        checkBrowseEntry("Clubs near you", mode: "player-hub-empty", throughApplications: true)
    }
    func testHomeOpeningPrivateDestinationOpens() {
        launchBrowseFixture("apply", host: "Home")
        let opening = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Open training'")).firstMatch
        scrollBrowseTo(opening); tap(opening)
        XCTAssertTrue(app.scrollViews["phase2-trial-detail"].waitForExistence(timeout: 10))
        submitBrowseApplication()
        XCTAssertTrue(app.buttons["Withdraw this application"].waitForExistence(timeout: 10))
        capture("I1F8-home-opening-application")
    }
    private func scrollBrowseTo(_ element: XCUIElement) {
        XCTAssertTrue(element.waitForExistence(timeout: 10))
        let top = app.frame.minY + 70
        for _ in 0..<12 {
            let bottom = app.keyboards.firstMatch.exists
                ? app.keyboards.firstMatch.frame.minY - 8 : app.tabBars.firstMatch.frame.minY - 8
            if element.isHittable && element.frame.minY > top && element.frame.maxY < bottom { return }
            let scroll = app.scrollViews.firstMatch
            if element.frame.minY <= top { scroll.swipeDown() } else { scroll.swipeUp() }
        }
        XCTAssertTrue(element.isHittable)
        XCTAssertGreaterThan(element.frame.minY, top)
        XCTAssertLessThan(element.frame.maxY, app.tabBars.firstMatch.frame.minY - 8)
    }
    private func launchBrowseFixture(_ mode: String, host: String) {
        app.launchArguments = ["-phase2Fixture", mode, "-initialTab", host.lowercased(),
                               "-reviewAccountSwitch", "-reviewCapture", "-reviewAppearance", "light"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons[host].waitForExistence(timeout: 15))
        tap(app.tabBars.buttons[host])
    }
    private func openBrowseList(_ entry: String, throughApplications: Bool = false) {
        if throughApplications {
            let applications = app.buttons["home-applications"]
            scrollBrowseTo(applications); capture("I1F8-home-applications-entry"); tap(applications)
            XCTAssertTrue(app.navigationBars["Applications"].waitForExistence(timeout: 10))
        }
        let button = app.buttons[entry]
        // Footer links can be hittable beneath the editorial tab bar: require safe bounds.
        scrollBrowseTo(button)
        XCTAssertLessThan(button.frame.maxY, app.tabBars.firstMatch.frame.minY)
        capture("I1F8-entry-" + entry)
        tap(button)
        if entry.lowercased().contains("clubs") {
            tap(app.buttons["club-101"])
            XCTAssertTrue(app.scrollViews["phase2-club-page"].waitForExistence(timeout: 10))
            capture("I1F8-\(entry)-club-detail")
            let trial = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Tuesday night' OR label CONTAINS 'Open training'")).firstMatch
            scrollBrowseTo(trial); tap(trial)
        } else {
            tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'trial-'")).firstMatch)
        }
        XCTAssertTrue(app.scrollViews["phase2-trial-detail"].waitForExistence(timeout: 10))
    }
    private func checkBrowseEntry(_ entry: String, mode: String = "player", host: String = "Home",
                                  throughApplications: Bool = false) {
        launchBrowseFixture(mode, host: host)
        openBrowseList(entry, throughApplications: throughApplications)
        capture("I1F8-\(mode)-\(host)-\(throughApplications ? "applications-" : "")\(entry)-trial-detail")
    }
    func testSignOutClearsApplicationOpenedViaHomeAndApplied() { checkAlternatePrivateBoundary(switchAccount: false) }
    func testSwitchClearsApplicationOpenedViaHomeAndApplied() { checkAlternatePrivateBoundary(switchAccount: true) }
    func testSignOutClearsDeepProfilesOpenedViaHomeAndApplied() { checkAlternatePrivateBoundary(switchAccount: false, profiles: true) }
    func testSwitchClearsDeepProfilesOpenedViaHomeAndApplied() { checkAlternatePrivateBoundary(switchAccount: true, profiles: true) }
    private func submitBrowseApplication() {
        let position = app.textFields["apply-position"]
        scrollBrowseTo(position); tap(position); position.typeText("Central midfield\n")
        tap(app.switches["apply-contact-consent"])
        scrollBrowseTo(app.buttons["apply-send"]); tap(app.buttons["apply-send"])
        XCTAssertTrue(app.staticTexts["application-sent"].waitForExistence(timeout: 10))
        scrollBrowseTo(app.buttons["See my application"]); tap(app.buttons["See my application"])
    }
    private func checkAlternatePrivateBoundary(switchAccount: Bool, profiles: Bool = false) {
        for host in ["Home", "Applied"] {
            launchBrowseFixture(profiles ? "ineligible" : "apply", host: host)
            openBrowseList(host == "Home" ? "home-trials" : "Browse trials")
            if profiles {
                scrollBrowseTo(app.buttons["Find or claim your profile"]); tap(app.buttons["Find or claim your profile"])
                XCTAssertTrue(app.staticTexts["Your place in the game"].waitForExistence(timeout: 10))
                tap(app.buttons["my-profiles-add"])
                XCTAssertTrue(app.textFields["player-onboarding-name-search"].waitForExistence(timeout: 10))
            } else {
                submitBrowseApplication()
                scrollBrowseTo(app.buttons["Withdraw this application"])
                XCTAssertTrue(app.buttons["Withdraw this application"].exists)
            }
            tap(app.tabBars.buttons["Account"])
            if switchAccount {
                tap(app.buttons["fixture-account-switch"])
                XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "identifier == 'fixture-account-identity' AND label == 'second@fixture.invalid'")).firstMatch.waitForExistence(timeout: 10))
            } else {
                tap(app.buttons["Sign Out"])
                XCTAssertTrue(app.buttons["Sign In"].waitForExistence(timeout: 10))
            }
            tap(app.tabBars.buttons[host])
            if host == "Home" {
                XCTAssertTrue(app.scrollViews["phase2-trial-detail"].waitForExistence(timeout: 10))
            } else {
                XCTAssertTrue(app.navigationBars["Applications"].waitForExistence(timeout: 10))
            }
            XCTAssertFalse(app.descendants(matching: .any)["phase2-application-detail"].exists)
            XCTAssertFalse(app.buttons["Withdraw this application"].exists)
            XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Applied as'")).firstMatch.exists)
            XCTAssertFalse(app.descendants(matching: .any)["my-profiles"].exists)
            XCTAssertFalse(app.textFields["player-onboarding-name-search"].exists)
            XCTAssertFalse(app.textFields["profile-editor-position"].exists)
            capture("I1F8-\(host)-\(profiles ? "profiles" : "application")-after-\(switchAccount ? "switch" : "signout")")
            app.terminate()
        }
    }
    func testSignOutClearsPrivateApplicationOnBothPublicStacks() {
        checkPrivateBoundary(mode: "apply", switchAccount: false)
    }
    func testAccountSwitchClearsPrivateApplicationOnBothPublicStacks() {
        checkPrivateBoundary(mode: "apply", switchAccount: true)
    }
    func testSignOutClearsProfilesOnBothPublicStacks() {
        checkPrivateBoundary(mode: "ineligible", switchAccount: false)
    }
    func testAccountSwitchClearsProfilesOnBothPublicStacks() {
        checkPrivateBoundary(mode: "ineligible", switchAccount: true)
    }
    func testSignOutClearsDeepProfileAndClaimPushes() {
        checkPrivateBoundary(mode: "ineligible", switchAccount: false, deeper: true)
    }
    func testAccountSwitchClearsDeepProfileAndClaimPushes() {
        checkPrivateBoundary(mode: "ineligible", switchAccount: true, deeper: true)
    }
    private func checkPrivateBoundary(mode: String, switchAccount: Bool, deeper: Bool = false) {
        for tab in ["Trials", "Clubs"] {
            let style = tab == "Trials" ? "Light" : "Dark"
            app.launchArguments = ["-phase2Fixture", mode, "-initialTab", tab.lowercased(),
                                   "-reviewAccountSwitch", "-reviewAppearance", style]
            app.launch()
            tap(app.tabBars.buttons[tab])
            if tab == "Clubs" {
                tap(app.buttons["club-101"])
                tap(app.buttons.matching(NSPredicate(format: "label CONTAINS 'Tuesday night' OR label CONTAINS 'Open training'")).firstMatch)
            } else {
                tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'trial-'")).firstMatch)
            }
            if mode == "apply" {
                let position = app.textFields["apply-position"]
                tap(position); position.typeText("Central midfield\n")
                tap(app.switches["apply-contact-consent"])
                tap(app.buttons["apply-send"])
                XCTAssertTrue(app.staticTexts["application-sent"].waitForExistence(timeout: 10))
                tap(app.buttons["See my application"])
                XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Applied as'")).firstMatch.waitForExistence(timeout: 10))
                scrollTo(app.buttons["Withdraw this application"])
            } else {
                tap(app.buttons["Find or claim your profile"])
                XCTAssertTrue(app.staticTexts["Your place in the game"].waitForExistence(timeout: 10))
                if deeper {
                    if tab == "Trials" {
                        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'my-profile-'")).firstMatch)
                        tap(app.buttons["my-profile-edit"])
                        XCTAssertTrue(app.textFields["profile-editor-position"].waitForExistence(timeout: 10))
                        let editorPosition = app.textFields["profile-editor-position"]
                        tap(editorPosition); editorPosition.typeText(" Private editor draft\n")
                        if app.buttons["Done"].exists { tap(app.buttons["Done"]) }
                        tap(app.tabBars.buttons["Account"])
                        tap(app.tabBars.buttons[tab])
                        XCTAssertTrue(editorPosition.waitForExistence(timeout: 10))
                        XCTAssertTrue((editorPosition.value as? String)?.contains("Private editor draft") == true)
                    } else {
                        tap(app.buttons["my-profiles-add"])
                        XCTAssertTrue(app.textFields["player-onboarding-name-search"].waitForExistence(timeout: 10))
                    }
                    XCTAssertFalse(app.staticTexts["Your place in the game"].isHittable)
                }
            }
            capture("I1F7-\(tab)-\(mode)-\(deeper ? "deep" : "entry")-before-\(switchAccount ? "switch" : "signout")")
            tap(app.tabBars.buttons["Account"])
            if switchAccount {
                tap(app.buttons["fixture-account-switch"])
                XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "identifier == 'fixture-account-identity' AND label == 'second@fixture.invalid'")).firstMatch.waitForExistence(timeout: 10))
            } else {
                tap(app.buttons["Sign Out"])
                XCTAssertTrue(app.buttons["Sign In"].waitForExistence(timeout: 10))
            }
            tap(app.tabBars.buttons[tab])
            XCTAssertTrue(app.scrollViews["phase2-trial-detail"].waitForExistence(timeout: 10))
            XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Applied as'")).firstMatch.exists)
            XCTAssertFalse(app.staticTexts["Your place in the game"].exists)
            XCTAssertFalse(app.buttons["Withdraw this application"].exists)
            XCTAssertFalse(app.descendants(matching: .any)["my-profiles"].exists)
            XCTAssertFalse(app.buttons["my-profiles-add"].exists)
            XCTAssertFalse(app.textFields["profile-editor-position"].exists)
            XCTAssertFalse(app.textFields["player-onboarding-name-search"].exists)
            XCTAssertFalse(app.staticTexts["application-sent"].exists)
            if !switchAccount {
                XCTAssertTrue(app.staticTexts["Sign in from Account to apply with your approved adult profile."].waitForExistence(timeout: 10))
            }
            capture("I1F7-\(tab)-\(mode)-\(deeper ? "deep" : "entry")-after-\(switchAccount ? "switch" : "signout")")
            if tab == "Clubs" {
                tap(app.navigationBars.buttons.firstMatch)
                XCTAssertTrue(app.staticTexts["The Saltings 3G, XW4 2QA"].waitForExistence(timeout: 10))
            }
            app.terminate()
        }
    }
    func testVisualOnlyPreviewCannotMaskProductionOverride() {
        app.launchArguments = ["-logoFixtureSeconds", "12", "-logoFixtureReduceMotion"]
        app.launchEnvironment["ACADEMY_LOCAL_API_URL"] = "https://api.theacademywatch.com/api"
        app.launch()
        XCTAssertTrue(app.staticTexts["developer-api-error"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.otherElements["logo-loader"].exists)
        capture("I1F10-visual-preview-production-override-refused")
    }

    func testLoadingFeedbackExposesFirstVisitTitleDetailAndWaitTime() {
        app.launchArguments = ["-logoFixtureSeconds", "12", "-logoFixtureReduceMotion"]
        app.launch()
        XCTAssertTrue(app.otherElements["logo-loader"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.otherElements["logo-loader"].label, "Loading")
        XCTAssertTrue(app.staticTexts["First visits can take about 30 seconds."].exists)
        XCTAssertTrue(app.staticTexts["Almost there"].exists)
        XCTAssertTrue(app.staticTexts["First visit — we're gathering players from around the world."].exists)
        // Separate accessible texts, rather than a card that ignores all its children.
        XCTAssertGreaterThanOrEqual(app.staticTexts.count, 3)
        capture("I1F7-scout-accessible-first-load")
    }
    func testLogoSurfaceReviewInLightDarkAndReduceMotion() {
        for style in ["Light", "Dark"] {
            for screen in ["loader-buttons", "loader-buttons-still", "loader-gold"] {
                app.launchArguments = ["-phase2Preview", screen, "-reviewCapture", "-reviewAppearance", style]
                app.launch()
                XCTAssertTrue(app.otherElements.matching(identifier: "logo-loader").firstMatch.waitForExistence(timeout: 10))
                capture("I1F7-\(screen)-\(style.lowercased())")
                app.terminate()
            }
        }
    }
    func testPendingThreadShowsRealStatusWithoutLegend() {
        assertThreadStatusWithoutLegend(mode: "thread-pending", status: "Pending")
    }
    func testAcceptedThreadShowsRealStatusWithoutLegend() {
        assertThreadStatusWithoutLegend(mode: "player", status: "Nabil accepted")
    }
    func testDeclinedThreadShowsRealStatusWithoutLegend() {
        assertThreadStatusWithoutLegend(mode: "thread-declined", status: "Declined")
    }
    private func assertThreadStatusWithoutLegend(mode: String, status: String) {
        for style in ["Light", "Dark"] {
            app.launchArguments = [
                "-phase2Preview", "N17", "-phase2Fixture", mode, "-reviewCapture", "-AppleInterfaceStyle", style,
            ]
            app.launch()
            let statusLine = app.staticTexts[status]
            XCTAssertTrue(statusLine.waitForExistence(timeout: 15))
            XCTAssertTrue(statusLine.isHittable)
            XCTAssertTrue(app.staticTexts["Quillmere Athletic said yes"].exists)
            let banner = app.descendants(matching: .any)["contact-thread-anti-scam-banner"].firstMatch
            XCTAssertTrue(banner.waitForExistence(timeout: 10))
            XCTAssertTrue(banner.label.contains("Never pay to be scouted."))
            let pinnedFrame = banner.frame
            XCTAssertTrue(banner.isHittable)
            XCTAssertGreaterThanOrEqual(pinnedFrame.minY, app.navigationBars.firstMatch.frame.maxY)
            func assertNoLegend() {
                for label in ["OTHER STATES YOU WILL SEE", "Other states you will see",
                              "WAITING ON CLUB", "WAITING ON PLAYER", "DECLINED", "EXPIRED", "WITHDRAWN"] {
                    XCTAssertFalse(app.staticTexts[label].exists, label)
                }
            }
            assertNoLegend()
            capture("I1F6-\(mode)-\(style.lowercased())-top")
            app.scrollViews.firstMatch.swipeUp()
            assertNoLegend()
            XCTAssertTrue(banner.isHittable)
            XCTAssertEqual(banner.frame, pinnedFrame)
            capture("I1F6-\(mode)-\(style.lowercased())-scrolled")
            app.terminate()
        }
    }
    func testAntiScamWarningPinnedThroughProductionScrollAndNewMessage() {
        app.launchArguments = ["-phase2Preview", "N17", "-AppleInterfaceStyle", "Light"]
        app.launch()
        let last = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'My dad will drive me'")).firstMatch
        XCTAssertTrue(last.waitForExistence(timeout: 15))
        let banner = app.descendants(matching: .any)["contact-thread-anti-scam-banner"].firstMatch
        let composer = app.descendants(matching: .any)["contact-message-composer"].firstMatch
        func assertPinned() {
            XCTAssertTrue(banner.exists)
            XCTAssertTrue(banner.isHittable)
            XCTAssertGreaterThanOrEqual(banner.frame.minY, app.navigationBars.firstMatch.frame.maxY)
            XCTAssertLessThanOrEqual(banner.frame.maxY, composer.frame.minY)
            XCTAssertLessThanOrEqual(banner.frame.maxY, app.frame.maxY)
        }
        XCTAssertTrue(composer.waitForExistence(timeout: 10))
        Thread.sleep(forTimeInterval: 1)
        assertPinned()
        capture("I1F4-warning-production-open")
        app.scrollViews.firstMatch.swipeUp()
        assertPinned()
        tap(composer); composer.typeText("A new message for regression.")
        tap(app.buttons["Send message"])
        XCTAssertTrue(app.staticTexts["A new message for regression."].waitForExistence(timeout: 10))
        assertPinned()
        capture("I1F4-warning-after-new-message")
    }
    func testHomeIncludesDirectAndOlderGrantedIntroductions() {
        for mode in ["direct-home", "older-introduction"] {
            launch(mode)
            let waiting = app.staticTexts["home-waiting"]
            XCTAssertTrue(waiting.waitForExistence(timeout: 10))
            let confirmed = NSPredicate(format: "label == %@", "1 thing is waiting on you.")
            expectation(for: confirmed, evaluatedWith: waiting)
            waitForExpectations(timeout: 10)
            let needs = app.buttons["home-introductions"]
            XCTAssertTrue(needs.exists)
            XCTAssertTrue(needs.label.lowercased().contains(mode == "direct-home" ? "reply needed" : "club said yes"))
            XCTAssertTrue(needs.label.contains(mode == "direct-home" ? "Choose whether to talk" : "Your club agreed"))
            capture("I1F4-home-" + mode)
            app.terminate()
        }
    }
    func testFailedTrialReadEndsLoaderAndShowsRetry() {
        launch("detail-error", tab: "trials")
        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'trial-'")).firstMatch)
        XCTAssertTrue(app.staticTexts["The service could not load this information. Please try again later."].waitForExistence(timeout: 10))
        XCTAssertFalse(app.descendants(matching: .any)["logo-loader"].exists)
        XCTAssertFalse(app.staticTexts["Loading opportunity…"].exists)
        XCTAssertTrue(app.buttons["Try again"].exists)
        capture("I1F4-trial-read-finished")
    }
    func testLegacyClubHomeOmitsColdWorkspaceReadFailure() {
        launch("club-offline")
        XCTAssertTrue(app.navigationBars["Home"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.descendants(matching: .any)["phase2-error"].exists)
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'draft is still here'")).firstMatch.exists)
        capture("I1F4-legacy-club-offline")
    }
    func testPublicPagesNeverLabelPageSizeAsOpenTotal() {
        launch("paged-public", tab: "trials")
        XCTAssertTrue(app.staticTexts["PAGE 1"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts["30 OPEN"].exists)
        scrollTo(app.buttons["Next"])
        XCTAssertLessThan(app.buttons["Next"].frame.maxY, app.tabBars.firstMatch.frame.minY)
        tap(app.buttons["Next"])
        XCTAssertTrue(app.staticTexts["PAGE 2"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts["1 OPEN"].exists)
        capture("I1F4-trials-page-two")
        tap(app.tabBars.buttons["Clubs"])
        tap(app.buttons["club-101"])
        XCTAssertTrue(app.staticTexts["Open now"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts["30 open"].exists)
        capture("I1F4-club-paged-posts")
    }
    func testSignedOutHomeSignInPreservesPublicTrialAndClubDestinations() {
        launch("player-signed-out")
        let signIn = app.buttons["home-sign-in"]
        XCTAssertTrue(signIn.waitForExistence(timeout: 10))
        XCTAssertTrue(signIn.isHittable)
        capture("I1F4-signed-out-home")
        tap(signIn)
        XCTAssertTrue(app.textFields["signin-email"].waitForExistence(timeout: 10))
        tap(app.buttons["Close sign in"])
        tap(app.tabBars.buttons["Clubs"]); tap(app.buttons["club-101"])
        XCTAssertTrue(app.staticTexts["The Saltings 3G, XW4 2QA"].waitForExistence(timeout: 10))
        tap(app.tabBars.buttons["Trials"])
        tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'trial-'")).firstMatch)
        XCTAssertTrue(app.staticTexts["Sign in from Account to apply with your approved adult profile."].waitForExistence(timeout: 10))
        tap(app.tabBars.buttons["Account"])
        tap(app.buttons["Sign In"])
        let email = app.textFields["signin-email"]
        tap(email); email.typeText("phase2@fixture.invalid")
        tap(app.buttons["signin-send-code"])
        let code = app.textFields["signin-code"]
        tap(code); code.typeText("123456")
        tap(app.buttons["signin-verify"])
        XCTAssertTrue(app.buttons["Sign Out"].waitForExistence(timeout: 10))
        tap(app.tabBars.buttons["Trials"])
        XCTAssertTrue(app.textFields["apply-position"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.scrollViews["phase2-trial-detail"].exists)
        XCTAssertFalse(app.staticTexts["Sign in from Account to apply with your approved adult profile."].exists)
        capture("I1F4-trial-retained-after-sign-in")
        tap(app.tabBars.buttons["Clubs"])
        XCTAssertTrue(app.staticTexts["The Saltings 3G, XW4 2QA"].waitForExistence(timeout: 10))
        capture("I1F4-club-retained-after-sign-in")
    }
    func testPermittedGreyBrandHeadersInBothAppearances() {
        for style in ["Light", "Dark"] {
            app.launchArguments = ["-phase2Fixture", "brand-grey", "-initialTab", "clubs", "-AppleInterfaceStyle", style]
            app.launch()
            tap(app.buttons["club-101"])
            XCTAssertTrue(app.staticTexts["Verified club"].waitForExistence(timeout: 10))
            capture("I1F4-grey-club-" + style.lowercased())
            tap(app.tabBars.buttons["Trials"])
            tap(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'trial-'")).firstMatch)
            XCTAssertTrue(app.scrollViews["phase2-trial-detail"].waitForExistence(timeout: 10))
            capture("I1F4-grey-trial-" + style.lowercased())
            app.terminate()
        }
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
        // A reused simulator must still exercise the first permission prompt.
        app.resetAuthorizationStatus(for: .location)
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
                XCTAssertTrue(app.otherElements["logo-loader"].waitForExistence(timeout: 15))
                XCTAssertEqual(app.otherElements["logo-loader"].label, "Loading")
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
