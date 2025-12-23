import os
from flask import Flask
from flask_restful import Api
from helpers.common_helpers import CommonHelpers
from helpers.logger import get_logger
import ui.bot_ui as bot_ui
import threading
import time
import requests

# Initialize logger
logger = get_logger()

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default-secret-key')
    
    # Initialize API
    api = Api(app)
    
    # Base URL for all endpoints
    base_url = '/api/v1/'
    
    # Register endpoints
    api.add_resource(bot_ui.HealthCheck, base_url + 'health')
    api.add_resource(bot_ui.DiscordAnalysis, base_url + 'analyze')
    
    
    # Initialize keep-alive only if APP_URL is set (for production)
    if os.getenv('APP_URL'):
        helpers = CommonHelpers()
        start_keep_alive(app, helpers)
    
    return app

def start_keep_alive(app, helpers):
    """Start the keep-alive thread"""
    app_url = os.getenv('APP_URL', 'http://app:5000')  # Default to internal Docker network URL
    ping_interval = int(os.getenv('PING_INTERVAL', 840))  # 14 minutes
    
    def ping_loop():
        while True:
            try:
                # Try internal URL first
                response = requests.get(f"{app_url}/api/v1/health")
                if response.status_code == 200:
                    logger.info(f"Ping successful at {time.strftime('%Y-%m-%d %H:%M:%S')}", "KEEP_ALIVE")
                else:
                    # Try external URL as fallback
                    external_url = 'http://localhost:5001'
                    response = requests.get(f"{external_url}/api/v1/health")
                    if response.status_code == 200:
                        logger.info(f"Ping successful (external) at {time.strftime('%Y-%m-%d %H:%M:%S')}", "KEEP_ALIVE")
                    else:
                        logger.warning(f"Ping failed with status {response.status_code}", "KEEP_ALIVE")
            except Exception as e:
                logger.error(f"Ping error: {str(e)}", "KEEP_ALIVE")
            time.sleep(ping_interval)
    
    # Start the ping thread
    thread = threading.Thread(target=ping_loop)
    thread.daemon = True
    thread.start()
    logger.info("Keep-alive service started", "KEEP_ALIVE")

# Create the app instance that will be imported by flask_app.py
app = create_app()
