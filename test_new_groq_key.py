#!/usr/bin/env python3
"""Test script to verify the new Groq API key works"""

import asyncio
import os
import sys

async def test_new_groq_key():
    """Test the new Groq API key"""

    # Use the new API key
    groq_api_key = "your_groq_api_key_here"

    try:
        from groq import AsyncGroq
        print("[OK] Groq library imported successfully")

        client = AsyncGroq(api_key=groq_api_key)
        print("[OK] AsyncGroq client initialized with new key")

        # Test with a simple request
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Hello! This is a test of the new API key. Respond with: 'New API key test successful!'"}],
            max_tokens=20
        )

        result = response.choices[0].message.content.strip()
        print(f"[OK] API test successful! Response: {result}")

        if "successful" in result.lower():
            print("[SUCCESS] New Groq API key is working perfectly!")
            return True
        else:
            print(f"[WARNING] API responded but with unexpected content: {result}")
            return True

    except ImportError:
        print("[FAIL] Groq library not installed")
        return False
    except Exception as e:
        print(f"[FAIL] API test failed: {e}")
        return False

async def main():
    """Main test function"""
    print("Testing New Groq API Key")
    print("=" * 40)

    success = await test_new_groq_key()

    if success:
        print("\n" + "=" * 40)
        print("✅ New Groq API key is valid and working!")
        print("The bot can now use this key for AI content generation.")
    else:
        print("\n" + "=" * 40)
        print("❌ New API key test failed. Please check the key.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())