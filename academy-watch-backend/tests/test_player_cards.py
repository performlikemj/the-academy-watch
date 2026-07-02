"""Tests for player_card_service — the single cached LLM step.

The LLM client is ALWAYS mocked (monkeypatch ``_generate_card_text`` by name);
no live call ever runs. Covers: threshold + limit selection, cache reuse
(second run generates 0), dry-run makes zero LLM calls and writes nothing, the
prompt payload carries ONLY verified numbers from delta_json, Outlook-safe HTML,
failure-skips-player, and the render-seam lookups.
"""

from datetime import date

import pytest
from flask import Flask
from src.models.league import db
from src.models.pulse import PlayerCardCache, PlayerPulse
from src.services import player_card_service as cards

WINDOW_END = date(2025, 9, 8)


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(flask_app)
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


def _add_pulse(pid, score, *, name="Player", goals=0, assists=0, apps=0, minutes=0, labels=(), window_end=WINDOW_END):
    signals = {f"sig{i}": {"label": lbl, "value": True} for i, lbl in enumerate(labels)}
    db.session.add(
        PlayerPulse(
            player_api_id=pid,
            window_end=window_end,
            score=score,
            delta_json={
                "window_start": "2025-09-02",
                "window_end": window_end.isoformat(),
                "window_days": 7,
                "signals": signals,
                "window_totals": {
                    "goals": goals,
                    "assists": assists,
                    "appearances": apps,
                    "minutes": minutes,
                    "starts": 0,
                },
                "context": {
                    "name": name,
                    "position": "Attacker",
                    "parent_club": "Man Utd",
                    "current_club": "Rio FC",
                    "status": "on_loan",
                    "current_level": "Senior",
                    "absences": None,
                },
                "score": score,
            },
        )
    )
    db.session.commit()


def _mock_llm(monkeypatch, text="He bagged a brace and an assist.", *, raise_exc=False):
    """Patch the ONE LLM function; return the list of payloads it was called with."""
    calls = []

    def fake(payload, model):
        calls.append({"payload": payload, "model": model})
        if raise_exc:
            raise RuntimeError("boom")
        return text

    monkeypatch.setattr(cards, "_generate_card_text", fake)
    return calls


class TestSelection:
    def test_only_above_threshold_generate(self, app, monkeypatch):
        _add_pulse(1, 5.0)
        _add_pulse(2, 2.0)  # below default 3.0
        calls = _mock_llm(monkeypatch)
        result = cards.generate_cards(WINDOW_END)
        assert result["generated"] == 1
        assert len(calls) == 1
        assert {c.player_api_id for c in PlayerCardCache.query.all()} == {1}

    def test_threshold_param_respected(self, app, monkeypatch):
        _add_pulse(1, 5.0)
        _add_pulse(2, 3.5)
        _mock_llm(monkeypatch)
        result = cards.generate_cards(WINDOW_END, threshold=4.0)
        assert result["generated"] == 1
        assert {c.player_api_id for c in PlayerCardCache.query.all()} == {1}

    def test_limit_respected(self, app, monkeypatch):
        for pid in (1, 2, 3):
            _add_pulse(pid, 5.0 + pid)
        calls = _mock_llm(monkeypatch)
        result = cards.generate_cards(WINDOW_END, limit=2)
        assert result["generated"] == 2
        assert result["candidates_total"] == 3
        assert len(result["candidates"]) == 2
        assert len(calls) == 2
        # Highest scores first (pid 3 then 2)
        assert [c["payload"]["player"]["name"] for c in calls] == ["Player", "Player"]
        assert {c.player_api_id for c in PlayerCardCache.query.all()} == {3, 2}


class TestCacheReuse:
    def test_second_run_generates_zero(self, app, monkeypatch):
        _add_pulse(1, 5.0)
        _add_pulse(2, 6.0)
        _mock_llm(monkeypatch)
        first = cards.generate_cards(WINDOW_END)
        assert first["generated"] == 2

        calls = _mock_llm(monkeypatch)
        second = cards.generate_cards(WINDOW_END)
        assert second["generated"] == 0
        assert second["skipped_cached"] == 2
        assert len(calls) == 0  # no LLM call on the reuse run
        assert PlayerCardCache.query.count() == 2


