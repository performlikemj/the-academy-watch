"""Reverse the review-duel bridge, merge, group-testing and production-handler probes."""

# ruff: noqa: F811
from datetime import date
from types import SimpleNamespace

import pytest
from src.models.follow import PlayerShadow
from src.models.funding import ClubRosterMember
from src.models.league import db
from src.models.tracked_player import TrackedPlayer
from src.models.video import VideoRosterEntry
from src.workers.vision_worker import _brief_context
from test_club_console import _active_suppression, _headers, _local
from test_club_console import client as client
from test_club_console import club_app as club_app
from test_club_results import rate_limited_club_app as rate_limited_club_app
from test_club_staff_access import _email, _h, _join
from test_club_staff_access import env as env
from test_uxm2_club import BRIEF_REFUSAL


def context(case, target, system=None):
    return _brief_context(
        {
            "id": 101,
            "club_program_id": case["pid"],
            "our_kit_color": "blue",
            "club_program": SimpleNamespace(system_brief_body=system),
        },
        [{"id": 102, "club_roster_member_id": target.id, "jersey_number": 9}],
        [target],
    )


@pytest.mark.parametrize("key_form", ["local", "provider", "merged"])
@pytest.mark.parametrize("writer", ["owner", "manager"])
def test_complete_inventory_refuses_suppressed_bridge_and_survivor_aliases(client, env, club_app, key_form, writer):
    outside = db.session.get(ClubRosterMember, env["m2"])
    provider_id = outside.player_api_id
    tracked = TrackedPlayer.query.filter_by(player_api_id=provider_id).first()
    tracked.player_name = "Brannock Outsidesquad"
    tracked.birth_date = date(2010, 1, 1)
    db.session.add(PlayerShadow(player_api_id=provider_id, player_name="Shadowalias Hiddenalias"))
    local = _local(club_app.c2["users"]["a"], name="Localalias Privatealias", birth_year=2010)
    local.api_player_id = provider_id
    if key_form == "local":
        outside.player_api_id, outside.local_player_id = None, local.id
    elif key_form == "merged":
        source = _local(club_app.c2["users"]["a"], name="Oldalias Oldperson", status="merged")
        source.merged_into_local_player_id = local.id
        outside.player_api_id, outside.local_player_id = None, source.id
    _active_suppression(player_api_id=provider_id)
    db.session.commit()
    if writer != "owner":
        _join(client, env, "invmgr", "manager", all_squads=True)
    headers = _headers("a") if writer == "owner" else _h(_email("invmgr"))
    url = f"{env['base']}/roster/{env['m1']}/brief"
    assert client.put(url, json={"body": "Check shoulders"}, headers=headers).status_code == 200
    target = db.session.get(ClubRosterMember, env["m1"])
    before = (target.coach_brief_body, target.brief_updated_at, target.brief_updated_by_user_id)
    for name in ["Brannock", "Shadowalias", "Localalias", "Privatealias"]:
        result = client.put(url, json={"body": f"{name} scans early"}, headers=headers)
        assert result.status_code == 422 and result.json == BRIEF_REFUSAL
        db.session.refresh(target)
        assert (target.coach_brief_body, target.brief_updated_at, target.brief_updated_by_user_id) == before
    assert context(env, target)["roster"]["102"]["lines"] == ["Check shoulders"]
    # Stored text predating this policy is also filtered at the worker boundary.
    target.coach_brief_body = "Brannock scans\nShadowalias scans\nLocalalias scans\nCheck shoulders"
    filtered = context(env, target, system="Privatealias scans\nStay compact")
    assert filtered["roster"]["102"]["lines"] == [*["Expectation withheld."] * 3, "Check shoulders"]
    assert filtered["system_brief"]["lines"] == ["Expectation withheld.", "Stay compact"]


