import os
from flask import Flask, request, jsonify
from flask_restful import Api
from helpers.common_helpers import CommonHelpers
from helpers.logger import get_logger
import ui.bot_ui as bot_ui
import threading
import time
import requests
import json
from datetime import datetime

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
    
    # Register error handlers
    register_error_handlers(app)
    
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

# Error Handlers
def register_error_handlers(app):
    @app.errorhandler(404)
    def not_found(error):
        logger.error(f"404 Not Found: {request.url}")
        return jsonify({
            'error': {
                'status': 404,
                'message': 'RESOURCE.NOT_FOUND',
                'path': request.url,
                'timestamp': datetime.now().isoformat()
            }
        }), 404

    @app.errorhandler(500)
    def internal_error(error):
        error_details = {
            'error': str(error),
            'type': type(error).__name__,
            'path': request.url,
            'method': request.method,
            'timestamp': datetime.now().isoformat()
        }
        
        # Log the error
        logger.error(f"500 Internal Error: {json.dumps(error_details, indent=2)}")
        
        # Report to Discord
        helpers = CommonHelpers()
        helpers.handle_exceptions(error, error_details)
        
        return jsonify({
            'error': {
                'status': 500,
                'message': 'SERVER.INTERNAL_ERROR',
                'timestamp': error_details['timestamp']
            }
        }), 500

    @app.errorhandler(400)
    def bad_request(error):
        logger.error(f"400 Bad Request: {request.url} - {str(error)}")
        return jsonify({
            'error': {
                'status': 400,
                'message': 'BAD_REQUEST',
                'details': str(error),
                'timestamp': datetime.now().isoformat()
            }
        }), 400

    @app.errorhandler(429)
    def too_many_requests(error):
        logger.error(f"429 Rate Limit Exceeded: {request.url}")
        return jsonify({
            'error': {
                'status': 429,
                'message': 'RATE_LIMIT_EXCEEDED',
                'timestamp': datetime.now().isoformat()
            }
        }), 429

# Create the app instance that will be imported by flask_app.py
app = create_app()
