import os
import subprocess
import sys
import time
import logging

# Import unified logger
from helpers.logger import get_logger

# Initialize logger
logger = get_logger()

def run_flask():
    """Run Flask API in a separate process"""
    logger.info("Starting Flask API", "RUNNER")
    return subprocess.Popen([sys.executable, 'flask_app.py'], 
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,
                          universal_newlines=True,
                          bufsize=1)  # Line buffered

def run_discord_bot():
    """Run Discord bot in a separate process"""
    logger.info("Starting Discord bot", "RUNNER")
    return subprocess.Popen([sys.executable, 'discord_bot.py'],
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,
                          universal_newlines=True,
                          bufsize=1)  # Line buffered

def monitor_process(process, name):
    """Monitor a process and log its output"""
    if process.poll() is not None:
        logger.critical(f"{name} process died with return code {process.returncode}", "RUNNER")
        return False
    
    # Read and log output
    output = process.stdout.readline()
    if output:
        logger.debug(f"{name}: {output.strip()}", "SUBPROCESS")
    
    return True

if __name__ == "__main__":
    logger.info("Starting services", "RUNNER")
    
    # Start both services
    flask_process = run_flask()
    discord_process = run_discord_bot()
    
    try:
        # Main loop to keep the process alive and monitor subprocesses
        while True:
            # Monitor Flask process
            if not monitor_process(flask_process, "Flask"):
                logger.warning("Restarting Flask API", "RUNNER")
                flask_process = run_flask()
            
            # Monitor Discord process
            if not monitor_process(discord_process, "Discord"):
                logger.warning("Restarting Discord bot", "RUNNER")
                discord_process = run_discord_bot()
            
            # Sleep to prevent high CPU usage
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down services", "RUNNER")
        flask_process.terminate()
        discord_process.terminate()
        flask_process.wait()
        discord_process.wait()
        logger.info("Services stopped", "RUNNER")