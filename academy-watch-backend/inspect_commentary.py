from src.models.league import db, NewsletterCommentary, Team, LoanedPlayer
from src.main import app

def inspect():
    with app.app_context():
        print("=" * 60)
        print("COMMENTARY DATABASE INSPECTION")
        print("=" * 60)
        
        # Find all commentaries
        commentaries = NewsletterCommentary.query.all()
        print(f"\n📝 Total commentaries in DB: {len(commentaries)}")
        
        for c in commentaries:
            print(f"\n--- Commentary ID {c.id} ---")
            print(f"  Title: {c.title}")
            print(f"  Team ID (DB): {c.team_id}")
            print(f"  Player ID: {c.player_id}")
            print(f"  Type: {c.commentary_type}")
            print(f"  Week: {c.week_start_date} to {c.week_end_date}")
            print(f"  Is Active: {c.is_active}")
            print(f"  Created: {c.created_at}")
            print(f"  Updated: {c.updated_at}")
            
            # Try to find the team
            if c.team_id:
                team = Team.query.get(c.team_id)
                if team:
                    print(f"  Team (resolved): {team.name} (API ID: {team.team_id}, Season: {team.season})")
                else:
                    print(f"  Team (resolved): NOT FOUND")
            
            # Try to find player
            if c.player_id:
                player = LoanedPlayer.query.filter_by(player_id=c.player_id).first()
                if player:
                    print(f"  Player (resolved): {player.player_name}")
                else:
                    print(f"  Player (resolved): NOT FOUND (searching by player_id={c.player_id})")
        
        print("\n" + "=" * 60)
        print("MANCHESTER UNITED TEAMS IN DB")
        print("=" * 60)
        
        man_u_teams = Team.query.filter(Team.name.like('%Manchester United%')).all()
        print(f"\nFound {len(man_u_teams)} Manchester United team records:")
        for t in man_u_teams:
            print(f"  DB ID: {t.id}, API ID: {t.team_id}, Season: {t.season}, Active: {t.is_active}")
        
        print("\n" + "=" * 60)
        print("H. AMASS PLAYER RECORDS")
        print("=" * 60)
        
        amass_players = LoanedPlayer.query.filter(LoanedPlayer.player_name.like('%Amass%')).all()
        print(f"\nFound {len(amass_players)} Amass player records:")
        for p in amass_players:
            print(f"  Player ID: {p.player_id}, Name: {p.player_name}, Team ID: {p.primary_team_id}")

if __name__ == "__main__":
    inspect()
