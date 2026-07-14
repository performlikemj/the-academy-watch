"""Shared mapping from an API-Football player stat block to FixturePlayerStats columns.

API-Football's ``/fixtures/players`` endpoint returns one ``statistics[0]`` dict per
player. Historically each writer hand-picked a subset of fields, which left rich
columns (tackles_interceptions, tackles_blocks, passes_accuracy, dribbles_attempts,
dribbles_past, the penalty set, offsides) almost entirely NULL in prod. Every
FixturePlayerStats writer must build its stat fields through
:func:`map_player_stat_block` so the full block is persisted everywhere.

The parsing semantics mirror ``APIFootballClient._upsert_player_fixture_stats`` (the
historical reference implementation): ``or {}`` guards on nested blocks, ``or 0``
coercion for counting stats, float coercion for rating, and string coercion for pass
accuracy. Identity fields (fixture_id, player_api_id, team_api_id), the formation
fields (formation, grid, formation_position) and raw_json are owned by callers.
"""


def map_player_stat_block(stat_block: dict | None) -> dict:
    """Map an API-Football ``statistics[0]`` dict to FixturePlayerStats column values.

    Returns a dict covering every stat column of ``FixturePlayerStats``. Passing an
    empty (or ``None``) block yields the defaults: 0 for counting stats
    (minutes/goals/assists/yellows/reds), ``False`` for flags, ``None`` for the rest.
    """
    stat_block = stat_block or {}

    games = stat_block.get("games", {}) or {}
    goals_block = stat_block.get("goals", {}) or {}
    cards = stat_block.get("cards", {}) or {}
    shots = stat_block.get("shots", {}) or {}
    passes = stat_block.get("passes", {}) or {}
    tackles = stat_block.get("tackles", {}) or {}
    duels = stat_block.get("duels", {}) or {}
    dribbles = stat_block.get("dribbles", {}) or {}
    fouls = stat_block.get("fouls", {}) or {}
    penalty = stat_block.get("penalty", {}) or {}

    # Store accuracy as a string (e.g. "68%"); the API sends an int or a string.
    pass_accuracy = passes.get("accuracy")
    if pass_accuracy is not None:
        pass_accuracy = pass_accuracy if isinstance(pass_accuracy, str) else f"{pass_accuracy}%"

    # The API spells it "commited" (known API-Football typo); fall back to the
    # correct spelling in case the provider ever fixes it.
    penalty_committed = penalty.get("commited")
    if penalty_committed is None:
        penalty_committed = penalty.get("committed")

    return {
        "minutes": games.get("minutes") or 0,
        "position": games.get("position"),
        "number": games.get("number"),
        "rating": float(games.get("rating")) if games.get("rating") else None,
        "captain": games.get("captain", False),
        "substitute": games.get("substitute", False),
        "goals": goals_block.get("total") or 0,
        "assists": goals_block.get("assists") or 0,
        "goals_conceded": goals_block.get("conceded"),
        "saves": goals_block.get("saves"),
        "yellows": cards.get("yellow") or 0,
        "reds": cards.get("red") or 0,
        "shots_total": shots.get("total"),
        "shots_on": shots.get("on"),
        "passes_total": passes.get("total"),
        "passes_key": passes.get("key"),
        "passes_accuracy": pass_accuracy,
        "tackles_total": tackles.get("total"),
        "tackles_blocks": tackles.get("blocks"),
        "tackles_interceptions": tackles.get("interceptions"),
        "duels_total": duels.get("total"),
        "duels_won": duels.get("won"),
        "dribbles_attempts": dribbles.get("attempts"),
        "dribbles_success": dribbles.get("success"),
        "dribbles_past": dribbles.get("past"),
        "fouls_drawn": fouls.get("drawn"),
        "fouls_committed": fouls.get("committed"),
        "penalty_won": penalty.get("won"),
        "penalty_committed": penalty_committed,
        "penalty_scored": penalty.get("scored"),
        "penalty_missed": penalty.get("missed"),
        "penalty_saved": penalty.get("saved"),
        "offsides": stat_block.get("offsides"),
    }
