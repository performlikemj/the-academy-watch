"""One line per match, and season totals that add up from exactly those lines.

``player_match_entries`` has no column tying a player's own report to the club's
report of the same match: a club row hangs off its ``club_results`` header, a
self row stands alone. The only shared identity is player + match date +
opponent text. This module is the single place that pairs them and totals the
result; it is pure (plain mappings in, plain dicts out) so every reader — web,
iOS, a future rollup feeder — gets the same answer.

Rules, all conservative:
- Two rows are the same match only when the date is identical and the opponent
  is identical after the club-result normalisation (trim, lower-case) plus
  collapsing runs of spaces. A different date is never merged.
- A club row confirms a match only while its status is ``club_confirmed``.
  When it does, the club's figures are the line; the player's own row is
  reduced to "matches" or "differs" and is never shown beside it or added to it.
- ``disputed`` rows stay out of lines and totals, as they already stay out of
  the season rollup.
"""

from collections.abc import Iterable, Mapping

# The player's own figures for a match. Counts are NOT NULL in storage.
FIGURE_FIELDS = ("minutes", "goals", "assists", "yellows", "reds")
# Optional figures: compared only when both reports state them.
OPTIONAL_FIGURE_FIELDS = ("saves", "goals_conceded", "result_for", "result_against")
_SUMMED_FIELDS = ("minutes", "goals", "assists")
_CARD_FIELDS = ("yellows", "reds")
_KEEPER_FIELDS = ("saves", "goals_conceded")
FULL_MATCH_MINUTES = 90


def opponent_key(opponent) -> str:
    """Match identity for an opponent label: trim, collapse spaces, lower-case."""
    return " ".join(str(opponent or "").split()).lower()


def _iso(value) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else value.isoformat()


def _recency(entry: Mapping) -> tuple:
    stamp = entry.get("updated_at") or entry.get("created_at")
    return (_iso(stamp) or "", entry.get("id") or 0)


def _latest(entries: list[Mapping]) -> Mapping | None:
    return max(entries, key=_recency) if entries else None


def _reports_agree(club: Mapping, own: Mapping) -> bool:
    if any(club.get(field) != own.get(field) for field in FIGURE_FIELDS):
        return False
    return all(
        club.get(field) == own.get(field)
        for field in OPTIONAL_FIGURE_FIELDS
        if club.get(field) is not None and own.get(field) is not None
    )


def merge_match_lines(entries: Iterable[Mapping]) -> list[dict]:
    """Collapse raw match entries into one line per match, newest first."""
    groups: dict[tuple[str, str], dict[str, list[Mapping]]] = {}
    for entry in entries:
        source, status = entry.get("source"), entry.get("status")
        if source == "club" and status == "club_confirmed":
            side = "club"
        elif source == "self" and status == "self_reported":
            side = "self"
        else:
            continue
        match_date = _iso(entry.get("match_date"))
        if not match_date:
            continue
        key = (match_date, opponent_key(entry.get("opponent")))
        groups.setdefault(key, {"club": [], "self": []})[side].append(entry)

    lines = []
    for (match_date, key), sides in groups.items():
        club, own = _latest(sides["club"]), _latest(sides["self"])
        shown = club or own
        # Only a club-confirmed line is compared with the player's own report.
        self_report = None
        if club is not None and own is not None:
            self_report = "matches" if _reports_agree(club, own) else "differs"
        lines.append(
            {
                "key": f"{match_date}|{key}",
                "season": shown.get("season"),
                "match_date": match_date,
                "opponent": shown.get("opponent"),
                # A label, not a figure: keep the player's when the club left it blank.
                "competition": shown.get("competition") or (own.get("competition") if own else None),
                "home_away": shown.get("home_away"),
                "result_for": shown.get("result_for"),
                "result_against": shown.get("result_against"),
                **{field: shown.get(field) for field in FIGURE_FIELDS},
                **{field: shown.get(field) for field in _KEEPER_FIELDS},
                "confirmation": "club_confirmed" if club is not None else "self_reported",
                "self_report": self_report,
            }
        )
    lines.sort(key=lambda line: line["key"])
    lines.sort(key=lambda line: line["match_date"], reverse=True)
    return lines


def _sum_known(lines: list[dict], field: str) -> int | None:
    known = [line[field] for line in lines if line.get(field) is not None]
    return sum(known) if known else None


def season_totals(lines: Iterable[Mapping]) -> dict:
    """Totals for exactly the given merged lines, each match counted once."""
    lines = list(lines)
    confirmed = [line for line in lines if line.get("confirmation") == "club_confirmed"]
    return {
        "matches": len(lines),
        "appearances": sum(1 for line in lines if (line.get("minutes") or 0) > 0),
        "full_matches": sum(1 for line in lines if (line.get("minutes") or 0) >= FULL_MATCH_MINUTES),
        **{field: sum(line.get(field) or 0 for line in lines) for field in _SUMMED_FIELDS},
        **{field: _sum_known(lines, field) for field in _CARD_FIELDS},
        # Unknown is not clean: cards are only "known" when every line states them.
        "cards_known": bool(lines) and all(line.get(field) is not None for line in lines for field in _CARD_FIELDS),
        **{field: _sum_known(lines, field) for field in _KEEPER_FIELDS},
        "keeper_matches": sum(1 for line in lines if any(line.get(field) is not None for field in _KEEPER_FIELDS)),
        "club_confirmed": len(confirmed),
        "self_reported_only": len(lines) - len(confirmed),
        "differing": sum(1 for line in confirmed if line.get("self_report") == "differs"),
    }


def seasons_from_entries(entries: Iterable[Mapping]) -> list[dict]:
    """Merged lines grouped by season (newest first), each with its own totals."""
    by_season: dict[int, list[dict]] = {}
    for line in merge_match_lines(entries):
        by_season.setdefault(line["season"], []).append(line)
    return [
        {"season": season, "lines": lines, "totals": season_totals(lines)}
        for season, lines in sorted(by_season.items(), key=lambda item: item[0], reverse=True)
    ]


__all__ = ["merge_match_lines", "opponent_key", "season_totals", "seasons_from_entries"]