class TestDryRun:
    def test_dry_run_no_llm_no_write(self, app, monkeypatch):
        _add_pulse(1, 5.0)
        _add_pulse(2, 6.0)
        calls = _mock_llm(monkeypatch)
        result = cards.generate_cards(WINDOW_END, dry_run=True)
        assert result["dry_run"] is True
        assert result["generated"] == 0
        assert len(calls) == 0
        assert PlayerCardCache.query.count() == 0
        assert {c["player_api_id"] for c in result["candidates"]} == {1, 2}


class TestProvenance:
    def test_payload_contains_only_verified_numbers(self, app, monkeypatch):
        _add_pulse(
            1,
            9.0,
            name="Alfie Striker",
            goals=3,
            assists=1,
            apps=2,
            minutes=170,
            labels=["First senior goal", "Promoted to first team"],
        )
        calls = _mock_llm(monkeypatch)
        cards.generate_cards(WINDOW_END)
        payload = calls[0]["payload"]
        # Numbers come verbatim from delta_json window_totals
        assert payload["stats"] == {"goals": 3, "assists": 1, "appearances": 2, "starts": 0, "minutes": 170}
        assert payload["player"]["name"] == "Alfie Striker"
        assert payload["highlights"] == ["First senior goal", "Promoted to first team"]
        # Payload shape is closed — no free-text fields leak in
        assert set(payload) == {"player", "window", "stats", "highlights"}


class TestOutput:
    def test_card_html_is_outlook_safe_and_escaped(self, app, monkeypatch):
        _add_pulse(1, 5.0)
        _mock_llm(monkeypatch, text="Goals & glory for the kid.")
        cards.generate_cards(WINDOW_END)
        row = PlayerCardCache.query.filter_by(player_api_id=1, window_end=WINDOW_END).one()
        assert row.card_html == "<p>Goals &amp; glory for the kid.</p>"
        assert row.card_text == "Goals & glory for the kid."
        assert row.model == "openai/gpt-oss-120b"

    def test_llm_output_trimmed_to_last_sentence(self, app, monkeypatch):
        _add_pulse(1, 5.0)
        _mock_llm(monkeypatch, text="A tidy brace. And a dangling frag")
        cards.generate_cards(WINDOW_END)
        row = PlayerCardCache.query.filter_by(player_api_id=1, window_end=WINDOW_END).one()
        assert row.card_text == "A tidy brace."


class TestFailureHandling:
    def test_empty_output_skips_player(self, app, monkeypatch):
        _add_pulse(1, 5.0)
        _mock_llm(monkeypatch, text="   ")
        result = cards.generate_cards(WINDOW_END)
        assert result["generated"] == 0
        assert result["failed"] == 1
        assert PlayerCardCache.query.count() == 0

    def test_exception_skips_player_no_cache_row(self, app, monkeypatch):
        _add_pulse(1, 5.0)
        _mock_llm(monkeypatch, raise_exc=True)
        result = cards.generate_cards(WINDOW_END)
        assert result["generated"] == 0
        assert result["failed"] == 1
        assert PlayerCardCache.query.count() == 0


class TestRenderSeam:
    def test_get_cards_for_window_and_latest(self, app, monkeypatch):
        _add_pulse(1, 5.0)
        _add_pulse(2, 6.0)
        _mock_llm(monkeypatch, text="Solid week.")
        cards.generate_cards(WINDOW_END)

        assert cards.latest_card_window() == WINDOW_END
        mapping = cards.get_cards_for_window(WINDOW_END)
        assert set(mapping) == {1, 2}
        assert mapping[1]["card_text"] == "Solid week."
        assert mapping[1]["card_html"] == "<p>Solid week.</p>"
        # Subset filter + empty list short-circuit
        assert set(cards.get_cards_for_window(WINDOW_END, player_api_ids=[2])) == {2}
        assert cards.get_cards_for_window(WINDOW_END, player_api_ids=[]) == {}
