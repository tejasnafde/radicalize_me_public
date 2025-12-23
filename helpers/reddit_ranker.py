"""
Reddit Semantic Ranker

Ranks Reddit posts by semantic similarity to the query using sentence transformers.
This improves relevance over simple engagement metrics (upvotes/comments).
"""

from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List
from helpers.logger import get_logger


class RedditRanker:
    def __init__(self):
        """Initialize the ranker with a lightweight sentence transformer model"""
        self.logger = get_logger()
        try:
            # Use a lightweight, free model that runs locally
            # all-MiniLM-L6-v2: 384 dimensions, 80MB, fast inference
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            self.logger.info("Reddit semantic ranker initialized successfully", "REDDIT_RANKER")
        except Exception as e:
            self.logger.error(f"Failed to initialize Reddit ranker: {str(e)}", "REDDIT_RANKER")
            self.model = None
    
    def rank_by_relevance(self, query: str, posts: list, top_k: int = 5) -> list:
        """
        Rank Reddit posts by semantic similarity to query
        
        Args:
            query: The search query
            posts: List of Reddit post objects (from PRAW)
            top_k: Number of top posts to return
            
        Returns:
            List of top_k most relevant posts, sorted by similarity
        """
        if not self.model:
            self.logger.warning("Ranker not initialized, returning posts as-is", "REDDIT_RANKER")
            return posts[:top_k]
        
        if not posts:
            return []
        
        try:
            # Encode the query
            query_embedding = self.model.encode(query, convert_to_tensor=False)
            
            scored_posts = []
            for post in posts:
                # Combine title and body for embedding
                # Limit text length to avoid memory issues
                text = f"{post.title} {post.selftext}"[:1000]
                
                # Encode the post
                post_embedding = self.model.encode(text, convert_to_tensor=False)
                
                # Calculate cosine similarity
                similarity = np.dot(query_embedding, post_embedding) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(post_embedding)
                )
                
                scored_posts.append((post, float(similarity)))
            
            # Sort by similarity (descending) and return top_k
            sorted_posts = sorted(scored_posts, key=lambda x: x[1], reverse=True)
            
            # Log similarity scores for debugging
            self.logger.debug(
                f"Top {min(top_k, len(sorted_posts))} post similarities: " +
                ", ".join([f"{score:.3f}" for _, score in sorted_posts[:top_k]]),
                "REDDIT_RANKER"
            )
            
            return [post for post, _ in sorted_posts[:top_k]]
            
        except Exception as e:
            self.logger.error(f"Error ranking posts: {str(e)}", "REDDIT_RANKER")
            # Fallback to original order
            return posts[:top_k]
