"""
GOL Sandbox Executor

Executes LLM-generated pandas code in a RestrictedPython sandbox
with allowlisted builtins, no imports, and a 10-second timeout.
"""

import ctypes
import logging
import threading

import numpy as np
import pandas as pd
from RestrictedPython import compile_restricted
from RestrictedPython.Guards import safe_builtins, safer_getattr

logger = logging.getLogger(__name__)

MAX_ROWS = 100
TIMEOUT_SECONDS = 10

ALLOWED_BUILTINS = {
    **safe_builtins,
    'len': len,
    'sorted': sorted,
    'min': min,
    'max': max,
    'sum': sum,
    'round': round,
    'abs': abs,
    'int': int,
    'float': float,
    'str': str,
    'bool': bool,
    'list': list,
    'dict': dict,
    'tuple': tuple,
    'set': set,
    'zip': zip,
    'enumerate': enumerate,
    'range': range,
    'map': map,
    'filter': filter,
    'any': any,
    'all': all,
    'isinstance': isinstance,
    'type': type,
    'True': True,
    'False': False,
    'None': None,
    'print': lambda *a, **kw: None,  # no-op print
}


BIG_6 = ['Arsenal', 'Chelsea', 'Liverpool', 'Manchester United',
         'Manchester City', 'Tottenham Hotspur']


