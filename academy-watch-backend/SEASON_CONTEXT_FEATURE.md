# Season Context Feature - Adding Narrative Depth to Weekly Reports

## Overview

The Season Context feature enriches weekly loan reports by providing cumulative season statistics and trends for each player. This allows the AI agent to add meaningful context and depth to weekly summaries, telling the full story of a player's season progression.

## The Problem

**Before:**
```
"Started and scored vs Arsenal. Good performance with 8.5 rating."
```

**Issue:** This tells us nothing about:
- Is this the player's first goal of the season or their 10th?
- Is this typical form or a standout performance?
- Are they on a scoring streak or breaking a drought?
- How does this compare to their season average?

## The Solution

**After:**
```
"Started and scored vs Arsenal (Rating: 8.5, 3/5 shots on target). This brings his 
season tally to 8 goals in 15 appearances, now averaging 0.6 goals per 90 minutes. 
His fourth goal in the last 5 games, establishing himself as a key outlet with 
excellent recent form."
```

**Benefits:**
- ✅ Season totals provide context
- ✅ Recent form shows trends
- ✅ Per-90 stats show efficiency
- ✅ Comparisons add depth
- ✅ Narratives emerge naturally

## Architecture

### 1. Data Collection Function

**Location:** `src/api_football_client.py`, lines 1444-1590

**Function:** `get_player_season_context()`

This function queries the database for all of a player's fixtures up to the report date and aggregates:

#### Season Stats (Cumulative)
- `games_played` - Total appearances
- `minutes` - Total minutes played
- `goals` - Total goals scored
- `assists` - Total assists
- `yellows` - Total yellow cards
- `reds` - Total red cards
- `avg_rating` - Average match rating
- `shots_total` / `shots_on` - Shot totals and accuracy
- `passes_key` - Key passes/chances created
- `tackles_total` - Defensive actions
- `duels_won` / `duels_total` - Physical dominance
- `clean_sheets` - For defenders/GKs

#### Recent Form (Last 5 Games)
Array of recent matches with:
- `date` - Match date
- `competition` - Competition name
- `goals` - Goals in that match
- `assists` - Assists in that match
- `minutes` - Minutes played
- `rating` - Match rating

#### Trends (Calculated Metrics)
- `goals_per_90` - Goal scoring rate per 90 minutes
- `assists_per_90` - Assist rate per 90 minutes
- `shot_accuracy` - Percentage of shots on target
- `goals_last_5` - Goals in last 5 games
- `assists_last_5` - Assists in last 5 games
- `g_a_last_5` - Combined goal contributions in last 5
- `duels_win_rate` - Percentage of duels won

### 2. Integration into Weekly Reports

**Location:** `src/api_football_client.py`, lines 1762-1778

Season context is fetched and attached to each player's summary:

```python
season_context = self.get_player_season_context(
    player_id=info["player_api_id"],
    loan_team_id=info["loan_team_api_id"],
    season=season,
    up_to_date=week_end,
    db_session=db_session,
)
s["season_context"] = season_context
```

### 3. AI Instructions

**Location:** `src/agents/weekly_agent.py`, lines 615-668

The AI is explicitly instructed to use season context:

#### When to Use Season Context

**Season Totals:**
- "brings his tally to 8 goals in 15 appearances"
- "now has 12 assists for the season"
- "reached double figures with his 10th goal"

**Recent Form:**
- "his fourth goal in the last 5 games"
- "ended a 6-game goalless drought"
- "scored in 3 consecutive matches"
- "yet to score this season"

**Trends:**
- "now averaging 0.7 goals per 90 minutes this season"
- "maintaining a 45% shot accuracy"
- "winning 78% of his duels"

**Comparisons:**
- "his best performance of the season"
- "matching his season average rating of 7.2"
- "below his usual standards"

**Milestones:**
- "reached 10 assists for the season"
- "first goal since September"
- "his 6th clean sheet in 12 games"

**Consistency:**
- "scored in 3 consecutive matches"
- "finding his rhythm after a slow start"
- "maintaining excellent form"

## Data Structure

Each player's weekly summary now includes:

