#!/usr/bin/env python3
"""
Simple bot launcher script
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

if __name__ == '__main__':
    print('🚀 Starting Yandex Market Bot...')
    print('=' * 50)

    try:
        # Import and run bot
        import bot
        print('✅ Bot loaded successfully!')

        # Run the bot (this will block)
        import asyncio
        asyncio.run(bot.main())

    except KeyboardInterrupt:
        print('\n🛑 Bot stopped by user')
    except Exception as e:
        print(f'❌ Bot failed to start: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)
