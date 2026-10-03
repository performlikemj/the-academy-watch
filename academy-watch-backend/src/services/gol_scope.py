"""Conservative frame dependencies for resident analysis names and helpers."""

import ast

HELPER_FRAMES = {
    "academy_comparison": {"tracked", "teams"},
    "first_team_graduates": {"tracked", "teams"},
    "player_status_breakdown": {"tracked", "teams"},
    "active_academy_pipeline": {"tracked", "teams", "fixture_stats", "team_profiles"},
    "academy_first_team_apps": {"tracked", "teams", "journeys"},
    "top_loan_performers": {"tracked", "fixture_stats", "teams", "team_profiles"},
    "player_career": {"journeys", "journey_entries"},
    "find_similar_players": {
        "tracked",
        "teams",
        "journeys",
        "journey_entries",
        "fixture_stats",
        "team_profiles",
        "players",
    },
    "find_hidden_talent": {
        "tracked",
        "teams",
        "journeys",
        "journey_entries",
        "fixture_stats",
        "team_profiles",
        "players",
    },
    "suggest_loan_destinations": {
        "tracked",
        "teams",
        "journeys",
        "journey_entries",
        "fixture_stats",
        "team_profiles",
        "players",
    },
}


def analysis_frame_names(code):
    """Include every loaded identifier, including aliased helper references.

    Restricted code has no dynamic namespace access. Overwritten local names
    may include extra frames, but never remove a frame that code can reference.
    """
    try:
        tree = ast.parse(code)
    except (SyntaxError, TypeError, RecursionError):
        return set()
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    return names | set().union(*(HELPER_FRAMES.get(name, set()) for name in names))
