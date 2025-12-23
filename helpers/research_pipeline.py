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
from .logger import get_logger
import re
from .search_apis import SearchAPIManager
from .common_helpers import CommonHelpers
from .reddit_helper import RedditHelper
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
    sources_used: list[dict] = Field(
        default=[],
        description="List of sources found and used in analysis"
    )
    pdf_links: list[dict] = Field(
        default=[],
        description="List of PDF documents found"
    )

class ResearchPipeline:
    def __init__(self):
        self.logger = get_logger()
        self.search_manager = SearchAPIManager()
        self.common_helpers = CommonHelpers()
        self.reddit_helper = RedditHelper()
        
        # Configure Google API
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        
        # Initialize multiple LLM providers
        self.llm_providers = []
        
        # Add Groq if API key is available (primary provider)
        if os.getenv('GROQ_API_KEY'):
            self.llm_providers.append({
                'name': 'groq',
                'llm': ChatGroq(
                    model_name="llama3-70b-8192",  # Updated to current production model
                    temperature=0.3,
                    max_tokens=2000,  # Increased slightly for complex analysis
                    groq_api_key=os.getenv('GROQ_API_KEY'),
                    max_retries=1,  # Allow one retry for transient errors
                    timeout=45  # Increased timeout for complex prompts
                )
            })
            # Fallback model with smaller context window for large content
            self.llm_providers.append({
                'name': 'groq_small',
                'llm': ChatGroq(
                    model_name="llama3-8b-8192",  # Smaller model with same context window
                    temperature=0.3,
                    max_tokens=2000,
                    groq_api_key=os.getenv('GROQ_API_KEY'),
                    max_retries=1,
                    timeout=30
                )
            })
            self.logger.debug("Groq providers initialized successfully (70B and 8B models)", "LLM_INIT")
        else:
            self.logger.debug("Groq provider not available - GROQ_API_KEY not set", "LLM_INIT")
        
        # Temporarily disable HuggingFace due to StopIteration async issues
        # TODO: Fix async generator issues with HuggingFace providers
        # if os.getenv('HUGGINGFACE_API_KEY'):
        #     self.llm_providers.extend([
        #         {
        #             'name': 'huggingface_mistral',
        #             'llm': AsyncInferenceClient(
        #                 model="mistralai/Mistral-7B-Instruct-v0.2",
        #                 token=os.getenv('HUGGINGFACE_API_KEY')
        #             )
        #         },
        #         {
        #             'name': 'huggingface_llama',
        #             'llm': AsyncInferenceClient(
        #                 model="meta-llama/Llama-2-70b-chat-hf",
        #                 token=os.getenv('HUGGINGFACE_API_KEY')
        #             )
        #         }
        #     ])
        #     self.logger.debug("HuggingFace providers (Mistral and Llama) initialized successfully", "LLM_INIT")
        # else:
        #     self.logger.debug("HuggingFace providers not available - HUGGINGFACE_API_KEY not set", "LLM_INIT")
        self.logger.debug("HuggingFace providers temporarily disabled due to async issues", "LLM_INIT")
        
        # Temporarily disable Gemini due to rate limiting on free tier
        # TODO: Re-enable when quotas reset or upgrade to paid tier
        # if os.getenv('GOOGLE_API_KEY'):
        #     self.llm_providers.append({
        #         'name': 'gemini',
        #         'llm': ChatGoogleGenerativeAI(
        #             model="gemini-1.5-pro",
        #             temperature=0.3,
        #             convert_system_message_to_human=True,
        #             safety_settings={
        #                 HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        #                 HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        #                 HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        #                 HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE
        #             },
        #             max_output_tokens=4000,  # Reduced token count
        #             max_retries=0,  # Reduced retries to avoid long waits
        #             timeout=30  # Add 30 second timeout
        #         )
        #     })
        #     self.logger.debug("Gemini provider initialized successfully", "LLM_INIT")
        # else:
        #     self.logger.debug("Gemini provider not available - GOOGLE_API_KEY not set", "LLM_INIT")
        self.logger.debug("Gemini provider temporarily disabled due to rate limiting", "LLM_INIT")
        
        if not self.llm_providers:
            raise ValueError("No LLM providers configured. Please set GROQ_API_KEY, HUGGINGFACE_API_KEY, or GOOGLE_API_KEY")
        
        # Log available providers
        provider_names = [p['name'] for p in self.llm_providers]
        self.logger.debug(f"Available LLM providers: {', '.join(provider_names)}", "LLM_INIT")
        
        # Other initializations
        self.allowed_domains = [
            'marxists.org', 'marx2mao.com', 'bannedthought.net',
            'marxist.com', 'marxistphilosophy.org', 'communist.red',
            'socialistworker.org', 'wsws.org', 'leftcom.org',
            'cpusa.org', 'bolshevik.org', 'revcom.us',
            'socialistreview.org.uk', 'isreview.org', 'jacobinmag.com',
            'monthlyreview.org', 'solidarity-us.org', 'communist-party.org.uk',
            'cpgb-ml.org', 'proletarian.co.uk', 'labournet.net'
            # 'encyclopedia.com', 'britannica.com', 'jstor.org',
            # 'cambridge.org', 'tandfonline.com', 'springer.com'
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
            ("system", """You are a search query optimizer for Marxist research. Transform user questions into effective search terms.

RULES:
1. Keep the core meaning of the original query
2. Make it searchable for academic sources
3. Output ONLY the search terms - no explanations
4. Maximum 80 characters
5. Use key terms that will find relevant sources

EXAMPLES:
User: "What is democratic centralism?"
Output: democratic centralism Marxist organizational theory

User: "Explain historical materialism"  
Output: historical materialism Marx dialectical materialism

User: "Tell me about the Russian Revolution"
Output: Russian Revolution 1917 Bolsheviks Lenin

Your turn - optimize this query:"""),
            ("human", "{query}")
        ])
        
        # Try each provider until one works
        for provider in self.llm_providers:
            try:
                self.logger.debug(f"Attempting query optimization with {provider['name']}", "PIPELINE")
                chain = prompt | provider['llm'] | StrOutputParser()
                result = await chain.ainvoke({"query": query})
                if result and isinstance(result, str) and len(result.strip()) > 0:
                    # Clean the result - take only the first line and limit length
                    cleaned_result = result.strip().split('\n')[0][:80].strip()
                    
                    # Validate that the result contains actual search terms, not instructions
                    if (cleaned_result and 
                        not cleaned_result.lower().startswith(('here is', 'output:', 'search', 'optimized')) and
                        len(cleaned_result.split()) >= 2):  # At least 2 words
                        self.logger.debug(f"Successfully optimized query using {provider['name']}: {cleaned_result}", "PIPELINE")
                        return cleaned_result
                    else:
                        self.logger.warning(f"Invalid optimization result from {provider['name']}: {cleaned_result}", "PIPELINE")
                        raise ValueError("Invalid optimization - not actual search terms")
                        
                self.logger.debug(f"Empty response from {provider['name']}", "PIPELINE")
                raise ValueError("Empty or invalid response")
            except Exception as e:
                self.logger.error(f"Failed with {provider['name']}: {str(e)}, trying next provider...", "PIPELINE")
                # Only wait 2 seconds between providers
                await asyncio.sleep(2)
                continue
        
        # If all providers fail, return original query
        self.logger.warning("All LLM providers failed for query optimization, using original query", "PIPELINE")
        return query

    async def process_query(self, query: str) -> Dict:
        """Main pipeline that processes a user query from start to finish"""
        try:
            self.logger.debug(f"Starting query processing: {query}", "PIPELINE")
            
            # 1. Try to optimize the query, but fall back to original if it fails
            optimized_query = await self.optimize_search_query(query)
            self.logger.debug(f"Query optimization complete. Original: {query}, Optimized: {optimized_query}", "PIPELINE")
            
            # 2. Gather research data
            research_data = await self.gather_research_data(optimized_query, query)
            self.logger.debug(f"Research data gathered. Sources: {len(research_data.get('sources', []))}", "PIPELINE")
            
            # 3. Generate structured response
            for provider in self.llm_providers:
                try:
                    self.logger.debug(f"Attempting response generation with {provider['name']}", "PIPELINE")
                    response = await self.generate_response(query, research_data, provider)
                    if response and isinstance(response, dict):
                        self.logger.debug(f"Successfully generated response using {provider['name']}", "PIPELINE")
                        # Convert dict to Pydantic model before returning
                        try:
                            response_model = Response(**response)
                            self.logger.debug(f"Response converted to Pydantic model: {response_model}", "PIPELINE")
                            return response_model
                        except Exception as e:
                            self.logger.error(f"Failed to convert response to Pydantic model: {str(e)}", "PIPELINE")
                            raise ValueError(f"Invalid response format: {str(e)}")
                    self.logger.debug(f"Invalid response format from {provider['name']}", "PIPELINE")
                    raise ValueError("Invalid response format from generate_response")
                except Exception as e:
                    self.logger.error(f"Failed with {provider['name']}: {str(e)}, trying next provider...", "PIPELINE")
                    # Only wait 2 seconds between providers
                    await asyncio.sleep(2)
                    continue
            
            raise Exception("All LLM providers failed to generate response")
            
        except Exception as e:
            self.logger.error(f"Pipeline failed for query: {query} - {str(e)}", "PIPELINE")
            return {
                "topic": "Error",
                "summary": f"Analysis failed: {str(e)}",
                "tools_used": [],
                "pdf_links": []
            }

    def _truncate_content_for_token_limit(self, research_data: Dict, max_tokens: int = 4000) -> Dict:
        """
        Truncate research data to fit within token limits.
        Rough estimate: 1 token ≈ 4 characters for English text
        """
        max_chars = max_tokens * 4  # Conservative estimate
        
        # Create a copy to avoid modifying original data
        truncated_data = research_data.copy()
        
        # Truncate sources content
        if 'sources' in truncated_data:
            total_chars = 0
            truncated_sources = []
            
            for source in truncated_data['sources']:
                source_copy = source.copy()
                content = source_copy.get('content', '')
                
                # Reserve space for other fields and structure
                remaining_chars = max_chars - total_chars - 1000  # 1000 chars buffer
                
                if remaining_chars <= 0:
                    break
                    
                if len(content) > remaining_chars:
                    # Truncate content but try to end at a sentence
                    truncated_content = content[:remaining_chars]
                    last_period = truncated_content.rfind('.')
                    if last_period > remaining_chars * 0.7:  # If we can keep 70% of content
                        truncated_content = truncated_content[:last_period + 1]
                    source_copy['content'] = truncated_content + "... [Content truncated due to length]"
                
                truncated_sources.append(source_copy)
                total_chars += len(source_copy.get('content', ''))
                
                if total_chars >= max_chars * 0.8:  # Use 80% of available space
                    break
            
            truncated_data['sources'] = truncated_sources
        
        # Also truncate other content fields
        for key in ['web_results', 'reddit_results']:
            if key in truncated_data and isinstance(truncated_data[key], dict):
                content = truncated_data[key].get('content', '')
                if len(content) > 1000:  # Limit other content to 1000 chars
                    truncated_data[key]['content'] = content[:1000] + "... [Truncated]"
        
        return truncated_data

    async def generate_response(self, query: str, research_data: Dict, provider: Dict) -> Dict:
        """Generates a structured response based on research data"""
        try:
            self.logger.debug("=== Starting generate_response ===", "PIPELINE")
            # Extract PDF links and prepare source tracking
            pdf_links = []
            used_sources = []
            
            # Prepare source tracking from research data
            for source in research_data.get("sources", []):
                if source.get("type") == "pdf":
                    pdf_links.append({
                        "title": source.get("title", "PDF Document"),
                        "url": source.get("url")
                    })
                # Add all sources to tracking list
                used_sources.append({
                    "url": source.get("url"),
                    "title": source.get("title", ""),
                    "type": source.get("type", "unknown"),
                    "cited": False  # Will be set to True if found in the response
                })
            
            # Check if we have sources
            sources_count = len(research_data.get('sources', []))
            pdf_count = len(research_data.get('pdf_links', []))
            sources_available = sources_count > 0 or pdf_count > 0
            self.logger.debug(f"Sources available - {sources_count} sources, {pdf_count} PDF links", "PIPELINE")
            
            self.logger.debug(f"Generating response for query: {query}", "PIPELINE")
            self.logger.debug(f"Research data sources: {sources_count}", "PIPELINE")
            
            # Truncate content to fit within token limits
            truncated_data = self._truncate_content_for_token_limit(research_data, max_tokens=4000)
            truncated_sources_count = len(truncated_data.get('sources', []))
            self.logger.debug(f"Content truncated: {sources_count} -> {truncated_sources_count} sources", "PIPELINE")
            
            # Create the analysis prompt template
            self.logger.debug("Creating analysis prompt template...", "PIPELINE")
            # Create the prompt template with proper output formatting
            analysis_prompt = ChatPromptTemplate.from_messages([
                ("system", """You are a Marxist historian and analyst. Analyze the provided research context using historical materialism and dialectical methods.
                RESEARCH CONTEXT:
                {context}
                ANALYSIS PROTOCOL:
                1. Focus on primary sources and historical documents
                2. Apply historical materialism and dialectical analysis
                3. ONLY cite sources if research data contains actual sources - use [Source#] notation where # is the index of the source in the research data
                4. If NO sources are available, provide analysis based on established historical materialism without fabricated citations
                5. Avoid Cold War-era propaganda terms and biased language
                6. Consider historical context and material conditions
                7. Use the agent scratchpad for intermediate steps: {agent_scratchpad}
                GUIDELINES:
                - Use historically accurate terminology
                - Avoid sensationalist or propagandistic language
                - Consider multiple perspectives and historical context
                - Focus on material conditions and class analysis
                - NEVER create fake citations - only cite if sources are actually provided
                - If no sources available, clearly state analysis is based on historical materialism principles
                - Maintain academic rigor and objectivity
                REQUIRED OUTPUT FORMAT:
                You MUST output ONLY a valid JSON object with these exact fields:
                {{
                    "topic": "string",
                    "summary": "string",
                    "tools_used": ["string", "string", "string"]
                }}
                Do not include any text before or after the JSON object.
                EXAMPLE WITH SOURCES:
                {{
                    "topic": "The Russian Revolution",
                    "summary": "The Russian Revolution of 1917 was a pivotal moment in world history [Source1]. According to primary documents [Source2], the working class played a crucial role...",
                    "tools_used": ["historical materialism", "dialectical analysis", "primary source analysis"]
                }}
                EXAMPLE WITHOUT SOURCES:
                {{
                    "topic": "The Russian Revolution", 
                    "summary": "The Russian Revolution of 1917 represents a fundamental transformation in class relations. Using historical materialist analysis, the revolution emerged from contradictions between productive forces and relations of production in Tsarist Russia...",
                    "tools_used": ["historical materialism", "dialectical analysis", "class analysis"]
                }}
                YOUR TASK:
                Analyze the following query: {query}"""),
                ("human", "Please analyze this query: {query}")
            ])
            self.logger.debug("Analysis prompt template created successfully", "PIPELINE")
            self.logger.debug(f"Attempting to generate response with {provider['name']}", "PIPELINE")
            self.logger.debug("About to format prompt...", "PIPELINE")
            # Format the prompt for all providers
            try:
                formatted_prompt = analysis_prompt.format(
                    query=query,
                    context=json.dumps(truncated_data),
                    agent_scratchpad=[]
                )
                self.logger.debug("Prompt formatted successfully", "PIPELINE")
            except KeyError as ke:
                self.logger.error(f"Missing required parameter in prompt template: {str(ke)}", "PIPELINE")
                self.logger.error(f"Available parameters: query={query}, context={json.dumps(truncated_data)[:100]}...", "PIPELINE")
                raise ValueError(f"Prompt template formatting failed: {str(ke)}")
            except Exception as e:
                self.logger.error(f"Error formatting prompt: {str(e)}", "PIPELINE")
                self.logger.error(f"Error type: {type(e).__name__}", "PIPELINE")
                self.logger.error(f"Prompt template variables: query={query}, context={json.dumps(truncated_data)[:100]}...", "PIPELINE")
                raise
            # Log the formatted prompt for debugging
            self.logger.debug(f"Formatted prompt for {provider['name']}: {formatted_prompt}", "PIPELINE")
            # Handle HuggingFace models differently
            if provider['name'].startswith('huggingface_'):
                self.logger.debug("Using HuggingFace model path...", "PIPELINE")
                response_text = None  # Initialize outside try block
                try:
                    # Generate response with proper error handling
                    response_text = await provider['llm'].text_generation(
                        prompt=formatted_prompt,
                        max_new_tokens=2000,  # Reduced token count
                        temperature=0.3,
                        do_sample=True,
                        return_full_text=False  # Only return the generated text
                    )
                    if not response_text:
                        raise ValueError("Empty response from HuggingFace model")
                    self.logger.debug(f"Raw response from {provider['name']}: {response_text}", "PIPELINE")
                    
                    # Try to parse the response as JSON
                    try:
                        response_dict = json.loads(response_text)
                    except json.JSONDecodeError:
                        # If not JSON, try to extract fields using regex
                        topic_match = re.search(r'"topic":\s*"([^"]+)"', response_text)
                        summary_match = re.search(r'"summary":\s*"([^"]+)"', response_text)
                        tools_match = re.search(r'"tools_used":\s*\[(.*?)\]', response_text)
                        if not all([topic_match, summary_match, tools_match]):
                            raise ValueError("Could not extract required fields from response")
                        response_dict = {
                            "topic": topic_match.group(1),
                            "summary": summary_match.group(1),
                            "tools_used": [tool.strip(' "') for tool in tools_match.group(1).split(',')]
                        }
                    # Validate the response structure
                    if not all(k in response_dict for k in ['topic', 'summary', 'tools_used']):
                        raise ValueError(f"Missing required fields in response: {response_dict}")
                    # Create Pydantic model
                    analysis_response = Response(**response_dict)
                except Exception as e:
                    self.logger.error(f"Failed to process HuggingFace response: {str(e)}", "PIPELINE")
                    if response_text is not None:
                        self.logger.error(f"Raw response: {response_text}", "PIPELINE")
                    raise ValueError(f"Failed to process HuggingFace response: {str(e)}")
            else:
                self.logger.debug(f"Using non-HuggingFace model path for {provider['name']}...", "PIPELINE")
                try:
                    # Step 1: Get the raw string output from the LLM
                    raw_llm_output_chain = provider['llm'] | StrOutputParser()
                    self.logger.debug(f"About to invoke LLM ({provider['name']}) for raw output...", "PIPELINE")
                    
                    # Add timeout for LLM calls to prevent hanging
                    try:
                        raw_response_text = await asyncio.wait_for(
                            raw_llm_output_chain.ainvoke(formatted_prompt),
                            timeout=60  # 60 second timeout
                        )
                    except asyncio.TimeoutError:
                        raise ValueError(f"{provider['name']} request timed out after 60 seconds")
                    self.logger.debug(f"Raw response from {provider['name']} (first 500 chars): {raw_response_text[:500]}...", "PIPELINE")
                    
                    # Step 2: Clean the response text
                    # Remove any text before the first '{' and after the last '}'
                    first_brace = raw_response_text.find('{')
                    last_brace = raw_response_text.rfind('}')
                    
                    if first_brace == -1:
                        raise ValueError("No JSON object found in response")
                    
                    # If no closing brace found, try to complete the JSON
                    if last_brace == -1 or last_brace <= first_brace:
                        self.logger.warning("Incomplete JSON response detected, attempting to fix", "PIPELINE")
                        # Try to find where the JSON content ends and add missing closing
                        json_start = raw_response_text[first_brace:]
                        # Look for the end of summary field as a fallback
                        if '"summary"' in json_start:
                            # Find end of summary content (look for quote after content)
                            summary_start = json_start.find('"summary"')
                            summary_content_start = json_start.find(':', summary_start)
                            if summary_content_start != -1:
                                # Try to find reasonable ending point
                                remaining = json_start[summary_content_start:]
                                # Look for patterns that suggest end of content
                                potential_ends = [
                                    remaining.find('",'),
                                    remaining.find('"}'),
                                    remaining.find('. '),
                                    remaining.find('.\n'),
                                ]
                                valid_ends = [end for end in potential_ends if end > 100]  # Ensure substantial content
                                if valid_ends:
                                    end_pos = min(valid_ends) + summary_content_start
                                    # Truncate and add proper closing
                                    truncated = json_start[:end_pos]
                                    if not truncated.endswith('"'):
                                        truncated += '"'
                                    json_string = truncated + ', "tools_used": ["historical materialism", "dialectical analysis", "class analysis"]}'
                                else:
                                    json_string = raw_response_text[first_brace:] + '}'
                            else:
                                json_string = raw_response_text[first_brace:] + '}'
                        else:
                            json_string = raw_response_text[first_brace:] + '}'
                    else:
                        json_string = raw_response_text[first_brace:last_brace + 1]
                    self.logger.debug(f"Extracted JSON string (first 500 chars): {json_string[:500]}...", "PIPELINE")
                    
                    # Step 3: Clean the JSON string
                    # Remove markdown code block markers if present
                    json_string = re.sub(r'```json\n?', '', json_string)
                    json_string = re.sub(r'\n?```', '', json_string)
                    
                    # Basic cleanup - only remove trailing commas and extra whitespace
                    json_string = json_string.strip()
                    json_string = re.sub(r',\s*}', '}', json_string)  # Remove trailing commas before closing braces
                    json_string = re.sub(r',\s*\]', ']', json_string)  # Remove trailing commas before closing brackets
                    
                    # Remove any invalid control characters
                    json_string = re.sub(r"[\x00-\x1F\x7F-\x9F]", "", json_string)
                    
                    self.logger.debug(f"Cleaned JSON string (first 500 chars): {json_string[:500]}...", "PIPELINE")
                    
                    # Step 4: Parse the JSON
                    try:
                        # First try to parse as is
                        try:
                            response_dict = json.loads(json_string)
                        except json.JSONDecodeError:
                            # If that fails, try to extract fields using regex
                            topic_match = re.search(r'"topic":\s*"([^"]+)"', json_string)
                            summary_match = re.search(r'"summary":\s*"([^"]+)"', json_string)
                            tools_match = re.search(r'"tools_used":\s*\[(.*?)\]', json_string)
                            
                            if not all([topic_match, summary_match, tools_match]):
                                raise ValueError("Could not extract required fields from response")
                            
                            response_dict = {
                                "topic": topic_match.group(1),
                                "summary": summary_match.group(1),
                                "tools_used": [tool.strip(' "') for tool in tools_match.group(1).split(',')]
                            }
                        
                        # Validate the response structure
                        if not all(k in response_dict for k in ['topic', 'summary', 'tools_used']):
                            raise ValueError(f"Missing required fields in response: {response_dict}")
                        
                        # Create Pydantic model
                        analysis_response = Response(**response_dict)
                        
                        # Validate no fake citations if no sources available
                        if not sources_available and '[Source' in response_dict.get('summary', ''):
                            self.logger.warning("LLM created fake citations despite no sources being available - this should not happen", "PIPELINE")
                            # Remove fake citations from summary
                            cleaned_summary = re.sub(r'\[Source\d+\]', '', response_dict['summary'])
                            response_dict['summary'] = cleaned_summary.strip()
                            analysis_response = Response(**response_dict)
                            self.logger.debug("Removed fake citations from response", "PIPELINE")
                            
                    except json.JSONDecodeError as jde:
                        self.logger.error(f"JSON parsing failed: {str(jde)}", "PIPELINE")
                        self.logger.error(f"Problematic JSON: {json_string[:500]}...", "PIPELINE")
                        raise ValueError(f"Invalid JSON format: {str(jde)}")
                    except Exception as e:
                        self.logger.error(f"Failed to create Response object: {str(e)}", "PIPELINE")
                        raise
                    
                except Exception as e:
                    self.logger.error(f"Error processing response from {provider['name']}: {str(e)}", "PIPELINE")
                    self.logger.error(f"Error type: {type(e).__name__}", "PIPELINE")
                    self.logger.error(f"Formatted prompt that was used (first 500 chars): {formatted_prompt[:500]}...", "PIPELINE")
                    if 'raw_response_text' in locals():
                        self.logger.error(f"Raw response text from {provider['name']} that led to error (first 500 chars): {raw_response_text[:500]}...", "PIPELINE")
                    raise

            if not analysis_response:
                self.logger.error(f"Empty response from {provider['name']}", "PIPELINE")
                raise ValueError("Empty response from LLM API") 
            # Debug the response structure
            self.logger.debug(f"Response type: {type(analysis_response)}", "PIPELINE")
            self.logger.debug(f"Response attributes: {dir(analysis_response)}", "PIPELINE")
            self.logger.debug(f"Response dict: {analysis_response.__dict__ if hasattr(analysis_response, '__dict__') else 'No __dict__'}", "PIPELINE")
            if not hasattr(analysis_response, 'topic') or not hasattr(analysis_response, 'summary'):
                self.logger.error(f"Invalid response structure from {provider['name']}: {analysis_response}", "PIPELINE")
                raise ValueError(f"Invalid response structure from LLM API: {analysis_response}")
            # After getting the response, track which sources were used
            if hasattr(analysis_response, 'summary'):
                # Find all source citations in the summary
                source_citations = re.findall(r'\[Source(\d+)\]', analysis_response.summary)
                # Mark sources as cited
                for citation in source_citations:
                    try:
                        index = int(citation) - 1  # Convert to 0-based index
                        if 0 <= index < len(used_sources):
                            used_sources[index]['cited'] = True
                    except ValueError:
                        continue

            # Add used sources to the response
            response = {
                "topic": analysis_response.topic,
                "summary": analysis_response.summary,
                "tools_used": analysis_response.tools_used,
                "pdf_links": pdf_links,
                "sources_used": used_sources if sources_available else []  # Include all sources when available
            }
            self.logger.debug(f"Successfully generated response using {provider['name']}", "PIPELINE")
            self.logger.debug(f"Response generated using {provider['name']}: {response}", "PIPELINE")
            return response
        except Exception as e:
            self.logger.error(f"Failed with {provider['name']}: {str(e)}", "PIPELINE")
            self.logger.error(f"Error type: {type(e).__name__}", "PIPELINE")
            self.logger.error(f"Error details: {str(e)}", "PIPELINE")
            raise

    async def gather_research_data(self, optimized_query: str, original_query: str) -> Dict:
        """Gather research data from multiple sources"""
        try:
            # Initialize research data structure
            research_data = {
                'sources': [],
                'web_results': [],
                'reddit_results': None,
                'query': original_query,
                'optimized_query': optimized_query
            }
            
            # Gather web search results
            web_results = await self.web_search(optimized_query)
            if web_results:
                research_data['web_results'] = web_results
                # Scrape content from web results
                scraped_data = await self.scrape_urls(web_results)
                research_data['sources'].extend(scraped_data)
            
            # Gather Reddit results using new RedditHelper
            try:
                reddit_results = await self.reddit_helper.search_reddit(optimized_query)
                if reddit_results and reddit_results.get('content') != "No relevant Reddit discussions found":
                    research_data['reddit_results'] = reddit_results
                    # Add Reddit posts as sources
                    if reddit_results.get('sources'):
                        for source_url in reddit_results['sources']:
                            research_data['sources'].append({
                                'url': source_url,
                                'title': 'Reddit Discussion',
                                'content': reddit_results['content'][:500],  # Preview
                                'type': 'reddit'
                            })
            except Exception as e:
                self.logger.error(f"Reddit search failed: {str(e)}", "PIPELINE")
            
            self.logger.debug(f"Gathered {len(research_data['sources'])} total sources", "PIPELINE")
            return research_data
            
        except Exception as e:
            self.logger.error(f"Failed to gather research data: {str(e)}", "PIPELINE")
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
            self.logger.error(f"Search failed after all retries: {str(e)}", "PIPELINE")
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
                    self.logger.debug(f"Handled PDF document: {result['link']}", "PIPELINE")
                    continue
                
                # For HTML content
                soup = BeautifulSoup(response.text, 'html.parser')
                main_content = soup.find('article') or soup.find('main') or soup.body
                
                if not main_content:
                    self.logger.debug(f"No main content found for {result['link']}, using snippet", "PIPELINE")
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
                self.logger.error(f"Error scraping {result['link']}: {str(e)}", "PIPELINE")
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