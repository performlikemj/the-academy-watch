from src.models.league import db, NewsletterCommentary, Team
from src.main import app

def fix_commentary_team_id():
    with app.app_context():
        print("=" * 60)
        print("FIXING COMMENTARY TEAM ID")
        print("=" * 60)
        
        # 1. Find the problematic commentary
        # We know it has ID 1 and Team ID 1 from the logs
        commentary = NewsletterCommentary.query.get(1)
        if not commentary:
            print("❌ Commentary with ID 1 not found!")
            return
            
        print(f"Found commentary: {commentary.title}")
        print(f"Current Team ID: {commentary.team_id}")
        
        # 2. Find the correct team ID (234)
        # We know from logs the newsletter is looking for team_id 234
        correct_team = Team.query.get(234)
        if not correct_team:
            print("❌ Target Team ID 234 not found!")
            return
            
        print(f"Target Team: {correct_team.name} (ID: {correct_team.id}, Season: {correct_team.season})")
        
        # 3. Update the commentary
        commentary.team_id = 234
        db.session.commit()
        
        print(f"✅ Successfully updated commentary team_id to 234")
        
        # Verify
        c_verify = NewsletterCommentary.query.get(1)
        print(f"Verification - New Team ID: {c_verify.team_id}")

if __name__ == "__main__":
    fix_commentary_team_id()
