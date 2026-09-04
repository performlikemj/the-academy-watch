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
    balances,
    refund_question,
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

        service = GolService(model_override=model_override)
    except Exception as e:
        logger.error(f"Failed to initialize GolService: {e}")
        return jsonify({"error": "Chat service unavailable"}), 503

    try:
        normalized_question = " ".join(message.split()).casefold()
        question_hash = hashlib.sha256(normalized_question.encode()).hexdigest()
        reservation = reserve_question(g.user, client_msg_id, question_hash=question_hash, role=role)
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

    def generate():
        usage = {
            "bucket": reservation["bucket"],
            "free_questions_remaining": reservation["free_questions_remaining"],
            "credit_balance": reservation["credit_balance"],
            "debited": reservation["debited"],
        }
        yield _sse("usage", usage)
        compensation_attempted = False

        def compensate():
            nonlocal compensation_attempted
            if compensation_attempted or not reservation["debited"]:
                return None
            compensation_attempted = True
            try:
                refunded = refund_question(g.user, client_msg_id)
            except Exception:
                logger.exception("Failed to compensate GOL question debit")
                return None
            if not refunded:
                return None
            return {
                "bucket": reservation["bucket"],
                **balances(g.user),
                "debited": reservation["debited"],
                "refunded": True,
            }

        try:
            for event in service.chat(message, history, session_id):
                evt_type = event.get("event", "token")
                evt_data = event.get("data", {})
                refunded_usage = compensate() if evt_type == "error" else None
                yield _sse(evt_type, evt_data)
                if refunded_usage is not None:
                    yield _sse("usage", refunded_usage)
        except GeneratorExit:
            raise
        except Exception as e:
            logger.error(f"SSE stream error: {e}", exc_info=True)
            refunded_usage = compensate()
            yield _sse("error", {"message": str(e)})
            if refunded_usage is not None:
                yield _sse("usage", refunded_usage)

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
