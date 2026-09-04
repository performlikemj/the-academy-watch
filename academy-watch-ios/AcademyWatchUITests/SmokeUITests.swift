import Foundation
import UIKit
import XCTest

final class SmokeUITests: XCTestCase {
    private let networkTimeout: TimeInterval = 60
    private var app: XCUIApplication!
    private var watchlistPlayerIDToRemove: String?
    private var listNameToDelete: String?
    private var shouldSignOut = false

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launch()
    }

    override func tearDownWithError() throws {
        if watchlistPlayerIDToRemove != nil || listNameToDelete != nil || shouldSignOut {
            app.terminate()
            app.launch()
            dismissPlayerPromptIfNeeded(timeout: 2)
            deleteSmokeListIfNeeded()
            removeSmokeWatchlistEntryIfNeeded()
            signOutIfNeeded()
        }
        app.terminate()
        app = nil
    }

    func testAnonymousWalk() throws {
        ensureSignedOut()
        selectTab("Scout Desk")

        let firstPlayer = firstElement(withIdentifierPrefix: "scout-player-", type: .button)
        require(firstPlayer, "Scout Desk should show at least one player row")
        saveScreenshot("01-scout-desk.png")

        let search = require(app.textFields["scout-search"], "Scout Desk search field should be available")
        search.tap()
        search.typeText("Lankshear")
        dismissKeyboardIfNeeded()

        let scoutDeskScroll = require(app.scrollViews["scout-desk-scroll"], "Scout Desk results should be scrollable")
        let result = scoutDeskScroll.buttons["scout-player-393195"]
        require(result, "Search should return W. Lankshear")
        scrollUntilOnScreen(result, in: scoutDeskScroll, message: "W. Lankshear result should be visible")
        saveScreenshot("02-lankshear-search.png")
        result.tap()

        require(app.navigationBars["W. Lankshear"], "W. Lankshear player detail should open")
        saveScreenshot("03-lankshear-detail.png")

        let seasonSection = app.staticTexts["SEASON STATS"]
        require(seasonSection, "Player detail should contain SEASON STATS")
        let seasonClubRow = require(element(identifier: "season-club-row"), "SEASON STATS should show a club row")
        let playerDetailScroll = require(
            app.scrollViews["player-detail-scroll"],
            "Player detail should contain a scroll view"
        )
        scrollUntilOnScreen(
            seasonClubRow,
            in: playerDetailScroll,
            message: "SEASON STATS club row should be visible"
        )
        if !isOnScreen(seasonSection) {
            drag(in: playerDetailScroll, fromFraction: 0.42, toFraction: 0.50)
        }
        XCTAssertTrue(isOnScreen(seasonSection), "SEASON STATS heading should be visible in the screenshot")
        XCTAssertTrue(
            seasonClubRow.label.localizedCaseInsensitiveContains("Middlesbrough"),
            "W. Lankshear SEASON STATS club row should identify Middlesbrough"
        )
        XCTAssertTrue(isOnScreen(seasonClubRow), "Middlesbrough club row should be visible in the screenshot")
        XCTAssertFalse(
            app.staticTexts["The service response format was not recognized."].exists,
            "SEASON STATS must decode the live response"
        )
        saveScreenshot("04-season-stats.png")

        let back = require(
            app.navigationBars.buttons["Scout Desk"],
            "Player detail should provide a back button"
        )
        back.tap()
        require(app.textFields["scout-search"], "Back should return to Scout Desk")
        dismissKeyboardIfNeeded()

        selectTab("Watchlist")
        require(
            app.staticTexts["Sign in to build your watchlist"],
            "Anonymous Watchlist should show its signed-out state"
        )
        saveScreenshot("05-anonymous-watchlist.png")

        selectTab("Lists")
        require(
            app.staticTexts["Sign in to organize your scouting"],
            "Anonymous Lists should show its signed-out state"
        )
        saveScreenshot("06-anonymous-lists.png")

        selectTab("Account")
        require(
            app.staticTexts["Your scout account"],
            "Anonymous Account should show its signed-out state"
        )
        saveScreenshot("07-anonymous-account.png")
    }

    func testReviewerScoutWalk() throws {
        let environment = ProcessInfo.processInfo.environment
        guard let email = environment["REVIEW_SCOUT_EMAIL"], !email.isEmpty,
              let code = environment["REVIEW_SCOUT_CODE"], !code.isEmpty
        else {
            throw XCTSkip(
                "Reviewer scout credentials are absent; set TEST_RUNNER_REVIEW_SCOUT_EMAIL and TEST_RUNNER_REVIEW_SCOUT_CODE."
            )
        }

        ensureSignedOut()
        selectTab("Account")
        let signIn = require(app.buttons["account-sign-in"], "Account should offer sign in")
        signIn.tap()

        let emailField = require(app.textFields["signin-email"], "Sign-in email field should appear")
        pasteSensitiveValue(email, into: emailField)
        let sendCode = require(app.buttons["signin-send-code"], "Send-code button should appear")
        sendCode.tap()

        let codeField = require(app.textFields["signin-code"], "Sign-in code field should appear")
        pasteSensitiveValue(code, into: codeField)
        let verify = require(app.buttons["signin-verify"], "Verify button should appear")
        verify.tap()

        let signedInAccount = element(identifier: "account-signed-in")
        if !signedInAccount.waitForExistence(timeout: 12) {
            let signInError = app.staticTexts["signin-error"]
            if signInError.waitForExistence(timeout: 3) {
                clearSensitiveCodeField(codeField)
                saveScreenshot("21-reviewer-sign-in-failed.png")
                XCTFail("Reviewer scout sign-in failed: \(signInError.label)")
                return
            }
        }
        dismissPlayerPromptIfNeeded(timeout: 8)
        require(signedInAccount, "Reviewer scout should be signed in")
        shouldSignOut = true
        require(app.staticTexts["Verified scout"], "Reviewer account should be scout-verified")
        saveScreenshot("21-reviewer-account-signed-in.png")

        selectTab("Scout Desk")
        let search = require(app.textFields["scout-search"], "Scout Desk search field should be available")
        search.tap()
        search.typeText("Lankshear")
        dismissKeyboardIfNeeded()
        let scoutDeskScroll = require(app.scrollViews["scout-desk-scroll"], "Scout Desk results should be scrollable")
        let result = scoutDeskScroll.buttons["scout-player-393195"]
        require(result, "Search should return W. Lankshear")
        scrollUntilOnScreen(result, in: scoutDeskScroll, message: "W. Lankshear result should be visible")
        result.tap()
        require(app.navigationBars["W. Lankshear"], "W. Lankshear player detail should open")
        saveScreenshot("22-reviewer-player.png")

        let addButton = firstElement(withIdentifierPrefix: "watchlist-add-", type: .button)
        require(addButton, "Player should not already be in the review account watchlist")
        let playerID = String(addButton.identifier.dropFirst("watchlist-add-".count))
        XCTAssertFalse(playerID.isEmpty, "Watchlist button should identify its player")
        addButton.tap()
        watchlistPlayerIDToRemove = playerID

        require(
            app.buttons["watchlist-remove-\(playerID)"],
            "Watchlist mutation should finish on player detail"
        )
        selectTab("Watchlist")
        let watchlistRow = require(
            app.buttons["watchlist-player-\(playerID)"],
            "Watchlist should show the newly added player"
        )
        saveScreenshot("23-watchlist-added.png")
        watchlistRow.tap()

        let removeButton = require(
            app.buttons["watchlist-remove-\(playerID)"],
            "Watchlisted player detail should offer removal"
        )
        removeButton.tap()
        require(
            app.buttons["watchlist-add-\(playerID)"],
            "Watchlist removal should finish on player detail"
        )
        watchlistPlayerIDToRemove = nil
        let watchlistBack = require(
            app.navigationBars.buttons["Watchlist"],
            "Player detail should return to Watchlist"
        )
        watchlistBack.tap()
        require(app.tabBars.buttons["Watchlist"], "Watchlist should remain usable after removal")
        XCTAssertFalse(
            app.buttons["watchlist-player-\(playerID)"].waitForExistence(timeout: 3),
            "Removed player should no longer appear in Watchlist"
        )
        saveScreenshot("24-watchlist-removed.png")

        selectTab("Lists")
        let createList = require(app.buttons["lists-create"].firstMatch, "Lists should offer list creation")
        createList.tap()
        let newListAlert = require(app.alerts["New List"], "New-list alert should appear")
        let listNameField = require(newListAlert.textFields.firstMatch, "New-list name field should appear")
        let listName = "UI smoke \(Int(Date().timeIntervalSince1970))"
        listNameField.tap()
        listNameField.typeText(listName)
        let createSubmit = require(
            newListAlert.buttons["lists-create-submit"].firstMatch,
            "New-list alert should offer Create"
        )
        createSubmit.tap()
        listNameToDelete = listName

        let createdListText = require(app.staticTexts[listName], "Created smoke list should appear")
        saveScreenshot("25-list-created.png")
        let createdListRow = app.buttons.containing(.staticText, identifier: listName).firstMatch
        require(createdListRow, "Created list should expose a row action")
        createdListRow.swipeLeft()
        let deleteList = firstElement(withIdentifierPrefix: "list-delete-", type: .button)
        require(deleteList, "Created list should expose its delete action")
        deleteList.tap()
        require(app.buttons["lists-create"].firstMatch, "Lists should remain usable after deletion")
        XCTAssertFalse(
            createdListText.waitForExistence(timeout: 3),
            "Deleted smoke list should no longer appear"
        )
        listNameToDelete = nil
        saveScreenshot("26-list-deleted.png")

        selectTab("Account")
        require(element(identifier: "account-signed-in"), "Signed-in Account should remain available")
        saveScreenshot("27-reviewer-account.png")

        let signOut = app.buttons["Sign Out"].firstMatch
        guard scrollUntilHittable(signOut, message: "Signed-in Account should offer sign out") else { return }
        signOut.tap()
        require(app.buttons["account-sign-in"], "Account should return to signed-out state")
        shouldSignOut = false
        saveScreenshot("30-signed-out-again.png")
    }

    @discardableResult
    private func require(
        _ element: XCUIElement,
        _ message: String,
        timeout: TimeInterval? = nil,
        file: StaticString = #filePath,
        line: UInt = #line
    ) -> XCUIElement {
        XCTAssertTrue(
            element.waitForExistence(timeout: timeout ?? networkTimeout),
            message,
            file: file,
            line: line
        )
        return element
    }

    private func selectTab(_ name: String) {
        let tab = require(app.tabBars.buttons[name], "\(name) tab should be available")
        tab.tap()
        dismissPlayerPromptIfNeeded(timeout: 1)
    }

    private func ensureSignedOut() {
        let accountTab = require(app.tabBars.buttons["Account"], "Account tab should be available")
        accountTab.tap()
        dismissPlayerPromptIfNeeded(timeout: 5)
        accountTab.tap()

        if app.buttons["account-sign-in"].waitForExistence(timeout: 2) {
            return
        }

        require(element(identifier: "account-signed-in"), "Account should show a signed-in or signed-out state")
        let signOut = app.buttons["Sign Out"].firstMatch
        guard scrollUntilHittable(signOut, message: "Existing session should be possible to sign out") else { return }
        signOut.tap()
        require(app.buttons["account-sign-in"], "Account should return to signed-out state")
    }

    private func scrollUntilOnScreen(
        _ element: XCUIElement,
        in scrollView: XCUIElement,
        message: String
    ) {
        for _ in 0 ..< 14 {
            if element.waitForExistence(timeout: 1), isOnScreen(element) {
                return
            }
            dragUp(in: scrollView)
        }
        XCTFail(message)
    }

    private func dragUp(in scrollView: XCUIElement) {
        drag(in: scrollView, fromFraction: 0.62, toFraction: 0.42)
    }

    private func drag(
        in scrollView: XCUIElement,
        fromFraction: CGFloat,
        toFraction: CGFloat
    ) {
        let frame = scrollView.frame
        let windowFrame = app.windows.firstMatch.frame
        let dragFrame = frame.intersection(windowFrame)
        guard !dragFrame.isEmpty, !dragFrame.isNull, !dragFrame.isInfinite else {
            if fromFraction < toFraction {
                scrollView.swipeDown()
            } else {
                scrollView.swipeUp()
            }
            return
        }

        let start = app.coordinate(
            withNormalizedOffset: CGVector(
                dx: dragFrame.midX / windowFrame.width,
                dy: (dragFrame.minY + dragFrame.height * fromFraction) / windowFrame.height
            )
        )
        let finish = app.coordinate(
            withNormalizedOffset: CGVector(
                dx: dragFrame.midX / windowFrame.width,
                dy: (dragFrame.minY + dragFrame.height * toFraction) / windowFrame.height
            )
        )
        start.press(
            forDuration: 0.05,
            thenDragTo: finish,
            withVelocity: .slow,
            thenHoldForDuration: 0
        )
    }

    private func isOnScreen(_ element: XCUIElement) -> Bool {
        guard element.exists else { return false }
        let frame = element.frame
        guard !frame.isEmpty, !frame.isNull, !frame.isInfinite else { return false }

        let windowFrame = app.windows.firstMatch.frame
        var visibleMaxY = windowFrame.maxY
        let tabBar = app.tabBars.firstMatch
        if tabBar.exists {
            visibleMaxY = min(visibleMaxY, tabBar.frame.minY)
        }
        let keyboard = app.keyboards.firstMatch
        if keyboard.exists {
            visibleMaxY = min(visibleMaxY, keyboard.frame.minY)
        }
        let navigationBar = app.navigationBars.firstMatch
        let visibleMinY = navigationBar.exists ? max(windowFrame.minY, navigationBar.frame.maxY) : windowFrame.minY
        guard visibleMaxY > visibleMinY else { return false }

        let visibleFrame = CGRect(
            x: windowFrame.minX,
            y: visibleMinY,
            width: windowFrame.width,
            height: visibleMaxY - visibleMinY
        )
        let intersection = visibleFrame.intersection(frame)
        let requiredVisibleHeight = min(frame.height, 44)
        return intersection.width > 0 && intersection.height >= requiredVisibleHeight
    }

    @discardableResult
    private func scrollUntilHittable(_ element: XCUIElement, message: String) -> Bool {
        let scrollView = require(app.scrollViews.firstMatch, "Screen should contain a scroll view")
        for _ in 0 ..< 14 {
            if element.waitForExistence(timeout: 1), element.isHittable {
                return true
            }
            scrollView.swipeUp()
        }
        XCTFail(message)
        return false
    }

    private func element(identifier: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: identifier).firstMatch
    }

    private func firstElement(
        withIdentifierPrefix prefix: String,
        type: XCUIElement.ElementType
    ) -> XCUIElement {
        app.descendants(matching: type)
            .matching(NSPredicate(format: "identifier BEGINSWITH %@", prefix))
            .firstMatch
    }

    private func saveScreenshot(_ fileName: String) {
        let screenshot = XCUIScreen.main.screenshot()
        guard let outputPath = ProcessInfo.processInfo.environment["SMOKE_OUT"], !outputPath.isEmpty else {
            let attachment = XCTAttachment(screenshot: screenshot)
            attachment.name = fileName
            attachment.lifetime = .keepAlways
            add(attachment)
            return
        }

        do {
            let directory = URL(fileURLWithPath: outputPath, isDirectory: true)
            try FileManager.default.createDirectory(
                at: directory,
                withIntermediateDirectories: true
            )
            try screenshot.pngRepresentation.write(to: directory.appendingPathComponent(fileName), options: .atomic)
        } catch {
            XCTFail("Could not save UI smoke screenshot \(fileName): \(error.localizedDescription)")
        }
    }

    private func pasteSensitiveValue(_ value: String, into field: XCUIElement) {
        UIPasteboard.general.string = value
        defer { UIPasteboard.general.string = "" }
        field.press(forDuration: 1.2)
        let paste = require(app.menuItems["Paste"], "Sensitive field should offer the Paste action")
        paste.tap()
    }

    private func dismissPlayerPromptIfNeeded(timeout: TimeInterval) {
        let dismiss = app.buttons["Not now"]
        guard dismiss.waitForExistence(timeout: timeout) else { return }
        dismiss.tap()
        _ = dismiss.waitForNonExistence(timeout: 5)
    }

    private func dismissKeyboardIfNeeded() {
        let keyboard = app.keyboards.firstMatch
        guard keyboard.waitForExistence(timeout: 1) else { return }
        let searchKey = keyboard.buttons["Search"]
        guard searchKey.waitForExistence(timeout: 2) else { return }
        searchKey.tap()
        _ = keyboard.waitForNonExistence(timeout: 5)
    }

    private func clearSensitiveCodeField(_ codeField: XCUIElement) {
        codeField.tap()
        codeField.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: 32))
        let keyboard = app.keyboards.firstMatch
        guard keyboard.waitForExistence(timeout: 1) else { return }
        app.scrollViews.firstMatch.swipeUp()
        _ = keyboard.waitForNonExistence(timeout: 5)
    }

    private func deleteSmokeListIfNeeded() {
        guard let listName = listNameToDelete else { return }
        guard tapTabIfPresent("Lists") else {
            recordCleanupFailure("list named \(listName): Lists tab was unavailable")
            return
        }
        let row = app.buttons.containing(.staticText, identifier: listName).firstMatch
        guard row.waitForExistence(timeout: 8) else {
            recordCleanupFailure("list named \(listName): row was not found")
            return
        }
        row.swipeLeft()
        let delete = firstElement(withIdentifierPrefix: "list-delete-", type: .button)
        guard delete.waitForExistence(timeout: 3) else {
            recordCleanupFailure("list named \(listName): delete action was not found")
            return
        }
        delete.tap()
        guard row.waitForNonExistence(timeout: 8) else {
            recordCleanupFailure("list named \(listName): row remained after delete")
            return
        }
        listNameToDelete = nil
    }

    private func removeSmokeWatchlistEntryIfNeeded() {
        guard let playerID = watchlistPlayerIDToRemove else { return }
        guard tapTabIfPresent("Watchlist") else {
            recordCleanupFailure("watchlist player id \(playerID): Watchlist tab was unavailable")
            return
        }
        let row = app.buttons["watchlist-player-\(playerID)"]
        guard row.waitForExistence(timeout: 8) else {
            recordCleanupFailure("watchlist player id \(playerID): row was not found")
            return
        }
        row.tap()
        let remove = app.buttons["watchlist-remove-\(playerID)"]
        guard remove.waitForExistence(timeout: 8) else {
            recordCleanupFailure("watchlist player id \(playerID): remove action was not found")
            return
        }
        remove.tap()
        guard app.buttons["watchlist-add-\(playerID)"].waitForExistence(timeout: 8) else {
            recordCleanupFailure("watchlist player id \(playerID): removal did not finish")
            return
        }
        watchlistPlayerIDToRemove = nil
    }

    private func recordCleanupFailure(_ detail: String) {
        XCTFail("LIVE ACCOUNT CLEANUP REQUIRED — \(detail)")
    }

    private func signOutIfNeeded() {
        guard shouldSignOut else { return }
        guard tapTabIfPresent("Account") else {
            recordCleanupFailure("reviewer session: Account tab was unavailable for sign-out")
            return
        }
        let signOut = app.buttons["Sign Out"].firstMatch
        guard scrollUntilHittable(signOut, message: "LIVE ACCOUNT CLEANUP REQUIRED — reviewer session could not reach Sign Out") else {
            return
        }
        signOut.tap()
        guard app.buttons["account-sign-in"].waitForExistence(timeout: 8) else {
            recordCleanupFailure("reviewer session: signed-out state did not appear")
            return
        }
        shouldSignOut = false
    }

    private func tapTabIfPresent(_ name: String) -> Bool {
        let tab = app.tabBars.buttons[name]
        guard tab.waitForExistence(timeout: 8) else { return false }
        tab.tap()
        return true
    }
}
