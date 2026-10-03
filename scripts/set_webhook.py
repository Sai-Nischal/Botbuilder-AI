#!/usr/bin/env python3
import asyncio
import sys
import argparse
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import TELEGRAM_BOT_TOKEN, PUBLIC_BASE_URL
from app.telegram_api import set_webhook, delete_webhook


async def main():
    parser = argparse.ArgumentParser(description="BotBuilder Webhook Management Script")
    parser.add_argument("--action", choices=["set", "delete"], default="set", help="Action to perform (set or delete)")
    parser.add_argument("--token", default=TELEGRAM_BOT_TOKEN, help="Telegram Bot API token")
    parser.add_argument("--url", default=f"{PUBLIC_BASE_URL}/telegram/webhook/shared", help="Webhook URL to register")
    parser.add_argument("--secret", default="shared-secret-key", help="Secret token header")

    args = parser.parse_args()

    if not args.token:
        print("Error: No bot token provided and TELEGRAM_BOT_TOKEN is empty in .env")
        sys.exit(1)

    if args.action == "set":
        print(f"Setting webhook for token '{args.token[:8]}...' to '{args.url}'...")
        success = await set_webhook(args.token, args.url, args.secret)
        if success:
            print("✓ Webhook registered successfully!")
        else:
            print("✕ Webhook registration failed.")
    elif args.action == "delete":
        print(f"Deleting webhook for token '{args.token[:8]}...'...")
        success = await delete_webhook(args.token)
        if success:
            print("✓ Webhook deleted successfully!")
        else:
            print("✕ Webhook deletion failed.")

if __name__ == "__main__":
    asyncio.run(main())
