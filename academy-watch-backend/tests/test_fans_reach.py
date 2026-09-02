"""S2 fan-follow routes, safe counts, and profile-activity preferences."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
import src.auth as auth_module
from src.auth import _ensure_user_account, issue_user_token
from src.models.league import League, Team, UserAccount, db
from src.models.player_fan import PlayerFan
from src.models.player_suppression import PlayerSuppression
from src.models.product_event import ProductEvent
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.tracked_player import TrackedPlayer


def _years_ago(years: int) -> date:
    today = datetime.now(UTC).date()
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, month=2, day=28)


def _tracked(player_api_id: int, *, birth_date: date | None = None, age: int | None = None) -> TrackedPlayer:
    league = League(
        league_id=1_000_000 + player_api_id,
        name=f"Fan League {player_api_id}",
        country="England",
        season=2026,
    )
    db.session.add(league)
    db.session.flush()
    team = Team(
        team_id=2_000_000 + player_api_id,
        name=f"Fan Team {player_api_id}",
        country="England",
        season=2026,
        league_id=league.id,
    )
    db.session.add(team)
    db.session.flush()
    player = TrackedPlayer(
        player_api_id=player_api_id,
        player_name=f"Fan Player {player_api_id}",
        team_id=team.id,
        birth_date=birth_date.isoformat() if birth_date is not None else None,
        age=age,
        status="academy",
        data_source="api-football",
        is_active=True,
    )
    db.session.add(player)
    db.session.flush()
    return player


def _local(name: str, *, birth_date: date | None, status: str = "approved") -> LocalPlayer:
    player = LocalPlayer(
        display_name=name,
        normalized_name=LocalPlayer.normalize_name(name),
        birth_date=birth_date,
        birth_year=birth_date.year if birth_date else None,
        status=status,
    )
    db.session.add(player)
    db.session.flush()
    player.api_player_id = -player.id
    db.session.flush()
    return player


def _account(email: str) -> tuple[UserAccount, dict[str, str]]:
    user = _ensure_user_account(email)
    db.session.commit()
    token = issue_user_token(email)["token"]
    return user, {"Authorization": f"Bearer {token}"}


def _claim(
    user: UserAccount,
    *,
    player_api_id: int | None = None,
    local_player_id: int | None = None,
    status: str = "approved",
) -> PlayerProfileClaim:
    claim = PlayerProfileClaim(
        player_api_id=player_api_id,
        local_player_id=local_player_id,
        user_account_id=user.id,
        relationship_type="player",
        status=status,
    )
    db.session.add(claim)
    db.session.flush()
    return claim


def _suppress(*, player_api_id: int | None = None, local_player_id: int | None = None) -> PlayerSuppression:
    suppression = PlayerSuppression(
        player_api_id=player_api_id,
        local_player_id=local_player_id,
        reason_code="player_request",
        requester_role="player",
        requester_contact="privacy@example.com",
        request_statement="Remove this profile.",
        status="active",
    )
    db.session.add(suppression)
    db.session.flush()
    return suppression


def _post_follow(client, player_api_id: int, headers: dict[str, str]):
    return client.post(
        f"/api/players/{player_api_id}/follow",
        headers=headers,
        content_type="application/json",
    )


def test_any_active_account_can_follow_tracked_adult_without_scout_verification(client, app, monkeypatch):
    monkeypatch.delenv("PUBLIC_API_BASE_URL", raising=False)
    player_id = 71_001
    _tracked(player_id, birth_date=_years_ago(22))
    db.session.commit()
    first_user, first_headers = _account("ordinary-fan@example.com")
    _second_user, second_headers = _account("another-fan@example.com")

    first = _post_follow(client, player_id, first_headers)
    assert first.status_code == 201
    assert first.get_json() == {
        "player_api_id": player_id,
        "following": True,
        "fans": 1,
        "created": True,
    }

    repeated = _post_follow(client, player_id, first_headers)
    assert repeated.status_code == 200
    assert repeated.get_json() == {
        "player_api_id": player_id,
        "following": True,
        "fans": 1,
        "created": False,
    }
    assert PlayerFan.query.filter_by(user_account_id=first_user.id, player_api_id=player_id).count() == 1
    assert (
        ProductEvent.query.filter_by(
            event_name="fan_follow_added",
            user_email=first_user.email,
        ).count()
        == 1
    )

    second = _post_follow(client, player_id, second_headers)
    assert second.status_code == 201
    assert second.get_json()["fans"] == 2

    count = client.get(f"/api/players/{player_id}/followers/count")
    assert count.status_code == 200
    assert count.get_json() == {
        "player_api_id": player_id,
        "fans": 2,
        "following": None,
        "share_url": f"http://localhost/p/{player_id}",
    }


def test_approved_adult_local_player_accepts_negative_signed_follow(client, app):
    local = _local("Adult Local", birth_date=_years_ago(24))
    db.session.commit()
    _user, headers = _account("local-fan@example.com")

    response = _post_follow(client, local.api_player_id, headers)
    assert response.status_code == 201
    assert response.get_json() == {
        "player_api_id": local.api_player_id,
        "following": True,
        "fans": 1,
        "created": True,
    }
    assert PlayerFan.query.filter_by(player_api_id=local.api_player_id).count() == 1


def test_follow_requires_authentication(client, app):
    player_id = 71_101
    _tracked(player_id, birth_date=_years_ago(21))
    db.session.commit()

    response = client.post(
        f"/api/players/{player_id}/follow",
        content_type="application/json",
    )
    assert response.status_code == 401
    assert PlayerFan.query.count() == 0


def test_neutral_404_mutation_guard_rejects_403_for_every_hidden_subject(client, app):
    minor_id = 71_201
    suppressed_id = 71_202
    unknown_age_id = 71_203
    _tracked(minor_id, birth_date=_years_ago(15))
    _tracked(suppressed_id, birth_date=_years_ago(25))
    _tracked(unknown_age_id)
    pending = _local("Pending Local", birth_date=_years_ago(23), status="pending")
    _suppress(player_api_id=suppressed_id)
    db.session.commit()
    user, headers = _account("neutrality@example.com")
    _claim(user, player_api_id=minor_id)
    db.session.commit()

    hidden_ids = [minor_id, suppressed_id, unknown_age_id, pending.api_player_id, 71_299]
    baseline = client.get(f"/api/players/{hidden_ids[-1]}/followers/count")
    assert baseline.status_code == 404
    assert baseline.get_json() == {"error": "Player not found"}

    for player_id in hidden_ids:
        count_response = client.get(f"/api/players/{player_id}/followers/count")
        follow_response = _post_follow(client, player_id, headers)
        assert count_response.status_code == 404
        assert follow_response.status_code == 404
        assert count_response.data == baseline.data
        assert follow_response.data == baseline.data

    assert PlayerFan.query.count() == 0
    assert ProductEvent.query.filter_by(event_name="fan_follow_added").count() == 0


def test_approved_owner_cannot_follow_own_public_profile(client, app):
    player_id = 71_301
    _tracked(player_id, birth_date=_years_ago(26))
    db.session.commit()
    owner, headers = _account("player-owner@example.com")
    _claim(owner, player_api_id=player_id)
    db.session.commit()

    response = _post_follow(client, player_id, headers)
    assert response.status_code == 400
    assert response.get_json() == {"error": "You cannot follow your own profile"}
    assert PlayerFan.query.count() == 0


def test_owner_follow_placed_while_claim_pending_is_excluded_after_approval(client, app):
    player_id = 71_401
    _tracked(player_id, birth_date=_years_ago(20))
    db.session.commit()
    owner, headers = _account("pending-owner@example.com")
    claim = _claim(owner, player_api_id=player_id, status="pending")
    db.session.commit()

    followed = _post_follow(client, player_id, headers)
    assert followed.status_code == 201
    assert followed.get_json()["fans"] == 1
    claim.status = "approved"
    db.session.commit()

    anonymous_count = client.get(f"/api/players/{player_id}/followers/count")
    owner_count = client.get(f"/api/players/{player_id}/followers/count", headers=headers)
    assert anonymous_count.get_json()["fans"] == 0
    assert owner_count.get_json()["fans"] == 0
    assert owner_count.get_json()["following"] is False
    assert PlayerFan.query.filter_by(user_account_id=owner.id, player_api_id=player_id).count() == 1
    assert _post_follow(client, player_id, headers).status_code == 400


def test_optional_auth_never_turns_count_read_into_401(client, app, monkeypatch):
    player_id = 71_501
    _tracked(player_id, birth_date=_years_ago(27))
    db.session.commit()
    fan, fan_headers = _account("following@example.com")
    _other, other_headers = _account("not-following@example.com")
    assert _post_follow(client, player_id, fan_headers).status_code == 201

    anonymous = client.get(f"/api/players/{player_id}/followers/count")
    malformed = client.get(
        f"/api/players/{player_id}/followers/count",
        headers={"Authorization": "Bearer definitely-not-valid"},
    )
    following = client.get(f"/api/players/{player_id}/followers/count", headers=fan_headers)
    not_following = client.get(f"/api/players/{player_id}/followers/count", headers=other_headers)
    assert [(response.status_code, response.get_json()["following"]) for response in (anonymous, malformed)] == [
        (200, None),
        (200, None),
    ]
    assert following.status_code == 200
    assert following.get_json()["following"] is True
    assert not_following.status_code == 200
    assert not_following.get_json()["following"] is False

    ttl = auth_module.USER_TOKEN_TTL_SECONDS
    monkeypatch.setattr(auth_module, "USER_TOKEN_TTL_SECONDS", -1)
    expired = client.get(f"/api/players/{player_id}/followers/count", headers=fan_headers)
    assert expired.status_code == 200
    assert expired.get_json()["following"] is None
    monkeypatch.setattr(auth_module, "USER_TOKEN_TTL_SECONDS", ttl)

    stale_user, stale_headers = _account("deleted-fan@example.com")
    db.session.delete(stale_user)
    db.session.commit()
    stale = client.get(f"/api/players/{player_id}/followers/count", headers=stale_headers)
    assert stale.status_code == 200
    assert stale.get_json()["following"] is None
    assert PlayerFan.query.filter_by(user_account_id=fan.id, player_api_id=player_id).count() == 1


def test_share_url_uses_configured_api_origin_not_request_host(client, app, monkeypatch):
    player_id = 71_601
    _tracked(player_id, birth_date=_years_ago(19))
    db.session.commit()
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.theacademywatch.com/")

    response = client.get(
        f"/api/players/{player_id}/followers/count",
        headers={"Host": "attacker.invalid"},
    )
    assert response.status_code == 200
    assert response.get_json()["share_url"] == f"https://api.theacademywatch.com/p/{player_id}"


def test_delete_is_idempotent_and_cleans_up_newly_suppressed_subject(client, app):
    player_id = 71_701
    _tracked(player_id, birth_date=_years_ago(31))
    db.session.commit()
    user, headers = _account("cleanup-fan@example.com")
    assert _post_follow(client, player_id, headers).status_code == 201

    _suppress(player_api_id=player_id)
    db.session.commit()
    first = client.delete(f"/api/players/{player_id}/follow", headers=headers)
    second = client.delete(f"/api/players/{player_id}/follow", headers=headers)
    assert first.status_code == 200
    assert first.get_json() == {
        "player_api_id": player_id,
        "following": False,
        "deleted": True,
    }
    assert second.status_code == 200
    assert second.get_json() == {
        "player_api_id": player_id,
        "following": False,
        "deleted": False,
    }
    assert PlayerFan.query.filter_by(user_account_id=user.id, player_api_id=player_id).count() == 0

    events = (
        ProductEvent.query.filter(ProductEvent.event_name.in_(["fan_follow_added", "fan_follow_removed"]))
        .order_by(ProductEvent.id.asc())
        .all()
    )
    assert [(event.event_name, event.user_email, event.props) for event in events] == [
        ("fan_follow_added", user.email, {"player_api_id": player_id}),
        ("fan_follow_removed", user.email, {"player_api_id": player_id}),
    ]


def test_email_preferences_get_and_patch_supported_fields(client, app):
    user, headers = _account("preference-owner@example.com")
    initial = client.get("/api/user/email-preferences", headers=headers)
    assert initial.status_code == 200
    assert initial.get_json() == {
        "user_id": user.id,
        "email_delivery_preference": "individual",
        "profile_activity_email_opt_in": False,
    }

    opted_in = client.patch(
        "/api/user/email-preferences",
        headers=headers,
        json={"profile_activity_email_opt_in": True},
    )
    assert opted_in.status_code == 200
    assert opted_in.get_json() == {
        "user_id": user.id,
        "email_delivery_preference": "individual",
        "profile_activity_email_opt_in": True,
    }

    digest = client.patch(
        "/api/user/email-preferences",
        headers=headers,
        json={"email_delivery_preference": "digest", "ignored_future_field": "safe"},
    )
    assert digest.status_code == 200
    assert digest.get_json() == {
        "user_id": user.id,
        "email_delivery_preference": "digest",
        "profile_activity_email_opt_in": True,
    }

    both = client.patch(
        "/api/user/email-preferences",
        headers=headers,
        json={
            "email_delivery_preference": "individual",
            "profile_activity_email_opt_in": False,
        },
    )
    assert both.status_code == 200
    assert both.get_json() == initial.get_json()


@pytest.mark.parametrize(
    "body",
    [
        [],
        7,
        None,
        {},
        {"unknown": True},
        {"email_delivery_preference": 1},
        {"email_delivery_preference": "weekly"},
        {"profile_activity_email_opt_in": 1},
        {"profile_activity_email_opt_in": "true"},
        {
            "email_delivery_preference": "digest",
            "profile_activity_email_opt_in": "true",
        },
    ],
)
def test_email_preferences_patch_rejects_non_object_empty_unknown_and_invalid_values(client, app, body):
    _user, headers = _account("invalid-preference@example.com")
    response = client.patch("/api/user/email-preferences", headers=headers, json=body)
    assert response.status_code == 400


def test_email_preferences_validate_every_field_before_mutating_any(client, app):
    user, headers = _account("atomic-preference@example.com")
    response = client.patch(
        "/api/user/email-preferences",
        headers=headers,
        json={
            "email_delivery_preference": "digest",
            "profile_activity_email_opt_in": "true",
        },
    )

    assert response.status_code == 400
    db.session.expire_all()
    stored = db.session.get(UserAccount, user.id)
    assert stored.email_delivery_preference == "individual"
    assert stored.profile_activity_email_opt_in is False
