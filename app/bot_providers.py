import secrets
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.config import PUBLIC_BASE_URL, ENABLE_MANAGED_BOTS
from app.db import Business, Bot
from app.security import encrypt_bot_token, decrypt_bot_token
from app.telegram_api import get_me, set_webhook, delete_webhook


class BotProvider(ABC):
    @abstractmethod
    async def connect_bot(self, db: Session, business: Business, token_or_data: str) -> Dict[str, Any]:
        """Connects a Telegram bot to the business."""
        pass

    @abstractmethod
    async def disconnect_bot(self, db: Session, business: Business) -> bool:
        """Disconnects the bot and removes webhooks."""
        pass


class BotFatherProvider(BotProvider):
    async def connect_bot(self, db: Session, business: Business, token: str) -> Dict[str, Any]:
        clean_token = token.strip()
        if not clean_token:
            raise ValueError("Bot token cannot be empty.")

        # 1. Validate token with getMe
        bot_info = await get_me(clean_token)
        bot_username = bot_info.get("username", "")

        # 2. Generate unguessable bot_key and secret_token
        bot_key = secrets.token_urlsafe(16)
        secret_token = secrets.token_urlsafe(32)

        # 3. Form webhook URL
        webhook_url = f"{PUBLIC_BASE_URL}/telegram/webhook/{bot_key}"

        # 4. Register webhook with Telegram
        success = await set_webhook(clean_token, webhook_url, secret_token)
        if not success:
            raise ValueError("Failed to register webhook with Telegram API.")

        # 5. Encrypt token for database storage
        enc_token = encrypt_bot_token(clean_token)

        # 6. Save or update Bot in DB
        existing_bot = db.query(Bot).filter(Bot.business_id == business.business_id).first()
        if existing_bot:
            existing_bot.mode = "branded"
            existing_bot.bot_key = bot_key
            existing_bot.encrypted_token = enc_token
            existing_bot.bot_username = bot_username
            existing_bot.secret_token = secret_token
            existing_bot.is_active = True
        else:
            new_bot = Bot(
                business_id=business.business_id,
                mode="branded",
                bot_key=bot_key,
                encrypted_token=enc_token,
                bot_username=bot_username,
                secret_token=secret_token,
                is_active=True
            )
            db.add(new_bot)

        db.commit()

        return {
            "success": True,
            "bot_username": bot_username,
            "bot_key": bot_key,
            "webhook_url": webhook_url
        }

    async def disconnect_bot(self, db: Session, business: Business) -> bool:
        bot = db.query(Bot).filter(Bot.business_id == business.business_id).first()
        if not bot:
            return True

        if bot.encrypted_token:
            token = decrypt_bot_token(bot.encrypted_token)
            if token:
                await delete_webhook(token)

        # Update bot record to shared mode and clear credentials
        bot.mode = "shared"
        bot.encrypted_token = None
        bot.bot_username = None
        bot.is_active = False
        db.commit()
        return True


class ManagedBotProvider(BotProvider):
    """
    Method 2: Telegram Managed Bots Stub.
    Feature flagged via ENABLE_MANAGED_BOTS (default: false).
    Note: Telegram managed bots require MTProto level user approval flows.
    """
    async def connect_bot(self, db: Session, business: Business, token_or_data: str) -> Dict[str, Any]:
        if not ENABLE_MANAGED_BOTS:
            raise NotImplementedError(
                "Telegram Managed Bots integration is currently disabled (ENABLE_MANAGED_BOTS=false). "
                "Managed bots require MTProto API layer authorization. Please use standard BotFather tokens."
            )
        raise NotImplementedError("Managed bots API handler pending full MTProto client configuration.")

    async def disconnect_bot(self, db: Session, business: Business) -> bool:
        return True
