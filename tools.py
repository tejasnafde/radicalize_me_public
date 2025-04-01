from typing import Annotated
from langchain.tools import tool
from bs4 import BeautifulSoup
import requests
from urllib.parse import quote_plus
from typing import List
import backoff
import re
import os
import praw
from praw.models import MoreComments



# Load environment variables from main.py context
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
    """Initialize Reddit client AFTER .env loading"""
    return praw.Reddit(
        client_id=os.getenv('REDDIT_CLIENT_ID'),
        client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
        username=os.getenv('REDDIT_USERNAME'),
        password=os.getenv('REDDIT_PASSWORD'),
        user_agent=os.getenv('REDDIT_USER_AGENT'),
        ratelimit_seconds=300,
        check_for_async=False
    )

allowed_subreddits = {
    'communism101', 'socialism', 'marxism',
    'communism', 'leftcommunism'
}

class MarxistScraper:
    """Enhanced Marxist document scraper with dialectical materialist parsing"""
    
    def __init__(self):
        self.headers = {'User-Agent': 'MarxistResearchBot/2.1 (+https://github.com/your/repo)'}
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
        """Dialectical parser for marxists.org archive"""
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
        return results[:5]

    def _clean_text(self, text: str) -> str:
        return re.sub(r'\s+', ' ', text).strip()

def format_reddit_url(subreddit: str, query: str) -> str:
    """Generate Reddit search URL for reference"""
    return f"https://www.reddit.com/r/{subreddit}/search/?q={quote_plus(query)}&restrict_sr=1"

def is_quality_content(submission) -> bool:
    """Dialectical filter for Reddit content"""
    return (submission.score > 2 and 
            #not submission.over_18 and
            #not submission.author == "[deleted]" and
            not submission.removed_by_category)

#@backoff.on_exception(backoff.expo, praw.exceptions.APIException, max_tries=3)
@tool
def reddit_search(query: str) -> str:
    """Search Marxist subreddits for contemporary discussions. 
    Available subreddits: communism101, socialism, marxism, communism, leftcommunism"""
    try:
        reddit = get_reddit_client()
        subreddit = "communism101"
        if subreddit.lower() not in allowed_subreddits:
            return f"❌ Subreddit {subreddit} not in approved list"
            
        sr = reddit.subreddit(subreddit)
        results = []
        
        for submission in sr.search(query, limit=5):
            if not is_quality_content(submission):
                continue
                
            content = f"""
            **{submission.title}** (Score: {submission.score})
            {submission.selftext[:500]}
            URL: {submission.url}
            """
            results.append(content.strip())
            

            submission.comments.replace_more(limit=0)
            for comment in submission.comments[:3]:
                try:
                    if (query.lower() in comment.body.lower() 
                            and comment.score > 1 
                            and not comment.removed):
                        results.append(
                            f"💬 Comment by u/{comment.author} (Score: {comment.score}):\n"
                            f"{comment.body[:300]}"
                        )
                except AttributeError as e:
                    print(f"Attribute error exception in submission.comments.replace_more {e}")
                    continue
                if len(results) >= 8:
                    break
                    
        return ("🔴 Reddit Analysis:\n" + "\n\n".join(results)[:4000] 
                or "No quality discussions found") + f"\n\nFull Search: {format_reddit_url(subreddit, query)}"
        
    except Exception as e:
        return f"❌ Reddit search error: {str(e)}"

@tool
def marxists_org_search(query: str) -> str:
    """Search marxists.org archive with proper Marxist source validation"""
    scraper = MarxistScraper()
    try:
        search_url = f"https://www.marxists.org/archive/search.htm?query={quote_plus(query)}"
        html = scraper._fetch(search_url)
        results = scraper._parse_marxists_org(html, query)
        if not results:
            return "🔍 No results found in marxists.org archive"
            
        formatted = []
        for i, res in enumerate(results, 1):
            formatted.append(f"[Source {i}] {res['title']}\nURL: {res['url']}\n{res['excerpt']}")
        
        return "marxists.org Results:\n" + "\n\n".join(formatted)
    except Exception as e:
        return f"❌ Failed to search marxists.org: {str(e)}"

@tool
def marxist_com_search(query: str) -> str:
    """Search International Marxist Tendency articles"""
    scraper = MarxistScraper()
    try:
        search_url = f"https://www.marxist.com/search-results.htm?q={quote_plus(query)}"
        html = scraper._fetch(search_url)
        soup = BeautifulSoup(html, 'html.parser')
        
        results = []
        for article in soup.select('.search-result-item'):
            title = article.select_one('h3 a').text.strip()
            url = article.select_one('h3 a')['href']
            date = article.select_one('.date').text.strip()
            excerpt = article.select_one('.excerpt').text.strip()
            results.append(f"{date} - {title}\n{url}\n{excerpt}")
        
        return "Marxist.com Results:\n" + "\n\n".join(results[:3])
    except Exception as e:
        return f"❌ Failed to search Marxist.com: {str(e)}"

@tool
def bannedthought_search(query: str) -> str:
    """Search BannedThought.net using their actual search API"""
    scraper = MarxistScraper()
    try:
        search_url = f"https://www.bannedthought.net/api/search?q={quote_plus(query)}"
        response = scraper.session.get(search_url)
        response.raise_for_status()
        
        results = []
        for item in response.json()['results'][:3]:
            results.append(f"{item['title']}\n{item['url']}\n{item['excerpt']}")
        
        return "BannedThought.net Results:\n" + "\n\n".join(results)
    except Exception as e:
        return f"❌ Failed to search BannedThought: {str(e)}"

@tool
def url_scraper(url: str) -> str:
    """Enhanced URL scraper with Marxist source validation"""
    scraper = MarxistScraper()
    try:
        html = scraper._fetch(url)
        soup = BeautifulSoup(html, 'html.parser')
        
        content = soup.find('div', class_='marxist-content') or \
                 soup.find('article') or \
                 soup.find('main') or \
                 soup.body
        
        clean_text = scraper._clean_text(content.text)
        return f"Content from {url}:\n{clean_text[:3000]}..."
    except Exception as e:
        return f"❌ Failed to scrape {url}: {str(e)}"
