"""Reverse RUXM2V3's canonical-name, sheet, output and exhausted-budget probes."""

# ruff: noqa: F811
from copy import deepcopy

import pytest
from src.models.follow import PlayerShadow
from src.models.funding import ClubRosterMember
from src.models.league import db
from src.models.tracked_player import TrackedPlayer
from src.models.video import VideoMatch, VideoRosterEntry
from src.services.brief_names import name_tokens
from src.services.coach_brief import brief_payload
from test_club_console import _active_suppression, _headers, _local
from test_club_console import client as client
from test_club_console import club_app as club_app
from test_club_results import rate_limited_club_app as rate_limited_club_app
from test_club_staff_access import _email, _h, _join, _match
from test_club_staff_access import env as env
from test_uxm2_club import BRIEF_REFUSAL
from test_uxm2f3_briefs import context

WITHHELD = "Expectation withheld."


@pytest.mark.parametrize("source", ["local", "tracked", "shadow", "sheet"])
@pytest.mark.parametrize("stored,typed", [("Mu\u0308ller", "Muller"), ("Ferna\u0301ndez", "Fernandez")])
def test_nfd_storage_refusal_and_worker_boundary(client, env, club_app, source, stored, typed):
    outside = db.session.get(ClubRosterMember, env["m2"])
    provider = outside.player_api_id
    if source == "local":
        local = _local(club_app.c2["users"]["a"], name=stored, birth_year=2010)
        outside.local_player_id, outside.player_api_id = local.id, None
        _active_suppression(local_player_id=local.id)
    elif source == "tracked":
        TrackedPlayer.query.filter_by(player_api_id=provider).update({"player_name": stored})
        _active_suppression(player_api_id=provider)
    elif source == "shadow":
        db.session.add(PlayerShadow(player_api_id=provider, player_name=stored))
        _active_suppression(player_api_id=provider)
    else:
        mid = _match(client, env, "sb")
        db.session.add(
            VideoRosterEntry(video_match_id=mid, jersey_number=9, club_roster_member_id=outside.id, player_name=stored)
        )
    db.session.commit()
    assert list(name_tokens([stored])) == [typed.casefold()]
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    url = f"{env['base']}/roster/{env['m1']}/brief"
    for spelling in [typed, stored]:
        body = f"{spelling} scans\nCheck shoulders"
        result = client.put(url, json={"body": body}, headers=_headers("a"))
        assert result.status_code == 422 and result.json == BRIEF_REFUSAL
        assert client.put(url, json={"body": body}, headers=_h(_email("coach"))).status_code == 200
        target = db.session.get(ClubRosterMember, env["m1"])
        worker = context(env, target, system=body)
        for payload in [worker["roster"]["102"], worker["system_brief"]]:
            assert payload["lines"] == [WITHHELD, "Check shoulders"]
            assert payload["hash"] == brief_payload(body)["hash"]
            assert spelling not in str(payload)


def test_suppressed_readable_sheet_alias_saves_like_unknown(client, env):
    outside = db.session.get(ClubRosterMember, env["m2"])
    outside.squad_id = env["sa"]
    mid = _match(client, env, "sa")
    db.session.add_all(
        [
            VideoRosterEntry(
                video_match_id=mid, jersey_number=9, club_roster_member_id=env["m1"], player_name="Known Visible"
            ),
            VideoRosterEntry(
                video_match_id=mid,
                jersey_number=10,
                club_roster_member_id=outside.id,
                player_name="Brannock Hiddenchild",
            ),
        ]
    )
    from src.services.club_access import record_coverage

    record_coverage(db.session.get(VideoMatch, mid))
    _active_suppression(player_api_id=outside.player_api_id)
    db.session.commit()
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    headers = _h(_email("coach"))
    sheet = client.get(f"{env['base']}/matches/{mid}", headers=headers)
    assert sheet.status_code == 200 and len(sheet.json["roster"]) == 1
    target = db.session.get(ClubRosterMember, env["m1"])
    url = f"{env['base']}/roster/{target.id}/brief"
    for word in ["Zzyzzx", "Brannock", "Hiddenchild"]:
        saved = client.put(url, json={"body": f"{word} scans\nCheck shoulders"}, headers=headers)
        assert saved.status_code == 200
        if word != "Zzyzzx":
            assert context(env, target)["roster"]["102"]["lines"] == [WITHHELD, "Check shoulders"]


