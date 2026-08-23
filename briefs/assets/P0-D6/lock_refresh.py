    # Serialize with the retention sweeper: it re-checks this row under the same lock before deleting footage.
    db.session.refresh(match, with_for_update=True)
