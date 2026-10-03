#!/usr/bin/env python3
"""Build the offline player-card review fixtures for the iOS app.

The match lines and their totals are NOT written by hand: raw club and
self-reported entries are run through the server's own merge
(`academy-watch-backend/src/services/match_lines.py`), so the app is shown
exactly what `GET /players/<id>/matches?view=lines` returns for those rows.

    git show origin/main:academy-watch-backend/src/services/match_lines.py > /tmp/match_lines.py
    python3 sim/build-player-card-fixtures.py --match-lines /tmp/match_lines.py

Every person, club and league is fictional (the staging story's world, the
same one the web screenshots use). Photos are generated grey silhouettes.
"""
import argparse
import datetime
import importlib.util
import json
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "AcademyWatch" / "Debug" / "ReviewFixtures"
PLAYER_ID = 900001
SEASON = 2026
LEAGUE = "Wendle & District Senior League, Premier Division"
OPPONENTS = [
    "Skerraby United", "Durnsea Juniors", "Pellowick Town", "Thrandby Wrens", "Greaveholme Town",
    "Marlowe Quay", "Fennick Rovers", "Ostley Vale", "Brackwater", "Holm St Agnes", "Wexcombe",
    "Saltern Athletic",
]
_ids = iter(range(1, 10_000))


def entry(source, match_date, opponent, **overrides):
    """One raw `player_match_entries` row, as the route hands it to the merge."""
    row = {
        "id": next(_ids), "season": SEASON, "match_date": match_date, "opponent": opponent,
        "competition": LEAGUE, "home_away": "home", "result_for": 3, "result_against": 1,
        "minutes": 90, "goals": 0, "assists": 0, "yellows": 0, "reds": 0,
        "saves": None, "goals_conceded": None,
        "source": source, "status": "club_confirmed" if source == "club" else "self_reported",
        "created_at": f"{match_date}T20:00:00",
    }
    row.update(overrides)
    return row


def both(match_date, opponent, own=None, **figures):
    """The club's row plus the player's own row for the same match."""
    return [entry("club", match_date, opponent, **figures),
            entry("self", match_date, opponent, **{**figures, **(own or {})})]


def full_season():
    """22 matches: 15 confirmed by the club, 7 only reported by the player."""
    rows = []
    for index in range(22):
        day = (datetime.date(2026, 8, 8) + datetime.timedelta(days=7 * index)).isoformat()
        figures = dict(
            home_away="away" if index % 2 else "home",
            competition="Wendleshire Senior Cup" if index % 6 == 5 else LEAGUE,
            result_for=[2, 1, 0, 3, 1, 2][index % 6], result_against=[0, 1, 2, 1, 1, 3][index % 6],
            minutes=0 if index == 9 else 64 if index % 5 == 3 else 78 if index % 7 == 6 else 90,
            goals=1 if index in (4, 15) else 0, assists=1 if index in (2, 6, 11, 13, 18) else 0,
            yellows=1 if index in (3, 8, 12, 19) else 0,
        )
        opponent = OPPONENTS[index % len(OPPONENTS)]
        if index % 3 == 2 and index != 20:
            rows.append(entry("self", day, opponent, **figures))
        elif index == 12:
            rows += both(day, opponent, own={"minutes": 90, "yellows": 0}, **figures)
        elif index % 2:
            rows += both(day, opponent, **figures)
        else:
            rows.append(entry("club", day, opponent, **figures))
    return rows


KOFI_PROFILE = {
    "player_api_id": PLAYER_ID, "self_reported": True,
    "bio": "Right-back at Quillmere Athletic. Five seasons in the first team. I like defending "
           "properly and I will overlap all day if someone covers me.",
    "positions": "RB, RWB", "preferred_foot": "right", "height_cm": 178,
    "contract_status": "under_contract", "availability": "not_looking", "languages": "English, Twi",
}
QUILLMERE = {"id": 1, "club_name": "Quillmere Athletic", "status": "club_confirmed", "season": "2026/27"}


def photo(number, name, primary=False):
    return {"id": number, "kind": "photo", "status": "approved", "public_url": f"__PC_PHOTO_{name}__",
            "is_primary": primary, "sort_order": number}


PORTRAIT = [photo(1, "portrait", True)]
KOFI = dict(name="Kofi Asante-Reid", position="Right-back", age=25)
ONE_MATCH = both("2026-09-20", "Skerraby United")

