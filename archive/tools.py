import json
from typing import Annotated
from langchain.tools import tool
from bs4 import BeautifulSoup
import requests
from urllib.parse import quote_plus
from typing import List, Dict, Optional
import backoff
import re
import os
import praw
from functools import lru_cache
from praw.models import MoreComments
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
try:
    from pydantic.v1 import BaseModel, Field
except ImportError:
    from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential
import time


@retry(stop=stop_after_attempt(3), 
       wait=wait_exponential(multiplier=1, min=4, max=10),
       reraise=True)
async def safe_ai_call(invoke_func, *args, **kwargs):
    try:
        return await invoke_func(*args, **kwargs)
    except Exception as e:
        print(f"API Error: {str(e)}")
        raise

allowed_domains = [
    'marxists.org',
    'marx2mao.com',
    'bannedthought.net',
    'marxist.com',
    'marxistphilosophy.org',
    'communist.red',
    'reddit.com'
]

@lru_cache(maxsize=100)
def get_reddit_client():
    return praw.Reddit(
        client_id=os.getenv('REDDIT_CLIENT_ID'),
        client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
        username=os.getenv('REDDIT_USERNAME'),
        password=os.getenv('REDDIT_PASSWORD'),
        user_agent=os.getenv('REDDIT_USER_AGENT'),
        ratelimit_seconds=300,
        check_for_async=False
    )

class ToolOutput(BaseModel):
    content: str = Field(description="Processed content from the tool")
    sources: List[str] = Field(description="List of source URLs used")
    tool_name: str

class RestrictedWebSearchInput(BaseModel):
    query: str = Field(description="Search query to look up")

class UrlScraperInput(BaseModel):
    url: str = Field(description="URL to scrape content from")
class RedditSearchInput(BaseModel):
    query: str = Field(description="Search query for Reddit")
    time_filter: str = Field("year", description="Time filter for search", enum=["hour", "day", "week", "month", "year"])

@tool(args_schema=RestrictedWebSearchInput)
@retry
def restricted_web_search(query: str) -> Dict:
    """Performs web search restricted to allowed domains using DuckDuckGo.
    Use for initial research phase to gather relevant documents.
    """
    try:
        site_filter = " OR ".join([f"site:{d}" for d in allowed_domains])
        enhanced_query = f"{query} {site_filter}"
        print(f"Sending request to DuckDuckGo with query length: {len(enhanced_query)}")
        search = DuckDuckGoSearchAPIWrapper(max_results=5)
        results = search.results(enhanced_query, 5)
        
        # Log the actual response for debugging
        print(f"Raw search results: {results}")

        # Check if results is a list and handle accordingly
        if isinstance(results, list):
            print("Received a list instead of an expected object.")
            return ToolOutput(
                content="Search error: Unexpected response format.",
                sources=[],
                tool_name="error in restricted web search"
            ).dict()

        print(f"Response status: {results.status if results else 'None'}")
        filtered = [
            {"title": r["title"], "url": r["link"], "snippet": r["snippet"]}
            for r in results if any(d in r["link"] for d in allowed_domains)
        ]
        print(f"18apr debug {filtered=}")
        return ToolOutput(
            content=json.dumps(filtered),
            sources=[r["url"] for r in filtered],
            tool_name="restricted_web_search"
        ).dict()
    
    except Exception as e:
        print(f"Error during search: {str(e)}")
        if "Ratelimit" in str(e):
            print("Rate limit reached. Waiting before retrying...")
            time.sleep(10)  # Wait for 10 seconds before retrying
            return restricted_web_search(query)  # Retry the same query

        # Attempt a second call with a modified query
        try:
            fallback_query = f"{query} site:marxists.org"
            print(f"Retrying with fallback query: {fallback_query}")
            results = search.results(fallback_query, 5)
            # Process results as before...
            # (Include the same logic for processing results here)
        except Exception as fallback_exception:
            print(f"Error on fallback: {str(fallback_exception)}")
        return ToolOutput(
                content=f"Search error on fallback: {str(fallback_exception)}",
            sources=[],
            tool_name="error in restricted web search"
        ).dict()

allowed_subreddits = {
    'communism101', 'socialism', 'marxism',
    'communism', 'leftcommunism'
}

