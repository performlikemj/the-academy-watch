"""
Server-side chart rendering service for email newsletters.

Generates static chart images using matplotlib that can be embedded in emails
where dynamic JavaScript charts aren't supported.
"""

import io
import os
import base64
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Polygon
import numpy as np

# Chart styling constants — Tactical Lens dark theme.
# These charts are embedded in newsletter cards over a deep navy background;
# light surfaces would look like islands of glare. The figure facecolor and
# axes facecolor are both set to TL_CARD so the chart blends into the
# surrounding card. Text is light slate (`gray` token, kept for backwards
# compat with existing render functions).
CHART_COLORS = {
    'primary': '#60a5fa',      # Royal blue (brighter for dark bg)
    'success': '#4ade80',      # Green
    'warning': '#fbbf24',      # Amber
    'danger': '#f87171',       # Red
    'info': '#38bdf8',         # Sky
    'gray': '#cbd5e1',         # Light slate — used for ALL labels/titles
    'gray_dim': '#94a3b8',     # Muted slate for secondary labels
}

# Tactical Lens surface tiers — used as facecolor for figures and axes so
# the chart drawing area blends into the card background instead of being
# a white rectangle on a dark page.
TL_CARD = '#222a3d'
TL_INNER = '#2d3449'
TL_GRID = '#475569'
TL_TEXT = '#e2e8f0'

POSITION_COLORS = {
    'Forward': '#f87171',
    'Midfielder': '#60a5fa',
    'Defender': '#4ade80',
    'Goalkeeper': '#fbbf24',
}

# Standard DPI bumped from 100 → 150 for crisp retina rendering. The figure
# pixel dimensions in newsletters stay valid because we still divide width/
# height by 100 for the figsize argument (logical inches). matplotlib then
# rasterises at 150dpi, producing a 1.5× sharper PNG at the same display size.
DPI = 150

# Directory to store generated chart images
CHARTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'static', 'charts')


def ensure_charts_dir():
    """Ensure the charts directory exists."""
    os.makedirs(CHARTS_DIR, exist_ok=True)


def generate_chart_id(block: dict, player_id: Optional[int], week_start: Optional[str], week_end: Optional[str]) -> str:
    """Generate a unique ID for a chart based on its configuration."""
    key_parts = [
        str(block.get('chart_type', '')),
        str(player_id or ''),
        str(week_start or ''),
        str(week_end or ''),
        str(sorted(block.get('chart_config', {}).get('stat_keys', []))),
        str(block.get('chart_config', {}).get('date_range', '')),
    ]
    key = '|'.join(key_parts)
    return hashlib.md5(key.encode()).hexdigest()[:12]


