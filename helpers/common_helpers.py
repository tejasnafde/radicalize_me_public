import os
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional
import requests
import praw
import asyncio
from functools import lru_cache

class CommonHelpers:
    def __init__(self):
        self.validate_env_vars()  # Call validation during initialization
        self.api_keys = [
            os.getenv('GOOGLE_API_KEY'),
            # Add more API keys here
        ]
        self.webhook_url = os.getenv('DISCORD_ERROR_WEBHOOK_URL')
        self.test_channel_id = os.getenv('DISCORD_TEST_CHANNEL_ID')
        self.bot_token = os.getenv('DISCORD_BOT_TOKEN')
        self.rate_limiter = {
            'web_search': time.time(),
            'reddit_search': time.time()
        }
        self.rate_limit_seconds = {
            'web_search': 2,
            'reddit_search': 5
        }
        self.reddit_client = self.get_reddit_client()

    def validate_env_vars(self):
        """Validate required environment variables"""
        required_vars = [
            'REDDIT_CLIENT_ID',
            'REDDIT_CLIENT_SECRET',
            'REDDIT_USERNAME',
            'REDDIT_PASSWORD',
            'REDDIT_USER_AGENT',
            'GOOGLE_API_KEY',
            'GOOGLE_CSE_ID',
            'SERPAPI_API_KEY',
            'DISCORD_ERROR_WEBHOOK_URL',
            'DISCORD_TOKEN'
        ]
        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

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
            # Format the message based on type
            if error_type == "DEBUG" and isinstance(message, str) and message.startswith("{"):
                # Parse JSON debug message
                try:
                    debug_data = json.loads(message)
                    formatted_message = {
                        "embeds": [{
                            "title": "🔍 Debug Info",
                            "description": f"**{debug_data.get('message', '')}**\n\n*{debug_data.get('timestamp', '')}*",
                            "color": 3447003,  # Blue color
                            "timestamp": datetime.now().isoformat()
                        }]
                    }
                except json.JSONDecodeError:
                    # If JSON parsing fails, use the original message
                    formatted_message = {
                        "embeds": [{
                            "title": "🔍 Debug Info",
                            "description": message,
                            "color": 3447003,
                            "timestamp": datetime.now().isoformat()
                        }]
                    }
            else:
                # For other message types
                formatted_message = {
                    "embeds": [{
                        "title": f"🤖 {error_type}",
                        "description": message,
                        "color": 16711680 if error_type == "ERROR" else 65280,  # Red for errors, Green for info
                        "timestamp": datetime.now().isoformat()
                    }]
                }

            # Send to webhook if available
            if self.webhook_url:
                requests.post(
                    self.webhook_url,
                    json=formatted_message
                )
        except Exception as e:
            print(f"[ERROR] Failed to send error report to Discord: {str(e)}")

    def debug_to_discord(self, message: str) -> None:
        """Send debug messages to Discord with additional context"""
        debug_info = {
            "message": message,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.report_to_discord(json.dumps(debug_info), "DEBUG")

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
        print(f"[INFO] Request logged: {json.dumps(log_entry)}")

    @lru_cache(maxsize=1)
    def get_reddit_client(self):
        """Cached Reddit client to avoid multiple initializations"""
        return praw.Reddit(
            client_id=os.getenv('REDDIT_CLIENT_ID'),
            client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
            username=os.getenv('REDDIT_USERNAME'),
            password=os.getenv('REDDIT_PASSWORD'),
            user_agent=os.getenv('REDDIT_USER_AGENT'),
            ratelimit_seconds=300,
            check_for_async=False
        )

    async def check_rate_limit(self, operation: str):
        """Check and enforce rate limits"""
        current_time = time.time()
        last_operation = self.rate_limiter.get(operation, 0)
        if current_time - last_operation < self.rate_limit_seconds[operation]:
            await asyncio.sleep(self.rate_limit_seconds[operation])
        self.rate_limiter[operation] = current_time