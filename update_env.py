#!/usr/bin/env python3
"""Update environment variables for Yandex affiliate parameters"""

import os
import sys

def update_env_vars():
    """Update environment variables for the new affiliate parameters"""

    # New affiliate parameters
    env_vars = {
        "YANDEX_REF_CLID": "14432017",
        "YANDEX_REF_VID": "blog",
        "YANDEX_REF_ERID": "5jtCeReNx12oajxRXisMXab"
    }

    print("Updating environment variables for Yandex affiliate parameters...")

    try:
        # Try to set environment variables (this works on Windows)
        for key, value in env_vars.items():
            os.environ[key] = value
            print(f"✅ Set {key}={value}")

        print("\nEnvironment variables updated successfully!")
        print("Note: These are session variables. For permanent storage,")
        print("add them to your .env file or system environment variables.")

    except Exception as e:
        print(f"❌ Error updating environment variables: {e}")
        return False

    return True

if __name__ == "__main__":
    success = update_env_vars()
    if success:
        print("\nYandex affiliate parameters:")
        print("- CLID: 14432017")
        print("- VID: blog")
        print("- ERID: 5jtCeReNx12oajxRXisMXab")
        print("\nThese will be used for generating affiliate links with ad-marking.")
    else:
        sys.exit(1)