import os
import logging
import sys
import json
import requests
from datetime import datetime
from logging.handlers import RotatingFileHandler

class UnifiedLogger:
    """
    Unified logging system that routes messages based on severity:
    - DEBUG/INFO/WARNING: Only to log files
    - ERROR/CRITICAL: To both log files and Discord
    """
    
    def __init__(self, discord_webhook_url=None):
        self.discord_webhook_url = discord_webhook_url
        self._setup_logging()
    
    def _setup_logging(self):
        """Set up the logging configuration"""
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)
        
        # Configure root logger with DEBUG level
        self.logger = logging.getLogger('unified_logger')
        self.logger.setLevel(logging.DEBUG)
        
        # Clear any existing handlers
        if self.logger.handlers:
            for handler in self.logger.handlers:
                self.logger.removeHandler(handler)
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
        )
        
        # Create file handler for all logs
        file_handler = RotatingFileHandler(
            'logs/app.log',
            maxBytes=20*1024*1024,  # 20MB
            backupCount=10
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        self.logger.addHandler(file_handler)
        
        # Create separate error log file
        error_handler = RotatingFileHandler(
            'logs/errors.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        self.logger.addHandler(error_handler)
        
        # Optional console handler (only for INFO and above to reduce spam)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
    
    def _send_to_discord(self, message: str, level: str, color: int):
        """Send message to Discord webhook"""
        if not self.discord_webhook_url:
            return
        
        try:
            formatted_message = {
                "embeds": [{
                    "title": f"🚨 {level}",
                    "description": message,
                    "color": color,
                    "timestamp": datetime.now().isoformat(),
                    "footer": {
                        "text": "Marxist Bot Alert System"
                    }
                }]
            }
            
            response = requests.post(
                self.discord_webhook_url,
                json=formatted_message,
                timeout=5
            )
            response.raise_for_status()
            
        except Exception as e:
            # Log Discord failure but don't create infinite loops
            self.logger.error(f"Failed to send Discord alert: {str(e)}")
    
    def debug(self, message: str, context: str = None):
        """Log debug message - files only"""
        full_message = f"[{context}] {message}" if context else message
        self.logger.debug(full_message)
    
    def info(self, message: str, context: str = None):
        """Log info message - files only"""
        full_message = f"[{context}] {message}" if context else message
        self.logger.info(full_message)
    
    def warning(self, message: str, context: str = None):
        """Log warning message - files only"""
        full_message = f"[{context}] {message}" if context else message
        self.logger.warning(full_message)
    
    def error(self, message: str, context: str = None, notify_discord: bool = True):
        """Log error message - files and optionally Discord"""
        full_message = f"[{context}] {message}" if context else message
        self.logger.error(full_message)
        
        # Skip Discord notification for webhook-related errors to prevent infinite loops
        if notify_discord and "Failed to send Discord alert" not in message:
            self._send_to_discord(full_message, "ERROR", 16711680)  # Red
    
    def critical(self, message: str, context: str = None, notify_discord: bool = True):
        """Log critical message - files and Discord"""
        full_message = f"[{context}] {message}" if context else message
        self.logger.critical(full_message)
        
        if notify_discord:
            self._send_to_discord(full_message, "CRITICAL", 10038562)  # Dark red
    
    def exception(self, message: str, context: str = None, exc_info: bool = True, notify_discord: bool = True):
        """Log exception with traceback - files and Discord"""
        full_message = f"[{context}] {message}" if context else message
        self.logger.error(full_message, exc_info=exc_info)
        
        if notify_discord:
            self._send_to_discord(f"{full_message}\n\nCheck logs for full traceback.", "EXCEPTION", 16711680)
    
    def query_start(self, query: str, user_id: str = None):
        """Log query start - convenient method for query processing"""
        context_info = f"User: {user_id}" if user_id else "System"
        self.info(f"Starting query processing: {query}", context_info)
    
    def api_call(self, api_name: str, action: str, details: str = None):
        """Log API calls - convenient method for API interactions"""
        message = f"{api_name} - {action}"
        if details:
            message += f": {details}"
        self.debug(message, "API")
    
    def search_result(self, search_type: str, query: str, result_count: int):
        """Log search results - convenient method for search operations"""
        self.debug(f"{search_type} search for '{query}' returned {result_count} results", "SEARCH")
    
    def llm_call(self, provider: str, action: str, details: str = None):
        """Log LLM interactions - convenient method for LLM calls"""
        message = f"{provider} - {action}"
        if details:
            message += f": {details}"
        self.debug(message, "LLM")


# Global logger instance
_global_logger = None

def get_logger(discord_webhook_url: str = None) -> UnifiedLogger:
    """Get the global logger instance"""
    global _global_logger
    if _global_logger is None:
        webhook_url = discord_webhook_url or os.getenv('DISCORD_ERROR_WEBHOOK_URL')
        _global_logger = UnifiedLogger(webhook_url)
    return _global_logger

def init_logging(discord_webhook_url: str = None):
    """Initialize the global logging system"""
    global _global_logger
    webhook_url = discord_webhook_url or os.getenv('DISCORD_ERROR_WEBHOOK_URL')
    _global_logger = UnifiedLogger(webhook_url)
    return _global_logger 