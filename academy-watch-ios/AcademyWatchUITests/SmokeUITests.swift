import Foundation
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

        let result = app.buttons.containing(.staticText, identifier: "W. Lankshear").firstMatch
        require(result, "Search should return W. Lankshear")
        saveScreenshot("02-lankshear-search.png")
        result.tap()

        require(app.navigationBars["W. Lankshear"], "W. Lankshear player detail should open")
        saveScreenshot("03-lankshear-detail.png")

        let seasonSection = app.staticTexts["SEASON STATS"]
        scrollUntilVisible(seasonSection, message: "Player detail should reach SEASON STATS")
        let seasonData = firstExistingElement(identifiers: ["season-club-row", "season-overview-row"])
        require(seasonData, "SEASON STATS should show a club row or stat overview")
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
        emailField.tap()
        emailField.typeText(email)
        let sendCode = require(app.buttons["signin-send-code"], "Send-code button should appear")
        sendCode.tap()

        let codeField = require(app.textFields["signin-code"], "Sign-in code field should appear")
        codeField.tap()
        codeField.typeText(code)
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
        require(app.staticTexts["Verified scout"], "Reviewer account should be scout-verified")
        shouldSignOut = true
        saveScreenshot("21-reviewer-account-signed-in.png")

        selectTab("Scout Desk")
        let search = require(app.textFields["scout-search"], "Scout Desk search field should be available")
        search.tap()
        search.typeText("Lankshear")
        let result = app.buttons.containing(.staticText, identifier: "W. Lankshear").firstMatch
        require(result, "Search should return W. Lankshear")
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
        scrollUntilHittable(signOut, message: "Signed-in Account should offer sign out")
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
        scrollUntilHittable(signOut, message: "Existing session should be possible to sign out")
        signOut.tap()
        require(app.buttons["account-sign-in"], "Account should return to signed-out state")
    }

    private func scrollUntilVisible(_ element: XCUIElement, message: String) {
        let scrollView = require(app.scrollViews.firstMatch, "Player detail should contain a scroll view")
        for _ in 0 ..< 14 {
            if element.waitForExistence(timeout: 1) {
                return
            }
            scrollView.swipeUp()
        }
        XCTFail(message)
    }

    private func scrollUntilHittable(_ element: XCUIElement, message: String) {
        let scrollView = require(app.scrollViews.firstMatch, "Screen should contain a scroll view")
        for _ in 0 ..< 14 {
            if element.waitForExistence(timeout: 1), element.isHittable {
                return
            }
            scrollView.swipeUp()
        }
        XCTFail(message)
    }

    private func firstExistingElement(identifiers: [String]) -> XCUIElement {
        for _ in 0 ..< 8 {
            for identifier in identifiers {
                let candidate = element(identifier: identifier)
                if candidate.waitForExistence(timeout: 1) {
                    return candidate
                }
            }
            app.scrollViews.firstMatch.swipeUp()
        }
        return element(identifier: identifiers[0])
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
        guard tapTabIfPresent("Lists") else { return }
        let row = app.buttons.containing(.staticText, identifier: listName).firstMatch
        guard row.waitForExistence(timeout: 8) else {
            listNameToDelete = nil
            return
        }
        row.swipeLeft()
        let delete = firstElement(withIdentifierPrefix: "list-delete-", type: .button)
        guard delete.waitForExistence(timeout: 3) else { return }
        delete.tap()
        _ = row.waitForNonExistence(timeout: 8)
        listNameToDelete = nil
    }

    private func removeSmokeWatchlistEntryIfNeeded() {
        guard let playerID = watchlistPlayerIDToRemove else { return }
        guard tapTabIfPresent("Watchlist") else { return }
        let row = app.buttons["watchlist-player-\(playerID)"]
        guard row.waitForExistence(timeout: 8) else {
            watchlistPlayerIDToRemove = nil
            return
        }
        row.tap()
        let remove = app.buttons["watchlist-remove-\(playerID)"]
        guard remove.waitForExistence(timeout: 8) else { return }
        remove.tap()
        _ = app.buttons["watchlist-add-\(playerID)"].waitForExistence(timeout: 8)
        watchlistPlayerIDToRemove = nil
    }

    private func signOutIfNeeded() {
        guard shouldSignOut, tapTabIfPresent("Account") else { return }
        let signOut = app.buttons["Sign Out"].firstMatch
        scrollUntilHittable(signOut, message: "Reviewer session should be possible to sign out")
        signOut.tap()
        _ = app.buttons["account-sign-in"].waitForExistence(timeout: 8)
        shouldSignOut = false
    }

    private func tapTabIfPresent(_ name: String) -> Bool {
        let tab = app.tabBars.buttons[name]
        guard tab.waitForExistence(timeout: 8) else { return false }
        tab.tap()
        return true
    }
}
