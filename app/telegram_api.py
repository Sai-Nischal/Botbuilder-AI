import httpx
from typing import Optional, Dict, Any, Union, List


BASE_TELEGRAM_URL = "https://api.telegram.org/bot{token}/{method}"


async def get_me(bot_token: str) -> Dict[str, Any]:
    """Validates bot token and returns bot details."""
    url = BASE_TELEGRAM_URL.format(token=bot_token, method="getMe")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        data = resp.json()
        if not data.get("ok"):
            error_msg = data.get("description", "Invalid bot token")
            raise ValueError(f"Telegram API Error: {error_msg}")
        return data.get("result", {})


async def set_webhook(bot_token: str, webhook_url: str, secret_token: str) -> bool:
    """Registers a webhook URL with secret_token header protection."""
    url = BASE_TELEGRAM_URL.format(token=bot_token, method="setWebhook")
    payload = {
        "url": webhook_url,
        "secret_token": secret_token,
        "allowed_updates": ["message", "callback_query"]
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload)
        data = resp.json()
        if not data.get("ok"):
            print(f"Failed to set Telegram webhook ({webhook_url}): {data.get('description')}")
            return False
        return True


async def delete_webhook(bot_token: str) -> bool:
    """Deletes registered webhook for the bot."""
    url = BASE_TELEGRAM_URL.format(token=bot_token, method="deleteWebhook")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json={"drop_pending_updates": True})
        data = resp.json()
        return bool(data.get("ok"))


async def send_message(
    bot_token: str,
    chat_id: Union[int, str],
    text: str,
    reply_markup: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Sends a chat message to Telegram."""
    url = BASE_TELEGRAM_URL.format(token=bot_token, method="sendMessage")
    
    # Telegram message character limit is 4096
    trimmed_text = text[:4000] if len(text) > 4000 else text

    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": trimmed_text,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload)
        return resp.json()


async def answer_callback_query(
    bot_token: str,
    callback_query_id: str,
    text: Optional[str] = None
) -> bool:
    """Answers an inline keyboard callback query."""
    url = BASE_TELEGRAM_URL.format(token=bot_token, method="answerCallbackQuery")
    payload: Dict[str, Any] = {
        "callback_query_id": callback_query_id
    }
    if text:
        payload["text"] = text

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload)
        data = resp.json()
        return bool(data.get("ok"))


async def set_bot_name(bot_token: str, name: str) -> bool:
    """Sets the display name of the bot on Telegram via setMyName API."""
    url = BASE_TELEGRAM_URL.format(token=bot_token, method="setMyName")
    payload = {"name": name[:64]}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            return bool(data.get("ok"))
    except Exception as e:
        print(f"[TELEGRAM API ERROR] setMyName failed for token {bot_token[:10]}...: {e}")
        return False


async def set_bot_description(bot_token: str, description: str) -> bool:
    """Sets the bot description shown before user presses Start via setMyDescription API."""
    url = BASE_TELEGRAM_URL.format(token=bot_token, method="setMyDescription")
    payload = {"description": description[:512]}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            return bool(data.get("ok"))
    except Exception as e:
        print(f"[TELEGRAM API ERROR] setMyDescription failed for token {bot_token[:10]}...: {e}")
        return False


async def set_bot_short_description(bot_token: str, short_description: str) -> bool:
    """Sets the short bio shown on bot profile card via setMyShortDescription API."""
    url = BASE_TELEGRAM_URL.format(token=bot_token, method="setMyShortDescription")
    payload = {"short_description": short_description[:120]}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            return bool(data.get("ok"))
    except Exception as e:
        print(f"[TELEGRAM API ERROR] setMyShortDescription failed for token {bot_token[:10]}...: {e}")
        return False


async def sync_bot_profile(bot_token: str, name: str, description: str, short_description: str) -> bool:
    """Convenience helper to auto-sync Telegram Bot Name, Description, and Bio."""
    if not bot_token or ":" not in bot_token:
        return False
    await set_bot_name(bot_token, name)
    await set_bot_description(bot_token, description)
    await set_bot_short_description(bot_token, short_description)
    print(f"[BOT PROFILE SYNCED] Synced Telegram Name: '{name}', Description & Bio for token {bot_token[:10]}...")
    return True