def _build_helpers(dataframes: dict) -> dict:
    """Build helper functions that operate on the loaded DataFrames.

    These run as normal Python (not RestrictedPython), so pandas is unrestricted.
    """

    def academy_comparison():
        """Big 6 academy status breakdown: first_team/on_loan/academy/released per club."""
        tracked = dataframes.get('tracked', pd.DataFrame())
        teams = dataframes.get('teams', pd.DataFrame())
        if tracked.empty or teams.empty:
            return pd.DataFrame(columns=['team', 'first_team', 'on_loan', 'academy', 'released'])

        merged = tracked.merge(teams[['id', 'name']], left_on='team_id', right_on='id', how='inner')
        merged = merged[merged['name'].isin(BIG_6)]
        if merged.empty:
            return pd.DataFrame(columns=['team', 'first_team', 'on_loan', 'academy', 'released'])

        pivot = merged.groupby(['name', 'status']).size().unstack(fill_value=0).reset_index()
        pivot = pivot.rename(columns={'name': 'team'})
        if 'first_team' in pivot.columns:
            pivot = pivot.sort_values('first_team', ascending=False)
        return pivot

    def first_team_graduates(team_name=None):
        """Players who reached the first team. Optional team_name filter (partial match)."""
        tracked = dataframes.get('tracked', pd.DataFrame())
        teams = dataframes.get('teams', pd.DataFrame())
        if tracked.empty or teams.empty:
            return pd.DataFrame(columns=['player_name', 'team', 'position', 'nationality', 'age'])

        ft = tracked[tracked['status'] == 'first_team']
        merged = ft.merge(teams[['id', 'name']], left_on='team_id', right_on='id', how='inner')
        if team_name:
            merged = merged[merged['name'].str.contains(team_name, case=False, na=False)]
        return (merged[['player_name', 'name', 'position', 'nationality', 'age']]
                .rename(columns={'name': 'team'})
                .sort_values(['team', 'player_name'])
                .reset_index(drop=True))

    def player_status_breakdown(team_name):
        """Status distribution for one team's tracked players."""
        tracked = dataframes.get('tracked', pd.DataFrame())
        teams = dataframes.get('teams', pd.DataFrame())
        if tracked.empty or teams.empty:
            return pd.DataFrame(columns=['status', 'count'])

        merged = tracked.merge(teams[['id', 'name']], left_on='team_id', right_on='id', how='inner')
        merged = merged[merged['name'].str.contains(team_name, case=False, na=False)]
        return (merged.groupby('status').size()
                .reset_index(name='count')
                .sort_values('count', ascending=False)
                .reset_index(drop=True))

    def active_academy_pipeline(team_name=None):
        """Players currently in an active academy pathway (excludes released/sold).

        Optional team_name filter (partial match). Without a filter, defaults to Big 6.
        """
        tracked = dataframes.get('tracked', pd.DataFrame())
        teams = dataframes.get('teams', pd.DataFrame())
        if tracked.empty or teams.empty:
            return pd.DataFrame(columns=['player_name', 'team', 'status', 'position', 'loan_club_name', 'age'])

        active = tracked[tracked['status'].isin(['academy', 'on_loan', 'first_team'])]
        merged = active.merge(teams[['id', 'name']], left_on='team_id', right_on='id', how='inner')
        if team_name:
            merged = merged[merged['name'].str.contains(team_name, case=False, na=False)]
        else:
            merged = merged[merged['name'].isin(BIG_6)]
        return (merged[['player_name', 'name', 'status', 'position', 'loan_club_name', 'age']]
                .rename(columns={'name': 'team'})
                .sort_values(['team', 'status', 'player_name'])
                .reset_index(drop=True))

    def academy_first_team_apps(team_name=None):
        """Graduates with first-team appearances, grouped by club. Deduplicated on player_api_id."""
        tracked = dataframes.get('tracked', pd.DataFrame())
        teams = dataframes.get('teams', pd.DataFrame())
        journeys = dataframes.get('journeys', pd.DataFrame())
        if tracked.empty or teams.empty or journeys.empty:
            return pd.DataFrame(columns=['team', 'total_graduates', 'total_first_team_apps'])

        ft = tracked[tracked['status'] == 'first_team'].drop_duplicates(subset=['player_api_id'])
        ft = ft.merge(teams[['id', 'name']], left_on='team_id', right_on='id', how='inner')
        ft = ft.merge(journeys[['player_api_id', 'total_first_team_apps']], on='player_api_id', how='left')
        ft['total_first_team_apps'] = ft['total_first_team_apps'].fillna(0).astype(int)

        if team_name:
            ft = ft[ft['name'].str.contains(team_name, case=False, na=False)]
        else:
            ft = ft[ft['name'].isin(BIG_6)]

        result = ft.groupby('name').agg(
            total_graduates=('player_api_id', 'count'),
            total_first_team_apps=('total_first_team_apps', 'sum')
        ).reset_index().rename(columns={'name': 'team'})
        return result.sort_values('total_first_team_apps', ascending=False).reset_index(drop=True)

    def top_loan_performers(season=None, limit=20):
        """Top loan players by goals this season."""
        loan_players = dataframes.get('loan_players', pd.DataFrame())
        fixture_stats = dataframes.get('fixture_stats', pd.DataFrame())
        if loan_players.empty or fixture_stats.empty:
            return pd.DataFrame(columns=['player_name', 'parent_club', 'loan_club', 'goals', 'assists', 'minutes', 'avg_rating'])

        fs = fixture_stats.copy()
        target_season = season if season else fs['season'].max()
        fs = fs[fs['season'] == target_season]

        merged = loan_players.merge(fs, on='player_api_id', how='inner')
        if merged.empty:
            return pd.DataFrame(columns=['player_name', 'parent_club', 'loan_club', 'goals', 'assists', 'minutes', 'avg_rating'])

        agg = merged.groupby(['player_api_id', 'player_name', 'parent_club', 'loan_club_name']).agg(
            goals=('goals', 'sum'),
            assists=('assists', 'sum'),
            minutes=('minutes', 'sum'),
            avg_rating=('rating', 'mean')
        ).reset_index()
        agg['avg_rating'] = agg['avg_rating'].round(2)
        agg = agg.sort_values(['goals', 'assists'], ascending=[False, False]).head(limit)
        return agg.rename(columns={
            'loan_club_name': 'loan_club'
        })[['player_name', 'parent_club', 'loan_club', 'goals', 'assists', 'minutes', 'avg_rating']].reset_index(drop=True)

    def player_career(player_name):
        """Season-by-season career for a player (partial name match)."""
        journeys = dataframes.get('journeys', pd.DataFrame())
        journey_entries = dataframes.get('journey_entries', pd.DataFrame())
        if journeys.empty or journey_entries.empty:
            return pd.DataFrame(columns=['season', 'club_name', 'level', 'appearances', 'goals', 'assists', 'minutes'])

        matches = journeys[journeys['player_name'].str.contains(player_name, case=False, na=False)]
        if matches.empty:
            return pd.DataFrame(columns=['season', 'club_name', 'level', 'appearances', 'goals', 'assists', 'minutes'])

        pid = matches.iloc[0]['player_api_id']
        entries = journey_entries[journey_entries['player_api_id'] == pid].sort_values('season')
        return entries[['season', 'club_name', 'level', 'appearances', 'goals', 'assists', 'minutes']].reset_index(drop=True)

    return {
        'academy_comparison': academy_comparison,
        'first_team_graduates': first_team_graduates,
        'player_status_breakdown': player_status_breakdown,
        'active_academy_pipeline': active_academy_pipeline,
        'academy_first_team_apps': academy_first_team_apps,
        'top_loan_performers': top_loan_performers,
        'player_career': player_career,
    }


