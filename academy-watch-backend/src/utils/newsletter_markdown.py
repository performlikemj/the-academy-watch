"""Newsletter to Reddit Markdown Converter

Converts newsletter JSON to Reddit-compatible markdown format
with proper formatting for sharing on Reddit.
"""

import json
from datetime import datetime
from typing import Optional, Any


def format_date(date_str: Optional[str]) -> str:
    """Format a date string for display.
    
    Args:
        date_str: ISO date string or None
        
    Returns:
        Formatted date string (e.g., "14 Dec 2024")
    """
    if not date_str:
        return ''
    try:
        # Handle both ISO datetime and date-only strings
        date_part = date_str[:10] if len(date_str) >= 10 else date_str
        date = datetime.strptime(date_part, '%Y-%m-%d')
        return date.strftime('%-d %b %Y')
    except (ValueError, TypeError):
        return str(date_str)


def get_result_emoji(result: Optional[str]) -> str:
    """Get result emoji based on match result.
    
    Args:
        result: Match result ('W', 'D', 'L')
        
    Returns:
        Emoji string
    """
    if not result:
        return '⚪'
    result_upper = result.upper()
    if result_upper == 'W':
        return '🟢'
    elif result_upper == 'D':
        return '🟡'
    elif result_upper == 'L':
        return '🔴'
    return '⚪'


def format_stats_line(stats: Optional[dict]) -> str:
    """Format stats line based on player position.
    
    Args:
        stats: Player statistics dict
        
    Returns:
        Formatted stats string
    """
    if not stats:
        return ''
    
    parts = []
    minutes = stats.get('minutes', 0) or 0
    parts.append(f"{minutes}'")
    
    position = stats.get('position', '') or ''
    
    if position in ('Goalkeeper', 'G'):
        # Goalkeeper stats
        saves = stats.get('saves', 0) or 0
        conceded = stats.get('goals_conceded', 0) or 0
        parts.append(f"{saves} saves")
        parts.append(f"{conceded} conceded")
    elif position in ('Defender', 'D'):
        # Defender stats
        tackles = stats.get('tackles_total', 0) or 0
        interceptions = stats.get('tackles_interceptions', 0) or 0
        if tackles or interceptions:
            parts.append(f"{tackles}T {interceptions}I")
        goals = stats.get('goals', 0) or 0
        assists = stats.get('assists', 0) or 0
        if goals > 0 or assists > 0:
            parts.append(f"{goals}G {assists}A")
    else:
        # Midfielder/Forward stats
        goals = stats.get('goals', 0) or 0
        assists = stats.get('assists', 0) or 0
        parts.append(f"{goals}G {assists}A")
        key_passes = stats.get('passes_key')
        if key_passes:
            parts.append(f"{key_passes} key passes")
        shots = stats.get('shots_total')
        if shots:
            parts.append(f"{shots} shots")
    
    rating = stats.get('rating')
    if rating:
        try:
            parts.append(f"⭐ {float(rating):.1f}")
        except (ValueError, TypeError):
            pass
    
    return ' | '.join(parts)


