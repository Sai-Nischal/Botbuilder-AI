#!/usr/bin/env python3
import asyncio
from typing import Optional
import httpx
from app.config import TELEGRAM_BOT_TOKENS
from app.db import init_db, SessionLocal, Bot
from app.security import decrypt_bot_token
from app.bot_core import process_telegram_update


async def poll_single_bot(token: str, bot_key: Optional[str] = None, bot_name: str = "Bot"):
    if not token or token.startswith("123456789"):
        return

    print(f"[{bot_name}] Starting long polling for token {token[:12]}...")
    url_del = f"https://api.telegram.org/bot{token}/deleteWebhook"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            await client.post(url_del, json={"drop_pending_updates": False})
        except Exception as e:
            print(f"[{bot_name}] deleteWebhook warning: {e}")

    offset = 0
    url_updates = f"https://api.telegram.org/bot{token}/getUpdates"

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            try:
                resp = await client.get(url_updates, params={"offset": offset, "timeout": 15})
                data = resp.json()
                if data.get("ok"):
                    updates = data.get("result", [])
                    for update in updates:
                        update_id = update["update_id"]
                        offset = max(offset, update_id + 1)

                        db = SessionLocal()
                        try:
                            await process_telegram_update(db, update, bot_key=bot_key)
                        except Exception as e:
                            print(f"[{bot_name} POLLING ERROR] Error processing update {update_id}: {e}")
                        finally:
                            db.close()
                elif not data.get("ok"):
                    print(f"[{bot_name}] Telegram API returned error: {data.get('description')}")
                    await asyncio.sleep(10)
            except asyncio.CancelledError:
                print(f"[{bot_name}] Polling stopped.")
                break
            except Exception as e:
                print(f"[{bot_name} CONNECTION ERROR] {e}. Retrying in 5s...")
                await asyncio.sleep(5)


async def run_polling():
    init_db()
    db = SessionLocal()
    tasks = []

    # 1. Shared Bot tokens
    for idx, token in enumerate(TELEGRAM_BOT_TOKENS):
        tasks.append(asyncio.create_task(poll_single_bot(token, bot_key=None, bot_name=f"SharedBot #{idx+1}")))

    # 2. Branded Bot tokens from DB
    branded_bots = db.query(Bot).filter(Bot.mode == "branded", Bot.is_active == True).all()
    for b in branded_bots:
        if b.encrypted_token:
            token = decrypt_bot_token(b.encrypted_token)
            if token:
                name = b.business.name if b.business else b.bot_key
                tasks.append(asyncio.create_task(poll_single_bot(token, bot_key=b.bot_key, bot_name=f"Branded: {name}")))

    db.close()

    if not tasks:
        print("No active bot tokens found to poll.")
        return

    print(f"🚀 Started long polling worker for {len(tasks)} active bot(s)...")
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(run_polling())
    except KeyboardInterrupt:
        print("\nPolling stopped.")
