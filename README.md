# Radicalize Me - Marxist Research Discord Bot

A Discord bot that provides Marxist analysis and research on user queries using multiple LLM providers, web scraping, and Reddit integration.

## Features

- 🔍 **Multi-source Research** - Searches Marxist websites, Reddit, and academic sources
- 📊 **Queue System** - Handles multiple users with position tracking and wait time estimates
- 🤖 **LLM-Powered Analysis** - Uses Google Gemini, Groq, and HuggingFace with automatic fallback
- 📝 **Comprehensive Logging** - Unified logging system with Discord error alerts
- 🎯 **Smart Citations** - Provides sources and references for all analysis

## Quick Start

### 1. Installation

```bash
git clone https://github.com/tejasnafde/radicalize_me_public.git
cd radicalize_me_public
pip install -r requirements.txt
```

### 2. Configuration

```bash
cp .env.example .env
# Edit .env with your API keys
```

**Required API Keys:**
- `GOOGLE_API_KEY` - Google Gemini (primary LLM)
- `DISCORD_TOKEN` - Discord bot token
- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` - Reddit API credentials

**Optional API Keys:**
- `GROQ_API_KEY`, `HUGGINGFACE_API_KEY` - Fallback LLMs
- `GOOGLE_CSE_ID`, `SERPAPI_API_KEY` - Search API fallbacks

### 3. Run

**Docker (Recommended):**
```bash
docker-compose up -d
```

**Local:**
```bash
python run.py
```

## Usage

### Discord Commands

- `@Bot <query>` - Ask a question and get Marxist analysis
- `!queue` - View current queue status (sent to DMs)
- `!mystatus` - Check your position in queue

### REST API

```bash
# Health check
curl http://localhost:5000/api/v1/health

# Analysis request
curl -X POST http://localhost:5000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"query": "What is democratic centralism?", "user_id": "123"}'
```

## Documentation

- [Queue System](QUEUE_SYSTEM.md) - Detailed queue implementation
- [Logging System](#logging-system) - Log viewer and filtering

## Logging System

The application uses a unified logging system with intelligent routing:

- **DEBUG/INFO/WARNING** - Only written to log files
- **ERROR/CRITICAL** - Written to log files AND sent to Discord

### Log Files

- `logs/app.log` - All logs (20MB rotation, 10 backups)
- `logs/errors.log` - Errors only (10MB rotation, 5 backups)

### Log Viewer

```bash
# View recent logs
python view_logs.py

# Follow in real-time
python view_logs.py --follow

# Filter by context
python view_logs.py --context PIPELINE --follow

# Filter by level
python view_logs.py --level ERROR

# Show only errors
python view_logs.py --errors-only
```

## Architecture

```
Discord Bot → Queue Manager → Bot Handler → Research Pipeline
                                              ↓
                            Web Search + Reddit + LLM Analysis
                                              ↓
                            Discord Notifier → User Response
```

**Key Components:**
- `discord_bot.py` - Discord bot entry point
- `helpers/queue_manager.py` - Async queue with persistence
- `helpers/research_pipeline.py` - Core research & LLM orchestration
- `helpers/reddit_helper.py` - Reddit integration
- `handlers/bot_handler.py` - Request processing

## Development

### Project Structure

```
radicalize_me_public/
├── discord_bot.py          # Discord bot entry point
├── flask_app.py            # Flask API entry point
├── run.py                  # Process runner (both services)
├── handlers/               # Request handlers
├── helpers/                # Core logic (pipeline, queue, etc.)
├── ui/                     # REST API endpoints
├── tests/                  # Test files
├── logs/                   # Runtime logs
└── archive/                # Legacy code (reference only)
```

### Running Tests

```bash
python test_queue.py
python test_reddit_integration.py
python tests.py
```

## Deployment

### Docker

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop
docker-compose down
```

### Environment Variables

See `.env.example` for all configuration options.

## Contributing

This is a personal project, but suggestions and feedback are welcome via issues.

## License

MIT License - See LICENSE file for details