def format_expanded_stats(stats: Optional[dict]) -> str:
    """Format expanded stats table for a player.
    
    Args:
        stats: Player statistics dict
        
    Returns:
        Markdown table string
    """
    if not stats:
        return ''
    
    lines = []
    
    # Check if we have expanded stats worth showing
    has_attacking = stats.get('shots_total') or stats.get('dribbles_attempts')
    has_passing = stats.get('passes_total') or stats.get('passes_key')
    has_defending = stats.get('tackles_total') or stats.get('tackles_interceptions')
    has_duels = stats.get('duels_total')
    position = stats.get('position', '') or ''
    has_gk = position in ('Goalkeeper', 'G') and (stats.get('saves') is not None or stats.get('goals_conceded') is not None)
    
    if not any([has_attacking, has_passing, has_defending, has_duels, has_gk]):
        return ''
    
    lines.append('')
    lines.append('| Category | Stat | Value |')
    lines.append('|:---------|:-----|------:|')
    
    # Attacking
    if has_attacking:
        shots = stats.get('shots_total')
        if shots:
            shots_on = stats.get('shots_on', 0) or 0
            lines.append(f"| ⚽ Attacking | Shots | {shots} ({shots_on} on target) |")
        dribbles_attempts = stats.get('dribbles_attempts')
        if dribbles_attempts:
            dribbles_success = stats.get('dribbles_success', 0) or 0
            lines.append(f"| ⚽ Attacking | Dribbles | {dribbles_success}/{dribbles_attempts} |")
    
    # Passing
    if has_passing:
        passes_total = stats.get('passes_total')
        if passes_total:
            lines.append(f"| 🎯 Passing | Passes | {passes_total} |")
        passes_key = stats.get('passes_key')
        if passes_key:
            lines.append(f"| 🎯 Passing | Key Passes | {passes_key} |")
        passes_accuracy = stats.get('passes_accuracy')
        if passes_accuracy:
            lines.append(f"| 🎯 Passing | Accuracy | {passes_accuracy}% |")
    
    # Defending
    if has_defending:
        tackles_total = stats.get('tackles_total')
        if tackles_total:
            lines.append(f"| 🛡️ Defending | Tackles | {tackles_total} |")
        interceptions = stats.get('tackles_interceptions')
        if interceptions:
            lines.append(f"| 🛡️ Defending | Interceptions | {interceptions} |")
        blocks = stats.get('tackles_blocks')
        if blocks:
            lines.append(f"| 🛡️ Defending | Blocks | {blocks} |")
    
    # Duels
    if has_duels:
        duels_total = stats.get('duels_total')
        duels_won = stats.get('duels_won', 0) or 0
        lines.append(f"| ⚔️ Duels | Won | {duels_won}/{duels_total} |")
    
    # Goalkeeper
    if has_gk:
        saves = stats.get('saves')
        if saves is not None:
            lines.append(f"| 🧤 Goalkeeper | Saves | {saves} |")
        goals_conceded = stats.get('goals_conceded')
        if goals_conceded is not None:
            lines.append(f"| 🧤 Goalkeeper | Conceded | {goals_conceded} |")
    
    # Discipline
    yellows = stats.get('yellows', 0) or 0
    reds = stats.get('reds', 0) or 0
    if yellows > 0 or reds > 0:
        lines.append(f"| ⚠️ Discipline | Cards | {yellows}🟨 {reds}🟥 |")
    
    return '\n'.join(lines)


def format_matches(matches: Optional[list], upcoming_fixtures: Optional[list]) -> str:
    """Format matches/fixtures for a player.
    
    Args:
        matches: List of completed match dicts
        upcoming_fixtures: List of upcoming fixture dicts
        
    Returns:
        Formatted matches string
    """
    if (not matches or len(matches) == 0) and (not upcoming_fixtures or len(upcoming_fixtures) == 0):
        return ''
    
    lines = []
    
    # Completed matches
    if matches and len(matches) > 0:
        lines.append('')
        lines.append("**This Week's Matches:**")
        for match in matches:
            emoji = get_result_emoji(match.get('result'))
            home_away = '(H)' if match.get('home') else '(A)'
            score_data = match.get('score', {})
            score = f"{score_data.get('home', '')}-{score_data.get('away', '')}" if score_data else ''
            competition = match.get('competition', '') or ''
            lines.append(f"- {emoji} vs {match.get('opponent', '')} {home_away} {score} — *{competition}*")
    
    # Fixtures from upcoming_fixtures
    if upcoming_fixtures and len(upcoming_fixtures) > 0:
        completed = [f for f in upcoming_fixtures if f.get('status') == 'completed' and f.get('result')]
        pending = [f for f in upcoming_fixtures if f.get('status') != 'completed' or not f.get('result')]
        
        if completed and (not matches or len(matches) == 0):
            lines.append('')
            lines.append('**Results:**')
            for fixture in completed:
                emoji = get_result_emoji(fixture.get('result'))
                prefix = 'vs' if fixture.get('is_home') else '@'
                score = f"{fixture.get('team_score', '')}-{fixture.get('opponent_score', '')}"
                competition = fixture.get('competition', '') or ''
                lines.append(f"- {emoji} {prefix} {fixture.get('opponent', '')} {score} — *{competition}*")
        
        if pending:
            lines.append('')
            lines.append('**Upcoming:**')
            for fixture in pending:
                prefix = 'vs' if fixture.get('is_home') else '@'
                date_str = fixture.get('date', '')
                formatted_date = format_date(date_str[:10] if date_str else '')
                competition = fixture.get('competition', '') or ''
                lines.append(f"- {prefix} {fixture.get('opponent', '')} — *{competition}* ({formatted_date})")
    
    return '\n'.join(lines)


def format_links(links: Optional[list]) -> str:
    """Format links for a player item.
    
    Args:
        links: List of link dicts or strings
        
    Returns:
        Formatted links string
    """
    if not links or len(links) == 0:
        return ''
    
    lines = ['', '**Links:**']
    for link in links:
        if isinstance(link, str):
            url = link
            title = 'Link'
        else:
            url = link.get('url', '')
            title = link.get('title', 'Link')
        
        if url:
            is_youtube = 'youtube.com' in url or 'youtu.be' in url
            icon = '🎬' if is_youtube else '🔗'
            lines.append(f"- {icon} [{title}]({url})")
    
    return '\n'.join(lines)