def execute_analysis(code: str, dataframes: dict, display: str = 'table', description: str = '') -> dict:
    """
    Execute pandas code in a restricted sandbox.

    Args:
        code: Python code that must assign its result to `result`.
        dataframes: dict of name -> pd.DataFrame.
        display: Display hint from the LLM ('table', 'bar_chart', etc.).
        description: Brief description of the analysis (passed through as metadata).

    Returns:
        Dict with result_type, display, meta, and formatted data.
    """
    if not code or not code.strip():
        return {'result_type': 'error', 'error': 'No code provided', 'display': display}

    # Compile with RestrictedPython
    try:
        byte_code = compile_restricted(code, '<gol-analysis>', 'exec')
    except SyntaxError as e:
        return {'result_type': 'error', 'error': f'Syntax error: {e}', 'display': display}

    if byte_code is None:
        return {'result_type': 'error', 'error': 'Code compilation failed', 'display': display}

    # Build restricted namespace
    restricted_globals = {
        '__builtins__': ALLOWED_BUILTINS,
        '_getattr_': safer_getattr,
        '_getiter_': iter,
        '_getitem_': _guarded_getitem,
        '_write_': _default_write,
        '_inplacevar_': _inplacevar,
        'pd': pd,
        'np': np,
        **dataframes,
        **_build_helpers(dataframes),
    }

    local_ns = {}

    # Execute with thread-based timeout (signal.alarm doesn't work outside main thread)
    exec_result = [None]  # [None] = success, or [exception]

    def _run():
        try:
            exec(byte_code, restricted_globals, local_ns)  # noqa: S102
        except Exception as e:
            exec_result[0] = e

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=TIMEOUT_SECONDS)

    if thread.is_alive():
        # Thread is still running — try to kill it
        _kill_thread(thread)
        return {'result_type': 'error', 'error': 'Analysis timed out (10s limit)', 'display': display}

    if exec_result[0] is not None:
        e = exec_result[0]
        return {
            'result_type': 'error',
            'error': f'{type(e).__name__}: {e}',
            'display': display,
        }

    # Extract result
    result = local_ns.get('result')
    if result is None:
        return {
            'result_type': 'error',
            'error': 'No `result` variable set. Your code must assign to `result`.',
            'display': display,
        }

    formatted = _format_result(result)
    formatted['display'] = display
    if description:
        formatted['meta'] = {'description': description}
    return formatted


def _kill_thread(thread):
    """Best-effort kill of a daemon thread via async exception."""
    try:
        tid = thread.ident
        if tid is not None:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_ulong(tid), ctypes.py_object(SystemExit)
            )
    except Exception:
        pass  # Daemon thread will be cleaned up on process exit


def _guarded_getitem(obj, key):
    return obj[key]


def _default_write(obj):
    """RestrictedPython guard for attribute assignment on containers."""
    return obj


def _inplacevar(op, x, y):
    """Handle in-place operations (+=, -=, etc.) in RestrictedPython."""
    if op == '+=':
        return x + y
    elif op == '-=':
        return x - y
    elif op == '*=':
        return x * y
    elif op == '/=':
        return x / y
    elif op == '//=':
        return x // y
    elif op == '%=':
        return x % y
    elif op == '**=':
        return x ** y
    elif op == '&=':
        return x & y
    elif op == '|=':
        return x | y
    elif op == '^=':
        return x ^ y
    raise ValueError(f"Unsupported in-place operation: {op}")


def _format_result(result) -> dict:
    """Convert the result variable into a JSON-serializable response."""
    if isinstance(result, pd.DataFrame):
        truncated = len(result) > MAX_ROWS
        df = result.head(MAX_ROWS)
        # Convert to native Python types for JSON serialization
        rows = []
        for _, row in df.iterrows():
            rows.append([_safe_value(v) for v in row.values])
        return {
            'result_type': 'table',
            'columns': [str(c) for c in df.columns],
            'rows': rows,
            'total_rows': len(result),
            'truncated': truncated,
        }

    if isinstance(result, pd.Series):
        df = result.reset_index()
        df.columns = [str(c) for c in df.columns]
        return _format_result(df)

    if isinstance(result, (int, float, np.integer, np.floating)):
        return {'result_type': 'scalar', 'value': _safe_value(result)}

    if isinstance(result, str):
        return {'result_type': 'scalar', 'value': result}

    if isinstance(result, (list, tuple)):
        return {'result_type': 'list', 'items': [_safe_value(v) for v in result[:MAX_ROWS]]}

    if isinstance(result, dict):
        return {'result_type': 'dict', 'data': {str(k): _safe_value(v) for k, v in result.items()}}

    return {'result_type': 'scalar', 'value': str(result)}


def _safe_value(v):
    """Convert numpy/pandas types to JSON-safe Python natives."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return round(float(v), 4)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [_safe_value(i) for i in v]
    return v
