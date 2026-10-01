#!/usr/bin/env python3
"""Capture real Phase 2 DTOs from the isolated, synthetic staging world.

Tokens remain in memory. Never point this script at production. Reads are the
normal mode. --exercise-writes creates one labelled scratch trial/application
and invite, records real write responses, then withdraws/closes/revokes them.
The staging SMTP sink receives the scratch invite; no external email is sent.
--capture-rate-limit sends bounded directory reads to capture a genuine 429.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1] / "AcademyWatchTests/Fixtures/Phase2"
BASE = "https://basecamp.tail37b60.ts.net:15443/api/"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exercise-writes", action="store_true")
    parser.add_argument("--capture-rate-limit", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    previous = args.output / "manifest.json"
    manifest = json.loads(previous.read_text())["fixtures"] if previous.exists() else []
    tokens = {}

    def request(path, persona, body=None, method="GET", name=None, dto=None):
        headers = {"Accept": "application/json", "Cache-Control": "no-store"}
        if persona != "visitor":
            headers["Authorization"] = "Bearer " + tokens[persona]
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(BASE + path, headers=headers, method=method,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read()
        value = json.loads(raw)
        if name:
            (args.output / (name + ".json")).write_bytes(raw if raw.endswith(b"\n") else raw + b"\n")
            manifest[:] = [item for item in manifest if item["file"] != name + ".json"]
            manifest.append(dict(file=name + ".json", captured_at=datetime.now(timezone.utc).isoformat(), persona=persona, method=method,
                                 path=path, status=status, dto=dto if status < 300 else "Error"))
            print(name, status, flush=True)
        return status, value

    for persona in ["club_owner", "coach_u18", "adult_player", "scout_verified", "visitor"]:
        # Visitor login deliberately yields no credentials. Never save auth responses.
        req = urllib.request.Request(BASE + "staging/login", method="POST",
                                     headers={"Content-Type": "application/json"},
                                     data=json.dumps({"persona": persona}).encode())
        with urllib.request.urlopen(req, timeout=30) as response:
            login = json.load(response)
        if persona != "visitor":
            tokens[persona] = login["token"]
    _, claims = request("funding/claims/me", "club_owner", name="owner-claims", dto="Phase2ClubClaimsResponse")
    program = next(c["program"] for c in claims["claims"] if c["status"] == "approved")
    pid = program["id"]
    for persona in tokens:
        request("me/club-access", persona, name=persona + "-memberships", dto="ClubMembershipsResponse")
    for path, name, dto in [
        ("features", "features", "Phase2FeatureResponse"),
        ("opportunities/features", "opportunity-features", "OpportunityFeatures"),
        ("programs/" + program["slug"], "public-club", "PublicClubResponse"),
        ("opportunities", "public-opportunities", "OpportunitiesResponse"),
        (f"opportunities?program_id={pid}", "public-club-opportunities", "OpportunitiesResponse"),
    ]:
        _, result = request(path, "visitor", name=name, dto=dto)
        if name == "public-opportunities":
            public_posts = result["opportunities"]
    request("club-directory/search", "visitor", {"q": "Quillmere", "page": 1}, "POST",
            "directory", "ClubDirectoryResponse")
    request("opportunities/" + public_posts[0]["id"], "visitor", name="public-opportunity", dto="OpportunityResponse")
    for persona in ["club_owner", "coach_u18"]:
        for suffix, dto in [("access/me", "ClubAccessResponse"), ("squads", "SquadsResponse"),
                            ("roster", "RosterResponse"), ("matches", "MatchesResponse")]:
            request(f"club/{pid}/{suffix}", persona, name=persona + "-" + suffix.replace("/", "-"), dto=dto)
    _, staff = request(f"club/{pid}/access", "club_owner", name="staff-board", dto="StaffBoardResponse")
    _, posts = request(f"club/{pid}/opportunities", "club_owner", name="club-opportunities", dto="OpportunitiesResponse")
    trial = next(p for p in posts["opportunities"] if p["type"] == "trial" and p["status"] == "published")
    _, pipeline = request(f'club/{pid}/opportunities/{trial["id"]}/applications', "club_owner",
                          name="pipeline", dto="ApplicationsResponse")
    aid = pipeline["applications"][0]["id"]
    request(f"club/{pid}/applications/{aid}", "club_owner", name="private-application", dto="ApplicationResponse")
    _, self_claims = request("me/application-claims", "adult_player", name="application-claims", dto="ApplicationClaimsResponse")
    _, mine = request("me/applications", "adult_player", name="my-applications", dto="ApplicationsResponse")
    request("me/applications/" + mine["applications"][0]["id"], "adult_player",
            name="my-application", dto="ApplicationResponse")
    request("me/applications", "scout_verified", name="scout-applications", dto="ApplicationsResponse")
    request(f"club/{pid}/staff-invites", "club_owner", {"email": "invalid", "role": "coach", "all_squads": True},
            "POST", "invalid-email-422", "StaffInviteResponse")
    for persona, box, name in [("adult_player", "inbox", "player-introductions"),
                               ("scout_verified", "sent", "scout-introductions")]:
        _, introductions = request("contact/requests?box=" + box + "&limit=50&offset=0", persona,
                                   name=name, dto="ContactRequestsResponse")
        thread = next((r for r in introductions.get("requests", []) if r.get("messaging_open")), None)
        if thread:
            request("contact/requests/" + thread["id"] + "/messages?limit=50&offset=0", persona,
                        name=persona + "-introduction-thread", dto="ContactMessagesResponse")
    if args.exercise_writes:
        now = datetime.now(timezone.utc)
        stamp = lambda days, hours=0: (now + timedelta(days=days, hours=hours)).isoformat()
        body = dict(type="trial", title="I1 contract refresh — scratch", description="Synthetic API contract capture.",
                    instructions="Contract capture only.", position_requirements="All positions", timezone="Europe/London",
                    gender_program="men", venue="Synthetic staging venue", address="Staging only",
                    closes_at=stamp(2), starts_at=stamp(3), ends_at=stamp(3, 2), capacity=10)
        status, created = request(f"club/{pid}/opportunities", "club_owner", body, "POST", "create-opportunity", "OpportunityResponse")
        if status != 201:
            raise RuntimeError("Scratch opportunity creation refused: " + str(created))
        post = created["opportunity"]
        app = None
        invite = None
        try:
            _, updated = request(f'club/{pid}/opportunities/{post["id"]}', "club_owner",
                                 {"expected_version": post["version"], "status": "published"}, "PATCH",
                                 "publish-opportunity", "OpportunityResponse")
            post = updated["opportunity"]
            request(f'club/{pid}/opportunities/{post["id"]}', "club_owner",
                    {"expected_version": post["version"], "title": ""}, "PATCH", "editor-title-422", "OpportunityResponse")
            request(f'club/{pid}/opportunities/{post["id"]}', "club_owner",
                    {"expected_version": post["version"] + 99, "status": "published"}, "PATCH", "editor-version-409", "OpportunityResponse")
            request(f'club/{pid}/opportunities/{post["id"]}', "club_owner",
                    {"expected_version": post["version"], "closes_at": stamp(91)}, "PATCH", "editor-horizon-422", "OpportunityResponse")
            _, updated = request(f'club/{pid}/opportunities/{post["id"]}', "club_owner",
                    {"expected_version": post["version"], "title": "I1 native editor contract — scratch", "timezone": "Asia/Kolkata", "squad_id": None},
                    "PATCH", "edit-opportunity", "OpportunityResponse")
            post = updated["opportunity"]
            status, submitted = request(f'opportunities/{post["id"]}/applications', "adult_player",
                                       dict(claim_id=self_claims["claims"][0]["claim_id"], position="Midfield",
                                            current_club="", contact_consent=True, client_request_id=str(uuid.uuid4())),
                                       "POST", "submit-application", "ApplicationResponse")
            if status != 201:
                raise RuntimeError("Scratch application refused: " + str(submitted))
            app = submitted["application"]
            request(f'club/{pid}/opportunities', "club_owner", name="editor-locked-posts", dto="OpportunitiesResponse")
            request(f'club/{pid}/opportunities/{post["id"]}', "club_owner",
                    {"expected_version": post["version"], "title": "Must not overwrite"}, "PATCH", "editor-terms-409", "OpportunityResponse")
            def transition(target, name, **fields):
                nonlocal app
                status, response = request(f'club/{pid}/applications/{app["id"]}/transition', "club_owner",
                                           dict(expected_version=app["version"], status=target, **fields), "POST",
                                           name, "ApplicationResponse")
                if status < 300:
                    app = response["application"]
                return status
            transition("shortlisted", "shortlist-application")
            transition("invited", "invalid-trial-422", trial_at=stamp(200), trial_venue="Staging")
            transition("invited", "invite-application", trial_at=stamp(4), trial_venue="Staging")
            request(f'club/{pid}/applications/{app["id"]}/notes', "club_owner", {"body": "Synthetic contract note."},
                    "POST", "create-note", "NoteResponse")
            _, response = request(f'me/applications/{app["id"]}/trial-response', "adult_player",
                                  {"expected_version": app["version"], "response": "accept"}, "POST",
                                  "confirm-application", "ApplicationResponse")
            app = response["application"]
            transition("invited", "reschedule-application", trial_at=stamp(5), trial_venue="Staging")
            # Scope update is a no-op for the existing synthetic coach; preserve every squad.
            person = next(p for p in staff["people"] if p["editable"] and p["role"] == "coach")
            request(f'club/{pid}/access/{person["grant_id"]}', "club_owner",
                    {k: person[k] for k in ["role", "all_squads", "squad_ids"]} | {"expected_version": person["version"]},
                    "PATCH", "update-grant", "Phase2Empty")
            _, response = request(f"club/{pid}/staff-invites", "club_owner",
                                  dict(email=f"i1-contract-{uuid.uuid4().hex[:8]}@staging.academywatch.test",
                                       role="coach", all_squads=True, squad_ids=[]), "POST", "create-staff-invite", "StaffInviteResponse")
            invite = response["invite"]
            # Real route refusal for a missing grant, without revoking a seeded person's access.
            request(f"club/{pid}/access/2147483647", "club_owner", {}, "DELETE", "delete-grant-refusal", "Phase2Empty")
        finally:
            if app:
                request(f'me/applications/{app["id"]}/withdraw', "adult_player", {"expected_version": app["version"]},
                        "POST", "withdraw-application", "ApplicationResponse")
            if invite:
                request(f'club/{pid}/staff-invites/{invite["id"]}/revoke', "club_owner", {}, "POST",
                        "revoke-staff-invite", "Phase2Empty")
            _, closed = request(f'club/{pid}/opportunities/{post["id"]}/close', "club_owner",
                    {"expected_version": post["version"], "status": "closed"}, "POST", "close-opportunity", "OpportunityResponse")
            # A second labelled scratch position exercises cancellation without changing seed data.
            status, position = request(f"club/{pid}/opportunities", "club_owner",
                    body | {"type": "position", "starts_at": None, "ends_at": None, "title": "I1 position contract — scratch"},
                    "POST", "create-position", "OpportunityResponse")
            if status == 201:
                vacancy = position["opportunity"]
                request(f'club/{pid}/opportunities/{vacancy["id"]}/close', "club_owner",
                    {"expected_version": vacancy["version"], "status": "cancelled"}, "POST", "cancel-opportunity", "OpportunityResponse")
    if args.capture_rate_limit:
        for _ in range(200):
            status, _ = request("club-directory/search", "visitor", {"q": "Quillmere"}, "POST")
            if status == 429:
                request("club-directory/search", "visitor", {"q": "Quillmere"}, "POST", "directory-rate-limit-429")
                break
        else:
            raise RuntimeError("No genuine 429 within bounded search requests")
    (args.output / "manifest.json").write_text(json.dumps(dict(
        source=BASE, captured_at=datetime.now(timezone.utc).isoformat(), fixtures=manifest), indent=2) + "\n")


if __name__ == "__main__":
    main()
