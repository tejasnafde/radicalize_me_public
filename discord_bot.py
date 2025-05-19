import os
import discord
from discord.ext import commands
import requests
import json
from helpers.common_helpers import CommonHelpers

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
    helpers.info_to_discord(f"Bot is ready! Logged in as {client.user}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if client.user.mentioned_in(message):
        try:
            # Extract query from message
            query = message.content.replace(f'<@{client.user.id}>', '').strip()
            
            # Make API request
            response = requests.post(
                API_URL,
                json={
                    'query': query,
                    'user_id': str(message.author.id),
                    'channel_id': str(message.channel.id)
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                await message.channel.send(result.get('message', 'No response from analysis'))
            else:
                helpers.debug_to_discord(f"API request failed with status {response.status_code}: {response.text}")
                await message.channel.send("Sorry, I encountered an error processing your request.")
                
        except Exception as e:
            helpers.debug_to_discord(f"Error processing message: {str(e)}")
            await message.channel.send("Sorry, I encountered an error processing your request.")

# Run the bot
if __name__ == "__main__":
    client.run(os.getenv('DISCORD_BOT_TOKEN'))