from flask import make_response, jsonify, request
from flask_restful import Resource, reqparse
from handlers.bot_handler import handle_bot_request
from helpers.discord_helper import report_to_discord

class HealthCheck(Resource):
    """Health check endpoint to verify service status"""
    def get(self):
        return make_response(jsonify({'status': 'healthy'}), 200)

class DiscordAnalysis(Resource):
    """Main endpoint for handling Discord bot analysis requests"""
    def post(self):
        try:
            # Parse request arguments
            parser = reqparse.RequestParser()
            parser.add_argument('query', type=str, required=True, help='Query cannot be blank')
            parser.add_argument('channel_id', type=str, required=True, help='Channel ID cannot be blank')
            parser.add_argument('user_id', type=str, required=True, help='User ID cannot be blank')
            data = parser.parse_args()

            # Process the request
            status, result = handle_bot_request(data)
            
            return make_response(jsonify({
                'status': status,
                'result': result
            }), status)

        except Exception as e:
            # Log error to Discord
            report_to_discord(str(e))
            
            # Return error response
            return make_response(jsonify({
                'status': 500,
                'error': str(e)
            }), 500)
