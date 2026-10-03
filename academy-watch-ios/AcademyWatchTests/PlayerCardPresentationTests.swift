import XCTest
@testable import AcademyWatch

/// The wording rules for the player card and the season read view. These are
/// the web's `tests/player-card.test.mjs` cases, so both clients say the same
/// thing about the same server answer.
final class PlayerCardPresentationTests: XCTestCase {
    // MARK: Builders (server-shaped JSON, decoded like a real response)

    static func decode<T: Decodable>(_ type: T.Type, _ object: Any) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: JSONSerialization.data(withJSONObject: object))
    }

    static func line(_ overrides: [String: Any?] = [:]) throws -> PlayerMatchLine {
        var object: [String: Any?] = [
            "key": "2026-09-20|skerraby united", "season": 2026, "match_date": "2026-09-20",
            "opponent": "Skerraby United", "competition": "Wendle & District Senior League, Premier Division",
            "home_away": "home", "result_for": 3, "result_against": 1, "minutes": 90, "goals": 0,
            "assists": 0, "yellows": 0, "reds": 0, "saves": nil, "goals_conceded": nil,
            "confirmation": "club_confirmed", "self_report": "matches", "shared_slot": false,
        ]
        overrides.forEach { object[$0.key] = $0.value }
        return try decode(PlayerMatchLine.self, object.mapValues { $0 ?? NSNull() })
    }

    static func totals(_ overrides: [String: Any?] = [:]) throws -> PlayerMatchLineTotals {
        var object: [String: Any?] = [
            "matches": 1, "appearances": 1, "full_matches": 1, "minutes": 90, "goals": 0, "assists": 0,
            "yellows": 0, "reds": 0, "cards_known": true, "saves": nil, "goals_conceded": nil,
            "keeper_matches": 0, "club_confirmed": 1, "self_reported_only": 0, "differing": 0,
        ]
        overrides.forEach { object[$0.key] = $0.value }
        return try decode(PlayerMatchLineTotals.self, object.mapValues { $0 ?? NSNull() })
    }

    static func stats(_ overrides: [String: Any?] = [:]) throws -> PlayerSeasonStats {
        var object: [String: Any?] = [
            "player_id": 42, "season": "2026/2027", "appearances": 30, "minutes": 2412, "goals": 4,
            "assists": 6, "source": "api-football", "clubs": [],
        ]
        overrides.forEach { object[$0.key] = $0.value }
        return try decode(PlayerSeasonStats.self, object.compactMapValues { $0 })
    }

    /// The server's own answer for a review state (`sim/build-player-card-fixtures.py`).
    static func serverSeason(_ state: String) throws -> PlayerMatchLineSeason {
        let url = try XCTUnwrap(Bundle.main.url(forResource: "player_card_states", withExtension: "json"))
        let root = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        let entry = try XCTUnwrap((root["states"] as? [String: Any])?[state] as? [String: Any])
        let response = try decode(PlayerMatchLinesResponse.self, try XCTUnwrap(entry["matches"]))
        return try XCTUnwrap(response.seasons.first)
    }

    private func tile(_ summary: SeasonSummary, _ key: String) -> SeasonTile? {
        summary.tiles.first { $0.key == key }
    }

    // MARK: Season block

    func testTheSingleConfirmedMatchReadsExactlyAsTheApprovedMockup() throws {
        let season = try Self.serverSeason("photo")
        let summary = PlayerCardText.summarizeSeason(lines: season.lines, totals: season.totals)

        XCTAssertEqual(summary.source, .grain)
        XCTAssertEqual(summary.tiles.map(\.key), ["minutes", "appearances", "contribution", "discipline"])
        XCTAssertEqual(tile(summary, "minutes")?.value, "90")
        XCTAssertEqual(tile(summary, "minutes")?.note, "Every minute of the 1 match recorded")
        XCTAssertEqual(tile(summary, "minutes")?.share, 1)
        XCTAssertEqual(tile(summary, "appearances")?.value, "1")
        XCTAssertEqual(tile(summary, "appearances")?.shortLabel, "Apps")
        XCTAssertEqual(tile(summary, "discipline")?.value, "Clean")
        XCTAssertEqual(
            summary.sentence,
            "Built from 1 match. 1 confirmed by the club, 0 only reported by the player."
        )
        XCTAssertTrue(summary.confirmed)
    }

    func testZerosAreQuietAndNeverListedAsFacts() throws {
        let summary = PlayerCardText.summarizeSeason(lines: [try Self.line()], totals: try Self.totals())
        let contribution = try XCTUnwrap(tile(summary, "contribution"))
        XCTAssertEqual(contribution.value, "0")
        XCTAssertTrue(contribution.quiet)
        XCTAssertEqual(contribution.note, "No goals or assists yet")
        XCTAssertEqual(PlayerCardText.lineSummary(try Self.line()), "No goals, assists or cards")
    }

    func testDisciplineSaysCleanOnlyWhenCardCountsAreStated() throws {
        let unknown = PlayerCardText.summarizeSeason(
            lines: [try Self.line(["yellows": nil, "reds": nil])],
            totals: try Self.totals(["yellows": nil, "reds": nil, "cards_known": false])
        )
        XCTAssertNil(tile(unknown, "discipline"), "unknown is not clean: no tile at all")

        let carded = PlayerCardText.summarizeSeason(
            lines: [try Self.line()], totals: try Self.totals(["yellows": 3, "reds": 1])
        )
        XCTAssertEqual(tile(carded, "discipline")?.value, "4 cards")
        XCTAssertEqual(tile(carded, "discipline")?.note, "3 yellow · 1 red")
        XCTAssertEqual(PlayerCardText.lineSummary(try Self.line(["yellows": nil, "reds": nil])), "No goals or assists")
    }

    func testAFullMixedSeasonStatesItsSourcesWithoutAccusingAnyone() throws {
        let season = try Self.serverSeason("full-season")
        let summary = PlayerCardText.summarizeSeason(lines: season.lines, totals: season.totals)

        XCTAssertEqual(season.lines.count, 22)
        XCTAssertEqual(tile(summary, "minutes")?.value, PlayerCardText.grouped(season.totals.minutes))
        XCTAssertEqual(tile(summary, "appearances")?.note, "Played in 21 of 22 matches recorded")
        XCTAssertEqual(tile(summary, "contribution")?.value, "7")
        XCTAssertEqual(tile(summary, "contribution")?.note, "2 goals · 5 assists")
        XCTAssertEqual(
            summary.sentence,
            "Built from 22 matches. 16 confirmed by the club, 6 only reported by the player. "
                + "Where the two reports differ, the club's figures are used."
        )
        // The tiles are the server's totals, which are the server's lines added once each.
        XCTAssertEqual(season.totals.minutes, season.lines.reduce(0) { $0 + ($1.minutes ?? 0) })
        XCTAssertEqual(season.totals.matches, season.lines.count)
    }

    func testOnlySelfReportedMatchesGetNoGreenTick() throws {
        let line = try Self.line(["confirmation": "self_reported", "self_report": nil])
        let summary = PlayerCardText.summarizeSeason(
            lines: [line], totals: try Self.totals(["club_confirmed": 0, "self_reported_only": 1])
        )
        XCTAssertFalse(summary.confirmed)
        XCTAssertEqual(
            summary.sentence,
            "Built from 1 match. 0 confirmed by the club, 1 only reported by the player."
        )
    }

    func testNoMatchesYetIsAnHonestEmptyStateWithNoZeroTiles() throws {
        let none = PlayerCardText.summarizeSeason()
        XCTAssertEqual(none.source, .none)
        XCTAssertTrue(none.tiles.isEmpty)
        XCTAssertNil(none.sentence)
        let zero = PlayerCardText.summarizeSeason(totals: try Self.totals(["matches": 0, "appearances": 0, "minutes": 0]))
        XCTAssertEqual(zero.source, .none)
    }

    func testGoalkeepersGetKeeperFiguresAndUnknownIsNotZero() throws {
        let season = try Self.serverSeason("keeper")
        let summary = PlayerCardText.summarizeSeason(lines: season.lines, totals: season.totals, goalkeeper: true)
        XCTAssertNil(tile(summary, "contribution"))
        XCTAssertEqual(tile(summary, "keeper")?.value, "13")
        XCTAssertEqual(tile(summary, "keeper")?.note, "3 conceded in 3 matches")

        let unknown = PlayerCardText.summarizeSeason(lines: [try Self.line()], totals: try Self.totals(), goalkeeper: true)
        XCTAssertEqual(tile(unknown, "keeper")?.value, "–")
        XCTAssertEqual(tile(unknown, "keeper")?.quiet, true)
        XCTAssertEqual(tile(unknown, "keeper")?.note, "No keeper figures recorded yet")

        let concededOnly = PlayerCardText.summarizeSeason(
            lines: [try Self.line()],
            totals: try Self.totals(["goals_conceded": 2, "keeper_matches": 1]), goalkeeper: true
        )
        XCTAssertEqual(tile(concededOnly, "keeper")?.label, "Conceded")
        XCTAssertEqual(tile(concededOnly, "keeper")?.value, "2")

        XCTAssertEqual(
            PlayerCardText.lineSummary(try Self.line(["saves": 3, "goals_conceded": 0]), goalkeeper: true),
            "3 saves · none conceded"
        )
        XCTAssertEqual(PlayerCardText.lineSummary(try Self.line(), goalkeeper: true), "No cards")
        XCTAssertEqual(
            PlayerCardText.lineSummary(try Self.line(["yellows": nil, "reds": nil]), goalkeeper: true),
            "No keeper figures recorded"
        )
    }

    func testProviderTotalsAreKeptWholeLabelledAndNeverAddedToTheLines() throws {
        let provider = try XCTUnwrap(PlayerCardText.providerTotals(try Self.stats(["yellows": 3, "reds": 0])))
        let clubLine = try Self.line(["self_report": nil])
        let summary = PlayerCardText.summarizeSeason(lines: [clubLine], totals: try Self.totals(), provider: provider)

        XCTAssertEqual(summary.source, .provider)
        XCTAssertEqual(tile(summary, "minutes")?.value, "2,412", "provider minutes, not 2,412 + 90")
        XCTAssertEqual(tile(summary, "appearances")?.value, "30", "provider appearances, not 31")
        XCTAssertNil(tile(summary, "appearances")?.note)
        XCTAssertEqual(tile(summary, "minutes")?.note, "80 minutes a game across 30 appearances")
        XCTAssertEqual(tile(summary, "discipline")?.value, "3 cards")
        XCTAssertFalse(summary.confirmed)
        XCTAssertEqual(
            summary.sentence,
            "Totals come from public match data. The 1 match entered by the club or the player is listed below and is not added to these totals."
        )
    }

    func testFrozenModeKeepsThePublicDataFreshnessLine() throws {
        let stats = try Self.stats([
            "source": "club",
            "public_match_data": [
                "available": true, "as_of": "2026-05-30T00:00:00Z",
                "totals": ["appearances": 12, "minutes": 900, "goals": 1, "assists": 2],
            ],
        ])
        let provider = try XCTUnwrap(PlayerCardText.providerTotals(stats))
        XCTAssertEqual(provider.appearances, 12)
        XCTAssertEqual(provider.asOf, "2026-05-30T00:00:00Z")
        let summary = PlayerCardText.summarizeSeason(provider: provider, frozen: true)
        XCTAssertEqual(summary.sentence, "Public match data — last updated 2026-05-30.")

        let unavailable = try Self.stats(["public_match_data": ["available": false, "totals": NSNull()]])
        XCTAssertNil(PlayerCardText.providerTotals(unavailable), "a frozen block with no provider play is not provider data")
    }

    func testAnEmptyOrGrainSourcedStatsResponseIsNotProviderData() throws {
        XCTAssertNil(PlayerCardText.providerTotals(nil))
        XCTAssertNil(PlayerCardText.providerTotals(try Self.stats(["appearances": 0, "minutes": 0])))
        XCTAssertNil(PlayerCardText.providerTotals(try Self.stats(["source": "club"])))
        XCTAssertNil(PlayerCardText.providerTotals(try Self.stats(["provenance": ["primary_source": "self-reported"]])))
        XCTAssertNil(PlayerCardText.providerTotals(try Self.stats(["provenance": ["source": "user"]])))
        XCTAssertNotNil(PlayerCardText.providerTotals(try Self.stats(["provenance": ["primary_source": "journey"]])))
    }

    func testLimitedCoverageProviderTotalsLeaveTheMinutesTileOut() throws {
        let provider = try XCTUnwrap(PlayerCardText.providerTotals(try Self.stats(["minutes": 0])))
        let summary = PlayerCardText.summarizeSeason(provider: provider, minutesKnown: false)
        XCTAssertNil(tile(summary, "minutes"))
        XCTAssertEqual(summary.tiles.first?.key, "appearances")
    }

    func testProviderTotalsWithoutStatedCardsShowNoDisciplineTile() throws {
        let provider = try XCTUnwrap(PlayerCardText.providerTotals(try Self.stats()))
        XCTAssertNil(tile(PlayerCardText.summarizeSeason(provider: provider), "discipline"))
    }

    func testProviderMatchRowsAreAWitnessOfPlayWhenTheTotalsReadIsEmptyOrFailed() throws {
        let rows = try Self.decode([PlayerRecentFixture].self, [
            ["id": 1, "fixture_id": 1, "player_api_id": 42, "fixture_date": "2026-09-06T15:00:00Z", "minutes": 90, "goals": 1, "assists": 0],
            ["id": 2, "fixture_id": 2, "player_api_id": 42, "fixture_date": "2026-09-20T15:00:00Z", "minutes": 72, "goals": 0, "assists": 1],
        ])
        let choice = PlayerCardText.seasonView(
            picked: nil, stats: nil, seasons: [], fallbackSeason: 2026, matchRows: rows, matchRowsSeason: 2026
        )
        let provider = try XCTUnwrap(choice.provider)
        XCTAssertTrue(provider.fromMatchRows)
        XCTAssertEqual(provider.appearances, 2)
        XCTAssertEqual(provider.minutes, 162)
        XCTAssertNil(provider.yellows, "cards the rows do not state stay unknown")
        XCTAssertEqual(provider.asOf, "2026-09-20")
        XCTAssertEqual(
            PlayerCardText.summarizeSeason(provider: provider).sentence,
            "Totals are built from the 2 matches in the public match log."
        )
        XCTAssertNil(
            PlayerCardText.seasonView(picked: 2025, stats: nil, seasons: [], fallbackSeason: 2026, matchRows: rows, matchRowsSeason: 2026).provider,
            "rows for another season are never shown under the picked season"
        )
    }

    // MARK: Which season

    func testTheSeasonShownIsThePickElseTheProviderSeasonElseTheNewestWithLines() throws {
        let older = try Self.decode(PlayerMatchLineSeason.self, [
            "season": 2025, "lines": [], "totals": ["matches": 1],
        ] as [String: Any])
        let newer = try Self.serverSeason("photo")
        let stats = try Self.stats()

        XCTAssertEqual(PlayerCardText.seasonView(picked: 2024, stats: stats, seasons: [newer, older], fallbackSeason: 2026).season, 2024)
        XCTAssertEqual(PlayerCardText.seasonView(picked: nil, stats: stats, seasons: [older], fallbackSeason: 2023).season, 2026)
        XCTAssertEqual(PlayerCardText.seasonView(picked: nil, stats: nil, seasons: [older], fallbackSeason: 2026).season, 2025)
        XCTAssertEqual(PlayerCardText.seasonView(picked: nil, stats: nil, seasons: [], fallbackSeason: 2026).season, 2026)
    }

    func testAPickedSeasonNeverShowsProviderTotalsThatBelongToAnotherSeason() throws {
        let choice = PlayerCardText.seasonView(picked: 2025, stats: try Self.stats(), seasons: [], fallbackSeason: 2026)
        XCTAssertEqual(choice.season, 2025)
        XCTAssertNil(choice.provider)
        XCTAssertFalse(choice.statsMatchSeason)
        XCTAssertEqual(PlayerCardText.summarizeSeason(lines: choice.lines, totals: choice.totals, provider: choice.provider).source, .none)
    }

    func testThisSeasonHeadsOnlyTheSeasonThatContainsToday() {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        let october = calendar.date(from: DateComponents(year: 2026, month: 10, day: 3))!
        let march = calendar.date(from: DateComponents(year: 2027, month: 3, day: 3))!
        XCTAssertEqual(PlayerCardText.calendarSeason(october, calendar: calendar), 2026)
        XCTAssertEqual(PlayerCardText.calendarSeason(march, calendar: calendar), 2026)
        XCTAssertEqual(PlayerCardText.seasonKicker(season: 2026, currentSeason: 2026), "This season")
        XCTAssertEqual(PlayerCardText.seasonKicker(season: 2025, currentSeason: 2026), "Season")
        XCTAssertEqual(PlayerCardText.seasonKicker(season: nil, currentSeason: 2026), "Season")
    }

    // MARK: Failed reads

    func testAFailedReadIsWordedAsALoadingProblemNeverAsAnEmptySeason() {
        func problem(lines: Bool = false, linesStale: Bool = false, totals: Bool = false, totalsStale: Bool = false, showing: Bool = false) -> String? {
            PlayerCardText.readProblem(linesError: lines, linesStale: linesStale, totalsError: totals, totalsStale: totalsStale, showing: showing)
        }
        XCTAssertNil(problem())
        XCTAssertEqual(
            problem(lines: true),
            "The matches could not be loaded. This is a loading problem — it does not mean nothing has been recorded."
        )
        XCTAssertEqual(
            problem(lines: true, totals: true),
            "The season could not be loaded. This is a loading problem — it does not mean nothing has been recorded."
        )
        XCTAssertEqual(problem(lines: true, linesStale: true, showing: true), "The latest figures could not be loaded. Showing what was loaded before.")
        XCTAssertEqual(
            problem(totals: true, showing: true),
            "The season totals could not be loaded. What is shown comes from the matches that did load."
        )
        XCTAssertEqual(problem(lines: true, showing: true), "The matches entered by the club or the player could not be loaded.")
    }

    // MARK: One match

    func testMatchDateVenueAndResultWording() throws {
        XCTAssertEqual(PlayerCardText.matchDateParts("2026-09-20"), MatchDateParts(day: "20 Sep", year: "2026", compact: "20 SEP 2026"))
        XCTAssertEqual(PlayerCardText.matchDateParts("2026-09-05T19:45:00").day, "5 Sep")
        XCTAssertEqual(PlayerCardText.matchDateParts(nil).compact, "DATE NOT RECORDED")
        XCTAssertEqual(PlayerCardText.matchDateParts("2026-13-01").day, "Date not recorded")
        XCTAssertEqual(PlayerCardText.venueLabel("neutral"), "neutral venue")
        XCTAssertNil(PlayerCardText.venueLabel("somewhere"))
        XCTAssertEqual(PlayerCardText.matchResult(try Self.line())?.label, "Won 3–1")
        XCTAssertEqual(PlayerCardText.matchResult(try Self.line(["result_for": 1, "result_against": 1]))?.outcome, "D")
        XCTAssertEqual(PlayerCardText.matchResult(try Self.line(["result_for": 0, "result_against": 2]))?.label, "Lost 0–2")
        XCTAssertNil(PlayerCardText.matchResult(try Self.line(["result_for": nil])))
        XCTAssertEqual(PlayerCardText.minutesShare(45), 0.5)
        XCTAssertEqual(PlayerCardText.minutesShare(120), 1)
        XCTAssertEqual(PlayerCardText.minutesShare(nil), 0)
    }

    func testSourceWordingIsNeutralAndUsesNoGenderedPronoun() throws {
        let matches = PlayerCardText.lineSource(try Self.line())
        XCTAssertEqual(matches, MatchLineSource(mark: "Club-confirmed", confirmed: true, note: "Matches the player's own report"))

        let differs = PlayerCardText.lineSource(try Self.line(["self_report": "differs"]))
        XCTAssertEqual(differs.mark, "Club-confirmed")
        XCTAssertEqual(differs.detail, "Club figures shown · Differs from the player's report")

        XCTAssertNil(PlayerCardText.lineSource(try Self.line(["self_report": nil])).detail)

        let own = PlayerCardText.lineSource(try Self.line(["confirmation": "self_reported", "self_report": nil]))
        XCTAssertEqual(own, MatchLineSource(mark: "Self-reported", confirmed: false))

        let wording = [matches, differs, own].flatMap { [$0.mark, $0.detail ?? ""] }.joined(separator: " ").lowercased()
        for word in [" his ", " her ", " he ", " she ", "wrong", "incorrect", "false", "disputed"] {
            XCTAssertFalse(" \(wording) ".contains(word), "never accuse, never guess a gender: \(word)")
        }
    }

    func testEntriesThatShareADateAndOpponentAreEachListedAndSaySo() throws {
        let club = try Self.line(["key": "2026-09-27|hallowfen rovers|club-1", "self_report": nil, "shared_slot": true])
        let own = try Self.line([
            "key": "2026-09-20|skerraby united|own-1", "confirmation": "self_reported", "self_report": nil, "shared_slot": true,
        ])
        XCTAssertEqual(PlayerCardText.lineSource(club).note, "One of several entries for this date and opponent")
        XCTAssertTrue(PlayerCardText.lineSource(club).confirmed)
        XCTAssertFalse(PlayerCardText.lineSource(own).confirmed)
        let summary = PlayerCardText.summarizeSeason(
            lines: [club, own], totals: try Self.totals(["matches": 2, "self_reported_only": 1])
        )
        XCTAssertEqual(
            summary.sentence,
            "Built from 2 matches. 1 confirmed by the club, 1 only reported by the player. "
                + "Entries that share a date and opponent are listed separately and each is counted."
        )
    }

    func testAnUnrecognisedConfirmationIsNeverShownAsClubConfirmed() throws {
        let line = try Self.line(["confirmation": "club_pending", "self_report": "unheard-of"])
        XCTAssertFalse(line.isClubConfirmed)
        XCTAssertNil(line.selfReport)
        XCTAssertEqual(PlayerCardText.lineSource(line).mark, "Self-reported")
    }

    func testVoiceOverReadsOneMatchInOrder() throws {
        let spoken = PlayerCardText.spokenLine(try Self.line(["self_report": "differs", "minutes": 74, "yellows": 1]), goalkeeper: false)
        XCTAssertEqual(
            spoken,
            "20 Sep 2026. Skerraby United, home. Wendle & District Senior League, Premier Division. Won 3–1. "
                + "74 minutes. 1 yellow. Club-confirmed. Club figures shown · Differs from the player's report"
        )
        XCTAssertTrue(
            PlayerCardText.spokenLine(try Self.line(["result_for": nil, "result_against": nil]), goalkeeper: false)
                .contains("Result not recorded")
        )
    }

    // MARK: Facts, identity, list card

    func testFactsStripListsOnlyFieldsWithAValueAndKeepsTheServerGatedAgentEmail() throws {
        XCTAssertTrue(PlayerCardText.profileFacts(nil).isEmpty)
        let sparse = try Self.decode(ShowcaseProfile.self, ["player_api_id": 1, "positions": "LW, RW", "preferred_foot": "left"])
        XCTAssertEqual(PlayerCardText.profileFacts(sparse).map(\.label), ["Positions", "Foot"])
        XCTAssertFalse(PlayerCardText.profileFacts(sparse).contains { $0.value.contains("–") || $0.value.contains("—") })

        let full = try Self.decode(ShowcaseProfile.self, [
            "player_api_id": 1, "positions": "RB, RWB", "preferred_foot": "right", "height_cm": 178,
            "contract_status": "under_contract", "contract_until": "2027-06-30", "availability": "not_looking",
            "nationality_secondary": "Ghana", "languages": "English, Twi", "agent_name": "  A. Mensah ",
            "agent_contact_email": "agent@example.invalid",
        ] as [String: Any])
        let facts = PlayerCardText.profileFacts(full)
        XCTAssertEqual(
            facts.map(\.label),
            ["Positions", "Foot", "Height", "Contract", "Availability", "Second nationality", "Languages", "Agent", "Agent email"]
        )
        XCTAssertEqual(facts.first { $0.label == "Contract" }?.value, "Under contract · until 30 Jun 2027")
        XCTAssertEqual(facts.first { $0.label == "Height" }?.value, "178 cm")
        XCTAssertEqual(facts.first { $0.label == "Agent" }?.value, "A. Mensah")
        XCTAssertEqual(facts.last?.isEmail, true)

        // Signed out, the server sends no email: nothing is invented for it.
        let signedOut = try Self.decode(ShowcaseProfile.self, ["player_api_id": 1, "agent_name": "A. Mensah", "contract_until": "2027-06-30"])
        XCTAssertEqual(PlayerCardText.profileFacts(signedOut).map(\.label), ["Contract", "Agent"])
        XCTAssertEqual(PlayerCardText.profileFacts(signedOut).first?.value, "Until 30 Jun 2027")
    }

    func testOnlyApprovedPhotosWithAPublicURLAreUsedPrimaryFirst() throws {
        let showcase = try Self.decode(PlayerShowcaseResponse.self, [
            "player_api_id": 1,
            "photos": [
                ["id": 3, "status": "approved", "public_url": "https://cdn.example.invalid/3.jpg", "sort_order": 1],
                ["id": 4, "status": "pending", "public_url": "https://cdn.example.invalid/4.jpg", "pending_preview_url": "https://cdn.example.invalid/p4"],
                ["id": 5, "status": "approved", "public_url": NSNull(), "approved_preview_url": "/api/showcase/media/5/preview"],
                ["id": 6, "status": "rejected", "public_url": "https://cdn.example.invalid/6.jpg"],
                ["id": 2, "status": "approved", "public_url": "https://cdn.example.invalid/2.jpg", "is_primary": true, "sort_order": 9],
                ["id": 1, "status": "approved", "public_url": "https://cdn.example.invalid/1.jpg", "sort_order": 1],
            ],
        ] as [String: Any])
        XCTAssertEqual(showcase.publicPhotos.map(\.id), [2, 1, 3])
    }

    func testClubConfirmationComesOnlyFromAClubConfirmedAffiliation() throws {
        let showcase = try Self.decode(PlayerShowcaseResponse.self, [
            "player_api_id": 1, "contactable": true,
            "affiliations": [
                ["id": 1, "club_name": "Old Town", "status": "club_confirmed", "season": "2025/26"],
                ["id": 2, "club_name": "Quillmere Athletic", "status": "club_confirmed", "season": 2026],
                ["id": 3, "club_name": "Claimed FC", "status": "self_reported"],
                ["id": 4, "club_name": NSNull(), "status": "club_confirmed"],
            ],
        ] as [String: Any])
        XCTAssertEqual(showcase.confirmedClubName, "Quillmere Athletic")
        XCTAssertTrue(showcase.contactable)

        let none = try Self.decode(PlayerShowcaseResponse.self, [
            "player_api_id": 1, "affiliations": [["id": 3, "club_name": "Claimed FC", "status": "pending"]],
        ] as [String: Any])
        XCTAssertNil(none.confirmedClubName)
        XCTAssertFalse(none.contactable)
        XCTAssertTrue(none.publicPhotos.isEmpty)
    }

    func testCardTextIsBuiltOnlyFromFieldsThatExist() {
        XCTAssertEqual(PlayerCardText.cardLine(position: "Right-back", clubName: "Quillmere Athletic"), "Right-back at Quillmere Athletic.")
        XCTAssertEqual(PlayerCardText.cardLine(position: "Winger", clubName: nil), "Winger.")
        XCTAssertEqual(PlayerCardText.cardLine(position: nil, clubName: " "), "")
        XCTAssertEqual(
            PlayerCardText.cardLine(position: "Midfielder", clubName: "Quillmere Athletic", bio: "Signed in May. Loves a tackle."),
            "Midfielder at Quillmere Athletic. Signed in May."
        )
        XCTAssertEqual(PlayerCardText.initials(of: "Kofi Asante-Reid"), "KA")
        XCTAssertEqual(PlayerCardText.initials(of: "  maximilian-alexander oluwaseun featherstonehaugh-abernathy "), "MF")
        XCTAssertEqual(PlayerCardText.initials(of: "Pelé"), "P")
        XCTAssertEqual(PlayerCardText.initials(of: " "), "·")
        XCTAssertEqual(PlayerCardText.roleLabel(positions: "RB, RWB", fallback: "Defender"), "RB · RWB")
        XCTAssertEqual(PlayerCardText.roleLabel(positions: "a/b;c,d", fallback: nil), "a · b · c")
        XCTAssertEqual(PlayerCardText.roleLabel(positions: " ", fallback: "Defender"), "Defender")
        XCTAssertNil(PlayerCardText.roleLabel(positions: nil, fallback: nil))
    }

    func testGoalkeeperDetectionMatchesTheEditForm() {
        for position in ["Goalkeeper", "GK", "g", "Keeper", "goalkeeper / sweeper", "GK, CB"] {
            XCTAssertTrue(PlayerCardText.isGoalkeeper(position: position), position)
        }
        for position in ["Midfielder", "Wing-back", "Gegenpresser", "Striker", "", nil] as [String?] {
            XCTAssertFalse(PlayerCardText.isGoalkeeper(position: position), position ?? "nil")
        }
    }

    func testListCountersArePrintedOnlyForFiguresThePageWouldAlsoShow() throws {
        func provenance(_ object: [String: Any]) throws -> SeasonProvenance { try Self.decode(SeasonProvenance.self, object) }
        XCTAssertTrue(PlayerCardText.isProviderSourced(try provenance(["primary_source": "journey"])))
        XCTAssertTrue(PlayerCardText.isProviderSourced(try provenance(["source": "api-football"])))
        XCTAssertTrue(PlayerCardText.isProviderSourced(try provenance(["source_category": "fixtures", "source": "club"])))
        XCTAssertFalse(PlayerCardText.isProviderSourced(try provenance(["source": "club"])))
        XCTAssertFalse(PlayerCardText.isProviderSourced(try provenance(["source": "self"])))
        XCTAssertFalse(PlayerCardText.isProviderSourced(try provenance(["primary_source": "matches"])))
        XCTAssertFalse(PlayerCardText.isProviderSourced(nil))
        XCTAssertTrue(PlayerCardText.isMatchLinesSourced(try provenance(["primary_source": "matches"])))
        XCTAssertFalse(PlayerCardText.isMatchLinesSourced(try provenance(["source": "matches"])))

        XCTAssertEqual(
            PlayerCardText.cardCounters(appearances: 30, minutes: 2412),
            [CardCounter(value: "30", unit: "apps"), CardCounter(value: "2,412", unit: "min")]
        )
        XCTAssertEqual(PlayerCardText.cardCounters(appearances: 1, minutes: 0), [CardCounter(value: "1", unit: "app")])
        XCTAssertTrue(PlayerCardText.cardCounters(appearances: 0, minutes: nil).isEmpty)
    }
}
