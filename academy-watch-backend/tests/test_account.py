"""Self-service account export and deletion contract tests (FC-TF1)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from flask import Flask
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.account import AccountDeletionEvent
from src.models.contact import ContactAuditEvent, ContactMessage, ContactOutcome, ContactRequest
from src.models.follow import Follow, FollowList, FollowPlayerSnapshot
from src.models.league import (
    CommunityTake,
    EmailToken,
    League,
    Newsletter,
    NewsletterPlayerYoutubeLink,
    PlayerLink,
    QuickTakeSubmission,
    StripeConnectedAccount,
    StripeSubscription,
    StripeSubscriptionPlan,
    Team,
    UserAccount,
    UserSubscription,
    db,
)
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.showcase import PlayerProfileClaim, PlayerShowcaseProfile
from src.models.trust import ContentReport, ScoutVerification

SUBJECT_ID = 91001
PLAYER_COUNTERPART_ID = 92002
SCOUT_COUNTERPART_ID = 93003
UNRELATED_SCOUT_ID = 94004
UNRELATED_PLAYER_ID = 95005
SUBJECT_PLAYER_ID = 7001
COUNTERPART_PLAYER_ID = 7002
UNRELATED_PLAYER_API_ID = 7999


@pytest.fixture
def account_app():
    from src.routes.account import account_bp
    from src.routes.showcase import showcase_bp

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="account-fixture-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=True,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(account_bp, url_prefix="/api")
    app.register_blueprint(showcase_bp, url_prefix="/api")

    with app.app_context():
        limiter.reset()
        db.create_all()
        yield app
        limiter.reset()
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(account_app):
    return account_app.test_client()


def _add_account(user_id: int, email: str, display_name: str) -> UserAccount:
    user = UserAccount(
        id=user_id,
        email=email,
        display_name=display_name,
        display_name_lower=display_name.lower(),
        display_name_confirmed=True,
    )
    db.session.add(user)
    return user


def _headers(email: str) -> dict[str, str]:
    token = issue_user_token(email)["token"]
    return {"Authorization": f"Bearer {token}"}


def _all_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_keys(child)


def _seed_full_account_graph():
    subject = _add_account(SUBJECT_ID, "delete-me@example.com", "Delete Me")
    player_counterpart = _add_account(
        PLAYER_COUNTERPART_ID,
        "player-counterpart@example.com",
        "Player Counterpart",
    )
    scout_counterpart = _add_account(
        SCOUT_COUNTERPART_ID,
        "scout-counterpart@example.com",
        "Scout Counterpart",
    )
    unrelated_scout = _add_account(
        UNRELATED_SCOUT_ID,
        "unrelated-scout@example.com",
        "Unrelated Scout",
    )
    unrelated_player = _add_account(
        UNRELATED_PLAYER_ID,
        "unrelated-player@example.com",
        "Unrelated Player",
    )

    league = League(league_id=88001, name="Fixture League", country="England", season=2026)
    team = Team(
        team_id=88002,
        name="Fixture Academy",
        country="England",
        season=2026,
        league=league,
    )
    newsletter = Newsletter(
        team=team,
        newsletter_type="weekly",
        title="Fixture issue",
        content="Provider-derived fixture content",
        public_slug="fixture-provider-issue",
    )
    db.session.add_all([league, team, newsletter])
    db.session.flush()

    subject_subscription = UserSubscription(
        email=subject.email,
        team_id=team.id,
        preferred_frequency="daily",
        active=True,
        unsubscribe_token="subject-secret-unsubscribe-token",
    )
    unrelated_subscription = UserSubscription(
        email=unrelated_scout.email,
        team_id=team.id,
        preferred_frequency="weekly",
        active=True,
        unsubscribe_token="unrelated-secret-unsubscribe-token",
    )
    subject_email_token = EmailToken(
        token="subject-private-email-token",
        email=subject.email,
        purpose="manage",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    subject_connected_account = StripeConnectedAccount(
        journalist_user_id=subject.id,
        stripe_account_id="acct_subject_private",
        onboarding_complete=True,
    )
    subject_subscription_plan = StripeSubscriptionPlan(
        journalist_user_id=subject.id,
        stripe_product_id="prod_subject_private",
        stripe_price_id="price_subject_private",
        price_amount=700,
    )
    subject_stripe_subscription = StripeSubscription(
        subscriber_user_id=scout_counterpart.id,
        journalist_user_id=subject.id,
        stripe_subscription_id="sub_subject_private",
        stripe_customer_id="cus_counterpart_private",
        status="active",
    )

    subject_watchlist = ScoutWatchlistEntry(
        user_account_id=subject.id,
        player_api_id=SUBJECT_PLAYER_ID,
        note="subject private watchlist note",
    )
    unrelated_watchlist = ScoutWatchlistEntry(
        user_account_id=unrelated_scout.id,
        player_api_id=UNRELATED_PLAYER_API_ID,
        note="UNRELATED WATCHLIST SENTINEL",
    )

    subject_list = FollowList(
        user_account_id=subject.id,
        name="Subject private prospects",
        cadence="weekly",
        is_active=True,
        player_cap=40,
    )
    unrelated_list = FollowList(
        user_account_id=unrelated_scout.id,
        name="UNRELATED FOLLOW LIST SENTINEL",
        cadence="weekly",
        is_active=True,
        player_cap=40,
    )
    db.session.add_all([subject_list, unrelated_list])
    db.session.flush()
    subject_follow = Follow(
        list_id=subject_list.id,
        kind="player",
        selector={"player_api_id": SUBJECT_PLAYER_ID},
        label="Subject prospect",
        note="subject follow note",
    )
    unrelated_follow = Follow(
        list_id=unrelated_list.id,
        kind="player",
        selector={"player_api_id": UNRELATED_PLAYER_API_ID},
        label="UNRELATED FOLLOW SENTINEL",
    )
    subject_snapshot = FollowPlayerSnapshot(
        user_account_id=subject.id,
        player_api_id=SUBJECT_PLAYER_ID,
        last_snapshot='{"appearances": 3}',
        note="subject snapshot note",
    )

    subject_verification = ScoutVerification(
        user_account_id=subject.id,
        full_name="Subject Scout",
        organization="Subject Scouting",
        role_title="Scout",
        statement="Subject verification statement",
        evidence_urls=["https://example.com/subject-evidence"],
        status="approved",
    )
    unrelated_verification = ScoutVerification(
        user_account_id=unrelated_scout.id,
        full_name="UNRELATED VERIFICATION SENTINEL",
        organization="Unrelated Scouting",
        role_title="Scout",
        statement="Unrelated verification statement",
        evidence_urls=["https://example.com/unrelated-evidence"],
        status="approved",
    )

    subject_claim = PlayerProfileClaim(
        player_api_id=SUBJECT_PLAYER_ID,
        user_account_id=subject.id,
        relationship_type="player",
        status="approved",
        message="subject private claim message",
        contract_status="free_agent",
    )
    counterpart_claim = PlayerProfileClaim(
        player_api_id=COUNTERPART_PLAYER_ID,
        user_account_id=player_counterpart.id,
        relationship_type="player",
        status="approved",
        message="counterpart claim message",
        contract_status="unknown",
    )
    unrelated_claim = PlayerProfileClaim(
        player_api_id=UNRELATED_PLAYER_API_ID,
        user_account_id=unrelated_player.id,
        relationship_type="player",
        status="approved",
        message="UNRELATED CLAIM SENTINEL",
        contract_status="contracted",
    )
    db.session.add_all([subject_claim, counterpart_claim, unrelated_claim])
    db.session.flush()

    subject_profile = PlayerShowcaseProfile(
        player_api_id=SUBJECT_PLAYER_ID,
        bio="subject self-reported biography",
        positions="CM,AM",
        preferred_foot="right",
        height_cm=181,
        status="approved",
        updated_by_user_id=subject.id,
        pending_contract_claim_id=subject_claim.id,
        pending_contract_status="contracted",
        pending_current_club_name="Subject pending club",
    )
    unrelated_profile = PlayerShowcaseProfile(
        player_api_id=UNRELATED_PLAYER_API_ID,
        bio="UNRELATED PROFILE SENTINEL",
        positions="GK",
        status="approved",
        updated_by_user_id=unrelated_player.id,
    )
    owner_link = PlayerLink(
        player_id=SUBJECT_PLAYER_ID,
        user_id=subject.id,
        url="https://www.youtube.com/watch?v=OwnLink0001",
        title="Subject owner-submitted reel",
        link_type="highlight",
        status="approved",
        sort_order=7,
    )
    curator_link = PlayerLink(
        player_id=SUBJECT_PLAYER_ID,
        user_id=player_counterpart.id,
        url="https://www.youtube.com/watch?v=Curated0001",
        title="Counterpart curated reel",
        link_type="highlight",
        status="approved",
        sort_order=9,
    )
    unrelated_link = PlayerLink(
        player_id=UNRELATED_PLAYER_API_ID,
        user_id=unrelated_player.id,
        url="https://www.youtube.com/watch?v=Unrelat0001",
        title="UNRELATED LINK SENTINEL",
        link_type="highlight",
        status="approved",
        sort_order=4,
    )
    provider_link = NewsletterPlayerYoutubeLink(
        newsletter_id=newsletter.id,
        player_id=SUBJECT_PLAYER_ID,
        player_name="Subject Player",
        youtube_link="https://www.youtube.com/watch?v=Provider001",
    )

    now = datetime.now(UTC).replace(tzinfo=None)
    sent_request = ContactRequest(
        id="00000000-0000-0000-0000-000000000001",
        scout_user_id=subject.id,
        player_api_id=COUNTERPART_PLAYER_ID,
        claim_id=counterpart_claim.id,
        message="subject sent contact request",
        status="accepted",
        routing_mode="direct",
        responded_at=now,
        expires_at=now + timedelta(days=7),
    )
    received_request = ContactRequest(
        id="00000000-0000-0000-0000-000000000002",
        scout_user_id=scout_counterpart.id,
        player_api_id=SUBJECT_PLAYER_ID,
        claim_id=subject_claim.id,
        message="counterpart sent contact request",
        status="accepted",
        routing_mode="direct",
        responded_at=now,
        expires_at=now + timedelta(days=7),
    )
    unrelated_request = ContactRequest(
        id="00000000-0000-0000-0000-000000000003",
        scout_user_id=unrelated_scout.id,
        player_api_id=UNRELATED_PLAYER_API_ID,
        claim_id=unrelated_claim.id,
        message="UNRELATED CONTACT REQUEST SENTINEL",
        status="accepted",
        routing_mode="direct",
        responded_at=now,
        expires_at=now + timedelta(days=7),
    )
    db.session.add_all([sent_request, received_request, unrelated_request])
    db.session.flush()

    messages = [
        ContactMessage(
            id="10000000-0000-0000-0000-000000000001",
            contact_request_id=sent_request.id,
            sender_user_id=subject.id,
            sender_role="scout",
            body="subject authored sent-thread message",
        ),
        ContactMessage(
            id="10000000-0000-0000-0000-000000000002",
            contact_request_id=sent_request.id,
            sender_user_id=player_counterpart.id,
            sender_role="player",
            body="counterpart reply remains visible",
        ),
        ContactMessage(
            id="10000000-0000-0000-0000-000000000003",
            contact_request_id=received_request.id,
            sender_user_id=scout_counterpart.id,
            sender_role="scout",
            body="counterpart opening message remains visible",
        ),
        ContactMessage(
            id="10000000-0000-0000-0000-000000000004",
            contact_request_id=received_request.id,
            sender_user_id=subject.id,
            sender_role="player",
            body="subject authored received-thread message",
        ),
        ContactMessage(
            id="10000000-0000-0000-0000-000000000005",
            contact_request_id=unrelated_request.id,
            sender_user_id=unrelated_scout.id,
            sender_role="scout",
            body="UNRELATED CONTACT MESSAGE SENTINEL",
        ),
    ]
    outcomes = [
        ContactOutcome(
            contact_request_id=sent_request.id,
            stage="contacted",
            reported_by_user_id=subject.id,
            notes="subject outcome on sent request",
            occurred_at=now,
        ),
        ContactOutcome(
            contact_request_id=received_request.id,
            stage="trial_scheduled",
            reported_by_user_id=subject.id,
            notes="subject outcome on received request",
            occurred_at=now,
        ),
        ContactOutcome(
            contact_request_id=unrelated_request.id,
            stage="no_fit",
            reported_by_user_id=unrelated_scout.id,
            notes="UNRELATED CONTACT OUTCOME SENTINEL",
            occurred_at=now,
        ),
    ]
    audit_events = [
        ContactAuditEvent(
            contact_request_id=sent_request.id,
            actor_user_id=subject.id,
            event_type="created",
            event_metadata={"source": "subject"},
        ),
        ContactAuditEvent(
            contact_request_id=sent_request.id,
            actor_user_id=player_counterpart.id,
            event_type="accepted",
            event_metadata={"source": "counterpart"},
        ),
        ContactAuditEvent(
            contact_request_id=received_request.id,
            actor_user_id=subject.id,
            event_type="message_sent",
            event_metadata={"source": "subject"},
        ),
        ContactAuditEvent(
            contact_request_id=unrelated_request.id,
            actor_user_id=unrelated_scout.id,
            event_type="created",
            event_metadata={"sentinel": "UNRELATED AUDIT SENTINEL"},
        ),
    ]

    subject_report = ContentReport(
        reporter_user_id=subject.id,
        subject_type="showcase_content",
        subject_id=str(SUBJECT_PLAYER_ID),
        reason_code="misleading_information",
        details="subject private content report",
        status="open",
    )
    unrelated_report = ContentReport(
        reporter_user_id=unrelated_scout.id,
        subject_type="player_profile",
        subject_id=str(UNRELATED_PLAYER_API_ID),
        reason_code="other",
        details="UNRELATED REPORT SENTINEL",
        status="open",
    )
    subject_community_take = CommunityTake(
        source_type="submission",
        source_author="Delete Me",
        content="retained approved community contribution",
        player_id=SUBJECT_PLAYER_ID,
        player_name="Subject Player",
        status="approved",
    )
    db.session.add(subject_community_take)
    db.session.flush()
    subject_quick_take = QuickTakeSubmission(
        submitter_name="Delete Me",
        submitter_email=subject.email,
        player_id=SUBJECT_PLAYER_ID,
        player_name="Subject Player",
        content="retained approved community contribution",
        status="approved",
        community_take_id=subject_community_take.id,
        ip_hash="subject-private-ip-hash",
        user_agent="subject-private-user-agent",
    )

    db.session.add_all(
        [
            subject_subscription,
            unrelated_subscription,
            subject_email_token,
            subject_connected_account,
            subject_subscription_plan,
            subject_stripe_subscription,
            subject_watchlist,
            unrelated_watchlist,
            subject_follow,
            unrelated_follow,
            subject_snapshot,
            subject_verification,
            unrelated_verification,
            subject_profile,
            unrelated_profile,
            owner_link,
            curator_link,
            unrelated_link,
            provider_link,
            *messages,
            *outcomes,
            *audit_events,
            subject_report,
            unrelated_report,
            subject_quick_take,
        ]
    )
    db.session.commit()

    return {
        "subject_email": subject.email,
        "subject_id": subject.id,
        "subject_claim_id": subject_claim.id,
        "subject_profile_id": subject_profile.id,
        "subject_link_id": owner_link.id,
        "subject_connected_account_id": subject_connected_account.id,
        "subject_subscription_plan_id": subject_subscription_plan.id,
        "subject_stripe_subscription_id": subject_stripe_subscription.id,
        "curator_link_id": curator_link.id,
        "provider_link_id": provider_link.id,
        "sent_request_id": sent_request.id,
        "received_request_id": received_request.id,
        "unrelated_request_id": unrelated_request.id,
        "subject_report_id": subject_report.id,
        "unrelated_report_id": unrelated_report.id,
        "subject_community_take_id": subject_community_take.id,
        "subject_quick_take_id": subject_quick_take.id,
        "subject_message_ids": [messages[0].id, messages[3].id],
        "counterpart_message_ids": [messages[1].id, messages[2].id],
        "subject_outcome_ids": [outcomes[0].id, outcomes[1].id],
        "subject_audit_ids": [audit_events[0].id, audit_events[2].id],
    }


def test_export_is_complete_safe_and_scoped_to_the_authenticated_user(client):
    seeded = _seed_full_account_graph()

    response = client.get("/api/account/export", headers=_headers(seeded["subject_email"]))

    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    required_keys = {
        "account",
        "scout_verifications",
        "watchlist_entries",
        "follow_lists",
        "showcase_claims",
        "showcase_profiles",
        "submitted_links",
        "contact_requests",
        "content_reports",
        "email_subscriptions",
    }
    assert required_keys <= payload.keys()
    assert payload["account"]["email"] == seeded["subject_email"]
    assert payload["account"]["scout_tier"] == "free"
    assert payload["account"]["scout_digest_opt_in"] is True
    assert len(payload["scout_verifications"]) == 1
    assert payload["scout_verifications"][0]["full_name"] == "Subject Scout"
    assert len(payload["watchlist_entries"]) == 1
    assert payload["watchlist_entries"][0]["note"] == "subject private watchlist note"

    assert len(payload["follow_lists"]) == 1
    exported_list = payload["follow_lists"][0]
    assert exported_list["name"] == "Subject private prospects"
    assert len(exported_list["follows"]) == 1
    assert exported_list["follows"][0]["note"] == "subject follow note"

    assert len(payload["showcase_claims"]) == 1
    assert payload["showcase_claims"][0]["player_api_id"] == SUBJECT_PLAYER_ID
    assert len(payload["showcase_profiles"]) == 1
    assert payload["showcase_profiles"][0]["bio"] == "subject self-reported biography"
    assert payload["showcase_profiles"][0]["pending_contract"]["claim_id"] == seeded["subject_claim_id"]
    assert payload["showcase_profiles"][0]["pending_contract"]["current_club_name"] == "Subject pending club"
    assert len(payload["submitted_links"]) == 1
    assert payload["submitted_links"][0]["title"] == "Subject owner-submitted reel"

    contact_requests = payload["contact_requests"]
    assert len(contact_requests["sent"]) == 1
    assert len(contact_requests["received"]) == 1
    assert contact_requests["club"] == []
    assert contact_requests["sent"][0]["id"] == seeded["sent_request_id"]
    assert contact_requests["received"][0]["id"] == seeded["received_request_id"]
    assert len(contact_requests["sent"][0]["messages"]) == 2
    assert len(contact_requests["received"][0]["messages"]) == 2
    assert len(contact_requests["sent"][0]["outcomes"]) == 1
    assert len(contact_requests["received"][0]["outcomes"]) == 1
    assert contact_requests["sent"][0]["participants"]["player"]["display_name"] == "Player Counterpart"
    assert contact_requests["received"][0]["participants"]["scout"]["display_name"] == "Scout Counterpart"

    assert len(payload["content_reports"]) == 1
    assert payload["content_reports"][0]["details"] == "subject private content report"
    subscriptions = payload["email_subscriptions"]
    assert subscriptions["delivery_preference"] == "individual"
    assert subscriptions["scout_digest_opt_in"] is True
    assert len(subscriptions["team_subscriptions"]) == 1
    assert subscriptions["team_subscriptions"][0]["preferred_frequency"] == "daily"

    all_keys = set(_all_keys(payload))
    assert "unsubscribe_token" not in all_keys
    assert "reporter_user_id" not in all_keys
    assert "scout_user_id" not in all_keys
    assert "sender_user_id" not in all_keys
    assert "reported_by_user_id" not in all_keys
    assert {claim["user_account_id"] for claim in payload["showcase_claims"]} == {seeded["subject_id"]}

    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "player-counterpart@example.com",
        "scout-counterpart@example.com",
        "unrelated-scout@example.com",
        "unrelated-player@example.com",
        str(PLAYER_COUNTERPART_ID),
        str(SCOUT_COUNTERPART_ID),
        str(UNRELATED_SCOUT_ID),
        str(UNRELATED_PLAYER_ID),
        "UNRELATED WATCHLIST SENTINEL",
        "UNRELATED FOLLOW LIST SENTINEL",
        "UNRELATED VERIFICATION SENTINEL",
        "UNRELATED CLAIM SENTINEL",
        "UNRELATED PROFILE SENTINEL",
        "UNRELATED LINK SENTINEL",
        "UNRELATED CONTACT REQUEST SENTINEL",
        "UNRELATED CONTACT MESSAGE SENTINEL",
        "UNRELATED CONTACT OUTCOME SENTINEL",
        "UNRELATED REPORT SENTINEL",
        "subject-secret-unsubscribe-token",
        "unrelated-secret-unsubscribe-token",
    ):
        assert forbidden not in serialized


def test_export_matches_live_contact_authorization(client, monkeypatch):
    import src.services.account as account_service

    subject = _add_account(96101, "participant@example.com", "Participant")
    scout = _add_account(96102, "participant-scout@example.com", "Participant Scout")
    other_player = _add_account(96103, "other-player@example.com", "Other Player")
    unrelated_scout = _add_account(96104, "unrelated-thread@example.com", "Unrelated Thread Scout")
    historical_claim = PlayerProfileClaim(
        player_api_id=7101,
        user_account_id=subject.id,
        relationship_type="player",
        status="revoked",
        contract_status="unknown",
    )
    other_claim = PlayerProfileClaim(
        player_api_id=7102,
        user_account_id=other_player.id,
        relationship_type="player",
        status="approved",
        contract_status="unknown",
    )
    db.session.add_all([historical_claim, other_claim])
    db.session.flush()
    now = datetime.now(UTC).replace(tzinfo=None)
    historical_request = ContactRequest(
        scout_user_id=scout.id,
        player_api_id=7101,
        claim_id=historical_claim.id,
        message="historical request",
        status="accepted",
        routing_mode="direct",
        expires_at=now + timedelta(days=7),
    )
    participated_request = ContactRequest(
        scout_user_id=scout.id,
        player_api_id=7102,
        claim_id=other_claim.id,
        message="club-participated request",
        status="accepted",
        routing_mode="club_included",
        club_program_id=44,
        club_consent_status="granted",
        expires_at=now + timedelta(days=7),
    )
    unrelated_request = ContactRequest(
        scout_user_id=unrelated_scout.id,
        player_api_id=7102,
        claim_id=other_claim.id,
        message="UNRELATED PARTICIPANT THREAD SENTINEL",
        status="declined",
        routing_mode="direct",
        expires_at=now + timedelta(days=7),
    )
    db.session.add_all([historical_request, participated_request, unrelated_request])
    db.session.flush()
    db.session.add(
        ContactMessage(
            contact_request_id=participated_request.id,
            sender_user_id=subject.id,
            sender_role="club",
            body="subject club message",
        )
    )
    db.session.commit()
    monkeypatch.setattr(account_service, "active_manager_program_ids", lambda user_id: [44])

    response = client.get("/api/account/export", headers=_headers(subject.email))

    assert response.status_code == 200, response.get_json()
    exported = response.get_json()["contact_requests"]
    assert exported["sent"] == []
    assert exported["received"] == []
    assert [row["id"] for row in exported["club"]] == [participated_request.id]
    assert exported["club"][0]["messages"][0]["body"] == "subject club message"
    assert historical_request.id not in json.dumps(exported)
    assert "UNRELATED PARTICIPANT THREAD SENTINEL" not in json.dumps(exported)


def test_delete_preserves_coowner_profile_and_reel_order(client):
    subject = _add_account(96201, "departing-coowner@example.com", "Departing Coowner")
    coowner = _add_account(96202, "remaining-coowner@example.com", "Remaining Coowner")
    player_id = 7201
    departing_claim = PlayerProfileClaim(
        id=87201,
        player_api_id=player_id,
        user_account_id=subject.id,
        relationship_type="agent",
        status="approved",
        contract_status="unknown",
    )
    remaining_claim = PlayerProfileClaim(
        id=87202,
        player_api_id=player_id,
        user_account_id=coowner.id,
        relationship_type="player",
        status="approved",
        contract_status="unknown",
    )
    profile = PlayerShowcaseProfile(
        player_api_id=player_id,
        bio="remaining owner's self-reported profile",
        status="approved",
        updated_by_user_id=coowner.id,
        pending_contract_claim_id=remaining_claim.id,
        pending_contract_status="contracted",
        pending_current_club_name="OTHER OWNER PRIVATE PENDING CLUB",
    )
    departing_link = PlayerLink(
        player_id=player_id,
        user_id=subject.id,
        url="https://www.youtube.com/watch?v=Departing01",
        title="departing owner link",
        link_type="highlight",
        status="approved",
        sort_order=7,
    )
    remaining_link = PlayerLink(
        player_id=player_id,
        user_id=coowner.id,
        url="https://www.youtube.com/watch?v=Remaining01",
        title="remaining owner link",
        link_type="highlight",
        status="approved",
        sort_order=9,
    )
    db.session.add_all([departing_claim, remaining_claim, profile, departing_link, remaining_link])
    db.session.commit()
    departing_claim_id = departing_claim.id
    remaining_claim_id = remaining_claim.id
    profile_id = profile.id
    departing_link_id = departing_link.id
    remaining_link_id = remaining_link.id
    headers = _headers(subject.email)

    exported = client.get("/api/account/export", headers=headers)
    assert exported.status_code == 200, exported.get_json()
    exported_json = exported.get_json()
    assert exported_json["showcase_profiles"][0]["pending_contract"] is None
    assert "OTHER OWNER PRIVATE PENDING CLUB" not in json.dumps(exported_json)

    response = client.post(
        "/api/account/delete",
        json={"confirm": "DELETE"},
        headers=headers,
    )

    assert response.status_code == 200, response.get_json()
    event = AccountDeletionEvent.query.one()
    assert event.counts["reset"]["reel_items"] == 0
    assert PlayerProfileClaim.query.filter_by(id=departing_claim_id).one_or_none() is None
    assert PlayerProfileClaim.query.filter_by(id=remaining_claim_id).one_or_none() is not None
    assert PlayerShowcaseProfile.query.filter_by(id=profile_id).one_or_none() is not None
    assert PlayerLink.query.filter_by(id=departing_link_id).one_or_none() is None
    assert PlayerLink.query.filter_by(id=remaining_link_id).one().sort_order == 9


def test_delete_preserves_and_anonymizes_funding_admin_audit(client):
    user = _add_account(96301, "funding-actor@example.com", "Funding Actor")
    db.session.execute(
        sa.text(
            "CREATE TABLE funding_admin_events ("
            "id INTEGER PRIMARY KEY, actor_email VARCHAR(254) NOT NULL, "
            "action VARCHAR(80) NOT NULL, target_type VARCHAR(40) NOT NULL, "
            "target_id INTEGER NOT NULL, reason TEXT NOT NULL, event_metadata JSON NOT NULL)"
        )
    )
    db.session.execute(
        sa.text(
            "INSERT INTO funding_admin_events "
            "(id, actor_email, action, target_type, target_id, reason, event_metadata) VALUES "
            "(1, :email, 'reviewed', 'claim', 4, 'retained audit', '{}'), "
            "(2, 'other-admin@example.com', 'reviewed', 'claim', 5, 'other audit', '{}')"
        ),
        {"email": user.email},
    )
    db.session.commit()

    response = client.post(
        "/api/account/delete",
        json={"confirm": "DELETE"},
        headers=_headers(user.email),
    )

    assert response.status_code == 200, response.get_json()
    event = AccountDeletionEvent.query.one()
    assert event.counts["anonymized"]["funding_admin_events"] == 1
    rows = db.session.execute(
        sa.text("SELECT id, actor_email, reason FROM funding_admin_events ORDER BY id")
    ).mappings()
    assert [dict(row) for row in rows] == [
        {"id": 1, "actor_email": "Account deleted", "reason": "retained audit"},
        {"id": 2, "actor_email": "other-admin@example.com", "reason": "other audit"},
    ]


def test_export_is_limited_to_three_per_hour_per_authenticated_user(client):
    first = _add_account(96006, "rate-one@example.com", "Rate One")
    second = _add_account(97007, "rate-two@example.com", "Rate Two")
    db.session.commit()

    first_headers = _headers(first.email)
    for _ in range(3):
        response = client.get("/api/account/export", headers=first_headers)
        assert response.status_code == 200, response.get_json()

    limited = client.get("/api/account/export", headers=first_headers)
    assert limited.status_code == 429

    independent = client.get("/api/account/export", headers=_headers(second.email))
    assert independent.status_code == 200, independent.get_json()


def test_delete_requires_exact_confirmation_and_preserves_account_on_error(client):
    user = _add_account(98008, "confirm-required@example.com", "Confirm Required")
    db.session.commit()
    headers = _headers(user.email)

    assert client.post("/api/account/delete", json={}, headers=headers).status_code == 400
    assert (
        client.post(
            "/api/account/delete",
            json={"confirm": "delete"},
            headers=headers,
        ).status_code
        == 400
    )
    assert UserAccount.query.filter_by(id=user.id).one_or_none() is not None
    assert AccountDeletionEvent.query.count() == 0


def test_delete_rolls_back_every_effect_when_a_late_step_fails(client, monkeypatch):
    import src.services.account as account_service

    user = _add_account(98108, "rollback@example.com", "Rollback User")
    watchlist = ScoutWatchlistEntry(
        user_account_id=user.id,
        player_api_id=7301,
        note="must survive rollback",
    )
    db.session.add(watchlist)
    db.session.commit()
    user_id = user.id
    watchlist_id = watchlist.id
    headers = _headers(user.email)

    def _fail_late(*_args, **_kwargs):
        raise RuntimeError("forced late deletion failure")

    monkeypatch.setattr(account_service, "_repoint_anonymized_user_foreign_keys", _fail_late)

    response = client.post(
        "/api/account/delete",
        json={"confirm": "DELETE"},
        headers=headers,
    )

    assert response.status_code == 500
    db.session.expire_all()
    assert UserAccount.query.filter_by(id=user_id, is_tombstone=False).one_or_none() is not None
    assert ScoutWatchlistEntry.query.filter_by(id=watchlist_id).one_or_none() is not None
    assert UserAccount.query.filter_by(is_tombstone=True).count() == 0
    assert AccountDeletionEvent.query.count() == 0


def test_delete_erases_owned_data_and_tombstones_shared_integrity(client):
    seeded = _seed_full_account_graph()
    headers = _headers(seeded["subject_email"])

    response = client.post(
        "/api/account/delete",
        json={"confirm": "DELETE"},
        headers=headers,
    )

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["deleted"] is True
    db.session.expire_all()

    assert UserAccount.query.filter_by(id=seeded["subject_id"]).one_or_none() is None
    event = AccountDeletionEvent.query.one()
    assert event.requested_at is not None
    assert event.completed_at is not None
    tombstone = UserAccount.query.filter_by(id=event.tombstone_user_id).one()
    assert tombstone.is_tombstone is True
    assert tombstone.display_name == "Account deleted"
    assert tombstone.email is None

    deleted = event.counts["deleted"]
    assert deleted["watchlist_entries"] == 1
    assert deleted["follow_lists"] == 1
    assert deleted["follows"] == 1
    assert deleted["follow_player_snapshots"] == 1
    assert deleted["scout_verifications"] == 1
    assert deleted["email_subscriptions"] == 1
    assert deleted["email_tokens"] == 1
    assert deleted["showcase_claims"] == 1
    assert deleted["showcase_profiles"] == 1
    assert deleted["submitted_links"] == 1
    assert deleted["stripe_connected_accounts"] == 1
    assert deleted["stripe_subscription_plans"] == 1
    assert deleted["stripe_subscriptions"] == 1
    anonymized = event.counts["anonymized"]
    assert anonymized["contact_requests"] == 2
    assert anonymized["contact_messages"] == 2
    assert anonymized["contact_outcomes"] == 2
    assert anonymized["contact_audit_events"] == 2
    assert anonymized["content_reports"] == 1
    assert anonymized["email_keyed_rows"] == 2
    assert event.counts["reset"]["reel_items"] == 1

    assert ScoutWatchlistEntry.query.filter_by(user_account_id=seeded["subject_id"]).count() == 0
    assert FollowList.query.filter_by(user_account_id=seeded["subject_id"]).count() == 0
    assert FollowPlayerSnapshot.query.filter_by(user_account_id=seeded["subject_id"]).count() == 0
    assert ScoutVerification.query.filter_by(user_account_id=seeded["subject_id"]).count() == 0
    assert UserSubscription.query.filter_by(email=seeded["subject_email"]).count() == 0
    assert EmailToken.query.filter_by(email=seeded["subject_email"]).count() == 0
    assert PlayerProfileClaim.query.filter_by(id=seeded["subject_claim_id"]).one_or_none() is None
    assert PlayerShowcaseProfile.query.filter_by(id=seeded["subject_profile_id"]).one_or_none() is None
    assert PlayerLink.query.filter_by(id=seeded["subject_link_id"]).one_or_none() is None
    assert StripeConnectedAccount.query.filter_by(id=seeded["subject_connected_account_id"]).one_or_none() is None
    assert StripeSubscriptionPlan.query.filter_by(id=seeded["subject_subscription_plan_id"]).one_or_none() is None
    assert StripeSubscription.query.filter_by(id=seeded["subject_stripe_subscription_id"]).one_or_none() is None

    curator_link = PlayerLink.query.filter_by(id=seeded["curator_link_id"]).one()
    assert curator_link.sort_order == 0
    assert NewsletterPlayerYoutubeLink.query.filter_by(id=seeded["provider_link_id"]).one_or_none() is not None
    assert PlayerProfileClaim.query.filter_by(player_api_id=UNRELATED_PLAYER_API_ID).count() == 1
    assert PlayerShowcaseProfile.query.filter_by(player_api_id=UNRELATED_PLAYER_API_ID).count() == 1
    assert UserSubscription.query.filter_by(email="unrelated-scout@example.com").count() == 1

    sent_request = ContactRequest.query.filter_by(id=seeded["sent_request_id"]).one()
    received_request = ContactRequest.query.filter_by(id=seeded["received_request_id"]).one()
    unrelated_request = ContactRequest.query.filter_by(id=seeded["unrelated_request_id"]).one()
    assert sent_request.scout_user_id == tombstone.id
    assert sent_request.status == "accepted"
    assert received_request.claim_id is None
    assert received_request.status == "accepted"
    assert received_request.to_dict()["participants"]["player"]["display_name"] == "Account deleted"
    assert unrelated_request.scout_user_id == UNRELATED_SCOUT_ID

    for message_id in seeded["subject_message_ids"]:
        message = ContactMessage.query.filter_by(id=message_id).one()
        assert message.sender_user_id == tombstone.id
        assert message.to_dict()["sender_display_name"] == "Account deleted"
    for message_id in seeded["counterpart_message_ids"]:
        assert ContactMessage.query.filter_by(id=message_id).one().sender_user_id != tombstone.id
    for outcome_id in seeded["subject_outcome_ids"]:
        assert ContactOutcome.query.filter_by(id=outcome_id).one().reported_by_user_id == tombstone.id
    for audit_id in seeded["subject_audit_ids"]:
        assert ContactAuditEvent.query.filter_by(id=audit_id).one().actor_user_id == tombstone.id

    report = ContentReport.query.filter_by(id=seeded["subject_report_id"]).one()
    assert report.reporter_user_id == tombstone.id
    assert report.details == "subject private content report"
    unrelated_report = ContentReport.query.filter_by(id=seeded["unrelated_report_id"]).one()
    assert unrelated_report.reporter_user_id == UNRELATED_SCOUT_ID
    community_take = CommunityTake.query.filter_by(id=seeded["subject_community_take_id"]).one()
    quick_take = QuickTakeSubmission.query.filter_by(id=seeded["subject_quick_take_id"]).one()
    assert community_take.source_author == "Account deleted"
    assert quick_take.submitter_name == "Account deleted"
    assert quick_take.submitter_email is None
    assert quick_take.ip_hash is None
    assert quick_take.user_agent is None

    public = client.get(f"/api/players/{SUBJECT_PLAYER_ID}/showcase")
    assert public.status_code == 200, public.get_json()
    public_payload = public.get_json()
    assert public_payload["claim_status"] == "unclaimed"
    assert public_payload["profile"] is None
    reel_by_url = {item["url"]: item for item in public_payload["reel"]}
    assert "https://www.youtube.com/watch?v=OwnLink0001" not in reel_by_url
    assert reel_by_url["https://www.youtube.com/watch?v=Curated0001"]["sort_order"] == 0
    assert reel_by_url["https://www.youtube.com/watch?v=Provider001"]["source"] == "newsletter"

    assert client.get("/api/account/export", headers=headers).status_code == 401
    repeated = client.post(
        "/api/account/delete",
        json={"confirm": "DELETE"},
        headers=headers,
    )
    assert repeated.status_code == 401
    assert AccountDeletionEvent.query.count() == 1


def test_tf01_is_guarded_chains_fc03_and_documents_gf01_ordering():
    migration = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "tf01_account_deletion.py"
    source = migration.read_text()

    assert 'revision = "tf01"' in source
    assert 'down_revision = "fc03"' in source
    assert "PR #636" in source
    assert "gf01" in source
    assert '"account_deletion_events"' in source
    assert '"is_tombstone"' in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "table_exists" in source
    assert "column_exists" in source
    assert "index_exists" in source


def test_live_app_registers_account_routes_and_boilerplate_user_rail_is_gone():
    backend_root = Path(__file__).resolve().parents[1]
    main_source = (backend_root / "src" / "main.py").read_text()

    assert "from src.routes.account import account_bp" in main_source
    assert 'app.register_blueprint(account_bp, url_prefix="/api")' in main_source
    assert not (backend_root / "src" / "routes" / "user.py").exists()
    assert not (backend_root / "src" / "models" / "user.py").exists()
