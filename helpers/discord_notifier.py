import discord
from typing import Optional, Dict, Any
from .logger import get_logger
from .queue_manager import QueueItem

class DiscordNotifier:
    """Handles Discord notifications for queue updates and results"""
    
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.logger = get_logger()
    
    async def notify_queue_position(self, item: QueueItem) -> bool:
        """Notify user of their position in the queue (only if position > 0)"""
        try:
            # Skip notification if user is first in queue (immediate processing)
            if item.position == 0:
                return True
            
            # Get the channel instead of DMing the user
            channel = self.bot.get_channel(int(item.channel_id))
            if not channel:
                # Fallback to DM if channel not accessible
                user = await self.bot.fetch_user(int(item.user_id))
                await user.send(f"📝 Your query is queued at position **#{item.position}**. Estimated wait: {self._estimate_wait_time(item.position)}")
                return True
            
            # Simple, non-intrusive message in channel
            wait_time = self._estimate_wait_time(item.position)
            await channel.send(f"📝 Query queued at position **#{item.position}** ({wait_time})")
            
            self.logger.info(f"Sent queue position notification: User={item.user_id}, Position={item.position}", "DISCORD_NOTIFIER")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send queue position notification: {str(e)}", "DISCORD_NOTIFIER")
            return False
    
    async def notify_processing_started(self, item: QueueItem) -> bool:
        """Notify user that their query is now being processed (only for queued items)"""
        try:
            # Get the channel instead of DMing the user
            channel = self.bot.get_channel(int(item.channel_id))
            if not channel:
                # Fallback to DM if channel not accessible
                user = await self.bot.fetch_user(int(item.user_id))
                await user.send(f"🔄 Processing your query now...")
                return True
            
            # Simple, non-intrusive message in channel  
            await channel.send(f"🔄 Processing query...")
            
            self.logger.info(f"Sent processing started notification: User={item.user_id}, ID={item.id}", "DISCORD_NOTIFIER")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send processing started notification: {str(e)}", "DISCORD_NOTIFIER")
            return False
    
    async def send_result(self, item: QueueItem) -> bool:
        """Send the final result to the channel (not DM)"""
        try:
            # Get the channel to reply in
            channel = self.bot.get_channel(int(item.channel_id))
            if not channel:
                # Fallback to DM if channel not accessible
                user = await self.bot.fetch_user(int(item.user_id))
                await user.send("✅ Analysis complete! (Could not access original channel)")
                return True
            
            if not item.result or "message" not in item.result:
                await channel.send("❌ Error: Invalid result format")
                return False
            
            result_data = item.result["message"]
            content = result_data.get("content", "No content available")
            
            # Send the actual content in the channel (Discord has 2000 char limit)
            if len(content) <= 2000:
                await channel.send(content)
            else:
                # Split content into chunks
                chunks = [content[i:i+1900] for i in range(0, len(content), 1900)]
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await channel.send(f"**Part {i+1}/{len(chunks)}:**\n{chunk}")
                    else:
                        await channel.send(f"**Part {i+1}/{len(chunks)}:**\n{chunk}")
            
            self.logger.info(f"Sent result to user: User={item.user_id}, ID={item.id}", "DISCORD_NOTIFIER")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send result: {str(e)}", "DISCORD_NOTIFIER")
            return False
    
    async def notify_error(self, item: QueueItem) -> bool:
        """Notify user of processing error"""
        try:
            user = await self.bot.fetch_user(int(item.user_id))
            
            embed = discord.Embed(
                title="❌ Processing Failed",
                description=f"Sorry, there was an error processing your query.",
                color=discord.Color.red()
            )
            
            embed.add_field(
                name="🆔 Query ID", 
                value=f"`{item.id}`", 
                inline=True
            )
            
            embed.add_field(
                name="❓ Your Query", 
                value=f"*{item.query[:150]}{'...' if len(item.query) > 150 else ''}*", 
                inline=False
            )
            
            if item.error:
                error_msg = item.error[:500] + "..." if len(item.error) > 500 else item.error
                embed.add_field(
                    name="🔍 Error Details", 
                    value=f"```{error_msg}```", 
                    inline=False
                )
            
            embed.set_footer(text="Please try rephrasing your question or try again later.")
            
            await user.send(embed=embed)
            
            self.logger.info(f"Sent error notification: User={item.user_id}, ID={item.id}", "DISCORD_NOTIFIER")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send error notification: {str(e)}", "DISCORD_NOTIFIER")
            return False
    
    async def send_queue_status(self, user_id: str, status_data: Dict[str, Any]) -> bool:
        """Send current queue status to user"""
        try:
            user = await self.bot.fetch_user(int(user_id))
            
            embed = discord.Embed(
                title="📊 Queue Status",
                description="Current processing queue information",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="📝 Items in Queue", 
                value=str(status_data.get("queue_size", 0)), 
                inline=True
            )
            
            embed.add_field(
                name="🔄 Currently Processing", 
                value="Yes" if status_data.get("is_processing") else "No", 
                inline=True
            )
            
            embed.add_field(
                name="💾 Max Capacity", 
                value=str(status_data.get("max_capacity", 50)), 
                inline=True
            )
            
            if status_data.get("current_processing"):
                embed.add_field(
                    name="🔍 Processing ID", 
                    value=f"`{status_data['current_processing']}`", 
                    inline=True
                )
            
            await user.send(embed=embed)
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send queue status: {str(e)}", "DISCORD_NOTIFIER")
            return False
    
    def _estimate_wait_time(self, position: int) -> str:
        """Estimate wait time based on queue position"""
        # Assume average processing time of 45 seconds per query
        avg_time_per_query = 45
        estimated_seconds = position * avg_time_per_query
        
        if estimated_seconds < 60:
            return f"~{estimated_seconds} seconds"
        elif estimated_seconds < 3600:
            minutes = estimated_seconds // 60
            return f"~{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            hours = estimated_seconds // 3600
            remaining_minutes = (estimated_seconds % 3600) // 60
            if remaining_minutes > 0:
                return f"~{hours}h {remaining_minutes}m"
            else:
                return f"~{hours} hour{'s' if hours != 1 else ''}"