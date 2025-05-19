from helpers.research_pipeline import ResearchPipeline
from helpers.common_helpers import CommonHelpers

class BotHandler:
    def __init__(self):
        self.research_pipeline = ResearchPipeline()
        self.common_helpers = CommonHelpers()
    async def handle_request(self, query: str, user_id: str, channel_id: str) -> dict:
        """Main handler for bot requests"""
        try:
            # Log request
            self.common_helpers.log_request({
                "query": query,
                "user_id": user_id,
                "channel_id": channel_id
            })
            # Validate query
            if not self.common_helpers.validate_query(query):
                return self.common_helpers.create_response(
                    400,
                    "Invalid query. Query must not be empty and must be less than 500 characters."
                )
            # Process query through the pipeline
            result = await self.research_pipeline.process_query(query)
            
            # Format response with proper Discord markdown
            formatted_content = f"## {result['topic']}\n\n{result['summary']}"
            if result.get('tools_used'):
                formatted_content += f"\n\n*Tools used: {', '.join(result['tools_used'])}*"
            
            return self.common_helpers.format_discord_response(
                formatted_content,
                result.get('tools_used', [])
            )
        except Exception as e:
            print(f"[ERROR] Bot request handling failed: {str(e)}")
            self.common_helpers.handle_exceptions(e, user_id)
            return self.common_helpers.create_response(500, str(e))