    if not video_retention.can_issue_upload_grant(match):
        return jsonify({"error": "retention deadline too close to issue an upload grant; create a new match"}), 409
