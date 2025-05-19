import os
from flask import Flask, request, jsonify
from flask_restful import Api
from helpers.common_helper import report_to_discord
from utils.log_util import app_log
import ui.discord_ui as discord_ui

# Initialize Flask app
app = Flask(__name__)
app_log(app)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default-secret-key')

# Initialize API and error handler
api = Api(app)

# Base URL for all endpoints
base_url = '/api/v1/'

# Health Check
api.add_resource(discord_ui.HealthCheck, base_url + 'health')

# Main Analysis Endpoint
api.add_resource(discord_ui.DiscordAnalysis, base_url + 'analyze')

# Error Handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'error': {
            'status': 404,
            'message': 'RESOURCE.NOT_FOUND'
        }
    }), 404

@app.errorhandler(500)
def internal_error(error):
    error_handler.report_to_discord(str(error))
    return jsonify({
        'error': {
            'status': 500,
            'message': 'SERVER.INTERNAL_ERROR'
        }
    }), 500
