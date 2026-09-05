"""Stable club-result correction, deletion, adoption, and rollback attacks."""

from __future__ import annotations

from datetime import date
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from flask_sqlalchemy.query import Query
from sqlalchemy import event, text
from src.extensions import limiter
from src.models.league import Team, UserAccount, db
from src.models.player_match_entry import ClubResult, PlayerMatchEntry
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.models.tracked_player import TrackedPlayer
from src.routes import club as club_routes
from src.services import season_rollup_service
from src.services.account import build_account_export, delete_account
from test_club_console import (
    _active_suppression,
    _add_api_member,
    _correct_result_payload,
    _grant_program_manager,
    _headers,
    _match,
    _result_payload,
)
from test_club_console import client as client
from test_club_console import club_app as club_app


def _create(client, program_id, members, **values):
    return client.post(
        f"/api/club/{program_id}/results",
        json=_result_payload(members, **values),
        headers=_headers("a"),
    )


def _put(client, result_id, members, **values):
    result = db.session.get(ClubResult, result_id)
    payload = _correct_result_payload(result_id, _result_payload(members, **values))
    return client.put(
        f"/api/club/{result.program_id}/results/{result_id}",
        json=payload,
        headers=_headers("a"),
    )


def _snapshot():
    return {
        model.__tablename__: [
            tuple(getattr(row, column.name) for column in model.__table__.columns)
            for row in model.query.order_by(model.id).all()
        ]
        for model in (ClubResult, PlayerMatchEntry, PlayerSeasonCell, PlayerSeasonTotal)
    }


@pytest.fixture
def rate_limited_club_app(monkeypatch):
    fixture = club_app.__wrapped__(monkeypatch, SimpleNamespace(param=True))
    app = next(fixture)
    try:
        yield app
    finally:
        with pytest.raises(StopIteration):
            next(fixture)


def test_result_write_limit_is_shared_across_create_update_and_delete(rate_limited_club_app):
    client = rate_limited_club_app.test_client()
    program_id = rate_limited_club_app.c2["program_a"]
    member = _add_api_member(client, program_id)
    payload = _result_payload([member])
    limiter.reset()
    try:
        responses = [
            client.post(f"/api/club/{program_id}/results", json=payload, headers=_headers("a")) for _ in range(30)
        ]
        result_id = responses[0].json["result"]["id"]
        correction = client.put(
            f"/api/club/{program_id}/results/{result_id}",
            json=_correct_result_payload(result_id, payload),
            headers=_headers("a"),
        )
        deletion = client.delete(
            f"/api/club/{program_id}/results/{result_id}",
            json={"expected_version": 1},
            headers=_headers("a"),
        )
    finally:
        limiter.reset()

    assert responses[0].status_code == 201
    assert all(response.status_code == 200 for response in responses[1:])
    assert correction.status_code == 429
    assert correction.json == {"error": "rate_limit_exceeded"}
    assert int(correction.headers["Retry-After"]) >= 1
    assert deletion.status_code == 429
    assert deletion.json == {"error": "rate_limit_exceeded"}


def test_result_reads_take_no_writer_or_quota_locks(club_app, client, monkeypatch):
    program_id = club_app.c2["program_a"]
    member = _add_api_member(client, program_id)
    created = _create(client, program_id, [member])
    result_id = created.json["result"]["id"]

    monkeypatch.setattr(
        club_routes,
        "_lock_program_quota",
        lambda _program_id: pytest.fail("read must not take the quota advisory lock"),
    )
    monkeypatch.setattr(
        Query,
        "with_for_update",
        lambda *_args, **_kwargs: pytest.fail("read must not request FOR UPDATE"),
    )

    detail = client.get(f"/api/club/{program_id}/results/{result_id}", headers=_headers("a"))
    listing = client.get(f"/api/club/{program_id}/results", headers=_headers("a"))

    assert detail.status_code == 200
    assert listing.status_code == 200


