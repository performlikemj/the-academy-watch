"""Reddit Service for posting newsletters to subreddits.

This service handles all Reddit operations using PRAW (Python Reddit API Wrapper).
It provides methods for authenticating, posting newsletters, and managing posts.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional, List

import praw
from prawcore.exceptions import PrawcoreException

logger = logging.getLogger(__name__)


class RedditServiceError(Exception):
    """Base exception for Reddit service errors."""
    pass


class RedditAuthenticationError(RedditServiceError):
    """Raised when Reddit authentication fails."""
    pass


class RedditPostingError(RedditServiceError):
    """Raised when posting to Reddit fails."""
    pass


class RedditService:
    """Service for interacting with Reddit API via PRAW.
    
    This service uses a single bot account to post
    loan reports to various team subreddits.
    """
    
    _instance: Optional['RedditService'] = None
    _reddit: Optional[praw.Reddit] = None
    
    def __init__(self):
        """Initialize the Reddit service with environment credentials."""
        self.client_id = os.environ.get('REDDIT_CLIENT_ID')
        self.client_secret = os.environ.get('REDDIT_CLIENT_SECRET')
        self.username = os.environ.get('REDDIT_USERNAME')
        self.password = os.environ.get('REDDIT_PASSWORD')
        self.user_agent = os.environ.get('REDDIT_USER_AGENT', 'TheAcademyWatch/1.0 by /u/TheAcademyWatchBot')
        
    @classmethod
    def get_instance(cls) -> 'RedditService':
        """Get or create a singleton instance of the Reddit service."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def is_configured(self) -> bool:
        """Check if Reddit credentials are configured."""
        return all([
            self.client_id,
            self.client_secret,
            self.username,
            self.password
        ])
    
    def authenticate(self) -> praw.Reddit:
        """Authenticate with Reddit and return a PRAW Reddit instance.
        
        Returns:
            praw.Reddit: Authenticated Reddit instance
            
        Raises:
            RedditAuthenticationError: If authentication fails
        """
        if not self.is_configured():
            raise RedditAuthenticationError(
                "Reddit credentials not configured. Please set REDDIT_CLIENT_ID, "
                "REDDIT_CLIENT_SECRET, REDDIT_USERNAME, and REDDIT_PASSWORD environment variables."
            )
        
        if self._reddit is not None:
            return self._reddit
        
        try:
            self._reddit = praw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                username=self.username,
                password=self.password,
                user_agent=self.user_agent
            )
            
            # Verify authentication by accessing the user
            _ = self._reddit.user.me()
            logger.info(f"Successfully authenticated as Reddit user: {self.username}")
            
            return self._reddit
            
        except PrawcoreException as e:
            logger.error(f"Reddit authentication failed: {e}")
            raise RedditAuthenticationError(f"Failed to authenticate with Reddit: {e}")
    
    def post_to_subreddit(
        self,
        subreddit_name: str,
        title: str,
        body: str,
        flair_text: Optional[str] = None
    ) -> dict:
        """Post a text submission to a subreddit.
        
        Args:
            subreddit_name: Name of the subreddit (without r/)
            title: Title of the post
            body: Markdown body content
            flair_text: Optional flair to apply
            
        Returns:
            dict with 'post_id', 'post_url', and 'permalink'
            
        Raises:
            RedditPostingError: If posting fails
        """
        try:
            reddit = self.authenticate()
            subreddit = reddit.subreddit(subreddit_name)
            
            # Check if we can post to this subreddit
            # Some subreddits have karma/age requirements
            
            submission = subreddit.submit(
                title=title,
                selftext=body,
                flair_text=flair_text
            )
            
            logger.info(f"Successfully posted to r/{subreddit_name}: {submission.id}")
            
            return {
                'post_id': submission.id,
                'post_url': f"https://reddit.com{submission.permalink}",
                'permalink': submission.permalink
            }
            
        except PrawcoreException as e:
            error_msg = str(e)
            logger.error(f"Failed to post to r/{subreddit_name}: {error_msg}")
            raise RedditPostingError(f"Failed to post to r/{subreddit_name}: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Unexpected error posting to r/{subreddit_name}: {error_msg}")
            raise RedditPostingError(f"Unexpected error: {error_msg}")
    
    def delete_post(self, post_id: str) -> bool:
        """Delete a Reddit post by its ID.
        
        Args:
            post_id: The Reddit post ID
            
        Returns:
            True if deletion was successful
            
        Raises:
            RedditPostingError: If deletion fails
        """
        try:
            reddit = self.authenticate()
            submission = reddit.submission(id=post_id)
            submission.delete()
            logger.info(f"Successfully deleted Reddit post: {post_id}")
            return True
            
        except PrawcoreException as e:
            logger.error(f"Failed to delete Reddit post {post_id}: {e}")
            raise RedditPostingError(f"Failed to delete post: {e}")
    
    def get_post_info(self, post_id: str) -> Optional[dict]:
        """Get information about a Reddit post.
        
        Args:
            post_id: The Reddit post ID
            
        Returns:
            dict with post information or None if not found
        """
        try:
            reddit = self.authenticate()
            submission = reddit.submission(id=post_id)
            
            return {
                'id': submission.id,
                'title': submission.title,
                'url': f"https://reddit.com{submission.permalink}",
                'score': submission.score,
                'upvote_ratio': submission.upvote_ratio,
                'num_comments': submission.num_comments,
                'created_utc': datetime.fromtimestamp(submission.created_utc, tz=timezone.utc),
                'is_removed': submission.removed_by_category is not None,
            }
            
        except PrawcoreException as e:
            logger.warning(f"Could not fetch Reddit post {post_id}: {e}")
            return None


