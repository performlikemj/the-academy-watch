    __table_args__ = (
        db.UniqueConstraint("user_account_id", "player_api_id", name="uq_scout_watchlist_user_player"),
        db.Index("ix_scout_watchlist_player", "player_api_id"),
    )