@pytest.mark.parametrize(
    "name,variant",
    [("Zoë Łukasz-Müller", "Lukasz"), ("Øystein", "Oystein"), ("Đanilo", "Danilo"), ("Großmann", "Grossmann")],
)
def test_supported_latin_variants_are_refused_and_removed_at_worker(client, env, name, variant):
    outside = db.session.get(ClubRosterMember, env["m2"])
    TrackedPlayer.query.filter_by(player_api_id=outside.player_api_id).update({"player_name": name})
    db.session.commit()
    url = f"{env['base']}/roster/{env['m1']}/brief"
    response = client.put(url, json={"body": f"{variant} scans"}, headers=_headers("a"))
    assert response.status_code == 422 and response.json == BRIEF_REFUSAL
    target = db.session.get(ClubRosterMember, env["m1"])
    target.coach_brief_body = f"{variant} scans\nCheck shoulders"
    assert context(env, target, system=f"{variant} scans\nStay compact")["roster"]["102"]["lines"] == [
        "Expectation withheld.",
        "Check shoulders",
    ]
    assert context(env, target, system=f"{variant} scans\nStay compact")["system_brief"]["lines"] == [
        "Expectation withheld.",
        "Stay compact",
    ]


def test_scoped_hidden_and_unknown_guesses_and_bisection_are_identical(client, env, club_app):
    outside = db.session.get(ClubRosterMember, env["m2"])
    hidden = _local(club_app.c2["users"]["a"], name="Brannock Outsidesquad", birth_year=2010)
    outside.local_player_id, outside.player_api_id = hidden.id, None
    _active_suppression(local_player_id=hidden.id)
    db.session.commit()
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    headers = _h(_email("coach"))
    url = f"{env['base']}/roster/{env['m1']}/brief"
    assert client.get(f"{env['base']}/roster/{outside.id}/profile", headers=headers).status_code == 404
    # Reverse the exact group-testing path: no subset identifies the hidden word.
    candidates = [f"Zzyzz{index}" for index in range(127)] + ["Brannock"]
    for size in [128, 64, 32, 16, 8, 4, 2, 1]:
        group = candidates[-size:]
        body = "\n".join(" ".join(group[i : i + 20]) for i in range(0, size, 20))
        response = client.put(url, json={"body": body}, headers=headers)
        assert response.status_code == 200
        assert "Brannock" not in str(context(env, db.session.get(ClubRosterMember, env["m1"])))
    outcomes = []
    for word in ["Zzyzzx", "Brannock"]:
        response = client.put(url, json={"body": f"{word} scans\nCheck shoulders"}, headers=headers)
        outcomes.append((response.status_code, set(response.json), set(response.json["member"])))
        assert response.json["member"]["brief"]["body"] == f"{word} scans\nCheck shoulders"
        assert "Brannock" not in str(context(env, db.session.get(ClubRosterMember, env["m1"])))
    assert outcomes[0] == outcomes[1]


def test_refusal_only_account_budget_and_real_app_429(rate_limited_club_app, monkeypatch):
    from src.extensions import limiter
    from src.main import app as real_app

    fixture = rate_limited_club_app
    seeded_client = fixture.test_client()
    case = env.__wrapped__(fixture, seeded_client, monkeypatch)
    _join(seeded_client, case, "coach", "coach", squads=[case["sa"]])
    _join(seeded_client, case, "allcoach", "coach", squads=[case["sa"]])
    TrackedPlayer.query.filter_by(player_api_id=db.session.get(ClubRosterMember, case["m1"]).player_api_id).update(
        {"player_name": "Insidesquad Visibleperson"}
    )
    db.session.commit()
    # Exercise src.main.app's real routes, limiter hooks, HTTP handler and
    # after_request hooks against only the disposable fixture engine.
    monkeypatch.setitem(db._app_engines, real_app, db.engines)
    for key in ["SECRET_KEY", "TESTING"]:
        monkeypatch.setitem(real_app.config, key, fixture.config[key])
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()
    client = real_app.test_client()
    url = f"{case['base']}/roster/{case['m1']}/brief"
    try:
        monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", "false")
        for _ in range(25):
            assert client.put(url, json={"body": "Check shoulders"}, headers=_headers("a")).status_code == 200
        monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", "true")
        for index in range(20):
            for body, status in [("Check shoulders", 200), ("Insidesquad scans", 422)]:
                response = client.put(
                    url,
                    json={"body": body},
                    headers=_h(_email("coach")),
                    environ_base={"REMOTE_ADDR": f"127.0.0.{index + 1}"},
                )
                assert response.status_code == status
        response = client.put(url, json={"body": "Insidesquad scans"}, headers=_h(_email("coach")))
        assert response.status_code == 429
        assert response.json == {"error": "Too many brief updates. Try again later."}
        assert int(response.headers["Retry-After"]) > 0
        assert response.headers["Cache-Control"] == "private, no-store"
        assert client.put(url, json={"body": "Check shoulders"}, headers=_h(_email("allcoach"))).status_code == 200
    finally:
        limiter.reset()


