import os, json
from src.main import app
from src.auth import issue_user_token
from src.models.showcase import LocalPlayer, PlayerProfileClaim
admin_email = (os.getenv("ADMIN_EMAILS") or "").split(",")[0].strip()
key = os.getenv("ADMIN_API_KEY") or ""
assert admin_email and key, "admin env missing"
with app.app_context():
    token = issue_user_token(admin_email, ttl_seconds=600, role="admin")["token"]
    c = app.test_client()
    H = {"Authorization": f"Bearer {token}", "X-API-Key": key, "Content-Type": "application/json"}
    out = {}
    lp = LocalPlayer.query.filter_by(display_name="Review Player").order_by(LocalPlayer.id.desc()).first()
    if lp is not None:
        out["local_player"] = {"id": lp.id, "status_before": lp.status}
        if lp.status != "approved":
            r = c.post(f"/api/admin/local-players/{lp.id}/review", headers=H, data=json.dumps({"action": "approve"}))
            out["local_player"]["approve_http"] = r.status_code
        claims = PlayerProfileClaim.query.filter_by(local_player_id=lp.id).all()
        out["claims"] = []
        for cl in claims:
            item = {"id": cl.id, "status_before": cl.status}
            if cl.status == "pending":
                r = c.post(f"/api/admin/showcase/claims/{cl.id}/review", headers=H, data=json.dumps({"action": "approve"}))
                item["approve_http"] = r.status_code
            out["claims"].append(item)
        # local showcase profile revision (if the profile PUT happened and is pending)
        try:
            from src.models.showcase import PlayerShowcaseProfile
            prof = PlayerShowcaseProfile.query.filter_by(local_player_id=lp.id).first()
            if prof is not None:
                out["profile"] = {"status_before": getattr(prof, "status", None)}
                if getattr(prof, "status", None) == "pending":
                    r = c.post(f"/api/admin/showcase/local-profiles/{lp.id}/review", headers=H, data=json.dumps({"action": "approve"}))
                    out["profile"]["approve_http"] = r.status_code
        except Exception as e:
            out["profile_error"] = type(e).__name__
    # club official claim submitted by the review SCOUT account (matched by claimant email from REVIEW_LOGIN_ACCOUNTS)
    try:
        from src.models.showcase import ClubOfficialClaim
        from src.models.league import UserAccount
        ra = json.loads(os.getenv("REVIEW_LOGIN_ACCOUNTS") or "{}")
        scout_email = ((ra.get("scout") or {}).get("email") or "").strip().lower()
        out["club_claims"] = []
        for cc in ClubOfficialClaim.query.filter(ClubOfficialClaim.status == "pending").all():
            ua = UserAccount.query.get(getattr(cc, "user_account_id", None) or getattr(cc, "user_id", None) or 0)
            claimant = (getattr(ua, "email", "") or "").strip().lower()
            if scout_email and claimant == scout_email:
                r = c.post(f"/api/admin/club-claims/{cc.id}/review", headers=H, data=json.dumps({"action": "approve"}))
                out["club_claims"].append({"id": cc.id, "approve_http": r.status_code, "err": (r.get_json() or {}).get("error")})
            else:
                out["club_claims"].append({"id": cc.id, "skipped": "not the review scout"})
    except Exception as e:
        import traceback; out["club_claims_error"] = type(e).__name__ + ": " + str(e)[:200] + " @ " + traceback.format_exc().strip().splitlines()[-2][:120]
    print("APPROVER " + json.dumps(out))
