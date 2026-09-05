"""GOL Assistant API endpoints.

Provides SSE streaming chat endpoint and conversation suggestions.
"""

import hashlib
import io
import json
import logging
import re

from flask import Blueprint, Response, g, jsonify, request, send_file, stream_with_context
from src.auth import require_api_key, require_user_auth
from src.config.stripe_config import billing_enabled
from src.extensions import limiter
from src.services.gol_credits import (
    ClientMsgIdReused,
    CreditsExhausted,
    QuestionInFlight,
    QuestionRecoveryExhausted,
    balances,
    finish_execution,
    reserve_question,
)
from src.services.scout_entitlements import decoded_bearer_role

gol_bp = Blueprint("gol", __name__)
logger = logging.getLogger(__name__)

# Admin users get a different model for the GOL assistant
_ADMIN_GOL_MODEL = "deepseek/deepseek-v4-flash-0731"
_CLIENT_MSG_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def _sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


@gol_bp.route("/gol/chat", methods=["POST"])
@require_user_auth
@limiter.limit("20/minute")
def gol_chat():
    """SSE streaming chat endpoint.

    Body: {message: str, client_msg_id: str, history: [{role, content}], session_id: str}
    Returns: text/event-stream with events: usage, token, data_card, tool_call, done, error
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "invalid_json"}), 400
    raw_message = data.get("message")
    message = raw_message.strip() if isinstance(raw_message, str) else ""

    if not message:
        return jsonify({"error": "message is required"}), 400

    history = data.get("history", [])
    session_id = data.get("session_id", "")
    client_msg_id = data.get("client_msg_id")
    if billing_enabled() and (not isinstance(client_msg_id, str) or not _CLIENT_MSG_ID_RE.fullmatch(client_msg_id)):
        return jsonify({"error": "invalid_client_msg_id"}), 400

    # Detect admin callers to route them to the admin model
    role = decoded_bearer_role()
    model_override = _ADMIN_GOL_MODEL if role == "admin" else None

    try:
        from src.services.gol_service import GolService
    except ImportError:
        logger.exception("Failed to import GolService")
        return jsonify({"error": "Chat service unavailable"}), 503

    metered = billing_enabled() and role != "admin"
    if metered:
        if not isinstance(history, list) or not isinstance(session_id, str):
            return jsonify({"error": "invalid_history_or_session"}), 400
        for entry in history:
            if (
                not isinstance(entry, dict)
                or entry.get("role") not in {"user", "assistant", "tool", "system"}
                or not isinstance(entry.get("content", ""), (str, type(None)))
            ):
                return jsonify({"error": "invalid_history"}), 400
            if "tool_call_id" in entry and not isinstance(entry["tool_call_id"], str):
                return jsonify({"error": "invalid_history"}), 400
            if "tool_calls" in entry:
                calls = entry["tool_calls"]
                if not isinstance(calls, list) or any(
                    not isinstance(call, dict)
                    or not isinstance(call.get("id"), str)
                    or call.get("type") != "function"
                    or not isinstance(call.get("function"), dict)
                    or not isinstance(call["function"].get("name"), str)
                    or not isinstance(call["function"].get("arguments"), str)
                    for call in calls
                ):
                    return jsonify({"error": "invalid_history"}), 400
        history = [GolService._sanitize_history_entry(entry) for entry in history]
    try:
        canonical = json.dumps(
            {
                "message": " ".join(message.split()).casefold(),
                "history": history if metered else [],
                "session_id": session_id if metered else "",
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        question_hash = hashlib.sha256(canonical.encode()).hexdigest()
        reservation = reserve_question(g.user, client_msg_id, question_hash=question_hash, role=role)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_history_or_session"}), 400
    except QuestionInFlight:
        return jsonify({"error": "in_flight"}), 409
    except QuestionRecoveryExhausted:
        return jsonify({"error": "recovery_exhausted"}), 409
    except ClientMsgIdReused:
        return jsonify({"error": "client_msg_id_reused"}), 409
    except CreditsExhausted as exc:
        return (
            jsonify(
                {
                    "error": "credits_exhausted",
                    "feature": "gol_chat",
                    "free_questions_remaining": exc.free_questions_remaining,
                    "credit_balance": exc.credit_balance,
                    "top_up_path": "/account/billing",
                }
            ),
            402,
        )

    # Resolve replays before constructing a potentially unavailable model client.
    if not reservation.get("replay"):
        try:
            service = GolService(model_override=model_override)
        except Exception:
            finish_execution(g.user, reservation, failed=True)
            logger.exception("Failed to initialize GolService")
            return jsonify({"error": "Chat service unavailable"}), 503

    def generate():
        usage = {key: reservation[key] for key in ("bucket", "free_questions_remaining", "credit_balance", "debited")}
        completed = reservation.get("replay", False)
        failed = False
        text = ""
        events = []

        def compensate():
            nonlocal failed
            if failed or completed:
                return None
            failed = True
            try:
                refunded = finish_execution(g.user, reservation, failed=True)
                if refunded:
                    return {**usage, **balances(g.user), "refunded": True}
            except Exception:
                logger.exception("Failed to compensate GOL question debit")
            return None

        try:
            yield _sse("usage", usage)
            if completed:
                yield _sse("replace", {"content": reservation["response_text"] or ""})
                for event in reservation["response_events"]:
                    # Stored replace events describe intermediate revisions; the full answer above wins.
                    if event["event"] != "replace":
                        yield _sse(event["event"], event["data"])
                yield _sse("done", {})
                return
            if not reservation.get("execution_id"):
                # Preserve the existing admin and billing-disabled streaming contract.
                yield from (
                    _sse(event.get("event", "token"), event.get("data", {}))
                    for event in service.chat(message, history, session_id)
                )
                return
            for event in service.chat(message, history, session_id):
                evt_type = event.get("event", "token")
                evt_data = event.get("data", {})
                if evt_type == "error":
                    refunded_usage = compensate()
                    yield _sse(evt_type, evt_data)
                    if refunded_usage is not None:
                        yield _sse("usage", refunded_usage)
                    return
                if evt_type == "token":
                    text += evt_data.get("content", "")
                elif evt_type == "replace":
                    text = evt_data.get("content", "")
                    events.append({"event": evt_type, "data": evt_data})
                elif evt_type == "done":
                    if reservation.get("execution_id") and not finish_execution(
                        g.user, reservation, response_text=text, response_events=events
                    ):
                        return
                    completed = True
                    yield _sse(evt_type, evt_data)
                    return
                elif evt_type not in {"usage", "tool_call"}:
                    events.append({"event": evt_type, "data": evt_data})
                yield _sse(evt_type, evt_data)
            refunded_usage = compensate()
            yield _sse("error", {"message": "Chat ended before completion"})
            if refunded_usage is not None:
                yield _sse("usage", refunded_usage)
        except GeneratorExit:
            compensate()
            raise
        except Exception as exc:
            logger.exception("SSE stream error")
            refunded_usage = compensate()
            yield _sse("error", {"message": str(exc)})
            if refunded_usage is not None:
                yield _sse("usage", refunded_usage)
        finally:
            if not completed:
                compensate()

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@gol_bp.route("/gol/suggestions", methods=["GET"])
def gol_suggestions():
    """Get conversation starter suggestions."""
    try:
        from src.services.gol_service import GolService

        service = GolService()
        suggestions = service.get_suggestions()
        return jsonify({"suggestions": suggestions})
    except Exception as e:
        logger.warning(f"Failed to get suggestions: {e}")
        return jsonify(
            {
                "suggestions": [
                    "Which Big 6 academy is producing the most first-team players?",
                    "Show me all players on loan from Arsenal",
                    "Who are the top-performing loan players this season?",
                    "Tell me about Chelsea's academy pipeline",
                ]
            }
        )


@gol_bp.route("/gol/export-pdf", methods=["POST"])
@require_user_auth
@limiter.limit("10/minute")
def gol_export_pdf():
    """Render a GOL chat transcript to a downloadable PDF.

    The frontend posts the full client-side message array because the chat
    has no server-side persistence. Rate-limited more strictly than
    ``/gol/chat`` because each export spawns matplotlib chart renders and a
    WeasyPrint pass — cheap but not free.
    """
    try:
        from src.services.pdf_renderer import render_gol_chat_pdf
    except ImportError:
        logger.exception("WeasyPrint not available for GOL PDF export")
        return jsonify(
            {
                "error": "pdf_renderer_unavailable",
                "message": "PDF export is not configured on this server.",
            }
        ), 503

    data = request.get_json(silent=True) or {}
    messages = data.get("messages") or []
    if not isinstance(messages, list) or not messages:
        return jsonify({"error": "messages array is required"}), 400

    # Soft cap: a single chat should never need more than ~200 turns. Beyond
    # that we're almost certainly looking at a bug or an abuse pattern, and
    # WeasyPrint will happily consume memory trying to paginate it.
    if len(messages) > 200:
        return jsonify({"error": "too many messages in chat export"}), 413

    try:
        pdf_bytes, filename = render_gol_chat_pdf(messages)
    except Exception as e:
        logger.exception("Failed to render GOL chat PDF")
        return jsonify({"error": "pdf_render_failed", "message": str(e)}), 500

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@gol_bp.route("/admin/gol/refresh-cache", methods=["POST"])
@require_api_key
def admin_refresh_gol_cache():
    """Invalidate the GOL DataFrame cache so the next query reloads from DB."""
    from src.services.gol_dataframes import DataFrameCache

    DataFrameCache.invalidate()
    return jsonify({"status": "cache invalidated"})
