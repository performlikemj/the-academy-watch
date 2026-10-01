"""Persisted safety standing survives feature rollback; active accounts are unchanged."""

from itsdangerous import BadSignature
from src.models.league import UserAccount, db


class AccountBindingUnavailable(BadSignature):
    """Rejected centrally while retaining required-auth account-not-found semantics."""


def account_can_act(user):
    return user is not None and not user.is_tombstone and getattr(user, "account_status", "active") == "active"


def assert_token_standing(payload):
    """Central serializer guard covers legacy and optional-auth token consumers."""
    if not isinstance(payload, dict) or not payload.get("email"):
        return
    user = UserAccount.query.filter_by(email=payload["email"]).populate_existing().first()
    bound_id = payload.get("user_id")
    stale_binding = user is None and bound_id is not None
    if user is not None:
        stale_binding = (
            user.is_tombstone
            or (bound_id is not None and bound_id != user.id)
            or (
                payload.get("account_created_at") is not None
                and (user.created_at is None or payload["account_created_at"] != user.created_at.isoformat())
            )
        )
    if stale_binding:
        raise AccountBindingUnavailable("account not found")
    if user is not None and (not account_can_act(user) or payload.get("auth_epoch", 0) != (user.auth_epoch or 0)):
        raise BadSignature("account unavailable")


def is_account_active(user_id):
    return account_can_act(db.session.get(UserAccount, user_id, populate_existing=True))


actor_id_can_act = is_account_active


def consent_recipient_can_act(contact_request_id):
    """Legacy anonymous email capability respects the recipient's current standing."""
    from src.models.contact import ContactRequest
    from src.services.contact import resolve_club_courtesy_target

    contact = db.session.get(ContactRequest, contact_request_id)
    if contact is None:
        return True  # The existing route supplies its neutral not-found response.
    target = resolve_club_courtesy_target(
        program_id=contact.club_program_id,
        club_name=getattr(contact.claim, "current_club_name", None),
        player_api_id=contact.player_api_id,
    )
    recipient = (target or {}).get("contact_email")
    if not recipient:
        return True
    account = UserAccount.query.filter_by(email=recipient.strip().lower()).populate_existing().first()
    # No account was bound to this old capability: keep legacy registry recipients.
    return account is None or account_can_act(account)


def issue_account_access_token(user):
    """Separate salt: this credential can never authenticate a normal bearer path."""
    from flask import current_app
    from itsdangerous import URLSafeTimedSerializer

    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="account-access").dumps(
        {"user_id": user.id, "epoch": user.auth_epoch, "created_at": user.created_at.isoformat()}
    )


def require_account_access(view):
    """Normal auth or a fresh OTP-bound credential for three account rights only."""
    from functools import wraps

    from flask import current_app, g, request
    from itsdangerous import URLSafeTimedSerializer
    from src.auth import require_user_auth, resolve_bearer_user

    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            user = resolve_bearer_user()
        except (BadSignature, LookupError, ValueError):
            user = None
        if user is None:
            try:
                token = request.headers.get("Authorization", "").removeprefix("Bearer ")
                data = URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="account-access").loads(
                    token, max_age=900
                )
                user = db.session.get(UserAccount, data["user_id"], populate_existing=True)
                if (
                    user is None
                    or user.is_tombstone
                    or user.auth_epoch != data["epoch"]
                    or user.created_at.isoformat() != data["created_at"]
                ):
                    raise BadSignature("invalid account access")
            except (BadSignature, KeyError, TypeError):
                # Delegate normal-bearer failures to the original decorator verbatim.
                return require_user_auth(view)(*args, **kwargs)
        g.user, g.user_id, g.user_email = user, user.id, user.email
        return view(*args, **kwargs)

    return wrapped