def render_quote_block(block: dict) -> str:
    """Render a quote block as Reddit-compatible markdown.

    Args:
        block: Quote block dict containing quote_text, source_name, source_type, etc.

    Returns:
        Reddit-formatted markdown quote string
    """
    quote_text = block.get('quote_text', '')
    source_name = block.get('source_name', '')
    source_type = block.get('source_type', 'public_link')
    source_platform = block.get('source_platform', '')
    source_url = block.get('source_url')
    quote_date = block.get('quote_date')

    # Format date if present (e.g., "2024-01" -> "(Jan 2024)")
    date_str = ''
    if quote_date:
        try:
            if len(quote_date) == 7:  # "2024-01"
                dt = datetime.strptime(quote_date, '%Y-%m')
                date_str = f" ({dt.strftime('%b %Y')})"
            elif len(quote_date) == 10:  # "2024-01-15"
                dt = datetime.strptime(quote_date, '%Y-%m-%d')
                date_str = f" ({dt.strftime('%b %d, %Y')})"
        except ValueError:
            date_str = f" ({quote_date})"

    # Build attribution based on source type
    if source_type == 'public_link' and source_url:
        attribution = f"[{source_name}]({source_url})"
    elif source_type == 'direct_message':
        platform_label = f"{source_platform} DM" if source_platform else "DM"
        attribution = f"{source_name}, via {platform_label}"
    elif source_type == 'email':
        attribution = f"{source_name}, via email"
    elif source_type == 'personal':
        attribution = f"{source_name}, speaking to The Academy Watch"
    elif source_type == 'anonymous':
        attribution = "according to sources"
    else:
        attribution = source_name

    return f'> "{quote_text}"\n> — {attribution}{date_str}\n'


def convert_newsletter_to_markdown(
    newsletter: dict,
    include_expanded_stats: bool = True,
    include_links: bool = True,
    web_url: Optional[str] = None
) -> str:
    """Convert newsletter JSON to Reddit-formatted markdown.
    
    Args:
        newsletter: The newsletter dict
        include_expanded_stats: Include detailed stats tables
        include_links: Include links section
        web_url: URL to the full newsletter
        
    Returns:
        Reddit-compatible markdown string
    """
    if not newsletter:
        return ''
    
    # Parse structured content if it's a string
    content = newsletter
    structured_content = newsletter.get('structured_content')
    if isinstance(structured_content, str):
        try:
            content = json.loads(structured_content)
        except (json.JSONDecodeError, TypeError):
            content = newsletter
    elif newsletter.get('enriched_content'):
        content = newsletter.get('enriched_content')
    
    lines = []
    
    # Header
    title = content.get('title') or newsletter.get('title') or 'Academy Pipeline Update'
    lines.append(f"# {title}")
    lines.append('')
    
    # Meta info
    date_range = content.get('range')
    if date_range and len(date_range) >= 2:
        lines.append(f"📅 **Week:** {format_date(date_range[0])} — {format_date(date_range[1])}")
    season = content.get('season')
    if season:
        lines.append(f"🏆 **Season:** {season}")
    lines.append('')
    lines.append('---')
    lines.append('')
    
    # Summary
    summary = content.get('summary')
    if summary:
        lines.append(f"> {summary}")
        lines.append('')
    
    # Highlights
    highlights = content.get('highlights', [])
    if highlights:
        lines.append('## ⭐ Highlights')
        lines.append('')
        for highlight in highlights:
            lines.append(f"- {highlight}")
        lines.append('')
    
    # By The Numbers
    by_numbers = content.get('by_numbers')
    if by_numbers:
        lines.append('## 📊 By The Numbers')
        lines.append('')
        
        minutes_leaders = by_numbers.get('minutes_leaders', [])
        if minutes_leaders:
            leaders = ', '.join([f"{r.get('player', '')} ({r.get('minutes', 0)}')" for r in minutes_leaders])
            lines.append(f"**Minutes Leaders:** {leaders}")
            lines.append('')
        
        ga_leaders = by_numbers.get('ga_leaders', [])
        if ga_leaders:
            leaders = ', '.join([f"{r.get('player', '')} ({r.get('g', 0)}G {r.get('a', 0)}A)" for r in ga_leaders])
            lines.append(f"**G+A Leaders:** {leaders}")
            lines.append('')
    
    # Sections (Player Reports)
    sections = content.get('sections', [])
    for section in sections:
        if not section or not isinstance(section, dict):
            continue
        
        section_title = section.get('title', 'Players')
        lines.append(f"## 📋 {section_title}")
        lines.append('')
        
        items = section.get('items', [])
        for item in items:
            if not item or not isinstance(item, dict):
                continue
            
            player_name = item.get('player_name', 'Unknown Player')
            loan_team = item.get('loan_team') or item.get('loan_team_name', '')
            
            # Player header
            lines.append(f"### {player_name}")
            if loan_team:
                lines.append(f"*On loan at {loan_team}*")
            lines.append('')
            
            # Stats line
            can_track = item.get('can_fetch_stats', True) is not False
            stats = item.get('stats')
            if can_track and stats:
                stats_line = format_stats_line(stats)
                if stats_line:
                    lines.append(f"**Stats:** {stats_line}")
                    lines.append('')
                
                # Expanded stats table
                if include_expanded_stats:
                    expanded_stats = format_expanded_stats(stats)
                    if expanded_stats:
                        lines.append(expanded_stats)
                        lines.append('')
            elif not can_track:
                lines.append('*Stats not available for this player*')
                lines.append('')
            
            # Week summary
            week_summary = item.get('week_summary')
            if week_summary:
                lines.append(week_summary)
                lines.append('')
            
            # Matches
            matches_section = format_matches(item.get('matches'), item.get('upcoming_fixtures'))
            if matches_section:
                lines.append(matches_section)
                lines.append('')
            
            # Links
            item_links = item.get('links', [])
            if include_links and item_links:
                lines.append(format_links(item_links))
                lines.append('')
            
            lines.append('---')
            lines.append('')
    
    # Footer
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('*Generated by [The Academy Watch](https://theacademywatch.com) — Weekly loan watch newsletters for football fans*')
    
    if web_url:
        lines.append('')
        lines.append(f"📰 [View full newsletter with interactive stats]({web_url})")
    
    return '\n'.join(lines)