def render_radar_chart(data: Dict[str, Any], width: int = 480, height: int = 480) -> bytes:
    """
    Render a radar/spider chart as PNG bytes.

    Supports both the new percentile-based format (position_group present)
    and the legacy normalized format.

    Args:
        data: Chart data from the API including 'data' array with stat info
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        PNG image as bytes
    """
    radar_data = data.get('data', [])
    player_name = data.get('player', {}).get('name', 'Player')
    matches_count = data.get('matches_count', 0)
    is_new_format = 'position_group' in data

    if not radar_data:
        return _render_empty_chart("No data available", width, height)

    # Setup figure with dark Tactical Lens facecolor so the polar plot blends
    # into the surrounding player card. The axes facecolor must also be set
    # explicitly — savefig facecolor only paints the area outside the axes.
    fig = plt.figure(figsize=(width/100, height/100), dpi=DPI)
    fig.patch.set_facecolor(TL_CARD)
    ax = fig.add_subplot(111, polar=True)
    ax.set_facecolor(TL_CARD)

    # Prepare data
    categories = [item.get('label', item.get('stat', '')) for item in radar_data]
    num_vars = len(categories)
    angles = [n / float(num_vars) * 2 * np.pi for n in range(num_vars)]
    angles += angles[:1]  # Complete the circle

    is_league_format = 'league_name' in data

    if is_league_format:
        # League-based: player vs league average, normalized to league max
        league_name = data.get('league_name', 'League')
        league_peers = data.get('league_peers', 0)
        position_group_label = data.get('position_group_label', 'Position')
        position_category = _group_to_category(data.get('position_group', 'CM'))
        color = POSITION_COLORS.get(position_category, CHART_COLORS['primary'])
        avg_color = '#94a3b8'  # Muted slate dashes for league avg overlay

        player_values = [item.get('player_normalized', 0) for item in radar_data]
        avg_values = [item.get('league_avg_normalized') for item in radar_data]
        has_overlay = any(v is not None for v in avg_values)

        player_values += player_values[:1]
        if has_overlay:
            avg_values_clean = [(v or 0) for v in avg_values] + [(avg_values[0] or 0)]
            ax.plot(angles, avg_values_clean, linewidth=1.5, color=avg_color, linestyle='--')
            ax.fill(angles, avg_values_clean, alpha=0.08, color=avg_color)

        ax.plot(angles, player_values, 'o-', linewidth=2, color=color, markersize=4)
        ax.fill(angles, player_values, alpha=0.3, color=color)

        if has_overlay:
            from matplotlib.lines import Line2D
            legend_elements = [
                Line2D([0], [0], color=color, linewidth=2, label='Player'),
                Line2D([0], [0], color=avg_color, linewidth=1.5, linestyle='--',
                       label=f'{league_name} Avg'),
            ]
            ax.legend(handles=legend_elements, loc='lower right', fontsize=7,
                      bbox_to_anchor=(1.25, -0.1), framealpha=0.8)
        else:
            # No league overlay (insufficient peers / unsupported league):
            # explicitly label the polygon as player-only so the reader doesn't
            # mistake the self-normalised polygon for a league comparison.
            from matplotlib.lines import Line2D
            ax.legend(
                handles=[Line2D([0], [0], color=color, linewidth=2,
                                label='Player only (no league overlay)')],
                loc='lower right', fontsize=7,
                bbox_to_anchor=(1.25, -0.1), framealpha=0.8,
            )
    elif is_new_format:
        # Percentile-based (fallback)
        position_category = _group_to_category(data.get('position_group', 'CM'))
        color = POSITION_COLORS.get(position_category, CHART_COLORS['primary'])
        player_values = [item.get('player_percentile', item.get('player_normalized', 0)) for item in radar_data]
        player_values += player_values[:1]
        ax.plot(angles, player_values, 'o-', linewidth=2, color=color, markersize=4)
        ax.fill(angles, player_values, alpha=0.3, color=color)
        league_name = None
        league_peers = 0
        position_group_label = data.get('position_group_label', '')
    else:
        # Legacy normalized format
        position_category = data.get('position_category', 'Midfielder')
        color = POSITION_COLORS.get(position_category, CHART_COLORS['primary'])
        values = [item.get('normalized', 0) for item in radar_data]
        values += values[:1]
        ax.plot(angles, values, 'o-', linewidth=2, color=color)
        ax.fill(angles, values, alpha=0.25, color=color)
        league_name = None
        league_peers = 0
        position_group_label = None

    # Configure axes — light slate labels + dark grid lines that are visible
    # against the deep navy facecolor without being noisy.
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, size=8, color=CHART_COLORS['gray'])
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75, 100])
    ax.set_yticklabels(['25%', '50%', '75%', '100%'], size=6, color=CHART_COLORS['gray_dim'])
    ax.set_rlabel_position(30)
    ax.tick_params(colors=CHART_COLORS['gray'])
    ax.grid(color=TL_GRID, alpha=0.45, linewidth=0.8)
    # Polar plot's outer ring spine
    for spine in ax.spines.values():
        spine.set_color(TL_GRID)
        spine.set_alpha(0.6)

    # Title
    title = f"{player_name}"
    if matches_count:
        title += f" - {matches_count} match{'es' if matches_count != 1 else ''}"
    ax.set_title(title, size=11, color=TL_TEXT, y=1.1, fontweight='bold')

    # Footer — always explain what the chart is showing. When league averages
    # are unavailable for the player's league, say so explicitly rather than
    # silently presenting a self-normalised polygon as if it were a comparison.
    if is_league_format:
        if has_overlay and league_name:
            footer = (
                f"Per 90 vs {league_peers} {position_group_label.lower()}s in "
                f"{league_name}. 100% = best in league."
            )
        elif league_name:
            footer = (
                f"League comparison unavailable for {league_name}. "
                f"Showing player-only per 90 stats normalised to peak axis."
            )
        else:
            footer = (
                "League comparison unavailable. "
                "Showing player-only per 90 stats normalised to peak axis."
            )
        fig.text(0.5, -0.02, footer, ha='center', fontsize=8, color=CHART_COLORS['gray_dim'])

    # Convert to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=TL_CARD, edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _group_to_category(group: str) -> str:
    """Map position group to broad category for color selection."""
    return {
        'GK': 'Goalkeeper', 'CB': 'Defender', 'FB': 'Defender',
        'DM': 'Midfielder', 'CM': 'Midfielder', 'AM': 'Midfielder',
        'W': 'Forward', 'ST': 'Forward',
    }.get(group, 'Midfielder')


