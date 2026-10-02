"""Duel regression: every overview queue counts the work its linked list exposes."""

import pytest
from src.models.funding import ClubProgramClaim, ClubProgramProfileRevision, ClubProgramUpdate
from src.models.league import (
    CommunityTake,
    ManualPlayerSubmission,
    PlayerFlag,
    PlayerLink,
    QuickTakeSubmission,
    Team,
    TeamTrackingRequest,
    UserAccount,
    db,
)
from src.models.showcase import (
    ClubOfficialClaim,
    LocalClub,
    LocalPlayer,
    PlayerClubAffiliation,
    PlayerProfileClaim,
    PlayerShowcaseMedia,
    PlayerShowcaseProfile,
)
from src.models.trust import ContentReport, ScoutVerification
from test_admin_control import action, headers, program, report, user
from test_admin_control import control_app as _control_app
from test_admin_control_postgres import pg_control as _pg_control

control_app = _control_app
pg_control = _pg_control

# The default pending/open filters selected by the linked admin tabs.
QUEUES = {
    "manual": ("/admin/manual-players?status=pending", None),
    "takes": ("/admin/community-takes?status=pending", "takes"),
    "submissions": ("/admin/community-takes/submissions?status=pending", "submissions"),
    "flags": ("/admin/flags?status=pending", "flags"),
    "tracking": ("/admin/tracking-requests?status=pending", None),
    "links": ("/admin/player-links/pending", None),
    "club_claims": ("/admin/funding/claims", "claims"),
    "club_profiles": ("/admin/funding/profile-revisions", "revisions"),
    "club_updates": ("/admin/funding/program-updates", "updates"),
    "scout_verifications": ("/admin/scout-verifications", "verifications"),
    "profile_claims": ("/admin/showcase/claims?status=pending", "claims"),
    "showcase_profiles": ("/admin/showcase/profiles?status=pending", "profiles"),
    "local_players": ("/admin/local-players?status=pending", "players"),
    "local_clubs": ("/admin/local-clubs?status=pending", "clubs"),
    "affiliations": ("/admin/showcase/affiliations?status=pending", "affiliations"),
    "official_claims": ("/admin/club-claims?status=pending", "claims"),
    "showcase_media": ("/admin/showcase/media?status=pending", "media"),
    "reports": ("/admin/reports", "reports"),
    "safeguarding": ("/admin/safety/cases", "rows"),
}


@pytest.mark.parametrize("database", ["control_app", "pg_control"])
def test_every_overview_count_matches_linked_queue(request, database):
    app = request.getfixturevalue(database)
    from src.routes.api import api_bp
    from src.routes.community_takes import community_takes_bp
    from src.routes.funding import funding_bp
    from src.routes.showcase import showcase_bp
    from src.routes.trust import trust_bp

    for blueprint in (api_bp, community_takes_bp, funding_bp, showcase_bp, trust_bp):
        app.register_blueprint(blueprint, url_prefix="/api")
    person, club = user(), program()
    other = UserAccount(
        email="reviewed@example.test", display_name="Reviewed Person", display_name_lower="reviewed person"
    )
    db.session.add(other)
    db.session.flush()
    # Remove the baseline community fixture from pending work (PG has no baseline).
    LocalPlayer.query.update({LocalPlayer.status: "approved"})
    db.session.add(Team(id=1, team_id=1, name="Fixture FC", country="JP", season=2026))
    local_club = LocalClub(name="Community FC")
    db.session.add(local_club)
    db.session.flush()
    for index, status in enumerate(("pending", "rejected")):
        applicant = person if index == 0 else other
        pid = 20 + index
        db.session.add(LocalPlayer(id=pid, display_name=f"User player {pid}", status=status, provenance="user"))
        db.session.flush()
        db.session.add_all(
            [
                ManualPlayerSubmission(user_id=person.id, player_name="Prospect", team_name="FC", status=status),
                CommunityTake(source_type="editor", source_author="Editor", content="Take", status=status),
                QuickTakeSubmission(player_name="Prospect", content="Submission", status=status),
                PlayerFlag(reason="Check data", status=status),
                TeamTrackingRequest(team_id=1, team_api_id=1, team_name="Fixture FC", status=status),
                PlayerLink(player_id=321, url="https://example.test/highlight", status=status),
                ClubProgramClaim(program_id=club.id, user_account_id=applicant.id, status=status),
                ClubProgramProfileRevision(program_id=club.id, submitted_by_user_id=person.id, status=status),
                ClubProgramUpdate(
                    program_id=club.id, author_user_id=person.id, title="Update", body="Body", status=status
                ),
                ScoutVerification(
                    user_account_id=applicant.id,
                    full_name="Scout",
                    organization="FC",
                    role_title="Scout",
                    statement="Evidence",
                    status=status,
                ),
                PlayerProfileClaim(
                    local_player_id=pid, user_account_id=person.id, relationship_type="player", status=status
                ),
                PlayerShowcaseProfile(local_player_id=pid, status=status),
                PlayerClubAffiliation(local_player_id=pid, local_club_id=local_club.id, status=status),
                ClubOfficialClaim(user_account_id=applicant.id, local_club_id=local_club.id, status=status),
                PlayerShowcaseMedia(local_player_id=pid, kind="photo", blob_path=f"photo-{pid}", status=status),
            ]
        )
    db.session.add_all(
        [
            LocalClub(name="Reviewed FC", status="approved"),
            LocalPlayer(
                display_name="Club-private roster player",
                status="pending",
                provenance="club",
                origin_program_id=club.id,
            ),
            PlayerShowcaseMedia(local_player_id=20, kind="video", blob_path="non-photo", status="pending"),
            PlayerShowcaseMedia(local_player_id=20, kind="photo", blob_path="not-uploaded", status="pending_upload"),
        ]
    )
    db.session.commit()
    open_case = report()
    closed_case = report("player_profile", "987")
    closed_case.status = "closed"
    db.session.get(ContentReport, closed_case.report_id).status = "resolved"
    db.session.commit()
    client, auth = app.test_client(), headers()
    overview = client.get("/api/admin/control/overview", headers=auth)
    assert overview.status_code == 200, overview.text
    counts = {row["key"]: row["count"] for row in overview.json["queues"]}
    assert counts.keys() == QUEUES.keys()
    mismatches = []
    for key, (path, collection) in QUEUES.items():
        response = client.get("/api" + path, headers=auth)
        assert response.status_code == 200, (key, response.text)
        rows = response.json if collection is None else response.json[collection]
        if counts[key] != len(rows) or len(rows) != 1:
            mismatches.append((key, counts[key], len(rows)))
    assert not mismatches, mismatches
    # A report and its case occupy two queues; the headline is queue items.
    assert open_case.report_id is not None
    assert overview.json["total"] == sum(counts.values()) == 19
    assert action(client, open_case, "close").status_code == 200
    for key in ("reports", "safeguarding"):
        path, collection = QUEUES[key]
        assert client.get("/api" + path, headers=auth).json[collection] == []
    after = client.get("/api/admin/control/overview", headers=auth).json
    assert after["total"] == 17