@pytest.mark.parametrize("outside_squad", [False, True])
def test_invisible_aliases_do_not_change_a_scoped_save_answer(client, env, outside_squad):
    from copy import deepcopy

    _join(client, env, "coach", "coach", squads=[env["sa"]])
    headers = _h(_email("coach"))
    url = f"{env['base']}/roster/{env['m1']}/brief"
    body = "Brannock scans\nCheck shoulders"
    before = client.put(url, json={"body": body}, headers=headers)
    outside = db.session.get(ClubRosterMember, env["m2"])
    outside.squad_id = env["sb"] if outside_squad else env["sa"]
    TrackedPlayer.query.filter_by(player_api_id=outside.player_api_id).update({"player_name": "Brannock Outsidesquad"})
    _active_suppression(player_api_id=outside.player_api_id)
    db.session.commit()
    after = client.put(url, json={"body": body}, headers=headers)
    assert before.status_code == after.status_code == 200

    def stable(response):
        payload = deepcopy(response.json)
        payload["member"]["brief"]["updated_at"] = None
        return payload

    assert stable(before) == stable(after)
    target = db.session.get(ClubRosterMember, env["m1"])
    assert context(env, target)["roster"]["102"]["lines"] == ["Expectation withheld.", "Check shoulders"]


def test_scoped_visible_roster_and_readable_match_sheet_names_are_refused(client, env):
    from src.models.video import VideoMatch
    from test_club_staff_access import _match as scoped_match

    _join(client, env, "coach", "coach", squads=[env["sa"]])
    mid = scoped_match(client, env, "sa")
    entry = VideoRosterEntry(
        video_match_id=mid, jersey_number=9, club_roster_member_id=env["m1"], player_name="Sheetalias Knownperson"
    )
    db.session.add(entry)
    # This match has established origin and only visible squad-member coverage.
    from src.services.club_access import record_coverage

    record_coverage(db.session.get(VideoMatch, mid))
    db.session.commit()
    url = f"{env['base']}/roster/{env['m1']}/brief"
    response = client.put(url, json={"body": "Sheetalias scans"}, headers=_h(_email("coach")))
    assert response.status_code == 422 and response.json == BRIEF_REFUSAL


def test_reverse_merge_alias_and_signed_shadow_names_never_reach_worker(client, env, club_app):
    # Survivor-only roster: retained old aliases must still be recognized.
    survivor = _local(club_app.c2["users"]["a"], name="Survivor Corrected")
    survivor.api_player_id = -survivor.id
    source = _local(club_app.c2["users"]["a"], name="Oldalias Oldperson", status="merged")
    source.merged_into_local_player_id = survivor.id
    db.session.add(PlayerShadow(player_api_id=-survivor.id, player_name="Signedalias Shadowperson"))
    outside = db.session.get(ClubRosterMember, env["m2"])
    outside.player_api_id, outside.local_player_id = None, survivor.id
    db.session.commit()
    target = db.session.get(ClubRosterMember, env["m1"])
    target.coach_brief_body = "Oldalias scans\nSignedalias scans\nSurvivor scans\nCheck shoulders"
    assert context(env, target)["roster"]["102"]["lines"] == [*["Expectation withheld."] * 3, "Check shoulders"]
    # Malformed historical merge cycles must terminate without losing names.
    survivor.merged_into_local_player_id = source.id
    db.session.commit()
    assert context(env, target)["roster"]["102"]["lines"] == [*["Expectation withheld."] * 3, "Check shoulders"]
