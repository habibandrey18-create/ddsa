#!/usr/bin/env python3
"""Test script to verify Groq API key is working"""

import os
import sys

def test_groq_api():
    """Test the Groq API connection"""
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        print("[FAIL] GROQ_API_KEY environment variable not found!")
        print("Please set it using one of these methods:")
        print("1. Run: setup_env.bat")
        print("2. Set manually: setx GROQ_API_KEY 'your_key_here' /M")
        print("3. Create .env file with: GROQ_API_KEY=your_key_here")
        return False

    try:
        from groq import Groq
        print("[OK] Groq library imported successfully")

        client = Groq(api_key=api_key)
        print("[OK] Groq client initialized")

        # Test with a simple request
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Hello, just testing the API. Respond with 'API test successful'"}],
            max_tokens=20
        )

        result = response.choices[0].message.content.strip()
        print(f"[OK] API test successful! Response: {result}")
        return True

    except ImportError:
        print("[FAIL] Groq library not installed. Run: pip install groq")
        return False
    except Exception as e:
        print(f"[FAIL] API test failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing Groq API connection...")
    success = test_groq_api()
    if success:
        print("\n[SUCCESS] Groq API is working correctly!")
        print("The bot should now be able to generate AI descriptions.")
    else:
        print("\n[FAILED] Groq API test failed. Please check your setup.")
        sys.exit(1)
