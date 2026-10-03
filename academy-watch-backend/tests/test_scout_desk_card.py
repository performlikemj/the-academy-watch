"""Scout desk card fields: the 'open to an introduction' filter, availability and introduction state."""

import os
from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from flask import Flask
from sqlalchemy import event, text
from src.auth import _ensure_user_account, issue_user_token
from src.models.contact import ContactAuditEvent, ContactRequest
from src.models.league import League, Team, UserAccount, db
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.showcase import PlayerProfileClaim, PlayerShowcaseProfile
from src.models.tracked_player import TrackedPlayer
from src.models.user_block import UserBlock
from src.services.contact import utcnow

SCOUT = "desk-scout@example.com"
PLAYER_IDS = list(range(2001, 2011))


def _database_uri():
    """In-memory SQLite, or — opt-in — a local scratch PostgreSQL database (created and dropped by the caller)."""
    uri = os.getenv("SD_POSTGRES_URL")
    if not uri:
        return "sqlite:///:memory:"
    parsed = sa.engine.make_url(uri)
    assert parsed.database == "aw_sd_scratch" and parsed.host in {"localhost", "127.0.0.1"}
    return uri


@pytest.fixture
def desk_app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("CONTACT_RAIL_ENABLED", "true")
    monkeypatch.setenv("CONTACT_REQUEST_EXPIRY_DAYS", "14")
    monkeypatch.setenv("CONTACT_DECLINE_COOLDOWN_DAYS", "30")
    monkeypatch.delenv("SCOUT_INCLUDE_LOCAL_PLAYERS", raising=False)
    monkeypatch.delenv("SEASON_ROLLUP_READS", raising=False)

    from src.routes.contact import contact_bp
    from src.routes.scout import scout_bp

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="desk-card-secret",
        SQLALCHEMY_DATABASE_URI=_database_uri(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    app.register_blueprint(scout_bp, url_prefix="/api")
    app.register_blueprint(contact_bp, url_prefix="/api")

    with app.app_context():
        # The narrow club registry projection, as in tests/test_contact.py.
        with db.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS club_programs ("
                    "id INTEGER PRIMARY KEY, name VARCHAR(180) NOT NULL, contact_email VARCHAR(254), "
                    "slug VARCHAR(200), team_api_id INTEGER, platform_status VARCHAR(20) NOT NULL, "
                    "emergency_hidden BOOLEAN NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS club_program_managers ("
                    "id INTEGER PRIMARY KEY, program_id INTEGER NOT NULL, "
                    "user_account_id INTEGER NOT NULL, status VARCHAR(20) NOT NULL)"
                )
            )
        db.create_all()
        _seed_players()
        yield app
        db.session.remove()
        if db.engine.dialect.name == "postgresql":
            # The scratch database is ours alone: empty it wholesale.
            with db.engine.begin() as connection:
                connection.execute(text("DROP SCHEMA public CASCADE"))
                connection.execute(text("CREATE SCHEMA public"))
        else:
            db.drop_all()
            with db.engine.begin() as connection:
                connection.execute(text("DROP TABLE IF EXISTS club_program_managers"))
                connection.execute(text("DROP TABLE IF EXISTS club_programs"))


@pytest.fixture
def client(desk_app):
    return desk_app.test_client()


def _seed_players():
    league = League(league_id=39, name="Premier League", country="England", season=2025, is_european_top_league=True)
    db.session.add(league)
    db.session.flush()
    parent = Team(team_id=33, name="Parent FC", country="England", season=2025, league_id=league.id, is_active=True)
    db.session.add(parent)
    db.session.flush()
    for player_id in PLAYER_IDS:
        db.session.add(
            TrackedPlayer(
                player_api_id=player_id,
                player_name=f"Player {player_id}",
                position="Midfielder",
                nationality="England",
                age=21,
                birth_date=f"{date.today().year - 21}-01-01",
                team_id=parent.id,
                status="first_team",
                data_depth="full_stats",
                is_active=True,
            )
        )
    db.session.commit()


def _user(email):
    user = UserAccount.query.filter_by(email=email).first()
    if user is None:
        user = _ensure_user_account(email)
        db.session.commit()
    return user


def _headers(email=SCOUT):
    _user(email)
    return {"Authorization": f"Bearer {issue_user_token(email)['token']}"}


