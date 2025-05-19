import discord
from discord.ext import commands
import os
import requests
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

client = commands.Bot(
    command_prefix=commands.when_mentioned,
    intents=intents
)

API_URL = os.getenv('API_URL', 'http://localhost:5000/api/v1/analyze')

@client.event
async def on_ready():
    print(f"Bot is ready! Logged in as {client.user}")

@client.event
async def on_message(message):
    if message.author.bot:
        return
    if client.user in message.mentions:
        query = message.content.replace(f'<@{client.user.id}>', '').strip()
        
        if not query:
            await message.channel.send("Please provide a query after the mention")
            return

        try:
            # Send loading message
            loading_msg = await message.channel.send("⚙️ Processing query...")
            
            # Forward the request to our Flask API
            response = requests.post(
                API_URL,
                json={
                    "query": query,
                    "channel_id": str(message.channel.id),
                    "user_id": str(message.author.id)
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                # Delete loading message
                await loading_msg.delete()
                
                # Send the response back to Discord
                if 'content' in result:
                    await message.channel.send(result['content'])
                else:
                    await message.channel.send("No response content found")
            else:
                await loading_msg.edit(content=f"❌ Error: {response.json().get('message', 'Unknown error')}")
                
        except Exception as e:
            print(f"Error processing message: {str(e)}")
            await message.channel.send(f"💥 An error occurred: {str(e)}")
    await client.process_commands(message)

# Run the bot
if __name__ == "__main__":
    client.run(os.getenv('DISCORD_BOT_TOKEN'))