@pytest.mark.parametrize(
    "body", ["Press high\nCheck shoulders", "Check shoulders\nPress high\nStay compact", "Press high"]
)
def test_reanalysis_keeps_stored_hash_and_expectation_positions(client, env, body, monkeypatch, tmp_path):
    import importlib
    import json
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "spike/video-analysis"))
    pipeline = importlib.import_module("qwen_match_analysis")
    # Exercise the same shipped presentation function used by PlayerReel.
    jsx = (root / "academy-watch-frontend/src/components/video/PlayerReel.jsx").read_text()
    start = jsx.index("export function briefChecksPresentation(")
    helper = jsx[start : jsx.index("\n}", start) + 2].removeprefix("export ")
    # Brief predates a newly added name, including leading/interior/all-withheld cases.
    target = db.session.get(ClubRosterMember, env["m1"])
    target.coach_brief_body = body
    outside = db.session.get(ClubRosterMember, env["m2"])
    TrackedPlayer.query.filter_by(player_api_id=outside.player_api_id).update({"player_name": "Jordan Press"})
    db.session.commit()
    for _ in range(2):
        worker = context(env, target, system=body)
        private_file = tmp_path / "brief.json"
        private_file.write_text(json.dumps(worker))
        assert pipeline._load_brief_context(private_file) == worker
        for payload in [worker["roster"]["102"], worker["system_brief"]]:
            assert payload["hash"] == brief_payload(body)["hash"]
            assert payload["lines"] == [WITHHELD if "Press" in line else line for line in body.splitlines()]
        checks = pipeline.gate_brief_checks(
            [{"expectation_index": i + 1, "verdict": "no_evidence"} for i in range(len(body.splitlines()))],
            worker["roster"]["102"]["hash"],
            [],
            (100, 100),
        )
        js = (
            helper
            + "\nconst input = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
            + (
                "const formatBriefEvidenceTime = () => null;\n"
                "process.stdout.write(JSON.stringify(briefChecksPresentation(...input)));"
            )
        )
        result = subprocess.run(
            ["node", "-e", js],
            input=json.dumps(
                [
                    {"jersey_number": 9, "brief_checks": checks},
                    [{"jersey_number": 9, "club_roster_member_id": target.id}],
                    [{"id": target.id, "brief": {"body": body, **brief_payload(body)}}],
                ]
            ),
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        presentation = json.loads(result.stdout)
        assert presentation["changed"] is False
        assert [item["expectation"] for item in presentation["items"]] == body.splitlines()
        assert [item["expectationIndex"] for item in presentation["items"]] == list(
            range(1, len(body.splitlines()) + 1)
        )


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
def test_scoped_served_analysis_does_not_disclose_private_filtering(client, env, role, monkeypatch):
    """Real worker + deterministic pipeline gate + every served club match adapter."""
    import importlib
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "spike/video-analysis"))
    pipeline = importlib.import_module("qwen_match_analysis")
    from src.services.club_access import record_coverage

    _join(client, env, role, role, squads=[env["sa"]])
    mid = _match(client, env, "sa")
    match = db.session.get(VideoMatch, mid)
    match.status = "finalized"
    entry = VideoRosterEntry(
        video_match_id=mid, jersey_number=9, club_roster_member_id=env["m1"], player_name="Known Visible"
    )
    db.session.add(entry)
    db.session.flush()
    record_coverage(match)
    outside = db.session.get(ClubRosterMember, env["m2"])
    TrackedPlayer.query.filter_by(player_api_id=outside.player_api_id).update({"player_name": "Brannock Outsidesquad"})
    _active_suppression(player_api_id=outside.player_api_id)
    db.session.commit()
    target = db.session.get(ClubRosterMember, env["m1"])
    outcomes = []
    for word in ["Zzyzzx", "Brannock"]:
        target.coach_brief_body = f"{word} scans\nCheck shoulders"
        worker = context(env, target, system=f"{word} scans")
        brief = worker["roster"]["102"]
        counts = {"brief_checks_total": 0, "brief_checks_evidence_found": 0, "brief_checks_downgraded": 0}
        checks = pipeline.gate_brief_checks(
            [
                {"expectation_index": i + 1, "verdict": "no_evidence", "evidence": None}
                for i in range(len(brief["lines"]))
            ],
            brief["hash"],
            {},
            None,
            counts,
        )
        ordinary = {"kit_color": "blue", "jersey_number": 9, "observations": ["Keeps width"], "confidence": "low"}
        analysis = {
            "player_notes": [
                ordinary | {"brief_checks": checks, "system_brief_hash": worker["system_brief"]["hash"]},
                {"kit_color": "blue", "jersey_number": 10, "observations": [], "brief_checks": checks},
            ],
            "sampling": counts | {"frames_analyzed": 4},
            "honest_limits": [
                "brief checks not produced for blue #10: invalid checks output",
                "Camera view is limited",
            ],
            "team_analysis": {"shape": "compact"},
        }
        match.capture_meta = {"qwen_analysis": analysis}
        db.session.commit()
        served = []
        for suffix in [f"matches/{mid}", "matches", f"matches/{mid}/reel", f"matches/{mid}/report"]:
            response = client.get(f"{env['base']}/{suffix}", headers=_h(_email(role)))
            assert response.status_code == 200, response.json
            served.append(response.json)
            assert "brief_checks" not in str(response.json)
            assert brief["hash"] not in str(response.json)
        owner = client.get(f"{env['base']}/matches/{mid}", headers=_headers("a"))
        assert owner.json["capture_meta"]["qwen_analysis"] == analysis
        scoped = served[0]["capture_meta"]["qwen_analysis"]
        assert scoped["player_notes"] == [ordinary]
        assert scoped["sampling"] == {"frames_analyzed": 4}
        assert scoped["honest_limits"] == ["Camera view is limited"]
        assert match.capture_meta == {"qwen_analysis": analysis}  # Projection must not mutate storage.
        outcomes.append(deepcopy(served))
    assert outcomes[0] == outcomes[1]


