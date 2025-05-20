import os
import discord
from discord.ext import commands
import requests
import json
from helpers.common_helpers import CommonHelpers
import aiohttp
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout  # Ensure logs go to stdout for Docker
)
logger = logging.getLogger(__name__)

# Initialize helpers
helpers = CommonHelpers()

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix='!', intents=intents)

# API configuration
API_URL = os.getenv('API_URL', 'http://app:5000/api/v1/analyze')  # Use service name in Docker network

@client.event
async def on_ready():
    logger.info(f"Bot is ready! Logged in as {client.user}")
    helpers.info_to_discord(f"Bot is ready! Logged in as {client.user}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if client.user.mentioned_in(message):
        try:
            # Extract query from message
            query = message.content.replace(f'<@{client.user.id}>', '').strip()
            logger.info(f"Received query: {query}")
            
            # Send initial response
            await message.channel.send("🔍 Analyzing your query... This may take a few minutes.")
            
            # Make API request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    API_URL,
                    json={"query": query, "user_id": str(message.author.id)}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Log the raw response data
                        logger.info(f"Raw API response: {json.dumps(data, indent=2)}")
                        helpers.debug_to_discord(f"Raw API response: {json.dumps(data, indent=2)}")
                        
                        # Check if we have a valid response
                        if not isinstance(data, dict) or 'message' not in data:
                            logger.error("Invalid response format from API")
                            raise ValueError("Invalid response format from API")
                        
                        message_data = data['message']
                        logger.info(f"Message data: {json.dumps(message_data, indent=2)}")
                        helpers.debug_to_discord(f"Message data: {json.dumps(message_data, indent=2)}")
                        
                        # Check if we have an error
                        if 'error' in message_data:
                            logger.error(f"API returned error: {message_data['error']}")
                            await message.channel.send(f"❌ Error: {message_data['error']}")
                            return
                        
                        # Format the response
                        if 'topic' in message_data and 'summary' in message_data:
                            response_text = f"**{message_data['topic']}**\n\n{message_data['summary']}\n\n"
                            
                            # Add PDF links section if available
                            if message_data.get('pdf_links'):
                                response_text += "\n**📚 Read More**\n"
                                for pdf in message_data['pdf_links']:
                                    response_text += f"• [{pdf['title']}]({pdf['url']})\n"
                            
                            # Log the final formatted response
                            logger.info(f"Final formatted response: {response_text}")
                            helpers.debug_to_discord(f"Final formatted response: {response_text}")
                            
                            # Send the response
                            await message.channel.send(response_text)
                        else:
                            logger.error(f"Missing fields in message_data. Available fields: {list(message_data.keys())}")
                            helpers.debug_to_discord(f"Missing fields in message_data. Available fields: {list(message_data.keys())}")
                            raise ValueError("Missing required fields in response")
                    else:
                        error_text = await response.text()
                        logger.error(f"API error response: {error_text}")
                        helpers.debug_to_discord(f"API error response: {error_text}")
                        await message.channel.send(f"❌ Error: {error_text}")
                        
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            helpers.report_to_discord(f"Error processing message: {str(e)}")
            await message.channel.send("❌ An error occurred while processing your request.")

# Run the bot
if __name__ == "__main__":
    logger.info("Starting Discord bot...")
    client.run(os.getenv('DISCORD_TOKEN'))