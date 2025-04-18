import json
from typing import Annotated
from langchain.tools import tool
from bs4 import BeautifulSoup
import requests
from urllib.parse import quote_plus
from typing import List, Dict
import backoff
import re
import os
import praw
from praw.models import MoreComments
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from pydantic import BaseModel, Field


allowed_domains = [
    'marxists.org',
    'marx2mao.com',
    'bannedthought.net',
    'marxist.com',
    'marxistphilosophy.org',
    'communist.red',
    'reddit.com'
]

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


@tool(args_schema=BaseModel, return_schema=ToolOutput)
def restricted_web_search(query: str) -> Dict:
    """Performs web search restricted to allowed domains using DuckDuckGo.
    Use for initial research phase to gather relevant documents.
    """
    try:
        site_filter = " OR ".join([f"site:{d}" for d in allowed_domains])
        enhanced_query = f"{query} {site_filter}"
        
        search = DuckDuckGoSearchAPIWrapper(max_results=5)
        results = search.results(enhanced_query, 5)
        
        filtered = [
            {"title": r["title"], "url": r["link"], "snippet": r["snippet"]}
            for r in results if any(d in r["link"] for d in allowed_domains)
        ]
        
        return ToolOutput(
            content=json.dumps(filtered),
            sources=[r["url"] for r in filtered]
        ).dict()
    
    except Exception as e:
        return ToolOutput(
            content=f"Search error: {str(e)}",
            sources=[]
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

class RedditInput(BaseModel):
    query: str
    time_filter: str = Field("year", enum=["hour", "day", "week", "month", "year"])

@tool(args_schema=RedditInput, return_schema=ToolOutput)
def reddit_search(query: str, time_filter: str = "year") -> Dict:
    """Searches Marxist subreddits for contemporary working-class perspectives.
    Focus on post-2020 discussions when analyzing current events.
    """
    try:
        reddit = praw.Reddit(
            client_id=os.getenv('REDDIT_CLIENT_ID'),
            client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
            user_agent=os.getenv('REDDIT_USER_AGENT')
        )
        
        results = []
        sources = []
        subreddits = ["communism101", "socialism", "marxism"]
        
        for sub in subreddits:
            submissions = reddit.subreddit(sub).search(
                query,
                limit=3,
                time_filter=time_filter,
                sort="relevance"
            )
            
            for post in submissions:
                if post.removed or post.selftext == "[removed]":
                    continue
                
                content = f"**{post.title}**\nScore: {post.score}\n{post.selftext[:500]}"
                results.append(content)
                sources.append(f"https://reddit.com{post.permalink}")
                
                post.comments.replace_more(limit=2)
                for comment in post.comments[:3]:
                    if not comment.removed and comment.body.strip():
                        results.append(f"Comment by {comment.author}: {comment.body[:300]}")
                        sources.append(f"https://reddit.com{comment.permalink}")
        
        return ToolOutput(
            content="\n\n".join(results)[:4000],
            sources=sources
        ).dict()
    
    except Exception as e:
        return ToolOutput(
            content=f"Reddit error: {str(e)}",
            sources=[]
        ).dict()



@tool(args_schema=BaseModel, return_schema=ToolOutput)
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
            sources=[url]
        ).dict()
        
    except Exception as e:
        return ToolOutput(
            content=f"Scraping error: {str(e)}",
            sources=[]
        ).dict()
