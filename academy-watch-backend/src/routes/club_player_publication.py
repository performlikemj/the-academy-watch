"""Adult-only club publication handoff; private token travels in a POST body."""

from functools import wraps

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy.exc import IntegrityError
from src.auth import require_api_key, require_user_auth
from src.extensions import limiter
from src.models.club_player_publication import ClubPlayerPublication as Publication
from src.models.funding import ClubRosterMember
from src.models.league import UserAccount, db
from src.models.showcase import LocalPlayer, local_player_is_minor
from src.services import club_player_publication as service
from src.services.club_access import require_club_permission

publication_bp = Blueprint("club_player_publication", __name__)


def flagged(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not service.enabled():
            abort(404)
        try:
            return view(*args, **kwargs)
        except service.PublicationError as exc:
            db.session.rollback()
            return jsonify(error=exc.code), exc.status
        except ValueError as exc:
            db.session.rollback()
            return jsonify(error=str(exc)), 400
        except IntegrityError:
            db.session.rollback()
            return jsonify(error="publication_conflict"), 409

    return wrapped


@publication_bp.before_app_request
def dark_routes():
    if service.enabled():
        return
    # Re-match without C1 rules, preserving SPA, OPTIONS and wrong-method parity.
    from flask import current_app
    from flask.globals import request_ctx
    from werkzeug.exceptions import MethodNotAllowed, NotFound
    from werkzeug.routing import Map, RequestRedirect

    def owned(endpoint):
        return endpoint.startswith("club_player_publication.") or endpoint == "contact.revoke_club_origin_request"

    adapter = current_app.url_map.bind_to_environ(request.environ)
    try:
        rule, _ = adapter.match(method=request.method, return_rule=True)
    except MethodNotAllowed as error:
        for method in error.valid_methods:
            rule, _ = adapter.match(method=method, return_rule=True)
            if owned(rule.endpoint):
                break
        else:
            return
    except (NotFound, RequestRedirect):
        return
    if not owned(rule.endpoint):
        return
    rules = tuple(current_app.url_map.iter_rules())
    cached = current_app.extensions.get("club_publication_dark_map")
    if cached is None or cached[0] != rules:
        visible_rules = []
        for candidate in rules:
            if owned(candidate.endpoint):
                continue
            copied = candidate.empty()
            copied.provide_automatic_options = getattr(candidate, "provide_automatic_options", False)
            visible_rules.append(copied)
        original = current_app.url_map
        visible = Map(
            visible_rules,
            converters=original.converters,
            strict_slashes=original.strict_slashes,
            merge_slashes=original.merge_slashes,
            redirect_defaults=original.redirect_defaults,
            host_matching=original.host_matching,
            default_subdomain=original.default_subdomain,
        )
        current_app.extensions["club_publication_dark_map"] = (rules, visible)
    else:
        visible = cached[1]
    request_ctx.url_adapter = visible.bind_to_environ(request.environ)
    request.routing_exception = None
    request.url_rule = None
    request.view_args = None
    request_ctx.match_request()


@publication_bp.after_request
def private_response(response):
    if service.enabled():
        response.headers["Cache-Control"] = "no-store"
    return response


def payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise service.PublicationError("invalid_payload", 400)
    return data


def user():
    return db.session.get(UserAccount, g.user_id)


def row(id_, **scope):
    result = Publication.query.filter_by(id=id_, **scope).populate_existing().with_for_update().first()
    if result is None:
        raise service.PublicationError("publication_unavailable", 404)
    return result


def notice(publication):
    if publication.recipient_user_id is None:
        return
    from src.services.notification_outbox import enqueue

    enqueue(
        dedupe_key=f"c1:{publication.id}:{publication.version}:{publication.recipient_user_id}",
        recipient_user_id=publication.recipient_user_id,
        event_type="publication_update",
        entity_type="club_player_publication",
        entity_id=publication.id,
        template="c1_publication",
        payload={"publication_id": publication.id},
    )


@publication_bp.get("/club/<int:program_id>/player-publications")
@flagged
@require_club_permission("player_invitations")
def club_list(program_id):
    rows = Publication.query.filter_by(program_id=program_id).order_by(Publication.id.desc()).limit(100).all()
    return jsonify(publications=[service.dto(r) for r in rows])


@publication_bp.get("/club/<int:program_id>/publication-candidates")
@flagged
@require_club_permission("player_invitations")
def candidates(program_id):
    rows = (
        LocalPlayer.query.join(ClubRosterMember, ClubRosterMember.local_player_id == LocalPlayer.id)
        .filter(
            ClubRosterMember.program_id == program_id,
            LocalPlayer.origin_program_id == program_id,
            LocalPlayer.provenance == "club",
            LocalPlayer.merged_into_local_player_id.is_(None),
            ~local_player_is_minor(LocalPlayer),
        )
        .order_by(LocalPlayer.display_name, LocalPlayer.id)
        .limit(100)
        .all()
    )
    return jsonify(players=[{"id": p.id, "name": p.display_name} for p in rows])


@publication_bp.post("/club/<int:program_id>/players/<int:local_id>/publication-invite")
@flagged
@require_club_permission("player_invitations")
@limiter.limit("20/hour", key_func=lambda: f"c1:{g.user_id}")
def club_invite(program_id, local_id):
    publication, token = service.invite(program_id, local_id, g.user_id, payload())
    service.audit(publication, "invited", g.user_id)
    db.session.commit()
    # Private shareable link, only hash persisted. OTP sign-in must match the recipient.
    return jsonify(publication=service.dto(publication), token=token), 201


@publication_bp.post("/club/<int:program_id>/player-publications/<int:publication_id>/revoke")
@flagged
@require_club_permission("player_invitations")
def club_revoke(program_id, publication_id):
    publication = row(publication_id, program_id=program_id)
    service.expect_version(publication, payload())
    service.revoke(publication, club=True)
    service.audit(publication, "club_revoked", g.user_id)
    notice(publication)
    db.session.commit()
    return jsonify(publication=service.dto(publication))


@publication_bp.post("/me/player-publication-invites/<string:action>")
@flagged
@require_user_auth
@limiter.limit("20/hour", key_func=lambda: f"c1:{g.user_id}")
def redeem(action):
    if action not in {"preview", "accept"}:
        abort(404)
    publication = service.redeem(user(), payload(), preview=action == "preview")
    if action == "accept":
        service.audit(publication, "claimed", g.user_id)
    db.session.commit()
    return jsonify(publication=service.dto(publication))


@publication_bp.get("/me/player-publications")
@flagged
@require_user_auth
def mine():
    rows = Publication.query.filter_by(recipient_user_id=g.user_id).order_by(Publication.id.desc()).all()
    return jsonify(publications=[service.dto(r) for r in rows])


@publication_bp.post("/me/player-publications/<int:publication_id>/<string:action>")
@flagged
@require_user_auth
@limiter.limit("30/hour", key_func=lambda: f"c1:{g.user_id}")
def player_action(publication_id, action):
    publication = row(publication_id, recipient_user_id=g.user_id)
    data = payload()
    if action == "consent":
        service.consent(publication, g.user_id, data)
    elif action == "withdraw":
        service.expect_version(publication, data)
        service.revoke(publication)
    else:
        abort(404)
    service.audit(publication, action, g.user_id)
    db.session.commit()
    return jsonify(publication=service.dto(publication))


@publication_bp.get("/admin/player-publications")
@flagged
@require_api_key
def admin_list():
    rows = Publication.query.filter_by(moderation_status="pending").order_by(Publication.id).limit(100).all()
    return jsonify(publications=[service.dto(r) for r in rows])


@publication_bp.post("/admin/player-publications/<int:publication_id>/review")
@flagged
@require_api_key
def admin_review(publication_id):
    publication = row(publication_id)
    service.review(publication, g.user_email, payload())
    notice(publication)
    db.session.commit()
    return jsonify(publication=service.dto(publication))
