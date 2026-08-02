import XCTest
@testable import AcademyWatch

final class PlayerDetailDecodingTests: XCTestCase {
    func testDecodesCapturedOutfielderProfileAndCurrentClubSemantics() throws {
        let profile = try decode(PlayerProfile.self, fixture: "player_profile_outfielder")

        XCTAssertEqual(profile.playerId, 403_064)
        XCTAssertEqual(profile.name, "H. Amass")
        XCTAssertEqual(profile.position, "Defender")
        XCTAssertEqual(profile.status, "on_loan")
        XCTAssertEqual(profile.age, 18)
        XCTAssertEqual(profile.nationality, "England")
        XCTAssertEqual(profile.currentClubName, "Norwich")
        XCTAssertEqual(profile.clubOriginLine, "from Manchester United")
        XCTAssertFalse(profile.isGoalkeeper)
        XCTAssertNotNil(profile.photoURL)
    }

    func testDecodesCapturedGoalkeeperProfile() throws {
        let profile = try decode(PlayerProfile.self, fixture: "player_profile_gk")

        XCTAssertEqual(profile.playerId, 145_060)
        XCTAssertEqual(profile.name, "S. Ngapandouetnbu")
        XCTAssertEqual(profile.currentClubName, "Montpellier")
        XCTAssertEqual(profile.clubOriginLine, "Marseille academy")
        XCTAssertTrue(profile.isGoalkeeper)
    }

    func testDecodesShadowProfileMarker() throws {
        let profile = try decodeJSON(
            PlayerProfile.self,
            json: """
            {
              "player_id": 2001,
              "name": "Shadow Prospect",
              "shadow": true
            }
            """
        )

        XCTAssertTrue(profile.isShadow)
    }

    func testDecodesCapturedSeasonStatsAndKeepsSourcesDistinct() throws {
        let stats = try decode(PlayerSeasonStats.self, fixture: "player_season_stats_outfielder")

        XCTAssertEqual(stats.playerId, 403_064)
        XCTAssertEqual(stats.season, "2025/2026")
        XCTAssertEqual(stats.appearances, 23)
        XCTAssertEqual(stats.minutes, 1_940)
        XCTAssertEqual(stats.avgRating, 6.83)
        XCTAssertEqual(stats.source, "local-db")
        XCTAssertEqual(stats.provenance?.source, "fixtures")
        XCTAssertEqual(stats.provenance?.fixturesMinutes, 1_940)
        XCTAssertEqual(stats.provenance?.journeyMinutes, 1_881)
        XCTAssertEqual(stats.provenance?.reconcileFlag, "journey-under-sync")
        XCTAssertEqual(stats.countingSourceLabel, "match-level data")

        // Club rows sum to the other whole source; they must not inherit the
        // headline's match-level label.
        XCTAssertEqual(stats.clubSourceLabel, "season totals")
        XCTAssertEqual(stats.clubs.count, 2)
        XCTAssertEqual(stats.clubs.first?.teamName, "Norwich")
        XCTAssertEqual(stats.clubs.first?.minutes, 15)
        XCTAssertTrue(stats.clubs[0].matchesCurrentClub(named: "Norwich"))
        XCTAssertFalse(stats.clubs[1].matchesCurrentClub(named: "Norwich"))
        XCTAssertEqual(stats.clubs.map(\.isCurrent), [true, true])
    }

    func testDecodesCapturedGoalkeeperSeasonStats() throws {
        let stats = try decode(PlayerSeasonStats.self, fixture: "player_season_stats_gk")

        XCTAssertEqual(stats.playerId, 145_060)
        XCTAssertEqual(stats.provenance?.source, "journey")
        XCTAssertEqual(stats.provenance?.reconcileFlag, "cup-gap")
        XCTAssertEqual(stats.countingSourceLabel, "season totals")
        XCTAssertEqual(stats.localAppearances, 27)
        XCTAssertTrue(stats.hasDetailedGoalkeeperCoverage)
        XCTAssertEqual(stats.saves, 83)
        XCTAssertEqual(stats.goalsConceded, 20)
        XCTAssertEqual(stats.cleanSheets, 10)

        let club = try XCTUnwrap(stats.clubs.first)
        XCTAssertEqual(club.teamName, "Montpellier")
        XCTAssertEqual(club.saves, 101)
        XCTAssertEqual(club.goalsConceded, 26)
    }

