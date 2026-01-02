# config/__init__.py
"""Configuration package for Yandex Market Bot"""

# Re-export main config module to maintain backward compatibility
# This allows both "import config" and "from config.link_generation_config import ..."

import sys
import os
import importlib.util

# Get parent directory
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
config_py_path = os.path.join(parent_dir, "config.py")

# Import main config module if it exists
if os.path.exists(config_py_path):
    try:
        # Import config.py directly
        spec = importlib.util.spec_from_file_location("config_py", config_py_path)
        config_py = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config_py)

        # Try to get settings from config_py
        if hasattr(config_py, 'settings'):
            settings = config_py.settings
        else:
            # Fallback: create basic settings-like object
            class FallbackSettings:
                def __init__(self):
                    # Set defaults from environment variables
                    import os
                    self.USE_POSTGRES = os.getenv('USE_POSTGRES', 'false').lower() == 'true'
                    self.USE_REDIS = os.getenv('USE_REDIS', 'false').lower() == 'true'
                    self.ENVIRONMENT = os.getenv('ENVIRONMENT', 'dev')
                    self.DEBUG_MODE = os.getenv('DEBUG_MODE', 'true').lower() == 'true'
                    self.BOT_TOKEN = os.getenv('BOT_TOKEN', '')
                    self.CHANNEL_ID = os.getenv('CHANNEL_ID', '@marketi_tochka')
                    self.ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
                    self.USE_OFFICIAL_API = os.getenv('USE_OFFICIAL_API', 'false').lower() == 'true'
                    self.HASHTAG_COUNT = int(os.getenv('HASHTAG_COUNT', '5'))
                    self.AUTO_SEARCH_QUERIES = os.getenv('AUTO_SEARCH_QUERIES', '')
                    self.AUTO_SEARCH_MAX_PER_QUERY = int(os.getenv('AUTO_SEARCH_MAX_PER_QUERY', '3'))
                    self.AUTO_MAIN_PAGE_ENABLED = os.getenv('AUTO_MAIN_PAGE_ENABLED', 'true').lower() == 'true'
                    self.AUTO_MAIN_PAGE_MAX = int(os.getenv('AUTO_MAIN_PAGE_MAX', '5'))

            settings = FallbackSettings()

        BOT_TOKEN = getattr(settings, 'BOT_TOKEN', '')
        TOKEN = BOT_TOKEN

        # Re-export other attributes from settings
        for attr in dir(settings):
            if not attr.startswith("_"):
                setattr(sys.modules[__name__], attr, getattr(settings, attr))

    except Exception as e:
        # If import fails, create fallback from environment
        print(f"Config import failed: {e}, using environment fallback")
        import os
        globals().update({
            'BOT_TOKEN': os.getenv('BOT_TOKEN', ''),
            'TOKEN': os.getenv('BOT_TOKEN', ''),
            'CHANNEL_ID': os.getenv('CHANNEL_ID', '@marketi_tochka'),
            'ADMIN_ID': int(os.getenv('ADMIN_ID', '0')),
            'USE_OFFICIAL_API': os.getenv('USE_OFFICIAL_API', 'false').lower() == 'true',
            'USE_POSTGRES': os.getenv('USE_POSTGRES', 'false').lower() == 'true',
            'USE_REDIS': os.getenv('USE_REDIS', 'false').lower() == 'true',
            'ENVIRONMENT': os.getenv('ENVIRONMENT', 'dev'),
            'DEBUG_MODE': os.getenv('DEBUG_MODE', 'true').lower() == 'true',
            'HASHTAG_COUNT': int(os.getenv('HASHTAG_COUNT', '5')),
            'AUTO_SEARCH_QUERIES': os.getenv('AUTO_SEARCH_QUERIES', ''),
            'AUTO_SEARCH_MAX_PER_QUERY': int(os.getenv('AUTO_SEARCH_MAX_PER_QUERY', '3')),
            'AUTO_MAIN_PAGE_ENABLED': os.getenv('AUTO_MAIN_PAGE_ENABLED', 'true').lower() == 'true',
            'AUTO_MAIN_PAGE_MAX': int(os.getenv('AUTO_MAIN_PAGE_MAX', '5')),
        })

# Also export link_generation_config
from . import link_generation_config
