"""Money lifecycle regressions; Stripe and model calls are always fake."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
import stripe
import test_gol_credits as gol_fixtures
from sqlalchemy import text, update
from src.models.billing import GolCheckoutTerms, StripeWebhookEvent
from src.models.gol_credits import GolChatExecution, GolCreditLedger, GolPaymentSettlement
from src.models.league import db
from src.models.product_event import ProductEvent
from src.services.gol_credits import (
    QuestionInFlight,
    QuestionRecoveryExhausted,
    balances,
    finish_execution,
    refund_question,
    reserve_question,
)
from test_gol_credits import (  # noqa: F401
    _checkout,
    _completed,
    _enable,
    _event,
    _headers,
    _packs,
    _post_event,
    _StubGolService,
    _user,
)

app = gol_fixtures.app
client = gol_fixtures.client


def _chat(client, user, **overrides):
    return client.post(
        "/api/gol/chat",
        headers=_headers(user),
        json={"message": "Question", "client_msg_id": "replay_question", **overrides},
    )


def _terms(row, *, credits=7, attached=True):
    terms = GolCheckoutTerms(
        purchase_key=str(uuid4()),
        checkout_row_id=row.id,
        stripe_session_id=row.stripe_session_id if attached else None,
        price_code=row.price_code,
        credits=credits,
        unit_amount_cents=2000,
        currency="usd",
        stripe_price_id="price_gol_starter",
    )
    db.session.add(terms)
    db.session.commit()
    return terms


def _expire_execution():
    execution = GolChatExecution.query.one()
    execution.lease_started_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=6)
    db.session.commit()
    return execution


def test_completed_replay_after_exhaustion_never_constructs_model_and_preserves_cards(app, client, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("GOL_FREE_ALLOWANCE", "1")
    user = _user()
    calls = Mock()
    events = [
        {"event": "token", "data": {"content": "draft"}},
        {"event": "replace", "data": {"content": "Final"}},
        {"event": "token", "data": {"content": " answer"}},
        {"event": "data_card", "data": {"title": "Evidence"}},
        {"event": "history_entries", "data": {"entries": [{"role": "assistant", "content": "Final answer"}]}},
        {"event": "done", "data": {}},
    ]

    def chat(*args):
        calls()
        yield from events

    monkeypatch.setattr(_StubGolService, "chat", chat)
    _chat(client, user).get_data()
    assert balances(user)["free_questions_remaining"] == 0
    stored = GolChatExecution.query.one()
    assert stored.response_text == "Final answer"
    assert json.loads(stored.response_events) == [events[1], events[3], events[4]]
    assert stored.created_at.tzinfo is None
    monkeypatch.setattr(_StubGolService, "__init__", Mock(side_effect=RuntimeError("model unavailable")))
    response = _chat(client, user)
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '"content": "Final answer"' in body
    assert body.index("event: usage") < body.index("event: replace") < body.index("event: data_card")
    assert body.index("event: history_entries") < body.index("event: done")
    assert calls.call_count == 1
    assert GolCreditLedger.query.filter_by(kind="debit").count() == 1


def test_fresh_execution_returns_409_before_sse(app, client, monkeypatch):
    _enable(monkeypatch)
    user = _user()
    response = _chat(client, user)  # Only initial usage has been consumed.
    duplicate = _chat(client, user)
    assert duplicate.status_code == 409
    assert duplicate.get_json() == {"error": "in_flight"}
    response.close()


@pytest.mark.parametrize("change", ["history", "tool_calls", "tool_call_id", "session_id"])
def test_all_effective_input_fields_bind_client_id(app, client, monkeypatch, change):
    _enable(monkeypatch)
    user = _user()
    history = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}],
        },
        {"role": "tool", "content": "result", "tool_call_id": "call_1"},
    ]
    _chat(client, user, history=history, session_id="session_1").get_data()
    session_id = "session_1"
    if change == "history":
        history[1]["content"] = "different result"
    elif change == "tool_calls":
        history[0]["tool_calls"][0]["function"]["arguments"] = '{"name":"different"}'
    elif change == "tool_call_id":
        history[1]["tool_call_id"] = "call_2"
    else:
        session_id = "session_2"
    response = _chat(client, user, history=history, session_id=session_id)
    assert response.status_code == 409
    assert response.get_json() == {"error": "client_msg_id_reused"}


@pytest.mark.parametrize(
    "payload",
    [
        {"history": "bad"},
        {"history": [None]},
        {"history": [{"role": "assistant", "tool_calls": [None]}]},
        {"session_id": []},
        {"history": [{"role": "tool", "content": [], "tool_call_id": 1}]},
    ],
)
def test_malformed_input_rejected_before_debit(app, client, monkeypatch, payload):
    _enable(monkeypatch)
    user = _user()
    assert _chat(client, user, **payload).status_code == 400
    assert GolCreditLedger.query.count() == GolChatExecution.query.count() == 0


@pytest.mark.parametrize("terminal", ["error", "eof", "exception"])
def test_unfinished_stream_refunds_exact_attempt_then_retry_creates_two(app, client, monkeypatch, terminal):
    _enable(monkeypatch)
    user = _user()

    def broken(*args):
        yield {"event": "token", "data": {"content": "partial"}}
        if terminal == "error":
            yield {"event": "error", "data": {"message": "failed"}}
        elif terminal == "exception":
            raise RuntimeError("failed")

    monkeypatch.setattr(_StubGolService, "chat", broken)
    body = _chat(client, user).get_data(as_text=True)
    assert '"refunded": true' in body
    first = GolCreditLedger.query.filter_by(kind="debit").one()
    assert GolChatExecution.query.one().status == "failed"
    monkeypatch.setattr(_StubGolService, "chat", lambda *a: iter([{"event": "done", "data": {}}]))
    _chat(client, user).get_data()
    second = GolCreditLedger.query.filter_by(kind="debit", attempt=2).one()
    assert not refund_question(user, "replay_question", debit_id=first.id)
    assert GolCreditLedger.query.filter_by(kind="reversal", debit_id=second.id).count() == 0
    assert GolChatExecution.query.filter_by(attempt=2).one().status == "completed"


def test_done_is_persisted_before_delivery_and_delivery_failure_never_refunds(app, client, monkeypatch):
    from src.routes import gol

    _enable(monkeypatch)
    user = _user()
    _StubGolService.events = [{"event": "token", "data": {"content": "durable"}}, {"event": "done", "data": {}}]
    real_sse = gol._sse

    def fail_delivery(kind, data):
        if kind == "done":
            assert GolChatExecution.query.one().status == "completed"
            raise RuntimeError("delivery failed")
        return real_sse(kind, data)

    monkeypatch.setattr(gol, "_sse", fail_delivery)
    _chat(client, user).get_data()
    assert GolCreditLedger.query.filter_by(kind="reversal").count() == 0
    monkeypatch.setattr(gol, "_sse", real_sse)
    monkeypatch.setattr(_StubGolService, "__init__", Mock(side_effect=RuntimeError("offline")))
    assert '"content": "durable"' in _chat(client, user).get_data(as_text=True)


def test_stale_recovery_fences_old_worker_and_limits_recovery_without_new_debit(app, monkeypatch):
    _enable(monkeypatch)
    user = _user()
    first = reserve_question(user, "lease_question", question_hash="a" * 64)
    _expire_execution()
    second = reserve_question(user, "lease_question", question_hash="a" * 64)
    assert second["debited"] is False
    assert second["lease_generation"] == first["lease_generation"] + 1
    with pytest.raises(QuestionInFlight):
        reserve_question(user, "lease_question", question_hash="a" * 64)
    assert not finish_execution(user, first, failed=True)
    assert not finish_execution(user, first, response_text="stale")
    assert GolCreditLedger.query.filter_by(kind="reversal").count() == 0
    _expire_execution()
    third = reserve_question(user, "lease_question", question_hash="a" * 64)
    assert third["lease_generation"] == 3
    execution = _expire_execution()
    # SQLite has no row locks. A second UPDATE with the old generation cannot claim.
    changed = db.session.execute(
        update(GolChatExecution)
        .where(
            GolChatExecution.id == execution.id,
            GolChatExecution.status == "running",
            GolChatExecution.lease_generation == 2,
        )
        .values(lease_generation=4)
    ).rowcount
    assert changed == 0
    db.session.commit()
    with pytest.raises(QuestionRecoveryExhausted):
        reserve_question(user, "lease_question", question_hash="a" * 64)
    assert GolChatExecution.query.one().status == "failed"
    assert GolCreditLedger.query.filter_by(kind="debit").count() == 1
    assert GolCreditLedger.query.filter_by(kind="reversal", debit_id=first["debit_id"]).count() == 1


def test_process_death_recovery_runs_once_without_second_debit(app, client, monkeypatch):
    _enable(monkeypatch)
    user = _user()
    old_response = _chat(client, user)
    _expire_execution()
    calls = Mock()

    def chat(*args):
        calls()
        yield {"event": "token", "data": {"content": "recovered"}}
        yield {"event": "done", "data": {}}

    monkeypatch.setattr(_StubGolService, "chat", chat)
    assert "recovered" in _chat(client, user).get_data(as_text=True)
    old_response.close()  # stale disconnect cannot undo the recovered answer.
    _chat(client, user).get_data()
    assert calls.call_count == 1
    assert GolCreditLedger.query.filter_by(kind="debit").count() == 1
    assert GolCreditLedger.query.filter_by(kind="reversal").count() == 0


@pytest.mark.parametrize(
    "sequence",
    [
        [1000, "grant"],
        ["grant", 1000],
        [2000, 1000, "grant"],
        [1000, 1000, "grant", 1000, 2000],
        ["grant", 1000, 1000, 2000],
    ],
)
def test_refund_target_monotonic_in_every_event_order(app, client, monkeypatch, sequence):
    _enable(monkeypatch)
    _packs(monkeypatch)
    user = _user()
    _checkout(user, "cs_order")
    target = 0
    for index, item in enumerate(sequence):
        if item == "grant":
            event = _event(f"evt_order_{index}", "checkout.session.completed", _completed("cs_order"))
        else:
            target = max(target, item)
            event = _event(
                f"evt_order_{index}", "charge.refunded", {"payment_intent": "pi_gol", "amount_refunded": item}
            )
        assert _post_event(client, event).status_code == 200
        assert _post_event(client, event).get_json()["duplicate"] is True
        assert GolPaymentSettlement.query.one().refund_target_cents == target
    expected = 7 - 7 * target // 2000
    assert balances(user)["credit_balance"] == expected
    settlement = GolPaymentSettlement.query.one()
    assert settlement.refund_applied_cents == target
    assert settlement.grant_ledger_id == GolCreditLedger.query.filter_by(kind="grant").one().id
    credits = sum(event.props["credits"] for event in ProductEvent.query.filter_by(event_name="gol_credits_refunded"))
    assert credits == 7 - expected


def _mock_checkout(monkeypatch):
    _packs(monkeypatch)
    monkeypatch.setattr(stripe.Customer, "create", Mock(return_value={"id": "cus_terms"}))
    create = Mock(return_value={"id": "cs_terms", "url": "https://example.test/checkout", "expires_at": 2000000000})
    monkeypatch.setattr(stripe.checkout.Session, "create", create)
    return create


@pytest.mark.parametrize("config_change", ["changed", "removed"])
def test_checkout_snapshots_survive_pack_config_change(app, client, monkeypatch, config_change):
    _enable(monkeypatch)
    _mock_checkout(monkeypatch)
    user = _user()
    response = client.post(
        "/api/billing/checkout", headers=_headers(user), json={"pack_id": "gol_starter", "client_key": "terms_checkout"}
    )
    assert response.status_code == 200
    if config_change == "changed":
        monkeypatch.setenv("GOL_STARTER_CREDITS", "99")
    else:
        monkeypatch.delenv("STRIPE_PRICE_GOL_STARTER")
    event = _event("evt_terms", "checkout.session.completed", _completed("cs_terms", amount=1800))
    assert _post_event(client, event).status_code == 200
    assert GolCreditLedger.query.filter_by(kind="grant").one().delta == 7
    assert GolCheckoutTerms.query.one().unit_amount_cents == 2000


def test_recreated_checkout_keeps_original_terms_for_delayed_completion(app, client, monkeypatch):
    from src.models.billing import BillingCheckoutSession

    _enable(monkeypatch)
    create = _mock_checkout(monkeypatch)
    user = _user()
    payload = {"pack_id": "gol_starter", "client_key": "terms_checkout"}
    client.post("/api/billing/checkout", headers=_headers(user), json=payload)
    row = BillingCheckoutSession.query.one()
    row.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
    db.session.commit()
    monkeypatch.setenv("GOL_STARTER_CREDITS", "11")
    create.return_value = {"id": "cs_terms_new", "url": "https://example.test/new", "expires_at": 2000000000}
    client.post("/api/billing/checkout", headers=_headers(user), json=payload)
    assert GolCheckoutTerms.query.count() == 2
    # Numeric legacy reference must never accidentally pick the new session's terms.
    completed = {**_completed("cs_terms"), "client_reference_id": str(row.id)}
    assert _post_event(client, _event("evt_original", "checkout.session.completed", completed)).status_code == 200
    assert GolCreditLedger.query.filter_by(stripe_session_id="cs_terms").one().delta == 7
    assert row.status == "open"
    assert (
        _post_event(
            client, _event("evt_new", "checkout.session.completed", _completed("cs_terms_new", payment_intent="pi_new"))
        ).status_code
        == 200
    )
    assert GolCreditLedger.query.filter_by(stripe_session_id="cs_terms_new").one().delta == 11


def test_remote_creation_crash_preserves_terms_and_key_webhook_fulfils_once(app, client, monkeypatch):
    _enable(monkeypatch)
    create = _mock_checkout(monkeypatch)
    user = _user()
    create.side_effect = RuntimeError("remote created, process died before attachment")
    response = client.post(
        "/api/billing/checkout", headers=_headers(user), json={"pack_id": "gol_starter", "client_key": "crash_checkout"}
    )
    assert response.status_code == 500
    terms = GolCheckoutTerms.query.one()
    assert terms.stripe_session_id is None
    assert terms.purchase_key == create.call_args.kwargs["metadata"]["purchase_key"]
    event = {**_completed("cs_remote"), "metadata": {"purchase_key": terms.purchase_key}}
    for index, kind in enumerate(["checkout.session.completed", "checkout.session.async_payment_succeeded"]):
        assert _post_event(client, _event(f"evt_remote_{index}", kind, event)).status_code == 200
    assert GolCreditLedger.query.filter_by(kind="grant").count() == 1
    assert GolCheckoutTerms.query.one().stripe_session_id == "cs_remote"


@pytest.mark.parametrize("paid_first", [False, True])
def test_real_deletion_with_executions_settlement_and_late_paid_events(app, client, monkeypatch, paid_first):
    _enable(monkeypatch)
    _packs(monkeypatch)
    db.session.execute(text("PRAGMA foreign_keys=ON"))
    db.session.commit()
    user = _user()
    _chat(client, user).get_data()
    reserve_question(user, "running_question", question_hash="b" * 64)
    row = _checkout(user, "cs_deleted")
    terms = _terms(row)
    key = terms.purchase_key
    # Avoid remote calls in the real deletion service.
    monkeypatch.setattr(stripe.checkout.Session, "expire", Mock(return_value={"status": "expired"}))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "fake_test_only")
    if paid_first:
        _post_event(client, _event("evt_before_delete", "checkout.session.completed", _completed("cs_deleted")))
        _post_event(
            client,
            _event(
                "evt_refund_before_delete", "charge.refunded", {"payment_intent": "pi_gol", "amount_refunded": 1000}
            ),
        )
    exported = client.get("/api/account/export", headers=_headers(user)).get_json()
    assert {e["status"] for e in exported["gol_chat_executions"]} == {"running", "completed"}
    assert exported["gol_chat_executions"][0]["input_hash"]
    response = client.post("/api/account/delete", headers=_headers(user), json={"confirm": "DELETE"})
    assert response.status_code == 200
    assert response.get_json()["counts"]["deleted"]["gol_chat_executions"] == 2
    assert GolChatExecution.query.count() == GolCreditLedger.query.count() == 0
    assert GolCheckoutTerms.query.one().checkout_row_id is None
    assert GolPaymentSettlement.query.filter(GolPaymentSettlement.grant_ledger_id.isnot(None)).count() == 0
    for index, kind in enumerate(["checkout.session.completed", "checkout.session.async_payment_succeeded"]):
        result = _post_event(client, _event(f"evt_deleted_{index}", kind, _completed("cs_deleted")))
        assert result.status_code == 200
        assert StripeWebhookEvent.query.filter_by(event_id=f"evt_deleted_{index}").one().status == "ignored"
    incidents = ProductEvent.query.filter_by(event_name="gol_orphaned_purchase").all()
    assert len(incidents) == (0 if paid_first else 1)
    if incidents:
        assert incidents[0].props["purchase_key"] == key
        assert incidents[0].user_email is None


def test_unpaid_or_unrelated_orphan_is_never_a_manual_refund(app, client, monkeypatch):
    _enable(monkeypatch)
    user = _user()
    row = _checkout(user, "cs_unpaid_orphan")
    terms = _terms(row)
    terms.checkout_row_id = None
    db.session.delete(row)
    db.session.commit()
    for index, obj in enumerate([_completed("cs_unpaid_orphan", paid=False), _completed("cs_unrelated")]):
        assert (
            _post_event(client, _event(f"evt_unrelated_{index}", "checkout.session.completed", obj)).status_code == 200
        )
    assert ProductEvent.query.filter_by(event_name="gol_orphaned_purchase").count() == 0
    assert GolCreditLedger.query.count() == 0


def test_execution_insert_failure_rolls_back_the_debit_too(app, monkeypatch):
    _enable(monkeypatch)
    user = _user()
    original_flush = db.session.flush

    def fail_execution_flush(*args, **kwargs):
        if any(isinstance(row, GolChatExecution) for row in db.session.new):
            raise RuntimeError("execution insert failed")
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(db.session, "flush", fail_execution_flush)
    with pytest.raises(RuntimeError, match="execution insert failed"):
        reserve_question(user, "atomic_question", question_hash="c" * 64)
    assert GolCreditLedger.query.count() == GolChatExecution.query.count() == 0


def test_pending_checkout_retry_reuses_durable_purchase_key(app, client, monkeypatch):
    _enable(monkeypatch)
    create = _mock_checkout(monkeypatch)
    user = _user()
    payload = {"pack_id": "gol_starter", "client_key": "pending_checkout"}
    create.side_effect = RuntimeError("network response lost")
    assert client.post("/api/billing/checkout", headers=_headers(user), json=payload).status_code == 500
    first_params = create.call_args.kwargs
    monkeypatch.setenv("GOL_STARTER_CREDITS", "100")
    create.side_effect = None
    assert client.post("/api/billing/checkout", headers=_headers(user), json=payload).status_code == 200
    assert create.call_args.kwargs == first_params
    assert GolCheckoutTerms.query.one().credits == 7


@pytest.mark.parametrize(
    "chunks",
    [[], [("token", 199)], [("token", 200)], [("token", 500)], [("replace", 500)], [("token", 150), ("replace", 50)]],
)
def test_disconnect_refund_depends_on_total_answer_characters_yielded(app, client, monkeypatch, chunks):
    _enable(monkeypatch)
    monkeypatch.setenv("GOL_FREE_ALLOWANCE", "1")
    user = _user()
    _StubGolService.events = [{"event": kind, "data": {"content": "x" * length}} for kind, length in chunks]
    _StubGolService.events.append({"event": "done", "data": {}})
    response = _chat(client, user)
    frames = iter(response.response)
    assert next(frames).decode().startswith("event: usage")
    for kind, length in chunks:
        frame = next(frames).decode()
        assert frame.startswith(f"event: {kind}")
        assert "x" * length in frame
    before_close = balances(user)
    response.close()
    delivered = sum(length for _, length in chunks)
    refunded = delivered < 200
    db.session.expire_all()
    execution = GolChatExecution.query.one()
    debit = GolCreditLedger.query.filter_by(kind="debit").one()
    assert execution.status == "failed"
    assert f";disconnect_delivered_chars={delivered};refund_withheld={str(not refunded).lower()}" in debit.note
    assert debit.note.partition(";")[0] == execution.input_hash
    assert GolCreditLedger.query.filter_by(kind="reversal", debit_id=debit.id).count() == int(refunded)
    assert balances(user)["free_questions_remaining"] == int(refunded)
    if not refunded:
        assert balances(user) == before_close
        # Replaying the same id must not retroactively refund the withheld charge.
        retry = _chat(client, user)
        assert retry.status_code == 402
        assert GolCreditLedger.query.filter_by(kind="reversal").count() == 0


@pytest.mark.parametrize("failure", ["error", "exception"])
def test_server_failure_after_large_answer_still_refunds(app, client, monkeypatch, failure):
    _enable(monkeypatch)
    user = _user()

    def chat(*args):
        yield {"event": "token", "data": {"content": "x" * 500}}
        if failure == "error":
            yield {"event": "error", "data": {"message": "server failed"}}
        else:
            raise RuntimeError("server failed")

    monkeypatch.setattr(_StubGolService, "chat", chat)
    assert '"refunded": true' in _chat(client, user).get_data(as_text=True)
    assert GolChatExecution.query.one().status == "failed"
    assert GolCreditLedger.query.filter_by(kind="reversal").count() == 1


def test_removed_legacy_pack_is_ignored_with_one_session_incident(app, client, monkeypatch, caplog):
    _enable(monkeypatch)
    user = _user()
    _checkout(user, "cs_removed_legacy")
    for index, kind in enumerate(["checkout.session.completed", "checkout.session.async_payment_succeeded"]):
        event = _event(f"evt_removed_legacy_{index}", kind, _completed("cs_removed_legacy"))
        assert _post_event(client, event).status_code == 200
        assert _post_event(client, event).get_json()["duplicate"] is True
        assert StripeWebhookEvent.query.filter_by(event_id=event["id"]).one().status == "ignored"
    incident = ProductEvent.query.filter_by(event_name="gol_unfulfillable_legacy_purchase").one()
    assert incident.props["session_id"] == "cs_removed_legacy"
    assert incident.props["payment_intent"] == "pi_gol"
    assert "Unfulfillable legacy GOL purchase cs_removed_legacy" in caplog.text
    assert GolCreditLedger.query.count() == 0


def test_no_payment_required_orphan_does_not_claim_a_paid_purchase(app, client, monkeypatch, caplog):
    _enable(monkeypatch)
    user = _user()
    row = _checkout(user, "cs_no_payment_orphan")
    terms = _terms(row)
    terms.checkout_row_id = None
    db.session.delete(row)
    db.session.commit()
    obj = {**_completed("cs_no_payment_orphan", payment_intent=None, amount=0), "payment_status": "no_payment_required"}
    assert _post_event(client, _event("evt_no_payment_orphan", "checkout.session.completed", obj)).status_code == 200
    assert StripeWebhookEvent.query.filter_by(event_id="evt_no_payment_orphan").one().status == "ignored"
    assert "Ignoring payment session without an owned GOL purchase: cs_no_payment_orphan" in caplog.text
    assert ProductEvent.query.filter_by(event_name="gol_orphaned_purchase").count() == 0
    assert GolCreditLedger.query.count() == 0
