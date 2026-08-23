
    def test_browse_marks_contactable_only_for_approved_player_claims(self, scout_client, seeded_players):
        user = UserAccount(email="claimant@example.com", display_name="Claimant", display_name_lower="claimant")
        db.session.add(user)
        db.session.flush()
        db.session.add_all(
            [
                PlayerProfileClaim(
                    player_api_id=1001, user_account_id=user.id, relationship_type="player", status="approved"
                ),
                PlayerProfileClaim(
                    player_api_id=1002, user_account_id=user.id, relationship_type="agent", status="approved"
                ),
                PlayerProfileClaim(
                    player_api_id=1003, user_account_id=user.id, relationship_type="player", status="pending"
                ),
            ]
        )
        db.session.commit()

        resp = scout_client.get("/api/scout/players")
        assert resp.status_code == 200
        by_id = {p["player_id"]: p for p in resp.get_json()["players"]}
        assert by_id[1001]["contactable"] is True
        assert by_id[1002]["contactable"] is False
        assert by_id[1003]["contactable"] is False
