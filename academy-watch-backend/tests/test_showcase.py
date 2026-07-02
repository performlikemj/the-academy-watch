"""Tests for the Talent Showcase blueprint (src/routes/showcase.py).

Covers claims (create / dedupe / review transitions / permissions / revoke),
owner-gated profile + reel curation (owner gate, validation, moderation
visibility, reorder), the public payload shape, Flywheel X verified footage +
roster linking, and the submit_player_link URL hardening in api.py.
"""

from datetime import date

import pytest
from flask import Flask
from src.auth import _ensure_user_account, issue_user_token
from src.models.league import League, PlayerLink, Team, db
from src.models.showcase import PlayerProfileClaim, PlayerShowcaseProfile
from src.models.tracked_player import TrackedPlayer
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry

ADMIN_KEY = "test-admin-key"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")

    from src.routes.api import api_bp
    from src.routes.showcase import showcase_bp

    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )

    db.init_app(flask_app)
    flask_app.register_blueprint(showcase_bp, url_prefix="/api")
    flask_app.register_blueprint(api_bp, url_prefix="/api")

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _user_headers(email):
    token = issue_user_token(email)["token"]
    return {"Authorization": f"Bearer {token}"}


def _admin_headers():
    token = issue_user_token("admin@test.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


def _make_user(email):
    user = _ensure_user_account(email)
    db.session.commit()
    return user


def _seed_team(team_id=33, name="Manchester United"):
    league = League.query.filter_by(league_id=39).first()
    if league is None:
        league = League(league_id=39, name="Premier League", country="England", season=2025)
        db.session.add(league)
        db.session.flush()
    team = Team(team_id=team_id, name=name, country="England", season=2025, league_id=league.id, is_active=True)
    db.session.add(team)
    db.session.flush()
    return team


def _tracked(team, player_api_id=5001, name="Kobbie Mainoo", **kwargs):
    tp = TrackedPlayer(
        player_api_id=player_api_id,
        player_name=name,
        team_id=team.id,
        status=kwargs.pop("status", "academy"),
        is_active=kwargs.pop("is_active", True),
        **kwargs,
    )
    db.session.add(tp)
    db.session.flush()
    return tp


def _approved_claim(player_api_id, email):
    user = _make_user(email)
    claim = PlayerProfileClaim(
        player_api_id=player_api_id,
        user_account_id=user.id,
        relationship_type="player",
        status="approved",
    )
    db.session.add(claim)
    db.session.commit()
    return user, claim


def _finalized_match(team, opponent="Rivals FC", status="finalized", match_date=None):
    match = VideoMatch(
        team_id=team.id,
        opponent_name=opponent,
        status=status,
        match_date=match_date or date(2025, 9, 1),
    )
    db.session.add(match)
    db.session.flush()
    return match


def _roster(match, tp_id=None, name="Kobbie Mainoo", number=37):
    entry = VideoRosterEntry(
        video_match_id=match.id,
        player_name=name,
        jersey_number=number,
        tracked_player_id=tp_id,
    )
    db.session.add(entry)
    db.session.flush()
    return entry


def _report(match, roster, tp_id=None, identity="human_confirmed", minutes=87.0, pct=72):
    rep = VideoPlayerReport(
        video_match_id=match.id,
        roster_entry_id=roster.id,
        tracked_player_id=tp_id,
        minutes_visible=minutes,
        identity_confidence=identity,
        coverage={"pct_of_match": pct},
        model_version="v1",
    )
    db.session.add(rep)
    db.session.flush()
    return rep


# --------------------------------------------------------------------------- #
# Claims
# --------------------------------------------------------------------------- #


class TestClaims:
    def test_create_claim_returns_pending(self, client):
        resp = client.post(
            "/api/players/5001/claim",
            json={"relationship_type": "player", "message": "This is me"},
            headers=_user_headers("kobbie@example.com"),
        )
        assert resp.status_code == 201
        claim = resp.get_json()["claim"]
        assert claim["status"] == "pending"
        assert claim["relationship_type"] == "player"
        assert claim["message"] == "This is me"

    def test_duplicate_claim_returns_409(self, client):
        headers = _user_headers("kobbie@example.com")
        first = client.post("/api/players/5001/claim", json={"relationship_type": "player"}, headers=headers)
        assert first.status_code == 201
        dupe = client.post("/api/players/5001/claim", json={"relationship_type": "agent"}, headers=headers)
        assert dupe.status_code == 409

    def test_invalid_relationship_type_rejected(self, client):
        resp = client.post(
            "/api/players/5001/claim",
            json={"relationship_type": "manager"},
            headers=_user_headers("kobbie@example.com"),
        )
        assert resp.status_code == 400

    def test_claim_requires_auth(self, client):
        resp = client.post("/api/players/5001/claim", json={"relationship_type": "player"})
        assert resp.status_code == 401

    def test_me_claims_lists_own_claims(self, app, client):
        with app.app_context():
            team = _seed_team()
            _tracked(team, player_api_id=5001, name="Kobbie Mainoo")
            db.session.commit()
        headers = _user_headers("kobbie@example.com")
        client.post("/api/players/5001/claim", json={"relationship_type": "player"}, headers=headers)
        resp = client.get("/api/me/claims", headers=headers)
        assert resp.status_code == 200
        claims = resp.get_json()["claims"]
        assert len(claims) == 1
        assert claims[0]["player_api_id"] == 5001
        assert claims[0]["player_name"] == "Kobbie Mainoo"


class TestAdminClaimReview:
    def test_approve_then_public_claim_status_claimed(self, app, client):
        headers = _user_headers("kobbie@example.com")
        create = client.post("/api/players/5001/claim", json={"relationship_type": "player"}, headers=headers)
        claim_id = create.get_json()["claim"]["id"]

        review = client.post(
            f"/api/admin/showcase/claims/{claim_id}/review",
            json={"action": "approve"},
            headers=_admin_headers(),
        )
        assert review.status_code == 200
        assert review.get_json()["claim"]["status"] == "approved"
        assert review.get_json()["claim"]["reviewed_by"] == "admin@test.com"

        public = client.get("/api/players/5001/showcase")
        assert public.get_json()["claim_status"] == "claimed"

    def test_reject_pending_claim(self, client):
        headers = _user_headers("kobbie@example.com")
        claim_id = client.post(
            "/api/players/5001/claim", json={"relationship_type": "player"}, headers=headers
        ).get_json()["claim"]["id"]
        review = client.post(
            f"/api/admin/showcase/claims/{claim_id}/review", json={"action": "reject"}, headers=_admin_headers()
        )
        assert review.status_code == 200
        assert review.get_json()["claim"]["status"] == "rejected"

    def test_revoke_requires_approved(self, client):
        headers = _user_headers("kobbie@example.com")
        claim_id = client.post(
            "/api/players/5001/claim", json={"relationship_type": "player"}, headers=headers
        ).get_json()["claim"]["id"]
        # pending → revoke is invalid
        bad = client.post(
            f"/api/admin/showcase/claims/{claim_id}/review", json={"action": "revoke"}, headers=_admin_headers()
        )
        assert bad.status_code == 409
        # approve, then revoke succeeds
        client.post(
            f"/api/admin/showcase/claims/{claim_id}/review", json={"action": "approve"}, headers=_admin_headers()
        )
        good = client.post(
            f"/api/admin/showcase/claims/{claim_id}/review", json={"action": "revoke"}, headers=_admin_headers()
        )
        assert good.status_code == 200
        assert good.get_json()["claim"]["status"] == "revoked"

    def test_approve_does_not_revoke_other_claims(self, app, client):
        # A player and an agent both claim; approving one leaves the other untouched.
        client.post(
            "/api/players/5001/claim", json={"relationship_type": "player"}, headers=_user_headers("player@x.com")
        )
        client.post(
            "/api/players/5001/claim", json={"relationship_type": "agent"}, headers=_user_headers("agent@x.com")
        )
        with app.app_context():
            claims = PlayerProfileClaim.query.filter_by(player_api_id=5001).order_by(PlayerProfileClaim.id).all()
            first_id = claims[0].id
        client.post(
            f"/api/admin/showcase/claims/{first_id}/review", json={"action": "approve"}, headers=_admin_headers()
        )
        listing = client.get("/api/admin/showcase/claims", headers=_admin_headers()).get_json()["claims"]
        statuses = sorted(c["status"] for c in listing)
        assert statuses == ["approved", "pending"]

    def test_review_requires_admin(self, client):
        headers = _user_headers("kobbie@example.com")
        claim_id = client.post(
            "/api/players/5001/claim", json={"relationship_type": "player"}, headers=headers
        ).get_json()["claim"]["id"]
        # A plain user Bearer token (no admin role / X-API-Key) is rejected.
        resp = client.post(f"/api/admin/showcase/claims/{claim_id}/review", json={"action": "approve"}, headers=headers)
        assert resp.status_code in (401, 403)


# --------------------------------------------------------------------------- #
# Owner gate + profile
# --------------------------------------------------------------------------- #


class TestProfileOwnerGate:
    def test_non_owner_cannot_edit_profile(self, client):
        # No claim at all → 403.
        resp = client.put(
            "/api/players/5001/showcase/profile",
            json={"bio": "hi"},
            headers=_user_headers("stranger@example.com"),
        )
        assert resp.status_code == 403

    def test_pending_claim_is_not_owner(self, client):
        headers = _user_headers("kobbie@example.com")
        client.post("/api/players/5001/claim", json={"relationship_type": "player"}, headers=headers)
        # Claim is pending (unapproved) → still not an owner.
        resp = client.put("/api/players/5001/showcase/profile", json={"bio": "hi"}, headers=headers)
        assert resp.status_code == 403

    def test_owner_edit_goes_pending_and_hidden_until_approved(self, app, client):
        with app.app_context():
            _approved_claim(5001, "kobbie@example.com")
        headers = _user_headers("kobbie@example.com")

        put = client.put(
            "/api/players/5001/showcase/profile",
            json={"bio": "Academy graduate", "positions": "CM", "preferred_foot": "right", "height_cm": 180},
            headers=headers,
        )
        assert put.status_code == 200
        assert put.get_json()["profile"]["status"] == "pending"

        # Public payload hides the pending profile.
        public = client.get("/api/players/5001/showcase").get_json()
        assert public["profile"] is None

        # Admin approves → now public.
        approve = client.post(
            "/api/admin/showcase/profiles/5001/review", json={"action": "approve"}, headers=_admin_headers()
        )
        assert approve.status_code == 200
        public = client.get("/api/players/5001/showcase").get_json()
        assert public["profile"] is not None
        assert public["profile"]["bio"] == "Academy graduate"
        assert public["profile"]["self_reported"] is True

    def test_invalid_preferred_foot_and_height(self, app, client):
        with app.app_context():
            _approved_claim(5001, "kobbie@example.com")
        headers = _user_headers("kobbie@example.com")
        assert (
            client.put(
                "/api/players/5001/showcase/profile", json={"preferred_foot": "sideways"}, headers=headers
            ).status_code
            == 400
        )
        assert (
            client.put("/api/players/5001/showcase/profile", json={"height_cm": 5}, headers=headers).status_code == 400
        )


# --------------------------------------------------------------------------- #
# Reel
# --------------------------------------------------------------------------- #


class TestReel:
    def _own(self, app):
        with app.app_context():
            _approved_claim(5001, "kobbie@example.com")

    def test_add_youtube_item_then_moderation_visibility(self, app, client):
        self._own(app)
        headers = _user_headers("kobbie@example.com")
        resp = client.post(
            "/api/players/5001/showcase/reel",
            json={"url": "https://www.youtube.com/watch?v=abc123", "title": "Screamer"},
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.get_json()["link"]["status"] == "pending"

        # Pending item is invisible to the public reel.
        public = client.get("/api/players/5001/showcase").get_json()
        assert public["reel"] == []

    def test_non_youtube_url_rejected(self, app, client):
        self._own(app)
        resp = client.post(
            "/api/players/5001/showcase/reel",
            json={"url": "https://vimeo.com/12345"},
            headers=_user_headers("kobbie@example.com"),
        )
        assert resp.status_code == 400

    def test_non_https_url_rejected(self, app, client):
        self._own(app)
        headers = _user_headers("kobbie@example.com")
        for bad in ("javascript:alert(1)", "http://www.youtube.com/watch?v=abc"):
            resp = client.post("/api/players/5001/showcase/reel", json={"url": bad}, headers=headers)
            assert resp.status_code == 400, bad

    def test_reel_cap_enforced(self, app, client):
        with app.app_context():
            _approved_claim(5001, "kobbie@example.com")
            for i in range(20):
                db.session.add(
                    PlayerLink(
                        player_id=5001,
                        url=f"https://youtu.be/vid{i}",
                        link_type="highlight",
                        status="approved",
                    )
                )
            db.session.commit()
        resp = client.post(
            "/api/players/5001/showcase/reel",
            json={"url": "https://youtu.be/onemore"},
            headers=_user_headers("kobbie@example.com"),
        )
        assert resp.status_code == 400

    def test_approved_highlight_appears_in_public_reel(self, app, client):
        with app.app_context():
            db.session.add(
                PlayerLink(
                    player_id=5001,
                    url="https://youtu.be/approved1",
                    title="Best bits",
                    link_type="highlight",
                    status="approved",
                    sort_order=0,
                )
            )
            db.session.commit()
        public = client.get("/api/players/5001/showcase").get_json()
        assert len(public["reel"]) == 1
        assert public["reel"][0]["url"] == "https://youtu.be/approved1"
        assert public["reel"][0]["sort_order"] == 0

    def test_reorder_ignores_foreign_and_synthetic_ids(self, app, client):
        with app.app_context():
            _approved_claim(5001, "kobbie@example.com")
            a = PlayerLink(player_id=5001, url="https://youtu.be/a", link_type="highlight", status="approved")
            b = PlayerLink(player_id=5001, url="https://youtu.be/b", link_type="highlight", status="approved")
            # A link belonging to a DIFFERENT player — must be ignored by reorder.
            foreign = PlayerLink(player_id=9999, url="https://youtu.be/f", link_type="highlight", status="approved")
            db.session.add_all([a, b, foreign])
            db.session.commit()
            a_id, b_id, foreign_id = a.id, b.id, foreign.id

        headers = _user_headers("kobbie@example.com")
        resp = client.patch(
            "/api/players/5001/showcase/reel/order",
            json={"ordered_ids": [b_id, a_id, foreign_id, "yt-1", 999999]},
            headers=headers,
        )
        assert resp.status_code == 200

        with app.app_context():
            assert db.session.get(PlayerLink, b_id).sort_order == 0
            assert db.session.get(PlayerLink, a_id).sort_order == 1
            # Foreign link untouched (still its default).
            assert db.session.get(PlayerLink, foreign_id).sort_order in (0, None)

        # Public reel now reflects the new order (b before a).
        public = client.get("/api/players/5001/showcase").get_json()
        urls = [r["url"] for r in public["reel"]]
        assert urls == ["https://youtu.be/b", "https://youtu.be/a"]

    def test_delete_permissions(self, app, client):
        with app.app_context():
            owner, _ = _approved_claim(5001, "owner@example.com")
            link = PlayerLink(
                player_id=5001, url="https://youtu.be/x", link_type="highlight", status="approved", user_id=owner.id
            )
            db.session.add(link)
            db.session.commit()
            link_id = link.id

        # A stranger with no claim and who did not submit it cannot delete.
        stranger = client.delete(
            f"/api/players/5001/showcase/reel/{link_id}", headers=_user_headers("stranger@example.com")
        )
        assert stranger.status_code == 403
        # The approved owner can delete.
        owner_del = client.delete(
            f"/api/players/5001/showcase/reel/{link_id}", headers=_user_headers("owner@example.com")
        )
        assert owner_del.status_code == 200

    def test_newsletter_youtube_links_merge_into_public_reel(self, app, client):
        from src.models.league import NewsletterPlayerYoutubeLink

        with app.app_context():
            # newsletter_id is a dangling ref (SQLite does not enforce FKs by
            # default); the reel merge only queries these rows by player_id.
            db.session.add(
                NewsletterPlayerYoutubeLink(
                    newsletter_id=1,
                    player_id=5001,
                    player_name="Kobbie Mainoo",
                    youtube_link="https://youtu.be/nl1",
                )
            )
            db.session.commit()
        public = client.get("/api/players/5001/showcase").get_json()
        assert any(r["source"] == "newsletter" and str(r["id"]).startswith("yt-") for r in public["reel"])


# --------------------------------------------------------------------------- #
# Public payload
# --------------------------------------------------------------------------- #


class TestPublicPayload:
    def test_shape_unclaimed_empty(self, client):
        resp = client.get("/api/players/5001/showcase")
        assert resp.status_code == 200
        data = resp.get_json()
        assert set(data.keys()) == {"player_api_id", "profile", "reel", "verified_footage", "claim_status"}
        assert data["profile"] is None
        assert data["reel"] == []
        assert data["verified_footage"] == []
        assert data["claim_status"] == "unclaimed"


# --------------------------------------------------------------------------- #
# Flywheel X — verified footage + roster linking
# --------------------------------------------------------------------------- #


class TestVerifiedFootage:
    def test_only_human_confirmed_linked_finalized(self, app, client):
        with app.app_context():
            team = _seed_team()
            tp = _tracked(team, player_api_id=5001, name="Kobbie Mainoo")

            # Qualifying: finalized + human_confirmed + linked roster.
            m1 = _finalized_match(team, opponent="Rivals FC", match_date=date(2025, 9, 10))
            r1 = _roster(m1, tp_id=tp.id, number=37)
            _report(m1, r1, tp_id=tp.id, identity="human_confirmed", minutes=88.0, pct=70)

            # Excluded: low-confidence identity.
            m2 = _finalized_match(team, opponent="Weak Signal FC", match_date=date(2025, 9, 3))
            r2 = _roster(m2, tp_id=tp.id, number=37)
            _report(m2, r2, tp_id=tp.id, identity="low", minutes=50.0)

            # Excluded: not finalized.
            m3 = _finalized_match(team, opponent="Pending FC", status="needs_tagging", match_date=date(2025, 9, 5))
            r3 = _roster(m3, tp_id=tp.id, number=37)
            _report(m3, r3, tp_id=tp.id, identity="human_confirmed", minutes=60.0)

            # Excluded: roster not linked to this player.
            m4 = _finalized_match(team, opponent="Unlinked FC", match_date=date(2025, 9, 7))
            r4 = _roster(m4, tp_id=None, number=99)
            _report(m4, r4, tp_id=None, identity="human_confirmed", minutes=90.0)
            db.session.commit()

        data = client.get("/api/players/5001/showcase").get_json()
        footage = data["verified_footage"]
        assert len(footage) == 1
        entry = footage[0]
        assert entry["opponent_name"] == "Rivals FC"
        assert entry["team_name"] == "Manchester United"
        assert entry["minutes_on_camera"] == 88.0
        assert entry["pct_of_match"] == 70
        assert entry["verified"] is True


class TestRosterLinking:
    def test_link_set_and_clear_propagates_denorm(self, app, client):
        with app.app_context():
            team = _seed_team()
            tp = _tracked(team, player_api_id=5001, name="Kobbie Mainoo")
            match = _finalized_match(team)
            roster = _roster(match, tp_id=None, number=37)
            report = _report(match, roster, tp_id=None, identity="human_confirmed")
            db.session.commit()
            roster_id, report_id, tp_id = roster.id, report.id, tp.id

        # Link.
        link = client.put(
            f"/api/admin/showcase/video-rosters/{roster_id}/link",
            json={"player_api_id": 5001},
            headers=_admin_headers(),
        )
        assert link.status_code == 200
        with app.app_context():
            assert db.session.get(VideoRosterEntry, roster_id).tracked_player_id == tp_id
            assert db.session.get(VideoPlayerReport, report_id).tracked_player_id == tp_id

        # Clear.
        clear = client.put(
            f"/api/admin/showcase/video-rosters/{roster_id}/link",
            json={"player_api_id": None},
            headers=_admin_headers(),
        )
        assert clear.status_code == 200
        with app.app_context():
            assert db.session.get(VideoRosterEntry, roster_id).tracked_player_id is None
            assert db.session.get(VideoPlayerReport, report_id).tracked_player_id is None

    def test_link_unknown_player_404(self, app, client):
        with app.app_context():
            team = _seed_team()
            match = _finalized_match(team)
            roster = _roster(match, tp_id=None)
            db.session.commit()
            roster_id = roster.id
        resp = client.put(
            f"/api/admin/showcase/video-rosters/{roster_id}/link",
            json={"player_api_id": 999999},
            headers=_admin_headers(),
        )
        assert resp.status_code == 404

    def test_video_rosters_listing_and_player_search(self, app, client):
        with app.app_context():
            team = _seed_team()
            tp = _tracked(team, player_api_id=5001, name="Kobbie Mainoo")
            match = _finalized_match(team)
            _roster(match, tp_id=tp.id, number=37)
            db.session.commit()

        rosters = client.get(
            "/api/admin/showcase/video-rosters?player_api_id=5001", headers=_admin_headers()
        ).get_json()["rosters"]
        assert len(rosters) == 1
        assert rosters[0]["player_name"] == "Kobbie Mainoo"

        search = client.get("/api/admin/showcase/player-search?q=mainoo", headers=_admin_headers()).get_json()[
            "players"
        ]
        assert search[0]["player_api_id"] == 5001


# --------------------------------------------------------------------------- #
# Optional-auth owner visibility on the public showcase endpoint
# --------------------------------------------------------------------------- #


class TestOptionalOwnerVisibility:
    def _seed_owner_with_drafts(self, app, owner_email="owner@example.com"):
        with app.app_context():
            owner, _ = _approved_claim(5001, owner_email)
            db.session.add(PlayerShowcaseProfile(player_api_id=5001, bio="Draft bio", status="pending"))
            db.session.add(
                PlayerLink(
                    player_id=5001,
                    user_id=owner.id,
                    url="https://youtu.be/pending1",
                    title="Draft clip",
                    link_type="highlight",
                    status="pending",
                )
            )
            db.session.commit()

    def test_owner_sees_pending_reel_and_profile_draft(self, app, client):
        self._seed_owner_with_drafts(app)
        data = client.get("/api/players/5001/showcase", headers=_user_headers("owner@example.com")).get_json()
        # Pending profile draft is visible to the owner, carrying its status.
        assert data["profile"] is not None
        assert data["profile"]["status"] == "pending"
        assert data["profile"]["bio"] == "Draft bio"
        # Pending reel item is visible to the owner, carrying its status.
        pending = [r for r in data["reel"] if r["url"] == "https://youtu.be/pending1"]
        assert len(pending) == 1
        assert pending[0]["status"] == "pending"

    def test_anonymous_gets_public_view(self, app, client):
        self._seed_owner_with_drafts(app)
        data = client.get("/api/players/5001/showcase").get_json()
        assert data["profile"] is None
        assert all(r["url"] != "https://youtu.be/pending1" for r in data["reel"])

    def test_non_owner_authed_gets_public_view(self, app, client):
        self._seed_owner_with_drafts(app)
        # A valid token for a user with NO approved claim → public view.
        data = client.get("/api/players/5001/showcase", headers=_user_headers("stranger@example.com")).get_json()
        assert data["profile"] is None
        assert all(r["url"] != "https://youtu.be/pending1" for r in data["reel"])

    def test_garbage_token_degrades_to_public_200(self, app, client):
        self._seed_owner_with_drafts(app)
        resp = client.get("/api/players/5001/showcase", headers={"Authorization": "Bearer not.a.real.token"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["profile"] is None
        assert all(r["url"] != "https://youtu.be/pending1" for r in data["reel"])


# --------------------------------------------------------------------------- #
# submit_player_link URL hardening (api.py)
# --------------------------------------------------------------------------- #


class TestSubmitPlayerLinkHardening:
    def test_javascript_url_rejected(self, client):
        resp = client.post(
            "/api/players/5001/links",
            json={"url": "javascript:alert(document.cookie)", "link_type": "article"},
            headers=_user_headers("fan@example.com"),
        )
        assert resp.status_code == 400

    def test_https_url_accepted(self, client):
        resp = client.post(
            "/api/players/5001/links",
            json={"url": "https://example.com/article", "link_type": "article"},
            headers=_user_headers("fan@example.com"),
        )
        assert resp.status_code == 201


# --------------------------------------------------------------------------- #
# Review-fix regressions (adversarial review 2026-07-02)
# --------------------------------------------------------------------------- #


class TestClaimRecovery:
    """A rejected/revoked claim must never be a permanent dead-end."""

    def _claim(self, client, email="kobbie@example.com"):
        return client.post(
            "/api/players/5001/claim",
            json={"relationship_type": "player", "message": "It's me"},
            headers=_user_headers(email),
        )

    def _review(self, client, claim_id, action):
        return client.post(
            f"/api/admin/showcase/claims/{claim_id}/review",
            json={"action": action},
            headers=_admin_headers(),
        )

    def test_rejected_claim_can_be_resubmitted(self, app, client):
        claim_id = self._claim(client).get_json()["claim"]["id"]
        assert self._review(client, claim_id, "reject").status_code == 200

        resub = self._claim(client)
        assert resub.status_code == 201
        body = resub.get_json()["claim"]
        assert body["id"] == claim_id  # same row, reset
        assert body["status"] == "pending"
        assert body["reviewed_by"] is None

    def test_revoked_claim_can_be_resubmitted(self, app, client):
        claim_id = self._claim(client).get_json()["claim"]["id"]
        assert self._review(client, claim_id, "approve").status_code == 200
        assert self._review(client, claim_id, "revoke").status_code == 200

        resub = self._claim(client)
        assert resub.status_code == 201
        assert resub.get_json()["claim"]["status"] == "pending"

    def test_admin_can_approve_rejected_claim(self, app, client):
        claim_id = self._claim(client).get_json()["claim"]["id"]
        assert self._review(client, claim_id, "reject").status_code == 200
        resp = self._review(client, claim_id, "approve")
        assert resp.status_code == 200
        assert resp.get_json()["claim"]["status"] == "approved"

    def test_pending_claim_still_409s_on_resubmit(self, app, client):
        assert self._claim(client).status_code == 201
        assert self._claim(client).status_code == 409

    def test_reject_still_requires_pending(self, app, client):
        claim_id = self._claim(client).get_json()["claim"]["id"]
        assert self._review(client, claim_id, "approve").status_code == 200
        assert self._review(client, claim_id, "reject").status_code == 409


class TestReelDedupAndSafety:
    """Newsletter merge: canonical video-id dedup + unsafe-URL filtering."""

    def _newsletter_link(self, url, player_id=5001):
        from src.models.league import Newsletter, NewsletterPlayerYoutubeLink

        newsletter = Newsletter.query.first()
        if newsletter is None:
            team = Team.query.first() or _seed_team()
            newsletter = Newsletter(team_id=team.id, title="Weekly", content="c", public_slug="weekly-test-slug")
            db.session.add(newsletter)
            db.session.flush()
        db.session.add(
            NewsletterPlayerYoutubeLink(
                newsletter_id=newsletter.id,
                player_id=player_id,
                player_name="Kobbie Mainoo",
                youtube_link=url,
            )
        )
        db.session.commit()

    def test_same_video_different_url_forms_dedups(self, app, client):
        with app.app_context():
            db.session.add(
                PlayerLink(
                    player_id=5001,
                    url="https://youtu.be/ABC123xyz",
                    link_type="highlight",
                    status="approved",
                )
            )
            db.session.commit()
            self._newsletter_link("https://www.youtube.com/watch?v=ABC123xyz")

        reel = client.get("/api/players/5001/showcase").get_json()["reel"]
        assert len(reel) == 1
        assert reel[0]["source"] == "user"

    def test_unsafe_newsletter_urls_never_reach_public_reel(self, app, client):
        with app.app_context():
            self._newsletter_link("javascript:alert(document.cookie)")
            self._newsletter_link("http://www.youtube.com/watch?v=insecure1")
            self._newsletter_link("https://example.com/not-youtube")
            self._newsletter_link("https://youtu.be/good1234")

        reel = client.get("/api/players/5001/showcase").get_json()["reel"]
        assert [r["url"] for r in reel] == ["https://youtu.be/good1234"]