    func testDecodesCapturedRecentFixturesAndSelectsNewestFive() throws {
        let fixtures = try decode(
            [PlayerRecentFixture].self,
            fixture: "player_recent_fixtures_outfielder"
        )

        XCTAssertEqual(fixtures.count, 23)
        XCTAssertEqual(fixtures.first?.fixtureDate, "2025-09-13T14:00:00")
        XCTAssertEqual(fixtures.last?.fixtureDate, "2026-01-26T20:00:00")

        let newestFive = Array(fixtures.suffix(5).reversed())
        XCTAssertEqual(newestFive.count, 5)
        XCTAssertEqual(newestFive.first?.opponent, "Coventry")
        XCTAssertEqual(newestFive.first?.minutes, 15)
        XCTAssertEqual(newestFive.first?.goals, 0)
        XCTAssertEqual(newestFive.first?.assists, 0)
        XCTAssertEqual(newestFive.first?.rating, 6.6)
    }

    func testDecodesCapturedJourneyAndBuildsNewestFirstSeasonTimeline() throws {
        let journey = try decode(PlayerJourneyResponse.self, fixture: "player_journey_outfielder")

        XCTAssertEqual(journey.playerId, 403_064)
        XCTAssertEqual(journey.source, "player_journey")
        XCTAssertEqual(journey.totalStints, 9)
        XCTAssertEqual(journey.stints.count, 9)

        let timeline = journey.timelineEntries
        XCTAssertEqual(timeline.count, 14)
        XCTAssertEqual(timeline.first?.season, 2025)
        XCTAssertEqual(timeline.first?.seasonLabel, "2025/26")
        XCTAssertEqual(timeline.first?.clubName, "Norwich")
        XCTAssertNil(timeline.first?.minutes)

        let unitedU18 = try XCTUnwrap(
            timeline.first { $0.season == 2024 && $0.clubName == "Manchester United U18" }
        )
        XCTAssertEqual(unitedU18.competitionCount, 2)
        XCTAssertEqual(unitedU18.appearances, 6)
        XCTAssertEqual(unitedU18.level, "U18")
        XCTAssertNil(unitedU18.entryType)

        let englandU17 = try XCTUnwrap(
            timeline.first { $0.season == 2024 && $0.clubName == "England U17" }
        )
        XCTAssertNil(englandU17.entryType)
    }

    func testDecodesCapturedAvailabilityAndEmptyAvailability() throws {
        let availability = try decode(
            PlayerAvailability.self,
            fixture: "player_availability_outfielder"
        )

        XCTAssertEqual(availability.playerId, 403_064)
        XCTAssertEqual(availability.summary.totalAbsences, 23)
        XCTAssertEqual(availability.summary.byReason["Hamstring Injury"], 17)
        XCTAssertEqual(availability.summary.lastAbsence?.reason, "Hamstring Injury")
        XCTAssertEqual(availability.absences.count, 23)
        XCTAssertFalse(availability.isDegraded)

        let empty = try decode(PlayerAvailability.self, fixture: "player_availability_gk")
        XCTAssertEqual(empty.playerId, 145_060)
        XCTAssertEqual(empty.summary.totalAbsences, 0)
        XCTAssertTrue(empty.absences.isEmpty)
        XCTAssertNil(empty.summary.lastAbsence)
        XCTAssertFalse(empty.isDegraded)
    }

    func testDecodesDegradedAvailabilityAsUnknown() throws {
        let availability = try decodeJSON(
            PlayerAvailability.self,
            json: """
            {
              "player_id": 403064,
              "season": 2025,
              "absences": [],
              "summary": {
                "total_absences": null,
                "by_reason": {},
                "last_absence": null
              },
              "degraded": true,
              "reason": "upstream_unavailable"
            }
            """
        )

        XCTAssertTrue(availability.isDegraded)
        XCTAssertEqual(availability.reason, "upstream_unavailable")
        XCTAssertNil(availability.summary.totalAbsences)
        XCTAssertTrue(availability.absences.isEmpty)
    }

    func testDecodesLegacyJourneyWithOmittedOptionalCollections() throws {
        let journey = try decodeJSON(
            PlayerJourneyResponse.self,
            json: """
            {
              "player_id": 999,
              "source": "tracked_player",
              "total_stints": 1,
              "stints": [{
                "id": "999-1",
                "team_api_id": 33,
                "team_name": "Academy FC",
                "team_logo": null,
                "stint_type": "academy",
                "level": "Academy",
                "is_current": true,
                "sequence": 1
              }]
            }
            """
        )

        XCTAssertEqual(journey.stints.count, 1)
        XCTAssertEqual(journey.stints[0].levels, ["Academy"])
        XCTAssertNil(journey.stints[0].years)
        XCTAssertNil(journey.stints[0].stats)
        XCTAssertTrue(journey.stints[0].competitions.isEmpty)
        XCTAssertTrue(journey.timelineEntries.isEmpty)
    }

