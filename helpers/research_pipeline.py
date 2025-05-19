import json
from typing import Dict, List, Any
import requests
from bs4 import BeautifulSoup
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from pydantic import BaseModel, Field, ValidationError
from google.generativeai.types.safety_types import HarmCategory, HarmBlockThreshold
from .common_helpers import CommonHelpers
import re
from .search_apis import SearchAPIManager
import asyncio

class Response(BaseModel):
    topic: str = Field(description="Main topic of analysis")
    summary: str = Field(description="Detailed Marxist analysis with citations")
    tools_used: list[str] = Field(
        min_items=3,
        description="EXACT tool names used in research"
    )

class ResearchPipeline:
    def __init__(self):
        self.common_helpers = CommonHelpers()  # This will validate env vars
        self.search_manager = SearchAPIManager()  # Add this line
        
        # Query optimization LLM
        self.query_optimizer = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.2,
            safety_settings={category: HarmBlockThreshold.BLOCK_NONE 
                           for category in HarmCategory}
        )
        
        # Response generation LLM
        self.response_generator = ChatGoogleGenerativeAI(
            model="gemini-1.5-pro",
            temperature=0.3,
            safety_settings={category: HarmBlockThreshold.BLOCK_NONE 
                           for category in HarmCategory},
            max_output_tokens=4000
        )
        
        # Other initializations
        self.allowed_domains = [
            'marxists.org', 'marx2mao.com', 'bannedthought.net',
            'marxist.com', 'marxistphilosophy.org', 'communist.red'
        ]
        self.headers = {'User-Agent': 'MarxistResearchBot/2.1'}
        self.parser = PydanticOutputParser(pydantic_object=Response)

    async def process_query(self, query: str) -> Dict:
        """Main pipeline that processes a user query from start to finish"""
        try:
            # 1. Optimize the query for better search results
            optimized_query = await self.optimize_search_query(query)
            
            # 2. Gather research data
            research_data = await self.gather_research_data(optimized_query, query)
            
            # 3. Generate structured response
            response = await self.generate_response(query, research_data)
            
            return response
            
        except Exception as e:
            self.common_helpers.debug_to_discord(f"Pipeline failed for query: {query} - {str(e)}")
            return {
                "topic": "Error",
                "summary": f"Analysis failed: {str(e)}",
                "tools_used": []
            }
    async def optimize_search_query(self, query: str) -> str:
        """Optimizes the user's query for better search results"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a research assistant. Optimize search queries for Marxist research. Output ONLY the optimized search query - maximum 100 characters. No explanations."),
            ("human", "{query}")
        ])
        chain = prompt | self.query_optimizer | StrOutputParser()
        return await chain.ainvoke({"query": query})
    async def gather_research_data(self, optimized_query: str, original_query: str) -> Dict:
        """Gathers research data from web and Reddit"""
        # Web search
        search_results = await self.web_search(optimized_query)
        
        # Scrape content
        scraped_content = await self.scrape_urls(search_results)
        
        # Reddit search
        reddit_results = await self.reddit_search(original_query)
        
        return {
            "original_query": original_query,
            "optimized_query": optimized_query,
            "sources": scraped_content,
            "reddit_content": reddit_results
        }
    async def generate_response(self, query: str, research_data: Dict) -> Dict:
        """Generates a structured response based on research data"""
        analysis_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Marxist analyst. Use provided research context and tools.
                
            RESEARCH CONTEXT:
            {context}
            ANALYSIS PROTOCOL:
            1. Cross-reference sources
            2. Apply historical materialism
            3. Cite sources with [Source#] notation
            4. Use the agent scratchpad for intermediate steps: {agent_scratchpad}"""),
            ("human", "{query}")
        ])
        
        # Create a chain with the prompt and LLM
        chain = analysis_prompt | self.response_generator | self.parser
        
        # Invoke the chain with the research data
        analysis_response = await chain.ainvoke({
            "query": query,
            "context": json.dumps(research_data),
            "agent_scratchpad": []
        })       
        return {
            "topic": analysis_response.topic,
            "summary": analysis_response.summary,
            "tools_used": analysis_response.tools_used
        }
    # Helper methods for web search, scraping, etc.
    async def web_search(self, query: str) -> List[Dict]:
        """Performs restricted web search with API rotation"""
        try:
            await self.common_helpers.check_rate_limit('web_search')
            site_filter = " OR ".join([f"site:{d}" for d in self.allowed_domains])
            
            # Use the search manager to handle API rotation
            results = await self.search_manager.search(query, site_filter)
            
            # Filter results to allowed domains
            return [r for r in results if any(d in r["link"] for d in self.allowed_domains)]
            
        except Exception as e:
            self.common_helpers.debug_to_discord(f"Search failed after all retries: {str(e)}")
            return []
    async def scrape_urls(self, search_results: List[Dict]) -> List[Dict]:
        """Scrapes content from search results"""
        scraped_content = []
        for result in search_results[:3]:  # Limit to 3 sources for depth
            try:
                response = requests.get(
                    result["link"], 
                    headers=self.headers, 
                    timeout=15
                )
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                main_content = soup.find('article') or soup.find('main') or soup.body
                
                # Clean and format text
                text = main_content.get_text(separator='\n', strip=True)
                text = re.sub(r'\n{3,}', '\n\n', text)[:2000]  # Limit content length
                
                scraped_content.append({
                    "url": result["link"],
                    "title": result.get("title", ""),
                    "content": text,
                    "snippet": result.get("snippet", "")
                })
                
            except Exception as e:
                self.common_helpers.debug_to_discord(f"Error scraping {result['link']}: {str(e)}")
                continue
                
        return scraped_content
    async def reddit_search(self, query: str) -> Dict:
        """Searches Reddit for relevant discussions"""
        try:
            await self.common_helpers.check_rate_limit('reddit_search')
            results = []
            sources = []
            allowed_subreddits = {
                'communism101', 'socialism', 'marxism',
                'communism', 'leftcommunism'
            }
            
            for sub in allowed_subreddits:
                try:
                    submissions = self.common_helpers.reddit_client.subreddit(sub).search(
                        query,
                        limit=3,
                        time_filter="year",
                        sort="relevance"
                    )
                    
                    for post in submissions:
                        # Skip removed or deleted posts
                        if hasattr(post, 'removed_by_category') or not hasattr(post, 'selftext') or post.selftext in ('[removed]', '[deleted]'):
                            continue
                        
                        # Add post content
                        content = f"**{post.title}**\nScore: {post.score}\n{post.selftext[:500]}"
                        results.append(content)
                        sources.append(f"https://reddit.com{post.permalink}")
                        
                        # Get top comments
                        post.comments.replace_more(limit=0)  # Don't load MoreComments
                        for comment in post.comments.list()[:3]:  # Top 3 comments
                            if hasattr(comment, 'body') and comment.body.strip() and not getattr(comment, 'removed', False):
                                author = getattr(comment, 'author', '[deleted]')
                                results.append(f"Comment by {author}: {comment.body[:300]}")
                                sources.append(f"https://reddit.com{comment.permalink}")
                
                except Exception as e:
                    self.common_helpers.debug_to_discord(f"Error searching subreddit {sub}: {str(e)}")
                    continue
            
            return {
                "content": "\n\n".join(results)[:4000] if results else "No relevant Reddit discussions found",
                "sources": sources,
                "tool_name": "reddit_search"
            }
            
        except Exception as e:
            self.common_helpers.debug_to_discord(f"Reddit search failed: {str(e)}")
            return {
                "content": f"Reddit error: {str(e)}",
                "sources": [],
                "tool_name": "error in reddit_search"
            }
    def format_response(self, analysis_response: str) -> Dict:
        """Formats the analysis response"""
        try:
            validated = self.parser.parse(analysis_response)
            return {
                "topic": validated.topic,
                "summary": validated.summary,
                "tools_used": validated.tools_used
            }
        except ValidationError:
            return {
                "topic": "Analysis",
                "summary": analysis_response,
                "tools_used": []
            }