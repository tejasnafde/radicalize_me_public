# Archive

This folder contains legacy code that has been replaced by newer implementations but is kept for reference.

## Archived Files

### `main.py` (364 lines)
**Archived on**: 2025-12-23  
**Reason**: Replaced by `discord_bot.py`  
**Description**: Original Discord bot implementation with inline LLM logic and agent-based approach. Superseded by modular architecture with separate handlers and helpers.

### `tools.py` (274 lines)
**Archived on**: 2025-12-23  
**Reason**: Integrated into `helpers/research_pipeline.py`  
**Description**: LangChain tools for web scraping and Reddit search. Functionality now part of the research pipeline with better error handling and logging.

## Why Archive Instead of Delete?

- **Reference**: Useful for understanding evolution of the codebase
- **Recovery**: Can reference old implementations if needed
- **Documentation**: Shows design decisions and what was tried before

## Note

These files are gitignored and not part of the active codebase. Do not import or use them in production code.
