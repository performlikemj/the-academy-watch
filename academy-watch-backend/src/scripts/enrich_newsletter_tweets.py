#!/usr/bin/env python3
"""Enrich a newsletter with Twitter/X content via the TwitterEnrichmentService.

Usage:
    cd academy-watch-backend
    python -m src.scripts.enrich_newsletter_tweets --newsletter-id 215
    python -m src.scripts.enrich_newsletter_tweets --newsletter-id 215 --team-id 18
    python -m src.scripts.enrich_newsletter_tweets --newsletter-id 215 --dry-run

Requires TWITTER_BEARER_TOKEN in environment or .env file.
Optional: TWITTER_DEBUG=1 for verbose output.
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enrich a newsletter with Twitter/X content.",
    )
    parser.add_argument(
        "--newsletter-id",
        type=int,
        required=True,
        help="Database ID of the newsletter to enrich.",
    )
    parser.add_argument(
        "--team-id",
        type=int,
        default=None,
        help="Database ID of the parent team. Auto-detected from newsletter if omitted.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Search and filter tweets but do not persist CommunityTake rows.",
    )
    args = parser.parse_args()

    # Import Flask app to get DB context
    from src.main import app

    with app.app_context():
        from src.models.league import Newsletter
        from src.services.twitter_enrichment_service import TwitterEnrichmentService

        newsletter = Newsletter.query.get(args.newsletter_id)
        if not newsletter:
            print(f"Newsletter {args.newsletter_id} not found.", file=sys.stderr)
            return 1

        team_id = args.team_id or newsletter.team_id
        if not team_id:
            print("Could not determine team_id. Pass --team-id.", file=sys.stderr)
            return 1

        service = TwitterEnrichmentService()
        if not service.is_configured():
            print(
                "TWITTER_BEARER_TOKEN not set or too short. Set it in the environment or .env file.",
                file=sys.stderr,
            )
            return 1

        print(
            f"Enriching newsletter {args.newsletter_id} "
            f"({newsletter.week_start_date} → {newsletter.week_end_date}) "
            f"for team {team_id}"
        )

        if args.dry_run:
            print("DRY RUN — tweets will be searched and filtered but not persisted.")
            import json

            content = newsletter.content
            if isinstance(content, str):
                content = json.loads(content)
            contexts = service._extract_player_contexts(
                content,
                newsletter.team.name if newsletter.team else "",
            )
            for ctx in contexts:
                start = f"{newsletter.week_start_date.isoformat()}T00:00:00Z"
                end = f"{newsletter.week_end_date.isoformat()}T23:59:59Z"
                raw = service._search_tweets(ctx, start, end)
                quality = service._quality_filter(raw, ctx)
                print(f"\n  {ctx.player_name} ({ctx.full_name}, {ctx.club})")
                print(f"    Raw: {len(raw)} | Quality: {len(quality)}")
                for tw in quality:
                    print(f'    [{tw.score}] @{tw.author_username}: "{tw.text[:80]}..." ({tw.accept_reason})')
            return 0

        result = service.enrich_newsletter(args.newsletter_id, team_id)
        print(f"\nDone: {result}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
