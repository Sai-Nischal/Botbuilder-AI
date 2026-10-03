#!/usr/bin/env python3
import asyncio
import httpx
from app.config import TELEGRAM_BOT_TOKEN
from app.db import init_db, SessionLocal
from app.bot_core import process_telegram_update


async def run_polling():
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("123456789"):
        print("Warning: TELEGRAM_BOT_TOKEN is not configured in .env file. Please add a valid Telegram bot token from @BotFather.")
        print("Polling process exiting.")
        return

    init_db()
    print("Starting Telegram Shared Bot Long Polling Service...")
    
    # First delete any existing webhook to enable long polling
    url_del = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook"
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(url_del, json={"drop_pending_updates": True})

    offset = 0
    url_updates = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            try:
                resp = await client.get(url_updates, params={"offset": offset, "timeout": 20})
                data = resp.json()
                if data.get("ok"):
                    updates = data.get("result", [])
                    for update in updates:
                        update_id = update["update_id"]
                        offset = max(offset, update_id + 1)

                        db = SessionLocal()
                        try:
                            await process_telegram_update(db, update, bot_key=None)
                        except Exception as e:
                            print(f"[POLLING ERROR] Error processing update {update_id}: {e}")
                        finally:
                            db.close()

            except asyncio.CancelledError:
                print("Polling stopped by user.")
                break
            except Exception as e:
                print(f"[POLLING CONNECTION ERROR] {e}. Retrying in 5 seconds...")
                await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(run_polling())
    except KeyboardInterrupt:
        print("\nPolling stopped.")
