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

# Chart styling constants
CHART_COLORS = {
    'primary': '#7c3aed',      # Violet
    'success': '#10b981',      # Green
    'warning': '#f59e0b',      # Amber
    'danger': '#ef4444',       # Red
    'info': '#3b82f6',         # Blue
    'gray': '#6b7280',
}

POSITION_COLORS = {
    'Forward': '#ef4444',
    'Midfielder': '#3b82f6',
    'Defender': '#10b981',
    'Goalkeeper': '#f59e0b',
}

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


def render_radar_chart(data: Dict[str, Any], width: int = 400, height: int = 400) -> bytes:
    """
    Render a radar/spider chart as PNG bytes.
    
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
    position_category = data.get('position_category', 'Midfielder')
    
    if not radar_data:
        return _render_empty_chart("No data available", width, height)
    
    # Setup figure
    fig = plt.figure(figsize=(width/100, height/100), dpi=100)
    ax = fig.add_subplot(111, polar=True)
    
    # Prepare data
    categories = [item.get('label', item.get('stat', '')) for item in radar_data]
    values = [item.get('normalized', 0) for item in radar_data]
    num_vars = len(categories)
    
    # Compute angle for each axis
    angles = [n / float(num_vars) * 2 * np.pi for n in range(num_vars)]
    angles += angles[:1]  # Complete the circle
    values += values[:1]  # Complete the polygon
    
    # Plot
    color = POSITION_COLORS.get(position_category, CHART_COLORS['primary'])
    ax.plot(angles, values, 'o-', linewidth=2, color=color)
    ax.fill(angles, values, alpha=0.25, color=color)
    
    # Configure axes
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, size=8, color=CHART_COLORS['gray'])
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75, 100])
    ax.set_yticklabels(['25', '50', '75', '100'], size=7, color=CHART_COLORS['gray'])
    ax.set_rlabel_position(30)
    
    # Title
    title = f"{player_name}"
    if matches_count:
        title += f" - {matches_count} match{'es' if matches_count != 1 else ''}"
    ax.set_title(title, size=10, color=CHART_COLORS['gray'], y=1.1, fontweight='bold')
    
    # Convert to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_bar_chart(data: Dict[str, Any], width: int = 500, height: int = 300) -> bytes:
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
    
    # Setup figure
    fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=100)
    
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
        bars = ax.bar(x + offset, values, width_bar, label=stat.replace('_', ' ').title(),
                      color=colors[i % len(colors)], alpha=0.8)
    
    # Configure axes
    ax.set_xlabel('Match', fontsize=9, color=CHART_COLORS['gray'])
    ax.set_ylabel('Value', fontsize=9, color=CHART_COLORS['gray'])
    ax.set_xticks(x)
    ax.set_xticklabels(matches, rotation=45, ha='right', fontsize=7)
    ax.legend(loc='upper right', fontsize=8)
    ax.set_title(f"{player_name} - Per Match Stats", fontsize=10, fontweight='bold', color=CHART_COLORS['gray'])
    
    # Style
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(colors=CHART_COLORS['gray'])
    
    plt.tight_layout()
    
    # Convert to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_line_chart(data: Dict[str, Any], width: int = 500, height: int = 300) -> bytes:
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
    
    # Setup figure
    fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=100)
    
    # Prepare data
    dates = [d.get('date', '')[:10] for d in line_data]
    x = np.arange(len(dates))
    
    colors = [CHART_COLORS['primary'], CHART_COLORS['success'], CHART_COLORS['info'],
              CHART_COLORS['warning'], CHART_COLORS['danger']]
    
    # Plot line for each stat
    for i, stat in enumerate(stat_keys):
        values = [d.get(stat, 0) or 0 for d in line_data]
        ax.plot(x, values, 'o-', label=stat.replace('_', ' ').title(),
                color=colors[i % len(colors)], linewidth=2, markersize=6)
    
    # Configure axes
    ax.set_xlabel('Date', fontsize=9, color=CHART_COLORS['gray'])
    ax.set_ylabel('Value', fontsize=9, color=CHART_COLORS['gray'])
    ax.set_xticks(x)
    ax.set_xticklabels(dates, rotation=45, ha='right', fontsize=7)
    ax.legend(loc='upper right', fontsize=8)
    ax.set_title(f"{player_name} - Performance Trend", fontsize=10, fontweight='bold', color=CHART_COLORS['gray'])
    
    # Style
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(colors=CHART_COLORS['gray'])
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Convert to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor='white', edgecolor='none')
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
    
    # Setup figure
    fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=100)
    ax.axis('off')
    
    # Title
    ax.text(0.5, 0.95, f"{player_name} - {len(fixtures)} Match Summary", 
            fontsize=11, fontweight='bold', ha='center', transform=ax.transAxes,
            color=CHART_COLORS['gray'])
    
    # Stats in a row
    stats = [
        (f"{total_minutes}'", "Minutes", CHART_COLORS['gray']),
        (f"{total_goals}", "Goals", CHART_COLORS['success'] if total_goals else CHART_COLORS['gray']),
        (f"{total_assists}", "Assists", CHART_COLORS['info'] if total_assists else CHART_COLORS['gray']),
        (f"{avg_rating:.1f}" if avg_rating else "-", "Avg Rating", CHART_COLORS['warning']),
        (f"{wins}W {draws}D {losses}L", "Results", CHART_COLORS['primary']),
    ]
    
    x_positions = np.linspace(0.1, 0.9, len(stats))
    for i, (value, label, color) in enumerate(stats):
        ax.text(x_positions[i], 0.55, str(value), fontsize=16, fontweight='bold', 
                ha='center', transform=ax.transAxes, color=color)
        ax.text(x_positions[i], 0.3, label, fontsize=9, ha='center', 
                transform=ax.transAxes, color=CHART_COLORS['gray'])
    
    # Convert to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor='white', edgecolor='none')
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
    
    # Setup figure
    fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=100)
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
    
    # Header styling
    for i, key in enumerate(headers):
        table[(0, i)].set_facecolor(CHART_COLORS['primary'])
        table[(0, i)].set_text_props(color='white', fontweight='bold')
    
    # Totals row styling
    if totals and rows:
        for i in range(len(headers)):
            table[(len(rows), i)].set_facecolor('#f3f4f6')
            table[(len(rows), i)].set_text_props(fontweight='bold')
    
    # Title
    title = f"{player_name} - {matches_count} Match Stats"
    if len(table_data) > 6:
        title += f" (showing {len(display_data)})"
    ax.set_title(title, fontsize=10, fontweight='bold', color=CHART_COLORS['gray'], y=0.95)
    
    plt.tight_layout()
    
    # Convert to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _render_empty_chart(message: str, width: int, height: int) -> bytes:
    """Render an empty chart placeholder with a message."""
    fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=100)
    ax.axis('off')
    ax.text(0.5, 0.5, message, fontsize=12, ha='center', va='center',
            color=CHART_COLORS['gray'], transform=ax.transAxes)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor='#f9fafb', edgecolor='none')
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

