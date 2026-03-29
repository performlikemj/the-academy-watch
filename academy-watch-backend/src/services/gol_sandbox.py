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

    def _dedup_tracked(df):
        """Deduplicate tracked players, preferring owning-club rows over academy rows.

        When a player has multiple TrackedPlayer rows (one per academy + owning club),
        the owning-club row (data_source='owning-club') should win because it represents
        the club that currently controls the player.
        """
        if df.empty:
            return df
        out = df.copy()
        out['_prio'] = out['data_source'].map(lambda x: 0 if x == 'owning-club' else 1)
        out = (out.sort_values(['_prio', 'updated_at'], ascending=[True, False])
               .drop_duplicates(subset=['player_api_id'])
               .drop(columns=['_prio']))
        return out

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
        fixture_stats = dataframes.get('fixture_stats', pd.DataFrame())
        if tracked.empty or teams.empty:
            return pd.DataFrame(columns=['player_name', 'team', 'status', 'position', 'current_club', 'age'])

        active = _dedup_tracked(
            tracked[tracked['status'].isin(['academy', 'on_loan', 'first_team'])]
        )
        merged = active.merge(teams[['id', 'name']], left_on='team_id', right_on='id', how='inner')
        if team_name:
            merged = merged[merged['name'].str.contains(team_name, case=False, na=False)]
        else:
            merged = merged[merged['name'].isin(BIG_6)]

        # Derive current club from fixture_stats for on_loan players (more accurate)
        if not fixture_stats.empty:
            fs = fixture_stats.copy()
            max_season = fs['season'].max()
            fs = fs[fs['season'] == max_season]
            team_mode = (
                fs.groupby('player_api_id')['team_api_id']
                .agg(lambda x: x.mode().iloc[0] if not x.mode().empty else None)
            )
            merged['current_club'] = merged.apply(
                lambda row: (
                    _resolve_team_name(team_mode.get(row['player_api_id']))
                    if row['status'] == 'on_loan' and pd.notna(team_mode.get(row['player_api_id']))
                    else _resolve_team_name_or_fallback(row.get('current_club_name'))
                ), axis=1,
            )

            # Enrich position from fixture_stats when TrackedPlayer.position is null
            pos_mode = (
                fs.groupby('player_api_id')['position']
                .agg(lambda x: x.mode().iloc[0] if not x.dropna().mode().empty else None)
            )
            merged['position'] = merged.apply(
                lambda row: (
                    row['position']
                    if pd.notna(row.get('position')) and row.get('position')
                    else (pos_mode.get(row['player_api_id']) or None)
                ), axis=1,
            )
        else:
            merged['current_club'] = merged['current_club_name'].apply(_resolve_team_name_or_fallback)

        return (merged[['player_api_id', 'player_name', 'name', 'status', 'position', 'current_club', 'age']]
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

        ft = _dedup_tracked(tracked[tracked['status'] == 'first_team'])
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
        """Top loan players by goals this season. Deduplicates multi-academy players."""
        tracked = dataframes.get('tracked', pd.DataFrame())
        fixture_stats = dataframes.get('fixture_stats', pd.DataFrame())
        if tracked.empty or fixture_stats.empty:
            return pd.DataFrame(columns=['player_name', 'parent_club', 'loan_club', 'goals', 'assists', 'minutes', 'avg_rating'])

        # Dedup FIRST (owning-club row wins), THEN filter to on-loan
        deduped = _dedup_tracked(tracked)
        loan = deduped[deduped['status'] == 'on_loan'].copy()

        fs = fixture_stats.copy()
        target_season = season if season else fs['season'].max()
        fs = fs[fs['season'] == target_season]

        # Use current_club_name from tracked data as loan club (not fixture_stats team)
        loan['loan_club'] = loan['current_club_name'].apply(_resolve_team_name_or_fallback)

        merged = loan.merge(fs, on='player_api_id', how='inner')
        if merged.empty:
            return pd.DataFrame(columns=['player_name', 'parent_club', 'loan_club', 'goals', 'assists', 'minutes', 'avg_rating'])

        agg = merged.groupby(['player_api_id', 'player_name', 'parent_club', 'loan_club']).agg(
            goals=('goals', 'sum'),
            assists=('assists', 'sum'),
            minutes=('minutes', 'sum'),
            avg_rating=('rating', 'mean'),
        ).reset_index()
        agg['avg_rating'] = agg['avg_rating'].round(2)

        # Filter out players where parent_club == loan_club (not actually on loan elsewhere)
        agg = agg[agg['parent_club'] != agg['loan_club']]

        agg = agg.sort_values(['goals', 'assists'], ascending=[False, False]).head(limit)
        return agg[['player_api_id', 'player_name', 'parent_club', 'loan_club', 'goals', 'assists', 'minutes', 'avg_rating']].reset_index(drop=True)

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
        entries = entries.copy()
        entries['player_api_id'] = pid
        return entries[['player_api_id', 'season', 'club_name', 'level', 'appearances', 'goals', 'assists', 'minutes']].reset_index(drop=True)

    # ── Scouting helpers ──────────────────────────────────────────────
    # Techniques inspired by open-source football analytics:
    # - Edd Webster's football_analytics (MIT) — PCA clustering approach
    # - Andrew Rowlinson's outliers-football (MIT) — outlier detection concept
    # - Nuno Felix's scouting-talent-in-portugal-app (MIT) — position grading
    # Standard PCA/z-score techniques; no code copied directly.

    # Per-position stat weights for talent detection
    _POSITION_METRICS = {
        'D': ['tackles_p90', 'interceptions_p90', 'blocks_p90', 'duel_win_rate', 'avg_rating'],
        'M': ['key_passes_p90', 'assists_p90', 'tackles_p90', 'dribbles_p90', 'avg_rating'],
        'F': ['goals_p90', 'shots_on_p90', 'assists_p90', 'dribbles_p90', 'avg_rating'],
    }

    # All per-90 feature columns used by PCA similarity
    _FEATURE_COLS = [
        'goals_p90', 'assists_p90', 'shots_p90', 'shots_on_p90',
        'passes_p90', 'key_passes_p90', 'tackles_p90', 'blocks_p90',
        'interceptions_p90', 'duels_p90', 'duel_win_rate',
        'dribbles_p90', 'fouls_drawn_p90', 'fouls_committed_p90', 'avg_rating',
    ]

    def _compute_per90_stats(fs_df, season=None, min_minutes=450, player_ids=None):
        """Aggregate fixture_stats to per-90-minute rates per player.

        Internal utility — not exposed to the LLM sandbox.
        """
        fs = fs_df.copy()
        if season is not None:
            fs = fs[fs['season'] == season]
        else:
            max_season = fs['season'].max()
            if pd.notna(max_season):
                fs = fs[fs['season'] == max_season]

        if player_ids is not None:
            fs = fs[fs['player_api_id'].isin(player_ids)]

        # Exclude goalkeepers
        fs = fs[fs['position'] != 'G']

        # Aggregate per player
        agg = fs.groupby('player_api_id').agg(
            total_minutes=('minutes', 'sum'),
            total_goals=('goals', 'sum'),
            total_assists=('assists', 'sum'),
            total_shots=('shots_total', 'sum'),
            total_shots_on=('shots_on', 'sum'),
            total_passes=('passes_total', 'sum'),
            total_key_passes=('passes_key', 'sum'),
            total_tackles=('tackles_total', 'sum'),
            total_blocks=('tackles_blocks', 'sum'),
            total_interceptions=('tackles_interceptions', 'sum'),
            total_duels=('duels_total', 'sum'),
            total_duels_won=('duels_won', 'sum'),
            total_dribbles=('dribbles_success', 'sum'),
            total_fouls_drawn=('fouls_drawn', 'sum'),
            total_fouls_committed=('fouls_committed', 'sum'),
            avg_rating=('rating', 'mean'),
            position=('position', lambda x: x.mode().iloc[0] if not x.mode().empty else 'M'),
            appearances=('fixture_id', 'nunique'),
        ).reset_index()

        # Filter minimum minutes
        agg = agg[agg['total_minutes'] >= min_minutes].copy()
        if agg.empty:
            return agg

        mins = agg['total_minutes']
        agg['goals_p90'] = (agg['total_goals'] / mins * 90).round(3)
        agg['assists_p90'] = (agg['total_assists'] / mins * 90).round(3)
        agg['shots_p90'] = (agg['total_shots'] / mins * 90).round(3)
        agg['shots_on_p90'] = (agg['total_shots_on'] / mins * 90).round(3)
        agg['passes_p90'] = (agg['total_passes'] / mins * 90).round(3)
        agg['key_passes_p90'] = (agg['total_key_passes'] / mins * 90).round(3)
        agg['tackles_p90'] = (agg['total_tackles'] / mins * 90).round(3)
        agg['blocks_p90'] = (agg['total_blocks'] / mins * 90).round(3)
        agg['interceptions_p90'] = (agg['total_interceptions'] / mins * 90).round(3)
        agg['duels_p90'] = (agg['total_duels'] / mins * 90).round(3)
        agg['duel_win_rate'] = np.where(
            agg['total_duels'] > 0,
            (agg['total_duels_won'] / agg['total_duels']).round(3),
            0.0,
        )
        agg['dribbles_p90'] = (agg['total_dribbles'] / mins * 90).round(3)
        agg['fouls_drawn_p90'] = (agg['total_fouls_drawn'] / mins * 90).round(3)
        agg['fouls_committed_p90'] = (agg['total_fouls_committed'] / mins * 90).round(3)
        agg['avg_rating'] = agg['avg_rating'].round(2)

        return agg

    def _resolve_player_name(player_api_id):
        """Look up a readable name for a player_api_id across available DataFrames."""
        for df_name in ('tracked', 'journeys', 'players'):
            df = dataframes.get(df_name, pd.DataFrame())
            if df.empty:
                continue
            match = df[df['player_api_id'] == player_api_id]
            if not match.empty:
                return match.iloc[0]['player_name']
        return str(player_api_id)

    def _resolve_team_name(team_api_id):
        """Look up a team name from team_api_id.

        Checks teams table first (current season), then team_profiles
        (canonical info cached from API-Football lookups).
        """
        if pd.isna(team_api_id):
            return ''
        try:
            tid = int(team_api_id)
        except (TypeError, ValueError):
            return str(team_api_id)

        # 1. Teams table (current season, explicitly tracked)
        teams = dataframes.get('teams', pd.DataFrame())
        if not teams.empty:
            match = teams[teams['team_id'] == tid]
            if not match.empty:
                return match.iloc[0]['name']

        # 2. TeamProfile table (canonical, no season filter)
        profiles = dataframes.get('team_profiles', pd.DataFrame())
        if not profiles.empty:
            match = profiles[profiles['team_id'] == tid]
            if not match.empty:
                return match.iloc[0]['name']

        # 3. Centralized resolver (DB + API fallback, caches to TeamProfile)
        try:
            from src.utils.team_resolver import resolve_team_name as _central_resolve
            return _central_resolve(tid)
        except Exception:
            return f'Team {tid}'

    def _resolve_team_name_or_fallback(value):
        """Resolve a current_club_name that might be a raw API ID or a real name."""
        if not value or (isinstance(value, float) and pd.isna(value)):
            return ''
        s = str(value).strip()
        if not s:
            return ''
        # If the value looks like a raw numeric ID, try to resolve it
        try:
            tid = int(s)
            return _resolve_team_name(tid)
        except (TypeError, ValueError):
            return s

    def _find_similar_via_journey(target_pid, per90_fixture, season, position, limit):
        """Fallback similarity search using journey_entries when fixture_stats unavailable.

        Builds reduced per-90 features (goals, assists) from season aggregates and
        compares against the fixture_stats-based pool.
        """
        je = dataframes.get('journey_entries', pd.DataFrame())
        tracked = dataframes.get('tracked', pd.DataFrame())
        empty = pd.DataFrame(columns=[
            'player_name', 'similarity', 'position', 'team',
            'goals_p90', 'assists_p90', 'avg_rating', 'minutes', 'note',
        ])

        if je.empty:
            return empty

        # Get target's latest season from journey_entries
        target_je = je[je['player_api_id'] == target_pid].copy()
        if target_je.empty:
            return empty

        target_season = season if season else target_je['season'].max()
        target_row = target_je[target_je['season'] == target_season]
        if target_row.empty:
            # Try any season
            target_row = target_je.sort_values('season', ascending=False).head(1)

        # Aggregate target's season stats (may have multiple entries per season)
        t_goals = target_row['goals'].sum()
        t_assists = target_row['assists'].sum()
        t_minutes = target_row['minutes'].sum()

        if t_minutes < 90:
            return empty

        t_goals_p90 = round(t_goals / t_minutes * 90, 3)
        t_assists_p90 = round(t_assists / t_minutes * 90, 3)

        # Get target position from tracked or journey level
        target_pos = position
        if not target_pos and not tracked.empty:
            t_match = tracked[tracked['player_api_id'] == target_pid]
            if not t_match.empty:
                pos_raw = t_match.iloc[0].get('position', '')
                pos_map = {'Goalkeeper': 'G', 'Defender': 'D', 'Midfielder': 'M', 'Attacker': 'F'}
                target_pos = pos_map.get(pos_raw, pos_raw)

        # Use the per90_fixture pool (players with fixture_stats) as comparison base.
        # Compare using the reduced feature set (goals_p90, assists_p90, avg_rating).
        pool = per90_fixture.copy()
        if target_pos and target_pos in ('D', 'M', 'F'):
            pos_pool = pool[pool['position'] == target_pos]
            if len(pos_pool) >= 3:
                pool = pos_pool

        reduced_features = ['goals_p90', 'assists_p90', 'avg_rating']
        available = [c for c in reduced_features if c in pool.columns]
        if not available:
            return empty

        # Build feature matrix for pool
        X_pool = pool[available].fillna(0).values.astype(float)

        # Build target vector from journey_entries
        target_vec = np.array([t_goals_p90, t_assists_p90, 0.0])  # no rating from journey
        # Only use features that are available
        target_vec = target_vec[:len(available)]

        # Z-score normalise
        means = np.nanmean(X_pool, axis=0)
        stds = np.nanstd(X_pool, axis=0)
        stds[stds == 0] = 1.0
        X_norm = (X_pool - means) / stds
        target_norm = (target_vec - means) / stds

        # Euclidean distance (no PCA needed with only 2-3 features)
        dists = np.linalg.norm(X_norm - target_norm, axis=1)
        max_dist = dists.max() if dists.max() > 0 else 1.0
        similarity = (100 * (1 - dists / max_dist)).round(1)

        pool = pool.copy()
        pool['similarity'] = similarity
        result = pool.nlargest(limit, 'similarity')

        result['player_name'] = result['player_api_id'].apply(_resolve_player_name)

        fixture_stats = dataframes.get('fixture_stats', pd.DataFrame())
        fs = fixture_stats.copy()
        if not fs.empty:
            fs_season = season if season else fs['season'].max()
            fs = fs[fs['season'] == fs_season]
            team_mode = (
                fs.groupby('player_api_id')['team_api_id']
                .agg(lambda x: x.mode().iloc[0] if not x.mode().empty else None)
            )
            result['team'] = result['player_api_id'].map(team_mode).apply(
                lambda x: _resolve_team_name(x) if pd.notna(x) else 'Unknown'
            )
        else:
            result['team'] = 'Unknown'

        result['note'] = 'based on season aggregates (limited stats)'
        cols = ['player_api_id', 'player_name', 'similarity', 'position', 'team',
                'goals_p90', 'assists_p90', 'avg_rating', 'total_minutes', 'note']
        out_cols = [c for c in cols if c in result.columns]
        out = result[out_cols].reset_index(drop=True)
        if 'total_minutes' in out.columns:
            out = out.rename(columns={'total_minutes': 'minutes'})
        return out

    def find_similar_players(player_name, position=None, season=None, limit=10, min_minutes=450):
        """Find players with similar statistical profiles using PCA.

        Args:
            player_name: Partial name match for the target player.
            position: Filter to 'D', 'M', or 'F'. Defaults to same as target.
            season: Season year (int). Defaults to latest.
            limit: Number of similar players to return.
            min_minutes: Minimum minutes played.

        Returns:
            DataFrame with player_name, similarity_score, position, team,
            and key per-90 stats.
        """
        fixture_stats = dataframes.get('fixture_stats', pd.DataFrame())
        tracked = dataframes.get('tracked', pd.DataFrame())
        journeys = dataframes.get('journeys', pd.DataFrame())
        empty = pd.DataFrame(columns=[
            'player_name', 'similarity', 'position', 'team',
            'goals_p90', 'assists_p90', 'avg_rating', 'minutes',
        ])

        if fixture_stats.empty:
            return empty

        # Compute per-90 stats
        per90 = _compute_per90_stats(fixture_stats, season=season, min_minutes=min_minutes)
        if per90.empty:
            return empty

        # Resolve target player — search across tracked + journeys
        target_pid = None
        for src in (tracked, journeys):
            if src.empty:
                continue
            matches = src[src['player_name'].str.contains(player_name, case=False, na=False)]
            if not matches.empty:
                target_pid = matches.iloc[0]['player_api_id']
                break

        if target_pid is None:
            return empty

        if target_pid not in per90['player_api_id'].values:
            # Target exists but has insufficient stats — relax min_minutes for target only
            per90_relaxed = _compute_per90_stats(
                fixture_stats, season=season, min_minutes=90, player_ids=[target_pid],
            )
            if per90_relaxed.empty:
                # Fallback: use journey_entries season aggregates when no fixture_stats
                return _find_similar_via_journey(target_pid, per90, season, position, limit)
            per90 = pd.concat([per90, per90_relaxed]).drop_duplicates(subset=['player_api_id'])

        # Filter by position
        target_pos = per90.loc[per90['player_api_id'] == target_pid, 'position'].iloc[0]
        filter_pos = position if position else target_pos
        per90_pos = per90[per90['position'] == filter_pos].copy()
        if len(per90_pos) < 3:
            per90_pos = per90.copy()  # Fall back to all positions if too few

        # Build feature matrix
        features = [c for c in _FEATURE_COLS if c in per90_pos.columns]
        X = per90_pos[features].fillna(0).values.astype(float)

        # Z-score normalise
        means = np.nanmean(X, axis=0)
        stds = np.nanstd(X, axis=0)
        stds[stds == 0] = 1.0  # Avoid division by zero
        X_norm = (X - means) / stds

        # PCA via SVD — keep components for 90% variance
        U, S, Vt = np.linalg.svd(X_norm, full_matrices=False)
        var_explained = np.cumsum(S ** 2) / np.sum(S ** 2)
        k = int(np.searchsorted(var_explained, 0.90) + 1)
        k = min(k, len(S))
        X_pca = X_norm @ Vt[:k].T

        # Find target index in filtered data
        pids = per90_pos['player_api_id'].values
        target_mask = pids == target_pid
        if not target_mask.any():
            return empty
        target_idx = np.where(target_mask)[0][0]

        # Euclidean distance
        dists = np.linalg.norm(X_pca - X_pca[target_idx], axis=1)
        max_dist = dists.max() if dists.max() > 0 else 1.0
        similarity = (100 * (1 - dists / max_dist)).round(1)

        per90_pos = per90_pos.copy()
        per90_pos['similarity'] = similarity

        # Exclude target, sort, take top N
        result = per90_pos[per90_pos['player_api_id'] != target_pid].copy()
        result = result.nlargest(limit, 'similarity')

        # Attach readable names and team
        result['player_name'] = result['player_api_id'].apply(_resolve_player_name)

        # Get most common team from fixture_stats
        fs = fixture_stats.copy()
        if season is None:
            fs = fs[fs['season'] == fs['season'].max()]
        else:
            fs = fs[fs['season'] == season]
        team_mode = (
            fs.groupby('player_api_id')['team_api_id']
            .agg(lambda x: x.mode().iloc[0] if not x.mode().empty else None)
        )
        result['team'] = result['player_api_id'].map(team_mode).apply(
            lambda x: _resolve_team_name(x) if pd.notna(x) else 'Unknown'
        )

        cols = ['player_api_id', 'player_name', 'similarity', 'position', 'team',
                'goals_p90', 'assists_p90', 'avg_rating', 'total_minutes']
        out_cols = [c for c in cols if c in result.columns]
        out = result[out_cols].reset_index(drop=True)
        if 'total_minutes' in out.columns:
            out = out.rename(columns={'total_minutes': 'minutes'})
        return out

    def find_hidden_talent(position=None, season=None, limit=15, min_minutes=450, loan_only=True):
        """Identify statistical outliers — players performing above expectations.

        Uses position-adjusted z-scores to find players whose per-90 stats are
        significantly above the mean for their position group. Each flagged player
        gets a human-readable explanation of which stats make them stand out.

        Args:
            position: Filter to 'D', 'M', or 'F'. None for all outfield positions.
            season: Season year (int). Defaults to latest.
            limit: Max number of results.
            min_minutes: Minimum minutes played.
            loan_only: If True, only include players tracked as on_loan.

        Returns:
            DataFrame with player_name, talent_score, grade, position, team,
            league, standout_stats, and key per-90 metrics.
        """
        fixture_stats = dataframes.get('fixture_stats', pd.DataFrame())
        tracked = dataframes.get('tracked', pd.DataFrame())
        empty = pd.DataFrame(columns=[
            'player_name', 'talent_score', 'grade', 'position', 'team',
            'league', 'standout_stats', 'goals_p90', 'assists_p90', 'avg_rating',
        ])

        if fixture_stats.empty:
            return empty

        # Determine player scope
        player_ids = None
        if loan_only and not tracked.empty:
            loan = _dedup_tracked(tracked[tracked['status'] == 'on_loan'])
            player_ids = set(loan['player_api_id'].tolist())
            if not player_ids:
                return empty

        per90 = _compute_per90_stats(fixture_stats, season=season, min_minutes=min_minutes)
        if per90.empty:
            return empty

        # When loan_only, compute z-scores against ALL players but only return loan players.
        # This way we measure loan players against the broader population.
        if player_ids is not None:
            per90_all = per90.copy()
            per90_loan = per90[per90['player_api_id'].isin(player_ids)].copy()
        else:
            per90_all = per90.copy()
            per90_loan = per90.copy()

        positions = [position] if position else ['D', 'M', 'F']
        results = []

        for pos in positions:
            metrics = _POSITION_METRICS.get(pos, _POSITION_METRICS['M'])
            pool = per90_all[per90_all['position'] == pos]
            candidates = per90_loan[per90_loan['position'] == pos]

            if pool.empty or candidates.empty or len(pool) < 5:
                continue
            candidates = candidates.copy()

            # Compute z-scores against full pool
            for m in metrics:
                if m not in pool.columns:
                    continue
                col_mean = pool[m].mean()
                col_std = pool[m].std()
                if col_std == 0 or pd.isna(col_std):
                    candidates[f'{m}_z'] = 0.0
                else:
                    candidates[f'{m}_z'] = ((candidates[m] - col_mean) / col_std).round(2)

            # Talent score = mean of positive z-scores only
            z_cols = [f'{m}_z' for m in metrics if f'{m}_z' in candidates.columns]
            if not z_cols:
                continue

            z_matrix = candidates[z_cols].values
            # Clamp negatives to 0 — we only reward above-average dimensions
            z_positive = np.clip(z_matrix, 0, None)
            talent_scores = np.nanmean(z_positive, axis=1).round(2)
            candidates = candidates.copy()
            candidates['talent_score'] = talent_scores

            # Build standout_stats explanation
            def _explain(row):
                parts = []
                for m in metrics:
                    z_col = f'{m}_z'
                    if z_col in row.index and row[z_col] >= 1.0:
                        label = m.replace('_p90', '').replace('_', ' ')
                        parts.append(f"{label}: {row[z_col]:+.1f} SD")
                return ', '.join(parts) if parts else 'above average across multiple metrics'
            candidates['standout_stats'] = candidates.apply(_explain, axis=1)

            # Grade (S/A/B/C/D)
            def _grade(score):
                if score >= 2.5:
                    return 'S'
                if score >= 2.0:
                    return 'A'
                if score >= 1.5:
                    return 'B'
                if score >= 1.0:
                    return 'C'
                if score >= 0.5:
                    return 'D'
                return 'F'
            candidates['grade'] = candidates['talent_score'].apply(_grade)

            # Only keep players with talent_score >= 0.5
            candidates = candidates[candidates['talent_score'] >= 0.5]
            results.append(candidates)

        if not results:
            return empty

        combined = pd.concat(results, ignore_index=True)
        combined = combined.nlargest(limit, 'talent_score')

        # Attach names and teams
        combined['player_name'] = combined['player_api_id'].apply(_resolve_player_name)

        fs = fixture_stats.copy()
        target_season = season if season else fs['season'].max()
        fs = fs[fs['season'] == target_season]
        team_mode = (
            fs.groupby('player_api_id')['team_api_id']
            .agg(lambda x: x.mode().iloc[0] if not x.mode().empty else None)
        )
        combined['team'] = combined['player_api_id'].map(team_mode).apply(
            lambda x: _resolve_team_name(x) if pd.notna(x) else 'Unknown'
        )

        # League from competition_name if available
        if 'competition_name' in fs.columns:
            league_mode = (
                fs.groupby('player_api_id')['competition_name']
                .agg(lambda x: x.mode().iloc[0] if not x.mode().empty else None)
            )
            combined['league'] = combined['player_api_id'].map(league_mode).fillna('Unknown')
        else:
            combined['league'] = 'Unknown'

        cols = ['player_api_id', 'player_name', 'talent_score', 'grade', 'position', 'team',
                'league', 'standout_stats', 'goals_p90', 'assists_p90', 'avg_rating']
        out_cols = [c for c in cols if c in combined.columns]
        return combined[out_cols].reset_index(drop=True)

    def suggest_loan_destinations(player_name, season=None, limit=5):
        """Suggest clubs where a player could go on loan based on position need and tactical fit.

        Analyses team formations, positional depth, and playing style to recommend
        clubs where the player would get meaningful minutes and fit tactically.

        Args:
            player_name: Partial name match for the target player.
            season: Season year. Defaults to latest.
            limit: Number of suggestions.

        Returns:
            DataFrame with team_name, league, formation, fit_score, reasoning.
        """
        fixture_stats = dataframes.get('fixture_stats', pd.DataFrame())
        tracked = dataframes.get('tracked', pd.DataFrame())
        journeys = dataframes.get('journeys', pd.DataFrame())
        teams = dataframes.get('teams', pd.DataFrame())
        empty = pd.DataFrame(columns=['team_name', 'league', 'formation', 'fit_score', 'reasoning'])

        if fixture_stats.empty:
            return empty

        # Find target player
        target_pid = None
        parent_team_ids = set()
        for src in (tracked, journeys):
            if src.empty:
                continue
            matches = src[src['player_name'].str.contains(player_name, case=False, na=False)]
            if not matches.empty:
                target_pid = matches.iloc[0]['player_api_id']
                break

        if target_pid is None:
            return empty

        # Get parent club IDs to exclude
        if not tracked.empty:
            parent_rows = tracked[tracked['player_api_id'] == target_pid]
            if not parent_rows.empty:
                for _, row in parent_rows.iterrows():
                    tid = row.get('team_id')
                    if pd.notna(tid):
                        t_match = teams[teams['id'] == int(tid)]
                        if not t_match.empty:
                            parent_team_ids.add(int(t_match.iloc[0]['team_id']))

        fs = fixture_stats.copy()
        target_season = season if season else fs['season'].max()
        fs = fs[fs['season'] == target_season]

        if fs.empty:
            return empty

        # Get player's per-90 stats and most common formation position
        player_fs = fs[fs['player_api_id'] == target_pid]
        per90_player = _compute_per90_stats(fixture_stats, season=season, min_minutes=90,
                                            player_ids=[target_pid])

        if per90_player.empty:
            return empty

        player_pos = per90_player.iloc[0]['position']  # D/M/F

        # Player's most common formation_position (e.g. CAM, LB, RW)
        fp_series = player_fs['formation_position'].dropna()
        player_fp = fp_series.mode().iloc[0] if not fp_series.empty else None

        # Player style profile (per-90 stats normalised)
        player_stats = per90_player.iloc[0]
        player_is_creative = (
            player_stats.get('key_passes_p90', 0) > 1.0 or
            player_stats.get('assists_p90', 0) > 0.15
        )
        player_is_physical = (
            player_stats.get('duels_p90', 0) > 5.0 or
            player_stats.get('tackles_p90', 0) > 2.0
        )
        player_is_direct = player_stats.get('dribbles_p90', 0) > 1.5

        # ── Build club profiles ──
        # Exclude parent clubs and the player's current team
        team_ids = fs['team_api_id'].unique()
        team_ids = [t for t in team_ids if t not in parent_team_ids]

        club_rows = []
        for t_id in team_ids:
            t_fs = fs[fs['team_api_id'] == t_id]
            if len(t_fs) < 5:  # Need at least 5 fixtures for reliable profile
                continue

            # Most common formation
            form_series = t_fs['formation'].dropna()
            if form_series.empty:
                continue
            main_formation = form_series.mode().iloc[0]

            # Does this team use the player's formation position?
            if player_fp:
                fp_matches = t_fs[t_fs['formation_position'] == player_fp]
                uses_position = len(fp_matches) > 0
                # Average rating of players in that position (positional depth/quality)
                pos_avg_rating = fp_matches['rating'].mean() if uses_position else None
            else:
                # Fall back to broad position match
                pos_matches = t_fs[t_fs['position'] == player_pos]
                uses_position = len(pos_matches) > 0
                pos_avg_rating = pos_matches['rating'].mean() if uses_position else None

            if not uses_position:
                continue

            # Team style indicators (per-match averages)
            fixtures_count = t_fs['fixture_id'].nunique()
            team_passes_pg = t_fs.groupby('fixture_id')['passes_total'].sum().mean()
            team_tackles_pg = t_fs.groupby('fixture_id')['tackles_total'].sum().mean()
            team_dribbles_pg = t_fs.groupby('fixture_id')['dribbles_success'].sum().mean()

            # Competition name
            comp = t_fs['competition_name'].mode().iloc[0] if 'competition_name' in t_fs.columns else 'Unknown'

            club_rows.append({
                'team_api_id': t_id,
                'formation': main_formation,
                'league': comp,
                'pos_avg_rating': pos_avg_rating,
                'passes_pg': team_passes_pg,
                'tackles_pg': team_tackles_pg,
                'dribbles_pg': team_dribbles_pg,
                'fixtures': fixtures_count,
            })

        if not club_rows:
            return empty

        clubs = pd.DataFrame(club_rows)

        # ── Score each club ──
        scores = []
        for _, club in clubs.iterrows():
            score = 50.0  # Base score
            reasons = []

            # Position need: lower rating at position = higher need
            if pd.notna(club['pos_avg_rating']):
                if club['pos_avg_rating'] < 6.5:
                    score += 20
                    reasons.append(f"position need (avg rating {club['pos_avg_rating']:.1f})")
                elif club['pos_avg_rating'] < 6.8:
                    score += 10
                    reasons.append(f"moderate position need (avg rating {club['pos_avg_rating']:.1f})")

            # Tactical fit
            high_possession = club['passes_pg'] > 350
            counter_attacking = club['passes_pg'] < 280
            physical_team = club['tackles_pg'] > 25

            if player_is_creative and high_possession:
                score += 15
                reasons.append("high-possession style suits creative player")
            elif player_is_direct and counter_attacking:
                score += 15
                reasons.append("counter-attacking style suits direct player")
            elif player_is_physical and physical_team:
                score += 15
                reasons.append("physical team suits physical player")
            elif player_is_creative and counter_attacking:
                score -= 5  # Mild mismatch
            elif player_is_direct and high_possession:
                score -= 5

            # Formation compatibility
            fp_label = player_fp if player_fp else player_pos
            reasons.append(f"plays {club['formation']} with {fp_label} role")

            # Game time opportunity (more fixtures = more established league)
            if club['fixtures'] >= 15:
                score += 5

            scores.append({
                'team_api_id': club['team_api_id'],
                'formation': club['formation'],
                'league': club['league'],
                'fit_score': round(score, 1),
                'reasoning': '; '.join(reasons),
            })

        result = pd.DataFrame(scores)
        result = result.nlargest(limit, 'fit_score')

        # Resolve team names
        result['team_name'] = result['team_api_id'].apply(_resolve_team_name)

        return result[['team_name', 'league', 'formation', 'fit_score', 'reasoning']].reset_index(drop=True)

    return {
        'academy_comparison': academy_comparison,
        'first_team_graduates': first_team_graduates,
        'player_status_breakdown': player_status_breakdown,
        'active_academy_pipeline': active_academy_pipeline,
        'academy_first_team_apps': academy_first_team_apps,
        'top_loan_performers': top_loan_performers,
        'player_career': player_career,
        'find_similar_players': find_similar_players,
        'find_hidden_talent': find_hidden_talent,
        'suggest_loan_destinations': suggest_loan_destinations,
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
    if isinstance(v, type(pd.NaT)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return round(float(v), 4)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if isinstance(v, pd.DataFrame):
        return f"[DataFrame: {len(v)} rows × {len(v.columns)} cols]"
    if isinstance(v, pd.Series):
        return v.tolist()
    if isinstance(v, (list, tuple)):
        return [_safe_value(i) for i in v]
    return v
