import os
from typing import Dict, List
from .common_helpers import CommonHelpers
from .logger import get_logger


class RedditHelper:
    def __init__(self):
        self.logger = get_logger()
        self.common_helpers = CommonHelpers()
        self.reddit = self.common_helpers.get_reddit_client()
        self.allowed_subreddits = {
            'communism101', 'socialism', 'marxism',
            'communism', 'leftcommunism'
        }

    async def search_reddit(self, query: str) -> Dict:
        """
        Searches Reddit for relevant discussions in leftist subreddits.
        This is the improved version from tools.py with proper filtering.
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
                        
                        # Handle both text posts and link posts
                        if hasattr(post, 'selftext') and post.selftext and post.selftext.strip():
                            post_content = post.selftext[:800]  # Increased content length
                        else:
                            post_content = "Link post - see URL for content"
                        
                        # Store post data for sorting
                        post_data = {
                            "title": post.title,
                            "content": post_content,
                            "score": post.score,
                            "subreddit": subreddit_name,
                            "url": f"https://reddit.com{post.permalink}",
                            "created_utc": post.created_utc,
                            "num_comments": post.num_comments,
                            "upvote_ratio": getattr(post, 'upvote_ratio', 0.0),
                            # Calculate relevance score (score + comment engagement)
                            "relevance_score": post.score + (post.num_comments * 0.5)
                        }
                        
                        all_posts.append(post_data)
                        
                except Exception as e:
                    self.logger.error(f"Error searching subreddit {subreddit_name}: {str(e)}", "REDDIT")
                    continue
            
            if all_posts:
                # Sort by relevance score (descending) and take top 5
                sorted_posts = sorted(all_posts, key=lambda x: x['relevance_score'], reverse=True)[:5]
                
                results = []
                sources = []
                
                for post_data in sorted_posts:
                    # Format post content
                    formatted_content = (
                        f"**r/{post_data['subreddit']} - {post_data['title']}**\n"
                        f"Score: {post_data['score']} | Comments: {post_data['num_comments']} | "
                        f"Upvote Ratio: {post_data['upvote_ratio']:.2f}\n"
                        f"{post_data['content']}\n"
                        f"URL: {post_data['url']}"
                    )
                    
                    results.append(formatted_content)
                    sources.append(post_data['url'])
                
                combined_content = "\n\n---\n\n".join(results)
                
                self.logger.debug(f"Reddit search completed: {len(sorted_posts)} posts found, "
                                f"{len(sources)} total sources, {len(combined_content)} characters", "REDDIT")
                
                return {
                    "content": combined_content,
                    "sources": sources,
                    "posts_count": len(sorted_posts),
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