STATES = {
    "photo": dict(**KOFI, profile=KOFI_PROFILE, photos=PORTRAIT, affiliations=[QUILLMERE], rows=ONE_MATCH),
    "no-photo": dict(**KOFI, profile=KOFI_PROFILE, photos=[], affiliations=[QUILLMERE], rows=ONE_MATCH),
    "no-matches": dict(
        name="Olu Adeyemi-Clarke", position="Winger", age=22, claimed=False,
        profile={"player_api_id": PLAYER_ID, "self_reported": True, "positions": "LW, RW", "preferred_foot": "left"},
        photos=[], affiliations=[], rows=[]),
    "full-season": dict(
        name="Reuben Castellane", position="Midfielder", age=23,
        profile={**KOFI_PROFILE, "positions": "CM, DM", "height_cm": 181, "languages": "English",
                 "bio": "Central midfielder. Signed from the summer open trial."},
        photos=PORTRAIT, affiliations=[QUILLMERE], rows=full_season()),
    "mismatch": dict(
        **KOFI, profile=KOFI_PROFILE, photos=PORTRAIT, affiliations=[QUILLMERE],
        rows=both("2026-09-27", "Durnsea Juniors", own={"minutes": 90, "yellows": 0}, home_away="away",
                  result_for=1, result_against=1, minutes=74, yellows=1)
        + ONE_MATCH
        + [entry("self", "2026-09-13", "Pellowick Town", home_away="away", result_for=0, result_against=2, assists=1)]),
    "long-names": dict(
        name="Maximilian-Alexander Oluwaseun Featherstonehaugh-Abernathy", position="Attacking midfielder", age=24,
        profile={**KOFI_PROFILE, "positions": "Attacking midfielder, Second striker, Left winger",
                 "languages": "English, Yoruba, French, Portuguese", "nationality_secondary": "Nigeria",
                 "bio": "Plays between the lines."},
        photos=PORTRAIT,
        affiliations=[{**QUILLMERE, "club_name": "Quillmere Athletic & Wendleshire Community Sports Association"}],
        rows=both("2026-09-20", "Greaveholme-under-Lyne Wanderers Reserves & Development",
                  competition="Wendleshire & District Football Association Senior Challenge Invitation Cup, "
                              "Preliminary Qualifying Round (Northern Section)",
                  home_away="neutral", goals=2, assists=1, yellows=1, reds=1)
        + [entry("self", "2026-09-13", "Skerraby United", competition=None, result_for=None, result_against=None)]),
    "several-photos": dict(
        **KOFI, profile=KOFI_PROFILE,
        photos=PORTRAIT + [photo(2, "second"), photo(3, "third"),
                           {"id": 4, "kind": "photo", "status": "pending", "public_url": None},
                           {"id": 5, "kind": "photo", "status": "approved", "public_url": None}],
        affiliations=[QUILLMERE], rows=ONE_MATCH),
    "keeper": dict(
        name="Tamsin Holloway", position="Goalkeeper", age=27,
        profile={"player_api_id": PLAYER_ID, "self_reported": True, "positions": "GK", "preferred_foot": "right",
                 "height_cm": 191, "contract_status": "under_contract", "languages": "English"},
        photos=PORTRAIT, affiliations=[QUILLMERE],
        rows=[entry("club", "2026-09-27", "Durnsea Juniors", home_away="away", result_for=0, result_against=2,
                    saves=6, goals_conceded=2)]
        + both("2026-09-20", "Skerraby United", saves=4, goals_conceded=1)
        + [entry("club", "2026-09-13", "Pellowick Town", result_for=1, result_against=0, saves=3,
                 goals_conceded=0, yellows=1),
           entry("self", "2026-09-06", "Thrandby Wrens", result_for=2, result_against=2)]),
    "white-photo": dict(**KOFI, profile=KOFI_PROFILE, photos=[photo(1, "white", True)], affiliations=[QUILLMERE],
                        rows=ONE_MATCH),
    # The match-lines read fails: an error with "Try again", never "no matches".
    "read-failed": dict(**KOFI, profile=KOFI_PROFILE, photos=[], affiliations=[QUILLMERE], rows=ONE_MATCH,
                        fail=["matches"]),
    # Provider-tracked player: provider totals stay whole, the club's line is listed, never added.
    "provider": dict(
        name="Test Prospect", position="Midfielder", age=19, claimed=False, club="Test Academy",
        profile=None, photos=[], affiliations=[],
        rows=[entry("club", "2026-09-20", "Skerraby United")],
        season_stats={"appearances": 30, "minutes": 2412, "goals": 4, "assists": 6, "yellows": 3, "reds": 0,
                      "avg_rating": 7.1, "source": "api-football", "stats_coverage": "full",
                      "provenance": {"source": "journey", "primary_source": "journey"}}),
    # The season-totals read fails for a provider-tracked player: totals are built
    # from the public match log that did load.
    "totals-failed": dict(
        name="Test Prospect", position="Midfielder", age=19, claimed=False, club="Test Academy",
        profile=None, photos=[], affiliations=[], rows=[], fail=["season-stats"],
        match_rows=[
            {"id": n, "fixture_id": 7000 + n, "player_api_id": PLAYER_ID, "fixture_date": day,
             "opponent": opponent, "competition": "Test League", "loan_team_name": "Test Academy",
             "is_home": n % 2 == 0, "minutes": minutes, "goals": goals, "assists": 0, "rating": 7.0,
             "saves": None, "goals_conceded": None, "yellows": 0, "reds": 0}
            for n, (day, opponent, minutes, goals) in enumerate(
                [("2026-09-06", "Marlowe Quay", 90, 1), ("2026-09-13", "Fennick Rovers", 72, 0),
                 ("2026-09-20", "Ostley Vale", 90, 0)], start=1)]),
}


