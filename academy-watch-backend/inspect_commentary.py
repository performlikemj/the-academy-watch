from src.main import app
from src.models.league import LoanedPlayer, NewsletterCommentary, Team
from src.utils.log_privacy import log_metadata


def inspect():
    with app.app_context():
        print(log_metadata("=" * 60))
        print("COMMENTARY DATABASE INSPECTION")
        print(log_metadata("=" * 60))

        # Find all commentaries
        commentaries = NewsletterCommentary.query.all()
        print(f"\n📝 Total commentaries in DB: {len(commentaries)}")

        for c in commentaries:
            print(f"\n--- Commentary ID {log_metadata(c.id)} ---")
            print(f"  Title: {log_metadata(c.title)}")
            print(f"  Team ID (DB): {log_metadata(c.team_id)}")
            print(f"  Player ID: {log_metadata(c.player_id)}")
            print(f"  Type: {log_metadata(c.commentary_type)}")
            print(f"  Week: {log_metadata(c.week_start_date)} to {log_metadata(c.week_end_date)}")
            print(f"  Is Active: {log_metadata(c.is_active)}")
            print(f"  Created: {log_metadata(c.created_at)}")
            print(f"  Updated: {log_metadata(c.updated_at)}")

            # Try to find the team
            if c.team_id:
                team = Team.query.get(c.team_id)
                if team:
                    print(
                        f"  Team (resolved): {log_metadata(team.name)} (API ID: {log_metadata(team.team_id)}, Season: {log_metadata(team.season)})"
                    )
                else:
                    print("  Team (resolved): NOT FOUND")

            # Try to find player
            if c.player_id:
                player = LoanedPlayer.query.filter_by(player_id=c.player_id).first()
                if player:
                    print(f"  Player (resolved): {log_metadata(player.player_name)}")
                else:
                    print(f"  Player (resolved): NOT FOUND (searching by player_id={log_metadata(c.player_id)})")

        print(log_metadata("\n" + "=" * 60))
        print("MANCHESTER UNITED TEAMS IN DB")
        print(log_metadata("=" * 60))

        man_u_teams = Team.query.filter(Team.name.like("%Manchester United%")).all()
        print(f"\nFound {len(man_u_teams)} Manchester United team records:")
        for t in man_u_teams:
            print(
                f"  DB ID: {log_metadata(t.id)}, API ID: {log_metadata(t.team_id)}, Season: {log_metadata(t.season)}, Active: {log_metadata(t.is_active)}"
            )

        print(log_metadata("\n" + "=" * 60))
        print("H. AMASS PLAYER RECORDS")
        print(log_metadata("=" * 60))

        amass_players = LoanedPlayer.query.filter(LoanedPlayer.player_name.like("%Amass%")).all()
        print(f"\nFound {len(amass_players)} Amass player records:")
        for p in amass_players:
            print(
                f"  Player ID: {log_metadata(p.player_id)}, Name: {log_metadata(p.player_name)}, Team ID: {log_metadata(p.primary_team_id)}"
            )


if __name__ == "__main__":
    inspect()
