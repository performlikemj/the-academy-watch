from datetime import date, timedelta, datetime, timezone

def get_monday_range(target: date) -> tuple[date, date]:
    """Returns the Monday start and Sunday end for the week containing target."""
    start = target - timedelta(days=target.weekday())
    end = start + timedelta(days=6)
    return start, end

def get_season_gameweeks(season_start_year: int | None = None) -> list[dict]:
    """
    Generates a list of gameweeks for the season.
    If season_start_year is None, infers it from today's date.
    Returns a list of dicts with label, start_date, end_date, is_current.
    """
    today = datetime.now(timezone.utc).date()
    
    if season_start_year is None:
        # If we are in Jan-June, season started prev year.
        # If we are in July-Dec, season starts this year.
        # Using July 1st as cutoff.
        if today.month < 7:
            season_start_year = today.year - 1
        else:
            season_start_year = today.year
            
    # Season usually runs Aug -> May, but let's just generate weeks 
    # from July 1st to June 30th of next year to be safe.
    
    start_date = date(season_start_year, 7, 1) # July 1st
    end_date = date(season_start_year + 1, 6, 30) # June 30th next year
    
    # Find the first Monday on or after start_date to align with Monday-Sunday cycles
    # If start_date is Monday, use it. Else find next Monday.
    days_ahead = (7 - start_date.weekday()) % 7
    # If we want the week that *contains* July 1st even if it starts in June, we'd do differently.
    # But usually gameweeks are clean chunks. Let's stick to Monday starts.
    # If July 1 is Tues, the first full week starts next Monday.
    # Alternatively, we can just back up to the Monday of that week.
    # Let's back up to the Monday containing July 1st to ensure we don't miss early action.
    current_monday, _ = get_monday_range(start_date)
    
    weeks = []
    gameweek_num = 1
    
    while current_monday <= end_date:
        week_end = current_monday + timedelta(days=6)
        
        # Check if this week is "current" (contains today)
        is_current = current_monday <= today <= week_end
        
        # Format: Nov 10 - Nov 16, 2025
        # Only add year to end date for brevity, or if ranges span years?
        # Standard simple format: "Nov 10 - Nov 16" is usually enough if context is clear,
        # but adding year avoids ambiguity.
        start_str = current_monday.strftime('%b %d')
        end_str = week_end.strftime('%b %d, %Y')
        label = f"{start_str} - {end_str}"
        
        weeks.append({
            "id": f"{current_monday.isoformat()}_{week_end.isoformat()}",
            "label": label,
            "start_date": current_monday.isoformat(),
            "end_date": week_end.isoformat(),
            "is_current": is_current,
            "gameweek_number": gameweek_num
        })
        
        current_monday += timedelta(days=7)
        gameweek_num += 1
        
    # Sort by date descending so latest is top
    weeks.reverse()
    
    return weeks

