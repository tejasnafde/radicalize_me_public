import os
import discord
import asyncio
from discord.ext import commands
from helpers.common_helpers import CommonHelpers
from helpers.queue_manager import QueueManager
from helpers.discord_notifier import DiscordNotifier
from handlers.bot_handler import BotHandler


# Import unified logger
from helpers.logger import get_logger

# Initialize logger and helpers
logger = get_logger()
helpers = CommonHelpers()

# Initialize queue system
queue_manager = QueueManager(max_queue_size=20)  # Allow up to 20 queued items
bot_handler = BotHandler()
discord_notifier = None  # Will be initialized after bot is ready

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix='!', intents=intents)

# API configuration
API_URL = os.getenv('API_URL', 'http://app:5000/api/v1/analyze')  # Use service name in Docker network

@client.event
async def on_ready():
    global discord_notifier
    logger.info(f"Bot is ready! Logged in as {client.user}", "DISCORD_BOT")
    
    # Initialize Discord notifier now that bot is ready
    discord_notifier = DiscordNotifier(client)
    
    # Start the queue processor
    queue_manager.start_processor(bot_handler, discord_notifier)
    
    helpers.info_to_discord(f"Bot is ready! Logged in as {client.user}")
    logger.info("Queue system initialized and started", "DISCORD_BOT")

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if client.user.mentioned_in(message):
        try:
            # Extract query from message
            query = message.content.replace(f'<@{client.user.id}>', '').strip()
            user_id = str(message.author.id)
            channel_id = str(message.channel.id)
            
            logger.query_start(query, user_id)
            
            # Validate query
            if not query or len(query.strip()) == 0:
                await message.channel.send("❌ Please provide a query after mentioning me!")
                return
            
            if len(query) > 500:
                await message.channel.send("❌ Query too long! Please keep it under 500 characters.")
                return
            
            try:
                # Add to queue
                queue_item = await queue_manager.add_to_queue(user_id, channel_id, query)
                
                # Send queue position notification (only if position > 0)
                await discord_notifier.notify_queue_position(queue_item)
                
                # For immediate processing (position 0), send a simple acknowledgment
                if queue_item.position == 0:
                    await message.channel.send("🔍 Processing your query...")
                    
            except asyncio.QueueFull:
                await message.channel.send(
                    "❌ The processing queue is currently full. Please try again in a few minutes!"
                )
                logger.warning(f"Queue full, rejected query from user {user_id}", "DISCORD_BOT")
                
        except Exception as e:
            logger.exception(f"Error processing message: {str(e)}", "DISCORD_BOT")
            helpers.report_to_discord(f"Error processing message: {str(e)}")
            await message.channel.send("❌ An error occurred while processing your request.")

# Add queue management commands
@client.command(name='queue')
async def queue_status(ctx):
    """Show current queue status"""
    try:
        status = await queue_manager.get_queue_status()
        await discord_notifier.send_queue_status(str(ctx.author.id), status)
        await ctx.send("📊 Queue status sent to your DMs!")
    except Exception as e:
        logger.error(f"Error showing queue status: {str(e)}", "DISCORD_BOT")
        await ctx.send("❌ Error retrieving queue status.")

@client.command(name='mystatus')
async def my_status(ctx):
    """Show user's current position in queue"""
    try:
        user_id = str(ctx.author.id)
        position = await queue_manager.get_user_queue_position(user_id)
        
        if position:
            wait_time = discord_notifier._estimate_wait_time(position)
            await ctx.send(f"📍 You're at position **#{position}** in the queue (~{wait_time} wait)")
        else:
            await ctx.send("✅ You don't have any queries in the current queue.")
            
    except Exception as e:
        logger.error(f"Error showing user status: {str(e)}", "DISCORD_BOT")
        await ctx.send("❌ Error retrieving your status.")

# Graceful shutdown handler
async def shutdown():
    """Gracefully shutdown the bot and queue system"""
    logger.info("Shutting down bot and queue system...", "DISCORD_BOT")
    await queue_manager.shutdown()
    await client.close()

# Run the bot
if __name__ == "__main__":
    logger.info("Starting Discord bot...")
    try:
        client.run(os.getenv('DISCORD_TOKEN'))
    except KeyboardInterrupt:
        logger.info("Received shutdown signal", "DISCORD_BOT")
        import asyncio
        asyncio.run(shutdown())