    func testRawJourneyEntryPreservesUnknownMinutes() throws {
        let journey = try decodeJSON(
            PlayerJourneyResponse.self,
            json: """
            {
              "player_id": 999,
              "source": "player_journey",
              "total_stints": 1,
              "entries": [{
                "id": 1,
                "season": 2025,
                "club": {"id": 33, "name": null, "logo": null},
                "level": "Senior",
                "entry_type": "first_team",
                "stats": {"appearances": 3, "goals": 1, "assists": 0}
              }]
            }
            """
        )

        let entry = try XCTUnwrap(journey.timelineEntries.first)
        XCTAssertEqual(entry.clubName, "Unknown club")
        XCTAssertEqual(entry.appearances, 3)
        XCTAssertNil(entry.minutes)
    }

    func testLimitedCoverageDoesNotPresentUnknownGoalkeeperEventsAsDetailedData() throws {
        let stats = try decodeJSON(
            PlayerSeasonStats.self,
            json: """
            {
              "player_id": 999,
              "season": "2025/2026",
              "appearances": 4,
              "minutes": 360,
              "goals": 0,
              "assists": 0,
              "avg_rating": null,
              "saves": 0,
              "goals_conceded": 0,
              "clean_sheets": 0,
              "source": "shadow",
              "stats_coverage": "limited",
              "clubs": [],
              "provenance": {
                "source": "none",
                "fixtures_minutes": 0,
                "journey_minutes": 0,
                "delta_pct": 0,
                "reconcile_flag": null
              }
            }
            """
        )

        XCTAssertEqual(stats.countingSourceLabel, "limited coverage")
        XCTAssertEqual(stats.matchDetailSourceLabel, "limited coverage")
        XCTAssertFalse(stats.hasDetailedGoalkeeperCoverage)
    }

    func testAPITotalsWithoutLocalRowsDoNotPresentDefaultGoalkeeperZeroesAsFacts() throws {
        let stats = try decodeJSON(
            PlayerSeasonStats.self,
            json: """
            {
              "player_id": 999,
              "season": "2025/2026",
              "appearances": 12,
              "minutes": 1080,
              "goals": 0,
              "assists": 0,
              "avg_rating": null,
              "saves": 0,
              "goals_conceded": 0,
              "clean_sheets": 0,
              "source": "api-football",
              "clubs": []
            }
            """
        )

        XCTAssertEqual(stats.countingSourceLabel, "season totals")
        XCTAssertNil(stats.localAppearances)
        XCTAssertFalse(stats.hasDetailedGoalkeeperCoverage)
        XCTAssertEqual(stats.matchDetailSourceLabel, "no match-level coverage")
    }

    func testJourneyCompetitionPreservesAbsentCountingTotals() throws {
        let journey = try decodeJSON(
            PlayerJourneyResponse.self,
            json: """
            {
              "player_id": 999,
              "source": "player_journey",
              "total_stints": 1,
              "stints": [{
                "id": "j-33-1",
                "team_api_id": 33,
                "team_name": "Academy FC",
                "levels": ["Senior"],
                "is_current": true,
                "sequence": 1,
                "competitions": [{
                  "season": 2025,
                  "league": "League",
                  "apps": null,
                  "goals": null,
                  "assists": null
                }]
              }]
            }
            """
        )

        let entry = try XCTUnwrap(journey.timelineEntries.first)
        XCTAssertNil(entry.appearances)
        XCTAssertNil(entry.goals)
        XCTAssertNil(entry.assists)
        XCTAssertNil(entry.minutes)
    }

    func testProvenanceOnlySeasonRemainsVisibleWithoutInventingHeadlineTotals() throws {
        let stats = try decodeJSON(
            PlayerSeasonStats.self,
            json: """
            {
              "player_id": 999,
              "season": "2025/2026",
              "appearances": 0,
              "minutes": 0,
              "goals": 0,
              "assists": 0,
              "avg_rating": null,
              "saves": 0,
              "goals_conceded": 0,
              "clean_sheets": 0,
              "source": "none",
              "clubs": [],
              "provenance": {
                "source": "journey",
                "fixtures_minutes": 0,
                "journey_minutes": 900,
                "delta_pct": 100,
                "reconcile_flag": "fixtures-invisible"
              }
            }
            """
        )

        XCTAssertFalse(stats.hasHeadlineData)
        XCTAssertTrue(stats.hasAnyData)
        XCTAssertEqual(stats.provenance?.sourceLabel, "season totals")
        XCTAssertEqual(stats.provenance?.detailText, "900 season mins · no match log coverage")
    }

    private func decode<Value: Decodable>(
        _ type: Value.Type,
        fixture: String
    ) throws -> Value {
        let fixtureURL = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: fixture, withExtension: "json")
        )
        let data = try Data(contentsOf: fixtureURL)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: data)
    }

    private func decodeJSON<Value: Decodable>(
        _ type: Value.Type,
        json: String
    ) throws -> Value {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: Data(json.utf8))
    }
}
