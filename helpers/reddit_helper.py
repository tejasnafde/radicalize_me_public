import os
from typing import Dict, List
from .common_helpers import CommonHelpers
from .logger import get_logger
from .reddit_ranker import RedditRanker


class RedditHelper:
    def __init__(self):
        self.logger = get_logger()
        self.common_helpers = CommonHelpers()
        self.reddit = self.common_helpers.get_reddit_client()
        self.ranker = RedditRanker()  # Initialize semantic ranker
        self.allowed_subreddits = {
            'communism101', 'socialism', 'marxism',
            'communism', 'leftcommunism'
        }

    async def search_reddit(self, query: str) -> Dict:
        """
        Searches Reddit for relevant discussions in leftist subreddits.
        Uses semantic ranking to improve relevance over engagement metrics.
        """
        try:
            await self.common_helpers.check_rate_limit('reddit_search')
            
            all_posts = []
            
            self.logger.debug(f"Starting Reddit search for query: {query}", "REDDIT")
            
            for subreddit_name in self.allowed_subreddits:
                try:
                    self.logger.debug(f"Searching subreddit: r/{subreddit_name}", "REDDIT")
                    subreddit = self.reddit.subreddit(subreddit_name)
                    
                    # Search submissions in this subreddit
                    submissions = subreddit.search(
                        query,
                        limit=10,  # Get more posts per subreddit to find quality content
                        time_filter="year",
                        sort="relevance"
                    )
                    
                    for post in submissions:
                        # Skip actually removed or deleted posts
                        if (hasattr(post, 'removed_by_category') and post.removed_by_category is not None) or \
                           (hasattr(post, 'selftext') and post.selftext in ('[removed]', '[deleted]')):
                            self.logger.debug(f"Skipping removed/deleted post: {post.title[:50]}...", "REDDIT")
                            continue
                        
                        # Store the actual post object for semantic ranking
                        all_posts.append(post)
                        
                except Exception as e:
                    self.logger.error(f"Error searching subreddit {subreddit_name}: {str(e)}", "REDDIT")
                    continue
            
            if all_posts:
                # Use semantic ranking to get most relevant posts
                self.logger.debug(f"Ranking {len(all_posts)} posts by semantic similarity", "REDDIT")
                ranked_posts = self.ranker.rank_by_relevance(query, all_posts, top_k=5)
                
                results = []
                sources = []
                
                for post in ranked_posts:
                    # Handle both text posts and link posts
                    if hasattr(post, 'selftext') and post.selftext and post.selftext.strip():
                        post_content = post.selftext[:800]  # Increased content length
                    else:
                        post_content = "Link post - see URL for content"
                    
                    # Format post content
                    formatted_content = (
                        f"**r/{post.subreddit.display_name} - {post.title}**\n"
                        f"Score: {post.score} | Comments: {post.num_comments} | "
                        f"Upvote Ratio: {getattr(post, 'upvote_ratio', 0.0):.2f}\n"
                        f"{post_content}\n"
                        f"URL: https://reddit.com{post.permalink}"
                    )
                    
                    results.append(formatted_content)
                    sources.append(f"https://reddit.com{post.permalink}")
                
                combined_content = "\n\n---\n\n".join(results)
                
                self.logger.debug(f"Reddit search completed: {len(ranked_posts)} posts found (ranked by relevance), "
                                f"{len(sources)} total sources, {len(combined_content)} characters", "REDDIT")
                
                return {
                    "content": combined_content,
                    "sources": sources,
                    "posts_count": len(ranked_posts),
                    "total_characters": len(combined_content),
                    "tool_name": "reddit_search"
                }
            else:
                self.logger.warning("No relevant Reddit discussions found", "REDDIT")
                return {
                    "content": "No relevant Reddit discussions found",
                    "sources": [],
                    "posts_count": 0,
                    "total_characters": 0,
                    "tool_name": "reddit_search"
                }
                
        except Exception as e:
            self.logger.error(f"Reddit search failed: {str(e)}", "REDDIT")
            return {
                "content": f"Reddit search error: {str(e)}",
                "sources": [],
                "posts_count": 0,
                "total_characters": 0,
                "tool_name": "reddit_search_error"
            }

    def get_subreddit_info(self, subreddit_name: str) -> Dict:
        """Get information about a specific subreddit"""
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            return {
                "name": subreddit_name,
                "display_name": subreddit.display_name,
                "subscribers": subreddit.subscribers,
                "description": subreddit.public_description[:200] if subreddit.public_description else "",
                "active": subreddit.active_user_count
            }
        except Exception as e:
            self.logger.error(f"Error getting subreddit info for {subreddit_name}: {str(e)}", "REDDIT")
            return {"error": str(e)}

    def list_available_subreddits(self) -> List[Dict]:
        """List information about all available subreddits"""
        subreddit_info = []
        for sub_name in self.allowed_subreddits:
            info = self.get_subreddit_info(sub_name)
            if "error" not in info:
                subreddit_info.append(info)
        return subreddit_info 