def _claim(player_api_id, *, email=None, status="approved", relationship_type="player", reviewed_days_ago=0):
    owner = _user(email or f"owner-{player_api_id}@example.com")
    claim = PlayerProfileClaim(
        user_account_id=owner.id,
        player_api_id=player_api_id,
        relationship_type=relationship_type,
        contract_status="free_agent" if relationship_type == "player" else "unknown",
        status=status,
        reviewed_at=utcnow() - timedelta(days=reviewed_days_ago) if status != "pending" else None,
    )
    db.session.add(claim)
    db.session.commit()
    return claim


def _block(blocker_id, blocked_id):
    db.session.add(UserBlock(blocker_user_id=blocker_id, blocked_user_id=blocked_id))
    db.session.commit()


def _request(scout_email, player_api_id, *, status="pending", created_days_ago=1, **fields):
    scout = _user(scout_email)
    created = utcnow() - timedelta(days=created_days_ago)
    row = ContactRequest(
        scout_user_id=scout.id,
        player_api_id=player_api_id,
        message="Hello",
        status=status,
        created_at=created,
        expires_at=fields.pop("expires_at", created + timedelta(days=14)),
        **fields,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _watch(email, *player_ids):
    user = _user(email)
    for player_id in player_ids:
        db.session.add(ScoutWatchlistEntry(user_account_id=user.id, player_api_id=player_id))
    db.session.commit()


def _introductions(client, email=SCOUT):
    response = client.get("/api/scout/watchlist", headers=_headers(email))
    assert response.status_code == 200, response.get_json()
    return {entry["player_api_id"]: entry.get("introduction") for entry in response.get_json()["entries"]}


class TestOpenToAnIntroductionFilter:
    def test_filter_is_the_contactable_flag_applied_before_count_and_paging(self, client):
        _claim(2001)
        _claim(2002)
        _claim(2003, status="pending")
        _claim(2004, relationship_type="guardian")

        everyone = client.get("/api/scout/players?sort=name&per_page=100").get_json()
        flagged = sorted(row["player_id"] for row in everyone["players"] if row["contactable"])
        assert everyone["total"] == len(PLAYER_IDS)
        assert flagged == [2001, 2002]

        filtered = client.get("/api/scout/players?sort=name&contactable=1&per_page=1").get_json()
        assert filtered["total"] == 2
        assert filtered["total_pages"] == 2
        assert [row["player_id"] for row in filtered["players"]] == [2001]
        second = client.get("/api/scout/players?sort=name&contactable=1&per_page=1&page=2").get_json()
        assert [row["player_id"] for row in second["players"]] == [2002]

        assert client.get("/api/scout/players?contactable=0").get_json()["total"] == len(PLAYER_IDS)

    def test_invalid_value_is_rejected(self, client):
        response = client.get("/api/scout/players?contactable=maybe")
        assert response.status_code == 400

    def test_csv_export_honours_the_filter(self, client):
        _claim(2001)
        response = client.get("/api/scout/export.csv?contactable=1&sort=name", headers=_headers())
        assert response.status_code == 200
        body = response.get_data(as_text=True).strip().splitlines()
        assert len(body) == 2
        assert body[1].startswith("2001,")


class TestDeskRowFields:
    def test_availability_comes_only_from_an_approved_profile(self, client):
        db.session.add_all(
            [
                PlayerShowcaseProfile(player_api_id=2001, availability="open_to_moves", status="approved"),
                PlayerShowcaseProfile(player_api_id=2002, availability="not_looking", status="pending"),
                PlayerShowcaseProfile(player_api_id=2003, availability=None, status="approved"),
            ]
        )
        db.session.commit()
        rows = {
            row["player_id"]: row
            for row in client.get("/api/scout/players?sort=name&per_page=100").get_json()["players"]
        }
        assert rows[2001]["availability"] == "open_to_moves"
        assert rows[2002]["availability"] is None
        assert rows[2003]["availability"] is None
        assert rows[2004]["availability"] is None

    def test_introduction_is_the_callers_own_and_absent_for_anonymous_readers(self, client):
        _claim(2001)
        _request(SCOUT, 2001)

        anonymous = client.get("/api/scout/players?sort=name&per_page=100").get_json()["players"]
        assert all("introduction" not in row for row in anonymous)

        own = {
            row["player_id"]: row
            for row in client.get("/api/scout/players?sort=name&per_page=100", headers=_headers()).get_json()["players"]
        }
        assert own[2001]["introduction"]["state"] == "pending"
        assert own[2002]["introduction"] == {"state": "none", "can_ask": False}

        other = {
            row["player_id"]: row
            for row in client.get(
                "/api/scout/players?sort=name&per_page=100", headers=_headers("other-scout@example.com")
            ).get_json()["players"]
        }
        assert other[2001]["introduction"] == {"state": "none", "can_ask": True}

    def test_a_bad_token_reads_as_anonymous(self, client):
        response = client.get("/api/scout/players", headers={"Authorization": "Bearer not-a-token"})
        assert response.status_code == 200
        assert all("introduction" not in row for row in response.get_json()["players"])


class TestWatchlistIntroductionState:
    def test_every_state_with_the_next_action_the_rules_allow(self, client):
        for player_id in PLAYER_IDS[:8]:
            _claim(player_id)
        _watch(SCOUT, *PLAYER_IDS)
        # 2001 not asked · 2002 pending · 2003 accepted · 2004 declined (cooling off)
        # 2005 declined long ago · 2006 past its expiry · 2007 withdrawn · 2008 withdrawn then asked again
        # 2009 / 2010 have no self-claim: nobody can be asked.
        _request(SCOUT, 2002)
        _request(SCOUT, 2003, status="accepted", responded_at=utcnow())
        recent = _request(SCOUT, 2004, status="declined", created_days_ago=5, responded_at=utcnow() - timedelta(days=2))
        _request(SCOUT, 2005, status="declined", created_days_ago=90, responded_at=utcnow() - timedelta(days=80))
        due = _request(SCOUT, 2006, created_days_ago=20)
        _request(SCOUT, 2007, status="withdrawn")
        _request(SCOUT, 2008, status="withdrawn", created_days_ago=9)
        _request(SCOUT, 2008, created_days_ago=1)
        _request("other-scout@example.com", 2001, status="accepted")

        intro = _introductions(client)

        assert intro[2001] == {"state": "none", "can_ask": True}
        assert (intro[2002]["state"], intro[2002]["waiting_on"], intro[2002]["can_ask"]) == ("pending", "player", False)
        assert (intro[2003]["state"], intro[2003]["conversation_open"], intro[2003]["can_ask"]) == (
            "accepted",
            True,
            False,
        )
        assert (intro[2004]["state"], intro[2004]["declined_by"], intro[2004]["can_ask"]) == (
            "declined",
            "player",
            False,
        )
        assert intro[2004]["ask_again_from"] == (recent.responded_at + timedelta(days=30)).isoformat()
        assert (intro[2005]["state"], intro[2005]["can_ask"], intro[2005]["ask_again_from"]) == ("declined", True, None)
        assert (intro[2006]["state"], intro[2006]["can_ask"]) == ("expired", True)
        assert (intro[2007]["state"], intro[2007]["can_ask"]) == ("withdrawn", True)
        assert (intro[2008]["state"], intro[2008]["can_ask"]) == ("pending", False)
        assert intro[2009] == {"state": "none", "can_ask": False}

        # Reporting a due request as expired writes nothing: the contact routes still own expiry.
        db.session.expire_all()
        assert db.session.get(ContactRequest, due.id).status == "pending"
        assert ContactAuditEvent.query.count() == 0

    def test_club_route_names_the_club_and_who_is_awaited(self, client):
        db.session.execute(
            text(
                "INSERT INTO club_programs (id, name, platform_status, emergency_hidden) "
                "VALUES (7, 'Quillmere Athletic', 'approved', false)"
            )
        )
        db.session.commit()
        _claim(2001)
        _claim(2002)
        _watch(SCOUT, 2001, 2002)
        _request(SCOUT, 2001, routing_mode="club_included", club_program_id=7, club_consent_status="pending")
        _request(
            SCOUT,
            2002,
            status="accepted",
            routing_mode="club_included",
            club_program_id=7,
            club_consent_status="pending",
        )

        intro = _introductions(client)

        assert (intro[2001]["via_club"], intro[2001]["waiting_on"]) == ("Quillmere Athletic", "club_and_player")
        assert (intro[2002]["waiting_on"], intro[2002]["conversation_open"]) == ("club", False)

    def test_a_declining_club_is_named_as_the_decliner(self, client):
        _claim(2001)
        _watch(SCOUT, 2001)
        _request(
            SCOUT,
            2001,
            status="declined",
            routing_mode="club_included",
            club_program_id=7,
            club_consent_status="declined",
            responded_at=utcnow(),
        )
        assert _introductions(client)[2001]["declined_by"] == "club"

    @pytest.mark.parametrize("scout_blocks", [True, False])
    def test_a_block_reads_like_any_player_who_cannot_be_asked(self, client, scout_blocks):
        # Never visible by omission: the same neutral answer as a player with no claim,
        # and the blocked claimant's thread is hidden as the sent box hides it.
        claim = _claim(2001)
        _watch(SCOUT, 2001, 2002)
        _request(SCOUT, 2001, status="accepted", claim_id=claim.id)
        scout = _user(SCOUT)
        _block(*((scout.id, claim.user_account_id) if scout_blocks else (claim.user_account_id, scout.id)))

        intro = _introductions(client)

        assert intro[2001] == intro[2002] == {"state": "none", "can_ask": False}

    @pytest.mark.parametrize("other_status,other_relationship", [("rejected", "player"), ("approved", "guardian")])
    def test_a_block_by_someone_who_is_not_the_requests_claimant_hides_nothing(
        self, client, other_status, other_relationship
    ):
        # Reviewers' probe: a rejected (or guardian) claim by a blocked account must not hide
        # the scout's thread with the real claimant, nor forbid asking.
        owner_claim = _claim(2001)
        other = _claim(
            2001, email="someone-else@example.com", status=other_status, relationship_type=other_relationship
        )
        _claim(2002)
        _claim(2002, email="someone-else@example.com", status=other_status, relationship_type=other_relationship)
        _watch(SCOUT, 2001, 2002)
        _request(SCOUT, 2001, claim_id=owner_claim.id)
        _block(other.user_account_id, _user(SCOUT).id)

        intro = _introductions(client)

        assert (intro[2001]["state"], intro[2001]["can_ask"]) == ("pending", False)
        assert intro[2002] == {"state": "none", "can_ask": True}

    def test_the_target_is_the_newest_approved_self_claim_and_only_its_owner_can_block(self, client):
        # Reviewers' probe: old approved claim A blocks the scout, newer approved claim B does not.
        blocked_old = _claim(2001, email="old-claimant@example.com", reviewed_days_ago=30)
        _claim(2001, email="new-claimant@example.com", reviewed_days_ago=1)
        # The other way round: the newest claimant is the one behind the block.
        _claim(2002, email="fine-claimant@example.com", reviewed_days_ago=30)
        blocked_new = _claim(2002, email="blocking-claimant@example.com", reviewed_days_ago=1)
        _watch(SCOUT, 2001, 2002)
        scout = _user(SCOUT)
        _block(blocked_old.user_account_id, scout.id)
        _block(scout.id, blocked_new.user_account_id)

        intro = _introductions(client)

        assert intro[2001] == {"state": "none", "can_ask": True}
        assert intro[2002] == {"state": "none", "can_ask": False}

    def test_nothing_is_said_when_the_contact_rail_is_off(self, client, monkeypatch):
        _claim(2001)
        _watch(SCOUT, 2001)
        _request(SCOUT, 2001)
        monkeypatch.setenv("CONTACT_RAIL_ENABLED", "false")
        assert _introductions(client) == {2001: None}

    def test_a_player_who_is_no_longer_tracked_carries_no_state(self, client):
        _claim(2001)
        _watch(SCOUT, 2001)
        _request(SCOUT, 2001)
        TrackedPlayer.query.filter_by(player_api_id=2001).update({"is_active": False})
        db.session.commit()

        response = client.get("/api/scout/watchlist", headers=_headers()).get_json()

        assert response["entries"][0]["player"] is None
        assert "introduction" not in response["entries"][0]

    def test_saving_a_note_does_not_drop_the_field_from_the_callers_copy(self, client):
        # The PATCH answer carries no introduction key, so the page keeps the one it loaded.
        _claim(2001)
        _watch(SCOUT, 2001)
        response = client.patch("/api/scout/watchlist/2001", json={"note": "Quick feet"}, headers=_headers())
        assert response.status_code == 200
        assert "introduction" not in response.get_json()["entry"]

    def test_query_count_does_not_grow_with_the_list(self, client, desk_app):
        for player_id in PLAYER_IDS:
            _claim(player_id)
            _request(SCOUT, player_id, status="withdrawn", created_days_ago=3)
            _request(SCOUT, player_id)
        headers = _headers()

        def selects():
            statements = []

            def record(_conn, _cursor, statement, *_args):
                statements.append(statement)

            event.listen(db.engine, "before_cursor_execute", record)
            try:
                assert client.get("/api/scout/watchlist", headers=headers).status_code == 200
            finally:
                event.remove(db.engine, "before_cursor_execute", record)
            return len(statements), sum("contact_requests" in statement for statement in statements)

        _watch(SCOUT, 2001)
        selects()  # first call pays one-off lookups (schema inspection) that are then cached
        one = selects()
        _watch(SCOUT, *PLAYER_IDS[1:])
        ten = selects()

        assert one == ten
        assert ten[1] == 1


# ---- The projection and the real route must agree -------------------------
# Each case is set up once, then asked twice: what does the watchlist say
# (``can_ask``), and what does POST /contact/requests actually do?


def _verified(email=SCOUT):
    from src.models.trust import ScoutVerification

    user = _user(email)
    db.session.add(
        ScoutVerification(
            user_account_id=user.id,
            full_name="Desk Scout",
            organization="Fixture Recruitment",
            role_title="Scout",
            statement="I recruit adult players.",
            evidence_urls=["https://example.com/scout"],
            status="approved",
            reviewed_at=utcnow(),
        )
    )
    db.session.commit()
    return user


def _case_no_claim():
    pass


def _case_approved_self_claim():
    _claim(2001)


def _case_claim_still_pending():
    _claim(2001, status="pending")


def _case_guardian_claim_only():
    _claim(2001, relationship_type="guardian")


def _case_pending_request():
    _request(SCOUT, 2001, claim_id=_claim(2001).id)


def _case_accepted_request():
    _request(SCOUT, 2001, status="accepted", responded_at=utcnow(), claim_id=_claim(2001).id)


def _case_declined_inside_the_cool_off():
    _request(SCOUT, 2001, status="declined", created_days_ago=5, responded_at=utcnow() - timedelta(days=2))
    _claim(2001)


def _case_declined_long_ago():
    _request(SCOUT, 2001, status="declined", created_days_ago=90, responded_at=utcnow() - timedelta(days=80))
    _claim(2001)


def _case_withdrawn():
    _request(SCOUT, 2001, status="withdrawn", claim_id=_claim(2001).id)


def _case_past_its_expiry_but_not_yet_written():
    _request(SCOUT, 2001, created_days_ago=20, claim_id=_claim(2001).id)


def _case_scout_blocks_the_claimant():
    _block(_user(SCOUT).id, _claim(2001).user_account_id)


def _case_claimant_blocks_the_scout():
    _block(_claim(2001).user_account_id, _user(SCOUT).id)


def _case_older_claimant_blocks_newer_does_not():
    old = _claim(2001, email="old-claimant@example.com", reviewed_days_ago=30)
    _claim(2001, email="new-claimant@example.com", reviewed_days_ago=1)
    _block(old.user_account_id, _user(SCOUT).id)


def _case_newest_claimant_blocks():
    _claim(2001, email="old-claimant@example.com", reviewed_days_ago=30)
    new = _claim(2001, email="new-claimant@example.com", reviewed_days_ago=1)
    _block(new.user_account_id, _user(SCOUT).id)


def _case_rejected_claimant_blocks():
    _claim(2001)
    rejected = _claim(2001, email="rejected@example.com", status="rejected")
    _block(rejected.user_account_id, _user(SCOUT).id)


def _case_hidden_active_request_to_a_blocked_older_claimant():
    # The thread is hidden (its claimant is blocked) but it still occupies the one active slot.
    old = _claim(2001, email="old-claimant@example.com", reviewed_days_ago=30)
    _claim(2001, email="new-claimant@example.com", reviewed_days_ago=1)
    _request(SCOUT, 2001, claim_id=old.id)
    _block(old.user_account_id, _user(SCOUT).id)


def _case_another_scouts_request():
    _claim(2001)
    _request("other-scout@example.com", 2001, status="accepted")


PARITY_CASES = [
    (_case_no_claim, False),
    (_case_approved_self_claim, True),
    (_case_claim_still_pending, False),
    (_case_guardian_claim_only, False),
    (_case_pending_request, False),
    (_case_accepted_request, False),
    (_case_declined_inside_the_cool_off, False),
    (_case_declined_long_ago, True),
    (_case_withdrawn, True),
    (_case_past_its_expiry_but_not_yet_written, True),
    (_case_scout_blocks_the_claimant, False),
    (_case_claimant_blocks_the_scout, False),
    (_case_older_claimant_blocks_newer_does_not, True),
    (_case_newest_claimant_blocks, False),
    (_case_rejected_claimant_blocks, True),
    (_case_hidden_active_request_to_a_blocked_older_claimant, False),
    (_case_another_scouts_request, True),
]


@pytest.mark.parametrize("arrange,allowed", PARITY_CASES, ids=[case.__name__[6:] for case, _ in PARITY_CASES])
def test_what_the_lists_offer_is_what_the_contact_route_does(client, monkeypatch, arrange, allowed):
    monkeypatch.setattr("src.routes.contact.send_club_courtesy_notice", lambda *_a, **_k: None)
    monkeypatch.setattr("src.routes.contact.send_club_consent_notice", lambda *_a, **_k: None)
    _verified()
    _watch(SCOUT, 2001)
    arrange()
    headers = _headers()

    watchlist = _introductions(client)[2001]
    desk = {
        row["player_id"]: row
        for row in client.get("/api/scout/players?sort=name&per_page=100", headers=headers).get_json()["players"]
    }[2001]["introduction"]
    created = client.post(
        "/api/contact/requests",
        json={"player_api_id": 2001, "message": "Hello", "permission_attestation": True},
        headers=headers,
    )

    assert watchlist == desk
    assert watchlist["can_ask"] is allowed
    assert (created.status_code == 201) is allowed, created.get_json()


# ---- "Conversation open" must be what the message route accepts ------------


def _club_thread(*, status, consent, club_first=False):
    db.session.execute(
        text(
            "INSERT INTO club_programs (id, name, platform_status, emergency_hidden) "
            "VALUES (7, 'Quillmere Athletic', 'approved', false)"
        )
    )
    manager = _user("club-manager@example.com")
    db.session.execute(
        text(
            "INSERT INTO club_program_managers (id, program_id, user_account_id, status) VALUES (1, 7, :uid, 'active')"
        ),
        {"uid": manager.id},
    )
    db.session.commit()
    claim = _claim(2001)
    claim.club_program_id = 7
    claim.contract_status = "contracted"
    db.session.commit()
    row = _request(
        SCOUT,
        2001,
        status=status,
        claim_id=claim.id,
        routing_mode="club_included",
        club_program_id=7,
        club_consent_status=consent,
        responded_at=utcnow() if status == "accepted" else None,
    )
    return row, manager


MESSAGE_CASES = [
    # (request status, club consent, who blocks whom, messages may be sent)
    ("pending", "pending", None, False),
    ("accepted", "pending", None, False),
    ("accepted", "granted", None, True),
    ("accepted", "granted", "manager_blocks_scout", False),
    ("accepted", "granted", "scout_blocks_manager", False),
    ("accepted", "granted", "unrelated_block", True),
]


@pytest.mark.parametrize("status,consent,block,sendable", MESSAGE_CASES)
def test_conversation_open_is_what_the_message_route_accepts(client, status, consent, block, sendable):
    _verified()
    _watch(SCOUT, 2001)
    row, manager = _club_thread(status=status, consent=consent)
    request_id = row.id
    scout = _user(SCOUT)
    if block == "manager_blocks_scout":
        _block(manager.id, scout.id)
    elif block == "scout_blocks_manager":
        _block(scout.id, manager.id)
    elif block == "unrelated_block":
        _block(scout.id, _user("nobody-in-this-thread@example.com").id)
    headers = _headers()

    watchlist = _introductions(client)[2001]
    desk = {
        row["player_id"]: row
        for row in client.get("/api/scout/players?sort=name&per_page=100", headers=headers).get_json()["players"]
    }[2001]["introduction"]
    sent = client.post(f"/api/contact/requests/{request_id}/messages", json={"body": "Hello"}, headers=headers)

    assert watchlist == desk
    assert watchlist["conversation_open"] is sendable
    assert (sent.status_code == 201) is sendable, sent.get_json()
    # A manager block makes the thread read-only — it never hides it and never re-opens asking.
    assert watchlist["read_only"] is (block in {"manager_blocks_scout", "scout_blocks_manager"})
    assert (watchlist["state"], watchlist["can_ask"], watchlist["request_id"]) == (status, False, request_id)
