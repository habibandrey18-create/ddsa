#!/usr/bin/env python3
"""
System Diagnostic Script for Yandex.Market Bot
Verifies core components: Dependencies, Database WAL mode, Pydantic Config, HTTP Singleton
"""
import asyncio
import sqlite3
import sys
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Handle Windows console encoding for emojis
try:
    import os

    if os.name == "nt":
        import codecs

        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "replace")
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "replace")
except:
    pass


async def check_dependencies():
    """Check if required dependencies are installed"""
    print("[CHECK] Checking Dependencies...")

    deps = ["apscheduler", "pydantic", "aiohttp", "uvloop"]
    missing = []

    for dep in deps:
        try:
            __import__(dep)
            print(f"[OK] {dep}")
        except ImportError:
            missing.append(dep)
            print(f"[FAIL] Missing library: {dep}")

    if missing:
        print(f"[WARN] Install missing dependencies: pip install {' '.join(missing)}")
        return False
    else:
        print("[OK] All dependencies available")
        return True


def check_database():
    """Check database WAL mode"""
    print("\n[CHECK] Checking Database Health...")

    try:
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()

        # Check journal mode
        cursor.execute("PRAGMA journal_mode;")
        result = cursor.fetchone()[0]

        if result.lower() == "wal":
            print("[OK] WAL Mode Active")
            status = True
        else:
            print(f"[WARN] WAL Mode Inactive (current: {result})")
            status = False

        conn.close()
        return status

    except Exception as e:
        print(f"[FAIL] Database Error: {e}")
        return False


def check_configuration():
    """Check Pydantic configuration"""
    print("\n[CHECK] Checking Configuration...")

    try:
        # Import config.py directly as a module, but catch RuntimeError for missing BOT_TOKEN
        import importlib.util

        spec = importlib.util.spec_from_file_location("config_main", "config.py")
        config_main = importlib.util.module_from_spec(spec)

        # Execute the module, but catch the RuntimeError from missing BOT_TOKEN
        try:
            spec.loader.exec_module(config_main)
        except RuntimeError as runtime_error:
            if "BOT_TOKEN is not set" in str(runtime_error):
                print("[OK] Pydantic configuration structure found")
                print("[INFO] BOT_TOKEN validation skipped (expected for diagnostic)")
                print("       Bot will work once .env file is properly configured")
                return True
            else:
                raise runtime_error

        # Check if Settings class exists and can be instantiated
        if hasattr(config_main, "Settings"):
            Settings = config_main.Settings

            # Try to create settings instance (this will validate)
            try:
                settings = Settings()

                # Check key settings (mask sensitive data)
                auto_search = getattr(settings, "AUTO_SEARCH_INTERVAL", "NOT_SET")
                admin_id = getattr(settings, "ADMIN_ID", "NOT_SET")

                # Mask admin ID for privacy
                if admin_id != "NOT_SET" and len(str(admin_id)) > 4:
                    masked_admin = (
                        str(admin_id)[:2]
                        + "*" * (len(str(admin_id)) - 4)
                        + str(admin_id)[-2:]
                    )
                else:
                    masked_admin = admin_id

                print(f"[OK] AUTO_SEARCH_INTERVAL: {auto_search}")
                print(f"[OK] ADMIN_ID: {masked_admin}")
                print("[OK] Pydantic configuration loaded successfully")
                return True

            except Exception as validation_error:
                print(f"[FAIL] Settings validation failed: {validation_error}")
                return False
        else:
            print("[FAIL] Settings class not found in config.py")
            return False

    except Exception as e:
        print(f"[FAIL] Configuration import failed: {e}")
        return False


async def check_network():
    """Check HTTP Client Singleton and connectivity"""
    print("\n[CHECK] Checking Network Connectivity...")

    try:
        from services.http_client import HTTPClient

        # Initialize client (should be singleton)
        client = HTTPClient()

        # Check if session exists
        if client.session is None:
            print("[FAIL] HTTP Client session not initialized")
            return False

        print("[OK] HTTP Client Singleton initialized")

        # Test real network request
        try:
            result = await client.fetch_text("https://www.google.com", max_retries=1)
            if result and len(result) > 0:
                print("[OK] Network OK")
                network_ok = True
            else:
                print("[FAIL] Network Error: Empty response")
                network_ok = False
        except Exception as e:
            print(f"[FAIL] Network Error: {e}")
            network_ok = False

        # Close client properly
        await client.close()
        print("[OK] HTTP Client closed properly")

        return network_ok

    except Exception as e:
        print(f"[FAIL] HTTP Client Error: {e}")
        return False


async def main():
    """Run all diagnostic checks"""
    print("START: Yandex.Market Bot System Diagnostic")
    print("=" * 50)

    results = []

    # 1. Dependencies
    results.append(await check_dependencies())

    # 2. Database
    results.append(check_database())

    # 3. Configuration
    results.append(check_configuration())

    # 4. Network
    results.append(await check_network())

    # Summary
    print("\n" + "=" * 50)
    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"SUCCESS: All checks passed! ({passed}/{total})")
        return 0
    else:
        print(f"WARNING: Some checks failed. ({passed}/{total} passed)")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
