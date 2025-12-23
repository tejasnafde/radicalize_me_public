import asyncio
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import uuid

from .logger import get_logger

@dataclass
class QueueItem:
    """Represents a query in the processing queue"""
    id: str
    user_id: str
    channel_id: str
    query: str
    timestamp: float
    status: str = "queued"  # queued, processing, completed, failed
    position: int = 0
    result: Optional[Dict] = None
    error: Optional[str] = None

class QueueManager:
    """Manages query processing queue with user notifications"""
    
    def __init__(self, max_queue_size: int = 50):
        self.logger = get_logger()
        self.max_queue_size = max_queue_size
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self.active_items: Dict[str, QueueItem] = {}  # Track all items by ID
        self.processing_lock = asyncio.Lock()
        self.is_processing = False
        self.current_item: Optional[QueueItem] = None
        self.queue_file = Path("logs/queue_state.json")
        
        # Load persisted queue on startup
        self._load_queue_state()
        
        # Start background processor
        self.processor_task = None
        
    def start_processor(self, bot_handler, discord_notifier):
        """Start the background queue processor"""
        if self.processor_task is None or self.processor_task.done():
            self.processor_task = asyncio.create_task(
                self._queue_processor(bot_handler, discord_notifier)
            )
            self.logger.info("Queue processor started", "QUEUE")
    
    async def add_to_queue(self, user_id: str, channel_id: str, query: str) -> QueueItem:
        """Add a new query to the queue"""
        # Generate unique ID for this query
        item_id = str(uuid.uuid4())[:8]
        
        # Create queue item
        item = QueueItem(
            id=item_id,
            user_id=user_id,
            channel_id=channel_id,
            query=query,
            timestamp=time.time()
        )
        
        try:
            # Check if queue is full
            if self.queue.qsize() >= self.max_queue_size:
                raise asyncio.QueueFull("Queue is at maximum capacity")
            
            # Add to queue
            await self.queue.put(item)
            self.active_items[item_id] = item
            
            # Update positions for all queued items
            await self._update_queue_positions()
            
            # Persist queue state
            self._save_queue_state()
            
            self.logger.info(f"Added query to queue: ID={item_id}, User={user_id}, Position={item.position}", "QUEUE")
            return item
            
        except asyncio.QueueFull:
            self.logger.warning(f"Queue full, rejecting query from user {user_id}", "QUEUE")
            raise
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        queued_count = self.queue.qsize()
        processing = self.current_item.id if self.current_item else None
        
        return {
            "queue_size": queued_count,
            "is_processing": self.is_processing,
            "current_processing": processing,
            "max_capacity": self.max_queue_size,
            "active_items": len(self.active_items)
        }
    
    async def get_item_status(self, item_id: str) -> Optional[QueueItem]:
        """Get status of a specific queue item"""
        return self.active_items.get(item_id)
    
    async def _update_queue_positions(self):
        """Update position numbers for all queued items"""
        position = 1
        temp_items = []
        
        # Extract all items from queue to update positions
        while not self.queue.empty():
            try:
                item = await asyncio.wait_for(self.queue.get(), timeout=0.1)
                item.position = position
                temp_items.append(item)
                position += 1
            except asyncio.TimeoutError:
                break
        
        # Put items back in queue
        for item in temp_items:
            await self.queue.put(item)
    
    async def _queue_processor(self, bot_handler, discord_notifier):
        """Background task that processes the queue"""
        self.logger.info("Queue processor started", "QUEUE")
        
        while True:
            try:
                # Wait for next item in queue
                item = await self.queue.get()
                
                async with self.processing_lock:
                    self.is_processing = True
                    self.current_item = item
                    item.status = "processing"
                    
                    self.logger.info(f"Starting to process query: ID={item.id}, User={item.user_id}", "QUEUE")
                    
                    # Only notify if there was a queue (position > 0 when added)
                    # For immediate processing (position 0), skip notification
                    if item.position > 0:
                        await discord_notifier.notify_processing_started(item)
                    
                    try:
                        # Process the query using bot handler
                        start_time = time.time()
                        result = await bot_handler.handle_request(
                            query=item.query,
                            user_id=item.user_id,
                            channel_id=item.channel_id
                        )
                        
                        processing_time = time.time() - start_time
                        
                        # Store result
                        item.result = result
                        item.status = "completed"
                        
                        self.logger.info(f"Query processed successfully: ID={item.id}, Time={processing_time:.2f}s", "QUEUE")
                        
                        # Send result to user
                        await discord_notifier.send_result(item)
                        
                    except Exception as e:
                        # Handle processing error
                        item.error = str(e)
                        item.status = "failed"
                        
                        self.logger.error(f"Query processing failed: ID={item.id}, Error={str(e)}", "QUEUE")
                        
                        # Notify user of error
                        await discord_notifier.notify_error(item)
                    
                    finally:
                        # Clean up
                        self.current_item = None
                        self.is_processing = False
                        
                        # Remove from active items after a delay (keep for status checks)
                        asyncio.create_task(self._cleanup_item(item.id, delay=300))  # 5 minute delay
                        
                        # Update queue positions for remaining items
                        await self._update_queue_positions()
                        
                        # Persist queue state
                        self._save_queue_state()
                        
                        # Mark task as done
                        self.queue.task_done()
            
            except Exception as e:
                self.logger.error(f"Queue processor error: {str(e)}", "QUEUE")
                await asyncio.sleep(5)  # Wait before retrying
    
    async def _cleanup_item(self, item_id: str, delay: int = 300):
        """Remove completed/failed items after delay"""
        await asyncio.sleep(delay)
        if item_id in self.active_items:
            del self.active_items[item_id]
            self.logger.debug(f"Cleaned up queue item: {item_id}", "QUEUE")
    
    def _save_queue_state(self):
        """Persist queue state to disk"""
        try:
            # Create logs directory if it doesn't exist
            self.queue_file.parent.mkdir(exist_ok=True)
            
            # Convert queue items to serializable format
            state = {
                "active_items": {
                    item_id: asdict(item) for item_id, item in self.active_items.items()
                },
                "timestamp": time.time()
            }
            
            with open(self.queue_file, 'w') as f:
                json.dump(state, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Failed to save queue state: {str(e)}", "QUEUE")
    
    def _load_queue_state(self):
        """Load persisted queue state from disk"""
        try:
            if self.queue_file.exists():
                with open(self.queue_file, 'r') as f:
                    state = json.load(f)
                
                # Restore active items
                for item_id, item_data in state.get("active_items", {}).items():
                    item = QueueItem(**item_data)
                    # Reset processing items to queued status on restart
                    if item.status == "processing":
                        item.status = "queued"
                    self.active_items[item_id] = item
                
                self.logger.info(f"Loaded queue state: {len(self.active_items)} items", "QUEUE")
                
        except Exception as e:
            self.logger.error(f"Failed to load queue state: {str(e)}", "QUEUE")
    
    async def get_user_queue_position(self, user_id: str) -> Optional[int]:
        """Get the earliest queue position for a user"""
        user_positions = []
        for item in self.active_items.values():
            if item.user_id == user_id and item.status == "queued":
                user_positions.append(item.position)
        
        return min(user_positions) if user_positions else None
    
    async def shutdown(self):
        """Gracefully shutdown the queue processor"""
        if self.processor_task:
            self.processor_task.cancel()
            try:
                await self.processor_task
            except asyncio.CancelledError:
                pass
        
        self._save_queue_state()
        self.logger.info("Queue manager shutdown complete", "QUEUE") 