        remaining = media_token_remaining_seconds(request.args.get("token", ""), match_id)
        if remaining <= 0:
            return jsonify({"error": "invalid or expired media token"}), 403
        resp = redirect(video_storage.mint_media_read_sas(match.blob_path, seconds=remaining))
