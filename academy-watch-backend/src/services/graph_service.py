import os
from datetime import datetime, timezone
from src.models.league import db
from src.models.weekly import FixturePlayerStats, Fixture
import logging

logger = logging.getLogger(__name__)

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    logger.warning("⚠️ Matplotlib not found. Graph generation will be disabled.")

class GraphService:
    def __init__(self, static_folder=None):
        if static_folder:
            self.static_folder = static_folder
        else:
            # Default to src/static/graphs
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.static_folder = os.path.join(base_dir, 'static', 'graphs')
        
        if not os.path.exists(self.static_folder):
            os.makedirs(self.static_folder)

    def generate_player_rating_graph(self, player_id, player_name):
        """Generates a graph of player ratings over time."""
        if not HAS_MATPLOTLIB:
            logger.info(f"Skipping rating graph for {player_name} (matplotlib missing)")
            return None

        try:
            # Fetch stats
            stats_query = db.session.query(
                FixturePlayerStats, Fixture
            ).join(
                Fixture, FixturePlayerStats.fixture_id == Fixture.id
            ).filter(
                FixturePlayerStats.player_api_id == player_id
            ).order_by(
                Fixture.date_utc.asc()
            ).all()

            if not stats_query:
                return None

            dates = []
            ratings = []
            
            for stats, fixture in stats_query:
                if stats.rating and stats.rating > 0:
                    dates.append(fixture.date_utc)
                    ratings.append(stats.rating)

            if not ratings:
                return None

            # Plotting
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(dates, ratings, marker='o', linestyle='-', color='#1f77b4', linewidth=2)
            ax.set_title(f'{player_name} - Match Ratings')
            ax.set_ylabel('Rating')
            ax.set_ylim(0, 10)
            ax.grid(True, linestyle='--', alpha=0.7)
            
            # Format dates
            fig.autofmt_xdate()
            
            # Save
            timestamp = int(datetime.now(timezone.utc).timestamp())
            filename = f"rating_{player_id}_{timestamp}.png"
            filepath = os.path.join(self.static_folder, filename)
            fig.savefig(filepath, bbox_inches='tight', dpi=100)
            plt.close(fig)

            return f"/static/graphs/{filename}"
        except Exception as e:
            print(f"Error generating rating graph for {player_id}: {e}")
            return None

    def generate_player_minutes_graph(self, player_id, player_name):
        """Generates a bar chart of minutes played."""
        if not HAS_MATPLOTLIB:
            logger.info(f"Skipping minutes graph for {player_name} (matplotlib missing)")
            return None

        try:
            # Fetch stats
            stats_query = db.session.query(
                FixturePlayerStats, Fixture
            ).join(
                Fixture, FixturePlayerStats.fixture_id == Fixture.id
            ).filter(
                FixturePlayerStats.player_api_id == player_id
            ).order_by(
                Fixture.date_utc.asc()
            ).all()

            if not stats_query:
                return None

            dates = []
            minutes = []
            
            for stats, fixture in stats_query:
                if stats.minutes is not None:
                    dates.append(fixture.date_utc.strftime('%Y-%m-%d'))
                    minutes.append(stats.minutes)

            if not minutes:
                return None

            # Plotting
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.bar(dates, minutes, color='#2ca02c')
            ax.set_title(f'{player_name} - Minutes Played')
            ax.set_ylabel('Minutes')
            ax.set_ylim(0, 95) # Usually 90 mins + stoppage
            ax.grid(True, axis='y', linestyle='--', alpha=0.7)
            
            # Format x-axis labels if too many
            if len(dates) > 10:
                ax.set_xticks(range(0, len(dates), max(1, len(dates)//10)))
                ax.set_xticklabels([dates[i] for i in range(0, len(dates), max(1, len(dates)//10))], rotation=45, ha='right')
            else:
                plt.xticks(rotation=45, ha='right')

            # Save
            timestamp = int(datetime.now(timezone.utc).timestamp())
            filename = f"minutes_{player_id}_{timestamp}.png"
            filepath = os.path.join(self.static_folder, filename)
            fig.savefig(filepath, bbox_inches='tight', dpi=100)
            plt.close(fig)

            return f"/static/graphs/{filename}"
        except Exception as e:
            print(f"Error generating minutes graph for {player_id}: {e}")
            return None