```json
{
  "player_name": "J. Sancho",
  "loan_team_name": "Chelsea",
  "matches": [...],
  "totals": {...},
  "season_context": {
    "season_stats": {
      "games_played": 15,
      "minutes": 1245,
      "goals": 8,
      "assists": 5,
      "yellows": 2,
      "reds": 0,
      "avg_rating": 7.4,
      "shots_total": 42,
      "shots_on": 19,
      "passes_key": 31,
      "tackles_total": 18,
      "duels_won": 87,
      "duels_total": 118,
      "clean_sheets": 0
    },
    "recent_form": [
      {"date": "2024-10-20", "goals": 1, "assists": 0, "rating": 8.5},
      {"date": "2024-10-13", "goals": 0, "assists": 1, "rating": 7.2},
      {"date": "2024-10-06", "goals": 1, "assists": 1, "rating": 8.0},
      {"date": "2024-09-29", "goals": 0, "assists": 0, "rating": 6.8},
      {"date": "2024-09-22", "goals": 1, "assists": 0, "rating": 7.5}
    ],
    "trends": {
      "goals_per_90": 0.58,
      "assists_per_90": 0.36,
      "shot_accuracy": 45.2,
      "goals_last_5": 3,
      "assists_last_5": 2,
      "g_a_last_5": 5,
      "duels_win_rate": 73.7
    }
  }
}
```

## Use Cases & Examples

### Example 1: Striker Finding Form

**Without Season Context:**
```
"Scored twice vs Brighton. Excellent performance with 8.9 rating."
```

**With Season Context:**
```
"Scored twice vs Brighton (Rating: 8.9, 4/6 shots on target), his first goals since 
the opening day in August. This ends a frustrating 8-game drought and brings his 
season tally to 3 goals in 11 appearances. With 0.26 goals per 90 minutes, he'll 
be eager to build on this breakthrough performance."
```

### Example 2: Midfielder on Hot Streak

**Without Season Context:**
```
"Assisted the winner vs Liverpool. Strong game."
```

**With Season Context:**
```
"Assisted the winner vs Liverpool (Rating: 7.8, 5 key passes), his fifth assist in 
the last 4 games. This brings his season tally to 11 assists in just 13 appearances, 
averaging 0.76 per 90 minutes - among the best in the division. Orchestrating attacks 
with remarkable consistency."
```

### Example 3: Defender's Consistent Form

**Without Season Context:**
```
"Started and kept a clean sheet vs Chelsea."
```

**With Season Context:**
```
"Started and kept a clean sheet vs Chelsea (Rating: 7.5, 4 tackles, 3 interceptions, 
won 11/13 duels). His 8th clean sheet in 16 appearances this season, maintaining an 
impressive 50% clean sheet rate. Winning 79% of his duels across the season, he's 
become a cornerstone of the defense."
```

### Example 4: Goalkeeper Having Career Season

**Without Season Context:**
```
"Made 6 saves in 2-1 win vs Arsenal."
```

**With Season Context:**
```
"Made 6 crucial saves in the 2-1 win vs Arsenal (Rating: 8.3), his 10th clean sheet 
of the season. Having played all 18 games with a 56% clean sheet rate and averaging 
7.6 per match - his best season to date. Establishing himself as the undisputed 
number one."
```

### Example 5: Young Player Struggling

**Without Season Context:**
```
"Started but struggled vs Manchester United. Rating 6.2."
```

**With Season Context:**
```
"Started but struggled vs Manchester United (Rating: 6.2, 0/4 shots on target, lost 
8/12 duels). Yet to score in 9 appearances this season despite accumulating 0.8 
expected goals per 90. The 20-year-old is still finding his feet at this level but 
shows promise with consistent minutes and strong work rate."
```

## Technical Details

### Database Query

The function queries `Fixture` and `FixturePlayerStats` tables:

```python
fixtures = (
    db_session.query(Fixture)
    .join(FixturePlayerStats)
    .filter(
        FixturePlayerStats.player_api_id == player_id,
        Fixture.season == season,
        Fixture.date_utc <= up_to_date.isoformat()
    )
    .order_by(Fixture.date_utc.desc())
    .limit(100)  # Safety limit
    .all()
)
```

### Performance Considerations

- **Efficient Query:** Uses indexed fields (player_api_id, season, date)
- **Limited Results:** Max 100 fixtures per player (covers full season)
- **Cached in Memory:** Context calculated once per player per report generation
- **Minimal Overhead:** ~50-100ms per player depending on fixture count
- **DB-First:** Uses stored fixture stats when available, avoids API calls

### Error Handling

If season context fails to load:
```python
except Exception as e:
    logger.warning(f"Failed to get season context for player {player_id}: {e}")
    s["season_context"] = {'season_stats': {}, 'recent_form': [], 'trends': {}}
```

