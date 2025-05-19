import os
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional
import requests

class CommonHelpers:
    def __init__(self):
        self.api_keys = [
            os.getenv('GOOGLE_API_KEY'),
            # Add more API keys here
        ]
        self.webhook_url = os.getenv('DISCORD_ERROR_WEBHOOK_URL')
        self.test_channel_id = os.getenv('DISCORD_TEST_CHANNEL_ID')
        self.bot_token = os.getenv('DISCORD_BOT_TOKEN')

    def create_response(self, status: int, result: Any, message: str = "") -> Dict:
        """Create a standardized response format"""
        resp = {
            "message": message if status == 200 else result
        }
        if status == 200:
            if isinstance(result, list):
                resp["list"] = result
            elif isinstance(result, dict):
                resp.update(result)
            elif isinstance(result, str):
                resp["message"] = result
        return resp

    def handle_exceptions(self, error: Exception, user_id: Optional[str] = None) -> None:
        """Handle exceptions and report them to Discord"""
        error_message = f"Error: {str(error)}\nTime: {datetime.now()}"
        if user_id:
            error_message += f"\nUser ID: {user_id}"
        self.report_to_discord(error_message)

    def report_to_discord(self, message: str, error_type: str = "ERROR") -> None:
        """Send error/debug messages to Discord channel"""
        try:
            formatted_message = {
                "embeds": [{
                    "title": f"🤖 {error_type}",
                    "description": message,
                    "color": 16711680 if error_type == "ERROR" else 65280,  # Red for errors, Green for debug
                    "timestamp": datetime.now().isoformat()
                }]
            }

            # Send to webhook if available
            if self.webhook_url:
                requests.post(
                    self.webhook_url,
                    json=formatted_message
                )
            
            # Also send to test channel if configured
            if self.test_channel_id and self.bot_token:
                channel_url = f"https://discord.com/api/v10/channels/{self.test_channel_id}/messages"
                headers = {
                    "Authorization": f"Bot {self.bot_token}",
                    "Content-Type": "application/json"
                }
                requests.post(
                    channel_url,
                    headers=headers,
                    json=formatted_message
                )

        except Exception as e:
            print(f"Failed to send error report to Discord: {str(e)}")

    def debug_to_discord(self, message: str) -> None:
        """Send debug messages to Discord"""
        self.report_to_discord(message, "DEBUG")

    def info_to_discord(self, message: str) -> None:
        """Send info messages to Discord"""
        self.report_to_discord(message, "INFO")

    def rotate_api_key(self) -> str:
        """Rotate between different API keys to avoid rate limits"""
        return self.api_keys[int(time.time()) % len(self.api_keys)]

    def validate_query(self, query: str) -> bool:
        """Validate the user's query"""
        if not query or len(query.strip()) == 0:
            return False
        if len(query) > 500:  # Arbitrary limit
            return False
        return True

    def format_discord_response(self, content: str, sources: list) -> Dict:
        """Format the response for Discord"""
        return {
            "content": content,
            "sources": sources,
            "timestamp": datetime.now().isoformat()
        }

    def log_request(self, request_data: Dict) -> None:
        """Log incoming requests"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "query": request_data.get("query"),
            "user_id": request_data.get("user_id"),
            "channel_id": request_data.get("channel_id")
        }
        # You can implement your preferred logging method here
        print(json.dumps(log_entry))