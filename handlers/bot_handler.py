from helpers.research_pipeline import ResearchPipeline
from helpers.common_helpers import CommonHelpers
from helpers.logger import get_logger
from datetime import datetime
from typing import Dict, Any
import logging

class BotHandler:
    def __init__(self):
        self.research_pipeline = ResearchPipeline()
        self.common_helpers = CommonHelpers()
        self.logger = get_logger()

    async def handle_request(self, query: str, user_id: str = None, channel_id: str = None) -> Dict[str, Any]:
        """Handle incoming request and return formatted response"""
        try:
            # Log request
            self.common_helpers.log_request({
                "query": query,
                "user_id": user_id,
                "channel_id": channel_id
            })
            
            # Process the query
            result = await self.research_pipeline.process_query(query)
            
            # Log the raw response for debugging
            self.logger.debug(f"Raw response from pipeline: {result}", "BOT_HANDLER")
            
            # Get the data from either Pydantic model or dict
            if hasattr(result, 'dict'):
                result_dict = result.dict()
            elif isinstance(result, dict):
                result_dict = result
            else:
                raise ValueError(f"Unexpected response type: {type(result)}")
            
            self.logger.debug(f"Processed result dict: {result_dict}", "BOT_HANDLER")
            
            # Format the response
            formatted_content = f"## {result_dict['topic']}\n\n{result_dict['summary']}"
            
            # Add actual sources if available, otherwise show analytical methods used
            actual_sources = result_dict.get('sources_used', [])
            pdf_links = result_dict.get('pdf_links', [])
            tools_used = result_dict.get('tools_used', [])
            
            # Debug logging to see what we have
            self.logger.debug(f"actual_sources: {actual_sources}", "BOT_HANDLER")
            self.logger.debug(f"pdf_links: {pdf_links}", "BOT_HANDLER")
            self.logger.debug(f"tools_used: {tools_used}", "BOT_HANDLER")
            
            # Always prioritize showing actual sources over analysis methods
            if actual_sources or pdf_links:
                formatted_content += "\n\n**Sources:**\n"
                # Add actual source URLs
                source_count = 1
                for source in actual_sources:
                    source_title = source.get('title', 'Source')
                    source_url = source.get('url', '')
                    cited_status = " ✓" if source.get('cited', False) else ""
                    formatted_content += f"- [{source_title}]({source_url}){cited_status}\n"
                    source_count += 1
                # Add PDF links
                for pdf in pdf_links:
                    pdf_title = pdf.get('title', 'PDF Document')
                    pdf_url = pdf.get('url', '')
                    formatted_content += f"- [{pdf_title}]({pdf_url}) (PDF)\n"
                    
                # Add analysis methods as secondary info
                if tools_used:
                    formatted_content += "\n**Analysis Methods:** " + ", ".join(tools_used)
            else:
                # Fallback to analysis methods if no sources
                formatted_content += "\n\n**Analysis Methods:**\n"
                for tool in tools_used:
                    formatted_content += f"- {tool}\n"
                    
            self.logger.debug(f"Formatted content: {formatted_content}", "BOT_HANDLER")
            
            # Create response with all required fields
            message = {
                "content": formatted_content,
                "sources": actual_sources if actual_sources else tools_used,
                "timestamp": datetime.now().isoformat(),
                "topic": result_dict['topic'],
                "summary": result_dict['summary'],
                "status": "success",
                "pdf_links": pdf_links
            }
            
            self.logger.debug(f"Formatted message: {message}", "BOT_HANDLER")
            return self.common_helpers.create_response(200, message)
            
        except Exception as e:
            self.logger.error(f"Bot request handling failed: {str(e)}", "BOT_HANDLER")
            self.common_helpers.handle_exceptions(e, user_id)
            error_message = {
                "content": f"Error processing request: {str(e)}",
                "sources": [],
                "timestamp": datetime.now().isoformat(),
                "topic": "Error",
                "summary": f"An error occurred: {str(e)}",
                "status": "error",
                "pdf_links": []
            }
            return self.common_helpers.create_response(500, error_message)