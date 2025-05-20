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
import os
import google.generativeai as genai

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
        
        # Configure Google API
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        
        # Use a single model for all operations
        self.llm = ChatGoogleGenerativeAI(
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

    async def optimize_search_query(self, query: str) -> str:
        """Optimizes the user's query for better search results"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Marxist research assistant. Optimize search queries for historical research.
            Focus on primary sources, academic works, and historical documents.
            Avoid Cold War-era propaganda terms and biased language.
            Output ONLY the optimized search query - maximum 100 characters.
            No explanations."""),
            ("human", "{query}")
        ])
        chain = prompt | self.llm | StrOutputParser()
        return await chain.ainvoke({"query": query})

    async def process_query(self, query: str) -> Dict:
        """Main pipeline that processes a user query from start to finish"""
        try:
            # 1. Optimize the query for better search results
            retry_count = 0
            max_retries = 3
            optimized_query = None
            
            while retry_count < max_retries:
                try:
                    optimized_query = await self.optimize_search_query(query)
                    if optimized_query:
                        # Add delay after query optimization
                        await asyncio.sleep(10)  # Wait 10 seconds before next API call
                        break
                except Exception as e:
                    # Extract retry delay from error message if available
                    retry_delay = 15  # Default delay (5 + 10 buffer)
                    if hasattr(e, 'response') and hasattr(e.response, 'json'):
                        try:
                            error_data = e.response.json()
                            if 'retry_delay' in error_data:
                                api_delay = int(error_data['retry_delay'].get('seconds', 5))
                                buffer = 10
                                retry_delay = api_delay + buffer  # Add 10 second buffer
                        except (ValueError, TypeError):
                            pass
                    
                    self.common_helpers.debug_to_discord(f"Rate limit hit, waiting {retry_delay} seconds before retry {retry_count + 1}/{max_retries}")
                    await asyncio.sleep(retry_delay)
                    
                    if not await self.common_helpers.handle_api_error(e, retry_count, max_retries):
                        raise
                    retry_count += 1
            
            if not optimized_query:
                raise ValueError("Failed to optimize query after maximum retries")
            
            # 2. Gather research data
            research_data = await self.gather_research_data(optimized_query, query)
            
            # 3. Generate structured response
            retry_count = 0
            while retry_count < max_retries:
                try:
                    response = await self.generate_response(query, research_data)
                    if response and isinstance(response, dict):
                        return response
                    raise ValueError("Invalid response format from generate_response")
                except Exception as e:
                    # Extract retry delay from error message if available
                    retry_delay = 15  # Default delay (5 + 10 buffer)
                    if hasattr(e, 'response') and hasattr(e.response, 'json'):
                        try:
                            error_data = e.response.json()
                            if 'retry_delay' in error_data:
                                api_delay = int(error_data['retry_delay'].get('seconds', 5))
                                buffer = 10
                                retry_delay = api_delay + buffer  # Add 10 second buffer
                        except (ValueError, TypeError):
                            pass
                    
                    self.common_helpers.debug_to_discord(f"Rate limit hit, waiting {retry_delay} seconds before retry {retry_count + 1}/{max_retries}")
                    await asyncio.sleep(retry_delay)
                    
                    if not await self.common_helpers.handle_api_error(e, retry_count, max_retries):
                        raise
                    retry_count += 1
            
            raise ValueError("Failed to generate response after maximum retries")
            
        except Exception as e:
            self.common_helpers.report_to_discord(f"Pipeline failed for query: {query} - {str(e)}")
            return {
                "topic": "Error",
                "summary": f"Analysis failed: {str(e)}",
                "tools_used": [],
                "pdf_links": []
            }

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
        try:
            # Extract PDF links from research data
            pdf_links = []
            for source in research_data.get("sources", []):
                if source.get("type") == "pdf":
                    pdf_links.append({
                        "title": source.get("title", "PDF Document"),
                        "url": source.get("url")
                    })

            self.common_helpers.debug_to_discord(f"Generating response for query: {query}")
            self.common_helpers.debug_to_discord(f"Research data sources: {len(research_data.get('sources', []))}")
            
            analysis_prompt = ChatPromptTemplate.from_messages([
                ("system", """You are a Marxist historian and analyst. Analyze the provided research context using historical materialism and dialectical methods.

                RESEARCH CONTEXT:
                {context}

                ANALYSIS PROTOCOL:
                1. Focus on primary sources and historical documents
                2. Apply historical materialism and dialectical analysis
                3. Cite sources with [Source#] notation
                4. Avoid Cold War-era propaganda terms and biased language
                5. Consider historical context and material conditions
                6. Use the agent scratchpad for intermediate steps: {agent_scratchpad}

                GUIDELINES:
                - Use historically accurate terminology
                - Avoid sensationalist or propagandistic language
                - Consider multiple perspectives and historical context
                - Focus on material conditions and class analysis
                - Cite specific sources for claims
                - Maintain academic rigor and objectivity"""),
                ("human", "{query}")
            ])
            
            # Create a chain with the prompt and LLM
            chain = analysis_prompt | self.llm | self.parser
            
            # Invoke the chain with the research data
            self.common_helpers.debug_to_discord("Invoking Gemini API for analysis...")
            analysis_response = await chain.ainvoke({
                "query": query,
                "context": json.dumps(research_data),
                "agent_scratchpad": []
            })
            
            self.common_helpers.debug_to_discord(f"Raw Gemini API response: {analysis_response}")
            
            if not analysis_response:
                raise ValueError("Empty response from Gemini API")
                
            if not hasattr(analysis_response, 'topic') or not hasattr(analysis_response, 'summary'):
                raise ValueError(f"Invalid response structure from Gemini API: {analysis_response}")

            # Add PDF links to the response
            response = {
                "topic": analysis_response.topic,
                "summary": analysis_response.summary,
                "tools_used": analysis_response.tools_used,
                "pdf_links": pdf_links
            }
            
            self.common_helpers.debug_to_discord(f"Final formatted response: {response}")
            return response
            
        except Exception as e:
            self.common_helpers.report_to_discord(f"Error in generate_response: {str(e)}")
            self.common_helpers.report_to_discord(f"Error type: {type(e).__name__}")
            self.common_helpers.report_to_discord(f"Error details: {str(e)}")
            raise

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
            self.common_helpers.report_to_discord(f"Search failed after all retries: {str(e)}")
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
                
                # Check content type
                content_type = response.headers.get('content-type', '').lower()
                
                if 'application/pdf' in content_type or result["link"].lower().endswith('.pdf'):
                    # For PDFs, just use the snippet and title
                    scraped_content.append({
                        "url": result["link"],
                        "title": result.get("title", ""),
                        "content": f"PDF Document: {result.get('snippet', '')}",
                        "snippet": result.get("snippet", ""),
                        "type": "pdf"
                    })
                    self.common_helpers.debug_to_discord(f"Handled PDF document: {result['link']}")
                    continue
                
                # For HTML content
                soup = BeautifulSoup(response.text, 'html.parser')
                main_content = soup.find('article') or soup.find('main') or soup.body
                
                if not main_content:
                    self.common_helpers.debug_to_discord(f"No main content found for {result['link']}, using snippet")
                    # If no main content found, use the snippet
                    scraped_content.append({
                        "url": result["link"],
                        "title": result.get("title", ""),
                        "content": result.get("snippet", ""),
                        "snippet": result.get("snippet", ""),
                        "type": "snippet"
                    })
                    continue
                
                # Clean and format text
                text = main_content.get_text(separator='\n', strip=True)
                text = re.sub(r'\n{3,}', '\n\n', text)[:2000]  # Limit content length
                
                scraped_content.append({
                    "url": result["link"],
                    "title": result.get("title", ""),
                    "content": text,
                    "snippet": result.get("snippet", ""),
                    "type": "html"
                })
                
            except Exception as e:
                self.common_helpers.report_to_discord(f"Error scraping {result['link']}: {str(e)}")
                # Add the result with just the snippet if scraping fails
                scraped_content.append({
                    "url": result["link"],
                    "title": result.get("title", ""),
                    "content": result.get("snippet", ""),
                    "snippet": result.get("snippet", ""),
                    "type": "error"
                })
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
                    self.common_helpers.report_to_discord(f"Error searching subreddit {sub}: {str(e)}")
                    continue
            
            return {
                "content": "\n\n".join(results)[:4000] if results else "No relevant Reddit discussions found",
                "sources": sources,
                "tool_name": "reddit_search"
            }
            
        except Exception as e:
            self.common_helpers.report_to_discord(f"Reddit search failed: {str(e)}")
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
                "tools_used": validated.tools_used,
                "pdf_links": []  # Initialize empty PDF links list
            }
        except ValidationError:
            return {
                "topic": "Analysis",
                "summary": analysis_response,
                "tools_used": [],
                "pdf_links": []  # Initialize empty PDF links list
            }