def scout_row(number, name, position, club, apps, minutes, provenance, **extra):
    row = {
        "id": 900000 + number, "player_id": 900000 + number, "player_name": name, "player_photo": None,
        "position": position, "age": 24, "nationality": "England",
        "primary_team_id": 9001, "primary_team_name": club, "primary_team_api_id": 9001,
        "loan_team_name": None, "loan_team_api_id": None, "loan_team_db_id": None, "loan_team_logo": None,
        "owner_team_id": None, "owner_team_name": None, "is_active": True, "status": "academy",
        "pathway_status": "academy", "current_level": None, "data_source": "review-fixture",
        "data_depth": "fixture", "sale_fee": None, "created_at": None, "updated_at": None,
        "appearances": apps, "goals": 0, "assists": 0, "minutes_played": minutes, "avg_rating": None,
        "goal_contributions": 0, "contributions_per90": None, "has_detailed_stats": False,
        "recent_form": [], "provenance": provenance, "contactable": True,
    }
    row.update(extra)
    return row


LONG = "Maximilian-Alexander Oluwaseun Featherstonehaugh-Abernathy"
LONG_CLUB = "Quillmere Athletic & Wendleshire Community Sports Association"
# What /scout/players returns today (the web's desk fixture): club- or
# player-entered figures must not be printed; provider-sourced rows keep them.
DESK = [
    scout_row(1, "Kofi Asante-Reid", "Right-back", "Quillmere Athletic", 1, 90, {"source": "club"}),
    scout_row(2, "Reuben Castellane", "Midfielder", "Quillmere Athletic", 15, 1238, {"source": "club"},
              player_photo="__PC_PHOTO_face__"),
    scout_row(3, "Olu Adeyemi-Clarke", "Winger", None, 0, 0, {"source": "self"}, contactable=False),
    scout_row(4, LONG, "Attacking midfielder", LONG_CLUB, 2, 180, {"source": "self"}),
    scout_row(5, "Tamsin Holloway", "Goalkeeper", "Quillmere Athletic", 3, 270, {"source": "club"}),
    scout_row(6, "Test Prospect", "Midfielder", "Test Academy", 30, 2412, {"primary_source": "journey"},
              contactable=False),
]
# The same desk once the server sends the card fields (PR #1138): an approved
# photo, the club-confirmed flag, one plain bio line and merged-lines totals.
DESK_NEXT = [
    scout_row(1, "Kofi Asante-Reid", "Right-back", "Quillmere Athletic", 1, 90, {"primary_source": "matches"},
              approved_photo_url="__PC_PHOTO_portrait__", club_confirmed=True,
              bio_line="Five seasons in the first team."),
    scout_row(2, "Reuben Castellane", "Midfielder", "Quillmere Athletic", 21, 1762, {"primary_source": "matches"},
              club_confirmed=True, bio_line="Central midfielder. Signed from the summer open trial."),
    scout_row(6, "Test Prospect", "Midfielder", "Test Academy", 30, 2412, {"primary_source": "journey"},
              contactable=False),
]


