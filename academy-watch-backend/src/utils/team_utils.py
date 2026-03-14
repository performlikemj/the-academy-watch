from src.models.league import TeamAlias, db
from sqlalchemy import func

def normalize_team_name(team_name):
    """
    Normalize a team name using the TeamAlias table.
    
    Args:
        team_name (str): The team name to normalize.
        
    Returns:
        str: The canonical team name if an alias is found, otherwise the original name (stripped).
    """
    if not team_name:
        return team_name
        
    name = team_name.strip()
    
    # Check for exact alias match (case-insensitive)
    alias = TeamAlias.query.filter(func.lower(TeamAlias.alias) == func.lower(name)).first()
    
    if alias:
        return alias.canonical_name
        
    return name

def get_canonical_team_id(team_name):
    """
    Get the team ID for a given team name (checking aliases).
    
    Args:
        team_name (str): The team name.
        
    Returns:
        int: The team ID if found via alias or direct lookup (if implemented), else None.
    """
    if not team_name:
        return None
        
    name = team_name.strip()
    
    # Check alias first
    alias = TeamAlias.query.filter(func.lower(TeamAlias.alias) == func.lower(name)).first()
    if alias and alias.team_id:
        return alias.team_id
        
    return None


def get_all_team_name_variations(team_name):
    """
    Get all known variations (aliases) for a team name, including the canonical name.
    
    Args:
        team_name (str): The team name to look up.
        
    Returns:
        list[str]: A list of all known names for this team.
    """
    if not team_name:
        return []
        
    canonical = normalize_team_name(team_name)
    
    # Find all aliases for this canonical name
    aliases = TeamAlias.query.filter(TeamAlias.canonical_name == canonical).all()
    
    variations = {canonical}
    for a in aliases:
        variations.add(a.alias)
        
    return list(variations)
