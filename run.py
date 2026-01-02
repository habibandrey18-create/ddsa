#!/usr/bin/env python3
"""
Entry point for the Yandex.Market Bot
"""
import sys
import os

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import and run the main application
import asyncio
from src.core.app import main

if __name__ == "__main__":
    asyncio.run(main())
