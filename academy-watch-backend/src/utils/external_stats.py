"""
Utility to fetch external stats using Brave Search and the stats parser.
"""
import logging
from typing import Dict, Any, Optional
from datetime import date

from src.utils.brave_players import BravePlayerCollection
from src.services.stats_parser import parse_stats_from_text

logger = logging.getLogger(__name__)

def fetch_external_stats(
    player_name: str,
    team_name: str,
    match_date: date,
    competition: Optional[str] = None
) -> Dict[str, Any]:
    """
    Attempt to fetch stats for a player in a specific match using external search.
    """
    try:
        # Construct a targeted search query
        date_str = match_date.strftime('%Y-%m-%d')
        query = f"{player_name} {team_name} match stats {date_str}"
        if competition:
            query += f" {competition}"
            
        logger.info(f"🔍 Searching for external stats: {query}")
        
        # Use Brave to get search results
        # We reuse BravePlayerCollection logic or just use the underlying search function if available.
        # Since BravePlayerCollection is for loans, we might need a simpler search wrapper.
        # For now, let's assume we can use the existing brave client pattern.
        
        from src.mcp.brave import search_brave # Assuming this exists or we can import the client
        
        # If search_brave isn't directly exposed, we might need to instantiate the client like in brave_players.py
        # Let's check how brave_players.py does it.
        # It seems to use `BraveSearch` class.
        
        from src.mcp.brave import BraveSearch
        brave = BraveSearch()
        
        results = brave.search(query, count=3)
        
        if not results or 'web' not in results or 'results' not in results['web']:
            logger.warning("No search results found for external stats")
            return {}
            
        # Aggregate snippets from top results
        snippets = []
        for res in results['web']['results']:
            title = res.get('title', '')
            desc = res.get('description', '')
            snippets.append(f"Title: {title}\nDescription: {desc}")
            
        combined_text = "\n---\n".join(snippets)
        
        # Parse the combined text
        stats = parse_stats_from_text(combined_text, player_name, team_name)
        
        if stats:
            logger.info(f"✅ Successfully extracted external stats for {player_name}: {stats}")
            return stats
            
    except Exception as e:
        logger.warning(f"Failed to fetch external stats: {e}")
        
    return {}
