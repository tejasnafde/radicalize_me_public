import os
import subprocess
import sys
from discord_bot import client
import asyncio

def run_flask():
    # Run Flask in a separate process
    subprocess.Popen([sys.executable, 'flask_app.py'])

def run_discord_bot():
    asyncio.run(client.start(os.getenv('DISCORD_TOKEN')))

if __name__ == "__main__":
    # Start Flask in a separate process
    run_flask()
    
    # Run Discord bot in main process
    run_discord_bot()