def test_result_list_batches_page_relationship_queries(club_app, client, monkeypatch):
    program_id = club_app.c2["program_a"]
    member = _add_api_member(client, program_id)
    for day in range(1, 4):
        assert (
            _create(
                client,
                program_id,
                [member],
                match_date=f"2025-09-0{day}",
                opponent=f"Rivals {day}",
            ).status_code
            == 201
        )

    monkeypatch.setattr(
        club_routes,
        "resolve_public_adult_subject",
        lambda _player_id: pytest.fail("list serialization must use the batched subject loader"),
    )
    query_counts = []

    def count_query(*_args):
        query_counts[-1] += 1

    event.listen(db.engine, "before_cursor_execute", count_query)
    try:
        query_counts.append(0)
        one = client.get(f"/api/club/{program_id}/results?limit=1", headers=_headers("a"))
        query_counts.append(0)
        page = client.get(f"/api/club/{program_id}/results?limit=100", headers=_headers("a"))
    finally:
        event.remove(db.engine, "before_cursor_execute", count_query)

    assert one.status_code == page.status_code == 200
    assert len(one.json["results"]) == 1
    assert len(page.json["results"]) == 3
    assert abs(query_counts[0] - query_counts[1]) <= 1


def test_result_unexpected_failure_logs_traceback(club_app, client, monkeypatch, caplog):
    program_id = club_app.c2["program_a"]
    monkeypatch.setattr(club_routes, "_write_stable_result", lambda *_args: (_ for _ in ()).throw(RuntimeError("boom")))

    with caplog.at_level("ERROR", logger=club_routes.__name__):
        response = client.post(f"/api/club/{program_id}/results", json={}, headers=_headers("a"))

    record = next(item for item in caplog.records if item.message.startswith("Club result operation failed"))
    assert response.status_code == 500
    assert response.json == {"error": "result_operation_failed"}
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError


def test_date_opponent_correction_retains_entry_id_and_refreshes_old_new_seasons(club_app, client):
    program_id = club_app.c2["program_a"]
    member = _add_api_member(client, program_id)
    created = _create(client, program_id, [member], match_date="2026-07-31")
    assert created.status_code == 201
    result_id = created.json["result"]["id"]
    entry_id = created.json["matches"][0]["id"]

    corrected = _put(
        client,
        result_id,
        [member],
        match_date="2026-08-01",
        opponent="Corrected United",
        competition="U21 League",
    )
    assert corrected.status_code == 200
    assert corrected.json["matches"][0]["id"] == entry_id
    assert corrected.json["result"]["version"] == 2
    assert corrected.json["refreshed_scopes"] == [
        {"player_api_id": 7001, "season": 2025},
        {"player_api_id": 7001, "season": 2026},
    ]
    assert PlayerSeasonTotal.query.filter_by(player_api_id=7001, season=2025).count() == 0
    assert PlayerSeasonTotal.query.filter_by(player_api_id=7001, season=2026, level_group="youth").count() == 1


def test_competition_level_correction_clears_old_level_total(club_app, client):
    program_id = club_app.c2["program_a"]
    member = _add_api_member(client, program_id)
    created = _create(client, program_id, [member], competition="U21 League")
    result_id = created.json["result"]["id"]
    assert PlayerSeasonTotal.query.filter_by(player_api_id=7001, season=2025, level_group="youth").count() == 1

    corrected = _put(client, result_id, [member], competition="County Premier League")

    assert corrected.status_code == 200
    assert PlayerSeasonTotal.query.filter_by(player_api_id=7001, season=2025, level_group="youth").count() == 0
    assert PlayerSeasonTotal.query.filter_by(player_api_id=7001, season=2025, level_group="senior").count() == 1


def test_complete_replacement_removes_omitted_and_last_line_requires_delete(club_app, client):
    program_id = club_app.c2["program_a"]
    first = _add_api_member(client, program_id, 7001)
    second = _add_api_member(client, program_id, 7002)
    created = _create(client, program_id, [first, second])
    result_id = created.json["result"]["id"]
    removed = next(row["id"] for row in created.json["matches"] if row["player_api_id"] == 7002)
    corrected = _put(client, result_id, [first])
    assert corrected.status_code == 200
    assert corrected.json["removed_entry_ids"] == [removed]
    empty = client.put(
        f"/api/club/{program_id}/results/{result_id}",
        json={**_result_payload([]), "expected_version": 2, "entries": []},
        headers=_headers("a"),
    )
    assert empty.status_code == 400