def players_payload(rows):
    return {"players": rows, "total": len(rows), "page": 1, "per_page": 20, "total_pages": 1, "season": SEASON}


def build_state(key, state, match_lines):
    club = state.get("club", "Quillmere Athletic")
    seasons = match_lines.seasons_from_entries(state["rows"])
    stats = {"player_id": PLAYER_ID, "season": "2026/2027", "appearances": 0, "minutes": 0, "goals": 0,
             "assists": 0, "avg_rating": None, "source": "local-db", "clubs": [], "provenance": None}
    if "season_stats" in state:
        stats.update(state["season_stats"])
        stats["clubs"] = [{"team_api_id": 9001, "team_name": club, "team_logo": None, "window_type": "Academy",
                           "is_current": True, **{k: stats[k] for k in ("appearances", "minutes", "goals", "assists")}}]
    claimed = state.get("claimed", True)
    return {
        "fail": state.get("fail", []),
        "profile": {
            "player_id": PLAYER_ID, "name": state["name"], "photo": None, "position": state["position"],
            "status": None, "age": state["age"], "nationality": "England", "shadow": False,
            "loan_team_name": None, "loan_team_id": None, "loan_team_logo": None,
            "parent_team_name": club, "parent_team_id": 9001, "parent_team_logo": None,
            "owner_team_name": None, "owner_team_id": None, "owner_team_logo": None, "sale_fee": None,
        },
        "showcase": {
            "player_api_id": PLAYER_ID, "profile": state["profile"], "reel": [], "verified_footage": [],
            "photos": state["photos"], "affiliations": state["affiliations"],
            "claim_status": "claimed" if claimed else "unclaimed", "contactable": claimed,
        },
        "matches": {"view": "lines", "seasons": seasons, "truncated": False},
        "season-stats": stats,
        "stats": {"matches": state.get("match_rows", []), "season": SEASON},
        "journey": {"player_id": PLAYER_ID, "source": "review-fixture", "birth_date": None, "entries": [],
                    "stints": [], "total_stints": 0},
        "followers/count": {"player_api_id": PLAYER_ID, "fans": 6, "following": False,
                            "share_url": f"https://theacademywatch.com/p/{PLAYER_ID}"},
    }


def png(path, width, height, pixel):
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixel(x, y))

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                     + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def rgb(value):
    return bytes(((value >> 16) & 255, (value >> 8) & 255, value & 255))


def silhouette(path, background, figure, width=300, height=384):
    """The web fixtures' grey silhouette (600 x 768 artwork, drawn at half size)."""
    back, fore = rgb(background), rgb(figure)
    scale = 600 / width

    def pixel(x, y):
        px, py = x * scale, y * scale
        if (px - 300) ** 2 + (py - 300) ** 2 <= 150 ** 2:
            return fore
        if py >= 500 and ((px - 300) / 290) ** 2 + ((py - 768) / 268) ** 2 <= 1:
            return fore
        return back

    png(path, width, height, pixel)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--match-lines", required=True, type=Path, help="The server's services/match_lines.py")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("match_lines", args.match_lines)
    match_lines = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(match_lines)

    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "states": {key: build_state(key, state, match_lines) for key, state in STATES.items()},
        "desk": players_payload(DESK),
        "desk-next": players_payload(DESK_NEXT),
    }
    (OUT / "player_card_states.json").write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")
    silhouette(OUT / "pc-photo-portrait.png", 0xC8C2B3, 0xA9A293)
    silhouette(OUT / "pc-photo-second.png", 0xB7C0B4, 0x8FA08C)
    silhouette(OUT / "pc-photo-third.png", 0xC9B8A6, 0xA58E78)
    silhouette(OUT / "pc-photo-face.png", 0xD8D2C4, 0xA9A293, width=148, height=148)
    png(OUT / "pc-photo-white.png", 300, 384, lambda x, y: b"\xff\xff\xff")
    for key, state in payload["states"].items():
        totals = [(season["season"], season["totals"]["matches"]) for season in state["matches"]["seasons"]]
        print(f"{key}: {totals}")


if __name__ == "__main__":
    main()
