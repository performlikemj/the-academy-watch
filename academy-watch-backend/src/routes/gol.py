"""GOL Assistant API endpoints.

Provides SSE streaming chat endpoint and conversation suggestions.
"""
from flask import Blueprint, request, Response, jsonify, stream_with_context
from src.extensions import limiter
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
            logger.error(f"SSE stream error: {e}")
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