The system gracefully degrades - the weekly report still generates, just without the extra context.

## Integration Points

### 1. Weekly Report Generation
**File:** `src/api_football_client.py`
- `get_player_season_context()` - Gathers season data
- `summarize_parent_loans_week()` - Attaches context to each player

### 2. AI Agent Instructions
**File:** `src/agents/weekly_agent.py`
- System instructions updated to explain season_context structure
- Examples provided for how to use the data
- Guidelines for when to reference season stats vs weekly stats

### 3. Newsletter Rendering
**File:** `src/agents/weekly_agent.py`
- Season context available in template data
- Can be displayed in player cards, tooltips, or detailed views

## Testing

### Test Coverage

**File:** `tests/test_weekly_agent.py`, lines 539-602

**Test:** `test_season_context_structure()`
- Verifies season_context structure is preserved
- Checks all required fields exist
- Validates data types and values

### Manual Testing

To verify season context is working:

1. Generate a weekly report for a team with active loanees
2. Check the response JSON for each player
3. Verify `season_context` field exists with:
   - `season_stats` (cumulative totals)
   - `recent_form` (last 5 games)
   - `trends` (calculated metrics)
4. Check AI-generated summary references season data

Example verification:
```python
report = client.summarize_parent_loans_week(...)
for loanee in report['loanees']:
    ctx = loanee.get('season_context')
    print(f"{loanee['player_name']}:")
    print(f"  Season: {ctx['season_stats']['goals']}G {ctx['season_stats']['assists']}A in {ctx['season_stats']['games_played']} games")
    print(f"  Trends: {ctx['trends']['goals_per_90']} G/90, {ctx['trends']['shot_accuracy']}% accuracy")
    print(f"  Recent: {ctx['trends']['goals_last_5']} goals in last 5")
```

## Future Enhancements

### Potential Additions

1. **Comparative Context**
   - Compare to other loanees from same parent club
   - Compare to league averages for position
   - Compare to previous season (if applicable)

2. **Advanced Trends**
   - Form trajectory (improving/declining)
   - Hot/cold streaks detection
   - Performance vs opponent quality
   - Home vs away splits

3. **Predictive Insights**
   - Expected goals (xG) vs actual goals
   - Overperforming/underperforming their metrics
   - Sustainability of current form

4. **Historical Context**
   - Career-best performances
   - Season-on-season progression
   - Development trajectory for young players

5. **Visual Elements**
   - Form graphs (goals/assists over time)
   - Heat maps of performance metrics
   - Comparison charts

### Data Enrichment

Currently uses stored fixture data. Could enhance with:
- Competition-specific breakdowns (league vs cup)
- Starting vs substitute appearances
- Performance by opponent strength
- Weather/pitch conditions impact

## Benefits Summary

### For Fans
- ✅ Richer, more engaging updates
- ✅ Better understanding of player development
- ✅ Context for highs and lows
- ✅ Ability to track progress over time

### For Coaches/Scouts
- ✅ Data-driven performance insights
- ✅ Form tracking and trend analysis
- ✅ Identification of consistency patterns
- ✅ Comparison across multiple loanees

### For Players
- ✅ Tangible metrics to track improvement
- ✅ Recognition of achievements (milestones)
- ✅ Context for their development journey

### For Content Quality
- ✅ Professional-level analysis
- ✅ Narrative depth and storytelling
- ✅ Fact-based reporting
- ✅ Engaging, informative content

## Conclusion

The Season Context feature transforms weekly loan reports from isolated snapshots into chapters of a longer story. By providing cumulative statistics, recent form analysis, and calculated trends, the AI can write summaries that are:

- **More Informative** - Full picture of player progress
- **More Engaging** - Narratives and storylines emerge
- **More Professional** - Data-driven insights
- **More Valuable** - Actionable for decision-makers

This feature leverages existing data in the database and adds minimal overhead while significantly enhancing the quality and depth of the generated reports.

## Files Modified

1. **`src/api_football_client.py`**
   - Lines 1444-1590: `get_player_season_context()` function
   - Lines 1762-1778: Integration into weekly summaries

2. **`src/agents/weekly_agent.py`**
   - Lines 619-622: Data structure documentation
   - Lines 642-649: Season context usage guidelines
   - Lines 664-665: Updated example with season context

3. **`tests/test_weekly_agent.py`**
   - Lines 539-602: Season context structure test

