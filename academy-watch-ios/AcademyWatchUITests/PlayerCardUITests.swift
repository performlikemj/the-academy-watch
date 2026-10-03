import XCTest

/// The redesigned player page and scout desk card, driven through the labelled
/// offline review fixtures (`-floodlightPreview pc-<state>`). Requests are
/// answered inside the app before any networking; nothing reaches a server.
final class PlayerCardUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUp() {
        continueAfterFailure = false
    }

    override func tearDown() {
        app?.terminate()
        app = nil
    }

    private func launch(_ state: String, extra: [String] = []) {
        app = XCUIApplication()
        app.launchArguments = ["-floodlightPreview", "pc-\(state)", "-reviewAppearance", "light"] + extra
        app.launch()
    }

    private func element(_ identifier: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: identifier).firstMatch
    }

    @discardableResult
    private func require(_ identifier: String, timeout: TimeInterval = 15, file: StaticString = #filePath, line: UInt = #line) -> XCUIElement {
        let found = element(identifier)
        XCTAssertTrue(found.waitForExistence(timeout: timeout), "\(identifier) should exist", file: file, line: line)
        return found
    }

    /// Scrolls the page until the element is on screen.
    @discardableResult
    private func reveal(_ identifier: String, file: StaticString = #filePath, line: UInt = #line) -> XCUIElement {
        let found = element(identifier)
        for _ in 0 ..< 14 where !(found.exists && found.isHittable) {
            app.swipeUp(velocity: .slow)
        }
        XCTAssertTrue(found.exists, "\(identifier) should be reachable by scrolling", file: file, line: line)
        return found
    }

    func testHeroFactsSeasonAndOneLinePerMatch() {
        launch("photo")
        XCTAssertEqual(require("player-hero-name").label, "Kofi Asante-Reid")
        XCTAssertEqual(require("player-hero-confirmed").label, "Confirmed by Quillmere Athletic")
        XCTAssertEqual(require("player-photo").label, "Kofi Asante-Reid", "the photo's description is the player's name")
        XCTAssertFalse(element("player-no-photo").exists)

        reveal("player-facts-note")
        XCTAssertTrue(app.descendants(matching: .any)["Positions: RB, RWB"].exists)
        XCTAssertTrue(app.descendants(matching: .any)["Availability: Not looking"].exists)
        XCTAssertFalse(app.descendants(matching: .any).matching(NSPredicate(format: "label BEGINSWITH 'Agent'")).firstMatch.exists)

        XCTAssertTrue(reveal("season-tile-minutes").label.hasPrefix("Minutes, 90"))
        XCTAssertTrue(reveal("season-tile-discipline").label.contains("Clean"))
        XCTAssertEqual(
            reveal("season-source").label,
            "Built from 1 match. 1 confirmed by the club, 0 only reported by the player."
        )
        let card = reveal("match-card")
        XCTAssertTrue(card.label.contains("Club-confirmed"))
        XCTAssertTrue(card.label.contains("Matches the player's own report"))
        XCTAssertEqual(app.descendants(matching: .any).matching(identifier: "match-card").count, 1, "one line per match")
    }

    func testNoPhotoIsTheInitialsTile() {
        launch("no-photo")
        XCTAssertEqual(require("player-no-photo").label, "Kofi Asante-Reid — no photo yet")
        XCTAssertFalse(element("player-photo").exists)
    }

    func testNoMatchesIsAnHonestEmptyStateWithoutZeroTiles() {
        launch("no-matches")
        require("player-hero-name")
        let empty = reveal("season-empty")
        XCTAssertTrue(empty.label.contains("No matches recorded yet"))
        XCTAssertFalse(element("season-tile-minutes").exists)
        XCTAssertFalse(element("match-card").exists)
        XCTAssertFalse(element("season-error").exists)
        XCTAssertFalse(element("player-hero-confirmed").exists)
    }

    func testFullSeasonShowsTheLatestTenThenAll() {
        launch("full-season", extra: ["-pcAnchor", "season"])
        XCTAssertTrue(require("season-source").label.hasPrefix("Built from 22 matches. 16 confirmed by the club, 6 only reported by the player."))
        XCTAssertTrue(reveal("season-tile-appearances").label.contains("21"))
        let more = reveal("match-lines-more")
        XCTAssertEqual(more.label, "Show all 22 matches")
        more.tap()
        XCTAssertEqual(reveal("match-lines-more").label, "Show the latest 10")
    }

    func testAMismatchShowsTheClubFiguresAndNeverAccuses() {
        launch("mismatch", extra: ["-pcAnchor", "matches"])
        require("match-card")
        let cards = app.descendants(matching: .any).matching(identifier: "match-card")
        let differs = cards.matching(NSPredicate(format: "label CONTAINS %@", "Club figures shown · Differs from the player's report")).firstMatch
        XCTAssertTrue(differs.waitForExistence(timeout: 10))
        XCTAssertTrue(differs.label.contains("74 minutes"), "the club's figures are the line")
        reveal("season-source")
        XCTAssertTrue(cards.matching(NSPredicate(format: "label CONTAINS 'Self-reported'")).firstMatch.exists)
    }

    func testAGoalkeeperGetsKeeperTiles() {
        launch("keeper", extra: ["-pcAnchor", "season"])
        XCTAssertTrue(require("season-tile-keeper").label.hasPrefix("Saves, 13"))
        XCTAssertFalse(element("season-tile-contribution").exists)
    }

    func testAFailedReadOffersTryAgainAndNeverSaysNoMatches() {
        launch("read-failed", extra: ["-pcAnchor", "season", "-pcFailOnce"])
        let error = require("season-error-text")
        XCTAssertTrue(error.label.hasPrefix("The matches could not be loaded."))
        XCTAssertFalse(element("season-empty").exists, "a failed read is never an empty season")
        XCTAssertFalse(app.staticTexts["No matches recorded yet"].exists)

        require("season-retry").tap()
        XCTAssertTrue(element("match-card").waitForExistence(timeout: 15))
        XCTAssertFalse(element("season-error").exists)
        XCTAssertTrue(element("season-tile-minutes").exists)
    }

    func testProviderTotalsStayWholeAndTheClubLineIsNotAdded() {
        launch("provider", extra: ["-pcAnchor", "season"])
        XCTAssertTrue(require("season-tile-minutes").label.hasPrefix("Minutes, 2,412"))
        XCTAssertTrue(require("season-tile-appearances").label.contains("30"))
        XCTAssertTrue(reveal("season-source").label.contains("is not added to these totals"))
        XCTAssertTrue(reveal("match-card").exists)
    }

    func testAFailedTotalsReadBuildsFromTheMatchLogThatDidLoad() {
        launch("totals-failed", extra: ["-pcAnchor", "season"])
        XCTAssertTrue(require("season-error-text").label.hasPrefix("The season totals could not be loaded."))
        XCTAssertTrue(reveal("season-tile-appearances").label.contains("3"))
        XCTAssertFalse(element("season-empty").exists)
    }

    func testLongNamesStayReadableAtAccessibilityTextSizes() {
        launch("long-names", extra: ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityL"])
        let name = require("player-hero-name")
        XCTAssertEqual(name.label, "Maximilian-Alexander Oluwaseun Featherstonehaugh-Abernathy")
        let window = app.windows.firstMatch.frame
        XCTAssertGreaterThanOrEqual(name.frame.minX, window.minX)
        XCTAssertLessThanOrEqual(name.frame.maxX, window.maxX, "the name wraps inside the hero")
        let card = reveal("match-card")
        XCTAssertLessThanOrEqual(card.frame.maxX, window.maxX)
        XCTAssertTrue(card.label.contains("Greaveholme-under-Lyne Wanderers Reserves & Development"))
    }

    func testDeskCardsFollowTheWebCountersAndTheTableIsStillThere() {
        launch("desk", extra: ["-pcAnchor", "results"])
        let kofi = app.buttons["scout-player-900001"]
        XCTAssertTrue(kofi.waitForExistence(timeout: 20))
        XCTAssertTrue(kofi.label.contains("Kofi Asante-Reid"))
        XCTAssertTrue(kofi.label.contains("No photo yet"))
        XCTAssertFalse(kofi.label.contains("appearance"), "club-entered figures stay off the card")

        let provider = app.buttons["scout-player-900006"]
        for _ in 0 ..< 16 where !provider.exists { app.swipeUp() }
        XCTAssertTrue(provider.exists)
        XCTAssertTrue(provider.label.contains("30 appearances, 2,412 minutes"))

        for _ in 0 ..< 16 where !app.segmentedControls["scout-result-view"].isHittable { app.swipeDown() }
        app.segmentedControls["scout-result-view"].buttons["Table"].tap()
        XCTAssertTrue(app.buttons["scout-player-900001"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["scout-player-900001"].label.contains("No photo yet"), "the table keeps today's rows")
        app.segmentedControls["scout-result-view"].buttons["Cards"].tap()
        XCTAssertTrue(app.buttons["scout-player-900001"].label.contains("No photo yet"))
    }
}
