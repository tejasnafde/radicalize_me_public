import os
import subprocess
import sys
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Log to stdout for Docker
    ]
)
logger = logging.getLogger(__name__)

def run_flask():
    """Run Flask API in a separate process"""
    logger.info("Starting Flask API...")
    return subprocess.Popen([sys.executable, 'flask_app.py'], 
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,
                          universal_newlines=True,
                          bufsize=1)  # Line buffered

def run_discord_bot():
    """Run Discord bot in a separate process"""
    logger.info("Starting Discord bot...")
    return subprocess.Popen([sys.executable, 'discord_bot.py'],
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,
                          universal_newlines=True,
                          bufsize=1)  # Line buffered

def monitor_process(process, name):
    """Monitor a process and log its output"""
    if process.poll() is not None:
        logger.error(f"{name} process died with return code {process.returncode}")
        return False
    
    # Read and log output
    output = process.stdout.readline()
    if output:
        logger.info(f"{name}: {output.strip()}")
    
    return True

if __name__ == "__main__":
    logger.info("Starting services...")
    
    # Start both services
    flask_process = run_flask()
    discord_process = run_discord_bot()
    
    try:
        # Main loop to keep the process alive and monitor subprocesses
        while True:
            # Monitor Flask process
            if not monitor_process(flask_process, "Flask"):
                logger.info("Restarting Flask API...")
                flask_process = run_flask()
            
            # Monitor Discord process
            if not monitor_process(discord_process, "Discord"):
                logger.info("Restarting Discord bot...")
                discord_process = run_discord_bot()
            
            # Sleep to prevent high CPU usage
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down services...")
        flask_process.terminate()
        discord_process.terminate()
        flask_process.wait()
        discord_process.wait()
        logger.info("Services stopped.")