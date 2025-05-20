import os
import discord
from discord.ext import commands
import requests
import json
from helpers.common_helpers import CommonHelpers
import aiohttp

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
            
            # Send initial response
            await message.channel.send("🔍 Analyzing your query...")
            
            # Make API request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    API_URL,
                    json={"query": query, "user_id": str(message.author.id)}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Format the response
                        response_text = f"**{data['topic']}**\n\n{data['summary']}\n\n"
                        
                        # Add PDF links section if available
                        if data.get('pdf_links'):
                            response_text += "\n**📚 Read More**\n"
                            for pdf in data['pdf_links']:
                                response_text += f"• [{pdf['title']}]({pdf['url']})\n"
                        
                        # Send the response
                        await message.channel.send(response_text)
                    else:
                        error_text = await response.text()
                        await message.channel.send(f"❌ Error: {error_text}")
                        
        except Exception as e:
            helpers.report_to_discord(f"Error processing message: {str(e)}")
            await message.channel.send("❌ An error occurred while processing your request.")

# Run the bot
if __name__ == "__main__":
    client.run(os.getenv('DISCORD_BOT_TOKEN'))