def post_newsletter_to_reddit(
    newsletter_id: int,
    team_subreddit_id: int,
    title: str,
    markdown_content: str,
    post_format: str = 'full'
) -> dict:
    """Post a newsletter to Reddit and record the result.
    
    This function handles the full workflow of posting to Reddit
    and recording the result in the database.
    
    Args:
        newsletter_id: ID of the newsletter being posted
        team_subreddit_id: ID of the team_subreddit record
        title: Title for the Reddit post
        markdown_content: The markdown content to post
        post_format: 'full' or 'compact'
        
    Returns:
        dict with posting result
    """
    from src.models.league import db, TeamSubreddit, RedditPost, Newsletter
    
    # Get the subreddit configuration
    team_subreddit = db.session.get(TeamSubreddit, team_subreddit_id)
    if not team_subreddit:
        raise RedditPostingError(f"TeamSubreddit {team_subreddit_id} not found")
    
    if not team_subreddit.is_active:
        raise RedditPostingError(f"Subreddit r/{team_subreddit.subreddit_name} is not active")
    
    # Check if already posted
    existing = RedditPost.query.filter_by(
        newsletter_id=newsletter_id,
        team_subreddit_id=team_subreddit_id
    ).first()
    
    if existing and existing.status == 'success':
        return {
            'status': 'already_posted',
            'post_url': existing.reddit_post_url,
            'message': 'Newsletter already posted to this subreddit'
        }
    
    # Create or update the RedditPost record
    if existing:
        reddit_post = existing
    else:
        reddit_post = RedditPost(
            newsletter_id=newsletter_id,
            team_subreddit_id=team_subreddit_id,
            post_title=title,
            status='pending'
        )
        db.session.add(reddit_post)
        db.session.flush()
    
    # Attempt to post to Reddit
    service = RedditService.get_instance()
    
    try:
        result = service.post_to_subreddit(
            subreddit_name=team_subreddit.subreddit_name,
            title=title,
            body=markdown_content
        )
        
        # Update the record with success
        reddit_post.reddit_post_id = result['post_id']
        reddit_post.reddit_post_url = result['post_url']
        reddit_post.status = 'success'
        reddit_post.posted_at = datetime.now(timezone.utc)
        reddit_post.error_message = None
        
        db.session.commit()
        
        return {
            'status': 'success',
            'post_id': result['post_id'],
            'post_url': result['post_url'],
            'subreddit': team_subreddit.subreddit_name
        }
        
    except RedditPostingError as e:
        # Update the record with failure
        reddit_post.status = 'failed'
        reddit_post.error_message = str(e)
        db.session.commit()
        
        return {
            'status': 'failed',
            'error': str(e),
            'subreddit': team_subreddit.subreddit_name
        }


def get_team_subreddits(team_id: int, active_only: bool = True) -> List[dict]:
    """Get all subreddit configurations for a team.
    
    Args:
        team_id: The team's database ID
        active_only: If True, only return active subreddits
        
    Returns:
        List of subreddit configuration dicts
    """
    from src.models.league import TeamSubreddit
    
    query = TeamSubreddit.query.filter_by(team_id=team_id)
    if active_only:
        query = query.filter_by(is_active=True)
    
    return [sub.to_dict() for sub in query.all()]


def get_newsletter_reddit_posts(newsletter_id: int) -> List[dict]:
    """Get all Reddit posts for a newsletter.
    
    Args:
        newsletter_id: The newsletter's database ID
        
    Returns:
        List of Reddit post dicts
    """
    from src.models.league import RedditPost
    
    posts = RedditPost.query.filter_by(newsletter_id=newsletter_id).all()
    return [post.to_dict() for post in posts]









