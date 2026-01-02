#!/usr/bin/env python3
"""
Test script for Night Mode logic
"""
import sys
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))


def test_night_mode_logic():
    """Test the night mode logic with different hours"""
    # Import config module directly to get the global variables
    import importlib.util

    spec = importlib.util.spec_from_file_location("config_main", "config.py")
    config_main = importlib.util.module_from_spec(spec)

    # Execute the module but catch BOT_TOKEN error
    try:
        spec.loader.exec_module(config_main)
    except RuntimeError as e:
        if "BOT_TOKEN is not set" in str(e):
            print("INFO: BOT_TOKEN not set (expected for test)")
        else:
            raise e

    print("TEST: Night Mode Logic")
    print("=" * 40)
    print(f"NIGHT_START: {config_main.NIGHT_START}, NIGHT_END: {config_main.NIGHT_END}")
    print()

    # Test various hours
    test_hours = [0, 1, 6, 7, 8, 9, 12, 18, 22, 23]

    for hour in test_hours:
        # Simulate the logic from bot.py
        night_start = config_main.NIGHT_START
        night_end = config_main.NIGHT_END

        # Handle night mode that spans midnight (e.g., 23:00 to 08:00)
        if night_start > night_end:
            # Night mode spans midnight (e.g., 23:00-08:00)
            is_night = hour >= night_start or hour < night_end
        else:
            # Night mode within same day (e.g., 22:00-23:00)
            is_night = night_start <= hour < night_end

        # Use silent notifications during night mode
        disable_notification = is_night

        status = "SILENT" if is_night else "NORMAL"
        print(f"Hour {hour:2d}: {status} (disable_notification={disable_notification})")


if __name__ == "__main__":
    test_night_mode_logic()
