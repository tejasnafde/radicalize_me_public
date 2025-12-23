#!/usr/bin/env python3
"""
Enhanced log viewer for the unified logging system.
Usage:
    python view_logs.py [log_file] [--tail N] [--filter KEYWORD] [--context CONTEXT] [--level LEVEL]
    
    log_file: Optional, the log file to view (default: logs/app.log)
    --tail N: Optional, show only the last N lines (default: 50)
    --filter KEYWORD: Optional, only show lines containing KEYWORD
    --context CONTEXT: Optional, only show lines from specific context (e.g., PIPELINE, SEARCH)
    --level LEVEL: Optional, only show lines of specific level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    --follow: Follow the log file (like tail -f)
    --errors-only: Show only error log file (logs/errors.log)
"""

import os
import sys
import argparse
import time
from datetime import datetime

def parse_args():
    parser = argparse.ArgumentParser(description="View application logs with filtering")
    parser.add_argument("log_file", nargs="?", default="logs/app.log", help="Log file to view")
    parser.add_argument("--tail", "-t", type=int, default=50, help="Number of lines to show")
    parser.add_argument("--filter", "-f", help="Only show lines containing this text")
    parser.add_argument("--context", "-c", help="Only show lines from specific context (e.g., PIPELINE, SEARCH)")
    parser.add_argument("--level", "-l", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
                       help="Only show lines of specific level")
    parser.add_argument("--follow", "-F", action="store_true", help="Follow the log file (like tail -f)")
    parser.add_argument("--errors-only", "-e", action="store_true", help="Show only error log file")
    parser.add_argument("--query", "-q", help="Show logs related to a specific query")
    return parser.parse_args()

def matches_filters(line, filter_text=None, context=None, level=None, query=None):
    """Check if a line matches all the specified filters"""
    if filter_text and filter_text.lower() not in line.lower():
        return False
    
    if level and f" - {level} - " not in line:
        return False
    
    if context and f"[{context}]" not in line:
        return False
    
    if query and query.lower() not in line.lower():
        return False
    
    return True

def tail_file(filename, num_lines, **filters):
    """Display the last num_lines of a file with filtering"""
    if not os.path.exists(filename):
        print(f"Error: File {filename} does not exist")
        return []
    
    try:
        with open(filename, 'r') as f:
            lines = f.readlines()
            
        # Apply filters
        filtered_lines = []
        for line in lines:
            if matches_filters(line, **filters):
                filtered_lines.append(line)
            
        return filtered_lines[-num_lines:] if filtered_lines else []
    except Exception as e:
        print(f"Error reading file: {str(e)}")
        return []

def follow_file(filename, **filters):
    """Follow a file like tail -f with filtering"""
    try:
        with open(filename, 'r') as f:
            # Go to the end of the file
            f.seek(0, 2)
            
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                
                if matches_filters(line, **filters):
                    yield line
    except KeyboardInterrupt:
        print("\nStopped following file.")
    except Exception as e:
        print(f"Error following file: {str(e)}")

def show_available_contexts():
    """Show available contexts by scanning log files"""
    contexts = set()
    log_files = ["logs/app.log", "logs/errors.log"]
    
    for log_file in log_files:
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r') as f:
                    for line in f:
                        # Look for [CONTEXT] patterns
                        import re
                        match = re.search(r'\[([A-Z_]+)\]', line)
                        if match:
                            contexts.add(match.group(1))
            except:
                continue
    
    return sorted(contexts)

def main():
    args = parse_args()
    
    # Handle special flags
    if args.errors_only:
        args.log_file = "logs/errors.log"
    
    if not os.path.exists(args.log_file):
        print(f"Log file not found: {args.log_file}")
        print("Available log files:")
        if os.path.exists("logs"):
            for file in os.listdir("logs"):
                if file.endswith(".log"):
                    print(f"  - logs/{file}")
        print("\nAvailable contexts:")
        for context in show_available_contexts():
            print(f"  - {context}")
        return
    
    # Prepare filters
    filters = {
        'filter_text': args.filter,
        'context': args.context,
        'level': args.level,
        'query': args.query
    }
    
    # Build description of what we're showing
    description_parts = []
    if args.context:
        description_parts.append(f"context={args.context}")
    if args.level:
        description_parts.append(f"level={args.level}")
    if args.filter:
        description_parts.append(f"containing='{args.filter}'")
    if args.query:
        description_parts.append(f"query='{args.query}'")
    
    description = " with " + ", ".join(description_parts) if description_parts else ""
    
    if args.follow:
        print(f"Following {args.log_file}{description} (Press Ctrl+C to stop)...")
        print("-" * 80)
        for line in follow_file(args.log_file, **filters):
            print(line, end="")
    else:
        lines = tail_file(args.log_file, args.tail, **filters)
        if lines:
            print(f"Last {len(lines)} lines from {args.log_file}{description}:")
            print("-" * 80)
            for line in lines:
                print(line, end="")
        else:
            print(f"No matching lines found in {args.log_file}")
            print("\nTry using different filters or check available contexts:")
            for context in show_available_contexts():
                print(f"  - {context}")

if __name__ == "__main__":
    main() 