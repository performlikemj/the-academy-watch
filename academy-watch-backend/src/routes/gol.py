"""GOL Assistant API endpoints.

Provides SSE streaming chat endpoint and conversation suggestions.
"""
from flask import Blueprint, request, Response, jsonify, stream_with_context, send_file
from src.extensions import limiter
from src.auth import require_api_key
import io
import json
import logging

gol_bp = Blueprint('gol', __name__)
logger = logging.getLogger(__name__)


@gol_bp.route('/gol/chat', methods=['POST'])
@limiter.limit("20/minute")
def gol_chat():
    """SSE streaming chat endpoint.

    Body: {message: str, history: [{role, content}], session_id: str}
    Returns: text/event-stream with events: token, data_card, tool_call, done, error
    """
    data = request.get_json() or {}
    message = (data.get('message') or '').strip()

    if not message:
        return jsonify({'error': 'message is required'}), 400

    history = data.get('history', [])
    session_id = data.get('session_id', '')

    try:
        from src.services.gol_service import GolService
        service = GolService()
    except Exception as e:
        logger.error(f"Failed to initialize GolService: {e}")
        return jsonify({'error': 'Chat service unavailable'}), 503

    def generate():
        try:
            for event in service.chat(message, history, session_id):
                evt_type = event.get('event', 'token')
                evt_data = event.get('data', {})
                yield f"event: {evt_type}\ndata: {json.dumps(evt_data)}\n\n"
        except Exception as e:
            logger.error(f"SSE stream error: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@gol_bp.route('/gol/suggestions', methods=['GET'])
def gol_suggestions():
    """Get conversation starter suggestions."""
    try:
        from src.services.gol_service import GolService
        service = GolService()
        suggestions = service.get_suggestions()
        return jsonify({'suggestions': suggestions})
    except Exception as e:
        logger.warning(f"Failed to get suggestions: {e}")
        return jsonify({'suggestions': [
            "Which Big 6 academy is producing the most first-team players?",
            "Show me all players on loan from Arsenal",
            "Who are the top-performing loan players this season?",
            "Tell me about Chelsea's academy pipeline",
        ]})


@gol_bp.route('/gol/export-pdf', methods=['POST'])
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
        return jsonify({
            'error': 'pdf_renderer_unavailable',
            'message': 'PDF export is not configured on this server.',
        }), 503

    data = request.get_json(silent=True) or {}
    messages = data.get('messages') or []
    if not isinstance(messages, list) or not messages:
        return jsonify({'error': 'messages array is required'}), 400

    # Soft cap: a single chat should never need more than ~200 turns. Beyond
    # that we're almost certainly looking at a bug or an abuse pattern, and
    # WeasyPrint will happily consume memory trying to paginate it.
    if len(messages) > 200:
        return jsonify({'error': 'too many messages in chat export'}), 413

    try:
        pdf_bytes, filename = render_gol_chat_pdf(messages)
    except Exception as e:
        logger.exception("Failed to render GOL chat PDF")
        return jsonify({'error': 'pdf_render_failed', 'message': str(e)}), 500

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename,
    )


@gol_bp.route('/admin/gol/refresh-cache', methods=['POST'])
@require_api_key
def admin_refresh_gol_cache():
    """Invalidate the GOL DataFrame cache so the next query reloads from DB."""
    from src.services.gol_dataframes import DataFrameCache
    DataFrameCache.invalidate()
    return jsonify({'status': 'cache invalidated'})
