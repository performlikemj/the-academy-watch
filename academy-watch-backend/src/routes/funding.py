"""Grassroots league registry, club admission, verification, and program pages."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from src.auth import _ensure_user_account, _safe_error_payload, require_api_key, require_user_auth
from src.extensions import limiter
from src.models.follow import Follow, FollowList
from src.models.funding import (
    ClubClaimEvidence,
    ClubConnectAccount,
    ClubProgram,
    ClubProgramClaim,
    ClubProgramManager,
    ClubProgramProfileRevision,
    FundingAdminEvent,
    FundingLeague,
)
from src.models.league import League, TeamProfile, UserAccount, db
from src.services.stripe_connect import (
    StripeConnectConfigurationError,
    create_express_organization_onboarding,
    retrieve_test_express_account,
    test_connect_configured,
)
from src.utils.sanitize import is_safe_https_url, sanitize_plain_text

logger = logging.getLogger(__name__)
funding_bp = Blueprint("funding", __name__)

LEVELS = {"pro_academy", "youth_national", "youth_regional", "recreational"}
GENDER_PROGRAMS = {"boys", "girls", "both"}
SEASON_CALENDARS = {"aug_may", "calendar_year", "fall_spring"}
DATA_TIERS = {"api_football", "film_room", "self_reported"}
REGISTRY_STATUSES = {"proposed", "approved", "rejected"}
ADMISSION_STATES = {"open", "waitlisted", "closed"}
CLAIM_STATUSES = {"pending", "approved", "rejected", "revoked"}
ORGANIZATION_FORMS = {"nonprofit", "company", "association", "school", "municipal", "other_organization"}
AUTHORIZATION_METHODS = {"official_domain_email", "signed_officer_authorization"}
MAX_PAGE = 200


def _clean(value, field, *, required=True, max_len=240):
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    cleaned = sanitize_plain_text(value).strip()
    if not cleaned:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if len(cleaned) > max_len:
        raise ValueError(f"{field} must be at most {max_len} characters")
    return cleaned


def _enum(value, field, allowed):
    cleaned = _clean(value, field, max_len=40).lower()
    if cleaned not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}")
    return cleaned


def _bool(value, field, *, must_be_true=False):
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    if must_be_true and not value:
        raise ValueError(f"{field} must be accepted")
    return value


def _https(value, field, *, required=False):
    cleaned = _clean(value, field, required=required, max_len=500)
    if cleaned and not is_safe_https_url(cleaned):
        raise ValueError(f"{field} must be an absolute https URL")
    return cleaned


def _slug(value):
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized[:180] or "program"


def _is_us(country):
    return (country or "").strip().upper() in {"US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"}


def _same_country(first, second):
    if _is_us(first) and _is_us(second):
        return True
    return (first or "").strip().casefold() == (second or "").strip().casefold()


def _current_user_account():
    user = getattr(g, "user", None)
    if user is not None:
        return user
    email = getattr(g, "user_email", None)
    if not email:
        return None
    user = UserAccount.query.filter_by(email=email).first()
    if user is None:
        user = _ensure_user_account(email)
        db.session.flush()
    return user


def _rate_limit_key():
    return getattr(g, "user_email", None) or request.remote_addr or "anon"


def _audit(action, target_type, target_id, reason, metadata=None):
    reason = _clean(reason, "reason", max_len=2000)
    event = FundingAdminEvent(
        actor_email=getattr(g, "user_email", None) or "system",
        action=action,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        event_metadata=metadata or {},
    )
    db.session.add(event)
    return event


def _parse_age_bands(value):
    if not isinstance(value, list) or not value:
        raise ValueError("age_bands must be a non-empty list")
    if len(value) > 20:
        raise ValueError("age_bands must contain at most 20 values")
    out = []
    for item in value:
        cleaned = _clean(item, "age_bands item", max_len=30)
        if cleaned not in out:
            out.append(cleaned)
    return out


def _parse_data_tier(payload):
    raw = _clean(payload.get("data_tier"), "data_tier", max_len=60).lower()
    league_api_id = payload.get("league_api_id")
    if raw.startswith("api_football:"):
        raw_id = raw.split(":", 1)[1]
        try:
            league_api_id = int(raw_id)
        except ValueError as exc:
            raise ValueError("api_football data tier requires a positive league_api_id") from exc
        raw = "api_football"
    if raw not in DATA_TIERS:
        raise ValueError("data_tier must be api_football:<league_api_id>, film_room, or self_reported")
    if raw == "api_football":
        if isinstance(league_api_id, bool):
            raise ValueError("league_api_id must be a positive integer")
        try:
            league_api_id = int(league_api_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("api_football data tier requires a positive league_api_id") from exc
        if league_api_id <= 0:
            raise ValueError("league_api_id must be a positive integer")
    else:
        league_api_id = None
    return raw, league_api_id


def _league_values(payload, *, proposal=False):
    data_tier, league_api_id = _parse_data_tier(payload)
    existing = League.query.filter_by(league_id=league_api_id).first() if league_api_id else None
    name = _clean(payload.get("name"), "name", max_len=160)
    country = _clean(payload.get("country"), "country", max_len=80)
    if existing is not None:
        # Provider-covered identity is bridged, never copied into a second
        # provider record or silently edited by registry users.
        name = existing.name
        country = existing.country
    return {
        "name": name,
        "country": country,
        "region": _clean(payload.get("region"), "region", max_len=120),
        "level": _enum(payload.get("level"), "level", LEVELS),
        "age_bands": _parse_age_bands(payload.get("age_bands")),
        "gender_program": _enum(payload.get("gender_program"), "gender_program", GENDER_PROGRAMS),
        "season_calendar": _enum(payload.get("season_calendar"), "season_calendar", SEASON_CALENDARS),
        "data_tier": data_tier,
        "league_api_id": league_api_id,
        "existing_league_id": existing.id if existing else None,
        "registry_status": "proposed"
        if proposal
        else _enum(payload.get("registry_status", "approved"), "registry_status", REGISTRY_STATUSES),
        "admission_state": "waitlisted"
        if proposal
        else _enum(payload.get("admission_state", "waitlisted"), "admission_state", ADMISSION_STATES),
    }


def _league_duplicate(values):
    if values.get("league_api_id"):
        row = FundingLeague.query.filter_by(league_api_id=values["league_api_id"]).first()
        if row:
            return row
    return FundingLeague.query.filter(
        func.lower(FundingLeague.name) == values["name"].lower(),
        func.lower(FundingLeague.country) == values["country"].lower(),
        func.lower(FundingLeague.region) == values["region"].lower(),
    ).first()


def _evidence_values(payload):
    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        raise ValueError("evidence is required")
    authorization_method = _enum(evidence.get("authorization_method"), "authorization_method", AUTHORIZATION_METHODS)
    official_email = _clean(evidence.get("official_email"), "official_email", required=False, max_len=254)
    authorization_reference = _clean(
        evidence.get("authorization_reference"), "authorization_reference", required=False, max_len=500
    )
    if authorization_method == "official_domain_email" and not official_email:
        raise ValueError("official_email is required for official-domain authorization")
    if authorization_method == "signed_officer_authorization" and not authorization_reference:
        raise ValueError("authorization_reference is required for signed officer authorization")
    if official_email and ("@" not in official_email or official_email.startswith("@") or official_email.endswith("@")):
        raise ValueError("official_email must be a valid email address")
    safeguarding_email = _clean(evidence.get("safeguarding_contact_email"), "safeguarding_contact_email", max_len=254)
    if "@" not in safeguarding_email:
        raise ValueError("safeguarding_contact_email must be a valid email address")
    return {
        "adult_authority_attested": _bool(
            evidence.get("adult_authority_attested"), "adult_authority_attested", must_be_true=True
        ),
        "official_email": official_email,
        "authorization_method": authorization_method,
        "authorization_reference": authorization_reference,
        "organization_form": _enum(evidence.get("organization_form"), "organization_form", ORGANIZATION_FORMS),
        "registration_reference": _clean(evidence.get("registration_reference"), "registration_reference", max_len=240),
        "official_contact_name": _clean(evidence.get("official_contact_name"), "official_contact_name", max_len=160),
        "official_contact_reference": _clean(
            evidence.get("official_contact_reference"), "official_contact_reference", max_len=500
        ),
        "safeguarding_contact_email": safeguarding_email,
        "safeguarding_policy_url": _https(evidence.get("safeguarding_policy_url"), "safeguarding_policy_url"),
        "safeguarding_policy_attested": _bool(
            evidence.get("safeguarding_policy_attested"), "safeguarding_policy_attested", must_be_true=True
        ),
        "eligible_organization_attested": _bool(
            evidence.get("eligible_organization_attested"), "eligible_organization_attested", must_be_true=True
        ),
        "payout_control_attested": _bool(
            evidence.get("payout_control_attested"), "payout_control_attested", must_be_true=True
        ),
        "evidence_notes": _clean(evidence.get("evidence_notes"), "evidence_notes", required=False, max_len=2000),
        "retention_expires_at": datetime.now(UTC) + timedelta(days=365),
    }


def _evidence_dict(evidence):
    if evidence is None:
        return None
    return {
        "adult_authority_attested": evidence.adult_authority_attested,
        "official_email": evidence.official_email,
        "authorization_method": evidence.authorization_method,
        "authorization_reference": evidence.authorization_reference,
        "organization_form": evidence.organization_form,
        "registration_reference": evidence.registration_reference,
        "official_contact_name": evidence.official_contact_name,
        "official_contact_reference": evidence.official_contact_reference,
        "safeguarding_contact_email": evidence.safeguarding_contact_email,
        "safeguarding_policy_url": evidence.safeguarding_policy_url,
        "safeguarding_policy_attested": evidence.safeguarding_policy_attested,
        "eligible_organization_attested": evidence.eligible_organization_attested,
        "payout_control_attested": evidence.payout_control_attested,
        "evidence_notes": evidence.evidence_notes,
        "retention_expires_at": evidence.retention_expires_at.isoformat() if evidence.retention_expires_at else None,
    }


def _evidence_meets_bar(evidence):
    if evidence is None:
        return False
    authorization_present = bool(
        (evidence.authorization_method == "official_domain_email" and evidence.official_email)
        or (evidence.authorization_method == "signed_officer_authorization" and evidence.authorization_reference)
    )
    return bool(
        evidence.adult_authority_attested
        and authorization_present
        and evidence.organization_form
        and evidence.registration_reference
        and evidence.official_contact_name
        and evidence.official_contact_reference
        and evidence.safeguarding_contact_email
        and evidence.safeguarding_policy_attested
        and evidence.eligible_organization_attested
        and evidence.payout_control_attested
    )


def _connect_dict(account):
    if account is None:
        return None
    return {
        "stripe_account_id": account.stripe_account_id,
        "account_type": account.account_type,
        "country": account.country,
        "business_type": account.business_type,
        "livemode": account.livemode,
        "transfers_active": account.transfers_active,
        "details_submitted": account.details_submitted,
        "payouts_enabled": account.payouts_enabled,
        "charges_enabled": account.charges_enabled,
        "requirements_due": account.requirements_due or [],
        "disabled_reason": account.disabled_reason,
        "onboarding_url": account.onboarding_url,
        "onboarding_expires_at": account.onboarding_expires_at.isoformat() if account.onboarding_expires_at else None,
        "is_ready": account.is_ready,
    }


def _refresh_program_verification(program, *, now=None):
    """Recompute the badge timestamp from current approval/grant/Connect rows."""
    db.session.flush()
    db.session.expire(program, ["managers", "connect_accounts"])
    verified = program.is_verified_program
    if verified:
        program.verified_at = program.verified_at or now or datetime.now(UTC)
    else:
        program.verified_at = None
    return verified


def _claim_dict(claim, *, admin=False):
    program = claim.program
    payload = {
        "id": claim.id,
        "status": claim.status,
        "relationship_type": claim.relationship_type,
        "applicant_message": claim.applicant_message,
        "review_reason": claim.review_reason,
        "reviewed_at": claim.reviewed_at.isoformat() if claim.reviewed_at else None,
        "created_at": claim.created_at.isoformat() if claim.created_at else None,
        "program": {
            **program.public_dict(),
            "platform_status": program.platform_status,
            "legal_name": program.legal_name if admin else None,
        },
    }
    if admin:
        payload.update(
            {
                "applicant_email": claim.user.email if claim.user else None,
                "evidence": _evidence_dict(claim.evidence),
                "connect": _connect_dict(program.connect_account),
                "audit_trail": [
                    {
                        "action": event.action,
                        "reason": event.reason,
                        "actor_email": event.actor_email,
                        "created_at": event.created_at.isoformat() if event.created_at else None,
                    }
                    for event in FundingAdminEvent.query.filter_by(target_type="claim", target_id=claim.id)
                    .order_by(FundingAdminEvent.created_at.asc(), FundingAdminEvent.id.asc())
                    .all()
                ],
            }
        )
    return payload


@funding_bp.route("/funding/leagues", methods=["GET"])
def public_funding_leagues():
    query = FundingLeague.query.filter_by(registry_status="approved", admission_state="open")
    country = _clean(request.args.get("country"), "country", required=False, max_len=80)
    if country:
        query = query.filter(func.lower(FundingLeague.country) == country.lower())
    rows = query.order_by(FundingLeague.country, FundingLeague.region, FundingLeague.name).limit(MAX_PAGE).all()
    return jsonify({"leagues": [row.to_dict() for row in rows]})


@funding_bp.route("/admin/funding/leagues", methods=["GET"])
@require_api_key
def admin_funding_leagues():
    query = FundingLeague.query
    for arg, column, allowed in (
        ("admission_state", FundingLeague.admission_state, ADMISSION_STATES),
        ("registry_status", FundingLeague.registry_status, REGISTRY_STATUSES),
        ("level", FundingLeague.level, LEVELS),
        ("gender_program", FundingLeague.gender_program, GENDER_PROGRAMS),
    ):
        value = (request.args.get(arg) or "").strip().lower()
        if value:
            if value not in allowed:
                return jsonify({"error": f"{arg} must be one of {sorted(allowed)}"}), 400
            query = query.filter(column == value)
    country = (request.args.get("country") or "").strip()
    if country:
        query = query.filter(func.lower(FundingLeague.country) == country.lower())
    search = (request.args.get("q") or "").strip()
    if search:
        token = f"%{search}%"
        query = query.filter(or_(FundingLeague.name.ilike(token), FundingLeague.region.ilike(token)))
    rows = query.order_by(FundingLeague.created_at.desc(), FundingLeague.id.desc()).limit(MAX_PAGE).all()
    return jsonify({"leagues": [row.to_dict(admin=True) for row in rows]})


@funding_bp.route("/admin/funding/leagues", methods=["POST"])
@require_api_key
def admin_create_funding_league():
    try:
        payload = request.get_json(silent=True) or {}
        reason = _clean(payload.get("reason"), "reason", max_len=2000)
        values = _league_values(payload)
        duplicate = _league_duplicate(values)
        if duplicate:
            return jsonify({"error": "league is already registered", "league": duplicate.to_dict(admin=True)}), 409
        league = FundingLeague(**values, reviewed_by=getattr(g, "user_email", None), reviewed_at=datetime.now(UTC))
        db.session.add(league)
        db.session.flush()
        _audit("league.created", "league", league.id, reason, {"admission_state": league.admission_state})
        db.session.commit()
        return jsonify({"league": league.to_dict(admin=True)}), 201
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "league is already registered"}), 409
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to create funding league")
        return jsonify(_safe_error_payload(exc, "Failed to create league")), 500


@funding_bp.route("/admin/funding/leagues/<int:league_id>", methods=["GET"])
@require_api_key
def admin_get_funding_league(league_id):
    league = db.session.get(FundingLeague, league_id)
    if league is None:
        return jsonify({"error": "league not found"}), 404
    return jsonify({"league": league.to_dict(admin=True)})


@funding_bp.route("/admin/funding/leagues/<int:league_id>", methods=["PATCH"])
@require_api_key
def admin_update_funding_league(league_id):
    try:
        league = db.session.get(FundingLeague, league_id)
        if league is None:
            return jsonify({"error": "league not found"}), 404
        payload = request.get_json(silent=True) or {}
        reason = _clean(payload.get("reason"), "reason", max_len=2000)
        before = {"admission_state": league.admission_state, "registry_status": league.registry_status}

        if league.existing_league_id and any(
            key in payload for key in ("name", "country", "data_tier", "league_api_id")
        ):
            return jsonify({"error": "provider-bridged identity fields are read-only"}), 409
        if "name" in payload:
            league.name = _clean(payload["name"], "name", max_len=160)
        if "country" in payload:
            league.country = _clean(payload["country"], "country", max_len=80)
        if "region" in payload:
            league.region = _clean(payload["region"], "region", max_len=120)
        if "level" in payload:
            league.level = _enum(payload["level"], "level", LEVELS)
        if "age_bands" in payload:
            league.age_bands = _parse_age_bands(payload["age_bands"])
        if "gender_program" in payload:
            league.gender_program = _enum(payload["gender_program"], "gender_program", GENDER_PROGRAMS)
        if "season_calendar" in payload:
            league.season_calendar = _enum(payload["season_calendar"], "season_calendar", SEASON_CALENDARS)
        if "admission_state" in payload:
            league.admission_state = _enum(payload["admission_state"], "admission_state", ADMISSION_STATES)
        if "registry_status" in payload:
            league.registry_status = _enum(payload["registry_status"], "registry_status", REGISTRY_STATUSES)
        if not league.existing_league_id and ("data_tier" in payload or "league_api_id" in payload):
            merged = {"data_tier": payload.get("data_tier", league.data_tier_key)}
            if "league_api_id" in payload:
                merged["league_api_id"] = payload["league_api_id"]
            tier, api_id = _parse_data_tier(merged)
            league.data_tier = tier
            league.league_api_id = api_id
            existing = League.query.filter_by(league_id=api_id).first() if api_id else None
            league.existing_league_id = existing.id if existing else None
            if existing:
                league.name, league.country = existing.name, existing.country
        league.reviewed_by = getattr(g, "user_email", None)
        league.review_reason = reason
        league.reviewed_at = datetime.now(UTC)
        _audit(
            "league.updated",
            "league",
            league.id,
            reason,
            {
                "before": before,
                "after": {"admission_state": league.admission_state, "registry_status": league.registry_status},
            },
        )
        db.session.commit()
        return jsonify({"league": league.to_dict(admin=True)})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "league update conflicts with an existing registry row"}), 409
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to update funding league")
        return jsonify(_safe_error_payload(exc, "Failed to update league")), 500


@funding_bp.route("/admin/funding/leagues/<int:league_id>", methods=["DELETE"])
@require_api_key
def admin_delete_funding_league(league_id):
    try:
        league = db.session.get(FundingLeague, league_id)
        if league is None:
            return jsonify({"deleted": False})
        if league.existing_league_id:
            return jsonify({"error": "provider-bridged leagues are read-only"}), 409
        if league.programs.count():
            return jsonify({"error": "league has club programs and cannot be deleted"}), 409
        payload = request.get_json(silent=True) or {}
        reason = _clean(payload.get("reason"), "reason", max_len=2000)
        _audit("league.deleted", "league", league.id, reason, {"name": league.name})
        db.session.delete(league)
        db.session.commit()
        return jsonify({"deleted": True})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to delete funding league")
        return jsonify(_safe_error_payload(exc, "Failed to delete league")), 500


@funding_bp.route("/funding/claims", methods=["POST"])
@require_user_auth
@limiter.limit("3 per hour", key_func=_rate_limit_key)
def submit_program_claim():
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        payload = request.get_json(silent=True) or {}
        proposed = payload.get("proposed_league")
        league_id = payload.get("funding_league_id")
        if bool(proposed) == bool(league_id):
            raise ValueError("choose one approved league or propose one new league")
        if proposed:
            if not isinstance(proposed, dict):
                raise ValueError("proposed_league must be an object")
            values = _league_values(proposed, proposal=True)
            league = _league_duplicate(values)
            if league is None:
                league = FundingLeague(**values, proposed_by_user_id=user.id)
                db.session.add(league)
                db.session.flush()
                _audit(
                    "league.proposed",
                    "league",
                    league.id,
                    "League proposed through a club program claim",
                    {"admission_state": league.admission_state},
                )
            elif league.registry_status == "approved" and league.admission_state == "open":
                raise ValueError("this league is already open; select it from the approved registry")
        else:
            if isinstance(league_id, bool):
                raise ValueError("funding_league_id must be a positive integer")
            try:
                league_id = int(league_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("funding_league_id must be a positive integer") from exc
            league = db.session.get(FundingLeague, league_id)
            if league is None or league.registry_status != "approved" or league.admission_state != "open":
                return jsonify({"error": "league is not approved and open for admission"}), 409

        evidence_values = _evidence_values(payload)
        team_api_id = payload.get("team_api_id")
        team_profile = None
        if team_api_id is not None:
            if isinstance(team_api_id, bool):
                raise ValueError("team_api_id must be a positive integer")
            try:
                team_api_id = int(team_api_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("team_api_id must be a positive integer") from exc
            team_profile = db.session.get(TeamProfile, team_api_id)
            if team_profile is None:
                raise ValueError("team_api_id does not map to a covered Team")

        submitted_name = _clean(payload.get("club_name"), "club_name", max_len=180)
        name = team_profile.name if team_profile else submitted_name
        country = (
            team_profile.country
            if team_profile and team_profile.country
            else _clean(payload.get("country"), "country", max_len=80)
        )
        legal_name = _clean(payload.get("legal_name"), "legal_name", max_len=220)
        region = _clean(payload.get("region"), "region", max_len=120)
        city = _clean(payload.get("city"), "city", required=False, max_len=120)
        crest_url = (
            team_profile.logo_url
            if team_profile and team_profile.logo_url
            else _https(payload.get("crest_url"), "crest_url")
        )
        if not _same_country(country, league.country):
            raise ValueError("club country must match the selected league country")
        program = ClubProgram.query.filter_by(team_api_id=team_api_id).first() if team_api_id else None
        if program is not None and program.funding_league_id != league.id:
            return jsonify({"error": "this covered club is already registered in another league"}), 409
        if program is None:
            base_slug = _slug(name)
            slug = base_slug
            suffix = 2
            while ClubProgram.query.filter_by(slug=slug).first():
                slug = f"{base_slug}-{suffix}"
                suffix += 1
            program = ClubProgram(
                funding_league_id=league.id,
                team_api_id=team_api_id,
                name=name,
                legal_name=legal_name,
                slug=slug,
                crest_url=crest_url,
                country=country,
                region=region,
                city=city,
                currency="USD"
                if _is_us(country)
                else _clean(payload.get("currency", "USD"), "currency", max_len=3).upper(),
                provenance_tier="provider_covered" if team_profile else "self_reported",
                platform_status="pending",
            )
            db.session.add(program)
            db.session.flush()

        existing_claim = ClubProgramClaim.query.filter_by(program_id=program.id, user_account_id=user.id).first()
        if existing_claim and existing_claim.status not in {"rejected", "revoked"}:
            return jsonify(
                {"error": "you already have a claim for this program", "claim": _claim_dict(existing_claim)}
            ), 409
        if existing_claim:
            claim = existing_claim
            claim.status = "pending"
            claim.reviewed_by = None
            claim.review_reason = None
            claim.reviewed_at = None
            if claim.evidence:
                for key, value in evidence_values.items():
                    setattr(claim.evidence, key, value)
            else:
                db.session.add(ClubClaimEvidence(claim=claim, **evidence_values))
        else:
            claim = ClubProgramClaim(
                program=program,
                user_account_id=user.id,
                relationship_type="club_official",
                status="pending",
                applicant_message=_clean(
                    payload.get("applicant_message"), "applicant_message", required=False, max_len=1000
                ),
            )
            db.session.add(claim)
            db.session.flush()
            db.session.add(ClubClaimEvidence(claim=claim, **evidence_values))
        db.session.flush()
        league_waitlisted = league.registry_status != "approved" or league.admission_state != "open"
        _audit(
            "claim.resubmitted" if existing_claim else "claim.submitted",
            "claim",
            claim.id,
            "Club program claim submitted for review",
            {"program_id": program.id, "league_id": league.id, "league_waitlisted": league_waitlisted},
        )
        db.session.commit()
        return jsonify({"claim": _claim_dict(claim), "league_waitlisted": league_waitlisted}), 201
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "this club or league claim already exists"}), 409
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to submit club program claim")
        return jsonify(_safe_error_payload(exc, "Failed to submit claim")), 500


@funding_bp.route("/funding/claims/me", methods=["GET"])
@require_user_auth
def my_program_claims():
    user = _current_user_account()
    if user is None:
        return jsonify({"error": "auth context missing email"}), 401
    claims = (
        ClubProgramClaim.query.filter_by(user_account_id=user.id)
        .order_by(ClubProgramClaim.created_at.desc(), ClubProgramClaim.id.desc())
        .all()
    )
    return jsonify({"claims": [_claim_dict(claim) for claim in claims]})


@funding_bp.route("/admin/funding/claims", methods=["GET"])
@require_api_key
def admin_program_claims():
    status = (request.args.get("status") or "pending").strip().lower()
    query = ClubProgramClaim.query
    if status != "all":
        if status not in CLAIM_STATUSES:
            return jsonify({"error": f"status must be one of {sorted(CLAIM_STATUSES)} or all"}), 400
        query = query.filter(ClubProgramClaim.status == status)
    claims = query.order_by(ClubProgramClaim.created_at.asc(), ClubProgramClaim.id.asc()).limit(MAX_PAGE).all()
    return jsonify({"claims": [_claim_dict(claim, admin=True) for claim in claims]})


def _apply_connect_result(account, result):
    for field in (
        "stripe_account_id",
        "livemode",
        "account_type",
        "country",
        "business_type",
        "details_submitted",
        "charges_enabled",
        "payouts_enabled",
        "transfers_active",
        "requirements_due",
        "disabled_reason",
        "onboarding_url",
        "onboarding_expires_at",
    ):
        if field in result:
            setattr(account, field, result[field])
    account.last_synced_at = datetime.now(UTC)


@funding_bp.route("/admin/funding/claims/<int:claim_id>/approve", methods=["POST"])
@require_api_key
def approve_program_claim(claim_id):
    try:
        claim = db.session.get(ClubProgramClaim, claim_id)
        if claim is None:
            return jsonify({"error": "claim not found"}), 404
        if claim.status not in {"pending", "rejected", "revoked"}:
            return jsonify({"error": f"cannot approve a {claim.status} claim"}), 409
        payload = request.get_json(silent=True) or {}
        reason = _clean(payload.get("reason"), "reason", max_len=2000)
        league = claim.program.league
        if league.registry_status != "approved" or league.admission_state != "open":
            return jsonify({"error": "the program league must be approved and open before claim approval"}), 409
        if not _evidence_meets_bar(claim.evidence):
            return jsonify({"error": "claim evidence no longer meets the approved verification bar"}), 409

        now = datetime.now(UTC)
        claim.status = "approved"
        claim.reviewed_by = getattr(g, "user_email", None)
        claim.review_reason = reason
        claim.reviewed_at = now
        program = claim.program
        program.platform_status = "approved"
        program.reviewed_by = getattr(g, "user_email", None)
        program.review_reason = reason
        program.reviewed_at = now
        program.next_review_at = now + timedelta(days=365)

        manager = ClubProgramManager.query.filter_by(
            program_id=program.id, user_account_id=claim.user_account_id
        ).first()
        if manager is None:
            manager = ClubProgramManager(
                program=program,
                user_account_id=claim.user_account_id,
                source_claim_id=claim.id,
                status="active",
                granted_by=getattr(g, "user_email", None) or "admin",
                granted_at=now,
            )
            db.session.add(manager)
        else:
            manager.status = "active"
            manager.source_claim_id = claim.id
            manager.granted_by = getattr(g, "user_email", None) or "admin"
            manager.granted_at = now
            manager.revoked_at = None
            manager.revoked_reason = None

        connect_error = None
        if _is_us(program.country):
            account = ClubConnectAccount.query.filter_by(program_id=program.id).first()
            if account is None:
                account = ClubConnectAccount(
                    program=program,
                    country="US",
                    business_type="company",
                    account_type="express",
                    requirements_due=["connect.onboarding_not_started"],
                )
                db.session.add(account)
            db.session.flush()
            if not account.stripe_account_id and test_connect_configured():
                try:
                    _apply_connect_result(account, create_express_organization_onboarding(program))
                except Exception as exc:  # approval survives an integration outage; badge remains off
                    logger.exception("Test Connect onboarding failed for program %s", program.id)
                    connect_error = type(exc).__name__
                    account.requirements_due = ["connect.onboarding_retry_required"]

        verified = _refresh_program_verification(program, now=now)
        _audit(
            "claim.approved",
            "claim",
            claim.id,
            reason,
            {
                "program_id": program.id,
                "verified": verified,
                "connect_test_configured": test_connect_configured(),
                "connect_error": connect_error,
            },
        )
        db.session.commit()
        return jsonify({"claim": _claim_dict(claim, admin=True)})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to approve club program claim")
        return jsonify(_safe_error_payload(exc, "Failed to approve claim")), 500


@funding_bp.route("/admin/funding/claims/<int:claim_id>/reject", methods=["POST"])
@require_api_key
def reject_program_claim(claim_id):
    try:
        claim = db.session.get(ClubProgramClaim, claim_id)
        if claim is None:
            return jsonify({"error": "claim not found"}), 404
        if claim.status != "pending":
            return jsonify({"error": f"cannot reject a {claim.status} claim"}), 409
        payload = request.get_json(silent=True) or {}
        reason = _clean(payload.get("reason"), "reason", max_len=2000)
        claim.status = "rejected"
        claim.reviewed_by = getattr(g, "user_email", None)
        claim.review_reason = reason
        claim.reviewed_at = datetime.now(UTC)
        program = claim.program
        has_active_manager = (
            ClubProgramManager.query.filter_by(program_id=program.id, status="active").first() is not None
        )
        if not has_active_manager:
            program.platform_status = "rejected"
            program.review_reason = reason
            program.reviewed_by = getattr(g, "user_email", None)
            program.reviewed_at = claim.reviewed_at
            program.verified_at = None
        _audit(
            "claim.rejected",
            "claim",
            claim.id,
            reason,
            {"program_id": claim.program_id, "program_remains_approved": has_active_manager},
        )
        db.session.commit()
        return jsonify({"claim": _claim_dict(claim, admin=True)})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to reject club program claim")
        return jsonify(_safe_error_payload(exc, "Failed to reject claim")), 500


@funding_bp.route("/admin/funding/claims/<int:claim_id>/revoke", methods=["POST"])
@require_api_key
def revoke_program_claim(claim_id):
    try:
        claim = db.session.get(ClubProgramClaim, claim_id)
        if claim is None:
            return jsonify({"error": "claim not found"}), 404
        if claim.status != "approved":
            return jsonify({"error": f"cannot revoke a {claim.status} claim"}), 409
        payload = request.get_json(silent=True) or {}
        reason = _clean(payload.get("reason"), "reason", max_len=2000)
        now = datetime.now(UTC)
        actor = getattr(g, "user_email", None) or "admin"

        claim.status = "revoked"
        claim.reviewed_by = actor
        claim.review_reason = reason
        claim.reviewed_at = now
        manager = ClubProgramManager.query.filter_by(
            program_id=claim.program_id,
            user_account_id=claim.user_account_id,
            source_claim_id=claim.id,
        ).first()
        if manager is not None and manager.status == "active":
            manager.status = "revoked"
            manager.revoked_by = actor
            manager.revoked_reason = reason
            manager.revoked_at = now

        db.session.flush()
        remaining_manager = (
            ClubProgramManager.query.filter_by(program_id=claim.program_id, status="active").first() is not None
        )
        program = claim.program
        if not remaining_manager:
            program.platform_status = "suspended"
            program.donations_enabled = False
            program.reviewed_by = actor
            program.review_reason = reason
            program.reviewed_at = now
        verified = _refresh_program_verification(program, now=now)
        _audit(
            "claim.revoked",
            "claim",
            claim.id,
            reason,
            {
                "program_id": claim.program_id,
                "manager_grant_id": manager.id if manager else None,
                "remaining_active_manager": remaining_manager,
                "verified": verified,
            },
        )
        db.session.commit()
        return jsonify({"claim": _claim_dict(claim, admin=True)})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to revoke club program claim")
        return jsonify(_safe_error_payload(exc, "Failed to revoke claim")), 500


@funding_bp.route("/admin/funding/programs/<int:program_id>/connect/sync", methods=["POST"])
@require_api_key
def sync_program_connect_account(program_id):
    try:
        program = db.session.get(ClubProgram, program_id)
        if program is None:
            return jsonify({"error": "program not found"}), 404
        if not _is_us(program.country):
            return jsonify({"error": "Connect readiness is only used for US programs in F2"}), 409
        account = ClubConnectAccount.query.filter_by(program_id=program.id).first()
        if account is None or not account.stripe_account_id:
            return jsonify({"error": "test Connect onboarding has not started"}), 409
        payload = request.get_json(silent=True) or {}
        reason = _clean(payload.get("reason"), "reason", max_len=2000)
        result = retrieve_test_express_account(account.stripe_account_id)
        if str(result.get("country") or "").upper() != "US":
            raise StripeConnectConfigurationError("F2 supports US connected accounts only")
        _apply_connect_result(account, result)
        verified = _refresh_program_verification(program)
        _audit(
            "connect.synced",
            "program",
            program.id,
            reason,
            {
                "stripe_account_id": account.stripe_account_id,
                "livemode": account.livemode,
                "verified": verified,
            },
        )
        db.session.commit()
        return jsonify(
            {
                "program": {**program.public_dict(), "platform_status": program.platform_status},
                "connect": _connect_dict(account),
            }
        )
    except (ValueError, StripeConnectConfigurationError) as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to sync test Connect account for program %s", program_id)
        return jsonify(_safe_error_payload(exc, "Failed to sync test Connect account")), 502


def _approved_revision(program):
    if program.approved_profile_revision_id:
        revision = db.session.get(ClubProgramProfileRevision, program.approved_profile_revision_id)
        if revision and revision.program_id == program.id and revision.status == "approved":
            return revision
    return (
        ClubProgramProfileRevision.query.filter_by(program_id=program.id, status="approved")
        .order_by(ClubProgramProfileRevision.created_at.desc(), ClubProgramProfileRevision.id.desc())
        .first()
    )


@funding_bp.route("/programs/<string:slug>", methods=["GET"])
def public_program(slug):
    program = ClubProgram.query.filter_by(slug=slug, platform_status="approved", emergency_hidden=False).first()
    if program is None:
        return jsonify({"error": "program not found"}), 404
    payload = program.public_dict()
    revision = _approved_revision(program)
    payload["program_provided"] = (
        {
            "label": "Program-provided",
            "summary": revision.summary,
            "age_groups": revision.age_groups or [],
            "activities": revision.activities or [],
            "funding_purpose": revision.funding_purpose,
            "official_url": revision.official_url,
            "safeguarding_url": revision.safeguarding_url,
            "updated_at": revision.created_at.isoformat() if revision.created_at else None,
        }
        if revision
        else None
    )
    payload["roster_links"] = (
        {
            "team_page": f"/teams/{program.team_profile.slug}" if program.team_profile.slug else None,
            "academy_roster_api": f"/teams/{program.team_api_id}/players?academy_only=true",
        }
        if program.team_profile
        else None
    )
    return jsonify({"program": payload})


@funding_bp.route("/programs/<string:slug>/save", methods=["POST"])
@require_user_auth
@limiter.limit("30 per minute", key_func=_rate_limit_key)
def save_program(slug):
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        program = ClubProgram.query.filter_by(slug=slug, platform_status="approved", emergency_hidden=False).first()
        if program is None:
            return jsonify({"error": "program not found"}), 404
        payload = request.get_json(silent=True) or {}
        notify = payload.get("notify_when_fundable", True)
        notify = _bool(notify, "notify_when_fundable")
        follow_list = FollowList.query.filter_by(user_account_id=user.id, is_default=True).first()
        if follow_list is None:
            follow_list = FollowList(user_account_id=user.id, name="My Watchlist", is_default=True)
            db.session.add(follow_list)
            db.session.flush()
        follow = next(
            (
                row
                for row in follow_list.follows.filter(Follow.kind == "academy_club").all()
                if (row.selector or {}).get("program_id") == program.id
            ),
            None,
        )
        created = follow is None
        if follow is None:
            follow = Follow(
                list_id=follow_list.id,
                kind="academy_club",
                selector={"program_id": program.id},
                label=f"Club program: {program.name}"[:160],
                notify_when_fundable=notify,
            )
            db.session.add(follow)
        else:
            follow.notify_when_fundable = notify
        db.session.commit()
        return (
            jsonify(
                {
                    "saved": True,
                    "notify_when_fundable": follow.notify_when_fundable,
                    "follow_id": follow.id,
                }
            ),
            201 if created else 200,
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to save program")
        return jsonify(_safe_error_payload(exc, "Failed to save program")), 500


@funding_bp.route("/admin/funding/demand", methods=["GET"])
@require_api_key
def admin_funding_demand():
    program_id_expr = Follow.selector["program_id"].as_integer()
    saved_users = func.count(func.distinct(FollowList.user_account_id))
    rows = (
        db.session.query(ClubProgram, saved_users.label("saved_count"))
        .join(
            Follow,
            (Follow.kind == "academy_club")
            & (Follow.notify_when_fundable.is_(True))
            & (program_id_expr == ClubProgram.id),
        )
        .join(FollowList, FollowList.id == Follow.list_id)
        .filter(ClubProgram.platform_status == "approved", ClubProgram.emergency_hidden.is_(False))
        .group_by(ClubProgram.id)
        .order_by(saved_users.desc(), ClubProgram.id.asc())
        .all()
    )
    by_region = {}
    by_league = {}
    programs = []
    for program, count in rows:
        region_key = f"{program.country} / {program.region}"
        by_region[region_key] = by_region.get(region_key, 0) + count
        league_name = program.league.name
        by_league[league_name] = by_league.get(league_name, 0) + count
        programs.append(
            {
                "program_id": program.id,
                "program_name": program.name,
                "slug": program.slug,
                "region": program.region,
                "country": program.country,
                "league": league_name,
                "saved_count": count,
            }
        )
    return jsonify(
        {
            "programs": programs,
            "by_region": [{"region": key, "saved_count": value} for key, value in sorted(by_region.items())],
            "by_league": [{"league": key, "saved_count": value} for key, value in sorted(by_league.items())],
        }
    )