def test_delete_refreshes_underlying_self_headline_and_is_repeatable(club_app, client):
    program_id = club_app.c2["program_a"]
    member = _add_api_member(client, program_id)
    self_entry = PlayerMatchEntry(
        player_api_id=7001,
        season=2025,
        source="self",
        status="self_reported",
        reported_by_user_id=club_app.c2["users"]["a"],
        match_date=date(2025, 8, 20),
        opponent="Self fixture",
        home_away="home",
        minutes=20,
        goals=0,
        assists=0,
        yellows=0,
        reds=0,
    )
    db.session.add(self_entry)
    db.session.commit()
    created = _create(client, program_id, [member])
    result_id = created.json["result"]["id"]
    deleted = client.delete(
        f"/api/club/{program_id}/results/{result_id}", json={"expected_version": 1}, headers=_headers("a")
    )
    repeated = client.delete(
        f"/api/club/{program_id}/results/{result_id}", json={"expected_version": 1}, headers=_headers("a")
    )
    assert deleted.json == repeated.json == {"deleted": True, "id": result_id, "version": 2}
    total = PlayerSeasonTotal.query.filter_by(player_api_id=7001, season=2025, level_group="senior").one()
    assert (total.primary_source, total.minutes) == ("user", 20)
    assert PlayerMatchEntry.query.filter_by(source="club").count() == 0
    replay = client.post(
        f"/api/club/{program_id}/results",
        json={
            **_result_payload([member]),
            "client_request_id": db.session.get(ClubResult, result_id).client_request_id,
        },
        headers=_headers("a"),
    )
    assert replay.json == {"error": "result_deleted"}


def test_create_replay_payload_reuse_fixture_collision_and_stale_put(club_app, client):
    program_id = club_app.c2["program_a"]
    member = _add_api_member(client, program_id)
    payload = _result_payload([member])
    first = client.post(f"/api/club/{program_id}/results", json=payload, headers=_headers("a"))
    replay = client.post(f"/api/club/{program_id}/results", json=payload, headers=_headers("a"))
    changed = client.post(f"/api/club/{program_id}/results", json={**payload, "result_for": 9}, headers=_headers("a"))
    collision_payload = {**payload, "client_request_id": str(uuid4())}
    collision = client.post(f"/api/club/{program_id}/results", json=collision_payload, headers=_headers("a"))
    assert (first.status_code, replay.status_code, changed.status_code, collision.status_code) == (201, 200, 409, 409)
    assert changed.json == {"error": "client_request_id_reused"}
    assert collision.json == {"error": "result_already_exists", "result_id": first.json["result"]["id"]}
    put = _put(client, first.json["result"]["id"], [member], result_for=3)
    stale = client.put(
        f"/api/club/{program_id}/results/{first.json['result']['id']}",
        json={**_correct_result_payload(first.json["result"]["id"], _result_payload([member])), "expected_version": 1},
        headers=_headers("a"),
    )
    assert put.status_code == 200
    assert stale.json == {"error": "result_version_conflict"}


def test_strict_request_shapes_reject_before_writes(club_app, client):
    program_id = club_app.c2["program_a"]
    member = _add_api_member(client, program_id)
    valid = _result_payload([member])
    invalid_payloads = [
        [],
        {**valid, "unknown": "field"},
        {**valid, "result_for": True},
        {**valid, "opponent": "x" * 121},
        {**valid, "home_away": "somewhere"},
        {**valid, "entries": valid["entries"] * 101},
        {
            **valid,
            "entries": [{key: value for key, value in valid["entries"][0].items() if key != "minutes"}],
        },
    ]
    responses = [
        client.post(f"/api/club/{program_id}/results", json=payload, headers=_headers("a"))
        for payload in invalid_payloads
    ]
    missing_key = client.post(
        f"/api/club/{program_id}/results",
        json={key: value for key, value in valid.items() if key != "client_request_id"},
        headers=_headers("a"),
    )

    assert [response.status_code for response in responses] == [400] * len(responses)
    assert [response.json for response in responses] == [{"error": "invalid_request"}] * len(responses)
    assert missing_key.status_code == 400
    assert missing_key.json == {"error": "client_request_id_required"}
    assert all(response.headers["Cache-Control"] == "private, no-store" for response in [*responses, missing_key])
    assert ClubResult.query.count() == PlayerMatchEntry.query.count() == 0


def test_transferred_existing_line_editable_but_removed_readd_needs_current_authority(club_app, client):
    program_id = club_app.c2["program_a"]
    player = TrackedPlayer.query.filter_by(player_api_id=7001).one()
    member = _add_api_member(client, program_id)
    created = _create(client, program_id, [member])
    result_id = created.json["result"]["id"]
    other_team = Team(team_id=9999, name="Transferred club", country="Japan", season=2026)
    db.session.add(other_team)
    db.session.flush()
    player.team_id = other_team.id
    player.current_club_api_id = 9999
    db.session.commit()
    historical = _put(client, result_id, [member], result_for=4)
    assert historical.status_code == 200
    entry_id = historical.json["matches"][0]["id"]
    removed = client.delete(
        f"/api/club/{program_id}/results/{result_id}", json={"expected_version": 2}, headers=_headers("a")
    )
    assert removed.status_code == 200
    # A different fixture proves the old roster attachment no longer grants entry-time authority.
    blocked = _create(client, program_id, [member], opponent="New Fixture")
    assert blocked.json == {"error": "player_not_affiliated", "player_api_ids": [7001]}
    assert db.session.get(PlayerMatchEntry, entry_id) is None


def test_second_manager_wrong_program_entry_and_suppressed_stub_rules(club_app, client):
    program_id = club_app.c2["program_a"]
    member = _add_api_member(client, program_id)
    _grant_program_manager(program_id, club_app.c2["users"]["b"])
    created = _create(client, program_id, [member])
    result_id = created.json["result"]["id"]
    _active_suppression(player_api_id=7001)
    detail = client.get(f"/api/club/{program_id}/results/{result_id}", headers=_headers("b"))
    assert detail.json["matches"] == [{"id": created.json["matches"][0]["id"], "unavailable": True}]
    edit = client.put(
        f"/api/club/{program_id}/results/{result_id}",
        json={**_correct_result_payload(result_id, _result_payload([member])), "expected_version": 1},
        headers=_headers("b"),
    )
    assert edit.status_code == 422
    assert edit.json == {"error": "result_player_unavailable", "entry_ids": [created.json["matches"][0]["id"]]}


def test_second_manager_can_correct_but_foreign_result_entry_is_rejected(club_app, client):
    program_a = club_app.c2["program_a"]
    program_b = club_app.c2["program_b"]
    member_a = _add_api_member(client, program_a, 7001)
    member_b = _add_api_member(client, program_b, 7002, "b")
    _grant_program_manager(program_a, club_app.c2["users"]["b"])
    result_a = _create(client, program_a, [member_a], opponent="Program A FC")
    result_b = client.post(
        f"/api/club/{program_b}/results",
        json=_result_payload([member_b], opponent="Program B FC"),
        headers=_headers("b"),
    )
    result_a_id = result_a.json["result"]["id"]
    own_entry_id = result_a.json["matches"][0]["id"]
    foreign_entry_id = result_b.json["matches"][0]["id"]

    corrected = client.put(
        f"/api/club/{program_a}/results/{result_a_id}",
        json={
            **_correct_result_payload(result_a_id, _result_payload([member_a], opponent="Program A FC")),
            "result_for": 4,
        },
        headers=_headers("b"),
    )
    injected = client.put(
        f"/api/club/{program_a}/results/{result_a_id}",
        json={
            **_correct_result_payload(result_a_id, _result_payload([member_a], opponent="Program A FC")),
            "entries": [
                {
                    **_correct_result_payload(result_a_id, _result_payload([member_a]))["entries"][0],
                    "entry_id": foreign_entry_id,
                }
            ],
        },
        headers=_headers("b"),
    )

    assert corrected.status_code == 200
    assert corrected.json["matches"][0]["id"] == own_entry_id
    assert injected.status_code == 409
    assert injected.json == {"error": "result_identity_conflict"}
    assert db.session.get(ClubResult, result_a_id).version == 2


