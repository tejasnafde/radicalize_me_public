import os
from typing import List, Dict, Optional
from googleapiclient.discovery import build
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
import requests
from datetime import datetime
import asyncio
import json
from .common_helpers import CommonHelpers

class SearchAPIManager:
    def __init__(self):
        self.helpers = CommonHelpers()
        self.helpers.debug_to_discord(f"Initializing SearchAPIManager at {datetime.now().isoformat()}")
        
        # Initialize API keys
        self.google_api_key = os.getenv('GOOGLE_API_KEY')  # This should be the Custom Search API key
        self.google_cse_id = os.getenv('GOOGLE_CSE_ID')
        self.serpapi_key = os.getenv('SERPAPI_API_KEY')
        
        # Log API key availability (without exposing the keys)
        self.helpers.debug_to_discord(
            f"API Keys Status - Google Custom Search: {'✓' if self.google_api_key else '✗'}, "
            f"Google CSE: {'✓' if self.google_cse_id else '✗'}, "
            f"SerpAPI: {'✓' if self.serpapi_key else '✗'}"
        )
        
        # Initialize search clients
        self.helpers.debug_to_discord("Initializing search clients...")
        self.google_service = build("customsearch", "v1", developerKey=self.google_api_key)
        self.ddg_search = DuckDuckGoSearchAPIWrapper(max_results=10)
        self.helpers.debug_to_discord("Search clients initialized successfully")
        
        # Track API usage and rate limits
        self.api_usage = {
            'google': {'last_used': 0, 'quota': 100, 'used': 0},
            'duckduckgo': {'last_used': 0, 'quota': 100, 'used': 0},
            'serpapi': {'last_used': 0, 'quota': 100, 'used': 0}
        }
        
        # Rate limit windows (in seconds)
        self.rate_limits = {
            'google': 1,
            'duckduckgo': 2,
            'serpapi': 1
        }
        self.helpers.debug_to_discord(
            f"Rate limits configured:\n" +
            f"• Google: {self.rate_limits['google']}s\n" +
            f"• DuckDuckGo: {self.rate_limits['duckduckgo']}s\n" +
            f"• SerpAPI: {self.rate_limits['serpapi']}s"
        )

    async def check_rate_limit(self, api: str) -> bool:
        """Check if an API is within its rate limit"""
        current_time = asyncio.get_event_loop().time()
        last_used = self.api_usage[api]['last_used']
        time_since_last_use = current_time - last_used
        is_available = time_since_last_use >= self.rate_limits[api]
        
        self.helpers.debug_to_discord(
            f"Rate limit check for {api}: "
            f"Last used: {datetime.fromtimestamp(last_used).isoformat()}, "
            f"Time since last use: {time_since_last_use:.2f}s, "
            f"Available: {is_available}"
        )
        
        return is_available

    async def update_api_usage(self, api: str):
        """Update API usage tracking"""
        previous_usage = self.api_usage[api]['used']
        self.api_usage[api]['last_used'] = asyncio.get_event_loop().time()
        self.api_usage[api]['used'] += 1
        
        self.helpers.debug_to_discord(
            f"Updated API usage for {api}: "
            f"Previous: {previous_usage}, "
            f"Current: {self.api_usage[api]['used']}, "
            f"Last used: {datetime.fromtimestamp(self.api_usage[api]['last_used']).isoformat()}"
        )

    async def get_available_api(self) -> Optional[str]:
        """Get the next available API that's not rate limited"""
        # Try APIs in specific order: SerpAPI -> DuckDuckGo -> Google
        api_order = ['serpapi', 'duckduckgo', 'google']
        
        for api in api_order:
            if await self.check_rate_limit(api):
                self.helpers.debug_to_discord(f"Selected {api} as next available API")
                return api
        
        self.helpers.debug_to_discord("No APIs available at the moment")
        return None

    async def search(self, query: str, site_filter: str) -> List[Dict]:
        """Perform search using available APIs"""
        self.helpers.debug_to_discord(f"Starting search for query: {query}")
        self.helpers.debug_to_discord(f"Site filter: {site_filter}")
        
        enhanced_query = f"{query} {site_filter}"
        max_retries = 3
        retry_count = 0
        tried_apis = set()
        
        while retry_count < max_retries:
            api = await self.get_available_api()
            if not api or api in tried_apis:
                self.helpers.debug_to_discord(f"All APIs are rate limited or tried. Attempt {retry_count + 1}/{max_retries}")
                await asyncio.sleep(5)  # Wait 5 seconds before retrying
                retry_count += 1
                continue
                
            try:
                self.helpers.debug_to_discord(f"Attempting search with {api} API")
                results = await self.search_with_api(api, enhanced_query)
                if results:
                    self.helpers.debug_to_discord(f"Successfully retrieved {len(results)} results from {api}")
                    await self.update_api_usage(api)
                    return results
                else:
                    self.helpers.debug_to_discord(f"No results returned from {api}")
                    tried_apis.add(api)
            except Exception as e:
                self.helpers.debug_to_discord(f"{api} search failed: {str(e)}")
                self.helpers.debug_to_discord(f"Full error details: {type(e).__name__}: {str(e)}")
                tried_apis.add(api)
                retry_count += 1
                await asyncio.sleep(2)  # Wait 2 seconds before trying next API
                continue
                
        self.helpers.debug_to_discord("All search APIs failed after maximum retries")
        raise Exception("All search APIs failed after maximum retries")

    async def search_with_api(self, api: str, query: str) -> List[Dict]:
        """Search using a specific API"""
        self.helpers.debug_to_discord(f"Executing {api} search with query: {query}")
        
        if api == 'google':
            try:
                result = self.google_service.cse().list(
                    q=query,
                    cx=self.google_cse_id,
                    num=5
                ).execute()
                
                self.helpers.debug_to_discord(f"Google search returned {len(result.get('items', []))} results")
                return [{
                    "title": item["title"],
                    "link": item["link"],
                    "snippet": item["snippet"]
                } for item in result.get("items", [])]
            except Exception as e:
                self.helpers.debug_to_discord(f"Google search failed: {str(e)}")
                raise
            
        elif api == 'duckduckgo':
            try:
                # Remove site filter for DuckDuckGo as it doesn't support it
                clean_query = query.split(" site:")[0]
                results = self.ddg_search.results(clean_query, 5)
                self.helpers.debug_to_discord(f"DuckDuckGo search returned {len(results)} results")
                return [{
                    "title": r["title"],
                    "link": r["link"],
                    "snippet": r["snippet"]
                } for r in results]
            except Exception as e:
                self.helpers.debug_to_discord(f"DuckDuckGo search failed: {str(e)}")
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
                self.helpers.debug_to_discord(f"SerpAPI request params: {json.dumps({k: v for k, v in params.items() if k != 'api_key'})}")
                
                response = requests.get("https://serpapi.com/search", params=params)
                data = response.json()
                
                if "error" in data:
                    self.helpers.debug_to_discord(f"SerpAPI returned error: {data['error']}")
                    raise Exception(f"SerpAPI error: {data['error']}")
                
                results = data.get("organic_results", [])
                self.helpers.debug_to_discord(f"SerpAPI search returned {len(results)} results")
                
                return [{
                    "title": result["title"],
                    "link": result["link"],
                    "snippet": result.get("snippet", "")
                } for result in results]
            except Exception as e:
                self.helpers.debug_to_discord(f"SerpAPI search failed: {str(e)}")
                raise
            
        return []