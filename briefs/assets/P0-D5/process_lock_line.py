    # Hold the row: the retention sweeper re-checks under this same lock before deleting footage.
    match = db.session.get(VideoMatch, match_id, with_for_update=True)
