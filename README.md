# radicalize_me_public
discord bot

## Unified Logging System

The application uses a unified logging system that intelligently routes messages based on severity. All logging has been migrated from print statements and the old logger system to this centralized approach.

- **DEBUG/INFO/WARNING**: Only written to log files (silent notifications)
- **ERROR/CRITICAL**: Written to both log files AND sent to Discord (active alerts)

### Log Files
- `logs/app.log` - All application logs with rotation (20MB max size, 10 backups)
- `logs/errors.log` - Only errors and critical issues (10MB max size, 5 backups)

### Context-Based Logging
All log messages include context tags for easy filtering:
- `[PIPELINE]` - Research pipeline operations
- `[SEARCH]` - Search API operations 
- `[LLM]` - Language model interactions
- `[SCRAPING]` - Web scraping operations
- `[DISCORD_BOT]` - Discord bot events
- `[RUNNER]` - Process management
- `[API]` - API calls and responses

### Enhanced Log Viewer
Use the enhanced `view_logs.py` script with powerful filtering:

```bash
# View all recent logs
python view_logs.py

# Follow logs in real-time
python view_logs.py --follow

# Filter by context (show only pipeline operations)
python view_logs.py --context PIPELINE --follow

# Filter by log level (show only errors)
python view_logs.py --level ERROR

# Show only error log file
python view_logs.py --errors-only

# Filter by query content
python view_logs.py --query "stalin" --follow

# Combine filters (pipeline errors only)
python view_logs.py --context PIPELINE --level ERROR

# Search for specific text
python view_logs.py --filter "optimization" --tail 100
```

### Available Commands
- `--tail N`: Show last N lines (default: 50)
- `--follow`: Follow log file in real-time
- `--context CTX`: Filter by context (PIPELINE, SEARCH, etc.)
- `--level LVL`: Filter by level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `--filter TEXT`: Show lines containing specific text
- `--query QUERY`: Show logs related to a specific query
- `--errors-only`: Show only the error log file

### Discord Notifications
Only errors and critical failures are sent to Discord, keeping your notification channel clean while maintaining full visibility into issues that need immediate attention.