def render_bar_chart(data: Dict[str, Any], width: int = 560, height: int = 320) -> bytes:
    """
    Render a bar chart as PNG bytes.

    Args:
        data: Chart data from the API including 'data' array with match stats
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        PNG image as bytes
    """
    bar_data = data.get('data', [])
    stat_keys = data.get('stat_keys', ['goals', 'assists', 'rating'])
    player_name = data.get('player', {}).get('name', 'Player')

    if not bar_data:
        return _render_empty_chart("No data available", width, height)

    # Setup figure with dark Tactical Lens facecolor.
    fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=DPI)
    fig.patch.set_facecolor(TL_CARD)
    ax.set_facecolor(TL_CARD)

    # Prepare data
    matches = [d.get('match', d.get('date', ''))[:20] for d in bar_data]
    x = np.arange(len(matches))
    width_bar = 0.8 / len(stat_keys)

    colors = [CHART_COLORS['primary'], CHART_COLORS['success'], CHART_COLORS['info'],
              CHART_COLORS['warning'], CHART_COLORS['danger']]

    # Plot bars for each stat
    for i, stat in enumerate(stat_keys):
        values = [d.get(stat, 0) or 0 for d in bar_data]
        offset = (i - len(stat_keys)/2 + 0.5) * width_bar
        ax.bar(x + offset, values, width_bar, label=stat.replace('_', ' ').title(),
               color=colors[i % len(colors)], alpha=0.85)

    # Configure axes — light slate labels on dark, subtle grid.
    ax.set_xlabel('Match', fontsize=9, color=CHART_COLORS['gray'])
    ax.set_ylabel('Value', fontsize=9, color=CHART_COLORS['gray'])
    ax.set_xticks(x)
    ax.set_xticklabels(matches, rotation=45, ha='right', fontsize=7, color=CHART_COLORS['gray'])
    legend = ax.legend(loc='upper right', fontsize=8, facecolor=TL_INNER, edgecolor=TL_GRID, labelcolor=TL_TEXT)
    if legend is not None:
        legend.get_frame().set_alpha(0.85)
    ax.set_title(f"{player_name} - Per Match Stats", fontsize=11, fontweight='bold', color=TL_TEXT)

    # Style — hide top/right spines, dark grid lines, light tick marks.
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color(TL_GRID)
    ax.spines['left'].set_color(TL_GRID)
    ax.tick_params(colors=CHART_COLORS['gray'])
    ax.yaxis.label.set_color(CHART_COLORS['gray'])
    ax.xaxis.label.set_color(CHART_COLORS['gray'])
    ax.grid(True, axis='y', alpha=0.25, color=TL_GRID, linewidth=0.6)

    plt.tight_layout()

    # Convert to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=TL_CARD, edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_line_chart(data: Dict[str, Any], width: int = 560, height: int = 320) -> bytes:
    """
    Render a line chart as PNG bytes.

    Args:
        data: Chart data from the API including 'data' array with time series stats
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        PNG image as bytes
    """
    line_data = data.get('data', [])
    stat_keys = data.get('stat_keys', ['goals', 'assists', 'rating'])
    player_name = data.get('player', {}).get('name', 'Player')

    if not line_data:
        return _render_empty_chart("No data available", width, height)

    # Even when line_data is non-empty, every stat value can still be None / 0
    # (e.g. limited-coverage leagues never populate `rating`). Plotting that
    # produces an empty-axes chart that looks broken — render an explicit
    # placeholder instead.
    has_any_value = any(
        d.get(stat) is not None and d.get(stat) > 0
        for d in line_data
        for stat in stat_keys
    )
    if not has_any_value:
        return _render_empty_chart(
            f"No {', '.join(stat_keys)} data available", width, height,
        )

    # Setup figure with dark Tactical Lens facecolor.
    fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=DPI)
    fig.patch.set_facecolor(TL_CARD)
    ax.set_facecolor(TL_CARD)

    # Prepare data
    dates = [d.get('date', '')[:10] for d in line_data]
    x = np.arange(len(dates))

    colors = [CHART_COLORS['primary'], CHART_COLORS['success'], CHART_COLORS['info'],
              CHART_COLORS['warning'], CHART_COLORS['danger']]

    # Plot line for each stat, skipping missing/zero values
    for i, stat in enumerate(stat_keys):
        raw_values = [d.get(stat) for d in line_data]
        # Build masked arrays so missing data points create gaps instead of zero dips
        values = []
        for v in raw_values:
            if v is not None and v > 0:
                values.append(v)
            else:
                values.append(float('nan'))
        ax.plot(x, values, 'o-', label=stat.replace('_', ' ').title(),
                color=colors[i % len(colors)], linewidth=2.2, markersize=6)

    # Configure axes — light slate labels + dark grid lines.
    ax.set_xlabel('Date', fontsize=9, color=CHART_COLORS['gray'])
    ax.set_ylabel('Value', fontsize=9, color=CHART_COLORS['gray'])
    ax.set_xticks(x)
    ax.set_xticklabels(dates, rotation=45, ha='right', fontsize=7, color=CHART_COLORS['gray'])
    legend = ax.legend(loc='upper right', fontsize=8, facecolor=TL_INNER, edgecolor=TL_GRID, labelcolor=TL_TEXT)
    if legend is not None:
        legend.get_frame().set_alpha(0.85)
    ax.set_title(f"{player_name} - Performance Trend", fontsize=11, fontweight='bold', color=TL_TEXT)

    # Style
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color(TL_GRID)
    ax.spines['left'].set_color(TL_GRID)
    ax.tick_params(colors=CHART_COLORS['gray'])
    ax.yaxis.label.set_color(CHART_COLORS['gray'])
    ax.xaxis.label.set_color(CHART_COLORS['gray'])
    ax.grid(True, alpha=0.3, color=TL_GRID, linewidth=0.6)

    plt.tight_layout()

    # Convert to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=TL_CARD, edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_match_cards_summary(data: Dict[str, Any], width: int = 500, height: int = 200) -> bytes:
    """
    Render a summary visualization for match cards.
    Since match cards are detailed, we render a summary bar showing key stats.
    
    Args:
        data: Chart data from the API including 'fixtures' array
        width: Image width in pixels  
        height: Image height in pixels
        
    Returns:
        PNG image as bytes
    """
    fixtures = data.get('fixtures', [])
    player_name = data.get('player', {}).get('name', 'Player')
    
    if not fixtures:
        return _render_empty_chart("No matches found", width, height)
    
    # Aggregate stats from fixtures
    total_minutes = sum(f.get('stats', {}).get('minutes', 0) or 0 for f in fixtures)
    total_goals = sum(f.get('stats', {}).get('goals', 0) or 0 for f in fixtures)
    total_assists = sum(f.get('stats', {}).get('assists', 0) or 0 for f in fixtures)
    
    ratings = [f.get('stats', {}).get('rating') for f in fixtures if f.get('stats', {}).get('rating')]
    avg_rating = sum(ratings) / len(ratings) if ratings else 0
    
    # Count results
    wins = sum(1 for f in fixtures if (f.get('is_home') and f['home_team']['score'] > f['away_team']['score']) or
               (not f.get('is_home') and f['away_team']['score'] > f['home_team']['score']))
    draws = sum(1 for f in fixtures if f['home_team']['score'] == f['away_team']['score'])
    losses = len(fixtures) - wins - draws
    
    # Setup figure with dark Tactical Lens facecolor.
    fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=DPI)
    fig.patch.set_facecolor(TL_CARD)
    ax.set_facecolor(TL_CARD)
    ax.axis('off')

    # Title
    ax.text(0.5, 0.95, f"{player_name} - {len(fixtures)} Match Summary",
            fontsize=12, fontweight='bold', ha='center', transform=ax.transAxes,
            color=TL_TEXT)

    # Stats in a row — use brighter primary tones for highlights, light slate
    # for neutral values, since the background is now dark navy.
    stats = [
        (f"{total_minutes}'", "Minutes", TL_TEXT),
        (f"{total_goals}", "Goals", CHART_COLORS['success'] if total_goals else CHART_COLORS['gray_dim']),
        (f"{total_assists}", "Assists", CHART_COLORS['info'] if total_assists else CHART_COLORS['gray_dim']),
        (f"{avg_rating:.1f}" if avg_rating else "-", "Avg Rating", CHART_COLORS['warning']),
        (f"{wins}W {draws}D {losses}L", "Results", CHART_COLORS['primary']),
    ]

    x_positions = np.linspace(0.1, 0.9, len(stats))
    for i, (value, label, color) in enumerate(stats):
        ax.text(x_positions[i], 0.55, str(value), fontsize=17, fontweight='bold',
                ha='center', transform=ax.transAxes, color=color)
        ax.text(x_positions[i], 0.3, label, fontsize=9, ha='center',
                transform=ax.transAxes, color=CHART_COLORS['gray'])

    # Convert to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=TL_CARD, edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_stat_table(data: Dict[str, Any], width: int = 500, height: int = 250) -> bytes:
    """
    Render a stat table as an image.
    
    Args:
        data: Chart data from the API including 'data' array and 'totals'
        width: Image width in pixels
        height: Image height in pixels
        
    Returns:
        PNG image as bytes
    """
    table_data = data.get('data', [])
    totals = data.get('totals', {})
    player_name = data.get('player', {}).get('name', 'Player')
    matches_count = data.get('matches_count', 0)
    
    if not table_data:
        return _render_empty_chart("No data available", width, height)
    
    # Limit rows for image size
    display_data = table_data[:6]  # Show max 6 matches
    
    # Setup figure with dark Tactical Lens facecolor.
    fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=DPI)
    fig.patch.set_facecolor(TL_CARD)
    ax.set_facecolor(TL_CARD)
    ax.axis('off')

    # Build table data
    headers = ['Date', 'Opponent', 'Result', 'Min', 'G', 'A', 'Rating']
    rows = []
    for d in display_data:
        rows.append([
            d.get('date', '')[:10],
            d.get('opponent', '')[:12],
            d.get('result', ''),
            str(d.get('minutes', 0) or 0),
            str(d.get('goals', 0) or 0),
            str(d.get('assists', 0) or 0),
            f"{d.get('rating', 0):.1f}" if d.get('rating') else '-',
        ])

    # Add totals row if we have totals
    if totals:
        rows.append([
            'TOTAL', '', '',
            str(totals.get('minutes', 0)),
            str(totals.get('goals', 0)),
            str(totals.get('assists', 0)),
            '-',
        ])

    # Create table
    table = ax.table(
        cellText=rows,
        colLabels=headers,
        cellLoc='center',
        loc='center',
        colWidths=[0.15, 0.2, 0.1, 0.1, 0.08, 0.08, 0.1]
    )

    # Style table
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1.2, 1.5)

    # Header styling — primary blue with white text. Body cells get the
    # tier-3 inner background so the table reads as a card-on-card.
    for i, key in enumerate(headers):
        cell = table[(0, i)]
        cell.set_facecolor(CHART_COLORS['primary'])
        cell.set_text_props(color='#0b1326', fontweight='bold')
        cell.set_edgecolor(TL_GRID)

    # Body row styling — dark cells with light text.
    body_count = len(rows) - (1 if totals else 0)
    for r in range(1, body_count + 1):
        for c in range(len(headers)):
            cell = table[(r, c)]
            cell.set_facecolor(TL_INNER)
            cell.set_text_props(color=TL_TEXT)
            cell.set_edgecolor(TL_GRID)

    # Totals row styling
    if totals and rows:
        for i in range(len(headers)):
            cell = table[(len(rows), i)]
            cell.set_facecolor('#1a2235')  # slightly darker than TL_INNER
            cell.set_text_props(fontweight='bold', color=CHART_COLORS['primary'])
            cell.set_edgecolor(TL_GRID)

    # Title
    title = f"{player_name} - {matches_count} Match Stats"
    if len(table_data) > 6:
        title += f" (showing {len(display_data)})"
    ax.set_title(title, fontsize=11, fontweight='bold', color=TL_TEXT, y=0.95)

    plt.tight_layout()

    # Convert to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=TL_CARD, edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _render_empty_chart(message: str, width: int, height: int) -> bytes:
    """Render an empty chart placeholder with a message — dark Tactical Lens
    surface so it blends into the surrounding card."""
    fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=DPI)
    fig.patch.set_facecolor(TL_CARD)
    ax.set_facecolor(TL_CARD)
    ax.axis('off')
    ax.text(0.5, 0.5, message, fontsize=12, ha='center', va='center',
            color=CHART_COLORS['gray'], transform=ax.transAxes)

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=TL_CARD, edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_chart(chart_type: str, data: Dict[str, Any], width: int = 500, height: int = 300) -> bytes:
    """
    Main entry point to render a chart based on type.
    
    Args:
        chart_type: One of 'radar', 'bar', 'line', 'match_card', 'stat_table'
        data: Chart data from the API
        width: Image width in pixels
        height: Image height in pixels
        
    Returns:
        PNG image as bytes
    """
    if chart_type == 'radar':
        return render_radar_chart(data, width, height)
    elif chart_type == 'bar':
        return render_bar_chart(data, width, height)
    elif chart_type == 'line':
        return render_line_chart(data, width, height)
    elif chart_type == 'match_card':
        return render_match_cards_summary(data, width, min(height, 200))
    elif chart_type == 'stat_table':
        return render_stat_table(data, width, height)
    else:
        return _render_empty_chart(f"Unknown chart type: {chart_type}", width, height)


def render_chart_to_base64(chart_type: str, data: Dict[str, Any], width: int = 500, height: int = 300) -> str:
    """
    Render a chart and return as base64 data URL.
    
    Args:
        chart_type: Chart type
        data: Chart data from the API
        width: Image width in pixels
        height: Image height in pixels
        
    Returns:
        Data URL string (data:image/png;base64,...)
    """
    image_bytes = render_chart(chart_type, data, width, height)
    b64 = base64.b64encode(image_bytes).decode('utf-8')
    return f"data:image/png;base64,{b64}"


def save_chart_to_file(chart_type: str, data: Dict[str, Any], filename: str,
                       width: int = 500, height: int = 300) -> str:
    """
    Render a chart and save to file.
    
    Args:
        chart_type: Chart type
        data: Chart data from the API
        filename: Filename (without extension)
        width: Image width in pixels
        height: Image height in pixels
        
    Returns:
        Path to saved file
    """
    ensure_charts_dir()
    image_bytes = render_chart(chart_type, data, width, height)
    
    filepath = os.path.join(CHARTS_DIR, f"{filename}.png")
    with open(filepath, 'wb') as f:
        f.write(image_bytes)
    
    return filepath

