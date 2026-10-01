"""RB3V2: real SPA routing parity and refund metadata after out-of-order delivery."""

import pytest
from src.models.admin_control import BillingCashEvent
from src.models.billing import BillingSubscription
from src.models.league import db
from src.services.admin_control_business import project_cash
from test_admin_control import control_app, user  # noqa: F401


@pytest.mark.parametrize("spa_present", [False, True])
@pytest.mark.parametrize("method", ["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@pytest.mark.parametrize(
    "path",
    [
        "/api/admin/users/1/suspend",
        "/api/admin/users/1/restore",
        "/api/admin/people",
        "/api/admin/programs/1",
        "/api/admin/safety/cases/1/actions",
        "/api/admin/business/summary",
    ],
)
def test_dark_routes_match_unknown_in_real_app(monkeypatch, tmp_path, spa_present, method, path):
    # Production entry point includes the SPA catch-all and application error handlers.
    from src.main import app

    for flag in ("ADMIN_PROGRAMS_ENABLED", "ADMIN_PEOPLE_ENABLED", "ADMIN_SAFETY_ENABLED", "ADMIN_BUSINESS_ENABLED"):
        monkeypatch.setenv(flag, "0")
    monkeypatch.setattr(app, "static_folder", str(tmp_path))
    if spa_present:
        (tmp_path / "index.html").write_text("SPA shell")
    client = app.test_client()
    unknown = client.open("/api/not-a-real-b3-path", method=method)
    dark = client.open(path, method=method)
    assert (dark.status_code, dark.data, dict(dark.headers)) == (
        unknown.status_code,
        unknown.data,
        dict(unknown.headers),
    )


@pytest.mark.parametrize("receipt_type", ["invoice.paid", "modern_invoice", "checkout.session.completed"])
def test_early_refund_metadata_backfills_once_without_replaying_refund(control_app, receipt_type):  # noqa: F811
    person_id = user().id
    db.session.add(
        BillingSubscription(
            scope_type="club_program",
            scope_id=42,
            product_code="club_pro",
            price_code="monthly",
            purchaser_user_id=person_id,
            stripe_customer_id="cus_backfill",
            stripe_subscription_id="sub_backfill",
            stripe_price_id="price_backfill",
            status="active",
        )
    )
    db.session.commit()
    refund = {
        "id": "ch_backfill",
        "currency": "usd",
        "payment_intent": "pi_backfill",
        "refunds": {"data": [{"id": "re_backfill", "amount": 250, "status": "succeeded", "created": 1790899200}]},
    }
    project_cash("charge.refunded", refund, "evt_refund", 1790899200)
    db.session.commit()
    row = BillingCashEvent.query.one()
    assert row.product_code == "unmapped"
    original = (row.id, row.source_key, row.amount_cents, row.currency, row.occurred_at, row.stripe_event_id)
    if receipt_type == "checkout.session.completed":
        from src.models.gol_credits import GolCreditLedger

        db.session.add(
            GolCreditLedger(
                user_account_id=person_id,
                kind="grant",
                bucket="prepaid",
                delta=10,
                idempotency_key="backfill-grant",
                stripe_session_id="cs_backfill",
                stripe_payment_intent_id="pi_backfill",
            )
        )
        db.session.commit()
        receipt = {
            "id": "cs_backfill",
            "mode": "payment",
            "payment_status": "paid",
            "currency": "usd",
            "amount_total": 1500,
            "payment_intent": "pi_backfill",
        }
        expected = ("gol", "user", person_id, person_id)
    else:
        receipt = {
            "id": "in_backfill",
            "currency": "usd",
            "amount_paid": 1500,
            "payment_intent": "pi_backfill",
            "subscription": "sub_backfill",
        }
        expected = ("club_pro", "club_program", 42, person_id)
        if receipt_type == "modern_invoice":
            receipt_type = "invoice.paid"
            receipt.pop("payment_intent")
            receipt["payments"] = {
                "data": [
                    {
                        "id": "ip_backfill",
                        "status": "paid",
                        "amount_paid": 1500,
                        "payment": {"type": "payment_intent", "payment_intent": "pi_backfill"},
                    }
                ]
            }
    for _ in range(2):
        project_cash(receipt_type, receipt, "evt_receipt", 1790812800)
        db.session.commit()
        db.session.expire_all()
        row = BillingCashEvent.query.filter_by(kind="refund").one()
        assert (row.product_code, row.scope_type, row.scope_id, row.purchaser_user_id) == expected
        assert (
            row.id,
            row.source_key,
            row.amount_cents,
            row.currency,
            row.occurred_at,
            row.stripe_event_id,
        ) == original
        assert BillingCashEvent.query.count() == 2
    # Upgrade repair: an already-deduplicated receipt must revisit old unmapped refunds.
    row.product_code = "unmapped"
    row.scope_type = row.scope_id = row.purchaser_user_id = None
    db.session.commit()
    project_cash(receipt_type, receipt, "evt_receipt", 1790812800)
    db.session.commit()
    db.session.expire_all()
    row = BillingCashEvent.query.filter_by(kind="refund").one()
    assert (row.product_code, row.scope_type, row.scope_id, row.purchaser_user_id) == expected
    assert BillingCashEvent.query.count() == 2


def test_real_app_dark_map_tracks_flags_and_keeps_sibling_tools(monkeypatch, tmp_path):
    from src.main import app

    monkeypatch.setenv("ADMIN_API_KEY", "test-control-key")
    monkeypatch.setattr(app, "static_folder", str(tmp_path))
    client = app.test_client()
    for value in ("0", "1", "0"):
        monkeypatch.setenv("ADMIN_PEOPLE_ENABLED", value)
        response = client.post("/api/admin/users/1/suspend")
        assert response.status_code == (401 if value == "1" else 405)
        # A2/existing role editor shares the B3 /admin/users namespace.
        assert client.put("/api/admin/users/1/author-permission").status_code == 401