class MarxistScraper:
    def __init__(self):
        self.headers = {'User-Agent': 'MarxistResearchBot/2.1'}
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    @staticmethod
    def validate_url(url: str):
        if not any(d in url for d in allowed_domains):
            raise ValueError(f"Prohibited domain: {url}")

    @backoff.on_exception(backoff.expo, requests.exceptions.RequestException, max_tries=3)
    def _fetch(self, url: str) -> str:
        self.validate_url(url)
        response = self.session.get(url, timeout=15)
        response.raise_for_status()
        return response.text

    def _parse_marxists_org(self, html: str, query: str) -> List[dict]:
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        
        for result in soup.select('.archive-list-item'):
            title_elem = result.select_one('.title a')
            if title_elem and query.lower() in title_elem.text.lower():
                url = f"https://www.marxists.org{title_elem['href']}"
                content = result.select_one('.excerpt').text.strip() if result.select_one('.excerpt') else ''
                results.append({
                    'title': title_elem.text.strip(),
                    'url': url,
                    'excerpt': self._clean_text(content)[:250]
                })
        return results[:5] or [self._handle_empty_results('marxists_org_search', query)]

    def _clean_text(self, text: str) -> str:
        return re.sub(r'\s+', ' ', text).strip()

    def _handle_empty_results(self, tool_name: str, query: str) -> dict:
        return {
            'title': f"No results from {tool_name}",
            'url': "",
            'excerpt': f"Query: {query} - Consider broadening terms or checking temporal relevance"
        }

def format_reddit_url(subreddit: str, query: str) -> str:
    return f"https://www.reddit.com/r/{subreddit}/search/?q={quote_plus(query)}&restrict_sr=1"

def is_quality_content(submission) -> bool:
    return (submission.score > 2 and 
            not submission.over_18 and
            not submission.author == "[deleted]" and
            not submission.removed_by_category)

@tool(args_schema=RedditSearchInput)
@retry
def reddit_search(query: str, time_filter: str = "year") -> Dict:
    """Searches Marxist subreddits for contemporary working-class perspectives."""
    try:
        reddit = get_reddit_client()
        results = []
        sources = []
        
        for sub in allowed_subreddits:
            try:
                submissions = reddit.subreddit(sub).search(
                    query,
                    limit=3,
                    time_filter=time_filter,
                    sort="relevance"
                )
                
                for post in submissions:
                    # Skip actually removed or deleted posts
                    if (hasattr(post, 'removed_by_category') and post.removed_by_category is not None) or (hasattr(post, 'selftext') and post.selftext in ('[removed]', '[deleted]')):
                        continue
                    
                    # Build content from title and available text
                    post_text = post.selftext[:500] if hasattr(post, 'selftext') and post.selftext else "Link post - see URL for content"
                    content = f"**{post.title}**\nScore: {post.score}\n{post_text}"
                    results.append(content)
                    sources.append(f"https://reddit.com{post.permalink}")
                    
                    # Handle comments more carefully
                    post.comments.replace_more(limit=0)  # Don't load MoreComments
                    for comment in post.comments.list()[:3]:  # Top 3 comments
                        if hasattr(comment, 'body') and comment.body.strip() and not getattr(comment, 'removed', False):
                            author = getattr(comment, 'author', '[deleted]')
                            results.append(f"Comment by {author}: {comment.body[:300]}")
                            sources.append(f"https://reddit.com{comment.permalink}")
            
            except Exception as e:
                print(f"Error searching subreddit {sub}: {str(e)}")
                continue
        
        return ToolOutput(
            content="\n\n".join(results)[:4000] if results else "No relevant Reddit discussions found",
            sources=sources,
            tool_name="reddit_search"
        ).dict()
    
    except Exception as e:
        return ToolOutput(
            content=f"Reddit error: {str(e)}",
            sources=[],
            tool_name="error in reddit_search"
        ).dict()



@tool(args_schema=UrlScraperInput)
@retry
def url_scraper(url: str) -> Dict:
    """Scrapes and processes content from a single URL. 
    Verify URL belongs to allowed domains before scraping.
    """
    try:
        if not any(d in url for d in allowed_domains):
            raise ValueError("Prohibited domain")
            
        response = requests.get(url, timeout=15, headers={'User-Agent': 'ResearchBot/2.0'})
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        main_content = soup.find('article') or soup.find('main') or soup.body
        
        # Clean content
        text = main_content.get_text(separator='\n', strip=True)
        text = re.sub(r'\n{3,}', '\n\n', text)[:3000]  # Truncate to fit context
        
        return ToolOutput(
            content=text,
            sources=[url],
            tool_name="url_scrapper"
        ).dict()
        
    except Exception as e:
        return ToolOutput(
            content=f"Scraping error: {str(e)}",
            sources=[],
            tool_name="error in url_scrapper"
        ).dict()