def convert_newsletter_to_compact_markdown(newsletter: dict) -> str:
    """Convert newsletter to a more compact Reddit format.
    
    Good for shorter posts or comments.
    
    Args:
        newsletter: The newsletter dict
        
    Returns:
        Compact Reddit markdown string
    """
    if not newsletter:
        return ''
    
    # Parse structured content if it's a string
    content = newsletter
    structured_content = newsletter.get('structured_content')
    if isinstance(structured_content, str):
        try:
            content = json.loads(structured_content)
        except (json.JSONDecodeError, TypeError):
            content = newsletter
    elif newsletter.get('enriched_content'):
        content = newsletter.get('enriched_content')
    
    lines = []
    
    # Header
    title = content.get('title') or newsletter.get('title') or 'Academy Pipeline Update'
    lines.append(f"# {title}")
    lines.append('')
    
    # Date range
    date_range = content.get('range')
    if date_range and len(date_range) >= 2:
        lines.append(f"📅 {format_date(date_range[0])} — {format_date(date_range[1])}")
        lines.append('')
    
    # Quick summary
    summary = content.get('summary')
    if summary:
        lines.append(f"> {summary}")
        lines.append('')
    
    # Player table
    sections = content.get('sections', [])
    for section in sections:
        if not section or not isinstance(section, dict):
            continue
        
        items = section.get('items', [])
        if not items:
            continue
        
        lines.append('| Player | Team | Stats |')
        lines.append('|:-------|:-----|:------|')
        
        for item in items:
            if not item or not isinstance(item, dict):
                continue
            
            player_name = item.get('player_name', 'Unknown')
            loan_team = item.get('loan_team') or item.get('loan_team_name', '-')
            
            stats_str = '-'
            stats = item.get('stats')
            if stats:
                mins = stats.get('minutes', 0) or 0
                goals = stats.get('goals', 0) or 0
                assists = stats.get('assists', 0) or 0
                rating = stats.get('rating')
                rating_str = f"⭐{float(rating):.1f}" if rating else ''
                stats_str = f"{mins}' {goals}G {assists}A {rating_str}".strip()
            
            lines.append(f"| {player_name} | {loan_team} | {stats_str} |")
        
        lines.append('')
    
    lines.append('---')
    lines.append('*via [The Academy Watch](https://theacademywatch.com)*')
    
    return '\n'.join(lines)


def generate_post_title(newsletter: dict, team_name: str) -> str:
    """Generate a Reddit post title from newsletter data.
    
    Args:
        newsletter: The newsletter dict
        team_name: Name of the team
        
    Returns:
        Post title string
    """
    # Parse structured content if needed
    content = newsletter
    structured_content = newsletter.get('structured_content')
    if isinstance(structured_content, str):
        try:
            content = json.loads(structured_content)
        except (json.JSONDecodeError, TypeError):
            content = newsletter
    
    # Get date range
    date_range = content.get('range', [])
    if date_range and len(date_range) >= 2:
        start_date = format_date(date_range[0])
        end_date = format_date(date_range[1])
        date_str = f"{start_date} - {end_date}"
    else:
        date_str = datetime.now().strftime('%-d %b %Y')
    
    return f"[Academy Watch] {team_name} Pipeline Update | {date_str}"









