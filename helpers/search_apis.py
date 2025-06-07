import os
from typing import List, Dict, Optional
from googleapiclient.discovery import build
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
import requests
from datetime import datetime
import asyncio
import json
from .logger import get_logger
from .common_helpers import CommonHelpers

class SearchAPIManager:
    def __init__(self):
        self.logger = get_logger()
        self.helpers = CommonHelpers()
        self.logger.debug(f"Initializing SearchAPIManager at {datetime.now().isoformat()}", "SEARCH")
        
        # Initialize API keys
        self.google_api_key = os.getenv('GOOGLE_API_KEY')  # This should be the Custom Search API key
        self.google_cse_id = os.getenv('GOOGLE_CSE_ID')
        self.serpapi_key = os.getenv('SERPAPI_API_KEY')
        
        # Log API key availability (without exposing the keys) - only to logs, not Discord
        self.logger.info(
            f"API Keys Status - Google Custom Search: {'✓' if self.google_api_key else '✗'}, "
            f"Google CSE: {'✓' if self.google_cse_id else '✗'}, "
            f"SerpAPI: {'✓' if self.serpapi_key else '✗'}", "SEARCH"
        )
        
        # Initialize search clients
        self.logger.debug("Initializing search clients...", "SEARCH")
        self.google_service = build("customsearch", "v1", developerKey=self.google_api_key)
        self.ddg_search = DuckDuckGoSearchAPIWrapper(max_results=10)
        self.logger.debug("Search clients initialized successfully", "SEARCH")
        
        # Track API usage and rate limits
        self.api_usage = {
            'google': {'last_used': 0, 'quota': 100, 'used': 0},
            'duckduckgo': {'last_used': 0, 'quota': 100, 'used': 0},
            'serpapi': {'last_used': 0, 'quota': 100, 'used': 0}
        }
        
        # Rate limit windows (in seconds)
        self.rate_limits = {
            'google': 10,
            'duckduckgo': 10,
            'serpapi': 10  # Increased from 1 to 10 seconds to avoid rate limits
        }
        self.logger.info(
            f"Rate limits configured - Google: {self.rate_limits['google']}s, "
            f"DuckDuckGo: {self.rate_limits['duckduckgo']}s, "
            f"SerpAPI: {self.rate_limits['serpapi']}s", "SEARCH"
        )

    async def check_rate_limit(self, api: str) -> bool:
        """Check if an API is within its rate limit"""
        current_time = asyncio.get_event_loop().time()
        last_used = self.api_usage[api]['last_used']
        time_since_last_use = current_time - last_used
        is_available = time_since_last_use >= self.rate_limits[api]
        
        self.logger.debug(
            f"Rate limit check for {api}: "
            f"Last used: {datetime.fromtimestamp(last_used).isoformat()}, "
            f"Time since last use: {time_since_last_use:.2f}s, "
            f"Available: {is_available}", "SEARCH"
        )
        
        return is_available

    async def update_api_usage(self, api: str):
        """Update API usage tracking"""
        previous_usage = self.api_usage[api]['used']
        self.api_usage[api]['last_used'] = asyncio.get_event_loop().time()
        self.api_usage[api]['used'] += 1
        
        self.logger.debug(
            f"Updated API usage for {api}: "
            f"Previous: {previous_usage}, "
            f"Current: {self.api_usage[api]['used']}, "
            f"Last used: {datetime.fromtimestamp(self.api_usage[api]['last_used']).isoformat()}", "SEARCH"
        )

    async def get_available_api(self) -> Optional[str]:
        """Get the next available API that's not rate limited"""
        # Try APIs in specific order: SerpAPI -> DuckDuckGo -> Google
        api_order = ['serpapi', 'duckduckgo', 'google']
        
        for api in api_order:
            if await self.check_rate_limit(api):
                self.logger.debug(f"Selected {api} as next available API", "SEARCH")
                return api
        
        self.logger.debug("No APIs available at the moment", "SEARCH")
        return None

    async def search(self, query: str, site_filter: str) -> List[Dict]:
        """Perform search using available APIs"""
        self.logger.debug(f"Starting search for query: {query}", "SEARCH")
        self.logger.debug(f"Site filter: {site_filter}", "SEARCH")
        
        enhanced_query = f"{query} {site_filter}"
        max_retries = 3
        retry_count = 0
        tried_apis = set()
        
        while retry_count < max_retries:
            # Try each API in order until one succeeds
            for api in ['serpapi', 'duckduckgo', 'google']:
                if api in tried_apis:
                    continue
                    
                if not await self.check_rate_limit(api):
                    self.logger.debug(f"{api} is rate limited, trying next API", "SEARCH")
                    continue
                
                try:
                    self.logger.debug(f"Attempting search with {api} API", "SEARCH")
                    results = await self.search_with_api(api, enhanced_query)
                    if results:
                        self.logger.debug(f"Successfully retrieved {len(results)} results from {api}", "SEARCH")
                        await self.update_api_usage(api)
                        return results
                    else:
                        self.logger.debug(f"No results returned from {api}", "SEARCH")
                        tried_apis.add(api)
                except Exception as e:
                    self.logger.error(f"{api} search failed: {str(e)}", "SEARCH")
                    self.logger.error(f"Full error details: {type(e).__name__}: {str(e)}", "SEARCH")
                    tried_apis.add(api)
                    # If it's a rate limit error, increase the rate limit for that API
                    if "rate limit" in str(e).lower() or "429" in str(e):
                        self.rate_limits[api] = 20  # Increase rate limit to 20 seconds
                        self.logger.debug(f"{api} rate limit hit, increasing wait time to 20 seconds", "SEARCH")
                    continue
            
            # If we've tried all APIs, increment retry count and wait
            if len(tried_apis) == 3:  # All APIs have been tried
                retry_count += 1
                if retry_count < max_retries:
                    self.logger.debug(f"All APIs failed. Retry {retry_count}/{max_retries}. Waiting 10 seconds...", "SEARCH")
                    await asyncio.sleep(10)  # Wait longer between retries
                    tried_apis.clear()  # Reset tried APIs for next retry
                continue
                
        self.logger.error("All search APIs failed after maximum retries", "SEARCH")
        raise Exception("All search APIs failed after maximum retries")

    async def search_with_api(self, api: str, query: str) -> List[Dict]:
        """Search using a specific API"""
        self.logger.debug(f"Executing {api} search with query: {query}", "SEARCH")
        
        if api == 'google':
            try:
                result = self.google_service.cse().list(
                    q=query,
                    cx=self.google_cse_id,
                    num=5
                ).execute()
                
                self.logger.debug(f"Google search returned {len(result.get('items', []))} results", "SEARCH")
                return [{
                    "title": item["title"],
                    "link": item["link"],
                    "snippet": item["snippet"]
                } for item in result.get("items", [])]
            except Exception as e:
                self.logger.error(f"Google search failed: {str(e)}", "SEARCH")
                raise
            
        elif api == 'duckduckgo':
            try:
                # Remove site filter for DuckDuckGo as it doesn't support it
                clean_query = query.split(" site:")[0]
                results = self.ddg_search.results(clean_query, 5)
                self.logger.debug(f"DuckDuckGo search returned {len(results)} results", "SEARCH")
                return [{
                    "title": r["title"],
                    "link": r["link"],
                    "snippet": r["snippet"]
                } for r in results]
            except Exception as e:
                self.logger.error(f"DuckDuckGo search failed: {str(e)}", "SEARCH")
                raise
            
        elif api == 'serpapi':
            try:
                params = {
                    "engine": "google",
                    "q": query,
                    "api_key": self.serpapi_key,
                    "num": 5,
                    "gl": "us",
                    "hl": "en"
                }
                self.logger.debug(f"SerpAPI request params: {json.dumps({k: v for k, v in params.items() if k != 'api_key'})}", "SEARCH")
                
                response = requests.get("https://serpapi.com/search", params=params)
                data = response.json()
                
                if "error" in data:
                    error_msg = data['error']
                    self.logger.error(f"SerpAPI returned error: {error_msg}", "SEARCH")
                    # If rate limited, wait longer before next attempt
                    if "rate limit" in error_msg.lower() or "429" in error_msg:
                        self.rate_limits['serpapi'] = 10  # Increase rate limit to 10 seconds
                        self.logger.debug("SerpAPI rate limit hit, increasing wait time to 10 seconds", "SEARCH")
                    raise Exception(f"SerpAPI error: {error_msg}")
                
                results = data.get("organic_results", [])
                self.logger.debug(f"SerpAPI search returned {len(results)} results", "SEARCH")
                
                return [{
                    "title": result["title"],
                    "link": result["link"],
                    "snippet": result.get("snippet", "")
                } for result in results]
            except Exception as e:
                self.logger.error(f"SerpAPI search failed: {str(e)}", "SEARCH")
                raise
            
        return []