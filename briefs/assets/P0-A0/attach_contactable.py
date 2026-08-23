def _attach_contactable(players: list[dict]) -> None:
    """Mark rows whose player has an approved self-claim — the contact rail's target set (one query)."""
    ids = {p["player_id"] for p in players if p.get("player_id")}
    claimed = set()
    if ids:
        rows = (
            db.session.query(PlayerProfileClaim.player_api_id)
            .filter(
                PlayerProfileClaim.player_api_id.in_(ids),
                PlayerProfileClaim.relationship_type == "player",
                PlayerProfileClaim.status == "approved",
            )
            .distinct()
            .all()
        )
        claimed = {row[0] for row in rows}
    for player in players:
        player["contactable"] = player.get("player_id") in claimed


