from langchain.tools import tool
from bs4 import BeautifulSoup
import requests
from urllib.parse import quote_plus
from typing import List
import backoff
import re

allowed_domains = [
    'marxists.org',
    'marx2mao.com',
    'bannedthought.net',
    'marxist.com',
    'marxistphilosophy.org',
    'communist.red'
]

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
        
        # Search through the proper archive structure
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
        return results[:5]  # Return top 5 relevant results

    def _clean_text(self, text: str) -> str:
        return re.sub(r'\s+', ' ', text).strip()

@tool
def marxists_org_search(query: str) -> str:
    """Search marxists.org archive with proper Marxist source validation"""
    scraper = MarxistScraper()
    try:
        search_url = f"https://www.marxists.org/archive/search.htm?query={quote_plus(query)}"
        html = scraper._fetch(search_url)
        results = scraper._parse_marxists_org(html, query)
        return "\n".join([f"{res['title']}\n{res['url']}\n{res['excerpt']}" for res in results])
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
        
        # Extract main content using Marxist document structure
        content = soup.find('div', class_='marxist-content') or \
                 soup.find('article') or \
                 soup.find('main') or \
                 soup.body
        
        clean_text = scraper._clean_text(content.text)
        return f"Content from {url}:\n{clean_text[:3000]}..."
    except Exception as e:
        return f"❌ Failed to scrape {url}: {str(e)}"