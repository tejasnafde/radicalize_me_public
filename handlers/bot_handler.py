from helpers.research_pipeline import ResearchPipeline
from helpers.common_helpers import CommonHelpers
from datetime import datetime
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class BotHandler:
    def __init__(self):
        self.research_pipeline = ResearchPipeline()
        self.common_helpers = CommonHelpers()

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
            self.common_helpers.debug_to_discord(f"Raw response from pipeline: {result}")
            
            # Get the data from either Pydantic model or dict
            if hasattr(result, 'dict'):
                result_dict = result.dict()
            elif isinstance(result, dict):
                result_dict = result
            else:
                raise ValueError(f"Unexpected response type: {type(result)}")
            
            self.common_helpers.debug_to_discord(f"Processed result dict: {result_dict}")
            
            # Format the response
            formatted_content = f"## {result_dict['topic']}\n\n{result_dict['summary']}"
            
            # Add tools used if available
            if result_dict.get('tools_used'):
                formatted_content += "\n\n**Sources:**\n"
                for tool in result_dict['tools_used']:
                    formatted_content += f"- {tool}\n"
            self.common_helpers.debug_to_discord(f"Formatted content: {formatted_content}")
            # Create response with all required fields
            message = {
                "content": formatted_content,
                "sources": result_dict.get('tools_used', []),
                "timestamp": datetime.now().isoformat(),
                "topic": result_dict['topic'],
                "summary": result_dict['summary'],
                "status": "success",
                "pdf_links": result_dict.get('pdf_links', [])
            }
            
            self.common_helpers.debug_to_discord(f"Formatted message: {message}")
            return self.common_helpers.create_response(200, message)
            
        except Exception as e:
            self.common_helpers.debug_to_discord(f"Bot request handling failed: {str(e)}")
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