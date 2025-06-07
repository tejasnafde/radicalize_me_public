import os
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional
import requests
import praw
import asyncio
from functools import lru_cache
import logging
import sys

# Import our custom logger first
from .logger import get_logger

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Use our custom logger
logger = get_logger(__name__)

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
            'web_search': 10,
            'reddit_search': 10
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
            logger.error(f"Missing required environment variables: {', '.join(missing)}", "ENV_VARS")
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    def create_response(self, status_code: int, message: Any) -> Dict[str, Any]:
        """Create a standardized response"""
        if isinstance(message, dict):
            # If message is already a dict with status, use it directly
            if "status" in message:
                return {
                    "status": message["status"],
                    "status_code": status_code,
                    "message": message
                }
            # If message is a dict without status, add status and preserve all fields
            return {
                "status": "success" if status_code < 400 else "error",
                "status_code": status_code,
                "message": message  # Preserve all fields in the message
            }
        
        # Otherwise create a new response structure
        return {
            "status": "success" if status_code < 400 else "error",
            "status_code": status_code,
            "message": message if isinstance(message, dict) else {"content": str(message)}
        }

    def handle_exceptions(self, error: Exception, user_id: Optional[str] = None) -> None:
        """Handle exceptions and report them to Discord"""
        error_message = f"Error: {str(error)}\nTime: {datetime.now()}"
        if user_id:
            error_message += f"\nUser ID: {user_id}"
        
        self.report_to_discord(error_message)

    def report_to_discord(self, message: str, error_type: str = "ERROR") -> None:
        """Send error/debug messages to Discord channel"""
        try:
            # Log to Docker first
            if error_type == "DEBUG":
                logger.debug(message)
            elif error_type == "INFO":
                logger.info(message)
            else:
                logger.error(message)

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
                    # Add console logging
                    logger.debug(f"[DEBUG] {debug_data.get('message', '')} - {debug_data.get('timestamp', '')}")
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
                    # Add console logging
                    logger.debug(f"[DEBUG] {message}")
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
                # Add console logging
                if error_type == "ERROR":
                    logger.error(f"[{error_type}] {message}")
                else:
                    logger.info(f"[{error_type}] {message}")

            # Send to webhook if available
            if self.webhook_url:
                try:
                    response = requests.post(
                        self.webhook_url,
                        json=formatted_message,
                        timeout=5  # Add timeout
                    )
                    response.raise_for_status()  # Raise exception for non-200 status codes
                    logger.info(f"[INFO] Successfully sent message to Discord webhook")
                except requests.exceptions.RequestException as e:
                    logger.error(f"[ERROR] Failed to send message to Discord webhook: {str(e)}")
                    if hasattr(e.response, 'text'):
                        logger.error(f"[ERROR] Discord API response: {e.response.text}")
            else:
                logger.warning("[WARNING] No Discord webhook URL configured")
        except Exception as e:
            logger.error(f"[ERROR] Failed to send error report to Discord: {str(e)}")
            logger.error(f"[ERROR] Message that failed to send: {message}")

    def info_to_discord(self, message: str) -> None:
        """Send info messages to Discord"""
        self.report_to_discord(message, "INFO")

    # def rotate_api_key(self) -> str:
    #     """Rotate between different API keys to avoid rate limits"""
    #     return self.api_keys[int(time.time()) % len(self.api_keys)]

    def validate_query(self, query: str) -> bool:
        """Validate the user's query"""
        if not query or len(query.strip()) == 0:
            return False
        if len(query) > 500:  # Arbitrary limit
            return False
        return True


    def log_request(self, request_data: Dict) -> None:
        """Log incoming requests"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "query": request_data.get("query"),
            "user_id": request_data.get("user_id"),
            "channel_id": request_data.get("channel_id")
        }
        logger.info(f"Request logged: {json.dumps(log_entry)}")

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

    async def ping_health_endpoint(self):
        """Ping the health endpoint to keep the service alive"""
        try:
            # Use the correct port (5001) for external access
            health_url = "http://localhost:5001/api/v1/health"
            logger.debug(f"Pinging health endpoint: {health_url}")
            response = requests.get(health_url, timeout=5)
            response.raise_for_status()
            logger.debug("Health check successful")
            return True
        except Exception as e:
            self.report_to_discord(f"Health check failed: {str(e)}")
            return False

    async def handle_api_error(self, error: Exception, retry_count: int = 0, max_retries: int = 3) -> bool:
        """Handle API errors with retry logic"""
        if retry_count >= max_retries:
            logger.warning(f"Max retries ({max_retries}) exceeded for API call")
            return False

        error_str = str(error).lower()
        
        # Check if it's a rate limit error
        if "429" in error_str or "quota" in error_str or "rate limit" in error_str:
            retry_delay = 40  # Default delay for rate limits
            try:
                # Try to extract retry delay from error message
                if "retry_delay" in error_str:
                    retry_delay = int(error_str.split("seconds: ")[1].split("}")[0])
            except:
                pass
            
            logger.info(f"Rate limit hit, waiting {retry_delay} seconds before retry {retry_count + 1}/{max_retries}")
            await asyncio.sleep(retry_delay)
            return True
            
        # Check if it's a parsing or data structure error
        if any(x in error_str for x in ["none", "subscriptable", "key", "index", "attribute"]):
            logger.error(f"Data structure error: {str(error)}")
            return False
            
        # Check if it's a network error
        if any(x in error_str for x in ["connection", "timeout", "network"]):
            logger.warning(f"Network error: {str(error)}")
            await asyncio.sleep(2 ** retry_count)  # Exponential backoff
            return True
            
        # For other errors, log and don't retry
        logger.error(f"Unhandled error type: {str(error)}")
        return False