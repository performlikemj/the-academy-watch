        resp = redirect(video_storage.mint_media_read_sas(match.blob_path))
        resp.headers["Cache-Control"] = "private, no-store"  # SAS rides the Location — don't cache/leak
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp
