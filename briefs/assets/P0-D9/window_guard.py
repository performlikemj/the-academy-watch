    if video_retention.retention_window_closed(match):
        return jsonify({"error": "retention window closed; the footage is due for deletion"}), 409
