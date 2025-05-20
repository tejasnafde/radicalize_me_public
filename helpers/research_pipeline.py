import json
from typing import Dict, List, Any
import requests
from bs4 import BeautifulSoup
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEndpoint
from langchain_groq import ChatGroq
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
from huggingface_hub import AsyncInferenceClient

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
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        
        # Initialize multiple LLM providers
        self.llm_providers = []
        
        # Add Groq if API key is available (fastest option)
        if os.getenv('GROQ_API_KEY'):
            self.llm_providers.append({
                'name': 'groq',
                'llm': ChatGroq(
                    model_name="llama3-70b-8192",  # Updated to current production model
                    temperature=0.3,
                    max_tokens=4000,
                    groq_api_key=os.getenv('GROQ_API_KEY'),
                    max_retries=0  # No retries, we'll handle it ourselves
                )
            })
            self.common_helpers.debug_to_discord("Groq provider initialized successfully")
        else:
            self.common_helpers.debug_to_discord("Groq provider not available - GROQ_API_KEY not set")
        
        # Add HuggingFace models if API key is available
        if os.getenv('HUGGINGFACE_API_KEY'):
            self.llm_providers.extend([
                {
                    'name': 'huggingface_mistral',
                    'llm': AsyncInferenceClient(
                        model="mistralai/Mistral-7B-Instruct-v0.2",
                        token=os.getenv('HUGGINGFACE_API_KEY')
                    )
                },
                {
                    'name': 'huggingface_llama',
                    'llm': AsyncInferenceClient(
                        model="meta-llama/Llama-2-70b-chat-hf",
                        token=os.getenv('HUGGINGFACE_API_KEY')
                    )
                }
            ])
            self.common_helpers.debug_to_discord("HuggingFace providers (Mistral and Llama) initialized successfully")
        else:
            self.common_helpers.debug_to_discord("HuggingFace providers not available - HUGGINGFACE_API_KEY not set")
        
        # Add Gemini as final fallback
        if os.getenv('GOOGLE_API_KEY'):
            self.llm_providers.append({
                'name': 'gemini',
                'llm': ChatGoogleGenerativeAI(
                    model="gemini-1.5-pro",
                    temperature=0.3,
                    convert_system_message_to_human=True,
                    safety_settings={
                        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE
                    },
                    max_output_tokens=4000,
                    max_retries=0  # Reduced retries to avoid long waits
                )
            })
            self.common_helpers.debug_to_discord("Gemini provider initialized successfully")
        else:
            self.common_helpers.debug_to_discord("Gemini provider not available - GOOGLE_API_KEY not set")
        
        if not self.llm_providers:
            raise ValueError("No LLM providers configured. Please set GROQ_API_KEY, HUGGINGFACE_API_KEY, or GOOGLE_API_KEY")
        
        # Log available providers
        provider_names = [p['name'] for p in self.llm_providers]
        self.common_helpers.debug_to_discord(f"Available LLM providers: {', '.join(provider_names)}")
        
        # Other initializations
        self.allowed_domains = [
            'marxists.org', 'marx2mao.com', 'bannedthought.net',
            'marxist.com', 'marxistphilosophy.org', 'communist.red'
        ]
        self.headers = {'User-Agent': 'MarxistResearchBot/2.1'}
        self.parser = PydanticOutputParser(pydantic_object=Response)
        self.current_provider_index = 0

    def _get_next_llm(self):
        """Get the next available LLM provider"""
        provider = self.llm_providers[self.current_provider_index]
        self.current_provider_index = (self.current_provider_index + 1) % len(self.llm_providers)
        return provider

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
        
        # Try each provider until one works
        for provider in self.llm_providers:
            try:
                self.common_helpers.debug_to_discord(f"Attempting query optimization with {provider['name']}")
                chain = prompt | provider['llm'] | StrOutputParser()
                result = await chain.ainvoke({"query": query})
                if result and isinstance(result, str) and len(result.strip()) > 0:
                    self.common_helpers.debug_to_discord(f"Successfully optimized query using {provider['name']}: {result}")
                    return result
                self.common_helpers.debug_to_discord(f"Empty response from {provider['name']}")
                raise ValueError("Empty or invalid response")
            except Exception as e:
                self.common_helpers.report_to_discord(f"Failed with {provider['name']}: {str(e)}, trying next provider...")
                # Only wait 2 seconds between providers
                await asyncio.sleep(2)
                continue
        
        # If all providers fail, return original query
        self.common_helpers.debug_to_discord("All LLM providers failed for query optimization, using original query")
        return query

    async def process_query(self, query: str) -> Dict:
        """Main pipeline that processes a user query from start to finish"""
        try:
            self.common_helpers.debug_to_discord(f"Starting query processing: {query}")
            
            # 1. Try to optimize the query, but fall back to original if it fails
            optimized_query = await self.optimize_search_query(query)
            self.common_helpers.debug_to_discord(f"Query optimization complete. Original: {query}, Optimized: {optimized_query}")
            
            # 2. Gather research data
            research_data = await self.gather_research_data(optimized_query, query)
            self.common_helpers.debug_to_discord(f"Research data gathered. Sources: {len(research_data.get('sources', []))}")
            
            # 3. Generate structured response
            for provider in self.llm_providers:
                try:
                    self.common_helpers.debug_to_discord(f"Attempting response generation with {provider['name']}")
                    response = await self.generate_response(query, research_data, provider)
                    if response and isinstance(response, dict):
                        self.common_helpers.debug_to_discord(f"Successfully generated response using {provider['name']}")
                        # Convert dict to Pydantic model before returning
                        try:
                            response_model = Response(**response)
                            self.common_helpers.debug_to_discord(f"Response converted to Pydantic model: {response_model}")
                            return response_model
                        except Exception as e:
                            self.common_helpers.report_to_discord(f"Failed to convert response to Pydantic model: {str(e)}")
                            raise ValueError(f"Invalid response format: {str(e)}")
                    self.common_helpers.debug_to_discord(f"Invalid response format from {provider['name']}")
                    raise ValueError("Invalid response format from generate_response")
                except Exception as e:
                    self.common_helpers.report_to_discord(f"Failed with {provider['name']}: {str(e)}, trying next provider...")
                    # Only wait 2 seconds between providers
                    await asyncio.sleep(2)
                    continue
            
            raise Exception("All LLM providers failed to generate response")
            
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
    async def generate_response(self, query: str, research_data: Dict, provider: Dict) -> Dict:
        """Generates a structured response based on research data"""
        try:
            self.common_helpers.debug_to_discord("=== Starting generate_response ===")
            
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
            
            self.common_helpers.debug_to_discord("Creating analysis prompt template...")
            # Create the prompt template with proper output formatting
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
                - Maintain academic rigor and objectivity

                YOUR TASK:
                Analyze the query: {query}

                {format_instructions}"""),
                ("human", "{query}")
            ])
            
            self.common_helpers.debug_to_discord("Analysis prompt template created successfully")
            self.common_helpers.debug_to_discord(f"Attempting to generate response with {provider['name']}")
            
            self.common_helpers.debug_to_discord("About to format prompt...")
            # Format the prompt for all providers
            try:
                formatted_prompt = analysis_prompt.format(
                    query=query,
                    context=json.dumps(research_data),
                    agent_scratchpad=[],
                    format_instructions=self.parser.get_format_instructions()
                )
                self.common_helpers.debug_to_discord("Prompt formatted successfully")
            except Exception as e:
                self.common_helpers.report_to_discord(f"Error formatting prompt: {str(e)}")
                self.common_helpers.report_to_discord(f"Error type: {type(e).__name__}")
                self.common_helpers.report_to_discord(f"Prompt template variables: query={query}, context={json.dumps(research_data)[:100]}...")
                raise
            
            # Log the formatted prompt for debugging
            self.common_helpers.debug_to_discord(f"Formatted prompt for {provider['name']}: {formatted_prompt}")
            
            # Handle HuggingFace models differently
            if provider['name'].startswith('huggingface_'):
                self.common_helpers.debug_to_discord("Using HuggingFace model path...")
                response_text = await provider['llm'].text_generation(
                    prompt=formatted_prompt,
                    max_new_tokens=4000,
                    temperature=0.3,
                    top_p=0.95,
                    do_sample=True
                )
                self.common_helpers.debug_to_discord("Got response from HuggingFace model")
                
                # Log the raw response for debugging
                self.common_helpers.debug_to_discord(f"Raw response from {provider['name']}: {response_text}")
                
                # Parse the response using the Pydantic parser
                try:
                    analysis_response = self.parser.parse(response_text)
                except Exception as e:
                    self.common_helpers.report_to_discord(f"Failed to parse HuggingFace response: {str(e)}")
                    self.common_helpers.report_to_discord(f"Raw response: {response_text}")
                    raise ValueError(f"Failed to parse HuggingFace response: {str(e)}")
            else:
                self.common_helpers.debug_to_discord("Using non-HuggingFace model path...")
                # For other providers, use the chain with the parser
                chain = provider['llm'] | self.parser
                try:
                    self.common_helpers.debug_to_discord("About to invoke chain...")
                    analysis_response = await chain.ainvoke(formatted_prompt)
                    self.common_helpers.debug_to_discord("Chain invoked successfully")
                except Exception as e:
                    self.common_helpers.report_to_discord(f"Error in chain.ainvoke: {str(e)}")
                    self.common_helpers.report_to_discord(f"Formatted prompt that caused error: {formatted_prompt}")
                    raise
            
            if not analysis_response:
                self.common_helpers.report_to_discord(f"Empty response from {provider['name']}")
                raise ValueError("Empty response from LLM API")
            
            # Debug the response structure
            self.common_helpers.debug_to_discord(f"Response type: {type(analysis_response)}")
            self.common_helpers.debug_to_discord(f"Response attributes: {dir(analysis_response)}")
            self.common_helpers.debug_to_discord(f"Response dict: {analysis_response.__dict__ if hasattr(analysis_response, '__dict__') else 'No __dict__'}")
            
            if not hasattr(analysis_response, 'topic') or not hasattr(analysis_response, 'summary'):
                self.common_helpers.report_to_discord(f"Invalid response structure from {provider['name']}: {analysis_response}")
                raise ValueError(f"Invalid response structure from LLM API: {analysis_response}")
            # Add PDF links to the response
            response = {
                "topic": analysis_response.topic,
                "summary": analysis_response.summary,
                "tools_used": analysis_response.tools_used,
                "pdf_links": pdf_links
            }
            
            self.common_helpers.debug_to_discord(f"Successfully generated response using {provider['name']}")
            self.common_helpers.debug_to_discord(f"Response generated using {provider['name']}: {response}")
            return response
            
        except Exception as e:
            self.common_helpers.report_to_discord(f"Failed with {provider['name']}: {str(e)}")
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