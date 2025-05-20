from flask import make_response, jsonify, request
from flask_restful import Resource, reqparse
from handlers.bot_handler import BotHandler
from helpers.common_helpers import CommonHelpers
import time
import asyncio

helpers = CommonHelpers()
bot_handler = BotHandler()

class HealthCheck(Resource):
    """Health check endpoint to verify service status"""
    def get(self):
        """Health check endpoint that returns system status"""
        try:
            status = {
                'status': 'healthy',
                'timestamp': time.time(),
                'version': '1.0.0'
            }
            return make_response(jsonify(helpers.create_response(200, status)), 200)
        except Exception as e:
            helpers.report_to_discord(f"[ERROR] Health check failed: {str(e)}")
            return make_response(jsonify(helpers.create_response(500, str(e))), 500)

class DiscordAnalysis(Resource):
    """Main endpoint for handling Discord bot analysis requests"""
    def post(self):
        data = None  # Initialize data variable
        try:
            # Parse request arguments
            parser = reqparse.RequestParser()
            parser.add_argument('query', type=str, required=True, help='Query cannot be blank')
            parser.add_argument('user_id', type=str, required=True, help='User ID cannot be blank')
            # Make channel_id optional
            parser.add_argument('channel_id', type=str, required=False)
            
            # Get raw JSON data for logging
            raw_data = request.get_json()
            data = parser.parse_args()
            
            # Log the incoming request
            helpers.log_request({
                'query': data['query'],
                'user_id': data['user_id'],
                'channel_id': data.get('channel_id', 'not provided')
            })
            
            # Validate the query
            if not helpers.validate_query(data['query']):
                return make_response(jsonify(helpers.create_response(
                    400, 
                    "Invalid query. Query must not be empty and must be less than 500 characters."
                )), 400)
            
            # Process the request using asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                bot_handler.handle_request(data['query'], data['user_id'], data.get('channel_id'))
            )
            loop.close()
            
            # Format response for Discord
            formatted_result = helpers.format_discord_response(
                result.get('content', ''),
                result.get('sources', [])
            )
            
            return make_response(jsonify(helpers.create_response(200, formatted_result)), 200)
        except Exception as e:
            helpers.report_to_discord(f"[ERROR] Analysis request failed: {str(e)}")
            # Only try to access data if it exists
            user_id = data.get('user_id') if data else None
            helpers.handle_exceptions(e, user_id)
            
            return make_response(jsonify(helpers.create_response(
                500,
                f"An error occurred: {str(e)}"
            )), 500)