def test_video_association_survives_reload_and_unchanged_lifecycle(club_app, client):
    program_id = club_app.c2["program_a"]
    member = _add_api_member(client, program_id)
    video = _match(program_id, status="finalized")
    video.blob_path = "matches/result.mp4"
    db.session.commit()
    created = _create(client, program_id, [member], video_match_id=video.id)
    assert created.status_code == 201
    video.status = "expired"
    db.session.commit()
    result_id = created.json["result"]["id"]
    corrected = _put(client, result_id, [member], video_match_id=video.id, result_for=3)
    detail = client.get(f"/api/club/{program_id}/results/{result_id}", headers=_headers("a"))
    assert corrected.status_code == 200
    assert detail.json["result"]["video_match_id"] == video.id
    assert detail.json["result"]["video_available"] is False


@pytest.mark.parametrize("failure", ["line_write", "first_refresh"])
def test_failure_rolls_back_header_lines_and_rollups(club_app, client, failure):
    program_id = club_app.c2["program_a"]
    member = _add_api_member(client, program_id)
    created = _create(client, program_id, [member])
    result_id = created.json["result"]["id"]
    before = _snapshot()
    target = "refresh_player_scopes" if failure == "first_refresh" else "_stable_result_payload"
    with (
        patch(f"src.routes.club.{target}", side_effect=RuntimeError("forced"))
        if failure == "line_write"
        else patch.object(season_rollup_service, target, side_effect=RuntimeError("forced"))
    ):
        response = _put(client, result_id, [member], match_date="2026-08-01", result_for=8)
    assert response.status_code == 500
    assert response.json == {"error": "result_operation_failed"}
    assert _snapshot() == before


def test_legacy_adoption_repeat_and_diagnostics(club_app):
    migration = import_module("migrations.versions.s4c1_club_results")
    program_id = club_app.c2["program_a"]
    user_id = club_app.c2["users"]["a"]
    legacy = PlayerMatchEntry(
        player_api_id=7001,
        season=2025,
        source="club",
        status="club_confirmed",
        reported_by_user_id=user_id,
        club_program_id=program_id,
        match_date=date(2025, 9, 2),
        opponent=" <b>Legacy</b> FC ",
        home_away="away",
        result_for=1,
        result_against=2,
        minutes=80,
        goals=1,
        assists=0,
        yellows=0,
        reds=0,
    )
    db.session.add(legacy)
    db.session.commit()
    with db.engine.begin() as bind:
        first = migration.backfill_legacy_results(bind)
        second = migration.backfill_legacy_results(bind)
    db.session.expire_all()
    assert first == {"adopted_results": 1, "adopted_entries": 1}
    assert second == {"adopted_results": 0, "adopted_entries": 0}
    assert db.session.get(PlayerMatchEntry, legacy.id).club_result_id
    db.session.execute(
        text("UPDATE player_match_entries SET club_program_id = NULL, club_result_id = NULL WHERE id = :id"),
        {"id": legacy.id},
    )
    db.session.commit()
    with pytest.raises(RuntimeError, match="null_program"):
        with db.engine.begin() as bind:
            migration.backfill_legacy_results(bind)


def test_account_export_and_erasure_include_result_identity_and_clear_header_actors(club_app, client):
    program_id = club_app.c2["program_a"]
    user_id = club_app.c2["users"]["a"]
    member = _add_api_member(client, program_id)
    created = _create(client, program_id, [member])
    result_id = created.json["result"]["id"]
    entry_id = created.json["matches"][0]["id"]
    user = db.session.get(UserAccount, user_id)

    exported = build_account_export(user)

    exported_entry = next(row for row in exported["match_entries"] if row["id"] == entry_id)
    assert exported_entry["club_result_id"] == result_id
    assert [row["id"] for row in exported["club_results"]] == [result_id]

    delete_account(user)
    db.session.commit()
    db.session.expire_all()
    header = db.session.get(ClubResult, result_id)
    assert header is not None
    assert (header.created_by_user_id, header.updated_by_user_id) == (None, None)
    assert db.session.get(PlayerMatchEntry, entry_id).club_result_id == result_id