@pytest.mark.parametrize("writer", ["owner", "coach"])
def test_clean_save_after_twenty_refusals_on_real_app(rate_limited_club_app, monkeypatch, writer):
    from src.extensions import limiter
    from src.main import app as real_app

    fixture = rate_limited_club_app
    seeded = fixture.test_client()
    case = env.__wrapped__(fixture, seeded, monkeypatch)
    _join(seeded, case, "coach", "coach", squads=[case["sa"]])
    monkeypatch.setitem(db._app_engines, real_app, db.engines)
    for key in ["SECRET_KEY", "TESTING"]:
        monkeypatch.setitem(real_app.config, key, fixture.config[key])
    monkeypatch.setattr(limiter, "enabled", True)
    if writer == "owner":
        monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", "false")
    limiter.reset()
    headers = _headers("a") if writer == "owner" else _h(_email("coach"))
    url = f"{case['base']}/roster/{case['m1']}/brief"
    try:
        with real_app.test_client() as real:
            for i in range(20):
                response = real.put(
                    url, json={"body": "Known scans"}, headers=headers, environ_base={"REMOTE_ADDR": f"127.0.0.{i + 1}"}
                )
                assert response.status_code == 422 and response.json == BRIEF_REFUSAL
            for body, status in [("Check shoulders", 200), ("Known scans", 429), ("Stay compact", 200), (12, 400)]:
                response = real.put(url, json={"body": body}, headers=headers)
                assert response.status_code == status
                if status == 429:
                    assert response.json == {"error": "Too many brief updates. Try again later."}
                    assert int(response.headers["Retry-After"]) > 0
                    assert response.headers["Cache-Control"] == "private, no-store"
    finally:
        limiter.reset()
