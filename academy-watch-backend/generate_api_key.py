#!/usr/bin/env python3
"""
Generate a secure admin API key for testing the loan detection system.

This script generates a random API key that can be used for local development.
DO NOT use this key in production - generate a proper secure key instead.
"""

import os
import secrets
import string

from src.utils.log_privacy import log_metadata


def generate_api_key(length=32):
    """Generate a secure random API key."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main():
    """Generate and display API key."""
    print("🔑 Generating Admin API Key")
    print(log_metadata("=" * 40))

    # Generate a secure API key
    api_key = generate_api_key(32)

    print(f"✅ Generated API Key: {log_metadata(api_key)}")
    print()
    print("📝 To use this key:")
    print("1. Add it to your .env file:")
    print(f"   ADMIN_API_KEY={log_metadata(api_key)}")
    print()
    print("2. Or set it as an environment variable:")
    print(f"   export ADMIN_API_KEY='{log_metadata(api_key)}'")
    print()
    print("3. Or pass it in your API requests:")
    print(f"   curl -H 'X-API-Key: {log_metadata(api_key)}' http://localhost:5001/detect-loan-candidates")
    print()
    print("⚠️  IMPORTANT:")
    print("   - This is for development/testing only")
    print("   - Use a proper secure key in production")
    print("   - Never commit API keys to version control")
    print()

    # Check if .env file exists
    env_file = ".env"
    if os.path.exists(env_file):
        print(f"📄 Found existing .env file: {log_metadata(env_file)}")
        print("   You can add the ADMIN_API_KEY line to it.")
    else:
        print("📄 No .env file found. Create one with:")
        print(f"   ADMIN_API_KEY={log_metadata(api_key)}")
        print("   API_FOOTBALL_KEY=your_api_football_key_here")

    return api_key


if __name__ == "__main__":
    main()
